from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load_module(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


remote = load_module("wikidebia_remote_compare")
update = sys.modules.get("wikidebia_update") or load_module("wikidebia_update")


class FakeReadAdapter:
    def __init__(self, pages):
        self.pages = pages
        self.language = None
        self.write_calls = 0

    def open_language(self, language, expected_user):
        self.language = language

    def assert_identity(self, expected_user):
        assert expected_user

    def close_language(self):
        self.language = None

    def read_page(self, title):
        row = self.pages.get((self.language, title))
        if row is None:
            return False, None, ""
        return True, row[0], row[1]

    def backlinks(self, title):
        return []

    def write_page(self, **kwargs):
        self.write_calls += 1
        raise AssertionError("write_page ne doit jamais être appelé")

    def move_page(self, **kwargs):
        self.write_calls += 1
        raise AssertionError("move_page ne doit jamais être appelé")

    def delete_page(self, **kwargs):
        self.write_calls += 1
        raise AssertionError("delete_page ne doit jamais être appelé")


def fake_validate_plan(project_root, plan_path, json_path, text_path):
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    unsigned = dict(plan)
    claimed = unsigned.pop("plan_sha256")
    assert claimed == update.sha_object(unsigned)
    report = {"validator_version": "0.4.29", "result": "passed", "summary": {"errors": 0, "warnings": 0}}
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    text_path.write_text("Plan valide.\n", encoding="utf-8")
    return report


def make_release(tmp_path: Path, *, authorize_summary_changes=True):
    project = tmp_path / "project"
    work_id = "EDIT-REMOTE-001"
    workspace = project / ".state/editorial-workspaces/debat_test" / work_id
    release_copy = workspace / "release-copy"
    files = {
        "imports/fr/debate/debate.wiki": "{{Débat|sujet=Débat test|date-création=2026-08-03}}\n",
        "imports/fr/arguments/A0001.wiki": "{{Argument|résumé=Ancien argument|date-création=2026-08-03}}\n",
        "output/fr/debate/debate.wiki": "{{Débat|sujet=Débat test|introduction=Version révisée|date-création=2026-08-03}}\n",
        "output/fr/arguments/A0001.wiki": "{{Argument|résumé=Argument révisé|date-création=2026-08-03}}\n",
        "output/en/debate/debate.wiki": "{{Debate|topic=Test debate|creation-date=2026-08-03}}\n",
        "output/en/arguments/A0001.wiki": "{{Argument|summary=Revised argument|creation-date=2026-08-03}}\n",
    }
    for rel, text in files.items():
        path = release_copy / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    provenance = {
        "schema": "wikidebia-import-provenance-1.0",
        "pages": [
            {"kind": "debate", "page_id": None, "canonical_title": "Débat test", "revision_id": 10, "import_path": "imports/fr/debate/debate.wiki"},
            {"kind": "argument", "page_id": "A0001", "canonical_title": "Ancien argument", "revision_id": 11, "import_path": "imports/fr/arguments/A0001.wiki"},
        ],
    }
    (release_copy / "data").mkdir(parents=True, exist_ok=True)
    (release_copy / "data/import_provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pages = [
        {"language": "fr", "page_id": "debat_test", "page_type": "debate", "canonical_title": "Débat test", "file_path": "output/fr/debate/debate.wiki"},
        {"language": "fr", "page_id": "A0001", "page_type": "argument", "canonical_title": "Argument amélioré", "file_path": "output/fr/arguments/A0001.wiki"},
        {"language": "en", "page_id": "debat_test", "page_type": "debate", "canonical_title": "Test debate", "file_path": "output/en/debate/debate.wiki"},
        {"language": "en", "page_id": "A0001", "page_type": "argument", "canonical_title": "Improved argument", "file_path": "output/en/arguments/A0001.wiki"},
    ]
    if authorize_summary_changes:
        pages[1]["summary_change_authorization"] = {
            "decision": "explicit_user_request", "action": "edit",
            "instruction": "Réécris le résumé de cet argument pour ce scénario de comparaison.",
        }
    manifest = {
        "debate_id": "debat_test", "global_status": "release_ready", "version": "test-release",
        "publication_gate": {"remote_write_authorized": False}, "pages": pages,
    }
    (release_copy / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    release_sha = remote.full_tree_sha256(release_copy)
    meta = {
        "schema": "wikidebia-editorial-workspace-1.0", "debate_id": "debat_test", "work_id": work_id,
        "normative_revision": "1.2.27", "status": "release_ready",
        "release_copy": {"path": "release-copy", "tree_sha256": release_sha, "status": "release_ready"},
    }
    meta["workspace_sha256"] = remote.workspace_receipt_hash(meta)
    (workspace / "workspace.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    receipt_dir = project / ".state/corpus-releases/debat_test" / work_id
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt = {"schema": "wikidebia-local-release-receipt-1.0", "debate_id": "debat_test", "work_id": work_id, "release_copy_tree_sha256": release_sha}
    receipt["receipt_sha256"] = remote._canonical_sha(receipt, "receipt_sha256")
    (receipt_dir / "release-receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    baseline = remote._import_baseline(release_copy, "debat_test")
    remote_pages = {("fr", row["canonical_title"]): (row["revision_id"], row["content"]) for row in baseline}
    return project, workspace, work_id, release_sha, remote_pages


def _stub_corpus_validation(monkeypatch):
    monkeypatch.setattr(update.RemoteUpdatePlanner, "_validate_new_corpus", lambda self: {
        "validator_version": "0.4.29", "result": "passed", "summary": {"errors": 0, "warnings": 0}
    })
    monkeypatch.setattr(remote.RemoteUpdatePlanner, "_validate_new_corpus", lambda self: {
        "validator_version": "0.4.29", "result": "passed", "summary": {"errors": 0, "warnings": 0}
    })


def test_remote_comparison_builds_signed_read_only_plan(tmp_path: Path, monkeypatch):
    _stub_corpus_validation(monkeypatch)
    project, workspace, work_id, release_sha, pages = make_release(tmp_path)
    adapter = FakeReadAdapter(pages)
    result = remote.compare_workspace(
        project, "debat_test", work_id, release_sha,
        comparison_id="REMOTE-20260803-001", adapter=adapter, validate_plan_fn=fake_validate_plan,
    )
    assert result["status"] == "plan_ready"
    assert result["remote_write_performed"] is False
    assert adapter.write_calls == 0
    run = project / ".state/remote-comparisons/debat_test" / work_id / "REMOTE-20260803-001"
    plan = json.loads((run / "update-plan.json").read_text(encoding="utf-8"))
    receipt = json.loads((run / "comparison-receipt.json").read_text(encoding="utf-8"))
    inventory = json.loads((run / "remote-inventory.json").read_text(encoding="utf-8"))
    assert "read_only_comparison_completed" in plan["preconditions"]
    assert "plan_not_executed" in plan["preconditions"]
    assert plan["counts"]["move"] == 1
    assert plan["counts"]["update"] == 1
    assert plan["counts"]["create"] == 2
    assert not plan["operations"]["manual_review"]
    assert not plan["operations"]["blocked"]
    assert receipt["plan_sha256"] == plan["plan_sha256"]
    assert receipt["comparison_schema"] == remote.COMPARISON_SCHEMA
    assert receipt["remote_write_performed"] is False
    assert receipt["execution_authorized"] is False
    assert inventory["remote_write_performed"] is False
    assert inventory["write_attempts"] == 0
    fr_baseline = json.loads((run / "baseline/fr.json").read_text(encoding="utf-8"))
    en_baseline = json.loads((run / "baseline/en.json").read_text(encoding="utf-8"))
    assert fr_baseline["source"]["kind"] == "graph_extraction_snapshot"
    assert len(fr_baseline["pages"]) == 2
    assert en_baseline["source"]["kind"] == "new_language_empty_baseline"
    assert en_baseline["pages"] == []
    meta = json.loads((workspace / "workspace.json").read_text(encoding="utf-8"))
    assert meta["status"] == "remote_plan_ready"


def test_remote_comparison_classifies_human_change_for_manual_review(tmp_path: Path, monkeypatch):
    _stub_corpus_validation(monkeypatch)
    project, workspace, work_id, release_sha, pages = make_release(tmp_path)
    key = next(key for key in pages if key[0] == "fr" and key[1] != "Débat test")
    revision, _ = pages[key]
    pages[key] = (revision + 100, "Modification humaine indépendante\n")
    result = remote.compare_workspace(
        project, "debat_test", work_id, release_sha,
        comparison_id="REMOTE-20260803-002", adapter=FakeReadAdapter(pages), validate_plan_fn=fake_validate_plan,
    )
    assert result["status"] == "manual_review"
    assert result["counts"]["manual_review"] == 1
    run = project / ".state/remote-comparisons/debat_test" / work_id / "REMOTE-20260803-002"
    plan = json.loads((run / "update-plan.json").read_text(encoding="utf-8"))
    assert len(plan["comparisons"]) == 1
    meta = json.loads((workspace / "workspace.json").read_text(encoding="utf-8"))
    assert meta["status"] == "remote_plan_manual_review"


def test_remote_comparison_requires_exact_release_hash(tmp_path: Path, monkeypatch):
    _stub_corpus_validation(monkeypatch)
    project, workspace, work_id, _, pages = make_release(tmp_path)
    try:
        remote.compare_workspace(
            project, "debat_test", work_id, "0" * 64,
            comparison_id="REMOTE-20260803-003", adapter=FakeReadAdapter(pages), validate_plan_fn=fake_validate_plan,
        )
    except remote.RemoteComparisonError as exc:
        assert "empreinte confirmée" in str(exc)
    else:
        raise AssertionError("Une empreinte de release-copy erronée a été acceptée")
    assert not (project / ".state/remote-comparisons/debat_test" / work_id / "REMOTE-20260803-003").exists()


def test_remote_comparison_prefers_signed_published_state(tmp_path: Path, monkeypatch):
    _stub_corpus_validation(monkeypatch)
    project, workspace, work_id, release_sha, pages = make_release(tmp_path)
    state_dir = project / ".state/published/debat_test/fr"
    state_dir.mkdir(parents=True)
    baseline = remote._import_baseline(workspace / "release-copy", "debat_test")
    state = {
        "state_version": update.STATE_VERSION,
        "debate_id": "debat_test", "language": "fr", "corpus_version": "old", "publication_date": "2026-08-03",
        "source_manifest_sha256": "0" * 64, "plan_sha256": "1" * 64,
        "pages": [{k: row[k] for k in ("page_id", "page_type", "canonical_title", "content_sha256", "revision_id", "status")} for row in baseline],
    }
    state["state_sha256"] = update.sha_object(state)
    (state_dir / "latest.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    remote.compare_workspace(
        project, "debat_test", work_id, release_sha,
        comparison_id="REMOTE-20260803-004", adapter=FakeReadAdapter(pages), validate_plan_fn=fake_validate_plan,
    )
    run = project / ".state/remote-comparisons/debat_test" / work_id / "REMOTE-20260803-004"
    fr_baseline = json.loads((run / "baseline/fr.json").read_text(encoding="utf-8"))
    assert fr_baseline["source"]["kind"] == "published_state_receipt"


def test_remote_comparison_applies_signed_publication_url_replacement(tmp_path: Path, monkeypatch):
    _stub_corpus_validation(monkeypatch)
    project, workspace, work_id, _release_sha, pages = make_release(tmp_path)
    release = workspace / "release-copy"
    source = release / "output/en/arguments/A0001.wiki"
    old_url = "https://archive.is/example"
    new_url = "https://example.org/original"
    source.write_text(source.read_text(encoding="utf-8") + old_url + "\n", encoding="utf-8")

    manifest_path = release / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["editorial_controls"] = {
        "manual_remote_adoption_path": "data/manual_remote_adoptions.json",
        "publication_url_replacements_path": "data/publication_url_replacements.json",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    replacement = {
        "version": "1.0", "debate_id": "debat_test", "entries": [{
            "language": "en", "page_id": "A0001", "old_url": old_url, "new_url": new_url,
            "owner_approved": True,
            "reason": "MediaWiki rejects the archive host; retain the exact original cited article.",
            "authorization_receipt_sha256": "a" * 64,
        }],
    }
    (release / "data/publication_url_replacements.json").write_text(
        json.dumps(replacement, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    adoption = {
        "version": "1.0", "debate_id": "debat_test", "decision": "Décision explicite du propriétaire",
        "entries": [{
            "language": "en", "page_id": "A0001", "title": "Improved argument",
            "reason": "Earlier remote revision explicitly adopted before URL sanitization.",
            "allow_proposed_change": True, "observed_revision_id": 50,
            "observed_sha256": "b" * 64, "allowed_lifecycle_parameter_changes": [],
        }],
    }
    (release / "data/manual_remote_adoptions.json").write_text(
        json.dumps(adoption, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    release_sha = remote.full_tree_sha256(release)
    meta_path = workspace / "workspace.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["release_copy"]["tree_sha256"] = release_sha
    meta["workspace_sha256"] = remote.workspace_receipt_hash(meta)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    receipt_path = project / ".state/corpus-releases/debat_test" / work_id / "release-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["release_copy_tree_sha256"] = release_sha
    receipt["receipt_sha256"] = remote._canonical_sha(receipt, "receipt_sha256")
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    remote_text = source.read_text(encoding="utf-8").replace(old_url, new_url)
    pages[("en", "Improved argument")] = (99, remote_text)
    result = remote.compare_workspace(
        project, "debat_test", work_id, release_sha, scope="en",
        comparison_id="REMOTE-20260803-005", adapter=FakeReadAdapter(pages), validate_plan_fn=fake_validate_plan,
    )
    assert result["status"] == "plan_ready"
    assert result["counts"]["skip"] == 1
    assert result["counts"]["blocked"] == 0
    plan = json.loads((project / ".state/remote-comparisons/debat_test" / work_id / "REMOTE-20260803-005/update-plan.json").read_text(encoding="utf-8"))
    skipped = next(row for row in plan["operations"]["skip"] if row["page_id"] == "A0001")
    effective = project / skipped["source_path"]
    assert skipped["new_sha256"] == update.sha_text(remote_text)
    assert new_url in effective.read_text(encoding="utf-8")
    assert old_url not in effective.read_text(encoding="utf-8")
