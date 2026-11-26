from __future__ import annotations

import json
from pathlib import Path

import wikidebia_workspace_status as status


def _meta(workspace_status: str, **extra):
    return {
        "status": workspace_status,
        "workspace_sha256": "w" * 64,
        "translated_copy": {"review_sha256": "t" * 64},
        "rendered_copy": {"tree_sha256": "r" * 64},
        "release_copy": {"tree_sha256": "l" * 64},
        **extra,
    }


def test_summary_verifies_remote_comparison_and_returns_exact_command(tmp_path: Path, monkeypatch):
    meta = _meta(
        "remote_plan_ready",
        remote_comparison={"comparison_id": "REMOTE-20261104-003"},
        remote_comparisons=[{"comparison_id": "REMOTE-20261104-003"}],
        remote_history=[{"large": "x" * 10000}],
    )
    monkeypatch.setattr(status, "_load_workspace", lambda *args: (tmp_path, meta))
    monkeypatch.setattr(
        status,
        "_load_comparison",
        lambda *args: {
            "plan": {
                "plan_sha256": "p" * 64,
                "operations": {
                    "create": [{}], "update": [], "move": [], "redirect": [],
                    "delete": [], "skip": [{}] * 697, "manual_review": [], "blocked": [],
                },
            },
            "receipt": {
                "status": "plan_ready",
                "scope": "all",
                "counts": {"skip": 697, "create": 1},
                "plan_sha256": "p" * 64,
                "receipt_sha256": "c" * 64,
            }
        },
    )

    result = status.summarize_workspace(tmp_path, "debat_test", "EDIT-TEST-001")

    assert result["next_command"] == (
        "./wikidebia corpus-workspace-plan-review debat_test --work-id EDIT-TEST-001 "
        "--comparison-id REMOTE-20261104-003 --prepare"
    )
    assert result["next_remote_read_possible"] is False
    assert result["next_remote_write_possible"] is False
    assert result["status_check_remote_access"] is False
    assert result["remote"]["counts"] == {"skip": 697, "create": 1}
    assert "remote_history" not in result
    assert len(json.dumps(result)) < 2500


def test_summary_shortcuts_signed_all_skip_plan_to_local_closure(tmp_path: Path, monkeypatch):
    meta = _meta(
        "remote_plan_ready",
        remote_comparison={"comparison_id": "REMOTE-20261104-003"},
        remote_comparisons=[{"comparison_id": "REMOTE-20261104-003"}],
    )
    operations = {
        "create": [], "update": [], "move": [], "redirect": [], "delete": [],
        "skip": [{"page_id": "A0001"}], "manual_review": [], "blocked": [],
    }
    monkeypatch.setattr(status, "_load_workspace", lambda *args: (tmp_path, meta))
    monkeypatch.setattr(
        status,
        "_load_comparison",
        lambda *args: {
            "plan": {"plan_sha256": "p" * 64, "operations": operations},
            "receipt": {
                "status": "plan_ready", "scope": "all", "counts": {"skip": 1},
                "plan_sha256": "p" * 64, "receipt_sha256": "c" * 64,
            },
        },
    )

    result = status.summarize_workspace(tmp_path, "debat_test", "EDIT-TEST-001")

    assert result["next_action"] == "close_workspace_from_signed_no_change_plan"
    assert result["next_command"].endswith("--confirm-no-change-plan-sha256 " + "p" * 64)
    assert result["next_remote_read_possible"] is False
    assert result["next_remote_write_possible"] is False
    assert "locale" in result["note"]


def test_status_maps_signed_acceptance_to_preflight_command():
    meta = _meta(
        "remote_plan_approved",
        remote_comparison={"comparison_id": "REMOTE-20261104-003"},
        remote_plan_review={
            "comparison_id": "REMOTE-20261104-003",
            "acceptance_sha256": "a" * 64,
        },
    )

    result = status._next_step(meta, "debat_test", "EDIT-TEST-001")

    assert result["command"].endswith("--confirm-acceptance-sha256 " + "a" * 64)
    assert result["remote_read_possible"] is True
    assert result["remote_write_possible"] is False


