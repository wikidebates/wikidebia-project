"""Preserved translations keep existing English arguments through final publication."""
from __future__ import annotations

import html
from pathlib import Path

import pytest

import wikidebia_final_publication as final
import wikidebia_global_resume as resume
import wikidebia_public_visibility as visibility
import wikidebia_review_workflow as workflow
from wikidebia_corpus_build import full_tree_sha256, load_json, sha256_file, write_json
from wikidebia_graph_actions import _set_optional_parameter_value


DEBATE = "debat_test"
REUSED_ID = "A0003"
REUSED_TITLE = "Existing English argument"


def _add_existing_english_frontier(corpus: Path) -> None:
    provenance_path = corpus / "data/import_provenance.json"
    provenance = load_json(provenance_path)
    page = next(row for row in provenance["pages"] if row.get("page_id") == REUSED_ID)
    source = corpus / page["import_path"]
    original = source.read_text(encoding="utf-8").replace("|justifications=|objections=", "")
    linked = _set_optional_parameter_value(
        original, "argument", "interlangue",
        "{{Lien interlangue|langue=en|page=" + REUSED_TITLE + "}}",
    )
    source.write_text(linked, encoding="utf-8")
    page["sha256"] = sha256_file(source)
    write_json(provenance_path, provenance)
    for path in (corpus / "data/registre_debat.json", corpus / "graph/graphe_argumentatif.json"):
        data = load_json(path)
        node = next(n for n in (data.get("graph") or data)["nodes"] if n["id"] == REUSED_ID)
        node["en"].update(canonical_title=REUSED_TITLE, displayed_title=REUSED_TITLE, title_status="locked")
        node["pages"]["en"]["wiki"].update(check_status="equivalent_existing", decision="reuse_existing",
                                          remote_title=REUSED_TITLE, remote_revision_id=42)
        node["pages"]["en"]["generation"]["status"] = "obsolete"
        write_json(path, data)


def _seal_preserved_release(tmp_path, monkeypatch):
    from test_wikidebia_translation_review import complete_semantic_convergence, complete_translation_review
    from test_wikidebia_release import writing_validator
    from test_wikidebia_render import approve_fixture_placements
    from test_translation_source_preservation import freeze, prepared
    import wikidebia_release as release
    import wikidebia_render as render
    import wikidebia_translation_review as translation

    project, workspace, work = prepared(tmp_path, adjust_corpus=_add_existing_english_frontier)
    freeze(project, work)
    translation.prepare_review(project, DEBATE, work)
    review_path = workspace / "reviews/en/translation_review.json"
    assert REUSED_ID not in {row["id"] for row in load_json(review_path)["arguments"]}
    complete_translation_review(workspace)
    review = load_json(review_path)
    # This source has no introduction. Preserve that historical absence.
    review["debate"].update(introduction="", subsections=[], keywords_order_preserved_by_relevance=True)
    review["debate"]["debate_field_semantic_risk_evidence"] = [
        row for row in review["debate"]["debate_field_semantic_risk_evidence"]
        if not row["risk"].startswith("introduction:")
    ]
    write_json(review_path, review)
    source_path = workspace / "data/sources_en_working.json"
    sources = load_json(source_path)
    for source in sources["sources"]:
        source["usage"] = [row for row in source["usage"] if row["page_id"] in {DEBATE, "A0001", "A0002"}]
    write_json(source_path, sources)
    finalized = translation.finalize_review(project, DEBATE, work)
    complete_semantic_convergence(project, work)
    monkeypatch.setattr(translation, "_run_validator", writing_validator)
    monkeypatch.setattr(render, "_run_validator", writing_validator)
    monkeypatch.setattr(release, "_run_validator", writing_validator)
    translation.apply_review(project, DEBATE, work, finalized["review_sha256"])
    approve_fixture_placements(workspace)
    rendered = render.render_workspace(project, DEBATE, work, finalized["review_sha256"])
    release.release_workspace(project, DEBATE, work, rendered["rendered_copy_tree_sha256"])
    return project, workspace, work


class PublicWiki:
    def __init__(self, published):
        self.published = published
        self.checked = []
        self.interrupted = True

    def pages(self, language, titles):
        return {title: {"exists": True, "revision_id": 42, "text": self.published[language][title][1]}
                for title in titles}

    def html(self, language, title):
        self.checked.append((language, title))
        kind, text = self.published[language][title]
        if self.interrupted and (language, title) == ("en", REUSED_TITLE):
            raise visibility.PublicUnavailable("HTTP 429")
        document = visibility._PublicDocument()
        document.feed(f'<h1 id="firstHeading">{html.escape(title)}</h1><div id="mw-content-text">')
        if language == "fr":
            target = visibility._interlanguage_target(text, kind)
            document.feed(f'<a href="{visibility._public_url("en", target)}">EN</a>')
        document.feed("</div>")
        return document


