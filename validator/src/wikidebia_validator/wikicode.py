from __future__ import annotations
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from .graph import state_at_least
from .package import PackageContext
from .historical_summary import (
    protected_historical_summary_keys as _shared_protected_historical_summary_keys,
    historically_absent_summary_keys as _shared_historically_absent_summary_keys,
    owner_removed_summary_keys as _shared_owner_removed_summary_keys,
)
from .translation import english_translation_deferred

@dataclass
class Template:
    name: str
    params: list[tuple[str, str]]
    raw: str

    def values(self, name: str) -> list[str]:
        return [v for k, v in self.params if k == name]

    def one(self, name: str) -> str | None:
        vals = self.values(name)
        return vals[0] if vals else None

class WikiParseError(ValueError):
    pass

def _extract_outer(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith('{{'):
        raise WikiParseError('Le fichier ne commence pas par un modèle')
    depth = 0
    end = None
    i = 0
    while i < len(stripped) - 1:
        pair = stripped[i:i + 2]
        if pair == '{{':
            depth += 1
            i += 2
            continue
        if pair == '}}':
            depth -= 1
            i += 2
            if depth == 0:
                end = i
                break
            if depth < 0:
                raise WikiParseError('Fermeture de modèle surnuméraire')
            continue
        i += 1
    if end is None or depth != 0:
        raise WikiParseError('Modèle non fermé')
    if stripped[end:].strip():
        raise WikiParseError('Texte extérieur au modèle principal')
    return stripped[:end]

def _split_top_level(content: str) -> list[str]:
    parts: list[str] = []
    start = 0
    brace_depth = 0
    link_depth = 0
    external_link_depth = 0
    i = 0
    while i < len(content):
        pair = content[i:i + 2]
        if pair == '{{':
            brace_depth += 1
            i += 2
            continue
        if pair == '}}':
            brace_depth -= 1
            i += 2
            continue
        if pair == '[[':
            link_depth += 1
            i += 2
            continue
        if pair == ']]':
            link_depth = max(0, link_depth - 1)
            i += 2
            continue
        if content[i] == '[' and link_depth == 0:
            external_link_depth += 1
            i += 1
            continue
        if content[i] == ']' and link_depth == 0 and external_link_depth:
            external_link_depth -= 1
            i += 1
            continue
        if content[i] == '|' and brace_depth == 0 and (link_depth == 0) and (external_link_depth == 0):
            tail = content[i + 1:]
            match = re.match('[ \t]*([^=|{}\\n]+?)=', tail)
            if match:
                parts.append(content[start:i])
                start = i + 1
        i += 1
    parts.append(content[start:])
    return parts

def parse_template(text: str) -> Template:
    raw = _extract_outer(text)
    inner = raw[2:-2]
    parts = _split_top_level(inner)
    name = parts[0].strip()
    if not name:
        raise WikiParseError('Nom de modèle vide')
    params: list[tuple[str, str]] = []
    for part in parts[1:]:
        if '=' not in part:
            raise WikiParseError(f'Paramètre sans signe égal : {part[:80]!r}')
        key, value = part.split('=', 1)
        key = key.strip()
        if not key:
            raise WikiParseError('Nom de paramètre vide')
        params.append((key, value.strip()))
    return Template(name, params, raw)

def parse_template_sequence(value: str) -> list[Template]:
    templates: list[Template] = []
    i = 0
    while i < len(value):
        while i < len(value) and value[i].isspace():
            i += 1
        if i >= len(value):
            break
        if value[i:i + 2] != '{{':
            raise WikiParseError('Contenu non-modèle inattendu dans une séquence de sous-modèles')
        depth = 0
        start = i
        while i < len(value) - 1:
            pair = value[i:i + 2]
            if pair == '{{':
                depth += 1
                i += 2
                continue
            if pair == '}}':
                depth -= 1
                i += 2
                if depth == 0:
                    templates.append(parse_template(value[start:i]))
                    break
                continue
            i += 1
        else:
            raise WikiParseError('Sous-modèle non fermé')
    return templates

def _mixed_citations(value: str) -> tuple[list[Template], list[tuple[int, str]]]:
    templates, passages = [], []
    cursor = 0
    while cursor < len(value):
        start = value.find('{{', cursor)
        if start < 0:
            if value[cursor:].strip(): passages.append((len(templates), value[cursor:].strip()))
            break
        if value[cursor:start].strip(): passages.append((len(templates), value[cursor:start].strip()))
        depth, end = 0, start
        while end < len(value) - 1:
            pair = value[end:end+2]
            if pair == '{{': depth += 1; end += 2
            elif pair == '}}':
                depth -= 1; end += 2
                if depth == 0: break
            else: end += 1
        if depth: raise WikiParseError('Citation non fermée')
        templates.append(parse_template(value[start:end])); cursor = end
    return templates, passages
TOP_LEGACY = {('fr', 'debate'): {'model': 'Débat', 'order': ['sujet', 'sujet-complet', 'avancement', 'avertissements-titre', 'avertissements-débat', 'introduction', 'articles-Wikipédia', 'arguments-pour', 'arguments-contre', 'avertissements-bibliographie', 'bibliographie-pour', 'bibliographie-contre', 'bibliographie-ni-pour-ni-contre', 'avertissements-sitographie', 'sitographie-pour', 'sitographie-contre', 'sitographie-ni-pour-ni-contre', 'avertissements-vidéographie', 'vidéographie-pour', 'vidéographie-contre', 'vidéographie-ni-pour-ni-contre', 'débats-connexes', 'rubriques', 'mots-clés', 'interlangue', 'date-création'], 'required': ['sujet', 'sujet-complet', 'avancement', 'avertissements-débat', 'introduction', 'arguments-pour', 'arguments-contre', 'rubriques', 'mots-clés', 'date-création'], 'fixed': {'avancement': 'Débat construit', 'avertissements-débat': 'Débat généré par IA'}, 'forbidden_generated': ['avertissements-titre', 'avertissements-bibliographie', 'avertissements-sitographie', 'avertissements-vidéographie']}, ('en', 'debate'): {'model': 'Debate', 'order': ['type', 'topic', 'progress', 'title-warnings', 'debate-warnings', 'introduction', 'wikipedia-articles', 'pro-arguments', 'con-arguments', 'pro-bibliography', 'con-bibliography', 'bibliography', 'pro-webliography', 'con-webliography', 'webliography', 'pro-videography', 'con-videography', 'videography', 'related-debates', 'sections', 'keywords', 'creation-date'], 'required': ['type', 'topic', 'progress', 'debate-warnings', 'introduction', 'pro-arguments', 'con-arguments', 'sections', 'keywords', 'creation-date'], 'fixed': {'progress': 'Constructed debate', 'debate-warnings': 'Debate generated by AI'}, 'forbidden_generated': ['title-warnings']}, ('fr', 'argument'): {'model': 'Argument', 'order': ['initialisation', 'nom', 'avertissements-titre', 'avertissements-argument', 'avertissements-résumé', 'résumé', 'citations', 'avertissements-références', 'références-bibliographiques', 'références-sitographiques', 'références-vidéographiques', 'avertissements-justifications', 'justifications', 'avertissements-objections', 'objections', 'débat-détaillé', 'rubriques', 'mots-clés', 'interlangue', 'date-création'], 'required': ['avertissements-argument', 'résumé', 'rubriques', 'mots-clés', 'date-création'], 'fixed': {'avertissements-argument': 'Argument généré par IA'}, 'forbidden_generated': ['initialisation', 'nom', 'avertissements-titre', 'avertissements-résumé', 'citations', 'avertissements-références', 'avertissements-justifications', 'avertissements-objections', 'débat-détaillé']}, ('en', 'argument'): {'model': 'Argument', 'order': ['initialization', 'name', 'title-warnings', 'argument-warnings', 'summary-warnings', 'summary', 'quotes', 'reference-warnings', 'bibliography', 'webliography', 'videography', 'justification-warnings', 'justifications', 'objection-warnings', 'objections', 'detailed-debate', 'sections', 'keywords', 'creation-date'], 'required': ['argument-warnings', 'summary', 'sections', 'keywords', 'creation-date'], 'fixed': {'argument-warnings': 'Argument generated by AI'}, 'forbidden_generated': ['initialization', 'name', 'title-warnings', 'summary-warnings', 'quotes', 'reference-warnings', 'justification-warnings', 'objection-warnings', 'detailed-debate']}}
# Historical public compatibility constant preserved bit-for-bit in meaning for
# feature-baseline audits. Runtime validation uses ACTIVE_TOP below.
TOP = {('fr', 'debate'): {'model': 'Débat',
                    'order': ['sujet',
                              'sujet-complet',
                              'avancement',
                              'avertissements-titre',
                              'avertissements-débat',
                              'introduction',
                              'articles-Wikipédia',
                              'arguments-pour',
                              'arguments-contre',
                              'avertissements-bibliographie',
                              'bibliographie-pour',
                              'bibliographie-contre',
                              'bibliographie-ni-pour-ni-contre',
                              'avertissements-sitographie',
                              'sitographie-pour',
                              'sitographie-contre',
                              'sitographie-ni-pour-ni-contre',
                              'avertissements-vidéographie',
                              'vidéographie-pour',
                              'vidéographie-contre',
                              'vidéographie-ni-pour-ni-contre',
                              'débats-connexes',
                              'rubriques',
                              'mots-clés',
                              'interlangue',
                              'date-création'],
                    'required': ['sujet', 'sujet-complet', 'avancement', 'avertissements-débat', 'introduction', 'arguments-pour', 'arguments-contre', 'rubriques', 'mots-clés', 'date-création'],
                    'fixed': {'avancement': 'Débat construit', 'avertissements-débat': 'Débat généré par IA'},
                    'forbidden_generated': ['avertissements-titre', 'avertissements-bibliographie', 'avertissements-sitographie', 'avertissements-vidéographie']},
 ('en', 'debate'): {'model': 'Debate',
                    'order': ['topic',
                              'complete-topic',
                              'progress',
                              'title-warnings',
                              'debate-warnings',
                              'introduction',
                              'wikipedia-articles',
                              'pro-arguments',
                              'con-arguments',
                              'pro-bibliography',
                              'con-bibliography',
                              'bibliography',
                              'pro-webliography',
                              'con-webliography',
                              'webliography',
                              'pro-videography',
                              'con-videography',
                              'videography',
                              'related-debates',
                              'sections',
                              'keywords',
                              'creation-date'],
                    'required': ['topic', 'complete-topic', 'progress', 'debate-warnings', 'introduction', 'pro-arguments', 'con-arguments', 'sections', 'keywords', 'creation-date'],
                    'fixed': {'progress': 'Constructed debate', 'debate-warnings': 'Debate generated by AI'},
                    'forbidden_generated': ['title-warnings']},
 ('fr', 'argument'): {'model': 'Argument',
                      'order': ['initialisation',
                                'nom-consacré',
                                'nom',
                                'titre-affiché',
                                'avertissements-titre',
                                'avertissements-argument',
                                'avertissements-résumé',
                                'résumé',
                                'citations',
                                'avertissements-références',
                                'références-bibliographiques',
                                'références-sitographiques',
                                'références-vidéographiques',
                                'avertissements-justifications',
                                'justifications',
                                'avertissements-objections',
                                'objections',
                                'débat-détaillé',
                                'rubriques',
                                'mots-clés',
                                'interlangue',
                                'date-création'],
                      'required': ['avertissements-argument', 'résumé', 'rubriques', 'mots-clés', 'date-création'],
                      'fixed': {'avertissements-argument': 'Argument généré par IA'},
                      'forbidden_generated': ['initialisation',
                                              'nom-consacré',
                                              'nom',
                                              'titre-affiché',
                                              'avertissements-titre',
                                              'avertissements-résumé',
                                              'citations',
                                              'avertissements-références',
                                              'avertissements-justifications',
                                              'avertissements-objections',
                                              'débat-détaillé']},
 ('en', 'argument'): {'model': 'Argument',
                      'order': ['initialization',
                                'established-name',
                                'name',
                                'title-warnings',
                                'argument-warnings',
                                'summary-warnings',
                                'summary',
                                'quotes',
                                'reference-warnings',
                                'bibliography',
                                'webliography',
                                'videography',
                                'justification-warnings',
                                'justifications',
                                'objection-warnings',
                                'objections',
                                'detailed-debate',
                                'sections',
                                'keywords',
                                'creation-date'],
                      'required': ['argument-warnings', 'summary', 'sections', 'keywords', 'creation-date'],
                      'fixed': {'argument-warnings': 'Argument generated by AI'},
                      'forbidden_generated': ['initialization',
                                              'established-name',
                                              'name',
                                              'title-warnings',
                                              'summary-warnings',
                                              'quotes',
                                              'reference-warnings',
                                              'justification-warnings',
                                              'objection-warnings',
                                              'detailed-debate']}}

# Canonical MediaWiki parameter contract for new/current packages (1.2.69+).
ACTIVE_TOP = {('fr', 'debate'): {'model': 'Débat',
                    'order': ['sujet',
                              'sujet-développé',
                              'avancement',
                              'avertissements-titre',
                              'avertissements-débat',
                              'introduction',
                              'articles-Wikipédia',
                              'arguments-pour',
                              'arguments-contre',
                              'avertissements-bibliographie',
                              'bibliographie-pour',
                              'bibliographie-contre',
                              'bibliographie-ni-pour-ni-contre',
                              'avertissements-sitographie',
                              'sitographie-pour',
                              'sitographie-contre',
                              'sitographie-ni-pour-ni-contre',
                              'avertissements-vidéographie',
                              'vidéographie-pour',
                              'vidéographie-contre',
                              'vidéographie-ni-pour-ni-contre',
                              'débats-connexes',
                              'rubriques',
                              'mots-clés',
                              'interlangue',
                              'date-création'],
                    'required': ['sujet', 'sujet-développé', 'avancement', 'avertissements-débat', 'introduction', 'arguments-pour', 'arguments-contre', 'rubriques', 'mots-clés', 'date-création'],
                    'fixed': {'avancement': 'Débat construit', 'avertissements-débat': 'Débat généré par IA'},
                    'forbidden_generated': ['avertissements-titre', 'avertissements-bibliographie', 'avertissements-sitographie', 'avertissements-vidéographie']},
 ('en', 'debate'): {'model': 'Debate',
                    'order': ['topic',
                              'expanded-topic',
                              'progress',
                              'title-warnings',
                              'debate-warnings',
                              'introduction',
                              'wikipedia-articles',
                              'pro-arguments',
                              'con-arguments',
                              'pro-bibliography',
                              'con-bibliography',
                              'bibliography',
                              'pro-webliography',
                              'con-webliography',
                              'webliography',
                              'pro-videography',
                              'con-videography',
                              'videography',
                              'related-debates',
                              'sections',
                              'keywords',
                              'creation-date'],
                    'required': ['topic', 'expanded-topic', 'progress', 'debate-warnings', 'introduction', 'pro-arguments', 'con-arguments', 'sections', 'keywords', 'creation-date'],
                    'fixed': {'progress': 'Constructed debate', 'debate-warnings': 'Debate generated by AI'},
                    'forbidden_generated': ['title-warnings']},
 ('fr', 'argument'): {'model': 'Argument',
                      'order': ['initialisation',
                                'nom-consacré',
                                'nom',
                                'titre-affiché',
                                'avertissements-titre',
                                'avertissements-argument',
                                'avertissements-résumé',
                                'résumé',
                                'citations',
                                'avertissements-références',
                                'références-bibliographiques',
                                'références-sitographiques',
                                'références-vidéographiques',
                                'avertissements-justifications',
                                'justifications',
                                'avertissements-objections',
                                'objections',
                                'débat-dédié',
                                'rubriques',
                                'mots-clés',
                                'interlangue',
                                'date-création'],
                      'required': ['avertissements-argument', 'résumé', 'rubriques', 'mots-clés', 'date-création'],
                      'fixed': {'avertissements-argument': 'Argument généré par IA'},
                      'forbidden_generated': ['initialisation',
                                              'nom-consacré',
                                              'nom',
                                              'titre-affiché',
                                              'avertissements-titre',
                                              'avertissements-résumé',
                                              'citations',
                                              'avertissements-références',
                                              'avertissements-justifications',
                                              'avertissements-objections',
                                              'débat-dédié']},
 ('en', 'argument'): {'model': 'Argument',
                      'order': ['initialization',
                                'established-name',
                                'name',
                                'title-warnings',
                                'argument-warnings',
                                'summary-warnings',
                                'summary',
                                'quotes',
                                'reference-warnings',
                                'bibliography',
                                'webliography',
                                'videography',
                                'justification-warnings',
                                'justifications',
                                'objection-warnings',
                                'objections',
                                'dedicated-debate',
                                'sections',
                                'keywords',
                                'creation-date'],
                      'required': ['argument-warnings', 'summary', 'sections', 'keywords', 'creation-date'],
                      'fixed': {'argument-warnings': 'Argument generated by AI'},
                      'forbidden_generated': ['initialization',
                                              'established-name',
                                              'name',
                                              'title-warnings',
                                              'summary-warnings',
                                              'quotes',
                                              'reference-warnings',
                                              'justification-warnings',
                                              'objection-warnings',
                                              'dedicated-debate']}}
SUB = {'Sous-partie': (['titre', 'contenu', 'avertissements'], ['titre', 'contenu']), 'Subsection': (['title', 'content', 'warnings'], ['title', 'content']), 'Article Wikipédia': (['page'], ['page']), 'Wikipedia article': (['page'], ['page']), 'Argument pour': (['page', 'titre-affiché', 'avertissements'], ['page', 'titre-affiché']), 'Argument contre': (['page', 'titre-affiché', 'avertissements'], ['page', 'titre-affiché']), 'Pro argument': (['page', 'displayed-title', 'warnings'], ['page', 'displayed-title']), 'Con argument': (['page', 'displayed-title', 'warnings'], ['page', 'displayed-title']), 'Justification': (['page', 'titre-affiché', 'displayed-title', 'avertissements', 'warnings'], ['page']), 'Objection': (['page', 'titre-affiché', 'displayed-title', 'avertissements', 'warnings'], ['page']), 'Interlangue': (['langue', 'page'], ['langue', 'page']), 'Lien interlangue': (['langue', 'page'], ['langue', 'page']), 'Débat connexe': (['page'], ['page']), 'Related debate': (['page'], ['page']), 'Référence bibliographique': (['auteurs', 'article', 'ouvrage', 'volume', 'numéro', 'localisation', 'page', 'édition', 'lieu', 'date', 'lien', 'avertissements'], ['auteurs']), 'Référence bibliographique pour': (['auteurs', 'article', 'ouvrage', 'volume', 'numéro', 'localisation', 'page', 'édition', 'lieu', 'date', 'lien', 'avertissements'], ['auteurs']), 'Référence bibliographique contre': (['auteurs', 'article', 'ouvrage', 'volume', 'numéro', 'localisation', 'page', 'édition', 'lieu', 'date', 'lien', 'avertissements'], ['auteurs']), 'Bibliographical reference': (['authors', 'article', 'work', 'volume', 'issue', 'location', 'page', 'publisher', 'place', 'date', 'link', 'warnings'], ['authors']), 'Pro bibliographical reference': (['authors', 'article', 'work', 'volume', 'issue', 'location', 'page', 'publisher', 'place', 'date', 'link', 'warnings'], ['authors']), 'Con bibliographical reference': (['authors', 'article', 'work', 'volume', 'issue', 'location', 'page', 'publisher', 'place', 'date', 'link', 'warnings'], ['authors']), 'Référence sitographique': (['lien', 'page', 'auteurs', 'site', 'date', 'avertissements'], ['lien', 'site']), 'Référence sitographique pour': (['lien', 'page', 'auteurs', 'site', 'date', 'avertissements'], ['lien', 'site']), 'Référence sitographique contre': (['lien', 'page', 'auteurs', 'site', 'date', 'avertissements'], ['lien', 'site']), 'Web reference': (['link', 'page', 'authors', 'site', 'date', 'warnings'], ['link', 'site']), 'Pro web reference': (['link', 'page', 'authors', 'site', 'date', 'warnings'], ['link', 'site']), 'Con web reference': (['link', 'page', 'authors', 'site', 'date', 'warnings'], ['link', 'site']), 'Référence vidéographique': (['titre', 'auteurs', 'lien', 'avertissements'], ['titre', 'lien']), 'Référence vidéographique pour': (['titre', 'auteurs', 'lien', 'avertissements'], ['titre', 'lien']), 'Référence vidéographique contre': (['titre', 'auteurs', 'lien', 'avertissements'], ['titre', 'lien']), 'Video reference': (['title', 'authors', 'link', 'warnings'], ['title', 'link']), 'Pro video reference': (['title', 'authors', 'link', 'warnings'], ['title', 'link']), 'Con video reference': (['title', 'authors', 'link', 'warnings'], ['title', 'link']), 'Citation': ([], ['citation']), 'Quote': (['quote', 'authors', 'article', 'work', 'volume', 'issue', 'page', 'location', 'publisher', 'place', 'date', 'link', 'warnings', 'citation', 'auteurs', 'ouvrage', 'numéro', 'localisation', 'édition', 'lieu', 'lien', 'avertissements-citation', 'avertissements'], [])}
SEQUENCE_PARAMS = {'introduction', 'articles-Wikipédia', 'arguments-pour', 'arguments-contre', 'bibliographie-pour', 'bibliographie-contre', 'bibliographie-ni-pour-ni-contre', 'sitographie-pour', 'sitographie-contre', 'sitographie-ni-pour-ni-contre', 'vidéographie-pour', 'vidéographie-contre', 'vidéographie-ni-pour-ni-contre', 'débats-connexes', 'wikipedia-articles', 'pro-arguments', 'con-arguments', 'pro-bibliography', 'con-bibliography', 'bibliography', 'pro-webliography', 'con-webliography', 'webliography', 'pro-videography', 'con-videography', 'videography', 'related-debates', 'références-bibliographiques', 'références-sitographiques', 'références-vidéographiques', 'justifications', 'objections', 'interlangue', 'citations', 'quotes'}
PARAM_TEMPLATE_ALLOWED = {'introduction': {'Sous-partie', 'Subsection'}, 'articles-Wikipédia': {'Article Wikipédia'}, 'wikipedia-articles': {'Wikipedia article'}, 'arguments-pour': {'Argument pour'}, 'arguments-contre': {'Argument contre'}, 'pro-arguments': {'Pro argument'}, 'con-arguments': {'Con argument'}, 'bibliographie-pour': {'Référence bibliographique pour'}, 'bibliographie-contre': {'Référence bibliographique contre'}, 'bibliographie-ni-pour-ni-contre': {'Référence bibliographique'}, 'pro-bibliography': {'Pro bibliographical reference'}, 'con-bibliography': {'Con bibliographical reference'}, 'bibliography': {'Bibliographical reference'}, 'sitographie-pour': {'Référence sitographique pour'}, 'sitographie-contre': {'Référence sitographique contre'}, 'sitographie-ni-pour-ni-contre': {'Référence sitographique'}, 'pro-webliography': {'Pro web reference'}, 'con-webliography': {'Con web reference'}, 'webliography': {'Web reference'}, 'vidéographie-pour': {'Référence vidéographique pour'}, 'vidéographie-contre': {'Référence vidéographique contre'}, 'vidéographie-ni-pour-ni-contre': {'Référence vidéographique'}, 'pro-videography': {'Pro video reference'}, 'con-videography': {'Con video reference'}, 'videography': {'Video reference'}, 'débats-connexes': {'Débat connexe'}, 'related-debates': {'Related debate'}, 'références-bibliographiques': {'Référence bibliographique'}, 'références-sitographiques': {'Référence sitographique'}, 'références-vidéographiques': {'Référence vidéographique'}, 'justifications': {'Justification'}, 'objections': {'Objection'}, 'citations': {'Citation'}, 'quotes': {'Quote'}, 'interlangue': {'Interlangue', 'Lien interlangue'}}
FR_SECTIONS = ['Aménagement', 'Culture', 'Droit', 'Écologie', 'Économie', 'Éducation', 'Éthique', 'Géopolitique', 'Histoire', 'Philosophie', 'Politique', 'Psychologie', 'Religion et spiritualité', 'Santé', 'Science', 'Société', 'Sport et loisirs', 'Technologie']
EN_SECTIONS = ['Planning', 'Culture', 'Law', 'Ecology', 'Economy', 'Education', 'Ethics', 'Geopolitics', 'History', 'Philosophy', 'Politics', 'Psychology', 'Religion and spirituality', 'Health', 'Science', 'Society', 'Sport and leisure', 'Technology']
EN_MONTHS = {'January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'}
FR_MONTHS = {'janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'}
EN_PLACES_EXPECTED_FR = {'London': 'Londres', 'Brussels': 'Bruxelles', 'Geneva': 'Genève', 'Copenhagen': 'Copenhague', 'The Hague': 'La Haye'}
FR_PLACES_EXPECTED_EN = {value: key for key, value in EN_PLACES_EXPECTED_FR.items()}
MACHINE_DOCUMENTARY_DATE_RE = re.compile('^\\d{4}-\\d{2}(?:-\\d{2})?(?:[T ]\\d{2}:\\d{2}(?::\\d{2})?(?:Z|[+-]\\d{2}:?\\d{2})?)?$')

def documentary_date_is_machine(value: str) -> bool:
    """Return True for ISO-like documentary dates; bare years remain valid."""
    return bool(MACHINE_DOCUMENTARY_DATE_RE.fullmatch(value.strip()))

def explicit_parenthetical_acronym(value: str) -> str | None:
    match = re.search('\\(([A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ0-9.-]{1,9})\\)', value)
    return match.group(1) if match else None

def _check_reference_language_and_typography(ctx: PackageContext, tmpl: Template, rel: str, lang: str) -> None:
    """Apply active 1.0.6 language-sensitive documentary rules."""
    if lang == 'fr':
        for match in re.finditer('[.!?;:]\\s*<ref(?:\\s|>)', tmpl.raw, flags=re.IGNORECASE):
            ctx.report.error('WDV-MWK-014', "Dans le texte français, l'appel de référence doit précéder le signe de ponctuation final", path=rel, details={'offset': match.start()})
    for key, value in tmpl.params:
        if key not in SEQUENCE_PARAMS:
            continue
        try:
            subs = parse_template_sequence(value)
        except WikiParseError:
            continue
        for sub in subs:
            date_value = sub.one('date') or ''
            place_value = sub.one('lieu' if lang == 'fr' else 'place') or ''
            if lang == 'fr':
                foreign_months = sorted((month for month in EN_MONTHS if re.search(f'\\b{re.escape(month)}\\b', date_value)))
                if foreign_months:
                    ctx.report.error('WDV-MWK-014', 'Date descriptive anglaise dans une page française', path=rel, details={'template': sub.name, 'date': date_value, 'months': foreign_months})
                if place_value in EN_PLACES_EXPECTED_FR:
                    ctx.report.error('WDV-MWK-014', 'Nom de lieu non adapté au français', path=rel, details={'actual': place_value, 'expected': EN_PLACES_EXPECTED_FR[place_value]})
            else:
                foreign_months = sorted((month for month in FR_MONTHS if re.search(f'\\b{re.escape(month)}\\b', date_value, flags=re.IGNORECASE)))
                if foreign_months:
                    ctx.report.error('WDV-MWK-014', 'Date descriptive française dans une page anglaise', path=rel, details={'template': sub.name, 'date': date_value, 'months': foreign_months})
                if place_value in FR_PLACES_EXPECTED_EN:
                    ctx.report.error('WDV-MWK-014', "Nom de lieu non adapté à l'anglais", path=rel, details={'actual': place_value, 'expected': FR_PLACES_EXPECTED_EN[place_value]})

def split_list(value: str) -> list[str]:
    return [x.strip() for x in value.split(',') if x.strip()]

def _alphabetical_key(value: str) -> str:
    folded = unicodedata.normalize('NFKD', value.casefold())
    return ''.join((c for c in folded if not unicodedata.combining(c)))

def alphabetically_sorted(values: list[str]) -> list[str]:
    return sorted(values, key=_alphabetical_key)

def _first_alpha_is_upper(value: str) -> bool:
    first = next((c for c in value.strip() if c.isalpha()), '')
    return bool(first and first.isupper())

def _first_alpha_is_lower(value: str) -> bool:
    first = next((c for c in value.strip() if c.isalpha()), '')
    return bool(first and first.islower())

def _complete_topic_looks_interrogative(value: str, lang: str) -> bool:
    clean = value.strip()
    if not clean or '?' in clean:
        return True
    if lang == 'fr':
        return bool(re.match('^(?:si\\b|faut[- ]?il\\b|est[- ]?ce\\s+que\\b|doit[- ]?on\\b|peut[- ]?on\\b)', clean, flags=re.I))
    return bool(re.match('^(?:whether\\b|if\\b|should\\b|can\\b|could\\b|is\\b|are\\b|do\\b|does\\b|must\\b)', clean, flags=re.I))
SPLIT_ADJACENT_TEMPLATES_RE = re.compile('}}[ \\t\\r\\n]+\\{\\{')

def split_adjacent_templates(text: str) -> list[re.Match[str]]:
    """Return forbidden whitespace-separated adjacent template boundaries."""
    return list(SPLIT_ADJACENT_TEMPLATES_RE.finditer(text))
PROTECTED_PAGE_PARAMETERS = {('fr', 'debate'): ('avancement', 'avertissements-titre', 'avertissements-débat', 'avertissements-bibliographie', 'avertissements-sitographie', 'avertissements-vidéographie', 'débats-connexes', 'interlangue', 'date-création'), ('en', 'debate'): ('progress', 'title-warnings', 'debate-warnings', 'related-debates', 'creation-date'), ('fr', 'argument'): ('initialisation', 'nom-consacré', 'nom', 'titre-affiché', 'avertissements-titre', 'avertissements-argument', 'avertissements-résumé', 'avertissements-références', 'avertissements-justifications', 'avertissements-objections', 'débat-dédié', 'interlangue', 'date-création'), ('en', 'argument'): ('initialization', 'established-name', 'name', 'title-warnings', 'argument-warnings', 'summary-warnings', 'reference-warnings', 'justification-warnings', 'objection-warnings', 'dedicated-debate', 'creation-date')}

def _protected_page_parameters(ctx: PackageContext, lang: str, page_type: str) -> tuple[str, ...]:
    return PROTECTED_PAGE_PARAMETERS[lang, page_type]
    legacy = {('fr', 'debate'): ('avancement', 'avertissements-débat', 'débats-connexes'), ('en', 'debate'): ('progress', 'debate-warnings', 'related-debates'), ('fr', 'argument'): ('avertissements-argument',), ('en', 'argument'): ('argument-warnings',)}[lang, page_type]
    if page_type != 'argument':
        return legacy
    controls = (ctx.manifest() or {}).get('editorial_controls') or {}
    protected_fields = set((controls.get('legacy_content_preservation') or {}).get('protected_fields') or [])
    extra: list[str] = []
    detailed = 'débat-dédié' if lang == 'fr' else 'dedicated-debate'
    name = 'nom-consacré' if lang == 'fr' else 'established-name'
    extra.append(detailed)
    extra.append(name)
    return (*legacy, *extra)

FR_EN_METADATA_VALUE_MAP = {
    'progress': {'Ébauche': 'Draft', 'Débat en construction': 'Debate under construction', 'Débat construit': 'Constructed debate'},
    'debate-warnings': {'Débat sensible': 'Sensitive debate', 'Débat saugrenu': 'Fanciful debate', 'Débat redondant': 'Redundant debate', 'Débat déséquilibré': 'Unbalanced debate', 'Plan à améliorer': 'Plan to improve', 'Débat généré par IA': 'Debate generated by AI'},
    'title-warnings:debate': {'Titre non standard': 'Non-standard title', 'Titre à simplifier': 'Title to simplify', 'Titre à expliciter': 'Title to be explained'},
    'title-warnings:argument': {'Titre désavantageux': 'Disadvantageous title', 'Titre peu clair': 'Unclear title', 'Titre incomplet': 'Incomplete title', 'Titre trop long': 'Too long title'},
    'argument-warnings': {'Argument sensible': 'Sensitive argument', 'Argument saugrenu': 'Fanciful argument', 'Argument potentiellement illégal': 'Potentially illegal argument', 'Argument généré par IA': 'Argument generated by AI'},
    'summary-warnings': {'Résumé à rédiger': 'Summary to be written', 'Résumé peu clair': 'Unclear summary', 'Résumé désavantageux': 'Biased summary'},
}
FR_EN_METADATA_PARAMETERS = {
    'debate': [('avancement','progress'), ('avertissements-titre','title-warnings'), ('avertissements-débat','debate-warnings')],
    # `initialisation` is a source-wiki page identifier and is deliberately not
    # projected to English. New translated Arguments must never carry
    # `initialization`; historical English pages remain governed by lifecycle
    # preservation independently of this translation mapping.
    'argument': [('avertissements-titre','title-warnings'), ('avertissements-argument','argument-warnings'), ('avertissements-résumé','summary-warnings'), ('avertissements-références','reference-warnings'), ('avertissements-justifications','justification-warnings'), ('avertissements-objections','objection-warnings'), ('débat-dédié','dedicated-debate')],
}

def _translated_english_source_template(ctx: PackageContext, page_manifest: dict[str, Any] | None) -> Template | None:
    if not isinstance(page_manifest, dict) or page_manifest.get('language') != 'en':
        return None
    manifest = ctx.manifest() or {}
    if str(((manifest.get('translation_status') or {}).get('en') or '')) not in {'ready', 'published'}:
        return None
    page_id, page_type = page_manifest.get('page_id'), page_manifest.get('page_type')
    source = next((p for p in manifest.get('pages', []) if p.get('language') == 'fr' and p.get('page_id') == page_id and p.get('page_type') == page_type), None)
    if not isinstance(source, dict) or not isinstance(source.get('file_path'), str):
        return None
    text = ctx.read_text(source['file_path'])
    if not isinstance(text, str):
        return None
    try:
        return parse_template(text)
    except WikiParseError:
        return None

def _mapped_warning_list(source_value: str, mapping: dict[str,str]) -> str | None:
    values=[part.strip() for part in source_value.split(',') if part.strip()]
    out=[]
    for value in values:
        target=mapping.get(value)
        if target is None:
            return None
        out.append(target)
    return ', '.join(out)

def _prepare_source_authoritative_translation(ctx: PackageContext, spec: dict[str, Any], tmpl: Template, page_type: str, rel: str, page_manifest: dict[str, Any]) -> bool:
    source = _translated_english_source_template(ctx, page_manifest)
    if source is None:
        return False
    source_params=dict(source.params)
    target_params=dict(tmpl.params)
    from .schema_validation import _valid_translation_source_preservation
    if _valid_translation_source_preservation(ctx):
        for fr_name, en_name in [('rubriques', 'sections'), ('mots-clés', 'keywords')]:
            if fr_name not in source_params and en_name in spec['required']:
                spec['required'].remove(en_name)
    # A target-language translation is a new remote page but not editorial creation from zero.
    # Creation defaults therefore do not apply; actual French metadata controls presence/value.
    for fixed_name in ('progress','debate-warnings','argument-warnings'):
        spec['fixed'].pop(fixed_name, None)
        if fixed_name in spec['required']:
            spec['required'].remove(fixed_name)
    metadata_pairs = list(FR_EN_METADATA_PARAMETERS[page_type])
    if page_type == 'argument' and not _current_template_parameter_contract(ctx):
        metadata_pairs = [(('débat-détaillé' if fr_name == 'débat-dédié' else fr_name), ('detailed-debate' if en_name == 'dedicated-debate' else en_name)) for fr_name, en_name in metadata_pairs]
    for fr_name,en_name in metadata_pairs:
        if en_name in spec['required']:
            spec['required'].remove(en_name)
        if en_name in spec['forbidden_generated']:
            spec['forbidden_generated'].remove(en_name)
        src = source_params.get(fr_name)
        actual = target_params.get(en_name)
        if src is None:
            if actual is not None:
                ctx.report.error('WDV-MWK-023', f'Le paramètre traduit {en_name} a été ajouté alors que {fr_name} est absent de la source française', path=rel, details={'page_id': page_manifest.get('page_id'), 'source_parameter': fr_name, 'target_parameter': en_name, 'actual': actual})
            continue
        if actual is None:
            ctx.report.error('WDV-MWK-023', f'Le paramètre traduit {en_name} manque alors que {fr_name} est présent dans la source française', path=rel, details={'page_id': page_manifest.get('page_id'), 'source_parameter': fr_name, 'target_parameter': en_name, 'source_value': src})
            continue
        expected = None
        if en_name == 'initialization':
            expected = src
        elif en_name == 'title-warnings':
            expected = _mapped_warning_list(src, FR_EN_METADATA_VALUE_MAP[f'title-warnings:{page_type}'])
        elif en_name in FR_EN_METADATA_VALUE_MAP:
            expected = _mapped_warning_list(src, FR_EN_METADATA_VALUE_MAP[en_name])
        elif en_name in {'reference-warnings','justification-warnings','objection-warnings'}:
            # No active corpus value currently uses these fields; require source/target presence and
            # leave any future unknown value to explicit translation review rather than inventing it.
            expected = actual
        elif en_name in {'dedicated-debate', 'detailed-debate'}:
            # The value is a translated canonical debate title and is independently covered by the
            # completed translation review; presence must exactly follow the French source.
            expected = actual
        if expected is None:
            ctx.report.error('WDV-MWK-023', f'Valeur française non reconnue pour la traduction de {fr_name}', path=rel, details={'page_id': page_manifest.get('page_id'), 'source_value': src})
        elif actual != expected:
            ctx.report.error('WDV-MWK-023', f'Valeur traduite incorrecte pour {en_name}', path=rel, details={'page_id': page_manifest.get('page_id'), 'source_value': src, 'expected': expected, 'actual': actual})
    # `creation-date` is intentionally independent from the French
    # `date-création` for a new translated page: the publisher replaces it with
    # the civil day of the first remote English creation. Shape/order checks
    # still require the parameter locally, while publication enforces the
    # runtime date and midnight boundary. Preexisting English pages are handled
    # by the lifecycle-preservation contract below.
    return True

def _argument_established_name_parameters(lang: str) -> tuple[str, str]:
    return (("nom-consacré", "nom") if lang == "fr" else ("established-name", "name"))


def _current_established_name_contract(ctx: PackageContext | None) -> bool:
    """Return whether this package uses the 1.2.58 canonical MediaWiki names.

    Norm versions are not editorial feature flags, but this distinction is a
    format-compatibility migration: packages authored before 1.2.58 may still
    contain the then-canonical `nom`/`name` field.
    """
    if ctx is None:
        return True
    manifest = ctx.manifest() or {}
    value = str(((manifest.get("normative_versions") or {}).get("consolidated_norm") or "")).strip()
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        return True
    return tuple(map(int, match.groups())) >= (1, 2, 58)


def _current_template_parameter_contract(ctx: PackageContext | None) -> bool:
    """Return whether the package uses the 1.2.69 MediaWiki parameter names.

    This is a format-compatibility distinction, not an editorial feature flag:
    older corpus packages may still contain the previously canonical parameter
    names and remain readable by the current validator.
    """
    if ctx is None:
        return True
    manifest = ctx.manifest() or {}
    value = str(((manifest.get("normative_versions") or {}).get("consolidated_norm") or "")).strip()
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        return True
    return tuple(map(int, match.groups())) >= (1, 2, 69)


def _renamed_parameter_names(lang: str, page_type: str) -> tuple[str, str] | None:
    if page_type == "debate":
        return (("sujet-développé", "sujet-complet") if lang == "fr" else ("expanded-topic", "complete-topic"))
    if page_type == "argument":
        return (("débat-dédié", "débat-détaillé") if lang == "fr" else ("dedicated-debate", "detailed-debate"))
    return None


def _renamed_parameter_for_contract(ctx: PackageContext | None, lang: str, page_type: str) -> str:
    pair = _renamed_parameter_names(lang, page_type)
    if pair is None:
        raise ValueError((lang, page_type))
    return pair[0] if _current_template_parameter_contract(ctx) else pair[1]


def _renamed_parameter_for_template(ctx: PackageContext | None, tmpl: Template | None, lang: str, page_type: str) -> str:
    pair = _renamed_parameter_names(lang, page_type)
    if pair is None:
        raise ValueError((lang, page_type))
    current, legacy = pair
    if tmpl is not None:
        if tmpl.one(current) is not None and tmpl.one(legacy) is None:
            return current
        if tmpl.one(legacy) is not None and tmpl.one(current) is None:
            return legacy
    return _renamed_parameter_for_contract(ctx, lang, page_type)


def _template_renamed_value(tmpl: Template | None, lang: str, page_type: str) -> str | None:
    if tmpl is None:
        return None
    pair = _renamed_parameter_names(lang, page_type)
    if pair is None:
        return None
    for name in pair:
        value = tmpl.one(name)
        if value is not None:
            return value
    return None


def _top_spec_for_context(ctx: PackageContext, lang: str, page_type: str) -> dict[str, Any]:
    base = ACTIVE_TOP[lang, page_type]
    if _current_template_parameter_contract(ctx):
        return base
    pair = _renamed_parameter_names(lang, page_type)
    if pair is None:
        return base
    current, legacy = pair
    replace = lambda name: legacy if name == current else name
    return {
        **base,
        "order": [replace(name) for name in base["order"]],
        "required": [replace(name) for name in base["required"]],
        "forbidden_generated": [replace(name) for name in base["forbidden_generated"]],
    }


def _argument_established_name_parameter(
    lang: str,
    tmpl: Template | None = None,
    page_manifest: dict[str, Any] | None = None,
    *,
    ctx: PackageContext | None = None,
) -> str:
    current, legacy = _argument_established_name_parameters(lang)
    preserved = page_manifest.get("preserved_parameters") if isinstance(page_manifest, dict) else None
    if isinstance(preserved, dict):
        current_state = preserved.get(current)
        legacy_state = preserved.get(legacy)
        if isinstance(current_state, dict) and current_state.get("present") is True:
            return current
        if isinstance(legacy_state, dict) and legacy_state.get("present") is True:
            return legacy
    if not _current_established_name_contract(ctx):
        # Exact compatibility for workspaces/packages created when nom/name was
        # still the canonical MediaWiki parameter.
        if tmpl is not None and tmpl.one(legacy) is not None:
            return legacy
        if tmpl is not None and tmpl.one(current) is not None:
            return current
        return legacy
    if isinstance(preserved, dict):
        if current in preserved and legacy not in preserved:
            return current
        if legacy in preserved and current not in preserved:
            return legacy
        # A 1.2.58 manifest may track both aliases as absent. New generation or
        # an explicit enrichment then uses only the canonical parameter.
        if current in preserved:
            return current
    if tmpl is not None and tmpl.one(current) is not None:
        return current
    return current


def _protected_page_parameters_for_manifest(ctx: PackageContext, lang: str, page_type: str, page_manifest: dict[str, Any] | None) -> tuple[str, ...]:
    protected = list(PROTECTED_PAGE_PARAMETERS[lang, page_type])
    if page_type != "argument" or not isinstance(page_manifest, dict):
        return tuple(protected)
    preserved = page_manifest.get("preserved_parameters")
    if not isinstance(preserved, dict):
        return tuple(protected)
    # Manifests sealed before top-level ``titre-affiché`` was inventoried do
    # not carry this key.  They remain readable; newly built checkpoints add
    # the explicit presence/value state before validation.
    if lang == "fr" and "titre-affiché" not in preserved and "titre-affiché" in protected:
        protected.remove("titre-affiché")
    current, legacy = _argument_established_name_parameters(lang)
    # Compatibility with pre-1.2.58 manifests that tracked only the legacy key,
    # and with a possible migrated manifest that tracks only the canonical key.
    if legacy in preserved and current not in preserved:
        protected.remove(current)
    elif current in preserved and legacy not in preserved:
        protected.remove(legacy)

    # Format compatibility for the 1.2.69 dedicated-debate rename. Historical
    # manifests may protect the former key; migrated/current manifests protect
    # the canonical key. The protected value itself is never transformed.
    dedicated_current, dedicated_legacy = _renamed_parameter_names(lang, "argument")
    if dedicated_legacy in preserved and dedicated_current not in preserved:
        if dedicated_current in protected:
            protected[protected.index(dedicated_current)] = dedicated_legacy
    elif dedicated_current in preserved and dedicated_legacy not in preserved:
        if dedicated_legacy in protected:
            protected[protected.index(dedicated_legacy)] = dedicated_current
    return tuple(protected)


def _apply_page_lifecycle_contract(ctx: PackageContext, spec: dict[str, Any], tmpl: Template, lang: str, page_type: str, rel: str, page_manifest: dict[str, Any] | None) -> None:
    if not isinstance(page_manifest, dict):
        ctx.report.error('WDV-MWK-023', 'Manifeste de page absent pour le contrôle création/modification', path=rel)
        return
    origin = page_manifest.get('page_origin')
    preserved = page_manifest.get('preserved_parameters')
    protected = _protected_page_parameters_for_manifest(ctx, lang, page_type, page_manifest)
    page_id = str(page_manifest.get('page_id') or '')
    name_parameter = _argument_established_name_parameter(lang, tmpl, page_manifest, ctx=ctx)
    name_assignment = _argument_name_assignment(ctx, page_id, lang) if page_type == 'argument' else None
    name_discovery = _argument_name_discovery(ctx, page_id, lang) if page_type == 'argument' else None
    if origin not in {'new', 'preexisting'} or not isinstance(preserved, dict):
        ctx.report.error('WDV-MWK-023', 'Origine ou paramètres préservés absents du manifeste de page', path=rel)
        return
    if origin == 'new':
        if preserved:
            ctx.report.error('WDV-MWK-023', 'Une page nouvelle ne doit pas déclarer de paramètres préservés', path=rel)
        translated_english = bool(lang == 'en' and _translated_english_source_template(ctx, page_manifest) is not None)
        if page_type == 'debate' and not translated_english:
            related = 'débats-connexes' if lang == 'fr' else 'related-debates'
            if related not in spec['forbidden_generated']:
                spec['forbidden_generated'].append(related)
        elif page_type == 'argument' and name_assignment is not None and tmpl.one(name_parameter) != name_assignment.get('name'):
            ctx.report.error('WDV-EDT-031', 'Le nom d’argument rendu diverge de l’attribution éditoriale approuvée', path=rel, details={'expected': name_assignment.get('name'), 'actual': tmpl.one(name_parameter)})
        elif isinstance(name_discovery, dict) and name_discovery.get('outcome') == 'known_name' and (tmpl.one(name_parameter) != name_discovery.get('name')):
            ctx.report.error('WDV-EDT-032', 'Le nom consacré rendu diverge de la revue documentaire', path=rel, details={'expected': name_discovery.get('name'), 'actual': tmpl.one(name_parameter)})
        elif isinstance(name_discovery, dict) and name_discovery.get('outcome') == 'none' and (tmpl.one(name_parameter) is not None):
            ctx.report.error('WDV-EDT-032', 'Un nom a été rendu malgré une recherche conclue sans appellation consacrée', path=rel, details={'actual': tmpl.one(name_parameter)})
        return
    for name in protected:
        if name in spec['required']:
            spec['required'].remove(name)
        spec['fixed'].pop(name, None)
        if name in spec['forbidden_generated']:
            spec['forbidden_generated'].remove(name)
    if set(preserved) != set(protected):
        ctx.report.error('WDV-MWK-023', 'L’état antérieur des paramètres protégés est incomplet', path=rel, details={'expected': list(protected), 'actual': sorted(preserved)})
        return
    for name in protected:
        state = preserved.get(name)
        if not isinstance(state, dict) or not isinstance(state.get('present'), bool):
            ctx.report.error('WDV-MWK-023', f'État antérieur invalide pour {name}', path=rel)
            continue
        actual = tmpl.one(name)
        if state['present']:
            expected = state.get('value')
            if not isinstance(expected, str) or not expected.strip() or actual != expected:
                ctx.report.error('WDV-MWK-023', f'Le paramètre existant {name} n’a pas été préservé exactement', path=rel, details={'expected': expected, 'actual': actual})
        elif actual is not None:
            if page_type == 'argument' and name == name_parameter and (name_assignment is not None) and (actual == name_assignment.get('name')):
                continue
            # A French interlanguage link is the one lifecycle field that may be
            # added after the English translation leaves deferred mode.  The
            # bilingual checks validate the exact locked target; this branch only
            # prevents the generic historical-preservation rule from rejecting
            # that explicitly authorised enrichment.
            if lang == 'fr' and name == 'interlangue':
                manifest = ctx.manifest() or {}
                status = str(((manifest.get('translation_status') or {}).get('en') or ''))
                en_page = next((row for row in (manifest.get('pages') or [])
                                if row.get('page_id') == page_id
                                and row.get('page_type') == page_type
                                and row.get('language') == 'en'
                                and isinstance(row.get('canonical_title'), str)
                                and row.get('canonical_title').strip()), None)
                if status in {'ready', 'published'} and en_page is not None:
                    continue
            ctx.report.error('WDV-MWK-023', f'Le paramètre {name} a été ajouté à une page existante alors qu’il était absent', path=rel, details={'actual': actual})
    if page_type == 'argument' and name_assignment is not None and (tmpl.one(name_parameter) != name_assignment.get('name')):
        ctx.report.error('WDV-EDT-031', 'Le nom d’argument rendu diverge de l’attribution éditoriale approuvée', path=rel, details={'expected': name_assignment.get('name'), 'actual': tmpl.one(name_parameter)})

def _preserved_schemeless_citation_link(
    ctx: PackageContext, sub: Template, lang: str, page_type: str,
    page_manifest: dict[str, Any] | None, value: str,
) -> bool:
    """Recognize only unchanged www links in a hash-verified French import.

    A new source still needs HTTP(S). Copying historical citation metadata,
    including into Quote, must not silently rewrite that metadata to make a
    creation-only URL rule pass.
    """
    if page_type != 'argument' or not isinstance(page_manifest, dict):
        return False
    if not re.fullmatch(r'www\.[A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z]{2,}(?:[/?#][^\s<>]*)?', value):
        return False
    if (lang, sub.name) not in {('fr', 'Citation'), ('en', 'Quote')}:
        return False
    if lang == 'fr' and page_manifest.get('page_origin') != 'preexisting':
        return False
    provenance = ctx.load_json('data/import_provenance.json') or {}
    if not isinstance(provenance, dict):
        return False
    page_id = page_manifest.get('page_id')
    rows = [r for r in provenance.get('pages') or [] if isinstance(r, dict)
            and r.get('kind') == 'argument' and r.get('page_id') == page_id]
    if len(rows) != 1:
        return False
    row = rows[0]
    import_path = row.get('import_path')
    if not isinstance(import_path, str) or not import_path.startswith('imports/fr/arguments/'):
        return False
    raw = ctx.read_bytes(import_path)
    if raw is None or hashlib.sha256(raw).hexdigest() != row.get('sha256'):
        return False
    try:
        original = parse_template(raw.decode('utf-8'))
        citations = get_subs(original, 'citations')
    except (UnicodeDecodeError, WikiParseError):
        return False
    if original.name != 'Argument':
        return False
    if lang == 'fr':
        return any(c.name == 'Citation' and c.params == sub.params for c in citations)
    # Only quote text, date and translation warnings may differ in English.
    actual = [(k, v) for k, v in sub.params if k not in {'quote', 'date', 'warnings'}]
    for citation in citations:
        if citation.name != 'Citation' or citation.one('lien') != value:
            continue
        source = [(_quote_parameter_name(k), v) for k, v in citation.params
                  if k not in {'citation', 'date', 'avertissements-citation'}]
        if source == actual:
            return True
    return False


def validate_template_shape(ctx: PackageContext, tmpl: Template, lang: str, page_type: str, rel: str, page_manifest: dict[str, Any] | None=None) -> None:
    base_spec = _top_spec_for_context(ctx, lang, page_type)
    if not _current_template_parameter_contract(ctx):
        pair = _renamed_parameter_names(lang, page_type)
        if pair is not None and tmpl.one(pair[0]) is not None and tmpl.one(pair[1]) is None:
            base_spec = ACTIVE_TOP[lang, page_type]
    spec = {**base_spec, 'order': list(base_spec['order']), 'required': list(base_spec['required']), 'forbidden_generated': list(base_spec['forbidden_generated'])}
    spec['fixed'] = dict(base_spec['fixed'])
    if page_type == 'argument':
        citation_parameter = 'citations' if lang == 'fr' else 'quotes'
        if citation_parameter in spec['forbidden_generated']:
            spec['forbidden_generated'].remove(citation_parameter)
    preservation = ((ctx.manifest() or {}).get('editorial_controls') or {}).get('legacy_content_preservation') or {}
    protected_fields = set(preservation.get('protected_fields') or [])
    if preservation.get('enabled') is True and page_type == 'argument':
        init_parameter = 'initialisation' if lang == 'fr' else 'initialization'
        if init_parameter in protected_fields and init_parameter in spec['forbidden_generated']:
            spec['forbidden_generated'].remove(init_parameter)
        detailed_parameter = _renamed_parameter_for_template(ctx, tmpl, lang, 'argument')
        if detailed_parameter in protected_fields and detailed_parameter in spec['forbidden_generated']:
            spec['forbidden_generated'].remove(detailed_parameter)
        name_parameter = _argument_established_name_parameter(lang, tmpl, page_manifest, ctx=ctx)
        if name_parameter in protected_fields and name_parameter in spec['forbidden_generated']:
            spec['forbidden_generated'].remove(name_parameter)
    if page_type == 'argument' and page_manifest is not None:
        current_name_parameter, legacy_name_parameter = _argument_established_name_parameters(lang)
        current_name_contract = _current_established_name_contract(ctx)
        keys_now = {k for k, _ in tmpl.params}
        if current_name_parameter in keys_now and legacy_name_parameter in keys_now:
            ctx.report.error('WDV-MWK-003', f'Les paramètres {current_name_parameter} et {legacy_name_parameter} ne peuvent pas coexister', path=rel)
        if current_name_contract and page_manifest.get('page_origin') == 'new' and legacy_name_parameter in keys_now:
            ctx.report.error('WDV-MWK-003', f'Le paramètre historique {legacy_name_parameter} est interdit sur une nouvelle page Argument; utiliser {current_name_parameter}', path=rel)
        preserved_now = page_manifest.get('preserved_parameters') or {}
        if page_manifest.get('page_origin') == 'preexisting' and isinstance(preserved_now, dict):
            for candidate in (current_name_parameter, legacy_name_parameter):
                state = preserved_now.get(candidate)
                if isinstance(state, dict) and state.get('present') is True and candidate in spec['forbidden_generated']:
                    spec['forbidden_generated'].remove(candidate)
    if page_type == 'argument' and page_manifest is not None:
        assigned = _argument_name_assignment(ctx, str(page_manifest.get('page_id') or ''), lang)
        assigned_parameter = _argument_established_name_parameter(lang, tmpl, page_manifest, ctx=ctx)
        if assigned is not None and assigned_parameter in spec['forbidden_generated']:
            spec['forbidden_generated'].remove(assigned_parameter)
        discovery = _argument_name_discovery(ctx, str(page_manifest.get('page_id') or ''), lang)
        if isinstance(discovery, dict) and discovery.get('outcome') == 'known_name' and (assigned_parameter in spec['forbidden_generated']):
            spec['forbidden_generated'].remove(assigned_parameter)
    translated_english = bool(lang == 'en' and isinstance(page_manifest, dict) and _translated_english_source_template(ctx, page_manifest) is not None)
    if translated_english:
        _prepare_source_authoritative_translation(ctx, spec, tmpl, page_type, rel, page_manifest)
    if page_type == 'argument' and page_manifest is not None:
        summary_parameter = 'résumé' if lang == 'fr' else 'summary'
        page_key = (page_manifest.get('page_id'), lang)
        if page_key in _historically_absent_summary_keys(ctx) | _owner_removed_summary_keys(ctx) and summary_parameter in spec['required']:
            spec['required'].remove(summary_parameter)
    if (
        page_type == 'debate'
        and isinstance(page_manifest, dict)
        and page_manifest.get('page_origin') == 'preexisting'
        and _historically_absent_introduction(ctx, lang)
        and 'introduction' in spec['required']
    ):
        spec['required'].remove('introduction')
    _apply_page_lifecycle_contract(ctx, spec, tmpl, lang, page_type, rel, page_manifest)
    if tmpl.name != spec['model']:
        ctx.report.error('WDV-MWK-002', f"Modèle principal attendu {spec['model']}, trouvé {tmpl.name}", path=rel)
    keys = [k for k, _ in tmpl.params]
    for dup, n in Counter(keys).items():
        if n > 1:
            ctx.report.error('WDV-MWK-003', f'Paramètre dupliqué : {dup}', path=rel)
    allowed = spec['order']
    for key in keys:
        if key not in allowed:
            ctx.report.error('WDV-MWK-003', f'Paramètre inconnu : {key}', path=rel)
    for key in spec['forbidden_generated']:
        if key in keys:
            ctx.report.error('WDV-MWK-003', f'Paramètre autorisé par la structure mais interdit dans une sortie générée : {key}', path=rel)
    for key in spec['required']:
        if key not in keys:
            ctx.report.error('WDV-MWK-004', f'Paramètre obligatoire absent : {key}', path=rel)
    for key, value in tmpl.params:
        if not value.strip():
            ctx.report.error('WDV-MWK-005', f'Paramètre vide interdit : {key}', path=rel)
    positions = [allowed.index(k) for k in keys if k in allowed]
    if positions != sorted(positions):
        ctx.report.error('WDV-MWK-006', 'Ordre relatif des paramètres incorrect', path=rel, details={'parameters': keys})
    for key, expected in spec['fixed'].items():
        actual = tmpl.one(key)
        if actual is not None and actual != expected:
            ctx.report.error('WDV-MWK-007', f'Valeur fixe incorrecte pour {key}', path=rel, details={'expected': expected, 'actual': actual})
    section_param = 'rubriques' if lang == 'fr' else 'sections'
    values = split_list(tmpl.one(section_param) or '')
    expected_values = alphabetically_sorted(values)
    if values and values != expected_values:
        ctx.report.error('WDV-MWK-016', f'{section_param} doit être rangé par ordre alphabétique', path=rel, details={'actual': values, 'expected': expected_values})
    if page_type == 'debate':
        topic_param = 'sujet' if lang == 'fr' else 'topic'
        topic = tmpl.one(topic_param) or ''
        if not _first_alpha_is_upper(topic):
            ctx.report.error('WDV-MWK-017', f'{topic_param} doit commencer par une majuscule', path=rel, details={'actual': topic})
        complete_param = _renamed_parameter_for_template(ctx, tmpl, lang, 'debate')
        complete = tmpl.one(complete_param) or ''
        if _complete_topic_looks_interrogative(complete, lang):
            ctx.report.error('WDV-EDT-018', f'{complete_param} doit compléter l’en-tête de la page sous une forme non interrogative', path=rel, details={'actual': complete})
        if not _first_alpha_is_lower(complete):
            ctx.report.error('WDV-EDT-018', f'{complete_param} doit normalement commencer par une minuscule dans les deux langues', path=rel, details={'actual': complete, 'exception_policy': 'reformuler avec un déterminant ou justifier un nom propre/acronyme inévitable dans la revue'})
        declared_acronym = explicit_parenthetical_acronym(topic)
        if declared_acronym and (not re.search(f'(?<![\\w.-]){re.escape(declared_acronym)}(?![\\w.-])', complete)):
            ctx.report.error('WDV-EDT-018', f'{complete_param} doit employer l’acronyme courant déclaré dans {topic_param}', path=rel, details={'acronym': declared_acronym, 'actual': complete})
    matches = split_adjacent_templates(tmpl.raw)
    if matches:
        first = matches[0]
        line = tmpl.raw.count('\n', 0, first.start()) + 1
        ctx.report.error('WDV-MWK-018', 'Deux modèles MediaWiki adjacents doivent être accolés sous la forme }}{{', path=rel, details={'occurrences': len(matches), 'first_line': line, 'replacement': '}}{{'})
    if re.search('<references\\b[^>]*(?:/\\s*)?>', tmpl.raw, flags=re.IGNORECASE):
        preserved_historical_intro = bool(
            lang == 'fr' and page_type == 'debate' and _preserved_historical_french_introduction(ctx)
        )
        intro_value = (tmpl.one('introduction') or '') if page_type == 'debate' else ''
        references_in_intro = bool(re.search('<references\\b[^>]*(?:/\\s*)?>', intro_value, flags=re.IGNORECASE))
        raw_without_intro = tmpl.raw.replace(intro_value, '', 1) if intro_value else tmpl.raw
        references_elsewhere = bool(re.search('<references\\b[^>]*(?:/\\s*)?>', raw_without_intro, flags=re.IGNORECASE))
        if not (preserved_historical_intro and references_in_intro and not references_elsewhere):
            ctx.report.error('WDV-EDT-010', 'La balise <references /> est interdite par la norme éditoriale courante', path=rel)
        else:
            ctx.report.info('WDV-EDT-010', 'Balise <references /> historique conservée dans une introduction française préexistante protégée', path=rel)
    for key, value in tmpl.params:
        if key not in SEQUENCE_PARAMS:
            continue
        try:
            subs = _mixed_citations(value)[0] if key in {'citations', 'quotes'} else parse_template_sequence(value)
        except WikiParseError as exc:
            ctx.report.error('WDV-MWK-001', f'Sous-modèles invalides dans {key} : {exc}', path=rel)
            continue
        for sub in subs:
            if sub.name not in SUB:
                ctx.report.error('WDV-MWK-012', f'Sous-modèle inconnu : {sub.name}', path=rel)
                continue
            expected_models = PARAM_TEMPLATE_ALLOWED.get(key)
            if expected_models and sub.name not in expected_models:
                ctx.report.error('WDV-MWK-012', f'Sous-modèle {sub.name} interdit dans le paramètre {key}', path=rel, details={'expected': sorted(expected_models)})
            if key == 'introduction':
                localized_model = 'Sous-partie' if lang == 'fr' else 'Subsection'
                if sub.name != localized_model:
                    ctx.report.error('WDV-MWK-022', f'Le modèle {sub.name} ne correspond pas à la langue de la page', path=rel, details={'expected': localized_model})
            if sub.name in {'Justification', 'Objection'}:
                wrong_names = {'displayed-title', 'warnings'} if lang == 'fr' else {'titre-affiché', 'avertissements'}
                found_wrong = sorted({name for name, _value in sub.params} & wrong_names)
                if found_wrong:
                    ctx.report.error('WDV-MWK-022', f'Paramètres de l’autre langue interdits dans {sub.name}', path=rel, details={'forbidden': found_wrong})
            order, required = SUB[sub.name]
            subkeys = [k for k, _ in sub.params]
            if len(subkeys) != len(set(subkeys)):
                ctx.report.error('WDV-MWK-012', f'Paramètre dupliqué dans {sub.name}', path=rel)
            dynamic_citation = sub.name in {'Citation', 'Quote'}
            if not dynamic_citation:
                for skey in subkeys:
                    if skey not in order:
                        ctx.report.error('WDV-MWK-012', f'Paramètre inconnu {skey} dans {sub.name}', path=rel)
                indexes = [order.index(x) for x in subkeys if x in order]
                if indexes != sorted(indexes):
                    ctx.report.error('WDV-MWK-006', f'Ordre incorrect dans {sub.name}', path=rel)
            for req in [] if dynamic_citation else required:
                if req not in subkeys or not (sub.one(req) or '').strip():
                    source = _translated_english_source_template(ctx, page_manifest) if lang == 'en' and page_type == 'debate' else None
                    source_sections = get_subs(source, 'introduction') if source else []
                    if sub.name == 'Subsection' and req == 'title' and subs.index(sub) < len(source_sections) and not source_sections[subs.index(sub)].one('titre'):
                        continue
                    ctx.report.error('WDV-MWK-012', f'Paramètre obligatoire {req} absent ou vide dans {sub.name}', path=rel)
            for skey, sval in sub.params:
                if not sval.strip():
                    ctx.report.error('WDV-MWK-005', f'Sous-paramètre vide interdit : {sub.name}.{skey}', path=rel)
                if skey in {'avertissements', 'warnings'}:
                    allowed_quote_warning = sub.name == 'Quote' and skey == 'warnings'
                    preserved_historical_subsection_warning = bool(
                        key == 'introduction' and page_type == 'debate'
                        and (
                            (
                                lang == 'fr' and sub.name == 'Sous-partie' and skey == 'avertissements'
                                and _preserved_historical_french_introduction(ctx)
                            )
                            or
                            (
                                lang == 'en' and sub.name == 'Subsection' and skey == 'warnings'
                                and _translated_historical_english_introduction(ctx)
                            )
                        )
                    )
                    if not allowed_quote_warning and not preserved_historical_subsection_warning:
                        ctx.report.error('WDV-MWK-003', f"Sous-paramètre d'avertissement interdit dans une sortie générée : {sub.name}.{skey}", path=rel)
                    elif preserved_historical_subsection_warning:
                        ctx.report.info('WDV-MWK-003', f"Sous-paramètre d'avertissement historique conservé depuis une source préexistante : {sub.name}.{skey}", path=rel)
                if skey in {'auteurs', 'authors'}:
                    candidate = sval.strip()
                    parsed_json = None
                    if candidate.startswith('['):
                        try:
                            parsed_json = json.loads(candidate)
                        except json.JSONDecodeError:
                            parsed_json = None
                    if isinstance(parsed_json, list) or (candidate.startswith('[') and candidate.endswith(']')):
                        ctx.report.error('WDV-DOC-006', 'Le champ auteur MediaWiki ne doit pas contenir une sérialisation de tableau JSON', path=rel, details={'template': sub.name, 'parameter': skey, 'actual': sval, 'conversion': "un élément -> texte brut ; plusieurs éléments -> valeurs séparées par ', ' ; liste vide -> paramètre omis"})
                    malformed_separator = ';' in candidate or '，' in candidate or bool(re.search('\\s+,|,(?! )|, {2,}|,$', candidate))
                    if malformed_separator:
                        ctx.report.error('WDV-DOC-007', 'Plusieurs auteurs doivent être séparés exactement par une virgule suivie d’une espace', path=rel, details={'template': sub.name, 'parameter': skey, 'actual': sval, 'expected_separator': ', '})
                if skey in {'numéro', 'issue'} and (not sval.isdigit()):
                    ctx.report.error('WDV-MWK-012', f'{sub.name}.{skey} doit contenir uniquement des chiffres', path=rel)
                if skey in {'lien', 'link'} and (not re.match('^https?://', sval)):
                    if _preserved_schemeless_citation_link(ctx, sub, lang, page_type, page_manifest, sval):
                        ctx.report.info('WDV-MWK-012', f'Lien historique sans schéma conservé exactement dans {sub.name}.{skey}', path=rel)
                    else:
                        ctx.report.error('WDV-MWK-012', f'URL HTTP/HTTPS attendue dans {sub.name}.{skey}', path=rel)
                if skey == 'page' and ('bibliographique' in sub.name.lower() or 'bibliographical' in sub.name.lower()):
                    if not re.fullmatch('[0-9]+(?:-[0-9]+)?', sval):
                        ctx.report.error('WDV-DOC-002', f'Pagination bibliographique non normalisée dans {sub.name}.page', path=rel, details={'value': sval})
                if skey in {'localisation', 'location'} and re.search('^(?:pages?|pp?\\.)\\s*[0-9]', sval, flags=re.I):
                    ctx.report.error('WDV-DOC-002', f'Pagination bibliographique placée dans {sub.name}.{skey} au lieu de page', path=rel, details={'value': sval})
                if skey == 'date' and re.search('\\b(?:consulté(?:e)?|accessed|retrieved)\\b', sval, flags=re.I):
                    ctx.report.error('WDV-DOC-003', f'Date de consultation utilisée comme date documentaire dans {sub.name}', path=rel, details={'value': sval})
                if skey == 'date' and documentary_date_is_machine(sval):
                    ctx.report.error('WDV-DOC-005', f'Date documentaire au format machine dans {sub.name}; utiliser une date en langage naturel', path=rel, details={'value': sval, 'creation_date_parameters_unchanged': ['date-création', 'creation-date']})
            if sub.name in {'Référence sitographique', 'Référence sitographique pour', 'Référence sitographique contre', 'Web reference', 'Pro web reference', 'Con web reference'}:
                page_value = (sub.one('page') or '').strip().casefold()
                site_value = (sub.one('site') or '').strip().casefold()
                author_value = (sub.one('auteurs') or sub.one('authors') or '').strip().casefold()
                if page_value and site_value and (page_value == site_value):
                    ctx.report.error('WDV-DOC-004', 'Le titre de page sitographique duplique le nom du site et doit être omis', path=rel, details={'template': sub.name, 'value': sub.one('page'), 'page_type': page_type})
                if author_value and site_value and (author_value == site_value):
                    ctx.report.error('WDV-DOC-004', 'Le champ auteur reproduit le nom du site : rechercher de nouveau la signature ou les crédits, puis omettre l’auteur si aucune responsabilité distincte n’est trouvée', path=rel, details={'template': sub.name, 'value': sub.one('site'), 'page_type': page_type, 'applies_to_argument_pages': True})
                if author_value and page_value and site_value and (author_value == page_value == site_value):
                    ctx.report.error('WDV-DOC-004', 'Les champs auteur, page et site sont remplis mécaniquement avec la même valeur', path=rel, details={'template': sub.name, 'value': sub.one('site'), 'page_type': page_type})
            if sub.name in {'Justification', 'Objection'}:
                expected_display = 'titre-affiché' if lang == 'fr' else 'displayed-title'
                wrong_display = 'displayed-title' if lang == 'fr' else 'titre-affiché'
                if not sub.one(expected_display):
                    ctx.report.error('WDV-MWK-012', f'{sub.name} doit contenir {expected_display}', path=rel)
                if sub.one(wrong_display) is not None:
                    ctx.report.error('WDV-MWK-012', f'{sub.name} mélange les paramètres français et anglais', path=rel)
            if sub.name.startswith('Référence bibliographique') and (not (sub.one('article') or sub.one('ouvrage'))):
                ctx.report.error('WDV-MWK-012', f'{sub.name} doit contenir article ou ouvrage', path=rel)
            if sub.name.endswith('bibliographical reference') or sub.name == 'Bibliographical reference':
                if not (sub.one('article') or sub.one('work')):
                    ctx.report.error('WDV-MWK-012', f'{sub.name} doit contenir article ou work', path=rel)

def get_subs(tmpl: Template, param: str) -> list[Template]:
    value = tmpl.one(param)
    if not value:
        return []
    try:
        return parse_template_sequence(value)
    except WikiParseError:
        if param in {'citations', 'quotes'}:
            try: return _mixed_citations(value)[0]
            except WikiParseError: pass
        return []

def expected_relations(registry: dict[str, Any], node_id: str, lang: str, relation: str, contextual_labels: list[dict[str, Any]] | None = None) -> list[tuple[str, str]]:
    nodes = {n.get('id'): n for n in registry.get('graph', {}).get('nodes', []) if n.get('status') == 'active'}
    edges = [e for e in registry.get('graph', {}).get('edges', []) if e.get('status') == 'active' and e.get('parent_node_id') == node_id and (e.get('relation') == relation)]
    edges.sort(key=lambda e: (e.get('order', 0), e.get('id', '')))
    out = []
    for e in edges:
        child = nodes.get(e.get('child_node_id'))
        if child:
            data = child.get(lang) or {}
            contextual_key = 'source_text' if lang == 'fr' else 'translated_text'
            label = next((r.get(contextual_key) for r in contextual_labels or [] if r.get('id') == 'edge:' + str(e.get('id')) and r.get('target_node_id') == child.get('id') and r.get(contextual_key)), data.get('displayed_title'))
            out.append((data.get('canonical_title'), label))
    return out

def _contextual_relation_labels(ctx: PackageContext, page_id: str, lang: str, page_type: str) -> list[dict[str, Any]]:
    """Return occurrence labels locked by the translation review.

    Legacy French content locks do not contain occurrence-level labels.  Once a
    translation review exists, its English content lock is also the authoritative
    record of the French source labels, under ``source_text``.  This fallback keeps
    the French render differential exact without changing the historical lock.
    """
    paths = ['data/en_content_lock.json'] if lang == 'en' else ['data/fr_content_lock.json', 'data/en_content_lock.json']
    for path in paths:
        if not ctx.exists(path):
            continue
        lock = ctx.load_json(path)
        if not isinstance(lock, dict):
            continue
        if page_type == 'debate':
            row = lock.get('debate') or {}
        else:
            row = next((entry for entry in lock.get('arguments') or [] if str(entry.get('id')) == page_id), {})
        labels = row.get('relation_labels') if isinstance(row, dict) else None
        if isinstance(labels, list) and labels:
            return labels
    return []


def _historically_absent_introduction(ctx: PackageContext, lang: str) -> bool:
    """Return whether the source debate explicitly lacked an introduction."""
    paths = ['data/fr_content_lock.json'] if lang == 'fr' else ['data/en_content_lock.json']
    for path in paths:
        if not ctx.exists(path):
            continue
        lock = ctx.load_json(path)
        debate = (lock.get('debate') or {}) if isinstance(lock, dict) else {}
        if debate.get('historical_introduction_present') is False:
            return True
        presence = (debate.get('source_parameter_presence') or {}).get(
            'introduction'
        )
        if isinstance(presence, dict) and presence.get('present') is False:
            return True
    return False

def relation_pairs(subs: list[Template], lang: str) -> list[tuple[str | None, str | None]]:
    display = 'titre-affiché' if lang == 'fr' else 'displayed-title'
    return [(s.one('page'), s.one(display)) for s in subs]
QUOTE_PARAMETER_MAP = {'citation': 'quote', 'auteurs': 'authors', 'article': 'article', 'ouvrage': 'work', 'volume': 'volume', 'numéro': 'issue', 'numero': 'issue', 'page': 'page', 'localisation': 'location', 'édition': 'publisher', 'edition': 'publisher', 'lieu': 'place', 'date': 'date', 'lien': 'link', 'avertissements citation': 'warnings', 'avertissements': 'warnings'}

def _quote_parameter_name(name: str) -> str | None:
    normalized = re.sub('[ _-]+', ' ', str(name).strip().casefold())
    return QUOTE_PARAMETER_MAP.get(normalized)

def _plain_for_lexical_count(value: str) -> str:
    value = re.sub(r"<ref\b[^>]*>.*?</ref>|<ref\b[^>]*/>", " ", value or "", flags=re.I | re.S)
    value = re.sub(r"\{\{[^{}]*\}\}|\[\[[^\]]+\]\]", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def _lexical_word_count(value: str) -> int:
    # Must remain byte-for-byte equivalent in semantics to the tokenizer used by
    # wikidebia_translation_review when lexical_ratio is sealed.  In particular,
    # French typographic apostrophes belong inside lexical tokens.
    return len(re.findall(r"[A-Za-zÀ-ÿ0-9]+(?:['’\-][A-Za-zÀ-ÿ0-9]+)*", _plain_for_lexical_count(value or "")))

def _parameter_pairs(rows: Any) -> list[tuple[str, str]]:
    if not isinstance(rows, list):
        return []
    out: list[tuple[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            return []
        name = str(row.get('name') or '').strip()
        value = str(row.get('value') or '').strip()
        if not name:
            return []
        # Les verrous conservent fidèlement la provenance, y compris les
        # sous-paramètres facultatifs historiquement présents mais vides. Le
        # wikicode canonique les omet conformément au profil de rendu.
        if not value:
            continue
        out.append((name, value))
    return out

def _validate_citations_against_locks(ctx: PackageContext, tmpl: Template, rel: str, lang: str, page_id: str) -> None:
    lock_path = 'data/fr_content_lock.json' if lang == 'fr' else 'data/en_content_lock.json'
    lock = ctx.load_json(lock_path, required=True)
    if not isinstance(lock, dict):
        return
    argument = next((row for row in lock.get('arguments', []) if isinstance(row, dict) and row.get('id') == page_id), None)
    if argument is None:
        ctx.report.error('WDV-MWK-021', 'Le verrou de contenu ne couvre pas cette page Argument', path=rel, details={'page_id': page_id, 'lock': lock_path})
        return
    expected_rows = argument.get('citations') or []
    parameter = 'citations' if lang == 'fr' else 'quotes'
    actual_templates = get_subs(tmpl, parameter)
    try:
        _, actual_passages = _mixed_citations(tmpl.one(parameter) or '')
        ids = [r.get('id') for r in expected_rows]
        expected_passages = [(ids.index(p['before_citation_id']) if p.get('before_citation_id') in ids else len(ids), str(p.get('text') or '').strip()) for p in argument.get('citation_passages') or []]
        if actual_passages != expected_passages:
            ctx.report.error('WDV-MWK-021', 'Passages hors citation absents, modifiés ou déplacés', path=rel)
    except WikiParseError as exc:
        ctx.report.error('WDV-MWK-021', str(exc), path=rel)
    if len(actual_templates) != len(expected_rows):
        ctx.report.error('WDV-MWK-021', 'Nombre de citations divergent du verrou éditorial', path=rel, details={'expected': len(expected_rows), 'actual': len(actual_templates), 'parameter': parameter})
        return
    for index, (actual, expected) in enumerate(zip(actual_templates, expected_rows), start=1):
        expected_model = 'Citation' if lang == 'fr' else 'Quote'
        if actual.name != expected_model:
            ctx.report.error('WDV-MWK-021', f'Le modèle {expected_model} est obligatoire dans {parameter}', path=rel, pointer=f'{parameter}/{index}')
            continue
        expected_params = _parameter_pairs(expected.get('source_parameters') if lang == 'fr' else expected.get('parameters'))
        actual_params = [(str(name).strip(), str(value).strip()) for name, value in actual.params]
        if actual_params != expected_params:
            ctx.report.error('WDV-MWK-021', 'Les paramètres de la citation divergent du verrou bilingue ; les noms doivent être anglais et seules les valeurs de quote et date peuvent être traduites', path=rel, pointer=f'{parameter}/{index}', details={'expected': expected_params, 'actual': actual_params, 'citation_id': expected.get('id')})
        if lang == 'en':
            current_contract = True
            warning_name = 'warnings' if current_contract else 'avertissements-citation'
            warning_values = [value for name, value in actual_params if name == warning_name]
            expected_warning = str(expected.get(warning_name) or '').strip()
            if warning_values != [expected_warning] or expected_warning.count('AI-translated quote') != 1:
                ctx.report.error('WDV-MWK-021', "La citation anglaise doit contenir une unique mention 'AI-translated quote', ajoutée avec le séparateur ', ' après tout avertissement existant", path=rel, pointer=f'{parameter}/{index}', details={'expected': expected_warning, 'actual': warning_values, 'parameter': warning_name})
            source = expected.get('source') or {}
            source_params = _parameter_pairs(source.get('source_parameters'))
            if current_contract:
                mapped_source: list[tuple[str, str]] = []
                unmapped: list[str] = []
                for source_name, source_value in source_params:
                    mapped_name = _quote_parameter_name(source_name)
                    if mapped_name is None:
                        unmapped.append(source_name)
                        continue
                    if mapped_name not in {'quote', 'date', 'warnings'}:
                        mapped_source.append((mapped_name, source_value))
                if unmapped:
                    ctx.report.error('WDV-MWK-021', 'Un paramètre français de Citation ne possède pas d’équivalent anglais déclaré', path=rel, pointer=f'{parameter}/{index}', details={'unmapped': unmapped})
                preserved_actual = [(name, value) for name, value in actual_params if name not in {'quote', 'date', 'warnings'}]
                if preserved_actual != mapped_source:
                    ctx.report.error('WDV-MWK-021', 'La valeur d’un paramètre documentaire de Quote a été modifiée ou son nom n’a pas été traduit en anglais', path=rel, pointer=f'{parameter}/{index}', details={'expected_preserved': mapped_source, 'actual_preserved': preserved_actual})
                # Completeness is a human attestation.  The lexical ratio is only a trigger
                # for a second explicit review; it never proves truncation on its own.
                completeness_reviewed = expected.get('quote_completeness_reviewed') is True
                completeness_note = str(expected.get('quote_completeness_note') or '').strip()
                if not completeness_reviewed or len(completeness_note) < 12:
                    ctx.report.error('WDV-MWK-024', 'La traduction complète de la valeur Citation→Quote n’est pas attestée par une revue humaine explicite', path=rel, pointer=f'{parameter}/{index}', details={'citation_id': expected.get('id')})
                source_quote = next((value for name, value in source_params if name == 'citation'), '')
                actual_quote = next((value for name, value in actual_params if name == 'quote'), '')
                fr_word_count = _lexical_word_count(source_quote or '')
                en_word_count = _lexical_word_count(actual_quote or '')
                ratio = (en_word_count / fr_word_count) if fr_word_count else None
                if ratio is not None:
                    stored_ratio = expected.get('lexical_ratio')
                    if isinstance(stored_ratio, (int, float)) and abs(float(stored_ratio) - ratio) > 0.02:
                        ctx.report.error('WDV-MWK-024', 'Le ratio lexical enregistré pour la Quote ne correspond plus au texte rendu', path=rel, pointer=f'{parameter}/{index}', details={'citation_id': expected.get('id'), 'stored_ratio': stored_ratio, 'actual_ratio': round(ratio, 3)})
                    if fr_word_count >= 8 and ratio < 0.60:
                        low_reviewed = expected.get('quote_low_ratio_reviewed') is True
                        low_note = str(expected.get('quote_low_ratio_note') or '').strip()
                        if not low_reviewed or len(low_note) < 12:
                            ctx.report.error('WDV-MWK-024', 'Ratio lexical faible : la seconde revue explicite de complétude de la Quote est absente', path=rel, pointer=f'{parameter}/{index}', details={'citation_id': expected.get('id'), 'fr_words': fr_word_count, 'en_words': en_word_count, 'ratio': round(ratio, 3)})
                        else:
                            ctx.report.info('WDV-MWK-024', 'Ratio lexical faible mais seconde revue humaine de complétude attestée', path=rel, pointer=f'{parameter}/{index}', details={'citation_id': expected.get('id'), 'fr_words': fr_word_count, 'en_words': en_word_count, 'ratio': round(ratio, 3)})
            else:
                preserved_source = [(name, value) for name, value in source_params if name not in {'citation', 'date', 'avertissements-citation'}]
                preserved_actual = [(name, value) for name, value in actual_params if name not in {'citation', 'date', 'avertissements-citation'}]
                if preserved_actual != preserved_source:
                    ctx.report.error('WDV-MWK-021', 'Un paramètre documentaire de la citation a été traduit ou modifié', path=rel, pointer=f'{parameter}/{index}', details={'expected_preserved': preserved_source, 'actual_preserved': preserved_actual})

def _argument_name_assignment(ctx: PackageContext, page_id: str, lang: str) -> dict[str, Any] | None:
    manifest = ctx.manifest() or {}
    controls = manifest.get('editorial_controls') or {}
    rel = controls.get('argument_name_assignment_path')
    if not rel:
        return None
    data = ctx.load_json(str(rel))
    if not isinstance(data, dict):
        return None
    row = next((entry for entry in data.get('entries') or [] if entry.get('language') == lang and str(entry.get('page_id')) == page_id), None)
    return row if isinstance(row, dict) else None

def _argument_name_discovery(ctx: PackageContext, page_id: str, lang: str) -> dict[str, Any] | None:
    manifest = ctx.manifest() or {}
    controls = manifest.get('editorial_controls') or {}
    rel = controls.get('argument_name_discovery_path')
    if not rel:
        return None
    data = ctx.load_json(str(rel))
    if not isinstance(data, dict):
        return None
    row = next((entry for entry in data.get('entries') or [] if entry.get('language') == lang and str(entry.get('page_id')) == page_id), None)
    return row if isinstance(row, dict) else None

def _manual_external_relations(ctx: PackageContext, page_id: str, lang: str, relation: str) -> list[tuple[str, str]]:
    manifest = ctx.manifest() or {}
    controls = manifest.get('editorial_controls') or {}
    result: list[tuple[str, str]] = []
    rel = controls.get('manual_remote_adoption_path')
    if rel:
        data = ctx.load_json(str(rel))
        if isinstance(data, dict):
            row = next((entry for entry in data.get('entries') or [] if entry.get('language') == lang and str(entry.get('page_id')) == page_id), None)
            if isinstance(row, dict):
                for external in row.get('external_relations') or []:
                    if external.get('relation') == relation:
                        result.append((external.get('page'), external.get('displayed_title')))
    # A translated external relation is not an English remote adoption.  It is a
    # source-authoritative translation of a French relation that was explicitly preserved.
    if lang == 'en' and ctx.exists('data/translated_external_relations.json'):
        translated = ctx.load_json('data/translated_external_relations.json')
        if isinstance(translated, dict):
            for external in translated.get('entries') or []:
                if str(external.get('page_id')) == page_id and external.get('relation') == relation and external.get('verified_in_rendered_page') is True:
                    result.append((external.get('page'), external.get('displayed_title')))
    return result

def _validate_argument_content(ctx: PackageContext, tmpl: Template, rel: str, lang: str, page_id: str, registry: dict[str, Any], page_manifest: dict[str, Any]) -> None:
    node = next((n for n in registry.get('graph', {}).get('nodes', []) if n.get('id') == page_id), None)
    if not node:
        ctx.report.error('WDV-GRA-003', f'Fichier de page pour un nœud inexistant : {page_id}', path=rel)
        return
    just_param = 'justifications'
    obj_param = 'objections'
    actual_just = relation_pairs(get_subs(tmpl, just_param), lang)
    actual_obj = relation_pairs(get_subs(tmpl, obj_param), lang)
    contextual = _contextual_relation_labels(ctx, page_id, lang, 'argument')
    expected_just = expected_relations(registry, page_id, lang, 'justification', contextual)
    expected_obj = expected_relations(registry, page_id, lang, 'objection', contextual)
    expected_just.extend(_manual_external_relations(ctx, page_id, lang, 'justification'))
    expected_obj.extend(_manual_external_relations(ctx, page_id, lang, 'objection'))
    depth_policy = registry.get('graph', {}).get('depth_policy') or {}
    depth_frontier = bool(
        lang == 'fr'
        and depth_policy.get('limit_policy') == 'bounded'
        and page_id in (depth_policy.get('frontier_node_ids') or [])
    )
    detailed_state = _historical_detailed_debate_states(ctx).get((page_id, lang)) or {}
    relations_omitted = detailed_state.get('present') is True and detailed_state.get('relations_omitted') is True and (not actual_just) and (not actual_obj)
    if depth_frontier:
        missing_just = [row for row in expected_just if row not in actual_just]
        missing_obj = [row for row in expected_obj if row not in actual_obj]
        if missing_just:
            ctx.report.error('WDV-MWK-008', 'Justifications du registre absentes de la frontière de profondeur', path=rel, details={'missing': missing_just, 'actual': actual_just})
        if missing_obj:
            ctx.report.error('WDV-MWK-008', 'Objections du registre absentes de la frontière de profondeur', path=rel, details={'missing': missing_obj, 'actual': actual_obj})
    elif not relations_omitted and actual_just != expected_just:
        ctx.report.error('WDV-MWK-008', 'Justifications MediaWiki divergentes du registre', path=rel, details={'expected': expected_just, 'actual': actual_just})
    if not depth_frontier and not relations_omitted and actual_obj != expected_obj:
        ctx.report.error('WDV-MWK-008', 'Objections MediaWiki divergentes du registre', path=rel, details={'expected': expected_obj, 'actual': actual_obj})
    section_param = 'rubriques' if lang == 'fr' else 'sections'
    expected_sections = (node.get(lang) or {}).get('rubriques' if lang == 'fr' else 'sections', [])
    actual_sections = split_list(tmpl.one(section_param) or '')
    if actual_sections != expected_sections:
        ctx.report.error('WDV-MWK-009', f'{section_param} divergent du registre', path=rel, details={'expected': expected_sections, 'actual': actual_sections})
    allowed = FR_SECTIONS if lang == 'fr' else EN_SECTIONS
    for value in actual_sections:
        if value not in allowed:
            ctx.report.error('WDV-MWK-009', f'{section_param} non autorisée : {value}', path=rel)
    kw_param = 'mots-clés' if lang == 'fr' else 'keywords'
    expected_kw = (node.get(lang) or {}).get('keywords', [])
    actual_kw = split_list(tmpl.one(kw_param) or '')
    if actual_kw != expected_kw:
        ctx.report.error('WDV-MWK-009', f'{kw_param} divergents du registre', path=rel, details={'expected': expected_kw, 'actual': actual_kw})
    _validate_citations_against_locks(ctx, tmpl, rel, lang, page_id)
    date_param = 'date-création' if lang == 'fr' else 'creation-date'
    expected_date = page_manifest.get('creation_date') or (((node.get('pages') or {}).get(lang) or {}).get('generation') or {}).get('creation_date')
    actual_date = tmpl.one(date_param)
    preserved_date = (page_manifest.get('preserved_parameters') or {}).get(date_param) if isinstance(page_manifest, dict) else None
    historical_absence = bool(page_manifest.get('page_origin') == 'preexisting' and isinstance(preserved_date, dict) and (preserved_date.get('present') is False))
    if not historical_absence and (not re.fullmatch('\\d{4}-\\d{2}-\\d{2}', actual_date or '') or (expected_date and actual_date != expected_date)):
        ctx.report.error('WDV-MWK-010', 'Date de création absente, invalide ou divergente', path=rel, details={'expected': expected_date, 'actual': actual_date})

def _validate_debate_content(ctx: PackageContext, tmpl: Template, rel: str, lang: str, registry: dict[str, Any], page_manifest: dict[str, Any]) -> None:
    wikipedia_parameter = 'articles-Wikipédia' if lang == 'fr' else 'wikipedia-articles'
    wikipedia_model = 'Article Wikipédia' if lang == 'fr' else 'Wikipedia article'
    articles = get_subs(tmpl, wikipedia_parameter)
    if not articles or any((article.name != wikipedia_model or not (article.one('page') or '').strip() for article in articles)):
        ctx.report.error('WDV-MWK-019', f'{wikipedia_parameter} doit contenir au moins un article Wikipédia vérifié', path=rel)
    occs = [o for o in registry.get('graph', {}).get('occurrences', []) if o.get('depth') == 1]
    nodes = {n.get('id'): n for n in registry.get('graph', {}).get('nodes', [])}
    contextual = _contextual_relation_labels(ctx, 'debate', lang, 'debate')
    for branch, param in (('pro', 'arguments-pour' if lang == 'fr' else 'pro-arguments'), ('con', 'arguments-contre' if lang == 'fr' else 'con-arguments')):
        expected = []
        for occ in sorted((o for o in occs if o.get('branch') == branch), key=lambda o: (o.get('order', 0), o.get('id', ''))):
            data = (nodes.get(occ.get('node_id')) or {}).get(lang) or {}
            contextual_key = 'source_text' if lang == 'fr' else 'translated_text'
            label = next((r.get(contextual_key) for r in contextual if r.get('id') == 'root:' + str(occ.get('id')) and r.get('target_node_id') == occ.get('node_id') and r.get(contextual_key)), data.get('displayed_title'))
            expected.append((data.get('canonical_title'), label))
        actual = relation_pairs(get_subs(tmpl, param), lang)
        if actual != expected:
            ctx.report.error('WDV-MWK-008', f'Liste {param} divergente du registre', path=rel, details={'expected': expected, 'actual': actual})
    date_param = 'date-création' if lang == 'fr' else 'creation-date'
    expected_date = page_manifest.get('creation_date')
    actual_date = tmpl.one(date_param)
    preserved_date = (page_manifest.get('preserved_parameters') or {}).get(date_param) if isinstance(page_manifest, dict) else None
    historical_absence = bool(page_manifest.get('page_origin') == 'preexisting' and isinstance(preserved_date, dict) and (preserved_date.get('present') is False))
    if not historical_absence and (not re.fullmatch('\\d{4}-\\d{2}-\\d{2}', actual_date or '') or (expected_date and actual_date != expected_date)):
        ctx.report.error('WDV-MWK-010', 'Date de création du débat invalide ou divergente', path=rel, details={'expected': expected_date, 'actual': actual_date})

def _validate_interlanguage(ctx: PackageContext, tmpl: Template, rel: str, lang: str, page_type: str, page_id: str, registry: dict[str, Any], staging: bool) -> None:
    manifest = ctx.manifest() or {}
    status = manifest.get('global_status')
    links = get_subs(tmpl, 'interlangue')
    raw_parameter_present = tmpl.one('interlangue') is not None
    if lang == 'en':
        if links or raw_parameter_present:
            ctx.report.error('WDV-MWK-011', 'Une page anglaise ne doit jamais contenir de lien interlangue', path=rel)
        return
    norm_120 = True
    deferred = english_translation_deferred(manifest)
    page_manifest = next((p for p in manifest.get('pages', []) if p.get('page_id') == page_id and p.get('language') == lang), {})
    inter_state = (page_manifest.get('preserved_parameters') or {}).get('interlangue') if isinstance(page_manifest, dict) else None
    historical_interlanguage = bool(deferred and links and isinstance(inter_state, dict) and (inter_state.get('present') is True) and (inter_state.get('value') == tmpl.one('interlangue')))
    expected_present = False if deferred else True if norm_120 else staging or state_at_least(status, 'interlanguage_applied')
    if expected_present and len(links) != 1:
        message = 'Un lien interlangue français unique est requis dès la création' if norm_120 else 'Un lien interlangue français unique est requis à cette étape'
        ctx.report.error('WDV-MWK-011', message, path=rel)
    if deferred and raw_parameter_present and (not links):
        ctx.report.error('WDV-MWK-011', 'Le paramètre interlangue doit être absent, et non vide, tant que la traduction anglaise est différée', path=rel)
    if not expected_present and (not deferred) and links:
        ctx.report.error('WDV-MWK-011', 'Lien interlangue français prématuré', path=rel)
    if deferred and len(links) > 1:
        ctx.report.error('WDV-MWK-011', "Une page française ne peut contenir qu'un seul lien interlangue", path=rel)
    if links:
        link = links[0]
        expected_model = 'Lien interlangue' if norm_120 or page_type == 'argument' else 'Interlangue'
        if link.name != expected_model:
            ctx.report.error('WDV-MWK-011', f'Sous-modèle interlangue attendu : {expected_model}', path=rel)
        if link.one('langue') != 'en':
            ctx.report.error('WDV-MWK-011', 'La langue cible doit être en', path=rel)
        if page_type == 'debate':
            english_record = ((registry.get('debate') or {}).get('pages') or {}).get('en') or {}
        else:
            node = next((n for n in registry.get('graph', {}).get('nodes', []) if n.get('id') == page_id), {})
            english_record = node.get('en') or {}
        expected_title = english_record.get('canonical_title')
        actual_title = link.one('page')
        if historical_interlanguage:
            if not actual_title:
                ctx.report.error('WDV-MWK-011', 'La cible du lien interlangue historique ne peut pas être vide', path=rel)
        else:
            if english_record.get('title_status') != 'locked' or not expected_title:
                ctx.report.error('WDV-MWK-011', 'Un lien interlangue exige un titre canonique anglais verrouillé', path=rel)
            if not actual_title:
                ctx.report.error('WDV-MWK-011', 'La cible du lien interlangue ne peut pas être vide', path=rel)
            elif actual_title != expected_title:
                ctx.report.error('WDV-MWK-011', 'Cible interlangue incorrecte', path=rel, details={'expected': expected_title, 'actual': actual_title})
PAIRED_EM_DASH_RE = re.compile('\\s—\\s[^—\\n]{1,500}?\\s—(?=\\s|[.,;:!?])')

def _validate_french_parenthetical_dashes(
    ctx: PackageContext,
    tmpl: Template,
    rel: str,
    page_type: str,
    page_id: str | None = None,
) -> None:
    # The rule applies to generated prose.  It must not be applied
    # retroactively to an exactly preserved historical summary/introduction,
    # nor to metadata carried inside an inline template (for example a legacy
    # tooltip copied from Wikipedia).
    if page_type == 'argument' and isinstance(page_id, str) and (page_id, 'fr') in _protected_historical_summary_keys(ctx):
        return
    if page_type == 'debate' and _preserved_historical_french_introduction(ctx):
        return

    values: list[tuple[str, str]] = []
    if page_type == 'argument':
        values.append(('résumé', tmpl.one('résumé') or ''))
    elif page_type == 'debate':
        try:
            for index, subsection in enumerate(get_subs(tmpl, 'introduction'), start=1):
                values.append((f'introduction/{index}/contenu', subsection.one('contenu') or ''))
        except WikiParseError:
            return
    for field, value in values:
        prose = re.sub('<ref\\b[^>]*>.*?</ref>', '', value, flags=re.IGNORECASE | re.DOTALL)
        for span in _inline_template_spans(prose):
            prose = prose.replace(span, ' ')
        match = PAIRED_EM_DASH_RE.search(prose)
        if match:
            excerpt = ' '.join(match.group(0).split())[:220]
            ctx.report.error('WDV-MWK-015', 'Une incise française doit employer des parenthèses, non une paire de tirets cadratins', path=rel, pointer=field, details={'excerpt': excerpt})
REF_BLOCK_RE = re.compile('<ref\\b[^>]*>.*?</ref>', flags=re.IGNORECASE | re.DOTALL)
SELF_CLOSING_REF_RE = re.compile('<ref\\b[^>]*/\\s*>', flags=re.IGNORECASE)

def _inline_template_spans(text: str) -> list[str]:
    """Extract balanced top-level inline templates from free prose."""
    out: list[str] = []
    i = 0
    while i < len(text) - 1:
        if text[i:i + 2] != '{{':
            i += 1
            continue
        start = i
        depth = 0
        while i < len(text) - 1:
            pair = text[i:i + 2]
            if pair == '{{':
                depth += 1
                i += 2
                continue
            if pair == '}}':
                depth -= 1
                i += 2
                if depth == 0:
                    out.append(text[start:i])
                    break
                continue
            i += 1
        else:
            break
    return out

def _display_parameter_redundant(article: str, displayed: str) -> bool:

    def norm(value: str) -> str:
        return ' '.join(value.replace('_', ' ').split()).casefold()
    return norm(article) == norm(displayed)

def _legacy_fr_content_lock_has_explicit_text_policy(lock: dict[str, Any]) -> bool:
    return isinstance(lock.get('historical_text_decisions'), dict) or isinstance(lock.get('historical_text_preservation'), dict)


def _legacy_render_differential_mode(ctx: PackageContext) -> bool:
    controls = (ctx.manifest() or {}).get('editorial_controls') or {}
    return controls.get('historical_text_render_validation_mode') == 'differential_preservation_v1'


def _legacy_fr_content_argument_rows(lock: dict[str, Any]) -> list[dict[str, Any]]:
    if _legacy_fr_content_lock_has_explicit_text_policy(lock):
        return []
    rows = lock.get('arguments')
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _protected_historical_summary_keys(ctx: PackageContext) -> set[tuple[str, str]]:
    return _shared_protected_historical_summary_keys(ctx)

def _historically_absent_summary_keys(ctx: PackageContext) -> set[tuple[str, str]]:
    return _shared_historically_absent_summary_keys(ctx)

def _preserved_historical_french_introduction(ctx: PackageContext) -> bool:
    cached = getattr(ctx, '_preserved_historical_french_introduction_cache', None)
    if isinstance(cached, bool):
        return cached
    if not ctx.exists('data/fr_content_lock.json'):
        setattr(ctx, '_preserved_historical_french_introduction_cache', False)
        return False
    lock = ctx.load_json('data/fr_content_lock.json')
    if not isinstance(lock, dict):
        setattr(ctx, '_preserved_historical_french_introduction_cache', False)
        return False
    decisions = lock.get('historical_text_decisions')
    if isinstance(decisions, dict):
        row = decisions.get('debate')
        result = bool(isinstance(row, dict) and row.get('page_origin') == 'preexisting'
                      and row.get('historical_status') == 'historical_existing'
                      and row.get('decision') == 'preserved')
    else:
        preservation = lock.get('historical_text_preservation')
        if isinstance(preservation, dict):
            row = preservation.get('debate')
            result = bool(isinstance(row, dict) and row.get('page_origin') == 'preexisting'
                          and row.get('preserved') is True
                          and row.get('introduction_provenance') == 'historical_existing')
        else:
            debate = lock.get('debate')
            result = bool(_legacy_render_differential_mode(ctx) and isinstance(debate, dict)
                          and debate.get('page_origin') == 'preexisting'
                          and isinstance(debate.get('introduction'), str) and debate.get('introduction').strip())
    setattr(ctx, '_preserved_historical_french_introduction_cache', result)
    return result

def _translated_historical_english_introduction(ctx: PackageContext) -> bool:
    cached = getattr(ctx, '_translated_historical_english_introduction_cache', None)
    if isinstance(cached, bool):
        return cached
    if not _legacy_render_differential_mode(ctx) or not ctx.exists('data/en_content_lock.json'):
        setattr(ctx, '_translated_historical_english_introduction_cache', False)
        return False
    lock = ctx.load_json('data/en_content_lock.json')
    debate = lock.get('debate') if isinstance(lock, dict) else None
    result = bool(
        isinstance(debate, dict)
        and debate.get('source_page_origin') == 'preexisting'
        and isinstance(debate.get('introduction'), str)
        and debate.get('introduction').strip()
        and _preserved_historical_french_introduction(ctx)
    )
    setattr(ctx, '_translated_historical_english_introduction_cache', result)
    return result


def _owner_removed_summary_keys(ctx: PackageContext) -> set[tuple[str, str]]:
    return _shared_owner_removed_summary_keys(ctx)

def _historical_detailed_debate_states(ctx: PackageContext) -> dict[tuple[str, str], dict[str, Any]]:
    cached = getattr(ctx, '_historical_detailed_debate_states_cache', None)
    if isinstance(cached, dict):
        return cached
    result: dict[tuple[str, str], dict[str, Any]] = {}
    manifest = ctx.manifest() or {}
    cfg = (manifest.get('editorial_controls') or {}).get('legacy_content_preservation') or {}
    protected = set(cfg.get('protected_fields') or [])
    if cfg.get('enabled') is True and protected.intersection({'débat-dédié', 'dedicated-debate', 'débat-détaillé', 'detailed-debate'}):
        rel = cfg.get('lock_path')
        if isinstance(rel, str) and ctx.exists(rel):
            lock = ctx.load_json(rel)
            if isinstance(lock, dict):
                for entry in lock.get('arguments') or []:
                    if not isinstance(entry, dict):
                        continue
                    node_id, language = (entry.get('id'), entry.get('language'))
                    state = entry.get('detailed_debate')
                    if isinstance(node_id, str) and language in {'fr', 'en'} and isinstance(state, dict):
                        result[node_id, language] = state
    status = str(((manifest.get('translation_status') or {}).get('en') or ''))
    if status in {'ready', 'published'}:
        en_ids = {str(p.get('page_id')) for p in manifest.get('pages', []) if p.get('language') == 'en' and p.get('page_type') == 'argument'}
        for (node_id, language), state in list(result.items()):
            if language == 'fr' and node_id in en_ids and state.get('present') is True:
                result[node_id, 'en'] = dict(state)
    setattr(ctx, '_historical_detailed_debate_states_cache', result)
    return result

def _validate_wikipedia_hover_links(ctx: PackageContext, tmpl: Template, rel: str, lang: str, page_type: str, *, skip_summary: bool=False) -> None:
    if page_type == 'argument' and skip_summary:
        return
    fields: list[tuple[str, str]] = []
    if page_type == 'argument':
        key = 'résumé' if lang == 'fr' else 'summary'
        fields.append((key, tmpl.one(key) or ''))
    else:
        content_key = 'contenu' if lang == 'fr' else 'content'
        for index, subsection in enumerate(get_subs(tmpl, 'introduction'), start=1):
            fields.append((f'introduction/{index}/{content_key}', subsection.one(content_key) or ''))
    expected_name = 'Lien Wikipédia' if lang == 'fr' else 'Wikipedia link'
    other_name = 'Wikipedia link' if lang == 'fr' else 'Lien Wikipédia'
    display_param = 'texte-affiché' if lang == 'fr' else 'displayed-text'
    wrong_display_param = 'displayed-text' if lang == 'fr' else 'texte-affiché'
    allowed = {'article', display_param}
    for pointer, value in fields:
        for ref_body in REF_BLOCK_RE.findall(value):
            if '{{Lien Wikipédia' in ref_body or '{{Wikipedia link' in ref_body:
                ctx.report.error('WDV-MWK-020', 'Un lien Wikipédia explicatif est interdit dans le corps d’une note <ref>', path=rel, pointer=pointer)
        prose = REF_BLOCK_RE.sub('', value)
        prose = SELF_CLOSING_REF_RE.sub('', prose)
        for raw in _inline_template_spans(prose):
            try:
                sub = parse_template(raw)
            except WikiParseError as exc:
                ctx.report.error('WDV-MWK-020', f'Modèle inline mal formé : {exc}', path=rel, pointer=pointer)
                continue
            if sub.name == other_name:
                ctx.report.error('WDV-MWK-020', f'Le modèle {sub.name} ne correspond pas à la langue de la page', path=rel, pointer=pointer, details={'expected': expected_name})
                continue
            if sub.name != expected_name:
                ctx.report.error('WDV-MWK-020', f'Modèle inline non autorisé dans ce champ : {sub.name}', path=rel, pointer=pointer, details={'allowed': expected_name})
                continue
            keys = [key for key, _ in sub.params]
            if len(keys) != len(set(keys)):
                ctx.report.error('WDV-MWK-020', f'Paramètre dupliqué dans {expected_name}', path=rel, pointer=pointer)
            unknown = [key for key in keys if key not in allowed]
            if unknown:
                ctx.report.error('WDV-MWK-020', f'Paramètre inconnu dans {expected_name}', path=rel, pointer=pointer, details={'unknown': unknown, 'allowed': sorted(allowed)})
            if wrong_display_param in keys:
                ctx.report.error('WDV-MWK-020', f'Paramètre d’affichage de l’autre langue interdit : {wrong_display_param}', path=rel, pointer=pointer)
            article = (sub.one('article') or '').strip()
            if not article:
                ctx.report.error('WDV-MWK-020', f'{expected_name} exige un paramètre article non vide', path=rel, pointer=pointer)
            elif re.match('https?://', article, flags=re.I):
                ctx.report.error('WDV-MWK-020', 'Le paramètre article doit contenir un titre de page, non une URL', path=rel, pointer=pointer, details={'article': article})
            displayed = sub.one(display_param)
            if displayed is not None:
                if not displayed.strip():
                    ctx.report.error('WDV-MWK-020', f'Le paramètre {display_param} ne peut pas être vide', path=rel, pointer=pointer)
                elif article and _display_parameter_redundant(article, displayed):
                    ctx.report.error('WDV-MWK-020', f'Le paramètre {display_param} est redondant ; adapter simplement la casse dans article', path=rel, pointer=pointer, details={'article': article, 'displayed': displayed})

def validate_page(ctx: PackageContext, page_manifest: dict[str, Any], *, override_path: str | None=None, staging: bool=False) -> Template | None:
    rel = override_path or page_manifest.get('file_path')
    if not rel:
        return None
    text = ctx.read_text(rel, required=page_manifest.get('status') in {'generated', 'validated', 'published'})
    if text is None:
        return None
    try:
        tmpl = parse_template(text)
    except WikiParseError as exc:
        ctx.report.error('WDV-MWK-001', str(exc), path=rel)
        return None
    lang = page_manifest.get('language')
    page_type = page_manifest.get('page_type')
    if (lang, page_type) not in ACTIVE_TOP:
        return tmpl
    from .source_preservation import preserved_french_page
    if preserved_french_page(ctx, page_manifest, text):
        _validate_interlanguage(ctx, tmpl, rel, lang, page_type, page_manifest.get('page_id'), ctx.registry() or {}, staging)
        ctx.report.info('WDV-MWK-023', 'Page française historique conservée exactement ; seul le lien interlangue a été ajouté', path=rel)
        return tmpl
    validate_template_shape(ctx, tmpl, lang, page_type, rel, page_manifest)
    _check_reference_language_and_typography(ctx, tmpl, rel, lang)
    page_key = (page_manifest.get('page_id'), lang)
    _validate_wikipedia_hover_links(ctx, tmpl, rel, lang, page_type, skip_summary=page_key in _protected_historical_summary_keys(ctx) | _historically_absent_summary_keys(ctx) | _owner_removed_summary_keys(ctx))
    page_id = page_manifest.get('page_id')
    if lang == 'fr':
        _validate_french_parenthetical_dashes(ctx, tmpl, rel, page_type, str(page_id) if page_id is not None else None)
    registry = ctx.registry() or {}
    if page_type == 'argument':
        _validate_argument_content(ctx, tmpl, rel, lang, page_id, registry, page_manifest)
    else:
        _validate_debate_content(ctx, tmpl, rel, lang, registry, page_manifest)
    _validate_interlanguage(ctx, tmpl, rel, lang, page_type, page_id, registry, staging)
    return tmpl


def _validate_bounded_depth_frontier_relations(
    ctx: PackageContext,
    registry: dict[str, Any],
    parsed_by_key: dict[tuple[str, str], Template],
) -> None:
    """Account for every preserved relation beyond a bounded extraction."""
    policy = registry.get('graph', {}).get('depth_policy') or {}
    if policy.get('limit_policy') != 'bounded':
        return
    frontier_ids = policy.get('frontier_node_ids') or []
    if not isinstance(frontier_ids, list):
        return
    actual = 0
    for page_id in frontier_ids:
        tmpl = parsed_by_key.get((page_id, 'fr'))
        if tmpl is None:
            continue
        actual += len(get_subs(tmpl, 'justifications'))
        actual += len(get_subs(tmpl, 'objections'))
    expected = policy.get('relations_omitted_at_frontier')
    if not isinstance(expected, int) or expected < 0 or actual != expected:
        ctx.report.error(
            'WDV-MWK-008',
            'Le nombre de relations préservées aux frontières de profondeur diverge de la politique bornée',
            path='data/registre_debat.json',
            details={'expected': expected, 'actual': actual, 'frontier_nodes': len(frontier_ids)},
        )

def _validate_legacy_content_preservation(ctx: PackageContext, parsed_by_key: dict[tuple[str, str], Template]) -> None:
    manifest = ctx.manifest() or {}
    controls = manifest.get('editorial_controls') or {}
    cfg = controls.get('legacy_content_preservation') or {}
    if cfg.get('enabled') is not True:
        return
    lock_rel = cfg.get('lock_path')
    if not isinstance(lock_rel, str) or not ctx.exists(lock_rel):
        ctx.report.error('WDV-EDT-027', 'Verrou des contenus historiques absent', path=lock_rel or 'manifest.json')
        return
    lock = ctx.load_json(lock_rel)
    if not isinstance(lock, dict):
        ctx.report.error('WDV-EDT-027', 'Verrou des contenus historiques invalide', path=lock_rel)
        return
    if lock.get('debate_id') != manifest.get('debate_id'):
        ctx.report.error('WDV-EDT-027', 'Le verrou historique ne correspond pas au débat', path=lock_rel)
    expected_source_sha = cfg.get('source_archive_sha256')
    if expected_source_sha and lock.get('source_archive_sha256') != expected_source_sha:
        ctx.report.error('WDV-EDT-027', 'Empreinte de la source historique divergente', path=lock_rel, details={'expected': expected_source_sha, 'actual': lock.get('source_archive_sha256')})
    source_templates: dict[tuple[str, str], Template] = {}
    inventory_rel = cfg.get('source_inventory_path')
    inventory_sha = cfg.get('source_inventory_sha256')
    if not isinstance(inventory_rel, str) or not ctx.exists(inventory_rel):
        ctx.report.error('WDV-EDT-027', 'Inventaire source historique absent', path=inventory_rel or 'manifest.json')
    else:
        raw_inventory = ctx.root.joinpath(inventory_rel).read_bytes()
        actual_inventory_sha = hashlib.sha256(raw_inventory).hexdigest()
        if inventory_sha != actual_inventory_sha:
            ctx.report.error('WDV-EDT-027', 'Empreinte de l’inventaire source historique divergente', path=inventory_rel, details={'expected': inventory_sha, 'actual': actual_inventory_sha})
        inventory = ctx.load_json(inventory_rel)
        if not isinstance(inventory, dict) or inventory.get('debate_id') != manifest.get('debate_id') or inventory.get('language') != 'fr':
            ctx.report.error('WDV-EDT-027', 'Inventaire source historique invalide', path=inventory_rel)
        else:
            for source_page in inventory.get('pages') or []:
                if not isinstance(source_page, dict) or source_page.get('page_type') not in {'argument', 'debate'}:
                    continue
                page_id = source_page.get('page_id')
                content = source_page.get('content')
                if not isinstance(page_id, str) or not isinstance(content, str):
                    continue
                try:
                    source_templates[page_id, 'fr'] = parse_template(content)
                except WikiParseError as exc:
                    ctx.report.error('WDV-EDT-027', f'Page source historique illisible : {exc}', path=inventory_rel, details={'page_id': page_id})
    protected_fields = set(cfg.get('protected_fields') or [])

    # Règle éditoriale courante : une page historique n'est jamais retraitée
    # comme une création. Tout paramètre top-level attesté par l'inventaire
    # historique reste présent, sauf suppression propriétaire explicitement
    # documentée ou exception relationnelle déjà attestée. La valeur d'une
    # ancienne verification_revision n'active ni ne désactive ce contrôle.
    if 'all-existing-parameters' in protected_fields:
        allowed_deletions: set[tuple[str, str, str]] = set()
        for row in lock.get('allowed_parameter_deletions') or []:
            if not isinstance(row, dict):
                continue
            page_id = row.get('page_id')
            language = row.get('language')
            parameter = row.get('parameter')
            if all(isinstance(v, str) and v for v in (page_id, language, parameter)):
                allowed_deletions.add((page_id, language, parameter))
        lock_entries = {
            (row.get('id'), row.get('language')): row
            for row in (lock.get('arguments') or []) if isinstance(row, dict)
        }
        for key, source_tmpl in source_templates.items():
            current = parsed_by_key.get(key)
            if current is None:
                continue
            current_names = {name for name, _ in current.params}
            source_names = {name for name, _ in source_tmpl.params}
            entry = lock_entries.get(key) or {}
            detailed = entry.get('detailed_debate') if isinstance(entry, dict) else None
            for parameter in sorted(source_names - current_names):
                permitted = (key[0], key[1], parameter) in allowed_deletions
                if parameter in {'justifications', 'objections'} and isinstance(detailed, dict) and detailed.get('relations_omitted') is True:
                    permitted = True
                if parameter in {'résumé', 'summary'} and isinstance(entry, dict) and entry.get('summary_provenance') == 'owner_removed':
                    permitted = True
                if not permitted:
                    ctx.report.error(
                        'WDV-EDT-030',
                        'Un paramètre d’une page historique a été supprimé sans décision explicite',
                        path=next((p.get('file_path') for p in manifest.get('pages', []) if p.get('page_id') == key[0] and p.get('language') == key[1]), lock_rel),
                        details={'page_id': key[0], 'language': key[1], 'parameter': parameter},
                    )
    entries = lock.get('arguments')
    if not isinstance(entries, list):
        ctx.report.error('WDV-EDT-027', 'Liste des pages historiques absente', path=lock_rel)
        return
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        key = (entry.get('id'), entry.get('language'))
        if not all((isinstance(v, str) for v in key)) or key in by_key:
            ctx.report.error('WDV-EDT-027', 'Entrée historique invalide ou dupliquée', path=lock_rel, details={'key': list(key)})
            continue
        by_key[key] = entry
    for key, entry in by_key.items():
        tmpl = parsed_by_key.get(key)
        if tmpl is None:
            ctx.report.error('WDV-EDT-027', 'Page historique protégée absente du manifeste', path=lock_rel, details={'page_id': key[0], 'language': key[1]})
            continue
        lang = key[1]
        if ('résumé' if lang == 'fr' else 'summary') in protected_fields:
            provenance = entry.get('summary_provenance')
            field = 'résumé' if lang == 'fr' else 'summary'
            source_tmpl = source_templates.get(key)
            source_summary = source_tmpl.one(field) if source_tmpl is not None else None
            if provenance not in {'historical_existing', 'generated_after_import', 'historical_absent', 'owner_removed'}:
                ctx.report.error('WDV-EDT-027', 'Provenance du résumé historique invalide', path=lock_rel, details={'page_id': key[0], 'provenance': provenance})
            elif source_tmpl is None:
                ctx.report.error('WDV-EDT-027', 'Page historique absente de l’inventaire source', path=lock_rel, details={'page_id': key[0], 'language': lang})
            elif provenance == 'historical_existing' and source_summary is None:
                ctx.report.error('WDV-EDT-027', 'Résumé déclaré historique mais absent de l’inventaire source', path=lock_rel, details={'page_id': key[0]})
            elif provenance in {'generated_after_import', 'historical_absent'} and source_summary is not None:
                ctx.report.error('WDV-EDT-027', 'Résumé historique présent dans l’inventaire mais classé comme absent ou généré', path=lock_rel, details={'page_id': key[0], 'provenance': provenance})
            elif provenance == 'owner_removed':
                if source_summary is None:
                    ctx.report.error('WDV-EDT-027', 'Suppression propriétaire déclarée pour un résumé historiquement absent', path=lock_rel, details={'page_id': key[0]})
                if len(str(entry.get('owner_decision') or '').strip()) < 10 or len(str(entry.get('owner_decision_recorded_at') or '').strip()) < 10:
                    ctx.report.error('WDV-EDT-027', 'Décision propriétaire insuffisamment documentée pour la suppression du résumé', path=lock_rel, details={'page_id': key[0]})
                actual = tmpl.one(field)
                if actual is not None:
                    ctx.report.error('WDV-EDT-027', 'Le résumé explicitement supprimé par le propriétaire est encore présent', path=next((p.get('file_path') for p in manifest.get('pages', []) if p.get('page_id') == key[0] and p.get('language') == lang), lock_rel), details={'page_id': key[0]})
            elif provenance == 'historical_absent':
                actual = tmpl.one(field)
                if actual is not None:
                    ctx.report.error('WDV-EDT-027', 'Un résumé a été ajouté à une page attestée sans résumé historique', path=next((p.get('file_path') for p in manifest.get('pages', []) if p.get('page_id') == key[0] and p.get('language') == lang), lock_rel), details={'page_id': key[0]})
            elif provenance == 'generated_after_import':
                actual = tmpl.one(field)
                if actual is None:
                    ctx.report.error('WDV-EDT-027', 'Un résumé généré après import ne peut pas être omis', path=next((p.get('file_path') for p in manifest.get('pages', []) if p.get('page_id') == key[0] and p.get('language') == lang), lock_rel), details={'page_id': key[0]})
            elif provenance == 'historical_existing':
                actual = tmpl.one(field)
                actual_sha = hashlib.sha256((actual or '').encode('utf-8')).hexdigest()
                expected_sha = entry.get('summary_sha256')
                expected_length = entry.get('summary_length')
                if source_summary is not None:
                    source_sha = hashlib.sha256(source_summary.encode('utf-8')).hexdigest()
                    if expected_sha != source_sha or expected_length != len(source_summary):
                        ctx.report.error('WDV-EDT-027', 'Verrou du résumé historique incohérent avec l’inventaire source', path=lock_rel, details={'page_id': key[0], 'expected_sha256': source_sha, 'lock_sha256': expected_sha})
                if actual is None or actual_sha != expected_sha or len(actual) != expected_length:
                    ctx.report.error('WDV-EDT-027', 'Résumé historique modifié', path=next((p.get('file_path') for p in manifest.get('pages', []) if p.get('page_id') == key[0] and p.get('language') == lang), lock_rel), details={'page_id': key[0], 'expected_sha256': expected_sha, 'actual_sha256': actual_sha})
        init_field = 'initialisation' if lang == 'fr' else 'initialization'
        if init_field in protected_fields:
            state = entry.get('initialisation') if lang == 'fr' else entry.get('initialization')
            actual = tmpl.one(init_field)
            source_tmpl = source_templates.get(key)
            source_initialisation = source_tmpl.one(init_field) if source_tmpl is not None else None
            if source_tmpl is not None:
                expected_present = source_initialisation is not None
                lock_present = isinstance(state, dict) and state.get('present') is True
                lock_value = state.get('value') if isinstance(state, dict) else None
                if lock_present != expected_present or (expected_present and lock_value != source_initialisation):
                    ctx.report.error('WDV-EDT-027', 'Verrou d’initialisation incohérent avec l’inventaire source', path=lock_rel, details={'page_id': key[0], 'expected': source_initialisation, 'lock': lock_value if lock_present else None})
            if not isinstance(state, dict) or not isinstance(state.get('present'), bool):
                ctx.report.error('WDV-EDT-027', "État historique d'initialisation invalide", path=lock_rel, details={'page_id': key[0]})
            elif state.get('present'):
                if actual != state.get('value'):
                    ctx.report.error('WDV-EDT-027', 'Paramètre initialisation historique modifié ou supprimé', path=next((p.get('file_path') for p in manifest.get('pages', []) if p.get('page_id') == key[0] and p.get('language') == lang), lock_rel), details={'page_id': key[0], 'expected': state.get('value'), 'actual': actual})
            elif actual is not None:
                ctx.report.error('WDV-EDT-027', 'Paramètre initialisation ajouté sans provenance historique', path=next((p.get('file_path') for p in manifest.get('pages', []) if p.get('page_id') == key[0] and p.get('language') == lang), lock_rel), details={'page_id': key[0], 'actual': actual})
        current_name_field, legacy_name_field = _argument_established_name_parameters(lang)
        name_field = current_name_field if current_name_field in protected_fields else legacy_name_field
        if name_field in protected_fields:
            state = entry.get(name_field)
            actual = tmpl.one(name_field)
            source_tmpl = source_templates.get(key)
            source_name = source_tmpl.one(name_field) if source_tmpl is not None else None
            if source_tmpl is not None:
                expected_present = source_name is not None
                lock_present = isinstance(state, dict) and state.get('present') is True
                lock_value = state.get('value') if isinstance(state, dict) else None
                if lock_present != expected_present or (expected_present and lock_value != source_name):
                    ctx.report.error('WDV-EDT-027', 'Verrou du paramètre nom incohérent avec l’inventaire source', path=lock_rel, details={'page_id': key[0], 'expected': source_name, 'lock': lock_value if lock_present else None})
            if not isinstance(state, dict) or not isinstance(state.get('present'), bool):
                ctx.report.error('WDV-EDT-027', 'État historique du paramètre nom invalide', path=lock_rel, details={'page_id': key[0]})
            elif state.get('present'):
                if actual != state.get('value'):
                    ctx.report.error('WDV-EDT-027', 'Paramètre nom historique modifié ou supprimé', path=next((p.get('file_path') for p in manifest.get('pages', []) if p.get('page_id') == key[0] and p.get('language') == lang), lock_rel), details={'page_id': key[0], 'expected': state.get('value'), 'actual': actual})
            elif actual is not None:
                assignment = _argument_name_assignment(ctx, key[0], lang)
                if not (assignment is not None and actual == assignment.get('name')):
                    ctx.report.error('WDV-EDT-027', 'Paramètre nom ajouté sans provenance historique ni attribution éditoriale approuvée', path=next((p.get('file_path') for p in manifest.get('pages', []) if p.get('page_id') == key[0] and p.get('language') == lang), lock_rel), details={'page_id': key[0], 'actual': actual})
        detailed_current, detailed_legacy = _renamed_parameter_names(lang, 'argument') or ('', '')
        detailed_field = detailed_current if detailed_current in protected_fields else detailed_legacy
        if detailed_field in protected_fields:
            state = entry.get('detailed_debate')
            actual = tmpl.one(detailed_field)
            source_tmpl = source_templates.get(key)
            source_value = _template_renamed_value(source_tmpl, lang, 'argument')
            if not isinstance(state, dict) or not isinstance(state.get('present'), bool):
                ctx.report.error('WDV-EDT-027', 'État historique du débat détaillé invalide', path=lock_rel, details={'page_id': key[0]})
            elif state.get('present'):
                expected = state.get('value')
                if not isinstance(expected, str) or not expected.strip():
                    ctx.report.error('WDV-EDT-027', 'Cible historique du débat détaillé absente', path=lock_rel, details={'page_id': key[0]})
                if source_tmpl is not None and source_value != expected:
                    ctx.report.error('WDV-EDT-027', 'Verrou du débat détaillé incohérent avec l’inventaire source', path=lock_rel, details={'page_id': key[0], 'expected': source_value, 'lock': expected})
                if actual != expected:
                    ctx.report.error('WDV-EDT-027', 'Paramètre débat-dédié historique modifié ou supprimé', path=next((p.get('file_path') for p in manifest.get('pages', []) if p.get('page_id') == key[0] and p.get('language') == lang), lock_rel), details={'page_id': key[0], 'expected': expected, 'actual': actual})
                if not isinstance(state.get('relations_omitted'), bool):
                    ctx.report.error('WDV-EDT-027', 'Décision d’omission des relations absente pour une frontière de débat détaillé', path=lock_rel, details={'page_id': key[0]})
                if state.get('relations_omitted') is True and state.get('owner_notified') is not True:
                    ctx.report.error('WDV-EDT-027', 'L’omission des justifications et objections n’a pas été signalée au propriétaire', path=lock_rel, details={'page_id': key[0]})
            else:
                if source_value is not None:
                    ctx.report.error('WDV-EDT-027', 'Débat détaillé présent dans l’inventaire mais déclaré absent du verrou', path=lock_rel, details={'page_id': key[0], 'source': source_value})
                if actual is not None:
                    ctx.report.error('WDV-EDT-027', 'Paramètre débat-dédié ajouté sans provenance historique', path=next((p.get('file_path') for p in manifest.get('pages', []) if p.get('page_id') == key[0] and p.get('language') == lang), lock_rel), details={'page_id': key[0], 'actual': actual})
    debate_id = manifest.get('debate_id')
    for key in parsed_by_key:
        if key[0] == debate_id:
            continue
        if key in source_templates and key not in by_key:
            ctx.report.error('WDV-EDT-027', 'Page importée active absente du verrou historique', path=lock_rel, details={'page_id': key[0], 'language': key[1]})
    for key, tmpl in parsed_by_key.items():
        if key in by_key:
            continue
        init_field = 'initialisation' if key[1] == 'fr' else 'initialization'
        if init_field in protected_fields and tmpl.one(init_field) is not None:
            ctx.report.error('WDV-EDT-027', 'Paramètre initialisation présent sur une page non attestée par le verrou historique', path=next((p.get('file_path') for p in manifest.get('pages', []) if p.get('page_id') == key[0] and p.get('language') == key[1]), lock_rel), details={'page_id': key[0], 'language': key[1]})
        current_name_field, legacy_name_field = _argument_established_name_parameters(key[1])
        name_field = current_name_field if current_name_field in protected_fields else legacy_name_field
        actual_name = tmpl.one(name_field)
        if name_field in protected_fields and actual_name is not None:
            assignment = _argument_name_assignment(ctx, key[0], key[1])
            if not (assignment is not None and actual_name == assignment.get('name')):
                ctx.report.error('WDV-EDT-027', 'Paramètre nom présent sur une page non attestée par le verrou historique ni par une attribution éditoriale approuvée', path=next((p.get('file_path') for p in manifest.get('pages', []) if p.get('page_id') == key[0] and p.get('language') == key[1]), lock_rel), details={'page_id': key[0], 'language': key[1]})
        detailed_current, detailed_legacy = _renamed_parameter_names(key[1], 'argument') or ('', '')
        detailed_field = detailed_current if detailed_current in protected_fields else detailed_legacy
        if detailed_field in protected_fields and _template_renamed_value(tmpl, key[1], 'argument') is not None:
            ctx.report.error('WDV-EDT-027', 'Paramètre débat-dédié présent sur une page non attestée par le verrou historique', path=next((p.get('file_path') for p in manifest.get('pages', []) if p.get('page_id') == key[0] and p.get('language') == key[1]), lock_rel), details={'page_id': key[0], 'language': key[1]})

def validate_wikicode(ctx: PackageContext) -> None:
    manifest = ctx.manifest()
    registry = ctx.registry()
    if not manifest or not registry:
        return
    pages = manifest.get('pages', [])
    declared_paths: set[str] = set()
    parsed_by_key: dict[tuple[str, str], Template] = {}
    for page in pages:
        path = page.get('file_path')
        if path:
            declared_paths.add(path)
        tmpl = validate_page(ctx, page)
        if tmpl:
            parsed_by_key[page.get('page_id'), page.get('language')] = tmpl
    _validate_legacy_content_preservation(ctx, parsed_by_key)
    _validate_fr_historical_text_preservation(ctx, parsed_by_key)
    _validate_bounded_depth_frontier_relations(ctx, registry, parsed_by_key)
    patch = ctx.load_json('patches/interlanguage_fr.validated.json')
    validate_staging = state_at_least(manifest.get('global_status'), 'interlanguage_prepared') or (isinstance(patch, dict) and patch.get('status') in {'validated', 'partially_applied', 'applied'})
    for path in ctx.iter_files('output/*/arguments/*.wiki'):
        rel = ctx.relative(path)
        if rel not in declared_paths:
            ctx.report.error('WDV-FS-006', 'Fichier de page Argument non déclaré dans le manifeste', path=rel)
    validate_aggregates(ctx, pages)
    ctx.report.metrics['wikicode'] = {'declared_pages': len(pages), 'parsed_pages': len(parsed_by_key)}



def _canonical_object_sha256(value: dict[str, Any], excluded_key: str | None = None) -> str:
    body = dict(value)
    if excluded_key:
        body.pop(excluded_key, None)
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_fr_historical_text_decisions_v2(
    ctx: PackageContext,
    parsed_by_key: dict[tuple[str, str], Template],
    lock: dict[str, Any],
    decisions: dict[str, Any],
) -> None:
    lock_rel = 'data/fr_content_lock.json'
    if decisions.get('policy') not in {'preserve_by_default_owner_authorized_v2', 'preserve_by_default_owner_authorized_v3'}:
        ctx.report.error('WDV-EDT-034', 'Politique de consentement des textes historiques inconnue', path=lock_rel)
        return
    consent_policy = str(decisions.get('policy'))
    manifest = ctx.manifest() or {}
    debate_page = next((p for p in manifest.get('pages', []) if p.get('language') == 'fr' and p.get('page_type') == 'debate'), None)
    argument_pages = {
        str(p.get('page_id')): p for p in manifest.get('pages', [])
        if p.get('language') == 'fr' and p.get('page_type') == 'argument' and isinstance(p.get('page_id'), str)
    }

    receipt = None
    receipt_changes: dict[str, dict[str, Any]] = {}
    receipt_path = decisions.get('authorization_receipt_path')
    receipt_sha = decisions.get('authorization_receipt_sha256')
    if receipt_path is not None:
        if not isinstance(receipt_path, str) or not ctx.exists(receipt_path):
            ctx.report.error('WDV-EDT-034', 'Reçu local d’autorisation propriétaire absent', path=lock_rel)
        else:
            raw = ctx.read_bytes(receipt_path)
            actual_sha = hashlib.sha256(raw).hexdigest()
            if receipt_sha != actual_sha:
                ctx.report.error('WDV-EDT-034', 'Empreinte du reçu d’autorisation propriétaire invalide', path=receipt_path)
            try:
                receipt = json.loads(raw.decode('utf-8'))
            except Exception:
                receipt = None
            if not isinstance(receipt, dict) or receipt.get('schema') != 'wikidebia-owner-historical-text-authorization-1.0':
                ctx.report.error('WDV-EDT-034', 'Schéma du reçu d’autorisation propriétaire invalide', path=receipt_path)
            elif receipt.get('authorization_sha256') != _canonical_object_sha256(receipt, 'authorization_sha256'):
                ctx.report.error('WDV-EDT-034', 'Scellement du reçu d’autorisation propriétaire invalide', path=receipt_path)
            elif receipt.get('debate_id') != lock.get('debate_id') or receipt.get('work_id') != lock.get('work_id'):
                ctx.report.error('WDV-EDT-034', 'Le reçu d’autorisation appartient à un autre débat ou Work', path=receipt_path)
            else:
                rows = receipt.get('changes')
                if isinstance(rows, list):
                    receipt_changes = {str(row.get('field_key')): row for row in rows if isinstance(row, dict) and row.get('field_key')}
    elif receipt_sha is not None:
        ctx.report.error('WDV-EDT-034', 'Empreinte d’autorisation présente sans chemin de reçu', path=lock_rel)

    authorized_keys: set[str] = set()

    def validate_row(row: Any, *, field_key: str, actual: str, path: str) -> None:
        if not isinstance(row, dict):
            ctx.report.error('WDV-EDT-034', 'Décision historique absente ou invalide', path=path, details={'field_key': field_key})
            return
        if row.get('page_origin') != 'preexisting':
            return
        historical_status = row.get('historical_status')
        if historical_status not in {'historical_existing', 'historical_absent'}:
            ctx.report.error('WDV-EDT-034', 'État historique invalide', path=path, details={'field_key': field_key})
        historical_sha = row.get('historical_sha256')
        final_sha = row.get('final_sha256')
        if not isinstance(historical_sha, str) or not re.fullmatch('[0-9a-f]{64}', historical_sha):
            ctx.report.error('WDV-EDT-034', 'Empreinte historique invalide', path=path, details={'field_key': field_key})
            return
        if not isinstance(final_sha, str) or not re.fullmatch('[0-9a-f]{64}', final_sha):
            ctx.report.error('WDV-EDT-034', 'Empreinte finale autorisée invalide', path=path, details={'field_key': field_key})
            return
        actual_sha = hashlib.sha256(actual.encode('utf-8')).hexdigest()
        decision = row.get('decision')
        if decision == 'preserved':
            if row.get('authorization') not in (None, {}):
                ctx.report.error('WDV-EDT-034', 'Un texte préservé ne doit pas porter d’autorisation de changement', path=path, details={'field_key': field_key})
            if historical_sha != final_sha or actual_sha != historical_sha:
                ctx.report.error('WDV-EDT-034', 'Texte historique modifié sans autorisation propriétaire', path=path, details={'field_key': field_key, 'historical_sha256': historical_sha, 'final_sha256': final_sha, 'actual_sha256': actual_sha})
            if historical_status == 'historical_absent' and actual != '':
                ctx.report.error('WDV-EDT-034', 'Un texte historiquement absent a été créé sans autorisation nominative', path=path, details={'field_key': field_key})
            return
        if decision != 'authorized_change':
            ctx.report.error('WDV-EDT-034', 'Décision historique inconnue', path=path, details={'field_key': field_key, 'decision': decision})
            return
        authorized_keys.add(field_key)
        auth = row.get('authorization')
        if not isinstance(auth, dict):
            ctx.report.error('WDV-EDT-034', 'Changement historique déclaré autorisé sans preuve de workflow', path=path, details={'field_key': field_key})
            return
        receipt_row = receipt_changes.get(field_key)
        if not isinstance(receipt_row, dict):
            ctx.report.error('WDV-EDT-034', 'Le reçu propriétaire ne couvre pas ce champ', path=path, details={'field_key': field_key})
            return
        for key, expected in (('historical_sha256', historical_sha), ('final_sha256', final_sha)):
            if receipt_row.get(key) != expected or auth.get(key) != expected:
                ctx.report.error('WDV-EDT-034', 'La preuve propriétaire ne correspond pas aux empreintes du champ', path=path, details={'field_key': field_key, 'component': key})
        if receipt_row.get('authorization_id') != auth.get('authorization_id'):
            ctx.report.error('WDV-EDT-034', 'Identifiant d’autorisation incohérent', path=path, details={'field_key': field_key})
        if consent_policy == 'preserve_by_default_owner_authorized_v3':
            if not isinstance(receipt_row.get('change_type'), str) or receipt_row.get('change_type') != auth.get('change_type'):
                ctx.report.error('WDV-EDT-034', 'Type de changement incohérent entre le verrou et le reçu propriétaire', path=path, details={'field_key': field_key})
        elif auth.get('change_type') is not None and receipt_row.get('change_type') != auth.get('change_type'):
            ctx.report.error('WDV-EDT-034', 'Type de changement incohérent dans un artefact compatible', path=path, details={'field_key': field_key})
        receipt_scope = receipt_row.get('change_scope')
        auth_scope = auth.get('change_scope')
        lock_scope = row.get('change_scope')
        if consent_policy == 'preserve_by_default_owner_authorized_v3':
            if not isinstance(receipt_scope, dict) or not isinstance(auth_scope, dict) or not isinstance(lock_scope, dict):
                ctx.report.error('WDV-EDT-034', 'Portée structurée du changement historique absente', path=path, details={'field_key': field_key})
            elif receipt_scope != auth_scope or receipt_scope != lock_scope:
                ctx.report.error('WDV-EDT-034', 'Portée du changement historique divergente entre verrou et reçu propriétaire', path=path, details={'field_key': field_key})
        elif any(scope is not None for scope in (receipt_scope, auth_scope, lock_scope)) and not (receipt_scope == auth_scope == lock_scope):
            ctx.report.error('WDV-EDT-034', 'Portée du changement historique divergente dans un artefact compatible', path=path, details={'field_key': field_key})
        if actual_sha != final_sha:
            ctx.report.error('WDV-EDT-034', 'Le rendu ne correspond pas à la valeur finale autorisée', path=path, details={'field_key': field_key, 'expected_sha256': final_sha, 'actual_sha256': actual_sha})

    debate_row = decisions.get('debate')
    if isinstance(debate_page, dict):
        tmpl = parsed_by_key.get((debate_page.get('page_id'), 'fr'))
        actual_intro = (tmpl.one('introduction') if tmpl else None) or ''
        validate_row(debate_row, field_key=f"debate:{lock.get('debate_id')}:introduction", actual=actual_intro, path=debate_page.get('file_path') or lock_rel)

    rows = decisions.get('arguments')
    if not isinstance(rows, list):
        ctx.report.error('WDV-EDT-034', 'Inventaire des décisions de résumés historiques absent', path=lock_rel)
        return
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str):
            ctx.report.error('WDV-EDT-034', 'Entrée de résumé historique invalide', path=lock_rel)
            continue
        node_id = str(row['id'])
        if node_id in seen:
            ctx.report.error('WDV-EDT-034', 'Entrée de résumé historique dupliquée', path=lock_rel, details={'page_id': node_id})
            continue
        seen.add(node_id)
        page = argument_pages.get(node_id)
        if not page:
            continue
        tmpl = parsed_by_key.get((node_id, 'fr'))
        actual_summary = (tmpl.one('résumé') if tmpl else None) or ''
        validate_row(row, field_key=f"argument:{node_id}:summary", actual=actual_summary, path=page.get('file_path') or lock_rel)

    if receipt_changes and set(receipt_changes) != authorized_keys:
        ctx.report.error('WDV-EDT-034', 'Le reçu propriétaire couvre des champs différents de ceux déclarés authorized_change', path=receipt_path or lock_rel, details={'receipt_fields': sorted(receipt_changes), 'authorized_fields': sorted(authorized_keys)})

def _validate_fr_historical_text_preservation(
    ctx: PackageContext,
    parsed_by_key: dict[tuple[str, str], Template],
) -> None:
    """Verify the exact historical introduction/summary hashes emitted by W10.

    Historical text is preserved by default. A scoped owner authorization may
    open an exact field/value during the same French content review. The content
    lock records historical and authorized-final hashes; validation requires the
    rendered value to match the applicable decision before publication.
    """
    lock_rel = 'data/fr_content_lock.json'
    if not ctx.exists(lock_rel):
        return
    lock = ctx.load_json(lock_rel)
    if not isinstance(lock, dict):
        return
    decisions = lock.get('historical_text_decisions')
    if isinstance(decisions, dict):
        _validate_fr_historical_text_decisions_v2(ctx, parsed_by_key, lock, decisions)
        return
    preservation = lock.get('historical_text_preservation')
    if not isinstance(preservation, dict):
        return
    if preservation.get('policy') != 'preserve_preexisting_exact_v1':
        ctx.report.error('WDV-EDT-034', 'Politique de préservation des textes historiques inconnue', path=lock_rel)
        return

    manifest = ctx.manifest() or {}
    debate_page = next(
        (p for p in manifest.get('pages', []) if p.get('language') == 'fr' and p.get('page_type') == 'debate'),
        None,
    )
    debate_row = preservation.get('debate')
    if isinstance(debate_row, dict) and debate_row.get('page_origin') == 'preexisting':
        if debate_row.get('preserved') is not True:
            ctx.report.error('WDV-EDT-034', 'Introduction historique non marquée comme préservée', path=lock_rel)
        source_sha = debate_row.get('source_sha256')
        if not isinstance(source_sha, str) or not re.fullmatch('[0-9a-f]{64}', source_sha):
            ctx.report.error('WDV-EDT-034', 'Empreinte source de l’introduction historique invalide', path=lock_rel)
        elif isinstance(debate_page, dict):
            tmpl = parsed_by_key.get((debate_page.get('page_id'), 'fr'))
            actual = (tmpl.one('introduction') if tmpl else None) or ''
            actual_sha = hashlib.sha256(actual.encode('utf-8')).hexdigest()
            if actual_sha != source_sha:
                ctx.report.error(
                    'WDV-EDT-034',
                    'Introduction historique modifiée pendant la reprise de contenu',
                    path=debate_page.get('file_path') or lock_rel,
                    details={'expected_sha256': source_sha, 'actual_sha256': actual_sha},
                )

    rows = preservation.get('arguments')
    if not isinstance(rows, list):
        ctx.report.error('WDV-EDT-034', 'Inventaire des résumés historiques absent', path=lock_rel)
        return
    by_page = {
        str(p.get('page_id')): p
        for p in manifest.get('pages', [])
        if p.get('language') == 'fr' and p.get('page_type') == 'argument' and isinstance(p.get('page_id'), str)
    }
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str):
            ctx.report.error('WDV-EDT-034', 'Entrée de résumé historique invalide', path=lock_rel)
            continue
        node_id = str(row['id'])
        if node_id in seen:
            ctx.report.error('WDV-EDT-034', 'Entrée de résumé historique dupliquée', path=lock_rel, details={'page_id': node_id})
            continue
        seen.add(node_id)
        if row.get('page_origin') != 'preexisting':
            continue
        if row.get('preserved') is not True:
            ctx.report.error('WDV-EDT-034', 'Résumé historique non marqué comme préservé', path=lock_rel, details={'page_id': node_id})
        source_sha = row.get('source_sha256')
        if not isinstance(source_sha, str) or not re.fullmatch('[0-9a-f]{64}', source_sha):
            ctx.report.error('WDV-EDT-034', 'Empreinte source du résumé historique invalide', path=lock_rel, details={'page_id': node_id})
            continue
        page = by_page.get(node_id)
        if not page:
            continue
        tmpl = parsed_by_key.get((node_id, 'fr'))
        actual = (tmpl.one('résumé') if tmpl else None) or ''
        actual_sha = hashlib.sha256(actual.encode('utf-8')).hexdigest()
        if actual_sha != source_sha:
            ctx.report.error(
                'WDV-EDT-034',
                'Résumé historique modifié ou créé pendant la reprise de contenu',
                path=page.get('file_path') or lock_rel,
                details={'page_id': node_id, 'expected_sha256': source_sha, 'actual_sha256': actual_sha},
            )

def validate_aggregates(ctx: PackageContext, pages: list[dict[str, Any]]) -> None:
    pages_by_batch: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in pages:
        if p.get('page_type') == 'argument' and p.get('batch_id'):
            pages_by_batch[p['batch_id']].append(p)
    manifest = ctx.manifest() or {}
    batches = {b.get('id'): b for b in manifest.get('batches', [])}
    for bid, batch_pages in pages_by_batch.items():
        batch = batches.get(bid)
        if not batch:
            continue
        aggregate = (batch.get('outputs') or {}).get('aggregate_path')
        if not aggregate or not ctx.exists(aggregate):
            continue
        text = ctx.read_text(aggregate)
        if text is None:
            continue
        pattern = re.compile('^===== PAGE : (.+?) =====\\n', re.MULTILINE)
        matches = list(pattern.finditer(text))
        titles = [m.group(1) for m in matches]
        expected_pages = sorted(batch_pages, key=lambda p: (batch.get('node_ids') or []).index(p.get('page_id')) if p.get('page_id') in (batch.get('node_ids') or []) else 10 ** 9)
        expected_titles = [p.get('canonical_title') for p in expected_pages]
        if titles != expected_titles:
            ctx.report.error('WDV-MWK-013', f"Séparateurs de l'agrégat {bid} divergents", path=aggregate, details={'expected': expected_titles, 'actual': titles})
        for i, page in enumerate(expected_pages):
            start = matches[i].end() if i < len(matches) else None
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            if start is None:
                break
            aggregate_content = text[start:end].strip('\n') + '\n'
            individual = ctx.read_text(page.get('file_path'))
            if individual is not None and aggregate_content != individual:
                ctx.report.error('WDV-MWK-013', f"Contenu agrégé différent du fichier individuel {page.get('page_id')}", path=aggregate)
