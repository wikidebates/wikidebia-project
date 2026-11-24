"""Draft imports never certify editorial content or touch a wiki."""
import copy
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import zipfile

import pytest

import wikidebia_creation_import as ci
import wikidebia_creation_context as cc
import wikidebia_creation_resume as cr
import wikidebia_manage as manager
from test_wikidebia_creation_resume import project, set_state, snapshot, load, put, edit

CORPUS = 'corpus/exemple'


def prepare(project, **kwargs):
    return ci.prepare_package(project, CORPUS, **kwargs)


def returned(project, prepared, states=None, text=None, edit_files=None, filename='returned.zip'):
    with zipfile.ZipFile(project / prepared['package_path']) as z:
        files = {name: z.read(name) for name in z.namelist()}
    response = json.loads(files['editable/RESPONSE.json'])
    for row in response['pages']:
        key = row['page_id']
        row['status'] = (states or {}).get(key, 'unchanged')
        if row['status'] != 'unchanged':
            path = 'editable/output/fr/' + ('debate/debate.wiki' if key == 'exemple' else f'arguments/{key}.wiki')
            files[path] = (text or '{{Argument|r\u00e9sum\u00e9=Brouillon propre a ce raisonnement}}').encode()
    files['editable/RESPONSE.json'] = cc._json(response)
    if edit_files:
        edit_files(files)
    target = project / 'incoming' / filename
    target.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(target, 'w') as z:
        for name, raw in files.items():
            z.writestr(name, raw)
    return target


def run_import(project, **kw):
    return ci.import_package(project, CORPUS, **kw)


def test_round_trip_partial_generated_and_unchanged(project, monkeypatch):
    before = snapshot(project / CORPUS)
    def forbidden(*args, **kw):
        raise AssertionError('No network or subprocess')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(subprocess, 'run', forbidden)
    p = prepare(project)
    assert snapshot(project / CORPUS) == before
    assert prepare(project)['status'] == 'reused'
    returned(project, p, {'A0001': 'partial'})
    r = run_import(project)
    assert r['status'] == 'imported' and r['pages_saved'] == ['A0001']
    assert r['editorial_validation_performed'] is False
    assert run_import(project)['status'] == 'already_imported'
    inv = cr.creation_resume(project, CORPUS, prepare=False)
    assert inv['counts']['draft_in_progress'] == 1
    assert inv['next']['page_ids'] == ['A0001', 'A0002']
    assert not (project / CORPUS / 'output/fr/arguments/A0002.wiki').exists()
    p2 = prepare(project)
    returned(project, p2, {'A0001': 'generated', 'A0002': 'generated'})
    assert run_import(project)['status'] == 'imported'
    assert cr.creation_resume(project, CORPUS, prepare=False)['next']['action'] == 'review_arguments'
    assert prepare(project)['status'] == 'review_required'
    m = load(project / CORPUS / 'manifest.json')
    assert m['global_status'] == 'fr_arguments_in_progress'
    assert all(p['validation']['status'] == 'pending' for p in m['pages'] if p['page_id'] in {'A0001', 'A0002'})
    assert m['batches'][0]['status'] == 'in_progress'
    # Everything except the exact outputs and their canonical metadata is untouched.
    after = snapshot(project / CORPUS)
    for name in before:
        if name not in {'manifest.json', 'data/registre_debat.json', 'output/fr/arguments/A0001.wiki', 'output/fr/arguments/A0002.wiki'}:
            assert after[name] == before[name]


def test_debate_import_requires_separate_review(project):
    set_state(project, 'exemple', 'pending')
    p = prepare(project)
    assert p['next']['action'] == 'draft_debate'
    returned(project, p, {'exemple': 'generated'}, text='{{D\u00e9bat|introduction=Texte}}')
    run_import(project)
    assert cr.creation_resume(project, CORPUS, prepare=False)['next']['action'] == 'review_debate'
    assert load(project / CORPUS / 'manifest.json')['global_status'] == 'graph_locked'


def test_unchanged_is_noop(project):
    p = prepare(project)
    before = snapshot(project / CORPUS)
    returned(project, p)
    assert run_import(project)['status'] == 'no_changes'
    assert snapshot(project / CORPUS) == before


