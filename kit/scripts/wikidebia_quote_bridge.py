"""Private, read-only bridge from locked French content to the quote resolver.

No external dependency, network access, registry import, translation approval
or mutation of an editorial lock. The resolver's independent documentary
checks remain mandatory. A handoff is advisory, never publication evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from wikidebia_corpus_build import canonical_json, load_json, sha256_file
from wikidebia_editorial_review import _assert_source_unchanged, _load_workspace
from wikidebia_translation_review import (
    _assert_content_copy, _reuses_existing_english_page, _source_snapshot,
)

REQUEST = "wikidebia-translation-citation-request-1"
HANDOFF = "wikidebia-translation-citation-handoff-1"
RECEIPT = "wikidebia-prepared-citation-receipt-1"
REVIEWED = "reviewed_receipt_rights_unreviewed"
PENDING = "review_pending"
STATES = {
    "ai_translation_required", "source_binding_required", "retry_documentary",
    "insufficient_evidence", PENDING, REVIEWED,
}
MAX_ITEMS = 200


class QuoteBridgeError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(canonical_json(value)).hexdigest()


def is_digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def unique_rows(rows, key):
    by_id = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get(key), str) or not row[key]:
            raise QuoteBridgeError("invalid_locked_identity")
        if row[key] in by_id:
            raise QuoteBridgeError("duplicate_locked_identity")
        by_id[row[key]] = row
    return by_id


def parameter_pairs(parameters):
    if not isinstance(parameters, list):
        raise QuoteBridgeError("invalid_locked_parameters")
    pairs = {}
    for p in parameters:
        if (not isinstance(p, dict) or set(p) != {"name", "value"}
                or not isinstance(p["name"], str) or not isinstance(p["value"], str)):
            raise QuoteBridgeError("invalid_locked_parameter")
        key = p["name"].strip()
        if not key or key in pairs:
            raise QuoteBridgeError("duplicate_or_empty_locked_parameter")
        pairs[key] = p["value"].strip()
    if not pairs.get("citation"):
        raise QuoteBridgeError("missing_locked_citation")
    return pairs


def locked_items(source, registry, metadata, content, provenance):
    """Collect occurrences from the authoritative French lock, not a draft.

    Revision/title come from the actual imported page, not from a renamed
    title or a locally fabricated revision. The resolver still requires an
    exact, unique match against that remote revision.
    """
    nodes = unique_rows(
        [n for n in (registry.get("graph") or {}).get("nodes") or []
         if n.get("status") == "active"], "id")
    locks = unique_rows(content.get("arguments") or [], "id")
    metas = unique_rows(metadata.get("arguments") or [], "entity_id")
    imports = unique_rows(
        [p for p in provenance.get("pages") or []
         if p.get("kind") == "argument"], "page_id")
    if set(nodes) != set(locks) or set(nodes) != set(metas) or not set(nodes) <= set(imports):
        raise QuoteBridgeError("incomplete_locked_argument_coverage")
    items, owners = [], {}
    for page_id, node in nodes.items():
        if _reuses_existing_english_page(node):
            continue
        citations = locks[page_id].get("citations") or []
        if not isinstance(citations, list):
            raise QuoteBridgeError("invalid_locked_citation_list")
        if not citations:
            continue
        imp = imports[page_id]
        rev = imp.get("revision_id")
        if rev is not None and (type(rev) is not int or rev <= 0):
            raise QuoteBridgeError("invalid_import_revision")
        path = Path(imp.get("import_path") or "")
        actual = source / path
        if (path.is_absolute() or path.parts[:2] != ("imports", "fr")
                or ".." in path.parts or not actual.is_file()
                or not actual.resolve().is_relative_to(source.resolve())
                or actual.is_symlink() or sha256_file(actual) != imp.get("sha256")):
            raise QuoteBridgeError("import_identity_changed")
        title = imp.get("canonical_title")
        if rev is None and not title:
            title = metas[page_id].get("canonical_title") or locks[page_id].get("canonical_title")
        if not isinstance(title, str) or not title.strip():
            raise QuoteBridgeError("missing_import_title")
        for citation in citations:
            if not isinstance(citation, dict):
                raise QuoteBridgeError("invalid_locked_citation")
            cid = citation.get("id")
            if (not isinstance(cid, str) or not cid.startswith(page_id + "-C")
                    or cid in owners):
                raise QuoteBridgeError("duplicate_or_invalid_citation_identity")
            parameters = citation.get("source_parameters")
            pairs = parameter_pairs(parameters)
            template = citation.get("source_template")
            if not isinstance(template, str) or not template.strip():
                raise QuoteBridgeError("missing_locked_template")
            if citation.get("citation") != pairs["citation"]:
                raise QuoteBridgeError("locked_citation_text_mismatch")
            owners[cid] = page_id
            items.append({"id": cid, "wiki_title": title, "revision": rev,
                          "source_template": template,
                          "source_parameters": copy.deepcopy(parameters)})
    return items, owners


def snapshot(project, debate_id, work_id):
    workspace, meta = _load_workspace(project, debate_id, work_id)
    if meta.get("status") not in {"fr_content_applied", "fr_source_preserved",
                                "en_translation_review_ready"}:
        raise QuoteBridgeError("translation_source_not_open")
    _assert_source_unchanged(project, debate_id, meta)
    source = _assert_content_copy(workspace, meta)
    registry, metadata, content, _ = _source_snapshot(source)
    if (content.get("debate_id") != debate_id or content.get("work_id") != work_id
            or content.get("status") not in {"locked_for_translation_and_generation",
                                            "frozen_as_imported"}):
        raise QuoteBridgeError("content_lock_identity_mismatch")
    provenance = load_json(source / "data/import_provenance.json")
    items, owners = locked_items(source, registry, metadata, content, provenance)
    return workspace, sha256_file(source / "data/fr_content_lock.json"), items, owners


def duplicate_sources(items, owners):
    """Report exact repeated quote values across argument pages; do not erase."""
    groups = defaultdict(set)
    for item in items:
        quote = parameter_pairs(item["source_parameters"])["citation"]
        groups[digest(quote)].add(owners[item["id"]])
    return sum(len(pages) > 1 for pages in groups.values())


def requests_for(lock_sha, items, owners, *, page_ids=(), batch_size=MAX_ITEMS):
    if not is_digest(lock_sha) or not 1 <= batch_size <= MAX_ITEMS:
        raise QuoteBridgeError("invalid_request_limits")
    selected = set(page_ids)
    if selected - set(owners.values()):
        raise QuoteBridgeError("requested_page_has_no_active_citations")
    rows = [item for item in items if not selected or owners[item["id"]] in selected]
    return [{"schema": REQUEST, "source_lock_sha256": lock_sha,
             "items": rows[i:i + batch_size]}
            for i in range(0, len(rows), batch_size)]


def write_private_request(workspace, request):
    """Only in the ignored workspace; immutable by content hash, mode 0600."""
    directory = workspace / "audits" / "quote-resolver" / "requests"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not directory.resolve().is_relative_to(workspace.resolve()):
        raise QuoteBridgeError("unsafe_request_directory")
    path = directory / (digest(request) + ".json")
    if path.is_symlink():
        raise QuoteBridgeError("unsafe_request_path")
    payload = canonical_json(request) + b"\n"
    if path.exists():
        if not path.is_file() or path.read_bytes() != payload:
            raise QuoteBridgeError("stored_request_changed")
        if path.stat().st_mode & 0o077:
            raise QuoteBridgeError("stored_request_not_private")
        return path
    fd, name = tempfile.mkstemp(prefix=".quote-request-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # Publish only a complete file; concurrent identical creation is safe.
        try:
            os.link(name, path)
        except FileExistsError:
            if path.is_symlink() or path.read_bytes() != payload or path.stat().st_mode & 0o077:
                raise QuoteBridgeError("stored_request_changed")
    finally:
        os.unlink(name)
    return path


def validate_request(request, lock_sha, items):
    if (not isinstance(request, dict)
            or set(request) != {"schema", "source_lock_sha256", "items"}
            or request.get("schema") != REQUEST
            or request.get("source_lock_sha256") != lock_sha
            or not isinstance(request.get("items"), list)
            or not 1 <= len(request["items"]) <= MAX_ITEMS):
        raise QuoteBridgeError("request_source_lock_mismatch")
    expected = {item["id"]: item for item in items}
    rows = unique_rows(request["items"], "id")
    if any(expected.get(cid) != row for cid, row in rows.items()):
        raise QuoteBridgeError("request_occurrence_changed")
    return rows


def _reviewed_fragments(row, item):
    """Check serialized integrity, not the truth of the editorial decision."""
    passage = row.get("published_passage")
    if (not isinstance(passage, dict) or passage.get("rights") != "unreviewed"
            or passage.get("auto_publish") is not False
            or passage.get("editorial_review_required") is not True):
        raise QuoteBridgeError("invalid_published_passage_scope")
    receipt = passage.get("receipt")
    if not isinstance(receipt, dict):
        raise QuoteBridgeError("missing_published_receipt")
    entry = receipt.get("entry_sha256")
    if (receipt.get("schema") != RECEIPT or not is_digest(entry)
            or digest({k: v for k, v in receipt.items() if k != "entry_sha256"}) != entry
            or receipt.get("rights") != "unreviewed" or receipt.get("auto_publish") is not False
            or receipt.get("semantic_status") != "editorial_decision_recorded"):
        raise QuoteBridgeError("published_receipt_integrity_mismatch")
    source = receipt.get("source") or {}
    params = parameter_pairs(item["source_parameters"])
    if (not is_digest(row.get("source_key")) or source.get("source_key") != row["source_key"]
            or source.get("quote_wikitext_sha256") != hashlib.sha256(
                params["citation"].encode("utf-8")).hexdigest()
            or source.get("metadata_sha256") != digest(sorted(
                (k, v) for k, v in params.items() if k != "citation"))
            or (row.get("evidence") or {}).get("receipt_sha256") != entry):
        raise QuoteBridgeError("published_receipt_source_mismatch")
    fragments = passage.get("fragments")
    expected = receipt.get("fragments")
    if (not isinstance(fragments, list) or not fragments
            or not isinstance(expected, list) or len(fragments) != len(expected)):
        raise QuoteBridgeError("invalid_published_fragments")
    for fragment, proof in zip(fragments, expected):
        if not isinstance(fragment, dict) or not isinstance(proof, dict):
            raise QuoteBridgeError("invalid_published_fragment")
        text = fragment.get("text")
        lo, hi = proof.get("char_start"), proof.get("char_end")
        if (not isinstance(text, str) or not text.strip()
                or type(lo) is not int or type(hi) is not int or not 0 <= lo < hi
                or hi - lo != len(text)
                or {k: v for k, v in fragment.items() if k != "text"} != proof
                or hashlib.sha256(text.encode("utf-8")).hexdigest() != proof.get("text_sha256")):
            raise QuoteBridgeError("published_fragment_integrity_mismatch")
    return digest([f["text"] for f in fragments])


def inspect_handoff(request, handoff, expected_sha, lock_sha, items, owners):
    expected = validate_request(request, lock_sha, items)
    if (not isinstance(handoff, dict) or not is_digest(expected_sha)
            or digest(handoff) != expected_sha or handoff.get("schema") != HANDOFF
            or handoff.get("source_lock_sha256") != lock_sha
            or handoff.get("request_sha256") != digest(request)
            or handoff.get("rights") != "unreviewed"
            or handoff.get("auto_publish") is not False
            or not isinstance(handoff.get("rows"), list)
            or not isinstance(handoff.get("packets"), list)):
        raise QuoteBridgeError("handoff_identity_mismatch")
    rows = unique_rows(handoff["rows"], "id")
    if set(rows) != set(expected):
        raise QuoteBridgeError("handoff_occurrence_coverage")
    packets = unique_rows(handoff["packets"], "packet_sha256")
    assigned = {}
    for sha, wrapper in packets.items():
        p = wrapper.get("packet")
        if (not is_digest(sha) or not isinstance(p, dict) or digest(p) != sha
                or p.get("translation_request_sha256") != digest(request)
                or p.get("source_lock_sha256") != lock_sha
                or not isinstance(p.get("sources"), dict)):
            raise QuoteBridgeError("handoff_packet_identity_mismatch")
        for source in p["sources"].values():
            for occurrence in source.get("occurrences") or []:
                cid = occurrence.get("case_id")
                if cid not in expected or cid in assigned:
                    raise QuoteBridgeError("handoff_packet_occurrence_mismatch")
                item = expected[cid]
                ref = occurrence.get("ref")
                if (not isinstance(ref, dict) or ref.get("revision") != item["revision"]
                        or occurrence.get("wiki_title") != item["wiki_title"]
                        or rows[cid].get("citation_ref") != ref
                        or rows[cid].get("source_key") != source.get("source_key")):
                    raise QuoteBridgeError("handoff_packet_source_mismatch")
                assigned[cid] = sha
    if set(assigned.values()) != set(packets):
        raise QuoteBridgeError("empty_handoff_packet")
    groups = defaultdict(set)
    for cid, row in rows.items():
        item = expected[cid]
        state = row.get("state")
        if (state not in STATES
                or row.get("source_parameters_sha256") != digest(item["source_parameters"])
                or row.get("packet_sha256") != assigned.get(cid)
                or (state == PENDING) != (cid in assigned)):
            raise QuoteBridgeError("handoff_row_mismatch")
        if state == REVIEWED:
            ref = row.get("citation_ref")
            if (not isinstance(ref, dict) or ref.get("revision") != item["revision"]
                    or type(item["revision"]) is not int):
                raise QuoteBridgeError("published_receipt_occurrence_mismatch")
            groups[_reviewed_fragments(row, item)].add(owners[cid])
        elif "published_passage" in row:
            raise QuoteBridgeError("unreviewed_row_has_published_passage")
    return {"request_sha256": digest(request), "handoff_sha256": expected_sha,
            "source_lock_sha256": lock_sha, "occurrences": len(rows),
            "states": dict(Counter(row["state"] for row in rows.values())),
            "packets": len(packets),
            "duplicate_published_groups_across_pages_in_batch": sum(
                len(pages) > 1 for pages in groups.values()),
            "editorial_review_required": True, "rights": "unreviewed",
            "publication_authorized": False, "translation_mutated": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("debate_id")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export")
    export.add_argument("--page-id", action="append", default=[])
    export.add_argument("--batch-size", type=int, default=MAX_ITEMS)
    verify = sub.add_parser("inspect")
    verify.add_argument("--request", type=Path, required=True)
    verify.add_argument("--handoff", type=Path, required=True)
    verify.add_argument("--handoff-sha", required=True)
    args = parser.parse_args(argv)
    try:
        workspace, lock_sha, items, owners = snapshot(
            args.project_root.resolve(), args.debate_id, args.work_id)
        if args.command == "export":
            requests = requests_for(lock_sha, items, owners, page_ids=args.page_id,
                                    batch_size=args.batch_size)
            paths = [write_private_request(workspace, req) for req in requests]
            result = {"source_lock_sha256": lock_sha,
                      "occurrences": sum(len(req["items"]) for req in requests),
                      "unpinned_occurrences": sum(item["revision"] is None
                          for req in requests for item in req["items"]),
                      "duplicate_source_groups_across_active_pages": duplicate_sources(items, owners),
                      "requests": [{"request_sha256": digest(req), "path": str(path)}
                                   for req, path in zip(requests, paths)],
                      "translation_mutated": False, "publication_authorized": False}
        else:
            result = inspect_handoff(load_json(args.request), load_json(args.handoff),
                                     args.handoff_sha, lock_sha, items, owners)
    except (ValueError, RuntimeError, OSError, KeyError, TypeError, AttributeError) as exc:
        # Do not echo source text, malformed JSON, or a raw traceback.
        reason = str(exc) if isinstance(exc, QuoteBridgeError) else type(exc).__name__
        print(json.dumps({"status": "blocked", "reason": reason}))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
