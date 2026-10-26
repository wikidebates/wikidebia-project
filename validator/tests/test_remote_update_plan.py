from __future__ import annotations
import json
from pathlib import Path
from wikidebia_validator.remote_plan import sha_object, validate_remote_plan


def valid_plan():
    plan = {
        "plan_version":"wikidebia-remote-update-plan-1.0","kit_version":"2.2.4","required_validator_version":"0.4.20",
        "debate_id":"demo","corpus_version":"v1","languages":["fr"],"scope_mode":"all","edit_summary_contract":"page_specific_v1",
        "state_source":{"kind":"published_state_receipt"},"new_manifest_sha256":"0"*64,"validator_report_sha256":"1"*64,
        "config_sha256":"2"*64,"operations":{name:[] for name in ("create","update","move","redirect","delete","skip","manual_review","blocked")},
        "comparisons":[],"counts":{name:0 for name in ("create","update","move","redirect","delete","skip","manual_review","blocked")},
        "preconditions":["new_corpus_validated"]
    }
    plan["plan_sha256"] = sha_object(plan)
    return plan


def test_valid_remote_update_plan(tmp_path: Path):
    path=tmp_path/'plan.json'; path.write_text(json.dumps(valid_plan()),encoding='utf-8')
    assert validate_remote_plan(path).errors == 0


def test_first_english_publication_accepts_workflow_release_baseline(tmp_path: Path):
    plan = valid_plan()
    plan["state_source"] = {
        "kind": "workflow_release_baseline",
        "work_id": "EDIT-20261026-001",
        "baseline_sha256": "3" * 64,
        "empty_baseline": True,
    }
    plan["plan_sha256"] = sha_object({k: v for k, v in plan.items() if k != "plan_sha256"})
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    assert validate_remote_plan(path).errors == 0


def test_plan_hash_tampering_is_blocked(tmp_path: Path):
    plan=valid_plan(); plan['debate_id']='other'
    path=tmp_path/'plan.json'; path.write_text(json.dumps(plan),encoding='utf-8')
    assert any(f.code=='WDV-RMT-001' for f in validate_remote_plan(path).findings)


def test_unsafe_delete_is_blocked(tmp_path: Path):
    plan=valid_plan()
    op={"wiki":"fr","language":"fr","title":"A","page_id":"A1","page_type":"argument","old_sha256":"3"*64,"new_sha256":None,"expected_revision_id":1,"observed_revision_id":1,"justification":"retired","preconditions":[],"result":None,"phase":7}
    plan['operations']['delete']=[op]; plan['counts']['delete']=1; plan['plan_sha256']=sha_object({k:v for k,v in plan.items() if k!='plan_sha256'})
    path=tmp_path/'plan.json'; path.write_text(json.dumps(plan),encoding='utf-8')
    assert any(f.code=='WDV-RMT-004' for f in validate_remote_plan(path).findings)


def test_page_specific_contract_blocks_generic_or_missing_mutation_summary(tmp_path: Path):
    plan = valid_plan()
    op = {
        "wiki":"fr","language":"fr","title":"A","page_id":"A1","page_type":"argument",
        "old_sha256":"3"*64,"new_sha256":"4"*64,"expected_revision_id":1,"observed_revision_id":1,
        "justification":"update","preconditions":["baserevid_unchanged"],"result":None,"phase":3,
    }
    plan["operations"]["update"] = [op]
    plan["counts"]["update"] = 1
    plan["plan_sha256"] = sha_object({k:v for k,v in plan.items() if k!="plan_sha256"})
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    assert any(f.code == "WDV-RMT-008" for f in validate_remote_plan(path).findings)

    op["edit_summary_policy"] = "content_diff_v1"
    op["edit_summary"] = "Corrections"
    plan["plan_sha256"] = sha_object({k:v for k,v in plan.items() if k!="plan_sha256"})
    path.write_text(json.dumps(plan), encoding="utf-8")
    assert any(f.code == "WDV-RMT-008" for f in validate_remote_plan(path).findings)


def test_page_specific_contract_accepts_signed_individual_summary(tmp_path: Path):
    plan = valid_plan()
    op = {
        "wiki":"fr","language":"fr","title":"A","page_id":"A1","page_type":"argument",
        "old_sha256":"3"*64,"new_sha256":"4"*64,"expected_revision_id":1,"observed_revision_id":1,
        "justification":"update","preconditions":["baserevid_unchanged"],"result":None,"phase":3,
        "edit_summary_policy":"content_diff_v1","edit_summary":"Mise à jour du résumé et des références",
    }
    plan["operations"]["update"] = [op]
    plan["counts"]["update"] = 1
    plan["plan_sha256"] = sha_object({k:v for k,v in plan.items() if k!="plan_sha256"})
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    assert not any(f.code == "WDV-RMT-008" for f in validate_remote_plan(path).findings)


def test_legacy_plan_without_individualized_contract_remains_readable(tmp_path: Path):
    plan = valid_plan()
    plan.pop("edit_summary_contract")
    plan["plan_sha256"] = sha_object({k:v for k,v in plan.items() if k!="plan_sha256"})
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    assert validate_remote_plan(path).errors == 0
