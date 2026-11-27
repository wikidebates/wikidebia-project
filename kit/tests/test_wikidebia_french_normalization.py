import pytest

import wikidebia_french_normalization as normalization
import wikidebia_review_workflow as workflow
import wikidebia_translation_review as translation
from wikidebia_translation_worklist import build_worklist
from french_normalization_fixture import (
    complete_fixture_french_normalization, fake_wiki, fixture_french_wiki,
)
from test_wikidebia_translation_review import make_french_locked
from wikidebia_corpus_build import load_json, write_json


DEBATE = "debat_test"


def test_normalization_requires_published_french_source(tmp_path):
    project, workspace, work_id = make_french_locked(tmp_path)
    with pytest.raises(normalization.FrenchNormalizationError, match="reçu de publication du contenu français absent"):
        translation.prepare_french_normalization(project, DEBATE, work_id)
    assert not (workspace / normalization.REVIEW_PATH).exists()


@pytest.mark.parametrize("invalid", ["missing", "pending", "unjustified_exception", "requires_changes"])
def test_every_normalization_criterion_needs_a_result(tmp_path, invalid):
    project, _, work_id = make_french_locked(tmp_path)
    workspace, revisions = fixture_french_wiki(project, DEBATE, work_id)
    with fake_wiki(revisions):
        translation.prepare_french_normalization(project, DEBATE, work_id)
        report = complete_fixture_french_normalization(workspace)
        if invalid == "missing":
            del report["criteria"]["keywords"]
        elif invalid == "unjustified_exception":
            report["criteria"]["keywords"].update(status="exception", note=" ")
        else:
            report["criteria"]["keywords"]["status"] = invalid
        write_json(workspace / normalization.REVIEW_PATH, report)
        with pytest.raises(normalization.FrenchNormalizationError, match="critères|keywords"):
            translation.prepare_review(project, DEBATE, work_id)
    assert not (workspace / "reviews/en/translation_review.json").exists()
    assert not (workspace / normalization.RECEIPT_PATH).exists()


def test_updated_wiki_revision_blocks_even_if_the_text_is_identical(tmp_path):
    project, _, work_id = make_french_locked(tmp_path)
    workspace, revisions = fixture_french_wiki(project, DEBATE, work_id)
    with fake_wiki(revisions):
        result = translation.prepare_french_normalization(project, DEBATE, work_id)
        debate = result["pages"][0]
        assert debate["url"].startswith("https://fr.wikidebates.org/wiki/")
        assert debate["revision_url"].endswith(f"/revision/{debate['revision_id']}/html")
        complete_fixture_french_normalization(workspace)
        revisions[debate["title"]]["revision_id"] += 1
        with pytest.raises(normalization.FrenchNormalizationError, match="Révision française non confirmée"):
            translation.prepare_review(project, DEBATE, work_id)
    assert not (workspace / "reviews/en/translation_review.json").exists()


def test_receipt_binds_review_and_keeps_existing_draft_edits(tmp_path):
    project, _, work_id = make_french_locked(tmp_path)
    workspace, revisions = fixture_french_wiki(project, DEBATE, work_id)
    with fake_wiki(revisions):
        translation.prepare_french_normalization(project, DEBATE, work_id)
        report = complete_fixture_french_normalization(workspace)
        report["criteria"]["documentation"].update(
            status="exception",
            note="A0001, citation historique conservée conformément à la décision de revue.",
        )
        write_json(workspace / normalization.REVIEW_PATH, report)
        translation.prepare_review(project, DEBATE, work_id)
        receipt = load_json(workspace / normalization.RECEIPT_PATH)
        draft_path = workspace / "reviews/en/translation_review.json"
        draft = load_json(draft_path)
        assert receipt["criteria"] == report["criteria"]
        assert draft.pop("french_normalization_receipt_sha256") == receipt["receipt_sha256"]
        draft["debate"]["topic"] = "An existing translation"
        write_json(draft_path, draft)
        assert translation.prepare_review(project, DEBATE, work_id)["idempotent"]
    draft = load_json(draft_path)
    assert draft["french_normalization_receipt_sha256"] == receipt["receipt_sha256"]
    assert draft["debate"]["topic"] == "An existing translation"
    report["criteria"]["documentation"]["note"] = "Décision modifiée après la préparation anglaise."
    write_json(workspace / normalization.REVIEW_PATH, report)
    with pytest.raises(normalization.FrenchNormalizationError, match="reçu français diverge"):
        translation.finalize_review(project, DEBATE, work_id)
    with pytest.raises(normalization.FrenchNormalizationError, match="reçu français diverge"):
        build_worklist(project, DEBATE, work_id)


def test_workflow_pauses_with_a_link_to_the_published_debate(tmp_path, monkeypatch):
    project, _, work_id = make_french_locked(tmp_path)
    workspace, revisions = fixture_french_wiki(project, DEBATE, work_id)
    state = {
        "debate_id": DEBATE, "work_id": work_id, "phase": "en_translation_review",
        "status": "running", "french_graph_publication": {"status": "verified_no_changes"},
        "french_content_publication": {"status": "published"},
    }
    prepared_types = []
    monkeypatch.setattr(
        workflow, "create_review_package",
        lambda *args, review_type, **kwargs: prepared_types.append(review_type),
    )
    with fake_wiki(revisions):
        waiting = workflow._mechanical_advance(project, state)
        assert waiting["status"] == "french_normalization_required"
        assert waiting["french_normalization"]["debate_url"].startswith("https://fr.wikidebates.org/wiki/")
        assert waiting["french_normalization"]["debate_revision_url"].endswith("/html")
        assert not prepared_types
        assert not (workspace / "reviews/en/translation_review.json").exists()
        complete_fixture_french_normalization(workspace)
        workflow._mechanical_advance(project, waiting)
    assert prepared_types == ["en_translation_review"]
    assert "french_normalization_blocker" not in state


def test_classification_evidence_is_reused_without_a_second_editorial_review(tmp_path):
    project, workspace, work_id = make_french_locked(tmp_path)
    _, revisions = fixture_french_wiki(project, DEBATE, work_id)
    with fake_wiki(revisions):
        translation.prepare_french_normalization(project, DEBATE, work_id)
        report = load_json(workspace / normalization.REVIEW_PATH)
        evidence = report["prior_review_evidence"]
        assert set(evidence["reusable_criteria"]) == {"sections", "keywords"}
        assert set(evidence["page_ids"]) == {page["page_id"] for page in report["pages"]}
        assert report["criteria"]["sections"]["status"] == "reused"
        assert report["criteria"]["keywords"]["status"] == "reused"
        assert report["criteria"]["graph"]["status"] == "pending"
        report = complete_fixture_french_normalization(workspace)
        translation.prepare_review(project, DEBATE, work_id)
        assert load_json(workspace / normalization.RECEIPT_PATH)["criteria"]["keywords"]["status"] == "reused"


def test_cannot_reuse_an_unattested_criterion(tmp_path):
    project, workspace, work_id = make_french_locked(tmp_path)
    _, revisions = fixture_french_wiki(project, DEBATE, work_id)
    with fake_wiki(revisions):
        translation.prepare_french_normalization(project, DEBATE, work_id)
        report = complete_fixture_french_normalization(workspace)
        report["criteria"]["graph"]["status"] = "reused"
        write_json(workspace / normalization.REVIEW_PATH, report)
        with pytest.raises(normalization.FrenchNormalizationError, match="graph"):
            translation.prepare_review(project, DEBATE, work_id)
