from .current_policy_helpers import CURRENT_NORM_FILE, CURRENT_NORM, CURRENT_VALIDATOR, CURRENT_KIT, current_norm_path
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_norm_1259_records_english_creation_metadata_rules():
    text = (ROOT / "normative_reference/01_normes" / CURRENT_NORM_FILE).read_text(encoding="utf-8")
    assert "ne transporte jamais `|initialisation=`/`|initialization=`" in text
    assert "Les paramètres de premier niveau `date-création` et `creation-date` sont obsolètes" in text
    assert "Le jour civil de publication ne déclenche plus de changement de plan." in text

def test_new_english_argument_still_forbids_initialization():
    from wikidebia_validator import wikicode
    assert "initialization" in wikicode.TOP[("en", "argument")]["forbidden_generated"]
    assert wikicode.TOP[("en", "argument")]["order"][:3] == ["initialization", "established-name", "name"]
