#!/usr/bin/env python3
"""Local French draft handoffs. Saving text is never editorial approval.

The canonical corpus is staged as a whole, then switched using two renames and
an explicit recovery journal. A crash can leave the corpus temporarily absent,
never a mixture of old pages and new metadata. Backups are retained for audit.
Only cooperating writers are serialized; unexpected concurrent changes block.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import copy
import datetime as dt
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
from typing import Any
import uuid
import zipfile

from wikidebia_creation_context import CreationContextError, _contained, _json, _sha
from wikidebia_creation_resume import ResumeInputs, creation_inventory, creation_resume
from wikidebia_release_info import NORM_VERSION, VALIDATOR_VERSION, KIT_VERSION

PACKAGE_SCHEMA = 'wikidebia-chatgpt-review-package-1.0'
RESPONSE_SCHEMA = 'wikidebia-creation-draft-response-1.0'
STATE_SCHEMA = 'wikidebia-creation-draft-request-1.0'
JOURNAL_SCHEMA = 'wikidebia-creation-draft-transaction-1.0'
LIMIT = 64 * 1024 * 1024
FILE_LIMIT = 8 * 1024 * 1024


class CreationImportError(CreationContextError):
    pass


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _path(root: Path, relative: str) -> Path:
    if (not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative
            or any(c in relative for c in '\x00\r\n')
            or PurePosixPath(relative).is_absolute()
            or relative != PurePosixPath(relative).as_posix()
            or '..' in PurePosixPath(relative).parts):
        raise CreationImportError('Non-canonical path')
    return _contained(root, root / relative)


def _locations(root: Path, corpus_path: str) -> tuple[Path, Path]:
    if not re.fullmatch(r'corpus/[a-z0-9][a-z0-9_-]{1,127}', corpus_path):
        raise CreationImportError('Use corpus/<debate_id> for a new French corpus')
    return _path(root, corpus_path), _path(root, '.state/creation-import/' + _sha(corpus_path.encode()))


def assert_no_pending_import(root: Path, corpus_path: str) -> None:
    # Also works when a crash happened between the two directory renames.
    control = _path(root, '.state/creation-import/' + _sha(corpus_path.encode()))
    if _contained(root, control / 'active.json').exists():
        raise CreationImportError('Interrupted draft import: run creation-import --corpus ' + corpus_path + ' --recover')


def _read(path: Path, limit: int = LIMIT) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
            raise CreationImportError('Non-regular, linked or oversized file: ' + path.name)
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise CreationImportError('Oversized input')
    return raw


def _tree(path: Path) -> str:
    if not path.is_dir() or path.is_symlink():
        raise CreationImportError('Missing or unsafe corpus directory')
    rows = []
    total = 0
    for item in sorted(path.rglob('*')):
        rel = item.relative_to(path).as_posix()
        if set(PurePosixPath(rel).parts) & {'private', '.git', '.venv'}:
            raise CreationImportError('Private data in creation corpus')
        item = _path(path, rel)
        if item.is_dir():
            continue
        raw = _read(item)
        total += len(raw)
        if total > 256 * 1024 * 1024:
            raise CreationImportError('Corpus exceeds staging safety limit')
        rows.append([rel, _sha(raw), stat.S_IMODE(item.stat().st_mode)])
    return _sha(_json(rows))


def _sync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    fd, name = tempfile.mkstemp(prefix='.writing-', dir=path.parent)
    os.fchmod(fd, mode)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        _sync_dir(path.parent)
    finally:
        Path(name).unlink(missing_ok=True)


def _seal(value: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(value)
    value['sha256'] = _sha(_json(value))
    return value


def _load(path: Path, schema: str) -> dict[str, Any]:
    value = json.loads(_read(path))
    if not isinstance(value, dict):
        raise CreationImportError('Expected a sealed object')
    given = value.pop('sha256', None)
    if value.get('schema') != schema or given != _sha(_json(value)):
        raise CreationImportError('Local receipt/journal checksum differs')
    value['sha256'] = given
    return value


@contextmanager
def _lock(root: Path, control: Path):
    try:
        import fcntl
    except ImportError as exc:
        raise CreationImportError('Creation import requires POSIX file locks') from exc
    control.mkdir(parents=True, exist_ok=True)
    lock = _contained(root, control / 'LOCK')
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_nlink != 1:
            raise CreationImportError('Unsafe lock file')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise CreationImportError('Another creation operation is active') from exc
        yield
    finally:
        os.close(fd)


def _zip_files(raw: bytes) -> dict[str, bytes]:
    if len(raw) > LIMIT:
        raise CreationImportError('Archive exceeds size limit')
    result = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        if len(infos) > 128 or sum(i.file_size for i in infos) > LIMIT:
            raise CreationImportError('Archive exceeds entry or decompressed size limit')
        seen = set()
        for info in infos:
            name = info.filename
            p = PurePosixPath(name)
            mode = stat.S_IFMT(info.external_attr >> 16)
            if (info.orig_filename != name or info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                    or p.is_absolute() or name.rstrip('/') != p.as_posix() or '..' in p.parts
                    or '\\' in name or ':' in name or any(c in name for c in '\x00\r\n')
                    or name in seen or mode not in (0, stat.S_IFDIR if info.is_dir() else stat.S_IFREG)
                    or info.flag_bits & 1 or info.file_size > FILE_LIMIT):
                raise CreationImportError('Unsafe, duplicate or oversized ZIP entry')
            seen.add(name)
            if info.is_dir():
                if name != p.as_posix() + '/' or info.file_size:
                    raise CreationImportError('Invalid ZIP directory entry')
                continue
            result[name] = archive.read(info)
    return result


def prepare_package(project_root: Path, corpus_path: str, *, max_pages: int = 8) -> dict[str, Any]:
    from wikidebia_review_workflow import _package_manifest_hash, _write_deterministic_zip
    root = project_root.resolve()
    corpus, control = _locations(root, corpus_path)
    with _lock(root, control):
        assert_no_pending_import(root, corpus_path)
        task = creation_resume(root, corpus_path, max_pages=max_pages)
        if task['next']['action'] not in {'draft_debate', 'draft_arguments'}:
            return dict(task, status='review_required', package_path=None)
        before = _tree(corpus)
        queue = json.loads(_read(_path(root, task['queue_path'] + '/QUEUE.json')))
        if queue['debate_id'] != corpus.name:
            raise CreationImportError('Corpus path and debate identity differ')
        context_dir = _path(root, task['context']['context_path'])
        context_manifest = json.loads(_read(context_dir / 'CONTEXT_MANIFEST.json'))
        inputs = {r['path']: r for r in queue['inputs'] + context_manifest['inputs']}
        key = _sha(_json([before, task['queue_sha256']]))
        package_id = str(uuid.uuid5(uuid.NAMESPACE_URL, key))
        request_path = _contained(root, control / (package_id + '.json'))
        target = _path(root, f'outgoing/{corpus.name}_creation_{package_id}.zip')
        if request_path.exists():
            old = _load(request_path, STATE_SCHEMA)
            if _sha(_read(target)) != old['archive_sha256']:
                raise CreationImportError('Prepared archive changed; preserve it and use the original')
            return dict(task, status='reused', package_path=target.relative_to(root).as_posix())
        selected = [r for r in queue['pages'] if r['page_id'] in task['next']['page_ids']]
        files = {}
        editable = []
        for row in selected:
            name = 'editable/' + row['file_path']
            raw = _read(_path(corpus, row['file_path'])) if row['sha256'] else b''
            files[name] = raw
            editable.append({'package_path': name, 'target_path': row['file_path'], 'sha256_at_prepare': _sha(raw)})
        files['editable/RESPONSE.json'] = _json({'schema': RESPONSE_SCHEMA, 'pages': [
            {'page_id': row['page_id'], 'status': 'unchanged'} for row in selected]})
        editable.append({'package_path': 'editable/RESPONSE.json', 'target_path': 'RESPONSE.json',
                         'sha256_at_prepare': _sha(files['editable/RESPONSE.json'])})
        context_entries = []
        for name in ('NORMATIVE_CONTEXT.md', 'CORPUS_CONTEXT.json'):
            raw = _read(_contained(root, context_dir / name))
            files['context/' + name] = raw
            context_entries.append({'package_path': 'context/' + name, 'target_path': name, 'sha256': _sha(raw)})
        instructions = (
            '# Brouillons de creation francaise\n\n'
            'Lire context/NORMATIVE_CONTEXT.md et context/CORPUS_CONTEXT.json.\n'
            'Modifier seulement editable/. Dans RESPONSE.json, conserver chaque page_id et choisir\n'
            'unchanged (texte inchange), partial (brouillon inacheve), generated (redaction terminee, a relire).\n'
            'Ne jamais ecrire validated. Les pages laissees unchanged ne sont pas remplacees.\n'
            'Une page generated exige le modele francais et une date-creation explicite au format ISO.\n'
            'Conserver la date de production deja declaree. Ne pas inventer de sources ni de preuves.\n'
            'Les sources, revues et controles editoriaux sont encore a enregistrer dans le workflow ordinaire.\n'
            'Cet import enregistre uniquement les textes : aucune revue, cloture de lot ou publication.\n'
            'Conserver les autres fichiers du ZIP intacts, le placer dans incoming/, puis lancer :\n'
            f'./wikidebia creation-import --corpus {corpus_path}\n'
        ).encode()
        files['INSTRUCTIONS.md'] = instructions
        manifest = {'schema': PACKAGE_SCHEMA, 'schema_version': '1.0', 'package_id': package_id,
                    'review_type': 'fr_creation_draft', 'debate_id': corpus.name, 'work_id': None,
                    'normative_revision': NORM_VERSION, 'validator_version': VALIDATOR_VERSION,
                    'kit_version': KIT_VERSION, 'prepared_at': _now(), 'source_anchor_sha256': before,
                    'editable_files': editable, 'context_files': context_entries, 'counts': {'pages': len(selected)},
                    'instructions_sha256': _sha(instructions)}
        manifest['manifest_sha256'] = _package_manifest_hash(manifest)
        files['REVIEW_PACKAGE.json'] = _json(manifest)
        temp = Path(tempfile.mkdtemp(prefix='.package-', dir=control))
        try:
            for name, raw in files.items():
                dest = temp / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(raw)
            if _tree(corpus) != before:
                raise CreationImportError('Corpus changed during preparation')
            for record in inputs.values():
                if _sha(_read(_path(root, record['path']))) != record['sha256']:
                    raise CreationImportError('Preparation inputs changed')
            _write_deterministic_zip(temp, target)
            _zip_files(_read(target))  # Never offer an archive that exceeds import limits.
            request = _seal({'schema': STATE_SCHEMA, 'manifest': manifest, 'corpus_path': corpus_path,
                             'before': before, 'selected': selected, 'inputs': list(inputs.values()),
                             'files': {name: _sha(raw) for name, raw in files.items()},
                             'archive_sha256': _sha(_read(target))})
            _write(request_path, _json(request))
        finally:
            shutil.rmtree(temp)
        return dict(task, status='prepared', package_path=target.relative_to(root).as_posix())


def _changes(request: dict[str, Any], files: dict[str, bytes]) -> list[tuple[dict[str, Any], str, bytes]]:
    if set(files) != set(request['files']):
        raise CreationImportError('Missing or extra package files')
    if json.loads(files['REVIEW_PACKAGE.json']) != request['manifest']:
        raise CreationImportError('Foreign or altered review manifest')
    for name, sha in request['files'].items():
        if not name.startswith('editable/') and _sha(files[name]) != sha:
            raise CreationImportError('Read-only package file changed: ' + name)
    response = json.loads(files['editable/RESPONSE.json'])
    if not isinstance(response, dict) or set(response) != {'schema', 'pages'} or response['schema'] != RESPONSE_SCHEMA:
        raise CreationImportError('Unsupported draft response')
    rows = response['pages']
    if not isinstance(rows, list) or any(not isinstance(r, dict) or set(r) != {'page_id', 'status'} for r in rows):
        raise CreationImportError('Invalid draft response rows')
    states = {r['page_id']: r['status'] for r in rows}
    if len(states) != len(rows) or set(states) != {r['page_id'] for r in request['selected']}:
        raise CreationImportError('Duplicate, missing or foreign response page')
    changes = []
    for row in request['selected']:
        state = states[row['page_id']]
        name = 'editable/' + row['file_path']
        raw = files[name]
        raw.decode('utf-8')
        if b'\x00' in raw or state not in {'unchanged', 'partial', 'generated'}:
            raise CreationImportError('Invalid draft state or text')
        if state == 'unchanged':
            if _sha(raw) != request['files'][name]:
                raise CreationImportError('Text changed but declared unchanged')
        elif not raw.strip():
            raise CreationImportError('A saved draft cannot be empty')
        else:
            changes.append((row, state, raw))
    return changes


def _apply_drafts(stage: Path, changes: list, stamp: str) -> None:
    # creation_inventory already loaded the installed structural validator.
    from wikidebia_validator.wikicode import parse_template
    manifest = json.loads(_read(stage / 'manifest.json'))
    registry_path = _path(stage, manifest['core_files']['registry'])
    registry = json.loads(_read(registry_path))
    originals = {p['page_id']: copy.deepcopy(p) for p in manifest['pages'] if p['language'] == 'fr'}
    pages = {p['page_id']: p for p in manifest['pages'] if p['language'] == 'fr'}
    records = {n['id']: n['pages']['fr'] for n in registry['graph']['nodes'] if n['status'] == 'active'}
    records[manifest['debate_id']] = registry['debate']['pages']['fr']
    changed = set()
    for row, state, raw in changes:
        key = row['page_id']
        p, rec = pages[key], records[key]
        dates_recorded = {d for d in (p.get('creation_date'), rec['generation'].get('creation_date')) if d}
        if len(dates_recorded) > 1:
            raise CreationImportError('Contradictory recorded creation dates')
        date = next(iter(dates_recorded), None)
        if state == 'generated':
            parsed = parse_template(raw.decode())
            expected = 'D\u00e9bat' if p['page_type'] == 'debate' else 'Argument'
            dates = parsed.values('date-cr\u00e9ation')
            if parsed.name != expected or len(dates) != 1 or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', dates[0]):
                raise CreationImportError('Generated draft needs its French model and explicit creation date')
            dt.date.fromisoformat(dates[0])
            if date and dates[0] != date:
                raise CreationImportError('Declared creation date changed')
            date = dates[0]
        dest = _path(stage, p['file_path'])
        _write(dest, raw)
        p.update(sha256=_sha(raw), status='generated' if state == 'generated' else 'assigned', creation_date=date)
        p['validation'] = {'status': 'pending', 'report_path': None, 'validated_at': None}
        rec['generation'].update(status='generated' if state == 'generated' else 'in_progress',
                                 creation_date=date, generated_at=stamp if state == 'generated' else None, validated_at=None)
        rec['file'].update(sha256=_sha(raw), status='present')
        changed.add(key)
    # Existing standalone page manifests are mirrors, not independent truth.
    for path in sorted((stage / 'manifests/pages').rglob('*.json')):
        old = json.loads(_read(_contained(stage, path)))
        key = old.get('page_id')
        if old.get('language') == 'fr' and key in changed:
            if old != originals[key]:
                raise CreationImportError('Standalone page manifest differs')
            _write(path, _json(pages[key]))
    old_batches = copy.deepcopy(registry['batches'])
    touched_batches = {pages[key]['batch_id'] for key in changed} - {None}
    for batch in registry['batches']:
        if batch['id'] in touched_batches:
            batch['status'] = 'in_progress'
            batch['outputs']['aggregate_sha256'] = None
            batch['work']['completed_at'] = None
    replacements = {b['id']: b for b in registry['batches'] if b['id'] in touched_batches}
    manifest['batches'] = [copy.deepcopy(replacements.get(b['id'], b)) for b in manifest['batches']]
    lots = stage / 'data/lots_fr.json'
    if lots.exists():
        mirror = json.loads(_read(lots))
        mirror['batches'] = [copy.deepcopy(replacements.get(b['id'], b)) for b in mirror['batches']]
        _write(lots, _json(mirror))
    for path in sorted((stage / 'manifests/batches').rglob('*.json')):
        old = json.loads(_read(_contained(stage, path)))
        if old.get('id') in touched_batches:
            expected = next(b for b in old_batches if b['id'] == old['id'])
            if old != expected:
                raise CreationImportError('Standalone batch manifest differs')
            _write(path, _json(next(b for b in registry['batches'] if b['id'] == old['id'])))
    # No batch is closed here; individual reports and earlier evidence remain untouched.
    manifest['global_status'] = 'graph_locked' if manifest['debate_id'] in changed else 'fr_arguments_in_progress'
    manifest['updated_at'] = stamp
    _write(registry_path, _json(registry))
    _write(stage / 'manifest.json', _json(manifest))


def _recover(root: Path, corpus_path: str, control: Path) -> dict[str, Any]:
    active = _contained(root, control / 'active.json')
    if not active.exists():
        return {'status': 'nothing_to_recover'}
    journal = _load(active, JOURNAL_SCHEMA)
    if journal.get('corpus_path') != corpus_path or not re.fullmatch(r'[a-f0-9]{64}', journal.get('transaction_id', '')):
        raise CreationImportError('Foreign transaction journal')
    transaction = _contained(root, control / journal['transaction_id'])
    corpus, _ = _locations(root, corpus_path)
    backup, stage = (_contained(root, transaction / name) for name in ('before', 'after'))
    current = _tree(corpus) if corpus.exists() else None
    previous = _tree(backup) if backup.exists() else None
    if current == journal['after'] and previous == journal['before'] and not stage.exists():
        receipt = dict(journal, status='imported', editorial_validation_performed=False,
                       publication_authorized=False, remote_write_performed=False)
        receipt.pop('sha256', None)
        _write(_contained(root, control / (journal['package_id'] + '.receipt.json')), _json(_seal(receipt)))
        status = 'imported'
    elif current is None and previous == journal['before']:
        os.rename(backup, corpus)
        _sync_dir(corpus.parent)
        _sync_dir(transaction)
        status = 'rolled_back'
    elif current == journal['before'] and previous is None:
        status = 'rolled_back'
    else:
        raise CreationImportError('Concurrent changes during transaction; preserve corpus, backup and journal for review')
    active.unlink()
    _sync_dir(control)
    return {'status': status, 'transaction_id': journal['transaction_id'],
            'editorial_validation_performed': False, 'publication_authorized': False}


def import_package(project_root: Path, corpus_path: str, *, archive: str | None = None,
                   recover: bool = False) -> dict[str, Any]:
    root = project_root.resolve()
    corpus, control = _locations(root, corpus_path)
    with _lock(root, control):
        recovered = _recover(root, corpus_path, control)
        if recover:
            return recovered
        if archive:
            if not archive.startswith('incoming/') or not archive.endswith('.zip'):
                raise CreationImportError('Select a ZIP under incoming/')
            candidate = _path(root, archive)
        else:
            candidates = []
            incoming = _path(root, 'incoming')
            for p in sorted(incoming.glob('*.zip')):
                data = _zip_files(_read(_contained(root, p)))
                if 'REVIEW_PACKAGE.json' not in data:
                    continue
                m = json.loads(data['REVIEW_PACKAGE.json'])
                if not isinstance(m, dict):
                    raise CreationImportError('Invalid review manifest')
                if m.get('review_type') == 'fr_creation_draft' and m.get('debate_id') == corpus.name:
                    candidates.append(p)
            if len(candidates) != 1:
                raise CreationImportError('Select exactly one creation ZIP with --archive incoming/<file>.zip')
            candidate = candidates[0]
        archive_raw = _read(candidate)
        files = _zip_files(archive_raw)
        manifest = json.loads(files.get('REVIEW_PACKAGE.json', b'{}'))
        if not isinstance(manifest, dict):
            raise CreationImportError('Invalid review manifest')
        package_id = manifest.get('package_id', '')
        if not re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', package_id):
            raise CreationImportError('Invalid package identity')
        request = _load(_contained(root, control / (package_id + '.json')), STATE_SCHEMA)
        if request['corpus_path'] != corpus_path:
            raise CreationImportError('Foreign corpus request')
        changes = _changes(request, files)
        digest = _sha(_json({name: _sha(raw) for name, raw in files.items()}))
        receipt_path = _contained(root, control / (package_id + '.receipt.json'))
        if receipt_path.exists():
            receipt = _load(receipt_path, JOURNAL_SCHEMA)
            if receipt['response_sha256'] != digest:
                raise CreationImportError('Package already consumed by a different response')
            # A historical receipt must never replay over later canonical progress.
            return {'status': 'already_imported', 'package_id': package_id,
                    'current_state_matches_receipt': _tree(corpus) == receipt['after'],
                    'editorial_validation_performed': False, 'publication_authorized': False}
        if _tree(corpus) != request['before']:
            raise CreationImportError('Stale package: corpus changed since preparation')
        inputs = ResumeInputs(root)
        inventory = creation_inventory(inputs, corpus_path)
        if inventory['debate_id'] != corpus.name:
            raise CreationImportError('Foreign corpus identity')
        for record in request['inputs']:
            if _sha(inputs.read(_path(root, record['path']))) != record['sha256']:
                raise CreationImportError('Stale package: context or norm changed')
        if not changes:
            return {'status': 'no_changes', 'editorial_validation_performed': False, 'publication_authorized': False}
        transaction_id = _sha(_json([package_id, digest]))
        transaction = _contained(root, control / transaction_id)
        # Earlier rolled-back preparation is retained, never overwritten.
        if transaction.exists():
            transaction_id = _sha(_json([transaction_id, str(uuid.uuid4())]))
            transaction = _contained(root, control / transaction_id)
        transaction.mkdir()
        if transaction.stat().st_dev != corpus.parent.stat().st_dev:
            raise CreationImportError('Corpus and transaction directory must share a filesystem')
        stage, backup = transaction / 'after', transaction / 'before'
        shutil.copytree(corpus, stage)
        if _tree(stage) != request['before']:
            raise CreationImportError('Corpus changed while staging')
        _apply_drafts(stage, changes, _now())
        # Check the newly written canonical metadata against the same resume contract.
        creation_inventory(ResumeInputs(root), stage.relative_to(root).as_posix())
        after = _tree(stage)
        # Flush copied files before publishing the journal. No promises for failing storage.
        for p in stage.rglob('*'):
            if p.is_file():
                with p.open('rb') as stream:
                    os.fsync(stream.fileno())
        for p in sorted((p for p in stage.rglob('*') if p.is_dir()), reverse=True):
            _sync_dir(p)
        _sync_dir(stage)
        _write(transaction / 'returned.zip', archive_raw)
        journal = _seal({'schema': JOURNAL_SCHEMA, 'corpus_path': corpus_path,
                         'transaction_id': transaction_id, 'package_id': package_id,
                         'response_sha256': digest, 'before': request['before'], 'after': after,
                         'pages_saved': [r['page_id'] for r, _, _ in changes]})
        inputs.verify()
        if _tree(corpus) != request['before']:
            raise CreationImportError('Corpus changed before installation')
        _write(_contained(root, control / 'active.json'), _json(journal))
        try:
            os.rename(corpus, backup)
            _sync_dir(corpus.parent)
            _sync_dir(transaction)
            if _tree(backup) != request['before']:
                raise CreationImportError('Concurrent corpus changes: original preserved in backup')
            os.rename(stage, corpus)
            _sync_dir(corpus.parent)
            _sync_dir(transaction)
            result = _recover(root, corpus_path, control)
        except BaseException:
            # The journal is intentionally retained. Recovery is conservative and
            # handles process death as well as exceptions; no blind rollback.
            raise
        return dict(result, package_id=package_id, pages_saved=journal['pages_saved'],
                    receipt_path=receipt_path.relative_to(root).as_posix())


def add_arguments(parser: argparse.ArgumentParser, *, preparing: bool) -> None:
    parser.add_argument('--corpus', required=True)
    if preparing:
        parser.add_argument('--max-pages', type=int, default=8)
    else:
        group = parser.add_mutually_exclusive_group()
        group.add_argument('--archive', help='Project-relative incoming/<file>.zip')
        group.add_argument('--recover', action='store_true')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=Path.cwd())
    subs = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'import'):
        add_arguments(subs.add_parser(name), preparing=name == 'prepare')
    args = parser.parse_args(argv)
    try:
        result = (prepare_package(args.project_root, args.corpus, max_pages=args.max_pages)
                  if args.command == 'prepare' else
                  import_package(args.project_root, args.corpus, archive=args.archive, recover=args.recover))
    except (CreationContextError, OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        print('CREATION IMPORT BLOCKED: ' + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
