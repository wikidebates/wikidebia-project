import json
from pathlib import Path

import wikidebia_final_publication as final
from wikidebia_publish import GenericPublisher, sha_text
from wikidebia_update import RemoteUpdatePlanner


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_generic_publisher_excludes_late_reused_page_ids():
    publisher = GenericPublisher.__new__(GenericPublisher)
    publisher.languages = ("en",)
    publisher.operation = {
        "kind": "full_page",
        "page_types": ["debate", "argument"],
        "exclude_page_ids": ["A0001"],
    }
    publisher.manifest = {
        "pages": [
            {"language": "en", "page_id": "demo", "page_type": "debate", "canonical_title": "Demo"},
            {"language": "en", "page_id": "A0001", "page_type": "argument", "canonical_title": "Existing"},
            {"language": "en", "page_id": "A0002", "page_type": "argument", "canonical_title": "New"},
        ]
    }

    selected = publisher._selected_pages()

    assert [row["page_id"] for row in selected] == ["demo", "A0002"]


def test_late_existing_translation_prunes_only_exclusive_descendants(tmp_path: Path, monkeypatch):
    release = tmp_path / "release"
    state = tmp_path / "state"
    french = release / "output/fr/arguments/A0001.wiki"
    french.parent.mkdir(parents=True)
    french.write_text(
        "{{Argument\n|interlangue={{Lien interlangue\n|langue=en\n|page=Existing A\n}}\n}}\n",
        encoding="utf-8",
    )
    _write(release / "manifest.json", {"pages": [
        {"language": "fr", "page_id": "demo", "page_type": "debate"},
        {"language": "fr", "page_id": "A0001", "page_type": "argument"},
        {"language": "en", "page_id": "A0001", "page_type": "argument"},
        {"language": "en", "page_id": "A0002", "page_type": "argument"},
        {"language": "en", "page_id": "A0003", "page_type": "argument"},
    ]})
    _write(release / "graph/graphe_argumentatif.json", {
        "nodes": [{"id": value} for value in ("A0001", "A0002", "A0003")],
        "occurrences": [
            {"id": "O1", "node_id": "A0001", "parent_occurrence_id": None},
            {"id": "O2", "node_id": "A0002", "parent_occurrence_id": "O1"},
            {"id": "O3", "node_id": "A0003", "parent_occurrence_id": None},
        ],
    })
    french_plan = {
        "plan_sha256": "fr-plan",
        "operations": {"skip": [{
            "language": "fr",
            "page_id": "A0001",
            "page_type": "argument",
            "title": "Argument A",
            "observed_revision_id": 10,
            "source_path": str(french),
        }]},
    }

    class Adapter:
        def open_language_read_only(self, language):
            assert language == "en"

        def read_page(self, title):
            assert title == "Existing A"
            return True, 20, "{{Argument}}"

        def close_language(self):
            pass

    monkeypatch.setattr(final, "build_adapter", lambda config, root: Adapter())

    receipt = final._discover_late_existing_english_reuse(
        tmp_path, release, state, french_plan, {"languages": ["en"]}
    )

    assert receipt is not None
    assert receipt["excluded_english_page_ids"] == ["A0001", "A0002"]
    assert receipt["excluded_french_page_ids"] == ["A0001", "A0002"]
    assert receipt["pruned_descendant_page_ids"] == ["A0002"]
    assert receipt["frontiers"][0]["english_revision_id"] == 20
    assert (state / "late-existing-english-reuse.json").is_file()


def test_remote_update_plan_filter_is_language_scoped_and_resigned():
    def row(language, page_id):
        return {"language": language, "page_id": page_id}

    plan = {
        "operations": {
            "create": [row("en", "A"), row("en", "B")],
            "update": [row("fr", "A"), row("fr", "B")],
            "skip": [], "move": [], "redirect": [], "delete": [], "manual_review": [], "blocked": [],
        },
        "comparisons": [row("en", "A"), row("fr", "A"), row("fr", "B")],
        "counts": {"create": 2, "update": 2},
        "plan_sha256": "old",
    }

    filtered = final._filter_remote_update_plan(plan, {"en": {"A"}, "fr": {"B"}})

    assert filtered["operations"]["create"] == [row("en", "B")]
    assert filtered["operations"]["update"] == [row("fr", "A")]
    assert filtered["comparisons"] == [row("fr", "A")]
    assert filtered["counts"]["create"] == 1
    assert filtered["counts"]["update"] == 1
    assert filtered["plan_sha256"] != "old"


