"""Differential and mutation proofs for attested no-op status allOf clauses.

Every non-matching, present built-in string can make a no-else if/then clause
vacuously valid. This file proves that this shortcut never changes even nested
error paths, messages, contexts, file checks or complete package findings.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from jsonschema.validators import extend, validator_for
from jsonschema.exceptions import SchemaError

from wikidebia_validator import schema_validation as sv
from wikidebia_validator.validator import validate_package
from .helpers import create_graph_package, dump

REGISTRY = "argument_registry.schema.json"
COMMON = "common.schema.json"
SCOPES = ("schema", "coherence", "graph", "files", "workflow")
NODE = ("graph", "nodes", 0)
PAGE = (*NODE, "pages")
OCC = ("graph", "occurrences", 0)
DELETE = object()

STATUS_FIELDS = (
    (*PAGE, "fr", "generation", "status"),
    (*PAGE, "en", "generation", "status"),
    (*PAGE, "fr", "file", "status"),
    (*PAGE, "en", "file", "status"),
    (*PAGE, "fr", "wiki", "check_status"),
    (*PAGE, "en", "wiki", "check_status"),
    (*PAGE, "fr", "interlanguage", "status"),
    (*PAGE, "en", "interlanguage", "status"),
    (*NODE, "en", "title_status"),
    ("graph", "lifecycle", "status"),
    (*OCC, "occurrence_role"),
)
STATUS_VALUES = (
    "pending", "validated", "created", "unassigned", "secondary",
    "unexpected_status", "", None, True, 1, [], {}, DELETE,
)
THEN_FIELDS = (
    (*PAGE, "fr", "generation", "creation_date"),
    (*PAGE, "fr", "file", "sha256"),
    (*PAGE, "fr", "wiki", "checked_at"),
    (*PAGE, "en", "wiki", "remote_title"),
    (*PAGE, "fr", "interlanguage", "verified_at"),
    (*NODE, "en", "canonical_title"),
    (*OCC, "parent_occurrence_id"),
)


def _report(root: Path, *, enabled: bool) -> dict:
    # Preserve *every* earlier shortcut, disabling only the new allOf guard.
    with patch.object(sv, "_matches_attested_library_versions", return_value=True):
        if enabled:
            return validate_package(root, scopes=SCOPES).to_dict()
        with patch.object(
            sv, "_guarded_registry_false_status_allof",
            side_effect=lambda cls, _schema: cls,
        ):
            return validate_package(root, scopes=SCOPES).to_dict()


def _mutate(root: Path, key_path: tuple, value: object) -> None:
    file = root / "data/registre_debat.json"
    instance = json.loads(file.read_text(encoding="utf-8"))
    obj = instance
    for key in key_path[:-1]:
        obj = obj[key]
    if value is DELETE:
        obj.pop(key_path[-1], None)
    else:
        obj[key_path[-1]] = value
    dump(file, instance)


@pytest.mark.parametrize("path", STATUS_FIELDS)
@pytest.mark.parametrize("value", STATUS_VALUES)
def test_identical_full_reports_for_statuses_and_invalid_types(
    tmp_path: Path, path: tuple, value: object,
):
    create_graph_package(tmp_path)
    _mutate(tmp_path, path, value)
    assert _report(tmp_path, enabled=True) == _report(tmp_path, enabled=False)


@pytest.mark.parametrize("path", THEN_FIELDS)
@pytest.mark.parametrize("value", [True, None, "", [], {}, DELETE])
def test_identical_full_reports_for_violated_then_branches(
    tmp_path: Path, path: tuple, value: object,
):
    create_graph_package(tmp_path)
    _mutate(tmp_path, path, value)
    assert _report(tmp_path, enabled=True) == _report(tmp_path, enabled=False)


def test_original_valid_corpus_has_identical_complete_reports(tmp_path: Path):
    create_graph_package(tmp_path)
    assert _report(tmp_path, enabled=True) == _report(tmp_path, enabled=False)


def test_attested_allof_is_registry_only_and_does_not_mutate_schemas():
    store = sv.SchemaStore()
    store._attested_runtime = True
    originals = copy.deepcopy(store.schemas)
    store.validate({}, REGISTRY)
    compiled = store._compiled[REGISTRY][1]
    native = validator_for(store.schemas[REGISTRY])
    assert type(compiled).VALIDATORS["allOf"] is not native.VALIDATORS["allOf"]
    assert store.schemas == originals
    store.validate({}, "scope.schema.json")
    assert type(store._compiled["scope.schema.json"][1]) is validator_for(
        store.schemas["scope.schema.json"]
    )


def test_unsupported_rule_inventory_disables_new_handler_only():
    store = sv.SchemaStore()
    store._attested_runtime = True
    with patch.object(sv, "_ATTESTED_STATUS_ALLOF_FALSE_BRANCH_COUNT", 50):
        store.validate({}, REGISTRY)
    assert type(store._compiled[REGISTRY][1]).VALIDATORS["allOf"] is (
        validator_for(store.schemas[REGISTRY]).VALIDATORS["allOf"]
    )


@pytest.mark.parametrize("broken_proof", ("runtime", "registry", "common", "type_guard"))
def test_unattested_inputs_and_failed_prior_guard_keep_native_allof(broken_proof: str):
    store = sv.SchemaStore()
    store._attested_runtime = True
    store.validate({}, REGISTRY)
    original = store._compiled[REGISTRY][1]
    if broken_proof == "runtime":
        store._attested_runtime = False
    elif broken_proof == "registry":
        store.schemas[REGISTRY]["properties"]["graph"]["properties"]["nodes"]["type"] = "object"
    elif broken_proof == "common":
        store.schemas[COMMON]["$defs"]["nodeId"]["pattern"] = "^B[0-9]+$"
    else:
        store._compiled.pop(REGISTRY, None)
        with patch.object(
            sv, "_guarded_registry_primitive_type", side_effect=lambda cls, _schema: cls,
        ):
            store.validate({}, REGISTRY)
    if broken_proof != "type_guard":
        store.validate({}, REGISTRY)
    candidate = store._compiled[REGISTRY][1]
    assert candidate is not original
    assert type(candidate).VALIDATORS["allOf"] is (
        validator_for(store.schemas[REGISTRY]).VALIDATORS["allOf"]
    )


def test_invalid_metaschema_cannot_resurrect_compiled_allof_handler():
    store = sv.SchemaStore()
    store._attested_runtime = True
    store.validate({}, REGISTRY)
    store.schemas[REGISTRY]["properties"]["graph"]["properties"]["nodes"]["type"] = "INVALID"
    with pytest.raises(SchemaError):
        store.validate({}, REGISTRY)
    assert REGISTRY not in store._compiled


def test_unproven_nested_schema_or_unknown_rule_shape_never_activates():
    cls = validator_for({"$schema": "https://json-schema.org/draft/2020-12/schema"})
    for expanded in (
        None, {}, True, [],
        {"allOf": [{"if": {"properties": {"status": {"const": "pending"}}}}]},
        {"allOf": [{"if": {"properties": {"status": {"const": "pending"}}},
                    "then": {}, "else": {}}]},
        {"allOf": [{"if": {"properties": {"status": {"enum": [True, "pending"]}}},
                    "then": {}}]},
        {"allOf": [{"if": {"properties": {"depth": {"const": 1}}},
                    "then": {}}]},
    ):
        assert sv._guarded_registry_false_status_allof(cls, expanded) is cls


def _errors(validator, instance) -> list:
    return [
        (
            list(err.absolute_path),
            list(err.absolute_schema_path),
            err.validator, err.message,
            [
                (list(child.absolute_path), list(child.absolute_schema_path),
                 child.validator, child.message)
                for child in err.context
            ],
        )
        for err in validator.iter_errors(instance)
    ]


def _allof_validators():
    store = sv.SchemaStore()
    store._attested_runtime = True
    store.validate({}, REGISTRY)
    compiled = store._compiled[REGISTRY][1]
    # This is one of the *actual* eligible lists in the compiled registry.
    clauses = (
        compiled.schema["properties"]["graph"]["properties"]["nodes"]
        ["items"]["properties"]["pages"]["properties"]["fr"]
        ["properties"]["wiki"]["allOf"]
    )
    schema = {"allOf": clauses}
    native = validator_for(store.schemas[REGISTRY])(
        schema, registry=store.registry, format_checker=store.format_checker,
    )
    optimized = type(compiled)(
        schema, registry=store.registry, format_checker=store.format_checker,
    )
    return store, clauses, native, optimized


@pytest.mark.parametrize(
    "instance",
    (
        {"check_status": "unchecked"},
        {"check_status": "created"},
        {"check_status": "equivalent_existing"},
        {"check_status": "future_status"},
        {"check_status": ""},
        {"check_status": None},
        {"check_status": True},
        {"check_status": 1},
        {},
        [],
        "unexpected",
        None,
        {"check_status": "created", "remote_revision_id": 0, "checked_at": False},
    ),
)
def test_allof_schema_path_and_nested_error_contexts_are_exact(instance):
    _, _, native, optimized = _allof_validators()
    assert _errors(optimized, instance) == _errors(native, instance)


@pytest.mark.parametrize("mutation", (
    "different_const", "new_else", "empty_properties", "add_if_keyword",
    "new_condition", "then_invalid", "other_clause", "replace_list",
))
def test_compiled_attested_clause_mutations_preserve_native_diagnostics(mutation: str):
    store, clauses, native, optimized = _allof_validators()
    if mutation == "different_const":
        clauses[0]["if"]["properties"]["check_status"]["const"] = "future_status"
    elif mutation == "new_else":
        clauses[0]["else"] = {"type": "string"}
    elif mutation == "empty_properties":
        clauses[0]["if"]["properties"] = {}
    elif mutation == "add_if_keyword":
        clauses[0]["if"]["required"] = ["remote_title"]
    elif mutation == "new_condition":
        clauses[0]["if"] = {"const": {"check_status": "unchecked"}}
    elif mutation == "then_invalid":
        clauses[0]["then"] = {"type": "number"}
    elif mutation == "other_clause":
        clauses.append({"type": "number"})
    else:
        clauses[:] = [{"const": {"check_status": "created"}}]
    for instance in (
        {"check_status": "unchecked"},
        {"check_status": "created"},
        {"check_status": "future_status"},
        {"check_status": "other", "remote_title": None},
        {"check_status": None},
        {},
    ):
        assert _errors(optimized, instance) == _errors(native, instance)


def test_subclass_and_modified_condition_keyword_implementations_cannot_be_skipped():
    store, clauses, native, optimized = _allof_validators()
    compiled_cls = type(optimized)
    native_allof = validator_for(store.schemas[REGISTRY]).VALIDATORS["allOf"]

    def altered_const(validator, value, instance, schema):
        # Make every const succeed; a fast skip based on ordinary const values
        # would incorrectly miss failing 'then' checks on unknown statuses.
        if False:
            yield

    override_cls = extend(compiled_cls, validators={
        "const": altered_const,
        "allOf": native_allof,
    })
    custom_cls = extend(compiled_cls, validators={"const": altered_const})
    for instance in (
        {"check_status": "future_status", "checked_at": False},
        {"check_status": "unchecked", "checked_at": False},
    ):
        assert _errors(
            custom_cls({"allOf": clauses}, registry=store.registry),
            instance,
        ) == _errors(
            override_cls({"allOf": clauses}, registry=store.registry),
            instance,
        )
    # In-place mutation of the compiled class' keyword dict must also be
    # caught, even though type(validator) remains *exactly* the attested class.
    with patch.dict(compiled_cls.VALIDATORS, {"const": altered_const}):
        for instance in (
            {"check_status": "future_status", "checked_at": False},
            {"check_status": "unchecked", "checked_at": False},
        ):
            assert _errors(optimized, instance) == _errors(
                override_cls({"allOf": clauses}, registry=store.registry),
                instance,
            )
