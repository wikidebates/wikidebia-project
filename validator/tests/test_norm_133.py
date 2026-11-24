from __future__ import annotations

import json
from pathlib import Path

from wikidebia_validator.package import PackageContext
from wikidebia_validator.report import Report
from wikidebia_validator.validator import validate_package
from wikidebia_validator.wikicode import PROTECTED_PAGE_PARAMETERS, parse_template, validate_template_shape
from .helpers import create_graph_package, dump


def context() -> PackageContext:
    return PackageContext(
        root=Path('.'),
        report=Report('0.4.39', '.', ['wikicode']),
        cache={'manifest.json': {'normative_versions': {'consolidated_norm': '1.2.33'}}},
    )


def debate(progress='Débat construit', warning='Débat généré par IA', related=None) -> str:
    rows = [
        '{{Débat',
        '|sujet=Sujet',
        '|sujet-développé=la question du sujet',
    ]
    if progress is not None:
        rows.append(f'|avancement={progress}')
    if warning is not None:
        rows.append(f'|avertissements-débat={warning}')
    rows.extend([
        '|introduction={{Sous-partie\n|titre=Définition\n|contenu=Texte.\n}}',
        '|articles-Wikipédia={{Article Wikipédia\n|page=Philosophie\n}}',
        '|arguments-pour={{Argument pour\n|page=Pour\n|titre-affiché=Pour\n}}',
        '|arguments-contre={{Argument contre\n|page=Contre\n|titre-affiché=Contre\n}}',
    ])
    if related is not None:
        rows.append(f'|débats-connexes={related}')
    rows.extend([
        '|rubriques=Société',
        '|mots-clés=sujet',
        '|interlangue={{Lien interlangue\n|langue=en\n|page=Topic\n}}',
        '|date-création=2026-08-05',
        '}}',
    ])
    return '\n'.join(rows)


def argument(warning='Argument généré par IA') -> str:
    rows=['{{Argument']
    if warning is not None:
        rows.append(f'|avertissements-argument={warning}')
    rows.extend([
        '|résumé=Un résumé complet développe le raisonnement propre à cet argument.',
        '|rubriques=Société',
        '|mots-clés=sujet',
        '|interlangue={{Lien interlangue\n|langue=en\n|page=Argument topic\n}}',
        '|date-création=2026-08-05',
        '}}',
    ])
    return '\n'.join(rows)



def preserved(text: str, page_type: str) -> dict:
    tmpl = parse_template(text)
    return {name: {"present": tmpl.one(name) is not None, "value": tmpl.one(name)} for name in PROTECTED_PAGE_PARAMETERS["fr", page_type]}

def test_new_debate_gets_creation_only_fields_and_no_related_debates():
    ctx=context()
    manifest={'page_origin':'new','creation_date':'2026-08-05','preserved_parameters':{}}
    validate_template_shape(ctx, parse_template(debate()), 'fr', 'debate', 'debate.wiki', manifest)
    assert not any(i.code == 'WDV-MWK-023' for i in ctx.report.findings)
    ctx=context()
    validate_template_shape(ctx, parse_template(debate(related='{{Débat connexe|page=Autre débat}}')), 'fr', 'debate', 'debate.wiki', manifest)
    assert any(i.code == 'WDV-MWK-003' and 'débats-connexes' in i.message for i in ctx.report.findings)


def test_preexisting_debate_preserves_exact_fields_or_absence():
    historical = debate('Débat en construction', None, '{{Débat connexe|page=Autre débat}}')
    existing={'page_origin':'preexisting','creation_date':'2026-08-05','preserved_parameters':preserved(historical, 'debate')}
    ctx=context()
    validate_template_shape(ctx, parse_template(debate('Débat en construction', None, '{{Débat connexe|page=Autre débat}}')), 'fr', 'debate', 'debate.wiki', existing)
    assert not any(i.code == 'WDV-MWK-023' for i in ctx.report.findings), ctx.report.to_text()
    ctx=context()
    validate_template_shape(ctx, parse_template(debate('Débat construit', 'Débat généré par IA', None)), 'fr', 'debate', 'debate.wiki', existing)
    assert any(i.code == 'WDV-MWK-023' for i in ctx.report.findings)


