"""Shared registry/projection validation must preserve exact findings in every case."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from wikidebia_validator.package import PackageContext
from wikidebia_validator.report import Report
from wikidebia_validator.schema_validation import (
    SchemaStore, _json_identical, _reusable_graph_fields,
)
from wikidebia_validator.validator import validate_package
from wikidebia_validator import schema_validation

from .helpers import create_graph_package, dump


def _report_comparison(package: Path, expect_reuse: bool) -> dict:
    """Force the original full path as an independent report-parity oracle."""
    optimized_graph_calls: list[tuple[str, ...]] = []
    original = SchemaStore.validate

    def instrument(self, instance, schema_name, *, _validated_graph_fields=()):
        if schema_name == "argument_graph.schema.json":
            optimized_graph_calls.append(_validated_graph_fields)
        return original(
            self, instance, schema_name,
            _validated_graph_fields=_validated_graph_fields,
        )

    with patch.object(SchemaStore, "validate", instrument):
        optimized = validate_package(package, scopes=["schema"]).to_dict()
    with patch.object(schema_validation, "_reusable_graph_fields", return_value=()):
        complete = validate_package(package, scopes=["schema"]).to_dict()

    assert optimized == complete
    assert bool(optimized_graph_calls)
    assert any(bool(fields) for fields in optimized_graph_calls) is expect_reuse
    return optimized


@pytest.mark.parametrize("scenario,expect_reuse", [
    ("unchanged", True),
    ("projection_exclusive_error", True),
    ("projection_extra_key", True),
    ("invalid_graph_in_both", False),
    ("different_projected_graph", False),
    ("projection_invalid_shared_field", False),
    ("registry_invalid_shared_field", False),
    ("registry_unrelated_error", False),
    ("shared_field_missing", False),
    ("different_json_scalar_types", False),
])
def test_proven_common_graph_reuse_preserves_exact_report(
    tmp_path: Path, scenario: str, expect_reuse: bool,
):
    create_graph_package(tmp_path)
    registry_path = tmp_path / "data/registre_debat.json"
    projection_path = tmp_path / "graph/graphe_argumentatif.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    projection = json.loads(projection_path.read_text(encoding="utf-8"))

    if scenario == "projection_exclusive_error":
        projection["graph_schema_version"] = 14
    elif scenario == "projection_extra_key":
        projection["unexpected_extra"] = "reject this"
    elif scenario == "invalid_graph_in_both":
        registry["graph"]["nodes"][0]["status"] = "INVALID"
        projection["nodes"][0]["status"] = "INVALID"
    elif scenario == "different_projected_graph":
        projection["nodes"][0]["fr"]["canonical_title"] = "Une autre proposition vérifiable"
    elif scenario == "projection_invalid_shared_field":
        projection["nodes"][0]["status"] = "INVALID"
    elif scenario == "registry_invalid_shared_field":
        registry["graph"]["nodes"][0]["status"] = "INVALID"
    elif scenario == "registry_unrelated_error":
        registry["debate"]["scope"]["proposition_fr"] = 12
    elif scenario == "shared_field_missing":
        registry["graph"].pop("nodes")
        projection.pop("nodes")
    elif scenario == "different_json_scalar_types":
        # Python considers True == 1, but JSON Schema does not.
        registry["graph"]["nodes"][0]["pages"]["fr"]["wiki"]["remote_revision_id"] = 1
        projection["nodes"][0]["pages"]["fr"]["wiki"]["remote_revision_id"] = True

    dump(registry_path, registry)
    dump(projection_path, projection)
    report = _report_comparison(tmp_path, expect_reuse)
    if scenario not in {"unchanged", "different_projected_graph"}:
        assert any(f["code"] == "WDV-SCH-003" for f in report["findings"])


def test_fast_path_fails_closed_when_schema_changes(tmp_path: Path):
    create_graph_package(tmp_path)
    store = SchemaStore()
    ctx = PackageContext(tmp_path, Report("test", ".", ["schema"]))
    registry = "data/registre_debat.json"
    projection = "graph/graphe_argumentatif.json"

    assert _reusable_graph_fields(ctx, store, registry, projection)
    store.schemas["argument_graph.schema.json"]["properties"]["nodes"]["items"]["properties"]["id"] = {"type": "boolean"}
    assert not _reusable_graph_fields(ctx, store, registry, projection)

    store = SchemaStore()
    store.schemas["argument_graph.schema.json"]["allOf"] = [{"required": ["nodes"]}]
    assert not _reusable_graph_fields(ctx, store, registry, projection)


def test_json_identity_never_confuses_bool_and_integer():
    assert not _json_identical({"x": [1]}, {"x": [True]})
    assert not _json_identical({"x": 1}, {"x": 1.0})
    assert _json_identical({"x": [1, {"a": "é"}]}, {"x": [1, {"a": "é"}]})


def test_noncanonical_graph_paths_keep_full_validation(tmp_path: Path):
    create_graph_package(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    registry_rel = "data/renamed_registry.json"
    graph_rel = "graph/renamed_graph.json"
    (tmp_path / registry_rel).write_bytes((tmp_path / "data/registre_debat.json").read_bytes())
    (tmp_path / graph_rel).write_bytes((tmp_path / "graph/graphe_argumentatif.json").read_bytes())
    manifest["core_files"]["registry"] = registry_rel
    manifest["core_files"]["graph_json"] = graph_rel
    dump(manifest_path, manifest)
    _report_comparison(tmp_path, False)