def test_interlanguage_only_resolves_reused_english_title_from_registry(tmp_path: Path):
    registry = tmp_path / "data/registre_debat.json"
    _write(registry, {
        "graph": {"nodes": [{
            "id": "A0001",
            "en": {"canonical_title": "Existing English argument", "title_status": "locked"},
        }]},
    })
    planner = RemoteUpdatePlanner.__new__(RemoteUpdatePlanner)
    planner.corpus_root = tmp_path
    planner.manifest = {
        "core_files": {"registry": "data/registre_debat.json"},
        "pages": [{"language": "fr", "page_id": "A0001", "page_type": "argument"}],
    }
    planner._registry_cache = False

    assert planner._english_title_for("A0001", "argument") == "Existing English argument"


def test_kit_migration_accepts_only_verified_rewrite_for_pending_create(tmp_path: Path):
    source = tmp_path / "output/en/arguments/A0001.wiki"
    source.parent.mkdir(parents=True)
    raw = "{{Argument\n|summary=[https://archive.md/example Evidence].\n}}\n"
    previous = raw.replace("https://archive.md/", "https://archive.is/")
    rewritten = raw.replace(
        "https://archive.md/example", "https://publisher.example/article"
    )
    source.write_text(raw, encoding="utf-8")
    common = {
        "operation_id": "publish", "kind": "full_page", "language": "en",
        "page_id": "A0001", "page_type": "argument", "title": "Evidence",
        "source_path": "output/en/arguments/A0001.wiki", "parameter": None,
        "local_file_sha256": final.sha256_file(source),
        "local_target_sha256": sha_text(raw), "edit_summary": "summary",
        "change_tags": ["chatgpt"], "publication_creation_date": None,
    }
    old = {"actions": [{**common, "operation": "create", "desired_sha256": sha_text(previous)}]}
    new = {"actions": [{**common, "operation": "create", "desired_sha256": sha_text(rewritten)}]}
    publisher = GenericPublisher.__new__(GenericPublisher)
    publisher.root = tmp_path
    publisher.operation = {"kind": "full_page", "remote_content_replacements": [{
        "from": "https://archive.md/example", "to": "https://publisher.example/article", "languages": ["en"],
    }]}
    previous_publisher = GenericPublisher.__new__(GenericPublisher)
    previous_publisher.operation = {"kind": "full_page", "remote_content_replacements": [{
        "from": "https://archive.md/", "to": "https://archive.is/", "languages": ["en"],
    }]}

    allowed = final._verified_pending_remote_content_replacements(
        old, new, publisher, previous_publisher
    )
    transition = final._english_plan_order_transition(
        old, new, allowed_pending_desired_changes=allowed
    )

    assert list(allowed) == [("en", "A0001")]
    assert transition["pending_desired_content_replacements"][0]["page_id"] == "A0001"
    assert transition["remaining_after_order_migration"][0]["page_id"] == "A0001"


def test_remote_content_replacements_are_loaded_from_scoped_receipt(tmp_path: Path):
    receipt = {
        "schema": final.REMOTE_CONTENT_REPLACEMENTS_SCHEMA,
        "schema_version": "1.0",
        "debate_id": "demo",
        "replacements": [{
            "from": "https://blocked.example/item",
            "to": "https://publisher.example/item",
            "languages": ["en"],
            "reason": "verified_original_url",
        }],
    }
    receipt["receipt_sha256"] = final._canonical(receipt, "receipt_sha256")
    _write(tmp_path / "remote-content-replacements.json", receipt)

    config = final._apply_remote_content_replacements(
        tmp_path, "demo", {"operation": {"kind": "full_page"}}
    )

    assert config["operation"]["remote_content_replacements"] == receipt["replacements"]
    assert config["operation"]["remote_content_replacements_receipt_sha256"] == receipt["receipt_sha256"]
