"""Guarded null-or-string JSON Schema optimization: exhaustive report parity.

The production JSON schemas are never rewritten. A speedup is eligible only
under exact attested schema, common-schema and library versions. On malformed
input the custom keyword delegates to the library's original implementation.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from jsonschema.validators import validator_for
from jsonschema.exceptions import SchemaError

from wikidebia_validator import schema_validation as sv
from wikidebia_validator.validator import validate_package
from .helpers import create_graph_package, dump


REGISTRY = "argument_registry.schema.json"
COMMON = "common.schema.json"


def _compare_reports(root: Path) -> tuple[dict, dict]:
    # Both variants have the SAME attested meta-check and common-ref expansion.
    # This isolates the fast keyword dispatch rather than comparing unlike
    # package validation configurations.
    with patch.object(sv, "_matches_attested_library_versions", return_value=True):
        accelerated = validate_package(root, scopes=["schema", "coherence", "graph", "files", "workflow"]).to_dict()
        with patch.object(
            sv, "_guarded_registry_nullable_oneof",
            side_effect=lambda cls, _expanded: cls,
        ):
            original = validate_package(root, scopes=["schema", "coherence", "graph", "files", "workflow"]).to_dict()
    assert accelerated == original
    return accelerated, original


def test_fast_guard_is_active_only_for_attested_registry_and_preserves_schema_objects():
    store = sv.SchemaStore()
    store._attested_runtime = True
    original_schemas = copy.deepcopy(store.schemas)
    store.validate({}, REGISTRY)
    compiled = store._compiled[REGISTRY][1]
    assert store._inlined_registry_common_sha256 == sv._ATTESTED_COMMON_SHA256
    assert type(compiled) is not validator_for(store.schemas[REGISTRY])
    assert compiled.schema is not store.schemas[REGISTRY]
    assert store.schemas == original_schemas

    # A completely separate schema or a copied/altered common schema never
    # inherits the fast keyword handler.
    store.validate({}, "scope.schema.json")
    assert type(store._compiled["scope.schema.json"][1]) is validator_for(
        store.schemas["scope.schema.json"]
    )


def test_unexpected_expansion_shape_falls_back_to_original_library_validator():
    with patch.object(sv, "_ATTESTED_NULLABLE_STRING_ONEOF_COUNT", 24):
        store = sv.SchemaStore()
        store._attested_runtime = True
        store.validate({}, REGISTRY)
    assert type(store._compiled[REGISTRY][1]) is validator_for(store.schemas[REGISTRY])


def test_schema_or_library_change_reverts_all_nullable_fast_paths():
    for kind in ("common", "registry", "runtime"):
        store = sv.SchemaStore()
        store._attested_runtime = True
        store.validate({}, REGISTRY)
        compiled = store._compiled[REGISTRY][1]
        assert type(compiled) is not validator_for(store.schemas[REGISTRY])
        if kind == "common":
            store.schemas[COMMON]["$defs"]["nodeId"]["pattern"] = "^X[0-9]+$"
        elif kind == "registry":
            store.schemas[REGISTRY]["properties"]["graph"]["properties"]["nodes"]["type"] = "object"
        else:
            store._attested_runtime = False
        store.validate({}, REGISTRY)
        changed = store._compiled[REGISTRY][1]
        assert changed is not compiled
        assert type(changed) is validator_for(store.schemas[REGISTRY])


def test_bad_mutated_schema_still_raises_schemaerror_without_stale_compilation():
    store = sv.SchemaStore()
    store._attested_runtime = True
    store.validate({}, REGISTRY)
    store.schemas[REGISTRY]["properties"]["graph"]["properties"]["nodes"]["type"] = "forbidden-schema-type"
    with pytest.raises(SchemaError):
        store.validate({}, REGISTRY)
    assert REGISTRY not in store._compiled


def test_direct_nullable_oneof_native_error_context_and_guarded_error_match():
    store = sv.SchemaStore()
    store._attested_runtime = True
    store.validate({}, REGISTRY)
    compiled = store._compiled[REGISTRY][1]
    nullable = compiled.schema["properties"]["graph"]["properties"]["nodes"]["items"]["properties"]["en"]["properties"]["canonical_title"]
    assert set(nullable) == {"oneOf"}
    assert len(nullable["oneOf"]) == 2

    def findings(v, value):
        return [
            (
                list(e.absolute_path),
                list(e.absolute_schema_path),
                e.message,
                [(list(child.path), list(child.schema_path), child.message) for child in e.context],
            )
            for e in v.iter_errors(value)
        ]

    native_cls = validator_for(store.schemas[REGISTRY])
    native = native_cls(nullable, registry=store.registry, format_checker=store.format_checker)
    guarded = type(compiled)(nullable, registry=store.registry, format_checker=store.format_checker)

    # The isolated nullable schema is not in the compiled registry's
    # attested object-id set; it follows the original library method.
    for value in (None, "Titre correct", "", " ", 17, True, [], {}, ["a"]):
        assert findings(guarded, value) == findings(native, value)


@pytest.mark.parametrize("mutation", [
    "valid",
    "null_en_title",
    "valid_en_title",
    "empty_en_title",
    "spaces_en_title",
    "wrong_en_title_type",
    "en_displayed_title_bad",
    "bad_fr_title",
    "invalid_rubriques",
    "too_many_rubriques",
    "duplicate_keywords",
    "invalid_english_status",
    "unknown_node_property",
    "missing_node_required",
    "bad_node_id",
    "bad_occurrence_id",
    "bad_generation_status",
    "generation_validated_without_dates",
    "generation_wrong_created_date",
    "invalid_file_hash",
    "missing_required_file_path",
    "created_wiki_without_revision",
    "wrong_remote_revision_type",
    "invalid_interlanguage_status",
    "verified_interlanguage_without_date",
    "invalid_nullable_source_url",
])
def test_full_report_identical_in_valid_and_invalid_states(tmp_path: Path, mutation: str):
    create_graph_package(tmp_path)
    if mutation != "valid":
        file = tmp_path / "data/registre_debat.json"
        data = json.loads(file.read_text(encoding="utf-8"))
        node = data["graph"]["nodes"][0]
        fr = node["fr"]
        en = node["en"]
        pages = node["pages"]
        generation = pages["fr"]["generation"]
        file_record = pages["fr"]["file"]
        wiki = pages["fr"]["wiki"]
        interlanguage = pages["fr"]["interlanguage"]
        occurrence = data["graph"]["occurrences"][0]

        if mutation == "null_en_title":
            en["canonical_title"] = None
        elif mutation == "valid_en_title":
            en["canonical_title"] = "Argument translated"
        elif mutation == "empty_en_title":
            en["canonical_title"] = ""
        elif mutation == "spaces_en_title":
            en["canonical_title"] = "  "
        elif mutation == "wrong_en_title_type":
            en["canonical_title"] = 17
        elif mutation == "en_displayed_title_bad":
            en["displayed_title"] = ""
        elif mutation == "bad_fr_title":
            fr["canonical_title"] = " "
        elif mutation == "invalid_rubriques":
            fr["rubriques"] = ["Not a category"]
        elif mutation == "too_many_rubriques":
            fr["rubriques"] = ["Science"] * 5
        elif mutation == "duplicate_keywords":
            fr["keywords"] = ["duplicate", "duplicate"]
        elif mutation == "invalid_english_status":
            en["title_status"] = "locked"
        elif mutation == "unknown_node_property":
            node["extra"] = True
        elif mutation == "missing_node_required":
            del node["id"]
        elif mutation == "bad_node_id":
            node["id"] = True
        elif mutation == "bad_occurrence_id":
            occurrence["id"] = "BAD"
        elif mutation == "bad_generation_status":
            generation["status"] = "unknown"
        elif mutation == "generation_validated_without_dates":
            generation["status"] = "validated"
        elif mutation == "generation_wrong_created_date":
            generation["creation_date"] = 1
        elif mutation == "invalid_file_hash":
            file_record["sha256"] = "abc"
        elif mutation == "missing_required_file_path":
            del file_record["path"]
        elif mutation == "created_wiki_without_revision":
            wiki["check_status"] = "created"
        elif mutation == "wrong_remote_revision_type":
            wiki["remote_revision_id"] = True
        elif mutation == "invalid_interlanguage_status":
            interlanguage["status"] = "unknown"
        elif mutation == "verified_interlanguage_without_date":
            interlanguage["status"] = "verified"
        elif mutation == "invalid_nullable_source_url":
            node["sources"]["fr"]["webliography"] = [12]
        dump(file, data)

    accelerated, _ = _compare_reports(tmp_path)
    if mutation in {
        "empty_en_title", "spaces_en_title", "wrong_en_title_type",
        "en_displayed_title_bad", "bad_fr_title", "invalid_rubriques",
        "too_many_rubriques", "duplicate_keywords", "invalid_english_status",
        "unknown_node_property", "missing_node_required", "bad_node_id",
        "bad_occurrence_id", "bad_generation_status",
        "generation_validated_without_dates",
        "generation_wrong_created_date", "invalid_file_hash",
        "missing_required_file_path", "created_wiki_without_revision",
        "wrong_remote_revision_type", "invalid_interlanguage_status",
        "verified_interlanguage_without_date", "invalid_nullable_source_url",
    }:
        assert any(f["code"] == "WDV-SCH-003" for f in accelerated["findings"])


def test_nested_nullable_oneof_with_mutated_compiled_branch_uses_original_callback():
    store = sv.SchemaStore()
    store._attested_runtime = True
    store.validate({}, REGISTRY)
    validator = store._compiled[REGISTRY][1]
    nullable = validator.schema["properties"]["graph"]["properties"]["nodes"]["items"]["properties"]["en"]["properties"]["canonical_title"]
    # Alter the internal expanded copy (not the normative source) after the
    # guard was constructed: it MUST fail closed if it sees new conditions.
    nullable["oneOf"][0]["type"] = "string"
    data = {"oneOf": [{"type": "string"}, nullable["oneOf"][1]]}
    assert nullable == data
    native = validator_for(store.schemas[REGISTRY])(nullable, registry=store.registry, format_checker=store.format_checker)
    # Passing the changed subtree itself through the guarded class should
    # behave exactly as the canonical library without any positive shortcut.
    guarded = type(validator)(nullable, registry=store.registry, format_checker=store.format_checker)
    left = [(e.message, len(e.context)) for e in native.iter_errors(None)]
    right = [(e.message, len(e.context)) for e in guarded.iter_errors(None)]
    assert left == right
    assert left
