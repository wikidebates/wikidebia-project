from __future__ import annotations

import json
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import wikidebia_content_review as content
import wikidebia_french_checkpoint as checkpoint
import wikidebia_review_workflow as workflow
import wikidebia_corpus_build as common
from test_wikidebia_content_review import make_metadata_applied, complete_content_review


def _rewrite_review_zip(source: Path, target: Path, *, note: str) -> None:
    temp = target.parent / (target.stem + "-unzipped")
    shutil.rmtree(temp, ignore_errors=True)
    temp.mkdir(parents=True)
    with zipfile.ZipFile(source) as archive:
        archive.extractall(temp)
    review_path = temp / "editable/reviews/fr/content_review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["global_review"]["note"] = note
    common.write_json(review_path, review)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(x for x in temp.rglob("*") if x.is_file()):
            archive.write(path, path.relative_to(temp).as_posix())
    shutil.rmtree(temp)


def _prepare_vote_like_review(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    content.prepare_review(project, "debat_test", work_id)
    complete_content_review(workspace)
    state = {
        "schema": workflow.WORKFLOW_SCHEMA,
        "schema_version": "1.0",
        "normative_revision": workflow.NORM_VERSION,
        "validator_version": workflow.VALIDATOR_VERSION,
        "kit_version": workflow.KIT_VERSION,
        "debate_id": "debat_test",
        "debate_title": "Le vote électronique doit-il être généralisé ?",
        "short_code": "VOTE",
        "phase": "fr_content_review",
        "status": "running",
        "work_id": work_id,
        "pending_review": None,
        "french_graph_publication": {"stage": "graph", "status": "published", "receipt_sha256": "g" * 64},
        "created_at": "2026-08-13T00:30:00+02:00",
        "updated_at": "2026-08-13T00:30:00+02:00",
    }
    workflow._save_workflow(project, state)
    graph_stage = project / ".state/fr-publication/debat_test" / work_id / "graph"
    (graph_stage / "checkpoint-corpus").mkdir(parents=True, exist_ok=True)
    (graph_stage / "checkpoint-corpus/marker.txt").write_text("published graph checkpoint", encoding="utf-8")
    common.write_json(graph_stage / "checkpoint.json", {"stage": "graph", "source_tree_sha256": "g"})
    common.write_json(graph_stage / "publication-receipt.json", {"stage": "graph", "status": "published"})
    pending = workflow.create_review_package(
        project,
        state,
        review_type="fr_content_review",
        base=workspace,
        editable_paths=[
            "reviews/fr/content_review.json",
            "data/sources_working.json",
            "reviews/fr/classification_review.json",
            "data/keyword_vocabulary_working.json",
        ],
        context_paths=["reviewed-copy/data/fr_page_metadata_lock.json"],
    )
    return project, workspace, work_id, pending


def test_vote_electronique_v6_local_validation_failure_then_v7_rebuilds_checkpoint_and_stops_for_normalization(tmp_path: Path, monkeypatch):
    project, workspace, work_id, pending = _prepare_vote_like_review(tmp_path)
    source_package = project / pending["package_path"]
    v6 = tmp_path / "vote-v6.zip"
    v7 = tmp_path / "vote-v7.zip"
    _rewrite_review_zip(source_package, v6, note="v6 documentaire : cette tentative doit échouer avant écriture distante.")
    _rewrite_review_zip(source_package, v7, note="v7 documentaire corrigée : cette tentative doit poursuivre le workflow.")

    source_shas: list[str] = []
    calls = {"count": 0}

    def publish_with_first_preflight_failure(project_root, debate_id, current_work_id, *, stage):
        assert stage == "content"
        cp = checkpoint.build_checkpoint(project_root, debate_id, current_work_id, stage=stage)
        receipt = json.loads((cp.parent / "checkpoint.json").read_text(encoding="utf-8"))
        source_shas.append(receipt["source_tree_sha256"])
        common.write_json(cp.parent / "remote-update-config.json", {"stage": "content", "attempt": calls["count"] + 1})
        calls["count"] += 1
        if calls["count"] == 1:
            # Equivalent to RemoteUpdatePlanner.build_plan() invoking the validator
            # and failing before update-plan.json exists and before PlanExecutor.
            raise RuntimeError("v6 validation documentaire refusée avant écriture distante")
        return {
            "schema": checkpoint.RECEIPT_SCHEMA,
            "schema_version": "1.0",
            "debate_id": debate_id,
            "work_id": current_work_id,
            "stage": "content",
            "status": "published",
            "receipt_sha256": "c" * 64,
            "checkpoint_tree_sha256": common.full_tree_sha256(cp),
        }

    monkeypatch.setattr(workflow, "publish_checkpoint", publish_with_first_preflight_failure)

    with pytest.raises(RuntimeError, match="v6 validation documentaire refusée"):
        workflow.import_review(project, "debat_test", v6)
    content_stage = project / ".state/fr-publication/debat_test" / work_id / "content"
    assert not content_stage.exists()
    assert (project / ".state/fr-publication/debat_test" / work_id / "graph/publication-receipt.json").is_file()

    result = workflow.import_review(project, "debat_test", v7)
    assert len(source_shas) == 2
    assert source_shas[0] != source_shas[1]
    assert result["phase"] == "en_translation_review"
    assert result["status"] == "french_normalization_required"
    assert result["pending_review"] is None
    assert not (workspace / "reviews/en/translation_review.json").exists()
    assert (content_stage / "checkpoint.json").is_file()
    assert (content_stage / "remote-update-config.json").is_file()
