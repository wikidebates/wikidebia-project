from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load_module(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


workspace_tool = sys.modules.get("wikidebia_editorial_workspace") or load_module("wikidebia_editorial_workspace")
review_tool = sys.modules.get("wikidebia_editorial_review") or load_module("wikidebia_editorial_review")
content_tool = sys.modules.get("wikidebia_content_review") or load_module("wikidebia_content_review")
common = sys.modules["wikidebia_corpus_build"]

from test_wikidebia_editorial_review import make_workspace, complete_review, _rename_keyword_in_review_and_vocabulary  # noqa: E402


def test_working_vocabulary_declares_semantic_atomicity_fields():
    data = workspace_tool.keyword_vocabulary_working([
        {"entity_type": "argument", "entity_id": "A1", "source": {"keywords": ["argument d'autorité", "psychologie"]}}
    ], "debat_test", "WORK-1")
    by_term = {row["fr"]: row for row in data["entries"]}
    assert by_term["psychologie"]["atomic_concept"] is True
    assert by_term["psychologie"]["compositional_intersection"] is False
    assert by_term["psychologie"]["multiword_exception"] is False
    assert by_term["argument d'autorité"]["atomic_concept"] is None
    assert by_term["argument d'autorité"]["compositional_intersection"] is None
    assert by_term["argument d'autorité"]["multiword_exception"] is None
    assert by_term["argument d'autorité"]["multiword_exception_rationale"] == ""


@pytest.mark.parametrize("keyword", [
    "psychologie religieuse", "municipalités de gauche", "port du voile",
    "interdiction du voile islamique", "femmes voilées",
])
def test_finalize_rejects_compositional_intersection(tmp_path: Path, keyword: str):
    project, workspace, work_id = make_workspace(tmp_path)
    complete_review(workspace)
    _rename_keyword_in_review_and_vocabulary(workspace, "argumentation", keyword)
    vocabulary_path = workspace / "data/keyword_vocabulary_working.json"
    vocabulary = json.loads(vocabulary_path.read_text(encoding="utf-8"))
    entry = next(row for row in vocabulary["entries"] if row["fr"] == keyword)
    entry.update({
        "kind": "noun_phrase",
        "atomic_concept": True,
        "compositional_intersection": False,
        "multiword_exception": True,
        "multiword_exception_rationale": "Justification artificielle volontairement suffisante en longueur pour tester le refus sémantique.",
    })
    common.write_json(vocabulary_path, vocabulary)
    with pytest.raises(review_tool.EditorialReviewError, match="décomposer en unités de base"):
        review_tool.finalize_review(project, "debat_test", work_id)


@pytest.mark.parametrize("keyword", ["argument d'autorité", "voile islamique"])
def test_finalize_accepts_atomic_phrase(tmp_path: Path, keyword: str):
    project, workspace, work_id = make_workspace(tmp_path)
    complete_review(workspace)
    _rename_keyword_in_review_and_vocabulary(workspace, "argumentation", keyword)
    vocabulary_path = workspace / "data/keyword_vocabulary_working.json"
    vocabulary = json.loads(vocabulary_path.read_text(encoding="utf-8"))
    entry = next(row for row in vocabulary["entries"] if row["fr"] == keyword)
    entry.update({
        "kind": "noun_phrase",
        "atomic_concept": True,
        "compositional_intersection": False,
        "multiword_exception": True,
        "multiword_exception_rationale": "Locution conventionnelle qui désigne un concept précis dans la navigation.",
    })
    common.write_json(vocabulary_path, vocabulary)
    result = review_tool.finalize_review(project, "debat_test", work_id)
    assert result["status"] == "fr_review_finalized"


@pytest.mark.parametrize("pair", [
    ["dictature", "dictatures"], ["femme", "Femmes"], ["Emancipation", "émancipation"],
])
def test_keyword_diagnostics_report_duplicate_variants(pair):
    issues = workspace_tool.keyword_diagnostics(pair, fallback=False)
    assert [issue["code"] for issue in issues if issue["severity"] == "correction"] == ["KEYWORDS_DUPLICATE"]


def test_summary_review_emits_originality_and_exact_mechanism_excerpt():
    summary = "Une prémisse concrète conduit à la conclusion en reliant clairement la cause et son effet. Une seconde phrase précise la portée."
    review = content_tool._summary_style_review([{
        "id": "A1",
        "summary": summary,
        "status": "approved",
        "attestations": {},
    }], "debat_test")
    assert review["schema_version"] == "1.0"
    assert review["debate_id"] == "debat_test"
    decision = review["entries"][0]["languages"]["fr"]
    assert decision["originality_reviewed"] is True
    assert decision["mechanism_statement"] in summary
    assert len(decision["mechanism_statement"]) >= 30
