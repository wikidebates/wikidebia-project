"""Unpublished research notes, not a source-verification or editorial receipt.

Only explicit observations are stored. Canonical sources, usages and page states
remain controlled by their ordinary review workflow. No network requests occur.
"""
from __future__ import annotations

import copy
import datetime as dt
import ipaddress
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from wikidebia_creation_context import CreationContextError, _json, _sha
from wikidebia_documentary_resources import _identity, build_resource_registry

RESPONSE_SCHEMA = 'wikidebia-creation-research-response-1.0'
LEDGER_SCHEMA = 'wikidebia-creation-research-notes-1.0'
LEDGER_PATH = 'data/creation_research.json'
EDITABLE_PATH = 'editable/RESEARCH.json'
MAX_ROWS = 200
MAX_LEDGER_BYTES = 32 * 1024 * 1024
METADATA = {'authors', 'article', 'work', 'volume', 'issue', 'location', 'publisher',
            'place', 'date', 'link', 'page', 'site', 'title'}


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise CreationContextError('Research notes: ' + message)


def _object(value: Any, fields: set[str]) -> dict:
    _require(isinstance(value, dict) and set(value) == fields, 'unexpected or missing fields')
    return value


def _text(value: Any, *, empty: bool = False, limit: int = 8000) -> str:
    _require(isinstance(value, str) and len(value) <= limit and '\x00' not in value
             and (empty or bool(value.strip())), 'invalid or oversized text')
    return value


def _rows(value: Any) -> list:
    _require(isinstance(value, list) and len(value) <= MAX_ROWS, 'too many rows or invalid list')
    return value


def _timestamp(value: Any) -> None:
    _text(value, limit=64)
    try:
        date = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise CreationContextError('Research notes: invalid observation timestamp') from exc
    _require(date.tzinfo is not None and date.utcoffset() is not None,
             'observation timestamp needs a timezone')
    _require(date <= dt.datetime.now(dt.timezone.utc), 'observation cannot be in the future')


def _date(value: Any) -> None:
    if value is not None:
        _require(isinstance(value, str) and bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}', value)), 'invalid recheck date')
        dt.date.fromisoformat(value)


def _url(value: str) -> None:
    _text(value, limit=4000)
    p = urlsplit(value)
    _require(p.scheme in {'http', 'https'} and bool(p.hostname) and not p.username and not p.password,
             'only public HTTP(S) reference URLs without credentials are allowed')
    host = p.hostname.lower()
    _require(host != 'localhost' and '.' in host and not host.endswith(('.local', '.internal', '.localhost')),
             'local reference URL')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    _require(address is None or address.is_global, 'private reference address')
    # No URL is dereferenced. Reject obvious credential-bearing URLs before export.
    _require(not any(re.search(r'token|password|secret|signature|^sig$|^auth$|api.?key', key, re.I)
                     for key, _ in parse_qsl(p.query)), 'credential-bearing reference URL')
    _ = p.port  # Reject malformed ports as well.


def _unique_fields(pairs: list) -> dict:
    out = {}
    for key, value in pairs:
        _require(key not in out, 'duplicate JSON field')
        out[key] = value
    return out


def empty_response() -> dict:
    return {'schema': RESPONSE_SCHEMA, 'resources': [], 'observations': [], 'searches': []}


