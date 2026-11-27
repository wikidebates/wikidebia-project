from __future__ import annotations

import copy
import importlib.util
import json
import shutil
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


content = load_module("wikidebia_content_review")
metadata = sys.modules.get("wikidebia_editorial_review") or load_module("wikidebia_editorial_review")
workspace_tool = sys.modules.get("wikidebia_editorial_workspace") or load_module("wikidebia_editorial_workspace")
common = sys.modules["wikidebia_corpus_build"]

def fake_validator(*args, **kwargs):
    return {"validator_version": "0.4.29", "result": "passed", "summary": {"errors": 0, "warnings": 0}}

metadata._run_validator = fake_validator
content._run_validator = fake_validator

from test_wikidebia_editorial_review import make_workspace, complete_review  # noqa: E402


def make_metadata_applied(tmp_path: Path, *, distinct_fourth_quote: bool = False) -> tuple[Path, Path, str]:
    project, workspace, work_id = make_workspace(tmp_path, distinct_fourth_quote=distinct_fourth_quote)
    complete_review(workspace)
    finalized = metadata.finalize_review(project, "debat_test", work_id)
    metadata.apply_review(project, "debat_test", work_id, finalized["review_sha256"])
    return project, workspace, work_id


def source_row(source_id: str, source_type: str, usages: list[dict[str, object]]) -> dict[str, object]:
    index = int(source_id[1:])
    metadata_row = {
        "authors": [f"Auteur {index}"],
        "article": None,
        "work": None,
        "volume": None,
        "issue": None,
        "location": None,
        "publisher": None,
        "place": None,
        "date": "3 août 2026",
        "link": None,
        "page": None,
        "site": None,
        "title": None,
    }
    if source_type == "bibliography":
        metadata_row["work"] = f"Ouvrage de référence {index}"
        document_kind = "book"
    elif source_type == "webliography":
        metadata_row["link"] = f"https://example.org/source-{index}"
        metadata_row["site"] = f"Site documentaire {index}"
        metadata_row["page"] = f"Page documentaire {index}"
        document_kind = "other"
    else:
        metadata_row["link"] = f"https://example.org/video-{index}"
        metadata_row["title"] = f"Vidéo documentaire {index}"
        metadata_row["site"] = f"Plateforme vidéo {index}"
        document_kind = "other"
    return {
        "id": source_id,
        "type": source_type,
        "language": "fr",
        "metadata": metadata_row,
        "verification": {
            "status": "verified",
            "verified_at": "2026-08-03T20:30:00+02:00",
            "primary_source": False,
            "notes": ["Notice et langue vérifiées pour la revue française."],
            "language_verified": True,
            "authorship_checked": True,
            "authorship_verified": True,
            "authorship_rechecked_after_site_match": False,
            "authorship_recheck_notes": [],
        },
        "usage": usages,
        "deduplication_key": f"source-{index}",
        "document_kind": document_kind,
        "equivalence_group": None,
    }


