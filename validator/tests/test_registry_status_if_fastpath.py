"""Exact-report tests for attested string-status JSON Schema conditional shortcuts.

The optimized schema retains every original branch. A present status string
can choose a branch directly; every other value uses the native if handler.
"""
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
SCOPES = ["schema", "coherence", "graph", "files", "workflow"]
DELETE = object()
NODE = ("graph", "nodes", 0)
PAGE = (*NODE, "pages")
OCC = ("graph", "occurrences", 0)

STATUS_PATHS = (
    (*PAGE, "fr", "generation", "status"),
    (*PAGE, "en", "generation", "status"),
    (*PAGE, "fr", "file", "status"),
    (*PAGE, "en", "file", "status"),
    (*PAGE, "fr", "wiki", "check_status"),
    (*PAGE, "en", "wiki", "check_status"),
    (*PAGE, "fr", "interlanguage", "status"),
    (*NODE, "en", "title_status"),
    ("graph", "lifecycle", "status"),
    (*OCC, "occurrence_role"),
)
STATUSES = (
    "pending", "created", "validated", "unassigned",
    "unexpected", "", None, True, 12, DELETE,
)
SECONDARY_PATHS = (
    (*PAGE, "fr", "generation", "creation_date"),
    (*PAGE, "fr", "file", "sha256"),
    (*PAGE, "fr", "wiki", "checked_at"),
    (*PAGE, "fr", "interlanguage", "verified_at"),
    (*NODE, "en", "canonical_title"),
    (*OCC, "depth"),
    (*OCC, "parent_occurrence_id"),
)
SECONDARY_VALUES = (True, "", None)


def _report(root: Path, *, enabled: bool) -> dict:
    # Both variants retain #178, #179 and #185, including the same original
    # schemas, exact attestations and nullable-oneOf optimization.
    with patch.object(sv, "_matches_attested_library_versions", return_value=True):
        if enabled:
            return validate_package(root, scopes=SCOPES).to_dict()
        with patch.object(
            sv, "_guarded_registry_status_if",
            side_effect=lambda cls, _schema: cls,
        ):
            return validate_package(root, scopes=SCOPES).to_dict()


def _mutate(root: Path, path: tuple, value: object) -> None:
    rel = root / "data/registre_debat.json"
    registry = json.loads(rel.read_text(encoding="utf-8"))
    target = registry
    for part in path[:-1]:
        target = target[part]
    if value is DELETE:
        target.pop(path[-1], None)
    else:
        target[path[-1]] = value
    dump(rel, registry)


@pytest.mark.parametrize("path", STATUS_PATHS)
@pytest.mark.parametrize("replacement", STATUSES)
def test_full_report_for_status_and_invalid_types_is_identical(
    tmp_path: Path, path: tuple, replacement: object,
):
    create_graph_package(tmp_path)
    _mutate(tmp_path, path, replacement)
    assert _report(tmp_path, enabled=True) == _report(tmp_path, enabled=False)


@pytest.mark.parametrize("path", SECONDARY_PATHS)
@pytest.mark.parametrize("replacement", SECONDARY_VALUES)
def test_full_report_for_invalid_then_payload_is_identical(
    tmp_path: Path, path: tuple, replacement: object,
):
    create_graph_package(tmp_path)
    _mutate(tmp_path, path, replacement)
    assert _report(tmp_path, enabled=True) == _report(tmp_path, enabled=False)


def test_original_valid_corpus_report_is_unchanged(tmp_path: Path):
    create_graph_package(tmp_path)
    assert _report(tmp_path, enabled=True) == _report(tmp_path, enabled=False)


def test_guard_is_attested_registry_only_and_preserves_canonical_schema():
    store = sv.SchemaStore()
    store._attested_runtime = True
    originals = copy.deepcopy(store.schemas)
    store.validate({}, REGISTRY)
    cls = type(store._compiled[REGISTRY][1])
    native = validator_for(store.schemas[REGISTRY])
    assert cls is not native
    assert cls.VALIDATORS["if"] is not native.VALIDATORS["if"]
    assert store._inlined_registry_common_sha256 == sv._ATTESTED_COMMON_SHA256
    assert store.schemas == originals
    store.validate({}, "scope.schema.json")
    assert type(store._compiled["scope.schema.json"][1]) is validator_for(
        store.schemas["scope.schema.json"]
    )


