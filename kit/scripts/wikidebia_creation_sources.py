"""Explicit documentary review of saved creation notes, never automatic verification.

A curated response contains identifiers and decisions, not copied bibliographies.
The canonical source registry is changed only on an explicitly attested review.
This is a local staging operation, with the draft import's recovery transaction.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from wikidebia_creation_context import CreationContextError, _json, _sha
from wikidebia_creation_research import _object, _text, _timestamp, _unique_fields, basis, load_notes
from wikidebia_documentary_resources import _identity

SCHEMA = 'wikidebia-creation-source-review-1.0'
AUDIT_SCHEMA = 'wikidebia-creation-source-audit-1.0'
EDITABLE_PATH = 'editable/SOURCES.json'
AUDIT_PATH = 'data/creation_source_reviews.json'
KINDS = {None, 'book', 'monograph', 'handbook', 'edited_volume', 'synthesis_report',
         'review_article', 'journal_article', 'book_chapter', 'conference_paper',
         'thesis', 'legal_text', 'other'}
DEBATE_ROLES = {'supports_introduction', 'pro_reference', 'con_reference', 'neutral_reference'}


def _require(ok: bool, why: str) -> None:
    if not ok:
        raise CreationContextError('Source review: ' + why)


def empty_response() -> dict:
    return {'schema': SCHEMA, 'reviewer': None, 'reviewed_at': None, 'decisions': []}


def help_text() -> bytes:
    return ("""# Revue explicite des references documentaires

Facultatif : laisser editable/SOURCES.json avec decisions=[] n'a aucun effet.
Utiliser `creation-package --research-only [--page-id A0001]`, sans toucher aux
textes ni statuts. Cette revue ne peut prendre que des notes RESEARCH deja
importees, accessibles dans context/CORPUS_CONTEXT.json. Ne jamais inventer
consultation, attestation, identite de relecteur, date ou preuve. La revue doit
etre effectivement realisee par le relecteur declare, sur la source elle-meme.

schema, reviewer, reviewed_at, decisions sont les seuls champs racine. Si une
selection est faite, reviewer (nom reel) et reviewed_at (ISO avec fuseau) sont
obligatoires. Chaque decision contient exactement :
- resource_id: identifiant R... de la note preexistante (jamais source:S...).
- document_kind: book/monograph/handbook/edited_volume/synthesis_report/
  review_article/journal_article/book_chapter/conference_paper/thesis/legal_text/
  other/null, choisi d'apres l'ouvrage reel, pas deduit du lien.
- primary_source: true ou false, apres examen.
- verification: {metadata_checked:true, language_verified:true,
  authorship_checked:true, authorship_verified:true/false, notes:"motif precis",
  variants_reviewed:true/false, variant_reason:"motif ou vide"}.
  authorship_verified est true si la notice comporte des auteurs; pour une
  notice sans auteur, il est false. Aucune valeur n'est precochée par le kit.
  En cas de variantes de meme identite, indiquer variants_reviewed=true et
  motiver le choix exact dans variant_reason ; aucun autre variant n'est efface.
- usages: liste non vide, chaque entree contient exactement :
  page_id, observation_id (O... consulted, supports, actuelle, propre a la page),
  role (supports_summary pour Argument ; supports_introduction/pro_reference/
  con_reference/neutral_reference pour Debat), selection_reason (motif propre
  a la page), documentary_scope (narrow_argument, introduction_fact,
  foundational_work ou broad_synthesis), also_develops_objections (true/false
  pour Argument, null pour Debat), objection_coverage_note (texte ou null).

La reference francaise doit avoir une langue fr explicite, des metadonnees
verifiees et le contenu consulte pour chaque usage. Tout champ documentaire
manquant doit etre recherche, puis conserve en nouvelle note/observation avant
la revue. La date de consultation n'est JAMAIS la date de publication.
Pour les pages Debate, seules les publications integralement francaises sont
admises. Les ressources d'autres langues restent dans le carnet : elles
suivent le workflow documentaire ordinaire, avec verification des equivalents.

