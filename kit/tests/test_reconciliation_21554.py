import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = json.loads((ROOT / "VERSIONS.json").read_text(encoding="utf-8"))


def test_validator_publication_metadata_regression_gates_are_declared():
    manifest = json.loads((ROOT / "KIT_MANIFEST.json").read_text(encoding="utf-8"))
    gates = set(manifest["regression_gates"])
    assert "validator_english_initialization_source_projection_regression" in gates
    assert "validator_retired_page_creation_date_regression" in gates
    assert "validator_english_creation_date_source_equality_regression" not in gates
    assert manifest["version"] == VERSIONS["kit"]
    assert manifest["validator_version"] == VERSIONS["validator"]
    assert manifest["normative_revision"] == VERSIONS["norm"]
