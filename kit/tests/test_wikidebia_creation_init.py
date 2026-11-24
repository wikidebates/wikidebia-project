from __future__ import annotations

import copy
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'kit/scripts'))
import wikidebia_creation_init as ci
import wikidebia_creation_import as di
import wikidebia_creation_resume as cr
import wikidebia_manage as manager


def load(path):
    return json.loads(path.read_bytes())


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(ci._json(value))


def snapshot(folder):
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob('*') if p.is_file()}


def plan_data():
    return {'schema': ci.PLAN_SCHEMA, 'debate_id': 'creation_exemple',
        'scope': {'canonical_title_fr': 'Faut-il adopter la mesure X ?',
                  'proposition_fr': 'La mesure X doit etre adoptee', 'scope_summary_fr': 'Comparer les effets collectifs et individuels de la mesure X.',
                  'jurisdiction': None, 'timeframe': None, 'included_topics': ['Effets de X'],
                  'excluded_topics': [], 'residual_ambiguities': [], 'editorial_constraints': []},
        'nodes': [{'id': f'A{i:04d}', 'canonical_title_fr': title, 'displayed_title_fr': title,
                   'rubriques': ['Politique'], 'keywords': ['mesure', 'politique']} for i, title in enumerate([
            'La mesure X produit un avantage collectif', 'La mesure X menace les libertes',
            'La mesure X change les incitations', 'La mesure X modifie les sanctions'], 1)],
        'placements': [
            {'occurrence_id': 'O00001', 'node_id': 'A0001', 'parent_occurrence_id': None, 'relation': None, 'branch': 'pro', 'order': 1, 'occurrence_role': 'primary'},
            {'occurrence_id': 'O00002', 'node_id': 'A0002', 'parent_occurrence_id': None, 'relation': None, 'branch': 'con', 'order': 1, 'occurrence_role': 'primary'},
            {'occurrence_id': 'O00003', 'node_id': 'A0003', 'parent_occurrence_id': 'O00001', 'relation': 'justification', 'branch': None, 'order': 1, 'occurrence_role': 'primary'},
            {'occurrence_id': 'O00004', 'node_id': 'A0004', 'parent_occurrence_id': 'O00003', 'relation': 'objection', 'branch': None, 'order': 1, 'occurrence_role': 'primary'},
            {'occurrence_id': 'O00005', 'node_id': 'A0003', 'parent_occurrence_id': 'O00002', 'relation': 'justification', 'branch': None, 'order': 1, 'occurrence_role': 'secondary'}],
        'batches': [{'node_ids': ['A0001', 'A0002'], 'dependency_node_ids': []},
                    {'node_ids': ['A0003', 'A0004'], 'dependency_node_ids': ['A0001']}]}


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
    put(tmp_path / 'incoming/plan.json', plan_data())
    return tmp_path


def prepared(project):
    result = ci.prepare(project, 'incoming/plan.json')
    files = ci._zip_files((project / result['package_path']).read_bytes())
    return result, files


def approved(files):
    # Synthetic approvals exercise the contract; never certify real content.
    review = ci.parse(files[ci.REVIEW_PATH])
    review.update(decision='approved', reviewer='Synthetic reviewer', reviewed_at=ci._now(),
                  scope_rationale='Synthetic scope review tied to the exact question and exclusions.')
    review['attestations'] = {k: True for k in review['attestations']}
    for i, row in enumerate(review['titles']):
        row.update(canonical_autonomy=True, complete_displayed_proposition=True, semantic_equivalence=True,
                   rationale=f'Synthetic title review {i}: the declared proposition remains identical.')
    for row in review['placement_review']['entries']:
        row.update(placement_status='approved', direct_fit=True,
                   rationale='Synthetic placement review: ' + row['occurrence_id'] + ' directly targets its declared parent.')
        if 'main_argument_review' in row:
            m = row['main_argument_review']
            for k in m:
                m[k] = k in {'direct_answer_to_debate', 'autonomous_without_parent', 'organizes_distinct_argument_family'}
        else:
            row['subordinate_review'] = {k: True for k in row['subordinate_review']}
    files[ci.REVIEW_PATH] = ci._json(review)
    return files


