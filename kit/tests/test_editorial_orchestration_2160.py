from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

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


wf = load_module("wikidebia_review_workflow")
manage = load_module("wikidebia_manage")
common = sys.modules["wikidebia_corpus_build"]


def make_state(project: Path, base: Path, review_type: str = "graph_review") -> dict:
    state = {
        "schema": wf.WORKFLOW_SCHEMA,
        "schema_version": "1.0",
        "debate_id": "debat_test",
        "debate_title": "Débat test ?",
        "phase": review_type,
        "status": "running",
        "work_id": None,
        "pending_review": None,
        "created_at": "2026-08-11T12:00:00+02:00",
        "updated_at": "2026-08-11T12:00:00+02:00",
    }
    wf._save_workflow(project, state)
    return state


def make_base(project: Path) -> Path:
    base = project / ".state/corpus-builds/debat_test"
    (base / "reviews").mkdir(parents=True)
    (base / "data").mkdir(parents=True)
    (base / "private").mkdir(parents=True)
    common.write_json(base / "reviews/edit.json", {"debate_id": "debat_test", "value": "pending"})
    common.write_json(base / "data/context.json", {"debate_id": "debat_test", "locked": True})
    (base / "private/secret.txt").write_text("TOP-SECRET", encoding="utf-8")
    return base


def test_workflow_reconcile_restores_release_boundary_from_signed_evidence(tmp_path, monkeypatch):
    debate_id, work_id = "debat_test", "EDIT-20261029-001"
    state = {
        "schema": wf.WORKFLOW_SCHEMA, "schema_version": "1.0", "debate_id": debate_id,
        "debate_title": "Débat test ?", "phase": "fr_content_review", "status": "awaiting_review",
        "work_id": work_id, "pending_review": {"review_type": "fr_content_review"},
        "created_at": "2026-10-29T10:00:00+01:00", "updated_at": "2026-10-29T10:00:00+01:00",
    }
    wf._save_workflow(tmp_path, state)
    workspace = tmp_path / ".state/editorial-workspaces" / debate_id / work_id
    release_copy = workspace / "release-copy"; release_copy.mkdir(parents=True)
    (release_copy / "manifest.json").write_text("{}\n", encoding="utf-8")
    tree = common.full_tree_sha256(release_copy)
    meta = {
        "schema": "wikidebia-editorial-workspace-1.0", "debate_id": debate_id, "work_id": work_id,
        "status": "release_ready", "release_copy": {"tree_sha256": tree},
        "local_release": {"archive": "release.zip"},
    }
    meta["workspace_sha256"] = wf.workspace_receipt_hash(meta)
    common.write_json(workspace / "workspace.json", meta)

    def signed(value):
        value = dict(value)
        value["receipt_sha256"] = wf._sha256_bytes(wf._canonical_json(value))
        return value

    release_receipt = signed({"debate_id": debate_id, "work_id": work_id, "release_copy_tree_sha256": tree})
    common.write_json(tmp_path / ".state/corpus-releases" / debate_id / work_id / "release-receipt.json", release_receipt)
    content_receipt = signed({"debate_id": debate_id, "work_id": work_id, "status": "published", "plan_sha256": "a" * 64})
    common.write_json(tmp_path / ".state/fr-publication" / debate_id / work_id / "content/publication-receipt.json", content_receipt)
    monkeypatch.setattr(wf, "resolve_workflow_release_baseline", lambda *a, **k: {"baseline_sha256": "b" * 64})

    result = wf.reconcile_workflow(tmp_path, debate_id)

    assert result["phase"] == result["status"] == "release_ready"
    assert "pending_review" not in result
    assert result["french_content_publication"]["receipt_sha256"] == content_receipt["receipt_sha256"]
    assert result["workflow_reconciliation"]["baseline_sha256"] == "b" * 64
    assert (tmp_path / ".state/workflows" / debate_id / "reconciliation.json").is_file()


def rewrite_zip(source: Path, target: Path, edit):
    temp = target.parent / "unzipped"
    shutil.rmtree(temp, ignore_errors=True)
    temp.mkdir(parents=True)
    with zipfile.ZipFile(source) as z:
        z.extractall(temp)
    edit(temp)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(x for x in temp.rglob("*") if x.is_file()):
            z.write(p, p.relative_to(temp).as_posix())
    shutil.rmtree(temp)


