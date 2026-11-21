"""Documentary memory is not documentary approval. No network or wiki is used."""
import copy
import json
from pathlib import Path
import socket
import subprocess
import sys
import zipfile

import pytest

import wikidebia_creation_context as cc
import wikidebia_creation_import as ci
import wikidebia_creation_research as research
import wikidebia_manage as manager
from test_wikidebia_creation_resume import project, set_state, snapshot, load, put
from test_wikidebia_creation_import import returned, CORPUS, run_import


def resource(key='r1', title='A documentary resource', link='https://example.org/paper'):
    return {'key': key, 'type': 'webliography', 'language': 'fr',
            'metadata': {'title': title, 'link': link}}


def observation(page='A0001', key='r1'):
    return {'page_id': page, 'resource_key': key, 'state': 'consulted',
            'observed_at': '2026-01-01T12:00:00Z', 'locator': 'Section 2',
            'excerpt': 'A brief passage actually read.', 'assessment': 'supports',
            'reason': 'The passage explains the particular mechanism.',
            'limitations': 'Limited to the population studied.', 'recheck_after': None}


def search(page='A0001', outcome='no_result', refs=None):
    return {'page_ids': [page], 'query': 'precise French equivalent query', 'provider': 'Catalogue',
            'searched_at': '2026-01-01T12:00:00Z', 'outcome': outcome,
            'resource_keys': refs or [], 'notes': 'Only the listed query was searched.', 'recheck_after': None}


def response():
    return dict(research.empty_response(), resources=[resource()], observations=[observation()], searches=[search()])


def prepare(root, **kw):
    return ci.prepare_package(root, CORPUS, **kw)


def send(root, package, payload, states=None):
    return returned(root, package, states,
        edit_files=lambda files: files.update({research.EDITABLE_PATH: cc._json(payload)}))


def notes(root):
    return load(root / CORPUS / research.LEDGER_PATH)


def context(root, *ids):
    r = cc.build_creation_context(root, 'arguments-fr', corpus_path=CORPUS, node_ids=ids or ['A0001'])
    payload = load(root / r['context_path'] / 'CORPUS_CONTEXT.json')
    assert 'canonical_sources' not in payload['research_notes']
    return dict(payload['research_notes'], canonical_sources=payload['sources'])


def test_combined_response_saves_text_and_research_without_verifying_sources(project, monkeypatch):
    before = snapshot(project / CORPUS)
    def forbidden(*args, **kw):
        raise AssertionError('No network or external process')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(subprocess, 'run', forbidden)
    package = prepare(project)
    payload = response()
    payload['observations'].append(observation('A0002'))
    send(project, package, payload, {'A0001': 'generated', 'A0002': 'partial'})
    r = run_import(project)
    assert r['research_saved'] == {'resources': 1, 'observations': 2, 'searches': 1}
    assert not r['source_verification_performed'] and not r['editorial_validation_performed']
    assert run_import(project)['status'] == 'already_imported'
    assert len(notes(project)['resources']) == 1
    assert notes(project)['observations'][0]['assessment'] == 'supports'
    after = snapshot(project / CORPUS)
    changed = {k for k in after if before.get(k) != after[k]}
    assert changed == {'manifest.json', 'data/registre_debat.json', research.LEDGER_PATH,
                       'output/fr/arguments/A0001.wiki', 'output/fr/arguments/A0002.wiki'}
    assert not context(project)['observations'][0]['page_basis_changed']
    assert not context(project)['source_verification_performed']


def test_research_only_saves_notes_on_generated_page_without_touching_any_canonical_byte(project):
    set_state(project, 'A0001', 'generated')
    set_state(project, 'A0002', 'generated')
    before = snapshot(project / CORPUS)
    assert prepare(project)['status'] == 'review_required'
    package = prepare(project, research_only=True)
    assert package['next']['action'] == 'research_only'
    assert prepare(project, research_only=True)['status'] == 'reused'
    send(project, package, response())
    assert run_import(project)['pages_saved'] == []
    after = snapshot(project / CORPUS)
    assert {k: v for k, v in after.items() if k != research.LEDGER_PATH} == before
    assert prepare(project)['status'] == 'review_required'


