from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys

import pytest

import wikidebia_creation_context as cc
import wikidebia_creation_resume as cr
import wikidebia_manage as manager

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "validator/src"))
from wikidebia_validator.graph import structural_sha256


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(cc._json(value))


def load(path):
    return json.loads(path.read_bytes())


def snapshot(path):
    return {p.relative_to(path).as_posix(): p.read_bytes() for p in path.rglob('*') if p.is_file()}


def edit(root, callback):
    corpus = root / 'corpus/exemple'
    m = load(corpus / 'manifest.json')
    r = load(corpus / 'data/registre_debat.json')
    callback(m, r)
    put(corpus / 'manifest.json', m)
    put(corpus / 'data/registre_debat.json', r)


def set_state(root, key, state, *, text=None):
    corpus = root / 'corpus/exemple'
    def change(m, r):
        p = next(p for p in m['pages'] if p['page_id'] == key)
        rec = r['debate']['pages']['fr'] if key == 'exemple' else next(n for n in r['graph']['nodes'] if n['id'] == key)['pages']['fr']
        present = state in {'generated', 'validated', 'in_progress', 'failed'}
        path = corpus / p['file_path']
        if present:
            raw = (text or '{{Argument|resume=An explicit draft}}').encode()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            sha = hashlib.sha256(raw).hexdigest()
        else:
            path.unlink(missing_ok=True)
            sha = None
        p.update(status={'pending': 'planned', 'in_progress': 'assigned'}.get(state, state), sha256=sha,
                 creation_date='2026-11-21' if present else None)
        p['validation'] = {'status': 'passed' if state == 'validated' else ('failed' if state == 'failed' else 'pending'),
                           'report_path': f'reports/{key}_fr.txt' if state == 'validated' else None,
                           'validated_at': '2026-11-21T00:00:00Z' if state == 'validated' else None}
        rec['generation'].update(status=state, creation_date=p['creation_date'],
                                 generated_at='2026-11-21T00:00:00Z' if present else None,
                                 validated_at=p['validation']['validated_at'])
        rec['file'].update(sha256=sha, status='validated' if state == 'validated' else ('present' if present else 'absent'))
        if state == 'validated':
            (corpus / f'reports/{key}_fr.txt').write_text('Recorded validation; not a new certificate.\n')
    edit(root, change)


def close_batch(root, index=0):
    corpus = root / 'corpus/exemple'
    def change(m, r):
        b = r['batches'][index]
        b['status'] = 'validated'
        aggregate = corpus / b['outputs']['aggregate_path']
        aggregate.parent.mkdir(parents=True, exist_ok=True)
        aggregate.write_text('Recorded aggregate\n')
        b['outputs']['aggregate_sha256'] = cc._sha(aggregate.read_bytes())
        (corpus / b['outputs']['report_path']).write_text('Recorded batch review\n')
        m['batches'] = copy.deepcopy(r['batches'])
    edit(root, change)


