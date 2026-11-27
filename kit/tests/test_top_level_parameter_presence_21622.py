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
import wikidebia_render as render
import wikidebia_translation_review as translation
import wikidebia_update as update
import wikidebia_editorial_workspace as workspace_tool

from test_wikidebia_content_review import make_metadata_applied, complete_content_review
from test_wikidebia_remote_update import make_fixture, FakeAdapter, TEST_VALIDATOR_PYTHON, argument


from french_normalization_fixture import prepare_fixture_translation

def _presence(names: list[str], present: set[str]) -> dict[str, dict[str, bool]]:
    return {name: {"present": name in present} for name in names}


def _a0021_rendered() -> str:
    node = {
        "id": "A0021",
        "fr": {"rubriques": ["Politique"], "keywords": ["vote électronique"]},
        "en": {"canonical_title": "Electronic voting argument"},
    }
    registry = {"graph": {"edges": [], "occurrences": [], "nodes": [node]}}
    source_presence = _presence(
        list(content.PAGE_EDITORIAL_PARAMETERS["argument"]),
        {"résumé", "citations", "justifications", "objections", "rubriques", "mots-clés"},
    )
    page = {
        "summary": "Résumé final inchangé dans sa présence top-level.",
        "citations": [],
        "sources": {},
        "page_origin": "preexisting",
        "preserved_parameters": {},
        "source_parameter_presence": source_presence,
    }
    return render._render_argument(
        lang="fr", node=node, content=page, registry=registry, sources={},
        include_interlanguage=False,
    )


def test_a0021_historical_empty_objections_is_canonically_omitted():
    remote = """{{Argument
|résumé=Résumé historique.
|citations=
|justifications=
|objections=
|rubriques=Politique
|mots-clés=vote électronique
}}
"""
    proposed = _a0021_rendered()
    assert "|objections=" not in proposed
    assert update.top_level_parameter_deletions(remote, proposed, "fr", "argument") == ["citations", "justifications", "objections"]


def test_historical_debate_documentary_buckets_are_omitted_when_empty():
    registry = {"debate": {"pages": {"en": {"canonical_title": "Should electronic voting be generalized?"}}}, "graph": {"edges": [], "occurrences": [], "nodes": []}}
    present = {
        "introduction", "articles-Wikipédia", "arguments-pour", "arguments-contre",
        "bibliographie-pour", "vidéographie-contre", "rubriques", "mots-clés",
    }
    debate = {
        "subject": "Vote électronique",
        "complete_topic": "la généralisation du vote électronique",
        "introduction": "{{Sous-partie|titre=Définition|contenu=Texte historique.}}",
        "wikipedia_articles": ["Vote électronique"],
        "documentation": {bucket: [] for bucket in content.DEBATE_BUCKETS},
        "page_origin": "preexisting",
        "preserved_parameters": {},
        "source_parameter_presence": _presence(list(content.PAGE_EDITORIAL_PARAMETERS["debate"]), present),
    }
    text = render._render_debate(
        lang="fr", registry=registry, metadata_lock={"debate": {"rubriques": ["Politique"], "keywords": ["vote électronique"]}},
        content_lock={"debate": debate}, sources={}, include_interlanguage=False,
    )
    assert "|bibliographie-pour=" not in text
    assert "|vidéographie-contre=" not in text
    # Historically absent + logically empty must remain absent.
    assert "|bibliographie-contre=" not in text
    assert "|sitographie-pour=" not in text
    remote = """{{Débat
|sujet=Vote électronique
|sujet-développé=la généralisation du vote électronique
|introduction={{Sous-partie|titre=Définition|contenu=Texte historique.}}
|articles-Wikipédia={{Article Wikipédia|page=Vote électronique}}
|bibliographie-pour={{Référence bibliographique pour|ouvrage=Elections Canada}}
|vidéographie-contre={{Référence vidéographique contre|titre=Hacking Democracy}}
|rubriques=Politique
|mots-clés=vote électronique
}}
"""
    assert update.top_level_parameter_deletions(remote, text, "fr", "debate") == ["bibliographie-pour", "vidéographie-contre"]


def test_new_page_does_not_gain_empty_parameters_from_logical_empty_values():
    node = {"id": "A9999", "fr": {"rubriques": ["Politique"], "keywords": ["vote"]}, "en": {"canonical_title": "Vote"}}
    registry = {"graph": {"edges": [], "occurrences": [], "nodes": [node]}}
    page = {"summary": "Résumé.", "citations": [], "sources": {}, "page_origin": "new", "preserved_parameters": {}, "source_parameter_presence": {}}
    text = render._render_argument(lang="fr", node=node, content=page, registry=registry, sources={}, include_interlanguage=False)
    assert "|citations=" not in text
    assert "|justifications=" not in text
    assert "|objections=" not in text