def _resource(row: Any) -> dict:
    _object(row, {'key', 'type', 'language', 'metadata'})
    _require(isinstance(row['key'], str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,80}', row['key'])), 'invalid resource key')
    _require(row['type'] in ('bibliography', 'webliography', 'videography'), 'invalid resource type')
    language = row['language']
    _require(language is None or (isinstance(language, str) and bool(re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z0-9]+)*', language))),
             'invalid language; null means unknown, not French')
    meta = row['metadata']
    _require(isinstance(meta, dict) and bool(meta) and set(meta) <= METADATA, 'invalid metadata')
    for key, value in meta.items():
        if key == 'authors':
            _rows(value)
            for author in value:
                _text(author, limit=500)
            _require(len(set(value)) == len(value), 'duplicate authors')
        elif value is not None:
            _text(value, limit=4000)
    _require(any(meta.get(key) for key in ('title', 'article', 'work', 'page')), 'resource needs its actual title')
    if meta.get('link'):
        _url(meta['link'])
    else:
        _require(bool(meta.get('authors')) and bool(meta.get('date')) and bool(meta.get('publisher')),
                 'offline resource needs authors, date and publisher to identify the edition')
    data = {k: copy.deepcopy(row[k]) for k in ('type', 'language', 'metadata')}
    data['identity_key'] = _identity(data)[1]
    # Same metadata observation is stored once; conflicting metadata are retained
    # as variants, never silently overwritten or treated as verified identity.
    data['id'] = 'R' + _sha(_json(data))
    return data


def basis(manifest: dict, registry: dict, scope: dict) -> dict[str, str]:
    titles = {n['id']: n.get('fr') for n in registry['graph']['nodes']}
    titles[manifest['debate_id']] = registry['debate'].get('pages', {}).get('fr', {}).get('canonical_title')
    return {p['page_id']: _sha(_json([p.get('sha256'), titles.get(p['page_id']), scope,
            registry['graph'].get('lifecycle', {}).get('structural_sha256')]))
            for p in manifest['pages'] if p.get('language') == 'fr'}


def load_notes(inputs: Any, corpus: Path, debate_id: str) -> dict:
    from wikidebia_creation_import import _path, _read
    path = _path(corpus, LEDGER_PATH)
    exists = inputs.exists(path) if hasattr(inputs, 'exists') else path.exists()
    if not exists:
        return {'schema': LEDGER_SCHEMA, 'debate_id': debate_id, 'resources': [], 'observations': [], 'searches': []}
    raw = _read(path, MAX_LEDGER_BYTES)
    _require(inputs.read(path) == raw, 'notes changed during reading')
    value = json.loads(raw)
    _object(value, {'schema', 'debate_id', 'resources', 'observations', 'searches', 'sha256'})
    sha = value.pop('sha256')
    _require(value['schema'] == LEDGER_SCHEMA and value['debate_id'] == debate_id
             and sha == _sha(_json(value)), 'foreign, unsupported or altered notes')
    for name in ('resources', 'observations', 'searches'):
        _require(isinstance(value[name], list) and all(isinstance(r, dict) and isinstance(r.get('id'), str)
                 for r in value[name]), 'invalid saved notes')
        _require(len({r['id'] for r in value[name]}) == len(value[name]), 'duplicate saved notes')
    return value


def merge_response(response: Any, old: dict, selected: set[str], page_basis: dict,
                   canonical: dict) -> tuple[dict, dict]:
    _object(response, {'schema', 'resources', 'observations', 'searches'})
    _require(response['schema'] == RESPONSE_SCHEMA, 'unknown research response')
    result = copy.deepcopy(old)
    resources = {r['id']: r for r in result['resources']}
    aliases = {key: key for key in resources}
    canonical_ids = {s['id']: s for s in canonical['sources']}
    aliases.update({'source:' + key: 'source:' + key for key in canonical_ids})
    source_hashes = {'source:' + key: _sha(_json({k: row.get(k) for k in ('type', 'language', 'metadata')}))
                     for key, row in canonical_ids.items()}
    source_hashes.update({key: _sha(_json(row)) for key, row in resources.items()})
    supplied = set()
    used = set()
    additions = {key: 0 for key in ('resources', 'observations', 'searches')}
    for row in _rows(response['resources']):
        resource = _resource(row)
        key = row['key']
        _require(key not in supplied and key not in aliases, 'duplicate or reserved resource key')
        supplied.add(key)
        aliases[key] = resource['id']
        if resource['id'] not in resources:
            resources[resource['id']] = resource
            result['resources'].append(resource)
            additions['resources'] += 1
        source_hashes[resource['id']] = _sha(_json(resource))

    def resolve(key: Any) -> str:
        _require(isinstance(key, str) and key in aliases, 'unknown resource reference')
        used.add(key)
        return aliases[key]

    existing_ids = {name: {r['id'] for r in result[name]} for name in ('observations', 'searches')}

    def append(name: str, entry: dict) -> None:
        entry['id'] = ('O' if name == 'observations' else 'Q') + _sha(_json(entry))
        if entry['id'] not in existing_ids[name]:
            existing_ids[name].add(entry['id'])
            result[name].append(entry)
            additions[name] += 1

    for row in _rows(response['observations']):
        _object(row, {'page_id', 'resource_key', 'state', 'observed_at', 'locator', 'excerpt',
                      'assessment', 'reason', 'limitations', 'recheck_after'})
        page_id = row['page_id']
        _require(isinstance(page_id, str) and page_id in selected, 'observation outside selected pages')
        _require(row['state'] in ('located', 'consulted'), 'observation is not a verified-source verdict')
        _require(row['assessment'] in ('unassessed', 'supports', 'context_only', 'opposes', 'uncertain'), 'unknown assessment')
        _timestamp(row['observed_at']); _date(row['recheck_after'])
        _text(row['limitations'], empty=True)
        consulted = row['state'] == 'consulted'
        for key in ('locator', 'excerpt', 'reason'):
            _text(row[key], empty=not consulted)
        _require(consulted or (row['assessment'] == 'unassessed' and not row['excerpt'] and not row['locator']),
                 'located is not a consultation or an argument assessment')
        entry = {k: copy.deepcopy(v) for k, v in row.items() if k != 'resource_key'}
        entry['resource_id'] = resolve(row['resource_key'])
        entry['resource_basis_sha256'] = source_hashes[entry['resource_id']]
        entry['page_basis_sha256'] = page_basis[page_id]
        append('observations', entry)
    for row in _rows(response['searches']):
        _object(row, {'page_ids', 'query', 'provider', 'searched_at', 'outcome', 'resource_keys', 'notes', 'recheck_after'})
        ids = _rows(row['page_ids'])
        _require(bool(ids) and all(isinstance(x, str) for x in ids) and len(set(ids)) == len(ids)
                 and set(ids) <= selected, 'search outside selected pages')
        for key in ('query', 'provider', 'notes'):
            _text(row[key])
        _timestamp(row['searched_at']); _date(row['recheck_after'])
        _require(row['outcome'] in ('found', 'no_result', 'inaccessible', 'not_relevant'), 'unknown search outcome')
        keys = _rows(row['resource_keys'])
        refs = [resolve(key) for key in keys]
        _require(len(set(refs)) == len(refs), 'duplicate search references')
        _require(row['outcome'] != 'no_result' or not refs, 'no_result cannot list found resources')
        _require(row['outcome'] != 'found' or bool(refs), 'found needs an identified resource')
        entry = {k: copy.deepcopy(v) for k, v in row.items() if k != 'resource_keys'}
        entry['resource_ids'] = refs
        entry['resource_basis_sha256'] = {key: source_hashes[key] for key in refs}
        entry['page_basis_sha256'] = {key: page_basis[key] for key in ids}
        append('searches', entry)
    _require(supplied <= used, 'unreferenced resources; attach each to a search or observation')
    _require(len(_json(result)) <= MAX_LEDGER_BYTES - 200, 'research ledger exceeds safety limit')
    return result, additions


def response_changes(root: Path, corpus: Path, request: dict, files: dict,
                     drafts: list | None = None) -> tuple[dict | None, dict]:
    from wikidebia_creation_resume import ResumeInputs
    from wikidebia_creation_import import _path
    if EDITABLE_PATH not in request['files']:
        return None, {}  # Pre-feature draft requests remain readable, not extensible.
    inputs = ResumeInputs(root)
    manifest = inputs.document(corpus / 'manifest.json')
    core = manifest['core_files']
    registry = inputs.document(_path(corpus, core['registry']))
    scope = inputs.document(_path(corpus, core['scope']))
    sources = inputs.document(_path(corpus, core['sources']))
    old = load_notes(inputs, corpus, manifest['debate_id'])
    returned_pages = {row['page_id']: _sha(raw) for row, _, raw in drafts or []}
    for page in manifest['pages']:
        if page.get('language') == 'fr' and page['page_id'] in returned_pages:
            page['sha256'] = returned_pages[page['page_id']]
    merged, counts = merge_response(json.loads(files[EDITABLE_PATH], object_pairs_hook=_unique_fields), old,
        {r['page_id'] for r in request['selected']}, basis(manifest, registry, scope), sources)
    inputs.verify()
    return (merged if any(counts.values()) else None), counts


def save_notes(stage: Path, notes: dict) -> None:
    from wikidebia_creation_import import _path, _seal, _write
    _write(_path(stage, LEDGER_PATH), _json(_seal(notes)))


def context_notes(inputs: Any, corpus: Path, manifest: dict, registry: dict, scope: dict,
                  selected: set[str], canonical: dict) -> dict:
    notes = load_notes(inputs, corpus, manifest['debate_id'])
    current = basis(manifest, registry, scope)
    observations = [copy.deepcopy(r) for r in notes['observations'] if r['page_id'] in selected]
    searches = [copy.deepcopy(r) for r in notes['searches'] if set(r['page_ids']) & selected]
    refs = {r['resource_id'] for r in observations}
    refs.update(x for r in searches for x in r['resource_ids'])
    source_hashes = {r['id']: _sha(_json(r)) for r in notes['resources']}
    source_hashes.update({'source:' + r['id']: _sha(_json({k: r.get(k) for k in ('type', 'language', 'metadata')}))
                          for r in canonical['sources']})
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    for row in observations + searches:
        saved = row['page_basis_sha256']
        row['page_basis_changed'] = (saved != current.get(row['page_id']) if isinstance(saved, str)
                                    else any(current.get(k) != v for k, v in saved.items()))
        row['recheck_due'] = bool(row['recheck_after'] and row['recheck_after'] <= today)
        saved_resource = row['resource_basis_sha256']
        row['resource_basis_changed'] = (saved_resource != source_hashes.get(row['resource_id'])
            if isinstance(saved_resource, str) else any(source_hashes.get(k) != v for k, v in saved_resource.items()))
        row['requires_editorial_review'] = True
    resources = [copy.deepcopy(r) for r in notes['resources'] if r['id'] in refs]
    # Canonical references are contextual, not copied into the research ledger.
    identities = {r['identity_key'] for r in resources}
    canonical_rows = [copy.deepcopy(s) for s in canonical['sources']
                      if 'source:' + s['id'] in refs or _identity(s)[1] in identities]
    groups = {s.get('equivalence_group') for s in canonical_rows} - {None, ''}
    ids = {s['id'] for s in canonical_rows}
    canonical_rows.extend(copy.deepcopy(s) for s in canonical['sources']
                          if s['id'] not in ids and s.get('equivalence_group') in groups)
    grouped = build_resource_registry({'debate_id': manifest['debate_id'], 'sources': resources + canonical_rows}, '')
    for group in grouped['resources']:
        group['metadata_variants_require_review'] = len(group['source_ids']) > 1
    return {'schema': LEDGER_SCHEMA, 'resources': resources, 'canonical_sources': canonical_rows,
            'resource_identity_groups': [{k: g[k] for k in ('id', 'identity_type', 'identity_key', 'source_ids',
                 'languages', 'conflicts', 'metadata_variants_require_review')} for g in grouped['resources']],
            'observations': observations, 'searches': searches,
            'source_verification_performed': False, 'research_complete': False,
            'notice': 'Recorded observations only; re-evaluate dates, metadata variants and page-specific relevance. '
                      'A negative search never proves absence. No observation is a publication approval.'}


def selection(root: Path, corpus_path: str, max_pages: int, page_ids: list[str]):
    """Research-only selection; never reopen validated content for editing."""
    from wikidebia_creation_resume import ResumeInputs, creation_inventory, select_next
    from wikidebia_creation_context import build_creation_context
    inputs = ResumeInputs(root)
    inventory = creation_inventory(inputs, corpus_path)
    _require(type(max_pages) is int and 1 <= max_pages <= 20, 'max-pages outside 1..20')
    pages = {p['page_id']: p for p in inventory['pages']}
    if page_ids:
        _require(len(page_ids) <= 20 and len(set(page_ids)) == len(page_ids) and set(page_ids) <= pages.keys(),
                 'unknown, duplicate or oversized page selection')
        ids = page_ids
    else:
        ids = select_next(inventory, max_pages)['page_ids']
    _require(bool(ids), 'no current pages; use --page-id for documentary notes only')
    debate_id = inventory['debate_id']
    _require(debate_id not in ids or ids == [debate_id], 'prepare debate and argument research separately')
    _require(all(pages[key]['state'] != 'recorded_validated' for key in ids), 'validated pages need their ordinary review workflow')
    stage = 'debat-fr' if ids == [debate_id] else 'arguments-fr'
    deps = sorted({key for b in inventory['batches'] if set(b['node_ids']) & set(ids)
                   for key in b['dependency_node_ids']} - set(ids))
    context = build_creation_context(root, stage, corpus_path=corpus_path,
        node_ids=ids if stage == 'arguments-fr' else (), dependency_node_ids=deps)
    inputs.verify()
    task = {'debate_id': debate_id, 'next': {'action': 'research_only', 'page_ids': ids},
            'context': context, 'queue_sha256': _sha(_json([inventory, ids])), 'publication_authorized': False}
    return task, [pages[key] for key in ids], inputs.records


def response_help() -> bytes:
    return ("""# Notes documentaires facultatives, non validees

RESEARCH.json peut rester vide. Ne pas inventer une recherche, une consultation,
un extrait ou une date. Enregistrer seulement le travail effectivement realise.
Ne pas confondre observed_at/searched_at (observation) et metadata.date (publication).
Une recherche negative reste limitee a sa requete, sa date et son perimetre.
Les pages Wiki restent les seuls textes; ces notes ne sont jamais publiees.

Le fichier contient exactement schema, resources, observations et searches.
resources : key (cle locale unique), type (bibliography/webliography/videography),
language (code ISO ou null si inconnu), metadata (seuls champs connus : authors,
article, work, volume, issue, location, publisher, place, date, link, page, site,
title). authors est une liste, les autres champs des textes ou null.
Exiger un vrai titre et un lien public sans secret; hors ligne, identifier aussi
auteurs, date et editeur. Ne pas traduire artificiellement un titre documentaire.

observations : page_id, resource_key, state (located/consulted), observed_at
(date-heure ISO avec fuseau), locator, excerpt, assessment
(unassessed/supports/context_only/opposes/uncertain), reason, limitations,
recheck_after (AAAA-MM-JJ ou null). consulted exige locator, excerpt et reason
non vides, issus du contenu effectivement consulte. located garde assessment
unassessed et locator/excerpt vides. Un extrait est court, pas un article entier.
consulted est une declaration du redacteur, pas une verification du kit.

searches : page_ids (liste non vide), query, provider, searched_at (ISO avec
fuseau), outcome (found/no_result/inaccessible/not_relevant), resource_keys
(liste), notes (motif/perimetre), recheck_after (AAAA-MM-JJ ou null).
found exige une ressource; no_result ne peut en lister. Aucun minimum de sources.

resource_key/resource_keys vise une key nouvelle, un identifiant R... deja dans
le contexte, ou source:S0001 pour une source du registre canonique existant.
Chaque ressource nouvelle doit etre liee a une observation ou recherche.
Ne modifier que les pages selectionnees, pas leurs dependances de contexte.
Les observations visent le texte retourne dans ce meme paquet, ou le texte
inchange. Les ajouts sont cumulatifs: ne pas recopier les anciennes recherches.
Les variantes de metadonnees contradictoires sont preservees pour revue.
Les notes liees a un ancien texte affichent page_basis_changed; leur pertinence
est a reevaluer. Toute reference retenue exige encore son enregistrement et sa
verification dans les registres documentaires ordinaires.
""").encode('utf-8')
