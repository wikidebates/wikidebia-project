import hashlib

import pytest

from wikidebia_validator.package import PackageContext
from wikidebia_validator.report import Report
from wikidebia_validator.wikicode import parse_template, validate_template_shape


def citation_context(tmp_path, *, link='www.example.org/article'):
    citation = '{{Citation|citation=Texte historique.|auteurs=Autrice|lien=' + link + '}}'
    raw = ('{{Argument|citations=' + citation + '}}\n').encode()
    path = tmp_path / 'imports/fr/arguments/A0001.wiki'
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    provenance = {'pages': [{'kind': 'argument', 'page_id': 'A0001',
        'import_path': 'imports/fr/arguments/A0001.wiki',
        'sha256': hashlib.sha256(raw).hexdigest()}]}
    ctx = PackageContext(tmp_path, Report('0.4.105', 'test', ['wikicode']),
        cache={'manifest.json': {}, 'data/import_provenance.json': provenance})
    page = {'page_id': 'A0001', 'page_origin': 'preexisting'}
    return ctx, page, citation


def url_errors(ctx):
    return [f for f in ctx.report.findings if f.level == 'ERROR'
            and f.code == 'WDV-MWK-012' and 'URL HTTP/HTTPS' in f.message]


def test_preserved_french_citation_accepts_schemeless_link(tmp_path):
    ctx, page, citation = citation_context(tmp_path)
    tmpl = parse_template('{{Argument|citations=' + citation + '}}')
    validate_template_shape(ctx, tmpl, 'fr', 'argument', 'output/fr/arguments/A0001.wiki', page)
    assert not url_errors(ctx)
    assert any(f.level == 'INFO' and 'Lien historique' in f.message for f in ctx.report.findings)


def test_english_quote_preserves_original_schemeless_documentary_link(tmp_path):
    ctx, page, _ = citation_context(tmp_path)
    page['page_origin'] = 'new'
    tmpl = parse_template('{{Argument|quotes={{Quote|quote=Translated text.|authors=Autrice|link=www.example.org/article|warnings=AI-translated quote}}}}')
    validate_template_shape(ctx, tmpl, 'en', 'argument', 'output/en/arguments/A0001.wiki', page)
    assert not url_errors(ctx)


@pytest.mark.parametrize('mutation', ['new_page', 'changed_url', 'changed_quote', 'changed_author', 'bad_hash', 'missing_provenance', 'different_page'])
def test_new_or_changed_citation_keeps_strict_url_rule(tmp_path, mutation):
    ctx, page, citation = citation_context(tmp_path)
    if mutation == 'new_page': page['page_origin'] = 'new'
    if mutation == 'changed_url': citation = citation.replace('/article', '/other')
    if mutation == 'changed_quote': citation = citation.replace('Texte historique.', 'Texte modifié.')
    if mutation == 'changed_author': citation = citation.replace('Autrice', 'Autre')
    if mutation == 'bad_hash': ctx.cache['data/import_provenance.json']['pages'][0]['sha256'] = '0' * 64
    if mutation == 'missing_provenance': ctx.cache['data/import_provenance.json'] = {}
    if mutation == 'different_page': page['page_id'] = 'A0002'
    tmpl = parse_template('{{Argument|citations=' + citation + '}}')
    validate_template_shape(ctx, tmpl, 'fr', 'argument', 'output/fr/arguments/A0001.wiki', page)
    assert url_errors(ctx)


def test_preservation_does_not_allow_an_unsafe_url_scheme(tmp_path):
    ctx, page, citation = citation_context(tmp_path, link='javascript:alert(1)')
    tmpl = parse_template('{{Argument|citations=' + citation + '}}')
    validate_template_shape(ctx, tmpl, 'fr', 'argument', 'output/fr/arguments/A0001.wiki', page)
    assert url_errors(ctx)


def test_english_quote_cannot_change_historical_attribution(tmp_path):
    ctx, page, _ = citation_context(tmp_path)
    tmpl = parse_template('{{Argument|quotes={{Quote|quote=Translated text.|authors=Autre|link=www.example.org/article|warnings=AI-translated quote}}}}')
    validate_template_shape(ctx, tmpl, 'en', 'argument', 'output/en/arguments/A0001.wiki', page)
    assert url_errors(ctx)