def complete_content_review(workspace: Path) -> None:
    review_path = workspace / "reviews/fr/content_review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    debate = review["debate"]["review"]
    # Imported debate text is protected: content review may update headings,
    # classification and documentation, but not the historical introduction.
    debate.update({
        "status": "approved",
        "subject_decision": "change",
        "proposed_subject": "Débat test",
        "complete_topic_decision": "change",
        "proposed_complete_topic": "la proposition du débat test",
        "topic_label_rationale": "Le libellé nominal désigne directement la controverse sans reprendre une question.",
        "common_acronym": None,
        "complete_topic_initial_capital_justification": None,
        "wikipedia_articles_decision": "change",
        "proposed_wikipedia_articles": ["Argumentation"],
        "wikipedia_articles_verified": True,
        "documentation_decisions": {bucket: "change" for bucket in content.DEBATE_BUCKETS},
        "documentation_rationales": {bucket: "Ces références documentent spécifiquement la position et la famille concernées." for bucket in content.DEBATE_BUCKETS},
        "documentation_family_notes": {
            "bibliography": "Des ouvrages de synthèse français couvrent les positions et le cadrage général.",
            "webliography": "Des ressources web françaises vérifiées complètent les positions et le contexte.",
            "videography": "Des ressources vidéo françaises vérifiées présentent les positions et la synthèse.",
        },
        "reviewer": "Relecteur Wikidéb'IA",
        "reviewed_at": "2026-08-03T21:00:00+02:00",
        "note": "Introduction historique conservée ; documentation et métadonnées françaises relues séparément.",
    })
    debate["proposed_documentation"] = {
        "bibliographie-pour": ["S00001"],
        "bibliographie-contre": ["S00002"],
        "bibliographie-ni-pour-ni-contre": [],
        "sitographie-pour": ["S00003"],
        "sitographie-contre": ["S00004"],
        "sitographie-ni-pour-ni-contre": [],
        "vidéographie-pour": ["S00005"],
        "vidéographie-contre": ["S00006"],
        "vidéographie-ni-pour-ni-contre": [],
    }
    for item in review["arguments"]:
        node_id = item["id"]
        decision = item["review"]
        decision.update({
            "status": "approved",
            # summary_decision/proposed_summary remain the exact protected
            # values created by prepare_review.
            "documentation_decisions": {bucket: "change" for bucket in content.ARGUMENT_BUCKETS},
            "proposed_sources": {"bibliography": ["S00001"], "webliography": [], "videography": []},
            "documentation_rationale": "La référence retenue soutient directement le contenu historique sans imposer de quota artificiel.",
            "reviewer": "Relecteur Wikidéb'IA",
            "reviewed_at": "2026-08-03T21:00:00+02:00",
            "note": "Résumé historique conservé exactement ; documentation française relue séparément.",
        })
    review["global_review"] = {
        "reviewer": "Relecteur Wikidéb'IA",
        "reviewed_at": "2026-08-03T21:15:00+02:00",
        "all_french_content_reviewed": True,
        "all_selected_sources_verified": True,
        "no_final_pages_generated": True,
        "english_translation_not_started": True,
        "blocking_issues": [],
        "note": "Toutes les décisions françaises ouvertes à la reprise ont été relues ; les textes historiques protégés restent inchangés.",
    }
    common.write_json(review_path, review)

    source_roles = {
        "S00001": "pro_reference", "S00002": "con_reference",
        "S00003": "pro_reference", "S00004": "con_reference",
        "S00005": "pro_reference", "S00006": "con_reference",
    }
    sources = []
    for source_id, source_type in (("S00001", "bibliography"), ("S00002", "bibliography"), ("S00003", "webliography"), ("S00004", "webliography"), ("S00005", "videography"), ("S00006", "videography")):
        usages = [{
            "page_id": "debat_test",
            "language": "fr",
            "role": source_roles[source_id],
            "language_fit": "native",
            "preferred_equivalent_source_id": None,
            "documentary_scope": "broad_synthesis",
            "selection_reason": "Cette source française documente précisément l’orientation qui lui est attribuée.",
        }]
        if source_id == "S00001":
            usages.extend({
                "page_id": item["id"],
                "language": "fr",
                "role": "supports_summary",
                "argument_development_verified": True,
                "also_develops_objections": False,
                "objection_coverage_note": None,
                "language_fit": "native",
                "preferred_equivalent_source_id": None,
                "documentary_scope": "narrow_argument",
                "selection_reason": "Cette source soutient directement le contenu historique de l'argument.",
            } for item in review["arguments"])
        sources.append(source_row(source_id, source_type, usages))
    working = {
        "schema": content.SOURCES_WORKING_SCHEMA,
        "source_registry_version": "1.0",
        "debate_id": "debat_test",
        "work_id": review["work_id"],
        "status": "draft",
        "prepared_at": review["prepared_at"],
        "sources": sources,
    }
    common.write_json(workspace / "data/sources_working.json", working)


