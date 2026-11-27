from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_versions_file_has_only_the_three_functional_versions():
    versions = json.loads((ROOT / "VERSIONS.json").read_text(encoding="utf-8"))
    assert versions == {"norm": "1.2.89", "validator": "0.4.106", "kit": "2.16.48"}


def test_versions_file_matches_validator_metadata():
    versions = json.loads((ROOT / "VERSIONS.json").read_text(encoding="utf-8"))
    compatibility = json.loads((ROOT / "COMPATIBILITY.json").read_text(encoding="utf-8"))
    assert compatibility["validator_version"] == versions["validator"]
    assert compatibility["implemented_normative_revision"] == versions["norm"]
    versioning_text = (ROOT / "src/wikidebia_validator/versioning.py").read_text(encoding="utf-8")
    init_text = (ROOT / "src/wikidebia_validator/__init__.py").read_text(encoding="utf-8")
    assert 'VERSIONS = _load_json("VERSIONS.json")' in versioning_text
    assert 'VALIDATOR_VERSION as __version__' in init_text


def test_compatibility_keeps_historical_corpus_revisions():
    compatibility = json.loads((ROOT / "COMPATIBILITY.json").read_text(encoding="utf-8"))
    supported = compatibility["compatible_normative_revisions"]
    assert "1.2.10" in supported
    assert "1.2.14" in supported
    assert supported[-1] == "1.2.89"


def test_schema_accepts_norm_versions_through_generic_semver_contract():
    common = json.loads((ROOT / "src/wikidebia_validator/schemas/common.schema.json").read_text(encoding="utf-8"))
    prop = common["$defs"]["normativeVersions"]["properties"]["consolidated_norm"]
    assert "$ref" in prop
    assert "enum" not in prop
