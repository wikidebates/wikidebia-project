from copy import deepcopy
from datetime import date
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import wikidebia_quote_bridge as bridge
import wikidebia_published_quote_review as review
from test_wikidebia_quote_bridge import item, request, envelope, reviewed, row_for

LOCK="a"*64


def fixture(decision="complete_equivalent"):
    src=item()
    row=reviewed(src)
    p=row["published_passage"]
    receipt=p["receipt"]
    source=receipt["source"]
    source.update(schema="wikidebia-mia-prepared-source-1",provider="mia",
                  mia_url="https://www.marxists.org/francais/test/a.htm",
                  quote_sha256="d"*64,has_explicit_ellipsis=decision=="omission_adjustment",
                  occurrence={"revision":4,"template_index":0,"template_sha256":"e"*64})
    source["source_key"]=bridge.digest({k:source[k] for k in review.SOURCE_FIELDS})
    row["source_key"]=source["source_key"]
    row["citation_ref"]={"revision":17,"template_index":0,"template_sha256":"c"*64,
                         "quote_sha256":source["quote_sha256"]}
    row["evidence"].update(origin="revalidated_existing_receipt",publication={},rights="unreviewed")
    receipt.update(decision=decision,reviewer="Synthetic reviewer",review_packet_sha256="f"*64)
    frags=p["fragments"]
    if decision=="omission_adjustment":
        frags[:]=[{"char_start":2,"char_end":5,"text":"One",
                   "text_sha256":hashlib.sha256(b"One").hexdigest()},
                  {"char_start":9,"char_end":12,"text":"two",
                   "text_sha256":hashlib.sha256(b"two").hexdigest()}]
        receipt["fragments"]=[{k:v for k,v in f.items() if k!="text"} for f in frags]
    proof=receipt["fragments"][0]
    target={"document":{"url":"https://www.marxists.org/archive/test/a.htm","revision":None,
                        "body_sha256":"a"*64,"blocks_sha256":"b"*64},
            "char_start":1 if decision=="boundary_adjustment" else proof["char_start"],
            "char_end":receipt["fragments"][-1]["char_end"],
            "text_sha256":proof["text_sha256"] if decision=="complete_equivalent" else "1"*64}
    target["candidate_key"]=bridge.digest(target)
    receipt["target"]=target
    seal_row(row)
    return src,row


def seal_row(row):
    receipt=row["published_passage"]["receipt"]
    receipt["entry_sha256"]=bridge.digest({k:v for k,v in receipt.items() if k!="entry_sha256"})
    row["evidence"]["receipt_sha256"]=receipt["entry_sha256"]


def prepare(src,row):
    req=request(src)
    handoff=envelope(req,[row])
    return review.prepare(req,handoff,bridge.digest(handoff),LOCK,[src],{src["id"]:"A0001"})


def completed(candidate):
    r=review.blank(candidate)
    r["status"]="reviewed_for_proposal"
    r["edition"].update(authors="Verified author",work="Published English work",
                        link=candidate["target_url"])
    r["edition_review"].update(reviewer="Synthetic editor",reviewed_on="2026-11-27",
        evidence_urls=[candidate["target_url"]],same_work_and_authorship_confirmed=True,
        english_edition_metadata_verified=True,missing_metadata_reviewed=True,
        attribution_and_translation_credit_preserved=True,
        note="Synthetic evidence test; this is not a real bibliographic decision.")
    r["rights_review"].update(status="reuse_reviewed",basis="public_domain",
        reviewer="Synthetic rights reviewer",reviewed_on="2026-11-27",
        evidence_urls=["https://example.org/rights"],exact_passage_and_target_site_reviewed=True,
        all_conditions_representable=True,note="Synthetic evidence test only; no real rights determination.")
    r["completeness_review"].update(reviewer="Synthetic editor",reviewed_on="2026-11-27",
        note="Synthetic check of the full meaning and boundaries of the quotation.",
        full_meaning_and_boundaries_confirmed=True)
    return r