def test_preexisting_argument_does_not_gain_ai_warning():
    manifest={'page_origin':'preexisting','creation_date':'2026-08-05','preserved_parameters':preserved(argument(None), 'argument')}
    ctx=context()
    validate_template_shape(ctx, parse_template(argument(None)), 'fr', 'argument', 'argument.wiki', manifest)
    assert not any(i.code == 'WDV-MWK-023' for i in ctx.report.findings), ctx.report.to_text()
    ctx=context()
    validate_template_shape(ctx, parse_template(argument()), 'fr', 'argument', 'argument.wiki', manifest)
    assert any(i.code == 'WDV-MWK-023' for i in ctx.report.findings)


def _source(argument_verified=True, also_objections=True, role='supports_summary'):
    usage={
        'page_id':'A0001','language':'fr','role':role,
        'language_fit':'native','preferred_equivalent_source_id':None,
        'documentary_scope':'narrow_argument',
        'selection_reason':'Cette source développe directement le raisonnement de l’argument.',
    }
    if argument_verified is not None:
        usage['argument_development_verified']=argument_verified
    if also_objections is not None:
        usage['also_develops_objections']=also_objections
    return {
        'id':'S00001','type':'bibliography','language':'fr','document_kind':'book','equivalence_group':None,
        'metadata':{'authors':['Auteur'],'article':None,'work':'Ouvrage','volume':None,'issue':None,'location':None,'publisher':'Éditeur','place':'Paris','date':'2020','link':None,'page':None,'site':None,'title':None},
        'verification':{'status':'verified','verified_at':'2026-08-05T00:00:00+02:00','primary_source':True,'notes':[],'language_verified':True,'authorship_checked':True,'authorship_verified':True},
        'usage':[usage],'deduplication_key':'ouvrage-auteur-2020',
    }


def _source_package(tmp_path, source):
    root=create_graph_package(tmp_path)
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    manifest['normative_versions']['consolidated_norm']='1.2.33'
    dump(root/'manifest.json',manifest)
    registry=json.loads((root/'data/registre_debat.json').read_text(encoding='utf-8'))
    registry['graph']['nodes'][0]['sources']['fr']['bibliography']=['S00001']
    dump(root/'data/registre_debat.json',registry)
    dump(root/'data/sources.json',{'source_registry_version':'1.2','debate_id':'exemple','sources':[source]})
    return root


def test_argument_reference_may_also_develop_objections(tmp_path):
    report=validate_package(_source_package(tmp_path,_source(True,True)),scopes=['sources'])
    assert not any(i.code == 'WDV-SRC-006' for i in report.findings), report.to_text()


def test_argument_reference_must_develop_argument_not_only_context(tmp_path):
    report=validate_package(_source_package(tmp_path,_source(None,True,'context')),scopes=['sources'])
    assert any(i.code == 'WDV-SRC-006' for i in report.findings), report.to_text()


def test_argument_reference_requires_explicit_argument_attestation(tmp_path):
    report=validate_package(_source_package(tmp_path,_source(None,False)),scopes=['sources'])
    assert any(i.code == 'WDV-SRC-006' for i in report.findings), report.to_text()

def test_preexisting_french_page_may_gain_interlanguage_when_english_is_ready():
    historical = argument(None).replace('|interlangue={{Lien interlangue\n|langue=en\n|page=Argument topic\n}}\n', '')
    page_manifest={'page_id':'A0001','page_type':'argument','page_origin':'preexisting','creation_date':'2026-08-05','preserved_parameters':preserved(historical, 'argument')}
    ctx = PackageContext(
        root=Path('.'),
        report=Report('0.4.73', '.', ['wikicode']),
        cache={'manifest.json': {
            'normative_versions': {'consolidated_norm': '1.2.58'},
            'translation_status': {'en': 'ready'},
            'pages': [
                {'page_id':'A0001','page_type':'argument','language':'fr','canonical_title':'Argument français'},
                {'page_id':'A0001','page_type':'argument','language':'en','canonical_title':'Argument topic'},
            ],
        }},
    )
    validate_template_shape(ctx, parse_template(argument(None)), 'fr', 'argument', 'argument.wiki', page_manifest)
    assert not any(i.code == 'WDV-MWK-023' and 'interlangue' in i.message for i in ctx.report.findings), ctx.report.to_text()

