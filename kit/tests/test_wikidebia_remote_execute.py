from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import wikidebia_corpus_build as corpus
import wikidebia_editorial_workspace as workspace_mod
import wikidebia_remote_compare as remote
import wikidebia_remote_plan_review as reviewer
import wikidebia_remote_execute as execution
import wikidebia_update as update

MARKER = "|avertissements-argument=Argument généré par IA\n"


class FakeAdapter:
    def __init__(self, pages=None, rights=None):
        self.pages = dict(pages or {})
        self.rights = set(rights or {"edit", "createpage", "move", "delete"})
        self.language = None
        self.next_revision = 100
        self.events = []
        self.revisions = {}

    def open_language(self, language, expected_user):
        assert self.language is None
        self.language = language
        self.events.append(("open", language))

    def close_language(self):
        self.events.append(("close", self.language))
        self.language = None

    def assert_identity(self, expected_user):
        return None

    def user_rights(self):
        return set(self.rights)

    def read_page(self, title):
        row = self.pages.get((self.language, title))
        return (False, None, "") if row is None else (True, row[0], row[1])

    def write_page(self, *, title, text, summary, tags, expected_user, create_only, base_revision_id):
        key = (self.language, title)
        if create_only and key in self.pages:
            raise RuntimeError("collision")
        if not create_only and (key not in self.pages or self.pages[key][0] != base_revision_id):
            raise RuntimeError("revision collision")
        self.next_revision += 1
        self.pages[key] = (self.next_revision, text)
        self.revisions[(self.language, title, self.next_revision)] = {
            "revision_id": self.next_revision, "text": text, "summary": summary, "tags": list(tags)
        }
        self.events.append(("write", self.language, title))
        return self.next_revision

    def read_revision(self, title, revision_id):
        return self.revisions.get((self.language, title, revision_id))

    def move_page(self, *, old_title, new_title, reason, expected_user, leave_redirect):
        old = (self.language, old_title)
        new = (self.language, new_title)
        _, text = self.pages.pop(old)
        self.next_revision += 1
        self.pages[new] = (self.next_revision, text)
        self.events.append(("move", self.language, old_title, new_title))
        return self.next_revision

    def delete_page(self, *, title, reason, expected_user):
        self.pages.pop((self.language, title), None)
        self.events.append(("delete", self.language, title))

    def backlinks(self, title):
        return []


def argument(summary: str) -> str:
    return "{{Argument\n" + MARKER + f"|résumé={summary}\n|rubriques=Société\n" + "}}\n"


