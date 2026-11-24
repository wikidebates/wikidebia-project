"""Regression: owner removal of obsolete top-level date metadata."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from wikidebia_update import remote_diff_is_only_preservable_metadata


@pytest.mark.parametrize("language,page_type,model,date_key,body_key", [
    ("fr", "debate", "Débat", "date-création", "introduction"),
    ("fr", "argument", "Argument", "date-création", "résumé"),
    ("en", "debate", "Debate", "creation-date", "introduction"),
    ("en", "argument", "Argument", "creation-date", "summary"),
])
def test_only_exact_retirement_is_adoptable(language, page_type, model, date_key, body_key):
    remote = "{{" + model + "\n|" + body_key + "=Content {{Citation|date=2026}}\n}}\n"
    prior = remote.replace("\n}}", "\n|" + date_key + "=2026-11-23\n}}")
    accepted, changed = remote_diff_is_only_preservable_metadata(prior, remote, language, page_type)
    assert accepted
    assert date_key in changed
    for altered in (
        remote.replace("Content", "Edited"),
        remote + "[[Category:Other]]",
        prior.replace("2026-11-23", "2026-11-24"),
    ):
        accepted, _ = remote_diff_is_only_preservable_metadata(prior, altered, language, page_type)
        assert not accepted
