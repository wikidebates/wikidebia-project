from copy import deepcopy
import json
from pathlib import Path

import pytest
import wikidebia_quote_bridge as bridge
import wikidebia_published_quote_contract as contract
import wikidebia_published_quote_review as review
import wikidebia_published_quote_selection as selection
from wikidebia_translation_review import TRANSLATION_REVIEW_SCHEMA, _blank_citation
from test_wikidebia_published_quote_review import fixture,prepare,completed,LOCK


def draft_fixture():
    src,row=fixture()
    candidate,=prepare(src,row)
    evidence=review.make_evidence(candidate,bridge.digest(candidate),completed(candidate))
    french={"id":src["id"],"source_template":src["source_template"],
            "source_parameters":deepcopy(src["source_parameters"]),
            "citation":src["source_parameters"][0]["value"]}
    content={"id":"A0001","citations":[french]}
    draft={"schema":TRANSLATION_REVIEW_SCHEMA,"status":"draft","review_sha256":None,
           "arguments":[{"id":"A0001","translation":{"status":"pending",
               "french":{"content":deepcopy(content)},"citations":[_blank_citation(french)]}}]}
    return draft,src,content,evidence


def pick(draft,src,content,*evidence):
    return selection.select_draft(draft,LOCK,[src],{src["id"]:"A0001"},[content],evidence)


def test_select_exact_proposal_without_approving_or_mutating_source():
    draft,src,content,evidence=draft_fixture()
    before=deepcopy(draft)
    updated,summary=pick(draft,src,content,evidence)
    row=updated["arguments"][0]["translation"]["citations"][0]
    assert updated["published_quote_contract"]==contract.EVIDENCE
    assert updated["status"]=="draft" and row["status"]=="pending"
    assert row["translated_citation"]==evidence["candidate"]["plain_quote"]
    assert row["translated_date"]==""
    assert row["published_quote_evidence"]==evidence
    assert not row["quote_completeness_reviewed"] and not row["translation_warning_appended"]
    assert row["source"]==content["citations"][0]
    assert summary=={"selected":[src["id"]],"already_selected":[]}
    assert draft==before
    # Another invocation preserves even subsequent editorial work on that row.
    row["status"]="approved"
    again,summary=pick(updated,src,content,evidence)
    assert again==updated
    assert summary=={"selected":[],"already_selected":[src["id"]]}


@pytest.mark.parametrize("change",["draft_text","approved","argument_approved","sealed","wrong_source","wrong_lock"])
def test_refuses_overwrite_or_wrong_binding(change):
    draft,src,content,evidence=draft_fixture()
    row=draft["arguments"][0]["translation"]["citations"][0]
    if change=="draft_text":
        row["translated_citation"]="Existing editorial work."
    elif change=="approved":
        row["status"]="approved"
    elif change=="argument_approved":
        draft["arguments"][0]["translation"]["status"]="approved"
    elif change=="sealed":
        draft["status"]="approved"
    elif change=="wrong_source":
        row["source"]["citation"]="Changed source."
    else:
        evidence["candidate"]["source_lock_sha256"]="f"*64
    before=deepcopy(draft)
    with pytest.raises((bridge.QuoteBridgeError,contract.PublishedQuoteError)):
        pick(draft,src,content,evidence)
    assert draft==before


def test_duplicate_batch_and_ineligible_citation_are_atomic():
    draft,src,content,evidence=draft_fixture()
    before=deepcopy(draft)
    for rows in ([evidence,evidence],[]):
        with pytest.raises(bridge.QuoteBridgeError):
            pick(draft,src,content,*rows)
        assert draft==before
    with pytest.raises(bridge.QuoteBridgeError,match="not_eligible"):
        selection.select_draft(draft,LOCK,[],{},[content],[evidence])


def test_evidence_files_are_private_and_content_addressed(tmp_path):
    _,_,_,evidence=draft_fixture()
    path=review.write_private(tmp_path,evidence,"evidence")
    assert selection.read_evidence(tmp_path,path)==evidence
    copy_path=tmp_path/path.name
    copy_path.write_bytes(path.read_bytes())
    with pytest.raises(bridge.QuoteBridgeError,match="private_evidence_path"):
        selection.read_evidence(tmp_path,copy_path)
    path.write_text("{}")
    with pytest.raises(bridge.QuoteBridgeError,match="file_digest_mismatch"):
        selection.read_evidence(tmp_path,path)


def test_atomic_draft_write_checks_original_bytes(tmp_path):
    path=tmp_path/"draft.json"
    path.write_bytes(b"{}\n")
    with pytest.raises(bridge.QuoteBridgeError,match="concurrent_draft_change"):
        selection._write_draft(path,{"status":"draft"},b"other")
    assert path.read_bytes()==b"{}\n"
    selection._write_draft(path,{"status":"draft"},b"{}\n")
    assert json.loads(path.read_bytes())=={"status":"draft"}
    assert path.stat().st_mode & 0o077 == 0