def test_empty_research_and_unchanged_text_is_noop(project):
    package = prepare(project)
    send(project, package, research.empty_response())
    before = snapshot(project / CORPUS)
    assert run_import(project)['status'] == 'no_changes'
    assert snapshot(project / CORPUS) == before


@pytest.mark.parametrize('state', ['partial', 'generated'])
def test_research_only_cannot_edit_drafts_or_generation_states(project, state):
    package = prepare(project, research_only=True)
    send(project, package, response(), {'A0001': state})
    before = snapshot(project / CORPUS)
    with pytest.raises(cc.CreationContextError, match='Research-only'):
        run_import(project)
    assert snapshot(project / CORPUS) == before


@pytest.mark.parametrize('ids', [['unknown'], ['A0001', 'A0001'], ['exemple', 'A0001']])
def test_explicit_selection_rejects_unknown_duplicate_or_mixed_pages(project, ids):
    with pytest.raises(cc.CreationContextError):
        prepare(project, research_only=True, page_ids=ids)


def test_selection_cannot_reopen_validated_pages(project):
    with pytest.raises(cc.CreationContextError, match='validated pages'):
        prepare(project, research_only=True, page_ids=['exemple'])
    with pytest.raises(ci.CreationImportError, match='research-only'):
        prepare(project, page_ids=['A0001'])


@pytest.mark.parametrize('limit', [0, 21, True])
def test_selection_checks_size(project, limit):
    with pytest.raises(cc.CreationContextError):
        prepare(project, research_only=True, max_pages=limit)


def test_explicit_selection_and_context_do_not_export_unrelated_notes(project):
    p = prepare(project, research_only=True, page_ids=['A0003'])
    r = response(); r['observations'] = [observation('A0003')]; r['searches'] = [search('A0003')]
    send(project, p, r); run_import(project)
    assert context(project)['observations'] == []
    assert context(project)['resources'] == []
    assert len(context(project, 'A0003')['observations']) == 1
    assert prepare(project)['next']['page_ids'] == ['A0001', 'A0002']


def test_later_text_change_marks_existing_evidence_stale_without_deleting_it(project):
    p = prepare(project); send(project, p, response()); run_import(project)
    before = notes(project)
    set_state(project, 'A0001', 'in_progress', text='Changed draft')
    c = context(project)
    assert c['observations'][0]['page_basis_changed']
    assert c['searches'][0]['page_basis_changed']
    assert c['observations'][0]['requires_editorial_review']
    assert notes(project) == before


def test_negative_and_expired_research_never_certifies_absence(project):
    r = research.empty_response(); row = search(); row['recheck_after'] = '2020-01-01'; r['searches'] = [row]
    p = prepare(project); send(project, p, r); run_import(project)
    c = context(project)
    assert c['searches'][0]['recheck_due'] and c['research_complete'] is False
    assert c['resources'] == [] and c['source_verification_performed'] is False
    assert 'never proves absence' in c['notice']


def test_identical_research_deduplicates_but_new_observation_keeps_history(project):
    p = prepare(project); r = response(); send(project, p, r); run_import(project)
    first = snapshot(project / CORPUS)
    p2 = prepare(project); send(project, p2, r)
    assert run_import(project)['status'] == 'no_changes'
    assert snapshot(project / CORPUS) == first
    r['observations'][0]['observed_at'] = '2026-01-02T12:00:00+00:00'
    send(project, p2, r)
    assert run_import(project)['research_saved'] == {'resources': 0, 'observations': 1, 'searches': 0}
    assert len(notes(project)['observations']) == 2


def test_existing_research_resource_id_can_be_reused_without_metadata_copy(project):
    p = prepare(project); send(project, p, response()); run_import(project)
    resource_id = notes(project)['resources'][0]['id']
    r = research.empty_response(); r['observations'] = [observation('A0002', resource_id)]
    p = prepare(project); send(project, p, r); run_import(project)
    assert len(notes(project)['resources']) == 1
    assert len(notes(project)['observations']) == 2


