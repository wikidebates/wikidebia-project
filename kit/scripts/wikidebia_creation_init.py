#!/usr/bin/env python3
"""Initialize a new French corpus from a locally bound, explicitly reviewed plan.

No wiki snapshot is fabricated. A plan is not an approval. Only the returned
review can lock its exact structure; page generation/validation remain pending.
"""
from __future__ import annotations

import argparse
import copy
import ctypes
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unicodedata
import uuid
from typing import Any

from wikidebia_creation_context import CreationContextError, _json, _sha, build_creation_context
from wikidebia_creation_import import (
    PACKAGE_SCHEMA, FILE_LIMIT, _path, _read, _tree, _write, _seal, _load, _lock,
    _locations, _sync_dir, _now, _zip_files, assert_no_pending_import, prepare_package,
)
from wikidebia_corpus_init import make_empty_page_record, derive_short_code, _markdown_graph
from wikidebia_corpus_build import prepare_placement_review, placement_review_issues, CorpusBuildError
from wikidebia_graph_correction import _validate_and_rebuild
from wikidebia_release_info import NORM_VERSION, VALIDATOR_VERSION, KIT_VERSION

PLAN_SCHEMA = 'wikidebia-creation-plan-1.0'
REVIEW_SCHEMA = 'wikidebia-creation-plan-review-1.0'
REQUEST_SCHEMA = 'wikidebia-creation-init-request-1.0'
RECEIPT_SCHEMA = 'wikidebia-creation-init-receipt-1.0'
RECEIPT_PATH = 'reports/creation_init_receipt.json'
REVIEW_PATH = 'editable/REVIEW.json'
SCOPES = ['schema', 'coherence', 'graph', 'batches', 'files', 'workflow']
ATTESTATIONS = ('scope_and_proposition_reviewed', 'graph_completeness_reviewed',
                'reuse_and_occurrences_reviewed', 'titles_reviewed', 'batches_reviewed',
                'new_corpus_confirmed', 'no_page_validation_or_publication_authorized')
SOURCE_ROOT = Path(__file__).resolve().parents[2]


def require(ok: bool, message: str) -> None:
    if not ok:
        raise CreationContextError('Creation initialization: ' + message)


def obj(value: Any, fields: set[str]) -> dict:
    require(isinstance(value, dict) and set(value) == fields, 'unexpected or missing fields')
    return value


def text(value: Any, minimum: int = 1) -> str:
    require(isinstance(value, str) and len(value.strip()) >= minimum and '\x00' not in value,
            'missing text or rationale')
    return value