def test_wrong_attested_count_disables_only_conditional_guard():
    store = sv.SchemaStore()
    store._attested_runtime = True
    with patch.object(sv, "_ATTESTED_REGISTRY_STATUS_IF_COUNT", 50):
        store.validate({}, REGISTRY)
    assert type(store._compiled[REGISTRY][1]).VALIDATORS["if"] is validator_for(
        store.schemas[REGISTRY]
    ).VALIDATORS["if"]


@pytest.mark.parametrize("changed", ["registry", "common", "runtime"])
def test_mutated_schema_or_runtime_reverts_to_native_handler(changed: str):
    store = sv.SchemaStore()
    store._attested_runtime = True
    store.validate({}, REGISTRY)
    old = store._compiled[REGISTRY][1]
    if changed == "registry":
        store.schemas[REGISTRY]["properties"]["graph"]["properties"]["nodes"]["type"] = "object"
    elif changed == "common":
        store.schemas[COMMON]["$defs"]["nodeId"]["pattern"] = "^B[0-9]+$"
    else:
        store._attested_runtime = False
    store.validate({}, REGISTRY)
    new = store._compiled[REGISTRY][1]
    assert old is not new
    assert new.schema is store.schemas[REGISTRY]
    assert type(new).VALIDATORS["if"] is validator_for(
        store.schemas[REGISTRY]
    ).VALIDATORS["if"]


def test_bad_schema_still_requires_meta_validation_and_clears_cache():
    store = sv.SchemaStore()
    store._attested_runtime = True
    store.validate({}, REGISTRY)
    store.schemas[REGISTRY]["properties"]["graph"]["properties"]["nodes"]["type"] = "invalid-json-type"
    with pytest.raises(SchemaError):
        store.validate({}, REGISTRY)
    assert REGISTRY not in store._compiled


def test_unproven_or_incomplete_rule_set_uses_original_keyword():
    cls = validator_for({"$schema": "https://json-schema.org/draft/2020-12/schema"})
    for expanded in (
        True, {}, {"if": {"properties": {"status": {"const": "pending"}}}},
        {"allOf": [{"if": {"properties": {"status": {"pattern": "x"}}}}]},
        {"allOf": [{"if": {"properties": {"status": {"enum": [1, True]}}}}]},
    ):
        assert sv._guarded_registry_status_if(cls, expanded) is cls


def _details(validator, instance):
    return [
        (
            list(err.path), list(err.schema_path), err.message, err.validator,
            [(list(child.path), list(child.schema_path), child.message) for child in err.context],
        )
        for err in validator.iter_errors(instance)
    ]


def test_compiled_if_mutation_does_not_preserve_unsafe_fast_path():
    store = sv.SchemaStore()
    store._attested_runtime = True
    store.validate({}, REGISTRY)
    compiled = store._compiled[REGISTRY][1]
    clause = (
        compiled.schema["properties"]["graph"]["properties"]["nodes"]
        ["items"]["properties"]["en"]["allOf"][0]
    )
    # Alter the expanded compiled schema, preserving the object's identity:
    # the stored proof must not cause a stale fast-path to be reused.
    clause["if"]["properties"]["title_status"]["const"] = "future_status"
    native_cls = validator_for(store.schemas[REGISTRY])
    baseline = native_cls(clause, registry=store.registry, format_checker=store.format_checker)
    candidate = type(compiled)(clause, registry=store.registry, format_checker=store.format_checker)
    for instance in (
        {"title_status": "future_status", "canonical_title": "x", "displayed_title": "x", "sections": [], "keywords": []},
        {"title_status": "unassigned", "canonical_title": "x", "displayed_title": "x", "sections": [], "keywords": []},
        {"title_status": True}, {"title_status": None}, {}, [], "not-an-object",
    ):
        assert _details(candidate, instance) == _details(baseline, instance)


def test_else_branch_for_numeric_depth_retains_original_error_context():
    store = sv.SchemaStore()
    store._attested_runtime = True
    store.validate({}, REGISTRY)
    compiled = store._compiled[REGISTRY][1]
    clause = (
        compiled.schema["properties"]["graph"]["properties"]["occurrences"]
        ["items"]["allOf"][0]
    )
    native_cls = validator_for(store.schemas[REGISTRY])
    baseline = native_cls(clause, registry=store.registry, format_checker=store.format_checker)
    candidate = type(compiled)(clause, registry=store.registry, format_checker=store.format_checker)
    for instance in (
        {"depth": 1, "parent_occurrence_id": None},
        {"depth": 2, "parent_occurrence_id": "BAD"},
        {"depth": True}, {"depth": None}, {}, 5,
    ):
        assert _details(candidate, instance) == _details(baseline, instance)
