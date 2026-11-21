"""Prevent obsolete documentary quotas in active creation instructions."""
from pathlib import Path
import json
import re

import pytest

ROOT = Path(__file__).resolve().parents[2]
FILES = ["workflow_production_wikidebia.md", "profils_rendu_wikidebia.md",
         "structures_mediawiki_wikidebia.md", "cahier_des_charges_consolide_wikidebia.md",
         "requirements_catalog_wikidebia.json", "MATRICE_TRACEABILITE_DESIDERATA.md"]


@pytest.mark.parametrize("name", FILES)
def test_active_documents_match_across_components_and_have_no_bucket_quota(name):
    left = ROOT / "norms/normative_reference/01_normes" / name
    right = ROOT / "validator/normative_reference/01_normes" / name
    text = left.read_text(encoding="utf-8")
    assert left.read_bytes() == right.read_bytes()
    # Read only active files, never rewrite or reject their historical snapshots.
    assert not re.search(r"neuf[^\n]*au moins deux|each of the nine[^\n]*at least two|contiennent chacun au moins deux sous-mod\u00e8les", text, re.I)
    if name == "requirements_catalog_wikidebia.json":
        row = next(r for r in json.loads(text)["requirements"] if r["id"] == "DFR-045")
        assert row["disposition"] == "active"
        assert "no per-parameter quota" in row["statement"]
        assert "empty optional parameter is omitted" in row["statement"]
    elif name != "MATRICE_TRACEABILITE_DESIDERATA.md":
        assert "sans quota par param\u00e8tre" in text
        assert "enti\u00e8rement omis" in text


def test_historical_changelog_still_records_old_rule():
    text = (ROOT / "norms/normative_reference/01_normes/CHANGELOG_NORMATIF.md").read_text()
    assert "au moins deux r\u00e9f\u00e9rences dans chacun des neuf" in text
