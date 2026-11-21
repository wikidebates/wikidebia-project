#!/usr/bin/env python3
"""Read-only MediaWiki pageid evidence for French relation-title aliases.

This is a separate evidence collector, NOT a publication or reconciliation
executor. It reads only French pages whose frozen release differs from the
signed published state, then resolves both spellings of each changed relation
target using MediaWiki query/info. All non-target bytes must match exactly.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

from wikidebia_corpus_build import (
    assert_control_directory, assert_no_symlinks, full_tree_sha256,
    load_json, now_iso, sha256_file, validate_debate_id, write_json,
    exclusive_lock,
)
from wikidebia_editorial_workspace import validate_work_id
from wikidebia_graph_actions import _main_template_raw, _segment_offsets, _top_level_equals
from wikidebia_graph_extract import _template_spans, normalize_key, parse_template
from wikidebia_post_publication import _signed, PostPublicationError
from wikidebia_render import _load_workspace
from wikidebia_update import sha_object, sha_text
from wikidebia_publish import PywikibotAdapter


SCHEMA = "wikidebia-french-relation-pageids-read-only-1.0"
RELATIONS = {
    "debate": {"arguments pour": "argument pour", "arguments contre": "argument contre"},
    "argument": {"justifications": "justification", "objections": "objection"},
}
HEX64 = re.compile(r"[0-9a-f]{64}")


class RelationPageIdError(PostPublicationError):
    pass


def _block(message: str) -> None:
    raise RelationPageIdError(message)


def _page_map(rows: Any, label: str) -> dict[tuple[str, str], dict[str, Any]]:
    if not isinstance(rows, list) or not rows:
        _block("Inventaire de pages absent : " + label)
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            _block("Inventaire de pages non structuré : " + label)
        key = (str(row.get("page_type") or ""), str(row.get("page_id") or ""))
        if key[0] not in RELATIONS or not key[1] or key in result:
            _block("Page invalide ou dupliquée : " + label)
        result[key] = row
    return result


def _masked(text: str) -> str:
    return re.sub(r"<!--.*?-->", lambda match: " " * len(match.group()), text, flags=re.S)


def _relation_targets(text: str, page_type: str) -> tuple[str, list[dict[str, str]]]:
    """Mask ONLY the base title of recognized page= relation targets.

    Everything else remains byte-identical, including occurrence order,
    displayed labels, anchors, duplicates, comments, and whitespace.
    """
    if page_type not in RELATIONS:
        _block("Type de page française inattendu")
    masked = _masked(text)
    try:
        raw, start, _ = _main_template_raw(masked, page_type)
    except Exception as exc:
        raise RelationPageIdError("Modèle principal absent ou ambigu") from exc
    # Exactly one main template; the old helper selects the longest one.
    expected_main = "debat" if page_type == "debate" else "argument"
    main_candidates = [
        (a, b) for a, b in _template_spans(masked)
        if (call := parse_template(masked[a:b]))
        and normalize_key(call.name) == expected_main
    ]
    if len(main_candidates) != 1:
        _block("Plusieurs modèles principaux ou un modèle introuvable")

    inner = raw[2:-2]
    replacements: list[tuple[int, int]] = []
    found: list[dict[str, str]] = []
    seen_parameters: set[str] = set()
    for index, (outer_a, outer_b) in enumerate(_segment_offsets(inner)):
        if index == 0:
            continue
        outer_part = inner[outer_a:outer_b]
        eq = _top_level_equals(outer_part)
        if eq is None:
            continue
        relation = normalize_key(outer_part[:eq].strip())
        if relation not in RELATIONS[page_type]:
            continue
        if relation in seen_parameters:
            _block("Paramètre relationnel dupliqué : " + relation)
        seen_parameters.add(relation)
        rel_value = outer_part[eq + 1:]
        absolute_value_start = start + 2 + outer_a + eq + 1
        for rel_a, rel_b in _template_spans(rel_value):
            call = parse_template(rel_value[rel_a:rel_b])
            if not call or normalize_key(call.name) != RELATIONS[page_type][relation]:
                continue
            sub_raw = rel_value[rel_a:rel_b]
            sub_inner = sub_raw[2:-2]
            page_parts: list[tuple[int, str]] = []
            for idx, (seg_a, seg_b) in enumerate(_segment_offsets(sub_inner)):
                if idx == 0:
                    continue
                seg = sub_inner[seg_a:seg_b]
                peq = _top_level_equals(seg)
                if peq is None or normalize_key(seg[:peq].strip()) != "page":
                    continue
                page_parts.append((seg_a + peq + 1, seg[peq + 1:]))
            if len(page_parts) != 1 or call.positional:
                _block("Relation sans paramètre page unique : " + relation)
            offset, value = page_parts[0]
            full_title = value.strip()
            if (not full_title or any(ch in full_title for ch in "{}[]|<>\r\n")
                    or full_title.count("#") > 1):
                _block("Titre relationnel ambigu : " + relation)
            base, separator, anchor = full_title.partition("#")
            base = base.strip()
            if not base or (separator and not anchor.strip()):
                _block("Cible de relation vide ou ancre invalide")
            title_a = value.find(base)
            if title_a < 0:
                _block("Impossible de localiser le paramètre page")
            abs_a = absolute_value_start + rel_a + 2 + offset + title_a
            abs_b = abs_a + len(base)
            if text[abs_a:abs_b] != base:
                _block("Le texte est ambigu à la position de la cible relationnelle")
            replacements.append((abs_a, abs_b))
            found.append({"relation": relation.replace(" ", "-") if page_type == "debate" else relation, "title": base})

    replaced = text
    for a, b in sorted(replacements, reverse=True):
        replaced = replaced[:a] + "<WIKIDEBIA_RELATION_TARGET>" + replaced[b:]
    return replaced, found


def changed_aliases(remote_text: str, release_text: str, page_type: str) -> list[dict[str, str]]:
    """Prove byte-identical structure aside from relation base titles."""
    before, source_targets = _relation_targets(remote_text, page_type)
    after, release_targets = _relation_targets(release_text, page_type)
    if before != after or len(source_targets) != len(release_targets):
        _block("Le français diverge hors des seuls titres de liens : libellé, ordre, ancre ou contenu")
    result = []
    for index, (old, new) in enumerate(zip(source_targets, release_targets)):
        if old["relation"] != new["relation"]:
            _block("Ordre des rubriques relationnelles modifié")
        if old["title"] != new["title"]:
            result.append({
                "occurrence_index": index,
                "relation": old["relation"],
                "original_title": old["title"],
                "release_title": new["title"],
            })
    if not result:
        _block("Les deux versions ont le même contenu relationnel : preuve superflue")
    return result


def resolve_titles_pageids(site: Any, titles: list[str]) -> dict[str, dict[str, Any]]:
    """Resolve each requested spelling with query/info/redirects, in batches of 50."""
    requested = list(dict.fromkeys(titles))
    if not requested or any(not isinstance(t, str) or not t.strip() or "|" in t or "#" in t for t in requested):
        _block("Jeu de titres à résoudre vide ou invalide")
    resolved: dict[str, dict[str, Any]] = {}
    for start in range(0, len(requested), 50):
        batch = requested[start:start + 50]
        data = site.simple_request(
            action="query", prop="info", redirects=1, titles="|".join(batch),
        ).submit()
        query = data.get("query") if isinstance(data, dict) else None
        if not isinstance(query, dict):
            _block("Réponse query/info MediaWiki invalide")
        redirects: dict[str, str] = {}
        for category in ("normalized", "redirects"):
            for item in query.get(category) or []:
                if not isinstance(item, dict) or not item.get("from") or not item.get("to"):
                    _block("Normalisation ou redirection MediaWiki invalide")
                if item.get("tofragment") or item["from"] in redirects:
                    _block("Redirection ambiguë, comportant une ancre ou dupliquée")
                redirects[str(item["from"])] = str(item["to"])
        raw = query.get("pages")
        rows = list(raw.values()) if isinstance(raw, dict) else raw
        if not isinstance(rows, list):
            _block("Pages MediaWiki manquantes")
        by_title = {}
        for page in rows:
            if not isinstance(page, dict) or not page.get("title"):
                _block("Page MediaWiki non structurée")
            title = str(page["title"])
            if title in by_title:
                _block("Page MediaWiki dupliquée")
            by_title[title] = page
        for title in batch:
            canonical = title
            seen = set()
            while canonical in redirects:
                if canonical in seen:
                    _block("Cycle de redirections MediaWiki")
                seen.add(canonical)
                canonical = redirects[canonical]
            page = by_title.get(canonical)
            if not page or "missing" in page or "invalid" in page:
                _block("Cible de relation introuvable sur MediaWiki : " + title)
            pageid = page.get("pageid")
            if type(pageid) is not int or pageid <= 0:
                _block("Identifiant MediaWiki non positif pour : " + title)
            resolved[title] = {"pageid": pageid, "resolved_title": canonical}
    if set(resolved) != set(requested):
        _block("Résolution de titres incomplète")
    return resolved


def verify_alias_proof(
    proof: Mapping[str, Any], *, debate_id: str, work_id: str, release_tree: str,
    manifest_sha256: str, french_state: Mapping[str, Any],
    changed: Mapping[tuple[str, str], tuple[str, str]],
) -> dict[str, int]:
    """Validate a signed read-only inventory against exact published revisions."""
    if (proof.get("schema") != SCHEMA
            or proof.get("debate_id") != debate_id or proof.get("work_id") != work_id
            or proof.get("release_copy_tree_sha256") != release_tree
            or proof.get("manifest_sha256") != manifest_sha256
            or proof.get("french_state_sha256") != french_state.get("state_sha256")
            or proof.get("remote_access_mode") != "read_only"
            or proof.get("remote_writes") != 0):
        _block("Provenance ou empreinte de preuve pageid divergente")
    page_rows = proof.get("pages")
    if not isinstance(page_rows, list) or not changed or len(page_rows) != len(changed):
        _block("Inventaire des pages de liens différent des écarts constatés")
    by_key = _page_map(page_rows, "preuve pageid")
    if set(by_key) != set(changed):
        _block("Inventaire des pages de liens incomplet ou excessif")
    states = _page_map(french_state.get("pages"), "état français")
    titles = proof.get("title_resolutions")
    if not isinstance(titles, dict):
        _block("Résolutions de cibles absentes")
    used: set[str] = set()
    total_changes = 0
    for key, (remote_hash, released_text) in changed.items():
        row, state = by_key[key], states[key]
        text = row.get("remote_text")
        if (not isinstance(text, str)
                or row.get("title") != state.get("canonical_title")
                or row.get("revision_id") != state.get("revision_id")
                or sha_text(text) != remote_hash
                or row.get("content_sha256") != remote_hash
                or row.get("release_sha256") != sha_text(released_text)):
            _block("Le texte d'une page diffère de la révision attestée : " + str(key))
        changes = changed_aliases(text, released_text, key[0])
        if row.get("changes") != changes:
            _block("Les changements de titres ne correspondent pas au texte source")
        for item in changes:
            old, new = item["original_title"], item["release_title"]
            used.update((old, new))
            a, b = titles.get(old), titles.get(new)
            if (not isinstance(a, dict) or not isinstance(b, dict)
                    or type(a.get("pageid")) is not int
                    or type(b.get("pageid")) is not int
                    or a["pageid"] <= 0 or a["pageid"] != b["pageid"]
                    or not isinstance(a.get("resolved_title"), str)
                    or not isinstance(b.get("resolved_title"), str)
                    or not a["resolved_title"] or not b["resolved_title"]
                    or a["resolved_title"] != b["resolved_title"]):
                _block("Cibles de relation de pageid différents ou sans preuve : " + old + " / " + new)
            total_changes += 1
    if set(titles) != used or proof.get("page_count") != len(changed) or proof.get("alias_count") != total_changes:
        _block("Inventaire de pageid inattendu, incomplet ou dupliqué")
    return {"page_count": len(changed), "alias_count": total_changes}


def collect_alias_proof(
    project_root: Path, debate_id: str, work_id: str, adapter: Any,
) -> dict[str, Any]:
    """Read only changed French source pages and resolve exact targets."""
    root = project_root.resolve()
    debate_id, work_id = validate_debate_id(debate_id), validate_work_id(work_id)
    workspace, meta = _load_workspace(root, debate_id, work_id)
    release = workspace / "release-copy"
    if not release.is_dir() or release.is_symlink():
        _block("Release absente")
    assert_no_symlinks(release)
    tree = full_tree_sha256(release)
    if (meta.get("release_copy") or {}).get("tree_sha256") != tree:
        _block("Release modifiée")
    manifest_path = release / "manifest.json"
    manifest = load_json(manifest_path)
    manifest_sha = sha256_file(manifest_path)
    if manifest.get("debate_id") != debate_id:
        _block("Manifeste étranger au débat")
    fr_state = _signed(
        root / ".state/published" / debate_id / "fr" / "latest.json",
        "état publié français", "state_sha256", root,
    )
    if fr_state.get("debate_id") != debate_id or fr_state.get("language") != "fr":
        _block("État publié français incompatible")
    state_rows = _page_map(fr_state.get("pages"), "état publié")
    manifest_rows = _page_map(
        [r for r in manifest.get("pages") or [] if r.get("language") == "fr"],
        "manifeste",
    )
    if set(state_rows) != set(manifest_rows) or fr_state.get("source_manifest_sha256") != manifest_sha:
        _block("Pages françaises ou empreinte de manifeste divergentes")
    pending: list[tuple[tuple[str, str], str, str, str, int]] = []
    for key, row in manifest_rows.items():
        state = state_rows[key]
        rel = str(row.get("file_path") or row.get("source_path") or "")
        if not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
            _block("Chemin de page français non portable")
        source = release / rel
        if (not source.is_file() or source.is_symlink()
                or not source.resolve().is_relative_to(release.resolve())):
            _block("Page de release française absente ou non sûre")
        proposed = source.read_text(encoding="utf-8")
        expected_hash = str(state.get("content_sha256") or "")
        if HEX64.fullmatch(expected_hash) is None:
            _block("Empreinte française publiée invalide")
        if sha_text(proposed) == expected_hash:
            continue
        revision_id = state.get("revision_id")
        if type(revision_id) is not int or revision_id <= 0:
            _block("Révision française publiée absente")
        pending.append((key, str(state.get("canonical_title") or ""), expected_hash, proposed, revision_id))
    if not pending:
        _block("Aucun écart de titres français à vérifier")

    requests = [item[1] for item in pending]
    if not all(requests) or len(set(requests)) != len(requests):
        _block("Titres des pages sources français manquants ou dupliqués")
    adapter.open_language_read_only("fr")
    try:
        snapshots = adapter.read_pages(requests)
        if not isinstance(snapshots, dict) or set(snapshots) != set(requests):
            _block("Lecture groupée française incomplète")
        rows = []
        required_titles: set[str] = set()
        for key, title, expected_hash, proposed, revision_id in pending:
            observed = snapshots[title]
            if not isinstance(observed, (tuple, list)) or len(observed) != 3:
                _block("Snapshot distant malformé : " + title)
            exists, observed_rev, observed_text = observed
            if (exists is not True or observed_rev != revision_id
                    or not isinstance(observed_text, str)
                    or sha_text(observed_text) != expected_hash):
                _block("La page française a changé depuis l'état publié signé : " + title)
            changes = changed_aliases(observed_text, proposed, key[0])
            for item in changes:
                required_titles.add(item["original_title"])
                required_titles.add(item["release_title"])
            rows.append({
                "page_type": key[0], "page_id": key[1], "title": title,
                "revision_id": revision_id, "content_sha256": expected_hash,
                "remote_text": observed_text, "release_sha256": sha_text(proposed),
                "changes": changes,
            })
        if not hasattr(adapter, "site") or adapter.site is None:
            _block("Site MediaWiki non accessible en lecture seule")
        requested = sorted(required_titles)
        resolved = resolve_titles_pageids(adapter.site, requested)
        confirmed = resolve_titles_pageids(adapter.site, requested)
        if confirmed != resolved:
            _block("Résolutions de titres instables entre les deux lectures")
        # Read back the source revisions again: a changed page invalidates
        # any title mapping, even if the target's pageid stayed constant.
        final_pages = adapter.read_page_revisions(requests)
        if not isinstance(final_pages, dict) or set(final_pages) != set(requests):
            _block("Contrôle final des révisions françaises incomplet")
        for _key, title, _expected_hash, _proposed, revision_id in pending:
            if final_pages[title] != (True, revision_id):
                _block("Une page source a changé pendant la résolution pageid : " + title)
    finally:
        adapter.close_language()
    proof = {
        "schema": SCHEMA, "debate_id": debate_id, "work_id": work_id,
        "created_at": now_iso(), "release_copy_tree_sha256": tree,
        "manifest_sha256": manifest_sha,
        "french_state_sha256": fr_state["state_sha256"],
        "remote_access_mode": "read_only", "remote_writes": 0,
        "page_count": len(rows),
        "alias_count": sum(len(row["changes"]) for row in rows),
        "pages": sorted(rows, key=lambda row: (row["page_type"], row["page_id"])),
        "title_resolutions": resolved,
    }
    proof["proof_sha256"] = sha_object(proof)
    checked = {
        (row["page_type"], row["page_id"]): (row["content_sha256"], next(
            (release / str(m.get("file_path") or m.get("source_path"))).read_text(encoding="utf-8")
            for key, m in manifest_rows.items() if key == (row["page_type"], row["page_id"])
        ))
        for row in rows
    }
    verify_alias_proof(
        proof, debate_id=debate_id, work_id=work_id, release_tree=tree,
        manifest_sha256=manifest_sha, french_state=fr_state, changed=checked,
    )
    return proof


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("debate_id")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--machine-readable", action="store_true")
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    from wikidebia_final_publication import _settings
    settings = _settings(root)
    adapter = PywikibotAdapter(
        str(settings.get("family") or "wikidebates"),
        {"fr": "fr"},
        root / "private/pywikibot",
        root / "kit/families/wikidebates_family.py",
    )
    with exclusive_lock(root, args.debate_id, "post-publication"):
        proof = collect_alias_proof(root, args.debate_id, args.work_id, adapter)
        state_root = assert_control_directory(root / ".state", root, create=True)
        post_root = assert_control_directory(state_root / "post-publication", root, create=True)
        debate_root = assert_control_directory(post_root / args.debate_id, root, create=True)
        work_root = assert_control_directory(debate_root / args.work_id, root, create=True)
        path = work_root / "fr-relation-pageids.json"
        if path.exists() or path.is_symlink():
            old = _signed(path, "preuve pageid", "proof_sha256", root)
            # Timestamp may differ on retry; never overwrite the earlier proof.
            stable = lambda row: {k: v for k, v in row.items() if k not in {"created_at", "proof_sha256"}}
            if stable(old) != stable(proof):
                _block("Preuve pageid existante divergente; ne pas écraser un reçu")
            proof = old
        else:
            write_json(path, proof)
    result = {
        "status": "verified_read_only",
        "path": path.relative_to(root).as_posix(),
        "proof_sha256": proof["proof_sha256"],
        "page_count": proof["page_count"], "alias_count": proof["alias_count"],
        "remote_writes": 0,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True,
                     indent=None if args.machine_readable else 2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RelationPageIdError, PostPublicationError, OSError, ValueError, KeyError) as exc:
        print(f"PREUVE PAGEID BLOQUÉE : {exc}", file=sys.stderr)
        raise SystemExit(2)
