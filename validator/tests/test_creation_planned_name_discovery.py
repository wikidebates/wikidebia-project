"""Only a physically absent, unproduced French creation page defers research."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from wikidebia_validator.coherence import validate_argument_name_discovery
from wikidebia_validator.package import PackageContext
from wikidebia_validator.report import Report


def write(root, rel, value):
    path = root/rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value)+"\n")


def data():
    wiki = {'check_status': 'unchecked', 'decision': None, 'remote_revision_id': None,
            'remote_sha256': None, 'published_at': None, 'checked_at': None, 'remote_title': None}
    page = {'page_id': 'A0001', 'page_type': 'argument', 'page_origin': 'new', 'language': 'fr',
            'status': 'planned', 'file_path': 'output/fr/arguments/A0001.wiki', 'sha256': None,
            'creation_date': None, 'wiki': dict(wiki), 'validation': {'status': 'pending'}}
    manifest = {'debate_id': 'example', 'global_status': 'graph_locked', 'translation_status': {'en': 'deferred'},
                'pages': [page]}
    record = {'file': {'path': page['file_path'], 'status': 'absent', 'sha256': None},
              'generation': {'status': 'pending', 'creation_date': None, 'generated_at': None, 'validated_at': None}, 'wiki': dict(wiki)}
    registry = {'graph': {'nodes': [{'id': 'A0001', 'status': 'active', 'pages': {'fr': record}}]}}
    return manifest, registry, page, record


def run(root, manifest, registry):
    write(root, 'manifest.json', manifest); write(root, 'data/registre_debat.json', registry)
    report = Report('test', str(root), ['coherence'])
    validate_argument_name_discovery(PackageContext(root, report), manifest)
    return report


@pytest.mark.parametrize('status', ['initialized', 'graph_draft', 'graph_validated', 'graph_locked'])
def test_only_precontent_absent_fr_pages_can_defer(tmp_path, status):
    m,r,p,n = data(); m['global_status'] = status
    assert run(tmp_path,m,r).errors == 0


@pytest.mark.parametrize('case', ['english', 'not_deferred', 'generated', 'validated', 'assigned', 'later_stage',
                                 'existing_text', 'hash', 'date', 'validation', 'record_missing', 'record_file',
                                 'record_hash', 'record_status', 'record_date', 'record_time', 'record_validated',
                                 'record_path', 'wiki_remote', 'record_remote', 'imported', 'content_lock'])
def test_documentary_requirement_never_silently_waived(tmp_path, case):
    m,r,p,n = data()
    if case == 'english': p['language'] = 'en'
    if case == 'not_deferred': m['translation_status']['en'] = 'ready'
    if case in {'generated', 'validated', 'assigned'}: p['status'] = case
    if case == 'later_stage': m['global_status'] = 'fr_content_complete'
    if case == 'existing_text': write(tmp_path,p['file_path'], 'existing text')
    if case == 'hash': p['sha256'] = 'f'*64
    if case == 'date': p['creation_date'] = '2026-11-21'
    if case == 'validation': p['validation']['status'] = 'passed'
    if case == 'record_missing': r['graph']['nodes'] = []
    if case == 'record_file': n['file']['status'] = 'present'
    if case == 'record_hash': n['file']['sha256'] = 'f'*64
    if case == 'record_status': n['generation']['status'] = 'generated'
    if case == 'record_date': n['generation']['creation_date'] = '2026-11-21'
    if case == 'record_time': n['generation']['generated_at'] = '2026-11-21T00:00:00Z'
    if case == 'record_validated': n['generation']['validated_at'] = '2026-11-21T00:00:00Z'
    if case == 'record_path': n['file']['path'] = 'other.wiki'
    if case == 'wiki_remote': p['wiki']['remote_revision_id'] = 42
    if case == 'record_remote': n['wiki']['remote_revision_id'] = 42
    if case == 'imported': write(tmp_path,'data/import_provenance.json', {})
    if case == 'content_lock': write(tmp_path,'data/fr_content_lock.json', {})
    assert any(f.code == 'WDV-EDT-032' for f in run(tmp_path,m,r).findings)


def test_explicit_review_is_still_checked(tmp_path):
    m,r,p,n = data()
    m['editorial_controls'] = {'argument_name_discovery_path': 'reviews/discovery.json'}
    write(tmp_path,'reviews/discovery.json', {'debate_id':'example', 'entries': []})
    assert run(tmp_path,m,r).errors
