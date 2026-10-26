from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import wikidebia_continuity as continuity


def _signed(value: dict, field: str) -> dict:
    result = dict(value)
    body = dict(result)
    body.pop(field, None)
    result[field] = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return result


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _fixture(project: Path, *, receipt_outside_work: bool = False) -> tuple[str, str, Path]:
    debate_id = "debat_test"
    work_id = "EDIT-20261023-001"
    _write(project / ".state/workflows" / debate_id / "workflow.json", {
        "debate_id": debate_id,
        "work_id": work_id,
    })

    checkpoint_plan = "1" * 64
    checkpoint_remote_receipt = "2" * 64
    content_receipt = _signed({
        "schema": "wikidebia-fr-publication-receipt-1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "status": "published",
        "plan_sha256": checkpoint_plan,
        "remote_receipt_sha256": checkpoint_remote_receipt,
    }, "receipt_sha256")
    _write(
        project / ".state/fr-publication" / debate_id / work_id / "content/publication-receipt.json",
        content_receipt,
    )

    page = {
        "page_id": "A0001",
        "page_type": "argument",
        "canonical_title": "Titre source",
        "content_sha256": "3" * 64,
        "revision_id": 10,
        "status": "published",
    }
    anchor = _signed({
        "schema": "wikidebia-published-state-1.0",
        "debate_id": debate_id,
        "language": "fr",
        "plan_sha256": checkpoint_plan,
        "receipt_sha256": checkpoint_remote_receipt,
        "source_manifest_sha256": "4" * 64,
        "corpus_version": "manifest-test",
        "pages": [page],
    }, "state_sha256")

    correction = _signed({
        "schema": "wikidebia-french-correction-receipt-1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "language": "fr",
        "plan_sha256": "5" * 64,
    }, "receipt_sha256")
    if receipt_outside_work:
        correction_path = project / ".state/other/correction-receipt.json"
    else:
        correction_path = (
            project / ".state/fr-publication" / debate_id / work_id / "content/correction-receipt.json"
        )
    _write(correction_path, correction)

    corrected_page = dict(page)
    corrected_page.update({
        "canonical_title": "Titre rétabli",
        "content_sha256": "6" * 64,
        "revision_id": 11,
    })
    corrected = dict(anchor)
    corrected.pop("state_sha256")
    corrected.update({
        "plan_sha256": correction["plan_sha256"],
        "receipt_path": correction_path.relative_to(project).as_posix(),
        "receipt_sha256": correction["receipt_sha256"],
        "pages": [corrected_page],
    })
    corrected = _signed(corrected, "state_sha256")

    state_root = project / ".state/published" / debate_id / "fr"
    _write(state_root / "20261023T120000Z.json", anchor)
    _write(state_root / "20261023T130000Z.json", corrected)
    _write(state_root / "latest.json", corrected)
    snapshot = project / "continuity" / debate_id / "latest"
    snapshot.mkdir(parents=True)
    (snapshot / "HANDOFF.md").write_text("# Reprise\n", encoding="utf-8")
    return debate_id, work_id, snapshot