@pytest.mark.parametrize('mutation', ['context', 'manifest', 'extra', 'missing', 'unchanged_text', 'validated', 'foreign', 'duplicate', 'empty', 'utf8', 'unknown_field'])
def test_bad_return_never_changes_corpus(project, mutation):
    p = prepare(project)
    def change(files):
        r = json.loads(files['editable/RESPONSE.json'])
        if mutation == 'context': files['context/NORMATIVE_CONTEXT.md'] += b'changed'
        if mutation == 'manifest': files['REVIEW_PACKAGE.json'] = files['REVIEW_PACKAGE.json'].replace(b'fr_creation_draft', b'graph_review')
        if mutation == 'extra': files['editable/data/sources.json'] = b'{}'
        if mutation == 'missing': files.pop('editable/output/fr/arguments/A0002.wiki')
        if mutation == 'unchanged_text': files['editable/output/fr/arguments/A0001.wiki'] = b'changed'
        if mutation == 'validated': r['pages'][0]['status'] = 'validated'
        if mutation == 'foreign': r['pages'][0]['page_id'] = 'A0003'
        if mutation == 'duplicate': r['pages'].append(r['pages'][0])
        if mutation == 'empty': r['pages'][0]['status'] = 'generated'
        if mutation == 'utf8': files['editable/output/fr/arguments/A0001.wiki'] = b'\xff'
        if mutation == 'unknown_field': r['approved'] = True
        files['editable/RESPONSE.json'] = cc._json(r)
    returned(project, p, edit_files=change)
    before = snapshot(project / CORPUS)
    with pytest.raises((ci.CreationImportError, ValueError)):
        run_import(project)
    assert snapshot(project / CORPUS) == before


@pytest.mark.parametrize('changed', ['scope.json', 'data/sources.json', 'manifest.json', 'norm', 'new_file'])
def test_stale_context_blocks(project, changed):
    p = prepare(project)
    returned(project, p, {'A0001': 'generated'})
    path = project / CORPUS / changed
    if changed == 'norm':
        path = next((project / 'norms').rglob('WIKIDEBIA_NORME_CONSOLIDEE_*.md'))
    path.write_bytes((path.read_bytes() if path.exists() else b'') + b'\n')
    before = snapshot(project / CORPUS)
    with pytest.raises(ci.CreationImportError, match='Stale'):
        run_import(project)
    assert snapshot(project / CORPUS) == before


@pytest.mark.parametrize('text', ['{{Debate|creation-date=2026-11-21}}', '{{Argument|date-cr\u00e9ation=2026-02-30}}', '{{Argument}}', '{{Argument|date-cr\u00e9ation=2026-11-21}}extra'])
def test_generated_envelope_is_checked_without_claiming_editorial_review(project, text):
    p = prepare(project)
    returned(project, p, {'A0001': 'generated'}, text=text)
    before = snapshot(project / CORPUS)
    with pytest.raises(ValueError): run_import(project)
    assert snapshot(project / CORPUS) == before


def test_existing_date_and_text_are_preserved_on_rejected_return(project):
    set_state(project, 'A0001', 'in_progress', text='Partial text')
    p = prepare(project)
    returned(project, p, {'A0001': 'generated'}, text='{{Argument|date-cr\u00e9ation=2026-11-22}}')
    before = snapshot(project / CORPUS)
    with pytest.raises(ci.CreationImportError, match='Obsolete page creation-date'): run_import(project)
    assert snapshot(project / CORPUS) == before


def test_failed_page_can_return_to_draft_not_validation(project):
    set_state(project, 'A0001', 'failed')
    p = prepare(project)
    returned(project, p, {'A0001': 'generated'})
    run_import(project)
    assert cr.creation_resume(project, CORPUS, prepare=False)['counts']['awaiting_review'] == 1


@pytest.mark.parametrize('which', ['page', 'batch', 'lots'])
def test_existing_mirrors_updated_coherently(project, which):
    base = project / CORPUS
    m = load(base / 'manifest.json')
    if which == 'page':
        path = base / 'manifests/pages/fr_A0001.json'; put(path, m['pages'][1])
    elif which == 'batch':
        path = base / 'manifests/batches/FR-A-001.json'; put(path, m['batches'][0])
    else:
        path = base / 'data/lots_fr.json'; put(path, {'batches': m['batches']})
    p = prepare(project); returned(project, p, {'A0001': 'generated'}); run_import(project)
    updated = load(base / 'manifest.json')
    assert load(path) == (updated['pages'][1] if which == 'page' else updated['batches'][0] if which == 'batch' else {'batches': updated['batches']})


@pytest.mark.parametrize('stop', ['before_move', 'after_backup', 'after_install'])
def test_crash_recovery_in_a_fresh_process(project, stop):
    p = prepare(project)
    returned(project, p, {'A0001': 'generated'})
    before = snapshot(project / CORPUS)
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
 if sys.argv[3] == 'before_move' and calls == 1: os._exit(74)
 real(a,b)
 if (sys.argv[3] == 'after_backup' and calls == 1) or (sys.argv[3] == 'after_install' and calls == 2): os._exit(74)