@pytest.fixture
def project(tmp_path):
    for rel in ['norms/VERSIONS.json', 'kit/configs/creation_context_sections.json']:
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, dest)
    version = load(ROOT / 'norms/VERSIONS.json')['norm']
    rel = f'norms/normative_reference/01_normes/WIKIDEBIA_NORME_CONSOLIDEE_{version}.md'
    (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / rel, tmp_path / rel)
    corpus = tmp_path / 'corpus/exemple'
    shutil.copytree(ROOT / 'validator/examples/valid_fr_package', corpus)
    m = load(corpus / 'manifest.json')
    r = load(corpus / 'data/registre_debat.json')
    m['global_status'] = 'fr_arguments_in_progress'
    m['translation_status'] = {'en': 'deferred'}
    # Two real schema-shaped nodes, plus a second independent batch.
    for i in (3, 4):
        key = f'A{i:04d}'
        n = copy.deepcopy(r['graph']['nodes'][i - 3])
        n['id'] = key
        n['fr']['canonical_title'] = f'Reason {i} is a distinct proposition'
        n['fr']['displayed_title'] = n['fr']['canonical_title']
        n['pages']['fr']['file']['path'] = f'output/fr/arguments/{key}.wiki'
        n['pages']['fr']['generation']['assigned_batch_id'] = 'FR-A-002'
        n['pages']['en']['file']['path'] = f'output/en/arguments/{key}.wiki'
        r['graph']['nodes'].append(n)
        o = copy.deepcopy(r['graph']['occurrences'][i-3])
        o.update(id=f'O{i:05d}', node_id=key, order=i)
        r['graph']['occurrences'].append(o)
        p = copy.deepcopy(m['pages'][i-2])
        p.update(page_id=key, canonical_title=n['fr']['canonical_title'], batch_id='FR-A-002',
                 file_path=f'output/fr/arguments/{key}.wiki')
        m['pages'].append(p)
    r['graph']['lifecycle']['structural_sha256'] = structural_sha256(r)
    b = copy.deepcopy(r['batches'][0])
    b.update(id='FR-A-002', node_ids=['A0003', 'A0004'], root_node_ids=['A0003', 'A0004'])
    b['outputs'].update(aggregate_path='output/fr/aggregates/batch_002.wiki', report_path='reports/batch002.txt')
    r['batches'].append(b)
    for b in r['batches']:
        b['status'] = 'in_progress'
    m['batches'] = copy.deepcopy(r['batches'])
    for p in m['pages']:
        p['page_origin'] = 'new'
    put(corpus/'manifest.json', m)
    put(corpus/'data/registre_debat.json', r)
    # Optional mirror must match the canonical registry, never a second queue.
    (corpus/'data/lots_fr.json').unlink(missing_ok=True)
    set_state(tmp_path, 'exemple', 'validated', text='{{Debat|introduction=Test}}')
    for i in range(1, 5):
        set_state(tmp_path, f'A{i:04d}', 'pending')
    return tmp_path


def result(project, **kw):
    return cr.creation_resume(project, 'corpus/exemple', **kw)


def test_next_is_deterministic_and_never_mutates_corpus(project, monkeypatch):
    before = snapshot(project/'corpus')
    def forbidden(*args, **kwargs):
        raise AssertionError('No network or subprocess is needed')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(subprocess, 'run', forbidden)
    first = result(project)
    assert first['next']['page_ids'] == ['A0001','A0002']
    assert first['next']['action'] == 'draft_arguments'
    assert first['context']['validation_performed'] is False
    assert first['publication_authorized'] is False
    second = result(project)
    assert second['status'] == 'reused'
    assert second['queue_sha256'] == first['queue_sha256']
    assert snapshot(project/'corpus') == before
    assert first['actual_billed_tokens'] is None
    assert first['actual_codex_cloud_credits'] is None
    assert str(project) not in (project/first['queue_path']/'QUEUE.json').read_text()


def test_status_is_read_only_even_without_state_directory(project):
    before = snapshot(project)
    report = result(project, prepare=False)
    assert report['status'] == 'inspected'
    assert 'context' not in report
    assert snapshot(project) == before
    assert not (project/'.state').exists()


def test_resume_after_saved_page_selects_only_remaining_then_review(project):
    first = result(project, max_pages=1)
    set_state(project,'A0001','generated')
    second = result(project,max_pages=1)
    assert second['next']['page_ids'] == ['A0002']
    assert second['queue_sha256'] != first['queue_sha256']
    context=load(project/second['context']['context_path']/'CORPUS_CONTEXT.json')
    assert context['selected_node_ids'] == ['A0002']
    assert 'A0001' not in context['page_texts']
    set_state(project,'A0002','generated')
    review = result(project)
    assert review['next']['action'] == 'review_arguments'
    assert review['next']['batch_id'] == 'FR-A-001'
    assert review['next']['page_ids'] == ['A0001','A0002']
    # The later batch is not opened merely because all drafts exist.
    assert 'A0003' not in review['next']['page_ids']