def test_canonical_source_reference_is_not_copied_or_modified(project):
    path = project / CORPUS / 'data/sources.json'; doc = load(path)
    s = resource(); s.pop('key'); s.update(id='S0001', usage=[], verification={'status': 'unverified'})
    doc['sources'] = [s]; put(path, doc)
    original = path.read_bytes()
    r = research.empty_response(); r['observations'] = [observation(key='source:S0001')]
    p = prepare(project); send(project, p, r); run_import(project)
    assert path.read_bytes() == original
    assert notes(project)['resources'] == []
    assert context(project)['canonical_sources'][0]['verification']['status'] == 'unverified'


def test_conflicting_metadata_are_preserved_as_variants_not_merged(project):
    r = response()
    r['resources'].append(resource('r2', 'A conflicting unrelated title'))
    r['observations'].append(observation(key='r2'))
    p = prepare(project); send(project, p, r); run_import(project)
    groups = context(project)['resource_identity_groups']
    assert len(groups) == 1
    assert groups[0]['conflicts'] and groups[0]['metadata_variants_require_review']
    assert len(notes(project)['resources']) == 2


def test_doi_variants_share_identity_without_equating_their_language(project):
    r = response(); r['resources'][0]['metadata']['link'] = 'https://doi.org/10.1000/EXAMPLE'
    r['resources'].append(resource('r2', link='https://dx.doi.org/10.1000/example'))
    r['resources'][1]['language'] = 'en'; r['observations'].append(observation(key='r2'))
    p = prepare(project); send(project, p, r); run_import(project)
    groups = context(project)['resource_identity_groups']
    assert len(groups) == 1 and groups[0]['identity_type'] == 'doi'
    assert groups[0]['languages'] == ['en', 'fr']


@pytest.mark.parametrize('change', [
    lambda r: r.update(verified=True),
    lambda r: r.update(schema='unknown'),
    lambda r: r['observations'][0].update(state='verified'),
    lambda r: r['observations'][0].update(assessment='approved'),
    lambda r: r['observations'][0].update(page_id='A0003'),
    lambda r: r['observations'][0].update(page_id='exemple'),
    lambda r: r['observations'][0].update(resource_key='missing'),
    lambda r: r['observations'][0].update(resource_key='source:S404'),
    lambda r: r['observations'][0].update(observed_at='2026-01-01'),
    lambda r: r['observations'][0].update(observed_at='9999-01-01T00:00:00Z'),
    lambda r: r['observations'][0].update(observed_at='not a date'),
    lambda r: r['observations'][0].update(recheck_after='2026-02-30'),
    lambda r: r['observations'][0].update(locator=''),
    lambda r: r['observations'][0].update(excerpt=''),
    lambda r: r['observations'][0].update(reason=''),
    lambda r: r['observations'][0].update(excerpt='x'*8001),
    lambda r: r['observations'][0].update(state='located'),
    lambda r: r['observations'][0].update(limitations='\x00'),
    lambda r: r['resources'].append(copy.deepcopy(r['resources'][0])),
    lambda r: r['resources'][0].update(language='French'),
    lambda r: r['resources'][0].update(type='verified'),
    lambda r: r['resources'][0]['metadata'].update(authors='Anonymous'),
    lambda r: r['resources'][0]['metadata'].update(verified=True),
    lambda r: r['resources'][0]['metadata'].update(title=''),
    lambda r: r['resources'][0]['metadata'].update(link=None),
    lambda r: r['resources'].append(resource('unused')),
    lambda r: r['searches'][0].update(page_ids=['A0001', 'A0001']),
    lambda r: r['searches'][0].update(page_ids=['A0003']),
    lambda r: r['searches'][0].update(resource_keys=['r1']),
    lambda r: r['searches'][0].update(outcome='found'),
    lambda r: r['searches'][0].update(query=''),
    lambda r: r['searches'][0].update(notes=''),
    lambda r: r.update(searches=[search()]*201),
])
def test_invalid_research_rejects_entire_return_without_writing_any_draft(project, change):
    r = response(); change(r)
    p = prepare(project); send(project, p, r, {'A0001': 'partial'})
    before = snapshot(project / CORPUS)
    with pytest.raises((cc.CreationContextError, ValueError)):
        run_import(project)
    assert snapshot(project / CORPUS) == before


