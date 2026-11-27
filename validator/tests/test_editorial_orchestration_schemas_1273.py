from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "src" / "wikidebia_validator" / "schemas"


def schema(name: str):
    value = json.loads((SCHEMAS / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(value)
    return Draft202012Validator(value)


def test_review_package_schema_accepts_minimal_signed_manifest_shape():
    validator = schema("chatgpt_review_package.schema.json")
    value = {
        "schema": "wikidebia-chatgpt-review-package-1.0", "schema_version": "1.0",
        "package_id": "123e4567-e89b-12d3-a456-426614174000", "review_type": "graph_review",
        "debate_id": "revenu_de_base", "work_id": None,
        "normative_revision": "1.2.73", "validator_version": "0.4.76", "kit_version": "2.16.0",
        "prepared_at": "2026-08-11T14:00:00+02:00", "source_anchor_sha256": "a" * 64,
        "editable_files": [{"package_path": "editable/reviews/graph_build_review.json", "target_path": "reviews/graph_build_review.json", "sha256_at_prepare": "b" * 64}],
        "context_files": [{"package_path": "context/manifest.json", "target_path": "manifest.json", "sha256": "c" * 64}],
        "counts": {"placements": 191}, "instructions_sha256": "d" * 64, "manifest_sha256": "e" * 64,
    }
    assert list(validator.iter_errors(value)) == []


def test_review_package_schema_rejects_unsafe_target_path():
    validator = schema("chatgpt_review_package.schema.json")
    value = {
        "schema": "wikidebia-chatgpt-review-package-1.0", "schema_version": "1.0",
        "package_id": "123e4567-e89b-12d3-a456-426614174000", "review_type": "graph_review",
        "debate_id": "revenu_de_base", "work_id": None,
        "normative_revision": "1.2.73", "validator_version": "0.4.76", "kit_version": "2.16.0",
        "prepared_at": "2026-08-11", "source_anchor_sha256": None,
        "editable_files": [{"package_path": "editable/x", "target_path": "../private/secret", "sha256_at_prepare": "b" * 64}],
        "context_files": [], "counts": {}, "instructions_sha256": "d" * 64, "manifest_sha256": "e" * 64,
    }
    assert list(validator.iter_errors(value))


def test_workflow_state_and_semantic_response_schemas():
    workflow = schema("editorial_orchestration_state.schema.json")
    state = {
        "schema": "wikidebia-editorial-orchestration-1.0", "schema_version": "1.0",
        "normative_revision": "1.2.73", "validator_version": "0.4.76", "kit_version": "2.16.0",
        "debate_id": "revenu_de_base", "debate_title": "Un revenu de base doit-il être instauré ?",
        "phase": "graph_review", "status": "awaiting_review", "work_id": None,
        "pending_review": {"review_type": "graph_review"}, "created_at": "2026-08-11", "updated_at": "2026-08-11",
    }
    assert list(workflow.iter_errors(state)) == []

    semantic = schema("semantic_review_response.schema.json")
    response = {
        "schema": "wikidebia-semantic-review-response-1.0", "schema_version": "1.0", "pass_number": 1,
        "method_family": "proposition_by_proposition", "method": "Comparaison proposition par proposition",
        "reviewer": "Relecteur A", "note": "Relecture indépendante", "new_certain_errors": 0, "findings": [],
    }
    assert list(semantic.iter_errors(response)) == []
    response["method_family"] = "same_method_twice"
    assert list(semantic.iter_errors(response))


def test_schema_catalog_and_capabilities_publish_orchestration_contracts():
    catalog = json.loads((SCHEMAS / "schema_catalog.json").read_text(encoding="utf-8"))
    paths = {row["path"] for row in catalog["schemas"]}
    assert {"chatgpt_review_package.schema.json", "editorial_orchestration_state.schema.json", "semantic_review_response.schema.json", "workflow_diagnostic_package.schema.json"} <= paths
    assert catalog["schema_count"] == len(catalog["schemas"])
    caps = json.loads((ROOT / "CAPABILITIES.json").read_text(encoding="utf-8"))
    assert caps["release"] == {"norm": "1.2.89", "validator": "0.4.106", "kit": "2.16.48"}
    assert caps["accepts"]["chatgpt_review_package"][0]["schema"] == "wikidebia-chatgpt-review-package-1.0"