def test_status_marks_execution_as_the_only_remote_write_step():
    meta = _meta(
        "remote_execution_ready",
        remote_comparison={"comparison_id": "REMOTE-20261104-003"},
        remote_execution={
            "comparison_id": "REMOTE-20261104-003",
            "mode": "no-delete",
            "preflight_sha256": "f" * 64,
        },
    )

    result = status._next_step(meta, "debat_test", "EDIT-TEST-001")

    assert "--execute --mode no-delete" in result["command"]
    assert result["command"].endswith("--confirm-preflight-sha256 " + "f" * 64)
    assert result["remote_read_possible"] is True
    assert result["remote_write_possible"] is True


def test_status_maps_completed_execution_to_exact_closure_command():
    meta = _meta(
        "remote_execution_completed",
        remote_comparison={"comparison_id": "REMOTE-20261104-003"},
        remote_execution={
            "comparison_id": "REMOTE-20261104-003",
            "receipt_sha256": "e" * 64,
            "mode": "all",
        },
    )

    result = status._next_step(meta, "debat_test", "EDIT-TEST-001")

    assert result["action"] == "close_workspace"
    assert result["command"].endswith("--confirm-execution-sha256 " + "e" * 64)
    assert result["remote_write_possible"] is False


def test_status_routes_local_finalization_without_copying_hashes():
    result = status._next_step(
        _meta("en_translation_applied"), "debat_test", "EDIT-TEST-001"
    )

    assert result["command"] == (
        "./wikidebia corpus-workspace-finalize debat_test --work-id EDIT-TEST-001"
    )
    assert "sha256" not in result["command"]
    assert result["remote_write_possible"] is False


def test_status_does_not_invent_semantic_review_inputs():
    result = status._next_step(
        _meta("en_translation_review_finalized"), "debat_test", "EDIT-TEST-001"
    )

    assert result["action"] == "record_two_semantic_convergence_passes"
    assert result["command"] is None
    assert "humaines" in result["note"]


def test_published_workspace_is_terminal():
    result = status._next_step(
        _meta("published"), "debat_test", "EDIT-TEST-001"
    )

    assert result["action"] == "complete"
    assert result["command"] is None
    assert status._phase("published") == "complete"

def test_preserved_release_uses_publish_preserved_without_remote_status_read(tmp_path, monkeypatch):
    from wikidebia_workflow_baseline import PRESERVED_IMPORT_POLICY
    monkeypatch.setattr(status, '_load_workspace', lambda *args: (tmp_path, _meta(
        'release_ready', source_preservation={'policy': PRESERVED_IMPORT_POLICY},
    )))
    import wikidebia_global_resume as resume
    monkeypatch.setattr(resume, '_published_receipt', lambda *args: None)
    result = status.summarize_workspace(tmp_path, 'debat_test', 'EDIT-TEST-001')
    assert result['next_command'] == './wikidebia publish-preserved debat_test --work-id EDIT-TEST-001'
    assert result['next_action'] == 'publish_preserved_release'
    assert result['next_remote_write_possible'] is False
    assert result['status_check_remote_access'] is False
    assert result['status_check_remote_write'] is False


def test_preserved_published_receipt_requires_local_reconciliation(tmp_path, monkeypatch):
    from wikidebia_workflow_baseline import PRESERVED_IMPORT_POLICY
    monkeypatch.setattr(status, '_load_workspace', lambda *args: (tmp_path, _meta(
        'release_ready', source_preservation={'policy': PRESERVED_IMPORT_POLICY},
    )))
    import wikidebia_global_resume as resume
    monkeypatch.setattr(resume, '_published_receipt', lambda *args: ({'status': 'published'}, tmp_path / 'receipt.json'))
    result = status.summarize_workspace(tmp_path, 'debat_test', 'EDIT-TEST-001')
    assert result['next_command'] == './wikidebia corpus-workspace-reconcile-publication debat_test --work-id EDIT-TEST-001'
    assert result['next_remote_write_possible'] is False

