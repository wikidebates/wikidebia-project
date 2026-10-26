from pathlib import Path
import json
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import wikidebia_editorial_review as editorial
import wikidebia_content_review as content
import wikidebia_french_checkpoint as checkpoint
import wikidebia_graph_actions as graph_actions
import wikidebia_review_workflow as workflow
from test_wikidebia_editorial_review import make_workspace, complete_review
from test_wikidebia_content_review import complete_content_review, make_metadata_applied


def _title_applied(tmp_path: Path):
    project, workspace, work_id = make_workspace(tmp_path)
    complete_review(workspace)
    finalized = editorial.finalize_title_review(project, "debat_test", work_id)
    editorial.apply_title_review(project, "debat_test", work_id, finalized["review_sha256"])
    return project, workspace, work_id


def test_title_checkpoint_does_not_publish_classification_changes(tmp_path: Path):
    project, workspace, work_id = _title_applied(tmp_path)
    cp = checkpoint.build_checkpoint(project, "debat_test", work_id, stage="graph")
    text = (cp / "output/fr/arguments/A0001.wiki").read_text(encoding="utf-8")
    # complete_review proposed extra keywords, but the graph/title checkpoint
    # must preserve the imported classification verbatim.
    assert "|mots-clés=test" in text
    assert "preuve, raisonnement" not in text
    debate = (cp / "output/fr/debate/debate.wiki").read_text(encoding="utf-8")
    assert "La démonstration A soutient explicitement la proposition du débat test" in debate
    manifest = json.loads((cp / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["translation_status"]["en"] == "deferred"
    receipt = json.loads((project / ".state/fr-publication/debat_test" / work_id / "graph/checkpoint.json").read_text(encoding="utf-8"))
    assert receipt["stage"] == "graph"
    delta = json.loads((cp / "data/fr_graph_checkpoint_delta.json").read_text(encoding="utf-8"))
    assert delta["status"] == "passed"
    assert {row["page_id"] for row in delta["pages"]} == {"debat_test", "A0001", "A0002", "A0003", "A0004"}
    assert all(row["status"] == "verified" for row in delta["pages"])


def test_graph_checkpoint_omits_empty_relation_parameters(tmp_path: Path):
    project, _workspace, work_id = _title_applied(tmp_path)
    cp = checkpoint.build_checkpoint(project, "debat_test", work_id, stage="graph")

    for path in (cp / "output/fr/arguments").glob("*.wiki"):
        text = path.read_text(encoding="utf-8")
        assert "|justifications=\n" not in text
        assert "|objections=\n" not in text


def test_depth_frontier_identification_is_explicit_and_bounded():
    assert checkpoint._depth_frontier_node_ids({
        "graph": {
            "depth_policy": {
                "limit_policy": "bounded",
                "frontier_node_ids": ["A0003", "A0004"],
            }
        }
    }) == {"A0003", "A0004"}
    assert checkpoint._depth_frontier_node_ids({
        "graph": {"depth_policy": {"limit_policy": "unbounded"}}
    }) == set()


def test_graph_checkpoint_preserves_out_of_scope_relations_on_depth_frontier(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    source = workspace / "reviewed-copy"
    import_path = source / "imports/fr/arguments/A0003.wiki"
    historical_relation = (
        "{{Justification|page=Hors périmètre|"
        "titre-affiché=Relation historique hors périmètre}}"
    )
    text = graph_actions._set_optional_parameter_value(
        import_path.read_text(encoding="utf-8"),
        "argument",
        "justifications",
        historical_relation,
    )
    text = graph_actions._set_optional_parameter_value(
        text, "argument", "titre-affiché", "Libellé historique de la page",
    )
    text = graph_actions._set_optional_parameter_value(
        text, "argument", "citations",
        "{{Citation|citation=Texte historique.\u00a0|auteurs=Autrice}}",
    )
    text = graph_actions._set_optional_parameter_value(
        text, "argument", "interlangue",
        "{{Lien interlangue|langue=en|page=Historical argument}}",
    )
    import_path.write_text(text, encoding="utf-8", newline="\n")

    provenance_path = source / "data/import_provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    row = next(entry for entry in provenance["pages"] if entry.get("page_id") == "A0003")
    row["sha256"] = checkpoint.sha256_file(import_path)
    row["size_bytes"] = import_path.stat().st_size
    provenance_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for relative in ("data/registre_debat.json", "graph/graphe_argumentatif.json"):
        path = source / relative
        payload = json.loads(path.read_text(encoding="utf-8"))
        graph = payload["graph"] if relative.startswith("data/") else payload
        graph["depth_policy"] = {
            "limit_policy": "bounded",
            "maximum_observed": 2,
            "maximum_edge_depth": 1,
            "frontier_node_ids": ["A0003"],
            "relations_omitted_at_frontier": 1,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    workspace_path = workspace / "workspace.json"
    metadata = json.loads(workspace_path.read_text(encoding="utf-8"))
    metadata["reviewed_copy"]["tree_sha256"] = editorial.full_tree_sha256(source)
    metadata["workspace_sha256"] = None
    metadata["workspace_sha256"] = editorial.workspace_receipt_hash(metadata)
    workspace_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    cp = checkpoint.build_checkpoint(project, "debat_test", work_id, stage="graph")
    output = (cp / "output/fr/arguments/A0003.wiki").read_text(encoding="utf-8")
    assert historical_relation in output

    content.prepare_review(project, "debat_test", work_id)
    complete_content_review(workspace)
    finalized = content.finalize_review(project, "debat_test", work_id)
    content.apply_review(project, "debat_test", work_id, finalized["review_sha256"])
    content_cp = checkpoint.build_checkpoint(project, "debat_test", work_id, stage="content")
    content_output = (content_cp / "output/fr/arguments/A0003.wiki").read_text(encoding="utf-8")
    assert historical_relation in content_output
    assert "|titre-affiché=Libellé historique de la page" in content_output
    assert "|citation=Texte historique.\u00a0" in content_output
    assert "|auteurs=Autrice" in content_output
    assert "|interlangue={{Lien interlangue|langue=en|page=Historical argument}}" in content_output
    assert "|justifications=\n" not in content_output
    assert "|objections=\n" not in content_output
    command = [
        sys.executable, "-I", str(project / "validator/scripts/wikidebia_validate.py"),
        "validate", str(content_cp),
    ]
    for scope in checkpoint.CONTENT_VALIDATION_SCOPES:
        command.extend(["--scope", scope])
    command.extend(["--format", "json"])
    validation = subprocess.run(
        command, cwd=project / "validator", text=True, capture_output=True, check=False,
    )
    assert validation.returncode == 0, validation.stdout + validation.stderr
def test_checkpoint_wraps_remote_plan_connectivity_failure(tmp_path: Path, monkeypatch):
    project, _workspace, work_id = _title_applied(tmp_path)

    class FailingPlanner:
        def __init__(self, *_args, **_kwargs):
            pass

        def build_plan(self, *, mode):
            assert mode == "all"
            raise RuntimeError("Cloudflare 403")

    monkeypatch.setattr(checkpoint, "RemoteUpdatePlanner", FailingPlanner)
    with pytest.raises(checkpoint.FrenchCheckpointError, match="Cloudflare 403") as caught:
        checkpoint.publish_checkpoint(project, "debat_test", work_id, stage="graph", adapter=object())
    assert caught.value.remote_execution_started is False


def test_review_packages_split_titles_from_classification_and_content(tmp_path: Path):
    project, workspace, work_id = _title_applied(tmp_path)
    state = {
        "schema": workflow.WORKFLOW_SCHEMA, "schema_version": "1.0",
        "normative_revision": workflow.NORM_VERSION, "validator_version": workflow.VALIDATOR_VERSION,
        "kit_version": workflow.KIT_VERSION, "debate_id": "debat_test", "debate_title": "Débat test ?",
        "short_code": "TEST", "phase": "fr_metadata_review", "status": "running", "work_id": work_id,
        "pending_review": None, "created_at": "2026-08-12T10:00:00+02:00", "updated_at": "2026-08-12T10:00:00+02:00",
    }
    # Title package is deliberately title-only.
    title_pending = workflow._prepare_metadata_package(project, state)
    title_manifest = json.loads((project / title_pending["manifest_path"]).read_text(encoding="utf-8")) if title_pending.get("manifest_path") else None
    # Inspect the generated ZIP manifest through the pending state payload.
    import zipfile
    with zipfile.ZipFile(project / title_pending["package_path"]) as z:
        names = set(z.namelist())
        assert "editable/reviews/fr/page_metadata_review.json" in names
        assert "editable/data/keyword_vocabulary_working.json" not in names

    # Reset pending so the next package can be prepared in the same fixture.
    state["pending_review"] = None
    content.prepare_review(project, "debat_test", work_id)
    with open(workspace / "reviews/fr/classification_review.json", encoding="utf-8") as f:
        classification = json.load(f)
    assert classification["review_scope"] == "classification_and_content"
    pending = workflow.create_review_package(
        project, state, review_type="fr_content_review", base=workspace,
        editable_paths=["reviews/fr/content_review.json", "data/sources_working.json", "reviews/fr/classification_review.json", "data/keyword_vocabulary_working.json"],
        context_paths=["reviewed-copy/data/fr_page_metadata_lock.json"],
    )
    with zipfile.ZipFile(project / pending["package_path"]) as z:
        names = set(z.namelist())
        assert "editable/reviews/fr/classification_review.json" in names
        assert "editable/data/keyword_vocabulary_working.json" in names
        assert "editable/reviews/fr/content_review.json" in names
        assert "editable/data/sources_working.json" in names


def test_content_checkpoint_uses_published_graph_state_not_import_inventory(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    cp = project / "cp"; cp.mkdir()
    # _config is sufficient to assert the state-resolution contract: graph gets
    # an explicit import inventory; content deliberately omits it so StateResolver
    # resolves .state/published from checkpoint 1.
    inv = project / "inventory"; inv.mkdir()
    graph_cfg = checkpoint._config(project, "demo", "EDIT-1", cp, "graph", inv)
    content_cfg = checkpoint._config(project, "demo", "EDIT-1", cp, "content", None)
    g = json.loads(graph_cfg.read_text(encoding="utf-8"))
    c = json.loads(content_cfg.read_text(encoding="utf-8"))
    assert g["state_inventory_root"] == str(inv)
    assert "state_inventory_root" not in c
    assert c["published_state_dir"].endswith("/.state/published")
    assert g["validator"]["profile"] == checkpoint.GRAPH_VALIDATION_PROFILE
    assert g["validator"]["scopes"] == list(checkpoint.GRAPH_VALIDATION_SCOPES)
    assert "wikicode" not in g["validator"]["scopes"]
    assert c["validator"]["profile"] == checkpoint.CONTENT_VALIDATION_PROFILE
    assert "wikicode" in c["validator"]["scopes"]


def test_sealed_release_can_resume_an_unattested_french_checkpoint(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    content.prepare_review(project, "debat_test", work_id)
    complete_content_review(workspace)
    finalized = content.finalize_review(project, "debat_test", work_id)
    content.apply_review(project, "debat_test", work_id, finalized["review_sha256"])

    metadata_path = workspace / "workspace.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["status"] = "release_ready"
    metadata["workspace_sha256"] = None
    metadata["workspace_sha256"] = editorial.workspace_receipt_hash(metadata)
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    _, graph_meta, _ = checkpoint._workspace(project, "debat_test", work_id, "graph")
    _, content_meta, _ = checkpoint._workspace(project, "debat_test", work_id, "content")
    assert graph_meta["status"] == "release_ready"
    assert content_meta["status"] == "release_ready"


def test_graph_checkpoint_uses_differential_validation_until_content_is_complete(tmp_path: Path):
    project, _workspace, work_id = _title_applied(tmp_path)
    cp = checkpoint.build_checkpoint(project, "debat_test", work_id, stage="graph")
    graph_config_path = checkpoint._config(project, "debat_test", work_id, cp, "graph", tmp_path / "inventory")
    graph_config = json.loads(graph_config_path.read_text(encoding="utf-8"))

    def validate(config):
        command = list(config["validator"]["command"])
        command.insert(command.index("validate") + 1, str(cp))
        for scope in config["validator"]["scopes"]:
            command.extend(["--scope", scope])
        command.extend(["--format", "json"])
        return subprocess.run(command, cwd=project, text=True, capture_output=True, check=False)

    graph_result = validate(graph_config)
    assert graph_result.returncode == 0, graph_result.stdout + graph_result.stderr
    assert not (cp / "data/fr_content_lock.json").exists()

    content_config_path = checkpoint._config(project, "debat_test", work_id, cp, "content", None)
    content_config = json.loads(content_config_path.read_text(encoding="utf-8"))
    content_result = validate(content_config)
    assert content_result.returncode != 0
    report = json.loads(content_result.stdout)
    assert report["summary"]["errors"] > 0
def test_checkpoint_published_state_evidence_is_signed_and_portable(tmp_path: Path):
    project = tmp_path / "project"
    state_path = project / ".state/published/debat_test/fr/latest.json"
    state_path.parent.mkdir(parents=True)
    state = {
        "state_version": "wikidebia-published-state-1.0",
        "debate_id": "debat_test",
        "language": "fr",
        "pages": [{"page_id": "A0001"}],
    }
    state["state_sha256"] = checkpoint.sha_object(state)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    evidence = checkpoint._published_state_evidence(project, "debat_test")
    assert evidence["path"] == ".state/published/debat_test/fr/latest.json"
    assert evidence["state_sha256"] == state["state_sha256"]
    assert evidence["pages"] == 1

    state["language"] = "en"
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(checkpoint.FrenchCheckpointError, match="Empreinte"):
        checkpoint._published_state_evidence(project, "debat_test")
