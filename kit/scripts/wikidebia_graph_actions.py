#!/usr/bin/env python3
"""Apply owner-approved structural graph actions and mirror them safely on FR MediaWiki.

This module bridges an editorial graph review and the historical pages imported by
``graph-extract``.  It supports four action families:

* remove/delete: remove an occurrence and, when the node disappears, delete its page;
* merge_redirect: remove a duplicate node and replace its page by a redirect;
* move: move an occurrence to another immediate parent/root branch;
* relation_change: keep the parent but change justification/objection or root branch.

Remote writes are explicit, revision-guarded and fully preflighted before the first
write.  Parent-page summaries are generated per concrete change.  For duplicate
merges they always mention the retained destination as a wikilink ``[[...]]``.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from wikidebia_corpus_build import (
    CorpusBuildError,
    build_payload_sha256,
    load_json,
    now_iso,
    write_json,
)
from wikidebia_corpus_init import compute_derived, _markdown_graph
from wikidebia_graph_extract import (
    _split_top_level,
    _template_spans,
    iter_templates,
    normalize_key,
    parse_template,
    title_from_template,
)
from wikidebia_publish import PywikibotAdapter
from wikidebia_update import UpdateAdapter, redirect_text, sha_text

ACTION_PLAN_SCHEMA = "wikidebia-graph-action-plan-1.0"
ACTION_RECEIPT_SCHEMA = "wikidebia-graph-action-execution-receipt-1.0"
ACTION_DECISIONS_SCHEMA = "wikidebia-graph-action-decisions-1.0"


def _sha256_file_bytes(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verified_historical_graph_action_mutations(
    project_root: Path, debate_id: str
) -> list[dict[str, Any]]:
    """Return mutations attested by immutable graph-action plans and receipts.

    2.16.4/2.16.5 overwrote ``reviews/graph_action_decisions.json`` after every
    correction round.  The per-run plan and execution receipt under
    ``.state/graph-actions/<debate_id>/`` are therefore the durable source for
    earlier rounds.  Only self-consistent plan/receipt pairs are accepted.
    """
    root = project_root / ".state/graph-actions" / debate_id
    if not root.is_dir():
        return []
    attested: list[dict[str, Any]] = []
    for run_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        plan_path = run_dir / "plan.json"
        receipt_path = run_dir / "execution-receipt.json"
        if not plan_path.is_file() or not receipt_path.is_file():
            continue
        try:
            plan = load_json(plan_path, "plan historique d'actions du graphe")
            receipt = load_json(receipt_path, "reçu historique d'actions du graphe")
        except Exception:
            continue
        if plan.get("schema") != ACTION_PLAN_SCHEMA or receipt.get("schema") != ACTION_RECEIPT_SCHEMA:
            continue
        if str(plan.get("debate_id") or "") != debate_id or str(receipt.get("debate_id") or "") != debate_id:
            continue
        if plan.get("plan_sha256") != _sha_object(plan, "plan_sha256"):
            continue
        if receipt.get("receipt_sha256") != _sha_object(receipt, "receipt_sha256"):
            continue
        if receipt.get("plan_sha256") != plan.get("plan_sha256"):
            continue
        results = receipt.get("results") or []
        if not isinstance(results, list):
            continue
        result_by_key: dict[tuple[str, str], Mapping[str, Any]] = {}
        for result in results:
            if not isinstance(result, Mapping):
                continue
            result_by_key[(str(result.get("title") or ""), str(result.get("operation") or ""))] = result
        mutations = plan.get("mutations") or []
        if not isinstance(mutations, list):
            continue
        for mutation in mutations:
            if not isinstance(mutation, Mapping):
                continue
            operation = str(mutation.get("operation") or "")
            if operation not in {"update", "redirect"}:
                continue
            result = result_by_key.get((str(mutation.get("title") or ""), operation))
            if not result or str(result.get("status") or "") != "written":
                continue
            if result.get("revision_id") is None:
                continue
            expected = mutation.get("expected_revision_id")
            old_revision = result.get("old_revision_id")
            if expected is not None and old_revision is not None:
                try:
                    if int(expected) != int(old_revision):
                        continue
                except (TypeError, ValueError):
                    continue
            row = dict(mutation)
            row["result_revision_id"] = result.get("revision_id")
            row["attestation_source"] = plan_path.relative_to(project_root).as_posix()
            attested.append(row)
    return attested


def repair_graph_action_import_provenance(
    build: Path, *, project_root: Path | None = None, debate_id: str | None = None
) -> dict[str, Any]:
    """Repair historical local provenance omissions after graph actions.

    The repair is deliberately narrow and version-agnostic. It accepts the latest
    local decision audit and, when the project root is supplied, every
    cryptographically self-consistent historical plan/receipt pair. This is
    necessary because older workflows could overwrite ``graph_action_decisions.json``
    after each correction round.  A row
    is refreshed only when the current local wikicode exactly matches an attested
    post-action hash and the recorded remote revision matches the attested written
    revision (or, for the legacy latest-audit fallback, has advanced past the
    pre-action revision).  Unrelated drift remains blocking.
    """
    decisions_path = build / "reviews/graph_action_decisions.json"
    provenance_path = build / "data/import_provenance.json"
    if not provenance_path.is_file():
        return {"status": "not_applicable", "repaired_paths": []}

    mutations: list[dict[str, Any]] = []
    if decisions_path.is_file():
        decisions = load_json(decisions_path, "décisions d'actions du graphe")
        latest = decisions.get("mutations") or []
        if not isinstance(latest, list):
            raise GraphActionError("Historique d'actions invalide pour la réparation")
        mutations.extend(dict(row) for row in latest if isinstance(row, Mapping))

    resolved_debate_id = str(debate_id or "").strip()
    if not resolved_debate_id:
        try:
            registry = load_json(build / "data/registre_debat.json", "registre maître")
            resolved_debate_id = str(registry.get("debate_id") or "").strip()
        except Exception:
            resolved_debate_id = ""
    if project_root is not None and resolved_debate_id:
        mutations.extend(_verified_historical_graph_action_mutations(project_root, resolved_debate_id))

    if not mutations:
        return {"status": "not_applicable", "repaired_paths": []}

    provenance = load_json(provenance_path, "provenance d'import")
    prov_rows = provenance.get("pages") or []
    if not isinstance(prov_rows, list):
        raise GraphActionError("Provenance d'import invalide pour la réparation")
    by_path = {
        str(row.get("import_path")): row
        for row in prov_rows
        if isinstance(row, dict) and row.get("import_path")
    }

    repaired: list[str] = []
    # Prefer later attestations when the same page was touched in several rounds.
    for mutation in reversed(mutations):
        operation = str(mutation.get("operation") or "")
        if operation not in {"update", "redirect"}:
            continue
        rel = str(mutation.get("source_path") or "")
        desired_sha = str(mutation.get("desired_sha256") or "")
        if not rel or not desired_sha or rel in repaired:
            continue
        row = by_path.get(rel)
        path = build / rel
        if row is None or not path.is_file():
            continue

        raw_sha = _sha256_file_bytes(path)
        if str(row.get("sha256") or "") == raw_sha:
            continue
        current_text = path.read_text(encoding="utf-8")
        if sha_text(current_text) != desired_sha:
            continue

        current_revision = row.get("revision_id")
        result_revision = mutation.get("result_revision_id")
        if result_revision is not None:
            try:
                revision_ok = current_revision is not None and int(current_revision) == int(result_revision)
            except (TypeError, ValueError):
                revision_ok = False
        else:
            old_revision = mutation.get("expected_revision_id")
            try:
                revision_ok = old_revision is not None and current_revision is not None and int(current_revision) != int(old_revision)
            except (TypeError, ValueError):
                revision_ok = False
        if not revision_ok:
            continue

        row["sha256"] = raw_sha
        row["size_bytes"] = path.stat().st_size
        repaired.append(rel)

    if repaired:
        write_json(provenance_path, provenance)
    return {"status": "repaired" if repaired else "unchanged", "repaired_paths": repaired}

_MAIN_TEMPLATE = {"debate": "debat", "argument": "argument"}
_RELATION_TEMPLATE = {
    ("debate", "pro"): "Argument pour",
    ("debate", "con"): "Argument contre",
    ("argument", "justification"): "Justification",
    ("argument", "objection"): "Objection",
}
_RELATION_PARAMETER = {
    ("debate", "pro"): "arguments-pour",
    ("debate", "con"): "arguments-contre",
    ("argument", "justification"): "justifications",
    ("argument", "objection"): "objections",
}


class GraphActionError(CorpusBuildError):
    pass


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha_object(value: Mapping[str, Any], excluded: str | None = None) -> str:
    body = copy.deepcopy(dict(value))
    if excluded:
        body.pop(excluded, None)
    return hashlib.sha256(_canonical_bytes(body)).hexdigest()


def _node_title(node_by_id: Mapping[str, Mapping[str, Any]], node_id: str) -> str:
    node = node_by_id.get(node_id)
    if not node:
        raise GraphActionError(f"Nœud inconnu : {node_id}")
    title = str(((node.get("fr") or {}).get("canonical_title") or "")).strip()
    if not title:
        raise GraphActionError(f"Titre français absent pour {node_id}")
    return title


def _structured_action(entry: Mapping[str, Any]) -> dict[str, Any] | None:
    raw = entry.get("correction") or entry.get("graph_action")
    if not isinstance(raw, Mapping):
        return None
    action = str(raw.get("action") or "none").strip()
    if action in {"", "none", "keep"}:
        return None
    result = {"action": action, "occurrence_id": str(entry.get("occurrence_id") or ""), "node_id": str(entry.get("node_id") or "")}
    for key in (
        "target_node_id", "new_parent_occurrence_id", "new_relation", "new_branch",
        "page_disposition", "reason", "edit_summary_parent", "edit_summary_page",
        "preserve_parent_relation",
    ):
        if raw.get(key) is not None:
            result[key] = raw.get(key)
    if raw.get("order") is not None:
        result["order"] = int(raw["order"])
    return result


def _legacy_action(entry: Mapping[str, Any]) -> dict[str, Any] | None:
    """Compatibility for 2.16.2/2.16.3 review ZIPs already returned by ChatGPT.

    Those ZIPs did not yet have a structured correction object.  The owner-approved
    reviews used an explicit, machine-recognisable French formulation.  We accept
    only that narrow formulation; arbitrary prose is never executed.
    """
    rationale = str(entry.get("rationale") or "")
    status = str(entry.get("placement_status") or "")
    oid = str(entry.get("occurrence_id") or "")
    nid = str(entry.get("node_id") or "")
    if "Suppression demandée explicitement par le propriétaire" not in rationale:
        return None
    exact = re.search(r"retirer le n[œo]ud\s+(A\d{4,})", rationale, flags=re.I)
    if not exact or exact.group(1).upper() != nid.upper():
        return None
    targets = re.findall(r"\b(A\d{4,})\s+est conservé", rationale, flags=re.I)
    if status == "needs_merge" and len(targets) == 1:
        return {
            "action": "merge_redirect",
            "occurrence_id": oid,
            "node_id": nid,
            "target_node_id": targets[0].upper(),
            "reason": rationale,
        }
    if not targets:
        return {
            "action": "remove",
            "occurrence_id": oid,
            "node_id": nid,
            "page_disposition": "delete",
            "reason": rationale,
        }
    return None


def extract_actions_from_review(build: Path) -> list[dict[str, Any]]:
    placement = load_json(build / "reviews/graph_placement_review.json", "revue de placement")
    rows = placement.get("entries") or []
    if not isinstance(rows, list):
        raise GraphActionError("reviews/graph_placement_review.json: entries doit être une liste")
    actions: list[dict[str, Any]] = []
    for entry in rows:
        if not isinstance(entry, Mapping):
            continue
        action = _structured_action(entry) or _legacy_action(entry)
        if action:
            actions.append(action)
    return actions


def _main_template_raw(text: str, page_type: str) -> tuple[str, int, int]:
    expected = _MAIN_TEMPLATE[page_type]
    candidates: list[tuple[int, int, str]] = []
    for start, end in _template_spans(text):
        raw = text[start:end]
        parsed = parse_template(raw)
        if parsed and normalize_key(parsed.name) == expected:
            candidates.append((start, end, raw))
    if not candidates:
        raise GraphActionError(f"Modèle principal introuvable pour page {page_type}")
    start, end, raw = max(candidates, key=lambda item: len(item[2]))
    return raw, start, end


def _segment_offsets(inner: str) -> list[tuple[int, int]]:
    """Top-level pipe-delimited segment offsets within a template inner body."""
    offsets: list[tuple[int, int]] = []
    start = 0
    template_stack: list[int] = []
    link_depth = 0
    i = 0
    while i < len(inner):
        if inner.startswith("{{{", i):
            template_stack.append(3); i += 3; continue
        if inner.startswith("{{", i):
            template_stack.append(2); i += 2; continue
        if inner.startswith("}}}", i) and template_stack and template_stack[-1] == 3:
            template_stack.pop(); i += 3; continue
        if inner.startswith("}}", i) and template_stack and template_stack[-1] == 2:
            template_stack.pop(); i += 2; continue
        if inner.startswith("[[", i):
            link_depth += 1; i += 2; continue
        if inner.startswith("]]", i) and link_depth:
            link_depth -= 1; i += 2; continue
        if inner[i] == "|" and not template_stack and not link_depth:
            offsets.append((start, i)); start = i + 1
        i += 1
    offsets.append((start, len(inner)))
    return offsets


def _top_level_equals(segment: str) -> int | None:
    parts = _split_top_level(segment, "=", maxsplit=1)
    if len(parts) != 2:
        return None
    # Find exact top-level '=' offset by the length of the first split component.
    return len(parts[0])


def _replace_parameter_value(text: str, page_type: str, parameter: str, new_value: str, *, create_if_missing: bool = True) -> str:
    raw, start, end = _main_template_raw(text, page_type)
    inner = raw[2:-2]
    wanted = normalize_key(parameter)
    for index, (seg_start, seg_end) in enumerate(_segment_offsets(inner)):
        if index == 0:
            continue
        segment = inner[seg_start:seg_end]
        eq = _top_level_equals(segment)
        if eq is None:
            continue
        key = segment[:eq].strip()
        if normalize_key(key) != wanted:
            continue
        old_value = segment[eq + 1:]
        leading = old_value[: len(old_value) - len(old_value.lstrip(" \t\r\n"))]
        trailing = old_value[len(old_value.rstrip(" \t\r\n")) :]
        replacement = leading + new_value.strip(" \t\r\n") + trailing
        abs_a = start + 2 + seg_start + eq + 1
        abs_b = start + 2 + seg_end
        return text[:abs_a] + replacement + text[abs_b:]
    if not create_if_missing:
        raise GraphActionError(f"Paramètre {parameter} introuvable")
    addition = f"|{parameter}={new_value.strip()}\n"
    # Relations belong before classification/date metadata when possible.
    insert_rel = None
    for candidate in ("rubriques", "mots-clés", "interlangue", "date-création"):
        marker = re.search(rf"(?m)^\|{re.escape(candidate)}=", raw)
        if marker:
            insert_rel = marker.start()
            break
    if insert_rel is None:
        insert_rel = raw.rfind("}}")
    new_raw = raw[:insert_rel] + addition + raw[insert_rel:]
    return text[:start] + new_raw + text[end:]


def _set_optional_parameter_value(text: str, page_type: str, parameter: str, new_value: str) -> str:
    """Set a non-empty top-level value, or omit the parameter when empty."""
    if new_value.strip():
        return _replace_parameter_value(
            text, page_type, parameter, new_value, create_if_missing=True,
        )

    raw, start, end = _main_template_raw(text, page_type)
    inner = raw[2:-2]
    wanted = normalize_key(parameter)
    for index, (seg_start, seg_end) in enumerate(_segment_offsets(inner)):
        if index == 0:
            continue
        segment = inner[seg_start:seg_end]
        eq = _top_level_equals(segment)
        if eq is None or normalize_key(segment[:eq].strip()) != wanted:
            continue
        # ``seg_start`` points just after the top-level pipe. Removing from the
        # pipe through the segment end also consumes its formatting newline.
        abs_a = start + 2 + seg_start - 1
        abs_b = start + 2 + seg_end
        return text[:abs_a] + text[abs_b:]
    return text


def _find_link_model(value: str, template_name: str, child_title: str) -> tuple[int, int, str]:
    matches: list[tuple[int, int, str]] = []
    for start, end in _template_spans(value):
        raw = value[start:end]
        parsed = parse_template(raw)
        if not parsed or normalize_key(parsed.name) != normalize_key(template_name):
            continue
        if title_from_template(parsed) == child_title:
            matches.append((start, end, raw))
    if len(matches) != 1:
        raise GraphActionError(
            f"Lien {template_name} vers {child_title!r} introuvable ou ambigu (trouvé {len(matches)})"
        )
    return matches[0]


def _parameter_value(text: str, page_type: str, parameter: str) -> str:
    raw, _, _ = _main_template_raw(text, page_type)
    parsed = parse_template(raw)
    if not parsed:
        raise GraphActionError("Modèle principal illisible")
    for key, value in parsed.params.items():
        if normalize_key(key) == normalize_key(parameter):
            return value
    return ""


def _remove_link(text: str, page_type: str, family: str, child_title: str) -> tuple[str, str]:
    parameter = _RELATION_PARAMETER[(page_type, family)]
    template_name = _RELATION_TEMPLATE[(page_type, family)]
    value = _parameter_value(text, page_type, parameter)
    a, b, raw = _find_link_model(value, template_name, child_title)
    new_value = value[:a] + value[b:]
    new_text = _set_optional_parameter_value(text, page_type, parameter, new_value)
    return new_text, raw


def _rename_link_model(raw: str, page_type: str, family: str) -> str:
    desired = _RELATION_TEMPLATE[(page_type, family)]
    parsed = parse_template(raw)
    if not parsed:
        raise GraphActionError("Sous-modèle de relation illisible")
    # Replace only the template name at the opening of this exact model.
    return re.sub(r"^\{\{\s*[^|}\n]+", "{{" + desired, raw, count=1)


def _retarget_link_model(raw: str, target_title: str) -> str:
    """Change only page=, retaining the historical label and formatting."""
    inner = raw[2:-2]
    matches = []
    for index, (start, end) in enumerate(_segment_offsets(inner)):
        segment = inner[start:end]
        eq = _top_level_equals(segment)
        if index and eq is not None and normalize_key(segment[:eq].strip()) == "page":
            value = segment[eq + 1:]
            leading = len(value) - len(value.lstrip())
            trailing = len(value.rstrip())
            matches.append((2 + start + eq + 1 + leading, 2 + start + eq + 1 + trailing))
    if len(matches) != 1:
        raise GraphActionError("Une fusion conservant la relation exige un unique paramètre page")
    start, end = matches[0]
    return raw[:start] + target_title + raw[end:]


def _add_link(text: str, page_type: str, family: str, raw_model: str) -> str:
    parameter = _RELATION_PARAMETER[(page_type, family)]
    renamed = _rename_link_model(raw_model, page_type, family)
    value = _parameter_value(text, page_type, parameter)
    if value.strip():
        new_value = value.rstrip() + renamed
    else:
        new_value = renamed
    return _replace_parameter_value(text, page_type, parameter, new_value, create_if_missing=True)


def _family_for_occurrence(occ: Mapping[str, Any], edge_by_id: Mapping[str, Mapping[str, Any]]) -> tuple[str, str]:
    if occ.get("parent_occurrence_id") is None:
        branch = str(occ.get("branch") or "")
        if branch not in {"pro", "con"}:
            raise GraphActionError(f"Branche racine invalide : {occ.get('id')}")
        return "debate", branch
    edge = edge_by_id.get(str(occ.get("edge_id") or "")) or {}
    relation = str(edge.get("relation") or "")
    if relation not in {"justification", "objection"}:
        raise GraphActionError(f"Relation invalide : {occ.get('id')}")
    return "argument", relation


def _page_owner_for_occurrence(occ: Mapping[str, Any], occ_by_id: Mapping[str, Mapping[str, Any]]) -> tuple[str, str | None]:
    parent = occ.get("parent_occurrence_id")
    if parent is None:
        return "debate", None
    parent_occ = occ_by_id.get(str(parent))
    if not parent_occ:
        raise GraphActionError(f"Parent d'occurrence introuvable : {parent}")
    return "argument", str(parent_occ["node_id"])


def _provenance_maps(build: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    prov = load_json(build / "data/import_provenance.json", "provenance d'import")
    debate = None
    arguments: dict[str, Any] = {}
    for row in prov.get("pages") or []:
        if not isinstance(row, dict):
            continue
        if row.get("kind") == "debate":
            debate = row
        elif row.get("kind") == "argument" and row.get("page_id"):
            arguments[str(row["page_id"])] = row
    if debate is None:
        raise GraphActionError("Provenance de la page Débat absente")
    return debate, arguments


def _source_page(build: Path, debate_row: Mapping[str, Any], arg_rows: Mapping[str, Mapping[str, Any]], page_type: str, page_id: str | None) -> tuple[Path, Mapping[str, Any]]:
    row = debate_row if page_type == "debate" else arg_rows.get(str(page_id))
    if not row:
        raise GraphActionError(f"Provenance absente pour {page_type}/{page_id}")
    path = build / str(row.get("import_path") or "")
    if not path.is_file():
        raise GraphActionError(f"Fichier importé absent : {path.relative_to(build)}")
    return path, row


def _summary_join(parts: Sequence[str]) -> str:
    unique: list[str] = []
    for part in parts:
        p = re.sub(r"\s+", " ", str(part)).strip()
        if p and p not in unique:
            unique.append(p)
    text = "; ".join(unique)
    if len(text) > 480:
        text = text[:477].rstrip() + "…"
    if len(text) < 3:
        raise GraphActionError("Résumé de modification individualisé vide")
    return text


def _parent_remove_summary(child_title: str, action: Mapping[str, Any], target_title: str | None) -> str:
    explicit = str(action.get("edit_summary_parent") or "").strip()
    if explicit:
        if action.get("action") == "merge_redirect" and target_title and f"[[{target_title}]]" not in explicit:
            raise GraphActionError("Le résumé parent d'un doublon doit contenir la cible sous forme [[Titre]]")
        return explicit
    if action.get("action") == "merge_redirect" and target_title:
        if action.get("preserve_parent_relation"):
            return f"Remplacement du doublon [[{child_title}]] par [[{target_title}]] ; relation et titre affiché conservés"
        return f"Retrait de l'argument doublon [[{child_title}]] ; argument conservé : [[{target_title}]]"
    if action.get("action") == "remove":
        return f"Retrait de l'argument [[{child_title}]] du graphe du débat"
    return f"Déplacement de l'argument [[{child_title}]] dans le graphe du débat"


def _page_action_summary(child_title: str, action: Mapping[str, Any], target_title: str | None) -> str:
    explicit = str(action.get("edit_summary_page") or "").strip()
    if explicit:
        return explicit
    if action.get("action") == "merge_redirect" and target_title:
        return f"Redirection de l'argument doublon vers [[{target_title}]]"
    if action.get("action") == "remove":
        return f"Suppression de l'argument [[{child_title}]] retiré du graphe"
    return f"Correction du placement de [[{child_title}]] dans le graphe"


def _normalize_actions(actions: Sequence[Mapping[str, Any]], registry: Mapping[str, Any]) -> list[dict[str, Any]]:
    graph = registry.get("graph") or {}
    nodes = [x for x in graph.get("nodes") or [] if x.get("status") == "active"]
    edges = [x for x in graph.get("edges") or [] if x.get("status") == "active"]
    occurrences = list(graph.get("occurrences") or [])
    node_by_id = {str(x["id"]): x for x in nodes}
    occ_by_id = {str(x["id"]): x for x in occurrences}
    children: dict[str, list[str]] = defaultdict(list)
    occs_by_node: dict[str, list[str]] = defaultdict(list)
    for occ in occurrences:
        oid = str(occ["id"]); nid = str(occ["node_id"])
        occs_by_node[nid].append(oid)
        if occ.get("parent_occurrence_id") is not None:
            children[str(occ["parent_occurrence_id"])].append(oid)
    result: list[dict[str, Any]] = []
    seen_occ: set[str] = set()
    for raw in actions:
        row = dict(raw)
        action = str(row.get("action") or "")
        oid = str(row.get("occurrence_id") or "")
        nid = str(row.get("node_id") or "")
        if action not in {"remove", "merge_redirect", "move", "relation_change"}:
            raise GraphActionError(f"Action de graphe inconnue : {action!r}")
        if oid not in occ_by_id or nid not in node_by_id or str(occ_by_id[oid].get("node_id")) != nid:
            raise GraphActionError(f"Action sur occurrence/nœud inconnu : {oid}/{nid}")
        if oid in seen_occ:
            raise GraphActionError(f"Plusieurs actions visent la même occurrence : {oid}")
        seen_occ.add(oid)
        preserve_relation = row.get("preserve_parent_relation", False)
        if type(preserve_relation) is not bool:
            raise GraphActionError("preserve_parent_relation doit être un booléen")
        if preserve_relation and (action != "merge_redirect" or occ_by_id[oid].get("parent_occurrence_id") is None):
            raise GraphActionError("La conservation de relation exige une fusion d'occurrence subordonnée")
        if action in {"remove", "merge_redirect"}:
            if len(occs_by_node[nid]) != 1:
                raise GraphActionError(f"Retrait de page interdit pour {nid}: le nœud possède {len(occs_by_node[nid])} occurrences")
            if children.get(oid):
                raise GraphActionError(f"Retrait de {nid} interdit : l'occurrence {oid} possède encore des enfants")
            if action == "merge_redirect":
                target = str(row.get("target_node_id") or "")
                if target == nid or target not in node_by_id:
                    raise GraphActionError(f"Cible de fusion invalide pour {nid}: {target!r}")
                if preserve_relation:
                    parent = occ_by_id[str(occ_by_id[oid]["parent_occurrence_id"])]["node_id"]
                    relation = (next((e for e in edges if e["id"] == occ_by_id[oid].get("edge_id")), {}) or {}).get("relation")
                    if parent == target or any(e["parent_node_id"] == parent and e["child_node_id"] == target and e["relation"] == relation for e in edges):
                        raise GraphActionError("La fusion créerait une relation réflexive ou déjà présente")
                row["page_disposition"] = "redirect"
            else:
                disposition = str(row.get("page_disposition") or "delete")
                if disposition not in {"delete", "keep"}:
                    raise GraphActionError(f"Disposition de page invalide pour {nid}: {disposition}")
                row["page_disposition"] = disposition
        elif action in {"move", "relation_change"}:
            if action == "relation_change":
                current = occ_by_id[oid]
                row.setdefault("new_parent_occurrence_id", current.get("parent_occurrence_id"))
            new_parent = row.get("new_parent_occurrence_id")
            if new_parent is None:
                branch = str(row.get("new_branch") or "")
                if branch not in {"pro", "con"}:
                    raise GraphActionError(f"new_branch obligatoire pour une racine : {oid}")
                row["new_relation"] = None
            else:
                new_parent = str(new_parent)
                if new_parent not in occ_by_id or new_parent == oid:
                    raise GraphActionError(f"Nouveau parent invalide pour {oid}: {new_parent!r}")
                relation = str(row.get("new_relation") or "")
                if relation not in {"justification", "objection"}:
                    raise GraphActionError(f"new_relation invalide pour {oid}")
                row["new_parent_occurrence_id"] = new_parent
                row["new_branch"] = None
        result.append(row)
    return result


def _refresh_terminal_frontiers(build: Path, registry: Mapping[str, Any], new_graph: Mapping[str, Any], policy: dict) -> None:
    """Reclassify moved frontier pages only when the snapshot proves no children.

    A moved frontier containing unexpanded relations still requires a fresh
    extraction; it must never be silently declared complete.
    """
    if policy.get("limit_policy") != "bounded":
        return
    nodes = {n["id"]: n for n in new_graph["nodes"]}
    _, arguments = _provenance_maps(build)
    retained = []
    for node_id in policy.get("frontier_node_ids") or []:
        node = nodes.get(node_id)
        if node is None:
            continue
        if node["derived"]["minimum_depth"] == policy["maximum_edge_depth"] + 1:
            retained.append(node_id)
            continue
        row = arguments.get(node_id)
        if row is None:
            raise GraphActionError(f"Source de frontière absente : {node_id}")
        text = (build / row["import_path"]).read_text(encoding="utf-8")
        if any(_parameter_value(text, "argument", field).strip() for field in ("justifications", "objections")):
            raise GraphActionError(f"Une nouvelle extraction est nécessaire pour la frontière déplacée {node_id}")
    policy["frontier_node_ids"] = retained


def _rebuild_graph(registry: dict[str, Any], actions: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    graph = registry.get("graph") or {}
    nodes = [copy.deepcopy(x) for x in graph.get("nodes") or [] if x.get("status") == "active"]
    old_edges = [copy.deepcopy(x) for x in graph.get("edges") or [] if x.get("status") == "active"]
    old_occurrences = [copy.deepcopy(x) for x in graph.get("occurrences") or []]
    edge_by_id = {str(x["id"]): x for x in old_edges}
    occ_by_id = {str(x["id"]): x for x in old_occurrences}
    node_by_id = {str(x["id"]): x for x in nodes}
    actions = _normalize_actions(actions, registry)

    removed_occ: set[str] = set()
    removed_node: set[str] = set()
    by_occ_changes: dict[str, dict[str, Any]] = {}
    for action in actions:
        oid, nid = str(action["occurrence_id"]), str(action["node_id"])
        if action["action"] == "merge_redirect" and action.get("preserve_parent_relation"):
            removed_node.add(nid)
            current = copy.deepcopy(occ_by_id[oid])
            current["node_id"] = str(action["target_node_id"])
            current["occurrence_role"] = "secondary"
            by_occ_changes[oid] = current
        elif action["action"] in {"remove", "merge_redirect"}:
            removed_occ.add(oid); removed_node.add(nid)
        else:
            current = copy.deepcopy(occ_by_id[oid])
            current["parent_occurrence_id"] = action.get("new_parent_occurrence_id")
            if current["parent_occurrence_id"] is None:
                current["branch"] = action.get("new_branch")
                current["_relation"] = None
            else:
                current["branch"] = None
                current["_relation"] = action.get("new_relation")
            if action.get("order") is not None:
                current["order"] = int(action["order"])
            by_occ_changes[oid] = current

    remaining_nodes = [x for x in nodes if str(x["id"]) not in removed_node]
    remaining_occ: dict[str, dict[str, Any]] = {}
    for old in old_occurrences:
        oid = str(old["id"])
        if oid in removed_occ:
            continue
        row = by_occ_changes.get(oid, copy.deepcopy(old))
        if "_relation" not in row:
            if row.get("parent_occurrence_id") is None:
                row["_relation"] = None
            else:
                edge = edge_by_id.get(str(row.get("edge_id") or "")) or {}
                row["_relation"] = edge.get("relation")
        remaining_occ[oid] = row

    # No surviving occurrence may point to a removed parent.
    for oid, row in remaining_occ.items():
        parent = row.get("parent_occurrence_id")
        if parent is not None and str(parent) not in remaining_occ:
            raise GraphActionError(f"L'occurrence {oid} pointe vers un parent retiré : {parent}")

    children: dict[str, list[str]] = defaultdict(list)
    roots: list[str] = []
    primaries: dict[str, list[str]] = defaultdict(list)
    for oid, row in remaining_occ.items():
        role = str(row.get("occurrence_role") or "")
        if role not in {"primary", "secondary"}:
            raise GraphActionError(f"occurrence_role invalide pour {oid}")
        if role == "primary":
            primaries[str(row["node_id"])].append(oid)
        parent = row.get("parent_occurrence_id")
        if parent is None:
            if row.get("branch") not in {"pro", "con"}:
                raise GraphActionError(f"Branche racine invalide pour {oid}")
            roots.append(oid)
        else:
            relation = row.get("_relation")
            if relation not in {"justification", "objection"}:
                raise GraphActionError(f"Relation invalide pour {oid}")
            children[str(parent)].append(oid)
    for node in remaining_nodes:
        nid = str(node["id"])
        if len(primaries.get(nid, [])) != 1:
            raise GraphActionError(f"Le nœud {nid} doit conserver exactement une occurrence primaire")
    for parent in children:
        if remaining_occ[parent].get("occurrence_role") != "primary":
            raise GraphActionError(f"Une occurrence secondaire ne peut pas porter d'enfants : {parent}")

    depth: dict[str, int] = {}; branch: dict[str, str] = {}; visiting: set[str] = set(); visited: set[str] = set()
    def visit(oid: str) -> None:
        if oid in visiting:
            raise GraphActionError(f"Cycle d'occurrences détecté autour de {oid}")
        if oid in visited:
            return
        visiting.add(oid); row = remaining_occ[oid]; parent = row.get("parent_occurrence_id")
        if parent is None:
            depth[oid] = 1; branch[oid] = str(row["branch"])
        else:
            parent = str(parent); visit(parent); depth[oid] = depth[parent] + 1; branch[oid] = branch[parent]
        visiting.remove(oid); visited.add(oid)
    for oid in sorted(remaining_occ):
        visit(oid)

    triples: dict[tuple[str, str, str], int] = {}
    for oid, row in remaining_occ.items():
        parent = row.get("parent_occurrence_id")
        if parent is None:
            continue
        parent_node = str(remaining_occ[str(parent)]["node_id"]); child_node = str(row["node_id"]); relation = str(row["_relation"])
        key = (parent_node, child_node, relation)
        triples[key] = min(triples.get(key, int(row.get("order") or 1)), int(row.get("order") or 1))
    sorted_triples = sorted(triples, key=lambda k: (k[0], triples[k], 0 if k[2] == "justification" else 1, k[1]))
    edge_for: dict[tuple[str, str, str], str] = {}
    edges: list[dict[str, Any]] = []
    for idx, key in enumerate(sorted_triples, 1):
        eid = f"E{idx:05d}"; edge_for[key] = eid
        edges.append({
            "id": eid, "parent_node_id": key[0], "child_node_id": key[1], "relation": key[2],
            "order": triples[key], "status": "active", "introduced_in_pass": "graph_owner_actions",
        })
    occurrences: list[dict[str, Any]] = []
    for oid in sorted(remaining_occ):
        row = remaining_occ[oid]; parent = row.get("parent_occurrence_id"); edge_id = None
        if parent is not None:
            key = (str(remaining_occ[str(parent)]["node_id"]), str(row["node_id"]), str(row["_relation"]))
            edge_id = edge_for[key]
        occurrences.append({
            "id": oid, "node_id": str(row["node_id"]),
            "parent_occurrence_id": str(parent) if parent is not None else None,
            "edge_id": edge_id, "branch": branch[oid], "depth": depth[oid],
            "order": int(row.get("order") or 1), "occurrence_role": str(row["occurrence_role"]),
            "render_children": bool(children.get(oid)) and row.get("occurrence_role") == "primary",
        })
    counts, per_node = compute_derived(remaining_nodes, edges, occurrences)
    for node in remaining_nodes:
        node["derived"] = per_node[str(node["id"])]
    return {
        "nodes": remaining_nodes, "edges": edges, "occurrences": occurrences, "derived_counts": counts,
    }, {"removed_nodes": sorted(removed_node), "removed_occurrences": sorted(removed_occ)}


def prepare_action_plan(build: Path, debate_id: str, actions: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    registry = load_json(build / "data/registre_debat.json", "registre maître")
    graph = registry.get("graph") or {}
    nodes = [x for x in graph.get("nodes") or [] if x.get("status") == "active"]
    edges = [x for x in graph.get("edges") or [] if x.get("status") == "active"]
    occurrences = list(graph.get("occurrences") or [])
    node_by_id = {str(x["id"]): x for x in nodes}; edge_by_id = {str(x["id"]): x for x in edges}; occ_by_id = {str(x["id"]): x for x in occurrences}
    actions = _normalize_actions(actions, registry)
    debate_row, arg_rows = _provenance_maps(build)

    desired_by_path: dict[str, str] = {}
    summary_parts: dict[str, list[str]] = defaultdict(list)
    page_meta: dict[str, dict[str, Any]] = {}

    def load_mutable(page_type: str, page_id: str | None) -> tuple[str, str, Mapping[str, Any]]:
        path, prov = _source_page(build, debate_row, arg_rows, page_type, page_id)
        rel = path.relative_to(build).as_posix()
        text = desired_by_path.get(rel, path.read_text(encoding="utf-8"))
        page_meta.setdefault(rel, {"page_type": page_type, "page_id": page_id, "provenance": dict(prov)})
        return rel, text, prov

    normalized_actions: list[dict[str, Any]] = []
    for action in actions:
        action = dict(action); oid = str(action["occurrence_id"]); nid = str(action["node_id"]); occ = occ_by_id[oid]
        child_title = _node_title(node_by_id, nid)
        old_page_type, old_owner = _page_owner_for_occurrence(occ, occ_by_id)
        old_family = _family_for_occurrence(occ, edge_by_id)[1]
        old_rel, old_text, _ = load_mutable(old_page_type, old_owner)
        before_change = old_text
        old_text, raw_model = _remove_link(old_text, old_page_type, old_family, child_title)
        desired_by_path[old_rel] = old_text
        target_title = None
        if action["action"] == "merge_redirect":
            target_title = _node_title(node_by_id, str(action["target_node_id"]))
            if action.get("preserve_parent_relation"):
                parameter = _RELATION_PARAMETER[(old_page_type, old_family)]
                before_removal = _parameter_value(before_change, old_page_type, parameter)
                a, b, original_model = _find_link_model(before_removal, _RELATION_TEMPLATE[(old_page_type, old_family)], child_title)
                desired_by_path[old_rel] = _replace_parameter_value(
                    before_change, old_page_type, parameter,
                    before_removal[:a] + _retarget_link_model(original_model, target_title) + before_removal[b:],
                    create_if_missing=False,
                )
        summary_parts[old_rel].append(_parent_remove_summary(child_title, action, target_title))

        if action["action"] in {"move", "relation_change"}:
            new_parent = action.get("new_parent_occurrence_id")
            if new_parent is None:
                new_page_type, new_owner, new_family = "debate", None, str(action["new_branch"])
                destination_label = "la branche " + ("pour" if new_family == "pro" else "contre")
            else:
                new_parent = str(new_parent); parent_occ = occ_by_id[new_parent]
                new_page_type, new_owner, new_family = "argument", str(parent_occ["node_id"]), str(action["new_relation"])
                destination_label = f"[[{_node_title(node_by_id, new_owner)}]]"
            new_rel, new_text, _ = load_mutable(new_page_type, new_owner)
            new_text = _add_link(new_text, new_page_type, new_family, raw_model)
            desired_by_path[new_rel] = new_text
            if new_rel == old_rel:
                summary_parts[new_rel].append(f"Reclassement de [[{child_title}]] dans le graphe")
            else:
                summary_parts[new_rel].append(f"Ajout de [[{child_title}]] après déplacement vers {destination_label}")

        if action["action"] in {"remove", "merge_redirect"}:
            child_rel, child_text, child_prov = load_mutable("argument", nid)
            disposition = str(action.get("page_disposition") or ("redirect" if action["action"] == "merge_redirect" else "delete"))
            if disposition == "redirect":
                desired_by_path[child_rel] = redirect_text("fr", str(target_title))
            page_meta[child_rel]["disposition"] = disposition
            page_meta[child_rel]["page_summary"] = _page_action_summary(child_title, action, target_title)
            page_meta[child_rel]["redirect_target"] = target_title
        normalized_actions.append(action)

    # Every edited parent gets a precise per-page summary.
    for rel, parts in summary_parts.items():
        page_meta[rel]["page_summary"] = _summary_join(parts)
        page_meta[rel]["disposition"] = "update"

    mutations: list[dict[str, Any]] = []
    for rel in sorted(page_meta):
        meta = page_meta[rel]; prov = meta["provenance"]; path = build / rel; old_text = path.read_text(encoding="utf-8")
        disposition = str(meta.get("disposition") or "update")
        desired = desired_by_path.get(rel)
        if disposition == "delete":
            desired_sha = None
        else:
            if desired is None:
                desired = old_text
            desired_sha = sha_text(desired)
        mutations.append({
            "language": "fr",
            "page_type": meta["page_type"], "page_id": meta["page_id"],
            "title": str(prov.get("canonical_title") or ""), "source_path": rel,
            "expected_revision_id": prov.get("revision_id"), "old_sha256": sha_text(old_text),
            "operation": disposition, "desired_sha256": desired_sha,
            "edit_summary": str(meta.get("page_summary") or ""),
            "redirect_target": meta.get("redirect_target"),
        })
    plan = {
        "schema": ACTION_PLAN_SCHEMA, "schema_version": "1.0", "debate_id": debate_id,
        "prepared_at": now_iso(), "source_build_sha256": build_payload_sha256(build),
        "actions": normalized_actions, "mutations": mutations,
        "plan_sha256": None,
    }
    plan["plan_sha256"] = _sha_object(plan, "plan_sha256")
    new_graph, change_meta = _rebuild_graph(registry, normalized_actions)
    return plan, desired_by_path, {"new_graph": new_graph, **change_meta}


def _local_settings(project_root: Path) -> dict[str, Any]:
    path = project_root / "config/wikidebia.local.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _adapter(project_root: Path) -> tuple[UpdateAdapter, str]:
    private = project_root / "private/pywikibot"
    if not (private / "user-config.py").is_file():
        raise GraphActionError("private/pywikibot/user-config.py est absent")
    settings = _local_settings(project_root)
    family = str(settings.get("family") or "wikidebates")
    expected_user = str(((settings.get("expected_users") or {}).get("fr") or "ChatGPT"))
    base = PywikibotAdapter(
        family=family,
        codes={"fr": "fr"},
        pywikibot_dir=private,
        family_file=project_root / "kit/families" / f"{family}_family.py",
    )
    return UpdateAdapter(base), expected_user


def _verification_policy(project_root: Path) -> tuple[int, float]:
    settings = _local_settings(project_root)
    attempts = max(1, int(settings.get("verification_attempts", 8)))
    delay = max(0.0, float(settings.get("verification_delay_seconds", 2)))
    return attempts, delay


def _verify_written_revision(
    adapter: UpdateAdapter,
    *,
    title: str,
    revision_id: int,
    desired: str,
    summary: str,
    attempts: int,
    delay: float,
) -> dict[str, Any]:
    """Verify the exact revision with bounded retries for MediaWiki replica/tag lag."""
    observed: dict[str, Any] | None = None
    for index in range(attempts):
        observed = adapter.read_revision(title, int(revision_id))
        if (
            observed
            and int(observed.get("revision_id") or 0) == int(revision_id)
            and sha_text(str(observed.get("text") or "")) == sha_text(desired)
            and str(observed.get("summary") or "") == str(summary)
            and "chatgpt" in {str(value) for value in (observed.get("tags") or [])}
        ):
            return observed
        if index + 1 < attempts and delay:
            time.sleep(delay)
    if not observed:
        raise GraphActionError(f"Révision écrite introuvable après {attempts} relectures : {title}")
    if int(observed.get("revision_id") or 0) != int(revision_id):
        raise GraphActionError(f"Identifiant de révision divergent après écriture : {title}")
    if sha_text(str(observed.get("text") or "")) != sha_text(desired):
        raise GraphActionError(f"Contenu distant divergent après écriture : {title}")
    if str(observed.get("summary") or "") != str(summary):
        raise GraphActionError(f"Résumé de modification distant divergent après écriture : {title}")
    if "chatgpt" not in {str(value) for value in (observed.get("tags") or [])}:
        raise GraphActionError(f"Balise chatgpt absente après {attempts} relectures : {title}")
    raise GraphActionError(f"Révision écrite non vérifiable après {attempts} relectures : {title}")


def _verify_remote_preflight(
    adapter: UpdateAdapter,
    plan: Mapping[str, Any],
    *,
    attempts: int,
    delay: float,
) -> dict[str, dict[str, Any]]:
    snapshots: dict[str, dict[str, Any]] = {}
    for row in plan.get("mutations") or []:
        title = str(row["title"]); exists, revision_id, remote_text = adapter.read_page(title)
        op = str(row["operation"]); desired_sha = row.get("desired_sha256")
        if op == "delete" and not exists:
            snapshots[title] = {"status": "already_done", "exists": False, "revision_id": None, "text": ""}; continue
        if op != "delete" and exists and desired_sha and sha_text(remote_text) == desired_sha:
            if revision_id is None:
                raise GraphActionError(f"État final présent sans révision vérifiable : {title}")
            # Idempotent restart after a partially successful previous execution:
            # accept the desired content only if the exact current revision is ours.
            _verify_written_revision(
                adapter, title=title, revision_id=int(revision_id), desired=remote_text,
                summary=str(row.get("edit_summary") or ""), attempts=attempts, delay=delay,
            )
            snapshots[title] = {"status": "already_done", "exists": True, "revision_id": revision_id, "text": remote_text}; continue
        if not exists or revision_id is None:
            raise GraphActionError(f"Page distante attendue absente : {title}")
        expected = row.get("expected_revision_id")
        if expected is None or int(revision_id) != int(expected) or sha_text(remote_text) != row.get("old_sha256"):
            raise GraphActionError(f"Page distante modifiée depuis graph-extract : {title}; aucune écriture n'a été effectuée")
        snapshots[title] = {"status": "ready", "exists": True, "revision_id": revision_id, "text": remote_text}
    return snapshots


def execute_remote_plan(project_root: Path, build: Path, plan: Mapping[str, Any], desired_by_path: Mapping[str, str]) -> dict[str, Any]:
    if plan.get("plan_sha256") != _sha_object(plan, "plan_sha256"):
        raise GraphActionError("Empreinte du plan d'actions divergente")
    adapter, expected_user = _adapter(project_root)
    adapter.open_language("fr", expected_user)
    results: list[dict[str, Any]] = []
    try:
        adapter.assert_identity(expected_user)
        rights = adapter.user_rights()
        required = {"edit"}
        if any(str(x.get("operation")) == "delete" for x in plan.get("mutations") or []):
            required.add("delete")
        missing = sorted(required - rights)
        if missing:
            raise GraphActionError(f"Droits MediaWiki absents : {', '.join(missing)}")
        tags = adapter.available_change_tags()
        if "chatgpt" not in tags:
            raise GraphActionError("La balise MediaWiki 'chatgpt' n'est pas disponible")
        attempts, delay = _verification_policy(project_root)
        snapshots = _verify_remote_preflight(adapter, plan, attempts=attempts, delay=delay)

        # Parent updates first, redirects second, actual deletions last.
        priority = {"update": 10, "redirect": 20, "delete": 30, "keep": 40}
        for row in sorted(plan.get("mutations") or [], key=lambda x: (priority.get(str(x.get("operation")), 99), str(x.get("title")))):
            op = str(row["operation"]); title = str(row["title"]); snap = snapshots[title]
            if snap["status"] == "already_done":
                results.append({"title": title, "operation": op, "status": "already_done", "revision_id": snap.get("revision_id"), "edit_summary": row["edit_summary"]})
                continue
            # Re-read immediately before every mutation to protect against concurrency.
            exists, revision_id, remote_text = adapter.read_page(title)
            if not exists or revision_id != snap["revision_id"] or sha_text(remote_text) != sha_text(snap["text"]):
                raise GraphActionError(f"Conflit distant apparu juste avant l'écriture : {title}")
            if op in {"update", "redirect"}:
                desired = desired_by_path[str(row["source_path"])]
                new_rev = adapter.write_page(
                    title=title, text=desired, summary=str(row["edit_summary"]), tags=["chatgpt"],
                    expected_user=expected_user, create_only=False, base_revision_id=revision_id,
                )
                _verify_written_revision(
                    adapter, title=title, revision_id=new_rev, desired=desired,
                    summary=str(row["edit_summary"]), attempts=attempts, delay=delay,
                )
                results.append({"title": title, "operation": op, "status": "written", "old_revision_id": revision_id, "revision_id": new_rev, "edit_summary": row["edit_summary"]})
            elif op == "delete":
                adapter.delete_page(title=title, reason=str(row["edit_summary"]), expected_user=expected_user)
                after, _, _ = adapter.read_page(title)
                if after:
                    raise GraphActionError(f"Suppression distante non vérifiée : {title}")
                results.append({"title": title, "operation": op, "status": "deleted", "old_revision_id": revision_id, "edit_summary": row["edit_summary"]})
            elif op == "keep":
                results.append({"title": title, "operation": op, "status": "kept", "revision_id": revision_id, "edit_summary": row["edit_summary"]})
            else:
                raise GraphActionError(f"Opération distante inconnue : {op}")
    finally:
        adapter.close_language()
    receipt = {
        "schema": ACTION_RECEIPT_SCHEMA, "schema_version": "1.0", "debate_id": plan["debate_id"],
        "plan_sha256": plan["plan_sha256"], "executed_at": now_iso(), "results": results, "receipt_sha256": None,
    }
    receipt["receipt_sha256"] = _sha_object(receipt, "receipt_sha256")
    return receipt


def apply_local_result(build: Path, plan: Mapping[str, Any], desired_by_path: Mapping[str, str], graph_result: Mapping[str, Any], receipt: Mapping[str, Any]) -> dict[str, Any]:
    registry = load_json(build / "data/registre_debat.json", "registre maître")
    projection = load_json(build / "graph/graphe_argumentatif.json", "projection graphe")
    manifest = load_json(build / "manifest.json", "manifest")
    provenance = load_json(build / "data/import_provenance.json", "provenance d'import")
    node_by_id_before = {str(x["id"]): x for x in (registry.get("graph") or {}).get("nodes") or []}

    # Preserve original imported pages before altering local import snapshots.
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    history_root = build / "history/graph-actions" / stamp
    history_root.mkdir(parents=True, exist_ok=True)
    for row in plan.get("mutations") or []:
        source = build / str(row["source_path"])
        if source.is_file():
            dest = history_root / str(row["source_path"])
            dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, dest)

    result_by_title = {str(x["title"]): x for x in receipt.get("results") or []}
    prov_rows = provenance.get("pages") or []
    for row in plan.get("mutations") or []:
        rel = str(row["source_path"]); source = build / rel; op = str(row["operation"])
        if op in {"update", "redirect"}:
            source.write_text(desired_by_path[rel], encoding="utf-8", newline="\n")
        remote = result_by_title.get(str(row["title"])) or {}
        for prov in prov_rows:
            if prov.get("import_path") == rel:
                if remote.get("revision_id") is not None:
                    prov["revision_id"] = remote.get("revision_id")
                if op in {"update", "redirect"} and source.is_file():
                    prov["sha256"] = _sha256_file_bytes(source)
                    prov["size_bytes"] = source.stat().st_size
                if op == "redirect":
                    prov["status"] = "retired_redirect"; prov["redirect_target"] = row.get("redirect_target")
                elif op == "delete":
                    prov["status"] = "retired_deleted"; prov["deleted_at"] = receipt.get("executed_at")
                elif op == "update":
                    prov["status"] = prov.get("status") or "active_import"
                break

    new_graph = copy.deepcopy(graph_result["new_graph"])
    lifecycle = copy.deepcopy((registry.get("graph") or {}).get("lifecycle") or {})
    lifecycle.update({"status": "draft", "validated_at": None, "locked_at": None, "locked_by_stage": None, "structural_sha256": None})
    depth_policy = copy.deepcopy((registry.get("graph") or {}).get("depth_policy") or {})
    depth_policy.setdefault("limit_policy", "unbounded")
    depth_policy["maximum_observed"] = new_graph["derived_counts"]["maximum_depth"]
    _refresh_terminal_frontiers(build, registry, new_graph, depth_policy)
    registry["graph"] = {"lifecycle": lifecycle, "depth_policy": depth_policy, **new_graph}
    for key in ("lifecycle", "depth_policy", "nodes", "edges", "occurrences", "derived_counts"):
        projection[key] = copy.deepcopy(registry["graph"][key])
    manifest["global_status"] = "graph_draft"; manifest["updated_at"] = now_iso()
    write_json(build / "manifest.json", manifest)
    write_json(build / "data/registre_debat.json", registry)
    write_json(build / "data/import_provenance.json", provenance)
    write_json(build / "graph/graphe_argumentatif.json", projection)
    title = str((projection.get("debate") or {}).get("title_fr") or plan["debate_id"])
    (build / "graph/graphe_argumentatif.md").write_text(
        _markdown_graph(title, new_graph["nodes"], new_graph["edges"], new_graph["occurrences"], new_graph["derived_counts"]),
        encoding="utf-8", newline="\n",
    )
    audit = {
        "schema": ACTION_DECISIONS_SCHEMA, "schema_version": "1.0", "debate_id": plan["debate_id"],
        "applied_at": now_iso(), "plan_sha256": plan["plan_sha256"], "receipt_sha256": receipt["receipt_sha256"],
        "actions": plan.get("actions") or [], "mutations": plan.get("mutations") or [],
        "historical_snapshot_path": history_root.relative_to(build).as_posix(),
    }
    write_json(build / "reviews/graph_action_decisions.json", audit)
    return {"status": "graph_actions_applied", "removed_nodes": graph_result.get("removed_nodes") or [], "remaining_occurrences": len(new_graph["occurrences"])}



def apply_review_actions_locally(
    project_root: Path,
    build: Path,
    debate_id: str,
    *,
    preflight_validator=None,
) -> dict[str, Any]:
    """Apply graph-owner decisions locally and defer every remote write.

    The desired graph is rebuilt now, but imported wikicode remains the exact
    remote snapshot. The first French graph/title checkpoint later materializes
    relation/title changes and executes moves, redirects and deletions together.
    """
    previous = None
    previous_path = build / "reviews/graph_action_decisions.json"
    if previous_path.is_file():
        candidate = load_json(previous_path, "décisions structurelles précédentes")
        if candidate.get("status") == "pending_remote_graph_checkpoint":
            if candidate.get("debate_id") != debate_id or candidate.get("decision_sha256") != _sha_object(candidate, "decision_sha256"):
                raise GraphActionError("Historique des décisions structurelles divergent")
            previous = candidate
    actions = extract_actions_from_review(build)
    if not actions:
        raise GraphActionError("La revue rejetée ne contient aucune décision structurelle exécutable")
    plan, _desired, graph_result = prepare_action_plan(build, debate_id, actions)

    # Validate the prospective graph without mutating the remote snapshot files.
    registry = load_json(build / "data/registre_debat.json", "registre maître")
    projection = load_json(build / "graph/graphe_argumentatif.json", "projection graphe")
    manifest = load_json(build / "manifest.json", "manifest")
    provenance = load_json(build / "data/import_provenance.json", "provenance d'import")
    old_registry = copy.deepcopy(registry)
    old_projection = copy.deepcopy(projection)
    old_manifest = copy.deepcopy(manifest)
    old_provenance = copy.deepcopy(provenance)

    new_graph = copy.deepcopy(graph_result["new_graph"])
    lifecycle = copy.deepcopy((registry.get("graph") or {}).get("lifecycle") or {})
    lifecycle.update({"status": "draft", "validated_at": None, "locked_at": None, "locked_by_stage": None, "structural_sha256": None})
    depth_policy = copy.deepcopy((registry.get("graph") or {}).get("depth_policy") or {})
    depth_policy.setdefault("limit_policy", "unbounded")
    depth_policy["maximum_observed"] = new_graph["derived_counts"]["maximum_depth"]
    _refresh_terminal_frontiers(build, registry, new_graph, depth_policy)
    registry["graph"] = {"lifecycle": lifecycle, "depth_policy": depth_policy, **new_graph}
    for key in ("lifecycle", "depth_policy", "nodes", "edges", "occurrences", "derived_counts"):
        projection[key] = copy.deepcopy(registry["graph"][key])
    manifest["global_status"] = "graph_draft"
    manifest["updated_at"] = now_iso()

    # Keep imported bytes/revisions untouched. Only label removed rows as pending
    # so later active-content reviews do not mistake them for active arguments.
    pending_by_page: dict[str, tuple[str, str | None]] = {}
    for action in plan.get("actions") or []:
        kind = str(action.get("action") or "")
        node_id = str(action.get("node_id") or "")
        if kind == "merge_redirect":
            pending_by_page[node_id] = ("pending_redirect", str(action.get("target_node_id") or ""))
        elif kind == "remove":
            pending_by_page[node_id] = ("pending_delete", None)
    for row in provenance.get("pages") or []:
        if not isinstance(row, dict) or row.get("kind") != "argument":
            continue
        page_id = str(row.get("page_id") or "")
        if page_id in pending_by_page:
            status, target_node_id = pending_by_page[page_id]
            row["status"] = status
            row["pending_remote_graph_checkpoint"] = True
            if target_node_id:
                row["pending_redirect_target_node_id"] = target_node_id

    write_json(build / "manifest.json", manifest)
    write_json(build / "data/registre_debat.json", registry)
    write_json(build / "data/import_provenance.json", provenance)
    write_json(build / "graph/graphe_argumentatif.json", projection)
    title = str((projection.get("debate") or {}).get("title_fr") or debate_id)
    (build / "graph/graphe_argumentatif.md").write_text(
        _markdown_graph(title, new_graph["nodes"], new_graph["edges"], new_graph["occurrences"], new_graph["derived_counts"]),
        encoding="utf-8", newline="\n",
    )
    if preflight_validator is not None:
        try:
            validation = preflight_validator(build)
            if not isinstance(validation, Mapping) or validation.get("status") == "failed":
                raise GraphActionError("La projection locale des décisions structurelles échoue à la validation")
        except Exception:
            write_json(build / "manifest.json", old_manifest)
            write_json(build / "data/registre_debat.json", old_registry)
            write_json(build / "data/import_provenance.json", old_provenance)
            write_json(build / "graph/graphe_argumentatif.json", old_projection)
            raise

    audit = {
        "schema": ACTION_DECISIONS_SCHEMA,
        "schema_version": "1.1",
        "debate_id": debate_id,
        "status": "pending_remote_graph_checkpoint",
        "applied_locally_at": now_iso(),
        "actions": copy.deepcopy(plan.get("actions") or []),
        "mutations": copy.deepcopy(plan.get("mutations") or []),
        "removed_nodes": copy.deepcopy(graph_result.get("removed_nodes") or []),
        "remote_writes_performed": False,
    }
    if previous is not None:
        for field in ("actions", "mutations", "removed_nodes"):
            audit[field] = copy.deepcopy(previous.get(field) or []) + audit[field]
        audit["previous_decision_sha256"] = previous["decision_sha256"]
    audit["decision_sha256"] = _sha_object(audit)
    write_json(build / "reviews/graph_action_decisions.json", audit)
    return {
        "status": "graph_actions_applied_locally",
        "remote_writes_performed": False,
        "removed_nodes": graph_result.get("removed_nodes") or [],
        "remaining_occurrences": len(new_graph["occurrences"]),
        "decision_sha256": audit["decision_sha256"],
    }

def execute_review_actions(
    project_root: Path,
    build: Path,
    debate_id: str,
    *,
    preflight_validator=None,
) -> dict[str, Any]:
    actions = extract_actions_from_review(build)
    if not actions:
        raise GraphActionError("La revue rejetée ne contient aucune décision structurelle exécutable")
    plan, desired, graph_result = prepare_action_plan(build, debate_id, actions)

    # Validate the exact prospective local graph before the first remote write.
    # The temporary receipt only provides revision placeholders required by the local
    # projection; it never authorizes or performs a remote operation.
    if preflight_validator is not None:
        preview_root = Path(tempfile.mkdtemp(prefix=f".{debate_id}-graph-action-preview-", dir=str(build.parent)))
        preview = preview_root / build.name
        try:
            shutil.copytree(build, preview, symlinks=False)
            preview_results = []
            for row in plan.get("mutations") or []:
                op = str(row.get("operation") or "")
                item = {
                    "title": row.get("title"),
                    "operation": op,
                    "status": "preview",
                    "old_revision_id": row.get("expected_revision_id"),
                    "edit_summary": row.get("edit_summary"),
                }
                if op != "delete":
                    item["revision_id"] = row.get("expected_revision_id")
                preview_results.append(item)
            preview_receipt = {
                "schema": ACTION_RECEIPT_SCHEMA,
                "schema_version": "1.0",
                "debate_id": debate_id,
                "plan_sha256": plan["plan_sha256"],
                "executed_at": now_iso(),
                "results": preview_results,
                "receipt_sha256": "preview",
            }
            apply_local_result(preview, plan, desired, graph_result, preview_receipt)
            validation = preflight_validator(preview)
            if not isinstance(validation, Mapping) or validation.get("status") == "failed":
                raise GraphActionError("La projection locale des décisions structurelles échoue à la validation; aucune écriture distante n'a été effectuée")
        finally:
            shutil.rmtree(preview_root, ignore_errors=True)

    run_dir = project_root / ".state/graph-actions" / debate_id / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    write_json(run_dir / "plan.json", plan)
    # The full remote preflight happens inside execute_remote_plan before the first write.
    receipt = execute_remote_plan(project_root, build, plan, desired)
    write_json(run_dir / "execution-receipt.json", receipt)
    local = apply_local_result(build, plan, desired, graph_result, receipt)
    return {
        **local,
        "plan_path": (run_dir / "plan.json").relative_to(project_root).as_posix(),
        "plan_sha256": plan["plan_sha256"],
        "receipt_path": (run_dir / "execution-receipt.json").relative_to(project_root).as_posix(),
        "receipt_sha256": receipt["receipt_sha256"],
        "remote_results": receipt["results"],
    }
