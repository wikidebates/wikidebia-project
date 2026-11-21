"""Offline parity of early EN translation findings with render source-registry rules."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import wikidebia_translation_review as review


def source(**metadata):
    return {
        "id": "S10001", "language": "en", "type": "bibliography",
        "document_kind": "journal_article",
        "metadata": {"article": "Verified article", "work": "Journal", "authors": ["A. Author"],
                     "link": "https://journal.example/article", **metadata},
        "usage": [{"page_id": "A0001", "language": "en", "role": "bibliography",
                   "selection_reason": "Directly relevant verified source."}],
        "verification": {},
    }


def findings(*sources):
    return review.collect_english_documentary_findings({"debate_id": "demo", "sources": list(sources)})


def test_early_finds_render_page_locator_and_localization_defects():
    row = source(location="pp. 12–19", page="pp. 12–19", date="2026-08-03")
    result = findings(row)
    issues = {x["issue"]: x for x in result}
    assert issues["bibliography_pagination_in_location"]["field"] == "metadata/location"
    assert issues["bibliography_invalid_page_range"]["field"] == "metadata/page"
    assert issues["bibliography_invalid_page_range"]["disposition"] == "certain_normalization"
    assert issues["machine_documentary_date"]["validator_code"] == "WDV-DOC-005"
    assert {x["entity_id"] for x in result} == {"S10001"}
    assert row["metadata"]["date"] == "2026-08-03"  # report, never silently rewrite


@pytest.mark.parametrize("value,accepted", [
    ("13", True), ("13-19", True), ("13–19", False),
    ("pp. 13-19", False), ("Nº 3", False), ("13/19", False),
])
def test_page_value_match_is_identical_to_render_validator(value, accepted):
    assert bool(review.DOCUMENTARY_PAGE_VALUE.fullmatch(value)) is accepted


def test_access_date_requires_real_publication_date_decision():
    row = source(date="Accessed 14 November 2026")
    issue = next(x for x in findings(row) if x["issue"] == "access_date_used_as_documentary_date")
    assert issue["disposition"] == "editorial_decision"
    assert issue["field"] == "metadata/date"
    assert issue["validator_code"] == "WDV-DOC-003"


def test_collection_number_on_a_book_is_editorial_warning_not_assumed_issue():
    row = source(issue="No. 7")
    row["document_kind"] = "book"
    row["metadata"]["article"] = None
    result = findings(row)
    warning = next(x for x in result if x["issue"] == "possible_collection_number_in_issue")
    assert warning["severity"] == "warning"
    assert warning["disposition"] == "editorial_decision"


def test_same_doi_or_url_with_conflicting_titles_reports_precise_field():
    first = source(title="History of Institutions")
    second = copy.deepcopy(first)
    second["id"] = "S10002"
    second["metadata"]["title"] = "Unrelated Article"
    issues = findings(first, second)
    identity = next(x for x in issues if x["issue"] == "conflicting_same_resource_identity")
    assert identity["validator_code"] == "WDV-DOC-009"
    assert "metadata/title" in identity["field"]
    assert "S10001" in identity["entity_id"] and "S10002" in identity["entity_id"]


def test_valid_british_date_and_historical_quote_remain_unchanged():
    row = source(page="13-19", date="3 August 2026")
    approved = {
        "debate_id": "demo",
        "final_values": {
            "sources": [row],
            "arguments": [{"id": "A0001", "canonical_title": "A coherent English title",
                           "citations": [{"text": "An original historical citation."}]}],
        },
    }
    snapshot = copy.deepcopy(approved)
    assert findings(row) == []
    assert review.collect_english_documentary_findings(approved) == []
    assert approved == snapshot
    assert review.collect_english_title_format_findings(approved) == []


def test_validator_date_and_location_regexes_are_kept_in_parity():
    validator_src = Path(__file__).resolve().parents[2] / "validator" / "src"
    if str(validator_src) not in sys.path:
        sys.path.insert(0, str(validator_src))
    from wikidebia_validator import editorial
    for value in ("pp. 13-19", "pages 12–17", "Issue 5", "13-19", ""):
        assert bool(review.DOCUMENTARY_PAGE_IN_LOCATION.fullmatch(value)) == bool(editorial.PAGE_ONLY.fullmatch(value))
    for value in ("accessed November 12", "consultée le 2 mars", "2026-02-13"):
        assert bool(review.DOCUMENTARY_ACCESS_DATE.search(value)) == bool(editorial.ACCESS_DATE.search(value))
    for value in ("3 August 2026", "2026-08-03", "2026-08", "2026-08-03T12:00"):
        assert bool(review.DOCUMENTARY_MACHINE_DATE.fullmatch(value)) == bool(
            __import__("re").fullmatch(r"\d{4}-\d{2}(?:-\d{2})?(?:[T ].*)?", value)
        )
