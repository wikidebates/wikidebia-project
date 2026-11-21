"""Cross-debate reuse is discovery only; page-level verification is not transferable."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import zipfile

import pytest

import wikidebia_creation_context as cc
import wikidebia_creation_import as ci
import wikidebia_creation_library as library
import wikidebia_creation_research as research
import wikidebia_creation_sources as sources
import wikidebia_manage as manager
from test_wikidebia_creation_resume import project, load, put, snapshot
from test_wikidebia_creation_import import CORPUS, returned, run_import
from test_wikidebia_creation_research import resource, observation, search


ORIGIN = 'corpus/autre'


def origin(project, *, name='autre', title='Reason 1 and documentary knowledge',
           link='https://example.org/reason-1', language='fr', note=True,
           source_record=False):
    source = project / 'corpus' / name
    shutil.copytree(project / CORPUS, source)
    manifest = load(source / 'manifest.json')
    manifest['debate_id'] = name
    for p in manifest['pages']:
        if p['page_id'] == 'exemple':
            p['page_id'] = name
    put(source/'manifest.json', manifest)
    registry = load(source/'data/registre_debat.json')
    registry['debate']['id'] = name
    put(source/'data/registre_debat.json', registry)
    scope = load(source/'scope.json')
    scope['debate_id'] = name
    put(source/'scope.json', scope)
    canonical = load(source/'data/sources.json')
    canonical['debate_id'] = name
    if source_record:
        canonical['sources'].append({
            'id': 'S00001', 'type': 'webliography', 'language': language,
            'metadata': {'title': title, 'link': link},
            'usage': [{'page_id': 'A0001', 'language': 'fr', 'role': 'supports_summary',
                       'selection_reason': 'Cette reference relie la raison documentaire a la mesure.'}]})
    put(source/'data/sources.json', canonical)
    if note:
        response = research.empty_response()
        response['resources'] = [dict(resource(title=title, link=link), language=language)]
        response['observations'] = [observation('A0001')]
        response['searches'] = [search()]
        saved = {'schema': research.LEDGER_SCHEMA, 'debate_id': name,
                 'resources': [], 'observations': [], 'searches': []}
        merged, counts = research.merge_response(response, saved, {'A0001'},
            research.basis(manifest, registry, scope), canonical)
        assert counts == {'resources': 1, 'observations': 1, 'searches': 1}
        research.save_notes(source, merged)
    return source


def entries(project):
    return load(project/library.LIBRARY_PATH)['notices']


def prepared(project, **kwargs):
    return ci.prepare_package(project, CORPUS, research_only=True, page_ids=['A0001'], **kwargs)


def preview(project, result):
    with zipfile.ZipFile(project/result['package_path']) as z:
        names = set(z.namelist())
        assert library.PREVIEW_PATH in names
        assert library.HELP_PATH in names
        return json.loads(z.read(library.PREVIEW_PATH)), names, z.read('editable/RESEARCH.json')


def test_library_is_opt_in_private_deterministic_and_offline(project, monkeypatch):
    origin(project)
    before = snapshot(project/CORPUS)
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: pytest.fail('network requested'))
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('subprocess requested'))
    report = library.build_library(project, [ORIGIN])
    assert report['notices'] == 1 and report['identities'] == 1
    assert report['source_verification_performed'] is False
    assert stat.S_IMODE((project/'private').stat().st_mode) == 0o700
    assert stat.S_IMODE((project/library.LIBRARY_PATH).stat().st_mode) == 0o600
    raw = (project/library.LIBRARY_PATH).read_bytes()
    assert library.build_library(project, [ORIGIN])['status'] == 'built'
    assert (project/library.LIBRARY_PATH).read_bytes() == raw
    assert snapshot(project/CORPUS) == before
    assert 'excerpt' not in raw.decode() and 'no_result' not in raw.decode()
    assert 'private' not in [x['path'] for x in load(project/library.LIBRARY_PATH)['inputs']]


def test_only_targeted_hints_are_added_with_no_verification_or_import(project):
    origin(project)
    library.build_library(project, [ORIGIN])
    before = snapshot(project/CORPUS)
    standard = prepared(project)
    with zipfile.ZipFile(project/standard['package_path']) as z:
        assert library.PREVIEW_PATH not in z.namelist()
    package = prepared(project, reuse_library=True)
    assert package['package_path'] != standard['package_path']
    view, names, research_response = preview(project, package)
    assert view['not_verified_for_target'] and view['prior_proofs_are_not_transferable']
    assert view['research_or_source_import_performed'] is False
    assert research_response == cc._json(research.empty_response())
    assert len(view['page_candidates']) == 1
    suggestions = view['page_candidates'][0]['candidates']
    assert len(suggestions) == 1
    suggestion = next(x for x in view['notices'] if x['hint_id'] == suggestions[0]['hint_id'])
    assert suggestion['metadata']['title'] == 'Reason 1 and documentary knowledge'
    assert suggestion['previous_contexts'][0]['debate_id'] == 'autre'
    assert suggestion['previous_contexts'][0]['page_id'] == 'A0001'
    assert suggestion['requires_new_target_observation_and_review'] is True
    assert 'observation_id' not in str(suggestion)
    assert snapshot(project/CORPUS) == before
    assert prepared(project, reuse_library=True)['status'] == 'reused'
    returned(project, package)
    assert run_import(project)['status'] == 'no_changes'
    assert snapshot(project/CORPUS) == before


def test_unrelated_arguments_do_not_receive_poorly_matching_sources(project):
    origin(project, title='Medical experiments in neuroscience', note=True)
    library.build_library(project, [ORIGIN])
    first, _, _ = preview(project, prepared(project, reuse_library=True))
    # The overlap of source title is absent, but the prior page's claim has lexical relevance.
    assert first['page_candidates'][0]['candidates']
    second, _, _ = preview(project, ci.prepare_package(project, CORPUS,
        research_only=True, page_ids=['A0004'], reuse_library=True))
    assert second['page_candidates'][0]['candidates'] == []


def test_explicit_query_can_select_metadata_based_candidate(project):
    origin(project, title='Neuroscience experiments', note=True)
    library.build_library(project, [ORIGIN])
    result = prepared(project, reuse_library=True, reuse_query='neuroscience')
    view, _, _ = preview(project, result)
    assert 'neuroscience' in view['page_candidates'][0]['candidates'][0]['matched_terms']
    assert prepared(project, reuse_library=True)['package_path'] != result['package_path']
    with pytest.raises(cc.CreationContextError, match='requires --reuse-library'):
        prepared(project, reuse_query='neuroscience')


def test_same_notice_is_deduplicated_across_debates(project):
    origin(project, name='autre')
    origin(project, name='troisieme')
    report = library.build_library(project, ['corpus/troisieme', ORIGIN])
    assert report['notices'] == 1
    row = entries(project)[0]
    assert row['origin_count'] == 2
    assert {x['debate_id'] for x in row['origins']} == {'autre', 'troisieme'}
    assert row['variants_require_review'] is False


def test_conflicting_source_metadata_are_preserved_as_variants(project):
    origin(project, name='autre', title='Reason 1 and documentary knowledge')
    origin(project, name='troisieme', title='Reason 1 with differing publication metadata')
    report = library.build_library(project, [ORIGIN, 'corpus/troisieme'])
    assert report['notices'] == 2 and report['identities'] == 1
    assert all(r['variants_require_review'] for r in entries(project))
    view, _, _ = preview(project, prepared(project, reuse_library=True))
    assert len(view['page_candidates'][0]['candidates']) == 2
    assert all(x['variants_require_review'] for x in view['notices'])


def test_existing_canonical_usage_is_only_an_old_context_not_target_verification(project):
    origin(project, note=False, source_record=True)
    library.build_library(project, [ORIGIN])
    assert entries(project)[0]['origins'][0]['prior_record'] == 'canonical_usage'
    assert 'verification' not in entries(project)[0]
    view, _, _ = preview(project, prepared(project, reuse_library=True))
    assert view['notices'][0]['requires_new_target_observation_and_review']


def _unidentifiable_canonical(project, *, source_id='S00002', language='fr',
                              metadata=None, page='A0001'):
    path = project/ORIGIN/'data/sources.json'
    canonical = load(path)
    canonical['sources'].append({
        'id': source_id, 'type': 'bibliography', 'language': language,
        'metadata': metadata if metadata is not None else {
            'work': 'Ancienne étude sans éditeur ni date', 'authors': ['Auteur ancien']},
        'usage': [{'language': 'fr', 'page_id': page, 'role': 'supports_summary',
                   'selection_reason': 'Source historique incomplète'}]})
    put(path, canonical)


def test_incomplete_historical_source_is_reported_not_reused_or_global_blocker(project):
    origin(project, note=False, source_record=True)
    _unidentifiable_canonical(project)
    before = snapshot(project/ORIGIN)
    report = library.build_library(project, [ORIGIN])
    assert report['notices'] == 1 and report['identities'] == 1
    assert report['omitted_unidentifiable_sources'] == 1
    assert report['omissions_by_corpus'] == {ORIGIN: 1}
    index, raw = library.load_library(project)
    assert index['omissions'] == [{'debate_id': 'autre', 'source_id': 'S00002',
                                  'reason': library.OMISSION_REASON}]
    assert all(row['metadata']['title'] != 'Ancienne étude sans éditeur ni date'
               for row in index['notices'])
    assert prepared(project, reuse_library=True)['reuse_candidate_count'] == 1
    assert snapshot(project/ORIGIN) == before
    assert library.build_library(project, [ORIGIN])['status'] == 'built'
    assert (project/library.LIBRARY_PATH).read_bytes() == raw



@pytest.mark.parametrize('metadata', [
    {'link': 'https://example.org/untitled', 'authors': ['A. B.']},
    {'authors': ['A. B.'], 'date': '2020', 'publisher': 'Éditeur'},
    {'title': None, 'link': 'https://example.org/untitled'},
])
def test_historical_source_missing_real_title_is_omitted_with_reason(project, metadata):
    origin(project, note=False, source_record=True)
    _unidentifiable_canonical(project, metadata=metadata)
    before = snapshot(project/ORIGIN)
    report = library.build_library(project, [ORIGIN])
    assert report['notices'] == 1
    assert report['omitted_unidentifiable_sources'] == 1
    assert report['omissions_by_corpus'] == {ORIGIN: 1}
    assert report['omissions_by_reason'] == {
        library.OMISSION_REASON: 0, library.MISSING_TITLE_REASON: 1}
    index, raw = library.load_library(project)
    assert index['omissions'] == [{'debate_id': 'autre', 'source_id': 'S00002',
                                  'reason': library.MISSING_TITLE_REASON}]
    assert snapshot(project/ORIGIN) == before
    assert library.build_library(project, [ORIGIN])['status'] == 'built'
    assert (project/library.LIBRARY_PATH).read_bytes() == raw


def test_missing_title_with_multiple_usages_counted_once(project):
    origin(project, note=False)
    _unidentifiable_canonical(project, metadata={'link': 'https://example.org/untitled'})
    path = project/ORIGIN/'data/sources.json'
    canonical = load(path)
    canonical['sources'][0]['usage'].append(dict(canonical['sources'][0]['usage'][0], page_id='A0002'))
    put(path, canonical)
    report = library.build_library(project, [ORIGIN])
    assert report['omitted_unidentifiable_sources'] == 1
    assert report['omissions_by_reason'][library.MISSING_TITLE_REASON] == 1


def test_mixed_historical_omission_reasons_are_auditable_and_loadable(project):
    origin(project, note=False, source_record=True)
    _unidentifiable_canonical(project, source_id='S00002')
    _unidentifiable_canonical(project, source_id='S00003',
                              metadata={'link': 'https://example.org/untitled'})
    report = library.build_library(project, [ORIGIN])
    assert report['notices'] == 1
    assert report['omitted_unidentifiable_sources'] == 2
    assert report['omissions_by_reason'] == {
        library.OMISSION_REASON: 1, library.MISSING_TITLE_REASON: 1}
    index, _ = library.load_library(project)
    assert [item['reason'] for item in index['omissions']] == [
        library.OMISSION_REASON, library.MISSING_TITLE_REASON]
    assert prepared(project, reuse_library=True)['reuse_candidate_count'] == 1


@pytest.mark.parametrize('link,error', [
    ('http://localhost/private', 'local reference URL'),
    ('https://example.org/untitled?token=secrets', 'credential-bearing reference URL'),
])
def test_missing_title_does_not_hide_unsafe_reference_link(project, link, error):
    origin(project, note=False)
    _unidentifiable_canonical(project, metadata={'link': link})
    with pytest.raises(cc.CreationContextError, match=error):
        library.build_library(project, [ORIGIN])
    assert not (project/library.LIBRARY_PATH).exists()


def test_missing_title_foreign_canonical_source_is_not_counted(project):
    origin(project, note=False)
    _unidentifiable_canonical(project, language='en', metadata={'link': 'https://example.org/untitled'})
    report = library.build_library(project, [ORIGIN])
    assert report['notices'] == 0 and report['omitted_unidentifiable_sources'] == 0
    assert report['omissions_by_reason'][library.MISSING_TITLE_REASON] == 0


def test_library_omission_reason_must_remain_known_even_with_valid_digest(project):
    origin(project, note=False)
    _unidentifiable_canonical(project, metadata={'link': 'https://example.org/untitled'})
    library.build_library(project, [ORIGIN])
    path = project/library.LIBRARY_PATH
    index = load(path)
    index['omissions'][0]['reason'] = 'verified_for_target'
    index['sha256'] = cc._sha(cc._json({k: v for k, v in index.items() if k != 'sha256'}))
    put(path, index)
    with pytest.raises(cc.CreationContextError, match='omission'):
        library.load_library(project)


def test_only_unidentifiable_historical_sources_yields_audited_empty_library(project):
    origin(project, note=False)
    _unidentifiable_canonical(project)
    report = library.build_library(project, [ORIGIN])
    assert (report['notices'], report['omitted_unidentifiable_sources']) == (0, 1)
    loaded, _ = library.load_library(project)
    assert loaded['notices'] == [] and len(loaded['omissions']) == 1
    assert prepared(project, reuse_library=True)['reuse_candidate_count'] == 0


def test_one_historical_source_with_multiple_uses_is_counted_once(project):
    origin(project, note=False)
    _unidentifiable_canonical(project)
    path = project/ORIGIN/'data/sources.json'
    canonical = load(path)
    duplicate_use = dict(canonical['sources'][0]['usage'][0], page_id='A0002')
    canonical['sources'][0]['usage'].append(duplicate_use)
    put(path, canonical)
    report = library.build_library(project, [ORIGIN])
    assert report['omitted_unidentifiable_sources'] == 1
    assert len(library.load_library(project)[0]['omissions']) == 1


def test_incomplete_historical_foreign_source_is_not_counted_as_french(project):
    origin(project, note=False)
    _unidentifiable_canonical(project, language='en')
    report = library.build_library(project, [ORIGIN])
    assert report['notices'] == 0 and report['omitted_unidentifiable_sources'] == 0


@pytest.mark.parametrize('metadata,error', [
    ({'title': 'Bad address', 'link': 'http://localhost/private'}, 'local reference URL'),
    ({'title': 'Bad data', 'link': 'https://example.org/ok', 'secret': 'bad'}, 'unexpected source metadata'),
])
def test_other_invalid_historical_sources_remain_blocking(project, metadata, error):
    origin(project, note=False)
    _unidentifiable_canonical(project, metadata=metadata)
    with pytest.raises(cc.CreationContextError, match=error):
        library.build_library(project, [ORIGIN])
    assert not (project/library.LIBRARY_PATH).exists()


def test_preexisting_signed_library_without_omission_field_still_loads(project):
    origin(project, note=False, source_record=True)
    library.build_library(project, [ORIGIN])
    libpath = project/library.LIBRARY_PATH
    old = load(libpath)
    old.pop('omissions')
    old['sha256'] = cc._sha(cc._json({k: v for k, v in old.items() if k != 'sha256'}))
    put(libpath, old)
    result, _ = library.load_library(project)
    assert result['notices'] and result.get('omissions', []) == []


def test_omission_report_cannot_claim_untracked_or_duplicate_source(project):
    origin(project, note=False)
    _unidentifiable_canonical(project)
    library.build_library(project, [ORIGIN])
    libpath = project/library.LIBRARY_PATH
    for modified in ('unknown-debate', 'duplicate'):
        lib = load(libpath)
        if modified == 'unknown-debate':
            lib['omissions'][0]['debate_id'] = 'other'
        else:
            lib['omissions'].append(dict(lib['omissions'][0]))
        lib['sha256'] = cc._sha(cc._json({k: v for k, v in lib.items() if k != 'sha256'}))
        put(libpath, lib)
        with pytest.raises(cc.CreationContextError, match='omission'):
            library.load_library(project)
        library.build_library(project, [ORIGIN])


def test_foreign_and_unknown_languages_are_never_treated_as_french(project):
    origin(project, note=True, language='en')
    assert library.build_library(project, [ORIGIN])['notices'] == 0
    source = project/ORIGIN/research.LEDGER_PATH
    obj = load(source)
    obj['resources'][0]['language'] = None
    # Even with a manually resealed legacy file, a resource ID must match its content.
    obj['sha256'] = cc._sha(cc._json({k:v for k,v in obj.items() if k != 'sha256'}))
    put(source, obj)
    with pytest.raises(cc.CreationContextError, match='identity was altered'):
        library.build_library(project, [ORIGIN])


def test_source_mutation_after_build_requires_rebuild(project):
    src = origin(project)
    library.build_library(project, [ORIGIN])
    scope = src/'scope.json'
    value = load(scope)
    value['scope_summary_fr'] += ' Updated.'
    put(scope, value)
    with pytest.raises(cc.CreationContextError, match='rebuild'):
        prepared(project, reuse_library=True)
    assert prepared(project)['status'] in ('prepared', 'reused')
    library.build_library(project, [ORIGIN])
    assert prepared(project, reuse_library=True)['status'] == 'prepared'


def test_prepared_return_rejects_source_or_library_change_without_mutating_target(project):
    origin(project)
    library.build_library(project, [ORIGIN])
    package = prepared(project, reuse_library=True)
    returned(project, package)
    before = snapshot(project/CORPUS)
    src = project/ORIGIN/'scope.json'
    data = load(src)
    data['scope_summary_fr'] += ' Revision'
    put(src, data)
    with pytest.raises(cc.CreationContextError, match='rebuild'):
        run_import(project)
    assert snapshot(project/CORPUS) == before
    put(src, dict(data, scope_summary_fr=data['scope_summary_fr'].replace(' Revision','')))
    lib = project/library.LIBRARY_PATH
    raw = lib.read_bytes()
    lib.write_bytes(raw + b'\n')
    with pytest.raises(cc.CreationContextError, match='library changed'):
        run_import(project)
    assert snapshot(project/CORPUS) == before


def test_library_tamper_and_insecure_permissions_are_blocked(project):
    origin(project)
    library.build_library(project, [ORIGIN])
    lib = project/library.LIBRARY_PATH
    os.chmod(lib, 0o644)
    with pytest.raises(cc.CreationContextError, match='readable'):
        prepared(project, reuse_library=True)
    os.chmod(lib, 0o600)
    data = load(lib)
    data['notices'][0]['metadata']['title'] = 'Forged authority'
    put(lib, data)
    with pytest.raises(cc.CreationContextError, match='corrupted'):
        prepared(project, reuse_library=True)


def test_unsafe_link_is_not_exported(project):
    src = origin(project)
    notes = load(src/research.LEDGER_PATH)
    notes['resources'][0]['metadata']['link'] = 'https://example.org/?api_key=secret'
    notes['sha256'] = cc._sha(cc._json({k:v for k,v in notes.items() if k != 'sha256'}))
    put(src/research.LEDGER_PATH, notes)
    with pytest.raises(cc.CreationContextError):
        library.build_library(project, [ORIGIN])
    assert not (project/library.LIBRARY_PATH).exists()


def test_invalid_sources_and_source_aliases_are_blocked(project):
    origin(project)
    with pytest.raises(cc.CreationContextError, match='distinct'):
        library.build_library(project, [ORIGIN, ORIGIN])
    with pytest.raises(cc.CreationContextError):
        library.build_library(project, ['corpus/../other'])
    with pytest.raises(cc.CreationContextError, match='foreign'):
        bad = project/ORIGIN/'manifest.json'
        obj = load(bad)
        obj['debate_id'] = 'wrong'
        put(bad, obj)
        library.build_library(project, [ORIGIN])


def test_research_only_import_cannot_treat_library_hint_as_an_observation(project):
    origin(project)
    library.build_library(project, [ORIGIN])
    package = prepared(project, reuse_library=True)
    hint = preview(project, package)[0]['page_candidates'][0]['candidates'][0]['hint_id']
    from test_wikidebia_creation_sources import chosen, review
    returned(project, package, edit_files=lambda files: files.update({
        sources.EDITABLE_PATH: cc._json(review(chosen(hint, 'Odoes-not-exist'))) }))
    before = snapshot(project/CORPUS)
    with pytest.raises(cc.CreationContextError):
        run_import(project)
    assert snapshot(project/CORPUS) == before


def test_library_export_does_not_leak_search_queries_or_full_excerpts(project):
    src = origin(project)
    saved = load(src/research.LEDGER_PATH)
    assert saved['searches'][0]['query']
    assert saved['observations'][0]['excerpt']
    library.build_library(project, [ORIGIN])
    raw = (project/library.LIBRARY_PATH).read_bytes()
    assert saved['searches'][0]['query'].encode() not in raw
    assert saved['observations'][0]['excerpt'].encode() not in raw
    preview_data, _, _ = preview(project, prepared(project, reuse_library=True))
    assert 'searched_at' not in str(preview_data)
    assert 'excerpt' not in str(preview_data)


def test_main_cli_builds_same_index_as_primitive(project, capsys):
    origin(project)
    assert manager.main(['--root', str(project), 'creation-library-build', '--corpus', ORIGIN]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['notices'] == 1
    assert manager.main(['--root', str(project), 'creation-package', '--corpus', CORPUS,
                         '--research-only', '--page-id', 'A0001', '--reuse-library']) == 0
    prepared_result = json.loads(capsys.readouterr().out)
    assert library.PREVIEW_PATH in preview(project, prepared_result)[1]


def test_library_is_never_required_for_legacy_creation_packages(project):
    package = prepared(project)
    with zipfile.ZipFile(project/package['package_path']) as z:
        assert library.PREVIEW_PATH not in z.namelist()
    assert package['status'] == 'prepared'
    assert not (project/library.LIBRARY_PATH).exists()
    returned(project, package)
    assert run_import(project)['status'] == 'no_changes'


def test_end_to_end_hint_requires_new_research_and_separate_source_review(project):
    origin(project)
    library.build_library(project, [ORIGIN])
    package = prepared(project, reuse_library=True)
    view, _, _ = preview(project, package)
    candidate = view['notices'][0]
    # This copy is explicitly a NEW discovery attempt for the target argument.
    new_research = research.empty_response()
    new_research['resources'] = [dict(resource('target-reference', title=candidate['metadata']['title'],
                                             link=candidate['metadata']['link']))]
    new_research['observations'] = [observation('A0001', 'target-reference')]
    returned(project, package, edit_files=lambda files: files.update({
        research.EDITABLE_PATH: cc._json(new_research)}))
    saved = run_import(project)
    assert saved['status'] == 'imported' and saved['sources_selected'] == {}
    assert not (project/CORPUS/sources.AUDIT_PATH).exists()
    target_notes = load(project/CORPUS/research.LEDGER_PATH)
    target_resource = target_notes['resources'][0]['id']
    target_observation = target_notes['observations'][0]['id']
    assert target_resource.startswith('R') and target_resource != candidate['hint_id']
    assert target_observation.startswith('O')
    package2 = prepared(project)
    from test_wikidebia_creation_sources import chosen, review
    returned(project, package2, filename='new-target-review.zip',
             edit_files=lambda files: files.update({sources.EDITABLE_PATH:
                 cc._json(review(chosen(target_resource, target_observation)))}))
    assert ci.import_package(project, CORPUS, archive='incoming/new-target-review.zip')['status'] == 'imported'
    assert load(project/CORPUS/'data/sources.json')['sources'][0]['metadata']['title'] == candidate['metadata']['title']


def test_shared_notices_are_emitted_once_across_many_target_pages(project):
    origin(project)
    library.build_library(project, [ORIGIN])
    package = ci.prepare_package(project, CORPUS, research_only=True,
                                 page_ids=['A0001', 'A0002', 'A0003', 'A0004'],
                                 reuse_library=True)
    view, _, _ = preview(project, package)
    ids = [c['hint_id'] for row in view['page_candidates'] for c in row['candidates']]
    assert ids
    assert len(view['notices']) == len(set(ids))
    assert package['reuse_candidate_count'] == len(ids)
    assert package['reuse_preview_bytes'] <= library.MAX_PREVIEW_BYTES
    assert 'metadata' not in str(view['page_candidates'])


def test_missing_note_becomes_present_invalidates_library(project):
    src = origin(project, note=False, source_record=True)
    library.build_library(project, [ORIGIN])
    assert prepared(project, reuse_library=True)['status'] == 'prepared'
    new_notes = {'schema': research.LEDGER_SCHEMA, 'debate_id': 'autre',
                 'resources': [], 'observations': [], 'searches': []}
    research.save_notes(src, new_notes)
    with pytest.raises(cc.CreationContextError, match='rebuild'):
        prepared(project, reuse_library=True)


def test_unsafe_private_directory_and_symlinks_are_rejected(project):
    origin(project)
    private = project/'private'
    private.mkdir(mode=0o755)
    os.chmod(private, 0o755)
    with pytest.raises(cc.CreationContextError, match='private/'):
        library.build_library(project, [ORIGIN])
    private.rmdir()
    external = project/'outside-private'
    external.mkdir()
    private.symlink_to(external, target_is_directory=True)
    with pytest.raises(cc.CreationContextError):
        library.build_library(project, [ORIGIN])


@pytest.mark.parametrize('query', ['', ' '*30, 'x'*161, '\x00injected'])
def test_reuse_query_bounds_are_checked(project, query):
    origin(project)
    library.build_library(project, [ORIGIN])
    with pytest.raises(cc.CreationContextError, match='invalid reuse search phrase'):
        prepared(project, reuse_library=True, reuse_query=query)


def test_discovered_but_not_consulted_source_is_a_hint_not_a_verified_source(project):
    src = origin(project, note=False)
    manifest = load(src/'manifest.json')
    registry = load(src/'data/registre_debat.json')
    scope = load(src/'scope.json')
    canonical = load(src/'data/sources.json')
    payload = dict(research.empty_response(),
                   resources=[resource(title='Reason 1 and documentary knowledge')],
                   searches=[search(outcome='found', refs=['r1'])])
    empty = {'schema': research.LEDGER_SCHEMA, 'debate_id': 'autre',
             'resources': [], 'observations': [], 'searches': []}
    data, _ = research.merge_response(payload, empty, {'A0001'},
        research.basis(manifest, registry, scope), canonical)
    research.save_notes(src, data)
    library.build_library(project, [ORIGIN])
    row = entries(project)[0]
    assert row['origins'][0]['prior_record'] == 'search_result'
    assert row['origins'][0]['assessment'] == 'unassessed'
    view, _, _ = preview(project, prepared(project, reuse_library=True))
    assert view['not_verified_for_target'] and view['notices']
    assert view['notices'][0]['requires_new_target_observation_and_review']
