#!/usr/bin/env python3
"""Create a Wikidéb'IA ``graph_draft`` corpus from a graph-extract snapshot.

The command is local-only. It never reads or writes MediaWiki. Source wikitext is
preserved below ``imports/fr`` and is not promoted to normative ``output/fr``
until a later editorial Work.
"""

from __future__ import annotations

from wikidebia_release_info import KIT_VERSION, NORM_VERSION, VALIDATOR_VERSION

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from collections import Counter, defaultdict, deque
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from wikidebia_graph_extract import (
    ARGUMENT_TEMPLATE_KEYS,
    DEBATE_TEMPLATE_KEYS,
    TemplateCall,
    _find_outer,
    _strip_markup,
    iter_templates,
    normalize_key,
)

CORPUS_INIT_VERSION = "1.0.0"
RUBRIQUES = {
    "Aménagement", "Culture", "Droit", "Écologie", "Économie", "Éducation",
    "Éthique", "Géopolitique", "Histoire", "Philosophie", "Politique",
    "Psychologie", "Religion et spiritualité", "Santé", "Science", "Société",
    "Sport et loisirs", "Technologie",
}


class CorpusInitError(RuntimeError):
    pass


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def safe_extract(archive: Path, destination: Path) -> None:
    try:
        with zipfile.ZipFile(archive) as bundle:
            seen: set[str] = set()
            for info in bundle.infolist():
                name = PurePosixPath(info.filename)
                if name.is_absolute() or ".." in name.parts or re.match(r"^[A-Za-z]:", info.filename):
                    raise CorpusInitError(f"Chemin ZIP dangereux : {info.filename}")
                normalized = name.as_posix()
                if normalized in seen:
                    raise CorpusInitError(f"Entrée ZIP dupliquée : {info.filename}")
                seen.add(normalized)
                mode = (info.external_attr >> 16) & 0o170000
                if mode == stat.S_IFLNK:
                    raise CorpusInitError(f"Lien symbolique interdit dans le ZIP : {info.filename}")
            bundle.extractall(destination)
    except zipfile.BadZipFile as exc:
        raise CorpusInitError(f"Archive ZIP invalide : {archive}") from exc


def normalize_title(value: str) -> tuple[str, list[str]]:
    original = unicodedata.normalize("NFC", str(value or ""))
    value = " ".join(original.replace("_", " ").split())
    changes: list[str] = []
    replacements = {"’": "'", "‘": "'", "“": '"', "”": '"', "«": '"', "»": '"'}
    for old, new in replacements.items():
        if old in value:
            value = value.replace(old, new)
            changes.append(f"{old}->{new}")
    value = value.rstrip(".").strip()
    if value != original and not changes:
        changes.append("normalisation_espaces_ou_point_final")
    if not value:
        raise CorpusInitError("Titre vide après normalisation")
    return value, changes


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return value or "debat"


def _alphabetical_key(value: str) -> str:
    folded = unicodedata.normalize("NFKD", str(value).casefold())
    return "".join(ch for ch in folded if not unicodedata.combining(ch))


def canonical_debate_id(value: str) -> str:
    result = slugify(value)
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,63}", result):
        raise CorpusInitError(f"debate_id invalide : {result}")
    return result


def validate_short_code(value: str) -> str:
    candidate = str(value or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9_-]{2,12}", candidate):
        raise CorpusInitError("short_code doit contenir 2 à 12 caractères A-Z, 0-9, _ ou -")
    return candidate


def derive_short_code(debate_id: str) -> str:
    """Derive a deterministic ASCII short code from the canonical debate id.

    The title itself is deliberately not used here: canonical_debate_id has
    already removed accents and punctuation, so the generated code can never
    contain a character that the short-code validator subsequently rejects.
    """
    canonical = canonical_debate_id(debate_id)
    parts = [part for part in re.split(r"[_-]+", canonical) if part]
    initials = "".join(part[0] for part in parts).upper()[:8]
    if len(initials) >= 2:
        return validate_short_code(initials)
    compact = re.sub(r"[^a-z0-9]", "", canonical).upper()[:8]
    return validate_short_code(compact)


def _split_metadata(value: str) -> list[str]:
    if not value.strip():
        return []
    template_values: list[str] = []
    for call in iter_templates(value):
        key = normalize_key(call.name)
        if key in {"rubrique", "section", "mot cle", "mot-clé", "keyword"}:
            candidate = call.get("page", "nom", "name", "mot-clé", "mot cle")
            if not candidate and call.positional:
                candidate = call.positional[0]
            candidate = _strip_markup(candidate)
            if candidate:
                template_values.append(candidate)
    if template_values:
        return list(dict.fromkeys(template_values))
    plain = re.sub(r"\{\{.*?\}\}", "", value, flags=re.DOTALL)
    parts = re.split(r"\s*(?:;|,|\n|\||•|·)\s*", plain)
    return list(dict.fromkeys(_strip_markup(part) for part in parts if _strip_markup(part)))