def test_partial_draft_is_resumed_before_fresh_pages(project):
    set_state(project,'A0002','in_progress',text='A partial but tracked draft')
    r=result(project,max_pages=1)
    assert r['next']['page_ids'] == ['A0002']
    ctx=load(project/r['context']['context_path']/'CORPUS_CONTEXT.json')
    assert ctx['page_texts']['A0002']['text'] == 'A partial but tracked draft'
    assert r['counts']['draft_in_progress'] == 1


def test_failed_page_is_correction_not_completed(project):
    set_state(project,'A0002','failed')
    r=result(project,max_pages=1)
    assert r['next']['page_ids'] == ['A0002']
    assert r['counts']['needs_correction'] == 1


def test_next_batch_requires_page_and_batch_closure(project):
    for key in ('A0001','A0002'): set_state(project,key,'validated')
    assert result(project)['next']['action'] == 'batch_review_required'
    close_batch(project)
    r=result(project)
    assert r['next']['batch_id'] == 'FR-A-002'
    assert r['next']['page_ids'] == ['A0003','A0004']
    for key in ('A0003','A0004'): set_state(project,key,'validated')
    close_batch(project,1)
    r=result(project)
    assert r['next']['action'] == 'global_review_required'
    assert r['context'] is None
    assert not r['publication_authorized']
    assert r['counts']['recorded_validated'] == 5


def test_no_duplicate_task_for_multiple_occurrences(project):
    def change(m,r):
        o=copy.deepcopy(r['graph']['occurrences'][0]);o.update(id='O00005',occurrence_role='secondary',order=5,render_children=False)
        r['graph']['occurrences'].append(o)
        r['graph']['lifecycle']['structural_sha256']=structural_sha256(r)
    edit(project,change)
    r=result(project)
    assert r['argument_count']==4
    assert r['next']['page_ids']==['A0001','A0002']
    context=load(project/r['context']['context_path']/'CORPUS_CONTEXT.json')
    assert len(context['graph_overview']['occurrences'])==5


def test_explicit_batch_dependency_is_read_but_never_assigned(project):
    for key in ('A0001','A0002'): set_state(project,key,'validated')
    close_batch(project)
    def change(m,r):
        r['batches'][1]['dependency_node_ids']=['A0001']
        m['batches']=copy.deepcopy(r['batches'])
    edit(project,change)
    r=result(project,max_pages=1)
    assert r['next']['page_ids']==['A0003']
    ctx=load(project/r['context']['context_path']/'CORPUS_CONTEXT.json')
    assert ctx['selected_node_ids']==['A0003']
    assert ctx['dependency_node_ids']==['A0001']
    assert 'A0001' in ctx['page_texts']


def test_future_unvalidated_dependency_is_explicit_blocker(project):
    def change(m,r):
        r['batches'][0]['dependency_node_ids']=['A0004'];m['batches']=copy.deepcopy(r['batches'])
    edit(project,change)
    r=result(project)
    assert r['next']['action']=='dependency_review_required'
    assert r['next']['dependency_node_ids']==['A0004']
    assert r['context'] is None


@pytest.mark.parametrize('state,action',[('pending','draft_debate'),('generated','review_debate')])
def test_debate_precedes_arguments(project,state,action):
    set_state(project,'exemple',state)
    r=result(project)
    assert r['next']['action']==action
    assert r['next']['page_ids']==['exemple']
    assert r['context']['stage']=='debat-fr'


@pytest.mark.parametrize('bad',[0,21,-1,True,'1'])
def test_invalid_limit(project,bad):
    with pytest.raises(cr.CreationResumeError): result(project,max_pages=bad)