def test_prepare_pending_then_explicitly_reviewed_proposal_not_publication():
    src,row=fixture()
    candidate,=prepare(src,row)
    assert candidate["rights"]=="unreviewed"
    pending=review.blank(candidate)
    assert pending["edition"]["link"] is None
    with pytest.raises(bridge.QuoteBridgeError):
        review.proposal(candidate,bridge.digest(candidate),pending)
    result=review.proposal(candidate,bridge.digest(candidate),completed(candidate))
    params={p["name"]:p["value"] for p in result["parameters"]}
    assert params=={"quote":"Synthetic test passage.","authors":"Verified author",
                    "work":"Published English work","link":candidate["target_url"]}
    assert result["publication_authorized"] is False and result["translation_mutated"] is False
    assert result["translation_origin"]=="published_translation"
    assert "AI-translated quote" not in json.dumps(result)


def test_receipt_rejects_wrong_boundaries_current_revision_or_target_identity():
    src,row=fixture()
    for mutation in (
        lambda r:r["citation_ref"].update(quote_sha256="0"*64),
        lambda r:r["published_passage"]["receipt"].update(decision="wrong_passage"),
        lambda r:r["published_passage"]["receipt"]["target"].update(candidate_key="0"*64),
        lambda r:r["published_passage"]["receipt"]["source"].update(mia_url="https://example.org/a"),
        lambda r:r["evidence"].update(origin="not_revalidated"),
    ):
        bad=deepcopy(row)
        mutation(bad)
        seal_row(bad)
        with pytest.raises(bridge.QuoteBridgeError):
            prepare(src,bad)


def test_no_reviewed_candidate_for_ai_or_retry_rows():
    src=item()
    assert not prepare(src,row_for(src,"ai_translation_required"))
    assert not prepare(src,row_for(src,"retry_documentary"))


def test_omission_marker_preserves_discontinuous_fragments():
    candidate,=prepare(*fixture("omission_adjustment"))
    result=review.proposal(candidate,bridge.digest(candidate),completed(candidate))
    assert result["parameters"][0]["value"]=="One […] two"


def test_edition_rights_attribution_and_exact_binding_are_required():
    candidate,=prepare(*fixture())
    for change in (
        lambda r:r["edition"].update(link="https://example.org/other"),
        lambda r:r["edition"].update(work=None),
        lambda r:r["edition_review"].update(attribution_and_translation_credit_preserved=False),
        lambda r:r["edition_review"].update(evidence_urls=["https://example.org/other"]),
        lambda r:r["rights_review"].update(status="pending"),
        lambda r:r["rights_review"].update(basis="found_online"),
        lambda r:r["rights_review"].update(all_conditions_representable=False),
        lambda r:r["rights_review"].update(evidence_urls=[]),
        lambda r:r["completeness_review"].update(full_meaning_and_boundaries_confirmed=False),
        lambda r:r.update(candidate_sha256="0"*64),
    ):
        r=completed(candidate)
        change(r)
        with pytest.raises(bridge.QuoteBridgeError):
            review.proposal(candidate,bridge.digest(candidate),r)
    with pytest.raises(bridge.QuoteBridgeError):
        review.proposal(candidate,"0"*64,completed(candidate))


def test_unsafe_metadata_not_rendered():
    candidate,=prepare(*fixture())
    for value in ("Bad|parameter=1","{{Template}}","[[Link]]","''Wiki markup''","<ref>Unsafe</ref>","multi\\nline"):
        r=completed(candidate)
        r["edition"]["work"]=value.replace("\\n","\n")
        with pytest.raises(bridge.QuoteBridgeError):
            review.proposal(candidate,bridge.digest(candidate),r)


def test_private_artifacts_are_immutable_and_idempotent(tmp_path):
    candidate,=prepare(*fixture())
    path=review.write_private(tmp_path,candidate,"candidate")
    assert path.stat().st_mode & 0o077 == 0
    assert json.loads(path.read_text())==candidate
    assert review.write_private(tmp_path,candidate,"candidate")==path
    template=review.write_private(tmp_path,review.blank(candidate),"review-template")
    assert template!=path
    path.write_text("{}\n")
    with pytest.raises(bridge.QuoteBridgeError,match="artifact_changed"):
        review.write_private(tmp_path,candidate,"candidate")


def test_syntax_that_would_change_rendering_is_not_silently_rewritten():
    candidate,=prepare(*fixture())
    for value in ("A &amp; B","[https://example.org/ label]","{{x}}","A|B"):
        r=completed(candidate)
        r["edition"]["work"]=value
        with pytest.raises(bridge.QuoteBridgeError):
            review.proposal(candidate,bridge.digest(candidate),r)