def test_preserved_translation_to_final_receipt_reuses_english_argument(tmp_path, monkeypatch):
    project, workspace, work = _seal_preserved_release(tmp_path, monkeypatch)
    package = workspace / "release-copy"
    manifest = load_json(package / "manifest.json")
    published = {"en": {REUSED_TITLE: ("argument", "{{Argument|summary=Existing English reasoning.}}")}, "fr": {}}
    rendered = {"en": {}, "fr": {}}
    english = {"actions": [], "package_fingerprints": {}}
    french = {"operations": {"update": [], "skip": []}}
    for page in manifest["pages"]:
        language, key, title = (page[field] for field in ("language", "page_id", "canonical_title"))
        text = (package / page["file_path"]).read_text(encoding="utf-8")
        row = {"language": language, "page_id": key, "title": title, "page_type": page["page_type"]}
        rendered[language][title] = (row["page_type"], text)
        if language == "en":
            english["actions"].append({**row, "operation": "create", "desired_sha256": visibility._sha_text(text)})
        else:
            french["operations"]["skip" if key == REUSED_ID else "update"].append({
                **row, "edit_summary_policy": "french_interlanguage_addition",
            })
    assert (len(english["actions"]), len(french["operations"]["update"])) == (3, 3)
    preserved = load_json(package / "data/source_preservation_receipt.json")
    for row in preserved["pages"]:
        original = (package / row["import_path"]).read_text(encoding="utf-8")
        published["fr"][row["canonical_title"]] = (row["kind"], original)
    reused = next(row["canonical_title"] for row in preserved["pages"] if row.get("page_id") == REUSED_ID)
    assert published["fr"][reused][1].rstrip("\n") == rendered["fr"][reused][1].rstrip("\n")

    def build_plans(root, debate, work_id, release_copy, state_dir, *, preserved):
        assert preserved
        result = {}
        for key, stem, plan in (
            ("en", "english-publication", english), ("fr", "french-update", french),
            ("safety", "safety-update", {"operations": {}}),
        ):
            plan["plan_sha256"] = final._canonical(plan, "plan_sha256")
            config = state_dir / f"{stem}-config.json"
            write_json(config, {})
            write_json(state_dir / f"{stem}-plan.json", plan)
            result.update({f"{key}_config_path": config, f"{key}_config": {}, f"{key}_plan": plan})
        return result

    # Simulate MediaWiki at the transport boundary while using the real preflight,
    # authorization, receipt chaining, public verification and corpus installation.
    monkeypatch.setattr(final, "_load_or_build_plans", build_plans)
    monkeypatch.setattr(final, "build_adapter", lambda *args: object())
    monkeypatch.setattr(final, "_remote_snapshot_for_english", lambda *args: [
        {**row, "exists": False} for row in english["actions"]
    ])
    monkeypatch.setattr(final, "_remote_snapshot_for_french", lambda *args: [
        {"language": "fr", "page_id": DEBATE if row["kind"] == "debate" else row["page_id"],
         "title": row["canonical_title"], "revision_id": row["revision_id"],
         "remote_sha256": visibility._sha_text((package / row["import_path"]).read_text())}
        for row in preserved["pages"]
    ])
    writes = []

    class Publisher:
        def __init__(self, *args):
            pass

        def _package_fingerprints(self):
            return {}

        def publish(self, **kwargs):
            writes.append("en")
            published["en"].update(rendered["en"])
            return {"created": 3}

    class LinkExecutor:
        def __init__(self, *args):
            pass

        def resume_latest_receipt(self, *args, **kwargs):
            return None

        def execute(self, *args, **kwargs):
            writes.append("fr")
            for row in french["operations"]["update"]:
                published["fr"][row["title"]] = rendered["fr"][row["title"]]
            return {"counts": {"updated": 3}}

    monkeypatch.setattr(final, "GenericPublisher", Publisher)
    monkeypatch.setattr(final, "PlanExecutor", LinkExecutor)
    client = PublicWiki(published)
    monkeypatch.setattr(visibility, "AnonymousMediaWiki", lambda: client)
    prepared_state = workflow.publish_preserved_workflow(project, DEBATE, work)
    assert prepared_state["status"] == "publication_prepared" and not writes
    initial = resume.discover_resume(project, debate_id=DEBATE, work_id=work)["selected"]
    assert initial["status"] == "publication_prepared"
    with pytest.raises(workflow.WorkflowError, match="déjà autorisée"):
        workflow.publish_prepared_workflow(project, DEBATE, initial["publication_preflight_sha256"], verify_only=True)
    assert not writes

    partial = workflow.publish_prepared_workflow(project, DEBATE, initial["publication_preflight_sha256"])
    assert partial["status"] == "blocked_final_publication" and writes == ["en", "fr"], partial.get("final_publication")
    current = resume.discover_resume(project, debate_id=DEBATE, work_id=work)["selected"]
    assert current["status"] == "public_verification_pending"
    assert current["next_command"].endswith("--verify-only") and not current["next_remote_write_possible"]
    assert current["public_verification_progress"] == {"en": 3, "fr": 4}

    french_receipt = final._state_dir(project, DEBATE, work) / "french-publication-receipt.json"
    held_receipt = french_receipt.with_suffix(".held")
    french_receipt.rename(held_receipt)
    refused = workflow.publish_prepared_workflow(project, DEBATE, current["publication_preflight_sha256"], verify_only=True)
    assert "deux reçus" in refused["final_publication"]["error"] and writes == ["en", "fr"]
    held_receipt.rename(french_receipt)

    client.checked.clear()
    client.interrupted = False
    published_state = workflow.publish_prepared_workflow(
        project, DEBATE, current["publication_preflight_sha256"], verify_only=True,
    )
    assert published_state["status"] == "published"
    receipt = published_state["final_publication"]
    assert receipt["receipt_sha256"] == final._canonical(receipt, "receipt_sha256")
    assert receipt["public_english_pages_verified"] == receipt["public_french_links_verified"] == 4
    assert client.checked == [("en", REUSED_TITLE)]
    assert writes == ["en", "fr"]
    assert load_json(workspace / "workspace.json")["status"] == "published"
    assert full_tree_sha256(project / "corpus" / DEBATE) == full_tree_sha256(package)