def test_review_package_is_minimal_and_excludes_secrets(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    base = make_base(project)
    state = make_state(project, base)
    pending = wf.create_review_package(
        project, state, review_type="graph_review", base=base,
        editable_paths=["reviews/edit.json"], context_paths=["data/context.json"], counts={"placements": 4},
    )
    archive = project / pending["package_path"]
    with zipfile.ZipFile(archive) as z:
        names = set(z.namelist())
        assert names == {
            "REVIEW_PACKAGE.json", "INSTRUCTIONS.md",
            "editable/reviews/edit.json", "context/data/context.json",
        }
        assert all("private" not in name and "secret" not in name for name in names)
        manifest = json.loads(z.read("REVIEW_PACKAGE.json"))
        assert manifest["schema"] == wf.PACKAGE_SCHEMA
        assert manifest["debate_id"] == "debat_test"
        assert manifest["editable_files"][0]["target_path"] == "reviews/edit.json"


def test_package_creation_is_idempotent_while_review_pending(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    base = make_base(project)
    state = make_state(project, base)
    first = wf.create_review_package(project, state, review_type="graph_review", base=base, editable_paths=["reviews/edit.json"], context_paths=["data/context.json"])
    reloaded = wf._load_workflow(project, "debat_test")
    second = wf.create_review_package(project, reloaded, review_type="graph_review", base=base, editable_paths=["reviews/edit.json"], context_paths=["data/context.json"])
    assert first["package_id"] == second["package_id"]
    assert first["archive_sha256"] == second["archive_sha256"]


def test_import_refuses_modified_context_and_wrong_corpus(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    base = make_base(project)
    state = make_state(project, base)
    pending = wf.create_review_package(project, state, review_type="graph_review", base=base, editable_paths=["reviews/edit.json"], context_paths=["data/context.json"])
    original = project / pending["package_path"]

    bad_context = tmp_path / "bad-context.zip"
    def change_context(root: Path):
        (root / "context/data/context.json").write_text('{}\n', encoding="utf-8")
    rewrite_zip(original, bad_context, change_context)
    with pytest.raises(wf.WorkflowError, match="contexte"):
        wf.import_review(project, "debat_test", bad_context)

    wrong = tmp_path / "wrong.zip"
    def change_manifest(root: Path):
        path = root / "REVIEW_PACKAGE.json"
        data = json.loads(path.read_text())
        data["debate_id"] = "autre_debat"
        data["manifest_sha256"] = wf._package_manifest_hash(data)
        common.write_json(path, data)
    rewrite_zip(original, wrong, change_manifest)
    with pytest.raises(wf.WorkflowError, match="autre corpus|provenance"):
        wf.import_review(project, "debat_test", wrong)


def test_valid_import_installs_only_editable_and_resumes(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    base = make_base(project)
    state = make_state(project, base)
    pending = wf.create_review_package(project, state, review_type="graph_review", base=base, editable_paths=["reviews/edit.json"], context_paths=["data/context.json"])
    original = project / pending["package_path"]
    returned = tmp_path / "returned.zip"
    def complete(root: Path):
        common.write_json(root / "editable/reviews/edit.json", {"debate_id": "debat_test", "value": "approved"})
    rewrite_zip(original, returned, complete)

    monkeypatch.setattr(wf, "finalize_graph_review", lambda project_root, base_path, debate_id: {"status": "approved", "review_sha256": "a" * 64})
    monkeypatch.setattr(wf, "_mechanical_advance", lambda project_root, s: s)
    result = wf.import_review(project, "debat_test", returned)
    assert common.load_json(base / "reviews/edit.json", "edit")["value"] == "approved"
    assert common.load_json(base / "data/context.json", "context")["locked"] is True
    assert result["phase"] == "promote_and_workspace"
    assert result["pending_review"] is None


def test_failed_import_restores_complete_control_directory(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    base = make_base(project)
    state = make_state(project, base)
    pending = wf.create_review_package(project, state, review_type="graph_review", base=base, editable_paths=["reviews/edit.json"], context_paths=["data/context.json"])
    original = project / pending["package_path"]
    returned = tmp_path / "returned.zip"
    rewrite_zip(original, returned, lambda root: common.write_json(root / "editable/reviews/edit.json", {"debate_id": "debat_test", "value": "bad"}))

    def failing_finalize(project_root, base_path, debate_id):
        (base_path / "reports").mkdir(exist_ok=True)
        (base_path / "reports/partial.txt").write_text("partial", encoding="utf-8")
        raise RuntimeError("validation failed")
    monkeypatch.setattr(wf, "finalize_graph_review", failing_finalize)
    with pytest.raises(RuntimeError, match="validation failed"):
        wf.import_review(project, "debat_test", returned)
    assert common.load_json(base / "reviews/edit.json", "edit")["value"] == "pending"
    assert not (base / "reports/partial.txt").exists()
    assert wf._load_workflow(project, "debat_test")["pending_review"]["package_id"] == pending["package_id"]


def test_manage_keeps_advanced_commands_and_adds_high_level_commands():
    parser = manage.build_parser()
    choices = parser._subparsers._group_actions[0].choices
    for command in (
        "corpus-init-from-snapshot", "corpus-review-graph", "corpus-promote",
        "corpus-workspace-review", "corpus-workspace-content-review",
        "corpus-workspace-translation", "corpus-workspace-semantic-convergence",
        "workflow", "review-import", "workflow-status",
    ):
        assert command in choices


def test_semantic_response_requires_real_method_family():
    response = wf._semantic_response_template("semantic_convergence_1")
    assert response["new_certain_errors"] is None
    assert response["method_family"] == ""
    assert wf.ALLOWED_METHOD_FAMILIES == {
        "proposition_by_proposition", "risk_marker_review", "reverse_source_target",
        "field_boundary_review", "independent_bilingual_reread",
    }


def test_workflow_stops_before_corpus_when_debate_already_exists_in_english(tmp_path: Path):
    from test_wikidebia_corpus_init import make_extraction

    project = tmp_path / "project"
    project.mkdir()
    source = make_extraction(tmp_path / "source")
    graph_path = next(source.glob("*_graphe_recursif_*.json"))
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    graph["metadata"].update({
        "traduction_du_débat_requise": False,
        "traduction_anglaise_débat_vérifiée": True,
        "traduction_anglaise_débat_existante": "Existing English debate",
        "url_traduction_anglaise_débat": "https://en.wikidebates.org/wiki/Existing_English_debate",
        "revision_traduction_anglaise_débat": 987,
        "vérification_traduction_anglaise_débat_effectuée_le": "2026-10-26T12:00:00+00:00",
    })
    common.write_json(graph_path, graph)

    state = wf.start_workflow(
        project,
        "Débat test ?",
        debate_id="debat_test",
        short_code="TEST",
        snapshot=source,
    )

    assert state["phase"] == "already_translated"
    assert state["status"] == "completed_existing_translation"
    assert state["existing_english_debate"] == {
        "title": "Existing English debate",
        "url": "https://en.wikidebates.org/wiki/Existing_English_debate",
        "revision_id": 987,
        "verified_at": "2026-10-26T12:00:00+00:00",
    }
    assert not (project / ".state/corpus-builds/debat_test").exists()
    assert wf._mechanical_advance(project, state)["phase"] == "already_translated"


def test_graph_extract_does_not_reuse_cache_without_translation_preflight(tmp_path: Path, monkeypatch):
    from test_wikidebia_corpus_init import make_extraction

    project = tmp_path / "project"
    output = project / ".state/graph-extract/debat_test"
    shutil.copytree(make_extraction(tmp_path / "source"), output)
    graph_path = next(output.glob("*_graphe_recursif_*.json"))
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    graph["metadata"].pop("traduction_du_débat_requise", None)
    common.write_json(graph_path, graph)
    script = project / "kit/scripts/wikidebia_graph_extract.py"
    script.parent.mkdir(parents=True)
    script.write_text("# test stub\n", encoding="utf-8")
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        updated = json.loads(graph_path.read_text(encoding="utf-8"))
        updated["metadata"]["traduction_du_débat_requise"] = True
        common.write_json(graph_path, updated)
        return wf.subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

    monkeypatch.setattr(wf.subprocess, "run", fake_run)
    selected = wf._run_graph_extract(project, "Débat test")

    assert selected == output
    assert len(calls) == 1


def test_end_to_end_graph_handoff_resumes_to_metadata_handoff(tmp_path: Path, monkeypatch):
    from test_wikidebia_corpus_init import make_extraction

    project = tmp_path / "project"
    project.mkdir()
    source = make_extraction(tmp_path / "source")
    monkeypatch.setattr(wf, "run_initial_validator", lambda project_root, package: {"status": "passed"})

    def fake_graph_validator(project_root, package, json_output, text_output, **kwargs):
        common.write_json(json_output, {"result": "passed", "summary": {"errors": 0, "warnings": 0}})
        text_output.parent.mkdir(parents=True, exist_ok=True)
        text_output.write_text("passed\n", encoding="utf-8")
        return {"result": "passed", "summary": {"errors": 0, "warnings": 0}}
    monkeypatch.setitem(wf.finalize_graph_review.__globals__, "run_validator", fake_graph_validator)

    def fake_promote(project_root: Path, debate_id: str, confirm_review_sha256: str):
        build = project_root / ".state/corpus-builds" / debate_id
        target = project_root / "corpus" / debate_id
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(build), str(target))
        return {"status": "promoted", "review_sha256": confirm_review_sha256}

    monkeypatch.setattr(wf, "promote_graph", fake_promote)

    state = wf.start_workflow(project, "Débat test ?", debate_id="debat_test", short_code="TEST", snapshot=source)
    assert state["pending_review"]["review_type"] == "graph_review"
    graph_zip = project / state["pending_review"]["package_path"]
    returned = tmp_path / "graph-reviewed.zip"

    def complete_graph(root: Path):
        placement_path = root / f"editable/{common.PLACEMENT_REVIEW}"
        placement = json.loads(placement_path.read_text(encoding="utf-8"))
        for entry in placement["entries"]:
            entry["placement_status"] = "approved"
            entry["direct_fit"] = True
            entry["rationale"] = "Cette occurrence vise directement la meilleure cible logique et conserve exactement sa fonction argumentative."
            if entry["declared_depth"] == 1:
                block = entry["main_argument_review"]
                block.update({
                    "direct_answer_to_debate": True,
                    "autonomous_without_parent": True,
                    "organizes_distinct_argument_family": True,
                    "more_general_nonduplicate_parent_available": False,
                    "principally_supports_or_attacks_specific_argument": False,
                    "principally_example_or_specialization": False,
                })
            else:
                entry["subordinate_review"].update({
                    "parent_is_best_immediate_target": True,
                    "relation_to_parent_explicit": True,
                })
        common.write_json(placement_path, placement)
        envelope_path = root / f"editable/{common.REVIEW_ENVELOPE}"
        envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
        envelope["decision"] = "approved"
        envelope["reviewer"] = "ChatGPT review"
        envelope["reviewed_at"] = "2026-08-11T14:00:00+02:00"
        envelope["attestations"] = {key: True for key in common.REQUIRED_ATTESTATIONS}
        envelope["blocking_issues"] = []
        envelope["notes"] = "Revue complète des placements et de la cohérence argumentative du graphe."
        common.write_json(envelope_path, envelope)
        titles_path = root / f"editable/{common.GRAPH_TITLE_REVIEW}"
        titles = json.loads(titles_path.read_text(encoding="utf-8"))
        for item in titles["items"]:
            title_review = item["review"]
            title_review["status"] = "approved"
            title_review["reviewer"] = "ChatGPT review"
            title_review["reviewed_at"] = "2026-08-11T14:00:00+02:00"
            if item["entity_type"] == "argument":
                title_review["canonical_title_decision"] = "keep"
                title_review["displayed_title_decision"] = "keep"
                title_review["canonical_title_rationale"] = "Le titre canonique source est autonome, explicite et identifie précisément le raisonnement de cette page."
                title_review["displayed_title_rationale"] = "Le titre affiché source conserve fidèlement le raisonnement et reste adapté au contexte de lecture de la branche."
                title_review["canonical_referents_explicit"] = True
                title_review["displayed_title_complete_proposition"] = True
                title_review["displayed_title_argument_intelligible"] = True
                title_review["displayed_title_concision_reviewed"] = True
                title_review["displayed_title_semantically_equivalent"] = True
                title_review["displayed_title_improves_readability_when_distinct"] = True
        common.write_json(titles_path, titles)

    rewrite_zip(graph_zip, returned, complete_graph)
    monkeypatch.setattr(wf, "publish_checkpoint", lambda *a, **k: {"status": "published", "stage": "graph", "receipt_sha256": "d" * 64})
    monkeypatch.setitem(wf.finalize_metadata_review.__globals__, "_run_validator", lambda *a, **k: {"result": "passed", "summary": {"errors": 0, "warnings": 0}, "report_sha256": "a" * 64})
    resumed = wf.import_review(project, "debat_test", returned)
    assert resumed["work_id"]
    assert resumed["french_graph_publication"]["status"] == "published"
    assert resumed["pending_review"]["review_type"] == "fr_content_review"
    content_zip = project / resumed["pending_review"]["package_path"]
    assert content_zip.is_file()
    with zipfile.ZipFile(content_zip) as z:
        assert "editable/reviews/fr/classification_review.json" in z.namelist()
        assert "editable/data/keyword_vocabulary_working.json" in z.namelist()
        assert not any(name.startswith("context/private/") for name in z.namelist())


def test_resume_after_interruption_adopts_existing_graph_draft_but_revalidates(tmp_path: Path, monkeypatch):
    from test_wikidebia_corpus_init import make_extraction
    project = tmp_path / "project"
    project.mkdir()
    source = make_extraction(project / "source")
    build = project / ".state/corpus-builds/debat_test"
    wf.build_corpus(source, build, debate_id="debat_test", short_code="TEST", scope_summary=None, overwrite=False)
    state = {
        "schema": wf.WORKFLOW_SCHEMA, "schema_version": "1.0", "debate_id": "debat_test",
        "debate_title": "Débat test ?", "short_code": "TEST", "phase": "initialize_graph",
        "status": "running", "work_id": None, "pending_review": None,
        "snapshot_path": "source", "force_refresh": False,
        "created_at": "2026-08-11T12:00:00+02:00", "updated_at": "2026-08-11T12:00:00+02:00",
    }
    wf._save_workflow(project, state)
    calls = []
    monkeypatch.setattr(wf, "run_initial_validator", lambda root, package: calls.append(package) or {"status": "passed"})
    resumed = wf.start_workflow(project, "Débat test ?", debate_id="debat_test")
    assert len(calls) == 1
    assert resumed["pending_review"]["review_type"] == "graph_review"


def test_import_refuses_local_edit_outside_handoff(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    base = make_base(project)
    state = make_state(project, base)
    pending = wf.create_review_package(project, state, review_type="graph_review", base=base, editable_paths=["reviews/edit.json"], context_paths=["data/context.json"])
    common.write_json(base / "reviews/edit.json", {"debate_id": "debat_test", "value": "modified-locally"})
    with pytest.raises(wf.WorkflowError, match="hors réimport"):
        wf.import_review(project, "debat_test", project / pending["package_path"])


def make_full_workspace(project: Path, debate_id: str = "debat_test", work_id: str = "EDIT-20260811-001") -> Path:
    workspace = project / ".state/editorial-workspaces" / debate_id / work_id
    common.write_json(workspace / "workspace.json", {
        "schema": "wikidebia-editorial-workspace-1.0", "schema_version": "1.0",
        "debate_id": debate_id, "work_id": work_id, "status": "audit_ready",
        "workspace_sha256": "0" * 64,
    })
    files = {
        "reviews/fr/page_metadata_review.json": {"items": [{"id": "A0001"}]},
        "data/keyword_vocabulary_working.json": {"entries": []},
        "audits/editorial_inventory.json": {"items": []},
        "tasks/editorial_tasks.json": {"tasks": []},
        "working-copy/scope.json": {"debate_id": debate_id},
        "working-copy/data/registre_debat.json": {"debate_id": debate_id},
        "working-copy/graph/graphe_argumentatif.json": {"debate_id": debate_id},
        "reviews/fr/content_review.json": {"arguments": [{"id": "A0001"}]},
        "data/sources_working.json": {"sources": []},
        "reviews/fr/classification_review.json": {"items": []},
        "audits/fr_content_inventory.json": {"arguments": []},
        "reviewed-copy/data/fr_page_metadata_lock.json": {"status": "locked"},
        "reviewed-copy/data/registre_debat.json": {"debate_id": debate_id},
        "reviewed-copy/data/sources.json": {"sources": []},
        "reviewed-copy/scope.json": {"debate_id": debate_id},
        "reviews/en/translation_review.json": {"status": "draft", "arguments": [{"id": "A0001"}], "review_units": [{"id": "U1"}]},
        "data/sources_en_working.json": {"sources": []},
        "audits/en_translation_inventory.json": {"arguments": []},
        "content-reviewed-copy/data/fr_page_metadata_lock.json": {"status": "locked"},
        "content-reviewed-copy/data/fr_content_lock.json": {"status": "locked"},
        "content-reviewed-copy/data/registre_debat.json": {"debate_id": debate_id},
        "content-reviewed-copy/data/sources.json": {"sources": []},
        "content-reviewed-copy/data/keyword_vocabulary.json": {"entries": []},
        "reviews/en/translation_readiness.json": {"status": "ready_for_translation"},
    }
    for rel, payload in files.items():
        common.write_json(workspace / rel, payload)
    for rel in (
        "audits/editorial_inventory.md", "audits/fr_content_inventory.md", "audits/en_translation_inventory.md",
    ):
        path = workspace / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("inventory\n", encoding="utf-8")
    return workspace


def returned_semantic_zip(source: Path, target: Path, *, family: str, method: str, errors: int, findings=None):
    def edit(root: Path):
        path = root / "editable/reviews/en/semantic_review_response.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data.update({
            "method_family": family,
            "method": method,
            "reviewer": "Relecteur indépendant",
            "note": "Relecture indépendante complète de la traduction.",
            "new_certain_errors": errors,
            "findings": list(findings or []),
        })
        common.write_json(path, data)
    rewrite_zip(source, target, edit)


def test_full_orchestration_reaches_final_publication_through_all_editorial_stops(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    work_id = "EDIT-20260811-001"
    workspace = make_full_workspace(project, work_id=work_id)
    state = {
        "schema": wf.WORKFLOW_SCHEMA, "schema_version": "1.0",
        "normative_revision": wf.NORM_VERSION, "validator_version": wf.VALIDATOR_VERSION, "kit_version": wf.KIT_VERSION,
        "debate_id": "debat_test", "debate_title": "Débat test ?", "short_code": "TEST",
        "phase": "fr_metadata_review", "status": "running", "work_id": work_id,
        "pending_review": None, "snapshot_path": None, "force_refresh": False,
        "created_at": "2026-08-11T12:00:00+02:00", "updated_at": "2026-08-11T12:00:00+02:00",
    }
    wf._save_workflow(project, state)

    monkeypatch.setattr(wf, "prepare_content_review", lambda *a, **k: {"status": "prepared"})
    monkeypatch.setattr(wf, "prepare_translation_review", lambda *a, **k: {"status": "prepared"})
    monkeypatch.setattr(wf, "finalize_metadata_review", lambda *a, **k: {"review_sha256": "1" * 64})
    monkeypatch.setattr(wf, "apply_metadata_review", lambda *a, **k: {"status": "applied"})
    monkeypatch.setattr(wf, "finalize_content_review", lambda *a, **k: {"review_sha256": "2" * 64})
    monkeypatch.setattr(wf, "apply_content_review", lambda *a, **k: {"status": "applied"})
    monkeypatch.setattr(wf, "publish_checkpoint", lambda *a, **k: {"status": "published", "receipt_sha256": "9" * 64})

    def finalize_translation(*args, **kwargs):
        review = common.load_json(workspace / "reviews/en/translation_review.json", "translation")
        review["status"] = "approved"
        review["review_sha256"] = "3" * 64
        review["semantic_content_sha256"] = "4" * 64
        common.write_json(workspace / "reviews/en/translation_review.json", review)
        return {"review_sha256": "3" * 64}
    monkeypatch.setattr(wf, "finalize_translation_review", finalize_translation)

    pass_calls = []
    def semantic_pass(*args, **kwargs):
        pass_calls.append(kwargs["method_family"])
        pass_no = len(pass_calls)
        status = "converged" if pass_no == 2 else "in_progress"
        common.write_json(workspace / "reviews/en/semantic_convergence_review.json", {
            "schema": "wikidebia-semantic-convergence-review-1.1", "schema_version": "1.1",
            "status": status, "passes": [{"pass_id": f"P{pass_no:03d}"}], "receipt_sha256": "5" * 64,
        })
        return {"status": status, "receipt_sha256": "5" * 64}
    monkeypatch.setattr(wf, "record_semantic_pass", semantic_pass)
    calls = []
    monkeypatch.setattr(wf, "apply_translation_review", lambda *a, **k: calls.append("apply") or {"status": "applied"})
    monkeypatch.setattr(wf, "render_workspace", lambda *a, **k: calls.append("render") or {"rendered_copy_tree_sha256": "6" * 64})
    monkeypatch.setattr(wf, "release_workspace", lambda *a, **k: calls.append("release") or {"archive": "outgoing/debat_test_release.zip", "status": "release_ready"})
    monkeypatch.setattr(wf, "publish_final_release", lambda *a, **k: calls.append("final_publish") or {"status": "published", "installed_release": {"path": "corpus/debat_test"}, "receipt_sha256": "7" * 64})

    # Metadata stop.
    state = wf._mechanical_advance(project, state)
    assert state["pending_review"]["review_type"] == "fr_metadata_review"
    metadata_zip = project / state["pending_review"]["package_path"]
    state = wf.import_review(project, "debat_test", metadata_zip)
    assert state["pending_review"]["review_type"] == "fr_content_review"

    # French content stop.
    content_zip = project / state["pending_review"]["package_path"]
    state = wf.import_review(project, "debat_test", content_zip)
    assert state["pending_review"]["review_type"] == "en_translation_review"

    # English translation stop.
    translation_zip = project / state["pending_review"]["package_path"]
    state = wf.import_review(project, "debat_test", translation_zip)
    assert state["pending_review"]["review_type"] == "semantic_convergence_1"

    # First independent semantic pass.
    sem1 = project / state["pending_review"]["package_path"]
    sem1_return = tmp_path / "semantic-pass-1.zip"
    returned_semantic_zip(sem1, sem1_return, family="proposition_by_proposition", method="Comparaison proposition par proposition", errors=0)
    state = wf.import_review(project, "debat_test", sem1_return)
    assert state["pending_review"]["review_type"] == "semantic_convergence_2"

    # Second distinct semantic pass triggers all remaining mechanics.
    sem2 = project / state["pending_review"]["package_path"]
    sem2_return = tmp_path / "semantic-pass-2.zip"
    returned_semantic_zip(sem2, sem2_return, family="risk_marker_review", method="Relecture des marqueurs de risque", errors=0)
    state = wf.import_review(project, "debat_test", sem2_return)
    assert state["status"] == "published"
    assert state["phase"] == "published"
    assert pass_calls == ["proposition_by_proposition", "risk_marker_review"]
    assert calls == ["apply", "render", "release", "final_publish"]
    assert state["release"]["archive"] == "outgoing/debat_test_release.zip"


def test_semantic_error_reopens_translation_and_restarts_two_pass_cycle(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    work_id = "EDIT-20260811-001"
    workspace = make_full_workspace(project, work_id=work_id)
    review = common.load_json(workspace / "reviews/en/translation_review.json", "translation")
    review.update({"status": "approved", "review_sha256": "3" * 64, "semantic_content_sha256": "4" * 64, "finalized_at": "2026-08-11"})
    common.write_json(workspace / "reviews/en/translation_review.json", review)
    state = {
        "schema": wf.WORKFLOW_SCHEMA, "schema_version": "1.0",
        "normative_revision": wf.NORM_VERSION, "validator_version": wf.VALIDATOR_VERSION, "kit_version": wf.KIT_VERSION,
        "debate_id": "debat_test", "debate_title": "Débat test ?", "short_code": "TEST",
        "phase": "semantic_convergence_1", "status": "running", "work_id": work_id,
        "pending_review": None, "snapshot_path": None, "force_refresh": False,
        "created_at": "2026-08-11T12:00:00+02:00", "updated_at": "2026-08-11T12:00:00+02:00",
    }
    wf._save_workflow(project, state)
    monkeypatch.setattr(wf, "record_semantic_pass", lambda *a, **k: {"status": "requires_revision"})
    monkeypatch.setattr(wf, "prepare_translation_review", lambda *a, **k: {"status": "prepared"})

    state = wf._mechanical_advance(project, state)
    first = project / state["pending_review"]["package_path"]
    returned = tmp_path / "semantic-with-error.zip"
    returned_semantic_zip(first, returned, family="field_boundary_review", method="Relecture des frontières de champs", errors=1, findings=[{"field": "summary", "issue": "Perte de modalité"}])
    state = wf.import_review(project, "debat_test", returned)
    assert state["pending_review"]["review_type"] == "en_translation_correction"
    correction_zip = project / state["pending_review"]["package_path"]
    with zipfile.ZipFile(correction_zip) as z:
        assert "context/reviews/en/semantic_convergence_findings.json" in z.namelist()
        findings = json.loads(z.read("context/reviews/en/semantic_convergence_findings.json"))
        assert findings["new_certain_errors"] == 1
    reopened = common.load_json(workspace / "reviews/en/translation_review.json", "translation")
    assert reopened["status"] == "draft"
    assert "review_sha256" not in reopened
    assert not (workspace / "reviews/en/semantic_convergence_review.json").exists()

    def finalize_translation(*args, **kwargs):
        fixed = common.load_json(workspace / "reviews/en/translation_review.json", "translation")
        fixed.update({"status": "approved", "review_sha256": "7" * 64, "semantic_content_sha256": "8" * 64})
        common.write_json(workspace / "reviews/en/translation_review.json", fixed)
        return {"review_sha256": "7" * 64}
    monkeypatch.setattr(wf, "finalize_translation_review", finalize_translation)
    state = wf.import_review(project, "debat_test", correction_zip)
    assert state["pending_review"]["review_type"] == "semantic_convergence_1"


def test_resume_after_promotion_interruption_reuses_promoted_corpus_and_preallocated_work_id(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    corpus = project / "corpus/debat_test"
    common.write_json(corpus / wf.REVIEW_ENVELOPE, {"review_sha256": "a" * 64})
    state = {
        "schema": wf.WORKFLOW_SCHEMA, "schema_version": "1.0",
        "normative_revision": wf.NORM_VERSION, "validator_version": wf.VALIDATOR_VERSION, "kit_version": wf.KIT_VERSION,
        "debate_id": "debat_test", "debate_title": "Débat test ?", "short_code": "TEST",
        "phase": "promote_and_workspace", "status": "running", "work_id": None,
        "pending_review": None, "snapshot_path": None, "force_refresh": False,
        "created_at": "2026-08-11T12:00:00+02:00", "updated_at": "2026-08-11T12:00:00+02:00",
    }
    wf._save_workflow(project, state)
    monkeypatch.setattr(wf, "graph_review_sha256", lambda review: "a" * 64)
    created = []
    def create_ws(root, debate_id, work_id):
        created.append(work_id)
        common.write_json(root / ".state/editorial-workspaces" / debate_id / work_id / "workspace.json", {"debate_id": debate_id, "work_id": work_id})
        return {"work_id": work_id}
    monkeypatch.setattr(wf, "create_workspace", create_ws)
    monkeypatch.setattr(wf, "_prepare_metadata_package", lambda root, s: s)
    result = wf._mechanical_advance(project, state)
    assert created and created[0].startswith("EDIT-")
    persisted = wf._load_workflow(project, "debat_test")
    assert persisted["work_id"] == created[0]
    assert result["phase"] == "fr_metadata_review"


def test_outgoing_is_private_for_git_and_root_template():
    assert manage.forbidden_git_path("outgoing/revenu_de_base_graph_review.zip")
    assert "/outgoing/" in manage.REQUIRED_GITIGNORE_RULES
    template = (Path(__file__).resolve().parents[1] / "root_template/.gitignore").read_text(encoding="utf-8")
    assert "/outgoing/" in {line.strip() for line in template.splitlines()}


def test_review_registry_covers_every_orchestrated_external_stop():
    assert set(wf.REVIEW_TYPES) == {
        "graph_review", "graph_correction", "fr_metadata_review", "fr_content_review", "en_translation_review",
        "en_translation_correction", "en_documentation_correction", "semantic_convergence_1", "semantic_convergence_2",
    }


def test_initial_validation_block_is_explained_packaged_and_retryable(tmp_path: Path, monkeypatch):
    from test_wikidebia_corpus_init import make_extraction

    project = tmp_path / "project"
    project.mkdir()
    source = make_extraction(tmp_path / "source")

    def failed_validator(project_root: Path, package: Path):
        reports = package / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        report_json = reports / "initial_validation.json"
        common.write_json(report_json, {
            "schema": "wikidebia-validator-report-1.0",
            "result": "failed",
            "summary": {"errors": 1, "warnings": 0, "infos": 0},
            "findings": [{
                "code": "WDV-GRA-005", "level": "ERROR",
                "message": "Cycle détecté : A0001 -> A0002 -> A0001",
                "path": "data/registre_debat.json", "pointer": None, "details": {},
            }],
        })
        (reports / "initial_validation.txt").write_text("cycle\n", encoding="utf-8")
        common.write_json(reports / "initial_validation_execution.json", {"status": "failed"})
        return {"status": "failed", "report_json": str(report_json)}

    monkeypatch.setattr(wf, "run_initial_validator", failed_validator)
    state = wf.start_workflow(project, "Débat test ?", debate_id="debat_test", short_code="TEST", snapshot=source)
    assert state["status"] == "blocked_technical"
    assert state["phase"] == "initial_validation_blocked"
    assert state["last_block"]["errors"][0]["code"] == "WDV-GRA-005"
    diagnostic = project / state["last_block"]["diagnostic_path"]
    assert diagnostic.is_file()
    with zipfile.ZipFile(diagnostic) as z:
        names = set(z.namelist())
        assert "DIAGNOSTIC_PACKAGE.json" in names
        assert "context/reports/initial_validation.json" in names
        assert "context/data/registre_debat.json" in names
        assert not any("private" in name or "secret" in name for name in names)
        manifest = json.loads(z.read("DIAGNOSTIC_PACKAGE.json"))
        assert manifest["schema"] == wf.DIAGNOSTIC_SCHEMA
        assert manifest["error_count"] == 1

    monkeypatch.setattr(wf, "run_initial_validator", lambda project_root, package: {"status": "passed"})
    resumed = wf.start_workflow(project, "Débat test ?", debate_id="debat_test")
    assert resumed["status"] == "awaiting_review"
    assert resumed["pending_review"]["review_type"] == "graph_review"
    assert "last_block" not in resumed


def test_workflow_derives_rdb_short_code_from_explicit_debate_id(tmp_path: Path, monkeypatch):
    from test_wikidebia_corpus_init import make_extraction
    project = tmp_path / "project"
    project.mkdir()
    source = make_extraction(tmp_path / "source")
    monkeypatch.setattr(wf, "run_initial_validator", lambda project_root, package: {"status": "passed"})

    state = wf.start_workflow(
        project,
        "Un revenu de base doit-il être instauré ?",
        debate_id="revenu_de_base",
        snapshot=source,
    )

    assert state["short_code"] == "RDB"
    manifest = common.load_json(project / ".state/corpus-builds/revenu_de_base/manifest.json", "manifest")
    assert manifest["short_code"] == "RDB"
    assert state["pending_review"]["review_type"] == "graph_review"


def test_existing_incomplete_workflow_accepts_explicit_short_code_without_reset(tmp_path: Path, monkeypatch):
    from test_wikidebia_corpus_init import make_extraction
    project = tmp_path / "project"
    project.mkdir()
    source = make_extraction(project / "source")
    state = {
        "schema": wf.WORKFLOW_SCHEMA, "schema_version": "1.0", "debate_id": "revenu_de_base",
        "debate_title": "Un revenu de base doit-il être instauré ?", "short_code": None,
        "phase": "initialize_graph", "status": "running", "work_id": None, "pending_review": None,
        "snapshot_path": "source", "force_refresh": False,
        "created_at": "2026-08-11T12:00:00+02:00", "updated_at": "2026-08-11T12:00:00+02:00",
    }
    wf._save_workflow(project, state)
    monkeypatch.setattr(wf, "run_initial_validator", lambda root, package: {"status": "passed"})

    resumed = wf.start_workflow(
        project,
        "Un revenu de base doit-il être instauré ?",
        debate_id="revenu_de_base",
        short_code="RDB",
    )

    assert resumed["short_code"] == "RDB"
    assert resumed["pending_review"]["review_type"] == "graph_review"


def test_existing_incomplete_workflow_repairs_missing_short_code_automatically(tmp_path: Path, monkeypatch):
    from test_wikidebia_corpus_init import make_extraction
    project = tmp_path / "project"
    project.mkdir()
    source = make_extraction(project / "source")
    state = {
        "schema": wf.WORKFLOW_SCHEMA, "schema_version": "1.0", "debate_id": "revenu_de_base",
        "debate_title": "Un revenu de base doit-il être instauré ?", "short_code": None,
        "phase": "initialize_graph", "status": "running", "work_id": None, "pending_review": None,
        "snapshot_path": "source", "force_refresh": False,
        "created_at": "2026-08-11T12:00:00+02:00", "updated_at": "2026-08-11T12:00:00+02:00",
    }
    wf._save_workflow(project, state)
    monkeypatch.setattr(wf, "run_initial_validator", lambda root, package: {"status": "passed"})

    resumed = wf.start_workflow(
        project,
        "Un revenu de base doit-il être instauré ?",
        debate_id="revenu_de_base",
    )

    assert resumed["short_code"] == "RDB"
    assert resumed["pending_review"]["review_type"] == "graph_review"


def test_existing_workflow_refuses_conflicting_explicit_short_code(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    state = {
        "schema": wf.WORKFLOW_SCHEMA, "schema_version": "1.0", "debate_id": "revenu_de_base",
        "debate_title": "Un revenu de base doit-il être instauré ?", "short_code": "RDB",
        "phase": "initialize_graph", "status": "running", "work_id": None, "pending_review": None,
        "snapshot_path": None, "force_refresh": False,
        "created_at": "2026-08-11T12:00:00+02:00", "updated_at": "2026-08-11T12:00:00+02:00",
    }
    wf._save_workflow(project, state)

    with pytest.raises(wf.WorkflowError, match="utilise déjà le short_code RDB"):
        wf.start_workflow(
            project,
            "Un revenu de base doit-il être instauré ?",
            debate_id="revenu_de_base",
            short_code="OTHER",
        )


def test_mechanical_failure_rolls_back_review_consumption_and_created_artifacts(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    base = make_base(project)
    state = make_state(project, base)
    pending = wf.create_review_package(
        project, state, review_type="graph_review", base=base,
        editable_paths=["reviews/edit.json"], context_paths=["data/context.json"],
    )
    original = project / pending["package_path"]
    returned = tmp_path / "returned-mechanical-failure.zip"
    rewrite_zip(
        original, returned,
        lambda root: common.write_json(root / "editable/reviews/edit.json", {"debate_id": "debat_test", "value": "approved"}),
    )

    monkeypatch.setattr(
        wf, "finalize_graph_review",
        lambda project_root, base_path, debate_id: {"status": "approved", "review_sha256": "a" * 64},
    )

    def failing_advance(root: Path, current: dict):
        # Reproduce the dangerous sequence that caused 2.16.5/2.16.6 to consume
        # the review before a workspace failure: promotion + work allocation +
        # persisted phase, followed by an exception.
        corpus = root / "corpus/debat_test"
        corpus.parent.mkdir(parents=True, exist_ok=True)
        base.rename(corpus)
        workspace = root / ".state/editorial-workspaces/debat_test/EDIT-20260811-001"
        workspace.mkdir(parents=True)
        common.write_json(workspace / "workspace.json", {"debate_id": "debat_test", "work_id": "EDIT-20260811-001"})
        promotion = root / ".state/corpus-promotions/debat_test"
        promotion.mkdir(parents=True)
        common.write_json(promotion / "partial.receipt.json", {"status": "partial"})
        (root / "outgoing/partial-next-review.zip").write_bytes(b"partial")
        current["work_id"] = "EDIT-20260811-001"
        current["phase"] = "fr_metadata_review"
        wf._save_workflow(root, current)
        raise RuntimeError("workspace creation failed")

    monkeypatch.setattr(wf, "_mechanical_advance", failing_advance)
    with pytest.raises(RuntimeError, match="workspace creation failed"):
        wf.import_review(project, "debat_test", returned)

    restored = wf._load_workflow(project, "debat_test")
    assert restored["phase"] == "graph_review"
    assert restored["pending_review"]["package_id"] == pending["package_id"]
    assert restored["work_id"] is None
    assert common.load_json(base / "reviews/edit.json", "edit")["value"] == "pending"
    assert not (project / "corpus/debat_test").exists()
    assert not (project / ".state/editorial-workspaces/debat_test/EDIT-20260811-001").exists()
    assert not (project / ".state/corpus-promotions/debat_test/partial.receipt.json").exists()
    assert not (project / "outgoing/partial-next-review.zip").exists()
    assert original.is_file()


def test_manage_review_import_selects_incoming_by_internal_debate_id(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    base = make_base(project)
    state = make_state(project, base)
    pending = wf.create_review_package(
        project, state, review_type="graph_review", base=base,
        editable_paths=["reviews/edit.json"], context_paths=["data/context.json"],
    )
    incoming = project / "incoming"
    incoming.mkdir()
    source = project / pending["package_path"]
    renamed = incoming / "nom-totalement-libre.zip"
    shutil.copy2(source, renamed)
    debate_id, selected = manage.find_review_archive(project)
    assert debate_id == "debat_test"
    assert selected == renamed
    debate_id2, selected2 = manage.find_review_archive(project, "debat_test")
    assert (debate_id2, selected2) == (debate_id, selected)


def test_manage_review_import_requires_debate_id_when_multiple_reviews(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    base = make_base(project)
    state = make_state(project, base)
    first = wf.create_review_package(
        project, state, review_type="graph_review", base=base,
        editable_paths=["reviews/edit.json"], context_paths=["data/context.json"],
    )
    incoming = project / "incoming"
    incoming.mkdir()
    shutil.copy2(project / first["package_path"], incoming / "a.zip")
    # Clone the package and change only the internal debate identity + manifest hash.
    second = incoming / "b.zip"
    rewrite_zip(project / first["package_path"], second, lambda root: _rewrite_package_debate(root, "autre_debat"))
    with pytest.raises(manage.ManagementError, match=r"review-import debat_test"):
        manage.find_review_archive(project)
    assert manage.find_review_archive(project, "autre_debat")[1] == second


def _rewrite_package_debate(root: Path, debate_id: str) -> None:
    path = root / "REVIEW_PACKAGE.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["debate_id"] = debate_id
    data["manifest_sha256"] = wf._package_manifest_hash(data)
    common.write_json(path, data)


def test_fr_content_import_publishes_before_preparing_english(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    base = make_base(project)
    state = make_state(project, base, "fr_content_review")
    state["work_id"] = "EDIT-20260812-001"
    wf._save_workflow(project, state)
    pending = wf.create_review_package(
        project, state, review_type="fr_content_review", base=base,
        editable_paths=["reviews/edit.json"], context_paths=["data/context.json"],
    )
    returned = tmp_path / "returned.zip"
    rewrite_zip(project / pending["package_path"], returned, lambda root: None)
    calls = []
    monkeypatch.setattr(wf, "finalize_content_review", lambda *a, **k: {"review_sha256": "a" * 64})
    monkeypatch.setattr(wf, "apply_content_review", lambda *a, **k: calls.append("apply") or {"status": "fr_content_applied"})
    monkeypatch.setattr(wf, "publish_checkpoint", lambda *a, **k: calls.append("publish") or {"status": "published", "receipt_sha256": "b" * 64})
    def advance(_project, state):
        calls.append("advance")
        assert state["phase"] == "en_translation_review"
        return state
    monkeypatch.setattr(wf, "_mechanical_advance", advance)
    result = wf.import_review(project, "debat_test", returned)
    assert calls == ["apply", "publish", "advance"]
    assert result["french_publication"]["status"] == "published"
    assert result["pending_review"] is None


def test_legacy_pending_english_review_publishes_french_checkpoint_before_resume(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    base = make_base(project)
    state = make_state(project, base, "en_translation_review")
    state["work_id"] = "EDIT-20260812-001"
    state["pending_review"] = {
        "review_type": "en_translation_review",
        "package_id": "legacy-en-package",
        "package_path": "outgoing/debat_test_en_translation_review.zip",
    }
    state.pop("french_publication", None)
    wf._save_workflow(project, state)
    calls = []
    monkeypatch.setattr(
        wf,
        "publish_checkpoint",
        lambda *a, **k: calls.append("publish") or {"status": "published", "receipt_sha256": "c" * 64},
    )
    resumed = wf._mechanical_advance(project, state)
    assert calls == ["publish", "publish"]
    assert resumed["pending_review"]["review_type"] == "en_translation_review"
    assert resumed["french_graph_publication"]["status"] == "published"
    assert resumed["french_content_publication"]["status"] == "published"
    saved = wf._load_workflow(project, "debat_test")
    assert saved["french_publication"]["receipt_sha256"] == "c" * 64


def test_workflow_resume_records_french_checkpoint_network_failure(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    base = make_base(project)
    state = make_state(project, base)
    state.update({
        "phase": "graph_publication_resume",
        "status": "running",
        "work_id": "EDIT-20261022-001",
        "remote_publication_stage": "graph",
    })
    wf._save_workflow(project, state)

    def fail_remote(_project, _state):
        raise wf.FrenchCheckpointError("Cloudflare 403", remote_execution_started=False)

    monkeypatch.setattr(wf, "_mechanical_advance", fail_remote)
    with pytest.raises(wf.FrenchCheckpointError, match="Cloudflare 403"):
        wf.start_workflow(project, "Débat test ?", debate_id="debat_test")

    saved = wf._load_workflow(project, "debat_test")
    assert saved["phase"] == "graph_publication_resume"
    assert saved["status"] == "blocked_remote_publication"
    assert saved["last_remote_publication_error"] == "Cloudflare 403"
    assert saved["last_remote_publication_execution_started"] is False

    monkeypatch.setattr(wf, "_mechanical_advance", lambda _project, current: current)
    resumed = wf.start_workflow(project, "Débat test ?", debate_id="debat_test")
    assert resumed["status"] == "running"
    assert "last_remote_publication_error" not in resumed
    assert "last_remote_publication_execution_started" not in resumed


def test_failure_after_successful_french_publication_does_not_rollback_sealed_review(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    base = make_base(project)
    state = make_state(project, base, "fr_content_review")
    state["work_id"] = "EDIT-20260812-001"
    wf._save_workflow(project, state)
    pending = wf.create_review_package(
        project, state, review_type="fr_content_review", base=base,
        editable_paths=["reviews/edit.json"], context_paths=["data/context.json"],
    )
    returned = tmp_path / "returned.zip"
    rewrite_zip(project / pending["package_path"], returned, lambda root: None)
    monkeypatch.setattr(wf, "finalize_content_review", lambda *a, **k: {"review_sha256": "a" * 64})
    monkeypatch.setattr(wf, "apply_content_review", lambda *a, **k: {"status": "fr_content_applied"})
    monkeypatch.setattr(wf, "publish_checkpoint", lambda *a, **k: {"status": "published", "receipt_sha256": "d" * 64})
    monkeypatch.setattr(wf, "_mechanical_advance", lambda *a, **k: (_ for _ in ()).throw(wf.WorkflowError("english prepare failed")))
    with pytest.raises(wf.WorkflowError, match="english prepare failed"):
        wf.import_review(project, "debat_test", returned)
    saved = wf._load_workflow(project, "debat_test")
    assert saved["status"] == "blocked_remote_publication"
    assert saved["phase"] == "fr_content_review"
    assert saved["pending_review"]["review_type"] == "fr_content_review"
    assert saved["french_publication"]["status"] == "published"


def _make_french_stage(project: Path, work_id: str, stage: str, *, marker: str) -> Path:
    root = project / ".state/fr-publication/debat_test" / work_id / stage
    (root / "checkpoint-corpus").mkdir(parents=True, exist_ok=True)
    (root / "checkpoint-corpus/marker.txt").write_text(marker, encoding="utf-8")
    common.write_json(root / "checkpoint.json", {"stage": stage, "source_tree_sha256": marker})
    return root


def test_fr_content_prewrite_failure_rolls_back_provisional_checkpoint_and_keeps_graph(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    base = make_base(project)
    state = make_state(project, base, "fr_content_review")
    state["work_id"] = "EDIT-20260812-001"
    wf._save_workflow(project, state)
    graph = _make_french_stage(project, state["work_id"], "graph", marker="published-graph")
    common.write_json(graph / "publication-receipt.json", {"stage": "graph", "status": "published"})
    graph_before = {p.relative_to(graph).as_posix(): p.read_bytes() for p in graph.rglob("*") if p.is_file()}
    pending = wf.create_review_package(
        project, state, review_type="fr_content_review", base=base,
        editable_paths=["reviews/edit.json"], context_paths=["data/context.json"],
    )
    returned = tmp_path / "returned.zip"
    rewrite_zip(project / pending["package_path"], returned, lambda root: None)
    monkeypatch.setattr(wf, "finalize_content_review", lambda *a, **k: {"review_sha256": "a" * 64})
    monkeypatch.setattr(wf, "apply_content_review", lambda *a, **k: {"status": "fr_content_applied"})

    def fail_before_remote(project_root, debate_id, work_id, *, stage):
        assert stage == "content"
        content_stage = _make_french_stage(project_root, work_id, stage, marker="attempt-A")
        common.write_json(content_stage / "remote-update-config.json", {"attempt": "A"})
        # Reproduce RemoteUpdatePlanner.build_plan() failing during validator execution:
        # there is deliberately no executable update-plan and no remote receipt.
        raise RuntimeError("validation documentaire refusée")

    monkeypatch.setattr(wf, "publish_checkpoint", fail_before_remote)
    with pytest.raises(RuntimeError, match="validation documentaire refusée"):
        wf.import_review(project, "debat_test", returned)

    content_stage = project / ".state/fr-publication/debat_test" / state["work_id"] / "content"
    assert not content_stage.exists()
    graph_after = {p.relative_to(graph).as_posix(): p.read_bytes() for p in graph.rglob("*") if p.is_file()}
    assert graph_after == graph_before
    saved = wf._load_workflow(project, "debat_test")
    assert saved["pending_review"]["review_type"] == "fr_content_review"


def test_fr_content_two_local_failures_leave_no_false_checkpoint_lock(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    base = make_base(project)
    state = make_state(project, base, "fr_content_review")
    state["work_id"] = "EDIT-20260812-001"
    wf._save_workflow(project, state)
    _make_french_stage(project, state["work_id"], "graph", marker="published-graph")
    pending = wf.create_review_package(
        project, state, review_type="fr_content_review", base=base,
        editable_paths=["reviews/edit.json"], context_paths=["data/context.json"],
    )
    returned = tmp_path / "returned.zip"
    rewrite_zip(project / pending["package_path"], returned, lambda root: None)
    monkeypatch.setattr(wf, "finalize_content_review", lambda *a, **k: {"review_sha256": "a" * 64})
    monkeypatch.setattr(wf, "apply_content_review", lambda *a, **k: {"status": "fr_content_applied"})
    attempts = {"count": 0}

    def fail_twice(project_root, debate_id, work_id, *, stage):
        attempts["count"] += 1
        content_stage = _make_french_stage(project_root, work_id, stage, marker=f"attempt-{attempts['count']}")
        common.write_json(content_stage / "remote-update-config.json", {"attempt": attempts["count"]})
        raise RuntimeError(f"local failure {attempts['count']}")

    monkeypatch.setattr(wf, "publish_checkpoint", fail_twice)
    for expected in (1, 2):
        with pytest.raises(RuntimeError, match=f"local failure {expected}"):
            wf.import_review(project, "debat_test", returned)
        assert not (project / ".state/fr-publication/debat_test" / state["work_id"] / "content").exists()
    assert attempts["count"] == 2


def test_fr_content_remote_execution_failure_preserves_checkpoint_plan_and_receipt_state(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    base = make_base(project)
    state = make_state(project, base, "fr_content_review")
    state["work_id"] = "EDIT-20260812-001"
    wf._save_workflow(project, state)
    _make_french_stage(project, state["work_id"], "graph", marker="published-graph")
    pending = wf.create_review_package(
        project, state, review_type="fr_content_review", base=base,
        editable_paths=["reviews/edit.json"], context_paths=["data/context.json"],
    )
    returned = tmp_path / "returned.zip"
    rewrite_zip(project / pending["package_path"], returned, lambda root: None)
    monkeypatch.setattr(wf, "finalize_content_review", lambda *a, **k: {"review_sha256": "a" * 64})
    monkeypatch.setattr(wf, "apply_content_review", lambda *a, **k: {"status": "fr_content_applied"})

    def fail_after_remote_started(project_root, debate_id, work_id, *, stage):
        content_stage = _make_french_stage(project_root, work_id, stage, marker="remote-started")
        common.write_json(content_stage / "update-plan.json", {"plan_sha256": "p" * 64, "operations": {"update": [{"page_id": "A0001"}]}})
        common.write_json(content_stage / "remote-execution-state.json", {"status": "started"})
        raise wf.FrenchCheckpointError("remote write interrupted", remote_execution_started=True)

    monkeypatch.setattr(wf, "publish_checkpoint", fail_after_remote_started)
    with pytest.raises(wf.FrenchCheckpointError, match="remote write interrupted"):
        wf.import_review(project, "debat_test", returned)

    content_stage = project / ".state/fr-publication/debat_test" / state["work_id"] / "content"
    assert (content_stage / "checkpoint-corpus/marker.txt").read_text(encoding="utf-8") == "remote-started"
    assert (content_stage / "update-plan.json").is_file()
    assert (content_stage / "remote-execution-state.json").is_file()
    saved = wf._load_workflow(project, "debat_test")
    assert saved["status"] == "blocked_remote_publication"
    assert saved["phase"] == "fr_content_review"
    assert saved["pending_review"]["review_type"] == "fr_content_review"


def test_post_convergence_title_preflight_reopens_translation_correction(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    workspace = project / "workspace"
    (workspace / "reviews/en").mkdir(parents=True)
    common.write_json(workspace / "reviews/en/translation_review.json", {
        "schema": "wikidebia-translation-review-1.4",
        "debate_id": "debat_test",
        "work_id": "W1",
        "status": "approved",
        "review_sha256": "sealed-review",
        "semantic_content_sha256": "old-semantic-hash",
        "finalized_at": "2026-08-18T20:00:00+02:00",
        "final_values": {
            "debate": {"canonical_title": "Should basic income be introduced?"},
            "arguments": [{
                "id": "A0004",
                "canonical_title": "Basic income is good for the national economy",
                "displayed_title": "A good thing for the country’s economy",
            }],
        },
    })
    common.write_json(workspace / "reviews/en/semantic_convergence_review.json", {
        "schema": "wikidebia-semantic-convergence-review-1.1", "status": "converged"
    })
    common.write_json(workspace / "workspace.json", {
        "status": "en_translation_review_finalized",
        "english_translation_review": {"status": "finalized"},
        "workspace_sha256": "old",
    })

    state = {
        "schema": wf.WORKFLOW_SCHEMA,
        "schema_version": "1.0",
        "debate_id": "debat_test",
        "debate_title": "Débat test ?",
        "phase": "apply_render_release",
        "status": "running",
        "work_id": "W1",
        "pending_review": None,
        "french_graph_publication": {"status": "no_changes"},
        "french_content_publication": {"status": "no_changes"},
        "created_at": "2026-08-18T20:00:00+02:00",
        "updated_at": "2026-08-18T20:00:00+02:00",
    }
    wf._save_workflow(project, state)

    def fake_current_workspace_meta(_project, _state):
        return workspace, common.load_json(workspace / "workspace.json", "workspace")

    def fake_prepare_translation(_project, current_state, *, correction=False):
        assert correction is True
        current_state["pending_review"] = {
            "review_type": "en_translation_correction",
            "package_path": "outgoing/debat_test_en_translation_correction.zip",
        }
        wf._save_workflow(_project, current_state)
        return current_state["pending_review"]

    monkeypatch.setattr(wf, "_current_workspace_meta", fake_current_workspace_meta)
    monkeypatch.setattr(wf, "workspace_receipt_hash", lambda meta: "new-workspace-hash")
    monkeypatch.setattr(wf, "_prepare_translation_package", fake_prepare_translation)
    monkeypatch.setattr(wf, "apply_translation_review", lambda *a, **k: (_ for _ in ()).throw(AssertionError("application must not run")))

    result = wf._mechanical_advance(project, state)
    assert result["phase"] == "en_translation_correction"
    assert result["pending_review"]["review_type"] == "en_translation_correction"
    reopened = common.load_json(workspace / "reviews/en/translation_review.json", "review")
    assert reopened["status"] == "draft"
    assert "review_sha256" not in reopened
    assert "semantic_content_sha256" not in reopened
    assert not (workspace / "reviews/en/semantic_convergence_review.json").exists()
    findings = common.load_json(workspace / "reviews/en/semantic_convergence_findings.json", "findings")
    assert findings["source_review_type"] == "post_convergence_title_preflight"
    assert findings["new_certain_errors"] == 1
    assert findings["findings"][0]["entity_id"] == "A0004"
    assert findings["findings"][0]["field"] == "displayed_title"


def test_21627_post_convergence_documentary_preflight_opens_sources_only_correction(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    workspace = project / "workspace"
    (workspace / "reviews/en").mkdir(parents=True)
    (workspace / "data").mkdir(parents=True)
    common.write_json(workspace / "data/sources_en_working.json", {"schema": "wikidebia-en-source-registry-working-1.0", "debate_id": "debat_test", "sources": []})
    common.write_json(workspace / "reviews/en/translation_review.json", {
        "schema": "wikidebia-en-translation-review-1.1",
        "debate_id": "debat_test", "work_id": "W1", "status": "approved",
        "review_sha256": "sealed-review", "semantic_content_sha256": "same-semantic",
        "finalized_at": "2026-08-18T23:00:00+02:00",
        "arguments": [], "debate": {},
        "final_values": {
            "debate": {"canonical_title": "Should basic income be introduced?"},
            "arguments": [],
            "sources": [{
                "id": "S10001", "type": "bibliography", "language": "en",
                "metadata": {"authors": ["Author"], "work": "Broad work"},
                "verification": {"status": "verified", "language_verified": True},
                "usage": [{"page_id": "debat_test", "language": "en", "role": "neutral_reference", "selection_reason": "Broad source selected for the debate."}],
                "deduplication_key": "s10001",
            }],
        },
    })
    common.write_json(workspace / "reviews/en/semantic_convergence_review.json", {"schema": "wikidebia-semantic-convergence-review-1.1", "status": "converged"})
    common.write_json(workspace / "workspace.json", {"status": "en_translation_review_finalized", "english_translation_review": {"status": "finalized"}, "workspace_sha256": "old"})
    state = {
        "schema": wf.WORKFLOW_SCHEMA, "schema_version": "1.0", "debate_id": "debat_test",
        "debate_title": "Débat test ?", "phase": "apply_render_release", "status": "running", "work_id": "W1",
        "pending_review": None, "french_graph_publication": {"status": "no_changes"},
        "french_content_publication": {"status": "no_changes"},
        "created_at": "2026-08-18T23:00:00+02:00", "updated_at": "2026-08-18T23:00:00+02:00",
    }
    wf._save_workflow(project, state)

    monkeypatch.setattr(wf, "_current_workspace_meta", lambda *_: (workspace, common.load_json(workspace / "workspace.json", "workspace")))
    monkeypatch.setattr(wf, "workspace_receipt_hash", lambda meta: "new-workspace-hash")

    def fake_prepare_docs(_project, current_state):
        current_state["pending_review"] = {"review_type": "en_documentation_correction", "package_path": "outgoing/docs.zip"}
        wf._save_workflow(_project, current_state)
        return current_state["pending_review"]

    monkeypatch.setattr(wf, "_prepare_documentation_correction_package", fake_prepare_docs)
    monkeypatch.setattr(wf, "apply_translation_review", lambda *a, **k: (_ for _ in ()).throw(AssertionError("application must not run")))

    result = wf._mechanical_advance(project, state)
    assert result["phase"] == "en_documentation_correction"
    assert result["pending_review"]["review_type"] == "en_documentation_correction"
    findings = common.load_json(workspace / "reviews/en/semantic_convergence_findings.json", "findings")
    assert findings["source_review_type"] == "post_convergence_documentary_preflight"
    issues = {row["issue"] for row in findings["findings"]}
    assert "debate_bibliography_document_kind_missing_or_invalid" in issues
    assert "debate_bibliography_scope_missing_or_invalid" in issues
    reopened = common.load_json(workspace / "reviews/en/translation_review.json", "review")
    assert reopened["status"] == "draft"
    assert "final_values" not in reopened
    assert not (workspace / "reviews/en/semantic_convergence_review.json").exists()


def test_release_ready_resume_enters_final_publication_without_rerunning_semantic_or_render(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    work_id = "EDIT-20260811-001"
    workspace = make_full_workspace(project, work_id=work_id)
    (workspace / "release-copy").mkdir(exist_ok=True)
    state = {
        "schema": wf.WORKFLOW_SCHEMA, "schema_version": "1.0",
        "normative_revision": wf.NORM_VERSION, "validator_version": wf.VALIDATOR_VERSION, "kit_version": wf.KIT_VERSION,
        "debate_id": "debat_test", "debate_title": "Débat test ?", "short_code": "TEST",
        "phase": "release_ready", "status": "release_ready", "work_id": work_id,
        "pending_review": None, "snapshot_path": None, "force_refresh": False,
        "release": {"archive": ".state/corpus-releases/debat_test/EDIT-20260811-001/debat_test.zip"},
        "created_at": "2026-08-11T12:00:00+02:00", "updated_at": "2026-08-11T12:00:00+02:00",
    }
    wf._save_workflow(project, state)
    calls = []
    monkeypatch.setattr(wf, "publish_final_release", lambda *a, **k: calls.append("final") or {
        "status": "published", "installed_release": {"path": "corpus/debat_test"}, "receipt_sha256": "8" * 64,
    })
    monkeypatch.setattr(wf, "render_workspace", lambda *a, **k: (_ for _ in ()).throw(AssertionError("render must not rerun")))
    monkeypatch.setattr(wf, "release_workspace", lambda *a, **k: (_ for _ in ()).throw(AssertionError("release must not rerun")))
    result = wf._mechanical_advance(project, state)
    assert result["status"] == "published"
    assert result["phase"] == "published"
    assert calls == ["final"]


def test_final_publication_conflict_is_persisted_without_reopening_reviews(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    work_id = "EDIT-20260811-001"
    workspace = make_full_workspace(project, work_id=work_id)
    (workspace / "release-copy").mkdir(exist_ok=True)
    state = {
        "schema": wf.WORKFLOW_SCHEMA, "schema_version": "1.0",
        "normative_revision": wf.NORM_VERSION, "validator_version": wf.VALIDATOR_VERSION, "kit_version": wf.KIT_VERSION,
        "debate_id": "debat_test", "debate_title": "Débat test ?", "short_code": "TEST",
        "phase": "final_publication", "status": "final_publication", "work_id": work_id,
        "pending_review": None, "snapshot_path": None, "force_refresh": False,
        "created_at": "2026-08-11T12:00:00+02:00", "updated_at": "2026-08-11T12:00:00+02:00",
    }
    wf._save_workflow(project, state)
    monkeypatch.setattr(wf, "publish_final_release", lambda *a, **k: (_ for _ in ()).throw(
        wf.FinalPublicationError("collision anglaise", remote_execution_started=False)
    ))
    result = wf._mechanical_advance(project, state)
    assert result["status"] == "blocked_final_publication"
    assert result["phase"] == "final_publication"
    assert result["pending_review"] is None
    assert result["final_publication"]["remote_execution_started"] is False
    assert "collision anglaise" in result["final_publication"]["error"]
