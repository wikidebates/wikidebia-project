from .current_policy_helpers import CURRENT_NORM_FILE, CURRENT_NORM, CURRENT_VALIDATOR, CURRENT_KIT, current_norm_path
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
NORM = ROOT / "normative_reference" / "01_normes"

def test_matrix_declares_active_revision_1260():
    text = (NORM / "MATRICE_TRACEABILITE_DESIDERATA.md").read_text(encoding="utf-8")
    assert f"- **Révision :** {CURRENT_NORM}" in text

def test_requirements_catalog_precedence_points_to_active_norm_1260():
    data = json.loads((NORM / "requirements_catalog_wikidebia.json").read_text(encoding="utf-8"))
    assert data["active_package_revision"] == CURRENT_NORM
    assert data["normative_revision"] == CURRENT_NORM
    assert CURRENT_NORM_FILE in data["precedence"]
    assert "WIKIDEBIA_NORME_CONSOLIDEE_1.2.58.md" not in data["precedence"]

def test_active_and_archived_consolidated_norms_are_coherent():
    active = sorted(p.name for p in NORM.glob("WIKIDEBIA_NORME_CONSOLIDEE_*.md"))
    assert active == [CURRENT_NORM_FILE]
    assert (NORM / "history" / "WIKIDEBIA_NORME_CONSOLIDEE_1.2.59.md").is_file()
    text = (NORM / active[0]).read_text(encoding="utf-8")
    assert "**Date d’effet :** 27 novembre 2026" in text
