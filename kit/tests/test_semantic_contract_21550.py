from __future__ import annotations
import json
import sys
from pathlib import Path
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from test_wikidebia_translation_review import make_french_locked, complete_translation_review, translation, common  # noqa: E402


def _prepared_complete(tmp_path: Path):
    project, workspace, work_id = make_french_locked(tmp_path)
    translation.prepare_review(project, "debat_test", work_id)
    complete_translation_review(workspace)
    path = workspace / "reviews/en/translation_review.json"
    return project, workspace, work_id, path, json.loads(path.read_text(encoding="utf-8"))


def test_displayed_title_field_lineage_is_blocking(tmp_path: Path):
    project, workspace, work_id, path, review = _prepared_complete(tmp_path)
    review["arguments"][0]["translation"]["displayed_title_translates_french_displayed_title"] = False
    common.write_json(path, review)
    with pytest.raises(translation.TranslationReviewError, match="traduire directement"):
        translation.finalize_review(project, "debat_test", work_id)


def test_english_only_metadiscourse_is_blocking(tmp_path: Path):
    project, workspace, work_id, path, review = _prepared_complete(tmp_path)
    row = review["arguments"][0]["translation"]
    row["summary"] = "The argument concludes that " + row["summary"][0].lower() + row["summary"][1:]
    common.write_json(path, review)
    with pytest.raises(translation.TranslationReviewError, match="Métadiscours ajouté uniquement en anglais"):
        translation.finalize_review(project, "debat_test", work_id)


def test_keyword_concept_id_is_generated_and_must_match_in_english(tmp_path: Path):
    project, workspace, work_id, path, review = _prepared_complete(tmp_path)
    assert review["vocabulary"]
    original = review["vocabulary"][0]["concept_id"]
    assert original.startswith("KWD-") and len(original) >= 16
    review["vocabulary"][0]["concept_id"] = "KWD-AAAAAAAAAAAA"
    assert review["vocabulary"][0]["concept_id"] != original
    common.write_json(path, review)
    with pytest.raises(translation.TranslationReviewError, match="concept_id anglais divergent"):
        translation.finalize_review(project, "debat_test", work_id)


def test_idiomatic_displayed_title_form_change_can_be_reviewed_explicitly(tmp_path: Path):
    project, workspace, work_id, path, review = _prepared_complete(tmp_path)
    row = review["arguments"][0]["translation"]
    row["displayed_title_source_form"] = "question"
    row["displayed_title_target_form"] = "proposition"
    row["displayed_title_form_change_reviewed"] = True
    row["displayed_title_speech_act_preserved"] = True
    row["displayed_title_form_change_note"] = "The change is idiomatic and preserves exactly the same speech act, thesis and logical scope."
    common.write_json(path, review)
    result = translation.finalize_review(project, "debat_test", work_id)
    assert result["status"] == "en_translation_review_finalized"


def test_idiomatic_displayed_title_form_change_without_review_is_blocked(tmp_path: Path):
    project, workspace, work_id, path, review = _prepared_complete(tmp_path)
    row = review["arguments"][0]["translation"]
    row["displayed_title_source_form"] = "question"
    row["displayed_title_target_form"] = "proposition"
    common.write_json(path, review)
    with pytest.raises(translation.TranslationReviewError, match="changement idiomatique de forme"):
        translation.finalize_review(project, "debat_test", work_id)


def test_debate_field_semantic_proof_is_bound_to_source_and_target(tmp_path: Path):
    project, workspace, work_id, path, review = _prepared_complete(tmp_path)
    debate = review["debate"]
    debate["french"]["content"]["subject"] = "Toujours le débat test"
    debate["topic"] = "Test debate"
    debate["debate_field_semantic_risk_reviewed"] = True
    debate["debate_field_semantic_risk_note"] = "The missing frequency marker was reviewed directly against the French topic field."
    debate["debate_field_semantic_risk_evidence"] = []
    # Exercise field-level evidence validation directly. Finalization now
    # rejects a forged embedded French field even before this semantic guard.
    _, sources = translation._validate_sources(
        json.loads((workspace / "data/sources_en_working.json").read_text()), "debat_test", set()
    )
    keywords = {row["fr"]: row["en"] for row in review["vocabulary"]}
    with pytest.raises(translation.TranslationReviewError, match="Chaque risque sémantique de Debate"):
        translation._validate_debate(debate, keywords, sources, "debat_test")