def extract_page_metadata(text: str, *, debate: bool = False) -> dict[str, Any]:
    calls = iter_templates(text)
    outer = _find_outer(calls, DEBATE_TEMPLATE_KEYS if debate else ARGUMENT_TEMPLATE_KEYS)
    if outer is None:
        raise CorpusInitError("Modèle principal Débat/Argument introuvable dans une page importée")
    rubriques = [item for item in _split_metadata(outer.get("rubriques", "sections")) if item in RUBRIQUES]
    keywords = _split_metadata(outer.get("mots-clés", "mots cles", "mots clés", "keywords"))
    creation_date = outer.get("date-création", "date creation", "creation-date", "creation date").strip() or None
    return {
        "rubriques": rubriques,
        "keywords": keywords,
        "creation_date": creation_date,
    }


@dataclasses.dataclass(frozen=True)
class ExtractionInput:
    root: Path
    graph_path: Path
    snapshot_manifest_path: Path
    cleanup: Path | None = None


def _find_single(root: Path, patterns: Sequence[str], label: str) -> Path:
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(root.rglob(pattern))
    candidates = sorted({path.resolve() for path in candidates if path.is_file()})
    if len(candidates) != 1:
        raise CorpusInitError(f"{label}: un fichier attendu, trouvé {len(candidates)}")
    return candidates[0]


def resolve_extraction_input(source: Path) -> ExtractionInput:
    source = source.expanduser().resolve()
    cleanup: Path | None = None
    if source.is_file() and source.suffix.lower() == ".zip":
        cleanup = Path(tempfile.mkdtemp(prefix="wikidebia-corpus-init-"))
        safe_extract(source, cleanup)
        root = cleanup
    elif source.is_file() and source.name == "snapshot_manifest.json":
        root = source.parent.parent
    elif source.is_dir():
        root = source
    else:
        raise CorpusInitError(f"Source introuvable ou non prise en charge : {source}")

    snapshot = _find_single(root, ["snapshot_manifest.json"], "Manifeste de snapshot")
    graph_candidates = [
        path for path in root.rglob("*.json")
        if path.is_file() and "graphe_recursif" in path.name and not path.name.endswith("manifest_sha256.json")
    ]
    if len(graph_candidates) != 1:
        raise CorpusInitError(f"Graphe d'extraction: un fichier attendu, trouvé {len(graph_candidates)}")
    return ExtractionInput(root=root, graph_path=graph_candidates[0], snapshot_manifest_path=snapshot, cleanup=cleanup)


def verify_extraction(inp: ExtractionInput) -> tuple[dict[str, Any], dict[str, Any]]:
    graph = json.loads(inp.graph_path.read_text(encoding="utf-8"))
    snapshot = json.loads(inp.snapshot_manifest_path.read_text(encoding="utf-8"))
    if snapshot.get("schema") != "wikidebia-graph-snapshot-1.0":
        raise CorpusInitError("Schéma de snapshot non pris en charge")
    rows = [snapshot.get("debate") or {}, *(snapshot.get("arguments") or [])]
    for row in rows:
        rel = row.get("relative_path")
        if not rel:
            raise CorpusInitError("Chemin absent dans le snapshot")
        path = inp.snapshot_manifest_path.parent / rel
        if not path.is_file():
            raise CorpusInitError(f"Page du snapshot absente : {rel}")
        if sha256_file(path) != row.get("sha256"):
            raise CorpusInitError(f"Empreinte invalide dans le snapshot : {rel}")
    package_manifests = list(inp.root.rglob("*_manifest_sha256_*.json"))
    verified_package_files: set[Path] = set()
    for path in package_manifests:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != "wikidebia-graph-extraction-package-1.0":
            continue
        if data.get("audit_status") != "passed":
            raise CorpusInitError("Le paquet d'extraction n'a pas réussi son audit")
        files = data.get("files") or []
        if data.get("declared_file_count") != len(files):
            raise CorpusInitError("Le manifeste du paquet d'extraction a un compteur de fichiers incohérent")
        manifest_root = path.parent.resolve()
        for item in files:
            rel = PurePosixPath(str(item.get("path") or ""))
            if not rel.parts or rel.is_absolute() or ".." in rel.parts:
                raise CorpusInitError(f"Chemin invalide dans le manifeste d'extraction : {item.get('path')}")
            candidate = (manifest_root / Path(*rel.parts)).resolve()
            try:
                candidate.relative_to(manifest_root)
            except ValueError as exc:
                raise CorpusInitError(f"Chemin extérieur au paquet d'extraction : {rel.as_posix()}") from exc
            if not candidate.is_file():
                raise CorpusInitError(f"Fichier déclaré absent du paquet d'extraction : {rel.as_posix()}")
            payload = candidate.read_bytes()
            if len(payload) != item.get("size_bytes"):
                raise CorpusInitError(f"Taille invalide dans le paquet d'extraction : {rel.as_posix()}")
            if sha256_bytes(payload) != item.get("sha256"):
                raise CorpusInitError(f"Empreinte invalide dans le paquet d'extraction : {rel.as_posix()}")
            verified_package_files.add(candidate)
    if verified_package_files:
        if inp.graph_path.resolve() not in verified_package_files:
            raise CorpusInitError("Le graphe récursif n'est pas couvert par le manifeste audité")
        if inp.snapshot_manifest_path.resolve() not in verified_package_files:
            raise CorpusInitError("Le manifeste de snapshot n'est pas couvert par le manifeste audité")
    return graph, snapshot


