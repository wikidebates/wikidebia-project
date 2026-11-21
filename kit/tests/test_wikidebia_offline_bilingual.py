from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import wikidebia_offline_bilingual as offline
from wikidebia_corpus_build import full_tree_sha256, sha256_file
from wikidebia_editorial_workspace import workspace_receipt_hash
from wikidebia_update import sha_object, sha_text


DEBATE = "debat_test"
WORK = "EDIT-TEST-001"


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _signed(data: dict, field: str) -> dict:
    data[field] = sha_object(data)
    return data


def _fixture(root: Path) -> tuple[Path, Path, dict]:
    workspace = root / ".state/editorial-workspaces" / DEBATE / WORK
    release = workspace / "release-copy"
    release.mkdir(parents=True)
    fr_text = "{{Débat|interlangue={{Lien interlangue|langue=en|page=Should we agree?}}}}"
    fr_source = release / "output/fr/debate.wiki"
    fr_source.parent.mkdir(parents=True)
    fr_source.write_text(fr_text, encoding="utf-8")
    manifest = {
        "debate_id": DEBATE,
        "pages": [
            {"language": "en", "page_id": "debate", "page_type": "debate",
             "canonical_title": "Should we agree?"},
            {"language": "fr", "page_id": "debate", "page_type": "debate",
             "canonical_title": "Faut-il être d'accord ?", "file_path": "output/fr/debate.wiki"},
        ],
    }
    _write(release / "manifest.json", manifest)
    msha = sha256_file(release / "manifest.json")
    tree = full_tree_sha256(release)
    metadata = {
        "schema": "wikidebia-editorial-workspace-1.0",
        "schema_version": "1.0", "debate_id": DEBATE, "work_id": WORK,
        "status": "release_ready", "release_copy": {"tree_sha256": tree},
    }
    metadata["workspace_sha256"] = workspace_receipt_hash(metadata)
    _write(workspace / "workspace.json", metadata)
    _write(root / ".state/workflows" / DEBATE / "workflow.json", {
        "schema": "wikidebia-editorial-orchestration-1.0",
        "debate_id": DEBATE, "work_id": WORK, "phase": "final_publication",
    })
    root_active = root / "corpus" / DEBATE
    root_active.mkdir(parents=True)
    (root_active / "previous.wiki").write_text("Source FR historique", encoding="utf-8")

    en_sha = "a" * 64
    fr_sha = sha_text(fr_text)
    en_plan = _signed({
        "schema": "wikidebia-publication-plan-1.0", "schema_version": "1.0",
        "debate_id": DEBATE, "blockers": [],
        "package_fingerprints": {"manifest_sha256": msha},
        "actions": [{"language": "en", "page_id": "debate", "page_type": "debate",
                     "title": "Should we agree?", "operation": "create",
                     "desired_sha256": en_sha, "edit_summary":
                     "Translation of the French page: [[:fr:Faut-il être d'accord ?|Faut-il être d'accord ?]]"}],
    }, "plan_sha256")
    fr_op = {
        "language": "fr", "page_id": "debate", "page_type": "debate",
        "title": "Faut-il être d'accord ?", "operation": "update",
        "new_sha256": fr_sha, "edit_summary_policy": "french_interlanguage_addition",
    }
    fr_plan = _signed({
        "plan_version": "wikidebia-remote-update-plan-1.0",
        "debate_id": DEBATE, "new_manifest_sha256": msha,
        "operations": {"update": [fr_op], "skip": [], "create": [],
                       "move": [], "redirect": [], "delete": [],
                       "blocked": [], "manual_review": []},
    }, "plan_sha256")
    en_page = {"page_type": "debate", "page_id": "debate", "canonical_title": "Should we agree?",
               "revision_id": 18, "content_sha256": en_sha, "status": "published"}
    fr_page = {"page_type": "debate", "page_id": "debate",
               "canonical_title": "Faut-il être d'accord ?", "revision_id": 21,
               "content_sha256": fr_sha, "status": "published"}
    en_receipt = _signed({
        "receipt_version": "wikidebia-publication-state-receipt-1.0",
        "debate_id": DEBATE, "language": "en", "plan_sha256": en_plan["plan_sha256"],
        "pages": [en_page],
    }, "receipt_sha256")
    fr_receipt = _signed({
        "receipt_version": "wikidebia-remote-update-receipt-1.0",
        "debate_id": DEBATE, "plan_sha256": fr_plan["plan_sha256"],
        "execution_mode": "full_update", "status": "executed",
        "results": [{"operation": "update", "language": "fr", "page_id": "debate",
                     "title": "Faut-il être d'accord ?", "status": "updated",
                     "revision_id": 21, "content_sha256": fr_sha}],
    }, "receipt_sha256")
    proofdir = root / ".state" / "evidence" / DEBATE / WORK
    paths = {
        "english_plan": proofdir / "english-plan.json",
        "french_plan": proofdir / "french-plan.json",
        "english_receipt": proofdir / "english-receipt.json",
        "french_receipt": proofdir / "french-receipt.json",
    }
    for name, value in zip(paths, (en_plan, fr_plan, en_receipt, fr_receipt)):
        _write(paths[name], value)
    selector = proofdir / "selector.json"
    _write(selector, {
        "schema": offline.SCHEMA, "debate_id": DEBATE, "work_id": WORK,
        **{name: path.relative_to(root).as_posix() for name, path in paths.items()},
    })
    for lang, plan, receipt, page in (
        ("en", en_plan, en_receipt, en_page), ("fr", fr_plan, fr_receipt, fr_page),
    ):
        _write(root / ".state/published" / DEBATE / lang / "latest.json",
               _signed({
                   "state_version": "wikidebia-published-state-1.0",
                   "debate_id": DEBATE, "language": lang, "plan_sha256": plan["plan_sha256"],
                   "receipt_sha256": receipt["receipt_sha256"], "source_manifest_sha256": msha,
                   "pages": [page],
               }, "state_sha256"))
    return selector, workspace, {"manifest": manifest, "metadata": metadata, "paths": paths}