@pytest.mark.parametrize('kind',[
    'missing_file','tampered_file','untracked_draft','path_collision','registry_path_drift',
    'registry_sha_drift','generation_drift','false_validated','missing_report','empty_report',
    'wrong_owner','unknown_page_state','obsolete_page','historical_page','remote_page',
    'duplicate_batch_owner','missing_batch_owner','batch_mirror_drift','unknown_batch_state',
    'false_batch_validation','source_identity','unknown_registry','unlocked_graph','hash_drift',
    'published_corpus','unknown_corpus_state','not_deferred','missing_origin',
])
def test_unsafe_or_inconsistent_state_fails_without_writing(project,kind):
    set_state(project,'A0001','generated')
    corpus=project/'corpus/exemple'
    m=load(corpus/'manifest.json');r=load(corpus/'data/registre_debat.json')
    p=m['pages'][1];rec=r['graph']['nodes'][0]['pages']['fr']
    if kind=='missing_file': (corpus/p['file_path']).unlink()
    elif kind=='tampered_file': (corpus/p['file_path']).write_text('Changed')
    elif kind=='untracked_draft': (corpus/m['pages'][2]['file_path']).write_text('Never overwrite me')
    elif kind=='path_collision': m['pages'][2]['file_path']=p['file_path']
    elif kind=='registry_path_drift': rec['file']['path']='output/fr/other.wiki'
    elif kind=='registry_sha_drift': rec['file']['sha256']='0'*64
    elif kind=='generation_drift': rec['generation']['status']='pending'
    elif kind=='false_validated': p['status']='validated'
    elif kind in {'missing_report','empty_report'}:
        path=corpus/'reports/exemple_fr.txt'
        path.unlink() if kind=='missing_report' else path.write_text('')
    elif kind=='wrong_owner': rec['generation']['assigned_batch_id']='FR-A-002'
    elif kind=='unknown_page_state': p['status']='magic_completed'
    elif kind=='obsolete_page': p['status']='obsolete'
    elif kind=='historical_page': p['page_origin']='preexisting'
    elif kind=='remote_page': p['wiki']['remote_revision_id']=42
    elif kind=='duplicate_batch_owner': r['batches'][1]['node_ids'].append('A0001');m['batches']=copy.deepcopy(r['batches'])
    elif kind=='missing_batch_owner': r['batches'][0]['node_ids'].remove('A0001');m['batches']=copy.deepcopy(r['batches'])
    elif kind=='batch_mirror_drift': m['batches'][0]['status']='planned'
    elif kind=='unknown_batch_state': r['batches'][0]['status']='magic';m['batches']=copy.deepcopy(r['batches'])
    elif kind=='false_batch_validation': r['batches'][0]['status']='validated';m['batches']=copy.deepcopy(r['batches'])
    elif kind=='source_identity':
        s=load(corpus/'data/sources.json');s['debate_id']='foreign';put(corpus/'data/sources.json',s)
    elif kind=='unknown_registry': r['schema']['registry_version']='99.0'
    elif kind=='unlocked_graph': r['graph']['lifecycle']['status']='draft'
    elif kind=='hash_drift': r['graph']['nodes'][0]['fr']['canonical_title']='Another thesis'
    elif kind=='published_corpus': m['global_status']='published'
    elif kind=='unknown_corpus_state': m['global_status']='magic'
    elif kind=='not_deferred': m['translation_status']['en']='ready'
    elif kind=='missing_origin': p.pop('page_origin')
    put(corpus/'manifest.json',m);put(corpus/'data/registre_debat.json',r)
    before=snapshot(corpus)
    with pytest.raises((cr.CreationResumeError,cc.CreationContextError)): result(project)
    assert snapshot(corpus)==before
    assert not (project/'.state').exists()