def ordered_titles(graph: Mapping[str, Any]) -> list[str]:
    roots = [*(graph.get("arguments_pour_niveau_1") or []), *(graph.get("arguments_contre_niveau_1") or [])]
    relations = graph.get("relations") or []
    adjacency: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in relations:
        adjacency[str(edge["source"])].append(edge)
    for edges in adjacency.values():
        edges.sort(key=lambda e: (int(e.get("ordre") or 1), 0 if e.get("relation") == "justification" else 1, str(e["cible"]).casefold()))
    seen: set[str] = set()
    order: list[str] = []
    queue = deque(str(item) for item in roots)
    while queue:
        title = queue.popleft()
        if title in seen:
            continue
        seen.add(title)
        order.append(title)
        queue.extend(str(edge["cible"]) for edge in adjacency.get(title, []))
    all_titles = {str(row["titre"]) for row in graph.get("noeuds") or []}
    all_titles.update(str(edge["source"]) for edge in relations)
    all_titles.update(str(edge["cible"]) for edge in relations)
    order.extend(sorted(all_titles - seen, key=str.casefold))
    return order


def choose_displayed_title(node_row: Mapping[str, Any], canonical: str) -> str:
    values = node_row.get("titres_affichés_observés") or []
    if isinstance(values, str):
        try:
            decoded = json.loads(values)
            values = decoded if isinstance(decoded, list) else [values]
        except json.JSONDecodeError:
            values = [item.strip() for item in values.split(";") if item.strip()]
    candidates: list[str] = []
    for value in values:
        normalized, _ = normalize_title(str(value))
        if normalized:
            candidates.append(normalized)
    return min(candidates, key=lambda item: (len(item), item.casefold())) if candidates else canonical


def make_empty_page_record(path: str, *, interlanguage: bool) -> dict[str, Any]:
    return {
        "generation": {
            "status": "pending",
            "assigned_batch_id": None,
            "creation_date": None,
            "generated_at": None,
            "validated_at": None,
        },
        "file": {"path": path, "sha256": None, "status": "absent"},
        "wiki": {
            "check_status": "unchecked",
            "decision": None,
            "remote_revision_id": None,
            "remote_sha256": None,
            "published_at": None,
            "checked_at": None,
            "remote_title": None,
        },
        "interlanguage": (
            {
                "status": "pending",
                "target_language": "en",
                "target_title": None,
                "inserted_at": None,
                "verified_at": None,
            }
            if interlanguage
            else {"status": "not_applicable"}
        ),
    }


