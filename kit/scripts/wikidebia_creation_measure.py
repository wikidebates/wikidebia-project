#!/usr/bin/env python3
"""Measure *observable* creation package payloads, not estimated cloud billing.

Compare prepared ZIPs from the exact same French corpus snapshot, with and
without optional cross-debate discovery hints. Never start a model, rerun
research, modify a corpus, or infer that a suggested source avoided research.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import zipfile
import sys
from typing import Any

from wikidebia_creation_context import CreationContextError, _sha
from wikidebia_creation_import import (_path, _read, _zip_files, _load, _locations,
                                        PACKAGE_SCHEMA, STATE_SCHEMA, LIMIT)
from wikidebia_creation_library import PREVIEW_PATH, HELP_PATH
from wikidebia_review_workflow import _package_manifest_hash

SCHEMA = 'wikidebia-creation-payload-measurement-1.0'
MAX_PAIRS = 32
SAFE_PACKAGE = re.compile(r'outgoing/[A-Za-z0-9][A-Za-z0-9_.-]{0,240}\.zip\Z')
SHARED_CONTEXT = {'context/NORMATIVE_CONTEXT.md', 'context/CORPUS_CONTEXT.json',
                  'context/RESEARCH_HELP.md', 'context/SOURCES_HELP.md'}


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise CreationContextError('Creation measurement: ' + message)


def _object(raw: bytes, label: str) -> dict:
    value = json.loads(raw)
    _require(isinstance(value, dict), 'expected JSON object: ' + label)
    return value


def _entries(manifest: dict, key: str, prop: str) -> dict[str, dict]:
    rows = manifest.get(key)
    _require(isinstance(rows, list) and len(rows) <= 128, 'invalid ' + key)
    result = {}
    for row in rows:
        _require(isinstance(row, dict) and isinstance(row.get('package_path'), str)
                 and isinstance(row.get(prop), str) and re.fullmatch('[a-f0-9]{64}', row[prop])
                 and row['package_path'] not in result,
                 'duplicate or invalid ' + key + ' entry')
        result[row['package_path']] = row
    return result


def inspect_package(root: Path, relative: str) -> dict[str, Any]:
    """Read the original review ZIP, checking its manifest and file digests."""
    _require(isinstance(relative, str) and SAFE_PACKAGE.fullmatch(relative) is not None,
             'use an outgoing/<name>.zip path')
    path = _path(root, relative)
    archive = _read(path, LIMIT)
    files = _zip_files(archive)
    _require('REVIEW_PACKAGE.json' in files and 'INSTRUCTIONS.md' in files,
             'not a creation review package')
    manifest = _object(files['REVIEW_PACKAGE.json'], 'REVIEW_PACKAGE.json')
    _require(manifest.get('schema') == PACKAGE_SCHEMA
             and manifest.get('review_type') == 'fr_creation_draft'
             and manifest.get('schema_version') == '1.0'
             and isinstance(manifest.get('debate_id'), str)
             and re.fullmatch('[a-z0-9][a-z0-9_-]{1,127}', manifest['debate_id']) is not None
             and isinstance(manifest.get('source_anchor_sha256'), str)
             and re.fullmatch('[a-f0-9]{64}', manifest['source_anchor_sha256']) is not None
             and manifest.get('manifest_sha256') == _package_manifest_hash(manifest),
             'invalid creation manifest/checksum')
    editable = _entries(manifest, 'editable_files', 'sha256_at_prepare')
    contexts = _entries(manifest, 'context_files', 'sha256')
    _require(bool(editable) and bool(contexts)
             and all(name.startswith('editable/') for name in editable)
             and all(name.startswith('context/') for name in contexts)
             and set(editable).isdisjoint(contexts)
             and set(files) == set(editable) | set(contexts) | {'INSTRUCTIONS.md', 'REVIEW_PACKAGE.json'},
             'package inventory mismatch')
    for name, row in contexts.items():
        _require(_sha(files[name]) == row['sha256'], 'modified context: ' + name)
    for name, row in editable.items():
        _require(_sha(files[name]) == row['sha256_at_prepare'],
                 'edited return is not an original prepared package: ' + name)
    _require(_sha(files['INSTRUCTIONS.md']) == manifest.get('instructions_sha256'),
             'modified package instructions')
    _require(SHARED_CONTEXT - {'context/SOURCES_HELP.md'} <= set(contexts),
             'missing standard context')
    _require(isinstance(manifest.get('counts'), dict)
             and type(manifest['counts'].get('pages')) is int
             and 1 <= manifest['counts']['pages'] <= 128,
             'invalid target page count')
    # Check the kit's original preparation receipt, not only a self-signed ZIP.
    _require(isinstance(manifest.get('package_id'), str) and
             re.fullmatch('[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}',
                          manifest['package_id']) is not None, 'invalid package identity')
    control = _locations(root, 'corpus/' + manifest['debate_id'])[1]
    request = _load(_path(control, manifest['package_id'] + '.json'), STATE_SCHEMA)
    _require(request.get('corpus_path') == 'corpus/' + manifest['debate_id']
             and request.get('manifest') == manifest
             and request.get('archive_sha256') == _sha(archive)
             and request.get('files') == {name: _sha(raw) for name, raw in files.items()},
             'archive does not match its original local preparation receipt')
    context_bytes = sum(len(files[k]) for k in contexts)
    editable_bytes = sum(len(files[k]) for k in editable)
    return {'path': relative, 'manifest': manifest, 'files': files, 'editable': editable,
            'contexts': contexts, 'sha256': _sha(archive),
            'size': {'zip_bytes': len(archive),
                     'uncompressed_files_bytes': sum(len(raw) for raw in files.values()),
                     'available_context_bytes': context_bytes + len(files['INSTRUCTIONS.md']),
                     'context_files_bytes': context_bytes,
                     'editable_files_bytes': editable_bytes,
                     'instructions_bytes': len(files['INSTRUCTIONS.md'])}}


def _candidate_stats(files: dict[str, bytes]) -> dict[str, int]:
    preview = _object(files[PREVIEW_PATH], PREVIEW_PATH)
    _require(preview.get('not_verified_for_target') is True
             and preview.get('prior_proofs_are_not_transferable') is True
             and preview.get('research_or_source_import_performed') is False,
             'reuse hints cannot certify a source')
    notices = preview.get('notices')
    pages = preview.get('page_candidates')
    _require(isinstance(notices, list) and isinstance(pages, list),
             'invalid reuse preview')
    notice_ids = []
    _require(all(isinstance(n, dict) and isinstance(n.get('hint_id'), str)
                 for n in notices), 'invalid reuse notice')
    ids = {n['hint_id'] for n in notices}
    _require(len(ids) == len(notices), 'duplicate reuse notice')
    for page in pages:
        _require(isinstance(page, dict) and isinstance(page.get('candidates'), list),
                 'invalid reuse page candidates')
        for hint in page['candidates']:
            _require(isinstance(hint, dict) and hint.get('hint_id') in ids,
                     'unreferenced candidate')
            notice_ids.append(hint['hint_id'])
    _require(set(notice_ids) == ids, 'unreferenced reuse notices')
    return {'candidate_links': len(notice_ids), 'unique_notices': len(notices),
            'duplicate_notice_references_avoided': len(notice_ids) - len(notices),
            'preview_bytes': len(files[PREVIEW_PATH])}


def measure_pair(root: Path, baseline_path: str, reused_path: str) -> dict[str, Any]:
    baseline = inspect_package(root, baseline_path)
    reused = inspect_package(root, reused_path)
    a, b = baseline['manifest'], reused['manifest']
    for field in ('debate_id', 'source_anchor_sha256', 'normative_revision',
                  'validator_version', 'kit_version', 'counts'):
        _require(a.get(field) == b.get(field), 'different corpus snapshot or scope: ' + field)
    _require(set(baseline['editable']) == set(reused['editable'])
             and all(baseline['files'][name] == reused['files'][name]
                     for name in baseline['editable']),
             'edited page or different editable scope')
    _require(PREVIEW_PATH not in baseline['files'] and HELP_PATH not in baseline['files']
             and PREVIEW_PATH in reused['files'] and HELP_PATH in reused['files'],
             'compare a regular package with a reuse-enabled package')
    _require(set(reused['contexts']) == set(baseline['contexts']) | {PREVIEW_PATH, HELP_PATH}
             and all(baseline['files'][name] == reused['files'][name]
                     for name in baseline['contexts']),
             'ordinary read-only contexts are not identical')
    stats = _candidate_stats(reused['files'])
    _require(len(_object(reused['files'][PREVIEW_PATH], PREVIEW_PATH)['page_candidates'])
             == a['counts']['pages'], 'reuse preview targets a different number of pages')
    keys = ('zip_bytes', 'uncompressed_files_bytes', 'available_context_bytes',
            'context_files_bytes', 'editable_files_bytes', 'instructions_bytes')
    delta = {key: reused['size'][key] - baseline['size'][key] for key in keys}
    _require(delta['context_files_bytes'] == len(reused['files'][PREVIEW_PATH])
             + len(reused['files'][HELP_PATH])
             and delta['editable_files_bytes'] == 0,
             'reuse modified ordinary context or editable content')
    return {'debate_id': a['debate_id'], 'scope_pages': a['counts']['pages'],
            'source_anchor_sha256': a['source_anchor_sha256'],
            'baseline': {'path': baseline_path, 'sha256': baseline['sha256'], **baseline['size']},
            'reuse': {'path': reused_path, 'sha256': reused['sha256'], **reused['size']},
            'delta_bytes_reuse_minus_baseline': delta, 'discovery_hints': stats,
            'actual_model_input_tokens': None, 'actual_model_output_tokens': None,
            'actual_codex_credits': None, 'documentary_researches_avoided': None,
            'editorial_quality_change': None}


def measure(root: Path, pairs: list[list[str]]) -> dict[str, Any]:
    _require(bool(pairs) and len(pairs) <= MAX_PAIRS, 'provide 1 to 32 pairs')
    _require(all(len(pair) == 2 for pair in pairs), 'each pair needs two ZIPs')
    seen = set()
    results = []
    for old, new in pairs:
        _require(old != new and (old, new) not in seen, 'duplicate or identical pair')
        seen.add((old, new))
        results.append(measure_pair(root, old, new))
    keys = results[0]['delta_bytes_reuse_minus_baseline']
    totals = {key: sum(row['delta_bytes_reuse_minus_baseline'][key] for row in results) for key in keys}
    hints = {key: sum(row['discovery_hints'][key] for row in results)
             for key in results[0]['discovery_hints']}
    return {'schema': SCHEMA, 'pairs_measured': len(results),
            'distinct_debates': len({r['debate_id'] for r in results}),
            'pairs': results, 'totals': {'delta_bytes_reuse_minus_baseline': totals,
                                        'discovery_hints': hints},
            'actual_billed_tokens': None, 'actual_codex_cloud_credits': None,
            'real_searches_avoided': None, 'actual_editorial_quality_change': None,
            'comparison_is': 'package payload only, from matching prepared snapshots',
            'limitations': [
                'The ZIP contains potential model inputs, not proof that all bytes were read.',
                'Bytes and matched hints are not tokenizer counts, billed credits or searches avoided.',
                'Reuse is an extra context payload; its positive delta is an overhead, not a saving.',
                'This tool performs no inference about editorial quality or factual verification.',
                'To measure real quota changes, compare provider usage from matched real runs.'
            ], 'remote_access_performed': False, 'remote_write_performed': False,
            'corpus_modified': False, 'editorial_validation_performed': False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=Path.cwd())
    parser.add_argument('--pair', nargs=2, action='append', required=True,
                        metavar=('REGULAR_ZIP', 'REUSE_ZIP'))
    args = parser.parse_args(argv)
    try:
        report = measure(args.project_root.resolve(), args.pair)
    except (CreationContextError, OSError, KeyError, ValueError, TypeError,
            zipfile.BadZipFile) as exc:
        print('CREATION MEASUREMENT BLOCKED: ' + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
