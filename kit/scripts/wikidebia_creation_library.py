#!/usr/bin/env python3
"""Private, explicitly opt-in cross-debate reference hints for French creation.

No target observation, source approval, verification, or corpus mutation is
produced by this tool. Prior context is a discovery hint, not transferable proof.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import unicodedata
from typing import Any

from wikidebia_creation_context import CreationContextError, _contained, _json, _sha
from wikidebia_creation_import import _locations, _path, _read, _sync_dir, assert_no_pending_import
from wikidebia_creation_research import (LEDGER_PATH, _resource, _unique_fields,
                                          _url, basis, load_notes, METADATA)
from wikidebia_documentary_resources import _identity
from wikidebia_creation_resume import ResumeInputs

SCHEMA = 'wikidebia-creation-cross-debate-library-1.0'
LIBRARY_PATH = 'private/creation_library.json'
PREVIEW_PATH = 'context/REUSE_CANDIDATES.json'
HELP_PATH = 'context/REUSE_HELP.md'
MAX_CORPORA = 32
MAX_VARIANTS = 12000
MAX_LIBRARY_BYTES = 16 * 1024 * 1024
MAX_PREVIEW_BYTES = 48 * 1024
STOPWORDS = {'dans', 'avec', 'pour', 'contre', 'sont', 'etre', 'etre', 'elle',
             'elles', 'leur', 'leurs', 'dont', 'sans', 'tout', 'tous', 'toute',
             'comme', 'quelle', 'quelles', 'quels', 'quel', 'cette', 'ceux',
             'celles', 'cest', 'faut', 'doit', 'peut', 'entre', 'selon', 'sous',
             'plus', 'moins', 'ainsi', 'aussi', 'autres', 'autre', 'partir',
             'debat', 'argument', 'arguments', 'possible', 'possibles',
             'raison', 'raisons', 'faire', 'avoir', 'etre', 'the', 'this',
             'that', 'with', 'from', 'should', 'would', 'these', 'those'}


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise CreationContextError('Creation library: ' + message)


def _clean_metadata(record: dict) -> dict | None:
    _require(isinstance(record, dict) and record.get('type') in
             ('bibliography', 'webliography', 'videography'), 'invalid source type')
    if record.get('language') != 'fr':
        return None  # Explicitly out of scope; unknown does not mean French.
    raw = record.get('metadata')
    _require(isinstance(raw, dict) and set(raw) <= METADATA, 'unexpected source metadata')
    metadata: dict[str, Any] = {}
    for key in sorted(raw):
        value = raw[key]
        if value in (None, '', []):
            continue
        if key == 'authors':
            _require(isinstance(value, list) and len(value) <= 200 and all(
                isinstance(v, str) and bool(v.strip()) and len(v) <= 500 for v in value),
                'invalid authors')
        else:
            _require(isinstance(value, str) and bool(value.strip()) and len(value) <= 4000
                     and '\x00' not in value, 'invalid documentary field')
        metadata[key] = copy.deepcopy(value)
    _require(any(metadata.get(k) for k in ('title', 'article', 'work', 'page')),
             'source missing its real title')
    if metadata.get('link'):
        _url(metadata['link'])  # No private, local or credential-bearing URL in a hint.
    else:
        _require(bool(metadata.get('authors')) and bool(metadata.get('date'))
                 and bool(metadata.get('publisher')), 'unidentifiable offline reference')
    return metadata


def _tokens(value: str) -> set[str]:
    folded = unicodedata.normalize('NFKD', value.casefold())
    folded = ''.join(char for char in folded if not unicodedata.combining(char))
    return {word for word in re.findall(r'[a-z0-9]{4,}', folded)
            if word not in STOPWORDS}


def _source_inputs(root: Path, corpus_path: str) -> tuple[dict, dict, dict, dict, dict, list]:
    corpus, _ = _locations(root, corpus_path)
    assert_no_pending_import(root, corpus_path)
    inputs = ResumeInputs(root)
    manifest = inputs.document(_contained(root, corpus / 'manifest.json'))
    _require(manifest.get('debate_id') == corpus.name, 'foreign corpus manifest')
    core = manifest.get('core_files')
    _require(isinstance(core, dict) and all(k in core for k in ('registry', 'sources', 'scope')),
             'missing canonical files')
    registry = inputs.document(_path(corpus, core['registry']))
    sources = inputs.document(_path(corpus, core['sources']))
    scope = inputs.document(_path(corpus, core['scope']))
    _require(registry.get('debate', {}).get('id') == corpus.name
             and sources.get('debate_id') == corpus.name
             and scope.get('debate_id') == corpus.name,
             'foreign canonical source, scope or registry')
    _require(isinstance(sources.get('sources'), list) and isinstance(manifest.get('pages'), list)
             and isinstance(registry.get('graph', {}).get('nodes'), list),
             'invalid canonical sources or graph')
    notes = load_notes(inputs, corpus, corpus.name)
    notes_path = _path(corpus, LEDGER_PATH)
    fingerprints = [{'path': r['path'], 'sha256': r['sha256']} for r in inputs.records.values()]
    if not notes_path.exists():
        fingerprints.append({'path': notes_path.relative_to(root).as_posix(), 'sha256': None})
    inputs.verify()
    return manifest, registry, sources, scope, notes, sorted(fingerprints, key=lambda r: r['path'])


def build_library(root: Path, corpus_paths: list[str]) -> dict:
    """Create a read-only catalogue of found *notices* (never proof for another page)."""
    root = root.resolve()
    _require(bool(corpus_paths) and len(corpus_paths) <= MAX_CORPORA
             and len(set(corpus_paths)) == len(corpus_paths), 'select 1..32 distinct corpora')
    variants: dict[str, dict] = {}
    fingerprints: dict[str, str | None] = {}
    for corpus_path in sorted(corpus_paths):
        manifest, registry, sources, scope, notes, current_inputs = _source_inputs(root, corpus_path)
        for row in current_inputs:
            _require(row['path'] not in fingerprints or fingerprints[row['path']] == row['sha256'],
                     'inconsistent source snapshot')
            fingerprints[row['path']] = row['sha256']
        page_titles = {p['page_id']: p.get('canonical_title') or '' for p in manifest['pages']
                       if p.get('language') == 'fr'}
        page_basis = basis(manifest, registry, scope)

        def include(source: dict, origin: dict) -> None:
            metadata = _clean_metadata(source)
            if metadata is None:
                return
            record = {'type': source['type'], 'language': 'fr', 'metadata': metadata}
            identity = _identity(record)[1]
            digest = _sha(_json(record))
            item = variants.setdefault(digest, dict(id=digest, identity_key=identity, **record,
                                                    origins=[]))
            _require(item['identity_key'] == identity and item['metadata'] == metadata,
                     'inconsistent documentary identity')
            _require(len(origin['page_title']) <= 1000, 'oversized origin title')
            _require(len(origin['reason']) <= 250, 'oversized prior context')
            if origin not in item['origins']:
                item['origins'].append(origin)

        for source in sources['sources']:
            _require(isinstance(source, dict) and isinstance(source.get('usage'), list),
                     'invalid canonical source entry')
            for use in source['usage']:
                if use.get('language') != 'fr' or use.get('page_id') not in page_titles:
                    continue
                include(source, {'debate_id': manifest['debate_id'], 'page_id': use['page_id'],
                                 'page_title': page_titles[use['page_id']], 'basis_current': None,
                                 'prior_record': 'canonical_usage', 'assessment': 'historical_use_only',
                                 'reason': str(use.get('selection_reason') or '')[:250],
                                 'recheck_after': None, 'observed_at': None})
        resources = {r['id']: r for r in notes['resources']}
        for r in resources.values():
            _require(isinstance(r, dict) and 'id' in r and 'identity_key' in r,
                     'malformed saved resource')
            # Re-run the input validator: an outer checksum alone is not enough.
            rebuilt = _resource({'key': 'source', 'type': r['type'],
                                 'language': r['language'], 'metadata': r['metadata']})
            _require(r['id'] == rebuilt['id'] and r['identity_key'] == rebuilt['identity_key'],
                     'resource identity was altered')
        for obs in notes['observations']:
            resource = resources.get(obs.get('resource_id'))
            if resource is None or obs.get('page_id') not in page_titles:
                continue
            _require(isinstance(obs.get('reason'), str) and len(obs['reason']) <= 8000
                     and obs.get('state') in ('located', 'consulted')
                     and obs.get('assessment') in ('unassessed', 'supports', 'context_only',
                                                   'opposes', 'uncertain'),
                     'invalid saved observation rationale or assessment')
            include(resource, {'debate_id': manifest['debate_id'], 'page_id': obs['page_id'],
                               'page_title': page_titles[obs['page_id']],
                               'basis_current': obs.get('page_basis_sha256') == page_basis.get(obs['page_id'])
                               and obs.get('resource_basis_sha256') == _sha(_json(resource)),
                               'prior_record': 'research_note',
                               'assessment': obs.get('assessment', 'unassessed'),
                               'reason': obs['reason'][:250],
                               'observed_at': obs.get('observed_at'),
                               'recheck_after': obs.get('recheck_after')})
        # A resource discovered by a search is useful even if nobody has yet
        # consulted it. Never turn a search result into a consulted observation.
        for search in notes['searches']:
            if search.get('outcome') != 'found':
                continue
            for rid in search.get('resource_ids', []):
                resource = resources.get(rid)
                if resource is None:
                    continue  # Already-canonical references have their own usages.
                for page_id in search.get('page_ids', []):
                    if page_id not in page_titles:
                        continue
                    include(resource, {
                        'debate_id': manifest['debate_id'], 'page_id': page_id,
                        'page_title': page_titles[page_id],
                        'basis_current': search.get('page_basis_sha256', {}).get(page_id) == page_basis.get(page_id)
                        and search.get('resource_basis_sha256', {}).get(rid) == _sha(_json(resource)),
                        'prior_record': 'search_result', 'assessment': 'unassessed',
                        'reason': '', 'observed_at': search.get('searched_at'),
                        'recheck_after': search.get('recheck_after')})
        _require(len(variants) <= MAX_VARIANTS, 'too many distinct documentary variants')
    source_list = []
    for item in sorted(variants.values(), key=lambda r: (r['identity_key'], r['id'])):
        item['origins'].sort(key=lambda r: _json(r))
        item['origin_count'] = len(item['origins'])
        item['origins'] = item['origins'][:8]
        source_list.append(item)
    counts: dict[str, int] = {}
    for item in source_list:
        counts[item['identity_key']] = counts.get(item['identity_key'], 0) + 1
    for item in source_list:
        item['variants_require_review'] = counts[item['identity_key']] > 1
    payload = {'schema': SCHEMA, 'corpora': sorted(corpus_paths),
               'inputs': [{'path': key, 'sha256': fingerprints[key]} for key in sorted(fingerprints)],
               'notices': source_list, 'authoritative_for_target': False,
               'source_verification_performed': False}
    signed = dict(payload, sha256=_sha(_json(payload)))
    raw = _json(signed)
    _require(len(raw) <= MAX_LIBRARY_BYTES, 'private library exceeds size limit')
    for record in payload['inputs']:
        _require(_fingerprint(root, record['path']) == record['sha256'],
                 'source changed during library build')
    path = _path(root, LIBRARY_PATH)
    directory = path.parent
    directory.mkdir(mode=0o700, exist_ok=True)
    _require(not directory.is_symlink() and stat.S_IMODE(directory.stat().st_mode) & 0o077 == 0,
             'private/ must not be readable by other users')
    fd, tmp = tempfile.mkstemp(prefix='.creation-library-', dir=directory)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        _sync_dir(directory)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return {'status': 'built', 'path': LIBRARY_PATH, 'corpora': len(corpus_paths),
            'notices': len(source_list), 'identities': len(counts),
            'bytes': len(raw), 'source_verification_performed': False,
            'publication_authorized': False}


def _fingerprint(root: Path, path: str) -> str | None:
    target = _path(root, path)
    if not target.exists():
        return None
    return _sha(_read(target, MAX_LIBRARY_BYTES * 2))


def load_library(root: Path) -> tuple[dict, bytes]:
    root = root.resolve()
    lib = _path(root, LIBRARY_PATH)
    _require(lib.is_file(), 'missing private library; run creation-library-build first')
    _require(stat.S_IMODE(lib.stat().st_mode) & 0o077 == 0,
             'library file must not be readable by other users')
    raw = _read(lib, MAX_LIBRARY_BYTES)
    value = json.loads(raw, object_pairs_hook=_unique_fields)
    _require(isinstance(value, dict) and set(value) == {'schema', 'corpora', 'inputs', 'notices',
                 'authoritative_for_target', 'source_verification_performed', 'sha256'},
             'invalid library schema')
    signature = value.pop('sha256')
    _require(value['schema'] == SCHEMA and value['authoritative_for_target'] is False
             and value['source_verification_performed'] is False
             and signature == _sha(_json(value)), 'corrupted or forged library snapshot')
    _require(isinstance(value['inputs'], list) and len(value['inputs']) <= MAX_CORPORA * 8
             and isinstance(value['notices'], list) and len(value['notices']) <= MAX_VARIANTS,
             'oversized catalogue')
    for input_record in value['inputs']:
        _require(isinstance(input_record, dict) and set(input_record) == {'path', 'sha256'}
                 and isinstance(input_record['path'], str)
                 and (input_record['sha256'] is None or
                      isinstance(input_record['sha256'], str) and
                      re.fullmatch(r'[a-f0-9]{64}', input_record['sha256'])),
                 'invalid snapshot fingerprint')
        _require(re.fullmatch(r'corpus/[a-z0-9][a-z0-9_-]{1,127}/(?:manifest\.json|scope\.json|data/[A-Za-z0-9_./-]+\.json)',
                                  input_record['path']) is not None,
                 'source fingerprint escapes corpus')
        _require(_fingerprint(root, input_record['path']) == input_record['sha256'],
                 'source corpus changed; rebuild the private library')
    for item in value['notices']:
        _require(isinstance(item, dict) and set(item) == {'id', 'identity_key', 'type',
                 'language', 'metadata', 'origins', 'origin_count', 'variants_require_review'},
                 'invalid catalogue entry')
        metadata = _clean_metadata(item)
        _require(metadata is not None and item['language'] == 'fr'
                 and item['id'] == _sha(_json({'type': item['type'], 'language': 'fr',
                                             'metadata': metadata}))
                 and item['identity_key'] == _identity(item)[1]
                 and isinstance(item['origins'], list)
                 and len(item['origins']) <= 8, 'invalid catalogue entry identity')
    value['sha256'] = signature
    return value, raw


def _preview_query(root: Path, selected: list, corpus: Path, user_query: str | None) -> dict:
    manifest = json.loads(_read(corpus / 'manifest.json'))
    titles = {p['page_id']: p.get('canonical_title') or '' for p in manifest['pages']
              if p.get('language') == 'fr'}
    if user_query is not None:
        _require(isinstance(user_query, str) and 1 <= len(user_query.strip()) <= 160
                 and '\x00' not in user_query, 'invalid reuse search phrase')
    keys = [row['page_id'] for row in selected]
    _require(all(key in titles for key in keys), 'unknown target page')
    return {key: {'title': titles[key],
                  'terms': sorted(_tokens(titles[key] + ' ' + (user_query or '')))}
            for key in keys}


def preview_library(root: Path, corpus: Path, selected: list, *, user_query: str | None = None,
                    library: dict | None = None) -> bytes:
    """Bounded per-page candidate context, not an automatic transfer of notes."""
    if library is None:
        library, _ = load_library(root)
    target_id = corpus.name
    pages = _preview_query(root, selected, corpus, user_query)
    result = {'schema': 'wikidebia-creation-cross-debate-preview-1.0',
              'library_sha256': library['sha256'], 'debate_id': target_id,
              'not_verified_for_target': True, 'prior_proofs_are_not_transferable': True,
              'research_or_source_import_performed': False,
              'notice': ('Suggestions de decouverte seulement. Rerechercher la ressource, sa langue, '
                         'ses metadonnees et sa pertinence pour CHAQUE page. Ne jamais importer '
                         'un ancien observation_id ni un statut verified. Aucune page n est validee.'),
              'notices': [], 'page_candidates': []}
    max_per_page = min(6, max(1, 24 // len(selected)))
    for page_id, target in pages.items():
        terms = set(target['terms'])
        ranked = []
        for source in library['notices']:
            origins = [o for o in source['origins'] if o['debate_id'] != target_id]
            if not origins:
                continue
            meta = source['metadata']
            title = ' '.join(str(meta.get(k) or '') for k in ('title', 'work', 'article', 'page'))
            title_matches = terms & _tokens(title)
            page_matches = terms & set().union(*(_tokens(o['page_title']) for o in origins))
            relevance = (len(title_matches) * 4 + len(page_matches) * 2)
            if not title_matches and len(page_matches) < 2:
                continue  # One generic word in another debate is a weak cue.
            suggestion = {'hint_id': source['id'],
                          'matched_terms': sorted(title_matches | page_matches),
                          'score_for_discovery_only': relevance}
            ranked.append((-relevance, source['id'], suggestion))
        ranked.sort()
        result['page_candidates'].append({'page_id': page_id,
              'page_title': target['title'], 'search_terms': target['terms'],
              'candidates': [candidate for _, _, candidate in ranked[:max_per_page]]})
    # Shared notices appear ONCE even when they are suggested for 20 pages.
    # Page-specific scores contain only references, not repeated bibliographies.
    by_id = {source['id']: source for source in library['notices']}
    def assign_notices() -> None:
        chosen = {suggestion['hint_id'] for row in result['page_candidates']
                  for suggestion in row['candidates']}
        result['notices'] = [
            {'hint_id': sid, 'identity_key': by_id[sid]['identity_key'],
             'type': by_id[sid]['type'], 'language': 'fr',
             'metadata': by_id[sid]['metadata'],
             'origin_count': by_id[sid]['origin_count'],
             'previous_contexts': [o for o in by_id[sid]['origins']
                                   if o['debate_id'] != target_id][:3],
             'variants_require_review': by_id[sid]['variants_require_review'],
             'requires_new_target_observation_and_review': True}
            for sid in sorted(chosen)]
    assign_notices()
    while len(_json(result)) > MAX_PREVIEW_BYTES:
        rows = [row for row in result['page_candidates'] if row['candidates']]
        _require(bool(rows), 'preview metadata is larger than safety limit')
        max(rows, key=lambda row: len(_json(row['candidates'][-1])))['candidates'].pop()
        assign_notices()
    return _json(result)


def help_text() -> bytes:
    return ("""# Notices reutilisables d'autres debats : contexte seul

Ce fichier est un index prive, opt-in et lecture seule. Ne jamais attribuer a la
page cible une attestation, une consultation, une citation ou un statut verified
depuis un autre debat. La similitude lexicale est une piste de recherche, pas
une preuve de pertinence. Les variantes de metadonnees restent a arbitrer.

Si une notice est utile, consulter de nouveau la ressource pour la page cible.
Consigner une recherche/observation REELLE via editable/RESEARCH.json. Apres
cet import, effectuer une revue independante par editable/SOURCES.json dans
un paquet --research-only ulterieur. Les champs observation_id et R... sont
propres au corpus : hint_id ne doit jamais etre utilise comme tel.

Ni cette bibliotheque, ni sa consultation, ni son inclusion dans un ZIP ne
modifient sources.json, le wikicode, un statut de validation ou un wiki distant.
Les recherches negatives et les extraits de sources ne sont pas transferes.
""").encode('utf-8')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=Path.cwd())
    parser.add_argument('--corpus', action='append', required=True)
    args = parser.parse_args(argv)
    try:
        report = build_library(args.project_root, args.corpus)
    except (CreationContextError, OSError, ValueError, KeyError, TypeError) as exc:
        print('CREATION LIBRARY BLOCKED: ' + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
