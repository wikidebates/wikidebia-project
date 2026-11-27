from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import wikidebia_quote_bridge as bridge
from test_wikidebia_translation_review import (
    common, make_french_locked, mark_existing_english_argument,
)


def item(cid="A0001-C001", title="Argument A", revision=17):
    return {"id": cid, "wiki_title": title, "revision": revision,
            "source_template": "Citation",
            "source_parameters": [
                {"name": "citation", "value": "Citation de test."},
                {"name": "lien", "value": "https://www.marxists.org/francais/test/a.htm"},
            ]}


def request(*items):
    return {"schema": bridge.REQUEST, "source_lock_sha256": "a"*64,
            "items": list(items)}


def envelope(req, rows, packets=()):
    return {"schema": bridge.HANDOFF, "request_sha256": bridge.digest(req),
            "source_lock_sha256": req["source_lock_sha256"], "rows": list(rows),
            "packets": list(packets), "rights": "unreviewed", "auto_publish": False}


def row_for(src, state):
    return {"id": src["id"], "state": state,
            "source_parameters_sha256": bridge.digest(src["source_parameters"])}


def reviewed(src):
    """Synthetic serialized receipt, not evidence of linguistic equivalence."""
    params = bridge.parameter_pairs(src["source_parameters"])
    text = "Synthetic test passage."
    source = {"source_key": "b"*64,
              "quote_wikitext_sha256": hashlib.sha256(params["citation"].encode()).hexdigest(),
              "metadata_sha256": bridge.digest(sorted(
                  (k, v) for k, v in params.items() if k != "citation"))}
    proof = {"char_start": 2, "char_end": 2+len(text),
             "text_sha256": hashlib.sha256(text.encode()).hexdigest()}
    entry = {"schema": bridge.RECEIPT, "source": source,
             "fragments": [proof], "rights": "unreviewed", "auto_publish": False,
             "semantic_status": "editorial_decision_recorded"}
    sha = bridge.digest(entry)
    return {**row_for(src, bridge.REVIEWED), "source_key": source["source_key"],
            "citation_ref": {"revision": src["revision"]},
            "evidence": {"receipt_sha256": sha},
            "published_passage": {"receipt": {**entry, "entry_sha256": sha},
                                  "fragments": [{**proof, "text": text}],
                                  "rights": "unreviewed", "auto_publish": False,
                                  "editorial_review_required": True}}


def inspect(req, handoff, *, lock_sha=None):
    return bridge.inspect_handoff(req, handoff, bridge.digest(handoff),
                                  lock_sha or req["source_lock_sha256"], req["items"],
                                  {s["id"]: s["id"].rsplit("-C", 1)[0] for s in req["items"]})


def test_export_from_real_locked_workspace_and_private_idempotent_requests(tmp_path):
    project, workspace, work_id = make_french_locked(tmp_path)
    source = workspace / "content-reviewed-copy"
    before = common.full_tree_sha256(source)
    workspace_meta = (workspace / "workspace.json").read_bytes()
    _, lock_sha, items, owners = bridge.snapshot(project, "debat_test", work_id)
    content = common.load_json(source / "data/fr_content_lock.json")
    provenance = common.load_json(source / "data/import_provenance.json")
    expected = {c["id"]: c for page in content["arguments"] for c in page["citations"]}
    imports = {p["page_id"]: p for p in provenance["pages"] if p.get("kind") == "argument"}
    assert items and {r["id"] for r in items} == set(expected)
    for r in items:
        assert r["source_parameters"] == expected[r["id"]]["source_parameters"]
        p = imports[owners[r["id"]]]
        assert r["revision"] == p.get("revision_id")
        assert r["wiki_title"] == p["canonical_title"]
    assert lock_sha == common.sha256_file(source / "data/fr_content_lock.json")
    requests = bridge.requests_for(lock_sha, items, owners, batch_size=2)
    assert sum(len(r["items"]) for r in requests) == len(items)
    for req in requests:
        path = bridge.write_private_request(workspace, req)
        assert bridge.write_private_request(workspace, req) == path
        assert path.stat().st_mode & 0o077 == 0
        assert json.loads(path.read_text()) == req
    assert common.full_tree_sha256(source) == before
    assert (workspace / "workspace.json").read_bytes() == workspace_meta
    assert not (workspace / "translated-copy").exists()
    mark_existing_english_argument(workspace)
    _, new_sha, active, active_owners = bridge.snapshot(project, "debat_test", work_id)
    assert "A0004" not in set(active_owners.values())
    assert len(active) < len(items)
    for req in requests:
        if any(owners[r["id"]] == "A0004" for r in req["items"]):
            with pytest.raises(bridge.QuoteBridgeError, match="request_occurrence_changed"):
                bridge.validate_request(req, new_sha, active)


