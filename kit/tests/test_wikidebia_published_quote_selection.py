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


def test_mixed_origin_work_from_import_to_canonical_render_fixture(tmp_path,monkeypatch):
    """Use an actual kit Work, not just hand-assembled lock rows.

    All documentary/semantic attestations and wiki contents are synthetic.
    No network access, real rights decision or publication is performed.
    """
    from datetime import datetime,timedelta,timezone
    import hashlib
    import test_wikidebia_editorial_workspace as workspace_fixture
    from test_wikidebia_translation_review import (
        make_french_locked,mark_existing_english_argument,complete_translation_review,
        complete_semantic_convergence,translation,common)
    from test_wikidebia_render import render,approve_fixture_placements
    from test_wikidebia_quote_index_contract import snapshot
    import wikidebia_quote_index_contract as index
    from wikidebia_quote_index_stage import stage

    # Introduce a synthetic MIA link before extraction/import and recalculate
    # the actual fixture's manifests. Never modify an already locked Work.
    original_extraction=workspace_fixture.make_extraction
    def extraction(root):
        source=original_extraction(root)
        path=source/"snapshot/pages/arguments/b.wiki"
        text=path.read_text(encoding="utf-8")
        assert text.count("|date=juin 2012}}")==1
        path.write_text(text.replace("|date=juin 2012}}",
            "|date=juin 2012|lien=https://www.marxists.org/francais/test/a.htm}}"),encoding="utf-8")
        def update(row,path):
            raw=path.read_bytes()
            row.update(sha256=hashlib.sha256(raw).hexdigest(),size_bytes=len(raw))
        snap=source/"snapshot/snapshot_manifest.json"
        data=common.load_json(snap)
        for row in data["arguments"]:
            if row["relative_path"]=="pages/arguments/b.wiki":
                update(row,path)
        common.write_json(snap,data)
        package=source/"test_manifest_sha256_2026-08-03.json"
        manifest=common.load_json(package)
        for row in manifest["files"]:
            if row["path"] in {"snapshot/pages/arguments/b.wiki","snapshot/snapshot_manifest.json"}:
                update(row,source/row["path"])
        common.write_json(package,manifest)
        return source
    monkeypatch.setattr(workspace_fixture,"make_extraction",extraction)
    project,workspace,work_id=make_french_locked(tmp_path)
    # The general fixture deliberately duplicates C and D. D is a distinct
    # already reused page in this test; it must not be sent for translation.
    mark_existing_english_argument(workspace)
    fr=workspace/"content-reviewed-copy"
    before=common.full_tree_sha256(fr)
    translation.prepare_review(project,"debat_test",work_id)
    _,lock_sha,items,owners=bridge.snapshot(project,"debat_test",work_id)
    assert "A0004" not in set(owners.values())
    src,= [item for item in items if owners[item["id"]]=="A0002"]
    src,row=fixture(source_item=src)
    req={"schema":bridge.REQUEST,"source_lock_sha256":lock_sha,"items":[src]}
    from test_wikidebia_quote_bridge import envelope
    handoff=envelope(req,[row])
    candidate,=review.prepare(req,handoff,bridge.digest(handoff),lock_sha,items,owners)
    evidence=review.make_evidence(candidate,bridge.digest(candidate),completed(candidate))
    evidence_path=review.write_private(workspace,evidence,"evidence")
    def stage_at(rows,minutes):
        value=snapshot(rows)
        now=datetime.now(timezone.utc)
        value.update(started_utc=(now-timedelta(minutes=minutes+1)).isoformat(),
                     finished_utc=(now-timedelta(minutes=minutes)).isoformat())
        path=tmp_path/"index.json"
        path.write_text(json.dumps(value),encoding="utf-8")
        sha=index.digest(value)
        stage(workspace,path,sha)
        return sha
    # The global gate must check the AI route as well as the published route.
    bad_sha=stage_at([(1,"External page",201,"Freedom consists in wanting what one wants.")],5)
    picked=selection.select_workspace(project,"debat_test",work_id,[evidence_path],bad_sha)
    assert picked["selected"]==[src["id"]]
    draft_path=workspace/"reviews/en/translation_review.json"
    draft=common.load_json(draft_path)
    draft_row=next(a["translation"]["citations"][0] for a in draft["arguments"] if a["id"]=="A0002")
    assert draft_row["status"]=="pending"
    assert draft_row["translated_citation"]==candidate["plain_quote"]
    # The standard helper supplies the rest of the synthetic review; its
    # legacy-only quote entries are replaced by the explicit published choice.
    complete_translation_review(workspace)
    draft=common.load_json(draft_path)
    draft_row=next(a["translation"]["citations"][0] for a in draft["arguments"] if a["id"]=="A0002")
    draft_row.update(translated_citation=candidate["plain_quote"],translated_date="",
                     preserved_parameters_unchanged=False,translation_warning_appended=False,
                     note="Synthetic published edition and full quotation reviewed.")
    common.write_json(draft_path,draft)
    with pytest.raises(translation.TranslationReviewError,match="Doublons exacts"):
        translation.finalize_review(project,"debat_test",work_id)
    assert common.load_json(draft_path)["status"]=="draft"
    assert not (workspace/"translated-copy").exists()
    good_sha=stage_at([(2,"Existing English argument",42,"An unrelated quotation.")],1)
    picked=selection.select_workspace(project,"debat_test",work_id,[evidence_path],good_sha)
    assert picked["already_selected"]==[src["id"]]
    sealed=translation.finalize_review(project,"debat_test",work_id)
    final_review=common.load_json(draft_path)
    assert final_review["quote_duplicate_audit"]["published_occurrences"]==1
    assert final_review["quote_duplicate_audit"]["ai_occurrences"]==2
    complete_semantic_convergence(project,work_id)
    translation.apply_review(project,"debat_test",work_id,sealed["review_sha256"])
    target=workspace/"translated-copy"
    frozen=common.load_json(target/"data/en_content_lock.json")
    assert frozen["quote_duplicate_audit"]["index_sha256"]==good_sha
    quotes={a["id"]:a["citations"][0] for a in frozen["arguments"]}
    assert quotes["A0002"]["translation_origin"]=="published_translation"
    assert quotes["A0002"]["parameters"]==evidence["proposal"]["parameters"]
    assert "AI-translated quote" in quotes["A0001"]["warnings"]
    assert "A0004" not in quotes
    assert common.full_tree_sha256(fr)==before
    assert (target/index.INDEX_PATH).is_file()
    norm=project/"norms/normative_reference/01_normes/WIKIDEBIA_NORME_CONSOLIDEE_1.2.70.md"
    norm.parent.mkdir(parents=True,exist_ok=True)
    norm.write_text("# Synthetic test norm\n",encoding="utf-8")
    approve_fixture_placements(workspace)
    translated_before=common.full_tree_sha256(target)
    # Production must remain blocked until coordinated activation.
    assert contract.ACTIVE is False
    with pytest.raises(render.RenderError,match="non activé"):
        render.render_workspace(project,"debat_test",work_id,sealed["review_sha256"])
    assert not (workspace/"rendered-copy").exists()
    # Test hypothetical activation only in this process. The fixture uses the
    # existing fake generic validator; dedicated independent validator tests
    # still verify the published quote and index contracts separately.
    monkeypatch.setattr(contract,"ACTIVE",True)
    rendered=render.render_workspace(project,"debat_test",work_id,sealed["review_sha256"])
    assert rendered["status"]=="bilingual_rendered"
    output=workspace/"rendered-copy/output/en/arguments"
    assert "|quote="+candidate["plain_quote"] in (output/"A0002.wiki").read_text(encoding="utf-8")
    assert "AI-translated quote" not in (output/"A0002.wiki").read_text(encoding="utf-8")
    assert "AI-translated quote" in (output/"A0001.wiki").read_text(encoding="utf-8")
    assert not (output/"A0004.wiki").exists()
    assert common.full_tree_sha256(target)==translated_before
    assert common.full_tree_sha256(fr)==before
