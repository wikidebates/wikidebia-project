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


render = load_module("wikidebia_render")
translation = sys.modules.get("wikidebia_translation_review") or load_module("wikidebia_translation_review")
common = sys.modules["wikidebia_corpus_build"]


def fake_validator(*args, **kwargs):
    return {"validator_version": "0.4.29", "result": "passed", "summary": {"errors": 0, "warnings": 0}}


render._run_validator = fake_validator
translation._run_validator = fake_validator
from test_wikidebia_translation_review import make_french_locked, complete_translation_review, complete_semantic_convergence, mark_existing_english_argument  # noqa: E402


def make_translated(tmp_path: Path, *, reuse_existing_argument: bool = False) -> tuple[Path, Path, str, str]:
    project, workspace, work_id = make_french_locked(tmp_path)
    if reuse_existing_argument:
        mark_existing_english_argument(workspace)
    norm_path = project / "norms/normative_reference/01_normes/WIKIDEBIA_NORME_CONSOLIDEE_1.2.70.md"
    norm_path.parent.mkdir(parents=True, exist_ok=True)
    norm_path.write_text("# Norme de test 1.2.27\n", encoding="utf-8")
    translation.prepare_review(project, "debat_test", work_id)
    complete_translation_review(workspace)
    sealed = translation.finalize_review(project, "debat_test", work_id)
    complete_semantic_convergence(project, work_id)
    translation.apply_review(project, "debat_test", work_id, sealed["review_sha256"])
    translated = workspace / "translated-copy"
    registry = json.loads((translated / "data/registre_debat.json").read_text(encoding="utf-8"))
    edges = {row["id"]: row for row in registry["graph"]["edges"]}
    entries = []
    for occurrence in registry["graph"]["occurrences"]:
        depth = occurrence["depth"]
        entry = {
            "occurrence_id": occurrence["id"],
            "node_id": occurrence["node_id"],
            "declared_depth": depth,
            "placement_status": "approved",
            "direct_fit": True,
            "rationale": "Le placement a été relu formellement et correspond à la cible logique immédiate du raisonnement.",
        }
        if depth == 1:
            entry.update({
                "declared_function": "main_argument",
                "semantic_target": "debate",
                "main_argument_review": {
                    "direct_answer_to_debate": True,
                    "autonomous_without_parent": True,
                    "organizes_distinct_argument_family": True,
                    "more_general_nonduplicate_parent_available": False,
                    "principally_supports_or_attacks_specific_argument": False,
                    "principally_example_or_specialization": False,
                },
            })
        else:
            entry.update({
                "declared_function": edges[occurrence["edge_id"]]["relation"],
                "semantic_target": occurrence["parent_occurrence_id"],
                "subordinate_review": {
                    "parent_is_best_immediate_target": True,
                    "relation_to_parent_explicit": True,
                },
            })
        entries.append(entry)
    (translated / "reviews/graph_placement_review.json").write_text(json.dumps({
        "normative_revision": "1.2.27",
        "debate_id": "debat_test",
        "status": "approved",
        "entries": entries,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    meta_path = workspace / "workspace.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["translated_copy"]["tree_sha256"] = common.full_tree_sha256(translated)
    meta["workspace_sha256"] = None
    meta["workspace_sha256"] = sys.modules["wikidebia_editorial_workspace"].workspace_receipt_hash(meta)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return project, workspace, work_id, sealed["review_sha256"]


def test_render_creates_distinct_bilingual_pages_and_direct_interlanguage_links(tmp_path: Path):
    project, workspace, work_id, review_sha = make_translated(tmp_path)
    translated_before = common.full_tree_sha256(workspace / "translated-copy")
    result = render.render_workspace(project, "debat_test", work_id, review_sha)
    target = workspace / "rendered-copy"
    assert result["status"] == "bilingual_rendered"
    assert result["pages"] == 10
    assert result["french_interlanguage_links"] == 5
    assert result["english_interlanguage_links"] == 0
    assert common.full_tree_sha256(workspace / "translated-copy") == translated_before
    registry = json.loads((target / "data/registre_debat.json").read_text(encoding="utf-8"))
    fr_debate = (target / "output/fr/debate/debate.wiki").read_text(encoding="utf-8")
    en_title = registry["debate"]["pages"]["en"]["canonical_title"]
    assert f"{{{{Lien interlangue\n|langue=en\n|page={en_title}\n}}}}" in fr_debate
    for node in registry["graph"]["nodes"]:
        if node["status"] != "active":
            continue
        fr = (target / f"output/fr/arguments/{node['id']}.wiki").read_text(encoding="utf-8")
        assert f"{{{{Lien interlangue\n|langue=en\n|page={node['en']['canonical_title']}\n}}}}" in fr
    for path in (target / "output/en").rglob("*.wiki"):
        assert "Lien interlangue" not in path.read_text(encoding="utf-8")
        assert "|interlangue=" not in path.read_text(encoding="utf-8")


def test_render_links_to_reused_english_argument_without_generating_it(tmp_path: Path):
    project, workspace, work_id, review_sha = make_translated(
        tmp_path, reuse_existing_argument=True
    )
    result = render.render_workspace(project, "debat_test", work_id, review_sha)
    target = workspace / "rendered-copy"
    registry = common.load_json(target / "data/registre_debat.json", "registre")
    reused = next(node for node in registry["graph"]["nodes"] if node["id"] == "A0004")

    assert result["pages"] == 9
    assert not (target / "output/en/arguments/A0004.wiki").exists()
    fr = (target / "output/fr/arguments/A0004.wiki").read_text(encoding="utf-8")
    assert "|page=Existing English argument" in fr
    assert reused["pages"]["en"]["wiki"]["decision"] == "reuse_existing"
    assert reused["pages"]["en"]["generation"]["status"] == "obsolete"
    en_pages = {
        page["page_id"]
        for page in common.load_json(target / "manifest.json", "manifest")["pages"]
        if page["language"] == "en"
    }
    assert "A0004" not in en_pages


def test_render_emits_translated_citations_without_mutating_source_metadata(tmp_path: Path):
    project, workspace, work_id, review_sha = make_translated(tmp_path)
    render.render_workspace(project, "debat_test", work_id, review_sha)
    target = workspace / "rendered-copy"
    fr = (target / "output/fr/arguments/A0001.wiki").read_text(encoding="utf-8")
    en = (target / "output/en/arguments/A0001.wiki").read_text(encoding="utf-8")
    assert "|citation=La liberté consiste à vouloir ce que l'on veut." in fr
    assert "|date=25 juin 2012" in fr
    assert "|quote=Freedom consists in wanting what one wants." in en
    assert "|date=25 June 2012" in en
    assert "|authors=Harry G. Frankfurt" in en
    assert "|article=Freedom of the Will and the Concept of a Person" in en
    assert "|work=The Importance of What We Care About" in en
    assert "|warnings=Texte abrégé, AI-translated quote" in en
    for forbidden in ("|citation=", "|auteurs=", "|ouvrage=", "|numéro=", "|localisation=", "|édition=", "|lieu=", "|lien=", "|avertissements-citation="):
        assert forbidden not in en
    assert "|quotes={{Quote" in en
    assert "|quotes={{Citation" not in en
    assert "|citations={{Citation" in fr


def test_legacy_french_quote_warning_alias_is_normalized_losslessly():
    source = (
        "{{Argument\n"
        "|citations={{Citation\n"
        "|citation=Texte historique.\n"
        "|avertissements=Citation trop courte\n"
        "}}\n"
        "|date-création=2022-02-25\n"
        "}}\n"
    )
    expected = source.replace(
        "|avertissements=Citation trop courte",
        "|avertissements-citation=Citation trop courte",
    )
    assert render._normalize_legacy_french_quote_warnings(source) == expected


def test_canonical_french_quote_warning_is_unchanged():
    source = "{{Argument|citations={{Citation|citation=Texte|avertissements-citation=Texte abrégé}}}}\n"
    assert render._normalize_legacy_french_quote_warnings(source) == source


def test_render_requires_exact_translation_hash(tmp_path: Path):
    project, workspace, work_id, _ = make_translated(tmp_path)
    try:
        render.render_workspace(project, "debat_test", work_id, "0" * 64)
    except render.RenderError as exc:
        assert "empreinte confirmée" in str(exc)
    else:
        raise AssertionError("Une empreinte de traduction erronée a été acceptée")
    assert not (workspace / "rendered-copy").exists()


def test_render_is_idempotent_and_locks_graph(tmp_path: Path):
    project, workspace, work_id, review_sha = make_translated(tmp_path)
    first = render.render_workspace(project, "debat_test", work_id, review_sha)
    second = render.render_workspace(project, "debat_test", work_id, review_sha)
    assert second["idempotent"] is True
    assert second["rendered_copy_tree_sha256"] == first["rendered_copy_tree_sha256"]
    target = workspace / "rendered-copy"
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    registry = json.loads((target / "data/registre_debat.json").read_text(encoding="utf-8"))
    assert manifest["global_status"] == "bilingual_validated"
    assert manifest["editorial_controls"]["historical_text_render_validation_mode"] == "differential_preservation_v1"
    assert registry["graph"]["lifecycle"]["status"] == "locked"
    assert all(page["status"] == "validated" for page in manifest["pages"])
    assert not any(path.name.endswith(".wiki") for path in (workspace / "translated-copy").rglob("*.wiki") if "imports" not in path.parts)


def test_render_lifecycle_fields_depend_on_page_origin():
    registry={
        'debate': {'pages': {'en': {'canonical_title':'Topic'}}},
        'graph': {'occurrences': [], 'nodes': [], 'edges': []},
    }
    metadata={'debate': {'rubriques':['Société'], 'keywords':['sujet']}}
    existing={
        'debate': {
            'subject':'Sujet','complete_topic':'la question du sujet','introduction':'Texte.',
            'wikipedia_articles':[],'documentation':{},
            'page_origin':'preexisting',
            'preserved_parameters':{
                'avancement':{'present':True,'value':'Débat en construction'},
                'avertissements-débat':{'present':False,'value':None},
                'débats-connexes':{'present':True,'value':'{{Débat connexe|page=Autre débat}}'},
            },
        }
    }
    text=render._render_debate(lang='fr',registry=registry,metadata_lock=metadata,content_lock=existing,sources={},creation_date='2026-08-05')
    assert '|avancement=Débat en construction' in text
    assert '|avertissements-débat=' not in text
    assert '|débats-connexes={{Débat connexe|page=Autre débat}}' in text
    new={'debate': {**existing['debate'],'page_origin':'new','preserved_parameters':{}}}
    text=render._render_debate(lang='fr',registry=registry,metadata_lock=metadata,content_lock=new,sources={},creation_date='2026-08-05')
    assert '|avancement=Débat construit' in text
    assert '|avertissements-débat=Débat généré par IA' in text
    assert '|débats-connexes=' not in text


def test_render_existing_argument_preserves_absent_ai_warning():
    node={'id':'A0001','fr':{'rubriques':['Société'],'keywords':['sujet']},'en':{'canonical_title':'Argument topic'}}
    registry={'graph':{'edges':[],'occurrences':[],'nodes':[node]}}
    content={
        'summary':'Le raisonnement est développé sans modifier les paramètres historiques.',
        'citations':[],'sources':{},'page_origin':'preexisting',
        'preserved_parameters':{'avertissements-argument':{'present':False,'value':None}},
    }
    text=render._render_argument(lang='fr',node=node,content=content,registry=registry,sources={},creation_date='2026-08-05')
    assert '|avertissements-argument=' not in text


def test_render_preserves_detailed_debate_and_omits_local_relations():
    child={'id':'A0002','fr':{'canonical_title':'Argument enfant','displayed_title':'Argument enfant','rubriques':['Société'],'keywords':['sujet']}}
    node={'id':'A0001','fr':{'rubriques':['Société'],'keywords':['sujet']},'en':{'canonical_title':'Argument topic'}}
    registry={'graph':{'edges':[{'id':'E00001','parent_node_id':'A0001','child_node_id':'A0002','relation':'justification','order':1,'status':'active'}],'occurrences':[],'nodes':[node,child]}}
    content={
        'summary':'Le raisonnement renvoie vers un débat autonome qui porte le développement détaillé.',
        'citations':[],'sources':{},'page_origin':'preexisting',
        'preserved_parameters':{
            'avertissements-argument':{'present':False,'value':None},
            'débat-dédié':{'present':True,'value':'Débat sous-jacent'},
        },
    }
    text=render._render_argument(lang='fr',node=node,content=content,registry=registry,sources={},creation_date='2026-08-05')
    assert '|débat-dédié=Débat sous-jacent' in text
    assert '|justifications=' not in text
    assert '|objections=' not in text


def test_render_translates_dedicated_debate_and_omits_english_local_relations():
    child = {'id': 'A0002', 'en': {'canonical_title': 'Child argument', 'displayed_title': 'Child argument'}}
    node = {
        'id': 'A0001',
        'fr': {'rubriques': ['Société'], 'keywords': ['sujet']},
        'en': {'canonical_title': 'Argument topic', 'sections': ['Society'], 'keywords': ['topic']},
    }
    registry = {'graph': {'edges': [{'id': 'E00001', 'parent_node_id': 'A0001', 'child_node_id': 'A0002', 'relation': 'justification', 'order': 1, 'status': 'active'}], 'occurrences': [], 'nodes': [node, child]}}
    content = {
        'summary': 'The argument points to a dedicated debate for its full development.',
        'citations': [], 'citation_passages': [], 'sources': {}, 'page_origin': 'new',
        'preserved_parameters': {},
        'dedicated_debate': 'Does the left bear responsibility for the rise of the far right?',
    }
    source_content = {
        'page_origin': 'preexisting',
        'preserved_parameters': {
            'débat-dédié': {'present': True, 'value': "La gauche a-t-elle une responsabilité dans la montée de l'extrême droite ?"},
        },
    }

    text = render._render_argument(
        lang='en', node=node, content=content, registry=registry, sources={},
        creation_date='2026-08-05', source_content=source_content,
    )

    assert '|dedicated-debate=Does the left bear responsibility for the rise of the far right?' in text
    assert '|justifications=' not in text
    assert '|objections=' not in text


def test_render_reads_reviewed_dedicated_debate_record_and_ignores_absent_source():
    node = {
        'id': 'A0001',
        'fr': {'rubriques': ['Société'], 'keywords': ['sujet']},
        'en': {'canonical_title': 'Argument topic', 'sections': ['Society'], 'keywords': ['topic']},
    }
    registry = {'graph': {'edges': [], 'occurrences': [], 'nodes': [node]}}
    content = {
        'summary': None, 'citations': [], 'citation_passages': [], 'sources': {},
        'page_origin': 'new', 'preserved_parameters': {},
        'dedicated_debate': {
            'dedicated_debate': None,
            'dedicated_debate_equivalence_reviewed': False,
            'dedicated_debate_review_note': '',
        },
    }
    source_content = {
        'page_origin': 'preexisting',
        'preserved_parameters': {'débat-dédié': {'present': False, 'value': None}},
    }
    text = render._render_argument(
        lang='en', node=node, content=content, registry=registry, sources={},
        creation_date='2026-08-05', source_content=source_content,
    )
    assert '|dedicated-debate=' not in text

    source_content['preserved_parameters']['débat-dédié'] = {
        'present': True,
        'value': 'Débat sous-jacent',
    }
    content['dedicated_debate'] = {
        'dedicated_debate': 'Underlying debate',
        'dedicated_debate_equivalence_reviewed': True,
        'dedicated_debate_review_note': 'The same underlying debate is translated.',
    }
    text = render._render_argument(
        lang='en', node=node, content=content, registry=registry, sources={},
        creation_date='2026-08-05', source_content=source_content,
    )
    assert '|dedicated-debate=Underlying debate' in text


def test_render_preserves_historical_argument_name():
    node={'id':'A0001','fr':{'rubriques':['Philosophie'],'keywords':['Dieu']},'en':{'canonical_title':'Argument topic'}}
    registry={'graph':{'edges':[],'occurrences':[],'nodes':[node]}}
    content={
        'summary':'Résumé historique conservé.', 'citations':[], 'sources':{}, 'page_origin':'preexisting',
        'preserved_parameters':{
            'nom':{'present':True,'value':'Argument cosmologique'},
            'avertissements-argument':{'present':False,'value':None},
        },
    }
    text=render._render_argument(lang='fr',node=node,content=content,registry=registry,sources={},creation_date='2026-08-05')
    assert '|nom=Argument cosmologique' in text
    assert text.index('|nom=') < text.index('|résumé=')


def test_render_new_argument_uses_nom_consacre_not_legacy_nom():
    node={'id':'A9001','fr':{'rubriques':['Philosophie'],'keywords':['Dieu']},'en':{'canonical_title':'Argument topic'}}
    registry={'graph':{'edges':[],'occurrences':[],'nodes':[node]}}
    content={
        'summary':'Résumé nouveau.', 'citations':[], 'sources':{}, 'page_origin':'new',
        'preserved_parameters':{}, 'argument_name':'Argument cosmologique',
    }
    text=render._render_argument(lang='fr',node=node,content=content,registry=registry,sources={},creation_date='2026-08-10')
    assert '|nom-consacré=Argument cosmologique' in text
    assert '|nom=Argument cosmologique' not in text
    assert text.index('|nom-consacré=') < text.index('|résumé=')


def test_render_new_english_argument_uses_established_name_not_legacy_name():
    node={'id':'A9002','fr':{'rubriques':['Philosophie'],'keywords':['Dieu']},'en':{'canonical_title':'Argument topic','sections':['Philosophy'],'keywords':['God']}}
    registry={'graph':{'edges':[],'occurrences':[],'nodes':[node]}}
    content={
        'summary':'New summary.', 'quotes':[], 'sources':{}, 'page_origin':'new',
        'preserved_parameters':{}, 'argument_name':'Cosmological argument',
    }
    text=render._render_argument(lang='en',node=node,content=content,registry=registry,sources={},creation_date='2026-08-10')
    assert '|established-name=Cosmological argument' in text
    assert '|name=Cosmological argument' not in text
    assert text.index('|established-name=') < text.index('|summary=')


def test_render_translated_english_debate_uses_french_metadata_presence_and_values():
    registry={
        'debate': {'pages': {'en': {'canonical_title':'Should electronic voting be generalized?'}}},
        'graph': {'occurrences': [], 'nodes': [], 'edges': []},
    }
    metadata={'debate': {'sections':['Politics'], 'keywords':['electronic voting']}}
    english={'debate': {
        'topic':'Electronic voting','complete_topic':'the generalization of electronic voting',
        'introduction':'Text.','wikipedia_articles':[],'documentation':{},
        'page_origin':'new','source_page_origin':'preexisting','preserved_parameters':{},
    }}
    french_absent={
        'subject':'Vote électronique','complete_topic':'la généralisation du vote électronique',
        'page_origin':'preexisting','preserved_parameters':{
            'avancement':{'present':False,'value':None},
            'avertissements-titre':{'present':False,'value':None},
            'avertissements-débat':{'present':False,'value':None},
        },
    }
    text=render._render_debate(
        lang='en',registry=registry,metadata_lock=metadata,content_lock=english,sources={},
        creation_date='2026-08-19',source_content=french_absent,
    )
    assert '|progress=' not in text
    assert '|title-warnings=' not in text
    assert '|debate-warnings=' not in text

    french_present={
        **french_absent,
        'preserved_parameters':{
            'avancement':{'present':True,'value':'Débat en construction'},
            'avertissements-titre':{'present':True,'value':'Titre à expliciter'},
            'avertissements-débat':{'present':True,'value':'Débat sensible'},
        },
    }
    text=render._render_debate(
        lang='en',registry=registry,metadata_lock=metadata,content_lock=english,sources={},
        creation_date='2026-08-19',source_content=french_present,
    )
    assert '|progress=Debate under construction' in text
    assert '|title-warnings=Title to be explained' in text
    assert '|debate-warnings=Sensitive debate' in text


def test_render_translated_english_argument_uses_french_warning_presence_and_values():
    node={
        'id':'A0001',
        'fr':{'rubriques':['Politique'],'keywords':['vote électronique']},
        'en':{'canonical_title':'Electronic voting can improve access','sections':['Politics'],'keywords':['electronic voting']},
    }
    registry={'graph':{'edges':[],'occurrences':[],'nodes':[node]}}
    english={
        'summary':'English historical summary.','citations':[],'sources':{},
        'page_origin':'new','source_page_origin':'preexisting','preserved_parameters':{},
    }
    french_absent={
        'summary':'Résumé historique français.','citations':[],'sources':{},'page_origin':'preexisting',
        'preserved_parameters':{
            'avertissements-titre':{'present':False,'value':None},
            'avertissements-argument':{'present':False,'value':None},
            'avertissements-résumé':{'present':False,'value':None},
        },
    }
    text=render._render_argument(
        lang='en',node=node,content=english,registry=registry,sources={},creation_date='2026-08-19',
        source_content=french_absent,
    )
    assert '|title-warnings=' not in text
    assert '|argument-warnings=' not in text
    assert '|summary-warnings=' not in text

    french_present={
        **french_absent,
        'preserved_parameters':{
            'avertissements-titre':{'present':True,'value':'Titre peu clair'},
            'avertissements-argument':{'present':True,'value':'Argument sensible'},
            'avertissements-résumé':{'present':True,'value':'Résumé peu clair'},
        },
    }
    text=render._render_argument(
        lang='en',node=node,content=english,registry=registry,sources={},creation_date='2026-08-19',
        source_content=french_present,
    )
    assert '|title-warnings=Unclear title' in text
    assert '|argument-warnings=Sensitive argument' in text
    assert '|summary-warnings=Unclear summary' in text


def test_render_translated_english_metadata_uses_effective_defaults_for_new_french_source():
    registry={
        'debate': {'pages': {'en': {'canonical_title':'New debate'}}},
        'graph': {'occurrences': [], 'nodes': [], 'edges': []},
    }
    metadata={'debate': {'sections':['Politics'], 'keywords':['test']}}
    english={'debate': {
        'topic':'Test','complete_topic':'the test', 'introduction':'Text.','wikipedia_articles':[],
        'documentation':{},'page_origin':'new','source_page_origin':'new','preserved_parameters':{},
    }}
    french={'page_origin':'new','preserved_parameters':{}}
    text=render._render_debate(
        lang='en',registry=registry,metadata_lock=metadata,content_lock=english,sources={},
        creation_date='2026-08-19',source_content=french,
    )
    assert '|progress=Constructed debate' in text
    assert '|debate-warnings=Debate generated by AI' in text


def test_render_localizes_machine_documentary_dates_inside_english_ref_without_touching_url():
    intro = (
        "{{Subsection|title=History|content=Claim"
        "<ref>Institution, Report, 2024-07-09, https://example.org/archive/2024-07-09/report</ref>.}}"
    )
    normalized = render._normalize_inline_documentary_dates(intro, "en")
    assert "9 July 2024" in normalized
    assert "https://example.org/archive/2024-07-09/report" in normalized
    assert "Report, 2024-07-09," not in normalized


def test_render_rebuilds_historical_summary_review_from_content_locks(tmp_path: Path):
    reviews = tmp_path / "reviews"
    data = tmp_path / "data"
    reviews.mkdir(); data.mkdir()
    # Reproduce a stale pre-provenance ledger that would otherwise trigger
    # WDV-EDT-013/020 by applying creation-style requirements retroactively.
    (reviews / "summary_style_review.json").write_text(json.dumps({
        "entries": [{"id": "A0001", "languages": {
            "fr": {"status": "approved", "note": "Ancienne attestation devenue obsolète."},
            "en": {"status": "approved", "note": "Stale translated attestation."},
        }}]
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (data / "fr_content_lock.json").write_text(json.dumps({
        "arguments": [{
            "id": "A0001", "page_origin": "preexisting", "status": "historical_existing",
            "summary_provenance": "historical_existing", "summary": "Résumé historique.",
            "note": "Résumé historique conservé exactement.",
        }]
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (data / "en_content_lock.json").write_text(json.dumps({
        "arguments": [{
            "id": "A0001", "page_origin": "new", "source_page_origin": "preexisting",
            "summary_provenance": "historical_existing", "summary": "Historical summary.",
            "summary_ratio_reviewed": True, "summary_length_ratio": 1.0,
            "summary_ratio_exception_rationale": "Ratio reviewed against the protected historical source.",
            "note": "English faithfully translates the protected historical source.",
        }]
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    render._finalize_summary_review(tmp_path, "debat_test")
    final = json.loads((reviews / "summary_style_review.json").read_text(encoding="utf-8"))
    row = final["entries"][0]["languages"]
    assert row["fr"]["status"] == "historical_existing"
    assert row["fr"]["historical_content_preserved"] is True
    assert row["en"]["status"] == "translated_historical_source"
    assert row["en"]["historical_source_preserved"] is True
    assert "forceful_expression" not in row["fr"]
    assert "forceful_expression" not in row["en"]


def test_finalize_individual_review_propagates_reviewed_historical_form_change(tmp_path: Path):
    registry = {"graph": {"nodes": [{
        "id": "A0001", "status": "active",
        "fr": {"canonical_title": "Faire compliqué quand on peut faire simple", "displayed_title": "Faire compliqué quand on peut faire simple", "rubriques": ["Société"], "keywords": ["simplicité"]},
        "en": {"canonical_title": "Making things complicated can be needless", "displayed_title": "Making things complicated when they could be simple", "sections": ["Society"], "keywords": ["simplicity"]},
    }]}}
    fr_meta = {"arguments": [{
        "entity_id": "A0001", "canonical_title": "Faire compliqué quand on peut faire simple",
        "displayed_title": "Faire compliqué quand on peut faire simple", "rubriques": ["Société"], "keywords": ["simplicité"],
        "decisions": {"displayed_title": "keep", "rubriques": "keep"},
        "rationales": {"displayed_title": "Titre historique conservé après revue.", "rubriques": {"Société": "Le raisonnement porte directement sur une pratique sociale."}, "keyword_order": "Pertinence décroissante vérifiée."},
    }]}
    en_meta = {"arguments": [{
        "id": "A0001", "canonical_title": "Making things complicated can be needless",
        "displayed_title": "Making things complicated when they could be simple", "sections": ["Society"], "keywords": ["simplicity"],
        "source_page_origin": "preexisting",
        "canonical_title_semantic_inventory_reviewed": True,
        "canonical_title_semantic_inventory_note": "Canonical title semantics reviewed against the locked French source.",
        "canonical_title_equivalent_to_french": True,
        "canonical_title_subject_preserved": True, "canonical_title_predicate_preserved": True,
        "canonical_title_scope_preserved": True, "canonical_title_modality_preserved": True,
        "displayed_title_source_form": "nominal_phrase", "displayed_title_target_form": "proposition",
        "displayed_title_source_form_reviewed": True, "displayed_title_no_formal_regression": True,
        "displayed_title_semantic_inventory_reviewed": True,
        "displayed_title_semantic_inventory_note": "The idiomatic form change preserves the same assertion and argumentative force.",
        "displayed_title_subject_preserved": True, "displayed_title_predicate_preserved": True,
        "displayed_title_scope_preserved": True, "displayed_title_modality_preserved": True,
        "displayed_title_form_change_reviewed": True, "displayed_title_speech_act_preserved": True,
        "displayed_title_form_change_note": "The idiomatic English rendering changes surface form while preserving the same assertion and argumentative force.",
    }]}
    (tmp_path / "reviews").mkdir()
    render._finalize_individual_review(tmp_path, registry, fr_meta, en_meta)
    review = json.loads((tmp_path / "reviews/individual_review.json").read_text(encoding="utf-8"))
    row = review["entries"][0]
    assert row["displayed_title_form_change_reviewed_en"] is True
    assert row["displayed_title_speech_act_preserved_en"] is True
    assert "idiomatic English rendering" in row["displayed_title_form_change_note_en"]


def test_finalize_keyword_vocabulary_reconciles_historical_atomicity_metadata(tmp_path: Path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "fr_content_lock.json").write_text(json.dumps({
        "arguments": [
            {"id": "A0073", "page_origin": "preexisting"},
            {"id": "A0106", "page_origin": "preexisting"},
        ]
    }, ensure_ascii=False), encoding="utf-8")
    (data / "en_content_lock.json").write_text(json.dumps({
        "arguments": [
            {"id": "A0073", "source_page_origin": "preexisting"},
            {"id": "A0106", "source_page_origin": "preexisting"},
        ]
    }, ensure_ascii=False), encoding="utf-8")
    vocab = {
        "entries": [
            {
                "concept_id": "K1",
                "fr": "partage du travail",
                "en": "work sharing",
                "atomic_concept": True,
                "compositional_intersection": False,
                "multiword_exception": False,
                "multiword_exception_rationale": "",
                "en_atomic_concept": True,
                "en_compositional_intersection": False,
                "en_multiword_exception": False,
                "en_multiword_exception_rationale": "",
                "usages": [{"entity_type": "argument", "entity_id": "A0073"}],
            },
            {
                "concept_id": "K2",
                "fr": "réduction du temps de travail",
                "en": "working-time reduction",
                "atomic_concept": True,
                "compositional_intersection": False,
                "multiword_exception": False,
                "multiword_exception_rationale": "",
                "en_atomic_concept": True,
                "en_compositional_intersection": False,
                "en_multiword_exception": True,
                "en_multiword_exception_rationale": "Old mechanically copied exception.",
                "usages": [
                    {"entity_type": "argument", "entity_id": "A0073"},
                    {"entity_type": "argument", "entity_id": "A0106"},
                ],
            },
        ]
    }
    (data / "keyword_vocabulary_bilingual.json").write_text(json.dumps(vocab, ensure_ascii=False), encoding="utf-8")

    render._finalize_keyword_vocabulary(tmp_path)
    final = json.loads((data / "keyword_vocabulary_bilingual.json").read_text(encoding="utf-8"))
    by_fr = {row["fr"]: row for row in final["entries"]}
    assert by_fr["partage du travail"]["multiword_exception"] is True
    assert "Locution conceptuelle historique" in by_fr["partage du travail"]["multiword_exception_rationale"]
    assert by_fr["réduction du temps de travail"]["multiword_exception"] is True
    assert by_fr["réduction du temps de travail"]["en_multiword_exception"] is False
    assert by_fr["réduction du temps de travail"]["en_multiword_exception_rationale"] == ""


def test_finalize_keyword_vocabulary_does_not_repair_new_unreviewed_concept(tmp_path: Path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "fr_content_lock.json").write_text(json.dumps({
        "arguments": [{"id": "A0001", "page_origin": "new"}]
    }), encoding="utf-8")
    (data / "en_content_lock.json").write_text(json.dumps({
        "arguments": [{"id": "A0001", "source_page_origin": "new"}]
    }), encoding="utf-8")
    vocab = {"entries": [{
        "fr": "réduction du temps de travail",
        "en": "working-time reduction",
        "atomic_concept": True,
        "compositional_intersection": False,
        "multiword_exception": False,
        "en_atomic_concept": True,
        "en_compositional_intersection": False,
        "en_multiword_exception": True,
        "en_multiword_exception_rationale": "Incorrect exception on a new concept.",
        "usages": [{"entity_type": "argument", "entity_id": "A0001"}],
    }]}
    path = data / "keyword_vocabulary_bilingual.json"
    path.write_text(json.dumps(vocab, ensure_ascii=False), encoding="utf-8")
    before = path.read_text(encoding="utf-8")
    render._finalize_keyword_vocabulary(tmp_path)
    assert path.read_text(encoding="utf-8") == before


def test_finalize_introduction_review_adds_historical_provenance_and_clear_sentence_exception(tmp_path: Path):
    (tmp_path / "data").mkdir()
    (tmp_path / "reviews").mkdir()
    (tmp_path / "output/en/debate").mkdir(parents=True)

    fr_intro = "{{Sous-partie|titre=Historique|contenu=Texte}}"
    (tmp_path / "data/fr_content_lock.json").write_text(json.dumps({
        "debate": {"page_origin": "preexisting", "introduction": fr_intro}
    }, ensure_ascii=False), encoding="utf-8")
    review = {
        "entries": [
            {
                "language": "fr",
                "subsections": [{"title": "Ancienne proposition"}],
            },
            {
                "language": "en",
                "source_page_origin": "preexisting",
                "reference_note_punctuation_reviewed": True,
            },
        ]
    }
    (tmp_path / "reviews/introduction_review.json").write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")
    body = (
        "Depending on the groups concerned, basic income is also called several other names. "
        "These expressions are not identical, but they share enough characteristics to describe the same policy family."
    )
    (tmp_path / "output/en/debate/debate.wiki").write_text(
        "{{Debate|introduction={{Subsection|title=Definition|content=Text<ref>" + body + "</ref>.}}}}",
        encoding="utf-8",
    )

    render._finalize_introduction_review(tmp_path)
    final = json.loads((tmp_path / "reviews/introduction_review.json").read_text(encoding="utf-8"))
    fr = next(row for row in final["entries"] if row["language"] == "fr")
    en = next(row for row in final["entries"] if row["language"] == "en")
    assert fr["status"] == "historical_existing"
    assert fr["historical_content_preserved"] is True
    assert len(fr["historical_source_sha256"]) == 64
    assert len(en["terminal_period_sentence_exceptions"]) == 1
    exc = en["terminal_period_sentence_exceptions"][0]
    assert exc["complete_sentence"] is True
    assert exc["sentence_evidence"] in body


def test_finalize_introduction_review_does_not_invent_exception_for_bibliographic_notice(tmp_path: Path):
    (tmp_path / "data").mkdir()
    (tmp_path / "reviews").mkdir()
    (tmp_path / "output/en/debate").mkdir(parents=True)
    (tmp_path / "data/fr_content_lock.json").write_text(json.dumps({
        "debate": {"page_origin": "preexisting", "introduction": "{{Sous-partie|titre=Historique|contenu=Texte}}"}
    }), encoding="utf-8")
    (tmp_path / "reviews/introduction_review.json").write_text(json.dumps({
        "entries": [
            {"language": "fr"},
            {"language": "en", "source_page_origin": "preexisting", "reference_note_punctuation_reviewed": True},
        ]
    }), encoding="utf-8")
    (tmp_path / "output/en/debate/debate.wiki").write_text(
        "{{Debate|introduction={{Subsection|title=Definition|content=Text<ref>Author, Title, Publisher, 2020.</ref>.}}}}",
        encoding="utf-8",
    )
    render._finalize_introduction_review(tmp_path)
    final = json.loads((tmp_path / "reviews/introduction_review.json").read_text(encoding="utf-8"))
    en = next(row for row in final["entries"] if row["language"] == "en")
    assert en.get("terminal_period_sentence_exceptions") == []


def test_relation_renderer_prefers_occurrence_level_displayed_title():
    registry = {
        "graph": {
            "nodes": [{
                "id": "A0002", "status": "active",
                "fr": {"canonical_title": "Titre cible", "displayed_title": "Titre global"},
                "en": {"canonical_title": "Target title", "displayed_title": "Global title"},
            }],
            "edges": [{
                "id": "E00001", "status": "active", "parent_node_id": "A0001",
                "child_node_id": "A0002", "relation": "objection", "order": 1,
            }],
        }
    }
    rendered = render._relations(
        registry, "A0001", "objection", "fr",
        [{"id": "edge:E00001", "source_text": "Libellé historique contextuel"}],
    )
    assert "titre-affiché=Libellé historique contextuel" in rendered
    assert "titre-affiché=Titre global" not in rendered

def test_published_content_checkpoint_requires_matching_receipts_and_review(tmp_path: Path):
    import hashlib
    import pytest
    from wikidebia_render import _published_content_checkpoint, _add_french_interlanguage, RenderError
    from wikidebia_corpus_build import full_tree_sha256
    root=tmp_path;state=root/'.state/fr-publication/test-debate/EDIT-001/content';checkpoint=state/'checkpoint-corpus'
    page=checkpoint/'output/fr/debate/debate.wiki';page.parent.mkdir(parents=True)
    original='{{Débat\n|introduction=Texte historique.\n|débats-connexes={{Débat connexe|page=Source}}\n|date-création=2020-01-01\n}}\n'
    page.write_text(original)
    def signed(value):
        value['receipt_sha256']=hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest();return value
    identity=dict(debate_id='test-debate',work_id='EDIT-001',stage='content',checkpoint_tree_sha256=full_tree_sha256(checkpoint))
    (state/'checkpoint.json').write_text(json.dumps(signed(dict(identity,source_content_review_sha256='review-fr'))))
    (state/'publication-receipt.json').write_text(json.dumps(signed(dict(identity,status='published'))))
    assert _published_content_checkpoint(root,'test-debate','EDIT-001',{'review_sha256':'review-fr'})==checkpoint/'output/fr'
    rendered=_add_french_interlanguage(original,'English debate')
    assert '|débats-connexes={{Débat connexe|page=Source}}' in rendered
    assert '|interlangue={{Lien interlangue\n|langue=en\n|page=English debate\n}}' in rendered
    with pytest.raises(RenderError):_published_content_checkpoint(root,'test-debate','EDIT-001',{'review_sha256':'wrong-review'})
    page.write_text(original.replace('historique','changé'))
    with pytest.raises(RenderError):_published_content_checkpoint(root,'test-debate','EDIT-001',{'review_sha256':'review-fr'})

def test_existing_english_creation_date_is_consistent_in_page_manifest_and_registry(tmp_path: Path):
    project,workspace,work_id,review_sha=make_translated(tmp_path)
    source=workspace/'translated-copy';path=source/'data/en_content_lock.json';content=json.loads(path.read_text());arg=content['arguments'][0];pid=arg['id']
    arg['page_origin']='preexisting';arg['preserved_parameters']={key:{'present':False,'value':None} for key in translation.EN_PAGE_LIFECYCLE_PARAMETERS['argument']}
    arg['preserved_parameters']['creation-date']={'present':True,'value':'2022-08-14'};path.write_text(json.dumps(content))
    target=workspace/'test-render-existing'
    render._build_rendered_copy(project,source,target,debate_id='debat_test',work_id=work_id,translation_review_sha256=review_sha)
    manifest=json.loads((target/'manifest.json').read_text());page=next(x for x in manifest['pages'] if x['language']=='en' and x['page_id']==pid)
    assert page['creation_date']=='2022-08-14'
    assert '|creation-date=2022-08-14' in (target/page['file_path']).read_text()
    registry=json.loads((target/'data/registre_debat.json').read_text());node=next(n for n in registry['graph']['nodes'] if n['id']==pid)
    assert node['pages']['en']['generation']['creation_date']=='2022-08-14'
