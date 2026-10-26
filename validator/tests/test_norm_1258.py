from __future__ import annotations

from wikidebia_validator.editorial import bilingual_semantic_marker_losses, validate_individual_review_data
from wikidebia_validator.report import Report
from wikidebia_validator.resource_registry import build_resource_registry, normalize_url
from tests.test_norm_1257 import _entry, _node


def _source(sid: str, label: str, link: str, language: str = "en"):
    return {
        "id": sid,
        "type": "bibliography",
        "language": language,
        "metadata": {
            "authors": ["Jane Doe"], "article": None, "work": label,
            "volume": None, "issue": None, "location": None,
            "publisher": "Example Press", "place": None, "date": "2024",
            "link": link, "page": None, "site": None, "title": None,
        },
        "verification": {"status": "verified", "verified_at": "2026-08-09T18:00:00+02:00", "primary_source": True, "notes": [], "language_verified": True},
        "usage": [{"page_id": "A0001", "language": language, "role": "supports_summary"}],
        "deduplication_key": sid.lower(),
    }


def test_resource_registry_normalizes_url_and_detects_same_identity_conflict():
    sources = {
        "source_registry_version": "1.0", "debate_id": "exemple",
        "sources": [
            _source("S00001", "First Book", "https://EXAMPLE.org/book/1/?utm_source=x&b=2&a=1"),
            _source("S00002", "Different Book", "https://example.org/book/1?a=1&b=2#chapter"),
        ],
    }
    registry = build_resource_registry(sources, "0" * 64)
    assert len(registry["resources"]) == 1
    resource = registry["resources"][0]
    assert resource["canonical_url"] == "https://example.org/book/1?a=1&b=2"
    assert resource["conflicts"][0]["kind"] == "same_identity_incompatible_label"


def test_resource_registry_accepts_short_title_inside_full_headline():
    full = _source(
        "S00001",
        "Nos vies confinées : Les femmes accomplissent 70 % en moyenne du travail familial et domestique",
        "https://example.org/article",
        language="fr",
    )
    short = _source(
        "S00002",
        "Les femmes accomplissent 70 % en moyenne du travail familial et domestique",
        "https://example.org/article#fragment",
        language="fr",
    )

    resource = build_resource_registry(
        {"source_registry_version": "1.0", "debate_id": "exemple", "sources": [full, short]},
        "0" * 64,
    )["resources"][0]

    assert resource["conflicts"] == []
    assert resource["labels"] == [{"language": "fr", "label": full["metadata"]["work"]}]
    assert len(resource["metadata_variants"]) == 2


def test_resource_registry_prefers_doi_identity():
    a = _source("S00001", "A Work", "https://doi.org/10.1234/ABC.5")
    b = _source("S00002", "A Work", "https://doi.org/10.1234/abc.5?utm_source=x")
    registry = build_resource_registry({"source_registry_version": "1.0", "debate_id": "exemple", "sources": [a, b]}, "0" * 64)
    assert len(registry["resources"]) == 1
    assert registry["resources"][0]["identity_type"] == "doi"
    assert registry["resources"][0]["doi"] == "10.1234/abc.5"


def test_semantic_marker_engine_covers_modal_scope_and_force():
    losses = bilingual_semantic_marker_losses(
        "Selon certains auteurs, tous ces cas sont souvent seulement supposés nécessaires et disparaissent aussitôt.",
        "These cases are necessary and disappear.",
    )
    for expected in {"attribution", "existential_quantifier", "universal_quantifier", "frequency_often", "restriction_only", "immediacy"}:
        assert expected in losses


def test_semantic_review_activation_depends_on_artifact_schema_not_norm_number():
    entry = _entry()
    issues = validate_individual_review_data(
        {"entries": [entry]}, [_node()], norm="1.2.56",
        translation_validation_mode="differential",
        translation_semantic_review_schema_version="1.1",
    )
    reasons = {i["reason"] for i in issues}
    assert "canonical_title_semantic_inventory_reviewed_en" in reasons


def test_validation_report_exposes_granular_layers():
    report = Report("0.4.61", "package", ["schema", "sources", "editorial", "bilingual"])
    report.error("WDV-GRA-001", "graph")
    report.warning("WDV-DOC-009", "doc")
    report.info("WDV-BIL-007", "semantic")
    layers = report.to_dict()["validation_layers"]
    assert layers["structural"]["status"] == "failed"
    assert layers["documentary"]["status"] == "passed_with_warnings"
    assert layers["semantic_review"]["status"] == "passed"
    assert layers["fresh_archive"]["status"] == "not_run"