def unique(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def parse(raw: bytes) -> dict:
    value = json.loads(raw, object_pairs_hook=unique,
                       parse_constant=lambda v: require(False, 'non-finite JSON value'))
    require(isinstance(value, dict), 'expected a JSON object')
    return value


def strings(value: Any) -> list[str]:
    require(isinstance(value, list) and all(isinstance(v, str) and v.strip() for v in value),
            'expected a list of nonempty strings')
    require(len(set(value)) == len(value), 'duplicate list entry')
    return value


def _validator():
    path = SOURCE_ROOT / 'validator/src'
    require(path.is_dir(), 'installed validator missing')
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    from wikidebia_validator.validator import validate_package
    return validate_package


def _validate(folder: Path) -> dict:
    report = _validator()(folder, scopes=SCOPES)
    payload = report.to_dict()
    _write(folder / 'reports/creation_structure.json', _json(payload))
    require(not report.errors, 'structural validation failed: ' + '; '.join(
        f'{f.code}: {f.message}' for f in report.findings if f.level == 'ERROR')[:2000])
    return payload


def _diagnostic(root: Path, folder: Path, plan: dict, error: Exception) -> str:
    """Retain the concrete failed report before a temporary candidate is removed."""
    from wikidebia_review_workflow import _write_deterministic_zip
    report_path = folder / 'reports/creation_structure.json'
    report = _read(report_path) if report_path.is_file() else _json({'error': str(error)})
    key = _sha(_json(plan) + report)[:20]
    target = _path(root, f"outgoing/{plan['debate_id']}_creation_init_diagnostic_{key}.zip")
    if not target.exists():
        with tempfile.TemporaryDirectory(dir=folder.parent, prefix='.diagnostic-') as temp:
            temp = Path(temp)
            _write(temp/'PLAN.json', _json(plan))
            _write(temp/'VALIDATION_REPORT.json', report)
            _write(temp/'INSTRUCTIONS.md', ('# Diagnostic de creation\n\n' + str(error) +
                '\nCorriger le plan puis refaire creation-prepare. Ce ZIP ne constitue pas une approbation.\n').encode())
            _write_deterministic_zip(temp, target)
    return target.relative_to(root).as_posix()


def _title(value: Any) -> str:
    text(value)
    require(value == unicodedata.normalize('NFC', value) and value == ' '.join(value.split())
            and len(value.encode('utf-8')) <= 255 and not any(c in value for c in '[]{}|#<>_\n\r')
            and not any(c in value for c in '\u2019\u2018\u02bc\uff07\u00ab\u00bb\u201c\u201d\u201e\u201f\u2039\u203a')
            and not value.endswith('.') and '...' not in value and '\u2026' not in value
            and value.count('"') % 2 == 0, 'title needs an explicit correction (no silent normalization)')
    return value


def _build(plan: dict, timestamp: str) -> dict[str, bytes]:
    obj(plan, {'schema', 'debate_id', 'scope', 'nodes', 'placements', 'batches'})
    require(plan['schema'] == PLAN_SCHEMA, 'unsupported plan schema')
    did = plan['debate_id']
    require(isinstance(did, str) and bool(re.fullmatch(r'[a-z0-9][a-z0-9_-]{1,63}', did)), 'invalid debate_id')
    scope_fields = {'canonical_title_fr', 'proposition_fr', 'scope_summary_fr', 'jurisdiction',
                    'timeframe', 'included_topics', 'excluded_topics', 'residual_ambiguities',
                    'editorial_constraints'}
    scope = copy.deepcopy(obj(plan['scope'], scope_fields))
    title = _title(scope['canonical_title_fr'])
    for field in ('proposition_fr', 'scope_summary_fr'):
        text(scope[field])
    for field in ('jurisdiction', 'timeframe'):
        require(scope[field] is None or isinstance(scope[field], str), 'invalid scope field')
    for field in ('included_topics', 'excluded_topics', 'residual_ambiguities', 'editorial_constraints'):
        strings(scope[field])
    scope.update(scope_schema_version='1.0', debate_id=did, related_debates=[],
                 source_documents=[{'path': 'data/creation_plan.json', 'sha256': _sha(_json(plan))}])
    require(isinstance(plan['nodes'], list) and bool(plan['nodes']), 'empty or invalid node inventory')
    nodes, ids, titles = [], set(), {title.casefold()}
    for row in plan['nodes']:
        obj(row, {'id', 'canonical_title_fr', 'displayed_title_fr', 'rubriques', 'keywords'})
        nid = row['id']
        require(isinstance(nid, str) and bool(re.fullmatch(r'A\d{4,}', nid)) and nid not in ids,
                'duplicate or invalid node id')
        canonical, displayed = _title(row['canonical_title_fr']), _title(row['displayed_title_fr'])
        require(canonical.casefold() not in titles, 'canonical title collision, including debate title')
        ids.add(nid)
        titles.add(canonical.casefold())
        nodes.append({'id': nid, 'status': 'active',
                      'fr': {'canonical_title': canonical, 'displayed_title': displayed, 'title_status': 'draft',
                             'rubriques': strings(row['rubriques']), 'keywords': strings(row['keywords'])},
                      'en': {'canonical_title': None, 'displayed_title': None, 'title_status': 'unassigned',
                             'sections': [], 'keywords': []},
                      'pages': {lang: make_empty_page_record(f'output/{lang}/arguments/{nid}.wiki',
                                                           interlanguage=lang == 'fr') for lang in ('fr', 'en')},
                      'sources': {lang: {'bibliography': [], 'webliography': [], 'videography': []}
                                  for lang in ('fr', 'en')}})
    rows = plan['placements']
    require(isinstance(rows, list) and bool(rows), 'missing placements')
    oids = set()
    for row in rows:
        obj(row, {'occurrence_id', 'node_id', 'parent_occurrence_id', 'relation', 'branch', 'order', 'occurrence_role'})
        oid = row['occurrence_id']
        require(isinstance(oid, str) and bool(re.fullmatch(r'O\d{4,}', oid)) and oid not in oids,
                'invalid or duplicate occurrence id')
        oids.add(oid)
        require(isinstance(row['node_id'], str) and row['node_id'] in ids, 'unknown occurrence node')
        require(type(row['order']) is int and row['order'] >= 1, 'order must be a positive integer')
        require(row['parent_occurrence_id'] is None or isinstance(row['parent_occurrence_id'], str), 'invalid parent')
    graph = {'nodes': nodes, 'edges': [], 'occurrences': [
        {'id': r['occurrence_id'], 'node_id': r['node_id']} for r in rows]}
    # Reuse the existing reconstruction of edges, depths, roles and derived counts.
    edges, occurrences, derived = _validate_and_rebuild({'graph': graph}, {'placements': copy.deepcopy(rows)})
    for edge in edges:
        edge['introduced_in_pass'] = 'creation_plan'
    graph.update(edges=edges, occurrences=occurrences, nodes=derived['nodes'], derived_counts=derived['counts'],
                 lifecycle={'status': 'draft', 'validated_at': None, 'locked_at': None,
                            'locked_by_stage': None, 'structural_sha256': None},
                 depth_policy={'limit_policy': 'unbounded', 'maximum_observed': derived['counts']['maximum_depth']})
    nodes = graph['nodes']
    # No user-entered paths or progress fields are accepted in a creation plan.
    labels = {'fr': {'pro': 'Arguments pour', 'con': 'Arguments contre'}, 'en': {'pro': None, 'con': None}}
    debate_pages = {lang: dict(make_empty_page_record(f'output/{lang}/debate/debate.wiki', interlanguage=lang == 'fr'),
                              canonical_title=title if lang == 'fr' else None,
                              title_status='draft' if lang == 'fr' else 'unassigned') for lang in ('fr', 'en')}
    registry = {'schema': {'registry_version': '1.0', 'graph_version': '1.0', 'mediawiki_structure_version': '1.0',
                           'render_profile_version': '1.0', 'validator_version': VALIDATOR_VERSION},
                'debate': {'id': did, 'scope': {k: scope[k] for k in ('proposition_fr', 'scope_summary_fr',
                            'jurisdiction', 'timeframe', 'included_topics', 'excluded_topics', 'residual_ambiguities')},
                          'labels': labels, 'pages': debate_pages},
                'graph': graph, 'batches': [], 'validations': [], 'migrations': []}
    require(isinstance(plan['batches'], list) and bool(plan['batches']), 'explicit batch composition required')
    covered = set()
    by_node = {n['id']: n for n in nodes}
    for index, row in enumerate(plan['batches'], 1):
        obj(row, {'node_ids', 'dependency_node_ids'})
        members, deps = strings(row['node_ids']), strings(row['dependency_node_ids'])
        require(bool(members) and set(members) <= ids and not set(members) & covered, 'invalid batch ownership')
        require(set(deps) <= covered, 'dependencies must belong to earlier batches (no scheduling deadlock)')
        bid = f'FR-A-{index:03d}'
        for nid in members:
            by_node[nid]['pages']['fr']['generation']['assigned_batch_id'] = bid
        registry['batches'].append({'batch_schema_version': '1.0', 'id': bid, 'debate_id': did,
            'language': 'fr', 'page_type': 'argument', 'strategy': 'manual_editorial',
            'root_node_ids': [r['node_id'] for r in occurrences if r['depth'] == 1 and r['node_id'] in members],
            'node_ids': members, 'dependency_node_ids': deps, 'status': 'planned',
            'inputs': {'registry_sha256': None, 'structural_sha256': None, 'render_profile_version': '1.0', 'handoff_path': None},
            'outputs': {'individual_directory': 'output/fr/arguments', 'aggregate_path': f'output/fr/aggregates/{bid}.wiki',
                        'aggregate_sha256': None, 'report_path': f'reports/{bid}.json'},
            'work': {'work_id': f'CREATION-{bid}', 'conversation_name': f'Arguments FR {bid}',
                     'started_at': None, 'completed_at': None}})
        covered.update(members)
    require(covered == ids, 'batches must cover each node exactly once')
    pages = []
    for pid, rec, canonical in [(did, debate_pages['fr'], title)] + [
            (n['id'], n['pages']['fr'], n['fr']['canonical_title']) for n in nodes]:
        pages.append({'page_manifest_version': '1.0', 'debate_id': did, 'page_id': pid,
                      'page_type': 'debate' if pid == did else 'argument', 'language': 'fr',
                      'canonical_title': canonical, 'file_path': rec['file']['path'], 'sha256': None,
                      'creation_date': None, 'batch_id': rec['generation']['assigned_batch_id'],
                      'page_origin': 'new', 'status': 'planned', 'structure_version': '1.0', 'render_profile_version': '1.0',
                      'validation': {'status': 'pending', 'report_path': None, 'validated_at': None}, 'wiki': rec['wiki']})
    manifest = {'package_schema_version': '1.0', 'debate_id': did, 'short_code': derive_short_code(did),
                'global_status': 'graph_draft', 'created_at': timestamp, 'updated_at': timestamp,
                'normative_versions': {'consolidated_norm': NORM_VERSION, 'mediawiki_structure': '1.0',
                                       'render_profile': '1.0', 'registry': '1.0', 'graph': '1.0',
                                       'workflow': '1.0', 'validator': VALIDATOR_VERSION},
                'translation_status': {'en': 'deferred'},
                'core_files': {'scope': 'scope.json', 'registry': 'data/registre_debat.json',
                               'graph_json': 'graph/graphe_argumentatif.json', 'graph_markdown': 'graph/graphe_argumentatif.md',
                               'sources': 'data/sources.json'}, 'pages': pages, 'batches': registry['batches'],
                'works': [], 'validations': [],
                'release': {k: None for k in ('release_manifest_path', 'release_zip_path', 'released_at', 'archived_at', 'release_receipt_path')},
                'editorial_controls': {'graph_placement_review_path': 'reviews/graph_placement_review.json',
                    'creation_date': timestamp[:10], 'creation_date_policy': 'per_page_preserved',
                    'individual_review_path': 'reviews/individual_review.json',
                    'individual_review_report_path': 'reports/individual_review.json',
                    'keyword_vocabulary_path': 'data/keyword_vocabulary.json',
                    'introduction_review_path': 'reviews/introduction_review.json',
                    'required_reports': ['reports/creation_structure.json'],
                    'introduction_references': {'required': True},
                    'debate_documentation': {'min_subsections': 1, 'min_references': 0,
                        'reject_singleton_bucket_pattern': False,
                        'profile_rationale': 'Documentation proportionate to the subject; no artificial reference quota.'}}}
    docs = {'manifest.json': manifest, 'scope.json': scope, 'data/registre_debat.json': registry,
            'data/creation_plan.json': plan,
            'data/sources.json': {'source_registry_version': '1.0', 'debate_id': did, 'sources': []},
            'data/lots_fr.json': {'batch_collection_version': '1.0', 'debate_id': did, 'language': 'fr', 'batches': registry['batches']},
            'graph/graphe_argumentatif.json': {'graph_schema_version': '1.0',
                'debate': {'id': did, 'title_fr': title, 'labels': labels}, **graph}}
    files = {name: _json(value) for name, value in docs.items()}
    files['graph/graphe_argumentatif.md'] = _markdown_graph(title, nodes, edges, occurrences, derived['counts']).encode()
    return files


def _producer_basis() -> dict[str, str]:
    paths = list((SOURCE_ROOT / 'validator/src').rglob('*.py')) + list((SOURCE_ROOT / 'validator/src').rglob('*.json'))
    paths += list((SOURCE_ROOT / 'kit/scripts').glob('wikidebia_creation*.py'))
    paths += [SOURCE_ROOT / ('kit/scripts/' + name + '.py') for name in (
        'wikidebia_corpus_init', 'wikidebia_corpus_build', 'wikidebia_graph_correction',
        'wikidebia_review_workflow', 'wikidebia_release_info')]
    paths += [SOURCE_ROOT / 'kit/VERSIONS.json', SOURCE_ROOT / 'validator/VERSIONS.json']
    return {p.relative_to(SOURCE_ROOT).as_posix(): _sha(_read(p)) for p in sorted(paths)}


def _rename_new(source: Path, target: Path) -> None:
    """Linux no-replace directory rename: even a concurrent empty target is safe."""
    libc = ctypes.CDLL(None, use_errno=True)
    require(hasattr(libc, 'renameat2'), 'atomic no-replace installation requires Linux renameat2')
    fn = libc.renameat2
    fn.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    fn.restype = ctypes.c_int
    if fn(-100, os.fsencode(source), -100, os.fsencode(target), 1) != 0:
        code = ctypes.get_errno()
        raise OSError(code, 'No-replace installation refused: ' + os.strerror(code))
    _sync_dir(target.parent)
    if source.parent != target.parent:
        _sync_dir(source.parent)


def _check_inputs(root: Path, request: dict) -> None:
    require(_producer_basis() == request['producer'], 'producer changed; prepare a new review')
    for path, digest in request['inputs'].items():
        require(_sha(_read(_path(root, path))) == digest, 'plan or normative input changed; prepare a new review')


def _review_template(plan: dict, registry: dict, package_id: str) -> dict:
    return {'schema': REVIEW_SCHEMA, 'package_id': package_id, 'plan_sha256': _sha(_json(plan)),
            'decision': 'pending', 'reviewer': '', 'reviewed_at': None, 'scope_rationale': '',
            'attestations': {k: False for k in ATTESTATIONS}, 'blocking_issues': [],
            'titles': [{'node_id': n['id'], 'canonical_title': n['fr']['canonical_title'],
                        'displayed_title': n['fr']['displayed_title'], 'canonical_autonomy': False,
                        'complete_displayed_proposition': False, 'semantic_equivalence': False, 'rationale': ''}
                       for n in registry['graph']['nodes']],
            'placement_review': prepare_placement_review(registry, plan['debate_id'])}


def _export(root: Path, folder: Path, request: dict) -> str:
    target = _path(root, request['outgoing_path'])
    raw = _read(folder / 'package.zip')
    require(_sha(raw) == request['archive_sha256'], 'stored package changed')
    if target.exists():
        require(_read(target) == raw, 'outgoing package changed; preserve it and use the prepared original')
    else:
        _write(target, raw)
    return target.relative_to(root).as_posix()


def prepare(project_root: Path, plan_path: str) -> dict:
    from wikidebia_review_workflow import _package_manifest_hash, _write_deterministic_zip
    root = project_root.resolve()
    require(plan_path.startswith('incoming/') and plan_path.endswith('.json'), 'use incoming/<plan>.json')
    plan_file = _path(root, plan_path)
    raw = _read(plan_file, FILE_LIMIT)
    plan = parse(raw)
    timestamp = _now()
    files = _build(plan, timestamp)
    did = plan['debate_id']
    target, control = _locations(root, 'corpus/' + did)
    with _lock(root, control):
        assert_no_pending_import(root, 'corpus/' + did)
        require(not target.exists(), 'corpus already exists; initialization never replaces it')
        context = build_creation_context(root, 'graphe')
        context_dir = _path(root, context['context_path'])
        norm_manifest = parse(_read(context_dir / 'CONTEXT_MANIFEST.json'))
        inputs = {r['path']: r['sha256'] for r in norm_manifest['inputs']}
        inputs[plan_path] = _sha(raw)
        producer = _producer_basis()
        package_id = str(uuid.uuid5(uuid.NAMESPACE_URL, _sha(_json([inputs, producer]))))
        parent = _path(root, '.state/creation-init/' + did)
        parent.mkdir(parents=True, exist_ok=True)
        folder = _path(root, parent.relative_to(root).as_posix() + '/' + package_id)
        if folder.exists():
            request = _load(folder / 'request.json', REQUEST_SCHEMA)
            _check_inputs(root, request)
            require(_tree(folder / 'candidate') == request['candidate_sha256'], 'prepared candidate changed')
            return {'status': 'reused', 'debate_id': did, 'package_path': _export(root, folder, request),
                    'corpus_created': False, 'publication_authorized': False}
        staging = Path(tempfile.mkdtemp(prefix='.preparing-', dir=parent))
        try:
            candidate = staging / 'candidate'
            for name, content in files.items():
                _write(candidate / name, content)
            try:
                _validate(candidate)
            except CreationContextError as exc:
                diagnostic = _diagnostic(root, candidate, plan, exc)
                raise CreationContextError(str(exc) + '; diagnostic: ' + diagnostic) from exc
            registry = parse(files['data/registre_debat.json'])
            review = _review_template(plan, registry, package_id)
            bundle = {REVIEW_PATH: _json(review), 'context/PLAN.json': _json(plan),
                      'context/GRAPH.md': files['graph/graphe_argumentatif.md'],
                      'context/BATCHES.json': files['data/lots_fr.json'],
                      'context/NORMATIVE_CONTEXT.md': _read(context_dir / 'NORMATIVE_CONTEXT.md'),
                      'context/STRUCTURAL_REPORT.json': _read(candidate / 'reports/creation_structure.json')}
            instructions = (
                '# Revue du plan de creation\n\n'
                'Lire PLAN.json, GRAPH.md, BATCHES.json et NORMATIVE_CONTEXT.md sous context/.\n'
                'Modifier seulement editable/REVIEW.json. Examiner cadrage, omissions, titres,\n'
                'placements de chaque occurrence et composition/ordre des lots.\n'
                'Une decision approved exige une revue reelle, nommee, datee et motivee.\n'
                'Ne jamais cocher automatiquement les attestations. Un refus ne cree aucun corpus.\n'
                'Si un titre ou placement doit changer, rejeter puis corriger le plan original et\n'
                'relancer creation-prepare : chaque nouveau plan exige une nouvelle revue complete.\n'
                'Aucun texte, source, date de creation ou accord de publication n\'est fabrique.\n'
                'Les controles structurels ne prouvent pas la qualite semantique de la revue.\n'
                'Rendre le ZIP complet dans incoming/, puis : ./wikidebia creation-init\n'
            ).encode()
            bundle['INSTRUCTIONS.md'] = instructions
            manifest = {'schema': PACKAGE_SCHEMA, 'schema_version': '1.0', 'package_id': package_id,
                'review_type': 'fr_creation_graph', 'debate_id': did, 'work_id': None,
                'normative_revision': NORM_VERSION, 'validator_version': VALIDATOR_VERSION,
                'kit_version': KIT_VERSION, 'prepared_at': timestamp, 'source_anchor_sha256': _tree(candidate),
                'editable_files': [{'package_path': REVIEW_PATH, 'target_path': 'reviews/creation_plan_review.json',
                                    'sha256_at_prepare': _sha(bundle[REVIEW_PATH])}],
                'context_files': [{'package_path': name, 'target_path': name[len('context/'):], 'sha256': _sha(content)}
                                  for name, content in bundle.items() if name.startswith('context/')],
                'counts': {'nodes': len(plan['nodes']), 'occurrences': len(plan['placements'])},
                'instructions_sha256': _sha(instructions)}
            manifest['manifest_sha256'] = _package_manifest_hash(manifest)
            bundle['REVIEW_PACKAGE.json'] = _json(manifest)
            package = staging / 'bundle'
            for name, content in bundle.items():
                _write(package / name, content)
            _write_deterministic_zip(package, staging / 'package.zip')
            _zip_files(_read(staging / 'package.zip'))
            shutil.rmtree(package)
            request = _seal({'schema': REQUEST_SCHEMA, 'manifest': manifest, 'inputs': inputs, 'producer': producer,
                'candidate_sha256': _tree(candidate), 'files': {name: _sha(content) for name, content in bundle.items()},
                'archive_sha256': _sha(_read(staging / 'package.zip')),
                'outgoing_path': f'outgoing/{did}_creation_plan_{package_id}.zip'})
            _write(staging / 'request.json', _json(request))
            _check_inputs(root, request)
            require(not target.exists(), 'corpus appeared during preparation')
            _rename_new(staging, folder)
            return {'status': 'prepared', 'debate_id': did, 'package_path': _export(root, folder, request),
                    'corpus_created': False, 'publication_authorized': False}
        finally:
            if staging.exists():
                shutil.rmtree(staging)


def _review(value: dict, plan: dict, registry: dict, package_id: str, prepared_at: str) -> bool:
    template = _review_template(plan, registry, package_id)
    obj(value, set(template))
    for key in ('schema', 'package_id', 'plan_sha256'):
        require(value[key] == template[key], 'foreign review identity')
    require(value['decision'] in ('approved', 'rejected'), 'review still pending')
    text(value['reviewer'], 2)
    when = dt.datetime.fromisoformat(text(value['reviewed_at']).replace('Z', '+00:00'))
    require(when.utcoffset() is not None and dt.datetime.fromisoformat(prepared_at) <= when <= dt.datetime.now(dt.timezone.utc),
            'review timestamp is undated, predates preparation or is in the future')
    text(value['scope_rationale'], 24)
    strings(value['blocking_issues'])
    if value['decision'] == 'rejected':
        require(bool(value['blocking_issues']), 'rejection must explain its blockers')
        return False
    require(not value['blocking_issues'], 'approved review contains blockers')
    obj(value['attestations'], set(ATTESTATIONS))
    require(all(v is True for v in value['attestations'].values()), 'incomplete review attestations')
    titles = value['titles']
    require(isinstance(titles, list) and len(titles) == len(template['titles']), 'title coverage differs')
    rows = {}
    for row in titles:
        obj(row, set(template['titles'][0]))
        require(isinstance(row['node_id'], str) and row['node_id'] not in rows, 'duplicate title review')
        rows[row['node_id']] = row
    require(set(rows) == {r['node_id'] for r in template['titles']}, 'foreign title review')
    for expected in template['titles']:
        row = rows[expected['node_id']]
        require(all(row[k] == expected[k] for k in ('node_id', 'canonical_title', 'displayed_title')), 'review changed a title')
        require(all(row[k] is True for k in ('canonical_autonomy', 'complete_displayed_proposition', 'semantic_equivalence')),
                'incomplete title review')
        text(row['rationale'], 24)
    issues = placement_review_issues(value['placement_review'], registry)
    require(not issues, 'placement review incomplete or rejected: ' + str(issues[:5]))
    return True


def _returned(root: Path, archive: str | None) -> tuple[bytes, dict[str, bytes]]:
    incoming = _path(root, 'incoming')
    if archive is not None:
        require(archive.startswith('incoming/') and archive.endswith('.zip'), 'use incoming/<return>.zip')
        raw = _read(_path(root, archive))
        return raw, _zip_files(raw)
    candidates = []
    for path in sorted(incoming.glob('*.zip')):
        raw = _read(_path(root, path.relative_to(root).as_posix()))
        files = _zip_files(raw)
        manifest = parse(files['REVIEW_PACKAGE.json']) if 'REVIEW_PACKAGE.json' in files else {}
        if manifest.get('review_type') == 'fr_creation_graph':
            candidates.append((raw, files))
    require(len(candidates) == 1, 'select a single creation-plan ZIP using --archive incoming/<return>.zip')
    return candidates[0]


def _inventory(folder: Path) -> dict[str, str]:
    _tree(folder)  # Apply the shared file/link/private-data guards first.
    return {p.relative_to(folder).as_posix(): _sha(_read(p)) for p in sorted(folder.rglob('*'))
            if p.is_file() and p.relative_to(folder).as_posix() != RECEIPT_PATH}


def _lock_graph(stage: Path, review: dict, timestamp: str) -> None:
    registry = parse(_read(stage / 'data/registre_debat.json'))
    manifest = parse(_read(stage / 'manifest.json'))
    # Record an actually executed structural check, never a fabricated page check.
    before = _tree(stage)
    report = _validate(stage)
    from wikidebia_validator.graph import structural_sha256
    require(not report['summary']['warnings'], 'resolve structural warnings before locking the graph')
    _write(stage / 'reports/creation_graph_preflight.json', _json(report))
    validation = {'id': 'V' + timestamp[:10].replace('-', '') + '-001', 'scope': 'graph', 'language': None,
                  'validator_version': VALIDATOR_VERSION, 'executed_at': timestamp, 'input_sha256': before,
                  'result': 'passed', 'blocking_errors': 0, 'warnings': 0,
                  'report_path': 'reports/creation_graph_preflight.json'}
    manifest.update(global_status='graph_locked', updated_at=timestamp, validations=[validation])
    registry['validations'] = [validation]
    registry['debate']['pages']['fr']['title_status'] = 'locked'
    for node in registry['graph']['nodes']:
        node['fr']['title_status'] = 'locked'
    digest = structural_sha256(registry)
    registry['graph']['lifecycle'].update(status='locked', validated_at=timestamp, locked_at=timestamp,
                                          locked_by_stage='creation_plan_review', structural_sha256=digest)
    for batch in registry['batches']:
        batch['inputs']['structural_sha256'] = digest
    manifest['batches'] = registry['batches']
    projection = parse(_read(stage / 'graph/graphe_argumentatif.json'))
    projection.update(registry['graph'])
    for name, value in {'manifest.json': manifest, 'data/registre_debat.json': registry,
                        'graph/graphe_argumentatif.json': projection,
                        'data/lots_fr.json': {'batch_collection_version': '1.0', 'debate_id': manifest['debate_id'],
                                             'language': 'fr', 'batches': registry['batches']},
                        'reviews/creation_plan_review.json': review,
                        'reviews/graph_placement_review.json': review['placement_review']}.items():
        _write(stage / name, _json(value))
    report = _validate(stage)
    require(not report['summary']['warnings'], 'locked corpus has unresolved structural warnings')


def initialize(project_root: Path, archive: str | None = None) -> dict:
    root = project_root.resolve()
    raw, files = _returned(root, archive)
    manifest = parse(files.get('REVIEW_PACKAGE.json', b'{}'))
    require(manifest.get('schema') == PACKAGE_SCHEMA and manifest.get('review_type') == 'fr_creation_graph', 'not a creation-plan return')
    did = manifest.get('debate_id')
    require(isinstance(did, str), 'missing debate identity')
    target, control = _locations(root, 'corpus/' + did)
    package_id = manifest.get('package_id')
    require(isinstance(package_id, str) and str(uuid.UUID(package_id)) == package_id, 'invalid package id')
    folder = _path(root, f'.state/creation-init/{did}/{package_id}')
    with _lock(root, control):
        assert_no_pending_import(root, 'corpus/' + did)
        request = _load(folder / 'request.json', REQUEST_SCHEMA)
        require(manifest == request['manifest'] and set(files) == set(request['files']), 'foreign or incomplete return')
        for name, digest in request['files'].items():
            if name != REVIEW_PATH:
                require(_sha(files[name]) == digest, 'immutable package file changed: ' + name)
        # Compare the logical ZIP contents, allowing harmless recompression only.
        response_sha = _sha(_json({k: _sha(v) for k, v in sorted(files.items())}))
        if target.exists():
            receipt = _load(_path(root, 'corpus/' + did + '/' + RECEIPT_PATH), RECEIPT_SCHEMA)
            require(receipt['package_id'] == package_id and receipt['response_sha256'] == response_sha,
                    'existing corpus belongs to another initialization; never replace it')
            return {'status': 'already_initialized', 'debate_id': did, 'corpus_path': 'corpus/' + did,
                    'current_state_matches_receipt': _inventory(target) == receipt['files'],
                    'publication_authorized': False, 'next_command': './wikidebia creation-package --corpus corpus/' + did}
        _check_inputs(root, request)
        candidate = folder / 'candidate'
        require(_tree(candidate) == request['candidate_sha256'], 'prepared candidate changed')
        plan = parse(files['context/PLAN.json'])
        registry = parse(_read(candidate / 'data/registre_debat.json'))
        review = parse(files[REVIEW_PATH])
        if review.get('decision') == 'approved':
            require(not any((folder / 'rejections').glob('*.json')),
                    'this plan was rejected; correct the original plan and prepare a new complete review')
        if not _review(review, plan, registry, package_id, manifest['prepared_at']):
            _write(folder / 'rejections' / (response_sha + '.json'), _json(review))
            return {'status': 'review_rejected', 'debate_id': did, 'corpus_created': False,
                    'blocking_issues': review['blocking_issues'], 'publication_authorized': False}
        staging = Path(tempfile.mkdtemp(prefix='.installing-', dir=folder))
        try:
            shutil.copytree(candidate, staging / 'corpus')
            stage = staging / 'corpus'
            timestamp = _now()
            try:
                _lock_graph(stage, review, timestamp)
            except CreationContextError as exc:
                diagnostic = _diagnostic(root, stage, plan, exc)
                raise CreationContextError(str(exc) + '; diagnostic: ' + diagnostic) from exc
            _write(stage / 'reports/creation_init_receipt.json', _json(_seal({
                'schema': RECEIPT_SCHEMA, 'debate_id': did, 'package_id': package_id,
                'response_sha256': response_sha, 'review_sha256': _sha(files[REVIEW_PATH]),
                'initialized_at': timestamp, 'files': _inventory(stage), 'publication_authorized': False})))
            # Retain the exact return separately from the corpus (never sent to a model).
            response_path = folder / ('response-' + response_sha + '.zip')
            if not response_path.exists():
                _write(response_path, raw)
            _check_inputs(root, request)
            require(_tree(candidate) == request['candidate_sha256'], 'candidate changed during initialization')
            _path(root, 'corpus').mkdir(parents=True, exist_ok=True)
            _path(root, 'corpus/' + did)  # Recheck all parents against symlinks.
            _rename_new(stage, target)
        finally:
            shutil.rmtree(staging)
    # The atomic installation is complete. A later handoff failure must not erase it.
    result = {'status': 'initialized', 'debate_id': did, 'corpus_path': 'corpus/' + did,
              'publication_authorized': False, 'page_validation_performed': False,
              'actual_billed_tokens': None, 'actual_codex_cloud_credits': None}
    try:
        result['draft_package'] = prepare_package(root, 'corpus/' + did)
    except (CreationContextError, OSError, ValueError, KeyError, TypeError) as exc:
        result.update(status='initialized_next_blocked', next_error=str(exc),
                      next_command='./wikidebia creation-package --corpus corpus/' + did)
    return result


def add_arguments(parser: argparse.ArgumentParser, *, preparing: bool) -> None:
    if preparing:
        parser.add_argument('--plan', required=True, help='Compact plan JSON under incoming/')
    else:
        parser.add_argument('--archive', help='Returned creation-plan review ZIP under incoming/')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest='command', required=True)
    add_arguments(sub.add_parser('prepare'), preparing=True)
    add_arguments(sub.add_parser('init'), preparing=False)
    args = parser.parse_args(argv)
    try:
        result = prepare(args.project_root, args.plan) if args.command == 'prepare' else initialize(args.project_root, args.archive)
    except (CreationContextError, CorpusBuildError, OSError, ValueError, KeyError, TypeError, RecursionError) as exc:
        print('INITIALISATION DE CREATION BLOQUEE : ' + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result['status'] not in {'review_rejected', 'initialized_next_blocked'} else 2


if __name__ == '__main__':
    raise SystemExit(main())
