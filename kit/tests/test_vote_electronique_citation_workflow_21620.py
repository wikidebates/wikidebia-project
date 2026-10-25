from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import wikidebia_content_review as content
import wikidebia_corpus_build as common
import wikidebia_french_checkpoint as checkpoint
import wikidebia_translation_review as translation
import wikidebia_editorial_workspace as workspace_tool

from test_wikidebia_content_review import (
    make_metadata_applied,
    _set_reviewed_historical_text,
    complete_content_review,
    _request_historical_change,
    _write_direct_owner_authorization,
)
from test_historical_selected_value_21618 import HISTORICAL_INTRO, FINAL_INTRO, STAKES_CONTENT


def _citation(article: str, quotation: str, link: str) -> str:
    return (
        "{{Citation"
        "|auteurs=Commission nationale de l'informatique et des libertés (CNIL)"
        f"|article={article}"
        f"|citation={quotation}"
        "|ouvrage="
        "|numéro="
        "|localisation="
        "|page="
        "|édition="
        "|lieu="
        "|date=28 mai 2006"
        f"|lien={link}"
        "}}"
    )


def _inject_vote_citations(workspace: Path) -> None:
    reviewed = workspace / "reviewed-copy"
    provenance_path = reviewed / "data/import_provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    shapes = {
        "A0001": _citation(
            "Le vote par Internet aux élections politiques, les éléments du débat",
            "Le vote par Internet soulève des questions de sécurité, de secret du scrutin et de confiance dans les résultats.",
            "https://www.cnil.fr/fr/le-vote-par-internet-aux-elections-politiques-les-elements-du-debat",
        ),
        "A0002": _citation(
            "Le vote électronique : quelles garanties pour la démocratie ?",
            "La dématérialisation du vote exige que les garanties démocratiques restent vérifiables par les électeurs et les autorités de contrôle.",
            "https://www.cnil.fr/fr/vote-electronique",
        ),
    }
    for row in provenance["pages"]:
        page_id = row.get("page_id")
        if page_id not in shapes:
            continue
        page = reviewed / row["import_path"]
        text = page.read_text(encoding="utf-8")
        parsed = content.iter_templates(text)[0]
        old = parsed.get("citations") or ""
        text = text.replace(f"|citations={old}", f"|citations={shapes[page_id]}", 1)
        page.write_text(text, encoding="utf-8")
        row["sha256"] = hashlib.sha256(page.read_bytes()).hexdigest()
        row["size_bytes"] = page.stat().st_size
    common.write_json(provenance_path, provenance)
    meta_path = workspace / "workspace.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["reviewed_copy"]["tree_sha256"] = common.full_tree_sha256(reviewed)
    meta["workspace_sha256"] = None
    meta["workspace_sha256"] = workspace_tool.workspace_receipt_hash(meta)
    common.write_json(meta_path, meta)


def _authorize_vote_intro(workspace: Path) -> None:
    review_path = workspace / "reviews/fr/content_review.json"
    data = json.loads(review_path.read_text(encoding="utf-8"))
    rev = data["debate"]["review"]
    rev["introduction_decision"] = "change"
    rev["proposed_introduction"] = FINAL_INTRO
    rev["subsections"] = [
        {"title": "Définition du vote électronique"},
        {"title": "Expériences menées à l'échelle d'un pays"},
        {"title": "Expérimentations en France"},
        {"title": "Historique du débat en France"},
        {
            "title": "Enjeux du débat",
            "purpose": "Présenter les incidences concrètes nécessaires pour comprendre les conséquences du choix technique.",
            "necessary_for_understanding": True,
            "technical_or_specialized": False,
            "relevance_to_debate_explained": False,
            "stakes_section": True,
            "concrete_stakes": [
                "Accessibilité et continuité concrète du service électoral pour les différents électeurs.",
                "Confiance publique dans la vérifiabilité, l’exactitude et la légitimité du résultat final.",
            ],
        },
    ]
    rev["specialized_term_inventory"] = [{
        "subsection_title": "Enjeux du débat",
        "scan_complete": True,
        "scan_note": "La nouvelle sous-partie a été relue intégralement et ne contient aucune notion spécialisée nécessitant un traitement supplémentaire.",
        "terms": [],
    }]
    rev["terminal_period_sentence_exceptions"] = []
    _request_historical_change(
        rev,
        field_key="debate:debat_test:introduction",
        final_value=FINAL_INTRO,
        change_type="structure",
        rationale="Ajout de la sous-partie Enjeux du débat explicitement demandé par le propriétaire.",
    )
    rev["historical_change_request"]["change_scope"] = content._subsection_change_scope(HISTORICAL_INTRO, FINAL_INTRO)
    common.write_json(review_path, data)
    _write_direct_owner_authorization(workspace, data)


def test_vote_electronique_authorized_review_with_empty_optional_citation_parameters_reaches_english_editorial_point(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    _set_reviewed_historical_text(workspace, intro=HISTORICAL_INTRO)
    _inject_vote_citations(workspace)

    content.prepare_review(project, "debat_test", work_id)
    complete_content_review(workspace)
    _authorize_vote_intro(workspace)
    finalized = content.finalize_review(project, "debat_test", work_id)
    content.apply_review(project, "debat_test", work_id, finalized["review_sha256"])

    lock = json.loads((workspace / "content-reviewed-copy/data/fr_content_lock.json").read_text(encoding="utf-8"))
    citations = {row["id"]: row["citations"][0] for row in lock["arguments"] if row["id"] in {"A0001", "A0002"}}
    assert set(citations) == {"A0001", "A0002"}
    for citation in citations.values():
        source_pairs = {(row["name"], row["value"]) for row in citation["source_parameters"]}
        for name in ("ouvrage", "numéro", "localisation", "page", "édition", "lieu"):
            assert (name, "") in source_pairs

    # This is the path that previously raised "Paramètre de citation vide".
    cp = checkpoint.build_checkpoint(project, "debat_test", work_id, stage="content")
    provenance = common.load_json(workspace / "reviewed-copy/data/import_provenance.json", "provenance")
    imports = {row["page_id"]: row["import_path"] for row in provenance["pages"]}
    for page_id in ("A0001", "A0002"):
        wiki = (cp / f"output/fr/arguments/{page_id}.wiki").read_text(encoding="utf-8")
        outer = content.iter_templates(wiki)[0]
        citation_wiki = outer.get("citations") or ""
        assert "{{Citation" in citation_wiki
        # The content checkpoint preserves the exact historical citation,
        # including optional parameters already empty in the imported page.
        imported = (workspace / "reviewed-copy" / imports[page_id]).read_text(encoding="utf-8")
        assert citation_wiki == content.iter_templates(imported)[0].get("citations")

    # Continue mechanically to the next genuine editorial point: English review.
    prepared = translation.prepare_review(project, "debat_test", work_id)
    assert prepared["status"] == "en_translation_review_ready"
    review = json.loads((workspace / "reviews/en/translation_review.json").read_text(encoding="utf-8"))
    by_id = {row["id"]: row["translation"] for row in review["arguments"]}
    for page_id in ("A0001", "A0002"):
        source = by_id[page_id]["citations"][0]["source"]
        preserved = {(row["name"], row["value"]) for row in source["source_parameters"]}
        for name in ("ouvrage", "numéro", "localisation", "page", "édition", "lieu"):
            assert (name, "") in preserved
