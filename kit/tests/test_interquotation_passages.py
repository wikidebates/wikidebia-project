"""Regression coverage for editorial text lost by quote-only assembly."""
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import wikidebia_citation_passages as passages
import wikidebia_content_review as content
import wikidebia_translation_review as translation
import wikidebia_render as render

FR = "Préambule.\n{{Citation|citation=Une première citation.|auteurs=Alice}}\n'''Objection :''' Deux lectures restent possibles.\n{{Citation|citation=Une seconde citation.|auteurs=Bob}}\nConclusion historique."
EN = ["Preamble.\n", "\n'''Objection:''' Two readings remain possible.\n", "\nHistorical conclusion."]


def translated_passages():
    source = passages.inventory_passages(FR, 'A0001')
    rows = passages.blank_translations(source)
    for row, text in zip(rows, EN):
        row.update(text=text, equivalent_to_french=True,
                   review_note='The qualification and its position relative to the quotations are preserved.')
    return source, rows


@pytest.mark.parametrize('lang', ['fr', 'en'])
def test_prose_survives_actual_argument_renderer_in_order(lang):
    source, rows = translated_passages()
    citations = content._citation_records(FR, 'A0001')
    if lang == 'en':
        for row, text in zip(citations, ['A first quotation.', 'A second quotation.']):
            row['parameters'] = [{'name': 'quote', 'value': text}]
    prose = passages.validate_translations(rows, source, 'A0001') if lang == 'en' else source
    output = render._render_argument(
        lang=lang, node={'id': 'A0001', 'fr': {}, 'en': {}},
        content={'citations': citations, 'citation_passages': prose},
        registry={'graph': {'nodes': [], 'edges': []}}, sources={}, include_interlanguage=False,
    )
    expected = EN if lang == 'en' else [p['text'] for p in source]
    assert output.index(expected[0]) < output.index('{{Quote' if lang == 'en' else '{{Citation')
    assert output.index(expected[1]) < output.index('{{Quote' if lang == 'en' else '{{Citation', output.index(expected[1]))
    assert output.index(expected[2]) > output.rindex('{{Quote' if lang == 'en' else '{{Citation')
    assert output.count('{{Quote' if lang == 'en' else '{{Citation') == 2


@pytest.mark.parametrize('mutation', ['delete', 'reorder', 'move', 'source', 'empty', 'unreviewed'])
def test_translation_cannot_drop_move_or_silently_rewrite_passages(mutation):
    source, rows = translated_passages()
    if mutation == 'delete': rows.pop(1)
    elif mutation == 'reorder': rows.reverse()
    elif mutation == 'move': rows[1]['before_citation_id'] = 'A0001-C001'
    elif mutation == 'source': rows[1]['source_text'] = 'A different French claim.'
    elif mutation == 'empty': rows[1]['text'] = ' '
    else: rows[1]['equivalent_to_french'] = False
    with pytest.raises(ValueError):
        passages.validate_translations(rows, source, 'A0001')


def test_prose_without_any_quote_is_preserved():
    source = passages.inventory_passages('Une précision sans citation.', 'A0001')
    assert passages.render_sequence([], source, lambda row: '') == 'Une précision sans citation.'


def test_legacy_locks_missing_original_prose_cannot_start_translation(tmp_path, monkeypatch):
    data = tmp_path / 'data'
    data.mkdir()
    for name in ['registre_debat.json', 'fr_page_metadata_lock.json', 'keyword_vocabulary.json']:
        (data / name).write_text('{}')
    (data / 'fr_content_lock.json').write_text(json.dumps({'arguments': [{'id': 'A0001'}]}))
    monkeypatch.setattr(translation, '_source_imports', lambda source: ({}, {}, [
        {'id': 'A0001', 'citation_passages': passages.inventory_passages(FR, 'A0001')}
    ]))
    with pytest.raises(translation.TranslationReviewError, match='Verrou français incomplet'):
        translation._source_snapshot(tmp_path)


def test_semantic_fingerprint_covers_translated_editorial_prose():
    source, rows = translated_passages()
    review = {'arguments': [{'id': 'A0001', 'translation': {'french': {
        'content': {'citation_passages': source}}}}],
        'final_values': {'arguments': [{'id': 'A0001', 'citation_passages': rows}]}}
    before = translation.semantic_content_sha256(review)
    review['final_values']['arguments'][0]['citation_passages'][1]['text'] += ' Certainly.'
    assert translation.semantic_content_sha256(review) != before


def test_renderer_rejects_missing_anchor_instead_of_omitting_prose():
    with pytest.raises(ValueError, match='Ancrage'):
        passages.render_sequence([], [{'id': 'P1', 'before_citation_id': 'missing', 'text': 'Keep this.'}], lambda row: '')


def test_translation_preparation_exposes_unreviewed_prose_without_auto_translation():
    source, _ = translated_passages()
    row = translation._blank_argument({'id': 'A0001', 'page_origin': 'preexisting'},
                                     {'citation_passages': source})
    assert [p['source_text'] for p in row['citation_passages']] == [p['text'] for p in source]
    assert all(p['text'] == '' and p['equivalent_to_french'] is False for p in row['citation_passages'])


def test_finalized_argument_retains_separately_reviewed_prose():
    from test_wikidebia_translation_review import nominal_argument_translation
    row, mapping = nominal_argument_translation()
    source = passages.inventory_passages('Une précision historique.', 'A-HIST')
    row['french']['content']['citation_passages'] = source
    row['citation_passages'] = passages.blank_translations(source)
    row['citation_passages'][0].update(text='A historical clarification.', equivalent_to_french=True,
        review_note='The historical qualification is faithfully translated as separate editorial prose.')
    final = translation._validate_argument({'id': 'A-HIST', 'translation': row}, mapping, {},
                                           authoritative_source_page_origin='preexisting')
    assert final['citation_passages'][0]['text'] == 'A historical clarification.'
    assert final['summary'] is None
    assert final['citations'] == []