L'import copie les notices depuis les notes, attribue les S... de facon
reproductible, dedoublonne par identite canonique, ajoute les usages et les
references reciproques des arguments, et garde un journal de revue. Il ne
modifie ni wikicode, ni statut de page, ni validation, ni wiki distant.
Une attestation de relecteur est une declaration, pas une preuve cryptographique
d'identite ou une verification independante effectuee par le logiciel.
Les controles documentaires et la revue editoriale finale restent obligatoires.
""").encode('utf-8')


def _review_response(raw: bytes) -> dict:
    value = json.loads(raw, object_pairs_hook=_unique_fields,
                       parse_constant=lambda _: _require(False, 'non-finite JSON value'))
    _object(value, {'schema', 'reviewer', 'reviewed_at', 'decisions'})
    _require(value['schema'] == SCHEMA and isinstance(value['decisions'], list)
             and len(value['decisions']) <= 100, 'unsupported schema or oversized selection')
    if value['decisions']:
        _text(value['reviewer'], limit=160)
        _timestamp(value['reviewed_at'])
    else:
        _require(value['reviewer'] is None and value['reviewed_at'] is None, 'empty review must not imply approval')
    return value


def _audit(corpus: Path, debate_id: str) -> dict:
    from wikidebia_creation_import import _path, _read
    path = _path(corpus, AUDIT_PATH)
    if not path.exists():
        return {'schema': AUDIT_SCHEMA, 'debate_id': debate_id, 'reviews': []}
    raw = json.loads(_read(path, 8 * 1024 * 1024), object_pairs_hook=_unique_fields)
    _object(raw, {'schema', 'debate_id', 'reviews', 'sha256'})
    signature = raw.pop('sha256')
    _require(raw['schema'] == AUDIT_SCHEMA and raw['debate_id'] == debate_id
             and isinstance(raw['reviews'], list) and signature == _sha(_json(raw)),
             'foreign or altered source review audit')
    return raw


def _materialize(resource: dict, decision: dict, reviewed_at: str, source_id: str) -> dict:
    from wikidebia_content_review import SOURCE_METADATA_FIELDS
    metadata = {key: copy.deepcopy(resource['metadata'].get(key, [] if key == 'authors' else None))
                for key in SOURCE_METADATA_FIELDS}
    for key, value in metadata.items():
        _require(value is None or (isinstance(value, list) if key == 'authors' else isinstance(value, str)),
                 'invalid documentary metadata')
    _require(isinstance(metadata['authors'], list), 'invalid author list')
    v = decision['verification']
    return {'id': source_id, 'type': resource['type'], 'language': resource['language'],
            'metadata': metadata,
            'verification': {'status': 'verified', 'verified_at': reviewed_at,
                             'primary_source': decision['primary_source'],
                             'notes': [v['notes']], 'language_verified': True,
                             'authorship_checked': True,
                             'authorship_verified': v['authorship_verified'],
                             'authorship_rechecked_after_site_match': False,
                             'authorship_recheck_notes': []},
            'usage': [], 'deduplication_key': resource['identity_key'],
            'document_kind': decision['document_kind'], 'equivalence_group': None}


def source_changes(root: Path, corpus: Path, request: dict, files: dict) -> tuple[dict | None, dict]:
    """Return only a validated, already-staged payload; never change live files."""
    from wikidebia_creation_import import _path
    from wikidebia_content_review import _validate_source_registry, SOURCES_WORKING_SCHEMA
    from wikidebia_creation_resume import ResumeInputs
    if EDITABLE_PATH not in request['files']:
        return None, {}  # Earlier draft packages remain importable.
    value = _review_response(files[EDITABLE_PATH])
    if not value['decisions']:
        return None, {}
    _require(request.get('research_only') is True, 'source review requires --research-only; drafts cannot be changed')
    inputs = ResumeInputs(root)
    manifest = inputs.document(corpus/'manifest.json')
    debate_id = manifest['debate_id']
    core = manifest['core_files']
    registry = inputs.document(_path(corpus, core['registry']))
    sources = inputs.document(_path(corpus, core['sources']))
    old = load_notes(inputs, corpus, debate_id)
    _require(old['resources'] and old['observations'], 'no saved evidence to review')
    selected = {r['page_id'] for r in request['selected']}
    current_basis = basis(manifest, registry, inputs.document(_path(corpus, core['scope'])))
    resources = {r['id']: r for r in old['resources']}
    observations = {r['id']: r for r in old['observations']}
    identity_groups: dict[str, list[str]] = {}
    for r in resources.values():
        identity_groups.setdefault(r['identity_key'], []).append(r['id'])
    canonical = copy.deepcopy(sources)
    new_registry = copy.deepcopy(registry)
    source_rows = canonical['sources']
    by_identity = {}
    for row in source_rows:
        key = _identity(row)[1]
        _require(key not in by_identity, 'existing canonical source identity collision')
        by_identity[key] = row
    by_node = {n['id']: n for n in new_registry['graph']['nodes'] if n['status'] == 'active'}
    next_number = max([int(r['id'][1:]) for r in source_rows
                       if re.fullmatch(r'S[0-9]{5,}', r['id'])] or [0]) + 1
    audit = _audit(corpus, debate_id)
    signatures = {r.get('decision_sha256') for r in audit['reviews']}
    touched, added_sources, added_usages = [], 0, 0
    seen_resources = set()
    for decision in value['decisions']:
        _object(decision, {'resource_id', 'document_kind', 'primary_source', 'verification', 'usages'})
        rid = decision['resource_id']
        _require(isinstance(rid, str) and rid in resources and rid not in seen_resources,
                 'unknown or duplicated research resource')
        seen_resources.add(rid)
        resource = resources[rid]
        _require(resource['language'] == 'fr', 'only a verified French edition can be adopted by this workflow')
        _require(decision['document_kind'] in KINDS and type(decision['primary_source']) is bool,
                 'document kind or primary-source assessment missing')
        meta = resource['metadata']
        if resource['type'] in {'webliography', 'videography'}:
            site = str(meta.get('site') or '').casefold().strip()
            label = str(meta.get('page') or meta.get('title') or '').casefold().strip()
            authors = {a.casefold().strip() for a in meta.get('authors') or []}
            _require(not site or (site != label and site not in authors),
                     'web/video author or title duplicates the site name')
        v = _object(decision['verification'], {'metadata_checked', 'language_verified',
                        'authorship_checked', 'authorship_verified', 'notes', 'variants_reviewed', 'variant_reason'})
        _require(all(v[k] is True for k in ('metadata_checked', 'language_verified', 'authorship_checked'))
                 and type(v['authorship_verified']) is bool and type(v['variants_reviewed']) is bool,
                 'documentary verification attestation incomplete')
        _text(v['notes'], limit=2000)
        _text(v['variant_reason'], empty=True, limit=2000)
        _require(v['authorship_verified'] == bool(resource['metadata'].get('authors')),
                 'authors must be verified only when credited')
        variants = identity_groups[resource['identity_key']]
        if len(variants) > 1:
            _require(v['variants_reviewed'] is True and len(v['variant_reason'].strip()) >= 12,
                     'source metadata variants need an explicit resolution')
        else:
            _require(not v['variant_reason'] and not v['variants_reviewed'],
                     'do not declare an inapplicable variants review')
        same = by_identity.get(resource['identity_key'])
        if same is not None:
            _require(same['type'] == resource['type'] and same['language'] == resource['language']
                     and same.get('verification', {}).get('status') == 'verified',
                     'canonical collision or unverified existing source')
            for key, field in resource['metadata'].items():
                if field not in (None, [], ''):
                    _require(same['metadata'].get(key) == field, 'conflicting metadata with canonical source')
            target = same
        else:
            source_id = f'S{next_number:05d}'
            next_number += 1
            target = _materialize(resource, decision, value['reviewed_at'], source_id)
            source_rows.append(target)
            by_identity[resource['identity_key']] = target
            added_sources += 1
        uses = decision['usages']
        _require(isinstance(uses, list) and 1 <= len(uses) <= 50, 'missing or oversized source usages')
        seen_uses = set()
        for use in uses:
            _object(use, {'page_id', 'observation_id', 'role', 'selection_reason',
                          'documentary_scope', 'also_develops_objections', 'objection_coverage_note'})
            page_id, role = use['page_id'], use['role']
            _require(isinstance(page_id, str) and page_id in selected and
                     (role in DEBATE_ROLES if page_id == debate_id else role == 'supports_summary'),
                     'foreign page or invalid source role')
            _require((page_id, role) not in seen_uses, 'duplicate usage for one page and role')
            seen_uses.add((page_id, role))
            _text(use['selection_reason'], limit=2000)
            _require(len(use['selection_reason'].strip()) >= 20, 'page-specific selection rationale too short')
            expected_scope = ({'foundational_work', 'broad_synthesis'} if page_id == debate_id
                              and resource['type'] == 'bibliography' and role != 'supports_introduction'
                              else {'introduction_fact'} if page_id == debate_id else {'narrow_argument'})
            _require(use['documentary_scope'] in expected_scope, 'invalid documentary scope for role')
            _require((type(use['also_develops_objections']) is bool if page_id != debate_id
                      else use['also_develops_objections'] is None)
                     and (use['objection_coverage_note'] is None or isinstance(use['objection_coverage_note'], str)),
                     'invalid objection coverage attestation')
            obs = observations.get(use['observation_id'])
            _require(obs is not None and obs.get('resource_id') == rid and obs.get('page_id') == page_id
                     and obs.get('state') == 'consulted' and obs.get('assessment') == 'supports',
                     'usage must cite a consulted supporting observation for this page and resource')
            from datetime import datetime, timezone
            _require(datetime.fromisoformat(obs['observed_at'].replace('Z', '+00:00'))
                     <= datetime.fromisoformat(value['reviewed_at'].replace('Z', '+00:00')),
                     'source review predates the cited consultation')
            _require(obs['page_basis_sha256'] == current_basis[page_id]
                     and obs['resource_basis_sha256'] == _sha(_json(resource)),
                     'research evidence stale after page/graph/metadata change')
            _require(obs.get('recheck_after') is None or obs['recheck_after'] > datetime.now(timezone.utc).date().isoformat(),
                     'research evidence due for recheck')
            usage = {'page_id': page_id, 'language': 'fr', 'role': role,
                     'language_fit': 'native', 'preferred_equivalent_source_id': None,
                     'documentary_scope': use['documentary_scope'],
                     'selection_reason': use['selection_reason'],
                     'argument_development_verified': True if page_id != debate_id else False,
                     'also_develops_objections': use['also_develops_objections'] if page_id != debate_id else False,
                     'objection_coverage_note': use['objection_coverage_note']}
            matched = [u for u in target['usage'] if u['page_id'] == page_id and u['language'] == 'fr' and u['role'] == role]
            _require(not matched or matched == [usage], 'conflicting existing usage must not be replaced')
            if not matched:
                target['usage'].append(usage)
                added_usages += 1
            if page_id != debate_id:
                node = by_node.get(page_id)
                _require(node is not None, 'unknown argument node')
                refs = node['sources']['fr'][resource['type']]
                if target['id'] not in refs:
                    refs.append(target['id'])
        sig = _sha(_json([value['reviewer'], value['reviewed_at'], decision]))
        if sig not in signatures:
            signatures.add(sig)
            touched.append({'decision_sha256': sig, 'reviewer': value['reviewer'],
                            'reviewed_at': value['reviewed_at'], 'resource_id': rid,
                            'canonical_source_id': target['id'],
                            'observations': [use['observation_id'] for use in uses]})
    _validate_source_registry({'schema': SOURCES_WORKING_SCHEMA, 'debate_id': debate_id,
                               'sources': source_rows}, debate_id)
    _require(len(_json(canonical)) <= 8 * 1024 * 1024, 'source registry too large')
    inputs.verify()
    if added_sources == 0 and added_usages == 0 and not touched:
        return None, {}
    audit['reviews'].extend(touched)
    return {'sources': canonical, 'registry': new_registry, 'audit': audit}, {
        'sources_added': added_sources, 'usages_added': added_usages,
        'reviews_recorded': len(touched), 'independent_verification_performed': False}


def save_source_changes(stage: Path, changes: dict, core: dict) -> None:
    from wikidebia_creation_import import _path, _write, _seal
    _write(_path(stage, core['sources']), _json(changes['sources']))
    _write(_path(stage, core['registry']), _json(changes['registry']))
    _write(_path(stage, AUDIT_PATH), _json(_seal(changes['audit'])))