def test_preserved_release_without_preparation_points_to_read_only_preflight(tmp_path, monkeypatch):
    from wikidebia_workflow_baseline import PRESERVED_IMPORT_POLICY
    monkeypatch.setattr(status, "_load_workspace", lambda *args: (tmp_path, _meta(
        "release_ready", source_preservation={"policy": PRESERVED_IMPORT_POLICY},
    )))
    import wikidebia_global_resume as resume
    monkeypatch.setattr(resume, "_published_receipt", lambda *args: None)
    result = status.summarize_workspace(tmp_path, "debat_test", "EDIT-TEST-001")
    assert result["next_action"] == "publish_preserved_release"
    assert result["next_command"] == "./wikidebia publish-preserved debat_test --work-id EDIT-TEST-001"
    assert result["next_remote_write_possible"] is False
    assert "préservée" in result["note"]


def test_preserved_resume_tracks_current_signed_preflight_and_completed_writes(tmp_path, monkeypatch):
    from wikidebia_corpus_build import write_json
    from wikidebia_workflow_baseline import PRESERVED_IMPORT_POLICY, sha_object

    debate, work = "debat_test", "EDIT-TEST-001"
    release_sha = "a" * 64
    monkeypatch.setattr(status, "_load_workspace", lambda *args: (tmp_path, _meta(
        "release_ready", source_preservation={"policy": PRESERVED_IMPORT_POLICY},
        release_copy={"tree_sha256": release_sha},
    )))
    state = tmp_path / ".state/final-publication" / debate / work

    def save(name, field, body):
        value = {**body, field: sha_object(body)}
        write_json(state / name, value)
        return value[field]

    en_sha, fr_sha, baseline_sha = "b" * 64, "c" * 64, "d" * 64
    preflight = {"status": "ready", "english_plan_sha256": en_sha, "french_plan_sha256": fr_sha}
    first = save("preflight.json", "preflight_sha256", preflight)
    save("publication-preparation.json", "preparation_sha256", {
        "status": "publication_prepared", "debate_id": debate, "work_id": work,
        "baseline_sha256": baseline_sha, "release_copy_tree_sha256": release_sha,
        "preflight_sha256": first, "en_plan_sha256": en_sha, "fr_plan_sha256": fr_sha,
    })
    prepared = status.summarize_workspace(tmp_path, debate, work)
    assert prepared["status"] == "publication_prepared"
    assert prepared["publication_preflight_sha256"] == first
    assert prepared["next_remote_write_possible"] is True

    current = save("preflight.json", "preflight_sha256", {**preflight, "checked_at": "refreshed"})
    save("authorization.json", "authorization_sha256", {
        "status": "authorized", "remote_write_authorized": True,
        "preflight_sha256": current, "baseline_sha256": baseline_sha,
    })
    partial = status.summarize_workspace(tmp_path, debate, work)
    assert partial["status"] == "final_publication_resume"
    assert partial["next_command"].endswith(current)
    assert partial["next_remote_write_possible"] is True

    save("english-publication-receipt.json", "receipt_sha256", {"status": "published", "plan_sha256": en_sha})
    save("french-publication-receipt.json", "receipt_sha256", {"status": "published", "plan_sha256": fr_sha})
    public = status.summarize_workspace(tmp_path, debate, work)
    assert public["status"] == "public_verification_pending"
    assert public["next_command"].endswith(f"{current} --verify-only")
    assert public["next_remote_read_possible"] is True and public["next_remote_write_possible"] is False

    save("french-publication-receipt.json", "receipt_sha256", {"status": "published", "plan_sha256": en_sha})
    invalid = status.summarize_workspace(tmp_path, debate, work)
    assert invalid["next_command"] is None and invalid["status"] == "final_publication_evidence_invalid"


def test_main_cli_exposes_publish_preserved():
    from wikidebia_manage import build_parser
    args = build_parser().parse_args([
        "publish-preserved", "debat_test", "--work-id", "EDIT-TEST-001",
    ])
    assert args.command == "publish-preserved"
    assert args.debate_id == "debat_test"
    assert args.work_id == "EDIT-TEST-001"
