"""Only measured package bytes, never fictitious ChatGPT/Codex savings."""
from __future__ import annotations

import json
import socket
import subprocess
import zipfile

import pytest

import wikidebia_creation_context as cc
import wikidebia_creation_import as ci
import wikidebia_creation_library as library
import wikidebia_creation_measure as measure
import wikidebia_manage as manager
from test_wikidebia_creation_resume import project, snapshot, load, put
from test_wikidebia_creation_import import CORPUS
from test_wikidebia_creation_library import ORIGIN, origin


def pair(project, *, corpus=CORPUS, pages=('A0001',), query=None):
    basic = ci.prepare_package(project, corpus, research_only=True, page_ids=list(pages))
    reused = ci.prepare_package(project, corpus, research_only=True, page_ids=list(pages),
                                reuse_library=True, reuse_query=query)
    return basic['package_path'], reused['package_path']


def ready(project):
    origin(project)
    assert library.build_library(project, [ORIGIN])['notices'] == 1
    return pair(project)


def modify_zip(project, rel, target, change):
    with zipfile.ZipFile(project/rel) as archive:
        entries = {n: archive.read(n) for n in archive.namelist()}
    entries[target] = change(entries[target])
    dest = project/'outgoing'/'altered.zip'
    with zipfile.ZipFile(dest, 'w') as archive:
        for name, raw in entries.items():
            archive.writestr(name, raw)
    return 'outgoing/altered.zip'


def test_measure_equal_scope_has_exact_additional_bytes_without_quota_claim(project):
    old, new = ready(project)
    before = snapshot(project/CORPUS)
    row = measure.measure_pair(project, old, new)
    assert row['scope_pages'] == 1
    assert row['discovery_hints']['candidate_links'] == 1
    assert row['discovery_hints']['unique_notices'] == 1
    assert row['discovery_hints']['duplicate_notice_references_avoided'] == 0
    assert row['delta_bytes_reuse_minus_baseline']['context_files_bytes'] > 0
    assert row['delta_bytes_reuse_minus_baseline']['available_context_bytes'] > 0
    assert row['delta_bytes_reuse_minus_baseline']['editable_files_bytes'] == 0
    assert row['actual_model_input_tokens'] is None
    assert row['actual_codex_credits'] is None
    assert row['documentary_researches_avoided'] is None
    assert row['editorial_quality_change'] is None
    assert snapshot(project/CORPUS) == before


def test_measure_is_deterministic_and_offline(project, monkeypatch):
    old, new = ready(project)
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: pytest.fail('network used'))
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('process used'))
    before = snapshot(project)
    a = measure.measure(project, [[old, new]])
    b = measure.measure(project, [[old, new]])
    assert a == b
    assert snapshot(project) == before
    assert a['remote_access_performed'] is False and a['corpus_modified'] is False


def test_repeated_pairs_aggregate_exact_totals_without_inventing_savings(project):
    old, new = ready(project)
    other = pair(project, pages=('A0002',), query='neuroscience')
    report = measure.measure(project, [[old, new], list(other)])
    assert report['pairs_measured'] == 2
    assert report['distinct_debates'] == 1
    for key, count in report['totals']['delta_bytes_reuse_minus_baseline'].items():
        assert count == sum(p['delta_bytes_reuse_minus_baseline'][key] for p in report['pairs'])
    assert report['actual_billed_tokens'] is None
    assert report['real_searches_avoided'] is None


def test_multiple_debates_count_is_not_confused_with_multiple_packages(project):
    other = origin(project, name='autre', note=False)
    other_manifest = load(other/'manifest.json')
    for page in other_manifest['pages']:
        page['debate_id'] = 'autre'
    for batch in other_manifest['batches']:
        batch['debate_id'] = 'autre'
    put(other/'manifest.json', other_manifest)
    other_registry = load(other/'data/registre_debat.json')
    for batch in other_registry['batches']:
        batch['debate_id'] = 'autre'
    put(other/'data/registre_debat.json', other_registry)
    origin(project, name='troisieme')
    library.build_library(project, ['corpus/troisieme'])
    a, b = pair(project)
    c, d = pair(project, corpus='corpus/autre')
    report = measure.measure(project, [[a,b],[c,d]])
    assert report['distinct_debates'] == 2
    assert report['pairs_measured'] == 2


def test_empty_reuse_suggestions_are_not_counted_as_saved_searches(project):
    origin(project, title='Unrelated cardiology trial')
    library.build_library(project, [ORIGIN])
    old, new = pair(project, pages=('A0004',))
    hints = measure.measure_pair(project, old, new)['discovery_hints']
    assert hints['candidate_links'] == hints['unique_notices'] == 0


def test_duplicate_notice_shared_between_pages_counted_once(project):
    origin(project)
    library.build_library(project, [ORIGIN])
    old, new = pair(project, pages=('A0001', 'A0002'))
    row = measure.measure_pair(project, old, new)
    hints = row['discovery_hints']
    assert hints['unique_notices'] <= hints['candidate_links']
    assert hints['duplicate_notice_references_avoided'] == (hints['candidate_links']-hints['unique_notices'])
    assert row['scope_pages'] == 2


