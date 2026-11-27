"""Experimental offline adapter for the quote resolver and kit unit packets.

Not part of the normal translation workflow. Only a trusted local caller
may pass CitationRegistry.reconstruct results. A receipt is a hash-bound
record, not a signature, a rights decision, or editorial publication approval.
The original signed packet and full patch stay local. The projected packet
and patch have distinct schemas and cannot be used by the ordinary kit.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter

from wikidebia_translation_patch import PATCH_SCHEMA, _verify_scope
from wikidebia_update import sha_object

VIEW = "wikidebia-experimental-prepared-citation-packet-1"
EDIT = "wikidebia-experimental-prepared-citation-patch-1"
MANIFEST = "wikidebia-experimental-prepared-citation-manifest-1"
PACKET = "wikidebia-translation-unit-packet-1.0"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def text_digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def is_digest(value):
    return isinstance(value, str) and len(value) == 64 and all(
        c in "0123456789abcdef" for c in value)


def index_rows(rows):
    result = {}
    for row in rows:
        cid = row["id"]
        if not isinstance(cid, str) or not cid or cid in result:
            raise ValueError("duplicate_or_invalid_row_id")
        result[cid] = row
    return result


def source_parameters_key(source):
    """Same exact raw parameter identity as the resolver. No title guessing."""
    if source.get("source_template", "").strip().casefold() != "citation":
        raise ValueError("unsupported_source_template")
    pairs = sorted((p["name"].strip(), p["value"].strip())
                   for p in source["source_parameters"])
    if len({p[0] for p in pairs}) != len(pairs):
        raise ValueError("duplicate_source_parameter")
    quote = [v for k, v in pairs if k == "citation"]
    links = [v for k, v in pairs if k == "lien"]
    if len(quote) != 1 or len(links) != 1 or not quote[0] or not links[0]:
        raise ValueError("missing_literal_source_parameter")
    if source.get("citation", "").strip() != quote[0]:
        raise ValueError("source_quote_mismatch")
    return (text_digest(quote[0]), digest([(k, v) for k, v in pairs if k != "citation"]))


def receipt_source_key(receipt):
    source = receipt["source"]
    body = {k: source[k] for k in ("schema", "provider", "mia_url", "quote_sha256",
                                  "quote_wikitext_sha256", "metadata_sha256")}
    if (body["schema"] != "wikidebia-mia-prepared-source-1"
            or body["provider"] != "mia" or digest(body) != source["source_key"]):
        raise ValueError("invalid_receipt_source_identity")
    return (source["quote_wikitext_sha256"], source["metadata_sha256"])


def prepared_index(reconstructed):
    """Index only exact registry materializations. Text never sent to AI."""
    index = {}
    conflicts = set()
    for result in reconstructed:
        if result.get("status") != "reviewed_passage_reconstructed":
            continue
        receipt = result["receipt"]
        body = {k: v for k, v in receipt.items() if k != "entry_sha256"}
        if (receipt.get("schema") != "wikidebia-prepared-citation-receipt-1"
                or digest(body) != receipt.get("entry_sha256")
                or result.get("source_key") != receipt["source"]["source_key"]
                or receipt.get("semantic_status") != "editorial_decision_recorded"
                or receipt.get("decision") not in {"complete_equivalent",
                    "boundary_adjustment", "omission_adjustment"}
                or receipt.get("rights") != "unreviewed" or receipt.get("auto_publish") is not False):
            raise ValueError("invalid_prepared_receipt")
        key = receipt_source_key(receipt)
        fragments = result["fragments"]
        if not fragments or [{k: v for k, v in f.items() if k != "text"}
                             for f in fragments] != receipt["fragments"]:
            raise ValueError("prepared_fragment_identity_mismatch")
        if any(text_digest(f["text"]) != f["text_sha256"] for f in fragments):
            raise ValueError("prepared_fragment_text_mismatch")
        # A literal editorial omission marker is inserted between independently
        # verified fragments; its final formatting still requires review.
        value = {"source_key": result["source_key"], "receipt_sha256": receipt["entry_sha256"],
                 "target_url": receipt["target"]["document"]["url"],
                 "text": " […] ".join(f["text"] for f in fragments),
                 "fragment_sha256": [f["text_sha256"] for f in fragments]}
        if key in index and (index[key]["text"], index[key]["target_url"]) != (
                value["text"], value["target_url"]):
            conflicts.add(key)
        index[key] = value
    for key in conflicts:
        index.pop(key, None)
    return index


def check_pair(packet, patch):
    unsigned = {k: v for k, v in packet.items() if k != "packet_sha256"}
    if (packet.get("schema") != PACKET or sha_object(unsigned) != packet.get("packet_sha256")
            or patch.get("schema") != PATCH_SCHEMA or patch.get("status") != "draft"
            or patch.get("patch_sha256") is not None
            or patch.get("base_packet_sha256") != packet.get("packet_sha256")
            or patch.get("base_translation_review_content_sha256") != packet.get("translation_review_content_sha256")
            or patch.get("base_content_reviewed_copy_sha256") != packet.get("current_content_reviewed_copy_sha256")
            or patch.get("unit_id") != packet["unit"]["id"]
            or any(packet[k] != patch.get(k) for k in ("debate_id", "work_id"))):
        raise ValueError("invalid_base_packet_or_patch")
    _verify_scope(patch, packet)
    if len(index_rows(packet["arguments"])) != len(index_rows(patch["arguments"])):
        raise ValueError("argument_scope_mismatch")


def project(packet, patch, reconstructed):
    """Hide prepared citation rows from both the AI view and edit template.

    Skip changed sources and any previously populated or approved target.
    No metadata/rights/linguistic approval is invented. The private manifest
    must be retained together with its digest, out of band from the AI.
    """
    check_pair(packet, patch)
    prepared = prepared_index(reconstructed)
    view = copy.deepcopy(packet)
    edit = copy.deepcopy(patch)
    view["schema"] = VIEW
    view["base_packet_sha256"] = view.pop("packet_sha256")
    edit["schema"] = EDIT
    edits = index_rows(edit["arguments"])
    records = {}
    counts = Counter()
    for arg in view["arguments"]:
        page_id = arg["id"]
        source_rows = arg["current_french"]["content"].get("citations") or []
        target_rows = arg["translation"].get("citations") or []
        patch_rows = edits[page_id]["translation"].get("citations") or []
        source_by_id, target_by_id, patch_by_id = map(index_rows, (source_rows, target_rows, patch_rows))
        if set(source_by_id) != set(target_by_id) or target_by_id != patch_by_id:
            raise ValueError("citation_scope_mismatch")
        hidden = []
        for cid, source in source_by_id.items():
            target = target_by_id[cid]
            if target.get("source") != source:
                raise ValueError("target_source_mismatch")
            try:
                key = source_parameters_key(source)
            except (KeyError, TypeError, ValueError, AttributeError):
                counts["unsupported_source"] += 1
                continue
            if key not in prepared:
                counts["no_prepared_match"] += 1
                continue
            if (arg.get("source_changed") is not False
                    or target.get("status") != "pending"
                    or target.get("translated_citation") not in ("", None)):
                counts["not_blank_or_source_changed"] += 1
                continue
            hidden.append(cid)
            records.setdefault(page_id, {})[cid] = {
                "source_sha256": digest(source), "target_before_sha256": digest(target),
                **copy.deepcopy(prepared[key]),
            }
        if hidden:
            hidden_set = set(hidden)
            for owner, rows in ((arg["current_french"]["content"], source_rows),
                                (arg["translation"], target_rows),
                                (edits[page_id]["translation"], patch_rows)):
                owner["citations"] = [row for row in rows if row["id"] not in hidden_set]
            # Keep anchors intact; the withheld IDs will be restored before
            # any kit validation or application. The AI cannot edit them.
            arg["withheld_citation_ids"] = hidden
    manifest = {"schema": MANIFEST, "base_packet_sha256": packet["packet_sha256"],
                "base_patch_sha256": digest(patch), "prepared": records,
                "rights_approved": False, "auto_publish": False}
    manifest_sha = digest(manifest)
    view["prepared_citations_manifest_sha256"] = manifest_sha
    edit["prepared_citations_manifest_sha256"] = manifest_sha
    view["experimental_note"] = ("Withheld citation rows will be restored locally; "
        "do not generate, translate, approve or change their anchors. "
        "Their editorial and rights review is not yet complete.")
    return view, edit, manifest, {"withheld_citations": sum(map(len, records.values())),
        "counts": dict(counts), "manifest_sha256": manifest_sha,
        "baseline_input_bytes": len(canonical(packet)) + len(canonical(patch)),
        "projected_input_bytes": len(canonical(view)) + len(canonical(edit))}


def restore(packet, original_patch, edited_patch, manifest, expected_manifest_sha):
    """Restore exact full citation rows, with pending editorial status.

    This does not seal, apply, or publish anything. The caller must run the
    normal review/validation flow once the published-quotation policy exists.
    """
    check_pair(packet, original_patch)
    if (manifest.get("schema") != MANIFEST or digest(manifest) != expected_manifest_sha
            or manifest.get("base_packet_sha256") != packet["packet_sha256"]
            or manifest.get("base_patch_sha256") != digest(original_patch)
            or manifest.get("rights_approved") is not False
            or manifest.get("auto_publish") is not False
            or edited_patch.get("schema") != EDIT
            or edited_patch.get("prepared_citations_manifest_sha256") != expected_manifest_sha):
        raise ValueError("projection_manifest_mismatch")
    out = copy.deepcopy(edited_patch)
    out["schema"] = PATCH_SCHEMA
    out.pop("prepared_citations_manifest_sha256")
    for k in ("debate_id", "work_id", "unit_id", "status", "base_packet_sha256",
              "base_translation_review_content_sha256", "base_content_reviewed_copy_sha256",
              "patch_sha256", "remote_access_performed", "remote_write_performed"):
        if out.get(k) != original_patch.get(k):
            raise ValueError("edited_patch_scope_changed")
    _verify_scope(out, packet)
    original = index_rows(original_patch["arguments"])
    output = index_rows(out["arguments"])
    if set(original) != set(output) or not set(manifest["prepared"]) <= set(original):
        raise ValueError("edited_argument_scope_changed")
    for page_id, row in output.items():
        expected = index_rows(original[page_id]["translation"].get("citations") or [])
        supplied = index_rows(row["translation"].get("citations") or [])
        hidden = manifest["prepared"].get(page_id, {})
        if not set(hidden) <= set(expected) or set(supplied) != set(expected) - set(hidden):
            raise ValueError("edited_citation_scope_changed")
        full = []
        for cid, original_row in expected.items():
            if cid in hidden:
                record = hidden[cid]
                if (digest(original_row) != record["target_before_sha256"]
                        or digest(original_row["source"]) != record["source_sha256"]):
                    raise ValueError("prepared_citation_stale")
                row_copy = copy.deepcopy(original_row)
                row_copy["translated_citation"] = record["text"]
                # Do not fabricate any attestations or change references.
                row_copy["status"] = "pending"
                full.append(row_copy)
            else:
                if supplied[cid].get("source") != original_row.get("source"):
                    raise ValueError("edited_citation_source_changed")
                full.append(supplied[cid])
        if expected or "citations" in row["translation"]:
            row["translation"]["citations"] = full
        if hidden:
            row["translation"]["status"] = "pending"
    if manifest["prepared"]:
        out["unit_decision"]["status"] = "pending"
    check_pair(packet, out)
    return out