@pytest.mark.parametrize('url', ['file:///etc/passwd', 'https://localhost/x', 'https://127.0.0.1/x',
    'https://192.168.1.2/x', 'https://user:password@example.org/x', 'https://example.org/?api_key=secret',
    'https://example.org/?X-Amz-Signature=secret', 'https://example.org:bad/x'])
def test_unsafe_resource_urls_are_never_saved(project, url):
    r = response(); r['resources'][0]['metadata']['link'] = url
    p = prepare(project); send(project, p, r)
    before = snapshot(project / CORPUS)
    with pytest.raises((cc.CreationContextError, ValueError)):
        run_import(project)
    assert snapshot(project / CORPUS) == before


def test_located_resource_and_unknown_language_are_not_promoted(project):
    r = response(); r['resources'][0]['language'] = None
    r['observations'][0].update(state='located', locator='', excerpt='', reason='', assessment='unassessed')
    p = prepare(project); send(project, p, r); run_import(project)
    assert notes(project)['resources'][0]['language'] is None
    assert notes(project)['observations'][0]['state'] == 'located'
    assert load(project / CORPUS / 'data/sources.json')['sources'] == []


def test_offline_resource_keeps_actual_bibliographical_metadata(project):
    r = response(); r['resources'][0].update(type='bibliography', metadata={
        'work': 'Actual title', 'authors': ['Named author'], 'date': '2012', 'publisher': 'Publisher'})
    p = prepare(project); send(project, p, r); run_import(project)
    assert notes(project)['resources'][0]['identity_key'].startswith('bib:')


@pytest.mark.parametrize('name', ['sources', 'scope'])
def test_context_change_stales_research_return(project, name):
    p = prepare(project); send(project, p, response())
    rel = load(project / CORPUS / 'manifest.json')['core_files'][name]
    path = project / CORPUS / rel; path.write_bytes(path.read_bytes() + b'\n')
    before = snapshot(project / CORPUS)
    with pytest.raises(ci.CreationImportError, match='Stale'):
        run_import(project)
    assert snapshot(project / CORPUS) == before


def test_tampered_notes_are_refused_even_when_not_selected(project):
    p = prepare(project); send(project, p, response()); run_import(project)
    path = project / CORPUS / research.LEDGER_PATH
    data = notes(project); data['observations'][0]['excerpt'] = 'tampered'; put(path, data)
    with pytest.raises(cc.CreationContextError, match='altered notes'):
        context(project, 'A0003')


@pytest.mark.parametrize('stop', ['before_move', 'after_backup', 'after_install'])
def test_research_transaction_recovers_after_process_death(project, stop):
    p = prepare(project); send(project, p, response(), {'A0001': 'generated'})
    before = snapshot(project / CORPUS)
    code = '''
import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import wikidebia_creation_import as ci
real=ci.os.rename
calls=0
def rename(a,b):
 global calls
 calls+=1
 if sys.argv[3]=='before_move' and calls==1: os._exit(74)
 real(a,b)
 if (sys.argv[3]=='after_backup' and calls==1) or (sys.argv[3]=='after_install' and calls==2): os._exit(74)
ci.os.rename=rename
ci.import_package(Path(sys.argv[2]),'corpus/exemple')
'''
    proc = subprocess.run([sys.executable, '-c', code, str(Path(ci.__file__).parent), str(project), stop], capture_output=True)
    assert proc.returncode == 74, proc.stderr
    result = run_import(project, recover=True)
    assert result['status'] == ('imported' if stop == 'after_install' else 'rolled_back')
    if stop != 'after_install':
        assert snapshot(project / CORPUS) == before
        run_import(project)
    assert len(notes(project)['observations']) == 1
    assert load(project / CORPUS / 'manifest.json')['pages'][1]['status'] == 'generated'


