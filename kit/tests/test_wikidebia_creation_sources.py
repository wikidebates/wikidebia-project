"""Source adoption is an explicit local review, not inferred from search notes."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import socket
import subprocess

import pytest

import wikidebia_creation_context as cc
import wikidebia_creation_import as ci
import wikidebia_creation_research as research
import wikidebia_creation_sources as sources
import wikidebia_creation_resume as resume
from test_wikidebia_creation_resume import project, set_state, snapshot, load, put
from test_wikidebia_creation_import import returned, CORPUS, run_import
from test_wikidebia_creation_research import resource, observation


def record(project, pages=('A0001',), *, title='Recorded documentary title', link='https://example.org/a-study',
           mutate=None):
    package = ci.prepare_package(project, CORPUS, research_only=True, page_ids=list(pages))
    entries = [observation(page, 'r1') for page in pages]
    notes = dict(research.empty_response(), resources=[resource(title=title, link=link)],
                 observations=entries)
    if mutate:
        mutate(notes)
    returned(project, package, edit_files=lambda files: files.update({
        research.EDITABLE_PATH: cc._json(notes)}))
    assert run_import(project)['status'] == 'imported'
    current = load(project/CORPUS/research.LEDGER_PATH)
    return current['resources'][0]['id'], [r['id'] for r in current['observations']]


def chosen(resource_id, observation_id, page='A0001', role='supports_summary'):
    return {
        'resource_id': resource_id, 'document_kind': 'other', 'primary_source': False,
        'verification': {
            'metadata_checked': True, 'language_verified': True,
            'authorship_checked': True, 'authorship_verified': False,
            'notes': 'La notice, le contenu et la langue ont ete effectivement examines.',
            'variants_reviewed': False, 'variant_reason': ''},
        'usages': [{'page_id': page, 'observation_id': observation_id, 'role': role,
                    'selection_reason': 'Cette source decrit directement le mecanisme particulier de ce raisonnement.',
                    'documentary_scope': 'narrow_argument' if page != 'exemple' else 'introduction_fact',
                    'also_develops_objections': False if page != 'exemple' else None,
                    'objection_coverage_note': None}]
    }


def review(*decisions):
    return {'schema': sources.SCHEMA, 'reviewer': 'Comite editorial test',
            'reviewed_at': '2026-11-21T10:00:00+01:00', 'decisions': list(decisions)}


def submit(project, decisions, *, pages=('A0001',), research_payload=None):
    package = ci.prepare_package(project, CORPUS, research_only=True, page_ids=list(pages))
    def editor(files):
        files[sources.EDITABLE_PATH] = cc._json(decisions)
        if research_payload is not None:
            files[research.EDITABLE_PATH] = cc._json(research_payload)
    returned(project, package, edit_files=editor)
    return package


def test_explicit_review_imports_canonical_source_reciprocal_usage_and_audit(project, monkeypatch):
    rid, ids = record(project)
    before = snapshot(project/CORPUS)
    def forbidden(*args, **kwargs):
        raise AssertionError('No network or model calls during source adoption')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(subprocess, 'run', forbidden)
    package = submit(project, review(chosen(rid, ids[0])))
    with __import__('zipfile').ZipFile(project/package['package_path']) as archive:
        assert sources.EDITABLE_PATH in archive.namelist()
        assert json.loads(archive.read(sources.EDITABLE_PATH)) == sources.empty_response()
        assert b'La revue doit' in archive.read('context/SOURCES_HELP.md')
    result = run_import(project)
    assert result['status'] == 'imported'
    assert result['sources_selected'] == {'sources_added': 1, 'usages_added': 1,
                                          'reviews_recorded': 1, 'independent_verification_performed': False}
    assert result['source_verification_performed'] is False
    after = snapshot(project/CORPUS)
    assert {k for k in after if before.get(k) != after[k]} == {
        'data/sources.json', 'data/registre_debat.json', sources.AUDIT_PATH}
    reg = load(project/CORPUS/'data/sources.json')['sources']
    s = reg[-1]
    assert s['id'].startswith('S') and s['metadata']['title'] == 'Recorded documentary title'
    assert s['verification']['status'] == 'verified'
    assert s['verification']['notes'] and s['usage'][0]['page_id'] == 'A0001'
    node = next(n for n in load(project/CORPUS/'data/registre_debat.json')['graph']['nodes'] if n['id'] == 'A0001')
    assert node['sources']['fr']['webliography'][-1] == s['id']
    assert s['id'] in [src['id'] for src in load(project/resume.creation_resume(project,CORPUS)['context']['context_path']/'CORPUS_CONTEXT.json')['sources']]
    assert run_import(project)['status'] == 'already_imported'


def test_exact_repeated_review_does_not_duplicate_source_usage_or_audit(project):
    rid, ids = record(project)
    doc = review(chosen(rid, ids[0]))
    submit(project, doc)
    run_import(project)
    old = snapshot(project/CORPUS)
    submit(project, doc)
    assert run_import(project)['status'] == 'no_changes'
    assert snapshot(project/CORPUS) == old


def test_same_source_shared_across_arguments_without_recopying_metadata(project):
    rid, observations = record(project, ('A0001', 'A0002'))
    submit(project, review(chosen(rid, observations[0])), pages=('A0001',))
    run_import(project)
    submit(project, review(chosen(rid, observations[1], page='A0002')), pages=('A0002',))
    result = run_import(project)
    assert result['sources_selected']['sources_added'] == 0
    assert result['sources_selected']['usages_added'] == 1
    reg = load(project/CORPUS/'data/sources.json')['sources']
    assert len(reg) == 1 and len(reg[0]['usage']) == 2
    nodes = load(project/CORPUS/'data/registre_debat.json')['graph']['nodes']
    assert all(reg[0]['id'] in next(n for n in nodes if n['id'] == page)['sources']['fr']['webliography']
               for page in ('A0001', 'A0002'))


@pytest.mark.parametrize('mutator', [
    lambda r: r['decisions'][0]['verification'].update(metadata_checked=False),
    lambda r: r['decisions'][0]['verification'].update(language_verified=False),
    lambda r: r['decisions'][0]['verification'].update(notes=''),
    lambda r: r['decisions'][0]['verification'].update(authorship_verified=True),
    lambda r: r['decisions'][0]['usages'][0].update(role='pro_reference'),
    lambda r: r['decisions'][0]['usages'][0].update(observation_id='Ounknown'),
    lambda r: r['decisions'][0]['usages'][0].update(selection_reason='vague'),
    lambda r: r['decisions'][0]['usages'][0].update(also_develops_objections=None),
    lambda r: r['decisions'][0]['usages'][0].update(documentary_scope='broad_synthesis'),
    lambda r: r.update(reviewer=''),
    lambda r: r.update(reviewed_at='2050-01-01T01:00:00Z'),
    lambda r: r['decisions'].append(copy.deepcopy(r['decisions'][0])),
    lambda r: r['decisions'][0].update(extra='malicious'),
])
def test_bad_attestations_do_not_change_any_canonical_file(project, mutator):
    rid, ids = record(project)
    payload = review(chosen(rid, ids[0]))
    mutator(payload)
    submit(project, payload)
    old = snapshot(project/CORPUS)
    with pytest.raises(cc.CreationContextError):
        run_import(project)
    assert snapshot(project/CORPUS) == old


def test_invalid_evidence_or_stale_page_blocks_entire_return(project):
    rid, ids = record(project)
    set_state(project, 'A0001', 'in_progress', text='Page changed after consultation')
    submit(project, review(chosen(rid, ids[0])))
    old = snapshot(project/CORPUS)
    with pytest.raises(cc.CreationContextError, match='stale'):
        run_import(project)
    assert snapshot(project/CORPUS) == old


def test_context_only_or_located_is_not_evidence_of_support(project):
    def context_only(notes):
        notes['observations'][0]['assessment'] = 'context_only'
    rid, ids = record(project, mutate=context_only)
    submit(project, review(chosen(rid, ids[0])))
    old = snapshot(project/CORPUS)
    with pytest.raises(cc.CreationContextError, match='consulted supporting observation'):
        run_import(project)
    assert snapshot(project/CORPUS) == old


def test_sources_cannot_be_selected_in_a_drafting_package(project):
    rid, ids = record(project)
    package = ci.prepare_package(project, CORPUS)
    with __import__('zipfile').ZipFile(project/package['package_path']) as archive:
        assert sources.EDITABLE_PATH not in archive.namelist()
    returned(project, package, edit_files=lambda files: files.update({sources.EDITABLE_PATH: cc._json(review(chosen(rid, ids[0])))}))
    with pytest.raises(cc.CreationContextError):
        run_import(project)


def test_review_cannot_adopt_new_research_in_same_reply(project):
    rid, ids = record(project)
    package = ci.prepare_package(project, CORPUS, research_only=True, page_ids=['A0001'])
    fresh = dict(research.empty_response(), resources=[resource('r-new', link='https://example.org/new')],
                 observations=[observation('A0001', 'r-new')])
    returned(project, package, edit_files=lambda files: files.update({
        sources.EDITABLE_PATH: cc._json(review(chosen('Runknown', ids[0]))),
        research.EDITABLE_PATH: cc._json(fresh)}))
    old = snapshot(project/CORPUS)
    with pytest.raises(cc.CreationContextError):
        run_import(project)
    assert snapshot(project/CORPUS) == old


def test_conflicting_variants_require_explicit_resolution(project):
    rid, ids = record(project)
    # A second metadata variant has exactly the same canonical URL and distinct title.
    package = ci.prepare_package(project, CORPUS, research_only=True, page_ids=['A0001'])
    new = dict(research.empty_response(), resources=[resource('v2', title='Different metadata title', link='https://example.org/a-study')],
               observations=[observation('A0001', 'v2')])
    returned(project, package, edit_files=lambda files: files.update({research.EDITABLE_PATH: cc._json(new)}))
    run_import(project)
    payload = review(chosen(rid, ids[0]))
    submit(project, payload)
    with pytest.raises(cc.CreationContextError, match='variants'):
        run_import(project)
    payload['decisions'][0]['verification'].update(variants_reviewed=True,
        variant_reason='The consulted publication shows the first title; the other is rejected.')
    submit(project, payload)
    assert run_import(project)['sources_selected']['sources_added'] == 1


def test_review_rejects_metadata_conflict_with_existing_canonical_source(project):
    rid, ids = record(project)
    submit(project, review(chosen(rid, ids[0])))
    run_import(project)
    # Same canonical URL but incompatible title remains a research variant.
    package = ci.prepare_package(project, CORPUS, research_only=True, page_ids=['A0002'])
    new = dict(research.empty_response(), resources=[resource('v2', title='Different title', link='https://example.org/a-study')],
               observations=[observation('A0002', 'v2')])
    returned(project, package, edit_files=lambda files: files.update({research.EDITABLE_PATH: cc._json(new)}))
    run_import(project)
    saved = load(project/CORPUS/research.LEDGER_PATH)
    other = next(r for r in saved['resources'] if r['id'] != rid)
    obs = next(o for o in saved['observations'] if o['resource_id'] == other['id'])
    doc = review(chosen(other['id'], obs['id'], 'A0002'))
    doc['decisions'][0]['verification'].update(variants_reviewed=True,
        variant_reason='The second title has been examined, and must not replace the first.')
    submit(project, doc, pages=('A0002',))
    old = snapshot(project/CORPUS)
    with pytest.raises(cc.CreationContextError, match='conflicting metadata'):
        run_import(project)
    assert snapshot(project/CORPUS) == old


def test_unchanged_sentinel_is_noop_and_old_package_compatibility(project):
    rid, ids = record(project)
    package = ci.prepare_package(project, CORPUS, research_only=True, page_ids=['A0001'])
    returned(project, package)
    old = snapshot(project/CORPUS)
    assert run_import(project)['status'] == 'no_changes'
    assert snapshot(project/CORPUS) == old


def test_new_evidence_and_approval_cannot_arrive_in_one_transaction(project):
    rid, ids = record(project)
    new_notes = dict(research.empty_response(), resources=[resource('new', link='https://example.org/new')],
                     observations=[observation('A0001', 'new')])
    submit(project, review(chosen(rid, ids[0])), research_payload=new_notes)
    old = snapshot(project/CORPUS)
    with pytest.raises(ci.CreationImportError, match='previously saved research'):
        run_import(project)
    assert snapshot(project/CORPUS) == old


def test_debate_documentary_usage_requires_review_but_no_argument_reciprocal_record(project):
    set_state(project, 'exemple', 'pending')
    rid, ids = record(project, ('exemple',))
    decision = chosen(rid, ids[0], page='exemple', role='supports_introduction')
    submit(project, review(decision), pages=('exemple',))
    assert run_import(project)['sources_selected']['usages_added'] == 1
    doc = load(project/CORPUS/'data/sources.json')['sources'][0]
    assert doc['usage'][0]['page_id'] == 'exemple'
    assert doc['usage'][0]['role'] == 'supports_introduction'
    assert doc['usage'][0]['documentary_scope'] == 'introduction_fact'


def test_source_adoption_recovers_after_process_crash(project):
    rid, ids = record(project)
    submit(project, review(chosen(rid, ids[0])))
    before = snapshot(project/CORPUS)
    import sys
    code = '''
import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import wikidebia_creation_import as ci
real = ci.os.rename
calls = 0
def rename(a,b):
 global calls
 calls += 1
 real(a,b)
 if calls == 1: os._exit(73)
ci.os.rename = rename
ci.import_package(Path(sys.argv[2]), 'corpus/exemple')
'''
    process = subprocess.run([sys.executable, '-c', code, str(Path(ci.__file__).parent), str(project)],
                             capture_output=True, text=True)
    assert process.returncode == 73, process.stderr
    with pytest.raises(ci.CreationImportError, match='Interrupted'):
        resume.creation_resume(project, CORPUS, prepare=False)
    assert run_import(project, recover=True)['status'] == 'rolled_back'
    assert snapshot(project/CORPUS) == before
    assert run_import(project)['status'] == 'imported'
    assert len(load(project/CORPUS/'data/sources.json')['sources']) == 1


def test_old_undocumented_research_package_still_imports_without_source_review(project):
    package = ci.prepare_package(project, CORPUS)
    assert 'sources' not in package
    returned(project, package, {'A0001': 'partial'})
    assert run_import(project)['status'] == 'imported'