@pytest.mark.parametrize('kind',['imported','page_symlink','core_symlink','output_symlink','traversal'])
def test_paths_and_provenance(project,kind):
    corpus=project/'corpus/exemple'
    if kind=='imported': put(corpus/'data/import_provenance.json',{})
    elif kind=='page_symlink':
        (corpus/'output/fr/arguments/A0001.wiki').symlink_to(corpus/'manifest.json')
    elif kind=='core_symlink':
        p=corpus/'data/sources.json';raw=p.read_bytes();p.unlink();(project/'source.json').write_bytes(raw);p.symlink_to(project/'source.json')
    elif kind=='output_symlink': (project/'.state').symlink_to(project/'corpus')
    else:
        edit(project,lambda m,r:m['core_files'].update(scope='../secret.json'))
    with pytest.raises(cc.CreationContextError): result(project)


@pytest.mark.parametrize('kind',['queue_edit','extra_file','queue_symlink'])
def test_queue_is_not_a_mutable_progress_database(project,kind):
    r=result(project);path=project/r['queue_path']
    if kind=='queue_edit': (path/'QUEUE.json').write_text('{}')
    elif kind=='extra_file': (path/'finished.json').write_text('{}')
    else:
        p=path/'NEXT.md';raw=p.read_bytes();p.unlink();(project/'other.md').write_bytes(raw);p.symlink_to(project/'other.md')
    before=snapshot(project/'corpus')
    with pytest.raises(cc.CreationContextError): result(project)
    assert snapshot(project/'corpus')==before


def test_missing_page_appearing_during_context_build_fails(project,monkeypatch):
    original=cr.build_creation_context
    def racing(*args,**kwargs):
        value=original(*args,**kwargs)
        (project/'corpus/exemple/output/fr/arguments/A0001.wiki').write_text('Concurrent draft')
        return value
    monkeypatch.setattr(cr,'build_creation_context',racing)
    with pytest.raises(cr.CreationResumeError,match='appeared'): result(project)
    assert not (project/'.state/creation-resume').exists()


def test_registry_changing_during_build_fails(project,monkeypatch):
    original=cr.build_creation_context
    def racing(*args,**kwargs):
        value=original(*args,**kwargs)
        edit(project,lambda m,r:r['batches'][0].update(status='planned'))
        return value
    monkeypatch.setattr(cr,'build_creation_context',racing)
    with pytest.raises(cc.CreationContextError,match='changed'): result(project)
    assert not (project/'.state/creation-resume').exists()


def test_changed_sources_invalidate_saved_plan(project):
    first=result(project)
    source=project/'corpus/exemple/data/sources.json'
    s=load(source);s['updated_at']='2026-11-21T01:00:00Z';put(source,s)
    assert result(project)['queue_sha256']!=first['queue_sha256']


@pytest.mark.parametrize('command',['creation-status','creation-next'])
def test_real_manager_cli(project,command,capsys):
    assert manager.main(['--root',str(project),command,'--corpus','corpus/exemple','--max-pages','1'])==0
    r=json.loads(capsys.readouterr().out)
    assert r['next']['page_ids']==['A0001']
    assert r['status']==('inspected' if command=='creation-status' else 'prepared')


def test_cli_failure_is_nonzero_and_no_traceback(project,capsys):
    assert manager.main(['--root',str(project),'creation-next','--corpus','private/secret'])==2
    assert 'BLOQUEE' in capsys.readouterr().err


def test_released_local_batch_is_not_reopened(project):
    for key in ('A0001','A0002'): set_state(project,key,'validated')
    close_batch(project)
    def change(m,r):
        r['batches'][0]['status']='released';m['batches']=copy.deepcopy(r['batches'])
    edit(project,change)
    assert result(project)['next']['batch_id']=='FR-A-002'


def test_tampered_closed_batch_aggregate_is_blocked(project):
    for key in ('A0001','A0002'): set_state(project,key,'validated')
    close_batch(project)
    r=load(project/'corpus/exemple/data/registre_debat.json')
    (project/'corpus/exemple'/r['batches'][0]['outputs']['aggregate_path']).write_text('Changed')
    with pytest.raises(cr.CreationResumeError,match='aggregate'): result(project)