def test_legacy_text_only_request_still_imports_but_cannot_add_research(project):
    from wikidebia_review_workflow import _package_manifest_hash
    p = prepare(project)
    with zipfile.ZipFile(project / p['package_path']) as z:
        files = {n:z.read(n) for n in z.namelist()}
    manifest = json.loads(files['REVIEW_PACKAGE.json']); pid = manifest['package_id']
    _, control = ci._locations(project, CORPUS)
    state_path = control / (pid + '.json')
    state = ci._load(state_path, ci.STATE_SCHEMA); state.pop('sha256')
    for name in (research.EDITABLE_PATH, 'context/RESEARCH_HELP.md'):
        del files[name]; del state['files'][name]
    manifest['editable_files'] = [r for r in manifest['editable_files'] if r['package_path'] != research.EDITABLE_PATH]
    manifest['context_files'] = [r for r in manifest['context_files'] if r['package_path'] != 'context/RESEARCH_HELP.md']
    manifest['manifest_sha256'] = _package_manifest_hash(manifest)
    files['REVIEW_PACKAGE.json'] = cc._json(manifest)
    state['manifest'] = manifest; state['files']['REVIEW_PACKAGE.json'] = cc._sha(files['REVIEW_PACKAGE.json'])
    put(state_path, ci._seal(state))
    with zipfile.ZipFile(project / p['package_path'], 'w') as z:
        for k,v in files.items(): z.writestr(k,v)
    returned(project, p, {'A0001':'partial'})
    assert run_import(project)['status'] == 'imported'
    assert not (project / CORPUS / research.LEDGER_PATH).exists()


def test_manager_cli_and_script_help_expose_optional_research(project, capsys):
    rc = manager.main(['--root', str(project), 'creation-package', '--corpus', CORPUS,
                       '--research-only', '--page-id', 'A0003'])
    assert rc == 0
    result = json.loads(capsys.readouterr().out)
    assert result['next']['page_ids'] == ['A0003']
    with zipfile.ZipFile(project / result['package_path']) as z:
        assert research.EDITABLE_PATH in z.namelist()
        assert json.loads(z.read('editable/RESPONSE.json'))['pages'] == [{'page_id':'A0003', 'status':'unchanged'}]


def test_canonical_metadata_change_requires_recheck_without_rewriting_notes(project):
    path = project / CORPUS / 'data/sources.json'; doc = load(path)
    s = resource(); s.pop('key'); s.update(id='S0001', usage=[])
    doc['sources'] = [s]; put(path, doc)
    payload = research.empty_response(); payload['observations'] = [observation(key='source:S0001')]
    p = prepare(project); send(project, p, payload); run_import(project)
    before = notes(project)
    assert not context(project)['observations'][0]['resource_basis_changed']
    doc['sources'][0]['metadata']['title'] = 'Changed edition title'; put(path, doc)
    c = context(project)
    assert c['observations'][0]['resource_basis_changed']
    assert notes(project) == before


def test_new_candidate_matches_existing_canonical_identity_without_inheriting_verification(project):
    path = project / CORPUS / 'data/sources.json'; doc = load(path)
    s = resource(); s.pop('key'); s.update(id='S0001', usage=[], verification={'status':'verified'})
    doc['sources'] = [s]; put(path, doc)
    p = prepare(project); send(project, p, response()); run_import(project)
    c = context(project)
    assert len(c['resource_identity_groups']) == 1
    assert c['canonical_sources'][0]['id'] == 'S0001'
    assert 'verification' not in notes(project)['resources'][0]
    assert not c['source_verification_performed']


def test_research_packet_page_is_readonly_even_if_status_unchanged(project):
    p = prepare(project, research_only=True)
    returned(project, p, edit_files=lambda files: files.update({
        'editable/output/fr/arguments/A0001.wiki': b'Unrequested edit'}))
    before = snapshot(project / CORPUS)
    with pytest.raises(ci.CreationImportError, match='declared unchanged'):
        run_import(project)
    assert snapshot(project / CORPUS) == before


