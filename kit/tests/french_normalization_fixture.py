from contextlib import contextmanager
from unittest.mock import patch

import wikidebia_french_normalization as normalization
import wikidebia_translation_review as translation
from wikidebia_corpus_build import load_json, write_json


def fixture_french_wiki(project, debate_id, work_id):
    workspace, meta = translation._load_workspace(project, debate_id, work_id)
    source = workspace / "content-reviewed-copy"
    revisions = {}
    rows = []
    registry = load_json(source / "data/registre_debat.json")
    nodes, _, _ = normalization.active_graph(registry)
    titles = {node["id"]: node["fr"]["canonical_title"] for node in nodes}
    titles[debate_id] = registry["debate"]["pages"]["fr"]["canonical_title"]
    frozen_path = source / "data/source_preservation_receipt.json"
    provenance = load_json(frozen_path if frozen_path.exists() else source / "data/import_provenance.json")
    for row in provenance["pages"]:
        page_id = debate_id if row["kind"] == "debate" else row["page_id"]
        if page_id not in titles:
            continue
        text = (source / row["import_path"]).read_text(encoding="utf-8")
        title = row["canonical_title"] if frozen_path.exists() else titles[page_id]
        revision = row["revision_id"]
        revisions[title] = {"text": text, "exists": True, "revision_id": revision, "redirect": False}
        rows.append({
            "page_id": page_id, "page_type": row["kind"], "status": "published",
            "canonical_title": title, "revision_id": revision,
            "content_sha256": normalization.sha_text(text),
        })

    if not frozen_path.exists():
        state = {"debate_id": debate_id, "language": "fr", "pages": rows}
        state["state_sha256"] = normalization.sha_object(state)
        write_json(project / ".state/published" / debate_id / "fr/latest.json", state)
        directory = project / ".state/fr-publication" / debate_id / work_id / "content"
        checkpoint = {
            "debate_id": debate_id, "work_id": work_id, "stage": "content",
            "source_tree_sha256": meta["content_reviewed_copy"]["tree_sha256"],
            "checkpoint_tree_sha256": "test-checkpoint",
        }
        checkpoint["receipt_sha256"] = normalization.sha_object(checkpoint)
        write_json(directory / "checkpoint.json", checkpoint)
        publication = {
            "debate_id": debate_id, "work_id": work_id, "stage": "content", "status": "published",
            "checkpoint_tree_sha256": checkpoint["checkpoint_tree_sha256"],
            "published_state": {"state_sha256": state["state_sha256"]},
        }
        publication["receipt_sha256"] = normalization.sha_object(publication)
        write_json(directory / "publication-receipt.json", publication)
    return workspace, revisions


@contextmanager
def fake_wiki(revisions):
    with patch.object(normalization, "AnonymousMediaWiki") as fake:
        fake.return_value.pages.side_effect = lambda language, titles: {
            title: revisions[title] for title in titles if title in revisions
        }
        yield fake.return_value


def complete_fixture_french_normalization(workspace):
    path = workspace / normalization.REVIEW_PATH
    review = load_json(path)
    review["reviewer"] = "Relecteur du corpus de test"
    for criterion in review["criteria"].values():
        criterion.update(status="checked", note="Contrôle simulé sur les révisions du corpus de test.")
    write_json(path, review)
    return review


def prepare_fixture_translation(project, debate_id, work_id, **kwargs):
    workspace, revisions = fixture_french_wiki(project, debate_id, work_id)
    with fake_wiki(revisions):
        translation.prepare_french_normalization(project, debate_id, work_id)
        complete_fixture_french_normalization(workspace)
        return translation.prepare_review(project, debate_id, work_id, **kwargs)