def test_manager_cli_json_and_guarded_output_paths(project, capsys):
    old, new = ready(project)
    assert manager.main(['--root', str(project), 'creation-measure', '--pair', old, new]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed['schema'] == measure.SCHEMA
    assert parsed['actual_codex_cloud_credits'] is None
    assert measure.main(['--project-root', str(project), '--pair', '../../bad.zip', new]) == 2
    assert 'outgoing/' in capsys.readouterr().err


@pytest.mark.parametrize('path', [
    'private/creation_library.json', '../outgoing/a.zip', '/tmp/absolute.zip',
    'outgoing/../a.zip', 'outgoing/dir/part.zip', 'incoming/returned.zip',
    'outgoing/fake.zip\n', 'outgoing\\bad.zip', 'outgoing/bad.txt',
])
def test_private_noncanonical_or_external_paths_are_rejected(project, path):
    old, new = ready(project)
    with pytest.raises(cc.CreationContextError, match='outgoing'):
        measure.measure_pair(project, path, new)


@pytest.mark.parametrize('tamper', [
    'instructions', 'context', 'manifest', 'editable', 'extra', 'missing', 'reuse_preview',
])
def test_altered_package_is_rejected_without_touching_corpus(project, tamper):
    old, new = ready(project)
    before = snapshot(project/CORPUS)
    if tamper == 'instructions':
        source, field = old, 'INSTRUCTIONS.md'
        corrupted = modify_zip(project, source, field, lambda raw: raw + b'!')
        args = (corrupted, new)
    elif tamper == 'context':
        corrupted = modify_zip(project, old, 'context/NORMATIVE_CONTEXT.md', lambda raw: raw + b'X')
        args = (corrupted, new)
    elif tamper == 'manifest':
        corrupted = modify_zip(project, old, 'REVIEW_PACKAGE.json', lambda raw: raw.replace(b'fr_creation_draft', b'forged_review_kind'))
        args = (corrupted, new)
    elif tamper == 'editable':
        corrupted = modify_zip(project, old, 'editable/RESEARCH.json', lambda raw: raw + b'\n')
        args = (corrupted, new)
    elif tamper == 'reuse_preview':
        corrupted = modify_zip(project, new, library.PREVIEW_PATH, lambda raw: raw + b'\n')
        args = (old, corrupted)
    else:
        with zipfile.ZipFile(project/old) as z:
            files = {k: z.read(k) for k in z.namelist()}
        if tamper == 'extra':
            files['private/export.json'] = b'{}'
        else:
            del files['context/NORMATIVE_CONTEXT.md']
        dest = project/'outgoing/altered.zip'
        with zipfile.ZipFile(dest, 'w') as z:
            for name, raw in files.items():
                z.writestr(name, raw)
        args = ('outgoing/altered.zip', new)
    with pytest.raises((cc.CreationContextError, KeyError, ValueError)):
        measure.measure_pair(project, *args)
    assert snapshot(project/CORPUS) == before


def test_rejects_two_normal_packages_or_reverse_order(project):
    old, new = ready(project)
    with pytest.raises(cc.CreationContextError, match='regular package'):
        measure.measure_pair(project, new, old)
    with pytest.raises(cc.CreationContextError, match='regular package'):
        measure.measure_pair(project, old, old)


def test_rejects_other_page_selection_even_same_corpus_snapshot(project):
    old, new = ready(project)
    _, other = pair(project, pages=('A0002',))
    with pytest.raises(cc.CreationContextError, match='scope|editable'):
        measure.measure_pair(project, old, other)


def test_rejects_other_snapshot_and_does_not_rewrite_any_state(project):
    old, new = ready(project)
    original = snapshot(project/CORPUS)
    with zipfile.ZipFile(project/new) as z:
        files = {k: z.read(k) for k in z.namelist()}
    m = json.loads(files['REVIEW_PACKAGE.json'])
    m['source_anchor_sha256'] = '0'*64
    m['manifest_sha256'] = __import__('wikidebia_review_workflow')._package_manifest_hash(m)
    files['REVIEW_PACKAGE.json'] = cc._json(m)
    with zipfile.ZipFile(project/'outgoing/altered.zip', 'w') as z:
        for k, v in files.items():
            z.writestr(k,v)
    with pytest.raises(cc.CreationContextError, match='preparation receipt'):
        measure.measure_pair(project, old, 'outgoing/altered.zip')
    assert snapshot(project/CORPUS) == original


def test_rejects_symlink_and_duplicate_measurement(project):
    old, new = ready(project)
    (project/'outgoing'/'linked.zip').symlink_to(project/new)
    with pytest.raises(cc.CreationContextError):
        measure.measure_pair(project, old, 'outgoing/linked.zip')
    with pytest.raises(cc.CreationContextError, match='duplicate'):
        measure.measure(project, [[old,new],[old,new]])


def test_input_size_and_pair_count_limits(project):
    old, new = ready(project)
    with pytest.raises(cc.CreationContextError, match='32 pairs'):
        measure.measure(project, [[old,new]]*33)
    with pytest.raises(cc.CreationContextError, match='1 to 32'):
        measure.measure(project, [])


def test_report_contains_no_source_titles_or_private_library_data(project):
    old, new = ready(project)
    report = measure.measure(project, [[old,new]])
    text = json.dumps(report)
    assert 'Reason 1 and documentary knowledge' not in text
    assert 'private/creation_library' not in text
    assert 'sources.json' not in text