def compute_derived(nodes: list[dict[str, Any]], edges: list[dict[str, Any]], occurrences: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for occ in occurrences:
        by_node[occ["node_id"]].append(occ)
    outgoing = Counter(edge["parent_node_id"] for edge in edges)
    edge_by_id = {edge["id"]: edge for edge in edges}
    just = Counter()
    obj = Counter()
    for occ in occurrences:
        edge = edge_by_id.get(occ.get("edge_id"))
        if edge:
            (just if edge["relation"] == "justification" else obj)[str(occ["depth"])] += 1
    per_node: dict[str, dict[str, Any]] = {}
    for node in nodes:
        occs = by_node[node["id"]]
        primaries = [occ for occ in occs if occ["occurrence_role"] == "primary"]
        per_node[node["id"]] = {
            "occurrence_count": len(occs),
            "minimum_depth": min(occ["depth"] for occ in occs),
            "maximum_depth": max(occ["depth"] for occ in occs),
            "is_main_argument_anywhere": any(occ["depth"] == 1 for occ in occs),
            "is_reused": len(occs) >= 2,
            "primary_occurrence_id": primaries[0]["id"] if len(primaries) == 1 else None,
        }
    counts = {
        "main_pro": sum(occ["depth"] == 1 and occ["branch"] == "pro" for occ in occurrences),
        "main_con": sum(occ["depth"] == 1 and occ["branch"] == "con" for occ in occurrences),
        "justifications_by_depth": dict(sorted(just.items(), key=lambda item: int(item[0]))),
        "objections_by_depth": dict(sorted(obj.items(), key=lambda item: int(item[0]))),
        "distinct_nodes": len(nodes),
        "total_occurrences": len(occurrences),
        "reused_nodes": sum(len(value) >= 2 for value in by_node.values()),
        "additional_reuses": len(occurrences) - len(nodes),
        "developed_nodes": sum(outgoing[node["id"]] > 0 for node in nodes),
        "leaf_nodes": sum(outgoing[node["id"]] == 0 for node in nodes),
        "maximum_depth": max((occ["depth"] for occ in occurrences), default=0),
    }
    return counts, per_node


def build_graph_objects(graph: Mapping[str, Any], page_metadata: Mapping[str, dict[str, Any]], debate_metadata: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], dict[str, str], list[dict[str, Any]]]:
    titles = ordered_titles(graph)
    canonical_sources: dict[str, list[str]] = defaultdict(list)
    for source_title in titles:
        canonical, _ = normalize_title(source_title)
        canonical_sources[canonical.casefold()].append(source_title)
    collisions = [values for values in canonical_sources.values() if len(values) > 1]
    if collisions:
        raise CorpusInitError(
            "Collision de titres après normalisation : "
            + "; ".join(" / ".join(values) for values in collisions[:5])
        )
    title_to_id = {title: f"A{index:04d}" for index, title in enumerate(titles, start=1)}
    rows_by_title = {str(row["titre"]): row for row in graph.get("noeuds") or []}
    normalizations: list[dict[str, Any]] = []

    all_rubriques = [rub for meta in page_metadata.values() for rub in meta.get("rubriques", [])]
    debate_rubriques = debate_metadata.get("rubriques", [])
    fallback_rubrique = (Counter(all_rubriques).most_common(1)[0][0] if all_rubriques else (debate_rubriques[0] if debate_rubriques else None))
    debate_keywords = debate_metadata.get("keywords", [])

    nodes: list[dict[str, Any]] = []
    for title in titles:
        canonical, changes = normalize_title(title)
        if changes:
            normalizations.append({"source_title": title, "registry_title": canonical, "changes": changes})
        row = rows_by_title.get(title, {})
        existing_english_title = str(
            row.get("traduction_anglaise_existante") or ""
        ).strip()
        reuse_existing_english = bool(
            row.get("traduction_anglaise_existante_vérifiée")
            and existing_english_title
            and row.get("traduction_anglaise_requise") is False
        )
        displayed = choose_displayed_title(row, canonical)
        meta = page_metadata.get(title, {})
        rubriques = list(meta.get("rubriques") or [])
        keywords = list(meta.get("keywords") or [])
        fallbacks: list[str] = []
        if not rubriques:
            if not fallback_rubrique:
                raise CorpusInitError(f"Rubrique absente pour {title!r} et aucun repli déterminable")
            rubriques = [fallback_rubrique]
            fallbacks.append(f"rubrique:{fallback_rubrique}")
        if not keywords:
            keyword = debate_keywords[0] if debate_keywords else slugify(graph["metadata"]["débat"]).replace("_", " ")
            keywords = [keyword]
            fallbacks.append(f"mot-clé:{keyword}")
        fr_page = make_empty_page_record(
            f"output/fr/arguments/{title_to_id[title]}.wiki", interlanguage=True
        )
        en_page = make_empty_page_record(
            f"output/en/arguments/{title_to_id[title]}.wiki", interlanguage=False
        )
        if reuse_existing_english:
            checked_at = str(
                row.get("vérification_traduction_anglaise_effectuée_le") or now_iso()
            )
            fr_page["interlanguage"].update(
                {"status": "ready", "target_title": existing_english_title}
            )
            en_page["generation"]["status"] = "obsolete"
            en_page["wiki"].update(
                {
                    "check_status": "equivalent_existing",
                    "decision": "reuse_existing",
                    "remote_revision_id": row.get(
                        "revision_traduction_anglaise_existante"
                    ),
                    "remote_title": existing_english_title,
                    "checked_at": checked_at,
                }
            )
        node = {
            "id": title_to_id[title],
            "status": "active",
            "fr": {
                "canonical_title": canonical,
                "displayed_title": displayed,
                "title_status": "draft",
                # A graph-extract import is a reprise of wiki content.  Preserve
                # the complete historical rubric set; creation-count rules are
                # reviewed later and must not truncate pre-existing metadata.
                "rubriques": sorted(dict.fromkeys(rubriques), key=_alphabetical_key),
                "keywords": list(dict.fromkeys(keywords)),
            },
            "en": {
                "canonical_title": existing_english_title if reuse_existing_english else None,
                "displayed_title": existing_english_title if reuse_existing_english else None,
                "title_status": "locked" if reuse_existing_english else "unassigned",
                "sections": [],
                "keywords": [],
            },
            "pages": {
                "fr": fr_page,
                "en": en_page,
            },
            "sources": {
                "fr": {"bibliography": [], "webliography": [], "videography": []},
                "en": {"bibliography": [], "webliography": [], "videography": []},
            },
            "derived": None,
        }
        nodes.append(node)
        if fallbacks:
            normalizations.append({"source_title": title, "registry_title": canonical, "metadata_fallbacks": fallbacks})

    relation_rows = list(graph.get("relations") or [])
    relation_rows.sort(key=lambda edge: (title_to_id[str(edge["source"])], int(edge.get("ordre") or 1), 0 if edge.get("relation") == "justification" else 1, title_to_id[str(edge["cible"])]))
    edges: list[dict[str, Any]] = []
    for index, row in enumerate(relation_rows, start=1):
        edges.append({
            "id": f"E{index:05d}",
            "parent_node_id": title_to_id[str(row["source"])],
            "child_node_id": title_to_id[str(row["cible"])],
            "relation": str(row["relation"]),
            "order": int(row.get("ordre") or 1),
            "status": "active",
            "introduced_in_pass": "wiki_snapshot_import",
        })

    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    incoming_count = Counter(edge["child_node_id"] for edge in edges)
    for edge in edges:
        outgoing[edge["parent_node_id"]].append(edge)

    roots_pro = [title_to_id[str(title)] for title in graph.get("arguments_pour_niveau_1") or []]
    roots_con = [title_to_id[str(title)] for title in graph.get("arguments_contre_niveau_1") or []]
    occurrences: list[dict[str, Any]] = []
    primary_by_node: dict[str, dict[str, Any]] = {}

    def add_occ(node_id: str, parent: dict[str, Any] | None, edge: dict[str, Any] | None, branch: str, order: int) -> dict[str, Any]:
        primary = node_id not in primary_by_node
        occ = {
            "id": f"O{len(occurrences)+1:05d}",
            "node_id": node_id,
            "parent_occurrence_id": parent["id"] if parent else None,
            "edge_id": edge["id"] if edge else None,
            "branch": branch,
            "depth": (parent["depth"] + 1) if parent else 1,
            "order": order,
            "occurrence_role": "primary" if primary else "secondary",
            "render_children": bool(outgoing.get(node_id)) if primary else False,
        }
        occurrences.append(occ)
        if primary:
            primary_by_node[node_id] = occ
        return occ

    for order, node_id in enumerate(roots_pro, start=1):
        add_occ(node_id, None, None, "pro", order)
    for order, node_id in enumerate(roots_con, start=1):
        add_occ(node_id, None, None, "con", order)

    queue = deque([*roots_pro, *roots_con])
    processed: set[str] = set()
    while queue:
        parent_id = queue.popleft()
        if parent_id in processed:
            continue
        processed.add(parent_id)
        parent_occ = primary_by_node.get(parent_id)
        if parent_occ is None:
            raise CorpusInitError(f"Occurrence primaire absente pour {parent_id}")
        for edge in outgoing.get(parent_id, []):
            child_id = edge["child_node_id"]
            was_new = child_id not in primary_by_node
            add_occ(child_id, parent_occ, edge, parent_occ["branch"], edge["order"])
            if was_new:
                queue.append(child_id)

    missing_occ = [node["id"] for node in nodes if node["id"] not in primary_by_node]
    if missing_occ:
        raise CorpusInitError(f"Nœuds inaccessibles sans occurrence primaire : {missing_occ[:5]}")

    counts, per_node = compute_derived(nodes, edges, occurrences)
    for node in nodes:
        node["derived"] = per_node[node["id"]]
    return nodes, edges, occurrences, counts, title_to_id, normalizations


