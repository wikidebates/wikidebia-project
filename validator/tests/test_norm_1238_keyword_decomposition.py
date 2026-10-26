from pathlib import Path
import json

from wikidebia_validator.editorial import keyword_atomicity_issues, lowercase_god_issues
from wikidebia_validator.validator import validate_package
from .helpers import create_fr_package, dump


def test_religious_psychology_is_compositional_but_authority_argument_is_atomic():
    bad = keyword_atomicity_issues(
        "psychologie religieuse",
        {"atomic_concept": True, "compositional_intersection": False, "multiword_exception": False},
        "fr", require_composition_attestation=True,
    )
    assert "compositional_intersection" in bad
    assert keyword_atomicity_issues(
        "argument d'autorité",
        {
            "atomic_concept": True, "compositional_intersection": False, "multiword_exception": True,
            "multiword_exception_rationale": "Locution stabilisée désignant un type d'argument irréductible à ses mots séparés.",
        },
        "fr", require_composition_attestation=True,
    ) == []


def test_english_domain_intersection_is_rejected():
    issues = keyword_atomicity_issues(
        "religious psychology",
        {"atomic_concept": True, "compositional_intersection": False, "multiword_exception": False},
        "en", require_composition_attestation=True,
    )
    assert "compositional_intersection" in issues


def test_lexicalized_history_keyword_accepts_explicit_atomic_exception():
    for keyword, language, rationale in (
        ("histoire du féminisme", "fr", "Cette locution désigne un concept lexicalisé unique et utile comme entrée de navigation."),
        ("history of feminism", "en", "English lexicalized navigation concept: this phrase names one atomic category rather than a compositional intersection."),
    ):
        assert keyword_atomicity_issues(
            keyword,
            {
                "atomic_concept": True,
                "compositional_intersection": False,
                "multiword_exception": True,
                "multiword_exception_rationale": rationale,
            },
            language,
            require_composition_attestation=True,
        ) == []


def test_lowercase_unique_god_is_rejected():
    assert lowercase_god_issues("Le dieu unique expliquerait le monde.") == ["lowercase_proper_name"]
    assert lowercase_god_issues("Un dieu local pourrait être imaginé.") == []


def _activate_1238_package(root: Path):
    create_fr_package(root)
    manifest=json.loads((root/'manifest.json').read_text())
    manifest['normative_versions']['consolidated_norm']='1.2.38'
    manifest['translation_status']={'en':'deferred'}
    manifest['editorial_controls']={
      'creation_date':'2026-07-23','creation_date_policy':'per_page_preserved','quality_policy_revision':'1.2.38',
      'individual_review_path':'reviews/individual_review.json','individual_review_report_path':'reports/individual.txt',
      'keyword_vocabulary_path':'data/keyword_vocabulary.json','summary_style_review_path':'reviews/summary_style_review.json',
      'required_reports':[],'debate_documentation':{'min_subsections':1,'min_references':0,'reject_singleton_bucket_pattern':True,'profile_rationale':'Profil de test complet.'},
      'introduction_references':{'required':True},'introduction_review_path':'reviews/introduction_review.json',
      'graph_placement_review_path':'reviews/graph_placement_review.json',
    }
    dump(root/'manifest.json',manifest)
    reg=json.loads((root/'data/registre_debat.json').read_text())
    for node in reg['graph']['nodes']:
        node['fr']['keywords']=['psychologie religieuse','religion']
    dump(root/'data/registre_debat.json',reg)
    vocab={'status':'draft','quality_policy_revision':'1.2.38','entries':[
      {'fr':'psychologie religieuse','en':None,'kind':'noun_phrase','scope':'site_navigation','cross_debate_reusable':True,'local_frequency_is_validity_criterion':False,'usage_count_in_debate':2,'atomic_concept':True,'compositional_intersection':False,'multiword_exception':False},
      {'fr':'religion','en':None,'kind':'noun','scope':'site_navigation','cross_debate_reusable':True,'local_frequency_is_validity_criterion':False,'usage_count_in_debate':2,'atomic_concept':True,'compositional_intersection':False,'multiword_exception':False},
    ]}
    dump(root/'data/keyword_vocabulary.json',vocab)
    # Minimal schema-valid review; other editorial findings are irrelevant to this integration assertion.
    entries=[]
    for node in reg['graph']['nodes']:
      entries.append({'id':node['id'],'languages':{'fr':{'status':'approved','originality_reviewed':True,'mechanism_statement':'La mesure agit par un mécanisme collectif expliqué dans le résumé de cette page.'}}})
    dump(root/'reviews/summary_style_review.json',{'schema_version':'1.0','normative_revision':'1.2.38','quality_policy_revision':'1.2.38','debate_id':'exemple','entries':entries})
    return root


def test_full_editorial_validation_emits_wdv_edt_025(tmp_path: Path):
    _activate_1238_package(tmp_path)
    report=validate_package(tmp_path,scopes=['editorial'])
    assert any(f.code=='WDV-EDT-025' and f.details.get('keyword')=='psychologie religieuse' for f in report.findings)


def test_schema_scope_checks_new_editorial_documents(tmp_path: Path):
    _activate_1238_package(tmp_path)
    vocab=json.loads((tmp_path/'data/keyword_vocabulary.json').read_text())
    vocab['entries'][0].pop('compositional_intersection')
    dump(tmp_path/'data/keyword_vocabulary.json',vocab)
    report=validate_package(tmp_path,scopes=['schema'])
    assert any(f.code=='WDV-SCH-003' and f.path=='data/keyword_vocabulary.json' for f in report.findings)


def test_legacy_norm_can_opt_into_quality_profile_without_global_migration(tmp_path: Path):
    _activate_1238_package(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    manifest["normative_versions"]["consolidated_norm"] = "1.2.30"
    dump(tmp_path / "manifest.json", manifest)
    review = json.loads((tmp_path / "reviews/summary_style_review.json").read_text())
    review["normative_revision"] = "1.2.30"
    dump(tmp_path / "reviews/summary_style_review.json", review)
    report = validate_package(tmp_path, scopes=["schema", "editorial"])
    assert any(f.code == "WDV-EDT-025" and f.details.get("keyword") == "psychologie religieuse" for f in report.findings)
    assert not any(f.code == "WDV-SCH-003" and f.path in {"data/keyword_vocabulary.json", "reviews/summary_style_review.json"} for f in report.findings)


def test_old_norm_and_missing_policy_revision_do_not_disable_current_keyword_rules(tmp_path: Path):
    _activate_1238_package(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    manifest["normative_versions"]["consolidated_norm"] = "1.2.30"
    manifest["editorial_controls"].pop("quality_policy_revision")
    dump(tmp_path / "manifest.json", manifest)
    review = json.loads((tmp_path / "reviews/summary_style_review.json").read_text())
    review["normative_revision"] = "1.2.30"
    review.pop("quality_policy_revision", None)
    dump(tmp_path / "reviews/summary_style_review.json", review)
    vocab = json.loads((tmp_path / "data/keyword_vocabulary.json").read_text())
    vocab.pop("quality_policy_revision", None)
    dump(tmp_path / "data/keyword_vocabulary.json", vocab)
    report = validate_package(tmp_path, scopes=["editorial"])
    assert any(f.code == "WDV-EDT-025" and f.details.get("keyword") == "psychologie religieuse" for f in report.findings)
