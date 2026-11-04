from __future__ import annotations

import json
from pathlib import Path

import pytest

import wikidebia_workspace_finalize as finalize
from wikidebia_corpus_build import full_tree_sha256


def test_translation_review_is_derived_from_verified_copy(tmp_path: Path):
    translated = tmp_path / "translated-copy"
    (translated / "data").mkdir(parents=True)
    review_sha = "a" * 64
    (translated / "data/en_translation_lock.json").write_text(
        json.dumps({"review_sha256": review_sha}) + "\n", encoding="utf-8"
    )
    meta = {
        "translated_copy": {
            "tree_sha256": full_tree_sha256(translated),
            "review_sha256": review_sha,
        }
    }

    assert finalize._translation_review(tmp_path, meta) == review_sha
    (translated / "changed.txt").write_text("changed\n", encoding="utf-8")
    with pytest.raises(finalize.WorkspaceFinalizeError, match="a changé"):
        finalize._translation_review(tmp_path, meta)


def test_finalize_creates_each_missing_stage_in_order(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    meta = {"status": "en_translation_applied"}
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(finalize, "_load_workspace", lambda *args: (workspace, meta))
    monkeypatch.setattr(finalize, "_translation_review", lambda *args: "review-sha")
    monkeypatch.setattr(finalize, "_reuse_render", lambda *args: None)
    monkeypatch.setattr(finalize, "_reuse_release", lambda *args: None)
    monkeypatch.setattr(finalize, "_reuse_comparison", lambda *args, **kwargs: None)

    def render(*args):
        calls.append(("render", args[-1]))
        return {"rendered_copy_tree_sha256": "render-sha"}

    def release(*args):
        calls.append(("release", args[-1]))
        return {"release_copy_tree_sha256": "release-sha", "archive_sha256": "archive-sha"}

    def compare(*args, **kwargs):
        calls.append(("remote", args[-1]))
        assert kwargs == {"scope": "all", "comparison_id": None}
        return {
            "status": "plan_ready",
            "comparison_id": "REMOTE-20261104-001",
            "plan": ".state/update-plan.json",
            "plan_sha256": "plan-sha",
            "counts": {"skip": 2},
        }

    monkeypatch.setattr(finalize, "render_workspace", render)
    monkeypatch.setattr(finalize, "release_workspace", release)
    monkeypatch.setattr(finalize, "compare_workspace", compare)

    result = finalize.finalize_workspace(tmp_path, "debat_test", "EDIT-TEST-001")

    assert calls == [
        ("render", "review-sha"),
        ("release", "render-sha"),
        ("remote", "release-sha"),
    ]
    assert result["status"] == "plan_ready"
    assert result["remote_write_performed"] is False
    assert {name: row["status"] for name, row in result["steps"].items()} == {
        "render": "created",
        "release": "created",
        "remote_compare": "created",
    }


def test_finalize_reuses_verified_stages_without_remote_read(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    meta = {"status": "remote_plan_ready"}
    monkeypatch.setattr(finalize, "_load_workspace", lambda *args: (workspace, meta))
    monkeypatch.setattr(finalize, "_translation_review", lambda *args: "review-sha")
    monkeypatch.setattr(
        finalize, "_reuse_render", lambda *args: {"status": "reused", "tree_sha256": "render-sha"}
    )
    monkeypatch.setattr(
        finalize, "_reuse_release", lambda *args: {"status": "reused", "tree_sha256": "release-sha"}
    )
    monkeypatch.setattr(
        finalize,
        "_reuse_comparison",
        lambda *args, **kwargs: {
            "status": "reused",
            "comparison_status": "plan_ready",
            "comparison_id": "REMOTE-20261104-001",
            "plan": "plan.json",
            "plan_sha256": "plan-sha",
            "counts": {"skip": 2},
            "remote_write_performed": False,
        },
    )
    monkeypatch.setattr(
        finalize, "render_workspace", lambda *args: pytest.fail("rendu relancé")
    )
    monkeypatch.setattr(
        finalize, "release_workspace", lambda *args: pytest.fail("release relancée")
    )
    monkeypatch.setattr(
        finalize, "compare_workspace", lambda *args, **kwargs: pytest.fail("wiki relu")
    )

    result = finalize.finalize_workspace(tmp_path, "debat_test", "EDIT-TEST-001")

    assert all(row["status"] == "reused" for row in result["steps"].values())


def test_refresh_remote_only_recreates_comparison(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    meta = {"status": "remote_plan_ready"}
    monkeypatch.setattr(finalize, "_load_workspace", lambda *args: (workspace, meta))
    monkeypatch.setattr(finalize, "_translation_review", lambda *args: "review-sha")
    monkeypatch.setattr(
        finalize, "_reuse_render", lambda *args: {"status": "reused", "tree_sha256": "render-sha"}
    )
    monkeypatch.setattr(
        finalize, "_reuse_release", lambda *args: {"status": "reused", "tree_sha256": "release-sha"}
    )
    monkeypatch.setattr(
        finalize, "_reuse_comparison", lambda *args, **kwargs: pytest.fail("comparaison réutilisée")
    )
    monkeypatch.setattr(
        finalize,
        "compare_workspace",
        lambda *args, **kwargs: {
            "status": "blocked",
            "comparison_id": kwargs["comparison_id"],
            "plan": "plan.json",
            "plan_sha256": "plan-sha",
            "counts": {"blocked": 1},
        },
    )

    result = finalize.finalize_workspace(
        tmp_path,
        "debat_test",
        "EDIT-TEST-001",
        refresh_remote=True,
        comparison_id="REMOTE-20261104-009",
    )

    assert result["status"] == "blocked"
    assert result["steps"]["render"]["status"] == "reused"
    assert result["steps"]["release"]["status"] == "reused"
    assert result["steps"]["remote_compare"]["status"] == "created"


def test_comparison_id_requires_explicit_refresh(tmp_path: Path):
    with pytest.raises(finalize.WorkspaceFinalizeError, match="exige --refresh-remote"):
        finalize.finalize_workspace(
            tmp_path,
            "debat_test",
            "EDIT-TEST-001",
            comparison_id="REMOTE-20261104-009",
        )
