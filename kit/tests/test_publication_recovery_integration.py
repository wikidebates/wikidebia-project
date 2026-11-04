from __future__ import annotations

import json
from pathlib import Path

import wikidebia_final_publication as final
import test_editorial_orchestration_2160 as workflow_fixture
import test_wikidebia_publish as publication_fixture
import test_wikidebia_remote_update as update_fixture


def test_publication_recovery_chain_from_spam_gate_to_workflow_reconciliation(tmp_path: Path, monkeypatch):
    publication_root = tmp_path / "publication"
    publication_root.mkdir()
    config, config_path, _fr_text, _en_text = publication_fixture.write_fixture(
        publication_root, "full_page"
    )
    english_source = publication_root / "corpus/demo/output/en/A1.wiki"
    rejected_url = "https://archive.is/example"
    accepted_url = "https://example.org/original"
    english_source.write_text(
        english_source.read_text(encoding="utf-8") + rejected_url + "\n",
        encoding="utf-8",
    )
    manifest_path = publication_root / "corpus/demo/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    next(
        row for row in manifest["pages"]
        if row["language"] == "en" and row["page_id"] == "A1"
    )["sha256"] = publication_fixture.module.sha_file(english_source)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    config["publication_url_replacements"] = [{
        "language": "en",
        "page_id": "A1",
        "old_url": rejected_url,
        "new_url": accepted_url,
        "owner_approved": True,
        "reason": "MediaWiki rejects the archive host; retain the exact original cited article.",
        "authorization_receipt_sha256": "a" * 64,
    }]
    config_path.write_text(json.dumps(config), encoding="utf-8")
    publication_adapter = publication_fixture.FakeAdapter()
    publication_adapter.spam_matches = {"archive.is"}
    publisher = publication_fixture.module.GenericPublisher(
        config, publication_adapter, config_path
    )
    publication_plan = publisher.build_plan()

    original_write = publication_adapter.write_page

    def interrupt_english_write(**kwargs):
        if publication_adapter.language == "en":
            raise RuntimeError("simulated interruption")
        return original_write(**kwargs)

    publication_adapter.write_page = interrupt_english_write
    try:
        publisher.publish(
            plan=publication_plan,
            confirmation=publication_plan["plan_sha256"],
        )
    except RuntimeError as exc:
        assert str(exc) == "simulated interruption"
    else:
        raise AssertionError("L’interruption de publication simulée n’a pas été propagée")
    failed_checkpoint = json.loads(
        (publication_root / "logs/test-progress.json").read_text(encoding="utf-8")
    )
    assert failed_checkpoint["status"] == "failed"
    assert failed_checkpoint["completed"] == [
        {"language": "fr", "page_id": "A1", "result": "created"}
    ]

    publication_adapter.write_page = original_write
    publisher.publish(
        plan=publication_plan,
        confirmation=publication_plan["plan_sha256"],
    )
    completed_checkpoint = json.loads(
        (publication_root / "logs/test-progress.json").read_text(encoding="utf-8")
    )
    assert completed_checkpoint["status"] == "completed"
    english_revision, published_english = publication_adapter.pages[("en", "Title EN")]
    assert rejected_url not in published_english
    assert accepted_url in published_english

    successor_root = tmp_path / "successor-release"
    (successor_root / "data").mkdir(parents=True)
    (successor_root / "page.wiki").write_text(published_english, encoding="utf-8")
    predecessor_sha = final.sha_text(published_english)
    successor_text = published_english + "\n"
    successor_sha = final.sha_text(successor_text)
    owner_decision = {
        "owner_approved": True,
        "decision": "explicit_user_request",
        "allow_proposed_change": True,
        "page_id": "A1",
        "language": "en",
        "title": "Title EN",
        "observed_revision_id": english_revision,
        "observed_sha256": predecessor_sha,
        "instruction": "Accept the audited English page and continue the complete publication recovery chain.",
    }
    successor = {
        "owner_approved": True,
        "predecessor_revision_id": english_revision,
        "predecessor_sha256": predecessor_sha,
        "observed_revision_id": english_revision + 1,
        "observed_sha256": successor_sha,
        "delta_policy": "whitespace_only",
        "verification_receipt_sha256": "b" * 64,
        "instruction": "Accept the audited whitespace-only successor revision for final publication.",
    }
    (successor_root / "data/successors.json").write_text(
        json.dumps({
            "debate_id": "demo",
            "entries": [{"page_id": "A1", "successor_revision": successor}],
        }),
        encoding="utf-8",
    )
    (successor_root / "manifest.json").write_text(
        json.dumps({
            "debate_id": "demo",
            "editorial_controls": {
                "english_successor_revisions_path": "data/successors.json"
            },
            "pages": [{
                "language": "en",
                "page_id": "A1",
                "canonical_title": "Title EN",
                "page_origin": "preexisting",
                "file_path": "page.wiki",
                "existing_english_update": owner_decision,
            }],
        }),
        encoding="utf-8",
    )
    approved = final._approved_english_updates(successor_root)["A1"]
    assert approved["observed_revision_id"] == english_revision + 1
    assert approved["observed_sha256"] == successor_sha

    retarget_root = tmp_path / "retarget"
    retarget_root.mkdir()
    proposed_french = update_fixture.argument("Version corpus")
    update_config, update_config_path = update_fixture.make_fixture(
        retarget_root,
        languages=("fr",),
        old_pages=[],
        new_pages=[("fr", "A1", "Titre FR", proposed_french)],
    )
    corpus = retarget_root / "corpus/demo"
    english_dir = corpus / "output/en"
    english_dir.mkdir(parents=True, exist_ok=True)
    english_file = english_dir / "A1.wiki"
    english_file.write_text(published_english, encoding="utf-8")
    update_manifest = json.loads((corpus / "manifest.json").read_text())
    update_manifest["translation_status"] = {"en": "ready"}
    update_manifest["pages"].append({
        "language": "en",
        "page_id": "A1",
        "page_type": "argument",
        "canonical_title": "Title EN",
        "file_path": "output/en/A1.wiki",
        "sha256": update_fixture.module.sha_file(english_file),
    })
    (corpus / "manifest.json").write_text(json.dumps(update_manifest), encoding="utf-8")
    remote_french = update_fixture.argument("Texte humain").replace(
        "|rubriques=Société",
        "|interlangue={{Lien interlangue\n|langue=en\n|page=Old English title\n}}\n|rubriques=Société",
    )
    update_config["interlanguage_only"] = True
    update_config["interlanguage_retargets"] = {"A1": "Old English title"}
    update_config_path.write_text(json.dumps(update_config), encoding="utf-8")
    update_adapter = update_fixture.FakeAdapter({("fr", "Titre FR"): (11, remote_french)})
    retarget_plan = update_fixture.module.RemoteUpdatePlanner(
        update_config, update_adapter, update_config_path
    ).build_plan()
    assert retarget_plan["counts"]["update"] == 1
    retarget_receipt = update_fixture.module.PlanExecutor(
        update_config, update_adapter, update_config_path
    ).execute(retarget_plan, retarget_plan["plan_sha256"])
    assert retarget_receipt["counts"]["updated"] == 1
    final_french = update_adapter.pages[("fr", "Titre FR")][1]
    assert "Texte humain" in final_french
    assert "|page=Title EN" in final_french
    assert "Old English title" not in final_french

    debate_id = "demo"
    work_id = "EDIT-RECOVERY-001"
    workflow = {
        "schema": workflow_fixture.wf.WORKFLOW_SCHEMA,
        "schema_version": "1.0",
        "debate_id": debate_id,
        "debate_title": "Démo",
        "phase": "fr_content_review",
        "status": "awaiting_review",
        "work_id": work_id,
        "pending_review": {"review_type": "fr_content_review"},
        "created_at": "2026-11-04T12:00:00+01:00",
        "updated_at": "2026-11-04T12:00:00+01:00",
    }
    workflow_fixture.wf._save_workflow(tmp_path, workflow)
    workspace = tmp_path / ".state/editorial-workspaces" / debate_id / work_id
    release_copy = workspace / "release-copy"
    (release_copy / "output/fr").mkdir(parents=True)
    (release_copy / "output/en").mkdir(parents=True)
    (release_copy / "output/fr/A1.wiki").write_text(final_french, encoding="utf-8")
    (release_copy / "output/en/A1.wiki").write_text(published_english, encoding="utf-8")
    release_tree = workflow_fixture.common.full_tree_sha256(release_copy)
    workspace_meta = {
        "schema": "wikidebia-editorial-workspace-1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "status": "release_ready",
        "release_copy": {"tree_sha256": release_tree},
        "local_release": {"archive": "release.zip"},
    }
    workspace_meta["workspace_sha256"] = workflow_fixture.wf.workspace_receipt_hash(
        workspace_meta
    )
    workflow_fixture.common.write_json(workspace / "workspace.json", workspace_meta)

    def signed(value):
        result = dict(value)
        result["receipt_sha256"] = workflow_fixture.wf._sha256_bytes(
            workflow_fixture.wf._canonical_json(result)
        )
        return result

    release_receipt = signed({
        "debate_id": debate_id,
        "work_id": work_id,
        "release_copy_tree_sha256": release_tree,
        "publication_plan_sha256": publication_plan["plan_sha256"],
    })
    workflow_fixture.common.write_json(
        tmp_path / ".state/corpus-releases" / debate_id / work_id / "release-receipt.json",
        release_receipt,
    )
    french_receipt = signed({
        "debate_id": debate_id,
        "work_id": work_id,
        "status": "published",
        "plan_sha256": retarget_plan["plan_sha256"],
    })
    workflow_fixture.common.write_json(
        tmp_path / ".state/fr-publication" / debate_id / work_id / "content/publication-receipt.json",
        french_receipt,
    )
    monkeypatch.setattr(
        workflow_fixture.wf,
        "resolve_workflow_release_baseline",
        lambda *args, **kwargs: {"baseline_sha256": approved["observed_sha256"]},
    )
    reconciled = workflow_fixture.wf.reconcile_workflow(tmp_path, debate_id)
    assert reconciled["phase"] == reconciled["status"] == "release_ready"
    assert reconciled["french_content_publication"]["receipt_sha256"] == french_receipt["receipt_sha256"]
    assert reconciled["workflow_reconciliation"]["baseline_sha256"] == successor_sha