def _add_final_publication(project: Path, debate_id: str, work_id: str) -> None:
    state_root = project / ".state/published" / debate_id
    corrected = json.loads((state_root / "fr/latest.json").read_text(encoding="utf-8"))
    final_root = project / ".state/final-publication" / debate_id / work_id
    receipts_root = project / ".state/receipts" / debate_id

    final_manifest = "7" * 64
    final_corpus = "manifest-final"
    french_content = "8" * 64
    english_content = "9" * 64
    baseline = _signed({
        "debate_id": debate_id,
        "work_id": work_id,
    }, "baseline_sha256")
    _write(final_root / "baseline.json", baseline)
    safety_plan = _signed({
        "debate_id": debate_id,
        "languages": ["fr", "en"],
    }, "plan_sha256")
    _write(final_root / "safety-update-plan.json", safety_plan)
    french_plan = _signed({
        "debate_id": debate_id,
        "languages": ["fr"],
        "new_manifest_sha256": final_manifest,
        "corpus_version": final_corpus,
        "operations": {
            "create": [],
            "update": [{
                "page_id": "A0001",
                "page_type": "argument",
                "new_sha256": french_content,
            }],
            "move": [],
            "redirect": [],
            "delete": [],
            "skip": [],
            "manual_review": [],
            "blocked": [],
        },
    }, "plan_sha256")
    _write(final_root / "french-update-plan.json", french_plan)

    underlying_french = _signed({
        "debate_id": debate_id,
        "plan_sha256": french_plan["plan_sha256"],
        "status": "executed",
    }, "receipt_sha256")
    _write(receipts_root / "latest.json", underlying_french)
    french_receipt = _signed({
        "status": "published",
        "plan_sha256": french_plan["plan_sha256"],
        "underlying_receipt_sha256": underlying_french["receipt_sha256"],
        "counts": {"already_done": 0, "updated": 1},
    }, "receipt_sha256")
    _write(final_root / "french-publication-receipt.json", french_receipt)

    english_plan = _signed({
        "debate_id": debate_id,
        "actions": [{
            "language": "en",
            "operation": "create",
            "page_id": "A0001",
            "page_type": "argument",
            "desired_sha256": english_content,
        }],
    }, "plan_sha256")
    _write(final_root / "english-publication-plan.json", english_plan)
    preflight = _signed({
        "status": "ready",
        "safety_plan_sha256": safety_plan["plan_sha256"],
        "english_plan_sha256": english_plan["plan_sha256"],
        "french_plan_sha256": french_plan["plan_sha256"],
    }, "preflight_sha256")
    _write(final_root / "preflight.json", preflight)
    authorization = _signed({
        "status": "authorized",
        "remote_write_authorized": True,
        "baseline_sha256": baseline["baseline_sha256"],
        "preflight_sha256": preflight["preflight_sha256"],
    }, "authorization_sha256")
    _write(final_root / "authorization.json", authorization)
    underlying_english = _signed({
        "debate_id": debate_id,
        "language": "en",
        "plan_sha256": english_plan["plan_sha256"],
    }, "receipt_sha256")
    english_receipt_path = receipts_root / "publication-en-20261024T001628Z.json"
    _write(english_receipt_path, underlying_english)
    english_receipt = _signed({
        "status": "published",
        "plan_sha256": english_plan["plan_sha256"],
        "counts": {"created": 1, "updated": 0, "skipped": 0},
    }, "receipt_sha256")
    _write(final_root / "english-publication-receipt.json", english_receipt)

    english_page = dict(corrected["pages"][0])
    english_page.update({
        "canonical_title": "English title",
        "content_sha256": english_content,
        "revision_id": 20,
    })
    english_state = _signed({
        "debate_id": debate_id,
        "language": "en",
        "plan_sha256": english_plan["plan_sha256"],
        "receipt_sha256": underlying_english["receipt_sha256"],
        "receipt_path": english_receipt_path.relative_to(project).as_posix(),
        "source_manifest_sha256": final_manifest,
        "corpus_version": final_corpus,
        "pages": [english_page],
    }, "state_sha256")
    _write(state_root / "en/20261024T001628Z.json", english_state)
    _write(state_root / "en/latest.json", english_state)

    final_page = dict(corrected["pages"][0])
    final_page.update({"content_sha256": french_content, "revision_id": 12})
    final_state = dict(corrected)
    final_state.pop("state_sha256")
    final_state.update({
        "plan_sha256": french_plan["plan_sha256"],
        "receipt_sha256": underlying_french["receipt_sha256"],
        "receipt_path": (receipts_root / "latest.json").relative_to(project).as_posix(),
        "source_manifest_sha256": final_manifest,
        "corpus_version": final_corpus,
        "pages": [final_page],
    })
    final_state = _signed(final_state, "state_sha256")
    _write(state_root / "fr/20261024T073600Z.json", final_state)
    _write(state_root / "fr/latest.json", final_state)

    final_receipt = _signed({
        "debate_id": debate_id,
        "work_id": work_id,
        "status": "published",
        "french_receipt_sha256": french_receipt["receipt_sha256"],
        "english_receipt_sha256": english_receipt["receipt_sha256"],
        "baseline_sha256": baseline["baseline_sha256"],
        "preflight_sha256": preflight["preflight_sha256"],
        "authorization_sha256": authorization["authorization_sha256"],
    }, "receipt_sha256")
    _write(final_root / "publication-receipt.json", final_receipt)


def test_sync_copies_complete_signed_french_succession(tmp_path: Path):
    debate_id, work_id, snapshot = _fixture(tmp_path)

    result = continuity.sync_signed_french_history(tmp_path, debate_id)

    assert result["history_state_count"] == 2
    assert result["post_checkpoint_correction_count"] == 1
    assert (snapshot / "runtime/published/fr/20261023T120000Z.json").is_file()
    assert (snapshot / "runtime/published/fr/20261023T130000Z.json").is_file()
    assert (snapshot / "runtime/published/fr/latest.json").is_file()
    assert (snapshot / "runtime/fr-publication/content/publication-receipt.json").is_file()
    assert (snapshot / "runtime/fr-publication/content/correction-receipt.json").is_file()
    assert continuity.verify_committed_snapshot(snapshot) == {
        "status": "passed",
        "debate_id": debate_id,
        "work_id": work_id,
        "history_state_count": 2,
        "post_checkpoint_correction_count": 1,
        "current_state_sha256": result["current_state_sha256"],
    }


def test_check_refuses_incomplete_projection(tmp_path: Path):
    debate_id, _work_id, snapshot = _fixture(tmp_path)
    continuity.sync_signed_french_history(tmp_path, debate_id)
    (snapshot / "runtime/published/fr/20261023T120000Z.json").unlink()

    with pytest.raises(continuity.ContinuityError, match="incomplète"):
        continuity.sync_signed_french_history(tmp_path, debate_id, check_only=True)


def test_sync_refuses_correction_receipt_outside_work(tmp_path: Path):
    debate_id, _work_id, _snapshot = _fixture(tmp_path, receipt_outside_work=True)

    with pytest.raises(continuity.ContinuityError, match="extérieur au périmètre"):
        continuity.sync_signed_french_history(tmp_path, debate_id)


def test_sync_copies_and_verifies_terminal_bilingual_publication(tmp_path: Path):
    debate_id, work_id, snapshot = _fixture(tmp_path)
    _add_final_publication(tmp_path, debate_id, work_id)

    result = continuity.sync_signed_french_history(tmp_path, debate_id)

    assert result["history_state_count"] == 3
    assert result["post_checkpoint_correction_count"] == 1
    assert (snapshot / "runtime/final-publication/publication-receipt.json").is_file()
    assert (snapshot / "runtime/published/en/latest.json").is_file()
    assert (snapshot / "runtime/receipts/publication-en-20261024T001628Z.json").is_file()
    assert continuity.verify_committed_snapshot(snapshot)["current_state_sha256"] == result[
        "current_state_sha256"
    ]


def test_every_committed_latest_snapshot_has_complete_signed_french_succession():
    project_root = Path(__file__).resolve().parents[2]
    snapshots = sorted((project_root / "continuity").glob("*/latest"))
    if not snapshots:
        pytest.skip("Les snapshots propres aux débats restent sur leurs branches dédiées")
    for snapshot in snapshots:
        continuity.verify_committed_snapshot(snapshot)