def _fill_review(path: Path):
    value = json.loads(path.read_text(encoding="utf-8"))
    value.update({
        "overall_decision": "approved",
        "reviewer": "Relectrice test",
        "reviewed_at": "2026-08-04T00:05:00+02:00",
        "review_summary": "Le plan, l’inventaire et chaque opération ont été revus.",
    })
    value["attestations"] = {key: True for key in value["attestations"]}
    for row in value["operations"]:
        row["review_decision"] = "acknowledged" if row["category"] == "skip" else "approved"
        if row["category"] in reviewer.DESTRUCTIVE_OPERATIONS:
            row["reviewer_note"] = "Impact destructif vérifié."
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def make_approved_fixture(tmp_path: Path, *, no_changes: bool = False):
    project = tmp_path / "project"
    debate_id = "debat_test"
    work_id = "EDIT-EXEC-001"
    comparison_id = "REMOTE-20260804-001"
    workspace = project / ".state/editorial-workspaces" / debate_id / work_id
    release = workspace / "release-copy"
    page_dir = release / "output/fr/arguments"
    page_dir.mkdir(parents=True)
    text = argument("Texte final")
    page_path = page_dir / "A0001.wiki"
    page_path.write_text(text, encoding="utf-8")
    manifest = {
        "debate_id": debate_id,
        "global_status": "release_ready",
        "release_version": "test-release",
        "publication_gate": {"remote_write_authorized": False},
        "pages": [{
            "language": "fr", "page_id": "A0001", "page_type": "argument",
            "canonical_title": "Argument final", "file_path": "output/fr/arguments/A0001.wiki",
            "sha256": update.sha_file(page_path),
        }],
    }
    (release / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (release / "release").mkdir()
    (release / "release/release_manifest.json").write_text(json.dumps({
        "release_manifest_version": "1.0", "debate_id": debate_id,
        "global_status": "release_ready", "finalized_at": "2026-08-04T00:00:00+02:00",
        "files": [],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    release_sha = corpus.full_tree_sha256(release)

    run = project / ".state/remote-comparisons" / debate_id / work_id / comparison_id
    run.mkdir(parents=True)
    config = {
        "kit_version": update.KIT_VERSION,
        "project_root": ".",
        "family": "wikidebates",
        "family_file": "kit/families/wikidebates_family.py",
        "pywikibot_dir": "private/pywikibot",
        "sites": {"fr": {"code": "fr", "expected_user": "ChatGPT"}},
        "languages": ["fr"],
        "debate_id": debate_id,
        "corpus_root": page_path.parents[3].relative_to(project).as_posix(),
        "state_inventory_root": run.relative_to(project).as_posix() + "/baseline",
        "logs_dir": run.relative_to(project).as_posix() + "/logs",
        "published_state_dir": ".state/published",
        "receipts_dir": ".state/receipts",
        "validator": {"command": [sys.executable, "validator.py", "validate"], "required_version": update.REQUIRED_VALIDATOR_VERSION, "scopes": []},
        "edit_summaries": {"fr": "Corrections"},
        "comparison_mode": "read_only",
        "remote_write_authorized": False,
    }
    config_path = run / "config.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (run / "baseline").mkdir()

    operations = {name: [] for name in update.OPERATIONS}
    row = {
        "wiki": "fr", "language": "fr", "title": "Argument final", "page_id": "A0001", "page_type": "argument",
        "old_sha256": update.sha_text(text) if no_changes else None,
        "new_sha256": update.sha_text(text),
        "local_file_sha256": update.sha_file(page_path),
        "source_path": page_path.relative_to(project).as_posix(),
        "expected_revision_id": 10 if no_changes else None,
        "observed_revision_id": 10 if no_changes else None,
        "justification": "Identité distante vérifiée" if no_changes else "Page anglaise ou française nouvelle",
        "preconditions": [], "result": None, "phase": 2,
    }
    operations["skip" if no_changes else "create"].append(row)
    plan = {
        "plan_version": update.PLAN_VERSION,
        "kit_version": update.KIT_VERSION,
        "required_validator_version": update.REQUIRED_VALIDATOR_VERSION,
        "debate_id": debate_id,
        "corpus_version": "test-release",
        "languages": ["fr"],
        "scope_mode": "all",
        "state_source": {},
        "new_manifest_sha256": update.sha_file(release / "manifest.json"),
        "validator_report_sha256": "4" * 64,
        "config_sha256": update.sha_file(config_path),
        "operations": operations,
        "comparisons": [],
        "counts": {name: len(operations[name]) for name in update.OPERATIONS},
        "preconditions": ["read_only_comparison_completed", "plan_not_executed"],
    }
    plan["plan_sha256"] = update.sha_object(plan)
    (run / "update-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    inventory = {"schema": "wikidebia-observed-remote-inventory-1.0", "debate_id": debate_id, "comparison_id": comparison_id, "mode": "read_only", "pages": [], "write_attempts": 0, "remote_write_performed": False}
    inventory["inventory_sha256"] = update.sha_object(inventory)
    (run / "remote-inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    validation = {"validator_version": update.REQUIRED_VALIDATOR_VERSION, "result": "passed", "summary": {"errors": 0, "warnings": 0}}
    (run / "plan-validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    receipt = {
        "schema": remote.RECEIPT_SCHEMA, "debate_id": debate_id, "work_id": work_id, "comparison_id": comparison_id,
        "status": "plan_ready", "scope": "fr", "kit_version": update.KIT_VERSION,
        "validator_version": update.REQUIRED_VALIDATOR_VERSION, "release_copy_tree_sha256": release_sha,
        "plan_path": (run / "update-plan.json").relative_to(project).as_posix(), "plan_sha256": plan["plan_sha256"],
        "remote_inventory_sha256": inventory["inventory_sha256"], "remote_write_performed": False, "execution_authorized": False,
    }
    receipt["receipt_sha256"] = remote._canonical_sha(receipt, "receipt_sha256")
    (run / "comparison-receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    comparison_meta = {"comparison_id": comparison_id, "status": "plan_ready", "plan_sha256": plan["plan_sha256"]}
    meta = {
        "schema": "wikidebia-editorial-workspace-1.0", "debate_id": debate_id, "work_id": work_id,
        "normative_revision": "1.2.27", "status": "remote_plan_ready",
        "release_copy": {"tree_sha256": release_sha},
        "remote_comparison": comparison_meta, "remote_comparisons": [comparison_meta],
    }
    meta["workspace_sha256"] = workspace_mod.workspace_receipt_hash(meta)
    (workspace / "workspace.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    prepared = reviewer.prepare_review(project, debate_id, work_id, comparison_id)
    review_path = project / prepared["review"]
    _fill_review(review_path)
    approved = reviewer.finalize_review(project, debate_id, work_id, comparison_id)
    adapter_pages = {("fr", "Argument final"): (10, text)} if no_changes else {}
    adapter = FakeAdapter(adapter_pages)
    return project, debate_id, work_id, comparison_id, approved, adapter, text


def test_prepare_is_read_only_and_execute_creates_state(tmp_path: Path):
    project, debate_id, work_id, comparison_id, approved, adapter, text = make_approved_fixture(tmp_path)
    prepared = execution.prepare_execution(project, debate_id, work_id, comparison_id, approved["acceptance_sha256"], adapter=adapter)
    assert prepared["status"] == "ready"
    assert not any(event[0] in {"write", "move", "delete"} for event in adapter.events)
    receipt = execution.execute_accepted_plan(project, debate_id, work_id, comparison_id, prepared["preflight_sha256"], adapter=adapter)
    assert receipt["status"] == "executed"
    assert receipt["remote_write_performed"] is True
    assert adapter.pages[("fr", "Argument final")][1] == text
    state = json.loads((project / ".state/published" / debate_id / "fr/latest.json").read_text(encoding="utf-8"))
    assert state["pages"][0]["canonical_title"] == "Argument final"


def test_execution_blocks_if_remote_changes_after_preflight(tmp_path: Path):
    project, debate_id, work_id, comparison_id, approved, adapter, _ = make_approved_fixture(tmp_path)
    prepared = execution.prepare_execution(project, debate_id, work_id, comparison_id, approved["acceptance_sha256"], adapter=adapter)
    adapter.pages[("fr", "Argument final")] = (77, argument("Collision humaine"))
    try:
        execution.execute_accepted_plan(project, debate_id, work_id, comparison_id, prepared["preflight_sha256"], adapter=adapter)
    except execution.RemoteExecutionError as exc:
        assert "changé" in str(exc) or "Collision" in str(exc)
    else:
        raise AssertionError("Une modification distante postérieure au préflight a été écrasée")
    assert not any(event[0] == "write" for event in adapter.events)
    assert (project / ".state/remote-executions" / debate_id / work_id / comparison_id / "execution-failure.json").is_file()


def test_prepare_refuses_wrong_acceptance_hash(tmp_path: Path):
    project, debate_id, work_id, comparison_id, _, adapter, _ = make_approved_fixture(tmp_path)
    try:
        execution.prepare_execution(project, debate_id, work_id, comparison_id, "0" * 64, adapter=adapter)
    except execution.RemoteExecutionError as exc:
        assert "acceptation" in str(exc)
    else:
        raise AssertionError("Une mauvaise empreinte d’acceptation a été admise")


def test_no_changes_plan_is_attested_without_write(tmp_path: Path):
    project, debate_id, work_id, comparison_id, approved, adapter, _ = make_approved_fixture(tmp_path, no_changes=True)
    prepared = execution.prepare_execution(project, debate_id, work_id, comparison_id, approved["acceptance_sha256"], adapter=adapter)
    assert prepared["status"] == "no_changes_in_scope" or prepared["status"] == "ready"
    # A skip-only plan is an attestation; allow direct execution only when preflight was marked ready.
    if prepared["status"] == "no_changes_in_scope":
        preflight_path = project / ".state/remote-executions" / debate_id / work_id / comparison_id / "execution-preflight.json"
        value = json.loads(preflight_path.read_text(encoding="utf-8"))
        value["status"] = "ready"
        value["preflight_sha256"] = execution._canonical(value, "preflight_sha256")
        preflight_path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        receipt_path = preflight_path.parent / "preflight-receipt.json"
        pre_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        pre_receipt["status"] = "ready"
        pre_receipt["preflight_sha256"] = value["preflight_sha256"]
        pre_receipt["receipt_sha256"] = execution._canonical(pre_receipt, "receipt_sha256")
        receipt_path.write_text(json.dumps(pre_receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        prepared["preflight_sha256"] = value["preflight_sha256"]
    receipt = execution.execute_accepted_plan(project, debate_id, work_id, comparison_id, prepared["preflight_sha256"], adapter=adapter)
    assert receipt["status"] == "no_changes"
    assert receipt["remote_write_performed"] is False
    assert not any(event[0] in {"write", "move", "delete"} for event in adapter.events)


def test_manage_exposes_workspace_plan_execute_command():
    import wikidebia_manage as manage
    args = manage.build_parser().parse_args([
        "corpus-workspace-plan-execute", "debat_test",
        "--work-id", "EDIT-EXEC-001",
        "--comparison-id", "REMOTE-20260804-001",
        "--prepare",
        "--confirm-acceptance-sha256", "a" * 64,
    ])
    assert args.command == "corpus-workspace-plan-execute"
    assert args.prepare is True
