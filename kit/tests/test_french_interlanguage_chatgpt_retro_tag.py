"""Offline regressions for a missing chatgpt tag on an already-written FR link."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from wikidebia_update import PlanExecutor, PlanConflict, sha_text
from wikidebia_retro_tag import RetroTagError


OLD = "{{Argument|résumé=Texte}}"
NEW = "{{Argument|résumé=Texte|interlangue={{Lien interlangue|langue=en|page=English title}}}}"
SUMMARY = "Ajout du lien interlangue vers la page anglaise : [[:en:English title|English title]]"


class TagAdapter:
    def __init__(self, *, tags=(), rights=True, delayed=0):
        self.page = (True, 41, NEW)
        self.revision = {
            "revision_id": 41, "parent_id": 40, "user": "ChatGPT",
            "text": NEW, "summary": SUMMARY, "tags": list(tags),
        }
        self.rights = rights
        self.delayed = delayed
        self.reads = 0
        self.tag_calls = 0
        self.writes = 0

    def read_page(self, title):
        assert title == "Titre français"
        return self.page

    def read_revision(self, title, revision_id):
        assert revision_id == 41
        self.reads += 1
        row = dict(self.revision)
        row["tags"] = list(row["tags"])
        if self.delayed and self.reads <= self.delayed:
            row["tags"] = []
        return row

    def assert_manual_tag_available(self, tag):
        if not self.rights:
            raise RetroTagError("changetags absent")
        assert tag == "chatgpt"

    def add_manual_revision_tag(self, revision_id, tag, expected_user):
        assert (revision_id, tag, expected_user) == (41, "chatgpt", "ChatGPT")
        self.tag_calls += 1
        if not self.rights:
            raise AssertionError("tagging occurred without rights")
        if tag not in self.revision["tags"]:
            self.revision["tags"].append(tag)

    def write_page(self, **kwargs):
        self.writes += 1
        raise AssertionError("Content must never be re-edited")


def fixture(adapter):
    executor = PlanExecutor.__new__(PlanExecutor)
    executor.adapter = adapter
    executor.config = {"verification_attempts": 2, "verification_delay_seconds": 0}
    executor.manifest = {"translation_status": {"en": "deferred"}}
    executor._source_text = lambda row: NEW
    executor._expected_row_summary = lambda row, operation, plan, text: SUMMARY
    row = {
        "operation": "update", "language": "fr", "page_type": "argument",
        "page_id": "A0001", "title": "Titre français",
        "new_sha256": sha_text(NEW), "old_sha256": sha_text(OLD),
        "expected_revision_id": 40,
        "edit_summary_policy": "french_interlanguage_addition",
        "edit_summary": SUMMARY,
    }
    return executor, row, {"plan_sha256": "a" * 64}


def test_missing_tag_is_repaired_on_exact_signed_revision_without_text_edit():
    adapter = TagAdapter()
    executor, row, plan = fixture(adapter)
    result = executor._execute_one(row, "ChatGPT", plan)
    assert result["status"] == "already_done"
    assert result["tag_repair"]["status"] == "tag_added"
    assert result["tag_repair"]["parent_revision_id"] == 40
    assert adapter.tag_calls == 1
    assert adapter.writes == 0
    second = executor._execute_one(row, "ChatGPT", plan)
    assert second["tag_repair"]["status"] == "already_tagged"
    assert adapter.tag_calls == 1
    assert adapter.writes == 0


def test_delayed_tag_is_read_without_second_tag_or_edit():
    adapter = TagAdapter(tags=["chatgpt"], delayed=0)
    executor, row, plan = fixture(adapter)
    result = executor._execute_one(row, "ChatGPT", plan)
    assert result["tag_repair"]["status"] == "already_tagged"
    assert adapter.tag_calls == adapter.writes == 0


def test_delayed_existing_tag_visibility_avoids_retro_tag():
    adapter = TagAdapter(tags=["chatgpt"], delayed=2)
    executor, row, plan = fixture(adapter)
    result = executor._execute_one(row, "ChatGPT", plan)
    assert result["tag_repair"]["status"] == "already_tagged"
    assert adapter.tag_calls == adapter.writes == 0


def test_delayed_post_tag_visibility_retries_without_content_edit():
    adapter = TagAdapter(delayed=2)
    executor, row, plan = fixture(adapter)
    result = executor._execute_one(row, "ChatGPT", plan)
    assert result["tag_repair"]["status"] == "tag_added"
    assert adapter.tag_calls == 1
    assert adapter.reads >= 3
    assert adapter.writes == 0


def test_missing_manual_tag_permission_blocks_without_edit():
    adapter = TagAdapter(rights=False)
    executor, row, plan = fixture(adapter)
    with pytest.raises(PlanConflict, match="changetags"):
        executor._execute_one(row, "ChatGPT", plan)
    assert adapter.tag_calls == adapter.writes == 0


@pytest.mark.parametrize("field,wrong", [
    ("parent_id", 33),
    ("user", "Human"),
    ("summary", "Modifications diverses"),
    ("text", "Une autre page"),
])
def test_signed_revision_provenance_mismatch_never_tags(field, wrong):
    adapter = TagAdapter()
    adapter.revision[field] = wrong
    executor, row, plan = fixture(adapter)
    with pytest.raises(PlanConflict, match="Provenance"):
        executor._execute_one(row, "ChatGPT", plan)
    assert adapter.tag_calls == adapter.writes == 0


def test_concurrent_edit_prevents_rattrapage():
    class ConcurrentAdapter(TagAdapter):
        def __init__(self):
            super().__init__()
            self.page_reads = 0

        def read_page(self, title):
            self.page_reads += 1
            return (True, 41, NEW) if self.page_reads == 1 else (True, 42, NEW)

    adapter = ConcurrentAdapter()
    executor, row, plan = fixture(adapter)
    with pytest.raises(PlanConflict, match="concurrente"):
        executor._execute_one(row, "ChatGPT", plan)
    assert adapter.tag_calls == adapter.writes == 0


def test_change_tags_only_on_french_interlanguage_policy():
    adapter = TagAdapter()
    executor, row, plan = fixture(adapter)
    row["edit_summary_policy"] = "content_diff_v1"
    with pytest.raises(PlanConflict, match="interlangue français signé"):
        executor._attest_french_interlanguage_tag(row, plan, 41, NEW, "ChatGPT")
    assert adapter.tag_calls == adapter.writes == 0