def test_offline_close_is_idempotent_and_preserves_backup(tmp_path: Path):
    selector, workspace, _ = _fixture(tmp_path)
    first = offline.reconcile_offline_bilingual(tmp_path, DEBATE, WORK, selector)
    assert first["status"] == "published"
    assert first["reconciliation"] == "completed"
    assert first["remote_access_performed"] is False
    assert first["remote_write_performed"] is False
    assert first["page_counts"] == {"fr": 1, "en": 1}
    previous = tmp_path / first["previous_corpus_backup"]
    assert (previous / "previous.wiki").read_text(encoding="utf-8") == "Source FR historique"
    assert not (tmp_path / "corpus" / DEBATE / "previous.wiki").exists()
    again = offline.reconcile_offline_bilingual(tmp_path, DEBATE, WORK, selector)
    assert again["reconciliation"] == "reused"
    assert first["receipt_sha256"] == again["receipt_sha256"]
    assert (previous / "previous.wiki").is_file()
    assert json.loads((workspace / "workspace.json").read_text())["status"] == "published"


@pytest.mark.parametrize("damage", ["unsigned_receipt", "missing_result", "wrong_revision",
                                   "wrong_summary_policy", "wrong_page_id", "wrong_manifest"])
def test_evidence_must_match_exact_pages_and_plans(tmp_path: Path, damage: str):
    selector, workspace, fixture = _fixture(tmp_path)
    path = fixture["paths"]["french_receipt"]
    value = json.loads(path.read_text(encoding="utf-8"))
    if damage == "unsigned_receipt":
        value["status"] = "falsified"
    elif damage == "missing_result":
        value["results"] = []
    elif damage == "wrong_revision":
        value["results"][0]["revision_id"] = 9000
    elif damage == "wrong_summary_policy":
        path = fixture["paths"]["french_plan"]
        value = json.loads(path.read_text(encoding="utf-8"))
        value["operations"]["update"][0]["edit_summary_policy"] = "content_diff_v1"
    elif damage == "wrong_page_id":
        path = fixture["paths"]["english_plan"]
        value = json.loads(path.read_text(encoding="utf-8"))
        value["actions"][0]["page_id"] = "other"
    elif damage == "wrong_manifest":
        path = workspace / "release-copy" / "manifest.json"
        value = fixture["manifest"] | {"debate_id": "other"}
    if damage not in {"unsigned_receipt", "wrong_manifest"}:
        value.pop("plan_sha256" if path.name.endswith("plan.json") else "receipt_sha256")
        value["plan_sha256" if path.name.endswith("plan.json") else "receipt_sha256"] = sha_object(value)
    _write(path, value)
    with pytest.raises(offline.PostPublicationError):
        offline.reconcile_offline_bilingual(tmp_path, DEBATE, WORK, selector)
    assert (tmp_path / "corpus" / DEBATE / "previous.wiki").is_file()
    assert json.loads((workspace / "workspace.json").read_text())["status"] == "release_ready"


def test_resume_after_local_receipt_written_but_workspace_not_changed(tmp_path: Path, monkeypatch):
    selector, workspace, _ = _fixture(tmp_path)
    original = offline.write_json
    workspace_path = workspace / "workspace.json"
    def fail_once(path, data):
        if path == workspace_path:
            raise OSError("simulated interruption after sealed receipt")
        return original(path, data)
    monkeypatch.setattr(offline, "write_json", fail_once)
    with pytest.raises(OSError, match="simulated interruption"):
        offline.reconcile_offline_bilingual(tmp_path, DEBATE, WORK, selector)
    monkeypatch.setattr(offline, "write_json", original)
    result = offline.reconcile_offline_bilingual(tmp_path, DEBATE, WORK, selector)
    assert result["reconciliation"] == "resumed"
    assert json.loads(workspace_path.read_text())["status"] == "published"


def test_active_corpus_tampering_blocks_resume(tmp_path: Path):
    selector, _workspace, _ = _fixture(tmp_path)
    result = offline.reconcile_offline_bilingual(tmp_path, DEBATE, WORK, selector)
    (tmp_path / "corpus" / DEBATE / "intrusion.txt").write_text("modified", encoding="utf-8")
    with pytest.raises(offline.PostPublicationError):
        offline.reconcile_offline_bilingual(tmp_path, DEBATE, WORK, selector)
    assert (tmp_path / result["previous_corpus_backup"] / "previous.wiki").is_file()

def test_french_release_content_must_be_byte_identical_to_attested_publication(tmp_path: Path):
    selector, workspace, fixture = _fixture(tmp_path)
    source = workspace / "release-copy/output/fr/debate.wiki"
    source.write_text("FR content drifted", encoding="utf-8")
    data = json.loads((workspace / "workspace.json").read_text(encoding="utf-8"))
    data["release_copy"]["tree_sha256"] = full_tree_sha256(workspace / "release-copy")
    data["workspace_sha256"] = workspace_receipt_hash(data)
    _write(workspace / "workspace.json", data)
    # A re-sealed local tree does not authorize changing a signed remote plan.
    with pytest.raises(offline.PostPublicationError):
        offline.reconcile_offline_bilingual(tmp_path, DEBATE, WORK, selector)
    assert (tmp_path / "corpus" / DEBATE / "previous.wiki").is_file()