def test_prepare_content_review_is_read_only_for_reviewed_copy(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    before = common.full_tree_sha256(workspace / "reviewed-copy")
    result = content.prepare_review(project, "debat_test", work_id)
    assert result["status"] == "fr_content_review_ready"
    assert common.full_tree_sha256(workspace / "reviewed-copy") == before
    review = json.loads((workspace / "reviews/fr/content_review.json").read_text(encoding="utf-8"))
    assert len(review["arguments"]) == 4
    assert review["debate"]["source"]["introduction"] == ""
    assert review["debate"]["review"]["introduction_decision"] == "keep"
    assert review["debate"]["review"]["proposed_introduction"] == ""
    assert all(item["review"]["summary_decision"] == "keep" for item in review["arguments"])
    assert all(item["review"]["proposed_summary"] == item["source"]["summary"] for item in review["arguments"])
    citations = {item["id"]: item["source"]["citations"] for item in review["arguments"]}
    assert citations["A0001"][0]["avertissements-citation"] == "Texte abrégé"
    assert citations["A0001"][0]["preserved_parameters"][0]["name"] == "auteurs"
    assert citations["A0002"][0]["date"] == "juin 2012"
    assert citations["A0004"][0]["date"] == "1971"
    translation = json.loads((workspace / "reviews/en/translation_readiness.json").read_text(encoding="utf-8"))
    assert translation["status"] == "blocked_by_french_content_review"


def test_finalize_content_review_seals_sources_and_content(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    content.prepare_review(project, "debat_test", work_id)
    complete_content_review(workspace)
    before = common.full_tree_sha256(workspace / "reviewed-copy")
    result = content.finalize_review(project, "debat_test", work_id)
    assert result["status"] == "fr_content_review_finalized"
    assert result["sources"] == 6
    assert result["arguments"] == 4
    assert common.full_tree_sha256(workspace / "reviewed-copy") == before
    sealed = json.loads((workspace / "reviews/fr/content_review.json").read_text(encoding="utf-8"))
    assert sealed["review_sha256"] == content.content_review_sha256(sealed)
    assert sealed["summary"]["debate_documentary_references"] == 6
    assert sealed["summary"]["citations"] == 4


def test_finalize_accepts_single_reference_in_a_debate_bucket(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    content.prepare_review(project, "debat_test", work_id)
    complete_content_review(workspace)
    result = content.finalize_review(project, "debat_test", work_id)
    assert result["status"] == "fr_content_review_finalized"


def test_finalize_rejects_same_reference_in_pro_and_con_buckets(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    content.prepare_review(project, "debat_test", work_id)
    complete_content_review(workspace)
    review_path = workspace / "reviews/fr/content_review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["debate"]["review"]["proposed_documentation"]["bibliographie-contre"] = ["S00001"]
    common.write_json(review_path, review)
    sources_path = workspace / "data/sources_working.json"
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    source = next(row for row in sources["sources"] if row["id"] == "S00001")
    source["usage"].append({
        "page_id": "debat_test", "language": "fr", "role": "con_reference",
        "language_fit": "native", "preferred_equivalent_source_id": None,
        "documentary_scope": "broad_synthesis",
        "selection_reason": "Cette attribution contradictoire sert uniquement à vérifier le blocage automatique.",
    })
    common.write_json(sources_path, sources)
    try:
        content.finalize_review(project, "debat_test", work_id)
    except content.ContentReviewError as exc:
        assert "ni pour ni contre" in str(exc) or "plusieurs orientations" in str(exc)
    else:
        raise AssertionError("Référence dupliquée entre pour et contre acceptée")


def test_finalize_rejects_rewrite_of_historical_summary(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    content.prepare_review(project, "debat_test", work_id)
    complete_content_review(workspace)
    path = workspace / "reviews/fr/content_review.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["arguments"][0]["review"]["summary_decision"] = "change"
    data["arguments"][0]["review"]["proposed_summary"] = "Un nouveau résumé qui ne doit pas être publié dans une reprise historique ordinaire."
    common.write_json(path, data)
    try:
        content.finalize_review(project, "debat_test", work_id)
    except content.ContentReviewError as exc:
        assert "résumé historique" in str(exc)
    else:
        raise AssertionError("Réécriture d’un résumé historique acceptée")


def test_finalize_rejects_unverified_source(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    content.prepare_review(project, "debat_test", work_id)
    complete_content_review(workspace)
    path = workspace / "data/sources_working.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["sources"][0]["verification"]["status"] = "unverified"
    common.write_json(path, data)
    try:
        content.finalize_review(project, "debat_test", work_id)
    except content.ContentReviewError as exc:
        assert "non vérifiée" in str(exc)
    else:
        raise AssertionError("Source non vérifiée acceptée")


def test_apply_content_review_creates_distinct_copy(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    content.prepare_review(project, "debat_test", work_id)
    complete_content_review(workspace)
    finalized = content.finalize_review(project, "debat_test", work_id)
    corpus_hash = common.full_tree_sha256(project / "corpus/debat_test")
    working_hash = common.full_tree_sha256(workspace / "working-copy")
    reviewed_hash = common.full_tree_sha256(workspace / "reviewed-copy")
    metadata_lock = (workspace / "reviewed-copy/data/fr_page_metadata_lock.json").read_bytes()
    result = content.apply_review(project, "debat_test", work_id, finalized["review_sha256"])
    target = workspace / "content-reviewed-copy"
    assert result["status"] == "fr_content_applied"
    assert target.is_dir()
    assert common.full_tree_sha256(project / "corpus/debat_test") == corpus_hash
    assert common.full_tree_sha256(workspace / "working-copy") == working_hash
    assert common.full_tree_sha256(workspace / "reviewed-copy") == reviewed_hash
    assert (target / "data/fr_page_metadata_lock.json").read_bytes() == metadata_lock
    assert not (target / "output").exists()
    lock = json.loads((target / "data/fr_content_lock.json").read_text(encoding="utf-8"))
    assert lock["status"] == "locked_for_translation_and_generation"
    assert len(lock["arguments"]) == 4
    decisions = lock["historical_text_decisions"]
    assert decisions["policy"] == content.HISTORICAL_TEXT_POLICY
    assert decisions["debate"]["decision"] == "preserved"
    assert all(row["decision"] == "preserved" for row in decisions["arguments"])
    changes = json.loads((target / "changes/fr_content_changeset.json").read_text(encoding="utf-8"))
    assert not any(op["field"] in {"summary", "introduction"} for op in changes["operations"])
    sources = json.loads((target / "data/sources.json").read_text(encoding="utf-8"))
    assert len(sources["sources"]) == 6
    translation = json.loads((workspace / "reviews/en/translation_readiness.json").read_text(encoding="utf-8"))
    assert translation["status"] == "ready_for_translation"


def test_historically_absent_summary_stays_absent_through_apply(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    reviewed = workspace / "reviewed-copy"
    provenance_path = reviewed / "data/import_provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    row = next(item for item in provenance["pages"] if item.get("page_id") == "A0001")
    page = reviewed / row["import_path"]
    text = page.read_text(encoding="utf-8")
    assert "|résumé=A" in text
    page.write_text(text.replace("|résumé=A", "", 1), encoding="utf-8")
    import hashlib
    row["sha256"] = hashlib.sha256(page.read_bytes()).hexdigest()
    row["size_bytes"] = page.stat().st_size
    common.write_json(provenance_path, provenance)
    meta_path = workspace / "workspace.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["reviewed_copy"]["tree_sha256"] = common.full_tree_sha256(reviewed)
    meta["workspace_sha256"] = None
    meta["workspace_sha256"] = workspace_tool.workspace_receipt_hash(meta)
    common.write_json(meta_path, meta)

    content.prepare_review(project, "debat_test", work_id)
    review = json.loads((workspace / "reviews/fr/content_review.json").read_text(encoding="utf-8"))
    item = next(row for row in review["arguments"] if row["id"] == "A0001")
    assert item["source"]["summary"] == ""
    assert item["review"]["summary_decision"] == "keep"
    assert item["review"]["historical_summary_present"] is False
    complete_content_review(workspace)
    finalized = content.finalize_review(project, "debat_test", work_id)
    content.apply_review(project, "debat_test", work_id, finalized["review_sha256"])
    target = workspace / "content-reviewed-copy"
    lock = json.loads((target / "data/fr_content_lock.json").read_text(encoding="utf-8"))
    final = next(row for row in lock["arguments"] if row["id"] == "A0001")
    assert final["summary"] is None
    assert final["summary_provenance"] == "historical_absent"
    style = json.loads((target / "reviews/summary_style_review.json").read_text(encoding="utf-8"))
    entry = next(row for row in style["entries"] if row["id"] == "A0001")
    assert entry["languages"]["fr"]["status"] == "historical_absent"


def test_apply_requires_exact_review_hash(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    content.prepare_review(project, "debat_test", work_id)
    complete_content_review(workspace)
    content.finalize_review(project, "debat_test", work_id)
    try:
        content.apply_review(project, "debat_test", work_id, "0" * 64)
    except content.ContentReviewError as exc:
        assert "empreinte confirmée" in str(exc)
    else:
        raise AssertionError("Mauvaise empreinte acceptée")
    assert not (workspace / "content-reviewed-copy").exists()


def test_finalize_rejects_reviewed_copy_changed_after_prepare(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    content.prepare_review(project, "debat_test", work_id)
    complete_content_review(workspace)
    (workspace / "reviewed-copy/scope.json").write_text("{}\n", encoding="utf-8")
    try:
        content.finalize_review(project, "debat_test", work_id)
    except content.ContentReviewError as exc:
        assert "reviewed-copy" in str(exc)
    else:
        raise AssertionError("Copie révisée altérée acceptée")


def test_finalize_rejects_youtube_video_without_creator(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    content.prepare_review(project, "debat_test", work_id)
    complete_content_review(workspace)
    sources_path = workspace / "data/sources_working.json"
    data = json.loads(sources_path.read_text(encoding="utf-8"))
    video = next(row for row in data["sources"] if row["id"] == "S00005")
    video["metadata"]["link"] = "https://www.youtube.com/watch?v=example"
    video["metadata"]["authors"] = []
    common.write_json(sources_path, data)
    try:
        content.finalize_review(project, "debat_test", work_id)
    except content.ContentReviewError as exc:
        assert "créateur ou la chaîne" in str(exc)
    else:
        raise AssertionError("Vidéo YouTube sans créateur acceptée")


def test_finalize_accepts_historical_introduction_without_current_stakes_section(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    content.prepare_review(project, "debat_test", work_id)
    complete_content_review(workspace)
    result = content.finalize_review(project, "debat_test", work_id)
    assert result["status"] == "fr_content_review_finalized"


def test_finalize_rejects_rewrite_of_historical_introduction(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    content.prepare_review(project, "debat_test", work_id)
    complete_content_review(workspace)
    review_path = workspace / "reviews/fr/content_review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    debate = review["debate"]["review"]
    debate["introduction_decision"] = "change"
    debate["proposed_introduction"] = "{{Sous-partie|titre=Nouvelle introduction|contenu=Cette introduction ne doit pas remplacer le texte historique dans la reprise ordinaire.}}"
    common.write_json(review_path, review)
    try:
        content.finalize_review(project, "debat_test", work_id)
    except content.ContentReviewError as exc:
        assert "introduction historique" in str(exc)
    else:
        raise AssertionError("Réécriture de l’introduction historique acceptée")



def test_specialized_term_inventory_covers_links_and_prior_treatment():
    from wikidebia_content_review import _validated_specialized_term_inventory
    intro = "{{Sous-partie|titre=Définition|contenu=Un {{Lien Wikipédia|article=Nécessité|texte-affiché=principe nécessaire}} est distingué.}}{{Sous-partie|titre=Suite|contenu=Le principe nécessaire est repris.}}"
    ledger=[{"title":"Définition","technical_or_specialized":True},{"title":"Suite","technical_or_specialized":True}]
    inventory=[{"subsection_title":"Définition","scan_complete":True,"scan_note":"La sous-partie entière a été relue pour identifier toutes les notions spécialisées.","terms":[{"term":"principe nécessaire","treatment":"wikipedia_link","article":"Nécessité"}]},{"subsection_title":"Suite","scan_complete":True,"scan_note":"La sous-partie entière a été relue et la répétition renvoie au premier traitement.","terms":[{"term":"principe nécessaire","treatment":"prior_treatment","prior_subsection_title":"Définition","prior_term":"principe nécessaire"}]}]
    assert _validated_specialized_term_inventory(intro,inventory,ledger)[1]['terms'][0]['treatment']=='prior_treatment'


def test_specialized_term_inventory_rejects_undeclared_link():
    from wikidebia_content_review import _validated_specialized_term_inventory, ContentReviewError
    intro = "{{Sous-partie|titre=Définition|contenu=Un {{Lien Wikipédia|article=Nécessité|texte-affiché=principe nécessaire}} est distingué.}}"
    ledger=[{"title":"Définition","technical_or_specialized":True}]
    inventory=[{"subsection_title":"Définition","scan_complete":True,"scan_note":"La sous-partie entière a été relue pour identifier toutes les notions spécialisées.","terms":[{"term":"principe nécessaire","treatment":"context_sufficient","justification":"Le contexte donne une définition complète de cette notion dans la phrase."}]}]
    try:
        _validated_specialized_term_inventory(intro,inventory,ledger)
    except ContentReviewError:
        return
    raise AssertionError('le lien non déclaré devait être refusé')


def test_argument_established_name_parameters_are_preserved_import_parameters():
    assert 'nom-consacré' in content.PAGE_LIFECYCLE_PARAMETERS['argument']
    assert 'nom' in content.PAGE_LIFECYCLE_PARAMETERS['argument']

# Historical test-name alias retained for non-regression traceability.
def test_argument_name_is_a_preserved_import_parameter():
    assert 'nom' in content.PAGE_LIFECYCLE_PARAMETERS['argument']


def test_prepare_content_review_accepts_explicitly_retired_provenance_rows(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    reviewed = workspace / "reviewed-copy"
    provenance_path = reviewed / "data/import_provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    source = next(row for row in provenance["pages"] if row.get("kind") == "argument")
    for page_id, status in (("A9001", "retired_redirect"), ("A9002", "retired_deleted")):
        row = copy.deepcopy(source)
        row["page_id"] = page_id
        row["status"] = status
        row["import_path"] = source["import_path"]
        provenance["pages"].append(row)
    common.write_json(provenance_path, provenance)
    meta_path = workspace / "workspace.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["reviewed_copy"]["tree_sha256"] = common.full_tree_sha256(reviewed)
    meta["workspace_sha256"] = None
    meta["workspace_sha256"] = workspace_tool.workspace_receipt_hash(meta)
    common.write_json(meta_path, meta)

    result = content.prepare_review(project, "debat_test", work_id)
    assert result["status"] == "fr_content_review_ready"
    review = json.loads((workspace / "reviews/fr/content_review.json").read_text(encoding="utf-8"))
    assert {item["id"] for item in review["arguments"]} == {"A0001", "A0002", "A0003", "A0004"}


def test_prepare_content_review_rejects_unretired_extra_provenance_row(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    reviewed = workspace / "reviewed-copy"
    provenance_path = reviewed / "data/import_provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    source = next(row for row in provenance["pages"] if row.get("kind") == "argument")
    row = copy.deepcopy(source)
    row["page_id"] = "A9001"
    row["status"] = "active_import"
    provenance["pages"].append(row)
    common.write_json(provenance_path, provenance)
    meta_path = workspace / "workspace.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["reviewed_copy"]["tree_sha256"] = common.full_tree_sha256(reviewed)
    meta["workspace_sha256"] = None
    meta["workspace_sha256"] = workspace_tool.workspace_receipt_hash(meta)
    common.write_json(meta_path, meta)

    import pytest
    with pytest.raises(content.ContentReviewError, match="non actifs.*pas explicitement retirés"):
        content.prepare_review(project, "debat_test", work_id)


def test_finalize_rejects_invalid_document_kind_in_working_registry(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    content.prepare_review(project, "debat_test", work_id)
    complete_content_review(workspace)
    path = workspace / "data/sources_working.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    registry["sources"][0]["document_kind"] = "website"
    common.write_json(path, registry)
    try:
        content.finalize_review(project, "debat_test", work_id)
    except content.ContentReviewError as exc:
        assert "document_kind" in str(exc)
        assert "website" in str(exc)
    else:
        raise AssertionError("document_kind hors schéma accepté dans sources_working.json")


def _set_reviewed_historical_text(workspace: Path, *, intro: str | None = None, summary_a0001: str | None = None) -> None:
    reviewed = workspace / "reviewed-copy"
    provenance_path = reviewed / "data/import_provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    for row in provenance["pages"]:
        if intro is not None and row.get("kind") == "debate":
            page = reviewed / row["import_path"]
            text = page.read_text(encoding="utf-8")
            parsed = content.iter_templates(text)[0]
            old = parsed.get("introduction") or ""
            if "introduction" in parsed.params:
                text = text.replace(f"|introduction={old}", f"|introduction={intro}", 1)
            else:
                # The compact fixture has no introduction parameter at all.
                # Insert it into the outer Debate template instead of relying
                # on a replacement of a non-existent empty parameter.
                newline = "\n" if text.endswith("\n") else ""
                body = text[:-1] if newline else text
                if not body.endswith("}}"):
                    raise AssertionError("Fixture Débat inattendue")
                body = body[:-2] + "|introduction=" + intro + "}}"
                text = body + newline
            page.write_text(text, encoding="utf-8")
            row["sha256"] = __import__("hashlib").sha256(page.read_bytes()).hexdigest()
            row["size_bytes"] = page.stat().st_size
        if summary_a0001 is not None and row.get("page_id") == "A0001":
            page = reviewed / row["import_path"]
            text = page.read_text(encoding="utf-8")
            parsed = content.iter_templates(text)[0]
            old = parsed.get("résumé") or ""
            if old:
                text = text.replace(f"|résumé={old}", f"|résumé={summary_a0001}", 1)
            else:
                text = text.replace("{{Argument\n", f"{{{{Argument\n|résumé={summary_a0001}\n", 1)
            page.write_text(text, encoding="utf-8")
            row["sha256"] = __import__("hashlib").sha256(page.read_bytes()).hexdigest()
            row["size_bytes"] = page.stat().st_size
    common.write_json(provenance_path, provenance)
    meta_path = workspace / "workspace.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["reviewed_copy"]["tree_sha256"] = common.full_tree_sha256(reviewed)
    meta["workspace_sha256"] = None
    meta["workspace_sha256"] = workspace_tool.workspace_receipt_hash(meta)
    common.write_json(meta_path, meta)


def _request_historical_change(holder: dict, *, field_key: str, final_value: str, change_type: str = "typo", rationale: str = "Correction historique explicitement approuvée par le propriétaire.") -> None:
    holder["historical_text_status"] = "authorization_requested"
    holder["historical_change_request"] = {
        "field_key": field_key,
        "final_value": final_value,
        "change_type": change_type,
        "rationale": rationale,
        "owner_instruction_reference": "conversation-owner-approval",
    }


def _write_direct_owner_authorization(workspace: Path, review: dict) -> dict:
    requested = content.collect_historical_change_requests(review)
    auth_id = "test-owner-auth"
    changes = []
    for row in requested:
        item = copy.deepcopy(row)
        item.update({
            "authorization_id": auth_id,
            "package_id": "test-package",
            "manifest_sha256": "a" * 64,
            "returned_archive_sha256": "b" * 64,
        })
        changes.append(item)
    auth = {
        "schema": content.HISTORICAL_AUTHORIZATION_SCHEMA,
        "schema_version": "1.0",
        "authorization_id": auth_id,
        "debate_id": review["debate_id"],
        "work_id": review["work_id"],
        "review_type": "fr_content_review",
        "package_id": "test-package",
        "manifest_sha256": "a" * 64,
        "returned_archive_sha256": "b" * 64,
        "review_payload_sha256": content.content_review_sha256(review),
        "authorization_method": "owner_explicit_cli_flag",
        "authorization_command": "review-import --authorize-historical-changes",
        "authorized_at": "2026-08-12T19:00:00+02:00",
        "changes": changes,
        "authorization_sha256": None,
    }
    auth["authorization_sha256"] = content._authorization_hash(auth)
    common.write_json(workspace / content.HISTORICAL_AUTHORIZATION_PATH, auth)
    return auth


def test_historical_suggestion_without_consent_is_preserved(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    content.prepare_review(project, "debat_test", work_id)
    complete_content_review(workspace)
    path = workspace / "reviews/fr/content_review.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    row = data["arguments"][0]["review"]
    row["suggested_change"] = {"value": "Suggestion non autorisée.", "change_type": "typo", "rationale": "Suggestion seulement, sans consentement propriétaire."}
    common.write_json(path, data)
    finalized = content.finalize_review(project, "debat_test", work_id)
    assert finalized["status"] == "fr_content_review_finalized"
    sealed = json.loads(path.read_text(encoding="utf-8"))
    assert sealed["final_values"]["arguments"][0]["summary"] == data["arguments"][0]["source"]["summary"]


def test_authorized_local_summary_correction_is_accepted_without_creation_style_rewrite(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    content.prepare_review(project, "debat_test", work_id)
    complete_content_review(workspace)
    path = workspace / "reviews/fr/content_review.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    item = data["arguments"][0]
    final = "A corrigé."
    item["review"]["summary_decision"] = "change"
    item["review"]["proposed_summary"] = final
    _request_historical_change(item["review"], field_key="argument:A0001:summary", final_value=final, change_type="grammar")
    common.write_json(path, data)
    _write_direct_owner_authorization(workspace, data)
    result = content.finalize_review(project, "debat_test", work_id)
    sealed = json.loads(path.read_text(encoding="utf-8"))
    arg = next(x for x in sealed["final_values"]["arguments"] if x["id"] == "A0001")
    assert result["authorized_historical_text_changes"] == 1
    assert arg["summary"] == final
    assert arg["historical_text_decision"] == "authorized_change"
    assert arg["attestations"] == {}


def test_authorized_substantive_summary_rewrite_is_scoped_and_traced(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    content.prepare_review(project, "debat_test", work_id)
    complete_content_review(workspace)
    path = workspace / "reviews/fr/content_review.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    item = data["arguments"][1]
    final = "Réécriture substantielle explicitement demandée pour ce seul résumé historique."
    item["review"]["summary_decision"] = "change"
    item["review"]["proposed_summary"] = final
    _request_historical_change(item["review"], field_key="argument:A0002:summary", final_value=final, change_type="substantive_rewrite")
    common.write_json(path, data)
    auth = _write_direct_owner_authorization(workspace, data)
    content.finalize_review(project, "debat_test", work_id)
    sealed = json.loads(path.read_text(encoding="utf-8"))
    arg = next(x for x in sealed["final_values"]["arguments"] if x["id"] == "A0002")
    assert arg["historical_authorization"]["authorization_id"] == auth["authorization_id"]
    assert arg["summary"] == final


def test_unauthorized_extra_historical_change_is_blocked_even_with_other_authorization(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    content.prepare_review(project, "debat_test", work_id)
    complete_content_review(workspace)
    path = workspace / "reviews/fr/content_review.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    first = data["arguments"][0]
    first["review"]["summary_decision"] = "change"
    first["review"]["proposed_summary"] = "Correction autorisée."
    _request_historical_change(first["review"], field_key="argument:A0001:summary", final_value="Correction autorisée.")
    common.write_json(path, data)
    _write_direct_owner_authorization(workspace, data)
    # Add a second unrequested delta after the authorization has been sealed.
    second = data["arguments"][1]
    second["review"]["summary_decision"] = "change"
    second["review"]["proposed_summary"] = "Modification parasite."
    common.write_json(path, data)
    try:
        content.finalize_review(project, "debat_test", work_id)
    except content.ContentReviewError as exc:
        assert "résumé historique" in str(exc) or "autorisation" in str(exc)
    else:
        raise AssertionError("Une modification historique hors portée a été acceptée")


def test_historically_absent_summary_creation_requires_nominative_consent(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    _set_reviewed_historical_text(workspace, summary_a0001="")
    # Explicitly remove the summary parameter after helper normalization.
    reviewed = workspace / "reviewed-copy"
    prov_path = reviewed / "data/import_provenance.json"
    prov = json.loads(prov_path.read_text(encoding="utf-8"))
    row = next(x for x in prov["pages"] if x.get("page_id") == "A0001")
    page = reviewed / row["import_path"]
    text = page.read_text(encoding="utf-8").replace("|résumé=\n", "", 1)
    page.write_text(text, encoding="utf-8")
    row["sha256"] = __import__("hashlib").sha256(page.read_bytes()).hexdigest(); row["size_bytes"] = page.stat().st_size
    common.write_json(prov_path, prov)
    meta_path = workspace / "workspace.json"; meta = json.loads(meta_path.read_text()); meta["reviewed_copy"]["tree_sha256"] = common.full_tree_sha256(reviewed); meta["workspace_sha256"] = None; meta["workspace_sha256"] = workspace_tool.workspace_receipt_hash(meta); common.write_json(meta_path, meta)
    content.prepare_review(project, "debat_test", work_id); complete_content_review(workspace)
    path = workspace / "reviews/fr/content_review.json"; data = json.loads(path.read_text())
    item = data["arguments"][0]; item["review"]["summary_decision"] = "change"; item["review"]["proposed_summary"] = "Résumé créé sans autorisation."
    common.write_json(path, data)
    try:
        content.finalize_review(project, "debat_test", work_id)
    except content.ContentReviewError as exc:
        assert "résumé historique" in str(exc)
    else:
        raise AssertionError("Création d’un résumé historiquement absent sans consentement acceptée")


def test_historically_absent_summary_creation_with_nominative_consent_is_accepted(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    # Reuse the proven absent-summary setup from the existing regression.
    reviewed = workspace / "reviewed-copy"; prov_path = reviewed / "data/import_provenance.json"; prov = json.loads(prov_path.read_text())
    row = next(x for x in prov["pages"] if x.get("page_id") == "A0001"); page = reviewed / row["import_path"]
    page.write_text(page.read_text().replace("|résumé=A", "", 1), encoding="utf-8")
    row["sha256"] = __import__("hashlib").sha256(page.read_bytes()).hexdigest(); row["size_bytes"] = page.stat().st_size; common.write_json(prov_path, prov)
    meta_path=workspace/"workspace.json"; meta=json.loads(meta_path.read_text()); meta["reviewed_copy"]["tree_sha256"]=common.full_tree_sha256(reviewed); meta["workspace_sha256"]=None; meta["workspace_sha256"]=workspace_tool.workspace_receipt_hash(meta); common.write_json(meta_path,meta)
    content.prepare_review(project,"debat_test",work_id); complete_content_review(workspace)
    path=workspace/"reviews/fr/content_review.json"; data=json.loads(path.read_text()); item=data["arguments"][0]
    final="Résumé créé parce que le propriétaire a explicitement demandé la création de ce résumé précis."
    item["review"]["summary_decision"]="change"; item["review"]["proposed_summary"]=final
    _request_historical_change(item["review"], field_key="argument:A0001:summary", final_value=final, change_type="create_summary")
    common.write_json(path,data); _write_direct_owner_authorization(workspace,data); content.finalize_review(project,"debat_test",work_id)
    sealed=json.loads(path.read_text()); arg=next(x for x in sealed["final_values"]["arguments"] if x["id"]=="A0001")
    assert arg["summary_provenance"] == "historical_authorized_creation" and arg["summary"] == final


def test_authorized_introduction_removes_references_tag(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    old = "{{Sous-partie|titre=Contexte|contenu=Texte historique.<references />}}"
    _set_reviewed_historical_text(workspace, intro=old)
    content.prepare_review(project,"debat_test",work_id); complete_content_review(workspace)
    path=workspace/"reviews/fr/content_review.json"; data=json.loads(path.read_text()); rev=data["debate"]["review"]
    final=old.replace("<references />", "")
    rev["introduction_decision"]="change"; rev["proposed_introduction"]=final; rev["subsections"]=[{"title":"Contexte"}]
    _request_historical_change(rev, field_key="debate:debat_test:introduction", final_value=final, change_type="mediawiki_syntax")
    common.write_json(path,data); _write_direct_owner_authorization(workspace,data); content.finalize_review(project,"debat_test",work_id)
    sealed=json.loads(path.read_text()); assert "<references" not in sealed["final_values"]["debate"]["introduction"]


def test_authorized_introduction_adds_stakes_subsection_without_third_publication_contract(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    old="{{Sous-partie|titre=Contexte|contenu=Texte historique.}}"; _set_reviewed_historical_text(workspace,intro=old)
    content.prepare_review(project,"debat_test",work_id); complete_content_review(workspace)
    path=workspace/"reviews/fr/content_review.json"; data=json.loads(path.read_text()); rev=data["debate"]["review"]
    stakes=(
        "Le choix d’un dispositif de vote modifie concrètement la manière dont les citoyens peuvent participer et contrôler le scrutin. "
        "Une panne ou une faille peut empêcher des électeurs de voter, retarder la proclamation des résultats ou fragiliser la confiance dans leur exactitude. "
        "À l’inverse, un système accessible à distance peut faciliter la participation de personnes éloignées ou empêchées. "
        "Le débat porte donc aussi sur la continuité du service électoral, l’accessibilité du vote et la confiance publique dans le résultat."
    )
    final=old+f"{{{{Sous-partie|titre=Enjeux du débat|contenu={stakes}}}}}"
    rev["introduction_decision"]="change"; rev["proposed_introduction"]=final
    rev["subsections"]=[
        {"title":"Contexte"},
        {"title":"Enjeux du débat","purpose":"Présenter les incidences concrètes nécessaires à la compréhension du désaccord.","necessary_for_understanding":True,"technical_or_specialized":False,"relevance_to_debate_explained":False,"stakes_section":True,"concrete_stakes":["Continuité et accessibilité concrète du service électoral pour les citoyens.","Confiance publique dans l’exactitude et la légitimité du résultat électoral."]},
    ]
    rev["specialized_term_inventory"]=[{"subsection_title":"Enjeux du débat","scan_complete":True,"scan_note":"La nouvelle sous-partie a été relue intégralement et ne contient pas de notion spécialisée nécessitant un traitement supplémentaire.","terms":[]}]
    rev["terminal_period_sentence_exceptions"]=[]
    _request_historical_change(rev, field_key="debate:debat_test:introduction", final_value=final, change_type="structure")
    rev["historical_change_request"]["change_scope"]=content._subsection_change_scope(old,final)
    common.write_json(path,data); _write_direct_owner_authorization(workspace,data); content.finalize_review(project,"debat_test",work_id)
    sealed=json.loads(path.read_text()); assert "Enjeux du débat" in sealed["final_values"]["debate"]["introduction"]


def test_content_lock_records_history_final_and_owner_consent(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path); content.prepare_review(project,"debat_test",work_id); complete_content_review(workspace)
    path=workspace/"reviews/fr/content_review.json"; data=json.loads(path.read_text()); item=data["arguments"][0]; old=item["source"]["summary"]; final="Correction autorisée et tracée."
    item["review"]["summary_decision"]="change"; item["review"]["proposed_summary"]=final; _request_historical_change(item["review"],field_key="argument:A0001:summary",final_value=final)
    common.write_json(path,data); auth=_write_direct_owner_authorization(workspace,data); finalized=content.finalize_review(project,"debat_test",work_id); content.apply_review(project,"debat_test",work_id,finalized["review_sha256"])
    lock=json.loads((workspace/"content-reviewed-copy/data/fr_content_lock.json").read_text()); row=next(x for x in lock["historical_text_decisions"]["arguments"] if x["id"]=="A0001")
    assert row["historical_sha256"] == content._historical_text_sha256(old)
    assert row["final_sha256"] == content._historical_text_sha256(final)
    assert row["decision"] == "authorized_change"
    assert row["authorization"]["authorization_id"] == auth["authorization_id"]
    changes=json.loads((workspace/"content-reviewed-copy/changes/fr_content_changeset.json").read_text())
    assert any(op["entity_id"]=="A0001" and op["field"]=="summary" for op in changes["operations"])


def test_legacy_review_delta_migrates_to_suggestion_without_losing_it():
    legacy={"debate_id":"d","debate":{"source":{"page_origin":"preexisting","introduction":"Ancien"},"review":{"introduction_decision":"change","proposed_introduction":"Proposé","introduction_rationale":"Proposition historique héritée assez détaillée."}},"arguments":[]}
    normalized,migration=content.normalize_historical_review_document(legacy)
    rev=normalized["debate"]["review"]
    assert migration["legacy_format_detected"] is True
    assert rev["introduction_decision"]=="keep" and rev["proposed_introduction"]=="Ancien"
    assert rev["suggested_change"]["value"]=="Proposé"


def test_legacy_review_with_explicit_change_request_preserves_authorizable_delta():
    legacy={"debate_id":"d","debate":{"source":{"page_origin":"preexisting","introduction":"Ancien"},"review":{"introduction_decision":"change","proposed_introduction":"Corrigé","historical_change_request":{"field_key":"debate:d:introduction","final_value":"Corrigé","change_type":"typo","rationale":"Correction précise explicitement proposée et approuvable.","owner_instruction_reference":"owner-msg"}}},"arguments":[]}
    normalized,migration=content.normalize_historical_review_document(legacy)
    assert normalized["debate"]["review"]["proposed_introduction"]=="Corrigé"
    assert migration["requests_preserved"]==1
    assert content.collect_historical_change_requests(normalized)[0]["field_key"]=="debate:d:introduction"
