from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_versions_file_has_only_the_three_functional_versions():
    versions = json.loads((ROOT / "VERSIONS.json").read_text(encoding="utf-8"))
    assert set(versions) == {"norm", "validator", "kit"}
    assert all(isinstance(value, str) and value for value in versions.values())

    forbidden = (
        "pour les paquets 1.2.",
        "pour les corpus 1.2.",
        "sous la norme 1.2.",
        "sous les normes 1.2.",
        "for packages declaring norm 1.2.",
        "for norm 1.2.",
    )
    failures = []
    for path in ROOT.glob("GUIDE_*.md"):
        text = path.read_text(encoding="utf-8").casefold()
        for phrase in forbidden:
            if phrase.casefold() in text:
                failures.append(f"{path.name}:{phrase}")
    assert failures == []


def test_versions_file_matches_kit_metadata_and_script():
    versions = json.loads((ROOT / "VERSIONS.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "KIT_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["version"] == versions["kit"]
    assert manifest["validator_version"] == versions["validator"]
    assert manifest["normative_revision"] == versions["norm"]
    script = (ROOT / "scripts/wikidebia_publish.py").read_text(encoding="utf-8")
    assert "from wikidebia_release_info import" in script
    assert "KIT_VERSION" in script and "REQUIRED_VALIDATOR_VERSION" in script


def test_graph_extractor_versions_match_kit():
    versions = json.loads((ROOT / "VERSIONS.json").read_text(encoding="utf-8"))
    script = (ROOT / "scripts/wikidebia_graph_extract.py").read_text(encoding="utf-8")
    assert "from wikidebia_release_info import KIT_VERSION" in script
    assert re.search(r'^GRAPH_EXTRACT_VERSION\s*=\s*"1\.2\.0"', script, re.M)


def test_editorial_workspace_versions_match_kit():
    versions = json.loads((ROOT / "VERSIONS.json").read_text(encoding="utf-8"))
    script = (ROOT / "scripts/wikidebia_editorial_workspace.py").read_text(encoding="utf-8")
    assert "from wikidebia_release_info import KIT_VERSION" in script
    build = (ROOT / "scripts/wikidebia_corpus_build.py").read_text(encoding="utf-8")
    assert "from wikidebia_release_info import" in build and "NORM_VERSION" in build


def test_editorial_review_versions_match_kit():
    versions = json.loads((ROOT / "VERSIONS.json").read_text(encoding="utf-8"))
    script = (ROOT / "scripts/wikidebia_editorial_review.py").read_text(encoding="utf-8")
    assert "from wikidebia_release_info import KIT_VERSION" in script