ci.os.rename = rename
ci.import_package(Path(sys.argv[2]), 'corpus/exemple')
'''
    scripts = Path(ci.__file__).parent
    proc = subprocess.run([sys.executable, '-c', code, str(scripts), str(project), stop], capture_output=True, text=True)
    assert proc.returncode == 74, proc.stderr
    with pytest.raises(ci.CreationImportError, match='Interrupted'):
        cr.creation_resume(project, CORPUS, prepare=False)
    r = run_import(project, recover=True)
    assert r['status'] == ('imported' if stop == 'after_install' else 'rolled_back')
    if stop != 'after_install':
        assert snapshot(project / CORPUS) == before
        assert run_import(project)['status'] == 'imported'
    else:
        assert run_import(project)['status'] == 'already_imported'
    assert cr.creation_resume(project, CORPUS, prepare=False)['counts']['awaiting_review'] == 1


def test_concurrent_change_in_backup_is_never_destroyed(project, monkeypatch):
    p = prepare(project); returned(project, p, {'A0001': 'generated'})
    real = ci.os.rename
    def rename(a, b):
        real(a, b)
        if Path(b).name == 'before': (Path(b) / 'concurrent.txt').write_text('Keep human text')
    monkeypatch.setattr(ci.os, 'rename', rename)
    with pytest.raises(ci.CreationImportError, match='Concurrent'):
        run_import(project)
    with pytest.raises(ci.CreationImportError, match='Concurrent'):
        run_import(project, recover=True)
    backup = next((project / '.state/creation-import').glob('*/*/before/concurrent.txt'))
    assert backup.read_text() == 'Keep human text'


def test_old_receipt_does_not_replay_over_later_progress(project):
    p = prepare(project); returned(project, p, {'A0001': 'generated'})
    run_import(project)
    set_state(project, 'A0001', 'validated')
    before = snapshot(project / CORPUS)
    r = run_import(project)
    assert r['status'] == 'already_imported' and r['current_state_matches_receipt'] is False
    assert snapshot(project / CORPUS) == before


def test_second_different_return_is_rejected(project):
    p = prepare(project); returned(project, p, {'A0001': 'generated'}); run_import(project)
    returned(project, p, {'A0001': 'partial'})
    with pytest.raises(ci.CreationImportError, match='already consumed'): run_import(project)


def test_two_packages_need_selection(project):
    p = prepare(project)
    returned(project, p, {'A0001': 'generated'})
    returned(project, p, {'A0002': 'partial'}, filename='other.zip')
    with pytest.raises(ci.CreationImportError, match='exactly one'): run_import(project)
    assert run_import(project, archive='incoming/returned.zip')['pages_saved'] == ['A0001']


@pytest.mark.parametrize('name', ['../oops', '/tmp/oops', 'editable/../oops', './editable/oops', 'editable//oops', 'private/password', 'editable\\oops'])
def test_dangerous_zip_entries_rejected(project, name):
    p = prepare(project)
    returned(project, p, edit_files=lambda f: f.update({name: b'bad'}))
    with pytest.raises(ci.CreationImportError): run_import(project)


@pytest.mark.parametrize('kind', ['symlink', 'duplicate', 'large'])
def test_archive_safety_limits(project, kind):
    p = prepare(project); path = returned(project, p)
    with zipfile.ZipFile(path, 'a', compression=zipfile.ZIP_DEFLATED) as z:
        if kind == 'symlink':
            info=zipfile.ZipInfo('link'); info.create_system=3; info.external_attr=0o120777 << 16
            z.writestr(info, '/etc/passwd')
        elif kind == 'duplicate':
            with pytest.warns(UserWarning): z.writestr('editable/RESPONSE.json', b'{}')
        else: z.writestr('large', b'x' * (ci.FILE_LIMIT+1))
    with pytest.raises(ci.CreationImportError): run_import(project)


def test_cooperative_lock_blocks_second_import(project):
    _, control = ci._locations(project, CORPUS)
    with ci._lock(project, control):
        with pytest.raises(ci.CreationImportError, match='Another'): prepare(project)


def test_cli_round_trip_and_errors(project):
    args = ['--root', str(project)]
    assert manager.main(args + ['creation-package', '--corpus', CORPUS, '--max-pages', '1']) == 0
    p = prepare(project, max_pages=1); returned(project, p, {'A0001':'generated'})
    assert manager.main(args + ['creation-import', '--corpus', CORPUS]) == 0
    assert manager.main(args + ['creation-import', '--corpus', CORPUS, '--recover']) == 0
    assert manager.main(args + ['creation-import', '--corpus', CORPUS, '--archive', '../bad.zip']) == 2


def test_packet_matches_existing_package_schema(project):
    import jsonschema
    p=prepare(project)
    with zipfile.ZipFile(project/p['package_path']) as z:
        doc=json.loads(z.read('REVIEW_PACKAGE.json'))
    path=Path(ci.__file__).resolve().parents[2]/'validator/src/wikidebia_validator/schemas/chatgpt_review_package.schema.json'
    jsonschema.validate(doc, load(path))


def test_english_batch_mirrors_are_not_replaced(project):
    def change(m, r):
        b = copy.deepcopy(r['batches'][0]); b.update(id='EN-A-001', language='en', status='planned')
        r['batches'].append(b)
        other=copy.deepcopy(b); other['work']['conversation_name']='Separate English provenance'
        m['batches'].append(other)
    edit(project, change)
    before=load(project/CORPUS/'manifest.json')['batches'][-1]
    p=prepare(project); returned(project,p,{'A0001':'partial'}); run_import(project)
    assert load(project/CORPUS/'manifest.json')['batches'][-1] == before


@pytest.mark.parametrize('kind', ['symlink_file', 'symlink_dir', 'hardlink', 'fifo'])
def test_unsafe_corpus_is_rejected(project, kind):
    import os
    base=project/CORPUS
    if kind == 'symlink_file': (base/'bad').symlink_to(base/'scope.json')
    if kind == 'symlink_dir': (base/'bad').symlink_to(base/'data', target_is_directory=True)
    if kind == 'hardlink': os.link(base/'scope.json', base/'bad')
    if kind == 'fifo': os.mkfifo(base/'bad')
    with pytest.raises((ci.CreationImportError, cc.CreationContextError)): prepare(project)


def test_altered_local_request_and_archive_are_not_trusted(project):
    p=prepare(project)
    returned(project,p,{'A0001':'generated'})
    _,control=ci._locations(project,CORPUS)
    req=next(control.glob('*.json'))
    value=load(req);value['before']='0'*64;put(req,value)
    with pytest.raises(ci.CreationImportError,match='checksum'): run_import(project)
    with pytest.raises(ci.CreationImportError,match='checksum'): prepare(project)


def test_altered_outgoing_archive_not_reused(project):
    p=prepare(project)
    (project/p['package_path']).write_bytes(b'not original')
    with pytest.raises(ci.CreationImportError,match='archive changed'): prepare(project)


def test_partial_draft_can_be_incomplete_wikicode(project):
    p=prepare(project)
    returned(project,p,{'A0001':'partial'},text='{{Argument|r\u00e9sum\u00e9=Debut incomplet')
    run_import(project)
    assert cr.creation_resume(project,CORPUS,prepare=False)['counts']['draft_in_progress']==1


def test_error_during_staging_preserves_every_canonical_file(project,monkeypatch):
    p=prepare(project);returned(project,p,{'A0001':'generated','A0002':'generated'})
    before=snapshot(project/CORPUS)
    original=ci._apply_drafts
    def fail(stage,changes,stamp):
        original(stage,changes,stamp)
        raise OSError('disk error before installation')
    monkeypatch.setattr(ci,'_apply_drafts',fail)
    with pytest.raises(OSError):run_import(project)
    assert snapshot(project/CORPUS)==before
    assert run_import(project,recover=True)['status']=='nothing_to_recover'


def test_small_return_after_long_draft_is_not_silently_adopted_as_unchanged(project):
    set_state(project,'A0001','in_progress',text='Important existing text '*100)
    p=prepare(project)
    returned(project,p,edit_files=lambda f:f.update({'editable/output/fr/arguments/A0001.wiki':b''}))
    before=snapshot(project/CORPUS)
    with pytest.raises(ci.CreationImportError,match='declared unchanged'):run_import(project)
    assert snapshot(project/CORPUS)==before


def test_foreign_corpus_is_not_selected(project):
    p=prepare(project); returned(project,p,{'A0001':'generated'})
    with pytest.raises(ci.CreationImportError,match='exactly one'):
        ci.import_package(project,'corpus/other')


def test_mirror_drift_before_preparation_blocks_installation(project):
    p=load(project/CORPUS/'manifest.json')['pages'][1]
    p['canonical_title']='Unreviewed title'
    put(project/CORPUS/'manifests/pages/A0001.json',p)
    p=prepare(project);returned(project,p,{'A0001':'generated'})
    before=snapshot(project/CORPUS)
    with pytest.raises(ci.CreationImportError,match='manifest differs'):run_import(project)
    assert snapshot(project/CORPUS)==before


def test_safe_zip_directory_entries_are_accepted(project):
    p=prepare(project); path=returned(project,p,{'A0001':'partial'})
    with zipfile.ZipFile(path,'a') as z:
        z.writestr('editable/', b''); z.writestr('context/', b'')
    assert run_import(project)['status']=='imported'


def test_partial_dates_must_not_be_reconciled_silently(project):
    set_state(project,'A0001','in_progress')
    def change(m,r):r['graph']['nodes'][0]['pages']['fr']['generation']['creation_date']='2026-11-20'
    edit(project,change)
    p=prepare(project);returned(project,p,{'A0001':'generated'})
    with pytest.raises(ci.CreationImportError,match='Contradictory recorded creation dates'):run_import(project)