def _markdown_graph(debate_title: str, nodes: list[dict[str, Any]], edges: list[dict[str, Any]], occurrences: list[dict[str, Any]], counts: dict[str, Any]) -> str:
    title_by_id = {node["id"]: node["fr"]["canonical_title"] for node in nodes}
    lines = [
        f"# Graphe argumentatif importé — {debate_title}", "",
        "Statut : brouillon importé, non verrouillé.", "",
        "## Compteurs normatifs", "",
        f"- Nœuds distincts : {counts['distinct_nodes']}",
        f"- Relations : {len(edges)}",
        f"- Occurrences normatives : {counts['total_occurrences']}",
        f"- Réutilisations supplémentaires : {counts['additional_reuses']}",
        f"- Profondeur maximale : {counts['maximum_depth']}", "",
        "## Arguments principaux", "",
    ]
    for branch, label in (("pro", "Pour"), ("con", "Contre")):
        lines.append(f"### {label}")
        lines.append("")
        for occ in [item for item in occurrences if item["depth"] == 1 and item["branch"] == branch]:
            lines.append(f"- `{occ['node_id']}` {title_by_id[occ['node_id']]}")
        lines.append("")
    lines.extend(["## Relations", ""])
    for edge in edges:
        lines.append(f"- `{edge['id']}` `{edge['parent_node_id']}` → **{edge['relation']}** → `{edge['child_node_id']}`")
    return "\n".join(lines) + "\n"


def _depth_policy(
    graph: Mapping[str, Any], title_to_id: Mapping[str, str], maximum_observed: int
) -> dict[str, Any]:
    metadata = graph.get("metadata") or {}
    requested = metadata.get("limite_profondeur")
    if requested is None:
        return {"limit_policy": "unbounded", "maximum_observed": maximum_observed}
    frontier = graph.get("frontières_profondeur") or {}
    if not isinstance(frontier, Mapping):
        raise CorpusInitError("Frontières de profondeur invalides dans le snapshot")
    frontier_ids: list[str] = []
    for title in frontier:
        node_id = title_to_id.get(str(title))
        if node_id is None:
            normalized, _ = normalize_title(str(title))
            node_id = next(
                (candidate for source, candidate in title_to_id.items() if normalize_title(source)[0] == normalized),
                None,
            )
        if node_id is None:
            raise CorpusInitError(f"Frontière de profondeur sans nœud actif : {title}")
        frontier_ids.append(node_id)
    return {
        "limit_policy": "bounded",
        "maximum_observed": maximum_observed,
        "maximum_edge_depth": int(requested),
        "frontier_node_ids": sorted(set(frontier_ids)),
        "relations_omitted_at_frontier": int(metadata.get("relations_ignorees_limite_profondeur") or 0),
    }


