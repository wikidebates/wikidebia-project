import copy
import pytest

from experimental_prepared_citations import (
    digest, text_digest, source_parameters_key, project, restore,
    prepared_index, PACKET,
)
from wikidebia_translation_patch import PATCH_SCHEMA
from wikidebia_update import sha_object


def fixture():
    source = {"id": "A1-C001", "source_template": "Citation",
              "source_parameters": [{"name": "citation", "value": "Phrase française test."},
                                    {"name": "lien", "value": "https://www.marxists.org/francais/test.htm"}],
              "citation": "Phrase française test."}
    other = copy.deepcopy(source)
    other["id"] = "A1-C002"
    other["source_parameters"][1]["value"] = "https://example.org/test"
    quote = "Exact English test sentence."
    a, b = source_parameters_key(source)
    identity = {"schema": "wikidebia-mia-prepared-source-1", "provider": "mia",
                "mia_url": source["source_parameters"][1]["value"],
                "quote_sha256": text_digest(source["citation"]),
                "quote_wikitext_sha256": a, "metadata_sha256": b}
    source_key = digest(identity)
    fragment = {"char_start": 0, "char_end": len(quote), "text_sha256": text_digest(quote)}
    receipt = {"schema": "wikidebia-prepared-citation-receipt-1",
               "source": {**identity, "source_key": source_key},
               "target": {"document": {"url": "https://www.marxists.org/archive/test.htm"}},
               "decision": "complete_equivalent", "fragments": [fragment],
               "semantic_status": "editorial_decision_recorded",
               "rights": "unreviewed", "auto_publish": False}
    receipt["entry_sha256"] = digest(receipt)
    result = {"status": "reviewed_passage_reconstructed", "source_key": source_key,
              "receipt": receipt, "fragments": [{**fragment, "text": quote}]}
    rows = [{"id": s["id"], "source": s, "status": "pending",
             "translated_citation": "", "citation_translated": False}
            for s in (source, other)]
    packet = {"schema": PACKET, "debate_id": "d", "work_id": "w", "unit": {"id": "U001"},
              "translation_review_content_sha256": "review",
              "current_content_reviewed_copy_sha256": "copy", "vocabulary": [], "relation_labels": [],
              "arguments": [{"id": "A1", "source_changed": False,
                  "current_french": {"content": {"citations": [source, other]}},
                  "translation": {"status": "pending", "citations": rows}}]}
    packet["packet_sha256"] = sha_object(packet)
    patch = {"schema": PATCH_SCHEMA, "debate_id": "d", "work_id": "w", "unit_id": "U001",
             "status": "draft", "patch_sha256": None, "base_packet_sha256": packet["packet_sha256"],
             "base_translation_review_content_sha256": "review",
             "base_content_reviewed_copy_sha256": "copy",
             "vocabulary": [], "relation_labels": [], "unit_decision": {"status": "pending"},
             "arguments": [{"id": "A1", "translation": copy.deepcopy(packet["arguments"][0]["translation"])}],
             "remote_access_performed": False, "remote_write_performed": False}
    return packet, patch, result, quote


def test_round_trip_removes_both_copies_and_restores_only_verified_text():
    packet, patch, result, quote = fixture()
    before = copy.deepcopy((packet, patch))
    view, edit, manifest, stats = project(packet, patch, [result])
    assert (packet, patch) == before
    assert stats["withheld_citations"] == 1
    assert view["arguments"][0]["withheld_citation_ids"] == ["A1-C001"]
    assert [x["id"] for x in view["arguments"][0]["current_french"]["content"]["citations"]] == ["A1-C002"]
    assert [x["id"] for x in view["arguments"][0]["translation"]["citations"]] == ["A1-C002"]
    assert [x["id"] for x in edit["arguments"][0]["translation"]["citations"]] == ["A1-C002"]
    edit["arguments"][0]["translation"]["citations"][0]["translated_citation"] = "AI translation"
    edit["unit_decision"]["status"] = "approved"
    restored = restore(packet, patch, edit, manifest, stats["manifest_sha256"])
    rows = restored["arguments"][0]["translation"]["citations"]
    assert [x["id"] for x in rows] == ["A1-C001", "A1-C002"]
    assert rows[0]["translated_citation"] == quote
    assert rows[0]["source"] == patch["arguments"][0]["translation"]["citations"][0]["source"]
    assert rows[0]["status"] == "pending"
    assert rows[0]["citation_translated"] is False
    assert rows[1]["translated_citation"] == "AI translation"
    assert restored["unit_decision"]["status"] == "pending"


def test_tampered_receipt_or_fragment_rejected():
    packet, patch, result, _ = fixture()
    result["fragments"][0]["text"] += "!"
    with pytest.raises(ValueError, match="prepared_fragment_text_mismatch"):
        project(packet, patch, [result])
    packet, patch, result, _ = fixture()
    result["receipt"]["source"]["mia_url"] = "https://example.org/test"
    with pytest.raises(ValueError, match="invalid_prepared_receipt"):
        project(packet, patch, [result])


def test_modified_manifest_and_injected_withheld_row_rejected():
    packet, patch, result, _ = fixture()
    _, edit, manifest, stats = project(packet, patch, [result])
    modified = copy.deepcopy(manifest)
    modified["prepared"]["A1"]["A1-C001"]["text"] = "fabricated"
    with pytest.raises(ValueError, match="projection_manifest_mismatch"):
        restore(packet, patch, edit, modified, stats["manifest_sha256"])
    edit["arguments"][0]["translation"]["citations"].append(
        copy.deepcopy(patch["arguments"][0]["translation"]["citations"][0]))
    with pytest.raises(ValueError, match="edited_citation_scope_changed"):
        restore(packet, patch, edit, manifest, stats["manifest_sha256"])


def test_existing_translation_and_changed_source_not_withheld():
    packet, patch, result, _ = fixture()
    packet["arguments"][0]["source_changed"] = True
    packet["packet_sha256"] = sha_object({k:v for k,v in packet.items() if k!="packet_sha256"})
    patch["base_packet_sha256"] = packet["packet_sha256"]
    assert project(packet, patch, [result])[3]["withheld_citations"] == 0
    packet, patch, result, _ = fixture()
    for item in (packet, patch):
        item["arguments"][0]["translation"]["citations"][0]["translated_citation"] = "Existing"
    packet["packet_sha256"] = sha_object({k:v for k,v in packet.items() if k!="packet_sha256"})
    patch["base_packet_sha256"] = packet["packet_sha256"]
    assert project(packet, patch, [result])[3]["withheld_citations"] == 0


def test_empty_preparation_preserves_all_rows():
    packet, patch, _, _ = fixture()
    _, edit, manifest, stats = project(packet, patch, [])
    assert stats["withheld_citations"] == 0
    assert restore(packet, patch, edit, manifest, stats["manifest_sha256"]) == patch


def test_changed_metadata_does_not_match():
    packet, patch, result, _ = fixture()
    source = packet["arguments"][0]["current_french"]["content"]["citations"][0]
    source["source_parameters"].append({"name": "auteurs", "value": "Different author"})
    # Both copies in packet share source; patch is independent.
    patch["arguments"][0]["translation"]["citations"][0]["source"] = copy.deepcopy(source)
    packet["packet_sha256"] = sha_object({k:v for k,v in packet.items() if k!="packet_sha256"})
    patch["base_packet_sha256"] = packet["packet_sha256"]
    assert project(packet, patch, [result])[3]["withheld_citations"] == 0