def returned(project, files, name='return.zip'):
    path = project / 'incoming' / name
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for key, value in files.items():
            archive.writestr(key, value)
    return path.relative_to(project).as_posix()


def initialized(project):
    _, files = prepared(project)
    return ci.initialize(project, returned(project, approved(files)))


def test_prepare_and_initialize_real_validation_and_draft_path(project):
    result, files = prepared(project)
    assert not (project / 'corpus/creation_exemple').exists()
    assert ci.parse(files[ci.REVIEW_PATH])['decision'] == 'pending'
    first = ci.initialize(project, returned(project, approved(files)))
    assert first['status'] == 'initialized', first
    corpus = project / first['corpus_path']
    m, r = load(corpus/'manifest.json'), load(corpus/'data/registre_debat.json')
    assert m['global_status'] == 'graph_locked'
    assert m['translation_status'] == {'en': 'deferred'}
    assert all(p['status'] == 'planned' and p['validation']['status'] == 'pending' and p['page_origin'] == 'new' for p in m['pages'])
    assert all('creation_date' not in p and p['sha256'] is None for p in m['pages'])
    assert not list(corpus.rglob('*.wiki'))
    assert not (corpus/'imports').exists()
    assert r['graph']['derived_counts']['distinct_nodes'] == 4
    assert r['graph']['derived_counts']['total_occurrences'] == 5
    assert r['graph']['derived_counts']['reused_nodes'] == 1
    assert r['graph']['lifecycle']['status'] == 'locked'
    assert first['draft_package']['next']['action'] == 'draft_debate'
    assert first['actual_codex_cloud_credits'] is None
    assert ci._validator()(corpus, scopes=ci.SCOPES).errors == 0
    assert str(project) not in ''.join(v.decode() for v in snapshot(corpus).values())


def test_prepare_reuses_exact_artifacts_and_never_mutates_plan(project):
    before = (project/'incoming/plan.json').read_bytes()
    first, files = prepared(project)
    current = snapshot(project/'.state/creation-init')
    second = ci.prepare(project, 'incoming/plan.json')
    assert second['status'] == 'reused'
    assert first['package_path'] == second['package_path']
    assert snapshot(project/'.state/creation-init') == current
    assert (project/'incoming/plan.json').read_bytes() == before


def test_replay_keeps_later_progress_and_recompressed_return(project):
    initialized(project)
    corpus = project/'corpus/creation_exemple'
    (corpus/'reports/later.txt').write_text('Later work, never overwrite')
    before = snapshot(corpus)
    result = ci.initialize(project, 'incoming/return.zip')
    assert result['status'] == 'already_initialized'
    assert result['current_state_matches_receipt'] is False
    assert snapshot(corpus) == before
    files = ci._zip_files((project/'incoming/return.zip').read_bytes())
    assert ci.initialize(project, returned(project, files, 'recompressed.zip'))['status'] == 'already_initialized'


def test_rejected_review_records_blockers_without_installation(project):
    _, files = prepared(project)
    review = ci.parse(files[ci.REVIEW_PATH])
    review.update(decision='rejected', reviewer='Synthetic reviewer', reviewed_at=ci._now(),
                  scope_rationale='The reviewed synthetic plan leaves a substantive ambiguity.', blocking_issues=['Ambiguous scope'])
    files[ci.REVIEW_PATH] = ci._json(review)
    assert ci.initialize(project, returned(project, files))['status'] == 'review_rejected'
    assert not (project/'corpus').exists()
    assert len(list((project/'.state/creation-init').rglob('rejections/*.json'))) == 1


@pytest.mark.parametrize('case', ['pending', 'missing_attestation', 'title_missing', 'title_duplicate', 'title_changed',
                                  'false_title_review', 'blank_rationale', 'placement_missing', 'placement_bad_target',
                                  'placement_pending', 'placement_action', 'blocking_approved', 'future', 'before', 'timezone',
                                  'foreign_identity', 'extra_field', 'duplicate_json'])