def test_changed_lock_rejected_before_export(tmp_path):
    project, workspace, work_id = make_french_locked(tmp_path)
    path = workspace / "content-reviewed-copy/data/fr_content_lock.json"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(Exception, match="a changé depuis le verrouillage"):
        bridge.snapshot(project, "debat_test", work_id)


def test_exact_parameters_batches_and_page_selection():
    items = [item(), item("A0002-C001"), item("A0002-C002", revision=None)]
    owners = {r["id"]: r["id"].rsplit("-C", 1)[0] for r in items}
    batches = bridge.requests_for("a"*64, items, owners, batch_size=1, page_ids=["A0002"])
    assert [r["items"][0] for r in batches] == items[1:]
    assert bridge.duplicate_sources(items, owners) == 1
    with pytest.raises(bridge.QuoteBridgeError):
        bridge.requests_for("a"*64, items, owners, page_ids=["A9999"])
    with pytest.raises(bridge.QuoteBridgeError):
        bridge.requests_for("a"*64, items, owners, batch_size=201)
    with pytest.raises(bridge.QuoteBridgeError):
        bridge.parameter_pairs(items[0]["source_parameters"]*2)


def test_reviewed_passages_remain_advisory_and_duplicates_are_reported():
    first, second = item(), item("A0002-C001", "Argument B", 18)
    req = request(first, second)
    handoff = envelope(req, [reviewed(first), reviewed(second)])
    summary = inspect(req, handoff)
    assert summary["states"] == {bridge.REVIEWED: 2}
    assert summary["duplicate_published_groups_across_pages_in_batch"] == 1
    assert summary["publication_authorized"] is False
    assert summary["translation_mutated"] is False
    assert "Synthetic test passage." not in json.dumps(summary)


def test_tampered_fragment_and_wrong_receipt_fail_even_with_recomputed_envelope():
    src = item()
    req = request(src)
    handoff = envelope(req, [reviewed(src)])
    tampered = copy.deepcopy(handoff)
    tampered["rows"][0]["published_passage"]["fragments"][0]["text"] = "Tampered"
    with pytest.raises(bridge.QuoteBridgeError, match="fragment_integrity"):
        inspect(req, tampered)
    another = item()
    another["source_parameters"][0]["value"] = "Different French citation."
    row = reviewed(another)
    row["source_parameters_sha256"] = bridge.digest(src["source_parameters"])
    with pytest.raises(bridge.QuoteBridgeError, match="receipt_source"):
        inspect(req, envelope(req, [row]))


def test_stale_request_missing_rows_and_unapproved_rights_are_refused():
    src = item()
    req = request(src)
    handoff = envelope(req, [row_for(src, "ai_translation_required")])
    with pytest.raises(bridge.QuoteBridgeError, match="source_lock"):
        inspect(req, handoff, lock_sha="c"*64)
    with pytest.raises(bridge.QuoteBridgeError, match="occurrence_coverage"):
        inspect(req, envelope(req, []))
    bad = copy.deepcopy(handoff)
    bad["auto_publish"] = True
    with pytest.raises(bridge.QuoteBridgeError, match="identity_mismatch"):
        inspect(req, bad)
    bad = copy.deepcopy(handoff)
    bad["rows"][0]["published_passage"] = {}
    with pytest.raises(bridge.QuoteBridgeError, match="unreviewed_row"):
        inspect(req, bad)


def test_pending_review_must_be_bound_to_exact_request_occurrence_and_packet():
    src = item()
    req = request(src)
    ref = {"revision": src["revision"], "template_index": 0}
    packet = {"translation_request_sha256": bridge.digest(req),
              "source_lock_sha256": req["source_lock_sha256"],
              "sources": {"q1": {"source_key": "b"*64, "occurrences": [
                  {"case_id": src["id"], "wiki_title": src["wiki_title"], "ref": ref}]}}}
    sha = bridge.digest(packet)
    row = {**row_for(src, bridge.PENDING), "packet_sha256": sha,
           "citation_ref": ref, "source_key": "b"*64}
    handoff = envelope(req, [row], [{"packet_sha256": sha, "packet": packet}])
    assert inspect(req, handoff)["packets"] == 1
    with pytest.raises(bridge.QuoteBridgeError, match="row_mismatch"):
        inspect(req, envelope(req, [row]))
    packet["sources"]["q1"]["occurrences"][0]["wiki_title"] = "Wrong page"
    changed = bridge.digest(packet)
    with pytest.raises(bridge.QuoteBridgeError, match="packet_source_mismatch"):
        inspect(req, envelope(req, [{**row, "packet_sha256": changed}],
                              [{"packet_sha256": changed, "packet": packet}]))