def test_partial_queue_creation_is_not_mistaken_for_complete(project):
    r=result(project)
    (project/r['queue_path']/'NEXT.md').unlink()
    with pytest.raises(cr.CreationResumeError,match='altered'): result(project)


def test_explicit_dependencies_must_exist_and_not_be_selected(project):
    for deps in (['A9999'],['A0001'],['A0002','A0002']):
        with pytest.raises(cc.CreationContextError):
            cc.build_creation_context(project,'arguments-fr',corpus_path='corpus/exemple',
                                      node_ids=['A0001'],dependency_node_ids=deps)


def test_large_resumption_does_not_expose_completed_unrelated_texts(project):
    corpus=project/'corpus/exemple'
    m=load(corpus/'manifest.json');r=load(corpus/'data/registre_debat.json')
    # 200 pages in a single canonical batch; no extra completion state.
    for i in range(5,201):
        key=f'A{i:04d}'
        n=copy.deepcopy(r['graph']['nodes'][0]);n['id']=key
        n['fr'].update(canonical_title=f'Independent reason {i}',displayed_title=f'Reason {i}')
        n['pages']['fr']['file']['path']=f'output/fr/arguments/{key}.wiki'
        r['graph']['nodes'].append(n)
        o=copy.deepcopy(r['graph']['occurrences'][0]);o.update(id=f'O{i:05d}',node_id=key,order=i)
        r['graph']['occurrences'].append(o)
        p=copy.deepcopy(m['pages'][1]);p.update(page_id=key,canonical_title=n['fr']['canonical_title'],file_path=n['pages']['fr']['file']['path'])
        m['pages'].append(p)
    keys=[n['id'] for n in r['graph']['nodes']]
    r['batches']=r['batches'][:1];r['batches'][0]['node_ids']=keys
    m['batches']=copy.deepcopy(r['batches'])
    for i,(n,p) in enumerate(zip(r['graph']['nodes'],m['pages'][1:]),1):
        rec=n['pages']['fr'];rec['generation']['assigned_batch_id']='FR-A-001';p['batch_id']='FR-A-001'
        if i<=198:
            raw=(f'UNRELATED_COMPLETED_TEXT_{i} ' * 300).encode()
            sha=cc._sha(raw);(corpus/p['file_path']).write_bytes(raw)
            p.update(status='generated',sha256=sha,creation_date='2026-11-21')
            rec['file'].update(status='present',sha256=sha)
            rec['generation'].update(status='generated',generated_at='2026-11-21T00:00:00Z',creation_date='2026-11-21')
    r['graph']['lifecycle']['structural_sha256']=structural_sha256(r)
    put(corpus/'manifest.json',m);put(corpus/'data/registre_debat.json',r)
    value=result(project)
    assert value['counts']['awaiting_review']==198
    assert value['next']['page_ids']==['A0199','A0200']
    ctx=load(project/value['context']['context_path']/'CORPUS_CONTEXT.json')
    assert len(ctx['graph_overview']['nodes'])==200
    assert not ctx['page_texts']
    assert 'UNRELATED_COMPLETED_TEXT' not in json.dumps(ctx)
    assert len(json.dumps(value).encode())<5000


def test_subprocess_resume_uses_only_persisted_canonical_inputs(project):
    command=[sys.executable,str(ROOT/'kit/scripts/wikidebia_creation_resume.py'),
             '--project-root',str(project),'--corpus','corpus/exemple','--max-pages','1']
    first=subprocess.run(command,capture_output=True,text=True,check=True)
    one=json.loads(first.stdout)
    assert one['next']['page_ids']==['A0001']
    two=json.loads(subprocess.run(command,capture_output=True,text=True,check=True).stdout)
    assert two['status']=='reused'
    set_state(project,'A0001','generated')
    three=json.loads(subprocess.run(command,capture_output=True,text=True,check=True).stdout)
    assert three['next']['page_ids']==['A0002']
    assert one['queue_sha256']!=three['queue_sha256']