def copy_import_pages(inp: ExtractionInput, snapshot: Mapping[str, Any], output_root: Path, title_to_id: Mapping[str, str]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    snapshot_root = inp.snapshot_manifest_path.parent
    imported: dict[str, dict[str, Any]] = {}
    provenance_rows: list[dict[str, Any]] = []

    debate_row = snapshot["debate"]
    debate_source = snapshot_root / debate_row["relative_path"]
    debate_target = output_root / "imports/fr/debate/debate.wiki"
    debate_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(debate_source, debate_target)
    debate_meta = extract_page_metadata(debate_target.read_text(encoding="utf-8"), debate=True)
    provenance_rows.append({**debate_row, "page_id": None, "import_path": debate_target.relative_to(output_root).as_posix(), "kind": "debate"})

    rows_by_title = {str(row["canonical_title"]): row for row in snapshot.get("arguments") or []}
    for source_title, node_id in title_to_id.items():
        row = rows_by_title.get(source_title)
        if row is None:
            normalized_source, _ = normalize_title(source_title)
            for title, candidate in rows_by_title.items():
                normalized_candidate, _ = normalize_title(title)
                if normalized_candidate == normalized_source:
                    row = candidate
                    break
        if row is None:
            raise CorpusInitError(f"Page absente du snapshot pour le nœud : {source_title}")
        source = snapshot_root / row["relative_path"]
        target = output_root / f"imports/fr/arguments/{node_id}.wiki"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        imported[source_title] = extract_page_metadata(target.read_text(encoding="utf-8"), debate=False)
        provenance_rows.append({**row, "page_id": node_id, "import_path": target.relative_to(output_root).as_posix(), "kind": "argument", "source_graph_title": source_title})

    provenance = {
        "schema": "wikidebia-import-provenance-1.0",
        "kit_version": KIT_VERSION,
        "corpus_init_version": CORPUS_INIT_VERSION,
        "source_snapshot_schema": snapshot.get("schema"),
        "source_extraction_date": snapshot.get("extraction_date"),
        "imported_at": now_iso(),
        "pages": provenance_rows,
    }
    return imported, {"debate_metadata": debate_meta, "provenance": provenance}


def build_corpus(
    source: Path,
    output_dir: Path,
    *,
    debate_id: str | None,
    short_code: str | None,
    scope_summary: str | None,
    overwrite: bool,
) -> dict[str, Any]:
    inp = resolve_extraction_input(source)
    try:
        graph, snapshot = verify_extraction(inp)
        debate_title_source = str(graph.get("metadata", {}).get("débat") or snapshot["debate"]["canonical_title"])
        debate_title, debate_title_changes = normalize_title(debate_title_source)
        debate_id = canonical_debate_id(debate_id or debate_title)
        short_code = validate_short_code(short_code) if short_code else derive_short_code(debate_id)
        output_dir = output_dir.expanduser().resolve()
        if output_dir.exists():
            if not overwrite:
                raise CorpusInitError(f"Le dossier existe déjà : {output_dir}; utiliser --overwrite")
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True)

        # A first pass gives stable IDs, then source pages are copied and parsed.
        title_order = ordered_titles(graph)
        provisional_ids = {title: f"A{index:04d}" for index, title in enumerate(title_order, start=1)}
        page_metadata, import_data = copy_import_pages(inp, snapshot, output_dir, provisional_ids)
        debate_metadata = import_data["debate_metadata"]
        nodes, edges, occurrences, counts, title_to_id, normalizations = build_graph_objects(graph, page_metadata, debate_metadata)
        if title_to_id != provisional_ids:
            raise CorpusInitError("Instabilité interne des identifiants de nœud")

        timestamp = now_iso()
        depth_max = counts["maximum_depth"]
        lifecycle = {"status": "draft", "validated_at": None, "locked_at": None, "locked_by_stage": None, "structural_sha256": None}
        depth_policy = _depth_policy(graph, title_to_id, depth_max)
        labels = {"fr": {"pro": "Arguments pour", "con": "Arguments contre"}, "en": {"pro": None, "con": None}}
        graph_block = {"lifecycle": lifecycle, "depth_policy": depth_policy, "nodes": nodes, "edges": edges, "occurrences": occurrences, "derived_counts": counts}

        scope_summary = scope_summary or f"Cadrage importé depuis la page « {debate_title_source} »; périmètre éditorial à revoir avant validation du graphe."
        scope = {
            "scope_schema_version": "1.0",
            "debate_id": debate_id,
            "canonical_title_fr": debate_title,
            "proposition_fr": debate_title,
            "scope_summary_fr": scope_summary,
            "jurisdiction": None,
            "timeframe": None,
            "included_topics": [],
            "excluded_topics": [],
            "residual_ambiguities": ["Le cadrage et le placement de chaque occurrence restent à valider après l'import technique."],
            "related_debates": sorted(set((graph.get("metadata", {}).get("frontières_débat_détaillé") or {}).values())),
            "editorial_constraints": ["Les fichiers sous imports/fr sont des sources historiques et ne sont pas des sorties validées."],
            "source_documents": [{"path": "data/import_provenance.json", "sha256": "0" * 64}],
        }

        debate_pages = {
            "fr": {
                "canonical_title": debate_title,
                "title_status": "draft",
                **make_empty_page_record("output/fr/debate/debate.wiki", interlanguage=True),
            },
            "en": {
                "canonical_title": None,
                "title_status": "unassigned",
                **make_empty_page_record("output/en/debate/debate.wiki", interlanguage=False),
            },
        }
        registry = {
            "schema": {
                "registry_version": "1.0",
                "graph_version": "1.0",
                "mediawiki_structure_version": "1.0",
                "render_profile_version": "1.0",
                "validator_version": VALIDATOR_VERSION,
            },
            "debate": {
                "id": debate_id,
                "scope": {
                    "proposition_fr": scope["proposition_fr"],
                    "scope_summary_fr": scope["scope_summary_fr"],
                    "jurisdiction": None,
                    "timeframe": None,
                    "included_topics": [],
                    "excluded_topics": [],
                    "residual_ambiguities": scope["residual_ambiguities"],
                },
                "labels": labels,
                "pages": debate_pages,
            },
            "graph": graph_block,
            "batches": [],
            "validations": [],
            "migrations": [],
        }
        graph_projection = {
            "graph_schema_version": "1.0",
            "debate": {"id": debate_id, "title_fr": debate_title, "labels": labels},
            **graph_block,
        }
        sources = {"source_registry_version": "1.0", "debate_id": debate_id, "sources": []}

        # Provenance is written first because scope.json references its hash.
        provenance = import_data["provenance"]
        provenance["debate_id"] = debate_id
        provenance["normalizations"] = ([{"source_title": debate_title_source, "registry_title": debate_title, "changes": debate_title_changes}] if debate_title_changes else []) + normalizations
        provenance["normative_occurrence_note"] = {
            "source_unfolded_occurrences": (
                graph.get("metadata", {}).get("occurrences_argumentatives_depliees_par_chemins")
                or graph.get("metadata", {}).get("occurrences_argumentatives")
            ),
            "normative_occurrences": counts["total_occurrences"],
            "explanation": "Le registre normatif crée une occurrence racine ou une occurrence par relation active; une occurrence secondaire ne développe pas ses enfants.",
        }
        write_json(output_dir / "data/import_provenance.json", provenance)
        scope["source_documents"][0]["sha256"] = sha256_file(output_dir / "data/import_provenance.json")

        write_json(output_dir / "scope.json", scope)
        write_json(output_dir / "data/registre_debat.json", registry)
        write_json(output_dir / "data/sources.json", sources)
        write_json(output_dir / "graph/graphe_argumentatif.json", graph_projection)
        (output_dir / "graph/graphe_argumentatif.md").write_text(_markdown_graph(debate_title, nodes, edges, occurrences, counts), encoding="utf-8", newline="\n")

        reviews = {
            "status": "pending",
            "generated_at": timestamp,
            "message": "Registre initialisé automatiquement; toutes les décisions éditoriales restent à revoir.",
            "items": [],
        }
        write_json(output_dir / "reviews/individual_review.json", reviews)
        write_json(output_dir / "reviews/graph_placement_review.json", reviews)
        write_json(output_dir / "reviews/introduction_review.json", reviews)
        write_json(output_dir / "data/keyword_vocabulary.json", {"status": "draft", "entries": []})
        (output_dir / "reports/import_report.md").parent.mkdir(parents=True, exist_ok=True)
        (output_dir / "reports/import_report.md").write_text(
            "\n".join([
                f"# Initialisation du corpus — {debate_title}", "",
                "Statut : `graph_draft`.", "",
                f"- Nœuds : {counts['distinct_nodes']}",
                f"- Relations : {len(edges)}",
                f"- Occurrences normatives : {counts['total_occurrences']}",
                f"- Pages sources importées : {len(provenance['pages'])}",
                f"- Normalisations ou replis consignés : {len(provenance['normalizations'])}", "",
                "Les fichiers `imports/fr/` ne sont pas des pages de sortie validées.",
            ]) + "\n", encoding="utf-8", newline="\n"
        )

        manifest = {
            "package_schema_version": "1.0",
            "debate_id": debate_id,
            "short_code": short_code,
            "global_status": "graph_draft",
            "created_at": timestamp,
            "updated_at": timestamp,
            "normative_versions": {
                "consolidated_norm": NORM_VERSION,
                "mediawiki_structure": "1.0",
                "render_profile": "1.0",
                "registry": "1.0",
                "graph": "1.0",
                "workflow": "1.0",
                "validator": VALIDATOR_VERSION,
            },
            "translation_status": {"en": "deferred"},
            "core_files": {
                "scope": "scope.json",
                "registry": "data/registre_debat.json",
                "graph_json": "graph/graphe_argumentatif.json",
                "graph_markdown": "graph/graphe_argumentatif.md",
                "sources": "data/sources.json",
            },
            "pages": [],
            "batches": [],
            "works": [{
                "work_id": "IMPORT-INITIALIZATION-001",
                "work_type": "initialization",
                "conversation_name": "Initialisation depuis un snapshot graph-extract",
                "status": "completed",
                "input_handoff": None,
                "output_handoff": None,
                "started_at": timestamp,
                "completed_at": timestamp,
            }],
            "validations": [],
            "release": {
                "release_manifest_path": None,
                "release_zip_path": None,
                "released_at": None,
                "archived_at": None,
                "release_receipt_path": None,
            },
            "editorial_controls": {
                "creation_date": dt.date.today().isoformat(),
                "individual_review_path": "reviews/individual_review.json",
                "individual_review_report_path": "reports/import_report.md",
                "keyword_vocabulary_path": "data/keyword_vocabulary.json",
                "required_reports": ["reports/import_report.md"],
                "debate_documentation": {
                    "min_subsections": 1,
                    "min_references": 0,
                    "reject_singleton_bucket_pattern": False,
                    "profile_rationale": "Profil provisoire sans quota par orientation; la revue éditoriale retiendra uniquement les sous-parties et sources réellement informatives.",
                },
                "introduction_references": {"required": True},
                "introduction_review_path": "reviews/introduction_review.json",
                "graph_placement_review_path": "reviews/graph_placement_review.json",
            },
        }
        write_json(output_dir / "manifest.json", manifest)
        return {
            "status": "created",
            "debate_id": debate_id,
            "short_code": short_code,
            "output_dir": str(output_dir),
            "nodes": counts["distinct_nodes"],
            "edges": len(edges),
            "source_unfolded_occurrences": provenance["normative_occurrence_note"]["source_unfolded_occurrences"],
            "normative_occurrences": counts["total_occurrences"],
            "occurrences": counts["total_occurrences"],
            "occurrence_semantics": (
                "Les occurrences normatives comptent une racine ou une relation active; "
                "les occurrences dépliées de l'extracteur comptent tous les chemins."
            ),
            "imports": len(provenance["pages"]),
        }
    finally:
        if inp.cleanup:
            shutil.rmtree(inp.cleanup, ignore_errors=True)


