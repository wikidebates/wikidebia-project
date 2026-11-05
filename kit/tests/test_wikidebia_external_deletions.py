from __future__ import annotations

import json
from pathlib import Path

import pytest

import wikidebia_external_deletions as deletions
from wikidebia_update import sha_object


DEBATE = "debat_test"
WORK = "EDIT-TEST-001"
COMPARISON = "REMOTE-20261104-001"
TITLE = "Argument supprimé"


def _signed(value: dict, field: str) -> dict:
    value[field] = sha_object(value)
    return value


def _evidence(project: Path) -> tuple[Path, dict, dict, dict]:
    run = project / ".state/remote-comparisons" / DEBATE / WORK / COMPARISON
    run.mkdir(parents=True)
    operation = {
        "wiki": "fr", "language": "fr", "title": TITLE, "page_id": "A1",
        "page_type": "argument", "old_sha256": None, "new_sha256": "1" * 64,
        "expected_revision_id": None, "observed_revision_id": None,
        "justification": "Page du nouveau corpus", "preconditions": ["title_absent_at_execution"],
        "result": None, "phase": 2, "source_path": "release/output/fr/A1.wiki",
        "local_file_sha256": "2" * 64,
    }
    operations = {
        name: ([operation] if name == "create" else [])
        for name in ("create", "update", "move", "redirect", "delete", "skip", "manual_review", "blocked")
    }
    plan = _signed({
        "debate_id": DEBATE, "operations": operations,
        "counts": {name: len(rows) for name, rows in operations.items()},
        "preconditions": [],
    }, "plan_sha256")
    inventory = _signed({
        "debate_id": DEBATE, "comparison_id": COMPARISON,
        "pages": [{
            "language": "fr", "canonical_title": TITLE, "exists": False,
            "revision_id": None, "content_sha256": None,
            "observed_at": "2026-11-04T12:00:00+00:00",
        }],
        "remote_write_performed": False,
    }, "inventory_sha256")
    receipt = _signed({
        "debate_id": DEBATE, "work_id": WORK, "comparison_id": COMPARISON,
        "plan_sha256": plan["plan_sha256"],
        "remote_inventory_sha256": inventory["inventory_sha256"],
        "release_copy_tree_sha256": "3" * 64,
        "remote_write_performed": False,
    }, "receipt_sha256")
    for name, value in (
        ("update-plan.json", plan), ("remote-inventory.json", inventory),
        ("comparison-receipt.json", receipt),
    ):
        (run / name).write_text(json.dumps(value) + "\n", encoding="utf-8")
    return run, receipt, plan, inventory


def test_acceptance_requires_signed_absence_and_is_idempotent(tmp_path: Path):
    _run, _receipt, plan, _inventory = _evidence(tmp_path)

    result = deletions.accept_external_deletion(
        tmp_path, DEBATE, WORK, COMPARISON, language="fr", page_id="A1",
        reason="Doublon supprimé volontairement", accepted_by="owner",
        confirm_plan_sha256=plan["plan_sha256"],
    )

    assert result["status"] == "registered"
    assert result["remote_write_performed"] is False
    path = tmp_path / result["registry_path"]
    registry = json.loads(path.read_text(encoding="utf-8"))
    unsigned = dict(registry)
    assert unsigned.pop("registry_sha256") == sha_object(unsigned)
    assert registry["entries"][0]["release_page_sha256"] == "1" * 64
    repeated = deletions.accept_external_deletion(
        tmp_path, DEBATE, WORK, COMPARISON, language="fr", page_id="A1",
        reason="Doublon supprimé volontairement", accepted_by="owner",
        confirm_plan_sha256=plan["plan_sha256"],
    )
    assert repeated["status"] == "already_registered"
    assert repeated["registry_sha256"] == result["registry_sha256"]


