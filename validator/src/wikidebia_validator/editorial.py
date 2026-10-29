from __future__ import annotations
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
import copy
import hashlib
import json
import re
import unicodedata
from typing import Any
from .package import PackageContext
from .historical_summary import (
    protected_historical_summary_keys as _shared_protected_historical_summary_keys,
    historically_absent_summary_keys as _shared_historically_absent_summary_keys,
    owner_removed_summary_keys as _shared_owner_removed_summary_keys,
)
from .translation import english_translation_deferred, english_translation_status, reuses_existing_english_page
from .wikicode import WikiParseError, get_subs, parse_template, _preserved_historical_french_introduction
AUTO_OBJECTION_FR = re.compile("^(?:cependant|toutefois|néanmoins|pourtant|mais|en revanche|inversement|une limite|cette limite|cet argument|l'argument)\\b", re.I)
AUTO_OBJECTION_EN = re.compile('^(?:however|nevertheless|yet|but|by contrast|conversely|one limitation|this limitation|this argument|the argument)\\b', re.I)
ACCESS_DATE = re.compile('\\b(?:consulté(?:e)?|accessed|retrieved)\\b', re.I)
PAGE_ONLY = re.compile('^(?:pages?|pp?\\.)\\s*[0-9]+(?:\\s*[-–—]\\s*[0-9]+)?$', re.I)
PAGE_VALUE = re.compile('^[0-9]+(?:-[0-9]+)?$')
ELLIPSIS = re.compile('(?:\\.\\.\\.|…|\\.\\s*\\.\\s*\\.)')
MALFORMED_FR_INITIAL = re.compile('^(?:S|E)\\s+[a-zàâçéèêëîïôûùüÿœ]', re.I)
DANGLING_FR = re.compile('\\b(?:de|du|des|à|au|aux|en|dans|par|pour|avec|sans|sur|sous|entre|et|ou|que|qui|dont|si|lorsque|comme)$', re.I)
DANGLING_EN = re.compile('\\b(?:of|to|in|on|for|with|without|by|and|or|that|which|when|as)$', re.I)
DOUBLE_WORD = re.compile("\\b([\\wÀ-ÿ'-]+)\\s+\\1\\b", re.I)
ALLOWED_KEYWORD_KINDS = {'noun', 'noun_phrase', 'proper_name', 'acronym'}
COMPLEX_QUOTES = re.compile('[«»“”„‟‹›]')
WORD_TOKEN = re.compile("[A-Za-zÀ-ÿ]+(?:[-’']+[A-Za-zÀ-ÿ]+)?")
SENTENCE_SPLIT = re.compile('(?<=[.!?])\\s+')
REF_BLOCK = re.compile('<ref\\b[^>]*>.*?</ref>|<ref\\b[^>]*/>', re.I | re.S)
WIKI_MARKUP = re.compile('\\{\\{[^{}]*\\}\\}|\\[\\[[^\\]]+\\]\\]')
NUMERIC_CLAIM = re.compile('(?<![A-Za-zÀ-ÿ0-9])(?:\\d{1,3}(?:[ \\u00a0\\u202f]\\d{3})+|\\d+)(?:[.,]\\d+)?(?:\\s*[-–—]\\s*(?:\\d{1,3}(?:[ \\u00a0\\u202f]\\d{3})+|\\d+)(?:[.,]\\d+)?)?(?:\\s*(?:%|pour\\s+cent|percent))?(?![A-Za-zÀ-ÿ0-9])', re.I)
SIMILARITY_STOPWORDS = {'fr': {'a', 'au', 'aux', 'avec', 'ce', 'ces', 'cet', 'cette', 'd', 'dans', 'de', 'des', 'du', 'elle', 'elles', 'en', 'est', 'et', 'il', 'ils', 'l', 'la', 'le', 'les', 'leur', 'leurs', 'mais', 'ne', 'ou', 'par', 'pas', 'peut', 'peuvent', 'plus', 'pour', 'que', 'qui', 'sa', 'se', 'ses', 'son', 'sont', 'sur', 'un', 'une', 'vers'}, 'en': {'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'can', 'could', 'for', 'from', 'in', 'is', 'it', 'may', 'of', 'on', 'or', 'that', 'the', 'their', 'these', 'this', 'to', 'toward', 'towards', 'with', 'would'}}
SUMMARY_SCAFFOLD_FR = re.compile("(?:plusieurs faits ou principes sont ici interprétés|cette conclusion s['’]appuie notamment sur les propositions suivantes|les faits, principes ou expériences invoqués|la thèse en tire une conséquence directe|la critique en tire une conséquence directe|le point concret est le suivant|la conséquence avancée est précise|dans le cas considéré, cela revient à dire|la proposition précise à examiner est que)", re.I)
SUMMARY_SCAFFOLD_EN = re.compile('(?:several facts or principles are interpreted here|this conclusion relies in particular on the following propositions|the facts, principles or experiences invoked|the thesis draws a direct consequence|the criticism draws a direct consequence|the concrete point is the following|the consequence advanced is precise|in the case considered, this amounts to saying)', re.I)
PRODUCTIVE_KEYWORD_FR = re.compile("^(?:limites?|histoire|construction|fiabilité|origine|sens|définition|concept|existence|preuves?|psychologie|sociologie|géographie|généalogie)\\s+(?:de|du|des|de la|de l['’])\\b", re.I)
PRODUCTIVE_KEYWORD_EN = re.compile('^(?:limits?|history|construction|reliability|origin|meaning|definition|concept|existence|evidence|psychology|sociology|geography|genealogy)\\s+(?:of|of the)\\b', re.I)
COMPOSITIONAL_KEYWORD_FR = re.compile('^(?:(?:psychologie|sociologie|histoire|géographie|généalogie)\\s+religieuse?s?|science\\s+et\\s+religion)$', re.I)
COMPOSITIONAL_KEYWORD_EN = re.compile('^(?:religious\\s+(?:psychology|sociology|history|geography|genealogy)|science\\s+and\\s+religion)$', re.I)
GENERIC_GOD_PREDETERMINERS = {'un', 'aucun', 'quelque', 'chaque', 'autre'}

def _plain_text(text: str) -> str:
    clean = REF_BLOCK.sub(' ', text or '')
    clean = WIKI_MARKUP.sub(' ', clean)
    return re.sub('\\s+', ' ', clean).strip()

def summary_first_sentence(text: str) -> str:
    clean = _plain_text(text)
    if not clean:
        return ''
    return SENTENCE_SPLIT.split(clean, maxsplit=1)[0].strip()

def _fold_token(token: str, language: str) -> str:
    folded = ''.join((c for c in unicodedata.normalize('NFKD', token.casefold()) if not unicodedata.combining(c)))
    if language == 'fr':
        if len(folded) > 5 and folded.endswith('es'):
            folded = folded[:-2]
        elif len(folded) > 4 and folded.endswith('s'):
            folded = folded[:-1]
    elif len(folded) > 5 and folded.endswith('ies'):
        folded = folded[:-3] + 'y'
    elif len(folded) > 5 and folded.endswith('ing'):
        folded = folded[:-3]
    elif len(folded) > 4 and folded.endswith('ed'):
        folded = folded[:-2]
    elif len(folded) > 4 and folded.endswith('s'):
        folded = folded[:-1]
    return folded

def _similarity_tokens(text: str, language: str) -> list[str]:
    expanded = re.sub("[-’']", ' ', _plain_text(text))
    tokens = [_fold_token(t, language) for t in WORD_TOKEN.findall(expanded)]
    stop = SIMILARITY_STOPWORDS.get(language, set())
    return [t for t in tokens if len(t) > 1 and t not in stop]

def opening_title_similarity(summary: str, titles: list[str], language: str, controls: dict[str, Any] | None=None) -> dict[str, Any]:
    """Return a cautious signal when the opening adds almost nothing to a title."""
    cfg = controls or {}
    threshold = float(cfg.get('opening_similarity_threshold', 0.84))
    max_extra = int(cfg.get('opening_max_extra_significant_words', 4))
    opening = summary_first_sentence(summary)
    opening_tokens = _similarity_tokens(opening, language)
    best: dict[str, Any] = {'issue': False, 'opening': opening, 'matched_title': '', 'sequence_similarity': 0.0, 'title_token_coverage': 0.0, 'jaccard_similarity': 0.0, 'extra_significant_words': len(opening_tokens), 'threshold': threshold, 'max_extra_significant_words': max_extra}
    if not opening_tokens:
        return best
    opening_set = set(opening_tokens)
    for title in titles:
        title_tokens = _similarity_tokens(title or '', language)
        if not title_tokens:
            continue
        title_set = set(title_tokens)
        common = opening_set & title_set
        union = opening_set | title_set
        sequence = SequenceMatcher(None, ' '.join(title_tokens), ' '.join(opening_tokens)).ratio()
        coverage = len(common) / len(title_set)
        jaccard = len(common) / len(union) if union else 0.0
        extra = sum((1 for token in opening_tokens if token not in title_set))
        exact = title_tokens == opening_tokens
        issue = exact or (coverage >= 0.8 and extra <= max_extra and (sequence >= threshold or jaccard >= max(0.72, threshold - 0.1)))
        candidate = {'issue': issue, 'opening': opening, 'matched_title': title, 'sequence_similarity': round(sequence, 3), 'title_token_coverage': round(coverage, 3), 'jaccard_similarity': round(jaccard, 3), 'extra_significant_words': extra, 'threshold': threshold, 'max_extra_significant_words': max_extra}
        if (candidate['issue'], candidate['sequence_similarity'], candidate['title_token_coverage']) > (best['issue'], best['sequence_similarity'], best['title_token_coverage']):
            best = candidate
    return best

def summary_quantitative_claims(text: str) -> list[str]:
    """Return digit-based quantitative expressions outside references and wiki markup."""
    return [m.group(0).strip() for m in NUMERIC_CLAIM.finditer(_plain_text(text))]

def summary_sentence_word_counts(text: str) -> list[int]:
    """Count lexical words per sentence after removing common inline wiki markup."""
    clean = REF_BLOCK.sub(' ', text or '')
    clean = WIKI_MARKUP.sub(' ', clean)
    sentences = [s.strip() for s in SENTENCE_SPLIT.split(clean.strip()) if s.strip()]
    return [len(WORD_TOKEN.findall(sentence)) for sentence in sentences]

def summary_style_issues(text: str, controls: dict[str, Any] | None=None) -> dict[str, Any]:
    """Return cautious readability heuristics; these signals never replace human review."""
    cfg = controls or {}
    counts = summary_sentence_word_counts(text)
    if not counts:
        return {'issues': ['empty'], 'sentence_word_counts': [], 'average_sentence_words': 0.0, 'long_sentence_ratio': 0.0}
    min_sentences = int(cfg.get('min_sentences', 3))
    long_words = int(cfg.get('long_sentence_words', 34))
    max_average = float(cfg.get('max_average_sentence_words', 28))
    max_ratio = float(cfg.get('max_long_sentence_ratio', 0.6))
    max_sentence = int(cfg.get('max_sentence_words', 50))
    average = sum(counts) / len(counts)
    ratio = sum((count >= long_words for count in counts)) / len(counts)
    issues: list[str] = []
    if len(counts) >= min_sentences and average > max_average and (ratio > max_ratio or all((count > max_average for count in counts))):
        issues.append('long_sentence_accumulation')
    if max(counts) > max_sentence:
        issues.append('very_long_sentence')
    return {'issues': issues, 'sentence_word_counts': counts, 'average_sentence_words': round(average, 2), 'long_sentence_ratio': round(ratio, 3), 'thresholds': {'min_sentences': min_sentences, 'long_sentence_words': long_words, 'max_average_sentence_words': max_average, 'max_long_sentence_ratio': max_ratio, 'max_sentence_words': max_sentence}}
DISPLAYED_TITLE_PREDICATES_FR = re.compile('\\b(?:est|sont|sera|seront|serait|seraient|peut|peuvent|pourrait|pourraient|doit|doivent|devrait|devraient|indique|indiquent|montre|montrent|prouve|prouvent|soutient|soutiennent|contredit|contredisent|suggère|suggèrent|suppose|supposent|présuppose|présupposent|implique|impliquent|explique|expliquent|révèle|révèlent|confirme|confirment|affaiblit|affaiblissent|renforce|renforcent|dépend|dépendent|existe|existent|résiste|résistent|permet|permettent|empêche|empêchent|rend|rendent|constitue|constituent|montre|montrent|justifie|justifient|conteste|contestent|nie|nient|établit|établissent|signale|signalent|favorise|favorisent|réduit|réduisent|augmente|augmentent|limite|limitent|produit|produisent|cause|causent|garantit|garantissent|suffit|suffisent|échoue|échouent|reste|restent|devient|deviennent|émerge|émergent|préexiste|préexistent|survit|survivent|persiste|persistent|varie|varient|distingue|distinguent)\\b', re.I)
FR_NONVERBAL_PRECEDERS = {'le', 'la', 'les', 'un', 'une', 'des', 'du', 'de', 'd', 'au', 'aux', 'à', 'a', 'en', 'dans', 'sur', 'sous', 'par', 'pour', 'avec', 'sans', 'entre', 'vers', 'chez', 'ce', 'cet', 'cette', 'ces', 'son', 'sa', 'ses', 'leur', 'leurs', 'notre', 'nos', 'votre', 'vos', 'mon', 'ma', 'mes', 'ton', 'ta', 'tes', 'quelques', 'plusieurs', 'certaines', 'certains', 'toutes', 'tous', 'et', 'ou', 'mais', 'ni'}
FR_COMMON_FINITE_IRREGULAR = {'attestent', 'atteste', 'apparaît', 'apparaissent', 'agissent', 'agit', 'croient', 'croit', 'disent', 'dit', 'font', 'fait', 'vont', 'va', 'vient', 'viennent', 'veut', 'veulent', 'donne', 'donnent', 'prétend', 'prétendent', 'reçoit', 'reçoivent', 'subit', 'subissent', 'utilise', 'utilisent', 'enseigne', 'enseignent', 'décrit', 'décrivent', 'attribue', 'attribuent', 'répond', 'répondent', 'appelle', 'appellent', 'demande', 'demandent', 'réactive', 'réactivent', 'accrédite', 'accréditent', 'remplit', 'remplissent', 'éveille', 'éveillent', 'provient', 'proviennent', 'concourt', 'concourent', 'pense', 'pensent', 'avance', 'avancent', 'incombe', 'incombent', 'préconise', 'préconisent', 'diffère', 'diffèrent', 'coexiste', 'coexistent', 'échappe', 'échappent', 'mélange', 'mélangent', 'motive', 'motivent', 'répond', 'répondent', 'se', 'doit', 'doivent', 'peut', 'peuvent', 'pourrait', 'pourraient', 'aurait', 'auraient', 'serait', 'seraient', 'sert', 'servent', 'vaut', 'valent', 'vit', 'vivent', 'vise', 'visent', 'commet', 'commettent'}

def _has_likely_finite_verb_fr(value: str) -> bool:
    """Conservative lexical/morphological fallback for ordinary French verbs.

    It rejects nominal labels such as « La résistance du monde à nos attentes »
    while accepting finite verbs not covered by the stable predicate list.
    """
    tokens = re.findall("[A-Za-zÀ-ÿ]+(?:['’][A-Za-zÀ-ÿ]+)?", value or '')
    lowered = [token.casefold().replace('’', "'") for token in tokens]
    for index, token in enumerate(lowered):
        previous = lowered[index - 1] if index else ''
        if token in FR_NONVERBAL_PRECEDERS or previous in FR_NONVERBAL_PRECEDERS:
            continue
        if token in FR_COMMON_FINITE_IRREGULAR:
            return True
        if re.search('(?:ent|issent|issent|ait|aient|era|eront|erait|eraient|ira|iront|irait|iraient|ît|issent|e)$', token):
            if len(token) >= 5:
                return True
    return False
DISPLAYED_TITLE_PREDICATES_EN = re.compile(r"\b(?:has|have|had|harms?|lacks?|works?|suffers?|leads?|fuels?|wastes?|subsidises?|infringes?|focuses?|understands?|amplifies?|imposes?|conflicts?|creates?|opens?|deters?|encourages?|lets?|worsens?|differs?|poses?|advocates?|legalised|regulates?|needs?|benefits?|plays?|owes?|holds?|held|faces?|performs?|aims?|prefers?|uses?|dominates?|cares?|reinforces?|loses?|lost|is|are|was|were|will|would|can|could|may|might|must|should|does|do|did|indicates?|shows?|proves?|supports?|contradicts?|suggests?|presupposes?|implies?|explains?|reveals?|confirms?|weakens?|strengthens?|depends?|exists?|resists?|allows?|prevents?|makes?|constitutes?|justifies?|challenges?|denies?|establishes?|signals?|favou?rs?|reduces?|increases?|limits?|produces?|causes?|guarantees?|suffices?|fails?|remains?|becomes?|emerges?|preexists?|survives?|persists?|varies?|distinguishes?|shapes?|happens?|arises?|undercuts?|requires?|entails?|means?|follows?|points?|rules?|excludes?|refutes?|demonstrates?)\b", re.I)
EN_RELATIVE_MARKER = re.compile(r"\b(?:that|who|which|whose)\b", re.I)
EN_AUXILIARY_OR_MODAL = {"has", "have", "had", "is", "are", "was", "were", "will", "would", "can", "cannot", "could", "may", "might", "must", "should", "does", "do", "did"}
ORDINARY_PREDICATES_EN = re.compile(
    r"\b(?:cannot|gets?|got|humiliates?|dehumanizes?|entrenches?|debated|provides?|serves?|gives?|gave|ruins?|paves?|inspires?|risks?|amounts?|draws?|enables?|deny|stems?|incites?|condemned|expressed|takes?|labels?|treats?|spreads?|manages?|benefits?|lowers?|votes?|fears?|seeks?|exploits?|comes?|caused|defends?|finds?|brings?|go|goes|went|needs?|appeals?|consider)\b", re.I,
)


def _has_main_clause_predicate_en(value: str) -> bool:
    """Conservatively require an English main-clause predicate.

    A relative clause alone does not make a displayed title propositional. This
    rejects failures such as ``Evidence that challenges the theory`` and
    ``Highly improbable events that shape history`` while retaining ordinary
    main-clause constructions such as ``Evidence that challenges the theory is
    weak`` and ``Those who believe the claim are mistaken``.
    """
    matches = sorted(
        [*DISPLAYED_TITLE_PREDICATES_EN.finditer(value or ""), *ORDINARY_PREDICATES_EN.finditer(value or "")],
        key=lambda match: match.start(),
    )
    # An infinitive within a nominal heading is not its main predicate.
    matches = [match for match in matches if not re.search(r"\bto\s+$", (value or "")[:match.start()], re.I)]
    if not matches:
        return False
    relatives = list(EN_RELATIVE_MARKER.finditer(value or ""))
    if not relatives:
        return True
    first_relative = relatives[0]
    if any(match.start() < first_relative.start() for match in matches):
        return True
    if len(matches) >= 2:
        return True
    match = matches[0]
    verb = match.group(0).casefold()
    between = re.findall(r"\b[\w'-]+\b", (value or "")[first_relative.end():match.start()])
    if verb in EN_AUXILIARY_OR_MODAL and len(between) >= 2:
        return True
    if verb in EN_AUXILIARY_OR_MODAL and re.match(r"^\s*(?:those|people|persons|anyone|everyone|someone)\s+who\b", value or "", re.I) and between:
        return True
    return False


def displayed_title_argument_issues(title: str, language: str) -> list[str]:
    """Conservative current check for obvious nominal labels (introduced in 1.2.19).

    This does not attempt full parsing. Human page-level attestations remain
    mandatory, while this check blocks the common failure mode where a title
    merely names a topic and contains no explicit predicate.
    """
    stripped = (title or '').strip()
    if not stripped:
        return ['empty']
    predicate = DISPLAYED_TITLE_PREDICATES_FR if language == 'fr' else DISPLAYED_TITLE_PREDICATES_EN
    if language == 'fr' and predicate.search(stripped):
        return []
    if language == 'en' and _has_main_clause_predicate_en(stripped):
        return []
    words = re.findall("\\b[\\wÀ-ÿ'-]+\\b", stripped)
    if language == 'fr':
        auxiliary_or_impersonal = re.search("\\b(?:n['’](?:a|ont|est|existe|y)|s['’][a-zà-ÿ]+|a|avons|ont|faut|y\\s+a|aspire|repose|relève|évolue|évoluent|correspond|sort|furent|allait|connaît|conduit|choisit|finit|impose|mérite|souffrent|force)\\b", stripped, re.I)
        if auxiliary_or_impersonal or _has_likely_finite_verb_fr(stripped):
            return []
    return ['missing_explicit_predicate']

SEMANTIC_MARKERS = {
    'attribution': (
        re.compile(r"\b(?:cens[ée]e?s?|pr[ée]tendu(?:e|es|s)?|attribu[ée]e?s?|imput[ée]e?s?|selon|d['’]apr[èe]s)\b", re.I),
        re.compile(r"\b(?:supposed|alleged|purported|attributed|ascribed|according\s+to)\b", re.I),
    ),
    'universal_quantifier': (re.compile(r"\b(?:tous|toutes|tout|chaque)\b", re.I), re.compile(r"\b(?:all|every|each)\b", re.I)),
    'existential_quantifier': (re.compile(r"\b(?:certains|certaines|quelques)\b", re.I), re.compile(r"\b(?:some|certain|a\s+few)\b", re.I)),
    'many_quantifier': (re.compile(r"\b(?:beaucoup|nombreux|nombreuses|innombrables)\b", re.I), re.compile(r"\b(?:many|numerous|countless|a\s+great\s+many|a\s+great\s+deal)\b", re.I)),
    'several_quantifier': (re.compile(r"\b(?:plusieurs|divers|diverses|diff[ée]rents|diff[ée]rentes)\b", re.I), re.compile(r"\b(?:several|multiple|various|different)\b", re.I)),
    'hypothesis_status': (re.compile(r"\b(?:hypoth[èe]se|supposition)\b", re.I), re.compile(r"\b(?:hypothesis|assumption|supposition)\b", re.I)),
    'interpretation_status': (re.compile(r"\b(?:interpr[èeé]t\w*|consid[èeé]r\w*|vu(?:e)?s?|lu(?:e)?s?)\b[^.!?]{0,80}\bcomme\b", re.I), re.compile(r"\b(?:interpreted|regarded|viewed|seen|understood|read)\s+as\b", re.I)),
    'strong_probative_force': (re.compile(r"\b(?:prouve|prouvent|d[ée]montre|d[ée]montrent|[ée]tablit|[ée]tablissent)\b", re.I), re.compile(r"\b(?:prove|proves|demonstrate|demonstrates|establish|establishes)\b", re.I)),
    'frequency_often': (re.compile(r"\bsouvent\b", re.I), re.compile(r"\b(?:often|frequently)\b", re.I)),
    'frequency_always': (re.compile(r"\b(?:toujours|de\s+tous\s+temps)\b", re.I), re.compile(r"\b(?:always|throughout\s+history|at\s+all\s+times)\b", re.I)),
    'necessity': (re.compile(r"\b(?:n[ée]cessaire|n[ée]cessairement|doit|doivent)\b", re.I), re.compile(r"\b(?:necessary|necessarily|must|has\s+to|have\s+to)\b", re.I)),
    'possibility': (re.compile(r"\b(?:peut|peuvent|pourrait|pourraient|possible|possiblement)\b", re.I), re.compile(r"\b(?:can|could|may|might|possible|possibly)\b", re.I)),
    'restriction_only': (re.compile(r"\b(?:seulement|uniquement|simplement)\b|\bne\b[^,.;:!?]{0,80}\bque\b", re.I), re.compile(r"\b(?:only|merely|simply|nothing\s+but)\b", re.I)),
    'negation': (re.compile(r"\b(?:ne|n['’])[^,.;:!?]{0,60}\b(?:pas|plus|jamais|aucun|aucune)\b|\b(?:sans|impossible)\b", re.I), re.compile(r"\b(?:not|no|never|without|impossible|cannot|can't|doesn't|don't|isn't|aren't|won't|wouldn't|couldn't)\b", re.I)),
    'condition': (re.compile(r"\b(?:si|m[êe]me\s+si|[àa]\s+condition\s+que)\b", re.I), re.compile(r"\b(?:if|even\s+if|provided\s+that|assuming\s+that)\b", re.I)),
    'causal_link': (re.compile(r"\b(?:car|parce\s+que|puisque|en\s+raison\s+de)\b", re.I), re.compile(r"\b(?:because|since|because\s+of|due\s+to)\b", re.I)),
    'consequence_link': (re.compile(r"\b(?:donc|par\s+cons[ée]quent|ce\s+qui|ainsi)\b", re.I), re.compile(r"\b(?:therefore|thus|hence|so|which)\b", re.I)),
    'concession': (re.compile(r"\b(?:m[êe]me\s+si|bien\s+que|quoique|cependant|n[ée]anmoins)\b", re.I), re.compile(r"\b(?:even\s+if|although|though|however|nevertheless)\b", re.I)),
    'comparison': (re.compile(r"\b(?:plus|moins|davantage|autant|mieux|pire)\b", re.I), re.compile(r"\b(?:more|less|fewer|greater|better|worse|as\s+much|as\s+many)\b", re.I)),
    'strong_intensity': (re.compile(r"\b(?:tr[èe]s|parfaitement|[ée]norm[ée]ment|fortement|radicalement)\b", re.I), re.compile(r"\b(?:very|perfectly|enormously|strongly|radically|far\s+more)\b", re.I)),
    'immediacy': (re.compile(r"\b(?:aussit[oô]t|imm[ée]diatement)\b", re.I), re.compile(r"\b(?:at\s+once|immediately|straightaway)\b", re.I)),
}


def semantic_marker_inventory(text: str, language: str) -> list[str]:
    index = 0 if language == 'fr' else 1
    return sorted(label for label, patterns in SEMANTIC_MARKERS.items() if patterns[index].search(text or ''))


def bilingual_semantic_marker_losses(fr_text: str, en_text: str) -> list[str]:
    """Conservative FR→EN review signals; never an automatic translation verdict."""
    fr_markers = set(semantic_marker_inventory(fr_text, 'fr'))
    en_markers = set(semantic_marker_inventory(en_text, 'en'))
    return sorted(fr_markers - en_markers)


def bilingual_title_marker_losses(fr_title: str, en_title: str) -> list[str]:
    return bilingual_semantic_marker_losses(fr_title, en_title)


# Structured FR→EN semantic-risk patterns.  These are deliberately conservative
# review signals: they never rewrite text and never constitute an automatic
# verdict of mistranslation.  They encode regression classes observed in real
# Wikidéb’IA translation audits that are not reducible to one missing keyword.
GENERIC_DEITY_FR = re.compile(r"\b(?:un|une|aucun|aucune|quelque|des)\s+dieu(?:x)?\b", re.I)
GENERIC_DEITY_EN = re.compile(r"\b(?:a|an|no|any|some)\s+god\b|\bgods\b", re.I)
PROPER_GOD_EN = re.compile(r"\bGod\b")
EPISTEMIC_INFERENCE_FR = re.compile(r"\b(?:conduit|am[eè]ne|incite)\s+[àa]\s+(?:le\s+)?consid[ée]rer|\b(?:sugg[èe]re|semble|para[iî]t)|\bpeut\s+(?:indiquer|sugg[ée]rer)\b", re.I)
EPISTEMIC_INFERENCE_EN = re.compile(r"\b(?:leads?\s+(?:us\s+)?to\s+(?:regard|consider|view)|suggests?|seems?|appears?|may\s+(?:indicate|suggest)|can\s+(?:indicate|suggest))\b", re.I)
DIRECT_CATEGORICAL_EN = re.compile(r"\b(?:is|are|makes?|proves?|shows?)\b", re.I)
ATTRIBUTED_PROPERTY_FR = re.compile(r"\b(?:attribu[ée]e?s?|imput[ée]e?s?|pr[ée]tendu(?:e|es|s)?|cens[ée]e?s?)\b", re.I)
DIRECT_GOD_PROPERTY_EN = re.compile(r"\bGod['’]s\b|\bdivine\s+[A-Za-z]", re.I)
QUANTITY_TIME_FR = re.compile(r"\bbeaucoup\s+de\s+temps\b", re.I)
SUFFICIENCY_TIME_EN = re.compile(r"\b(?:sufficient|enough)\s+time\b", re.I)
EQUIVALENCE_FR = re.compile(r"\b(?:cela|ça|ce)\s+revient\s+au\s+m[êe]me\b|\b[ée]quivaut\b", re.I)
WEAK_SAME_PROBLEM_EN = re.compile(r"\b(?:raise|raises|pose|poses)\s+the\s+same\s+problem\b", re.I)
IRRATIONAL_GOD_FR = re.compile(r"\bDieu\b[^.!?]{0,80}\b(?:objet\s+)?irrationnel\b", re.I)
IRRATIONAL_BELIEF_EN = re.compile(r"\bbelief\s+in\s+(?:God|him)\b[^.!?]{0,40}\birrational\b", re.I)
HYPOTHESIS_FR = re.compile(r"\bhypoth[èe]se\b", re.I)
HYPOTHESIS_EN = re.compile(r"\b(?:hypothesis|assumption)\b", re.I)
INTERPRETATION_FR = re.compile(r"\b(?:interpr[èeé]t\w*|consid[èeé]r\w*|vu(?:e)?s?|lu(?:e)?s?)\b[^.!?]{0,80}\bcomme\b", re.I)
INTERPRETATION_EN = re.compile(r"\b(?:interpreted|regarded|viewed|seen|understood|read)\s+as\b", re.I)
STRONG_PROOF_FR = re.compile(r"\b(?:prouve|prouvent|d[ée]montre|d[ée]montrent|[ée]tablit|[ée]tablissent)\b", re.I)
STRONG_PROOF_EN = re.compile(r"\b(?:prove|proves|demonstrate|demonstrates|establish|establishes)\b", re.I)
WEAK_PROOF_EN = re.compile(r"\b(?:support|supports|suggest|suggests|indicate|indicates|show|shows|evidence)\b", re.I)
SEVERAL_SCOPE_FR = re.compile(r"\b(?:plusieurs|divers|diverses|diff[ée]rents|diff[ée]rentes)\b", re.I)
SEVERAL_SCOPE_EN = re.compile(r"\b(?:several|multiple|various|different|many|numerous)\b", re.I)
CAUSAL_FR = re.compile(r"\b(?:car|parce\s+que|puisque)\b", re.I)
CONDITIONAL_EN = re.compile(r"\b(?:if|provided\s+that|assuming\s+that)\b", re.I)
CAUSAL_EN = re.compile(r"\b(?:because|since|as\s+a\s+result\s+of|due\s+to)\b", re.I)
EARTH_ANCHOR_FR = re.compile(r"\bsur\s+Terre\b", re.I)
EARTH_ANCHOR_EN = re.compile(r"\bon\s+Earth\b", re.I)
LIFE_EXISTENCE_FR = re.compile(r"\b(?:existence|pr[ée]sence)\s+de\s+la\s+vie\b", re.I)
LIFE_ORIGIN_EN = re.compile(r"\borigin\s+of\s+life\b", re.I)

SEMANTIC_LEXICAL_RISK_PAIRS = (
    ("unsupported_qualifier_lost", re.compile(r"\b(?:sans\s+soutien|non\s+[ée]tay[ée]e?|non\s+fond[ée]e?)\b", re.I), re.compile(r"\b(?:unsupported|unsubstantiated|unfounded)\b", re.I)),
    ("inherent_qualifier_lost", re.compile(r"\bintrins[èe]quement\b", re.I), re.compile(r"\binherently\b", re.I)),
    ("collective_scope_lost", re.compile(r"\bcollectivement\b", re.I), re.compile(r"\bcollectively\b", re.I)),
    ("religious_diversity_qualifier_lost", re.compile(r"\bdiversit[ée]\s+religieuse\b", re.I), re.compile(r"\breligious\s+diversity\b", re.I)),
    ("living_conditions_qualifier_lost", re.compile(r"\bconditions\s+de\s+vie\b", re.I), re.compile(r"\bliving\s+conditions\b", re.I)),
    ("sensationalism_qualifier_lost", re.compile(r"\bsensationnalisme\b", re.I), re.compile(r"\bsensationalism\b", re.I)),
    ("inexplicable_weakened_to_unexplained", re.compile(r"\binexplicable\b", re.I), re.compile(r"\binexplicable\b", re.I)),
    ("invariants_concept_lost", re.compile(r"\binvariants?\b", re.I), re.compile(r"\binvariants?\b", re.I)),
    ("arriere_monde_mistranslated", re.compile(r"\barri[èe]re-monde\b", re.I), re.compile(r"\b(?:otherworld|world\s+beyond|transcendent\s+world|metaphysical\s+world)\b", re.I)),
    ("reglage_mistranslated_as_tuner", re.compile(r"\br[ée]glage\b", re.I), re.compile(r"\b(?:adjustment|setting|fine-tuning|tuning)\b", re.I)),
    ("tordre_mistranslated_as_reinterpreting", re.compile(r"\btord(?:re|u|ue|ent)\b", re.I), re.compile(r"\b(?:distort|twist|warp|bend)\w*\b", re.I)),
)


def bilingual_semantic_structure_signals(fr_text: str, en_text: str) -> list[str]:
    """Return structured semantic-risk signals for human bilingual review.

    The function intentionally detects only asymmetric patterns with a strong
    chance of changing scope or logical force.  It is a review aid, not an
    automatic translation judge.
    """
    fr = fr_text or ''
    en = en_text or ''
    signals: list[str] = []
    if GENERIC_DEITY_FR.search(fr) and PROPER_GOD_EN.search(en) and not GENERIC_DEITY_EN.search(en):
        signals.append('generic_deity_to_proper_God')
    if ATTRIBUTED_PROPERTY_FR.search(fr) and DIRECT_GOD_PROPERTY_EN.search(en) and not SEMANTIC_MARKERS['attribution'][1].search(en):
        signals.append('attributed_property_to_direct_property')
    if EPISTEMIC_INFERENCE_FR.search(fr) and DIRECT_CATEGORICAL_EN.search(en) and not EPISTEMIC_INFERENCE_EN.search(en):
        signals.append('epistemic_inference_to_categorical_assertion')
    if QUANTITY_TIME_FR.search(fr) and SUFFICIENCY_TIME_EN.search(en):
        signals.append('quantity_to_sufficiency')
    if EQUIVALENCE_FR.search(fr) and WEAK_SAME_PROBLEM_EN.search(en):
        signals.append('equivalence_weakened_to_same_problem')
    if IRRATIONAL_GOD_FR.search(fr) and IRRATIONAL_BELIEF_EN.search(en):
        signals.append('predicate_subject_shift_God_to_belief')
    if HYPOTHESIS_FR.search(fr) and not HYPOTHESIS_EN.search(en):
        signals.append('hypothesis_status_lost')
    if INTERPRETATION_FR.search(fr) and not INTERPRETATION_EN.search(en):
        signals.append('interpretation_status_lost')
    if STRONG_PROOF_FR.search(fr) and WEAK_PROOF_EN.search(en) and not STRONG_PROOF_EN.search(en):
        signals.append('probative_force_weakened')
    if SEVERAL_SCOPE_FR.search(fr) and not SEVERAL_SCOPE_EN.search(en):
        signals.append('plural_or_several_scope_lost')
    if CAUSAL_FR.search(fr) and CONDITIONAL_EN.search(en) and not CAUSAL_EN.search(en):
        signals.append('causal_relation_shifted_to_condition')
    if EARTH_ANCHOR_FR.search(fr) and not EARTH_ANCHOR_EN.search(en):
        signals.append('earth_scope_anchor_lost')
    if LIFE_EXISTENCE_FR.search(fr) and LIFE_ORIGIN_EN.search(en):
        signals.append('life_existence_shifted_to_origin')
    for label, fr_pattern, en_pattern in SEMANTIC_LEXICAL_RISK_PAIRS:
        if fr_pattern.search(fr) and not en_pattern.search(en):
            signals.append(label)
    return sorted(set(signals))


def displayed_title_translation_form_regression(fr_title: str, en_title: str) -> list[str]:
    """Block only clear formal degradation introduced by FR→EN translation."""
    fr_issues = displayed_title_argument_issues(fr_title, 'fr')
    en_issues = displayed_title_argument_issues(en_title, 'en')
    if not fr_issues and en_issues:
        return ['source_proposition_target_nonproposition', *en_issues]
    return []


def displayed_title_issues(title: str, language: str) -> list[str]:
    """Return stable reason labels for malformed or truncated displayed titles."""
    value = title or ''
    issues: list[str] = []
    if value != value.strip():
        issues.append('surrounding_whitespace')
    stripped = value.strip()
    if not stripped:
        return ['empty']
    if ELLIPSIS.search(stripped):
        issues.append('ellipsis')
    if COMPLEX_QUOTES.search(stripped):
        issues.append('complex_quotes')
    if stripped.count('"') % 2:
        issues.append('unbalanced_quotes')
    if len(stripped) < 12:
        issues.append('too_short')
    first_alpha = next((c for c in stripped if c.isalpha()), '')
    if first_alpha and (not first_alpha.isupper()):
        issues.append('lowercase_initial')
    if language == 'fr' and MALFORMED_FR_INITIAL.search(stripped):
        issues.append('malformed_article')
    dangling = DANGLING_FR if language == 'fr' else DANGLING_EN
    stranded_relative = language == 'en' and re.search(
        r"\b(?:those|people|politicians|persons)\s+(?:whom\s+)?(?:the\s+public|we|they|voters)\s+(?:wanted?|wants?)\s+to\s+get\s+rid\s+of$", stripped, re.I,
    )
    begin_with = language == 'en' and re.search(r'\bbegin\s+with$', stripped, re.I)
    if dangling.search(stripped) and not (stranded_relative or begin_with):
        issues.append('dangling_connector')
    if DOUBLE_WORD.search(stripped):
        issues.append('doubled_word')
    return issues

def summary_word_ratio(fr_text: str, en_text: str) -> float:
    fr_words = re.findall("\\b[\\wÀ-ÿ'-]+\\b", fr_text or '')
    en_words = re.findall("\\b[\\w'-]+\\b", en_text or '')
    return len(en_words) / len(fr_words) if fr_words else 0.0

def keyword_capitalization_issues(keyword: str, kind: str) -> list[str]:
    value = str(keyword or '')
    first = next((char for char in value if char.isalpha()), '')
    if kind in {'noun', 'noun_phrase'} and first and first.isupper():
        return ['common_keyword_initial_uppercase']
    if kind == 'acronym':
        letters = [char for char in value if char.isalpha()]
        if not letters or any((char.islower() for char in letters)):
            return ['acronym_not_uppercase']
    return []

def keyword_form_issues(
    keywords: list[str],
    *,
    enforce_count: bool = True,
    allowed_long_keywords: set[str] | None = None,
) -> list[str]:
    issues: list[str] = []
    allowed_long_keywords = allowed_long_keywords or set()
    if enforce_count and not 2 <= len(keywords) <= 4:
        issues.append('count')
    if len(keywords) != len(set(keywords)):
        issues.append('duplicates')
    for keyword in keywords:
        if not isinstance(keyword, str) or not keyword.strip():
            issues.append('empty')
            continue
        if keyword != keyword.strip():
            issues.append('surrounding_whitespace')
        if ELLIPSIS.search(keyword):
            issues.append('ellipsis')
        if len(keyword) > 40:
            issues.append('too_long')
        # A long lexicalized concept is permitted when the controlled
        # vocabulary carries the explicit atomic/multiword attestation.
        if len(WORD_TOKEN.findall(keyword)) > 4 and keyword not in allowed_long_keywords:
            issues.append('too_many_words')
    return sorted(set(issues))

def keyword_atomicity_issues(keyword: str, entry: dict[str, Any] | None, language: str | None=None, *, require_composition_attestation: bool=False) -> list[str]:
    """Apply semantic atomicity rules to one controlled keyword."""
    value = str(keyword or '').strip()
    data = entry or {}
    issues: list[str] = []
    tokens = WORD_TOKEN.findall(value)
    lang = language or ('en' if re.search('\\b(?:of|and|the)\\b', value, re.I) else 'fr')
    has_connector = bool(re.search('\\b(?:de|du|des|la|le|et|of|and|the)\\b', value, re.I) or re.search("\\bd[’']", value, re.I))
    productive = PRODUCTIVE_KEYWORD_EN if lang == 'en' else PRODUCTIVE_KEYWORD_FR
    compositional = COMPOSITIONAL_KEYWORD_EN if lang == 'en' else COMPOSITIONAL_KEYWORD_FR
    if data.get('atomic_concept') is not True:
        issues.append('atomic_concept_not_attested')
    rationale = str(data.get('multiword_exception_rationale') or '').strip()
    semantic_markers = (
        'locution', 'catégorie', 'concept', 'nom propre', "type d'argument", 'type d’argument',
        'lexicalized', 'lexicalised', 'atomic category', 'proper name', 'argument type',
    )
    justified_productive_exception = bool(
        data.get('atomic_concept') is True
        and data.get('compositional_intersection') is False
        and data.get('multiword_exception') is True
        and len(rationale) >= 20
        and any(marker in rationale.casefold() for marker in semantic_markers)
    )
    if productive.search(value) and not justified_productive_exception:
        issues.append('productive_thematic_phrase')
    if compositional.search(value):
        issues.append('compositional_intersection')
    if require_composition_attestation and data.get('compositional_intersection') is not False:
        issues.append('compositional_intersection_not_rejected')
    requires_exception = len(tokens) > 2 or has_connector
    if requires_exception:
        if data.get('multiword_exception') is not True:
            issues.append('multiword_exception_missing')
        if len(rationale) < 20:
            issues.append('multiword_exception_rationale')
        elif require_composition_attestation and not any(marker in rationale.casefold() for marker in semantic_markers):
            issues.append('multiword_exception_rationale_not_semantic')
    elif data.get('multiword_exception') is True:
        issues.append('unnecessary_multiword_exception')
    return sorted(set(issues))

def summary_template_issues(text: str, language: str) -> list[str]:
    plain = _plain_text(text)
    marker = SUMMARY_SCAFFOLD_FR if language == 'fr' else SUMMARY_SCAFFOLD_EN
    issues: list[str] = []
    if marker.search(plain):
        issues.append('generic_scaffolding')
    return issues

def normalized_summary_sentences(text: str, language: str) -> list[str]:
    plain = _plain_text(text)
    values: list[str] = []
    for sentence in SENTENCE_SPLIT.split(plain):
        tokens = [_fold_token(token, language) for token in WORD_TOKEN.findall(sentence)]
        if len(tokens) >= 8:
            values.append(' '.join(tokens))
    return values

def lowercase_god_issues(text: str) -> list[str]:
    issues: list[str] = []
    for match in re.finditer('(?<![A-Za-zÀ-ÿ])dieu(?![A-Za-zÀ-ÿ])', _plain_text(text)):
        prefix = _plain_text(text)[:match.start()]
        previous_match = re.search("([A-Za-zÀ-ÿ’'-]+)\\s*$", prefix)
        previous = previous_match.group(1).casefold() if previous_match else ''
        generic = previous in GENERIC_GOD_PREDETERMINERS or prefix.casefold().endswith("n'importe quel ")
        if not generic:
            issues.append('lowercase_proper_name')
    return issues

def _active(ctx: PackageContext) -> bool:
    """Editorial validation is cumulative and independent of norm revision."""
    return True

def summary_has_auto_objection(text: str, language: str) -> bool:
    sentences = [s.strip() for s in re.split('(?<=[.!?])\\s+', text.strip()) if s.strip()]
    if not sentences:
        return True
    final = sentences[-1]
    marker = AUTO_OBJECTION_FR if language == 'fr' else AUTO_OBJECTION_EN
    return bool(marker.search(final))

def title_copy_ratio(nodes: list[dict[str, Any]], language: str) -> float:
    vals = []
    for node in nodes:
        data = node.get(language) or {}
        canonical = (data.get('canonical_title') or '').strip().casefold()
        displayed = (data.get('displayed_title') or '').strip().casefold()
        if canonical:
            vals.append(canonical == displayed)
    return sum(vals) / len(vals) if vals else 1.0

def displayed_title_concision_issues(canonical_title: str, displayed_title: str) -> list[str]:
    """Return current concision failures for one title pair (rule introduced in 1.2.22)."""
    canonical = (canonical_title or '').strip()
    displayed = (displayed_title or '').strip()
    if not canonical or not displayed:
        return []
    issues: list[str] = []
    if canonical.casefold() == displayed.casefold():
        issues.append('exact_copy')
    canonical_words = WORD_TOKEN.findall(canonical)
    displayed_words = WORD_TOKEN.findall(displayed)
    if len(canonical_words) >= 8 and len(displayed_words) > len(canonical_words):
        issues.append('displayed_longer_than_canonical')
    return issues

def dominant_classification_ratio(nodes: list[dict[str, Any]], language: str) -> float:
    key = 'rubriques' if language == 'fr' else 'sections'
    combos = [tuple((node.get(language) or {}).get(key) or []) for node in nodes]
    if not combos:
        return 1.0
    return Counter(combos).most_common(1)[0][1] / len(combos)

def _parse_page(ctx: PackageContext, rel: str):
    text = ctx.read_text(rel)
    if text is None:
        return None
    try:
        return parse_template(text)
    except WikiParseError:
        return None

def _summary(tmpl, lang: str) -> str:
    return tmpl.one('résumé' if lang == 'fr' else 'summary') or ''

def _validate_documentary_registry(ctx: PackageContext) -> tuple[int, int]:
    sources = ctx.sources() or {}
    pagination_errors = 0
    date_errors = 0
    for source in sources.get('sources', []):
        metadata = source.get('metadata') or {}
        location = metadata.get('location')
        page = metadata.get('page')
        if source.get('type') == 'bibliography':
            if isinstance(location, str) and PAGE_ONLY.fullmatch(location.strip()):
                pagination_errors += 1
                ctx.report.error('WDV-DOC-002', 'Pagination bibliographique encore placée dans location/localisation', path=ctx.core_paths()['sources'], details={'source_id': source.get('id'), 'value': location})
            if page is not None and (not PAGE_VALUE.fullmatch(str(page))):
                pagination_errors += 1
                ctx.report.error('WDV-DOC-002', 'Valeur page bibliographique non normalisée', path=ctx.core_paths()['sources'], details={'source_id': source.get('id'), 'value': page})
        date = metadata.get('date')
        if isinstance(date, str) and ACCESS_DATE.search(date):
            date_errors += 1
            ctx.report.error('WDV-DOC-003', 'Date de simple consultation conservée comme date documentaire', path=ctx.core_paths()['sources'], details={'source_id': source.get('id'), 'value': date})
        if isinstance(date, str) and re.fullmatch('\\d{4}-\\d{2}(?:-\\d{2})?(?:[T ].*)?', date.strip()):
            date_errors += 1
            ctx.report.error('WDV-DOC-005', 'Date documentaire au format machine dans le registre des sources', path=ctx.core_paths()['sources'], details={'source_id': source.get('id'), 'value': date})
        if source.get('type') in {'webliography', 'videography'}:
            verification = source.get('verification') or {}
            site = str(metadata.get('site') or '').strip().casefold()
            page_or_title = str(metadata.get('page') or metadata.get('title') or '').strip().casefold()
            authors = [str(value).strip().casefold() for value in metadata.get('authors') or [] if str(value).strip()]
            if verification.get('authorship_checked') is not True:
                ctx.report.error('WDV-DOC-004', 'La responsabilité d’auteur d’une source Web ou vidéo doit avoir été vérifiée', path=ctx.core_paths()['sources'], details={'source_id': source.get('id'), 'source_type': source.get('type')})
            if authors and verification.get('authorship_verified') is not True:
                ctx.report.error('WDV-DOC-004', 'Un auteur renseigné pour une source Web ou vidéo doit être explicitement vérifié', path=ctx.core_paths()['sources'], details={'source_id': source.get('id')})
            if site and page_or_title and (site == page_or_title):
                ctx.report.error('WDV-DOC-004', 'Le titre ou la page du registre documentaire duplique le nom du site et doit être omis', path=ctx.core_paths()['sources'], details={'source_id': source.get('id'), 'value': metadata.get('site'), 'source_type': source.get('type')})
            if site and site in authors:
                ctx.report.error('WDV-DOC-004', 'Un auteur du registre reproduit le nom du site : une seconde recherche d’attribution est obligatoire et le champ doit être omis si aucun auteur distinct n’est identifié', path=ctx.core_paths()['sources'], details={'source_id': source.get('id'), 'value': metadata.get('site'), 'source_type': source.get('type'), 'authorship_rechecked_after_site_match': verification.get('authorship_rechecked_after_site_match')})
    # 1.2.57: one canonical link/DOI must not claim incompatible identity
    # metadata within a language. Missing optional metadata is not a conflict, and
    # page/location locators may legitimately differ between citations of one work.
    def _norm_identity_text(value: Any) -> str:
        text = str(value or '').strip().casefold().replace('’', "'").replace('“', '"').replace('”', '"')
        return re.sub(r'\s+', ' ', text)

    by_resource: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for source in sources.get('sources', []):
        metadata = source.get('metadata') or {}
        locator = str(metadata.get('doi') or metadata.get('link') or source.get('doi') or source.get('link') or '').strip()
        if not locator:
            continue
        language = str(source.get('language') or metadata.get('language') or '').strip().casefold()
        by_resource.setdefault((language, locator), []).append(source)
    identity_fields = ('article', 'work', 'title', 'date', 'publisher', 'site')
    for (language, locator), rows in by_resource.items():
        if len(rows) < 2:
            continue
        conflicts: dict[str, list[str]] = {}
        for field in identity_fields:
            values = sorted({_norm_identity_text((row.get('metadata') or {}).get(field)) for row in rows if _norm_identity_text((row.get('metadata') or {}).get(field))})
            if len(values) > 1:
                conflicts[field] = values
        author_values = set()
        for row in rows:
            authors = (row.get('metadata') or {}).get('authors') or []
            if isinstance(authors, str):
                authors = [authors]
            normalized = tuple(_norm_identity_text(a) for a in authors if _norm_identity_text(a))
            if normalized:
                author_values.add(normalized)
        if len(author_values) > 1:
            conflicts['authors'] = ['; '.join(value) for value in sorted(author_values)]
        if conflicts:
            ctx.report.error('WDV-DOC-009', 'Une même URL/DOI est décrite avec des métadonnées d’identité incompatibles dans la même langue', path=ctx.core_paths()['sources'], details={'language': language, 'locator': locator, 'source_ids': [str(r.get('id') or '') for r in rows], 'conflicts': conflicts})
    return (pagination_errors, date_errors)

def _historically_absent_debate_introduction(ctx: PackageContext) -> bool:
    if not ctx.exists('data/fr_content_lock.json'):
        return False
    lock = ctx.load_json('data/fr_content_lock.json')
    decisions = lock.get('historical_text_decisions') if isinstance(lock, dict) else None
    row = decisions.get('debate') if isinstance(decisions, dict) else None
    legacy_absence = bool(
        isinstance(row, dict)
        and row.get('page_origin') == 'preexisting'
        and row.get('historical_status') == 'historical_absent'
        and row.get('decision') == 'preserved'
    )
    if legacy_absence:
        return True
    debate = lock.get('debate') if isinstance(lock, dict) else None
    return bool(
        isinstance(debate, dict)
        and debate.get('page_origin') == 'preexisting'
        and debate.get('historical_introduction_present') is False
        and debate.get('historical_text_decision') == 'preserved'
    )


def _validate_debate_docs(ctx: PackageContext, manifest: dict[str, Any], controls: dict[str, Any], norm: str | None=None) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    cfg = controls.get('debate_documentation') or {}
    min_subsections = int(cfg.get('min_subsections', 1))
    min_references = int(cfg.get('min_references', 0))
    reject_singleton = cfg.get('reject_singleton_bucket_pattern') is True
    profile_rationale = cfg.get('profile_rationale')
    documentation_policy_1242 = True
    video_authorship_policy_1242 = True
    if not isinstance(profile_rationale, str) or not profile_rationale.strip():
        ctx.report.error('WDV-EDT-004', 'Justification des minima documentaires locaux absente', path='manifest.json')
    debate_pages = [p for p in manifest.get('pages', []) if p.get('page_type') == 'debate']
    doc_params = {'fr': ['bibliographie-pour', 'bibliographie-contre', 'bibliographie-ni-pour-ni-contre', 'sitographie-pour', 'sitographie-contre', 'sitographie-ni-pour-ni-contre', 'vidéographie-pour', 'vidéographie-contre', 'vidéographie-ni-pour-ni-contre'], 'en': ['pro-bibliography', 'con-bibliography', 'bibliography', 'pro-webliography', 'con-webliography', 'webliography', 'pro-videography', 'con-videography', 'videography']}
    for page in debate_pages:
        lang = page.get('language')
        tmpl = _parse_page(ctx, page.get('file_path'))
        if not tmpl:
            continue
        from .source_preservation import preserved_french_page
        exact_french = lang == 'fr' and preserved_french_page(ctx, page, ctx.read_text(page['file_path']) or '')
        intro_count = len(get_subs(tmpl, 'introduction'))
        bucket_templates = [get_subs(tmpl, param) for param in doc_params[lang]]
        counts = [len(items) for items in bucket_templates]
        distinct_counts = [len({re.sub('\\s+', ' ', item.raw).strip().casefold() for item in items}) for items in bucket_templates]
        total = sum(counts)
        metrics[lang] = {'introduction_subsections': intro_count, 'documentary_references': total, 'bucket_counts': counts, 'distinct_bucket_counts': distinct_counts, 'profile_minima': {'subsections': min_subsections, 'references': min_references}, 'profile_rationale': profile_rationale}
        historical_absent_introduction = (
            _historically_absent_debate_introduction(ctx)
            or (exact_french and intro_count == 0)
        )
        effective_min_subsections = 0 if historical_absent_introduction else min_subsections
        metrics[lang]['profile_minima']['subsections'] = effective_min_subsections
        if intro_count < effective_min_subsections or total < min_references:
            ctx.report.error('WDV-EDT-004', 'Page de débat insuffisamment développée ou documentée selon le profil déclaré', path=page.get('file_path'), details=metrics[lang])
        if not documentation_policy_1242:
            insufficient = {param: {'total': count, 'distinct': distinct} for param, count, distinct in zip(doc_params[lang], counts, distinct_counts) if distinct < 2}
            if insufficient:
                ctx.report.error('WDV-EDT-004', 'Chaque paramètre documentaire de la page de débat doit contenir au moins deux références distinctes', path=page.get('file_path'), details={'minimum_distinct_per_bucket': 2, 'insufficient_buckets': insufficient, 'bucket_counts': dict(zip(doc_params[lang], counts)), 'distinct_bucket_counts': dict(zip(doc_params[lang], distinct_counts))})
        if documentation_policy_1242:
            source_orientations: dict[str, set[str]] = defaultdict(set)
            source_locations: dict[str, list[str]] = defaultdict(list)
            for param, items in zip(doc_params[lang], bucket_templates):
                if lang == 'fr':
                    orientation = 'pro' if param.endswith('-pour') else 'con' if param.endswith('-contre') else 'neutral'
                else:
                    orientation = 'pro' if param.startswith('pro-') else 'con' if param.startswith('con-') else 'neutral'
                for item in items:
                    link = (item.one('lien') or item.one('link') or '').strip()
                    title = (item.one('ouvrage') or item.one('work') or item.one('page') or item.one('titre') or item.one('title') or '').strip()
                    authors = (item.one('auteurs') or item.one('authors') or '').strip()
                    identity = re.sub('\\s+', ' ', link or f'{title}|{authors}').strip().casefold()
                    if not identity:
                        identity = re.sub('\\s+', ' ', re.sub('Référence (?:bibliographique|sitographique|vidéographique)(?: pour| contre)?', 'Référence', item.raw, count=1)).strip().casefold()
                    source_orientations[identity].add(orientation)
                    source_locations[identity].append(param)
            duplicates = {identity: {'orientations': sorted(source_orientations[identity]), 'parameters': source_locations[identity]} for identity in source_orientations if len(source_orientations[identity]) > 1}
            if duplicates:
                ctx.report.error('WDV-EDT-004', 'Une même référence documentaire est classée dans plusieurs orientations; une source couvrant plusieurs positions doit être placée dans la rubrique neutre', path=page.get('file_path'), details={'duplicate_count': len(duplicates), 'duplicates': dict(list(duplicates.items())[:25])})
        if video_authorship_policy_1242 and not exact_french:
            video_missing_authors = []
            for param, items in zip(doc_params[lang][6:9], bucket_templates[6:9]):
                for item in items:
                    link = (item.one('lien') or item.one('link') or '').strip()
                    authors = (item.one('auteurs') or item.one('authors') or '').strip()
                    if re.search('(?:youtube\\.com|youtu\\.be)', link, re.I) and (not authors):
                        video_missing_authors.append({'parameter': param, 'title': item.one('titre') or item.one('title'), 'link': link})
            if video_missing_authors:
                ctx.report.error('WDV-DOC-004', 'Une référence vidéo YouTube de la page de débat ne précise pas le créateur ou la chaîne affichée par la plateforme', path=page.get('file_path'), details={'missing_count': len(video_missing_authors), 'references': video_missing_authors})
        nonzero = [x for x in counts if x]
        if reject_singleton and nonzero and (len(nonzero) >= 6) and (len(set(nonzero)) == 1) and (nonzero[0] == 1):
            ctx.report.error('WDV-EDT-004', "Documentation répartie selon le motif mécanique d'une référence par rubrique", path=page.get('file_path'), details={'bucket_counts': counts})
    return metrics

def _validate_dates(ctx: PackageContext, manifest: dict[str, Any], expected: str | None, policy: str='per_page_preserved') -> int:
    """Validate immutable creation dates.

    ``single_active_date`` preserves the historical behaviour for newly produced
    homogeneous corpora. ``per_page_preserved`` is intended for imported or
    resumed corpora whose pages legitimately have different creation dates: the
    page manifest becomes the page-level source of truth and must agree with the
    canonical wikicode and the registry.
    """
    errors = 0
    if policy not in {'single_active_date', 'per_page_preserved'}:
        ctx.report.error('WDV-EDT-005', 'Politique de date de création inconnue', path='manifest.json', details={'policy': policy})
        return 1
    if policy == 'single_active_date' and (not expected):
        ctx.report.error('WDV-EDT-005', 'Date active attendue absente du profil de contrôle du paquet', path='manifest.json')
        return 1
    registry = ctx.registry() or {}
    debate_id = (registry.get('debate') or {}).get('id')
    nodes = {str(n.get('id')): n for n in (registry.get('graph') or {}).get('nodes') or []}
    for page in manifest.get('pages', []):
        page_date = page.get('creation_date')
        page_expected = page_date if policy == 'per_page_preserved' else expected
        if not isinstance(page_expected, str) or not re.fullmatch('\\d{4}-\\d{2}-\\d{2}', page_expected):
            errors += 1
            ctx.report.error('WDV-EDT-005', 'Date de création de page absente ou mal formée', path='manifest.json', details={'page_id': page.get('page_id'), 'language': page.get('language'), 'actual': page_date})
            continue
        if policy == 'single_active_date' and page_date != page_expected:
            errors += 1
            ctx.report.error('WDV-EDT-005', 'Date active divergente dans le manifeste de page', path='manifest.json', details={'page_id': page.get('page_id'), 'language': page.get('language'), 'expected': page_expected, 'actual': page_date})
        tmpl = _parse_page(ctx, page.get('file_path'))
        date_parameter = 'date-création' if page.get('language') == 'fr' else 'creation-date'
        preserved = (page.get('preserved_parameters') or {}).get(date_parameter) if page.get('page_origin') == 'preexisting' else None
        historical_date_absent = policy == 'per_page_preserved' and isinstance(preserved, dict) and (preserved.get('present') is False)
        if tmpl:
            actual_date = tmpl.one(date_parameter)
            if historical_date_absent:
                if actual_date is not None:
                    errors += 1
                    ctx.report.error('WDV-EDT-005', 'Date de création historiquement absente mais ajoutée dans le wikicode canonique', path=page.get('file_path'), details={'actual': actual_date})
            elif actual_date != page_expected:
                errors += 1
                ctx.report.error('WDV-EDT-005', 'Date de création divergente dans le wikicode canonique', path=page.get('file_path'), details={'expected': page_expected, 'actual': actual_date})
        page_id = str(page.get('page_id') or '')
        if page_id == str(debate_id):
            registry_page = ((registry.get('debate') or {}).get('pages') or {}).get(page.get('language')) or {}
        else:
            registry_page = ((nodes.get(page_id) or {}).get('pages') or {}).get(page.get('language')) or {}
        registry_date = (registry_page.get('generation') or {}).get('creation_date')
        if registry_date != page_expected:
            errors += 1
            ctx.report.error('WDV-EDT-005', 'Date de création divergente dans le registre', path=ctx.core_paths().get('registry'), details={'page_id': page_id, 'language': page.get('language'), 'expected': page_expected, 'actual': registry_date})
        if page.get('language') == 'fr':
            canonical = Path(page.get('file_path', ''))
            try:
                suffix = canonical.relative_to(Path('output/fr'))
            except ValueError:
                continue
            staging = (Path('staging/interlanguage/fr') / suffix).as_posix()
            st = _parse_page(ctx, staging)
            if st:
                actual_staging_date = st.one('date-création')
                if historical_date_absent:
                    if actual_staging_date is not None:
                        errors += 1
                        ctx.report.error('WDV-EDT-005', 'Date de création historiquement absente mais ajoutée dans le staging français', path=staging, details={'actual': actual_staging_date})
                elif actual_staging_date != page_expected:
                    errors += 1
                    ctx.report.error('WDV-EDT-005', 'Date de création divergente dans le staging français', path=staging, details={'expected': page_expected, 'actual': actual_staging_date})
    return errors

def _validate_traceability(ctx: PackageContext, manifest: dict[str, Any], editorial_controls: dict[str, Any], trace_controls: dict[str, Any]) -> dict[str, Any]:
    required_reports = editorial_controls.get('required_reports') or []
    missing_reports = [p for p in required_reports if not ctx.exists(p)]
    if missing_reports:
        ctx.report.error('WDV-EDT-006', 'Rapports déclarés obligatoires absents', details={'paths': missing_reports})
    handoff_paths = trace_controls.get('required_corrective_handoffs') or []
    missing_handoffs = [p for p in handoff_paths if not ctx.exists(p)]
    if missing_handoffs:
        ctx.report.error('WDV-EDT-006', 'Handoffs correctifs déclarés absents', details={'paths': missing_handoffs})
    checked = 0
    for rel in handoff_paths:
        data = ctx.load_json(rel) if ctx.exists(rel) else None
        if not isinstance(data, dict):
            continue
        checked += 1
        if data.get('remote_operations_performed') is not False:
            ctx.report.error('WDV-EDT-006', "Un handoff correctif n'atteste pas l'absence d'opération distante", path=rel)
        if data.get('debate_id') != manifest.get('debate_id'):
            ctx.report.error('WDV-EDT-006', 'Handoff correctif rattaché à un autre débat', path=rel)
    gate = manifest.get('publication_gate') or {}
    if trace_controls.get('remote_write_must_be_false') is True and gate.get('remote_write_authorized') is not False:
        ctx.report.error('WDV-EDT-006', 'Le paquet autorise à tort une écriture distante', path='manifest.json')
    return {'reports_missing': missing_reports, 'handoffs_declared': len(handoff_paths), 'handoffs_checked': checked, 'handoffs_missing': missing_handoffs, 'remote_write_authorized': gate.get('remote_write_authorized')}

def _load_keyword_vocabulary(ctx: PackageContext, controls: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    rel = controls.get('keyword_vocabulary_path')
    data = ctx.load_json(rel) if isinstance(rel, str) and ctx.exists(rel) else None
    if not isinstance(data, dict):
        return ({}, {})
    entries = data.get('entries') or []
    by_fr: dict[str, dict[str, Any]] = {}
    by_en: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        fr = entry.get('fr')
        en = entry.get('en')
        if isinstance(fr, str):
            by_fr[fr] = entry
        if isinstance(en, str):
            by_en[en] = entry
    return (by_fr, by_en)

def _validate_intro_references(ctx: PackageContext, manifest: dict[str, Any], controls: dict[str, Any]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    cfg = controls.get('introduction_references') or {}
    if cfg.get('required') is not True:
        ctx.report.error('WDV-EDT-010', 'Contrôle des appels inline des introductions non activé', path='manifest.json')
    min_subsections = int(cfg.get('min_subsections', 1))
    typed_fr = {'référence bibliographique', 'référence bibliographique pour', 'référence bibliographique contre', 'référence sitographique', 'référence sitographique pour', 'référence sitographique contre', 'référence vidéographique', 'référence vidéographique pour', 'référence vidéographique contre'}
    typed_en = {'bibliographical reference', 'pro bibliographical reference', 'con bibliographical reference', 'web reference', 'pro web reference', 'con web reference', 'video reference', 'pro video reference', 'con video reference'}
    ref_pair_re = re.compile('<ref\\b(?P<attrs>[^>/]*?)>(?P<body>.*?)</ref\\s*>', flags=re.I | re.S)
    ref_self_re = re.compile('<ref\\b(?P<attrs>[^>]*)/\\s*>', flags=re.I | re.S)
    name_re = re.compile('\\bname\\s*=\\s*(?:\\"([^\\"]+)\\"|\'([^\']+)\'|([^\\s>]+))', flags=re.I)
    template_re = re.compile('\\{\\{\\s*([^|}\\n]+)', flags=re.I)
    machine_date_re = re.compile('(?<!\\d)\\d{4}-\\d{2}(?:-\\d{2})?(?:[T ][0-9:.+Z-]+)?(?!\\d)')
    punctuation_policy = True
    intro_review_rel = controls.get('introduction_review_path')
    intro_review = ctx.load_json(intro_review_rel) if punctuation_policy and isinstance(intro_review_rel, str) and ctx.exists(intro_review_rel) else {}
    review_by_lang = {entry.get('language'): entry for entry in intro_review.get('entries') or [] if isinstance(entry, dict)} if isinstance(intro_review, dict) else {}
    for page in [p for p in manifest.get('pages', []) if p.get('page_type') == 'debate']:
        lang = page.get('language')
        tmpl = _parse_page(ctx, page.get('file_path'))
        if not tmpl:
            continue
        intro = tmpl.one('introduction') or ''
        blocks = [s.one('contenu' if lang == 'fr' else 'content') or '' for s in get_subs(tmpl, 'introduction')]
        invalid = []
        invalid_models: list[dict[str, Any]] = []
        invalid_direct_notes: list[dict[str, Any]] = []
        machine_dates: list[dict[str, Any]] = []
        terminal_period_notes: list[dict[str, Any]] = []
        unmatched_sentence_exceptions: list[str] = []
        defined_names: set[str] = set()
        referenced_names: list[tuple[int, str]] = []
        expected_model = 'Référence' if lang == 'fr' else 'Reference'
        typed_models = typed_fr if lang == 'fr' else typed_en
        for index, block in enumerate(blocks):
            has_inline = bool(re.search('<ref\\b', block, flags=re.I))
            has_references_tag = bool(re.search('<references\\b', block, flags=re.I))
            if has_references_tag:
                invalid.append(index + 1)
            for match in ref_pair_re.finditer(block):
                body = match.group('body').strip()
                attrs = match.group('attrs') or ''
                named = name_re.search(attrs)
                if named:
                    defined_names.add(next((group for group in named.groups() if group is not None)))
                if punctuation_policy and body.endswith('.'):
                    body_sha = hashlib.sha256(body.encode('utf-8')).hexdigest()
                    review_entry = review_by_lang.get(lang) or {}
                    exceptions = review_entry.get('terminal_period_sentence_exceptions') if isinstance(review_entry, dict) else []
                    match_exception = next((item for item in exceptions or [] if isinstance(item, dict) and item.get('body_sha256') == body_sha and (item.get('complete_sentence') is True) and isinstance(item.get('sentence_evidence'), str) and (item.get('sentence_evidence').strip() in body)), None)
                    if match_exception is None:
                        terminal_period_notes.append({'subsection': index + 1, 'body_sha256': body_sha, 'body_excerpt': body[:180]})
                templates = [m.group(1).strip() for m in template_re.finditer(body)]
                if templates:
                    invalid_direct_notes.append({'subsection': index + 1, 'reason': 'mediawiki_template_forbidden', 'templates': templates})
                if not body:
                    invalid_direct_notes.append({'subsection': index + 1, 'reason': 'empty_reference_body'})
                body_without_urls = re.sub(r'https?://[^\s<>\]]+', ' ', body, flags=re.I)
                for dm in machine_date_re.finditer(body_without_urls):
                    machine_dates.append({'subsection': index + 1, 'value': dm.group(0)})
            for match in ref_self_re.finditer(block):
                named = name_re.search(match.group('attrs') or '')
                if named:
                    referenced_names.append((index + 1, next((group for group in named.groups() if group is not None))))
                else:
                    invalid_direct_notes.append({'subsection': index + 1, 'reason': 'self_closing_unnamed_reference'})
        missing_named = [{'subsection': idx, 'name': name} for idx, name in referenced_names if name not in defined_names]
        ref_calls = len(re.findall('<ref\\b', intro, flags=re.I))
        claim_driven_policy = True
        metrics[lang] = {'subsections': len(blocks), 'ref_calls': ref_calls, 'references_blocks': len(re.findall('<references\\b', intro, flags=re.I)), 'invalid_subsections': invalid, 'minimum': min_subsections, 'claim_driven_policy': claim_driven_policy, 'expected_inline_reference_model': None, 'inline_reference_body_mode': 'direct_wikicode_without_templates', 'invalid_inline_reference_models': invalid_models, 'invalid_direct_reference_notes': invalid_direct_notes, 'undefined_named_references': missing_named, 'machine_documentary_dates': machine_dates, 'terminal_period_reference_notes': terminal_period_notes, 'punctuation_policy_revision': '1.2.44' if punctuation_policy else None}
        minimum_failure = not claim_driven_policy and len(blocks) < min_subsections
        preserved_historical_fr = bool(lang == 'fr' and _preserved_historical_french_introduction(ctx))
        if preserved_historical_fr:
            metrics[lang]['historical_preservation_exception'] = True
            if invalid or invalid_direct_notes or missing_named or machine_dates or terminal_period_notes:
                ctx.report.info(
                    'WDV-EDT-010',
                    'Contrôles de création des références inline non appliqués rétroactivement à une introduction française historique préservée',
                    path=page.get('file_path'),
                    details=metrics[lang],
                )
            continue
        if minimum_failure or invalid:
            if claim_driven_policy:
                message = 'Balise <references /> présente dans l’introduction'
            else:
                message = 'Appels de référence inline absents ou bloc <references /> mal placé dans l’introduction'
            ctx.report.error('WDV-EDT-010', message, path=page.get('file_path'), details=metrics[lang])
        if invalid_direct_notes or missing_named:
            ctx.report.error('WDV-EDT-010', 'Les appels inline de l’introduction doivent contenir une référence rédigée directement, sans modèle MediaWiki', path=page.get('file_path'), details=metrics[lang])
        if machine_dates:
            ctx.report.error('WDV-DOC-005', 'Date documentaire au format machine dans un appel de référence inline', path=page.get('file_path'), details={'dates': machine_dates, 'creation_date_parameters_unchanged': ['date-création', 'creation-date']})
        if punctuation_policy and terminal_period_notes:
            ctx.report.error('WDV-DOC-008', 'Une simple notice de référence ne doit pas se terminer par un point avant </ref>; toute exception doit être une phrase complète attestée', path=page.get('file_path'), details={'notes': terminal_period_notes, 'review_path': intro_review_rel})
    return metrics
INTRO_REVIEW_TRUE_FIELDS = ('subject_and_scope_defined', 'debate_question_explained', 'history_and_evolution_addressed', 'current_state_addressed_or_not_applicable', 'stakes_explained', 'factual_claims_referenced', 'progression_coherent', 'no_argument_tree_mirroring', 'no_topic_specific_checklist')

def _normalized_wikipedia_article(value: Any) -> str:
    return re.sub('[_\\s]+', ' ', str(value or '')).strip().casefold()

def _normalized_visible_text(value: Any) -> str:
    text = str(value or '').replace('’', "'")
    text = re.sub('\\s+', ' ', text).strip().casefold()
    return text

def _wikipedia_hover_entries(content: str, lang: str) -> list[dict[str, str]]:
    model = 'Lien\\s+Wikipédia' if lang == 'fr' else 'Wikipedia\\s+link'
    display_key = 'texte-affiché' if lang == 'fr' else 'displayed-text'
    pattern = re.compile('\\{\\{\\s*' + model + '\\s*\\|(?P<body>.*?)\\}\\}', re.I | re.S)
    entries: list[dict[str, str]] = []
    for match in pattern.finditer(content or ''):
        body = match.group('body')
        params: dict[str, str] = {}
        for chunk in body.split('|'):
            if '=' in chunk:
                key, value = chunk.split('=', 1)
                params[key.strip().casefold()] = value.strip()
        article = params.get('article', '')
        display = params.get(display_key.casefold()) or article
        if article:
            entries.append({'article': _normalized_wikipedia_article(article), 'display': _normalized_visible_text(display)})
    return entries

def _wikipedia_hover_articles(content: str, lang: str) -> set[str]:
    """Article inventory retained for backward-compatible review-file parsing."""
    return {entry['article'] for entry in _wikipedia_hover_entries(content, lang)}

def _visible_subsection_text(content: str, lang: str) -> str:
    text = content or ''
    entries = _wikipedia_hover_entries(text, lang)
    model = 'Lien\\s+Wikipédia' if lang == 'fr' else 'Wikipedia\\s+link'
    display_key = 'texte-affiché' if lang == 'fr' else 'displayed-text'
    pattern = re.compile('\\{\\{\\s*' + model + '\\s*\\|(?P<body>.*?)\\}\\}', re.I | re.S)

    def repl(match: re.Match[str]) -> str:
        params: dict[str, str] = {}
        for chunk in match.group('body').split('|'):
            if '=' in chunk:
                k, v = chunk.split('=', 1)
                params[k.strip().casefold()] = v.strip()
        return params.get(display_key.casefold()) or params.get('article', '')
    text = pattern.sub(repl, text)
    text = re.sub('<ref(?:\\s[^>]*)?>.*?</ref>|<ref(?:\\s[^>]*)?\\s*/>', ' ', text, flags=re.I | re.S)
    text = re.sub('\\{\\{.*?\\}\\}', ' ', text, flags=re.S)
    return _normalized_visible_text(text)

def validate_introduction_review_data(review: Any, actual_titles: dict[str, list[str]], norm: str | None=None, complete_topics: dict[str, str] | None=None, topics: dict[str, str] | None=None, introduction_policy_revision: str | None=None, inline_reference_punctuation_policy_revision: str | None=None, wikipedia_link_consistency_policy_revision: str | None=None, specialized_term_explanation_policy_revision: str | None=None, actual_contents: dict[str, dict[str, str]] | None=None, translation_semantic_review_schema_version: str='1.0') -> list[dict[str, Any]]:
    """Return stable inconsistencies in the bilingual introduction-review ledger."""
    issues: list[dict[str, Any]] = []
    if not isinstance(review, dict):
        return [{'reason': 'missing_or_invalid_document'}]
    entries = review.get('entries')
    if not isinstance(entries, list):
        return issues + [{'reason': 'missing_entries'}]
    by_lang: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get('language') not in {'fr', 'en'}:
            issues.append({'reason': 'invalid_entry'})
            continue
        lang = entry['language']
        if lang in by_lang:
            issues.append({'reason': 'duplicate_language', 'language': lang})
            continue
        by_lang[lang] = entry
    for lang, titles in actual_titles.items():
        entry = by_lang.get(lang)
        if not entry:
            issues.append({'reason': 'missing_language', 'language': lang})
            continue
        historical_status = str(entry.get('status') or '')
        historical_translation = lang == 'en' and str(entry.get('source_page_origin') or '') == 'preexisting'
        if historical_translation:
            # A newly created English target may translate a historically human
            # French source. Creation-profile requirements (notably the mandatory
            # Stakes subsection) do not become applicable merely because the
            # target page is technically new. The translation remains an
            # autonomous, documented international adaptation.
            for field in (
                'historical_source_profile_respected',
                'france_specific_context_reviewed',
                'international_context_adaptation_reviewed',
                'no_unjustified_substantive_addition',
                'english_documentation_localized',
                'canonical_title_semantic_inventory_reviewed',
                'topic_semantic_equivalence_reviewed',
                'complete_topic_semantic_equivalence_reviewed',
                'introduction_claim_inventory_reviewed',
                'subsection_structure_equivalence_reviewed',
            ):
                if entry.get(field) is not True:
                    issues.append({'reason': 'historical_translation_attestation_false_or_missing', 'language': lang, 'field': field})
            # Source provenance changes the creation profile, not the intrinsic
            # quality bar for the English page. Documentation, inline citations,
            # hover links and specialized-term review remain mandatory.
            for field in (
                'factual_claims_referenced',
                'documentation_proportionate_to_literature',
                'wikipedia_hover_links_reviewed',
                'specialized_terms_linked_or_explained',
                'documentation_orientation_reviewed',
                'youtube_authorship_reviewed',
                'reference_note_punctuation_reviewed',
                'specialized_term_inventory_reviewed',
            ):
                if entry.get(field) is not True:
                    issues.append({'reason': 'historical_translation_intrinsic_quality_missing', 'language': lang, 'field': field})
            if len(str(entry.get('introduction_adaptation_rationale') or '').strip()) < 30:
                issues.append({'reason': 'historical_translation_adaptation_rationale', 'language': lang})
            if len(str(entry.get('canonical_title_semantic_inventory_note') or '').strip()) < 20:
                issues.append({'reason': 'canonical_title_semantic_inventory_note', 'language': lang})
            if len(str(entry.get('introduction_claim_inventory_note') or '').strip()) < 30:
                issues.append({'reason': 'introduction_claim_inventory_note', 'language': lang})
            family_notes = entry.get('documentation_family_notes')
            aggregate_families = {'bibliography', 'webliography', 'videography'}
            oriented_families = {
                'pro-bibliography', 'con-bibliography', 'bibliography',
                'pro-webliography', 'con-webliography', 'webliography',
                'pro-videography', 'con-videography', 'videography',
            }
            note_keys = set(family_notes) if isinstance(family_notes, dict) else set()
            if not isinstance(family_notes, dict) or not (note_keys == aggregate_families or note_keys == oriented_families):
                issues.append({'reason': 'documentation_family_notes', 'language': lang})
            else:
                for family, note in family_notes.items():
                    if not isinstance(note, str) or len(note.strip()) < 20:
                        issues.append({'reason': 'documentation_family_note', 'language': lang, 'family': family})
            rows = entry.get('subsections')
            if not isinstance(rows, list):
                issues.append({'reason': 'missing_subsections', 'language': lang})
            else:
                ledger_titles = [row.get('title') for row in rows if isinstance(row, dict)]
                if ledger_titles != titles:
                    issues.append({'reason': 'subsection_titles_mismatch', 'language': lang, 'expected': titles, 'actual': ledger_titles})
            inventory = entry.get('specialized_term_inventory')
            if inventory is not None:
                if not isinstance(inventory, list):
                    issues.append({'reason': 'specialized_term_inventory_missing', 'language': lang})
                else:
                    inv_titles = [str(row.get('subsection_title') or '').strip() for row in inventory if isinstance(row, dict)]
                    if inv_titles and (inv_titles != titles or len(inv_titles) != len(inventory)):
                        issues.append({'reason': 'specialized_term_inventory_subsections_mismatch', 'language': lang, 'expected': titles, 'actual': inv_titles})
            continue
        if historical_status in {'historical_existing', 'historical_absent', 'historical_authorized_change'}:
            # Historical introductions are protected by default.  A scoped
            # owner-authorized correction remains exempt from retroactive
            # creation-style requirements; the v2 historical-text lock checks
            # the authorization chain and exact final hash.
            authorized = historical_status == 'historical_authorized_change'
            if authorized:
                if entry.get('owner_authorized_change') is not True:
                    issues.append({'reason': 'historical_introduction_authorization_missing', 'language': lang})
                final_sha = entry.get('authorized_final_sha256')
                if not isinstance(final_sha, str) or not re.fullmatch('[0-9a-f]{64}', final_sha):
                    issues.append({'reason': 'historical_introduction_final_sha256', 'language': lang})
                if not isinstance(entry.get('authorization'), dict):
                    issues.append({'reason': 'historical_introduction_authorization_missing', 'language': lang})
            elif entry.get('historical_content_preserved') is not True:
                issues.append({'reason': 'historical_introduction_not_preserved', 'language': lang})
            source_sha = entry.get('historical_source_sha256')
            if not isinstance(source_sha, str) or not re.fullmatch('[0-9a-f]{64}', source_sha):
                issues.append({'reason': 'historical_introduction_source_sha256', 'language': lang})
            if historical_status == 'historical_absent' and entry.get('historical_absence_verified') is not True:
                issues.append({'reason': 'historical_introduction_absence_unverified', 'language': lang})
            if len(str(entry.get('note') or '').strip()) < 12:
                issues.append({'reason': 'historical_introduction_note', 'language': lang})
            # For an unchanged historical introduction the content lock is
            # authoritative.  Older review ledgers may contain a proposed
            # rewrite that was never owner-authorized; those stale subsection
            # rows must not requalify the preserved source as newly generated.
            # A genuinely owner-authorized change still has to describe the
            # selected final structure.
            if authorized:
                rows = entry.get('subsections')
                if not isinstance(rows, list):
                    issues.append({'reason': 'missing_subsections', 'language': lang})
                else:
                    ledger_titles = [row.get('title') for row in rows if isinstance(row, dict)]
                    if ledger_titles != titles:
                        issues.append({'reason': 'subsection_titles_mismatch', 'language': lang, 'expected': titles, 'actual': ledger_titles})
            continue
        # Current introduction requirements are cumulative. Historical policy
        # revision fields are accepted as trace metadata but never activate rules.
        policy_1243 = True
        policy_1244 = True
        policy_1245 = True
        policy_1246 = True
        required_intro_fields = INTRO_REVIEW_TRUE_FIELDS + ('information_density_reviewed', 'subsections_non_redundant', 'no_generic_stakes_filler', 'documentation_orientation_reviewed', 'youtube_authorship_reviewed', 'dedicated_stakes_subsection_present', 'stakes_consequences_concrete', 'stakes_not_argument_catalogue')
        if translation_semantic_review_schema_version in {'1.1', '1.2', '1.3', '1.4'} and lang == 'en':
            required_intro_fields += ('canonical_title_semantic_inventory_reviewed', 'topic_semantic_equivalence_reviewed', 'complete_topic_semantic_equivalence_reviewed', 'introduction_claim_inventory_reviewed', 'subsection_structure_equivalence_reviewed')
        for field in required_intro_fields:
            if entry.get(field) is not True:
                issues.append({'reason': 'attestation_false_or_missing', 'language': lang, 'field': field})
        if translation_semantic_review_schema_version in {'1.1', '1.2', '1.3', '1.4'} and lang == 'en':
            if len(str(entry.get('canonical_title_semantic_inventory_note') or '').strip()) < 20:
                issues.append({'reason': 'canonical_title_semantic_inventory_note', 'language': lang})
            if len(str(entry.get('introduction_claim_inventory_note') or '').strip()) < 30:
                issues.append({'reason': 'introduction_claim_inventory_note', 'language': lang})
        for field in ('complete_topic_fits_heading', 'debate_sections_precise', 'documentation_proportionate_to_literature'):
            if entry.get(field) is not True:
                issues.append({'reason': field, 'language': lang})
        family_notes = entry.get('documentation_family_notes')
        expected_families = {'bibliography', 'webliography', 'videography'}
        if not isinstance(family_notes, dict) or set(family_notes) != expected_families:
            issues.append({'reason': 'documentation_family_notes', 'language': lang})
        else:
            for family, note in family_notes.items():
                if not isinstance(note, str) or len(note.strip()) < 20:
                    issues.append({'reason': 'documentation_family_note', 'language': lang, 'family': family})
        for field in ('wikipedia_hover_links_reviewed', 'specialized_terms_linked_or_explained'):
            if entry.get(field) is not True:
                issues.append({'reason': field, 'language': lang})
        acronym = entry.get('common_acronym')
        if acronym is not None and (not isinstance(acronym, str) or not acronym.strip()):
            issues.append({'reason': 'invalid_common_acronym', 'language': lang})
        if entry.get('common_acronym_used_or_not_applicable') is not True:
            issues.append({'reason': 'common_acronym_attestation', 'language': lang})
        if isinstance(acronym, str) and acronym.strip() and (complete_topics is not None):
            complete = complete_topics.get(lang, '')
            if not re.search(f'(?<![\\w.-]){re.escape(acronym.strip())}(?![\\w.-])', complete):
                issues.append({'reason': 'common_acronym_missing_from_complete_topic', 'language': lang, 'acronym': acronym.strip(), 'complete_topic': complete})
        for field in ('topic_is_nominal_label', 'conventional_topic_label_used_or_not_applicable', 'complete_topic_lowercase_initial_or_justified'):
            if entry.get(field) is not True:
                issues.append({'reason': field, 'language': lang})
        rationale = entry.get('topic_label_rationale')
        if not isinstance(rationale, str) or len(rationale.strip()) < 12:
            issues.append({'reason': 'topic_label_rationale', 'language': lang})
        complete = (complete_topics or {}).get(lang, '')
        first_alpha = next((char for char in complete.strip() if char.isalpha()), '')
        if first_alpha and first_alpha.isupper():
            justification = entry.get('complete_topic_initial_capital_justification')
            if not isinstance(justification, str) or len(justification.strip()) < 12:
                issues.append({'reason': 'complete_topic_initial_capital_justification', 'language': lang, 'complete_topic': complete})
        topic = (topics or {}).get(lang, '')
        if not topic.strip():
            issues.append({'reason': 'missing_topic', 'language': lang})
        if policy_1243:
            expected_stakes_title = 'Enjeux du débat' if lang == 'fr' else 'Stakes of the debate'
            normalized_titles = [re.sub('\\s+', ' ', str(title or '')).strip().casefold() for title in titles]
            if expected_stakes_title.casefold() not in normalized_titles:
                issues.append({'reason': 'missing_dedicated_stakes_subsection', 'language': lang, 'expected_title': expected_stakes_title})
            elif actual_contents is not None:
                contents = actual_contents.get(lang) or {}
                stakes_content = next((value for title, value in contents.items() if re.sub('\\s+', ' ', str(title)).strip().casefold() == expected_stakes_title.casefold()), '')
                plain_stakes = re.sub('<ref(?:\\s[^>]*)?>.*?</ref>|<ref(?:\\s[^>]*)?\\s*/>', ' ', stakes_content, flags=re.I | re.S)
                plain_stakes = re.sub('\\{\\{.*?\\}\\}', ' ', plain_stakes, flags=re.S)
                words = re.findall('[A-Za-zÀ-ÿ0-9]+', plain_stakes)
                sentences = [part for part in re.split('(?<=[.!?])\\s+', plain_stakes.strip()) if part.strip()]
                if len(words) < 45 or len(sentences) < 3:
                    issues.append({'reason': 'stakes_subsection_too_thin', 'language': lang, 'word_count': len(words), 'sentence_count': len(sentences)})
        if policy_1244:
            if entry.get('reference_note_punctuation_reviewed') is not True:
                issues.append({'reason': 'reference_note_punctuation_review_missing', 'language': lang})
            exceptions = entry.get('terminal_period_sentence_exceptions')
            if not isinstance(exceptions, list):
                issues.append({'reason': 'terminal_period_sentence_exceptions_missing', 'language': lang})
            else:
                seen_exception_hashes: set[str] = set()
                for exception in exceptions:
                    if not isinstance(exception, dict):
                        issues.append({'reason': 'invalid_terminal_period_sentence_exception', 'language': lang})
                        continue
                    body_sha = exception.get('body_sha256')
                    evidence = exception.get('sentence_evidence')
                    if not isinstance(body_sha, str) or not re.fullmatch('[0-9a-f]{64}', body_sha) or body_sha in seen_exception_hashes or (exception.get('complete_sentence') is not True) or (not isinstance(evidence, str)) or (len(evidence.strip()) < 12):
                        issues.append({'reason': 'invalid_terminal_period_sentence_exception', 'language': lang, 'body_sha256': body_sha})
                    else:
                        seen_exception_hashes.add(body_sha)
        rows = entry.get('subsections')
        if not isinstance(rows, list):
            issues.append({'reason': 'missing_subsections', 'language': lang})
            continue
        ledger_titles = [row.get('title') for row in rows if isinstance(row, dict)]
        if ledger_titles != titles:
            issues.append({'reason': 'subsection_titles_mismatch', 'language': lang, 'expected': titles, 'actual': ledger_titles})
        if policy_1243:
            expected_stakes_title = 'Enjeux du débat' if lang == 'fr' else 'Stakes of the debate'
            stakes_rows = [row for row in rows if isinstance(row, dict) and re.sub('\\s+', ' ', str(row.get('title') or '')).strip().casefold() == expected_stakes_title.casefold()]
            if len(stakes_rows) != 1:
                issues.append({'reason': 'stakes_review_row_count', 'language': lang, 'count': len(stakes_rows)})
            else:
                stakes_row = stakes_rows[0]
                if stakes_row.get('stakes_section') is not True:
                    issues.append({'reason': 'stakes_section_attestation', 'language': lang})
                concrete = stakes_row.get('concrete_stakes')
                if not isinstance(concrete, list) or len(concrete) < 2:
                    issues.append({'reason': 'concrete_stakes_missing', 'language': lang})
                else:
                    cleaned = [str(value).strip() for value in concrete if isinstance(value, str) and str(value).strip()]
                    if len(cleaned) != len(concrete) or len({value.casefold() for value in cleaned}) != len(cleaned) or any((len(value) < 20 for value in cleaned)):
                        issues.append({'reason': 'invalid_concrete_stakes', 'language': lang})
        if policy_1246:
            if entry.get('specialized_term_inventory_reviewed') is not True:
                issues.append({'reason': 'specialized_term_inventory_review_missing', 'language': lang})
            inventory = entry.get('specialized_term_inventory')
            if not isinstance(inventory, list):
                issues.append({'reason': 'specialized_term_inventory_missing', 'language': lang})
            else:
                inv_titles = [str(row.get('subsection_title') or '').strip() for row in inventory if isinstance(row, dict)]
                if inv_titles != titles or len(inv_titles) != len(inventory):
                    issues.append({'reason': 'specialized_term_inventory_subsections_mismatch', 'language': lang, 'expected': titles, 'actual': inv_titles})
                contents = actual_contents.get(lang, {}) if isinstance(actual_contents, dict) else {}
                ledger_by_title = {str(row.get('title') or '').strip(): row for row in rows if isinstance(row, dict)}
                prior: dict[tuple[str, str], str] = {}
                for inv_index, inv in enumerate(inventory, start=1):
                    if not isinstance(inv, dict):
                        issues.append({'reason': 'invalid_specialized_term_inventory_entry', 'language': lang, 'index': inv_index})
                        continue
                    title = str(inv.get('subsection_title') or '').strip()
                    terms = inv.get('terms')
                    scan_note = str(inv.get('scan_note') or '').strip()
                    if title not in contents:
                        issues.append({'reason': 'specialized_term_inventory_subsection_missing', 'language': lang, 'index': inv_index, 'subsection_title': title})
                        continue
                    if inv.get('scan_complete') is not True or len(scan_note) < 30:
                        issues.append({'reason': 'specialized_term_scan_incomplete', 'language': lang, 'subsection_title': title})
                    if not isinstance(terms, list):
                        issues.append({'reason': 'specialized_term_list_invalid', 'language': lang, 'subsection_title': title})
                        continue
                    if (ledger_by_title.get(title) or {}).get('technical_or_specialized') is True and (not terms):
                        issues.append({'reason': 'technical_subsection_inventory_empty', 'language': lang, 'subsection_title': title})
                    visible = _visible_subsection_text(contents[title], lang)
                    hover = _wikipedia_hover_entries(contents[title], lang)
                    declared_hover: set[tuple[str, str]] = set()
                    seen: set[str] = set()
                    for term_index, row in enumerate(terms, start=1):
                        if not isinstance(row, dict):
                            issues.append({'reason': 'invalid_specialized_term_entry', 'language': lang, 'subsection_title': title, 'term': term_index})
                            continue
                        term = str(row.get('term') or '').strip()
                        norm_term = _normalized_visible_text(term)
                        treatment = row.get('treatment')
                        if not term or norm_term in seen or treatment not in {'wikipedia_link', 'explained_inline', 'prior_treatment', 'context_sufficient'}:
                            issues.append({'reason': 'invalid_specialized_term_entry', 'language': lang, 'subsection_title': title, 'term': term_index})
                            continue
                        seen.add(norm_term)
                        if norm_term not in visible:
                            issues.append({'reason': 'specialized_term_not_in_subsection', 'language': lang, 'subsection_title': title, 'term': term})
                        if treatment == 'wikipedia_link':
                            article = str(row.get('article') or '').strip()
                            key = (_normalized_wikipedia_article(article), norm_term)
                            if not article or key not in {(x['article'], x['display']) for x in hover}:
                                issues.append({'reason': 'specialized_term_declared_link_missing', 'language': lang, 'subsection_title': title, 'term': term, 'article': article})
                            else:
                                declared_hover.add(key)
                                prior[title, norm_term] = 'wikipedia_link'
                        elif treatment == 'explained_inline':
                            excerpt = str(row.get('explanation_excerpt') or '').strip()
                            if len(excerpt) < 20 or _normalized_visible_text(excerpt) not in visible:
                                issues.append({'reason': 'specialized_term_inline_explanation_missing', 'language': lang, 'subsection_title': title, 'term': term})
                            else:
                                prior[title, norm_term] = 'explained_inline'
                        elif treatment == 'prior_treatment':
                            prior_title = str(row.get('prior_subsection_title') or '').strip()
                            prior_term = _normalized_visible_text(row.get('prior_term'))
                            if prior_title not in titles[:max(0, inv_index - 1)] or prior.get((prior_title, prior_term)) not in {'wikipedia_link', 'explained_inline'}:
                                issues.append({'reason': 'specialized_term_prior_treatment_invalid', 'language': lang, 'subsection_title': title, 'term': term, 'prior_subsection_title': prior_title, 'prior_term': row.get('prior_term')})
                        elif treatment == 'context_sufficient':
                            justification = str(row.get('justification') or '').strip()
                            if len(justification) < 30:
                                issues.append({'reason': 'specialized_term_context_justification_missing', 'language': lang, 'subsection_title': title, 'term': term})
                    actual_hover = {(x['article'], x['display']) for x in hover}
                    for article, display in sorted(actual_hover - declared_hover):
                        issues.append({'reason': 'undeclared_wikipedia_hover_link', 'language': lang, 'subsection_title': title, 'article': article, 'display': display})
        if policy_1245 and (not policy_1246):
            if entry.get('wikipedia_link_consistency_reviewed') is not True:
                issues.append({'reason': 'wikipedia_link_consistency_review_missing', 'language': lang})
            groups = entry.get('wikipedia_link_groups')
            if not isinstance(groups, list):
                issues.append({'reason': 'wikipedia_link_groups_missing', 'language': lang})
            else:
                contents = actual_contents.get(lang, {}) if isinstance(actual_contents, dict) else {}
                for group_index, group in enumerate(groups, start=1):
                    if not isinstance(group, dict):
                        issues.append({'reason': 'invalid_wikipedia_link_group', 'language': lang, 'group': group_index})
                        continue
                    subsection_title = str(group.get('subsection_title') or '').strip()
                    rationale = str(group.get('rationale') or '').strip()
                    terms = group.get('terms')
                    if not subsection_title or subsection_title not in contents:
                        issues.append({'reason': 'wikipedia_link_group_subsection_missing', 'language': lang, 'group': group_index, 'subsection_title': subsection_title})
                        continue
                    if len(rationale) < 20:
                        issues.append({'reason': 'wikipedia_link_group_rationale_missing', 'language': lang, 'group': group_index})
                    if not isinstance(terms, list) or len(terms) < 2:
                        issues.append({'reason': 'wikipedia_link_group_terms_invalid', 'language': lang, 'group': group_index})
                        continue
                    present_articles = _wikipedia_hover_articles(contents[subsection_title], lang)
                    seen_terms: set[str] = set()
                    for term_index, term_row in enumerate(terms, start=1):
                        if not isinstance(term_row, dict):
                            issues.append({'reason': 'invalid_wikipedia_link_term', 'language': lang, 'group': group_index, 'term': term_index})
                            continue
                        term = str(term_row.get('term') or '').strip()
                        article = str(term_row.get('article') or '').strip()
                        linked = term_row.get('linked')
                        if not term or term.casefold() in seen_terms or linked not in {True, False}:
                            issues.append({'reason': 'invalid_wikipedia_link_term', 'language': lang, 'group': group_index, 'term': term_index})
                            continue
                        seen_terms.add(term.casefold())
                        if linked is True:
                            if not article or _normalized_wikipedia_article(article) not in present_articles:
                                issues.append({'reason': 'declared_wikipedia_link_missing', 'language': lang, 'group': group_index, 'term': term, 'article': article})
                        else:
                            justification = str(term_row.get('justification') or '').strip()
                            if len(justification) < 20:
                                issues.append({'reason': 'unlinked_peer_term_unjustified', 'language': lang, 'group': group_index, 'term': term})
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                issues.append({'reason': 'invalid_subsection_entry', 'language': lang, 'index': index})
                continue
            if not isinstance(row.get('purpose'), str) or not row['purpose'].strip():
                issues.append({'reason': 'missing_purpose', 'language': lang, 'index': index})
            if row.get('necessary_for_understanding') is not True:
                issues.append({'reason': 'subsection_not_attested_as_necessary', 'language': lang, 'index': index})
            if row.get('technical_or_specialized') is True and row.get('relevance_to_debate_explained') is not True:
                issues.append({'reason': 'technical_relevance_not_explained', 'language': lang, 'index': index})
    extra = sorted(set(by_lang) - set(actual_titles))
    for lang in extra:
        issues.append({'reason': 'unexpected_language', 'language': lang})
    return issues

def _validate_introduction_review(ctx: PackageContext, manifest: dict[str, Any], controls: dict[str, Any], norm: str | None) -> dict[str, Any]:
    rel = controls.get('introduction_review_path')
    if not isinstance(rel, str) or not rel:
        ctx.report.error('WDV-EDT-017', 'Registre bilingue de revue des introductions absent', path='manifest.json')
        return {'path': rel, 'issues': [{'reason': 'missing_path'}]}
    review = ctx.load_json(rel) if ctx.exists(rel) else None
    if isinstance(review, dict) and isinstance(review.get('entries'), list) and _preserved_historical_french_introduction(ctx):
        # The FR content lock is authoritative for historical provenance.
        # Legacy introduction_review ledgers may predate the preservation
        # contract and can contain an unselected proposed rewrite.  Annotate a
        # copy for differential validation without mutating the package.
        review = copy.deepcopy(review)
        fr_entry = next((row for row in review.get('entries') or [] if isinstance(row, dict) and row.get('language') == 'fr'), None)
        if isinstance(fr_entry, dict) and ctx.exists('data/fr_content_lock.json'):
            fr_lock = ctx.load_json('data/fr_content_lock.json')
            debate_lock = fr_lock.get('debate') if isinstance(fr_lock, dict) else None
            historical_intro = debate_lock.get('introduction') if isinstance(debate_lock, dict) else None
            if isinstance(historical_intro, str) and historical_intro.strip():
                fr_entry['status'] = 'historical_existing'
                fr_entry['historical_content_preserved'] = True
                fr_entry['historical_source_sha256'] = hashlib.sha256(historical_intro.encode('utf-8')).hexdigest()
                fr_entry.setdefault('note', 'Introduction française historique préservée ; les propositions de réécriture antérieures ne sont pas la valeur éditoriale sélectionnée.')
    if english_translation_deferred(manifest) and isinstance(review, dict) and isinstance(review.get('entries'), list):
        review = dict(review)
        review['entries'] = [entry for entry in review['entries'] if isinstance(entry, dict) and entry.get('language') == 'fr']
    actual_titles: dict[str, list[str]] = {}
    actual_contents: dict[str, dict[str, str]] = {}
    complete_topics: dict[str, str] = {}
    topics: dict[str, str] = {}
    for page in [p for p in manifest.get('pages', []) if p.get('page_type') == 'debate']:
        lang = page.get('language')
        tmpl = _parse_page(ctx, page.get('file_path'))
        if lang not in {'fr', 'en'} or not tmpl:
            continue
        key = 'titre' if lang == 'fr' else 'title'
        complete_key = 'sujet-développé' if lang == 'fr' else 'expanded-topic'
        topic_key = 'sujet' if lang == 'fr' else 'topic'
        subsections = get_subs(tmpl, 'introduction')
        actual_titles[lang] = [(sub.one(key) or '').strip() for sub in subsections]
        content_key = 'contenu' if lang == 'fr' else 'content'
        actual_contents[lang] = {(sub.one(key) or '').strip(): (sub.one(content_key) or '').strip() for sub in subsections}
        complete_topics[lang] = (tmpl.one(complete_key) or '').strip()
        topics[lang] = (tmpl.one(topic_key) or '').strip()
    issues = validate_introduction_review_data(review, actual_titles, norm=norm, complete_topics=complete_topics, topics=topics, introduction_policy_revision=controls.get('introduction_policy_revision'), inline_reference_punctuation_policy_revision=controls.get('inline_reference_punctuation_policy_revision'), wikipedia_link_consistency_policy_revision=controls.get('wikipedia_link_consistency_policy_revision'), specialized_term_explanation_policy_revision=controls.get('specialized_term_explanation_policy_revision'), actual_contents=actual_contents, translation_semantic_review_schema_version=str(controls.get('translation_semantic_review_schema_version') or '1.0'))
    for issue in issues:
        reason = issue.get('reason')
        if reason in {'complete_topic_fits_heading', 'invalid_common_acronym', 'common_acronym_attestation', 'common_acronym_missing_from_complete_topic', 'topic_is_nominal_label', 'conventional_topic_label_used_or_not_applicable', 'complete_topic_lowercase_initial_or_justified', 'topic_label_rationale', 'complete_topic_initial_capital_justification', 'missing_topic'}:
            code = 'WDV-EDT-018'
            message = 'La forme de sujet-développé ou expanded-topic, notamment l’usage de l’acronyme courant, n’est pas conforme'
        elif reason in {'debate_sections_precise', 'documentation_proportionate_to_literature', 'documentation_family_notes', 'documentation_family_note'}:
            code = 'WDV-EDT-019'
            message = 'La précision des rubriques ou la profondeur documentaire de la page de débat n’est pas attestée'
        elif reason in {'reference_note_punctuation_review_missing', 'terminal_period_sentence_exceptions_missing', 'invalid_terminal_period_sentence_exception'}:
            code = 'WDV-DOC-008'
            message = 'La revue de la ponctuation terminale des notes de référence est absente ou incohérente'
        elif reason in {'specialized_term_inventory_review_missing', 'specialized_term_inventory_missing', 'specialized_term_inventory_subsections_mismatch', 'invalid_specialized_term_inventory_entry', 'specialized_term_inventory_subsection_missing', 'specialized_term_scan_incomplete', 'specialized_term_list_invalid', 'technical_subsection_inventory_empty', 'invalid_specialized_term_entry', 'specialized_term_not_in_subsection', 'specialized_term_declared_link_missing', 'specialized_term_inline_explanation_missing', 'specialized_term_prior_treatment_invalid', 'specialized_term_context_justification_missing', 'undeclared_wikipedia_hover_link'}:
            code = 'WDV-EDT-029'
            message = 'L’inventaire général des notions spécialisées de l’introduction est absent ou incohérent'
        elif reason in {'wikipedia_link_consistency_review_missing', 'wikipedia_link_groups_missing', 'invalid_wikipedia_link_group', 'wikipedia_link_group_subsection_missing', 'wikipedia_link_group_rationale_missing', 'wikipedia_link_group_terms_invalid', 'invalid_wikipedia_link_term', 'declared_wikipedia_link_missing', 'unlinked_peer_term_unjustified'}:
            code = 'WDV-EDT-028'
            message = 'La cohérence locale des liens Wikipédia explicatifs est absente ou incohérente'
        elif reason in {'missing_dedicated_stakes_subsection', 'stakes_subsection_too_thin', 'stakes_review_row_count', 'stakes_section_attestation', 'concrete_stakes_missing', 'invalid_concrete_stakes'}:
            code = 'WDV-EDT-017'
            message = 'La sous-partie obligatoire sur les enjeux du débat est absente, trop générale ou insuffisamment attestée'
        elif reason in {'historical_introduction_not_preserved', 'historical_introduction_source_sha256', 'historical_introduction_absence_unverified', 'historical_introduction_note', 'historical_introduction_authorization_missing', 'historical_introduction_final_sha256'}:
            code = 'WDV-EDT-034'
            message = 'La préservation de l’introduction historique n’est pas correctement attestée'
        else:
            code = 'WDV-EDT-017'
            message = 'Revue structurelle de l’introduction absente ou incohérente'
        ctx.report.error(code, message, path=rel, details=issue)
    return {'path': rel, 'languages': sorted(actual_titles), 'subsection_titles': actual_titles, 'issues': issues}

def _validate_normative_non_regression(ctx: PackageContext, manifest: dict[str, Any], trace_controls: dict[str, Any]) -> dict[str, Any]:
    norm = (manifest.get('normative_versions') or {}).get('consolidated_norm')
    active = sorted(ctx.iter_files('normative/WIKIDEBIA_NORME_CONSOLIDEE_*.md'))
    names = [Path(p).name for p in active]
    expected = f'WIKIDEBIA_NORME_CONSOLIDEE_{norm}.md'
    if len(active) != 1 or names != [expected]:
        ctx.report.error('WDV-EDT-011', 'La norme consolidée active n’est pas unique ou ne correspond pas au manifeste', path='normative', details={'active': names, 'expected': expected})
    handoff_rel = trace_controls.get('current_handoff_path')
    expected_work = trace_controls.get('current_corrective_work_id')
    handoff = ctx.load_json(handoff_rel) if isinstance(handoff_rel, str) and ctx.exists(handoff_rel) else None
    if not isinstance(handoff, dict):
        ctx.report.error('WDV-EDT-011', 'Handoff correctif courant absent', path=handoff_rel or 'manifest.json')
    else:
        nv = handoff.get('normative_versions') or {}
        expected_validator = (manifest.get('normative_versions') or {}).get('validator')
        if handoff.get('work_id') != expected_work or nv.get('consolidated_norm') != norm or nv.get('validator') != expected_validator or (handoff.get('remote_operations_performed') is not False):
            ctx.report.error('WDV-EDT-011', 'Handoff correctif courant incohérent', path=handoff_rel, details={'work_id': handoff.get('work_id'), 'normative_versions': nv, 'remote_operations_performed': handoff.get('remote_operations_performed'), 'expected_work': expected_work, 'expected_norm': norm, 'expected_validator': expected_validator})
    return {'active_norms': names, 'current_handoff': handoff_rel if isinstance(handoff, dict) else None}

def validate_individual_review_data(review: Any, nodes: list[dict[str, Any]], norm: str | None=None, english_deferred: bool=False, displayed_title_policy_revision: str | None=None, displayed_title_policy_node_ids: set[str] | None=None, translation_validation_mode: str='absolute', translation_semantic_review_schema_version: str='1.0', preexisting_node_ids: set[str] | None=None) -> list[dict[str, Any]]:
    """Return stable inconsistencies in a generic page-by-page editorial ledger."""
    issues: list[dict[str, Any]] = []
    if not isinstance(review, dict):
        return [{'reason': 'missing_or_invalid_document'}]
    entries = review.get('entries')
    if not isinstance(entries, list):
        return [{'reason': 'missing_entries'}]
    active = {n.get('id'): n for n in nodes}
    by_id: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get('id'), str):
            issues.append({'reason': 'invalid_entry'})
            continue
        node_id = entry['id']
        if node_id in by_id:
            issues.append({'reason': 'duplicate_entry', 'node_id': node_id})
        by_id[node_id] = entry
    if set(by_id) != set(active):
        issues.append({'reason': 'coverage', 'missing': sorted(set(active) - set(by_id)), 'extra': sorted(set(by_id) - set(active))})
    for node_id, node in active.items():
        entry = by_id.get(node_id)
        if not entry:
            continue
        fr = node.get('fr') or {}
        en = node.get('en') or {}
        node_english_deferred = english_deferred or reuses_existing_english_page(node)
        if entry.get('title_decision') not in {'reformulated', 'retained_after_review'}:
            issues.append({'reason': 'title_decision', 'node_id': node_id})
        if entry.get('canonical_referents_explicit_fr') is not True or (not node_english_deferred and entry.get('canonical_referents_explicit_en') is not True):
            issues.append({'reason': 'canonical_referents_explicit', 'node_id': node_id})
        current_differential = translation_validation_mode == 'differential'
        preexisting_fr = preexisting_node_ids is not None and str(node_id) in preexisting_node_ids
        # Historical displayed titles may legitimately rely on their immediate
        # rendering context.  Do not force a false explicit-referent attestation
        # merely because an English target page is technically new.
        if not preexisting_fr and not current_differential:
            if entry.get('displayed_referents_explicit_fr') is not True or (not node_english_deferred and entry.get('displayed_referents_explicit_en') is not True):
                issues.append({'reason': 'displayed_referents_explicit', 'node_id': node_id})
        if current_differential:
            # The French source is authoritative in translation mode: attest its
            # reviewed source form, but do not retroactively impose creation-form
            # rules on historical content.
            required_title_attestations = ['displayed_title_argument_intelligible_fr']
            if not node_english_deferred:
                required_title_attestations.append('displayed_title_source_form_reviewed_fr')
        elif preexisting_fr:
            # A pre-existing wiki displayed title is historical source content.
            # Complete-proposition form is a creation rule, not a retroactive rewrite rule.
            required_title_attestations = ['displayed_title_argument_intelligible_fr']
        else:
            required_title_attestations = ['displayed_title_complete_proposition_fr', 'displayed_title_argument_intelligible_fr']
        if not node_english_deferred:
            if current_differential:
                required_title_attestations += [
                    'displayed_title_argument_intelligible_en',
                    'displayed_title_source_form_reviewed_en',
                    'displayed_title_no_formal_regression_en',
                    'displayed_title_semantic_inventory_reviewed_en',
                ]
                if (not preexisting_fr) and (not displayed_title_argument_issues(str(fr.get('displayed_title') or ''), 'fr')):
                    required_title_attestations.append('displayed_title_complete_proposition_en')
            else:
                required_title_attestations += ['displayed_title_complete_proposition_en', 'displayed_title_argument_intelligible_en']
        for field in required_title_attestations:
            if entry.get(field) is not True:
                issues.append({'reason': field, 'node_id': node_id})
        if current_differential and not node_english_deferred:
            allowed_forms = {'proposition', 'question', 'imperative', 'thematic_label', 'nominal_phrase', 'doctrinal_label', 'other'}
            source_form_fr = str(entry.get('displayed_title_source_form_fr') or '')
            source_form_en = str(entry.get('displayed_title_source_form_en') or '')
            target_form_en = str(entry.get('displayed_title_target_form_en') or '')
            if source_form_fr not in allowed_forms or source_form_en not in allowed_forms or target_form_en not in allowed_forms:
                issues.append({'reason': 'displayed_title_form_classification', 'node_id': node_id})
            elif source_form_en != target_form_en:
                # A source-authoritative translation may change surface form for
                # idiomatic reasons, but only under an explicit speech-act review.
                if source_form_en == 'proposition' and target_form_en != 'proposition':
                    issues.append({'reason': 'displayed_title_form_regression', 'node_id': node_id, 'source_form_fr': source_form_fr, 'source_form_en': source_form_en, 'target_form_en': target_form_en})
                elif entry.get('displayed_title_form_change_reviewed_en') is not True or entry.get('displayed_title_speech_act_preserved_en') is not True or len(str(entry.get('displayed_title_form_change_note_en') or '').strip()) < 24:
                    issues.append({'reason': 'displayed_title_form_change_unreviewed', 'node_id': node_id, 'source_form_fr': source_form_fr, 'source_form_en': source_form_en, 'target_form_en': target_form_en})
            if translation_semantic_review_schema_version in {'1.1', '1.2', '1.3', '1.4'}:
                if entry.get('canonical_title_semantic_inventory_reviewed_en') is not True:
                    issues.append({'reason': 'canonical_title_semantic_inventory_reviewed_en', 'node_id': node_id})
                if entry.get('canonical_title_semantically_equivalent_en') is not True:
                    issues.append({'reason': 'canonical_title_semantically_equivalent_en', 'node_id': node_id})
                if len(str(entry.get('canonical_title_semantic_inventory_note_en') or '').strip()) < 20:
                    issues.append({'reason': 'canonical_title_semantic_inventory_note_en', 'node_id': node_id})
            if translation_semantic_review_schema_version in {'1.2', '1.3', '1.4'}:
                for field in (
                    'canonical_title_subject_preserved_en', 'canonical_title_predicate_preserved_en',
                    'canonical_title_scope_preserved_en', 'canonical_title_modality_preserved_en',
                    'displayed_title_subject_preserved_en', 'displayed_title_predicate_preserved_en',
                    'displayed_title_scope_preserved_en', 'displayed_title_modality_preserved_en',
                ):
                    if entry.get(field) is not True:
                        issues.append({'reason': field, 'node_id': node_id})
            if len(str(entry.get('displayed_title_semantic_inventory_note_en') or '').strip()) < 20:
                issues.append({'reason': 'displayed_title_semantic_inventory_note_en', 'node_id': node_id})
        concision_fields = ['displayed_title_concision_reviewed_fr']
        if not node_english_deferred:
            concision_fields.append('displayed_title_concision_reviewed_en')
        for field in concision_fields:
            if entry.get(field) is not True:
                issues.append({'reason': field, 'node_id': node_id})
        reviewed_languages = (('fr', fr),) if node_english_deferred else (('fr', fr), ('en', en))
        for lang, data in reviewed_languages:
            canonical = (data.get('canonical_title') or '').strip().casefold()
            displayed = (data.get('displayed_title') or '').strip().casefold()
            justification = str(entry.get(f'displayed_title_identity_justification_{lang}') or '').strip()
            if canonical and canonical != displayed and (displayed_title_policy_node_ids is None or node_id in displayed_title_policy_node_ids):
                if entry.get(f'displayed_title_semantic_equivalence_reviewed_{lang}') is not True:
                    issues.append({'reason': f'displayed_title_semantic_equivalence_reviewed_{lang}', 'node_id': node_id})
                if not current_differential and entry.get(f'displayed_title_readability_improvement_reviewed_{lang}') is not True:
                    issues.append({'reason': f'displayed_title_readability_improvement_reviewed_{lang}', 'node_id': node_id})
                if not current_differential and len(str(entry.get('title_reason') or '').strip()) < 40:
                    issues.append({'reason': 'displayed_title_difference_reason', 'node_id': node_id})
        if not str(entry.get('title_reason') or '').strip():
            issues.append({'reason': 'title_reason', 'node_id': node_id})
        if entry.get('new_displayed_title_fr') != fr.get('displayed_title'):
            issues.append({'reason': 'displayed_title', 'node_id': node_id})
        selected = fr.get('rubriques') or []
        if entry.get('new_rubriques') != selected:
            issues.append({'reason': 'rubriques', 'node_id': node_id})
        if not node_english_deferred:
            if entry.get('new_displayed_title_en') != en.get('displayed_title'):
                issues.append({'reason': 'displayed_title_en', 'node_id': node_id})
            if entry.get('new_sections_en') != (en.get('sections') or []):
                issues.append({'reason': 'sections_en', 'node_id': node_id})
        if entry.get('new_keywords_fr') != (fr.get('keywords') or []):
            issues.append({'reason': 'keywords_fr', 'node_id': node_id})
        if not node_english_deferred and entry.get('new_keywords_en') != (en.get('keywords') or []):
            issues.append({'reason': 'keywords_en', 'node_id': node_id})
        for lang in ('fr',) if node_english_deferred else ('fr', 'en'):
            if entry.get(f'keywords_ordered_by_relevance_{lang}') is not True:
                issues.append({'reason': f'keywords_ordered_by_relevance_{lang}', 'node_id': node_id})
            rationale = str(entry.get(f'keyword_order_rationale_{lang}') or '').strip()
            if len(rationale) < 20:
                issues.append({'reason': f'keyword_order_rationale_{lang}', 'node_id': node_id})
        if entry.get('rubric_decision') not in {'adjusted', 'retained_after_review'}:
            issues.append({'reason': 'rubric_decision', 'node_id': node_id})
        rationales = entry.get('rubric_rationales')
        if not isinstance(rationales, dict):
            issues.append({'reason': 'rubric_rationales', 'node_id': node_id})
            continue
        if set(rationales) != set(selected):
            issues.append({'reason': 'rubric_rationale_coverage', 'node_id': node_id, 'missing': sorted(set(selected) - set(rationales)), 'extra': sorted(set(rationales) - set(selected))})
        for rubric, reason in rationales.items():
            if not isinstance(reason, str) or len(reason.strip()) < 12:
                issues.append({'reason': 'rubric_rationale', 'node_id': node_id, 'rubric': rubric})
    return issues

def validate_graph_placement_review_data(review: Any, registry: dict[str, Any], norm: str | None=None) -> list[dict[str, Any]]:
    """Validate the occurrence-by-occurrence semantic placement ledger."""
    issues: list[dict[str, Any]] = []
    if not isinstance(review, dict):
        return [{'reason': 'missing_or_invalid_document'}]
    if review.get('debate_id') != (registry.get('debate') or {}).get('id'):
        issues.append({'reason': 'debate_id', 'expected': (registry.get('debate') or {}).get('id'), 'actual': review.get('debate_id')})
    entries = review.get('entries')
    if not isinstance(entries, list):
        return issues + [{'reason': 'missing_entries'}]
    graph = registry.get('graph') or {}
    active_nodes = {n.get('id') for n in graph.get('nodes', []) if n.get('status') == 'active'}
    occurrences = [o for o in graph.get('occurrences', []) if o.get('node_id') in active_nodes]
    occ_by_id = {o.get('id'): o for o in occurrences}
    edge_by_id = {e.get('id'): e for e in graph.get('edges', []) if e.get('status') == 'active'}
    by_id: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get('occurrence_id'), str):
            issues.append({'reason': 'invalid_entry'})
            continue
        oid = entry['occurrence_id']
        if oid in by_id:
            issues.append({'reason': 'duplicate_entry', 'occurrence_id': oid})
        by_id[oid] = entry
    if set(by_id) != set(occ_by_id):
        issues.append({'reason': 'coverage', 'missing': sorted(set(occ_by_id) - set(by_id)), 'extra': sorted(set(by_id) - set(occ_by_id))})
    for oid, occ in occ_by_id.items():
        entry = by_id.get(oid)
        if not entry:
            continue
        depth = occ.get('depth')
        if entry.get('node_id') != occ.get('node_id'):
            issues.append({'reason': 'node_id', 'occurrence_id': oid})
        if entry.get('declared_depth') != depth:
            issues.append({'reason': 'declared_depth', 'occurrence_id': oid, 'expected': depth, 'actual': entry.get('declared_depth')})
        if entry.get('placement_status') not in {'approved', 'moved_after_review'}:
            issues.append({'reason': 'placement_status', 'occurrence_id': oid})
        if entry.get('direct_fit') is not True:
            issues.append({'reason': 'direct_fit', 'occurrence_id': oid})
        rationale = entry.get('rationale')
        if not isinstance(rationale, str) or len(rationale.strip()) < 24:
            issues.append({'reason': 'rationale', 'occurrence_id': oid})
        if depth == 1:
            if entry.get('declared_function') != 'main_argument':
                issues.append({'reason': 'declared_function', 'occurrence_id': oid, 'expected': 'main_argument'})
            if entry.get('semantic_target') != 'debate':
                issues.append({'reason': 'semantic_target', 'occurrence_id': oid, 'expected': 'debate'})
            review_main = entry.get('main_argument_review')
            if not isinstance(review_main, dict):
                issues.append({'reason': 'main_argument_review', 'occurrence_id': oid})
                continue
            required_true = ('direct_answer_to_debate', 'autonomous_without_parent', 'organizes_distinct_argument_family')
            required_false = ('more_general_nonduplicate_parent_available', 'principally_supports_or_attacks_specific_argument', 'principally_example_or_specialization')
            for field in required_true:
                if review_main.get(field) is not True:
                    issues.append({'reason': field, 'occurrence_id': oid})
            for field in required_false:
                if review_main.get(field) is not False:
                    issues.append({'reason': field, 'occurrence_id': oid})
        else:
            parent_id = occ.get('parent_occurrence_id')
            edge = edge_by_id.get(occ.get('edge_id')) or {}
            relation = edge.get('relation')
            if entry.get('semantic_target') != parent_id:
                issues.append({'reason': 'semantic_target', 'occurrence_id': oid, 'expected': parent_id})
            if entry.get('declared_function') != relation:
                issues.append({'reason': 'declared_function', 'occurrence_id': oid, 'expected': relation})
            sub = entry.get('subordinate_review')
            if not isinstance(sub, dict):
                issues.append({'reason': 'subordinate_review', 'occurrence_id': oid})
                continue
            if sub.get('parent_is_best_immediate_target') is not True:
                issues.append({'reason': 'parent_is_best_immediate_target', 'occurrence_id': oid})
            if sub.get('relation_to_parent_explicit') is not True:
                issues.append({'reason': 'relation_to_parent_explicit', 'occurrence_id': oid})
    return issues

def _validate_graph_placement_review(ctx: PackageContext, registry: dict[str, Any], controls: dict[str, Any], norm: str) -> dict[str, Any]:
    rel = controls.get('graph_placement_review_path')
    review = ctx.load_json(rel) if isinstance(rel, str) and ctx.exists(rel) else None
    issues = validate_graph_placement_review_data(review, registry, norm=norm)
    if issues:
        ctx.report.error('WDV-EDT-022', 'Revue du placement des arguments absente ou incohérente', path=rel or 'manifest.json', details={'issue_count': len(issues), 'issues': issues[:40]})
    entries = review.get('entries', []) if isinstance(review, dict) else []
    return {'path': rel, 'reviewed_occurrences': len(entries), 'main_arguments': sum((1 for e in entries if isinstance(e, dict) and e.get('declared_depth') == 1)), 'moved_after_review': sum((1 for e in entries if isinstance(e, dict) and e.get('placement_status') == 'moved_after_review')), 'issues': len(issues)}

def _validate_individual_editorial_review(ctx: PackageContext, nodes: list[dict[str, Any]], controls: dict[str, Any]) -> dict[str, Any]:
    rel = controls.get('individual_review_path')
    review = ctx.load_json(rel) if isinstance(rel, str) and ctx.exists(rel) else None
    norm = ((ctx.manifest() or {}).get('normative_versions') or {}).get('consolidated_norm')
    deferred = english_translation_deferred(ctx.manifest() or {})
    policy_node_ids: set[str] | None = None
    if controls.get('displayed_title_policy_scope') == 'generated_pages_only':
        legacy = controls.get('legacy_content_preservation') or {}
        lock_path = legacy.get('lock_path')
        lock = ctx.load_json(lock_path) if isinstance(lock_path, str) and ctx.exists(lock_path) else None
        historical_ids = {str(row.get('id')) for row in lock.get('arguments') or [] if isinstance(row, dict) and row.get('id')} if isinstance(lock, dict) else set()
        policy_node_ids = {str(node.get('id')) for node in nodes if str(node.get('id')) not in historical_ids}
    page_rows = (ctx.manifest() or {}).get('pages') or []
    preexisting_node_ids = {str(row.get('page_id')) for row in page_rows if isinstance(row, dict) and row.get('language') == 'fr' and row.get('page_type') == 'argument' and row.get('page_origin') == 'preexisting' and row.get('page_id')}
    issues = validate_individual_review_data(review, nodes, norm=norm, english_deferred=deferred, displayed_title_policy_revision=controls.get('displayed_title_policy_revision'), displayed_title_policy_node_ids=policy_node_ids, translation_validation_mode=str(controls.get('translation_validation_mode') or 'absolute'), translation_semantic_review_schema_version=str(controls.get('translation_semantic_review_schema_version') or '1.0'), preexisting_node_ids=preexisting_node_ids)
    if issues:
        ctx.report.error('WDV-EDT-012', 'Revue individuelle des titres affichés et rubriques absente ou incohérente', path=rel or 'manifest.json', details={'issue_count': len(issues), 'issues': issues[:25]})
    entries = review.get('entries', []) if isinstance(review, dict) else []
    return {'reviewed_nodes': len(entries), 'title_reformulated': sum((1 for e in entries if isinstance(e, dict) and e.get('title_decision') == 'reformulated')), 'title_retained_after_review': sum((1 for e in entries if isinstance(e, dict) and e.get('title_decision') == 'retained_after_review')), 'rubrics_adjusted': sum((1 for e in entries if isinstance(e, dict) and e.get('rubric_decision') == 'adjusted')), 'rubric_rationales': sum((len(e.get('rubric_rationales') or {}) for e in entries if isinstance(e, dict))), 'issues': len(issues)}

def validate_summary_style_review_data(review: Any, nodes: list[dict[str, Any]], page_languages: dict[str, set[str]], norm: str='1.1.8', quantitative_pages: set[tuple[str, str]] | None=None, summaries: dict[tuple[str, str], str] | None=None, quality_policy_revision: str | None=None, summary_policy_revision: str | None=None, protected_historical: set[tuple[str, str]] | None=None, historically_absent: set[tuple[str, str]] | None=None, owner_removed_summaries: set[tuple[str, str]] | None=None) -> list[dict[str, Any]]:
    """Validate page-level human attestations for direct, general-public summaries."""
    issues: list[dict[str, Any]] = []
    quantitative = quantitative_pages or set()
    summary_map = summaries or {}
    protected = protected_historical or set()
    absent = historically_absent or set()
    owner_removed = owner_removed_summaries or set()
    quality_1238 = True
    if not isinstance(review, dict):
        return [{'reason': 'missing_or_invalid_document'}]
    entries = review.get('entries')
    if not isinstance(entries, list):
        return issues + [{'reason': 'missing_entries'}]
    active_ids = {n.get('id') for n in nodes}
    by_id: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get('id'), str):
            issues.append({'reason': 'invalid_entry'})
            continue
        node_id = entry['id']
        if node_id in by_id:
            issues.append({'reason': 'duplicate_entry', 'node_id': node_id})
        by_id[node_id] = entry
    # Summary-style attestations are creation/rewrite controls. Historical,
    # historically absent and owner-removed summaries are governed by the
    # authoritative FR/EN content locks instead (not by this style ledger).
    # A legacy ledger may still contain rows for those summaries, but their
    # presence, status or creation-style fields must never be required to
    # validate the historical content.
    def _style_exempt(node_id: str, lang: str) -> bool:
        key = (node_id, lang)
        if key in protected or key in absent or key in owner_removed:
            return True
        # Compatibility for direct/unit validation and legacy ledgers where
        # only the French protected key was materialized: an English decision
        # explicitly marked as a translation of that protected historical
        # source is also outside the creation-style profile. Full package
        # validation normally derives the English protected key from the
        # content locks before reaching this function.
        if lang == 'en' and (node_id, 'fr') in protected:
            entry = by_id.get(node_id)
            languages = entry.get('languages') if isinstance(entry, dict) else None
            decision = languages.get('en') if isinstance(languages, dict) else None
            if isinstance(decision, dict) and decision.get('status') == 'translated_historical_source':
                return True
        return False

    def _style_required_languages(node_id: str) -> set[str]:
        return {lang for lang in page_languages.get(node_id, set()) if not _style_exempt(node_id, lang)}

    expected = {node_id for node_id in active_ids if _style_required_languages(str(node_id))}
    active_with_pages = {node_id for node_id in active_ids if page_languages.get(node_id)}
    missing = expected - set(by_id)
    extra = set(by_id) - active_with_pages
    if missing or extra:
        issues.append({'reason': 'coverage', 'missing': sorted(missing), 'extra': sorted(extra)})
    required_true = ['thesis_first', 'general_public_style', 'sentence_rhythm_reviewed', 'technical_terms_reviewed']
    required_true += ['opening_develops_title', 'example_or_data_reviewed', 'assertive_tone_reviewed', 'no_artificial_example_or_number', 'no_polemical_overstatement']
    required_true += ['conviction_visible']
    required_true += ['wikipedia_hover_links_reviewed', 'specialized_terms_linked_or_explained']
    if quality_1238:
        required_true += ['originality_reviewed']
    for node_id in expected:
        entry = by_id.get(node_id)
        if not entry:
            continue
        languages = entry.get('languages')
        if not isinstance(languages, dict):
            issues.append({'reason': 'languages', 'node_id': node_id})
            continue
        all_languages = page_languages.get(node_id, set())
        required_languages = _style_required_languages(node_id)
        # Historical language rows may remain in a legacy ledger and are
        # harmless; only unknown languages are invalid, while every language
        # that actually requires style review must be present.
        if not required_languages.issubset(set(languages)) or not set(languages).issubset(all_languages):
            issues.append({'reason': 'language_coverage', 'node_id': node_id, 'missing': sorted(required_languages - set(languages)), 'extra': sorted(set(languages) - all_languages)})
        for lang in required_languages:
            decision = languages.get(lang)
            if not isinstance(decision, dict):
                issues.append({'reason': 'language_decision', 'node_id': node_id, 'language': lang})
                continue
            key_tuple = (node_id, lang)
            if decision.get('status') not in {'approved', 'revised'}:
                issues.append({'reason': 'status', 'node_id': node_id, 'language': lang})
            effective_required_true = list(required_true)
            for key in effective_required_true:
                if decision.get(key) is not True:
                    issues.append({'reason': key, 'node_id': node_id, 'language': lang})
            expression = str(decision.get('forceful_expression') or '').strip()
            summary_text = summary_map.get((node_id, lang), '')
            normalized_expression = re.sub('\\s+', ' ', expression).casefold()
            normalized_summary = re.sub('\\s+', ' ', _plain_text(summary_text)).casefold()
            if len(WORD_TOKEN.findall(expression)) < 3 or len(expression) < 12:
                issues.append({'reason': 'forceful_expression', 'node_id': node_id, 'language': lang})
            elif normalized_expression not in normalized_summary:
                issues.append({'reason': 'forceful_expression_not_in_summary', 'node_id': node_id, 'language': lang, 'expression': expression})
            if quality_1238 and key_tuple not in protected:
                mechanism = str(decision.get('mechanism_statement') or '').strip()
                summary_text = summary_map.get((node_id, lang), '')
                normalized_mechanism = re.sub('\\s+', ' ', mechanism).casefold()
                normalized_summary = re.sub('\\s+', ' ', _plain_text(summary_text)).casefold()
                summary_tokens = WORD_TOKEN.findall(_plain_text(summary_text))
                summary_too_short_for_normal_minimum = len(summary_tokens) < 6 or len(_plain_text(summary_text)) < 30
                mechanism_too_short = len(WORD_TOKEN.findall(mechanism)) < 6 or len(mechanism) < 30
                if mechanism_too_short and not (summary_too_short_for_normal_minimum and normalized_mechanism == normalized_summary):
                    issues.append({'reason': 'mechanism_statement', 'node_id': node_id, 'language': lang})
                elif normalized_mechanism not in normalized_summary:
                    issues.append({'reason': 'mechanism_statement_not_in_summary', 'node_id': node_id, 'language': lang, 'statement': mechanism})
            if (node_id, lang) in quantitative:
                if decision.get('quantitative_claims_verified') is not True:
                    issues.append({'reason': 'quantitative_claims_verified', 'node_id': node_id, 'language': lang})
                if len(str(decision.get('quantitative_claims_note') or '').strip()) < 12:
                    issues.append({'reason': 'quantitative_claims_note', 'node_id': node_id, 'language': lang})
            if len(str(decision.get('note') or '').strip()) < 12:
                issues.append({'reason': 'note', 'node_id': node_id, 'language': lang})
    return issues

def _protected_historical_summary_keys(ctx: PackageContext) -> set[tuple[str, str]]:
    return _shared_protected_historical_summary_keys(ctx)

def _historically_absent_summary_keys(ctx: PackageContext) -> set[tuple[str, str]]:
    return _shared_historically_absent_summary_keys(ctx)

def _owner_removed_summary_keys(ctx: PackageContext) -> set[tuple[str, str]]:
    return _shared_owner_removed_summary_keys(ctx)

def _fr_metadata_lock_entry(ctx: PackageContext, node_id: str) -> dict[str, Any] | None:
    cache = getattr(ctx, '_fr_metadata_lock_entry_cache', None)
    if not isinstance(cache, dict):
        cache = {}
        rel = 'data/fr_page_metadata_lock.json'
        data = ctx.load_json(rel) if ctx.exists(rel) else None
        if isinstance(data, dict):
            debate = data.get('debate')
            if isinstance(debate, dict):
                cache['debate'] = debate
            for entry in data.get('arguments') or []:
                if isinstance(entry, dict) and isinstance(entry.get('entity_id'), str):
                    cache[str(entry['entity_id'])] = entry
        setattr(ctx, '_fr_metadata_lock_entry_cache', cache)
    row = cache.get(str(node_id))
    return row if isinstance(row, dict) else None


def _individual_review_entry(ctx: PackageContext, node_id: str) -> dict[str, Any] | None:
    cache=getattr(ctx, '_individual_review_entry_cache', None)
    if not isinstance(cache, dict):
        controls=((ctx.manifest() or {}).get('editorial_controls') or {})
        rel=controls.get('individual_review_path')
        data=ctx.load_json(rel) if isinstance(rel,str) and ctx.exists(rel) else None
        cache={str(e.get('id')):e for e in (data.get('entries') or []) if isinstance(data,dict) and isinstance(e,dict) and isinstance(e.get('id'),str)} if isinstance(data,dict) else {}
        setattr(ctx, '_individual_review_entry_cache', cache)
    row=cache.get(str(node_id))
    return row if isinstance(row,dict) else None

def _summary_review_decision(ctx: PackageContext, node_id: str, language: str) -> dict[str, Any] | None:
    cache=getattr(ctx, '_summary_review_decision_cache', None)
    if not isinstance(cache, dict):
        controls=((ctx.manifest() or {}).get('editorial_controls') or {})
        rel=controls.get('summary_style_review_path')
        data=ctx.load_json(rel) if isinstance(rel,str) and ctx.exists(rel) else None
        cache={}
        if isinstance(data,dict):
            for entry in data.get('entries') or []:
                if isinstance(entry,dict) and isinstance(entry.get('id'),str):
                    for lang, decision in (entry.get('languages') or {}).items():
                        if isinstance(decision,dict): cache[(entry['id'],lang)]=decision
        setattr(ctx, '_summary_review_decision_cache', cache)
    row=cache.get((str(node_id),language))
    return row if isinstance(row,dict) else None

def _localized_keyword_entry(entry: dict[str, Any] | None, language: str) -> dict[str, Any]:
    data=dict(entry or {})
    if language == 'en':
        for base in ('kind','capitalization_policy','multiword_exception','multiword_exception_rationale','compositional_intersection','atomic_concept','productive_phrase_exception','productive_phrase_exception_rationale'):
            key='en_'+base
            if key in data:
                data[base]=data[key]
    return data

def _validate_summary_style(ctx: PackageContext, nodes: list[dict[str, Any]], manifest: dict[str, Any], controls: dict[str, Any], norm: str) -> dict[str, Any]:
    cfg = controls.get('summary_style') or {}
    review_rel = controls.get('summary_style_review_path')
    summary_quality_active = True
    capitalization_active = True
    page_languages: dict[str, set[str]] = {}
    node_map = {n.get('id'): n for n in nodes}
    quantitative_pages: set[tuple[str, str]] = set()
    summaries: dict[tuple[str, str], str] = {}
    heuristic_warnings = 0
    opening_warnings = 0
    quantitative_summaries = 0
    reviewed_pages = 0
    protected_historical = _protected_historical_summary_keys(ctx)
    historically_absent = _historically_absent_summary_keys(ctx)
    owner_removed_summaries = _owner_removed_summary_keys(ctx)
    for page in manifest.get('pages', []):
        if page.get('page_type') != 'argument':
            continue
        node_id = page.get('page_id')
        lang = page.get('language')
        if isinstance(node_id, str) and lang in {'fr', 'en'}:
            page_languages.setdefault(node_id, set()).add(lang)
        tmpl = _parse_page(ctx, page.get('file_path'))
        if not tmpl or lang not in {'fr', 'en'}:
            continue
        if (node_id, lang) in historically_absent | owner_removed_summaries:
            summaries[node_id, lang] = ''
            continue
        summary = _summary(tmpl, lang)
        if isinstance(node_id, str):
            summaries[node_id, lang] = summary
        is_protected_historical = (node_id, lang) in protected_historical
        decision = _summary_review_decision(ctx, str(node_id), lang)
        manual_style_ok = isinstance(decision, dict) and decision.get('status') in {'approved','revised'} and decision.get('general_public_style') is True and decision.get('sentence_rhythm_reviewed') is True
        if not is_protected_historical and cfg.get('enabled') is True:
            metrics = summary_style_issues(summary, cfg)
            if metrics['issues'] and not manual_style_ok:
                heuristic_warnings += 1
                ctx.report.warning('WDV-EDT-013', 'Le rythme du résumé paraît trop lourd pour un style encyclopédique grand public', path=page.get('file_path'), details={'node_id': node_id, 'language': lang, **metrics})
        if not is_protected_historical and cfg.get('opening_title_similarity_enabled', True) is True:
            data = (node_map.get(node_id) or {}).get(lang) or {}
            titles = [data.get('canonical_title') or '', data.get('displayed_title') or '', page.get('canonical_title') or '']
            opening_metrics = opening_title_similarity(summary, titles, lang, cfg)
            manual_opening_ok = isinstance(decision, dict) and decision.get('status') in {'approved','revised'} and decision.get('opening_develops_title') is True
            if opening_metrics['issue'] and not manual_opening_ok:
                opening_warnings += 1
                ctx.report.warning('WDV-EDT-014', 'La première phrase du résumé répète ou paraphrase trop étroitement le titre', path=page.get('file_path'), details={'node_id': node_id, 'language': lang, **opening_metrics})
        claims = summary_quantitative_claims(summary) if not is_protected_historical else []
        if claims:
            quantitative_pages.add((node_id, lang))
            quantitative_summaries += 1
    if summary_quality_active or capitalization_active:
        sentence_uses: dict[tuple[str, str], list[str]] = defaultdict(list)
        graph = (ctx.registry() or {}).get('graph') or {}
        children: dict[str, list[str]] = defaultdict(list)
        if summary_quality_active:
            for edge in graph.get('edges', []):
                if edge.get('status') == 'active':
                    child = node_map.get(edge.get('child_node_id')) or {}
                    for language in ('fr', 'en'):
                        data = child.get(language) or {}
                        for title in (data.get('canonical_title'), data.get('displayed_title')):
                            if isinstance(title, str) and title.strip():
                                children[str(edge.get('parent_node_id'))].append(_plain_text(title).casefold())
        for (node_id, language), summary in summaries.items():
            if (node_id, language) in protected_historical:
                continue
            if summary_quality_active:
                reasons = summary_template_issues(summary, language)
                normalized = _plain_text(summary).casefold()
                copied_children = sorted({title for title in children.get(node_id, []) if len(WORD_TOKEN.findall(title)) >= 4 and title in normalized})
                if len(copied_children) >= 2:
                    reasons.append('child_title_enumeration')
                if reasons:
                    ctx.report.error('WDV-EDT-024', 'Résumé construit par gabarit générique, métadiscours ou énumération de pages filles', path=next((p.get('file_path') for p in manifest.get('pages', []) if p.get('page_id') == node_id and p.get('language') == language), 'manifest.json'), details={'node_id': node_id, 'language': language, 'reasons': sorted(set(reasons)), 'copied_child_titles': copied_children[:6]})
                for sentence in normalized_summary_sentences(summary, language):
                    sentence_uses[language, sentence].append(node_id)
            if capitalization_active and language == 'fr':
                deity_reasons = lowercase_god_issues(summary)
                if deity_reasons:
                    ctx.report.error('WDV-EDT-026', 'Le nom propre « Dieu » est écrit avec une minuscule dans le résumé', path=next((p.get('file_path') for p in manifest.get('pages', []) if p.get('page_id') == node_id and p.get('language') == language), 'manifest.json'), details={'node_id': node_id, 'reasons': deity_reasons})
        if summary_quality_active:
            for (language, sentence), node_ids in sentence_uses.items():
                if len(node_ids) >= 4:
                    ctx.report.error('WDV-EDT-024', 'Une même phrase de résumé est répétée dans au moins quatre pages', path=review_rel or 'manifest.json', details={'language': language, 'occurrences': len(node_ids), 'node_ids': sorted(node_ids), 'normalized_sentence': sentence})
    differential_translation = bool((manifest.get('editorial_controls') or {}).get('translation_validation_mode') == 'differential')
    marker_engine_active = str((manifest.get('editorial_controls') or {}).get('semantic_marker_engine_version') or '') in {'1.0', '1.1', '1.2', '1.3'}
    if differential_translation and marker_engine_active:
        semantic_summary_signals = 0
        for node_id in sorted(node_map):
            fr_summary = summaries.get((node_id, 'fr'), '')
            en_summary = summaries.get((node_id, 'en'), '')
            if not fr_summary or not en_summary:
                continue
            losses = bilingual_semantic_marker_losses(fr_summary, en_summary)
            structure_signals = bilingual_semantic_structure_signals(fr_summary, en_summary)
            if losses:
                semantic_summary_signals += 1
                en_page = next((p.get('file_path') for p in manifest.get('pages', []) if p.get('page_id') == node_id and p.get('language') == 'en'), 'manifest.json')
                ctx.report.info('WDV-BIL-007', 'Marqueurs sémantiques français possiblement perdus dans le résumé anglais ; revue bilingue requise', path=en_page, details={'node_id': node_id, 'field': 'summary', 'marker_families': losses})
            if structure_signals:
                en_page = next((p.get('file_path') for p in manifest.get('pages', []) if p.get('page_id') == node_id and p.get('language') == 'en'), 'manifest.json')
                ctx.report.info('WDV-BIL-008', 'Structure sémantique FR→EN possiblement déplacée dans le résumé ; revue humaine requise', path=en_page, details={'node_id': node_id, 'field': 'summary', 'signals': structure_signals})
        ctx.report.metrics.setdefault('semantic_marker_engine', {})['summary_pages_with_signals'] = semantic_summary_signals
    review = ctx.load_json(review_rel) if isinstance(review_rel, str) and ctx.exists(review_rel) else None
    issues = validate_summary_style_review_data(review, nodes, page_languages, norm=norm, quantitative_pages=quantitative_pages, summaries=summaries, protected_historical=protected_historical, historically_absent=historically_absent, owner_removed_summaries=owner_removed_summaries)
    opening_review_reasons = {'opening_develops_title'}
    quantitative_reasons = {'quantitative_claims_verified', 'quantitative_claims_note'}
    force_reasons = {'conviction_visible', 'forceful_expression', 'forceful_expression_not_in_summary'}
    opening_issues = [i for i in issues if i.get('reason') in opening_review_reasons]
    quantitative_issues = [i for i in issues if i.get('reason') in quantitative_reasons]
    force_issues = [i for i in issues if i.get('reason') in force_reasons]
    other_issues = [i for i in issues if i.get('reason') not in opening_review_reasons | quantitative_reasons | force_reasons]
    if other_issues:
        ctx.report.error('WDV-EDT-013', 'Revue humaine du style grand public, des exemples et du ton absente ou incohérente', path=review_rel or 'manifest.json', details={'issue_count': len(other_issues), 'issues': other_issues[:25]})
    if force_issues:
        ctx.report.error('WDV-EDT-020', 'La force expressive du résumé n’est pas attestée par un extrait réellement présent dans le texte', path=review_rel or 'manifest.json', details={'issue_count': len(force_issues), 'issues': force_issues[:25]})
    if opening_issues:
        ctx.report.error('WDV-EDT-014', 'L’attestation humaine que l’ouverture développe le titre est absente ou incohérente', path=review_rel or 'manifest.json', details={'issue_count': len(opening_issues), 'issues': opening_issues[:25]})
    if quantitative_issues:
        ctx.report.error('WDV-EDT-015', 'Une donnée chiffrée du résumé ne possède pas d’attestation documentaire humaine conforme', path=review_rel or 'manifest.json', details={'issue_count': len(quantitative_issues), 'issues': quantitative_issues[:25]})
    if isinstance(review, dict) and isinstance(review.get('entries'), list):
        reviewed_pages = sum((len(e.get('languages') or {}) for e in review['entries'] if isinstance(e, dict)))
    return {'heuristic_warnings': heuristic_warnings, 'opening_similarity_warnings': opening_warnings, 'quantitative_summaries': quantitative_summaries, 'reviewed_language_pages': reviewed_pages, 'review_issues': len(issues)}

def _canonical_object_sha256(data: dict[str, Any], omitted_field: str) -> str:
    normalized = dict(data)
    normalized.pop(omitted_field, None)
    raw = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _validate_semantic_convergence(ctx: PackageContext, controls: dict[str, Any], english_deferred: bool) -> dict[str, Any]:
    path = controls.get('semantic_convergence_review_path')
    schema_version = str(controls.get('semantic_convergence_review_schema_version') or '')
    if english_deferred and not path:
        return {'required': False, 'status': 'deferred'}
    if not path:
        if str(controls.get('translation_semantic_review_schema_version') or '') in {'1.3', '1.4'}:
            ctx.report.error('WDV-BIL-009', 'Reçu de convergence sémantique absent pour une traduction utilisant la revue 1.3', path='manifest.json')
        return {'required': False, 'status': 'absent'}
    if schema_version not in {'1.0', '1.1'} or not ctx.exists(path):
        ctx.report.error('WDV-BIL-009', 'Reçu de convergence sémantique déclaré mais absent ou de version incorrecte', path=path or 'manifest.json')
        return {'required': True, 'status': 'invalid'}
    receipt = ctx.load_json(path)
    review_path = 'reviews/en/translation_review.json'
    review = ctx.load_json(review_path) if ctx.exists(review_path) else None
    if not isinstance(receipt, dict) or not isinstance(review, dict):
        ctx.report.error('WDV-BIL-009', 'Reçu de convergence ou revue de traduction illisible', path=path)
        return {'required': True, 'status': 'invalid'}
    issues: list[str] = []
    review_sha = str(review.get('review_sha256') or '')
    semantic_sha = str(review.get('semantic_content_sha256') or '')
    if not review_sha or _canonical_object_sha256(review, 'review_sha256') != review_sha:
        issues.append('translation_review_sha256_invalid')
    if receipt.get('translation_review_sha256') != review_sha:
        issues.append('translation_review_sha256_mismatch')
    if not semantic_sha or receipt.get('semantic_content_sha256') != semantic_sha:
        issues.append('semantic_content_sha256_mismatch')
    if _canonical_object_sha256(receipt, 'receipt_sha256') != receipt.get('receipt_sha256'):
        issues.append('receipt_sha256_invalid')
    passes = receipt.get('passes') or []
    if receipt.get('status') != 'converged' or not isinstance(passes, list) or len(passes) < 2:
        issues.append('not_converged')
    else:
        first, second = passes[-2], passes[-1]
        if any((not isinstance(row, dict) or row.get('new_certain_errors') != 0 or row.get('translation_review_sha256') != review_sha or row.get('semantic_content_sha256') != semantic_sha) for row in (first, second)):
            issues.append('final_passes_not_clean_or_not_bound')
        if isinstance(first, dict) and isinstance(second, dict) and str(first.get('method') or '').strip().casefold() == str(second.get('method') or '').strip().casefold():
            issues.append('final_methods_not_distinct')
        if schema_version == '1.1' and isinstance(first, dict) and isinstance(second, dict):
            allowed_families = {'proposition_by_proposition', 'risk_marker_review', 'reverse_source_target', 'field_boundary_review', 'independent_bilingual_reread'}
            families = [str(first.get('method_family') or '').strip(), str(second.get('method_family') or '').strip()]
            if any(family not in allowed_families for family in families):
                issues.append('final_method_family_missing_or_invalid')
            elif families[0] == families[1]:
                issues.append('final_method_families_not_distinct')
    if issues:
        ctx.report.error('WDV-BIL-009', 'Convergence sémantique finale invalide', path=path, details={'reasons': issues})
    return {'required': True, 'status': receipt.get('status'), 'passes': len(passes) if isinstance(passes, list) else 0, 'issues': issues}


def validate_editorial(ctx: PackageContext) -> None:
    if not _active(ctx):
        return
    manifest = ctx.manifest() or {}
    norm = (manifest.get('normative_versions') or {}).get('consolidated_norm')
    english_deferred = english_translation_deferred(manifest)
    registry = ctx.registry() or {}
    editorial_controls = manifest.get('editorial_controls') or {}
    keyword_quality_active = True
    trace_controls = manifest.get('traceability_controls') or {}
    if not editorial_controls or not trace_controls:
        ctx.report.error('WDV-EDT-011', 'Profils de contrôle déclaratifs absents du manifeste', path='manifest.json')
    if not editorial_controls.get('summary_style') or not editorial_controls.get('summary_style_review_path'):
        ctx.report.error('WDV-EDT-013', 'Contrôles de style des résumés absents du manifeste', path='manifest.json')
    summary_cfg = editorial_controls.get('summary_style') or {}
    required_119 = {'opening_title_similarity_enabled', 'opening_similarity_threshold', 'opening_max_extra_significant_words', 'quantitative_claim_review_required'}
    missing_119 = sorted(required_119 - set(summary_cfg))
    invalid_119 = sorted((key for key in ('opening_title_similarity_enabled', 'quantitative_claim_review_required') if key in summary_cfg and summary_cfg.get(key) is not True))
    if missing_119 or invalid_119:
        ctx.report.error('WDV-EDT-013', 'Configuration éditoriale courante incomplète ou désactivée', path='manifest.json', details={'missing': missing_119, 'must_be_true': invalid_119})
    nodes = [n for n in (registry.get('graph') or {}).get('nodes', []) if n.get('status') == 'active']
    title_metrics: dict[str, Any] = {}
    classification_metrics: dict[str, Any] = {}
    summary_counts: dict[str, Any] = {}
    title_quality_counts = {'fr': 0, 'en': 0}
    keyword_quality_counts = {'fr': 0, 'en': 0}
    page_map = {(p.get('page_id'), p.get('language')): p for p in manifest.get('pages', [])}
    differential_translation = bool(editorial_controls.get('translation_validation_mode') == 'differential')

    def source_page_preexisting(node_id: Any, language: str) -> bool:
        target = page_map.get((node_id, language))
        if language == 'en' and differential_translation:
            source = page_map.get((node_id, 'fr'))
            if source is not None:
                return source.get('page_origin') == 'preexisting'
        return bool(target and target.get('page_origin') == 'preexisting')
    vocab_fr, vocab_en = _load_keyword_vocabulary(ctx, editorial_controls)
    from .source_preservation import source_keywords
    preserved_keywords = source_keywords(ctx)
    capitalization_vocabularies = (('fr', vocab_fr),) if english_deferred else (('fr', vocab_fr), ('en', vocab_en))
    for language, vocabulary in capitalization_vocabularies:
        folded: dict[str, str] = {}
        for term, entry in vocabulary.items():
            previous = folded.get(term.casefold())
            preserved_case_variant = bool(
                language == 'fr'
                and previous in preserved_keywords
                and term in preserved_keywords
            )
            if previous is not None and previous != term and not preserved_case_variant:
                ctx.report.error('WDV-EDT-023', 'Entrées de vocabulaire ne différant que par la casse', path=editorial_controls.get('keyword_vocabulary_path'), details={'language': language, 'first': previous, 'second': term})
            folded[term.casefold()] = term
            localized = _localized_keyword_entry(entry, language)
            kind = str(localized.get('kind') or '')
            expected_policy = {'noun': 'lowercase_common', 'noun_phrase': 'lowercase_common', 'proper_name': 'canonical_proper_name', 'acronym': 'canonical_acronym'}.get(kind)
            if localized.get('capitalization_policy') != expected_policy:
                ctx.report.error('WDV-EDT-023', 'Politique de capitalisation du mot-clé absente ou incohérente', path=editorial_controls.get('keyword_vocabulary_path'), details={'language': language, 'keyword': term, 'kind': kind, 'expected_policy': expected_policy, 'actual_policy': localized.get('capitalization_policy')})
            reasons = keyword_capitalization_issues(term, kind)
            if reasons and not (language == 'fr' and term in preserved_keywords):
                ctx.report.error('WDV-EDT-023', 'Capitalisation non canonique du mot-clé', path=editorial_controls.get('keyword_vocabulary_path'), details={'language': language, 'keyword': term, 'kind': kind, 'reasons': reasons})
            rationale_field = 'capitalization_rationale' if language == 'fr' else 'capitalization_rationale_en'
            rationale = str(entry.get(rationale_field) or '').strip()
            if kind in {'proper_name', 'acronym'} and len(rationale) < 12:
                ctx.report.error('WDV-EDT-023', 'Majuscule canonique insuffisamment justifiée', path=editorial_controls.get('keyword_vocabulary_path'), details={'language': language, 'keyword': term, 'kind': kind})
            if kind in {'noun', 'noun_phrase'} and rationale:
                ctx.report.error('WDV-EDT-023', 'Justification de majuscule inattendue pour un nom commun', path=editorial_controls.get('keyword_vocabulary_path'), details={'language': language, 'keyword': term})
    if vocab_fr:
        concept_entries = list({id(entry): entry for entry in vocab_fr.values()}.values())
        present_ids = [str(entry.get('concept_id') or '').strip() for entry in concept_entries]
        if any(present_ids):
            if any(not cid for cid in present_ids) or len(present_ids) != len(set(present_ids)) or any(not re.fullmatch(r'KWD-[A-F0-9]{12,64}', cid) for cid in present_ids):
                ctx.report.error('WDV-EDT-033', 'concept_id des mots-clés absent, dupliqué ou invalide dans un vocabulaire courant', path=editorial_controls.get('keyword_vocabulary_path'))
    # La politique courante des titres affichés est cumulative : l’identité avec le titre canonique
    # est permise lorsqu’elle est déjà la meilleure formulation; aucune dérogation versionnée ne l’active.
    identity_exception_ids: set[str] = set()
    identity_exception_cfg = editorial_controls.get('displayed_title_identity_exception') or {}
    editorial_languages = ('fr',) if english_deferred else ('fr', 'en')
    for lang in editorial_languages:
        assessed_nodes = [
            node for node in nodes
            if lang != 'en' or not reuses_existing_english_page(node)
        ]
        ratio = title_copy_ratio(assessed_nodes, lang)
        exact_ids = {str(node.get('id')) for node in assessed_nodes if ((node.get(lang) or {}).get('canonical_title') or '').strip() and ((node.get(lang) or {}).get('canonical_title') or '').strip().casefold() == ((node.get(lang) or {}).get('displayed_title') or '').strip().casefold()}
        exempt = identity_exception_ids if identity_exception_cfg.get('language') == lang else set()
        effective_exact = exact_ids - exempt
        effective_ratio = len(effective_exact) / len(assessed_nodes) if assessed_nodes else 1.0
        title_metrics[lang] = ratio
        title_metrics[f'{lang}_effective_after_owner_exception'] = effective_ratio
        title_metrics[f'{lang}_owner_exception_count'] = len(exact_ids & exempt)
        cratio = dominant_classification_ratio(assessed_nodes, lang)
        classification_metrics[lang] = cratio
        keyword_sets = [tuple((node.get(lang) or {}).get('keywords') or []) for node in assessed_nodes]
        dominant_keyword_set_ratio = Counter(keyword_sets).most_common(1)[0][1] / len(keyword_sets) if keyword_sets else 1.0
        generated_keyword_sets = [
            tuple((node.get(lang) or {}).get('keywords') or [])
            for node in assessed_nodes if not source_page_preexisting(node.get('id'), lang)
        ]
        generated_dominant_keyword_set_ratio = (
            Counter(generated_keyword_sets).most_common(1)[0][1] / len(generated_keyword_sets)
            if generated_keyword_sets else 0.0
        )
        threshold = 0.25
        if generated_keyword_sets and generated_dominant_keyword_set_ratio > threshold:
            ctx.report.error('WDV-EDT-008', 'Un même jeu de mots-clés attribué par Wikidéb’IA domine mécaniquement le corpus', path=ctx.core_paths()['registry'], details={'language': lang, 'ratio': generated_dominant_keyword_set_ratio, 'threshold': threshold, 'source_profile': 'generated'})
        elif dominant_keyword_set_ratio > threshold:
            ctx.report.info('WDV-EDT-008', 'Un même jeu historique de mots-clés dépasse 25 % du corpus ; signal de revue non bloquant', path=ctx.core_paths()['registry'], details={'language': lang, 'ratio': dominant_keyword_set_ratio, 'threshold': threshold, 'source_profile': 'historical'})
        bad_summary = 0
        for node in assessed_nodes:
            node_id = node.get('id')
            data = node.get(lang) or {}
            page = page_map.get((node_id, lang))
            preexisting_page = bool(page and page.get('page_origin') == 'preexisting')
            source_preexisting = source_page_preexisting(node_id, lang)
            canonical_title = data.get('canonical_title') or ''
            marker_engine_active = str((manifest.get('editorial_controls') or {}).get('semantic_marker_engine_version') or '') in {'1.0', '1.1', '1.2', '1.3'}
            if lang == 'en' and differential_translation and marker_engine_active:
                fr_canonical = (node.get('fr') or {}).get('canonical_title') or ''
                canonical_losses = bilingual_semantic_marker_losses(fr_canonical, canonical_title)
                canonical_structure = bilingual_semantic_structure_signals(fr_canonical, canonical_title)
                if canonical_losses:
                    ctx.report.info('WDV-BIL-007', 'Marqueurs sémantiques français possiblement perdus dans le titre canonique anglais ; revue bilingue requise', path=ctx.core_paths()['registry'], details={'node_id': node_id, 'field': 'canonical_title', 'fr_text': fr_canonical, 'en_text': canonical_title, 'marker_families': canonical_losses})
                if canonical_structure:
                    ctx.report.info('WDV-BIL-008', 'Structure sémantique FR→EN possiblement déplacée dans le titre canonique ; revue humaine requise', path=ctx.core_paths()['registry'], details={'node_id': node_id, 'field': 'canonical_title', 'fr_text': fr_canonical, 'en_text': canonical_title, 'signals': canonical_structure})
            canonical_quote_reasons = []
            if COMPLEX_QUOTES.search(canonical_title):
                canonical_quote_reasons.append('complex_quotes')
            if canonical_title.count('"') % 2:
                canonical_quote_reasons.append('unbalanced_quotes')
            if canonical_quote_reasons:
                title_quality_counts[lang] += 1
                ctx.report.error('WDV-EDT-009', 'Guillemets non conformes dans un titre canonique', path=ctx.core_paths()['registry'], details={'node_id': node_id, 'language': lang, 'title': canonical_title, 'reasons': canonical_quote_reasons})
            title = data.get('displayed_title') or ''
            reasons = displayed_title_issues(title, lang)
            if source_preexisting or differential_translation:
                allowed_historical_reasons = {'too_short', 'lowercase_initial'}
                if source_preexisting:
                    allowed_historical_reasons.add('ellipsis')
                reasons = [reason for reason in reasons if reason not in allowed_historical_reasons]
            if reasons:
                title_quality_counts[lang] += 1
                ctx.report.error('WDV-EDT-007', 'Titre affiché tronqué, mal formé ou grammaticalement incomplet', path=ctx.core_paths()['registry'], details={'node_id': node_id, 'language': lang, 'title': title, 'reasons': reasons})
            argument_reasons = displayed_title_argument_issues(title, lang)
            individual = _individual_review_entry(ctx, str(node_id))
            manual_argument_ok = isinstance(individual, dict) and individual.get(f'displayed_title_complete_proposition_{lang}') is True and individual.get(f'displayed_title_argument_intelligible_{lang}') is True
            if (lang == 'fr' and differential_translation) or (source_preexisting and not differential_translation):
                # Validated French source and pre-existing wiki pages are historical
                # baselines, not targets for retroactive enforcement of creation-only
                # complete-proposition rules. Obvious malformed-title checks above remain.
                argument_reasons = []
            elif lang == 'en' and differential_translation:
                fr_title = (node.get('fr') or {}).get('displayed_title') or ''
                argument_reasons = displayed_title_translation_form_regression(fr_title, title)
                if isinstance(individual, dict) and individual.get('displayed_title_source_form_reviewed_en') is True and individual.get('displayed_title_no_formal_regression_en') is True and individual.get('displayed_title_source_form_en') == individual.get('displayed_title_target_form_en') and individual.get('displayed_title_target_form_en') in {'nominal_phrase', 'thematic_label', 'question', 'other'}:
                    argument_reasons = []
                if (
                    isinstance(individual, dict)
                    and individual.get('displayed_title_source_form_reviewed_en') is True
                    and individual.get('displayed_title_no_formal_regression_en') is True
                    and individual.get('displayed_title_source_form_en') == 'proposition'
                    and individual.get('displayed_title_target_form_en') == 'proposition'
                    and individual.get('displayed_title_complete_proposition_en') is True
                    and individual.get('displayed_title_argument_intelligible_en') is True
                ):
                    argument_reasons = []
                marker_losses = bilingual_title_marker_losses(fr_title, title) if marker_engine_active else []
                structure_signals = bilingual_semantic_structure_signals(fr_title, title) if marker_engine_active else []
                if marker_losses:
                    ctx.report.info('WDV-BIL-007', 'Marqueurs sémantiques français possiblement perdus dans le titre anglais ; revue bilingue requise avant toute correction', path=ctx.core_paths()['registry'], details={'node_id': node_id, 'fr_title': fr_title, 'en_title': title, 'marker_families': marker_losses})
                if structure_signals:
                    ctx.report.info('WDV-BIL-008', 'Structure sémantique FR→EN possiblement déplacée dans le titre affiché ; revue humaine requise', path=ctx.core_paths()['registry'], details={'node_id': node_id, 'field': 'displayed_title', 'fr_text': fr_title, 'en_text': title, 'signals': structure_signals})
            # A manual proposition/intelligibility attestation may resolve a heuristic
            # absolute-form warning, but it must not waive a differential FR→EN
            # regression detected against the authoritative source.
            manual_override = manual_argument_ok and not (lang == 'en' and differential_translation)
            if argument_reasons and not manual_override:
                title_quality_counts[lang] += 1
                ctx.report.error('WDV-EDT-021', 'Titre affiché non propositionnel ou argument incompréhensible', path=ctx.core_paths()['registry'], details={'node_id': node_id, 'language': lang, 'title': title, 'reasons': argument_reasons, 'validation_mode': 'differential' if (lang == 'en' and differential_translation) else 'absolute'})
            concision_reasons = [reason for reason in displayed_title_concision_issues(canonical_title, title) if reason != 'exact_copy']
            manual_concision_ok = isinstance(individual, dict) and individual.get(f'displayed_title_concision_reviewed_{lang}') is True and individual.get(f'displayed_title_semantic_equivalence_reviewed_{lang}') is True
            if concision_reasons and not manual_concision_ok and not source_preexisting and not differential_translation:
                title_quality_counts[lang] += 1
                ctx.report.error('WDV-EDT-001', 'Titre affiché plus long que le titre canonique', path=ctx.core_paths()['registry'], details={'node_id': node_id, 'language': lang, 'canonical_title': canonical_title, 'displayed_title': title, 'reasons': concision_reasons})
            keywords = data.get('keywords') or []
            historical_keyword_values: set[str] = set()
            if source_preexisting and lang == 'fr':
                lock_entry = _fr_metadata_lock_entry(ctx, str(node_id))
                preservation = lock_entry.get('preexisting_keyword_preservation') if isinstance(lock_entry, dict) else None
                if isinstance(preservation, dict) and isinstance(preservation.get('historical_final_keywords'), list):
                    historical_keyword_values = {str(value) for value in preservation.get('historical_final_keywords') or []}
                elif not ctx.exists('data/fr_page_metadata_lock.json'):
                    historical_keyword_values = {str(value) for value in keywords}
            # Only the numerical creation quota is provenance-sensitive.
            # Intrinsic quality rules apply to the complete final historical list too.
            vocabulary = vocab_fr if lang == 'fr' else vocab_en
            allowed_long_keywords: set[str] = set()
            if vocabulary:
                for keyword in keywords:
                    entry = vocabulary.get(keyword)
                    if entry and not keyword_atomicity_issues(
                        keyword,
                        _localized_keyword_entry(entry, lang),
                        lang,
                        require_composition_attestation=True,
                    ):
                        allowed_long_keywords.add(keyword)
            kw_reasons = keyword_form_issues(
                keywords,
                enforce_count=not source_preexisting,
                allowed_long_keywords=allowed_long_keywords,
            )
            if 'duplicates' in kw_reasons:
                from types import SimpleNamespace
                from .schema_validation import _preserved_keyword_duplicates
                index = (registry.get('graph') or {}).get('nodes', []).index(node)
                proof = SimpleNamespace(validator='uniqueItems', absolute_path=['graph','nodes',index,lang,'keywords'])
                if _preserved_keyword_duplicates(ctx, 'argument_registry.schema.json', registry, proof):
                    kw_reasons.remove('duplicates')
            if kw_reasons:
                keyword_quality_counts[lang] += 1
                ctx.report.error('WDV-EDT-008', 'Jeu de mots-clés mal formé', path=ctx.core_paths()['registry'], details={'node_id': node_id, 'language': lang, 'keywords': keywords, 'reasons': kw_reasons})
            if vocab_fr or vocab_en:
                vocabulary = vocab_fr if lang == 'fr' else vocab_en
                for keyword in keywords:
                    entry = vocabulary.get(keyword)
                    if not entry:
                        keyword_quality_counts[lang] += 1
                        ctx.report.error('WDV-EDT-008', 'Mot-clé absent du vocabulaire éditorial contrôlé', path=ctx.core_paths()['registry'], details={'node_id': node_id, 'language': lang, 'keyword': keyword})
                    elif _localized_keyword_entry(entry, lang).get('kind') not in ALLOWED_KEYWORD_KINDS:
                        keyword_quality_counts[lang] += 1
                        ctx.report.error('WDV-EDT-008', "Mot-clé qui n'est ni un nom ni un groupe nominal", path=editorial_controls.get('keyword_vocabulary_path'), details={'node_id': node_id, 'language': lang, 'keyword': keyword, 'kind': _localized_keyword_entry(entry, lang).get('kind')})
                if keyword_quality_active:
                    for keyword in keywords:
                        entry = vocabulary.get(keyword)
                        atomicity_reasons = keyword_atomicity_issues(keyword, _localized_keyword_entry(entry, lang), lang, require_composition_attestation=True)
                        if atomicity_reasons:
                            keyword_quality_counts[lang] += 1
                            ctx.report.error('WDV-EDT-025', 'Mot-clé non atomique ou exception multi-mots insuffisamment justifiée', path=editorial_controls.get('keyword_vocabulary_path'), details={'node_id': node_id, 'language': lang, 'keyword': keyword, 'reasons': atomicity_reasons})
                if lang == 'fr' and (not english_deferred) and not reuses_existing_english_page(node):
                    en_keywords = (node.get('en') or {}).get('keywords') or []
                    if len(keywords) == len(en_keywords):
                        for fr_keyword, en_keyword in zip(keywords, en_keywords):
                            entry = vocab_fr.get(fr_keyword)
                            if entry and entry.get('en') != en_keyword:
                                keyword_quality_counts[lang] += 1
                                ctx.report.error('WDV-EDT-008', 'Traduction de mot-clé divergente du vocabulaire contrôlé', path=ctx.core_paths()['registry'], details={'node_id': node_id, 'fr': fr_keyword, 'actual_en': en_keyword, 'expected_en': entry.get('en')})
                    else:
                        keyword_quality_counts[lang] += 1
                        ctx.report.error('WDV-EDT-008', 'Nombre de mots-clés divergent dans la paire bilingue', path=ctx.core_paths()['registry'], details={'node_id': node_id, 'fr_count': len(keywords), 'en_count': len(en_keywords)})
            if not page:
                continue
            tmpl = _parse_page(ctx, page.get('file_path'))
            decision = _summary_review_decision(ctx, str(node_id), lang)
            manual_summary_ok = isinstance(decision, dict) and decision.get('status') in {'approved','revised'} and decision.get('thesis_first') is True and decision.get('no_polemical_overstatement') is True and decision.get('originality_reviewed') is True
            if tmpl and (node_id, lang) not in _protected_historical_summary_keys(ctx) | _historically_absent_summary_keys(ctx) | _owner_removed_summary_keys(ctx) and summary_has_auto_objection(_summary(tmpl, lang), lang) and not manual_summary_ok:
                bad_summary += 1
                ctx.report.error('WDV-EDT-003', 'Le résumé se termine par une auto-objection, une concession ou du métadiscours', path=page.get('file_path'))
        summary_counts[lang] = bad_summary
        title_metrics[f'{lang}_dominant_keyword_set_ratio'] = dominant_keyword_set_ratio
        title_metrics[f'{lang}_generated_dominant_keyword_set_ratio'] = generated_dominant_keyword_set_ratio
    if vocab_fr:
        vocab_path = editorial_controls.get('keyword_vocabulary_path')
        if len(vocab_fr) < 8:
            ctx.report.error('WDV-EDT-008', 'Vocabulaire de navigation à l’échelle du wiki insuffisant', path=vocab_path, details={'terms': len(vocab_fr), 'minimum': 8})
        actual_usage_fr = Counter((k for node in nodes for k in (node.get('fr') or {}).get('keywords') or []))
        for keyword, count in sorted(actual_usage_fr.items()):
            entry = vocab_fr.get(keyword) or {}
            if entry.get('scope') != 'site_navigation' or entry.get('cross_debate_reusable') is not True:
                ctx.report.error('WDV-EDT-008', 'Portée inter-débat du mot-clé non attestée', path=vocab_path, details={'keyword': keyword, 'scope': entry.get('scope'), 'cross_debate_reusable': entry.get('cross_debate_reusable')})
            if entry.get('local_frequency_is_validity_criterion') is not False:
                ctx.report.error('WDV-EDT-008', 'La fréquence locale est utilisée à tort comme critère d’admissibilité', path=vocab_path, details={'keyword': keyword})
            if entry and entry.get('usage_count_in_debate') != count:
                ctx.report.error('WDV-EDT-008', 'Fréquence descriptive du vocabulaire divergente du registre', path=vocab_path, details={'keyword': keyword, 'declared': entry.get('usage_count_in_debate'), 'actual': count})
    summary_ratio_errors = 0
    if not english_deferred:
        for node in nodes:
            node_id = node.get('id')
            fr_page = page_map.get((node_id, 'fr'))
            en_page = page_map.get((node_id, 'en'))
            if not fr_page or not en_page:
                continue
            fr_tmpl = _parse_page(ctx, fr_page.get('file_path'))
            en_tmpl = _parse_page(ctx, en_page.get('file_path'))
            if not fr_tmpl or not en_tmpl:
                continue
            absent_keys = _historically_absent_summary_keys(ctx) | _owner_removed_summary_keys(ctx)
            if (node_id, 'fr') in absent_keys or (node_id, 'en') in absent_keys:
                continue
            fr_summary = _summary(fr_tmpl, 'fr')
            en_summary = _summary(en_tmpl, 'en')
            ratio = summary_word_ratio(fr_summary, en_summary)
            if ratio < 0.6 or ratio > 1.45:
                historical_source = source_page_preexisting(node_id, 'en') or (node_id, 'fr') in _protected_historical_summary_keys(ctx)
                decision = _summary_review_decision(ctx, str(node_id), 'en')
                ratio_reviewed = isinstance(decision, dict) and decision.get('summary_ratio_reviewed') is True
                rationale = str((decision or {}).get('summary_ratio_exception_rationale') or '').strip() if isinstance(decision, dict) else ''
                if historical_source and ratio_reviewed and len(rationale) >= 24:
                    ctx.report.info('WDV-BIL-006', 'Ratio EN/FR atypique d’un résumé historique revu et explicitement justifié', details={'node_id': node_id, 'word_ratio_en_over_fr': ratio, 'historical_source': True, 'rationale': rationale})
                else:
                    summary_ratio_errors += 1
                    ctx.report.error('WDV-BIL-006', 'Asymétrie substantielle probable entre les résumés français et anglais', details={'node_id': node_id, 'word_ratio_en_over_fr': ratio, 'historical_source': historical_source, 'ratio_reviewed': ratio_reviewed})
    pagination_errors, date_errors = _validate_documentary_registry(ctx)
    docs = _validate_debate_docs(ctx, manifest, editorial_controls, norm)
    intro_refs = _validate_intro_references(ctx, manifest, editorial_controls)
    normative_non_regression = _validate_normative_non_regression(ctx, manifest, trace_controls)
    individual_review = _validate_individual_editorial_review(ctx, nodes, editorial_controls)
    summary_style = _validate_summary_style(ctx, nodes, manifest, editorial_controls, norm)
    graph_placement_review = _validate_graph_placement_review(ctx, registry, editorial_controls, norm)
    introduction_review = _validate_introduction_review(ctx, manifest, editorial_controls, norm)
    date_migration_errors = _validate_dates(ctx, manifest, editorial_controls.get('creation_date'), editorial_controls.get('creation_date_policy', 'per_page_preserved'))
    trace = _validate_traceability(ctx, manifest, editorial_controls, trace_controls)
    semantic_convergence = _validate_semantic_convergence(ctx, editorial_controls, english_deferred)
    ctx.report.metrics['editorial'] = {'active_nodes': len(nodes), 'canonical_display_copy_ratio': {k: v for k, v in title_metrics.items() if not k.endswith('dominant_keyword_set_ratio')}, 'dominant_keyword_set_ratio': {lang: title_metrics.get(f'{lang}_dominant_keyword_set_ratio') for lang in editorial_languages}, 'generated_dominant_keyword_set_ratio': {lang: title_metrics.get(f'{lang}_generated_dominant_keyword_set_ratio') for lang in editorial_languages}, 'displayed_title_quality_errors': title_quality_counts, 'keyword_quality_errors': keyword_quality_counts, 'dominant_classification_ratio': classification_metrics, 'summary_auto_objections': summary_counts, 'summary_bilingual_ratio_errors': summary_ratio_errors, 'documentary_pagination_errors': pagination_errors, 'documentary_access_date_errors': date_errors, 'debate_documentation': docs, 'introduction_references': intro_refs, 'normative_non_regression': normative_non_regression, 'individual_editorial_review': individual_review, 'graph_placement_review': graph_placement_review, 'summary_style': summary_style, 'introduction_review': introduction_review, 'creation_date_errors': date_migration_errors, 'traceability': trace, 'semantic_convergence': semantic_convergence, 'english_translation_status': english_translation_status(manifest), 'english_translation_deferred': english_deferred}
    editorial_errors = any((f.level in {'ERROR', 'WARNING'} and (f.code.startswith('WDV-EDT-') or f.code in {'WDV-BIL-006', 'WDV-BIL-009'}) for f in ctx.report.findings))
    if not editorial_errors:
        review_path = editorial_controls.get('individual_review_report_path')
        label = trace_controls.get('current_corrective_work_id', 'current')
        ctx.report.info('WDV-DOC-001', f'Revue éditoriale humaine {label} enregistrée et contrôles automatisés réussis.', path=review_path)
