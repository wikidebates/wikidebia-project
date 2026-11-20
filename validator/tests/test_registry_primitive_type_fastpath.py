"""Prove exact JSON Schema type/error behavior with the attested positive path.

Only *successes* for exact builtin primitive types are shortened in the
attested registry. All incorrect types and altered type-checkers still use
the original jsonschema handler, preserving every finding and error context.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from jsonschema.exceptions import SchemaError
from jsonschema.validators import extend, validator_for

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

# Each mutation preserves the outer package but can make a field invalid.
# Test type acceptance, diagnostic contexts, and the native fallback for
# missing/null/bool/str/list/dict/float/int values.
PATHS = (
    (*NODE, "id"),
    (*NODE, "status"),
    (*NODE, "fr"),
    (*NODE, "fr", "canonical_title"),
    (*NODE, "fr", "rubriques"),
    (*NODE, "fr", "keywords"),
    (*NODE, "en"),
    (*NODE, "en", "canonical_title"),
    (*PAGE, "fr", "generation", "status"),
    (*PAGE, "fr", "file", "status"),
    (*PAGE, "fr", "wiki", "check_status"),
    (*OCC, "depth"),
    (*OCC, "render_children"),
)
VALUES = (
    None,
    True,
    1,
    1.0,
    "",
    "valid string",
    [],
    {},
    DELETE,
)


def _report(root: Path, *, optimized: bool) -> dict:
    with patch.object(sv, "_matches_attested_library_versions", return_value=True):
        if optimized:
            return validate_package(root, scopes=list(SCOPES)).to_dict()
        with patch.object(
            sv, "_guarded_registry_primitive_type",
            side_effect=lambda cls, _expanded: cls,
        ):
            return validate_package(root, scopes=list(SCOPES)).to_dict()


def _replace(root: Path, keys: tuple, value: object) -> None:
    path = root / "data/registre_debat.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    target = doc
    for key in keys[:-1]:
        target = target[key]
    if value is DELETE:
        target.pop(keys[-1], None)
    else:
        target[keys[-1]] = value
    dump(path, doc)


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("value", VALUES)
def test_full_report_preserved_for_builtins_and_invalid_fields(
    tmp_path: Path, path: tuple, value: object,
):
    create_graph_package(tmp_path)
    _replace(tmp_path, path, value)
    assert _report(tmp_path, optimized=True) == _report(tmp_path, optimized=False)


def test_valid_graph_report_unchanged(tmp_path: Path):
    create_graph_package(tmp_path)
    assert _report(tmp_path, optimized=True) == _report(tmp_path, optimized=False)


def test_exact_attestation_activates_primitive_shortcut_without_touching_sources():
    store = sv.SchemaStore()
    store._attested_runtime = True
    before = copy.deepcopy(store.schemas)
    store.validate({}, REGISTRY)
    cls = type(store._compiled[REGISTRY][1])
    native = validator_for(store.schemas[REGISTRY])
    assert cls is not native
    assert cls.VALIDATORS["type"] is not native.VALIDATORS["type"]
    assert store.schemas == before
    assert store._inlined_registry_common_sha256 == sv._ATTESTED_COMMON_SHA256
    store.validate({}, "scope.schema.json")
    assert type(store._compiled["scope.schema.json"][1]) is validator_for(
        store.schemas["scope.schema.json"]
    )


@pytest.mark.parametrize("which", ["oneof", "conditional", "type"])
def test_fast_type_never_survives_a_failed_prior_proof(which: str):
    store = sv.SchemaStore()
    store._attested_runtime = True
    if which == "oneof":
        field, value = "_ATTESTED_NULLABLE_STRING_ONEOF_COUNT", 24
    elif which == "conditional":
        field, value = "_ATTESTED_REGISTRY_STATUS_IF_COUNT", 50
    else:
        field, value = "_ATTESTED_REGISTRY_PRIMITIVE_TYPE_COUNT", 335
    with patch.object(sv, field, value):
        store.validate({}, REGISTRY)
    cls = type(store._compiled[REGISTRY][1])
    assert cls.VALIDATORS["type"] is validator_for(
        store.schemas[REGISTRY]
    ).VALIDATORS["type"]
    if which == "oneof":
        assert cls is validator_for(store.schemas[REGISTRY])


@pytest.mark.parametrize("source_change", ["registry", "common", "runtime"])
def test_source_or_library_change_reverts_to_native_type(source_change: str):
    store = sv.SchemaStore()
    store._attested_runtime = True
    store.validate({}, REGISTRY)
    previous = store._compiled[REGISTRY][1]
    if source_change == "registry":
        store.schemas[REGISTRY]["properties"]["graph"]["properties"]["nodes"]["type"] = "object"
        store.schemas[REGISTRY]["properties"]["graph"]["properties"]["nodes"]["maxItems"] = 5
    elif source_change == "common":
        store.schemas[COMMON]["$defs"]["nodeId"]["pattern"] = "^B[0-9]+$"
    else:
        store._attested_runtime = False
    store.validate({}, REGISTRY)
    current = store._compiled[REGISTRY][1]
    assert current is not previous
    assert current.schema is store.schemas[REGISTRY]
    assert type(current).VALIDATORS["type"] is validator_for(
        store.schemas[REGISTRY]
    ).VALIDATORS["type"]


def test_bad_schema_fails_metaschema_and_never_resurrects_stale_validator():
    store = sv.SchemaStore()
    store._attested_runtime = True
    store.validate({}, REGISTRY)
    store.schemas[REGISTRY]["properties"]["graph"]["properties"]["nodes"]["type"] = "invalid-type"
    with pytest.raises(SchemaError):
        store.validate({}, REGISTRY)
    assert REGISTRY not in store._compiled


def test_unproven_nested_or_unknown_schema_shape_cannot_activate_type_handler():
    cls = validator_for({"$schema": "https://json-schema.org/draft/2020-12/schema"})
    for schema in (
        True, {}, {"type": "string"}, {"type": ["string", "null"]},
        {"allOf": [{"type": "integer"}]},
    ):
        assert sv._guarded_registry_primitive_type(cls, schema) is cls


def _errors(validator, value):
    return [
        (
            list(e.path), list(e.schema_path), e.message, e.validator,
            [(list(c.path), list(c.schema_path), c.message) for c in e.context],
        )
        for e in validator.iter_errors(value)
    ]


def test_compiled_subschema_mutation_reverts_to_native_keyword_diagnostics():
    store = sv.SchemaStore()
    store._attested_runtime = True
    store.validate({}, REGISTRY)
    compiled = store._compiled[REGISTRY][1]
    schema = (
        compiled.schema["properties"]["graph"]["properties"]["nodes"]
        ["items"]["properties"]["fr"]["properties"]["canonical_title"]
    )
    assert schema.get("type") == "string"
    schema["type"] = "integer"  # identity is unchanged but the original rule is no longer attested
    native = validator_for(store.schemas[REGISTRY])(
        schema, registry=store.registry, format_checker=store.format_checker,
    )
    candidate = type(compiled)(
        schema, registry=store.registry, format_checker=store.format_checker,
    )
    for value in (None, 1, 1.0, "string", "", True, {}, [], 0):
        assert _errors(native, value) == _errors(candidate, value)


def test_custom_typechecker_is_never_bypassed_even_for_builtin_values():
    store = sv.SchemaStore()
    store._attested_runtime = True
    store.validate({}, REGISTRY)
    compiled = store._compiled[REGISTRY][1]
    schema = (
        compiled.schema["properties"]["graph"]["properties"]["nodes"]
        ["items"]["properties"]["fr"]["properties"]["canonical_title"]
    )
    # Reject strings in the custom checker rather than pretending integers
    # are strings: minLength/regex must never be fed integers by the test.
    checker = type(compiled).TYPE_CHECKER.redefine(
        "string", lambda _checker, instance: False,
    )
    custom_guard = extend(type(compiled), type_checker=checker)
    native = extend(validator_for(store.schemas[REGISTRY]), type_checker=checker)
    baseline = native(schema, registry=store.registry, format_checker=store.format_checker)
    candidate = custom_guard(schema, registry=store.registry, format_checker=store.format_checker)
    for value in ("normal string", 1, None, True, 1.5):
        assert _errors(baseline, value) == _errors(candidate, value)


@pytest.mark.parametrize("kind,value", [
    ("string", "s"), ("object", {}), ("array", []), ("boolean", True),
    ("null", None), ("integer", 12), ("integer", True), ("integer", 12.0),
    ("string", None), ("array", {}), ("object", []), ("null", False),
])
def test_builtin_type_keyword_exact_context(kind: str, value: object):
    # Compare the public keyword's full error objects in isolation, even for
    # values such as True (which is a subclass of int in Python).
    store = sv.SchemaStore()
    store._attested_runtime = True
    store.validate({}, REGISTRY)
    native_cls = validator_for(store.schemas[REGISTRY])
    guarded_cls = type(store._compiled[REGISTRY][1])
    # This standalone schema is not one of the attested object identities,
    # so it MUST be validated entirely by the native keyword.
    doc = {"type": kind}
    original = native_cls(doc, registry=store.registry, format_checker=store.format_checker)
    accelerated = guarded_cls(doc, registry=store.registry, format_checker=store.format_checker)
    assert _errors(original, value) == _errors(accelerated, value)


def test_string_subclasses_and_custom_instances_fall_back_to_native():
    class FancyString(str):
        pass
    class FancyDict(dict):
        pass

    store = sv.SchemaStore()
    store._attested_runtime = True
    store.validate({}, REGISTRY)
    compiled = store._compiled[REGISTRY][1]
    schema = (
        compiled.schema["properties"]["graph"]["properties"]["nodes"]
        ["items"]["properties"]["fr"]["properties"]["canonical_title"]
    )
    native = validator_for(store.schemas[REGISTRY])(
        schema, registry=store.registry, format_checker=store.format_checker,
    )
    optimized = type(compiled)(
        schema, registry=store.registry, format_checker=store.format_checker,
    )
    for value in (FancyString("hello"), FancyDict(), 2.0):
        assert _errors(native, value) == _errors(optimized, value)