def test_acceptance_rejects_tampered_comparison(tmp_path: Path):
    run, _receipt, plan, _inventory = _evidence(tmp_path)
    value = json.loads((run / "remote-inventory.json").read_text(encoding="utf-8"))
    value["pages"][0]["exists"] = True
    (run / "remote-inventory.json").write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(deletions.ExternalDeletionError, match="inventaire distant invalide"):
        deletions.accept_external_deletion(
            tmp_path, DEBATE, WORK, COMPARISON, language="fr", page_id="A1",
            reason="Doublon supprimé volontairement", accepted_by="owner",
            confirm_plan_sha256=plan["plan_sha256"],
        )


def test_acceptance_rejects_unsafe_comparison_identifier(tmp_path: Path):
    with pytest.raises(deletions.ExternalDeletionError, match="REMOTE-AAAAMMJJ-NNN"):
        deletions.accept_external_deletion(
            tmp_path, DEBATE, WORK, "../../outside", language="fr", page_id="A1",
            reason="Doublon supprimé volontairement", accepted_by="owner",
            confirm_plan_sha256="1" * 64,
        )


def test_matching_acceptance_turns_recreation_into_audited_skip(tmp_path: Path):
    _run, _receipt, plan, inventory = _evidence(tmp_path)
    deletions.accept_external_deletion(
        tmp_path, DEBATE, WORK, COMPARISON, language="fr", page_id="A1",
        reason="Doublon supprimé volontairement", accepted_by="owner",
        confirm_plan_sha256=plan["plan_sha256"],
    )
    unsigned = dict(plan)
    unsigned.pop("plan_sha256")

    result = deletions.apply_external_deletions(tmp_path, DEBATE, unsigned, inventory)

    assert result["applied"] == 1
    assert unsigned["counts"]["create"] == 0
    assert unsigned["counts"]["skip"] == 1
    skipped = unsigned["operations"]["skip"][0]
    assert skipped["page_id"] == "A1"
    assert skipped["external_deletion_acceptance"]["registry_sha256"] == result["registry_sha256"]
    assert "accepted_external_deletions_applied" in unsigned["preconditions"]


def test_changed_release_source_is_never_silently_skipped(tmp_path: Path):
    _run, _receipt, plan, inventory = _evidence(tmp_path)
    deletions.accept_external_deletion(
        tmp_path, DEBATE, WORK, COMPARISON, language="fr", page_id="A1",
        reason="Doublon supprimé volontairement", accepted_by="owner",
        confirm_plan_sha256=plan["plan_sha256"],
    )
    unsigned = dict(plan)
    unsigned.pop("plan_sha256")
    unsigned["operations"]["create"][0]["new_sha256"] = "9" * 64

    result = deletions.apply_external_deletions(tmp_path, DEBATE, unsigned, inventory)

    assert result["applied"] == 0
    assert result["source_mismatches"] == [
        {"language": "fr", "page_id": "A1", "reason": "release_source_changed"}
    ]
    assert unsigned["counts"]["create"] == 1


def test_registry_export_import_and_revocation_are_signed_and_monotonic(tmp_path: Path):
    _run, _receipt, plan, _inventory = _evidence(tmp_path)
    deletions.accept_external_deletion(
        tmp_path, DEBATE, WORK, COMPARISON, language="fr", page_id="A1",
        reason="Doublon supprimé volontairement", accepted_by="owner",
        confirm_plan_sha256=plan["plan_sha256"],
    )
    exported = tmp_path / "portable/registry.json"
    result = deletions.export_registry(tmp_path, DEBATE, exported)
    assert result["status"] == "exported"
    local = deletions.registry_path(tmp_path, DEBATE)
    local.unlink()
    imported = deletions.import_registry(tmp_path, DEBATE, exported)
    assert imported["status"] == "imported"

    revoked = deletions.revoke_external_deletion(
        tmp_path, DEBATE, language="fr", page_id="A1",
        reason="La suppression doit être réexaminée", revoked_by="owner",
    )
    assert revoked["status"] == "revoked"
    registry = json.loads(local.read_text())
    unsigned = dict(registry)
    assert unsigned.pop("registry_sha256") == sha_object(unsigned)
    assert registry["entries"][0]["status"] == "revoked"
    with pytest.raises(deletions.ExternalDeletionError, match="régresser"):
        deletions.import_registry(tmp_path, DEBATE, exported)
