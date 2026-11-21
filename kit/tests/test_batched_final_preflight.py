"""Read-only final-publication preflight must use bounded MediaWiki batches."""
import pytest

import wikidebia_final_publication as publication


class FakePreflightAdapter:
    def __init__(self, pages=None):
        self.pages = dict(pages or {})
        self.language = None
        self.calls = []
        self.read_one_calls = 0
        self.missing_response = False

    def open_language(self, language, expected_user):
        assert self.language is None
        self.language = language

    def close_language(self):
        self.language = None

    def assert_identity(self, expected_user):
        assert expected_user == "ChatGPT"

    def available_change_tags(self):
        return {"chatgpt", "translated-fr"}

    def user_rights(self):
        return {"edit", "createpage"}

    def read_pages(self, titles):
        self.calls.append((self.language, tuple(titles)))
        if self.missing_response:
            return {}
        return {title: self.pages.get((self.language, title), (False, None, "")) for title in titles}

    def read_page(self, title):
        self.read_one_calls += 1
        raise AssertionError("individual preflight page reads are not required")


def test_english_preflight_uses_one_batched_pass_for_many_pages():
    adapter = FakePreflightAdapter()
    plan = {"actions": [{
        "language": "en", "page_id": f"A{i:04d}",
        "title": f"English {i}", "operation": "create",
    } for i in range(125)]}
    snapshot = publication._remote_snapshot_for_english(adapter, plan, "ChatGPT")
    assert len(snapshot) == 125
    assert all(row["exists"] is False for row in snapshot)
    assert adapter.calls == [("en", tuple(f"English {i}" for i in range(125)))]
    assert adapter.read_one_calls == 0
    assert adapter.language is None


def test_french_preflight_uses_batched_snapshots_and_rejects_divergence():
    content = "{{Argument|résumé=Source}}"
    adapter = FakePreflightAdapter({
        ("fr", "Titre FR"): (True, 41, content),
    })
    row = {
        "language": "fr", "page_id": "A0001", "title": "Titre FR",
        "expected_revision_id": 41, "old_sha256": publication.sha_text(content),
    }
    plan = {"operations": {"update": [row]}}
    snapshot = publication._remote_snapshot_for_french(adapter, plan, "ChatGPT")
    assert len(snapshot) == 1
    assert adapter.calls == [("fr", ("Titre FR",))]
    assert adapter.read_one_calls == 0
    assert adapter.language is None

    row["expected_revision_id"] = 40
    with pytest.raises(publication.FinalPublicationError, match="changé depuis le plan"):
        publication._remote_snapshot_for_french(adapter, plan, "ChatGPT")
    assert adapter.language is None


def test_incomplete_batched_preflight_blocks_both_languages():
    adapter = FakePreflightAdapter()
    adapter.missing_response = True
    en_plan = {"actions": [{
        "language": "en", "page_id": "A0001", "title": "English 1", "operation": "create",
    }]}
    with pytest.raises(publication.FinalPublicationError, match="incomplète"):
        publication._remote_snapshot_for_english(adapter, en_plan, "ChatGPT")
    assert adapter.language is None
    fr_plan = {"operations": {"create": [{
        "language": "fr", "page_id": "A0001", "title": "Titre FR",
    }]}}
    with pytest.raises(publication.FinalPublicationError, match="incomplète"):
        publication._remote_snapshot_for_french(adapter, fr_plan, "ChatGPT")
    assert adapter.language is None
