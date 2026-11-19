"""Cache reuse never bypasses schema validation or corrupts report ordering."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from jsonschema.exceptions import SchemaError

from wikidebia_validator.schema_validation import SchemaStore


def test_repeated_validation_reuses_checked_schema_without_changing_findings():
    store = SchemaStore()
    schema = "scope.schema.json"
    instance = {"unexpected": 42}
    first = [(list(e.absolute_path), e.message) for e in store.validate(instance, schema)]
    assert first
    cached = store._compiled[schema][1]
    with patch.object(type(cached), "check_schema", side_effect=AssertionError("rechecked")):
        second = [(list(e.absolute_path), e.message) for e in store.validate(instance, schema)]
    assert first == second
    assert store._compiled[schema][1] is cached


def test_modified_schema_invalidates_compilation_and_rechecks_metaschema():
    store = SchemaStore()
    schema = "scope.schema.json"
    store.validate({}, schema)
    initial = store._compiled[schema]
    store.schemas[schema]["properties"] = {"arbitrary": {"type": "integer"}}
    store.validate({"arbitrary": "bad"}, schema)
    assert store._compiled[schema][0] != initial[0]
    assert store._compiled[schema][1] is not initial[1]
    assert any("integer" in e.message for e in store.validate({"arbitrary": "bad"}, schema))

    store.schemas[schema]["properties"]["arbitrary"]["type"] = "not-a-json-schema-type"
    with pytest.raises(SchemaError):
        store.validate({"arbitrary": 1}, schema)


def test_two_stores_do_not_share_cached_validators():
    left, right = SchemaStore(), SchemaStore()
    left.validate({}, "scope.schema.json")
    assert "scope.schema.json" in left._compiled
    assert not right._compiled
