import hashlib
import json
from types import SimpleNamespace
from pathlib import Path

from wikidebia_validator.package import PackageContext
from wikidebia_validator.report import Report
from wikidebia_validator.schema_validation import _preserved_keyword_duplicates, _valid_translation_source_preservation
from wikidebia_validator.graph import contextual_title_issues

def dump(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def fixture(root):
    source='{{Argument|mots-clés=cannabis, liberté, cannabis}}'
    path=root/'imports/fr/arguments/A0001.wiki';path.parent.mkdir(parents=True);path.write_text(source)
    page={'kind':'argument','page_id':'A0001','import_path':'imports/fr/arguments/A0001.wiki','revision_id':10,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    receipt={'schema':'wikidebia-translation-source-preservation-1.0','policy':'published-french-import-preserved-for-translation-1.0','pages':[page]}
    receipt['receipt_sha256']=hashlib.sha256(json.dumps(receipt,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    dump(root/'data/source_preservation_receipt.json',receipt)
    dump(root/'data/import_provenance.json',{'schema':'wikidebia-import-provenance-1.0','pages':[page]})
    for filename in ['fr_content_lock.json','fr_page_metadata_lock.json']:dump(root/'data'/filename,{'source_preservation_receipt_sha256':receipt['receipt_sha256']})
    dump(root/'data/keyword_vocabulary_bilingual.json',{'entries':[{'fr':'cannabis','en':'cannabis'},{'fr':'liberté','en':'liberty'}]})
    dump(root/'manifest.json',{'pages':[]})
    registry={'graph':{'nodes':[{'id':'A0001','en':{'keywords':['cannabis','liberty','cannabis']}}]}}
    return registry

def context(root):
    return PackageContext(root,Report('test',str(root),['schema']))

def error():
    return SimpleNamespace(validator='uniqueItems',absolute_path=['graph','nodes',0,'en','keywords'])

def test_only_exact_source_duplicates_are_exempt(tmp_path):
    registry=fixture(tmp_path);ctx=context(tmp_path)
    assert _valid_translation_source_preservation(ctx)
    assert _preserved_keyword_duplicates(ctx,'argument_registry.schema.json',registry,error())
    registry['graph']['nodes'][0]['en']['keywords'].append('liberty')
    assert not _preserved_keyword_duplicates(ctx,'argument_registry.schema.json',registry,error())

def test_modified_source_or_receipt_cannot_exempt_duplicates(tmp_path):
    registry=fixture(tmp_path)
    (tmp_path/'imports/fr/arguments/A0001.wiki').write_text('{{Argument|mots-clés=cannabis, liberté}}')
    assert not _preserved_keyword_duplicates(context(tmp_path),'argument_registry.schema.json',registry,error())

def test_new_english_keyword_collision_is_not_an_existing_duplicate(tmp_path):
    registry=fixture(tmp_path)
    dump(tmp_path/'data/keyword_vocabulary_bilingual.json',{'entries':[{'fr':'cannabis','en':'same'},{'fr':'liberté','en':'same'}]})
    registry['graph']['nodes'][0]['en']['keywords']=['same','same','same']
    assert not _preserved_keyword_duplicates(context(tmp_path),'argument_registry.schema.json',registry,error())

def test_impersonal_it_with_intensifier_is_not_a_contextual_referent():
    assert not contextual_title_issues('It is entirely possible to decriminalise all drugs','en')
    assert 'initial_contextual_referent' in contextual_title_issues('It is entirely harmful','en')

def test_impersonal_judgments_supply_their_subject_in_the_following_clause():
    titles = [
        'It is entirely rational to regard threatening people as enemies',
        'It is false to claim that the far right wins every debate',
        "It is very uncomfortable to acknowledge, but there is a connection between Heidegger's thought and Nazism",
        'It would be rational to examine opposing arguments',
        'It is false that every debate is harmless',
    ]
    for title in titles:
        assert not contextual_title_issues(title, 'en'), title
    for title in ['It is entirely rational', 'It is false', 'It is very uncomfortable',
                  'It is harmful to democracy', 'It changes public opinion']:
        assert 'initial_contextual_referent' in contextual_title_issues(title, 'en'), title

def test_missing_final_newline_is_preserved_only_for_the_exact_import(tmp_path):
    fixture(tmp_path);ctx=context(tmp_path)
    rel='imports/fr/arguments/A0001.wiki'
    assert ctx.read_text(rel).endswith('}}')
    assert not any(f.code=='WDV-FS-005' for f in ctx.report.findings)
    generated=tmp_path/'output/en/arguments/A0001.wiki';generated.parent.mkdir(parents=True);generated.write_text('{{Argument}}')
    ctx.read_text('output/en/arguments/A0001.wiki')
    assert any(f.code=='WDV-FS-005' and f.path=='output/en/arguments/A0001.wiki' for f in ctx.report.findings)
    (tmp_path/rel).write_text('{{Argument|mots-clés=changed}}')
    new=context(tmp_path);new.read_text(rel)
    assert any(f.code=='WDV-FS-005' and f.path==rel for f in new.report.findings)

def test_bilingual_sections_use_source_categories_and_english_alphabetical_order(tmp_path):
    from wikidebia_validator.bilingual import validate_bilingual
    registry=fixture(tmp_path)
    node=registry['graph']['nodes'][0]
    node.update(status='active',fr={'rubriques':['Droit','Économie']})
    node['en']['sections']=['Economy','Law']
    receipt=json.loads((tmp_path/'data/source_preservation_receipt.json').read_text())
    dump(tmp_path/'data/fr_page_metadata_lock.json',{'source_preservation_receipt_sha256':receipt['receipt_sha256'],'arguments':[{'entity_id':'A0001','rubriques':['Droit','Économie']}]})
    ctx=context(tmp_path);ctx.registry=lambda:registry
    validate_bilingual(ctx)
    assert not any(f.code=='WDV-BIL-004' for f in ctx.report.findings)
    node['en']['sections']=['Law','Economy']
    ctx=context(tmp_path);ctx.registry=lambda:registry;validate_bilingual(ctx)
    assert any(f.code=='WDV-BIL-004' for f in ctx.report.findings)

def test_source_page_preservation_allows_only_the_added_link(tmp_path):
    from wikidebia_validator.source_preservation import preserved_french_page
    fixture(tmp_path);ctx=context(tmp_path)
    page={'page_id':'A0001','language':'fr','page_type':'argument'}
    source=(tmp_path/'imports/fr/arguments/A0001.wiki').read_text()
    good=source[:-2]+'|interlangue={{Lien interlangue|langue=en|page=Title}}\n}}\n'
    assert preserved_french_page(ctx,page,good)
    assert not preserved_french_page(ctx,page,good.replace('liberté','contrôle'))
    assert not preserved_french_page(ctx,page,good.replace('}}\n}}','}}\n|résumé=Nouveau texte}}'))

def test_mixed_quote_passages_keep_positions_and_full_text():
    from wikidebia_validator.wikicode import _mixed_citations
    quotes,gaps=_mixed_citations('{{Quote|quote=First}}A complete passage.{{Quote|quote=Second}}End.')
    assert [q.one('quote') for q in quotes]==['First','Second']
    assert gaps==[(1,'A complete passage.'),(2,'End.')]

def test_common_english_verbs_are_predicates_without_accepting_nominal_headings():
    from wikidebia_validator.editorial import displayed_title_argument_issues
    assert not displayed_title_argument_issues('Prohibition harms society','en')
    assert not displayed_title_argument_issues('Users have suffered the consequences','en')
    assert displayed_title_argument_issues('An economy built on dependence','en')

def test_only_proven_historical_absence_can_have_no_rubric(tmp_path):
    from wikidebia_validator.schema_validation import _preserved_empty_rubrics
    registry=fixture(tmp_path);registry['graph']['nodes'][0]['fr']={'rubriques':[]}
    err=SimpleNamespace(validator='minItems',absolute_path=['graph','nodes',0,'fr','rubriques'])
    assert _preserved_empty_rubrics(context(tmp_path),'argument_registry.schema.json',registry,err)
    (tmp_path/'imports/fr/arguments/A0001.wiki').write_text('{{Argument|rubriques=Santé}}')
    assert not _preserved_empty_rubrics(context(tmp_path),'argument_registry.schema.json',registry,err)

def test_ordinary_english_predicates_remain_propositions_without_accepting_fragments():
    from wikidebia_validator.editorial import displayed_title_argument_issues, displayed_title_issues
    for title in ['Debating the enemy gets us nowhere', 'Some debates humiliate the people they target',
                  'Stigmatizing enemies only entrenches them', 'We cannot debate enemies',
                  'Many philosophers debated Heidegger', 'Some debates provide cover for violence',
                  'The list of opinions risks growing forever', 'Consider the writer who expressed anti-Zionism',
                  'People consciously or unconsciously defend harmful ideologies',
                  'We go to great lengths to label opponents',
                  'False opinions that appeal to emotion survive debunking intact',
                  'Antisemitism no longer needs dog whistles']:
        assert not displayed_title_argument_issues(title, 'en'), title
    for title in ['An opportunity to humiliate people', 'Evidence that entrenches existing views',
                  'An economy built on dependence', 'Ideas about political enemies',
                  'Opinions that appeal to emotion']:
        assert displayed_title_argument_issues(title, 'en'), title
    good='Protest votes often bring to power politicians far worse than those the public wanted to get rid of'
    assert 'dangling_connector' not in displayed_title_issues(good, 'en')
    assert 'dangling_connector' in displayed_title_issues('Protest votes often bring politicians to', 'en')