def test_historical_nonempty_value_is_never_emptied_by_presence_preservation():
    params: list[tuple[str, object]] = []
    page = {
        "page_origin": "preexisting",
        "source_parameter_presence": {"objections": {"present": True}},
    }
    value = "{{Objection|page=Objection historique|titre-affiché=Objection historique}}"
    render._append_editorial_parameter(params, page, "objections", value)
    assert params == [("objections", value)]


def test_explicit_allowed_parameter_deletion_remains_authorized(tmp_path: Path):
    remote = "{{Argument\n|résumé=Ancien\n|objections={{Objection|page=X|titre-affiché=X}}\n|rubriques=Société\n}}\n"
    proposed = "{{Argument\n|résumé=Nouveau\n|rubriques=Société\n}}\n"
    config, path = make_fixture(
        tmp_path,
        old_pages=[("fr", "A1", "Titre", remote)],
        new_pages=[("fr", "A1", "Titre", proposed)],
    )
    corpus = tmp_path / "corpus/demo"
    manifest_path = corpus / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["editorial_controls"] = {
        "legacy_content_preservation": {"lock_path": "data/legacy_lock.json"}
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (corpus / "data").mkdir(exist_ok=True)
    (corpus / "data/legacy_lock.json").write_text(json.dumps({
        "allowed_parameter_deletions": [{"page_id": "A1", "language": "fr", "parameter": "objections"}]
    }), encoding="utf-8")
    adapter = FakeAdapter({("fr", "Titre"): (10, remote)})
    plan = update.RemoteUpdatePlanner(config, adapter, path).build_plan()
    assert plan["counts"]["update"] == 1
    assert plan["counts"]["blocked"] == 0


def _inject_real_presence_shapes(workspace: Path) -> None:
    reviewed = workspace / "reviewed-copy"
    provenance_path = reviewed / "data/import_provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    debate_row = next(row for row in provenance["pages"] if row.get("kind") == "debate")
    debate_path = reviewed / debate_row["import_path"]
    text = debate_path.read_text(encoding="utf-8")
    text = text.replace(
        "|rubriques=",
        "|bibliographie-pour={{Référence bibliographique pour|ouvrage=Elections Canada}}"
        "|vidéographie-contre={{Référence vidéographique contre|titre=Hacking Democracy}}"
        "|rubriques=",
        1,
    )
    debate_path.write_text(text, encoding="utf-8")
    debate_row["sha256"] = hashlib.sha256(debate_path.read_bytes()).hexdigest()
    debate_row["size_bytes"] = debate_path.stat().st_size
    common.write_json(provenance_path, provenance)
    meta_path = workspace / "workspace.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["reviewed_copy"]["tree_sha256"] = common.full_tree_sha256(reviewed)
    meta["workspace_sha256"] = None
    meta["workspace_sha256"] = workspace_tool.workspace_receipt_hash(meta)
    common.write_json(meta_path, meta)


def test_vote_electronique_v8_presence_flows_import_to_lock_checkpoint_and_english_handoff(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    _inject_real_presence_shapes(workspace)
    content.prepare_review(project, "debat_test", work_id)
    complete_content_review(workspace)
    review_path = workspace / "reviews/fr/content_review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    # The historical buckets were non-empty, but the reviewed editorial result is empty.
    review["debate"]["review"]["proposed_documentation"]["bibliographie-pour"] = []
    review["debate"]["review"]["proposed_documentation"]["vidéographie-contre"] = []
    common.write_json(review_path, review)
    # S00006 was used only by the historical videography-con bucket; once that
    # bucket is reviewed to empty it must leave the controlled source registry.
    sources_path = workspace / "data/sources_working.json"
    sources_doc = json.loads(sources_path.read_text(encoding="utf-8"))
    sources_doc["sources"] = [row for row in sources_doc["sources"] if row.get("id") != "S00006"]
    common.write_json(sources_path, sources_doc)
    finalized = content.finalize_review(project, "debat_test", work_id)
    content.apply_review(project, "debat_test", work_id, finalized["review_sha256"])

    lock = json.loads((workspace / "content-reviewed-copy/data/fr_content_lock.json").read_text(encoding="utf-8"))
    assert lock["debate"]["source_parameter_presence"]["bibliographie-pour"]["present"] is True
    assert lock["debate"]["source_parameter_presence"]["vidéographie-contre"]["present"] is True
    a0001 = next(row for row in lock["arguments"] if row["id"] == "A0001")
    assert a0001["source_parameter_presence"]["objections"]["present"] is True

    cp = checkpoint.build_checkpoint(project, "debat_test", work_id, stage="content")
    debate_wiki = (cp / "output/fr/debate/debate.wiki").read_text(encoding="utf-8")
    arg_wiki = (cp / "output/fr/arguments/A0001.wiki").read_text(encoding="utf-8")
    assert "|bibliographie-pour=" not in debate_wiki
    assert "|vidéographie-contre=" not in debate_wiki
    assert "|objections=" not in arg_wiki

    reviewed = workspace / "reviewed-copy"
    provenance = json.loads((reviewed / "data/import_provenance.json").read_text(encoding="utf-8"))
    debate_src = reviewed / next(row["import_path"] for row in provenance["pages"] if row.get("kind") == "debate")
    arg_src = reviewed / next(row["import_path"] for row in provenance["pages"] if row.get("page_id") == "A0001")
    debate_deletions = update.top_level_parameter_deletions(debate_src.read_text(encoding="utf-8"), debate_wiki, "fr", "debate")
    assert "bibliographie-pour" in debate_deletions
    assert "vidéographie-contre" in debate_deletions
    assert "objections" in update.top_level_parameter_deletions(arg_src.read_text(encoding="utf-8"), arg_wiki, "fr", "argument")

    prepared = prepare_fixture_translation(project, "debat_test", work_id)
    assert prepared["status"] == "en_translation_review_ready"


def test_vote_electronique_v8_remote_preflight_resolves_100_updates_without_parameter_deletion_blocks(tmp_path: Path):
    rows_old = []
    rows_new = []
    remote_pages = {}

    # A0021 real regression shape: historical empty objections is canonically omitted.
    a0021_remote = "{{Argument\n|résumé=Ancien A0021\n|objections=\n|rubriques=Politique\n|mots-clés=vote électronique\n}}\n"
    a0021_new = _a0021_rendered().replace("Résumé final inchangé dans sa présence top-level.", "Nouveau A0021")
    rows_old.append(("fr", "A0021", "A0021", a0021_remote, "argument"))
    rows_new.append(("fr", "A0021", "A0021", a0021_new, "argument"))
    remote_pages[("fr", "A0021")] = (10, a0021_remote)

    # Debate regression shape: two documentary buckets become canonically absent when empty.
    debate_remote = """{{Débat
|sujet=Vote électronique
|sujet-développé=la généralisation du vote électronique
|introduction=Texte historique
|articles-Wikipédia={{Article Wikipédia|page=Vote électronique}}
|bibliographie-pour={{Référence bibliographique pour|ouvrage=Elections Canada}}
|vidéographie-contre={{Référence vidéographique contre|titre=Hacking Democracy}}
|rubriques=Politique
|mots-clés=vote électronique
}}
"""
    registry = {"debate": {"pages": {"en": {"canonical_title": "Electronic voting"}}}, "graph": {"edges": [], "occurrences": [], "nodes": []}}
    present = {"introduction", "articles-Wikipédia", "arguments-pour", "arguments-contre", "bibliographie-pour", "vidéographie-contre", "rubriques", "mots-clés"}
    debate_content = {"subject": "Vote électronique", "complete_topic": "la généralisation du vote électronique", "introduction": "Texte historique modifié", "wikipedia_articles": ["Vote électronique"], "documentation": {bucket: [] for bucket in content.DEBATE_BUCKETS}, "page_origin": "preexisting", "preserved_parameters": {}, "source_parameter_presence": _presence(list(content.PAGE_EDITORIAL_PARAMETERS["debate"]), present)}
    debate_new = render._render_debate(lang="fr", registry=registry, metadata_lock={"debate": {"rubriques": ["Politique"], "keywords": ["vote électronique"]}}, content_lock={"debate": debate_content}, sources={}, include_interlanguage=False)
    rows_old.append(("fr", "demo", "Débat vote électronique", debate_remote, "debate"))
    rows_new.append(("fr", "demo", "Débat vote électronique", debate_new, "debate"))
    remote_pages[("fr", "Débat vote électronique")] = (11, debate_remote)

    for i in range(98):
        page_id = f"A{1000+i:04d}"
        title = f"Argument {i}"
        old = argument(f"Ancien {i}")
        new = argument(f"Nouveau {i}")
        rows_old.append(("fr", page_id, title, old, "argument"))
        rows_new.append(("fr", page_id, title, new, "argument"))
        remote_pages[("fr", title)] = (100 + i, old)

    config, path = make_fixture(tmp_path, old_pages=rows_old, new_pages=rows_new)
    adapter = FakeAdapter(remote_pages)
    plan = update.RemoteUpdatePlanner(config, adapter, path).build_plan()
    assert plan["counts"]["update"] == 100
    assert plan["counts"]["blocked"] == 0
    assert plan["counts"]["manual_review"] == 0
    assert all(not row.get("unauthorized_parameter_deletions") for row in plan["operations"]["update"])
    receipt = update.PlanExecutor(config, adapter, path).execute(plan, plan["plan_sha256"])
    assert receipt["counts"]["updated"] == 100


def test_pre_21622_applied_review_is_migrated_from_immutable_reviewed_copy(tmp_path: Path):
    project, workspace, work_id = make_metadata_applied(tmp_path)
    _inject_real_presence_shapes(workspace)
    content.prepare_review(project, "debat_test", work_id)
    complete_content_review(workspace)
    finalized = content.finalize_review(project, "debat_test", work_id)
    content.apply_review(project, "debat_test", work_id, finalized["review_sha256"])

    # Simulate an approved/applied artifact produced before 2.16.22: the
    # editorial review and the derived content lock both lack the new presence
    # inventory, but the immutable reviewed-copy still contains the historical
    # wikicode from which it can be reconstructed.
    review_path = workspace / "reviews/fr/content_review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["final_values"]["debate"].pop("source_parameter_presence", None)
    for row in review["final_values"]["arguments"]:
        row.pop("source_parameter_presence", None)
    review["review_sha256"] = content.content_review_sha256(review)
    common.write_json(review_path, review)

    target = workspace / "content-reviewed-copy"
    lock_path = target / "data/fr_content_lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock["debate"].pop("source_parameter_presence", None)
    for row in lock["arguments"]:
        row.pop("source_parameter_presence", None)
    common.write_json(lock_path, lock)

    meta_path = workspace / "workspace.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["content_reviewed_copy"]["tree_sha256"] = common.full_tree_sha256(target)
    meta["content_reviewed_copy"]["review_sha256"] = review["review_sha256"]
    meta["french_content_review"]["review_sha256"] = review["review_sha256"]
    meta["workspace_sha256"] = None
    meta["workspace_sha256"] = workspace_tool.workspace_receipt_hash(meta)
    common.write_json(meta_path, meta)

    migrated = content.apply_review(
        project,
        "debat_test",
        work_id,
        review["review_sha256"],
    )
    assert migrated["status"] == "fr_content_applied"
    assert not migrated.get("idempotent", False)

    rebuilt_lock = json.loads(lock_path.read_text(encoding="utf-8"))
    assert rebuilt_lock["debate"]["source_parameter_presence"]["bibliographie-pour"]["present"] is True
    assert rebuilt_lock["debate"]["source_parameter_presence"]["vidéographie-contre"]["present"] is True
    a0001 = next(row for row in rebuilt_lock["arguments"] if row["id"] == "A0001")
    assert a0001["source_parameter_presence"]["objections"]["present"] is True


def test_preflight_allows_canonical_optional_omission_but_blocks_non_omittable_deletion(tmp_path: Path):
    remote = "{{Débat\n|sujet=Test\n|sujet-développé=le test\n|articles-Wikipédia={{Article Wikipédia|page=Test}}\n|bibliographie-pour=\n|rubriques=Société\n|mots-clés=test\n}}\n"
    proposed = "{{Débat\n|sujet=Test\n|sujet-développé=le test\n|rubriques=Société\n|mots-clés=test\n}}\n"
    config, path = make_fixture(
        tmp_path,
        old_pages=[("fr", "demo", "Titre", remote, "debate")],
        new_pages=[("fr", "demo", "Titre", proposed, "debate")],
    )
    adapter = FakeAdapter({("fr", "Titre"): (10, remote)})
    plan = update.RemoteUpdatePlanner(config, adapter, path).build_plan()
    assert plan["counts"]["blocked"] == 1
    blocked = plan["operations"]["blocked"][0]
    assert blocked["unauthorized_parameter_deletions"] == ["articles-Wikipédia"]
    assert "bibliographie-pour" not in blocked["unauthorized_parameter_deletions"]
