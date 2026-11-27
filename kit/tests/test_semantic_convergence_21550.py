from __future__ import annotations
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from test_wikidebia_translation_review import (  # noqa: E402
    make_french_locked, complete_translation_review, translation, convergence,
)


from french_normalization_fixture import prepare_fixture_translation

def _sealed(tmp_path: Path):
    project, workspace, work_id = make_french_locked(tmp_path)
    prepare_fixture_translation(project, "debat_test", work_id)
    complete_translation_review(workspace)
    sealed = translation.finalize_review(project, "debat_test", work_id)
    return project, workspace, work_id, sealed


def test_apply_is_blocked_before_two_convergent_passes(tmp_path: Path):
    project, workspace, work_id, sealed = _sealed(tmp_path)
    try:
        translation.apply_review(project, "debat_test", work_id, sealed["review_sha256"])
    except translation.TranslationReviewError as exc:
        assert "passes sémantiques" in str(exc)
    else:
        raise AssertionError("application must be blocked without semantic convergence")


def test_two_distinct_zero_error_passes_converge_and_apply(tmp_path: Path):
    project, workspace, work_id, sealed = _sealed(tmp_path)
    first = convergence.record_pass(project, "debat_test", work_id,
        method_family="proposition_by_proposition", method="proposition-by-proposition semantic comparison", reviewer="Reviewer A",
        note="The first pass compares every proposition and its modal and logical force against the immutable French source.")
    assert first["status"] == "in_progress"
    second = convergence.record_pass(project, "debat_test", work_id,
        method_family="risk_marker_review", method="risk-marker and edge-proposition reread", reviewer="Reviewer B",
        note="The second pass focuses independently on semantic risk markers, first and last propositions, scope and concrete anchors.")
    assert second["status"] == "converged"
    receipt = json.loads((workspace / "reviews/en/semantic_convergence_review.json").read_text(encoding="utf-8"))
    review = json.loads((workspace / "reviews/en/translation_review.json").read_text(encoding="utf-8"))
    convergence.verify_receipt(receipt, review)
    result = translation.apply_review(project, "debat_test", work_id, sealed["review_sha256"])
    assert result["status"] == "en_translation_applied"
    copied = json.loads((workspace / "translated-copy/reviews/en/semantic_convergence_review.json").read_text(encoding="utf-8"))
    assert copied["receipt_sha256"] == receipt["receipt_sha256"]


def test_same_method_twice_does_not_converge(tmp_path: Path):
    project, workspace, work_id, sealed = _sealed(tmp_path)
    for reviewer in ("Reviewer A", "Reviewer B"):
        result = convergence.record_pass(project, "debat_test", work_id,
            method_family="risk_marker_review", method="same semantic reread method", reviewer=reviewer,
            note="This intentionally repeats the same method to verify that independence is enforced by the convergence gate.")
    assert result["status"] == "in_progress"


def test_distinct_method_texts_in_same_family_do_not_converge(tmp_path: Path):
    project, workspace, work_id, sealed = _sealed(tmp_path)
    convergence.record_pass(project, "debat_test", work_id,
        method_family="risk_marker_review", method="risk-marker checklist pass one", reviewer="Reviewer A",
        note="The first pass uses the normalized risk-marker family and checks modal, quantifier and scope markers.")
    result = convergence.record_pass(project, "debat_test", work_id,
        method_family="risk_marker_review", method="different risk-marker checklist pass two", reviewer="Reviewer B",
        note="The second pass uses different wording but the same normalized review family, so it is not independent enough.")
    assert result["status"] == "in_progress"


def test_nonzero_error_pass_resets_convergence_chain(tmp_path: Path):
    project, workspace, work_id, sealed = _sealed(tmp_path)
    convergence.record_pass(project, "debat_test", work_id,
        method_family="proposition_by_proposition", method="first semantic comparison method", reviewer="Reviewer A",
        note="This zero-error pass would qualify unless a subsequent pass finds a certain error.")
    bad = convergence.record_pass(project, "debat_test", work_id,
        method_family="risk_marker_review", method="second independent semantic method", reviewer="Reviewer B",
        note="This pass intentionally reports a newly detected certain translation error and therefore invalidates convergence.",
        new_certain_errors=1)
    assert bad["status"] == "requires_revision"
    zero = convergence.record_pass(project, "debat_test", work_id,
        method_family="field_boundary_review", method="third independent semantic method", reviewer="Reviewer C",
        note="A single clean pass after a certain error is not enough to restore two-pass convergence.")
    assert zero["status"] == "in_progress"


def test_receipt_is_bound_to_exact_semantic_content_hash(tmp_path: Path):
    project, workspace, work_id, sealed = _sealed(tmp_path)
    convergence.record_pass(project, "debat_test", work_id,
        method_family="proposition_by_proposition", method="first independent semantic method", reviewer="Reviewer A",
        note="The first pass is bound to the exact semantic content hash of the finalized translation review.")
    convergence.record_pass(project, "debat_test", work_id,
        method_family="risk_marker_review", method="second independent semantic method", reviewer="Reviewer B",
        note="The second pass is also bound to the exact same immutable semantic content hash.")
    receipt = json.loads((workspace / "reviews/en/semantic_convergence_review.json").read_text(encoding="utf-8"))
    review_path = workspace / "reviews/en/translation_review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["final_values"]["arguments"][0]["displayed_title"] += " now"
    # Deliberately do not reseal: verification must fail immediately.
    try:
        convergence.verify_receipt(receipt, review)
    except translation.TranslationReviewError:
        pass
    else:
        raise AssertionError("receipt must not validate after semantic content mutation")