def test_incomplete_or_foreign_approval_never_installs(project, case):
    _, files = prepared(project)
    approved(files)
    r = ci.parse(files[ci.REVIEW_PATH])
    if case == 'pending': r['decision'] = 'pending'
    if case == 'missing_attestation': r['attestations']['batches_reviewed'] = False
    if case == 'title_missing': r['titles'].pop()
    if case == 'title_duplicate': r['titles'][1] = copy.deepcopy(r['titles'][0])
    if case == 'title_changed': r['titles'][0]['canonical_title'] = 'Different title'
    if case == 'false_title_review': r['titles'][0]['semantic_equivalence'] = False
    if case == 'blank_rationale': r['titles'][0]['rationale'] = ''
    if case == 'placement_missing': r['placement_review']['entries'].pop()
    if case == 'placement_bad_target': r['placement_review']['entries'][-1]['semantic_target'] = 'O00001'
    if case == 'placement_pending': r['placement_review']['entries'][0]['placement_status'] = 'pending'
    if case == 'placement_action': r['placement_review']['entries'][0]['correction']['action'] = 'move'
    if case == 'blocking_approved': r['blocking_issues'] = ['Unresolved omission']
    if case == 'future': r['reviewed_at'] = '2999-01-01T00:00:00Z'
    if case == 'before': r['reviewed_at'] = '2000-01-01T00:00:00Z'
    if case == 'timezone': r['reviewed_at'] = '2026-11-21T00:00:00'
    if case == 'foreign_identity': r['plan_sha256'] = 'f'*64
    if case == 'extra_field': r['publication_authorized'] = True
    files[ci.REVIEW_PATH] = ci._json(r)
    if case == 'duplicate_json': files[ci.REVIEW_PATH] = files[ci.REVIEW_PATH].replace(b'{', b'{"decision":"approved",', 1)
    with pytest.raises((ci.CreationContextError, ValueError)):
        ci.initialize(project, returned(project, files))
    assert not (project/'corpus/creation_exemple').exists()


@pytest.mark.parametrize('case', ['unknown_parent', 'cycle', 'unknown_node', 'node_duplicate', 'occ_duplicate',
                                  'secondary_children', 'extra_plan_field', 'order_bool', 'order_string',
                                  'self_edge', 'title_collision', 'debate_collision', 'unsafe_id', 'bad_title',
                                  'bad_category', 'uncovered_batch', 'duplicate_batch', 'future_dependency', 'no_primary'])
def test_invalid_plan_is_not_prepared(project, case):
    p = plan_data()
    if case == 'unknown_parent': p['placements'][2]['parent_occurrence_id'] = 'O88888'
    if case == 'cycle': p['placements'][2]['parent_occurrence_id'] = 'O00004'
    if case == 'unknown_node': p['placements'][2]['node_id'] = 'A9999'
    if case == 'node_duplicate': p['nodes'].append(copy.deepcopy(p['nodes'][0]))
    if case == 'occ_duplicate': p['placements'].append(copy.deepcopy(p['placements'][0]))
    if case == 'secondary_children': p['placements'][3]['parent_occurrence_id'] = 'O00005'
    if case == 'extra_plan_field': p['approved'] = True
    if case == 'order_bool': p['placements'][0]['order'] = True
    if case == 'order_string': p['placements'][0]['order'] = '1'
    if case == 'self_edge': p['placements'][-1]['node_id'] = 'A0002'
    if case == 'title_collision': p['nodes'][1]['canonical_title_fr'] = p['nodes'][0]['canonical_title_fr'].upper()
    if case == 'debate_collision': p['nodes'][1]['canonical_title_fr'] = p['scope']['canonical_title_fr']
    if case == 'unsafe_id': p['debate_id'] = '../foreign'
    if case == 'bad_title': p['nodes'][0]['displayed_title_fr'] = 'Truncated...'
    if case == 'bad_category': p['nodes'][0]['rubriques'] = ['Unknown category']
    if case == 'uncovered_batch': p['batches'][1]['node_ids'].pop()
    if case == 'duplicate_batch': p['batches'].append(copy.deepcopy(p['batches'][0]))
    if case == 'future_dependency': p['batches'][0]['dependency_node_ids'] = ['A0003']
    if case == 'no_primary': p['placements'][2]['occurrence_role'] = 'secondary'
    put(project/'incoming/plan.json', p)
    with pytest.raises((ci.CreationContextError, ci.CorpusBuildError)):
        ci.prepare(project, 'incoming/plan.json')
    assert not (project/'corpus').exists()
    assert not [p for p in (project/'outgoing').glob('*.zip') if 'diagnostic' not in p.name]