@pytest.mark.parametrize('name', ['INSTRUCTIONS.md', 'context/RESEARCH_HELP.md', 'context/CORPUS_CONTEXT.json'])
def test_research_package_readonly_guidance_is_bound_to_local_request(project, name):
    p = prepare(project)
    def tamper(files):
        files[name] += b'Changed'
        files[research.EDITABLE_PATH] = cc._json(response())
    returned(project, p, edit_files=tamper)
    before = snapshot(project / CORPUS)
    with pytest.raises(ci.CreationImportError):
        run_import(project)
    assert snapshot(project / CORPUS) == before


def test_duplicate_json_fields_are_rejected(project):
    p = prepare(project)
    raw = cc._json(response()).decode().replace('"observations":', '"observations": [], "observations":', 1)
    returned(project, p, edit_files=lambda files: files.update({research.EDITABLE_PATH: raw.encode()}))
    with pytest.raises(cc.CreationContextError, match='duplicate JSON'):
        run_import(project)


def test_linked_ledger_is_rejected(project):
    p = prepare(project); send(project, p, response()); run_import(project)
    path = project / CORPUS / research.LEDGER_PATH
    old = project / 'private_notes.json'; path.rename(old); path.symlink_to(old)
    with pytest.raises(cc.CreationContextError, match='Symlink'):
        context(project)


def test_package_manifest_remains_compatible_with_existing_schema(project):
    import jsonschema
    p = prepare(project, research_only=True)
    with zipfile.ZipFile(project / p['package_path']) as z:
        manifest = json.loads(z.read('REVIEW_PACKAGE.json'))
    root = Path(__file__).resolve().parents[2]
    schema = load(root / 'validator/src/wikidebia_validator/schemas/chatgpt_review_package.schema.json')
    jsonschema.Draft202012Validator(schema).validate(manifest)


def test_changed_norm_produces_a_new_research_only_request(project):
    p = prepare(project, research_only=True)
    version = load(project / 'norms/VERSIONS.json')['norm']
    path = project / f'norms/normative_reference/01_normes/WIKIDEBIA_NORME_CONSOLIDEE_{version}.md'
    path.write_bytes(b'Updated normative preamble.\n' + path.read_bytes())
    new = prepare(project, research_only=True)
    assert new['package_path'] != p['package_path']
    send(project, p, response())
    with pytest.raises(ci.CreationImportError, match='context or norm changed'):
        run_import(project)


def test_research_context_preserves_official_language_equivalents(project):
    path = project / CORPUS / 'data/sources.json'; doc = load(path)
    english = resource(); english.pop('key')
    english.update(id='S0001', language='en', equivalence_group='work-1', usage=[])
    french = resource(link='https://example.org/french'); french.pop('key')
    french.update(id='S0002', equivalence_group='work-1', usage=[])
    doc['sources'] = [english, french]; put(path, doc)
    r = research.empty_response(); r['observations'] = [observation(key='source:S0001')]
    p = prepare(project); send(project, p, r); run_import(project)
    c = context(project)
    assert set(c['canonical_source_ids']) == {'S0001', 'S0002'}
    assert [s['id'] for s in c['canonical_sources']] == ['S0001', 'S0002']


def test_stale_receipt_never_overwrites_later_research(project):
    p = prepare(project); send(project, p, response()); run_import(project)
    original = (project / 'incoming/returned.zip').read_bytes()
    r = response(); r['observations'][0]['reason'] = 'New observation of the same source.'
    p = prepare(project); send(project, p, r); run_import(project)
    before = snapshot(project / CORPUS)
    (project / 'incoming/returned.zip').write_bytes(original)
    receipt = run_import(project)
    assert receipt['status'] == 'already_imported'
    assert receipt['current_state_matches_receipt'] is False
    assert snapshot(project / CORPUS) == before
