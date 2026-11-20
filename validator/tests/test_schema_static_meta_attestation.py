"""Exact JSON Schema attestations may skip *only* redundant meta-validation.

All instance checks and error reports must be identical to the original
full check_schema path. New, mutated, unsupported schemas fail closed.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for

from wikidebia_validator import schema_validation as sv
from wikidebia_validator.validator import validate_package

from .helpers import create_graph_package, dump


def test_every_attested_schema_is_exact_and_meta_valid():
    store = sv.SchemaStore()
    assert sv._schema_fingerprint(store.schemas["common.schema.json"]) == sv._ATTESTED_COMMON_SHA256
    for name, fingerprint in sv._ATTESTED_SCHEMA_SHA256.items():
        schema = store.schemas[name]
        assert sv._schema_fingerprint(schema) == fingerprint, name
        # The immutable fingerprint is never accepted on faith by the CI:
        # independently check the real bundled schema against its metaschema.
        validator_for(schema).check_schema(schema)
    validator_for(store.schemas["common.schema.json"]).check_schema(
        store.schemas["common.schema.json"]
    )


def test_exact_attestation_reuses_meta_check_without_skipping_instance_errors():
    store = sv.SchemaStore()
    store._attested_runtime = True
    with patch.object(Draft202012Validator, "check_schema", side_effect=AssertionError("unexpected meta-check")):
        errors = store.validate("not an object", "scope.schema.json")
    assert errors and any(error.validator == "type" for error in errors)


def test_modified_schema_must_be_meta_checked_and_reject_malformed_syntax():
    store = sv.SchemaStore()
    store._attested_runtime = True
    store.validate({}, "scope.schema.json")
    store.schemas["scope.schema.json"]["properties"] = {"new": {"type": "invalid-type"}}
    with pytest.raises(SchemaError):
        store.validate({"new": True}, "scope.schema.json")


def test_modified_common_schema_forces_original_meta_check_even_if_root_unchanged():
    store = sv.SchemaStore()
    store._attested_runtime = True
    store.schemas["common.schema.json"]["new_property"] = {"type": "integer"}
    with patch.object(Draft202012Validator, "check_schema", side_effect=RuntimeError("must recheck")):
        with pytest.raises(RuntimeError, match="must recheck"):
            store.validate({}, "scope.schema.json")


def test_unattested_runtime_and_unknown_schema_still_use_original_meta_check():
    store = sv.SchemaStore()
    store._attested_runtime = False
    with patch.object(Draft202012Validator, "check_schema", side_effect=RuntimeError("older jsonschema")):
        with pytest.raises(RuntimeError, match="older jsonschema"):
            store.validate({}, "scope.schema.json")
    store = sv.SchemaStore()
    store._attested_runtime = True
    store.schemas["new.schema.json"] = {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}
    with patch.object(Draft202012Validator, "check_schema", side_effect=RuntimeError("new schema")):
        with pytest.raises(RuntimeError, match="new schema"):
            store.validate({}, "new.schema.json")


@pytest.mark.parametrize("mutation", ["unchanged", "invalid_registry_status", "invalid_graph_status"])
def test_complete_reports_match_original_meta_checks(tmp_path: Path, mutation: str):
    create_graph_package(tmp_path)
    registry = tmp_path / "data/registre_debat.json"
    graph = tmp_path / "graph/graphe_argumentatif.json"
    if mutation == "invalid_registry_status":
        doc = json.loads(registry.read_text(encoding="utf-8"))
        doc["graph"]["nodes"][0]["status"] = "NOT-A-STATUS"
        dump(registry, doc)
    elif mutation == "invalid_graph_status":
        doc = json.loads(graph.read_text(encoding="utf-8"))
        doc["nodes"][0]["status"] = "NOT-A-STATUS"
        dump(graph, doc)
    with patch.object(sv, "_matches_attested_library_versions", return_value=True):
        attested = validate_package(tmp_path, scopes=["schema"]).to_dict()
    with patch.object(sv, "_matches_attested_library_versions", return_value=False):
        complete = validate_package(tmp_path, scopes=["schema"]).to_dict()
    assert attested == complete
    if mutation != "unchanged":
        assert any(f["code"] == "WDV-SCH-003" for f in attested["findings"])