@pytest.mark.parametrize('case', ['plan', 'norm', 'producer', 'candidate', 'context', 'extra_file', 'missing_file', 'manifest', 'request'])
def test_stale_or_tampered_return_blocked(project, monkeypatch, case):
    _, files = prepared(project)
    approved(files)
    if case == 'plan': (project/'incoming/plan.json').write_bytes((project/'incoming/plan.json').read_bytes()+b'\n')
    if case == 'norm':
        norm = next((project/'norms/normative_reference/01_normes').glob('*.md'))
        norm.write_bytes(norm.read_bytes()+b'\n')
    if case == 'producer': monkeypatch.setattr(ci, '_producer_basis', lambda: {})
    if case == 'candidate': next((project/'.state/creation-init').rglob('candidate/scope.json')).write_text('{}')
    if case == 'context': files['context/PLAN.json'] += b'\n'
    if case == 'extra_file': files['editable/unopened.wiki'] = b'New text'
    if case == 'missing_file': files.pop('context/PLAN.json')
    if case == 'manifest':
        m = ci.parse(files['REVIEW_PACKAGE.json']); m['source_anchor_sha256'] = 'f'*64
        files['REVIEW_PACKAGE.json'] = ci._json(m)
    if case == 'request': next((project/'.state/creation-init').rglob('request.json')).write_text('{}')
    with pytest.raises(ci.CreationContextError): ci.initialize(project, returned(project, files))
    assert not (project/'corpus/creation_exemple').exists()


def test_existing_empty_corpus_is_never_replaced_even_racing(project, monkeypatch):
    _, files = prepared(project)
    archive = returned(project, approved(files))
    original = ci._rename_new
    def race(source, target):
        target.mkdir(parents=True)
        return original(source, target)
    monkeypatch.setattr(ci, '_rename_new', race)
    with pytest.raises(FileExistsError): ci.initialize(project, archive)
    assert list((project/'corpus/creation_exemple').iterdir()) == []


def test_existing_corpus_blocks_preparation(project):
    folder = project/'corpus/creation_exemple'; folder.mkdir(parents=True)
    (folder/'important.txt').write_text('Never delete')
    with pytest.raises(ci.CreationContextError): ci.prepare(project, 'incoming/plan.json')
    assert (folder/'important.txt').read_text() == 'Never delete'


@pytest.mark.parametrize('kind', ['symlink', 'hardlink'])
def test_linked_input_rejected(project, kind):
    source = project/'incoming/plan.json'
    target = project/'incoming/linked.json'
    if kind == 'symlink': target.symlink_to(source)
    else: os.link(source, target)
    with pytest.raises(ci.CreationContextError): ci.prepare(project, 'incoming/linked.json')


