"""Bounded static common-ref expansion preserves every instance-validation report."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for

from wikidebia_validator import schema_validation as sv
from wikidebia_validator.validator import validate_package
from .helpers import create_graph_package, dump


REGISTRY = "argument_registry.schema.json"
COMMON = "common.schema.json"


def _report(root: Path, *, attested: bool) -> dict:
    with patch.object(sv, "_matches_attested_library_versions", return_value=attested):
        return validate_package(root, scopes=["schema"]).to_dict()


def test_attested_common_ref_expansion_is_meta_valid_and_never_edits_source():
    store = sv.SchemaStore()
    before = copy.deepcopy(store.schemas)
    original = store.schemas[REGISTRY]
    expanded = sv._inline_attested_common_references(
        original, store.schemas[COMMON]
    )
    validator_for(expanded).check_schema(expanded)
    assert store.schemas == before
    assert expanded is not original
    assert expanded["properties"]["graph"] == original["properties"]["graph"] or (
        # External graph refs are now expanded, but the field shape remains.
        expanded["properties"]["graph"]["type"] == "object"
    )

    def count_common_refs(value):
        if isinstance(value, dict):
            return int(str(value.get("$ref", "")).startswith("common.schema.json#/$defs/")) + sum(
                count_common_refs(item) for item in value.values()
            )
        if isinstance(value, list):
            return sum(count_common_refs(item) for item in value)
        return 0

    assert count_common_refs(original) > 0
    assert count_common_refs(expanded) == 0


def test_registry_uses_inlined_schema_only_on_exact_attested_source():
    store = sv.SchemaStore()
    store._attested_runtime = True
    store.validate({}, REGISTRY)
    assert store._inlined_registry_common_sha256 == sv._ATTESTED_COMMON_SHA256
    validator = store._compiled[REGISTRY][1]
    assert validator.schema is not store.schemas[REGISTRY]
    assert validator.schema["properties"]["graph"] is not store.schemas[REGISTRY]["properties"]["graph"]


def test_common_mutation_invalidates_inlined_compilation_and_uses_original_schema():
    store = sv.SchemaStore()
    store._attested_runtime = True
    store.validate({}, REGISTRY)
    old = store._compiled[REGISTRY][1]
    store.schemas[COMMON]["$defs"]["nodeId"]["pattern"] = "^B[0-9]{4,}$"
    store.validate({}, REGISTRY)
    assert store._inlined_registry_common_sha256 is None
    assert store._compiled[REGISTRY][1] is not old
    assert store._compiled[REGISTRY][1].schema is store.schemas[REGISTRY]


def test_runtime_attestation_revoked_after_compilation_discards_inlined_snapshot():
    store = sv.SchemaStore()
    store._attested_runtime = True
    store.validate({}, REGISTRY)
    old = store._compiled[REGISTRY][1]
    store._attested_runtime = False
    store.validate({}, REGISTRY)
    assert store._inlined_registry_common_sha256 is None
    assert store._compiled[REGISTRY][1] is not old
    assert store._compiled[REGISTRY][1].schema is store.schemas[REGISTRY]


def test_changed_registry_schema_is_not_inlined_and_gets_meta_checked():
    store = sv.SchemaStore()
    store._attested_runtime = True
    store.validate({}, REGISTRY)
    store.schemas[REGISTRY]["properties"]["graph"]["properties"]["nodes"]["type"] = "invalid-json-type"
    with pytest.raises(SchemaError):
        store.validate({}, REGISTRY)
    assert store._inlined_registry_common_sha256 is None
    assert REGISTRY not in store._compiled
    # Even if the original registry schema is restored, a subsequent
    # common-definition change must never resurrect a stale optimized copy.
    store.schemas[REGISTRY]["properties"]["graph"]["properties"]["nodes"]["type"] = "array"
    store.schemas[COMMON]["$defs"]["nodeId"]["pattern"] = "^B[0-9]{4,}$"
    store.validate({}, REGISTRY)
    assert store._compiled[REGISTRY][1].schema is store.schemas[REGISTRY]


def test_unattested_new_store_keeps_original_validator_schema():
    store = sv.SchemaStore()
    store._attested_runtime = False
    store.validate({}, REGISTRY)
    assert store._compiled[REGISTRY][1].schema is store.schemas[REGISTRY]
    assert store._inlined_registry_common_sha256 is None


@pytest.mark.parametrize("unsafe", [
    "unknown_definition", "cyclic_definition", "dynamic_anchor",
    "local_ref_with_siblings", "schema_id", "foreign_ref",
])
def test_unproven_common_ref_expansion_fails_closed(unsafe):
    schema = {"properties": {"x": {"$ref": "common.schema.json#/$defs/special"}}}
    common = {"$defs": {"special": {"type": "string"}}}
    if unsafe == "unknown_definition":
        schema["properties"]["x"]["$ref"] += "UNKNOWN"
    elif unsafe == "cyclic_definition":
        common["$defs"]["special"] = {"$ref": "#/$defs/special"}
    elif unsafe == "dynamic_anchor":
        common["$defs"]["special"]["$dynamicAnchor"] = "needle"
    elif unsafe == "local_ref_with_siblings":
        common["$defs"]["special"] = {"$ref": "#/$defs/other", "type": "string"}
        common["$defs"]["other"] = {"type": "string"}
    elif unsafe == "schema_id":
        common["$defs"]["special"]["$id"] = "different.schema.json"
    elif unsafe == "foreign_ref":
        common["$defs"]["special"] = {"$ref": "another.schema.json"}
    with pytest.raises(sv._UnsafeCommonReference):
        sv._inline_attested_common_references(schema, common)


@pytest.mark.parametrize("mutation", [
    "valid", "bad_node_id", "bad_node_status", "bad_fr_title",
    "bad_rubric_count", "duplicate_keywords", "bad_english_status",
    "bad_page_revision", "bad_occurrence_node", "unexpected_french_key",
    "missing_required", "lifecycle_locked_without_date",
    "invalid_nested_json_type",
])
def test_full_schema_report_matches_unchanged_validator(tmp_path: Path, mutation: str):
    create_graph_package(tmp_path)
    if mutation != "valid":
        path = tmp_path / "data/registre_debat.json"
        registry = json.loads(path.read_text(encoding="utf-8"))
        graph = registry["graph"]
        node = graph["nodes"][0]
        if mutation == "bad_node_id":
            node["id"] = 12
        elif mutation == "bad_node_status":
            node["status"] = "INVALID"
        elif mutation == "bad_fr_title":
            node["fr"]["canonical_title"] = " "
        elif mutation == "bad_rubric_count":
            node["fr"]["rubriques"] = ["Science"] * 5
        elif mutation == "duplicate_keywords":
            node["fr"]["keywords"] = ["double", "double"]
        elif mutation == "bad_english_status":
            node["en"]["title_status"] = "locked"
        elif mutation == "bad_page_revision":
            node["pages"]["fr"]["wiki"]["remote_revision_id"] = True
        elif mutation == "bad_occurrence_node":
            graph["occurrences"][0]["node_id"] = None
        elif mutation == "unexpected_french_key":
            node["fr"]["extra"] = 1
        elif mutation == "missing_required":
            del node["fr"]["canonical_title"]
        elif mutation == "lifecycle_locked_without_date":
            graph["lifecycle"]["locked_at"] = None
        elif mutation == "invalid_nested_json_type":
            node["pages"]["en"]["file"]["sha256"] = {}
        dump(path, registry)
    fast = _report(tmp_path, attested=True)
    reference = _report(tmp_path, attested=False)
    assert fast == reference
    if mutation != "valid":
        assert any(f["code"] == "WDV-SCH-003" for f in fast["findings"])
