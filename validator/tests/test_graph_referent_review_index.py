"""Indexing large individual title reviews preserves historical first-match semantics."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from wikidebia_validator.graph import _canonical_referent_manually_verified
from wikidebia_validator.package import PackageContext
from wikidebia_validator.report import Report
from wikidebia_validator.validator import validate_package
from wikidebia_validator.graph import structural_sha256

from .helpers import create_graph_package, dump, graph_projection


REVIEW_PATH = "reviews/individual_title_review.json"


def setup_review(tmp_path: Path, entries, *, rel: str = REVIEW_PATH) -> PackageContext:
    create_graph_package(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["editorial_controls"] = {"individual_review_path": rel}
    dump(manifest_path, manifest)
    if rel == REVIEW_PATH:
        dump(tmp_path / rel, {"entries": entries, "status": "reviewed"})
    return PackageContext(tmp_path, Report("test", tmp_path.name, ["graph"]))


def long_review(first=None):
    entries = [
        {"id": f"A{i:04d}", "canonical_referents_explicit_fr": i % 3 == 0}
        for i in range(10, 90)
    ]
    if first is not None:
        entries.insert(0, first)
    return entries


def test_index_retains_first_duplicate_id_even_if_second_is_approved(tmp_path):
    entries = long_review(
        {"id": "A0001", "canonical_referents_explicit_fr": False},
    )
    entries.append({"id": "A0001", "canonical_referents_explicit_fr": True})
    ctx = setup_review(tmp_path, entries)
    cache = {}
    assert not _canonical_referent_manually_verified(ctx, "A0001", "fr", _entry_index=cache)
    assert not _canonical_referent_manually_verified(ctx, "A0001", "fr")
    assert "rows" in cache and cache["rows"]["A0001"] is ctx.load_json(REVIEW_PATH)["entries"][0]
    assert _canonical_referent_manually_verified(ctx, "A0012", "fr", _entry_index=cache)


def test_existing_review_entry_mutation_is_visible_through_cached_reference(tmp_path):
    ctx = setup_review(tmp_path, long_review(
        {"id": "A0001", "canonical_referents_explicit_fr": False},
    ))
    memo = {}
    assert not _canonical_referent_manually_verified(ctx, "A0001", "fr", _entry_index=memo)
    ctx.load_json(REVIEW_PATH)["entries"][0]["canonical_referents_explicit_fr"] = True
    assert _canonical_referent_manually_verified(ctx, "A0001", "fr", _entry_index=memo)
    assert _canonical_referent_manually_verified(ctx, "A0001", "fr")


def test_replaced_review_document_invalidates_index(tmp_path):
    ctx = setup_review(tmp_path, long_review())
    memo = {}
    assert not _canonical_referent_manually_verified(ctx, "A0001", "fr", _entry_index=memo)
    new_entries = long_review(
        {"id": "A0001", "canonical_referents_explicit_fr": True},
    )
    ctx.cache[REVIEW_PATH] = {"entries": new_entries}
    assert _canonical_referent_manually_verified(ctx, "A0001", "fr", _entry_index=memo)


def test_review_list_length_change_invalidates_index(tmp_path):
    ctx = setup_review(tmp_path, long_review())
    memo = {}
    assert not _canonical_referent_manually_verified(ctx, "A0001", "fr", _entry_index=memo)
    ctx.load_json(REVIEW_PATH)["entries"].append({
        "id": "A0001", "canonical_referents_explicit_fr": True,
    })
    assert _canonical_referent_manually_verified(ctx, "A0001", "fr", _entry_index=memo)


def test_short_review_uses_historical_scan_without_building_index(tmp_path):
    ctx = setup_review(tmp_path, [{"id": "A0001", "canonical_referents_explicit_fr": True}])
    memo = {}
    assert _canonical_referent_manually_verified(ctx, "A0001", "fr", _entry_index=memo)
    assert memo == {}
    assert not _canonical_referent_manually_verified(ctx, "A9999", "en", _entry_index=memo)


def test_missing_review_path_keeps_historical_denial(tmp_path):
    ctx = setup_review(tmp_path, [], rel="reviews/missing.json")
    assert not _canonical_referent_manually_verified(ctx, "A0001", "fr", _entry_index={})
    assert ctx.report.errors == 0


@pytest.mark.parametrize("review_path", ["../escaped.json", "/outside.json", "reviews/../escape.json"])
def test_unsafe_review_path_still_generates_original_fs_diagnostic(tmp_path, review_path):
    ctx = setup_review(tmp_path, [], rel=review_path)
    memo = {}
    first = _canonical_referent_manually_verified(ctx, "A0001", "fr")
    second = _canonical_referent_manually_verified(ctx, "A0001", "fr", _entry_index=memo)
    assert first is False and second is False
    assert [f.code for f in ctx.report.findings] == ["WDV-FS-002", "WDV-FS-002"]


def test_malformed_review_json_is_still_rejected(tmp_path):
    ctx = setup_review(tmp_path, [])
    (tmp_path / REVIEW_PATH).write_text("{not json}\n", encoding="utf-8")
    ctx.cache.pop(REVIEW_PATH, None)
    assert not _canonical_referent_manually_verified(ctx, "A0001", "fr", _entry_index={})
    assert any(f.code == "WDV-SCH-001" for f in ctx.report.findings)


def test_contextual_title_attestation_is_respected_with_large_review(tmp_path):
    ctx = setup_review(tmp_path, long_review(
        {"id": "A0001", "canonical_referents_explicit_fr": True},
    ))
    reg_path = tmp_path / "data/registre_debat.json"
    registry = json.loads(reg_path.read_text(encoding="utf-8"))
    registry["graph"]["nodes"][0]["fr"]["canonical_title"] = "Ce programme apporte un bénéfice collectif"
    registry["graph"]["nodes"][1]["fr"]["canonical_title"] = "Ce programme présente un risque collectif"
    registry["graph"]["lifecycle"]["structural_sha256"] = structural_sha256(registry)
    dump(reg_path, registry)
    dump(tmp_path / "graph/graphe_argumentatif.json", graph_projection(registry))
    report = validate_package(tmp_path, scopes=["graph"])
    issues = [f for f in report.findings if f.code == "WDV-EDT-016"]
    assert len(issues) == 1, report.to_text()
    assert "/A0002/" not in (issues[0].pointer or "")
    assert issues[0].pointer.endswith("/A0002/fr/canonical_title")