def test_cli_prepare_init_and_resume(project, capsys):
    assert manager.main(['--root', str(project), 'creation-prepare', '--plan', 'incoming/plan.json']) == 0
    info = json.loads(capsys.readouterr().out)
    files = ci._zip_files((project/info['package_path']).read_bytes())
    returned(project, approved(files))
    assert manager.main(['--root', str(project), 'creation-init']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['draft_package']['next']['action'] == 'draft_debate'
    assert cr.creation_resume(project, 'corpus/creation_exemple')['next']['page_ids'] == ['creation_exemple']


def test_draft_and_research_import_after_initialization(project):
    result = initialized(project)
    files = ci._zip_files((project/result['draft_package']['package_path']).read_bytes())
    response = ci.parse(files['editable/RESPONSE.json'])
    response['pages'][0]['status'] = 'partial'
    files['editable/RESPONSE.json'] = ci._json(response)
    files['editable/output/fr/debate/debate.wiki'] = b'A genuinely unfinished draft'
    path = returned(project, files, 'draft.zip')
    result = di.import_package(project, 'corpus/creation_exemple', archive=path)
    assert result['status'] == 'imported'
    assert cr.creation_resume(project, 'corpus/creation_exemple')['counts']['draft_in_progress'] == 1


def test_no_network_or_subprocess_during_initialization(project, monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('No remote access or model execution')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(subprocess, 'run', forbidden)
    assert initialized(project)['status'] == 'initialized'


def test_handoff_failure_preserves_installed_corpus(project, monkeypatch):
    def fail(*args, **kwargs): raise ci.CreationContextError('Injected handoff failure')
    monkeypatch.setattr(ci, 'prepare_package', fail)
    assert initialized(project)['status'] == 'initialized_next_blocked'
    assert (project/'corpus/creation_exemple/manifest.json').is_file()
    assert ci.initialize(project, 'incoming/return.zip')['status'] == 'already_initialized'


def test_late_plan_change_is_not_installed(project, monkeypatch):
    _, files = prepared(project)
    archive = returned(project, approved(files))
    original = ci._lock_graph
    def change(stage, review, timestamp):
        original(stage, review, timestamp)
        (project/'incoming/plan.json').write_bytes(b'{}')
    monkeypatch.setattr(ci, '_lock_graph', change)
    with pytest.raises(ci.CreationContextError): ci.initialize(project, archive)
    assert not (project/'corpus/creation_exemple').exists()


@pytest.mark.parametrize('after', [False, True])
def test_process_crash_before_or_after_atomic_installation(project, after):
    _, files = prepared(project)
    archive = returned(project, approved(files))
    code = '''
import os, sys
sys.path.insert(0, sys.argv[1])
import wikidebia_creation_init as c
from pathlib import Path
original = c._rename_new
def crash(source, target):
    if sys.argv[4] == 'yes': original(source, target)
    os._exit(71)
c._rename_new = crash
c.initialize(Path(sys.argv[2]), sys.argv[3])
'''
    completed = subprocess.run([sys.executable, '-c', code, str(ROOT/'kit/scripts'), str(project), archive, 'yes' if after else 'no'], capture_output=True)
    assert completed.returncode == 71, completed.stderr.decode()
    target = project/'corpus/creation_exemple'
    assert target.exists() is after
    result = ci.initialize(project, archive)
    assert result['status'] == ('already_initialized' if after else 'initialized')
    assert ci._validator()(target, scopes=ci.SCOPES).errors == 0


def test_rejected_package_cannot_be_promoted_by_toggling_decision(project):
    _, files = prepared(project)
    approved(files)
    r = ci.parse(files[ci.REVIEW_PATH])
    r.update(decision='rejected', blocking_issues=['A required revision of the question'])
    files[ci.REVIEW_PATH] = ci._json(r)
    ci.initialize(project, returned(project, files))
    r.update(decision='approved', blocking_issues=[])
    files[ci.REVIEW_PATH] = ci._json(r)
    with pytest.raises(ci.CreationContextError, match='was rejected'):
        ci.initialize(project, returned(project, files))
    p = load(project/'incoming/plan.json')
    p['scope']['scope_summary_fr'] += ' Clarified question.'
    put(project/'incoming/plan.json', p)
    _, new = prepared(project)
    assert ci.parse(new['REVIEW_PACKAGE.json'])['package_id'] != ci.parse(files['REVIEW_PACKAGE.json'])['package_id']
    assert ci.initialize(project, returned(project, approved(new)))['status'] == 'initialized'


def test_full_validation_does_not_confuse_initialization_with_release(project):
    initialized(project)
    report = ci._validator()(project/'corpus/creation_exemple', scopes=['all'])
    assert report.errors > 0
    assert load(project/'corpus/creation_exemple/manifest.json')['global_status'] == 'graph_locked'


def test_package_conforms_to_existing_handoff_schema(project):
    _, files = prepared(project)
    from wikidebia_validator.schema_validation import SchemaStore
    assert SchemaStore().validate(ci.parse(files['REVIEW_PACKAGE.json']), 'chatgpt_review_package.schema.json') == []


def test_changed_return_never_reinitializes_existing_corpus(project):
    initialized(project)
    before = snapshot(project/'corpus')
    files = ci._zip_files((project/'incoming/return.zip').read_bytes())
    files[ci.REVIEW_PATH] += b'\n'
    with pytest.raises(ci.CreationContextError): ci.initialize(project, returned(project,files))
    assert snapshot(project/'corpus') == before


def test_pending_draft_import_blocks_initialization_even_when_corpus_absent(project):
    _, files = prepared(project)
    archive = returned(project, approved(files))
    _, control = ci._locations(project, 'corpus/creation_exemple')
    (control/'active.json').write_text('{}')
    with pytest.raises(ci.CreationContextError, match='Interrupted'):
        ci.initialize(project, archive)
    assert not (project/'corpus/creation_exemple').exists()


def test_automatic_archive_selection_refuses_multiple_plan_returns(project):
    _, files = prepared(project)
    approved(files)
    returned(project, files, 'one.zip'); returned(project, files, 'two.zip')
    with pytest.raises(ci.CreationContextError, match='select a single'):
        ci.initialize(project)


def test_new_corpus_is_complete_if_fsync_fails_after_rename(project, monkeypatch):
    _, files = prepared(project)
    archive = returned(project, approved(files))
    original = ci._sync_dir
    def fail(path):
        if path == project/'corpus': raise OSError('Injected sync failure after rename')
        original(path)
    monkeypatch.setattr(ci, '_sync_dir', fail)
    with pytest.raises(OSError): ci.initialize(project, archive)
    assert ci.initialize(project, archive)['status'] == 'already_initialized'


def test_failed_validation_retains_concrete_diagnostic(project):
    p = plan_data(); p['nodes'][0]['rubriques'] = ['Invalid category']
    put(project/'incoming/plan.json', p)
    with pytest.raises(ci.CreationContextError, match='diagnostic: outgoing/'):
        ci.prepare(project, 'incoming/plan.json')
    paths = list((project/'outgoing').glob('*diagnostic*.zip'))
    assert len(paths) == 1
    files = ci._zip_files(paths[0].read_bytes())
    assert ci.parse(files['VALIDATION_REPORT.json'])['summary']['errors'] > 0
    assert 'REVIEW_PACKAGE.json' not in files


def test_large_synthetic_plan_builds_once_then_hands_off_one_debate(project):
    p = plan_data()
    for i in range(5, 201):
        n = copy.deepcopy(p['nodes'][0])
        n.update(id=f'A{i:04d}', canonical_title_fr=f'La mesure X modifie le mecanisme {i}',
                 displayed_title_fr=f'La mesure X modifie le mecanisme {i}')
        p['nodes'].append(n)
        p['placements'].append({'occurrence_id':f'O{i+1:05d}', 'node_id':n['id'], 'parent_occurrence_id':'O00001',
                                'relation':'justification', 'branch':None, 'order':i, 'occurrence_role':'primary'})
    p['batches'] += [{'node_ids': [f'A{i:04d}' for i in range(start,min(start+20,201))],
                     'dependency_node_ids':['A0001']} for start in range(5,201,20)]
    put(project/'incoming/plan.json', p)
    first, files = prepared(project)
    assert ci.prepare(project, 'incoming/plan.json')['status'] == 'reused'
    result = ci.initialize(project,returned(project,approved(files)))
    assert result['status'] == 'initialized'
    assert result['draft_package']['next']['page_ids'] == ['creation_exemple']
    assert len(load(project/'corpus/creation_exemple/manifest.json')['pages']) == 201


def test_unsafe_archive_member_is_refused(project):
    _, files = prepared(project)
    files['../outside.json'] = b'{}'
    with pytest.raises(ci.CreationContextError): ci.initialize(project,returned(project,approved(files)))


def test_lock_prevents_concurrent_cooperating_initializations(project):
    _, files = prepared(project)
    archive = returned(project, approved(files))
    _, control = ci._locations(project, 'corpus/creation_exemple')
    with ci._lock(project, control):
        with pytest.raises(ci.CreationContextError, match='Another creation operation'):
            ci.initialize(project, archive)