def run_validator(project_root: Path, package: Path) -> dict[str, Any]:
    python = project_root / ".venv/bin/python"
    if not python.is_file():
        python = Path(sys.executable)
    validator_src = project_root / "validator/src"
    validator_script = project_root / "validator/scripts/wikidebia_validate.py"
    if not validator_src.is_dir() or not validator_script.is_file():
        return {"status": "not_run", "reason": "validateur local incomplet"}
    report_json = package / "reports/initial_validation.json"
    report_txt = package / "reports/initial_validation.txt"
    env = dict(**__import__("os").environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONNOUSERSITE"] = "1"
    env.pop("PYTHONHOME", None)
    command = [
        str(python), "-I", str(validator_script), "validate", str(package),
        "--scope", "schema", "--scope", "coherence", "--scope", "graph",
        "--scope", "files", "--scope", "workflow", "--format", "both",
        "--text-output", str(report_txt), "--json-output", str(report_json),
    ]
    completed = subprocess.run(command, text=True, capture_output=True, env=env, check=False)
    result = {
        "status": "passed" if completed.returncode == 0 else "failed",
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
        "report_json": report_json.relative_to(package).as_posix(),
        "report_text": report_txt.relative_to(package).as_posix(),
    }
    write_json(package / "reports/initial_validation_execution.json", result)
    return result


def assert_build_output_path(output_dir: Path, project_root: Path) -> None:
    allowed = (project_root / ".state" / "corpus-builds").resolve()
    selected = output_dir.expanduser().resolve()
    try:
        relative = selected.relative_to(allowed)
    except ValueError as exc:
        raise CorpusInitError(
            f"La sortie doit rester sous {allowed}; chemin refusé : {selected}"
        ) from exc
    if not relative.parts:
        raise CorpusInitError("Le dossier racine .state/corpus-builds ne peut pas être remplacé directement")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Initialiser un corpus graph_draft depuis un snapshot graph-extract.")
    parser.add_argument("snapshot", type=Path, help="Dossier, snapshot_manifest.json ou ZIP audité de graph-extract")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--debate-id")
    parser.add_argument("--short-code")
    parser.add_argument("--scope-summary")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--skip-validation", action="store_true")
    parser.add_argument("--machine-readable", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.project_root:
        assert_build_output_path(args.output_dir, args.project_root.resolve())
    result = build_corpus(
        args.snapshot,
        args.output_dir,
        debate_id=args.debate_id,
        short_code=args.short_code,
        scope_summary=args.scope_summary,
        overwrite=args.overwrite,
    )
    if not args.skip_validation and args.project_root:
        validation = run_validator(args.project_root.resolve(), args.output_dir.resolve())
        result["validation"] = validation
        if validation["status"] == "failed":
            result["status"] = "created_but_validation_failed"
    print(json.dumps(result, ensure_ascii=False, sort_keys=True) if args.machine_readable else json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "created" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CorpusInitError as exc:
        print(f"WIKIDEBIA BLOQUÉ : {exc}", file=sys.stderr)
        raise SystemExit(2)
