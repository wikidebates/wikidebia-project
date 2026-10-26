#!/usr/bin/env python3
"""Prepare, finalize and apply the English translation review of a workspace.

This phase starts only after French metadata and content have been locked. It
collects English titles, sections, keywords, debate content, argument summaries
and documentary sources in a formal review ledger. Finalization seals the
review; application creates an atomically visible ``translated-copy/``. No
MediaWiki page is rendered and no remote access is performed.
"""

from __future__ import annotations

from wikidebia_citation_passages import blank_translations, validate_translations

from wikidebia_release_info import KIT_VERSION
from wikidebia_title_structure import canonical_title_structure_issues

import argparse
import collections
from datetime import date as calendar_date
import copy
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from wikidebia_corpus_build import (
    NORM_VERSION,
    VALIDATOR_VERSION,
    CorpusBuildError,
    canonical_json,
    exclusive_lock,
    full_tree_sha256,
    load_json,
    now_iso,
    relative_to_project,
    sha256_bytes,
    structural_sha256,
    write_json,
)
from wikidebia_documentary_resources import (
    build_file as build_documentary_resource_registry,
    normalize_doi,
    normalize_url,
)
from wikidebia_editorial_workspace import WorkspaceError, fsync_directory, validate_work_id, workspace_receipt_hash
from wikidebia_editorial_review import EditorialReviewError, _assert_source_unchanged, _load_workspace, _run_validator
from wikidebia_content_review import (
    _source_imports,
    ARGUMENT_BUCKETS,
    SOURCE_METADATA_FIELDS,
    SUMMARY_TRUE_FIELDS,
    INTRO_TRUE_FIELDS,
    NUMBER,
    META_DISCOURSE_FR,
    META_DISCOURSE_EN,
)

DISPLAYED_TITLE_FORMS = {"proposition", "question", "imperative", "thematic_label", "nominal_phrase", "doctrinal_label", "other"}
HISTORICAL_INTRO_TRANSLATION_TRUE_FIELDS = (
    "historical_source_profile_respected",
    "france_specific_context_reviewed",
    "international_context_adaptation_reviewed",
    "no_unjustified_substantive_addition",
    "english_documentation_localized",
)
HISTORICAL_INTRO_UNIVERSAL_TRUE_FIELDS = (
    "factual_claims_referenced",
    "documentation_proportionate_to_literature",
    "wikipedia_hover_links_reviewed",
    "specialized_terms_linked_or_explained",
    "documentation_orientation_reviewed",
    "youtube_authorship_reviewed",
    "reference_note_punctuation_reviewed",
    "specialized_term_inventory_reviewed",
)
NAME_SEARCH_PROVENANCE = {"actual_log", "fresh_recheck", "historical_reconstruction"}
TRANSLATION_REVIEW_SCHEMA = "wikidebia-en-translation-review-1.1"
TRANSLATION_LOCK_SCHEMA = "wikidebia-en-translation-lock-1.0"
EN_METADATA_LOCK_SCHEMA = "wikidebia-en-page-metadata-lock-1.0"
EN_CONTENT_LOCK_SCHEMA = "wikidebia-en-content-lock-1.0"
TRANSLATION_CHANGESET_SCHEMA = "wikidebia-en-translation-changeset-1.0"

_KEYWORD_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ0-9]+(?:['’][A-Za-zÀ-ÿ0-9]+)?")

def _english_keyword_form_metadata(term: str, source_entry: Mapping[str, Any]) -> dict[str, Any]:
    """Return English-localized form metadata for one controlled keyword.

    Atomicity is a property of the controlled concept, while the need for a
    multi-word exception depends on the *linguistic form in the target
    language*.  A French locution such as ``bourrage d'urnes`` may therefore
    legitimately become the ordinary two-word compound ``ballot stuffing``.
    """
    value = str(term or "").strip()
    tokens = _KEYWORD_WORD_RE.findall(value)
    source_kind = str(source_entry.get("en_kind") or source_entry.get("kind") or "")
    if source_kind in {"proper_name", "acronym"}:
        kind = source_kind
    else:
        kind = "noun" if len(tokens) <= 1 else "noun_phrase"
    capitalization_policy = {
        "noun": "lowercase_common",
        "noun_phrase": "lowercase_common",
        "proper_name": "canonical_proper_name",
        "acronym": "canonical_acronym",
    }.get(kind)
    has_connector = bool(re.search(r"\b(?:of|and|the)\b", value, flags=re.IGNORECASE))
    requires_exception = len(tokens) > 2 or has_connector
    rationale = (
        f'English lexicalized navigation concept "{value}": this phrase names one atomic category rather than a compositional intersection.'
        if requires_exception else ""
    )
    return {
        "en_kind": kind,
        "en_capitalization_policy": capitalization_policy,
        "en_atomic_concept": source_entry.get("atomic_concept") is True,
        "en_compositional_intersection": False if source_entry.get("compositional_intersection") is False else source_entry.get("compositional_intersection"),
        "en_multiword_exception": requires_exception,
        "en_multiword_exception_rationale": rationale,
    }
EN_SOURCES_WORKING_SCHEMA = "wikidebia-en-source-registry-working-1.0"
SEMANTIC_CONVERGENCE_SCHEMA = "wikidebia-semantic-convergence-review-1.1"
SEMANTIC_CONVERGENCE_SUPPORTED = {
    ("wikidebia-semantic-convergence-review-1.0", "1.0"),
    ("wikidebia-semantic-convergence-review-1.1", "1.1"),
}
SEMANTIC_CONVERGENCE_METHOD_FAMILIES = {
    "proposition_by_proposition",
    "risk_marker_review",
    "reverse_source_target",
    "field_boundary_review",
    "independent_bilingual_reread",
}

SEMANTIC_RISK_MARKERS = {
    # Keep these labels aligned with validator.editorial.SEMANTIC_MARKERS.
    "attribution": (re.compile(r"\b(?:cens[ée]e?s?|pr[ée]tendu(?:e|es|s)?|attribu[ée]e?s?|imput[ée]e?s?|selon|d['’]apr[èe]s)\b", re.I), re.compile(r"\b(?:supposed|alleged|purported|attributed|ascribed|according\s+to)\b", re.I)),
    "universal_quantifier": (re.compile(r"\b(?:tous|toutes|tout|chaque)\b", re.I), re.compile(r"\b(?:all|every|each)\b", re.I)),
    "existential_quantifier": (re.compile(r"\b(?:certains|certaines|quelques)\b", re.I), re.compile(r"\b(?:some|certain|a\s+few)\b", re.I)),
    "many_quantifier": (re.compile(r"\b(?:beaucoup|nombreux|nombreuses|innombrables)\b", re.I), re.compile(r"\b(?:many|numerous|countless|a\s+great\s+many|a\s+great\s+deal)\b", re.I)),
    "several_quantifier": (re.compile(r"\b(?:plusieurs|divers|diverses|diff[ée]rents|diff[ée]rentes)\b", re.I), re.compile(r"\b(?:several|multiple|various|different)\b", re.I)),
    "hypothesis_status": (re.compile(r"\b(?:hypoth[èe]se|supposition)\b", re.I), re.compile(r"\b(?:hypothesis|assumption|supposition)\b", re.I)),
    "interpretation_status": (re.compile(r"\b(?:interpr[èeé]t\w*|consid[èeé]r\w*|vu(?:e)?s?|lu(?:e)?s?)\b[^.!?]{0,80}\bcomme\b", re.I), re.compile(r"\b(?:interpreted|regarded|viewed|seen|understood|read)\s+as\b", re.I)),
    "strong_probative_force": (re.compile(r"\b(?:prouve|prouvent|d[ée]montre|d[ée]montrent|[ée]tablit|[ée]tablissent)\b", re.I), re.compile(r"\b(?:prove|proves|demonstrate|demonstrates|establish|establishes)\b", re.I)),
    "frequency_often": (re.compile(r"\bsouvent\b", re.I), re.compile(r"\b(?:often|frequently)\b", re.I)),
    "frequency_always": (re.compile(r"\b(?:toujours|de\s+tous\s+temps)\b", re.I), re.compile(r"\b(?:always|throughout\s+history|at\s+all\s+times)\b", re.I)),
    "necessity": (re.compile(r"\b(?:n[ée]cessaire|n[ée]cessairement|doit|doivent)\b", re.I), re.compile(r"\b(?:necessary|necessarily|must|has\s+to|have\s+to)\b", re.I)),
    "possibility": (re.compile(r"\b(?:peut|peuvent|pourrait|pourraient|possible|possiblement)\b", re.I), re.compile(r"\b(?:can|could|may|might|possible|possibly)\b", re.I)),
    "restriction_only": (re.compile(r"\b(?:seulement|uniquement|simplement)\b|\bne\b[^,.;:!?]{0,80}\bque\b", re.I), re.compile(r"\b(?:only|merely|simply|nothing\s+but)\b", re.I)),
    "negation": (re.compile(r"\b(?:ne|n['’])[^,.;:!?]{0,60}\b(?:pas|plus|jamais|aucun|aucune)\b|\b(?:sans|impossible)\b", re.I), re.compile(r"\b(?:not|no|never|without|impossible|cannot|can't|doesn't|don't|isn't|aren't|won't|wouldn't|couldn't)\b", re.I)),
    "condition": (re.compile(r"\b(?:si|m[êe]me\s+si|[àa]\s+condition\s+que)\b", re.I), re.compile(r"\b(?:if|even\s+if|provided\s+that|assuming\s+that)\b", re.I)),
    "causal_link": (re.compile(r"\b(?:car|parce\s+que|puisque|en\s+raison\s+de)\b", re.I), re.compile(r"\b(?:because|since|because\s+of|due\s+to)\b", re.I)),
    "consequence_link": (re.compile(r"\b(?:donc|par\s+cons[ée]quent|ce\s+qui|ainsi)\b", re.I), re.compile(r"\b(?:therefore|thus|hence|so|which)\b", re.I)),
    "concession": (re.compile(r"\b(?:m[êe]me\s+si|bien\s+que|quoique|cependant|n[ée]anmoins)\b", re.I), re.compile(r"\b(?:even\s+if|although|though|however|nevertheless)\b", re.I)),
    "comparison": (re.compile(r"\b(?:plus|moins|davantage|autant|mieux|pire)\b", re.I), re.compile(r"\b(?:more|less|fewer|greater|better|worse|as\s+much|as\s+many)\b", re.I)),
    "strong_intensity": (re.compile(r"\b(?:tr[èe]s|parfaitement|[ée]norm[ée]ment|fortement|radicalement)\b", re.I), re.compile(r"\b(?:very|perfectly|enormously|strongly|radically|far\s+more)\b", re.I)),
    "immediacy": (re.compile(r"\b(?:aussit[oô]t|imm[ée]diatement)\b", re.I), re.compile(r"\b(?:at\s+once|immediately|straightaway)\b", re.I)),
}

def _field_sha256(value: Any) -> str:
    return sha256_bytes(str(value or "").encode("utf-8"))

def _proposition_edges(value: Any) -> tuple[str, str]:
    text = _plain(str(value or "")).strip()
    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    if not parts:
        return "", ""
    return parts[0], parts[-1]

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


def _semantic_risk_signals(fr_text: Any, en_text: Any) -> list[str]:
    fr = _plain(str(fr_text or ""))
    en = _plain(str(en_text or ""))
    risks = [f"marker_loss:{label}" for label, (fr_pattern, en_pattern) in SEMANTIC_RISK_MARKERS.items() if fr_pattern.search(fr) and not en_pattern.search(en)]
    if META_DISCOURSE_EN.search(en) and not META_DISCOURSE_FR.search(fr):
        risks.append("metadiscourse_added_in_english")
    if SEMANTIC_RISK_MARKERS["strong_probative_force"][0].search(fr) and re.search(r"\b(?:support|supports|suggest|suggests|indicate|indicates|show|shows|evidence)\b", en, re.I) and not SEMANTIC_RISK_MARKERS["strong_probative_force"][1].search(en):
        risks.append("probative_force_weakened")
    if SEMANTIC_RISK_MARKERS["causal_link"][0].search(fr) and SEMANTIC_RISK_MARKERS["condition"][1].search(en) and not SEMANTIC_RISK_MARKERS["causal_link"][1].search(en):
        risks.append("causal_relation_shifted_to_condition")
    if re.search(r"\bsur\s+Terre\b", fr, re.I) and not re.search(r"\bon\s+Earth\b", en, re.I):
        risks.append("earth_scope_anchor_lost")
    if re.search(r"\b(?:existence|pr[ée]sence)\s+de\s+la\s+vie\b", fr, re.I) and re.search(r"\borigin\s+of\s+life\b", en, re.I):
        risks.append("life_existence_shifted_to_origin")
    if re.search(r"\b(?:un|une|aucun|aucune|quelque|des)\s+dieu(?:x)?\b", fr, re.I) and re.search(r"\bGod\b", en) and not re.search(r"\b(?:a|an|no|any|some)\s+god\b|\bgods\b", en, re.I):
        risks.append("generic_deity_to_proper_God")
    for label, fr_pattern, en_pattern in SEMANTIC_LEXICAL_RISK_PAIRS:
        if fr_pattern.search(fr) and not en_pattern.search(en):
            risks.append(label)
    return sorted(set(risks))

def semantic_content_payload(review: Mapping[str, Any]) -> dict[str, Any]:
    final = review.get("final_values") or {}
    debate_final = final.get("debate") or {}
    debate_source = ((review.get("debate") or {}).get("french") or {})
    payload: dict[str, Any] = {
        "debate": {
            "fr_metadata": debate_source.get("metadata") or {},
            "fr_content": debate_source.get("content") or {},
            "en": {key: debate_final.get(key) for key in ("canonical_title", "topic", "complete_topic", "introduction")},
        },
        "arguments": [],
    }
    original_by_id = {str(item.get("id")): item for item in review.get("arguments") or [] if isinstance(item, dict)}
    for arg in sorted(final.get("arguments") or [], key=lambda row: str(row.get("id"))):
        node_id = str(arg.get("id"))
        source = (((original_by_id.get(node_id) or {}).get("translation") or {}).get("french") or {})
        payload["arguments"].append({
            "id": node_id,
            "fr_metadata": source.get("metadata") or {},
            "fr_summary": (source.get("content") or {}).get("summary"),
            "en_canonical_title": arg.get("canonical_title"),
            "en_displayed_title": arg.get("displayed_title"),
            "en_summary": arg.get("summary"),
        })
    for item, arg in zip(payload["arguments"], sorted(final.get("arguments") or [], key=lambda row: str(row.get("id")))):
        original = original_by_id.get(str(arg.get("id"))) or {}
        french = (((original.get("translation") or {}).get("french") or {}).get("content") or {})
        if french.get("citation_passages") or arg.get("citation_passages"):
            item["fr_citation_passages"] = copy.deepcopy(french.get("citation_passages") or [])
            item["en_citation_passages"] = copy.deepcopy(arg.get("citation_passages") or [])
        if french.get("citations") or arg.get("citations"):
            item["fr_citations"] = copy.deepcopy(french.get("citations") or [])
            item["en_citations"] = copy.deepcopy(arg.get("citations") or [])
        if arg.get("relation_labels"):
            item["relation_labels"] = copy.deepcopy(arg["relation_labels"])
        if arg.get("dedicated_debate"):
            item["en_dedicated_debate"] = arg["dedicated_debate"]
    if debate_final.get("relation_labels"):
        payload["debate"]["relation_labels"] = copy.deepcopy(debate_final["relation_labels"])
    return payload

def semantic_content_sha256(review: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json(semantic_content_payload(review)))


def semantic_convergence_receipt_sha256(receipt: Mapping[str, Any]) -> str:
    data = copy.deepcopy(dict(receipt))
    data.pop("receipt_sha256", None)
    return sha256_bytes(canonical_json(data))


def verify_semantic_convergence_receipt(receipt: Mapping[str, Any], review: Mapping[str, Any]) -> None:
    review_sha = str(review.get("review_sha256") or "")
    semantic_sha = semantic_content_sha256(review)
    schema_pair = (str(receipt.get("schema") or ""), str(receipt.get("schema_version") or ""))
    if schema_pair not in SEMANTIC_CONVERGENCE_SUPPORTED:
        raise TranslationReviewError("Schéma du reçu de convergence sémantique invalide")
    if receipt.get("translation_review_sha256") != review_sha or receipt.get("semantic_content_sha256") != semantic_sha:
        raise TranslationReviewError("Le reçu de convergence sémantique ne vise plus la revue scellée courante")
    if receipt.get("receipt_sha256") != semantic_convergence_receipt_sha256(receipt):
        raise TranslationReviewError("Empreinte du reçu de convergence sémantique invalide")
    passes = receipt.get("passes") or []
    if receipt.get("status") != "converged" or not isinstance(passes, list) or len(passes) < 2:
        raise TranslationReviewError("Deux passes sémantiques convergentes sont requises avant application")
    first, second = passes[-2], passes[-1]
    for row in (first, second):
        if row.get("new_certain_errors") != 0 or row.get("translation_review_sha256") != review_sha or row.get("semantic_content_sha256") != semantic_sha:
            raise TranslationReviewError("Les deux dernières passes de convergence doivent viser le même contenu et constater zéro nouvelle erreur certaine")
    if str(first.get("method") or "").strip().casefold() == str(second.get("method") or "").strip().casefold():
        raise TranslationReviewError("Les deux passes finales de convergence doivent employer des méthodes distinctes")
    if schema_pair[1] == "1.1":
        families = [str(row.get("method_family") or "").strip() for row in (first, second)]
        if any(family not in SEMANTIC_CONVERGENCE_METHOD_FAMILIES for family in families):
            raise TranslationReviewError("Les passes de convergence 1.1 doivent déclarer une famille de méthode normalisée")
        if families[0] == families[1]:
            raise TranslationReviewError("Les deux passes finales de convergence doivent appartenir à des familles de méthodes distinctes")

EN_PAGE_LIFECYCLE_PARAMETERS = {
    # Existing-page metadata is opaque.  These fields describe the imported
    # page state and must not be cleaned up by a translation/generation profile.
    "debate": ("progress", "title-warnings", "debate-warnings", "related-debates", "creation-date"),
    "argument": (
        "initialization", "established-name", "name", "title-warnings", "argument-warnings", "summary-warnings",
        "reference-warnings", "justification-warnings", "objection-warnings",
        "dedicated-debate", "creation-date",
    ),
}


def _validate_page_lifecycle(row: Mapping[str, Any], page_type: str, label: str) -> dict[str, Any]:
    origin = row.get("page_origin", "new")
    if origin not in {"new", "preexisting"}:
        raise TranslationReviewError(f"Origine de page invalide pour {label}")
    raw = row.get("preserved_parameters") or {}
    if not isinstance(raw, dict):
        raise TranslationReviewError(f"Paramètres préservés invalides pour {label}")
    allowed = EN_PAGE_LIFECYCLE_PARAMETERS[page_type]
    if page_type == "argument" and "detailed-debate" in raw and "dedicated-debate" not in raw:
        raw = dict(raw)
        raw["dedicated-debate"] = raw.pop("detailed-debate")
    if set(raw) - set(allowed):
        raise TranslationReviewError(f"Paramètre préservé inconnu pour {label}")
    if origin == "new":
        if raw:
            raise TranslationReviewError(f"Une page nouvelle ne peut pas déclarer de paramètres préservés : {label}")
        return {"page_origin": "new", "preserved_parameters": {}}
    if set(raw) != set(allowed):
        raise TranslationReviewError(f"L’état antérieur des paramètres doit être complet pour {label}")
    clean: dict[str, dict[str, Any]] = {}
    for name in allowed:
        state = raw.get(name)
        if not isinstance(state, dict) or not isinstance(state.get("present"), bool):
            raise TranslationReviewError(f"État antérieur invalide pour {label}/{name}")
        value = state.get("value")
        if state["present"]:
            if not isinstance(value, str) or not value.strip():
                raise TranslationReviewError(f"Valeur antérieure absente pour {label}/{name}")
            clean[name] = {"present": True, "value": value}
        else:
            if value is not None:
                raise TranslationReviewError(f"Une valeur ne peut être fournie pour un paramètre absent : {label}/{name}")
            clean[name] = {"present": False, "value": None}
    return {"page_origin": "preexisting", "preserved_parameters": clean}

SECTION_MAP = {
    "Aménagement": "Planning", "Culture": "Culture", "Droit": "Law", "Écologie": "Ecology",
    "Économie": "Economy", "Éducation": "Education", "Éthique": "Ethics", "Géopolitique": "Geopolitics",
    "Histoire": "History", "Philosophie": "Philosophy", "Politique": "Politics", "Psychologie": "Psychology",
    "Religion et spiritualité": "Religion and spirituality", "Santé": "Health", "Science": "Science",
    "Société": "Society", "Sport et loisirs": "Sport and leisure", "Technologie": "Technology",
}
EN_SECTIONS = set(SECTION_MAP.values())
DEBATE_BUCKETS = {
    "pro-bibliography": ("bibliography", "pro_reference"),
    "con-bibliography": ("bibliography", "con_reference"),
    "bibliography": ("bibliography", "neutral_reference"),
    "pro-webliography": ("webliography", "pro_reference"),
    "con-webliography": ("webliography", "con_reference"),
    "webliography": ("webliography", "neutral_reference"),
    "pro-videography": ("videography", "pro_reference"),
    "con-videography": ("videography", "con_reference"),
    "videography": ("videography", "neutral_reference"),
}
SOURCE_ID = re.compile(r"^S[0-9]{5,}$")
HTTP_URL = re.compile(r"^https?://", re.I)
BAD_QUOTES = re.compile(r"[«»“”„‹›]")
BAD_TITLE_APOSTROPHES = re.compile(r"[’‘ʼ＇]")
BAD_ELLIPSIS = re.compile(r"\.\.\.|…")
QUESTION_TOPIC = re.compile(r"^(?:whether\b|should\b|must\b|is\b|are\b|does\b|do\b|can\b)", re.I)

FRENCH_TEMPLATE_NAMES = {
    "Sous-partie", "Article Wikipédia", "Argument pour", "Argument contre",
    "Référence bibliographique", "Référence bibliographique pour", "Référence bibliographique contre",
    "Référence sitographique", "Référence sitographique pour", "Référence sitographique contre",
    "Référence vidéographique", "Référence vidéographique pour", "Référence vidéographique contre",
    "Lien Wikipédia", "Lien interlangue", "Débat connexe", "Citation",
}
FRENCH_TEMPLATE_RE = re.compile(
    r"\{\{\s*(" + "|".join(re.escape(name) for name in sorted(FRENCH_TEMPLATE_NAMES, key=len, reverse=True)) + r")(?:\s*[|}])",
    re.I,
)
FRENCH_PARAMETER_NAMES = {
    "titre", "contenu", "texte-affiché", "auteurs", "ouvrage", "numéro", "localisation",
    "édition", "lieu", "lien", "avertissements", "titre-affiché", "langue", "citation",
    "avertissements-citation", "résumé", "rubriques", "mots-clés", "date-création",
}
FRENCH_PARAMETER_RE = re.compile(
    r"\|\s*(" + "|".join(re.escape(name) for name in sorted(FRENCH_PARAMETER_NAMES, key=len, reverse=True)) + r")\s*=",
    re.I,
)

def _assert_english_wikicode_localized(value: str, label: str) -> None:
    template = FRENCH_TEMPLATE_RE.search(value)
    if template:
        raise TranslationReviewError(f"Modèle français interdit dans {label} : {template.group(1)}")
    parameter = FRENCH_PARAMETER_RE.search(value)
    if parameter:
        raise TranslationReviewError(f"Paramètre français interdit dans {label} : {parameter.group(1)}")

TRANSLATED_CITATION_WARNING = "AI-translated quote"
FR_MONTHS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}
EN_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
CITATION_CONTROLLED_NAMES = {"citation", "date", "avertissements-citation", "avertissements citation", "avertissements"}
CITATION_PARAMETER_MAP = {
    "citation": "quote",
    "auteurs": "authors",
    "article": "article",
    "ouvrage": "work",
    "volume": "volume",
    "numéro": "issue",
    "numero": "issue",
    "page": "page",
    "localisation": "location",
    "édition": "publisher",
    "edition": "publisher",
    "lieu": "place",
    "date": "date",
    "lien": "link",
    "avertissements citation": "warnings",
    "avertissements": "warnings",
}


def _citation_warning(existing: Any) -> str:
    value = str(existing or "").strip().strip(",").strip()
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if TRANSLATED_CITATION_WARNING not in parts:
        parts.append(TRANSLATED_CITATION_WARNING)
    return ", ".join(parts)


def _date_signature(value: Any, language: str) -> tuple[int, int | None, int | None] | None:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return None
    if re.fullmatch(r"\d{4}", text) and int(text) > 0:
        return (int(text), None, None)
    months = dict(FR_MONTHS if language == "fr" else EN_MONTHS)
    months.update({
        "jan": 1, "janv": 1, "feb": 2, "febr": 2, "févr": 2, "fevr": 2,
        "mar": 3, "apr": 4, "avr": 4, "jun": 6, "june": 6, "juin": 6,
        "jul": 7, "juil": 7, "aug": 8, "sep": 9, "sept": 9,
        "oct": 10, "nov": 11, "dec": 12, "déc": 12,
    })
    month_range = re.fullmatch(
        r"([A-Za-zÀ-ÿ]+)\s*[-–]\s*([A-Za-zÀ-ÿ]+)\s+(\d{4})", text, re.I
    )
    if month_range and all(month.casefold() in months for month in month_range.group(1, 2)):
        # A negative third component distinguishes a month range from a day.
        return (int(month_range.group(3)), months[month_range.group(1).casefold()], -months[month_range.group(2).casefold()])
    if language == "fr":
        text = re.sub(r"^1er(?=[/.\s])", "1", text, flags=re.I)
        # Historical French imports also use day/month/year and month/year.
        numeric = re.fullmatch(r"(\d{1,2})([/.])(\d{1,2})\2(\d{2}|\d{4})", text)
        if numeric:
            day, month, year = int(numeric[1]), int(numeric[3]), int(numeric[4])
            if year < 100:
                year += 2000 if year < 70 else 1900
            try:
                calendar_date(year, month, day)
            except ValueError:
                return None
            return (year, month, day)
        numeric_month = re.fullmatch(r"(\d{1,2})/(\d{4})", text)
        if numeric_month:
            month, year = int(numeric_month[1]), int(numeric_month[2])
            if 1 <= month <= 12 and year > 0:
                return (year, month, None)
            return None
        text = re.sub(r"([A-Za-zÀ-ÿ]+)\.(?=\s)", r"\1", text)
    else:
        months.update({name[:3]: number for name, number in EN_MONTHS.items()})
        months["sept"] = 9
        text = re.sub(r"([A-Za-z]+)\.(?=\s)", r"\1", text)
        # Published English quotations may already have an English date.
        match = re.fullmatch(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", text, re.I)
        if match and match[1].casefold() in months:
            try:
                day = calendar_date(int(match[3]), months[match[1].casefold()], int(match[2]))
            except ValueError:
                return None
            return (day.year, day.month, day.day)
    match = re.fullmatch(r"(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\s+(\d{4})", text, re.I)
    if match and match.group(2).casefold() in months:
        year, month, day = int(match.group(3)), months[match.group(2).casefold()], int(match.group(1))
        try:
            calendar_date(year, month, day)
        except ValueError:
            return None
        return (year, month, day)
    match = re.fullmatch(r"([A-Za-zÀ-ÿ]+)\s+(\d{4})", text, re.I)
    if match and match.group(1).casefold() in months and int(match.group(2)) > 0:
        return (int(match.group(2)), months[match.group(1).casefold()], None)
    return None


def _citation_source_text(source: Mapping[str, Any]) -> str:
    for parameter in source.get("source_parameters") or []:
        if not isinstance(parameter, Mapping):
            continue
        name = re.sub(r"[ _-]+", " ", str(parameter.get("name") or "").strip().casefold())
        if name == "citation":
            return str(parameter.get("value") or "")
    return str(source.get("citation") or "")


def _lexical_word_count(value: str) -> int:
    return len(re.findall(r"[A-Za-zÀ-ÿ0-9]+(?:['’\-][A-Za-zÀ-ÿ0-9]+)*", _plain(value or "")))


def _blank_citation(source: Mapping[str, Any]) -> dict[str, Any]:
    source_date = str(source.get("date") or "").strip()
    return {
        "id": source.get("id"),
        "source": copy.deepcopy(source),
        "status": "pending",
        "translated_citation": "",
        "translated_date": source_date if re.fullmatch(r"\d{4}", source_date) else "",
        "citation_translated": False,
        "date_translated_or_language_neutral": False,
        "preserved_parameters_unchanged": False,
        "documentary_parameter_overrides": [],
        "translation_warning_appended": False,
        "quote_completeness_reviewed": False,
        "quote_completeness_note": "",
        "quote_low_ratio_reviewed": False,
        "quote_low_ratio_note": "",
        "reviewer": "",
        "reviewed_at": None,
        "note": "",
    }


def _citation_documentary_overrides(
    row: Mapping[str, Any], source: Mapping[str, Any], citation_id: str,
) -> dict[str, dict[str, str]]:
    """Validate a target-wiki-safe replacement of an archive.is wrapper."""
    raw = row.get("documentary_parameter_overrides") or []
    if not isinstance(raw, list):
        raise TranslationReviewError(f"Surcharges documentaires invalides pour {citation_id}")
    source_values = {
        re.sub(r"[ _-]+", " ", str(item.get("name") or "").strip().casefold()): str(item.get("value") or "")
        for item in source.get("source_parameters") or [] if isinstance(item, Mapping)
    }
    result: dict[str, dict[str, str]] = {}
    for item in raw:
        if not isinstance(item, Mapping):
            raise TranslationReviewError(f"Surcharge documentaire invalide pour {citation_id}")
        source_name = re.sub(r"[ _-]+", " ", str(item.get("source_name") or "").strip().casefold())
        output_name = str(item.get("output_name") or "").strip()
        source_value = str(item.get("source_value") or "").strip()
        translated_value = str(item.get("translated_value") or "").strip()
        reason = str(item.get("reason") or "").strip()
        if source_name != "lien" or output_name != "link" or source_name in result:
            raise TranslationReviewError(f"Seul un remplacement lien→link unique est autorisé pour {citation_id}")
        if source_values.get(source_name) != source_value or len(reason) < 20:
            raise TranslationReviewError(f"Provenance ou justification de surcharge invalide pour {citation_id}")
        match = re.fullmatch(r"https?://archive\.is/[^/]+/(https?://.+)", source_value, re.I)
        if not match or translated_value != match.group(1):
            raise TranslationReviewError(
                f"La surcharge de {citation_id} doit reprendre exactement l’URL originale incluse dans archive.is"
            )
        result[source_name] = {
            "source_name": "lien", "output_name": "link", "source_value": source_value,
            "translated_value": translated_value, "reason": reason,
        }
    return result


def _validate_citations(rows: Any, french_rows: Sequence[Mapping[str, Any]], node_id: str) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        raise TranslationReviewError(f"Liste de citations anglaises absente pour {node_id}")
    expected = {str(row.get("id")): row for row in french_rows}
    if {str(row.get("id")) for row in rows if isinstance(row, dict)} != set(expected):
        raise TranslationReviewError(f"Les citations anglaises ne couvrent pas exactement les citations françaises de {node_id}")
    final: list[dict[str, Any]] = []
    by_id = {str(row.get("id")): row for row in rows}
    for citation_id, source in expected.items():
        row = by_id[citation_id]
        if row.get("source") != source:
            raise TranslationReviewError(f"Les paramètres source de la citation {citation_id} ont été modifiés")
        if row.get("status") != "approved":
            raise TranslationReviewError(f"Traduction de citation non approuvée : {citation_id}")
        translated = _text(row.get("translated_citation"), f"citation traduite {citation_id}", 2)
        source_date = str(source.get("date") or "").strip()
        translated_date = str(row.get("translated_date") or "").strip()
        if not source_date and translated_date:
            raise TranslationReviewError(f"Une date a été inventée pour la citation {citation_id}")
        if source_date:
            if not translated_date:
                raise TranslationReviewError(f"Date anglaise absente pour la citation {citation_id}")
            fr_sig = _date_signature(source_date, "fr") or _date_signature(source_date, "en")
            numeric_expression = re.fullmatch(r"[0-9\s()/.,–—-]+", source_date) is not None
            short_year_date = re.fullmatch(r"\d{1,2}[/.]\d{1,2}[/.]\d{2}", source_date) is not None
            opaque_numeric_date = numeric_expression and (fr_sig is None or short_year_date)
            preserved_numeric_date = translated_date == source_date and numeric_expression
            if opaque_numeric_date and translated_date != source_date:
                raise TranslationReviewError(
                    f"Format de date source non reconnu pour {citation_id}; conservation exacte requise : {source_date}"
                )
            if fr_sig is None and not preserved_numeric_date:
                raise TranslationReviewError(f"Format de date source non reconnu pour {citation_id}; revue nécessaire : {source_date}")
            en_sig = _date_signature(translated_date, "en")
            if preserved_numeric_date:
                # Preserve bibliographic expressions (year/issue, two edition
                # years, short years) without guessing a calendar date.
                en_sig = fr_sig
            if en_sig != fr_sig:
                raise TranslationReviewError(f"La date traduite ne désigne pas la même date pour {citation_id}")
        for field in ("citation_translated", "date_translated_or_language_neutral", "preserved_parameters_unchanged", "translation_warning_appended", "quote_completeness_reviewed"):
            if row.get(field) is not True:
                raise TranslationReviewError(f"Attestation de citation manquante pour {citation_id} : {field}")
        completeness_note = _text(row.get("quote_completeness_note"), f"note de complétude de citation {citation_id}", 12)
        source_words = _lexical_word_count(_citation_source_text(source))
        translated_words = _lexical_word_count(translated)
        lexical_ratio = (translated_words / source_words) if source_words else None
        low_ratio_reviewed = bool(row.get("quote_low_ratio_reviewed"))
        low_ratio_note = str(row.get("quote_low_ratio_note") or "").strip()
        if lexical_ratio is not None and source_words >= 8 and lexical_ratio < 0.60:
            if not low_ratio_reviewed or len(low_ratio_note) < 12:
                raise TranslationReviewError(
                    f"La citation {citation_id} est très courte par rapport à la source ; une seconde revue explicite de complétude est requise"
                )
        _text(row.get("reviewer"), f"relecteur de citation {citation_id}", 3)
        _text(row.get("reviewed_at"), f"date de revue de citation {citation_id}", 10)
        _text(row.get("note"), f"note de revue de citation {citation_id}", 8)
        warning = _citation_warning(source.get("avertissements-citation"))
        documentary_overrides = _citation_documentary_overrides(row, source, citation_id)
        output_parameters: list[dict[str, str]] = []
        warning_inserted = False
        for parameter in source.get("source_parameters") or []:
            source_name = str(parameter.get("name") or "").strip()
            normalized = re.sub(r"[ _-]+", " ", source_name.casefold())
            output_name = CITATION_PARAMETER_MAP.get(normalized)
            if output_name is None:
                raise TranslationReviewError(
                    f"Paramètre français de citation sans équivalent anglais déclaré pour {citation_id} : {source_name}"
                )
            if output_name == "quote":
                output_value = translated
            elif output_name == "date":
                output_value = translated_date
            elif output_name == "warnings":
                if warning_inserted:
                    continue
                output_value = warning
                warning_inserted = True
            else:
                override = documentary_overrides.get(normalized)
                output_value = override["translated_value"] if override else str(parameter.get("value") or "")
            output_parameters.append({
                "name": output_name,
                "value": output_value,
                "source_name": source_name,
            })
        if not warning_inserted:
            output_parameters.append({
                "name": "warnings",
                "value": warning,
                "source_name": "avertissements-citation",
            })
        final.append({
            "id": citation_id,
            "source_template": source.get("source_template") or "Citation",
            "output_template": "Quote",
            "quote": translated,
            "date": translated_date,
            "warnings": warning,
            "parameter_name_mapping": copy.deepcopy(CITATION_PARAMETER_MAP),
            "preserved_parameters": copy.deepcopy(source.get("preserved_parameters") or []),
            "documentary_parameter_overrides": list(documentary_overrides.values()),
            "parameters": output_parameters,
            "source": copy.deepcopy(source),
            "source_word_count": source_words,
            "translated_word_count": translated_words,
            "lexical_ratio": lexical_ratio,
            "quote_completeness_reviewed": True,
            "quote_completeness_note": completeness_note,
            "quote_low_ratio_reviewed": low_ratio_reviewed,
            "quote_low_ratio_note": low_ratio_note,
            "reviewer": row.get("reviewer"),
            "reviewed_at": row.get("reviewed_at"),
            "note": row.get("note"),
        })
    return final


class TranslationReviewError(EditorialReviewError):
    pass


def _reuses_existing_english_page(node: Mapping[str, Any]) -> bool:
    wiki = ((((node.get("pages") or {}).get("en") or {}).get("wiki") or {}))
    en = node.get("en") or {}
    return (
        wiki.get("check_status") == "equivalent_existing"
        and wiki.get("decision") == "reuse_existing"
        and bool(en.get("canonical_title"))
        and en.get("title_status") == "locked"
    )


def translation_review_sha256(review: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(review))
    body.pop("review_sha256", None)
    return sha256_bytes(canonical_json(body))


def _text(value: Any, label: str, minimum: int = 1) -> str:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        raise TranslationReviewError(f"{label} est absent ou trop court")
    return value.strip()


def _strings(value: Any, label: str, *, allow_source_duplicates: bool = False) -> list[str]:
    if not isinstance(value, list):
        raise TranslationReviewError(f"{label} doit être une liste")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise TranslationReviewError(f"{label} contient une valeur vide")
        clean = item.strip()
        if clean in result and not allow_source_duplicates:
            raise TranslationReviewError(f"{label} contient un doublon : {clean}")
        result.append(clean)
    return result


def _plain(value: str) -> str:
    value = re.sub(r"<ref\b[^>]*>.*?</ref>|<ref\b[^>]*/>", " ", value or "", flags=re.I | re.S)
    value = re.sub(r"\{\{[^{}]*\}\}|\[\[[^\]]+\]\]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _assert_content_copy(workspace: Path, meta: Mapping[str, Any]) -> Path:
    source = workspace / "content-reviewed-copy"
    if not source.is_dir() or source.is_symlink():
        raise TranslationReviewError("content-reviewed-copy absent ou non sûr")
    expected = str((meta.get("content_reviewed_copy") or {}).get("tree_sha256") or "")
    actual = full_tree_sha256(source)
    if not expected or actual != expected:
        raise TranslationReviewError("content-reviewed-copy a changé depuis le verrouillage français")
    if (source / "output").exists():
        raise TranslationReviewError("Des pages finales existent déjà dans content-reviewed-copy")
    for required in ("data/fr_page_metadata_lock.json", "data/fr_content_lock.json", "data/keyword_vocabulary.json"):
        if not (source / required).is_file():
            raise TranslationReviewError(f"Verrou français requis absent : {required}")
    return source


def _french_source_page_origin(fr_meta: Mapping[str, Any], fr_content: Mapping[str, Any]) -> str:
    """Return the editorial origin of the authoritative French source page.

    This is intentionally distinct from ``page_origin`` in the English review,
    which describes the lifecycle of the target English page.  Creation-only
    editorial rules follow the French source origin, not the fact that the
    translated target will usually be a newly created page.
    """
    values = [
        str(fr_meta.get("page_origin") or "").strip(),
        str(fr_content.get("page_origin") or "").strip(),
    ]
    declared = [value for value in values if value in {"new", "preexisting"}]
    if len(set(declared)) > 1:
        raise TranslationReviewError("Provenance française incohérente entre verrous de métadonnées et de contenu")
    if declared:
        return declared[0]
    # Compatibility for locks prepared before page_origin was propagated.
    # Historical summary/introduction provenance is sufficient evidence that
    # the source is a pre-existing wiki page; otherwise keep the creation
    # profile rather than silently inventing historical provenance.
    if str(fr_content.get("summary_provenance") or "").startswith("historical_"):
        return "preexisting"
    if str(fr_content.get("introduction_provenance") or "").startswith("historical_"):
        return "preexisting"
    return "new"


def _requires_relation_label_review(
    metadata_lock: Mapping[str, Any], content_lock: Mapping[str, Any],
) -> bool:
    """Require occurrence labels whenever the complete French graph is historical."""
    if content_lock.get("source_preservation_policy"):
        return True
    meta_arguments = {
        str(row.get("entity_id") or row.get("id")): row
        for row in metadata_lock.get("arguments") or []
        if isinstance(row, Mapping)
    }
    content_arguments = {
        str(row.get("id")): row
        for row in content_lock.get("arguments") or []
        if isinstance(row, Mapping)
    }
    if not content_arguments or set(meta_arguments) != set(content_arguments):
        return False
    origins = [
        _french_source_page_origin(
            metadata_lock.get("debate") or {}, content_lock.get("debate") or {},
        )
    ]
    origins.extend(
        _french_source_page_origin(meta_arguments[node_id], content_arguments[node_id])
        for node_id in sorted(content_arguments)
    )
    return all(origin == "preexisting" for origin in origins)


def _source_snapshot(source: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    registry = load_json(source / "data/registre_debat.json", "registre du débat")
    metadata = load_json(source / "data/fr_page_metadata_lock.json", "verrou des métadonnées françaises")
    content = load_json(source / "data/fr_content_lock.json", "verrou du contenu français")
    _, _, imported = _source_imports(source)
    if content.get("source_preservation_policy"):
        from wikidebia_translation_source import verify_frozen_source
        verify_frozen_source(source, metadata, content)
    locked = {r["id"]: r for r in content.get("arguments") or []}
    for row in imported:
        if (locked.get(row["id"], {}).get("citation_passages") or []) != (row.get("citation_passages") or []):
            raise TranslationReviewError("Verrou français incomplet pour les passages hors Citation : " + row["id"] + "; reprendre la revue française")
    vocabulary = load_json(source / "data/keyword_vocabulary.json", "vocabulaire français")
    return registry, metadata, content, vocabulary


def _blank_debate(fr_meta: Mapping[str, Any], fr_content: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": "pending",
        "page_origin": "new",
        "source_page_origin": _french_source_page_origin(fr_meta, fr_content),
        "preserved_parameters": {},
        "canonical_title": "",
        "topic": "",
        "complete_topic": "",
        "sections": [],
        "keywords": [],
        "introduction": "",
        "subsections": [],
        "specialized_term_inventory": [],
        "wikipedia_articles": [],
        "documentation": {bucket: [] for bucket in DEBATE_BUCKETS},
        "documentation_family_notes": {"bibliography": "", "webliography": "", "videography": ""},
        "topic_label_rationale": "",
        "complete_topic_initial_capital_justification": None,
        "metadata_equivalent_to_french": False,
        "content_equivalent_to_french": False,
        "canonical_title_semantic_inventory_reviewed": False,
        "canonical_title_semantic_inventory_note": "",
        "topic_semantic_equivalence_reviewed": False,
        "complete_topic_semantic_equivalence_reviewed": False,
        "introduction_claim_inventory_reviewed": False,
        "introduction_claim_inventory_note": "",
        "subsection_structure_equivalence_reviewed": False,
        "debate_field_semantic_risk_reviewed": False,
        "debate_field_semantic_risk_note": "",
        "debate_field_semantic_risk_evidence": [],
        "sections_exactly_mapped": False,
        "keywords_exactly_mapped": False,
        "keywords_order_preserved_by_relevance": False,
        "introduction_functionally_equivalent": False,
        "wikipedia_articles_verified": False,
        "all_debate_sources_english": False,
        "reviewer": "",
        "reviewed_at": None,
        "note": "",
        "introduction_adaptation_rationale": "",
        **{field: False for field in INTRO_TRUE_FIELDS},
        **{field: False for field in HISTORICAL_INTRO_TRANSLATION_TRUE_FIELDS},
        **{field: False for field in HISTORICAL_INTRO_UNIVERSAL_TRUE_FIELDS},
        "french": {"metadata": copy.deepcopy(fr_meta), "content": copy.deepcopy(fr_content)},
    }


def _blank_argument(fr_meta: Mapping[str, Any], fr_content: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": "pending",
        "page_origin": "new",
        "source_page_origin": _french_source_page_origin(fr_meta, fr_content),
        "preserved_parameters": {},
        "dedicated_debate": None,
        "dedicated_debate_equivalent_to_french": False,
        "dedicated_debate_review_note": "",
        "canonical_title": "",
        "displayed_title": "",
        "sections": [],
        "keywords": [],
        "summary": "",
        "citations": [_blank_citation(row) for row in (fr_content.get("citations") or [])],
        "citation_passages": blank_translations(fr_content.get("citation_passages") or []),
        "dedicated_debate": None,
        "dedicated_debate_equivalence_reviewed": False,
        "dedicated_debate_review_note": "",
        "sources": {bucket: [] for bucket in ARGUMENT_BUCKETS},
        "argument_name_search_queries": [],
        "argument_name_search_scope_note": "",
        "argument_name_search_provenance": "",
        "argument_name_search_provenance_note": "",
        "argument_name_outcome": "pending",
        "argument_name": None,
        "argument_name_evidence": [],
        "argument_name_same_reasoning_confirmed": False,
        "argument_name_non_invented_label_confirmed": False,
        "argument_name_language_fit_confirmed": False,
        "argument_name_rationale": "",
        "argument_name_page_reasoning_scope_summary": "",
        "argument_name_literature_scope_summary": "",
        "argument_name_scope_relation": "",
        "argument_name_scope_identity_confirmed": False,
        "metadata_equivalent_to_french": False,
        "summary_equivalent_to_french": False,
        "canonical_title_semantic_inventory_reviewed": False,
        "canonical_title_semantic_inventory_note": "",
        "canonical_title_equivalent_to_french": False,
        "canonical_title_subject_preserved": False,
        "canonical_title_predicate_preserved": False,
        "canonical_title_scope_preserved": False,
        "canonical_title_modality_preserved": False,
        "sections_exactly_mapped": False,
        "keywords_exactly_mapped": False,
        "keywords_order_preserved_by_relevance": False,
        "title_is_idiomatic": False,
        "displayed_title_source_form": "",
        "displayed_title_target_form": "",
        "displayed_title_source_form_reviewed": False,
        "displayed_title_no_formal_regression": False,
        "displayed_title_semantic_inventory_reviewed": False,
        "displayed_title_semantic_inventory_note": "",
        "displayed_title_subject_preserved": False,
        "displayed_title_predicate_preserved": False,
        "displayed_title_scope_preserved": False,
        "displayed_title_modality_preserved": False,
        "displayed_title_is_complete_proposition": False,
        "displayed_title_concision_reviewed": False,
        "displayed_title_semantically_equivalent": False,
        "displayed_title_improves_readability_when_distinct": False,
        "displayed_title_translates_french_displayed_title": False,
        "displayed_title_identity_pattern_reviewed": False,
        "displayed_title_identity_pattern_note": "",
        "displayed_title_form_change_reviewed": False,
        "displayed_title_speech_act_preserved": False,
        "displayed_title_form_change_note": "",
        "summary_ratio_reviewed": False,
        "summary_ratio_exception_rationale": "",
        "summary_subject_predicate_scope_modality_reviewed": False,
        "summary_opening_proposition_preserved": False,
        "summary_closing_proposition_preserved": False,
        "summary_conditions_exclusivities_preserved": False,
        "summary_decisive_premises_preserved": False,
        "summary_semantic_evidence_note": "",
        "semantic_risk_reviewed": False,
        "semantic_risk_note": "",
        "semantic_risk_evidence": [],
        "forceful_expression": "",
        "quantitative_claims_verified": False,
        "quantitative_claims_note": "",
        "historical_quantitative_transfer_reviewed": False,
        "historical_quantitative_transfer_note": "",
        "documentation_rationale": "",
        "reviewer": "",
        "reviewed_at": None,
        "note": "",
        **{field: False for field in SUMMARY_TRUE_FIELDS},
        "french": {"metadata": copy.deepcopy(fr_meta), "content": copy.deepcopy(fr_content)},
    }


def _translation_risk_profile(fr_meta: Mapping[str, Any], fr_content: Mapping[str, Any]) -> dict[str, Any]:
    """Estimate review density from the immutable French source.

    The score allocates human review effort; it is never a quality grade and
    never authorizes automatic rewriting.  Only source-side observable factors
    are used so the plan exists before English drafting begins.
    """
    factors: list[dict[str, Any]] = []
    score = 0
    citations = list(fr_content.get("citations") or [])
    if citations:
        points = min(6, len(citations) * 2)
        score += points
        factors.append({"factor": "citations", "count": len(citations), "points": points})
    long_citations = 0
    for row in citations:
        text = str((row or {}).get("citation") or (row or {}).get("text") or "")
        if len(re.findall(r"\b[\wÀ-ÿ'-]+\b", text)) >= 120:
            long_citations += 1
    if long_citations:
        points = min(4, long_citations * 2)
        score += points
        factors.append({"factor": "long_citations", "count": long_citations, "points": points})
    source_count = sum(len(v or []) for v in (fr_content.get("sources") or {}).values()) if isinstance(fr_content.get("sources"), dict) else 0
    if source_count:
        points = min(5, source_count)
        score += points
        factors.append({"factor": "documentary_sources", "count": source_count, "points": points})
    summary = str(fr_content.get("summary") or "")
    words = len(re.findall(r"\b[\wÀ-ÿ'-]+\b", summary))
    if words >= 220:
        score += 4; factors.append({"factor": "long_summary", "count": words, "points": 4})
    elif words >= 120:
        score += 2; factors.append({"factor": "long_summary", "count": words, "points": 2})
    logical = re.findall(r"\b(?:si|même\s+si|donc|car|parce\s+que|cependant|néanmoins|seulement|uniquement|tous|certains|souvent|toujours|nécessaire|possible|attribu[ée]e?s?|selon)\b", summary, re.I)
    if len(logical) >= 6:
        score += 2; factors.append({"factor": "logical_marker_density", "count": len(logical), "points": 2})
    numbers = re.findall(r"(?<!\w)\d+(?:[.,]\d+)?(?!\w)", summary)
    if numbers:
        score += 1; factors.append({"factor": "quantitative_claims", "count": len(numbers), "points": 1})
    preserved = fr_meta.get("preserved_parameters") or {}
    if isinstance(preserved, dict) and str(preserved.get("name") or "").strip():
        score += 2; factors.append({"factor": "conventional_name_present_in_source", "count": 1, "points": 2})
    if score >= 12:
        level, unit = "very_high", 5
    elif score >= 8:
        level, unit = "high", 6
    elif score >= 4:
        level, unit = "medium", 8
    else:
        level, unit = "low", 10
    return {"score": score, "level": level, "recommended_unit_size": unit, "factors": factors}


def _build_translation_review_units(argument_rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    target = 10
    severity = {"low": 0, "medium": 1, "high": 2, "very_high": 3}
    def close() -> None:
        nonlocal current, target
        if not current:
            return
        max_level = max((row["review_risk"]["level"] for row in current), key=lambda x: severity[x])
        units.append({
            "id": f"U{len(units)+1:03d}",
            "page_ids": [row["id"] for row in current],
            "target_size": target,
            "max_risk_level": max_level,
            "status": "pending",
            "reviewer": "",
            "reviewed_at": None,
            "note": "",
        })
        current = []
        target = 10
    for row in argument_rows:
        rec = int(row["review_risk"]["recommended_unit_size"])
        if current and len(current) >= min(target, rec):
            close()
        current.append(row)
        target = min(target, rec)
        if len(current) >= target:
            close()
    close()
    return units


def prepare_review(project_root: Path, debate_id: str, work_id: str, *, overwrite: bool = False) -> dict[str, Any]:
    workspace, meta = _load_workspace(project_root, debate_id, work_id)
    if meta.get("status") not in {"fr_content_applied", "fr_source_preserved", "en_translation_review_ready"}:
        raise TranslationReviewError(f"Statut incompatible avec la préparation anglaise : {meta.get('status')}")
    _assert_source_unchanged(project_root, debate_id, meta)
    source = _assert_content_copy(workspace, meta)
    readiness = load_json(workspace / "reviews/en/translation_readiness.json", "préparation anglaise")
    if readiness.get("status") != "ready_for_translation" and not (overwrite and meta.get("status") == "en_translation_review_ready" and readiness.get("status") == "translation_review_in_progress"):
        raise TranslationReviewError("La préparation anglaise n’est pas ouverte")
    review_path = workspace / "reviews/en/translation_review.json"
    sources_path = workspace / "data/sources_en_working.json"
    if review_path.exists() and not overwrite:
        current = load_json(review_path, "revue anglaise")
        return {"status": "en_translation_review_ready", "debate_id": debate_id, "work_id": work_id, "arguments": len(current.get("arguments") or []), "idempotent": True}
    if overwrite and (workspace / "translated-copy").exists():
        raise TranslationReviewError("Impossible de régénérer une traduction déjà appliquée")
    registry, metadata_lock, content_lock, vocabulary = _source_snapshot(source)
    fr_meta_by_id = {str(row.get("entity_id")): row for row in metadata_lock.get("arguments") or []}
    fr_content_by_id = {str(row.get("id")): row for row in content_lock.get("arguments") or []}
    active_nodes = [node for node in ((registry.get("graph") or {}).get("nodes") or []) if node.get("status") == "active"]
    active_ids = [str(node.get("id")) for node in active_nodes]
    translation_ids = [
        str(node.get("id"))
        for node in active_nodes
        if not _reuses_existing_english_page(node)
    ]
    if set(active_ids) != set(fr_meta_by_id) or set(active_ids) != set(fr_content_by_id):
        raise TranslationReviewError("Les verrous français ne couvrent pas exactement les arguments actifs")
    now = now_iso()
    review = {
        "schema": TRANSLATION_REVIEW_SCHEMA,
        "schema_version": "1.1",
        "normative_revision": NORM_VERSION,
        "kit_version": KIT_VERSION,
        "debate_id": debate_id,
        "work_id": work_id,
        "source_language": "fr",
        "target_language": "en",
        "status": "draft",
        "prepared_at": now,
        "prepared_content_reviewed_copy_sha256": full_tree_sha256(source),
        "french_metadata_review_sha256": metadata_lock.get("review_sha256"),
        "french_content_review_sha256": content_lock.get("review_sha256"),
        "section_mapping": copy.deepcopy(SECTION_MAP),
        "vocabulary": [
            {
                "concept_id": row.get("concept_id"), "fr": row.get("fr"), "en": row.get("en") or "", "definition_en": "",
                "kind": row.get("kind"), "capitalization_policy": row.get("capitalization_policy"),
                "capitalization_verified": False, "capitalization_rationale_en": "",
                "status": "pending", "idiomatic_equivalent": False, "same_concept": False,
                "reviewer": "", "reviewed_at": None, "note": "",
                "usages": copy.deepcopy(row.get("usages") or []),
            }
            for row in vocabulary.get("entries") or []
        ],
        "debate": _blank_debate(metadata_lock.get("debate") or {}, content_lock.get("debate") or {}),
        "arguments": [],
        "review_units": [],
        "global_review": {
            "reviewer": "", "reviewed_at": None,
            "all_entities_translated": False, "all_equivalences_reviewed": False,
            "all_selected_sources_verified": False, "relations_and_occurrences_unchanged": False,
            "no_final_pages_generated": True, "remote_access_not_used": True,
            "blocking_issues": [], "note": "",
        },
        "review_sha256": None,
    }
    review["arguments"] = [
        {"id": node_id, "review_risk": _translation_risk_profile(fr_meta_by_id[node_id], fr_content_by_id[node_id]), "translation": _blank_argument(fr_meta_by_id[node_id], fr_content_by_id[node_id])}
        for node_id in translation_ids
    ]
    if (
        _requires_relation_label_review(metadata_lock, content_lock)
        or _historical_relation_labels_required(content_lock)
    ):
        from wikidebia_translation_source import relation_labels_from_source
        reused_ids = set(active_ids) - set(translation_ids)
        review["relation_labels"] = [
            {**r, "translated_text": "", "equivalent_to_french": False, "review_note": ""}
            for r in relation_labels_from_source(
                source, exclude_target_node_ids=reused_ids
            )
        ]
    review["review_units"] = _build_translation_review_units(review["arguments"])
    unit_by_page = {page_id: unit["id"] for unit in review["review_units"] for page_id in unit["page_ids"]}
    for item in review["arguments"]:
        item["review_unit_id"] = unit_by_page[item["id"]]
    write_json(review_path, review)
    write_json(sources_path, {
        "schema": EN_SOURCES_WORKING_SCHEMA,
        "source_registry_version": "1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "status": "draft",
        "prepared_at": now,
        "sources": [],
    })
    write_json(workspace / "audits/en_translation_inventory.json", {
        "schema": "wikidebia-en-translation-inventory-1.0",
        "debate_id": debate_id, "work_id": work_id, "generated_at": now,
        "arguments": len(translation_ids),
        "reused_existing_arguments": len(active_ids) - len(translation_ids),
        "vocabulary_entries": len(review["vocabulary"]),
        "review_units": len(review["review_units"]),
        "risk_levels": dict(collections.Counter(item["review_risk"]["level"] for item in review["arguments"])),
        "french_sources": len((load_json(source / "data/sources.json", "sources françaises").get("sources") or [])),
        "boundaries": {"automatic_translation": False, "final_pages_generated": False, "remote_access": False},
    })
    (workspace / "audits/en_translation_inventory.md").write_text(
        "\n".join(["# English translation inventory", "", f"- Debate: `{debate_id}`", f"- Arguments to translate: {len(translation_ids)}", f"- Existing English arguments reused: {len(active_ids) - len(translation_ids)}", f"- Controlled terms: {len(review['vocabulary'])}", "", "No automatic translation or final page generation was performed.", ""]),
        encoding="utf-8", newline="\n",
    )
    meta = copy.deepcopy(meta)
    meta["kit_version"] = KIT_VERSION
    meta["status"] = "en_translation_review_ready"
    meta.setdefault("artifacts", {})["english_translation_review"] = "reviews/en/translation_review.json"
    meta["artifacts"]["english_sources_working"] = "data/sources_en_working.json"
    meta["artifacts"]["translated_copy"] = "translated-copy"
    meta["english_translation_review"] = {"status": "prepared", "prepared_at": now, "prepared_content_reviewed_copy_sha256": review["prepared_content_reviewed_copy_sha256"]}
    meta["boundaries"]["english_translation_started"] = True
    meta["boundaries"]["final_pages_generated"] = False
    meta["workspace_sha256"] = None
    meta["workspace_sha256"] = workspace_receipt_hash(meta)
    write_json(workspace / "workspace.json", meta)
    readiness["status"] = "translation_review_in_progress"
    for item in readiness.get("items") or []:
        item["translation_status"] = (
            "reuse_existing_english_page"
            if item.get("entity_type") == "argument"
            and str(item.get("entity_id") or item.get("id") or item.get("page_id") or "")
            not in set(translation_ids)
            else "translation_review_in_progress"
        )
    write_json(workspace / "reviews/en/translation_readiness.json", readiness)
    return {"status": "en_translation_review_ready", "debate_id": debate_id, "work_id": work_id, "review_path": relative_to_project(review_path, project_root), "sources_path": relative_to_project(sources_path, project_root), "arguments": len(translation_ids), "reused_existing_arguments": len(active_ids) - len(translation_ids), "automatic_translation": False, "final_pages_generated": False}


LEGACY_SOURCE_VERIFICATION_KEYS = {"checked_at", "method", "note"}
SOURCE_DOCUMENT_KINDS = {
    "book", "monograph", "handbook", "edited_volume", "synthesis_report", "review_article",
    "journal_article", "book_chapter", "conference_paper", "thesis", "legal_text", "other",
}
DEBATE_BIBLIOGRAPHY_SCOPES = {"foundational_work", "broad_synthesis"}


def _fold_documentary(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def collect_english_documentary_findings(review: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Collect documentary defects that would make the finalized source registry fail.

    This guard exists for translation reviews finalized by older kit versions that
    accepted a looser ``sources_en_working.json`` contract than the canonical
    ``data/sources.json`` registry.  Findings are editorial tasks: the helper never
    invents a document kind, a debate-level scope, or an authorship attestation.
    """
    final_values = review.get("final_values") if isinstance(review, Mapping) else None
    sources = final_values.get("sources") if isinstance(final_values, Mapping) else None
    if not isinstance(sources, list):
        return []
    debate_id = str(review.get("debate_id") or "")
    findings: list[dict[str, Any]] = []
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        sid = str(source.get("id") or "")
        stype = str(source.get("type") or "")
        metadata = source.get("metadata") or {}
        verification = source.get("verification") or {}
        usages = source.get("usage") or []
        if stype == "bibliography":
            debate_usages = [u for u in usages if isinstance(u, Mapping) and str(u.get("page_id") or "") == debate_id and u.get("language") == "en"]
            if debate_usages:
                kind = source.get("document_kind")
                if kind not in SOURCE_DOCUMENT_KINDS:
                    findings.append({
                        "entity_type": "source", "entity_id": sid, "field": "document_kind",
                        "issue": "debate_bibliography_document_kind_missing_or_invalid",
                        "current_value": kind,
                        "required_correction": "Record the resource's actual document_kind from the supported vocabulary. Debate-bibliography admissibility is determined by foundational/broad scope and justification, not by a closed subset of document kinds.",
                    })
                for index, usage in enumerate(usages):
                    if not isinstance(usage, Mapping) or str(usage.get("page_id") or "") != debate_id or usage.get("language") != "en":
                        continue
                    scope = usage.get("documentary_scope")
                    if scope not in DEBATE_BIBLIOGRAPHY_SCOPES:
                        findings.append({
                            "entity_type": "source", "entity_id": sid, "field": f"usage/{index}/documentary_scope",
                            "issue": "debate_bibliography_scope_missing_or_invalid",
                            "current_value": scope,
                            "required_correction": "Review whether the source is a foundational work or broad synthesis. If it is too narrow for Debate bibliography, remove it from that Debate bibliography rather than fabricating a scope.",
                        })
                    if len(str(usage.get("selection_reason") or "").strip()) < 12:
                        findings.append({
                            "entity_type": "source", "entity_id": sid, "field": f"usage/{index}/selection_reason",
                            "issue": "debate_bibliography_selection_reason_insufficient",
                            "current_value": usage.get("selection_reason"),
                            "required_correction": "Provide a specific selection rationale explaining why the source belongs in the Debate bibliography.",
                        })
        if stype in {"webliography", "videography"}:
            authors = [str(value).strip() for value in (metadata.get("authors") or []) if str(value).strip()]
            site = _fold_documentary(metadata.get("site"))
            folded_authors = [_fold_documentary(value) for value in authors]
            if verification.get("authorship_checked") is not True:
                findings.append({
                    "entity_type": "source", "entity_id": sid, "field": "verification/authorship_checked",
                    "issue": "authorship_not_checked", "current_value": verification.get("authorship_checked"),
                    "required_correction": "Verify the responsible person or organization for the Web/video content.",
                })
            if authors and verification.get("authorship_verified") is not True:
                findings.append({
                    "entity_type": "source", "entity_id": sid, "field": "verification/authorship_verified",
                    "issue": "authorship_not_explicitly_verified", "current_value": verification.get("authorship_verified"),
                    "required_correction": "Record explicit authorship verification for the listed author(s), or remove authors that are not explicitly responsible for the content.",
                })
            if site and site in folded_authors:
                findings.append({
                    "entity_type": "source", "entity_id": sid, "field": "metadata/authors",
                    "issue": "author_duplicates_site", "current_value": authors,
                    "required_correction": "Recheck attribution. Do not copy the site name mechanically as author; omit it if no distinct credited responsibility is shown, or replace it with the explicitly credited responsible author/organization.",
                })
            page_or_title = _fold_documentary(metadata.get("page") or metadata.get("title"))
            if site and page_or_title and site == page_or_title:
                findings.append({
                    "entity_type": "source", "entity_id": sid, "field": "metadata/title",
                    "issue": "page_or_title_duplicates_site", "current_value": metadata.get("page") or metadata.get("title"),
                    "required_correction": "Omit the redundant page/title value when it merely duplicates the site name.",
                })
    return findings


def _canonical_source_for_registry(source: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize supported legacy source-verification metadata at the output boundary.

    Older English review packages recorded verification provenance as
    checked_at/method/note and had no primary-source classification.  The
    canonical source registry uses verified_at/notes and keeps an explicit null
    when that historical review never recorded primary_source; no boolean is
    invented during compatibility migration.
    """
    clean = copy.deepcopy(dict(source))
    verification = clean.get("verification")
    if not isinstance(verification, dict):
        return clean
    verification = copy.deepcopy(verification)
    legacy = any(key in verification for key in LEGACY_SOURCE_VERIFICATION_KEYS)
    if legacy:
        if "verified_at" not in verification:
            verification["verified_at"] = verification.get("checked_at")
        if "primary_source" not in verification:
            verification["primary_source"] = None
        notes = verification.get("notes")
        if not isinstance(notes, list):
            notes = []
        else:
            notes = [str(item) for item in notes if str(item).strip()]
        note = str(verification.get("note") or "").strip()
        method = str(verification.get("method") or "").strip()
        if note and note not in notes:
            notes.append(note)
        if method:
            method_note = f"Verification method: {method}"
            if method_note not in notes:
                notes.append(method_note)
        verification["notes"] = notes
        for key in LEGACY_SOURCE_VERIFICATION_KEYS:
            verification.pop(key, None)
    clean["verification"] = verification
    return clean


def _documentary_identity_key(source: Mapping[str, Any]) -> tuple[str, str] | None:
    """Return the canonical same-language identity used to reuse an existing source.

    An English translation review can independently select a resource already present
    in the French registry because that resource was previously used cross-lingually.
    The review keeps its temporary source id for provenance, while the canonical
    registry must retain one source id for the same DOI/URL/resource identity.
    """
    language = str(source.get("language") or "").strip()
    if not language:
        return None
    metadata = source.get("metadata") or {}
    link = metadata.get("link")
    doi = normalize_doi(link) or normalize_doi(source.get("deduplication_key"))
    if doi:
        return language, f"doi:{doi}"
    url = normalize_url(link)
    if url:
        return language, f"url:{url}"
    dedup = str(source.get("deduplication_key") or "").strip().casefold()
    return (language, dedup) if dedup else None


def _merge_translated_sources_with_existing(
    existing_rows: Sequence[Mapping[str, Any]],
    translated_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Merge reviewed EN sources without duplicating an existing canonical resource.

    Existing canonical metadata is preserved. Only reviewed English usages are added
    when the same-language DOI/URL/dedup identity already exists. A disagreement in
    documentary family or document_kind remains blocking rather than being normalized
    silently.
    """
    merged = [_canonical_source_for_registry(row) for row in copy.deepcopy(list(existing_rows))]
    identity_to_index: dict[tuple[str, str], int] = {}
    for index, row in enumerate(merged):
        identity = _documentary_identity_key(row)
        if identity is not None:
            identity_to_index.setdefault(identity, index)

    remap: dict[str, str] = {}
    for raw in translated_rows:
        row = _canonical_source_for_registry(raw)
        source_id = str(row.get("id") or "")
        identity = _documentary_identity_key(row)
        existing_index = identity_to_index.get(identity) if identity is not None else None
        if existing_index is None:
            merged.append(row)
            if identity is not None:
                identity_to_index[identity] = len(merged) - 1
            continue

        existing = merged[existing_index]
        existing_id = str(existing.get("id") or "")
        if not existing_id or existing_id == source_id:
            raise TranslationReviewError(f"Identité documentaire canonique ambiguë pour {source_id or existing_id}")
        if existing.get("type") != row.get("type"):
            raise TranslationReviewError(
                f"La ressource anglaise {source_id} existe déjà sous {existing_id} avec un autre type documentaire"
            )
        if existing.get("document_kind") != row.get("document_kind"):
            raise TranslationReviewError(
                f"La ressource anglaise {source_id} existe déjà sous {existing_id} avec un autre document_kind"
            )

        existing_usages = existing.setdefault("usage", [])
        by_slot: dict[tuple[str, str, str], dict[str, Any]] = {}
        for usage in existing_usages:
            if not isinstance(usage, dict):
                continue
            slot = (str(usage.get("page_id") or ""), str(usage.get("language") or ""), str(usage.get("role") or ""))
            by_slot[slot] = usage
        for usage in row.get("usage") or []:
            if not isinstance(usage, dict):
                continue
            slot = (str(usage.get("page_id") or ""), str(usage.get("language") or ""), str(usage.get("role") or ""))
            previous = by_slot.get(slot)
            if previous is not None:
                if canonical_json(previous) != canonical_json(usage):
                    raise TranslationReviewError(
                        f"Usages documentaires incompatibles pour la ressource canonique {existing_id} ({slot[0]}/{slot[1]}/{slot[2]})"
                    )
                continue
            copied = copy.deepcopy(usage)
            existing_usages.append(copied)
            by_slot[slot] = copied
        remap[source_id] = existing_id

    for row in merged:
        for usage in row.get("usage") or []:
            if not isinstance(usage, dict):
                continue
            preferred = usage.get("preferred_equivalent_source_id")
            if isinstance(preferred, str) and preferred in remap:
                usage["preferred_equivalent_source_id"] = remap[preferred]
    return merged, remap


def _remap_final_source_ids(final: Mapping[str, Any], remap: Mapping[str, str]) -> dict[str, Any]:
    effective = copy.deepcopy(dict(final))
    if not remap:
        return effective
    debate = effective.get("debate") or {}
    for values in (debate.get("documentation") or {}).values():
        if isinstance(values, list):
            values[:] = [remap.get(str(source_id), str(source_id)) for source_id in values]
    for argument in effective.get("arguments") or []:
        if not isinstance(argument, dict):
            continue
        for values in (argument.get("sources") or {}).values():
            if isinstance(values, list):
                values[:] = [remap.get(str(source_id), str(source_id)) for source_id in values]
    return effective


def _validate_sources(data: Mapping[str, Any], debate_id: str, french_ids: set[str]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if data.get("schema") != EN_SOURCES_WORKING_SCHEMA or data.get("debate_id") != debate_id:
        raise TranslationReviewError("Schéma ou identité du registre documentaire anglais invalide")
    rows = data.get("sources")
    if not isinstance(rows, list):
        raise TranslationReviewError("Le registre documentaire anglais doit contenir une liste sources")
    result: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    dedup: set[str] = set()
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise TranslationReviewError(f"Source anglaise #{index} invalide")
        sid = _text(row.get("id"), f"identifiant de source anglaise #{index}")
        if not SOURCE_ID.fullmatch(sid) or sid in by_id or sid in french_ids:
            raise TranslationReviewError(f"Identifiant documentaire anglais invalide, dupliqué ou déjà utilisé : {sid}")
        stype = row.get("type")
        if stype not in {"bibliography", "webliography", "videography"}:
            raise TranslationReviewError(f"Type documentaire anglais invalide pour {sid}")
        if row.get("language") != "en":
            raise TranslationReviewError(f"La langue réelle de {sid} doit être en")
        metadata = row.get("metadata")
        if not isinstance(metadata, dict) or set(metadata) != set(SOURCE_METADATA_FIELDS):
            raise TranslationReviewError(f"Métadonnées anglaises incomplètes pour {sid}")
        authors = metadata.get("authors")
        if not isinstance(authors, list) or any(not isinstance(a, str) or not a.strip() for a in authors):
            raise TranslationReviewError(f"Auteurs invalides pour {sid}")
        if stype == "bibliography" and (not authors or not (metadata.get("article") or metadata.get("work"))):
            raise TranslationReviewError(f"Référence bibliographique anglaise incomplète : {sid}")
        if stype in {"webliography", "videography"} and not HTTP_URL.match(str(metadata.get("link") or "")):
            raise TranslationReviewError(f"Lien HTTP(S) obligatoire pour {sid}")
        if stype == "videography" and re.search(r"(?:youtube\.com/(?:watch|live)|youtu\.be/)", str(metadata.get("link") or ""), re.I) and not authors:
            raise TranslationReviewError(f"Une vidéo YouTube anglaise doit indiquer le créateur ou la chaîne : {sid}")
        verification = row.get("verification")
        if not isinstance(verification, dict) or verification.get("status") != "verified" or verification.get("language_verified") is not True:
            raise TranslationReviewError(f"Source anglaise non vérifiée : {sid}")
        legacy_verification = any(key in verification for key in LEGACY_SOURCE_VERIFICATION_KEYS)
        if legacy_verification:
            if not str(verification.get("checked_at") or "").strip():
                raise TranslationReviewError(f"Horodatage de vérification historique absent pour {sid}")
        else:
            if "verified_at" not in verification or "notes" not in verification or "primary_source" not in verification:
                raise TranslationReviewError(
                    f"Vérification documentaire canonique incomplète pour {sid} : "
                    "verified_at, primary_source et notes sont requis"
                )
            if not isinstance(verification.get("primary_source"), bool):
                raise TranslationReviewError(f"primary_source doit être booléen pour une nouvelle vérification documentaire : {sid}")
            if not isinstance(verification.get("notes"), list):
                raise TranslationReviewError(f"notes doit être une liste pour {sid}")
        if stype in {"webliography", "videography"} and verification.get("authorship_checked") is not True:
            raise TranslationReviewError(f"Attribution anglaise non vérifiée : {sid}")
        if stype in {"webliography", "videography"}:
            folded_site = _fold_documentary(metadata.get("site"))
            folded_authors = [_fold_documentary(value) for value in authors]
            if authors and verification.get("authorship_verified") is not True:
                raise TranslationReviewError(f"Attribution anglaise renseignée mais non explicitement vérifiée : {sid}")
            if folded_site and folded_site in folded_authors:
                raise TranslationReviewError(
                    f"Le nom du site est encore utilisé comme auteur pour {sid}; "
                    "revérifier l’attribution et omettre l’auteur si aucune responsabilité distincte n’est créditée"
                )
            page_or_title = _fold_documentary(metadata.get("page") or metadata.get("title"))
            if folded_site and page_or_title and folded_site == page_or_title:
                raise TranslationReviewError(f"Le titre/page duplique le nom du site pour {sid}")
        usages = row.get("usage")
        if not isinstance(usages, list) or not usages:
            raise TranslationReviewError(f"Aucun usage documentaire anglais pour {sid}")
        for usage in usages:
            if not isinstance(usage, dict) or usage.get("language") != "en" or not usage.get("page_id") or not usage.get("role"):
                raise TranslationReviewError(f"Usage anglais invalide pour {sid}")
            if usage.get("role") == "supports_summary":
                if usage.get("argument_development_verified") is not True:
                    raise TranslationReviewError(f"Le développement de l’argument n’est pas vérifié pour {sid}")
                if not isinstance(usage.get("also_develops_objections"), bool):
                    raise TranslationReviewError(f"La couverture éventuelle d’objections doit être attestée pour {sid}")
            if len(str(usage.get("selection_reason") or "").strip()) < 12:
                raise TranslationReviewError(f"Justification de sélection anglaise insuffisante pour {sid}")
            if usage.get("page_id") == debate_id and stype == "bibliography":
                if row.get("document_kind") not in SOURCE_DOCUMENT_KINDS:
                    raise TranslationReviewError(f"document_kind de bibliographie Debate absent ou invalide pour {sid}")
                if usage.get("documentary_scope") not in DEBATE_BIBLIOGRAPHY_SCOPES:
                    raise TranslationReviewError(
                        f"Portée bibliographique Debate non revue pour {sid}: "
                        "foundational_work ou broad_synthesis requis"
                    )
        key = _text(row.get("deduplication_key"), f"clé de dédoublonnage de {sid}")
        if key in dedup:
            raise TranslationReviewError(f"Clé documentaire anglaise dupliquée : {key}")
        dedup.add(key)
        projected = copy.deepcopy(row)
        # Consultation receipts are working evidence, not source-registry fields.
        projected.pop("evidence", None)
        by_id[sid] = projected
        result.append(copy.deepcopy(projected))
    return result, by_id


def _has_usage(source: Mapping[str, Any], page_id: str, roles: set[str]) -> bool:
    return any(u.get("page_id") == page_id and u.get("language") == "en" and u.get("role") in roles for u in source.get("usage") or [])


def _title_format_issues(value: Any, *, canonical: bool = False) -> list[str]:
    text = str(value or "").strip()
    issues: list[str] = []
    if BAD_QUOTES.search(text):
        issues.append("typographic_or_chevron_quote")
    if BAD_TITLE_APOSTROPHES.search(text):
        issues.append("non_ascii_apostrophe")
    if BAD_ELLIPSIS.search(text):
        issues.append("ellipsis")
    if text.endswith("."):
        issues.append("terminal_period")
    if canonical:
        issues.extend(canonical_title_structure_issues(text))
    return issues


def _validate_title(value: Any, label: str, *, displayed: bool = False) -> str:
    text = _text(value, label, 1 if displayed else 8)
    issues = _title_format_issues(text, canonical=not displayed)
    if issues:
        raise TranslationReviewError(f"Titre anglais non conforme : {label} ({', '.join(issues)})")
    return text


def collect_english_title_format_findings(review: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Collect title-format defects before applying a converged translation.

    This is primarily a compatibility guard for reviews finalized by older kit
    versions that did not reject non-ASCII apostrophes early enough.  It does
    not normalize the content: any defect reopens the editorial translation so
    that the exact reviewed value changes explicitly and semantic convergence
    can restart on the new hash.
    """
    findings: list[dict[str, Any]] = []
    final_values = review.get("final_values") if isinstance(review, Mapping) else None
    if isinstance(final_values, Mapping):
        debate = final_values.get("debate") or {}
        value = debate.get("canonical_title") if isinstance(debate, Mapping) else None
        issues = _title_format_issues(value, canonical=True)
        if issues:
            findings.append({
                "entity_type": "debate", "entity_id": str(review.get("debate_id") or ""),
                "field": "canonical_title", "current_value": str(value or ""),
                "issues": issues,
                "required_correction": "Review the canonical title as one sentence preserving its meaning and scope; do not merely swap punctuation or rewrite quotations.",
            })
        arguments = final_values.get("arguments") or []
        for row in arguments:
            if not isinstance(row, Mapping):
                continue
            for field in ("canonical_title", "displayed_title"):
                value = row.get(field)
                issues = _title_format_issues(value, canonical=field == "canonical_title")
                if issues:
                    findings.append({
                        "entity_type": "argument", "entity_id": str(row.get("id") or ""),
                        "field": field, "current_value": str(value or ""),
                        "issues": issues,
                        "required_correction": "Review the title without changing its meaning; canonical titles require one sentence, while historical displayed labels retain their source form.",
                    })
        return findings

    # Draft-review fallback (useful to tests and future callers).
    debate = review.get("debate") if isinstance(review, Mapping) else None
    if isinstance(debate, Mapping):
        translation = debate.get("translation") if isinstance(debate.get("translation"), Mapping) else debate
        value = translation.get("canonical_title") if isinstance(translation, Mapping) else None
        issues = _title_format_issues(value, canonical=True)
        if issues:
            findings.append({"entity_type": "debate", "entity_id": str(review.get("debate_id") or ""), "field": "canonical_title", "current_value": str(value or ""), "issues": issues})
    for item in review.get("arguments") or [] if isinstance(review, Mapping) else []:
        if not isinstance(item, Mapping):
            continue
        row = item.get("translation") or {}
        if not isinstance(row, Mapping):
            continue
        for field in ("canonical_title", "displayed_title"):
            value = row.get(field)
            issues = _title_format_issues(value, canonical=field == "canonical_title")
            if issues:
                findings.append({"entity_type": "argument", "entity_id": str(item.get("id") or ""), "field": field, "current_value": str(value or ""), "issues": issues})
    return findings


def _first_alphabetic(value: str) -> str:
    return next((char for char in value if char.isalpha()), "")


def _english_capitalization_issues(value: str, kind: str) -> list[str]:
    first = _first_alphabetic(value)
    if kind in {"noun", "noun_phrase"} and first and first.isupper():
        return ["common_keyword_initial_uppercase"]
    if kind == "acronym":
        letters = [char for char in value if char.isalpha()]
        if not letters or any(char.islower() for char in letters):
            return ["acronym_not_uppercase"]
    return []


def _historical_relation_labels_required(content_lock: Mapping[str, Any]) -> bool:
    """Ordinary reviewed imports retain contextual labels just like frozen imports."""
    pages = [content_lock.get("debate") or {}, *(content_lock.get("arguments") or [])]
    return bool(content_lock.get("source_preservation_policy")) or bool(pages) and all(
        page.get("page_origin") == "preexisting" for page in pages
    )


def _validate_vocabulary(rows: Any, french_entries: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    if not isinstance(rows, list) or len(rows) != len(french_entries):
        raise TranslationReviewError("Le vocabulaire anglais ne couvre pas exactement le vocabulaire français")
    expected = {str(row.get("fr")): row for row in french_entries}
    result: list[dict[str, Any]] = []
    mapping: dict[str, str] = {}
    english_seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or str(row.get("fr")) not in expected:
            raise TranslationReviewError("Entrée de vocabulaire anglaise inconnue")
        fr = str(row.get("fr"))
        expected_concept_id = str(expected[fr].get("concept_id") or "").strip()
        actual_concept_id = str(row.get("concept_id") or "").strip()
        if expected_concept_id and actual_concept_id != expected_concept_id:
            raise TranslationReviewError(f"concept_id anglais divergent pour {fr}")
        if actual_concept_id and not re.fullmatch(r"KWD-[A-F0-9]{12,64}", actual_concept_id):
            raise TranslationReviewError(f"concept_id anglais invalide pour {fr}")
        en = _text(row.get("en"), f"équivalent anglais de {fr}", 2)
        if en.casefold() in english_seen:
            raise TranslationReviewError(f"Équivalent anglais dupliqué : {en}")
        english_seen.add(en.casefold())
        kind = str(expected[fr].get("kind") or "")
        if row.get("kind") != kind or row.get("capitalization_policy") != expected[fr].get("capitalization_policy"):
            raise TranslationReviewError(f"Nature ou politique de capitalisation divergente : {fr}")
        english_kind = str(row.get("en_kind") or kind)
        policies = {"noun": "lowercase_common", "noun_phrase": "lowercase_common", "proper_name": "canonical_proper_name", "acronym": "canonical_acronym"}
        if english_kind not in policies or (row.get("en_capitalization_policy") is not None and row["en_capitalization_policy"] != policies[english_kind]):
            raise TranslationReviewError(f"Nature ou politique de forme anglaise invalide : {fr}")
        if english_kind != kind and len(str(row.get("capitalization_rationale_en") or "").strip()) < 12:
            raise TranslationReviewError(f"Changement de forme lexicale anglaise non justifié : {fr}")
        capitalization_issues = _english_capitalization_issues(en, english_kind)
        if capitalization_issues:
            raise TranslationReviewError(f"Capitalisation anglaise non canonique pour {fr} : {capitalization_issues}")
        if row.get("capitalization_verified") is not True:
            raise TranslationReviewError(f"Capitalisation anglaise non attestée : {fr}")
        if english_kind in {"proper_name", "acronym"} and len(str(row.get("capitalization_rationale_en") or "").strip()) < 12:
            raise TranslationReviewError(f"Justification de capitalisation anglaise insuffisante : {fr}")
        if english_kind == kind and kind in {"noun", "noun_phrase"} and str(row.get("capitalization_rationale_en") or "").strip():
            raise TranslationReviewError(f"Justification de majuscule anglaise inattendue pour le nom commun : {fr}")
        if row.get("status") != "approved" or row.get("idiomatic_equivalent") is not True or row.get("same_concept") is not True:
            raise TranslationReviewError(f"Équivalence lexicale non approuvée : {fr}")
        _text(row.get("definition_en"), f"définition anglaise de {fr}", 8)
        _text(row.get("reviewer"), f"relecteur lexical de {fr}", 3)
        _text(row.get("reviewed_at"), f"date de revue lexicale de {fr}", 10)
        _text(row.get("note"), f"note lexicale de {fr}", 8)
        mapping[fr] = en
        result.append(copy.deepcopy(row))
    if set(mapping) != set(expected):
        raise TranslationReviewError("Le vocabulaire anglais omet des termes français")
    return result, mapping


def _expected_sections(fr: Sequence[str], *, preserve_source_order: bool = False) -> list[str]:
    try:
        values = [SECTION_MAP[item] for item in fr]
        return sorted(values, key=lambda x: x.casefold())
    except KeyError as exc:
        raise TranslationReviewError(f"Rubrique française sans section anglaise contrôlée : {exc.args[0]}") from exc


def _expected_keywords(fr: Sequence[str], mapping: Mapping[str, str]) -> list[str]:
    try:
        return [mapping[item] for item in fr]
    except KeyError as exc:
        raise TranslationReviewError(f"Mot-clé français sans équivalent anglais : {exc.args[0]}") from exc


def _validate_debate(row: Mapping[str, Any], mapping: Mapping[str, str], sources: Mapping[str, Mapping[str, Any]], debate_id: str, *, authoritative_source_page_origin: str | None = None, authoritative_source_preservation_policy: str | None = None) -> dict[str, Any]:
    if row.get("status") != "approved":
        raise TranslationReviewError("Traduction de la page Debate non approuvée")
    fr_meta = ((row.get("french") or {}).get("metadata") or {})
    fr_content = ((row.get("french") or {}).get("content") or {})
    embedded_source_page_origin = _french_source_page_origin(fr_meta, fr_content)
    source_page_origin = authoritative_source_page_origin or embedded_source_page_origin
    if source_page_origin not in {"new", "preexisting"} or embedded_source_page_origin != source_page_origin:
        raise TranslationReviewError("La provenance éditoriale française intégrée à Debate diverge du verrou français autoritatif")
    if str(row.get("source_page_origin") or source_page_origin) != source_page_origin:
        raise TranslationReviewError("La provenance éditoriale française de Debate ne peut pas être modifiée dans la revue anglaise")
    title = _validate_title(row.get("canonical_title"), "titre canonique de Debate")
    topic = _text(row.get("topic"), "topic", 3)
    complete = _text(row.get("complete_topic"), "expanded-topic", 3)
    if QUESTION_TOPIC.search(complete):
        raise TranslationReviewError("expanded-topic doit être nominal et non interrogatif")
    if complete[0].isalpha() and complete[0].isupper() and not row.get("complete_topic_initial_capital_justification"):
        raise TranslationReviewError("La majuscule initiale de expanded-topic doit être justifiée")
    for field in ("canonical_title_semantic_inventory_reviewed", "topic_semantic_equivalence_reviewed", "complete_topic_semantic_equivalence_reviewed", "introduction_claim_inventory_reviewed", "subsection_structure_equivalence_reviewed"):
        if row.get(field) is not True:
            raise TranslationReviewError(f"Attestation sémantique différentielle manquante pour Debate : {field}")
    canonical_inventory_note = _text(row.get("canonical_title_semantic_inventory_note"), "inventaire sémantique du titre canonique de Debate", 20)
    introduction_inventory_note = _text(row.get("introduction_claim_inventory_note"), "inventaire des affirmations de l’introduction anglaise", 30)
    fr_canonical = str(fr_meta.get("canonical_title") or fr_meta.get("titre_canonique") or "").strip()
    fr_topic = str(fr_content.get("subject") or fr_content.get("topic") or "").strip()
    fr_complete = str(fr_content.get("complete_topic") or fr_content.get("sujet_complet") or "").strip()
    fr_introduction = str(fr_content.get("introduction") or "").strip()
    debate_risk_by_field = {
        "canonical_title": _semantic_risk_signals(fr_canonical, title),
        "topic": _semantic_risk_signals(fr_topic, topic),
        "complete_topic": _semantic_risk_signals(fr_complete, complete),
    }
    sections = _strings(row.get("sections"), "sections de Debate")
    expected_sections = _expected_sections(fr_meta.get("rubriques") or [], preserve_source_order=bool(authoritative_source_preservation_policy))
    if sections != expected_sections or row.get("sections_exactly_mapped") is not True:
        raise TranslationReviewError("Les sections anglaises de Debate ne correspondent pas aux rubriques françaises")
    keywords = _strings(row.get("keywords"), "keywords de Debate", allow_source_duplicates=bool(authoritative_source_preservation_policy))
    expected_keywords = _expected_keywords(fr_meta.get("keywords") or [], mapping)
    if keywords != expected_keywords or row.get("keywords_exactly_mapped") is not True:
        raise TranslationReviewError("Les keywords de Debate ne correspondent pas au vocabulaire contrôlé")
    if source_page_origin == "new" and not 5 <= len(keywords) <= 8:
        raise TranslationReviewError("Une Debate issue d’une source française nouvelle doit comporter cinq à huit keywords")
    if row.get("keywords_order_preserved_by_relevance") is not True:
        raise TranslationReviewError("L’ordre de pertinence des keywords de Debate n’est pas attesté")
    introduction = _text(row.get("introduction"), "introduction anglaise", 40)
    _assert_english_wikicode_localized(introduction, "l’introduction anglaise")
    debate_risk_by_field["introduction"] = _semantic_risk_signals(fr_introduction, introduction)
    debate_semantic_risks = sorted({f"{field}:{risk}" for field, risks in debate_risk_by_field.items() for risk in risks})
    debate_risk_note = str(row.get("debate_field_semantic_risk_note") or "").strip()
    debate_risk_evidence = row.get("debate_field_semantic_risk_evidence") or []
    if debate_semantic_risks:
        if row.get("debate_field_semantic_risk_reviewed") is not True:
            raise TranslationReviewError(f"Risques sémantiques de Debate non revus : {debate_semantic_risks}")
        debate_risk_note = _text(debate_risk_note, "note de risque sémantique de Debate", 24)
        if not isinstance(debate_risk_evidence, list):
            raise TranslationReviewError("Preuves sémantiques de Debate invalides")
        covered = set()
        source_fields = {"canonical_title": fr_canonical, "topic": fr_topic, "complete_topic": fr_complete, "introduction": fr_introduction}
        target_fields = {"canonical_title": title, "topic": topic, "complete_topic": complete, "introduction": introduction}
        for evidence_row in debate_risk_evidence:
            if not isinstance(evidence_row, dict) or str(evidence_row.get("risk") or "") not in debate_semantic_risks:
                raise TranslationReviewError("Preuve sémantique de Debate inconnue")
            risk = str(evidence_row.get("risk")); field = risk.split(":", 1)[0]
            source_excerpt = _text(evidence_row.get("source_excerpt"), f"extrait source du risque {risk}", 3)
            target_excerpt = _text(evidence_row.get("target_excerpt"), f"extrait cible du risque {risk}", 3)
            _text(evidence_row.get("note"), f"note du risque {risk}", 12)
            if _plain(source_excerpt).casefold() not in _plain(source_fields[field]).casefold() or _plain(target_excerpt).casefold() not in _plain(target_fields[field]).casefold():
                raise TranslationReviewError(f"Extrait de preuve de Debate absent du champ {field}")
            covered.add(risk)
        if covered != set(debate_semantic_risks):
            raise TranslationReviewError("Chaque risque sémantique de Debate doit avoir une preuve source/cible")
    elif not isinstance(debate_risk_evidence, list):
        raise TranslationReviewError("Preuves sémantiques de Debate invalides")
    historical_intro_profile = {field: bool(row.get(field)) for field in HISTORICAL_INTRO_TRANSLATION_TRUE_FIELDS}
    introduction_adaptation_rationale = str(row.get("introduction_adaptation_rationale") or "").strip()
    subsections = row.get("subsections")
    if not isinstance(subsections, list) or not subsections:
        raise TranslationReviewError("L’introduction anglaise doit comporter des sous-parties")
    stakes_rows = []
    for subsection_index, sub in enumerate(subsections):
        if not isinstance(sub, dict):
            raise TranslationReviewError("Sous-partie anglaise invalide")
        source_subsections = fr_content.get("subsections") or []
        source_title_absent = source_page_origin == "preexisting" and subsection_index < len(source_subsections) and not str(source_subsections[subsection_index].get("title") or "").strip()
        subtitle = "" if source_title_absent and not str(sub.get("title") or "").strip() else _text(sub.get("title"), "titre de sous-partie anglaise", 3)
        _text(sub.get("purpose"), "fonction de sous-partie anglaise", 12)
        if sub.get("necessary_for_understanding") is not True or sub.get("relevance_to_debate_explained") is not True:
            raise TranslationReviewError("Chaque sous-partie anglaise doit être nécessaire et contextualisée")
        if subtitle == "Stakes of the debate":
            stakes_rows.append(sub)
    if source_page_origin == "new":
        if len(stakes_rows) != 1:
            raise TranslationReviewError('A Debate translated from newly authored French content must contain exactly one subsection titled "Stakes of the debate"')
        stakes_row = stakes_rows[0]
        if stakes_row.get("stakes_section") is not True:
            raise TranslationReviewError("The review must explicitly identify the Stakes of the debate subsection")
        concrete_stakes = stakes_row.get("concrete_stakes")
        normalized_stakes = [str(item).strip() for item in concrete_stakes or [] if str(item).strip()]
        if len(normalized_stakes) < 2 or len({item.casefold() for item in normalized_stakes}) < 2 or any(len(item) < 20 for item in normalized_stakes):
            raise TranslationReviewError("The Stakes of the debate subsection must record at least two distinct concrete consequences")
        stake_content_match = re.search(r"\{\{Subsection\|title=Stakes of the debate\|content=(.*?)\}\}", introduction, re.S)
        stake_content = stake_content_match.group(1).strip() if stake_content_match else ""
        if len(re.findall(r"\b[\w'-]+\b", stake_content)) < 45 or len(re.findall(r"[.!?](?:\s|$)", stake_content)) < 3:
            raise TranslationReviewError("The Stakes of the debate subsection is too brief or merely symbolic")
    else:
        profile_fields_present = any(field in row for field in HISTORICAL_INTRO_TRANSLATION_TRUE_FIELDS) or "introduction_adaptation_rationale" in row
        if profile_fields_present:
            for field in HISTORICAL_INTRO_TRANSLATION_TRUE_FIELDS:
                if row.get(field) is not True:
                    raise TranslationReviewError(f"Attestation d’adaptation de l’introduction historique manquante : {field}")
            introduction_adaptation_rationale = _text(row.get("introduction_adaptation_rationale"), "justification de l’adaptation internationale de l’introduction historique", 30)
            historical_intro_profile = {field: True for field in HISTORICAL_INTRO_TRANSLATION_TRUE_FIELDS}
        else:
            # Schema-compatible normalization for review documents prepared before
            # source-provenance-specific intro attestations were introduced. The
            # older format already requires functional equivalence, claim review
            # and subsection-structure review below; absence of the new keys is
            # therefore treated as legacy format, not as a negative attestation.
            historical_intro_profile = {field: True for field in HISTORICAL_INTRO_TRANSLATION_TRUE_FIELDS}
            introduction_adaptation_rationale = str(row.get("note") or "Legacy historical-introduction review normalized from the supported review schema.").strip()
        # Historical source status removes only creation-profile requirements.
        # Documentary, citation and terminology quality remains applicable to
        # the English adaptation.  These fields already existed in the legacy
        # INTRO_TRUE_FIELDS profile, so supported older review packages can be
        # normalized without inventing a weaker contract.
        for field in HISTORICAL_INTRO_UNIVERSAL_TRUE_FIELDS:
            if row.get(field) is not True:
                raise TranslationReviewError(f"Attestation de qualité intrinsèque de l’introduction historique manquante : {field}")
    wikipedia = _strings(row.get("wikipedia_articles"), "articles Wikipédia anglais")
    if not wikipedia or row.get("wikipedia_articles_verified") is not True:
        raise TranslationReviewError("Au moins un article Wikipédia anglais vérifié est obligatoire")
    documentation = row.get("documentation")
    if not isinstance(documentation, dict) or set(documentation) != set(DEBATE_BUCKETS):
        raise TranslationReviewError("Neuf paramètres documentaires anglais requis")
    final_doc: dict[str, list[str]] = {}
    selected_roles: dict[str, set[str]] = {}
    for bucket, (stype, role) in DEBATE_BUCKETS.items():
        ids = _strings(documentation.get(bucket), bucket)
        for sid in ids:
            source = sources.get(sid)
            if not source or source.get("type") != stype or source.get("language") != "en" or not _has_usage(source, debate_id, {role}):
                raise TranslationReviewError(f"Source anglaise incompatible dans {bucket} : {sid}")
            selected_roles.setdefault(sid, set()).add(role)
        final_doc[bucket] = ids
    conflicts = {sid: sorted(roles) for sid, roles in selected_roles.items() if len(roles) > 1}
    if conflicts:
        raise TranslationReviewError(
            "Une même source anglaise ne peut figurer dans plusieurs orientations; une source couvrant les deux camps doit être neutral: "
            + repr(conflicts)
        )
    required_debate_fields = ("metadata_equivalent_to_french", "content_equivalent_to_french", "introduction_functionally_equivalent", "all_debate_sources_english")
    if source_page_origin == "new":
        required_debate_fields = (*required_debate_fields, *INTRO_TRUE_FIELDS)
    for field in required_debate_fields:
        if row.get(field) is not True:
            raise TranslationReviewError(f"Attestation anglaise manquante pour Debate : {field}")
    _text(row.get("topic_label_rationale"), "justification de topic", 12)
    _text(row.get("reviewer"), "relecteur de Debate", 3)
    _text(row.get("reviewed_at"), "date de revue de Debate", 10)
    _text(row.get("note"), "note de revue de Debate", 12)
    return {
        "canonical_title": title, "topic": topic, "complete_topic": complete,
        "sections": sections, "keywords": keywords, "introduction": introduction,
        "subsections": copy.deepcopy(subsections), "wikipedia_articles": wikipedia,
        "documentation": final_doc, "documentation_family_notes": copy.deepcopy(row.get("documentation_family_notes") or {}),
        "topic_label_rationale": row.get("topic_label_rationale"),
        "complete_topic_initial_capital_justification": row.get("complete_topic_initial_capital_justification"),
        "canonical_title_semantic_inventory_reviewed": True,
        "canonical_title_semantic_inventory_note": canonical_inventory_note,
        "topic_semantic_equivalence_reviewed": True,
        "complete_topic_semantic_equivalence_reviewed": True,
        "introduction_claim_inventory_reviewed": True,
        "introduction_claim_inventory_note": introduction_inventory_note,
        "subsection_structure_equivalence_reviewed": True,
        "debate_field_semantic_risks": debate_semantic_risks,
        "debate_field_semantic_risk_reviewed": bool(row.get("debate_field_semantic_risk_reviewed")) if debate_semantic_risks else True,
        "debate_field_semantic_risk_note": debate_risk_note,
        "debate_field_semantic_risk_evidence": copy.deepcopy(debate_risk_evidence),
        "field_sha256": {
            "fr_canonical_title": _field_sha256(fr_canonical), "en_canonical_title": _field_sha256(title),
            "fr_topic": _field_sha256(fr_topic), "en_topic": _field_sha256(topic),
            "fr_complete_topic": _field_sha256(fr_complete), "en_complete_topic": _field_sha256(complete),
            "fr_introduction": _field_sha256(fr_introduction), "en_introduction": _field_sha256(introduction),
        },
        "reviewer": row.get("reviewer"), "reviewed_at": row.get("reviewed_at"), "note": row.get("note"),
        "source_page_origin": source_page_origin,
        "introduction_adaptation_rationale": introduction_adaptation_rationale,
        **historical_intro_profile,
        **({field: True for field in HISTORICAL_INTRO_UNIVERSAL_TRUE_FIELDS} if source_page_origin == "preexisting" else {}),
        "french_subject": fr_content.get("subject"), "french_complete_topic": fr_content.get("complete_topic"),
        **_validate_page_lifecycle(row, "debate", "Debate"),
    }


def _validate_argument_name_discovery(row: Mapping[str, Any], node_id: str, page_origin: str) -> tuple[str | None, dict[str, Any] | None]:
    if page_origin != "new":
        return None, None
    queries = _strings(row.get("argument_name_search_queries"), f"recherches de nom de {node_id}")
    if len(queries) < 2 or len(set(queries)) != len(queries):
        raise TranslationReviewError(f"Au moins deux recherches distinctes sont requises pour le nom de {node_id}")
    scope_note = _text(row.get("argument_name_search_scope_note"), f"périmètre de recherche du nom de {node_id}", 12)
    provenance = str(row.get("argument_name_search_provenance") or "")
    if provenance not in NAME_SEARCH_PROVENANCE:
        raise TranslationReviewError(f"Provenance de recherche du nom invalide pour {node_id}")
    provenance_note = _text(row.get("argument_name_search_provenance_note"), f"note de provenance de recherche du nom de {node_id}", 12)
    if provenance == "historical_reconstruction":
        raise TranslationReviewError(f"Une page anglaise nouvelle doit utiliser un journal réel ou une nouvelle recherche, pas une reconstruction historique : {node_id}")
    rationale = _text(row.get("argument_name_rationale"), f"justification de recherche du nom de {node_id}", 12)
    page_scope = _text(row.get("argument_name_page_reasoning_scope_summary"), f"portée du raisonnement de la page {node_id}", 12)
    outcome = str(row.get("argument_name_outcome") or "")
    evidence = row.get("argument_name_evidence")
    if not isinstance(evidence, list):
        raise TranslationReviewError(f"Preuves documentaires invalides pour le nom de {node_id}")
    if outcome == "known_name":
        name = _text(row.get("argument_name"), f"nom consacré de {node_id}", 2)
        first_alpha = next((char for char in name if char.isalpha()), "")
        if first_alpha and not first_alpha.isupper():
            raise TranslationReviewError(f"Le established-name= anglais est un sous-titre et doit commencer par une majuscule : {node_id}")
        if not evidence:
            raise TranslationReviewError(f"Nom consacré sans preuve documentaire pour {node_id}")
        for ev in evidence:
            if not isinstance(ev, dict):
                raise TranslationReviewError(f"Preuve documentaire invalide pour {node_id}")
            _text(ev.get("source"), f"source du nom de {node_id}", 6)
            _text(ev.get("label_as_used"), f"appellation attestée de {node_id}", 2)
            _text(ev.get("locator"), f"localisation du nom de {node_id}", 2)
        for field in ("argument_name_same_reasoning_confirmed", "argument_name_non_invented_label_confirmed", "argument_name_language_fit_confirmed"):
            if row.get(field) is not True:
                raise TranslationReviewError(f"Attestation de nom consacrée absente pour {node_id} : {field}")
        literature_scope = _text(row.get("argument_name_literature_scope_summary"), f"portée littéraire du nom de {node_id}", 12)
        scope_relation = str(row.get("argument_name_scope_relation") or "")
        if scope_relation != "exact_match" or row.get("argument_name_scope_identity_confirmed") is not True:
            raise TranslationReviewError(f"Le established-name= doit désigner exactement la portée du raisonnement de la page : {node_id}")
        same = True
    elif outcome == "none":
        if row.get("argument_name") not in (None, ""):
            raise TranslationReviewError(f"Un nom ne peut être fourni après une recherche négative pour {node_id}")
        if row.get("argument_name_non_invented_label_confirmed") is not True or row.get("argument_name_language_fit_confirmed") is not True:
            raise TranslationReviewError(f"Attestation de recherche négative incomplète pour {node_id}")
        name = None
        literature_scope = ""
        scope_relation = ""
        same = False
    else:
        raise TranslationReviewError(f"Résultat de recherche du nom invalide pour {node_id}")
    return name, {
        "search_reviewed": True,
        "search_queries": queries,
        "search_scope_note": scope_note,
        "search_provenance": provenance,
        "search_provenance_note": provenance_note,
        "outcome": outcome,
        "name": name,
        "evidence": evidence,
        "same_reasoning_confirmed": same,
        "non_invented_label_confirmed": bool(row.get("argument_name_non_invented_label_confirmed")),
        "language_fit_confirmed": bool(row.get("argument_name_language_fit_confirmed")),
        "rationale": rationale,
        "page_reasoning_scope_summary": page_scope,
        "literature_name_scope_summary": literature_scope,
        "scope_relation": scope_relation,
        "scope_identity_confirmed": bool(row.get("argument_name_scope_identity_confirmed")) if outcome == "known_name" else False,
    }


def _validate_dedicated_debate(row: Mapping[str, Any], node_id: str) -> dict[str, Any]:
    french = ((row.get("french") or {}).get("content") or {})
    preserved = french.get("preserved_parameters") or {}
    state = preserved.get("débat-dédié") or preserved.get("débat-détaillé") or {}
    value = row.get("dedicated_debate")
    if not state.get("present"):
        if value not in (None, ""):
            raise TranslationReviewError(f"Débat dédié anglais ajouté sans source française : {node_id}")
        return {"dedicated_debate": None, "dedicated_debate_equivalence_reviewed": False, "dedicated_debate_review_note": ""}
    title = _validate_title(value, f"titre du débat dédié anglais de {node_id}")
    if row.get("dedicated_debate_equivalence_reviewed") is not True:
        raise TranslationReviewError(f"Traduction du débat dédié non revue : {node_id}")
    note = _text(row.get("dedicated_debate_review_note"), f"revue du débat dédié de {node_id}", 24)
    return {"dedicated_debate": title, "dedicated_debate_equivalence_reviewed": True, "dedicated_debate_review_note": note}


def _validate_argument(item: Mapping[str, Any], mapping: Mapping[str, str], sources: Mapping[str, Mapping[str, Any]], *, authoritative_source_page_origin: str | None = None, authoritative_source_preservation_policy: str | None = None) -> dict[str, Any]:
    node_id = _text(item.get("id"), "identifiant d’argument")
    row = item.get("translation") or {}
    if row.get("status") != "approved":
        raise TranslationReviewError(f"Traduction anglaise non approuvée pour {node_id}")
    fr_meta = ((row.get("french") or {}).get("metadata") or {})
    fr_content = ((row.get("french") or {}).get("content") or {})
    embedded_source_page_origin = _french_source_page_origin(fr_meta, fr_content)
    source_page_origin = authoritative_source_page_origin or embedded_source_page_origin
    if source_page_origin not in {"new", "preexisting"} or embedded_source_page_origin != source_page_origin:
        raise TranslationReviewError(f"La provenance française intégrée diverge du verrou français autoritatif pour {node_id}")
    if str(row.get("source_page_origin") or source_page_origin) != source_page_origin:
        raise TranslationReviewError(f"La provenance éditoriale française ne peut pas être modifiée pour {node_id}")
    canonical = _validate_title(row.get("canonical_title"), f"titre canonique anglais de {node_id}")
    displayed = _validate_title(row.get("displayed_title"), f"titre affiché anglais de {node_id}", displayed=True)
    # Translation preserves the validated source form, regardless of the French
    # source's origin or the English page's lifecycle. Creation rules belong to
    # generation; the differential form and meaning checks below still apply.
    if row.get("canonical_title_semantic_inventory_reviewed") is not True or row.get("canonical_title_equivalent_to_french") is not True:
        raise TranslationReviewError(f"Revue sémantique différentielle du titre canonique manquante pour {node_id}")
    for field in ("canonical_title_subject_preserved", "canonical_title_predicate_preserved", "canonical_title_scope_preserved", "canonical_title_modality_preserved"):
        if row.get(field) is not True:
            raise TranslationReviewError(f"Attestation structurée du titre canonique absente pour {node_id} : {field}")
    canonical_inventory_note = _text(row.get("canonical_title_semantic_inventory_note"), f"inventaire sémantique du titre canonique de {node_id}", 20)
    fr_canonical = str(fr_meta.get("canonical_title") or fr_meta.get("titre_canonique") or "").strip()
    fr_displayed = str(fr_meta.get("displayed_title") or fr_meta.get("titre_affiché") or fr_meta.get("titre-affiché") or "").strip()
    if row.get("displayed_title_translates_french_displayed_title") is not True:
        raise TranslationReviewError(f"Le displayed-title anglais doit traduire directement le titre-affiché français : {node_id}")
    if fr_canonical and fr_displayed:
        source_identity = fr_canonical.casefold() == fr_displayed.casefold()
        target_identity = canonical.casefold() == displayed.casefold()
        if source_identity != target_identity:
            if row.get("displayed_title_identity_pattern_reviewed") is not True:
                raise TranslationReviewError(f"Changement de relation canonique/affiché non revu pour {node_id}")
            _text(row.get("displayed_title_identity_pattern_note"), f"note de filiation du displayed-title de {node_id}", 20)
    source_form = str(row.get("displayed_title_source_form") or "")
    target_form = str(row.get("displayed_title_target_form") or "")
    if source_form not in DISPLAYED_TITLE_FORMS or target_form not in DISPLAYED_TITLE_FORMS:
        raise TranslationReviewError(f"Forme source/cible du displayed-title non classée pour {node_id}")
    for field in ("displayed_title_source_form_reviewed", "displayed_title_no_formal_regression", "displayed_title_semantic_inventory_reviewed"):
        if row.get(field) is not True:
            raise TranslationReviewError(f"Attestation différentielle manquante pour {node_id} : {field}")
    semantic_inventory_note = _text(row.get("displayed_title_semantic_inventory_note"), f"inventaire sémantique du displayed-title de {node_id}", 20)
    for field in ("displayed_title_subject_preserved", "displayed_title_predicate_preserved", "displayed_title_scope_preserved", "displayed_title_modality_preserved"):
        if row.get(field) is not True:
            raise TranslationReviewError(f"Attestation structurée du displayed-title absente pour {node_id} : {field}")
    if source_form != target_form:
        if row.get("displayed_title_form_change_reviewed") is not True or row.get("displayed_title_speech_act_preserved") is not True:
            raise TranslationReviewError(f"Le changement idiomatique de forme du displayed-title exige une revue explicite de l’acte de langage : {node_id} ({source_form} -> {target_form})")
        _text(row.get("displayed_title_form_change_note"), f"justification du changement de forme du displayed-title de {node_id}", 24)
        if source_form == "proposition" and target_form != "proposition":
            raise TranslationReviewError(f"Une proposition française ne peut pas devenir un fragment ou une autre forme non propositionnelle : {node_id}")
    if source_form == "proposition" and row.get("displayed_title_is_complete_proposition") is not True:
        raise TranslationReviewError(f"Un displayed-title source propositionnel doit rester propositionnel en anglais : {node_id}")
    sections = _strings(row.get("sections"), f"sections de {node_id}")
    if sections != _expected_sections(fr_meta.get("rubriques") or [], preserve_source_order=bool(authoritative_source_preservation_policy)) or row.get("sections_exactly_mapped") is not True:
        raise TranslationReviewError(f"Sections anglaises divergentes pour {node_id}")
    keywords = _strings(row.get("keywords"), f"keywords de {node_id}", allow_source_duplicates=bool(authoritative_source_preservation_policy))
    if keywords != _expected_keywords(fr_meta.get("keywords") or [], mapping) or row.get("keywords_exactly_mapped") is not True:
        raise TranslationReviewError(f"Keywords anglais divergents pour {node_id}")
    if source_page_origin == "new" and not 2 <= len(keywords) <= 4:
        raise TranslationReviewError(f"Un argument issu d’une source française nouvelle doit comporter deux à quatre keywords : {node_id}")
    if row.get("keywords_order_preserved_by_relevance") is not True:
        raise TranslationReviewError(f"Ordre de pertinence des keywords non attesté pour {node_id}")
    raw_fr_summary = fr_content.get("summary")
    summary_provenance = str(fr_content.get("summary_provenance") or "")
    historical_summary = summary_provenance in {"historical_existing", "historical_authorized_change", "historical_authorized_creation"}
    summary_absent = raw_fr_summary is None or not str(raw_fr_summary).strip()
    if summary_absent:
        if row.get("summary") not in (None, ""):
            raise TranslationReviewError(f"Un summary anglais ne peut pas être inventé lorsque le résumé français est historiquement absent : {node_id}")
        summary = None
        ratio = None
        expression = None
        numbers = []
        semantic_risks = []
        semantic_risk_note = ""
        semantic_evidence_note = ""
        evidence_rows = []
        source_opening = source_closing = target_opening = target_closing = ""
        for field in ("metadata_equivalent_to_french", "summary_equivalent_to_french", "title_is_idiomatic", "displayed_title_concision_reviewed", "displayed_title_semantically_equivalent"):
            if row.get(field) is not True:
                raise TranslationReviewError(f"Attestation anglaise manquante pour {node_id} : {field}")
    else:
        # A protected historical summary remains the authoritative source even
        # when it would be too short or stylistically non-conforming under the
        # rules for newly authored summaries.  Translation validation is
        # differential: require a non-empty faithful target, but do not force
        # creation-style minimum lengths onto the historical source.
        summary_minimum = 1 if historical_summary else 40
        summary = _text(row.get("summary"), f"summary de {node_id}", summary_minimum)
        _assert_english_wikicode_localized(summary, f"le summary de {node_id}")
        fr_summary = _text(raw_fr_summary, f"résumé français verrouillé de {node_id}", summary_minimum)
        en_metadiscourse = bool(META_DISCOURSE_EN.search(_plain(summary)))
        fr_metadiscourse = bool(META_DISCOURSE_FR.search(_plain(fr_summary)))
        if en_metadiscourse and not fr_metadiscourse:
            raise TranslationReviewError(f"Métadiscours ajouté uniquement en anglais dans le summary de {node_id}")
        ratio = len(_plain(summary)) / max(1, len(_plain(fr_summary)))
        if row.get("summary_ratio_reviewed") is not True:
            raise TranslationReviewError(f"Ratio anglais/français non revu pour {node_id} : {ratio:.2f}")
        if not 0.60 <= ratio <= 1.45:
            if historical_summary:
                ratio_rationale = str(row.get("summary_ratio_exception_rationale") or "").strip()
                if len(ratio_rationale) < 24:
                    raise TranslationReviewError(f"Ratio anglais/français historique hors plage pour {node_id} : {ratio:.2f}; une justification explicite de l’équivalence est requise")
            else:
                raise TranslationReviewError(f"Ratio anglais/français hors limites pour {node_id} : {ratio:.2f}")
        required_summary_fields = (
            "metadata_equivalent_to_french",
            "summary_equivalent_to_french",
            "title_is_idiomatic",
            "displayed_title_concision_reviewed",
            "displayed_title_semantically_equivalent",
        )
        # SUMMARY_TRUE_FIELDS describe the quality profile of newly authored
        # summaries.  They are not retroactive constraints on an exact
        # historical source carried into translation.
        if not historical_summary:
            required_summary_fields = (*required_summary_fields, *SUMMARY_TRUE_FIELDS)
        for field in required_summary_fields:
            if row.get(field) is not True:
                raise TranslationReviewError(f"Attestation anglaise manquante pour {node_id} : {field}")
        if row.get("summary_subject_predicate_scope_modality_reviewed") is not True:
            raise TranslationReviewError(f"Revue structurée sujet/prédicat/portée/modalité du summary absente pour {node_id}")
        for field in ("summary_opening_proposition_preserved", "summary_closing_proposition_preserved", "summary_conditions_exclusivities_preserved", "summary_decisive_premises_preserved"):
            if row.get(field) is not True:
                raise TranslationReviewError(f"Attestation propositionnelle du summary absente pour {node_id} : {field}")
        semantic_evidence_note = _text(row.get("summary_semantic_evidence_note"), f"preuve sémantique du summary de {node_id}", 24)
        semantic_risks = sorted(set(
            _semantic_risk_signals(fr_summary, summary)
            + _semantic_risk_signals(fr_canonical, canonical)
            + _semantic_risk_signals(fr_displayed, displayed)
        ))
        if semantic_risks:
            if row.get("semantic_risk_reviewed") is not True:
                raise TranslationReviewError(f"Risques sémantiques non revus pour {node_id} : {semantic_risks}")
            semantic_risk_note = _text(row.get("semantic_risk_note"), f"note de risque sémantique de {node_id}", 24)
            evidence_rows = row.get("semantic_risk_evidence")
            if not isinstance(evidence_rows, list):
                raise TranslationReviewError(f"Preuves des risques sémantiques invalides pour {node_id}")
            covered = set()
            source_blob = " ".join((fr_canonical, fr_displayed, fr_summary)).casefold()
            target_blob = " ".join((canonical, displayed, summary)).casefold()
            for evidence_row in evidence_rows:
                if not isinstance(evidence_row, dict) or str(evidence_row.get("risk") or "") not in semantic_risks:
                    raise TranslationReviewError(f"Preuve de risque sémantique inconnue pour {node_id}")
                risk = str(evidence_row.get("risk"))
                source_excerpt = _text(evidence_row.get("source_excerpt"), f"extrait source du risque {risk} de {node_id}", 3)
                target_excerpt = _text(evidence_row.get("target_excerpt"), f"extrait cible du risque {risk} de {node_id}", 3)
                _text(evidence_row.get("note"), f"note de preuve du risque {risk} de {node_id}", 12)
                if _plain(source_excerpt).casefold() not in _plain(source_blob).casefold() or _plain(target_excerpt).casefold() not in _plain(target_blob).casefold():
                    raise TranslationReviewError(f"Extrait de preuve sémantique absent du contenu pour {node_id} : {risk}")
                covered.add(risk)
            if covered != set(semantic_risks):
                raise TranslationReviewError(f"Chaque risque sémantique doit avoir une preuve source/cible pour {node_id}")
        else:
            semantic_risk_note = str(row.get("semantic_risk_note") or "").strip()
            evidence_rows = []
        source_opening, source_closing = _proposition_edges(fr_summary)
        target_opening, target_closing = _proposition_edges(summary)
        if historical_summary:
            expression = None
        else:
            expression = _text(row.get("forceful_expression"), f"expression de force anglaise de {node_id}", 8)
            if _plain(expression).casefold() not in _plain(summary).casefold():
                raise TranslationReviewError(f"L’expression de force anglaise est absente du summary de {node_id}")
        numbers = NUMBER.findall(_plain(summary))
        if numbers and (row.get("quantitative_claims_verified") is not True or len(str(row.get("quantitative_claims_note") or "").strip()) < 12):
            from wikidebia_translation_source import POLICY, historical_numbers_preserved
            preserved = historical_summary and source_page_origin == "preexisting" and (
                authoritative_source_page_origin == "preexisting"
                or authoritative_source_preservation_policy == POLICY and fr_content.get("source_preservation_policy") == POLICY
            )
            if not (preserved and row.get("historical_quantitative_transfer_reviewed") is True
                    and len(str(row.get("historical_quantitative_transfer_note") or "").strip()) >= 24
                    and historical_numbers_preserved(fr_summary, summary)):
                raise TranslationReviewError(f"Donnée chiffrée anglaise non vérifiée dans {node_id}")
    citations = _validate_citations(row.get("citations"), fr_content.get("citations") or [], node_id)
    try:
        passages = validate_translations(row.get("citation_passages", []), fr_content.get("citation_passages") or [], node_id)
    except ValueError as exc:
        raise TranslationReviewError(str(exc)) from exc
    for passage in passages:
        _assert_english_wikicode_localized(passage["text"], "passage hors Citation de " + node_id)
    selected = row.get("sources")
    if not isinstance(selected, dict) or set(selected) != set(ARGUMENT_BUCKETS):
        raise TranslationReviewError(f"Sélection documentaire anglaise absente pour {node_id}")
    final_sources: dict[str, list[str]] = {}
    for bucket, stype in ARGUMENT_BUCKETS.items():
        ids = _strings(selected.get(bucket), f"sources anglaises {bucket} de {node_id}")
        for sid in ids:
            source = sources.get(sid)
            if not source or source.get("type") != stype or not _has_usage(source, node_id, {"supports_summary"}):
                raise TranslationReviewError(f"Source anglaise incompatible pour {node_id} : {sid}")
        final_sources[bucket] = ids
    _text(row.get("documentation_rationale"), f"justification documentaire anglaise de {node_id}", 12)
    _text(row.get("reviewer"), f"relecteur anglais de {node_id}", 3)
    _text(row.get("reviewed_at"), f"date de revue anglaise de {node_id}", 10)
    _text(row.get("note"), f"note de revue anglaise de {node_id}", 12)
    lifecycle = _validate_page_lifecycle(row, "argument", node_id)
    fr_preserved = fr_content.get("preserved_parameters") or {}
    fr_dedicated_state = fr_preserved.get("débat-dédié") or fr_preserved.get("débat-détaillé") or {}
    if fr_dedicated_state.get("present") is True:
        dedicated_debate = _text(
            row.get("dedicated_debate"), f"dedicated-debate anglais de {node_id}", 8,
        )
        if row.get("dedicated_debate_equivalent_to_french") is not True:
            raise TranslationReviewError(
                f"Le dedicated-debate anglais doit traduire le débat-dédié français : {node_id}"
            )
        dedicated_debate_review_note = _text(
            row.get("dedicated_debate_review_note"),
            f"note de traduction du dedicated-debate de {node_id}", 12,
        )
    else:
        if row.get("dedicated_debate") not in (None, ""):
            raise TranslationReviewError(f"dedicated-debate anglais inventé sans source française : {node_id}")
        dedicated_debate = None
        dedicated_debate_review_note = ""
    argument_name, name_discovery = _validate_argument_name_discovery(row, node_id, lifecycle["page_origin"])
    dedicated_debate = _validate_dedicated_debate(row, node_id)
    existing_update = row.get("existing_english_update")
    if existing_update is not None:
        if (lifecycle["page_origin"] != "preexisting" or not isinstance(existing_update, dict)
                or existing_update.get("owner_approved") is not True
                or existing_update.get("decision") != "explicit_user_request"
                or existing_update.get("title") != canonical
                or existing_update.get("page_id") != node_id
                or existing_update.get("language") != "en"
                or not isinstance(existing_update.get("observed_revision_id"), int)
                or existing_update["observed_revision_id"] <= 0
                or not re.fullmatch(r"[a-f0-9]{64}", str(existing_update.get("observed_sha256") or ""))):
            raise TranslationReviewError(f"Autorisation de reprise anglaise invalide : {node_id}")
        _text(existing_update.get("instruction"), f"instruction propriétaire anglaise {node_id}", 24)
        _text(existing_update.get("reason"), f"motif de reprise anglaise {node_id}", 24)
    return {
        **({"existing_english_update": copy.deepcopy(existing_update)} if existing_update is not None else {}),
        **dedicated_debate,
        "id": node_id, "canonical_title": canonical, "displayed_title": displayed,
        "sections": sections, "keywords": keywords, "summary": summary, "citations": citations, "citation_passages": passages, "sources": final_sources,
        "summary_provenance": summary_provenance or ("historical_absent" if summary_absent else "translated_source"),
        "summary_length_ratio": (round(ratio, 4) if ratio is not None else None),
        "summary_ratio_reviewed": bool(row.get("summary_ratio_reviewed")) if ratio is not None else True,
        "summary_ratio_exception_rationale": str(row.get("summary_ratio_exception_rationale") or "").strip(),
        "source_page_origin": source_page_origin, "forceful_expression": expression,
        "dedicated_debate": dedicated_debate,
        "dedicated_debate_equivalent_to_french": dedicated_debate is not None,
        "dedicated_debate_review_note": dedicated_debate_review_note,
        "quantitative_claims": numbers, "quantitative_claims_verified": bool(row.get("quantitative_claims_verified")),
        "quantitative_claims_note": row.get("quantitative_claims_note"),
        "historical_quantitative_transfer_reviewed": bool(row.get("historical_quantitative_transfer_reviewed")),
        "historical_quantitative_transfer_note": row.get("historical_quantitative_transfer_note"),
        "reviewer": row.get("reviewer"), "reviewed_at": row.get("reviewed_at"), "note": row.get("note"),
        "argument_name": argument_name, "argument_name_discovery": name_discovery,
        "canonical_title_semantic_inventory_reviewed": True,
        "canonical_title_semantic_inventory_note": canonical_inventory_note,
        "canonical_title_equivalent_to_french": True,
        "canonical_title_subject_preserved": True, "canonical_title_predicate_preserved": True,
        "canonical_title_scope_preserved": True, "canonical_title_modality_preserved": True,
        "displayed_title_source_form": source_form, "displayed_title_target_form": target_form,
        "displayed_title_source_form_reviewed": True, "displayed_title_no_formal_regression": True,
        "displayed_title_semantic_inventory_reviewed": True, "displayed_title_semantic_inventory_note": semantic_inventory_note,
        "displayed_title_subject_preserved": True, "displayed_title_predicate_preserved": True,
        "displayed_title_scope_preserved": True, "displayed_title_modality_preserved": True,
        "summary_subject_predicate_scope_modality_reviewed": bool(row.get("summary_subject_predicate_scope_modality_reviewed")) if summary is not None else True,
        "displayed_title_is_complete_proposition": bool(row.get("displayed_title_is_complete_proposition")),
        "displayed_title_translates_french_displayed_title": True,
        "displayed_title_identity_pattern_reviewed": bool(row.get("displayed_title_identity_pattern_reviewed")),
        "displayed_title_identity_pattern_note": str(row.get("displayed_title_identity_pattern_note") or "").strip(),
        "displayed_title_form_change_reviewed": bool(row.get("displayed_title_form_change_reviewed")) if source_form != target_form else True,
        "displayed_title_speech_act_preserved": bool(row.get("displayed_title_speech_act_preserved")) if source_form != target_form else True,
        "displayed_title_form_change_note": str(row.get("displayed_title_form_change_note") or "").strip(),
        "summary_opening_proposition_preserved": bool(row.get("summary_opening_proposition_preserved")) if summary is not None else True,
        "summary_closing_proposition_preserved": bool(row.get("summary_closing_proposition_preserved")) if summary is not None else True,
        "summary_conditions_exclusivities_preserved": bool(row.get("summary_conditions_exclusivities_preserved")) if summary is not None else True,
        "summary_decisive_premises_preserved": bool(row.get("summary_decisive_premises_preserved")) if summary is not None else True,
        "summary_semantic_evidence": {
            "source_opening": source_opening, "target_opening": target_opening,
            "source_closing": source_closing, "target_closing": target_closing,
            "note": semantic_evidence_note,
        } if summary is not None else None,
        "semantic_risks": semantic_risks,
        "semantic_risk_reviewed": bool(row.get("semantic_risk_reviewed")) if semantic_risks else True,
        "semantic_risk_note": semantic_risk_note,
        "semantic_risk_evidence": copy.deepcopy(evidence_rows),
        "field_sha256": {
            "fr_canonical_title": _field_sha256(fr_canonical), "en_canonical_title": _field_sha256(canonical),
            "fr_displayed_title": _field_sha256(fr_displayed), "en_displayed_title": _field_sha256(displayed),
            "fr_summary": _field_sha256(raw_fr_summary or ""), "en_summary": _field_sha256(summary or ""),
        },
        **lifecycle,
    }


def finalize_review(project_root: Path, debate_id: str, work_id: str) -> dict[str, Any]:
    workspace, meta = _load_workspace(project_root, debate_id, work_id)
    if meta.get("status") not in {"en_translation_review_ready", "en_translation_review_finalized"}:
        raise TranslationReviewError(f"Statut incompatible avec la finalisation anglaise : {meta.get('status')}")
    _assert_source_unchanged(project_root, debate_id, meta)
    source = _assert_content_copy(workspace, meta)
    review_path = workspace / "reviews/en/translation_review.json"
    review = load_json(review_path, "revue anglaise")
    if review.get("status") == "approved" and review.get("review_sha256"):
        if review.get("review_sha256") != translation_review_sha256(review):
            raise TranslationReviewError("Empreinte de revue anglaise invalide")
        if review.get("prepared_content_reviewed_copy_sha256") != full_tree_sha256(source):
            raise TranslationReviewError("content-reviewed-copy a changé depuis la finalisation anglaise")
        return {"status": "en_translation_review_finalized", "debate_id": debate_id, "work_id": work_id, "review_sha256": review["review_sha256"], "idempotent": True}
    if review.get("schema") != TRANSLATION_REVIEW_SCHEMA or review.get("debate_id") != debate_id or review.get("work_id") != work_id:
        raise TranslationReviewError("Schéma ou identité de revue anglaise invalide")
    if review.get("prepared_content_reviewed_copy_sha256") != full_tree_sha256(source):
        raise TranslationReviewError("Base française divergente pour la revue anglaise")
    registry, metadata_lock, content_lock, vocabulary_fr = _source_snapshot(source)
    french_source_rows = load_json(source / "data/sources.json", "sources françaises").get("sources") or []
    french_ids = {str(row.get("id")) for row in french_source_rows}
    english_rows, by_source = _validate_sources(load_json(workspace / "data/sources_en_working.json", "sources anglaises"), debate_id, french_ids)
    vocabulary, keyword_map = _validate_vocabulary(review.get("vocabulary"), vocabulary_fr.get("entries") or [])
    authoritative_debate_origin = _french_source_page_origin(metadata_lock.get("debate") or {}, content_lock.get("debate") or {})
    source_policy = content_lock.get("source_preservation_policy")
    if (review.get("debate") or {}).get("french") != {"metadata": metadata_lock.get("debate"), "content": content_lock.get("debate")}:
        raise TranslationReviewError("La source française intégrée de Debate diffère du snapshot autoritatif")
    final_debate = _validate_debate(
        review.get("debate") or {}, keyword_map, by_source, debate_id,
        authoritative_source_page_origin=authoritative_debate_origin,
        authoritative_source_preservation_policy=source_policy,
    )
    items = review.get("arguments")
    if not isinstance(items, list):
        raise TranslationReviewError("Liste des arguments anglais absente")
    active_nodes = [node for node in ((registry.get("graph") or {}).get("nodes") or []) if node.get("status") == "active"]
    translation_ids = {
        str(node.get("id"))
        for node in active_nodes
        if not _reuses_existing_english_page(node)
    }
    if {str(item.get("id")) for item in items if isinstance(item, dict)} != translation_ids:
        raise TranslationReviewError("La revue anglaise ne couvre pas exactement les arguments restant à traduire")
    fr_meta_by_id = {str(row.get("entity_id") or row.get("id")): row for row in (metadata_lock.get("arguments") or []) if isinstance(row, dict)}
    fr_content_by_id = {str(row.get("id")): row for row in (content_lock.get("arguments") or []) if isinstance(row, dict)}
    final_arguments = []
    for item in items:
        node_id = str(item.get("id") or "")
        authoritative_origin = _french_source_page_origin(fr_meta_by_id.get(node_id) or {}, fr_content_by_id.get(node_id) or {})
        if (item.get("translation") or {}).get("french") != {"metadata": fr_meta_by_id.get(node_id), "content": fr_content_by_id.get(node_id)}:
            raise TranslationReviewError("Source française intégrée divergente du snapshot autoritatif : " + node_id)
        final_arguments.append(_validate_argument(item, keyword_map, by_source, authoritative_source_page_origin=authoritative_origin, authoritative_source_preservation_policy=source_policy))
    if (
        _requires_relation_label_review(metadata_lock, content_lock)
        or _historical_relation_labels_required(content_lock)
    ):
        from wikidebia_translation_source import validate_relation_labels
        reused_ids = {
            str(node.get("id"))
            for node in active_nodes
            if _reuses_existing_english_page(node)
        }
        contextual_labels = validate_relation_labels(
            review.get("relation_labels"),
            source,
            exclude_target_node_ids=reused_ids,
        )
        final_debate["relation_labels"] = [r for r in contextual_labels if r["source_page_id"] == "debate"]
        for argument in final_arguments:
            argument["relation_labels"] = [r for r in contextual_labels if r["source_page_id"] == argument["id"]]
    canonical_titles = [row["canonical_title"].casefold() for row in final_arguments]
    reused_titles = [
        str((node.get("en") or {}).get("canonical_title") or "").casefold()
        for node in active_nodes
        if _reuses_existing_english_page(node)
    ]
    all_argument_titles = [*canonical_titles, *reused_titles]
    if len(set(all_argument_titles)) != len(all_argument_titles) or final_debate["canonical_title"].casefold() in all_argument_titles:
        raise TranslationReviewError("Collision de titres canoniques anglais")
    exact = sum(row["canonical_title"].casefold() == row["displayed_title"].casefold() for row in final_arguments)
    generated_arguments = [row for row in final_arguments if row.get("source_page_origin") == "new"]
    keyword_sets = collections.Counter(tuple(row["keywords"]) for row in generated_arguments)
    if generated_arguments and max(keyword_sets.values(), default=0) / len(generated_arguments) > 0.25:
        raise TranslationReviewError("Un même jeu exact de keywords domine plus de 25 % des arguments issus d’une création")
    review_units = review.get("review_units")
    if not isinstance(review_units, list) or (items and not review_units):
        raise TranslationReviewError("Plan d’unités de revue anglaise absent")
    covered: list[str] = []
    for unit in review_units:
        if not isinstance(unit, dict) or unit.get("status") != "approved":
            raise TranslationReviewError("Toutes les unités de revue anglaise doivent être closes indépendamment")
        page_ids = unit.get("page_ids")
        if not isinstance(page_ids, list) or not page_ids:
            raise TranslationReviewError("Unité de revue anglaise vide ou invalide")
        if len(page_ids) > int(unit.get("target_size") or 0):
            raise TranslationReviewError(f"Unité de revue trop grande pour son risque déclaré : {unit.get('id')}")
        _text(unit.get("reviewer"), f"relecteur de l’unité {unit.get('id')}", 3)
        _text(unit.get("reviewed_at"), f"date de l’unité {unit.get('id')}", 10)
        _text(unit.get("note"), f"note de l’unité {unit.get('id')}", 12)
        covered.extend(str(x) for x in page_ids)
    if sorted(covered) != sorted(str(item.get("id")) for item in items) or len(covered) != len(set(covered)):
        raise TranslationReviewError("Les unités de revue ne couvrent pas exactement chaque argument une fois")
    global_review = review.get("global_review") or {}
    for field in ("all_entities_translated", "all_equivalences_reviewed", "all_selected_sources_verified", "relations_and_occurrences_unchanged", "no_final_pages_generated", "remote_access_not_used"):
        if global_review.get(field) is not True:
            raise TranslationReviewError(f"Attestation globale anglaise manquante : {field}")
    if global_review.get("blocking_issues") not in ([], None):
        raise TranslationReviewError("La revue anglaise contient encore des blocages")
    _text(global_review.get("reviewer"), "relecteur global anglais", 3)
    _text(global_review.get("reviewed_at"), "date de revue globale anglaise", 10)
    _text(global_review.get("note"), "note de revue globale anglaise", 12)
    selected_ids: set[str] = set()
    for ids in final_debate["documentation"].values(): selected_ids.update(ids)
    for arg in final_arguments:
        for ids in arg["sources"].values(): selected_ids.update(ids)
    if selected_ids != set(by_source):
        raise TranslationReviewError(f"Le registre anglais doit couvrir exactement les sources retenues; inutilisées={sorted(set(by_source)-selected_ids)}, absentes={sorted(selected_ids-set(by_source))}")
    finalized = copy.deepcopy(review)
    finalized.update({
        "kit_version": KIT_VERSION, "status": "approved", "finalized_at": now_iso(),
        "source_registry_sha256": sha256_bytes(canonical_json({"source_registry_version": "1.0", "debate_id": debate_id, "sources": english_rows})),
        "final_values": {"debate": final_debate, "arguments": final_arguments, "vocabulary": vocabulary, "sources": english_rows},
        "summary": {"arguments": len(final_arguments), "vocabulary_entries": len(vocabulary), "sources": len(english_rows), "debate_documentary_references": sum(len(v) for v in final_debate["documentation"].values()), "argument_documentary_references": sum(len(v) for arg in final_arguments for v in arg["sources"].values()), "citations": sum(len(arg.get("citations") or []) for arg in final_arguments)},
        "review_sha256": None,
    })
    finalized["semantic_content_sha256"] = semantic_content_sha256(finalized)
    finalized["review_sha256"] = translation_review_sha256(finalized)
    write_json(review_path, finalized)
    meta = copy.deepcopy(meta)
    meta["kit_version"] = KIT_VERSION
    meta["status"] = "en_translation_review_finalized"
    meta["english_translation_review"] = {"status": "finalized", "review_sha256": finalized["review_sha256"], "finalized_at": finalized["finalized_at"], "prepared_content_reviewed_copy_sha256": finalized["prepared_content_reviewed_copy_sha256"]}
    meta["workspace_sha256"] = None
    meta["workspace_sha256"] = workspace_receipt_hash(meta)
    write_json(workspace / "workspace.json", meta)
    return {"status": "en_translation_review_finalized", "debate_id": debate_id, "work_id": work_id, "review_sha256": finalized["review_sha256"], **finalized["summary"], "content_reviewed_copy_mutated": False, "final_pages_generated": False}


def _merge_introduction_review(path: Path, debate: Mapping[str, Any]) -> None:
    data = load_json(path, "revue des introductions") if path.is_file() else {"normative_revision": NORM_VERSION, "entries": []}
    entries = [row for row in data.get("entries") or [] if row.get("language") != "en"]
    source_page_origin = str(debate.get("source_page_origin") or "new")
    profile = (
        {field: True for field in INTRO_TRUE_FIELDS}
        if source_page_origin == "new"
        else {
            **{field: bool(debate.get(field)) for field in HISTORICAL_INTRO_TRANSLATION_TRUE_FIELDS},
            **{field: bool(debate.get(field)) for field in HISTORICAL_INTRO_UNIVERSAL_TRUE_FIELDS},
        }
    )
    entries.append({"language": "en", "source_page_origin": source_page_origin, **profile, "introduction_adaptation_rationale": debate.get("introduction_adaptation_rationale"), "documentation_family_notes": copy.deepcopy(debate.get("documentation_family_notes") or {}), "common_acronym": None, "topic_label_rationale": debate.get("topic_label_rationale"), "complete_topic_initial_capital_justification": debate.get("complete_topic_initial_capital_justification"), "subsections": copy.deepcopy(debate.get("subsections") or []), "specialized_term_inventory": copy.deepcopy(debate.get("specialized_term_inventory") or []), "canonical_title_semantic_inventory_reviewed": bool(debate.get("canonical_title_semantic_inventory_reviewed")), "canonical_title_semantic_inventory_note": debate.get("canonical_title_semantic_inventory_note"), "topic_semantic_equivalence_reviewed": bool(debate.get("topic_semantic_equivalence_reviewed")), "complete_topic_semantic_equivalence_reviewed": bool(debate.get("complete_topic_semantic_equivalence_reviewed")), "introduction_claim_inventory_reviewed": bool(debate.get("introduction_claim_inventory_reviewed")), "introduction_claim_inventory_note": debate.get("introduction_claim_inventory_note"), "subsection_structure_equivalence_reviewed": bool(debate.get("subsection_structure_equivalence_reviewed"))})
    data["entries"] = entries
    write_json(path, data)


def _summary_mechanism_excerpt(summary: Any) -> str:
    text = str(summary or "").strip()
    if not text:
        return "The reviewed summary explicitly states the central mechanism supporting the claim."
    first = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0].strip()
    return first if len(first) >= 30 else text


def _merge_summary_review(path: Path, arguments: Sequence[Mapping[str, Any]], debate_id: str) -> None:
    data = load_json(path, "revue des résumés") if path.is_file() else {"normative_revision": NORM_VERSION, "entries": []}
    by_id = {str(row.get("id")): row for row in data.get("entries") or []}
    for arg in arguments:
        entry = by_id.setdefault(arg["id"], {"id": arg["id"], "languages": {}})
        if arg.get("summary") is None:
            entry.setdefault("languages", {})["en"] = {
                "status": "historical_absent",
                "historical_absence_verified": True,
                "note": arg.get("note") or "French source summary is historically absent and the English parameter is omitted.",
            }
        elif arg.get("summary_provenance") in {"historical_existing", "historical_authorized_change", "historical_authorized_creation"}:
            entry.setdefault("languages", {})["en"] = {
                "status": "translated_historical_source",
                "historical_source_preserved": True,
                "summary_ratio_reviewed": bool(arg.get("summary_ratio_reviewed")),
                "summary_length_ratio": arg.get("summary_length_ratio"),
                "summary_ratio_exception_rationale": arg.get("summary_ratio_exception_rationale") or "",
                "note": arg.get("note") or "English summary faithfully translates a protected historical French summary without retroactive style rewriting.",
            }
        else:
            entry.setdefault("languages", {})["en"] = {
                "status": "translated_and_reviewed", "thesis_first": True, "general_public_style": True,
                "sentence_rhythm_reviewed": True, "technical_terms_reviewed": True,
                "opening_develops_title": True, "example_or_data_reviewed": True,
                "assertive_tone_reviewed": True, "no_artificial_example_or_number": True,
                "no_polemical_overstatement": True, "conviction_visible": True,
                "wikipedia_hover_links_reviewed": True, "specialized_terms_linked_or_explained": True,
                "forceful_expression": arg.get("forceful_expression"),
                "originality_reviewed": True,
                "mechanism_statement": _summary_mechanism_excerpt(arg.get("summary")),
                "quantitative_claims_verified": arg.get("quantitative_claims_verified"),
                "quantitative_claims_note": arg.get("quantitative_claims_note"), "note": arg.get("note"),
            }
    data["schema_version"] = "1.0"
    data["normative_revision"] = NORM_VERSION
    data.pop("quality_policy_revision", None)
    data["debate_id"] = debate_id
    data["entries"] = [by_id[key] for key in sorted(by_id)]
    write_json(path, data)


def _build_translated_copy(project_root: Path, source: Path, target: Path, review: Mapping[str, Any], debate_id: str, work_id: str) -> dict[str, Any]:
    shutil.copytree(source, target, symlinks=False, copy_function=shutil.copy2)
    convergence_source = target.parent / "reviews/en/semantic_convergence_review.json"
    if not convergence_source.is_file():
        raise TranslationReviewError("Reçu de convergence sémantique absent avant construction de translated-copy")
    convergence_receipt = load_json(convergence_source, "reçu de convergence sémantique")
    verify_semantic_convergence_receipt(convergence_receipt, review)
    convergence_target = target / "reviews/en/semantic_convergence_review.json"
    convergence_target.parent.mkdir(parents=True, exist_ok=True)
    write_json(convergence_target, convergence_receipt)
    reviewed_final = review["final_values"]
    french_sources = load_json(target / "data/sources.json", "sources françaises")
    merged_sources, documentary_source_id_remap = _merge_translated_sources_with_existing(
        french_sources.get("sources") or [], reviewed_final.get("sources") or []
    )
    final = _remap_final_source_ids(reviewed_final, documentary_source_id_remap)
    registry = load_json(target / "data/registre_debat.json", "registre du débat")
    old_structural = str((((registry.get("graph") or {}).get("lifecycle") or {}).get("structural_sha256") or ""))
    by_id = {row["id"]: row for row in final["arguments"]}
    debate_pages = (registry.setdefault("debate", {}).setdefault("pages", {}))
    en_debate = debate_pages.setdefault("en", {})
    en_debate["canonical_title"] = final["debate"]["canonical_title"]
    en_debate["title_status"] = "validated"
    fr_debate = debate_pages.setdefault("fr", {})
    fr_debate.setdefault("interlanguage", {})["target_title"] = final["debate"]["canonical_title"]
    fr_debate["interlanguage"]["status"] = "ready"
    operations: list[dict[str, Any]] = []
    for node in ((registry.get("graph") or {}).get("nodes") or []):
        if node.get("status") != "active": continue
        if _reuses_existing_english_page(node):
            existing_title = str((node.get("en") or {}).get("canonical_title") or "")
            node.setdefault("pages", {}).setdefault("fr", {}).setdefault(
                "interlanguage", {}
            ).update({"target_title": existing_title, "status": "ready"})
            continue
        row = by_id[str(node.get("id"))]
        en = node.setdefault("en", {})
        before = copy.deepcopy(en)
        en.update({"canonical_title": row["canonical_title"], "displayed_title": row["displayed_title"], "sections": copy.deepcopy(row["sections"]), "keywords": copy.deepcopy(row["keywords"]), "title_status": "validated"})
        node.setdefault("sources", {}).setdefault("en", {}).update(copy.deepcopy(row["sources"]))
        pages = node.setdefault("pages", {})
        pages.setdefault("fr", {}).setdefault("interlanguage", {})["target_title"] = row["canonical_title"]
        pages["fr"]["interlanguage"]["status"] = "ready"
        operations.append({"entity_type": "argument", "entity_id": row["id"], "field": "english_projection", "before": before, "after": copy.deepcopy(en)})
    new_structural = structural_sha256(registry)
    lifecycle = (registry.get("graph") or {}).get("lifecycle") or {}
    lifecycle["structural_sha256"] = new_structural
    projection = load_json(target / "graph/graphe_argumentatif.json", "projection du graphe")
    projection["nodes"] = copy.deepcopy((registry.get("graph") or {}).get("nodes") or [])
    projection["lifecycle"] = copy.deepcopy(lifecycle)
    timestamp = now_iso()
    metadata_lock = {
        "schema": EN_METADATA_LOCK_SCHEMA, "schema_version": "1.0", "normative_revision": NORM_VERSION,
        "kit_version": KIT_VERSION, "debate_id": debate_id, "work_id": work_id, "language": "en",
        "status": "locked_for_generation", "review_sha256": review["review_sha256"], "applied_at": timestamp,
        "old_structural_sha256": old_structural, "new_structural_sha256": new_structural,
        "debate": {k: copy.deepcopy(final["debate"][k]) for k in (
            "canonical_title", "topic", "complete_topic", "sections", "keywords", "source_page_origin",
            "canonical_title_semantic_inventory_reviewed", "canonical_title_semantic_inventory_note",
            "topic_semantic_equivalence_reviewed", "complete_topic_semantic_equivalence_reviewed",
            "introduction_claim_inventory_reviewed", "introduction_claim_inventory_note",
            "subsection_structure_equivalence_reviewed", "debate_field_semantic_risks", "debate_field_semantic_risk_reviewed",
            "debate_field_semantic_risk_note", "debate_field_semantic_risk_evidence", "field_sha256", "reviewer", "reviewed_at", "note"
        )},
        "arguments": [{k: copy.deepcopy(row[k]) for k in (
            "id", "canonical_title", "displayed_title", "sections", "keywords", "source_page_origin",
            "dedicated_debate", "dedicated_debate_equivalence_reviewed", "dedicated_debate_review_note",
            "canonical_title_semantic_inventory_reviewed", "canonical_title_semantic_inventory_note",
            "canonical_title_equivalent_to_french", "canonical_title_subject_preserved", "canonical_title_predicate_preserved",
            "canonical_title_scope_preserved", "canonical_title_modality_preserved", "displayed_title_source_form", "displayed_title_target_form",
            "displayed_title_source_form_reviewed", "displayed_title_no_formal_regression",
            "displayed_title_semantic_inventory_reviewed", "displayed_title_semantic_inventory_note",
            "displayed_title_subject_preserved", "displayed_title_predicate_preserved", "displayed_title_scope_preserved", "displayed_title_modality_preserved",
            "displayed_title_form_change_reviewed", "displayed_title_speech_act_preserved", "displayed_title_form_change_note",
            "summary_subject_predicate_scope_modality_reviewed", "displayed_title_is_complete_proposition", "semantic_risks", "semantic_risk_reviewed",
            "semantic_risk_note", "semantic_risk_evidence", "field_sha256", "reviewer", "reviewed_at", "note"
        ) if k in row or k not in {"dedicated_debate", "dedicated_debate_equivalence_reviewed", "dedicated_debate_review_note"}} for row in final["arguments"]],
    }
    content_lock = {
        "schema": EN_CONTENT_LOCK_SCHEMA, "schema_version": "1.0", "normative_revision": NORM_VERSION,
        "kit_version": KIT_VERSION, "debate_id": debate_id, "work_id": work_id, "language": "en",
        "status": "locked_for_generation", "review_sha256": review["review_sha256"],
        "source_registry_sha256": review["source_registry_sha256"], "applied_at": timestamp,
        "debate": copy.deepcopy(final["debate"]), "arguments": copy.deepcopy(final["arguments"]),
    }
    translation_lock = {
        "schema": TRANSLATION_LOCK_SCHEMA, "schema_version": "1.0", "normative_revision": NORM_VERSION,
        "kit_version": KIT_VERSION, "debate_id": debate_id, "work_id": work_id,
        "source_language": "fr", "target_language": "en", "status": "locked_for_generation",
        "review_sha256": review["review_sha256"], "french_metadata_review_sha256": review["french_metadata_review_sha256"],
        "french_content_review_sha256": review["french_content_review_sha256"],
        "semantic_content_sha256": review.get("semantic_content_sha256"),
        "semantic_convergence_receipt_sha256": convergence_receipt.get("receipt_sha256"),
        "semantic_convergence_pass_count": len(convergence_receipt.get("passes") or []),
        "applied_at": timestamp,
        "relations_and_occurrences_unchanged": True, "argument_count": len(final["arguments"]),
        "vocabulary_count": len(final["vocabulary"]), "source_count": len(final["sources"]),
        "citation_count": sum(len(arg.get("citations") or []) for arg in final["arguments"]),
        "citation_translation_policy": {
            "translated_value_fields": ["citation->quote", "date->date"],
            "parameter_names": "all_french_parameter_names_are_mapped_to_declared_english_names",
            "preserved_values": "all_values_except_quote_and_date",
            "parameter_mapping": copy.deepcopy(CITATION_PARAMETER_MAP),
            "warning_parameter": "warnings",
            "warning_value": TRANSLATED_CITATION_WARNING,
            "warning_separator": ", ",
        },
    }
    vocabulary = load_json(target / "data/keyword_vocabulary.json", "vocabulaire français")
    if content_lock.get("source_preservation_policy") or load_json(source / "data/fr_content_lock.json", "source française").get("source_preservation_policy"):
        for entry in vocabulary.get("entries") or []:
            multiword = len(str(entry.get("fr") or "").split()) > 1
            entry.update(scope="site_navigation",cross_debate_reusable=True,local_frequency_is_validity_criterion=False,
                usage_count_in_debate=len(entry.get("usages") or []),atomic_concept=True,compositional_intersection=False,
                multiword_exception=multiword)
            if multiword:
                entry["multiword_exception_rationale"] = "Locution thématique conservée et relue dans la traduction : " + str(entry["fr"])
        write_json(target / "data/keyword_vocabulary.json", vocabulary)
    by_fr = {row["fr"]: row for row in final["vocabulary"]}
    bilingual_entries = []
    for row in vocabulary.get("entries") or []:
        merged = copy.deepcopy(row)
        translated = by_fr[str(row.get("fr"))]
        merged.update({"concept_id": translated.get("concept_id") or merged.get("concept_id"), "en": translated["en"], "definition_en": translated["definition_en"], "capitalization_rationale_en": translated.get("capitalization_rationale_en", ""), "status": "approved_bilingual", "english_review": {"reviewer": translated["reviewer"], "reviewed_at": translated["reviewed_at"], "note": translated["note"]}})
        merged.update(_english_keyword_form_metadata(translated["en"], {**row, **translated}))
        bilingual_entries.append(merged)
    changeset = {
        "schema": TRANSLATION_CHANGESET_SCHEMA, "schema_version": "1.0", "debate_id": debate_id,
        "work_id": work_id, "status": "applied", "review_sha256": review["review_sha256"],
        "applied_at": timestamp, "operation_count": len(operations) + 1,
        "operations": [{"entity_type": "debate", "entity_id": debate_id, "field": "english_projection", "before": None, "after": copy.deepcopy(final["debate"])}] + operations,
        "relations_mutated": False, "occurrences_mutated": False, "french_locks_mutated": False,
        "final_pages_generated": False, "remote_access": False,
    }
    write_json(target / "data/registre_debat.json", registry)
    write_json(target / "graph/graphe_argumentatif.json", projection)
    write_json(target / "data/sources.json", {"source_registry_version": "1.0", "debate_id": debate_id, "sources": merged_sources})
    build_documentary_resource_registry(target / "data/sources.json", target / "data/documentary_resources.json")
    write_json(target / "data/en_page_metadata_lock.json", metadata_lock)
    write_json(target / "data/en_content_lock.json", content_lock)
    write_json(target / "data/en_translation_lock.json", translation_lock)
    name_review_path = target / "reviews/argument_name_discovery_review.json"
    existing_name_review = load_json(name_review_path, "revue des noms d’arguments") if name_review_path.is_file() else {
        "version": "wikidebia-argument-name-discovery-review-1.2",
        "normative_revision": NORM_VERSION,
        "debate_id": debate_id,
        "entries": [],
    }
    name_entries = [row for row in (existing_name_review.get("entries") or []) if row.get("language") != "en"]
    for arg in final["arguments"]:
        if arg.get("page_origin") != "new":
            continue
        discovery = copy.deepcopy(arg.get("argument_name_discovery") or {})
        name_entries.append({
            "language": "en", "page_id": arg["id"], "title": arg["canonical_title"], "page_origin": "new",
            **discovery,
        })
    write_json(name_review_path, {
        "version": "wikidebia-argument-name-discovery-review-1.2",
        "normative_revision": NORM_VERSION,
        "debate_id": debate_id,
        "entries": name_entries,
    })
    write_json(target / "data/keyword_vocabulary_bilingual.json", {"schema": "wikidebia-keyword-vocabulary-bilingual-1.0", "normative_revision": NORM_VERSION, "debate_id": debate_id, "status": "approved_bilingual", "language_status": "bilingual_locked", "review_sha256": review["review_sha256"], "entries": bilingual_entries})
    write_json(target / "changes/en_translation_changeset.json", changeset)
    write_json(target / "reviews/en/translation_review.json", copy.deepcopy(review))
    _merge_introduction_review(target / "reviews/introduction_review.json", final["debate"])
    _merge_summary_review(target / "reviews/summary_style_review.json", final["arguments"], debate_id)
    manifest = load_json(target / "manifest.json", "manifest.json")
    manifest.setdefault("translation_status", {})["en"] = "ready"
    controls = manifest.setdefault("editorial_controls", {})
    controls["translation_validation_mode"] = "differential"
    controls["translation_semantic_review_schema_version"] = "1.4"
    controls["semantic_marker_engine_version"] = "1.3"
    controls["semantic_convergence_review_path"] = "reviews/en/semantic_convergence_review.json"
    controls["semantic_convergence_review_schema_version"] = "1.1"
    controls["quote_completeness_review_schema_version"] = "1.0"
    controls["documentary_resource_registry_path"] = "data/documentary_resources.json"
    controls["documentary_resource_registry_schema_version"] = "1.0"
    controls["argument_name_discovery_path"] = "reviews/argument_name_discovery_review.json"
    required_reports = controls.setdefault("required_reports", [])
    for rel in ("reports/en_translation_preflight.json", "reports/en_translation_validation.json"):
        if rel not in required_reports: required_reports.append(rel)
    manifest["updated_at"] = timestamp
    write_json(target / "manifest.json", manifest)
    preflight = _run_validator(project_root, target, scopes=("schema", "coherence", "graph", "files", "sources"), json_output=target / "reports/en_translation_preflight.json", text_output=target / "reports/en_translation_preflight.txt")
    validation = _run_validator(project_root, target, scopes=("schema", "coherence", "graph", "files", "sources", "bilingual", "workflow"), json_output=target / "reports/en_translation_validation.json", text_output=target / "reports/en_translation_validation.txt")
    return {"metadata_lock": metadata_lock, "content_lock": content_lock, "translation_lock": translation_lock, "changeset": changeset, "preflight_result": preflight.get("result"), "validator_result": validation.get("result")}


def apply_review(project_root: Path, debate_id: str, work_id: str, confirm_review_sha256: str) -> dict[str, Any]:
    workspace, meta = _load_workspace(project_root, debate_id, work_id)
    if meta.get("status") not in {"en_translation_review_finalized", "en_translation_applied"}:
        raise TranslationReviewError(f"Statut incompatible avec l’application anglaise : {meta.get('status')}")
    _assert_source_unchanged(project_root, debate_id, meta)
    source = _assert_content_copy(workspace, meta)
    review = load_json(workspace / "reviews/en/translation_review.json", "revue anglaise")
    if review.get("status") != "approved" or review.get("review_sha256") != translation_review_sha256(review):
        raise TranslationReviewError("La revue anglaise n’est pas finalisée ou son empreinte est invalide")
    if confirm_review_sha256 != review.get("review_sha256"):
        raise TranslationReviewError("L’empreinte confirmée ne correspond pas à la revue anglaise")
    if review.get("prepared_content_reviewed_copy_sha256") != full_tree_sha256(source):
        raise TranslationReviewError("content-reviewed-copy a changé depuis la finalisation anglaise")
    convergence_path = workspace / "reviews/en/semantic_convergence_review.json"
    if not convergence_path.is_file():
        raise TranslationReviewError("Deux passes sémantiques convergentes sont requises avant application")
    convergence_receipt = load_json(convergence_path, "reçu de convergence sémantique")
    verify_semantic_convergence_receipt(convergence_receipt, review)
    target = workspace / "translated-copy"
    if target.is_dir():
        if meta.get("status") != "en_translation_applied":
            raise TranslationReviewError("translated-copy existe sans état cohérent")
        expected = str((meta.get("translated_copy") or {}).get("tree_sha256") or "")
        actual = full_tree_sha256(target)
        if actual != expected: raise TranslationReviewError("Empreinte de translated-copy divergente")
        return {"status": "en_translation_applied", "debate_id": debate_id, "work_id": work_id, "review_sha256": review["review_sha256"], "translated_copy_tree_sha256": actual, "idempotent": True}
    if target.exists() or target.is_symlink():
        raise TranslationReviewError("Chemin translated-copy déjà occupé")
    temp = Path(tempfile.mkdtemp(prefix=".translated-copy.tmp-", dir=workspace))
    try:
        shutil.rmtree(temp)
        result = _build_translated_copy(project_root, source, temp, review, debate_id, work_id)
        for rel in ("imports",):
            if full_tree_sha256(temp / rel) != full_tree_sha256(source / rel):
                raise TranslationReviewError(f"La provenance {rel} a été modifiée pendant la traduction")
        for rel in ("data/fr_page_metadata_lock.json", "data/fr_content_lock.json"):
            if (temp / rel).read_bytes() != (source / rel).read_bytes():
                raise TranslationReviewError(f"Le verrou français {rel} a été modifié")
        tree_hash = full_tree_sha256(temp)
        os.replace(temp, target)
        fsync_directory(workspace)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    applied_at = result["translation_lock"]["applied_at"]
    readiness = load_json(workspace / "reviews/en/translation_readiness.json", "préparation anglaise")
    readiness["status"] = "translation_locked"
    readiness["english_translation_review_sha256"] = review["review_sha256"]
    readiness["english_translation_locked_at"] = applied_at
    for item in readiness.get("items") or []:
        if item.get("translation_status") == "reuse_existing_english_page":
            item["equivalence_review_status"] = "not_applicable_existing_page"
        else:
            item["translation_status"] = "translated_and_locked"
            item["equivalence_review_status"] = "approved"
    write_json(workspace / "reviews/en/translation_readiness.json", readiness)
    meta = copy.deepcopy(meta)
    meta["kit_version"] = KIT_VERSION
    meta["status"] = "en_translation_applied"
    meta["translated_copy"] = {"path": "translated-copy", "tree_sha256": tree_hash, "status": "bilingual_content_locked", "review_sha256": review["review_sha256"], "applied_at": applied_at}
    meta["english_translation_review"]["status"] = "applied"
    meta["english_translation_review"]["applied_at"] = applied_at
    meta["boundaries"]["english_translation_started"] = True
    meta["boundaries"]["final_pages_generated"] = False
    meta["boundaries"]["remote_access"] = False
    meta["workspace_sha256"] = None
    meta["workspace_sha256"] = workspace_receipt_hash(meta)
    write_json(workspace / "workspace.json", meta)
    return {"status": "en_translation_applied", "debate_id": debate_id, "work_id": work_id, "review_sha256": review["review_sha256"], "translated_copy": relative_to_project(target, project_root), "translated_copy_tree_sha256": tree_hash, "arguments": len(review["final_values"]["arguments"]), "sources": len(review["final_values"]["sources"]), "vocabulary_entries": len(review["final_values"]["vocabulary"]), "relations_mutated": False, "occurrences_mutated": False, "french_locks_mutated": False, "final_pages_generated": False, "remote_access": False, "validator_result": result["validator_result"]}


def reopen_review(project_root: Path, debate_id: str, work_id: str, *, reviewer: str, note: str) -> dict[str, Any]:
    workspace, meta = _load_workspace(project_root, debate_id, work_id)
    applied = meta.get("status") == "en_translation_applied"
    if meta.get("status") not in {"en_translation_review_finalized", "en_translation_applied"} or (workspace / "rendered-copy").exists():
        raise TranslationReviewError("Seule une revue finalisée avant rendu peut être rouverte")
    if applied and full_tree_sha256(workspace / "translated-copy") != (meta.get("translated_copy") or {}).get("tree_sha256"):
        raise TranslationReviewError("La copie appliquée a changé ; réouverture refusée")
    if not applied and (workspace / "translated-copy").exists():
        raise TranslationReviewError("Copie appliquée sans reçu cohérent")
    _text(reviewer, "relecteur de la réouverture", 3)
    _text(note, "motif de la réouverture", 24)
    _assert_source_unchanged(project_root, debate_id, meta)
    _assert_content_copy(workspace, meta)
    path = workspace / "reviews/en/translation_review.json"
    review = load_json(path, "revue finalisée")
    if review.get("status") != "approved" or review.get("review_sha256") != translation_review_sha256(review):
        raise TranslationReviewError("La revue à archiver n’est pas un artefact scellé valide")
    old_sha = review["review_sha256"]
    archive = workspace / "reviews/en/history" / ("translation_review." + old_sha + ".json")
    if archive.exists() and archive.read_bytes() != path.read_bytes():
        raise TranslationReviewError("Archive de revue déjà occupée par un autre contenu")
    if applied:
        previous = workspace / "reviews/en/history" / ("translated-copy." + old_sha)
        if previous.exists():
            raise TranslationReviewError("Archive de copie appliquée déjà occupée")
        previous.parent.mkdir(parents=True, exist_ok=True)
        os.replace(workspace / "translated-copy", previous)
        meta.setdefault("translation_application_history", []).append(copy.deepcopy(meta["translated_copy"]))
        meta.pop("translated_copy", None)
    archive.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, archive)
    review.update(status="draft", review_sha256=None, reopening={"previous_review_sha256": old_sha, "reviewer": reviewer, "note": note, "reopened_at": now_iso()})
    for key in ("final_values", "finalized_at", "semantic_content_sha256", "source_registry_sha256"):
        review.pop(key, None)
    write_json(path, review)
    meta["status"] = "en_translation_review_ready"
    meta["english_translation_review"] = {"status": "reopened", "previous_review_sha256": old_sha}
    meta["workspace_sha256"] = None
    meta["workspace_sha256"] = workspace_receipt_hash(meta)
    write_json(workspace / "workspace.json", meta)
    return {"status": "en_translation_review_ready", "archived_review_sha256": old_sha, "reviewer": reviewer, "note": note}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Préparer, finaliser ou appliquer la traduction anglaise contrôlée.")
    parser.add_argument("debate_id")
    parser.add_argument("--work-id", required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--freeze-imported-source", action="store_true", help="Geler les pages françaises publiées telles qu’importées, sans réécriture ni revérification documentaire revendiquée")
    action.add_argument("--reopen-review", action="store_true", help="Archiver et rouvrir une revue finalisée avant rendu, en préservant toute copie appliquée")
    action.add_argument("--finalize", action="store_true")
    action.add_argument("--apply", action="store_true")
    parser.add_argument("--overwrite-review", action="store_true")
    parser.add_argument("--confirm-review-sha256")
    parser.add_argument("--reviewer")
    parser.add_argument("--note")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--machine-readable", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = args.project_root.expanduser().resolve()
    work_id = validate_work_id(args.work_id)
    if args.apply and not args.confirm_review_sha256:
        raise TranslationReviewError("--confirm-review-sha256 est obligatoire avec --apply")
    with exclusive_lock(project_root, args.debate_id, "editorial_translation_review"):
        if args.reopen_review:
            result = reopen_review(project_root, args.debate_id, work_id, reviewer=args.reviewer or "", note=args.note or "")
        elif args.freeze_imported_source:
            from wikidebia_translation_source import freeze_imported_source
            result = freeze_imported_source(project_root, args.debate_id, work_id, reviewer=args.reviewer or "", note=args.note or "")
        elif args.prepare:
            result = prepare_review(project_root, args.debate_id, work_id, overwrite=args.overwrite_review)
        elif args.finalize:
            result = finalize_review(project_root, args.debate_id, work_id)
        else:
            result = apply_review(project_root, args.debate_id, work_id, str(args.confirm_review_sha256))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True) if args.machine_readable else json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (TranslationReviewError, EditorialReviewError, WorkspaceError, CorpusBuildError) as exc:
        print(f"WIKIDEBIA BLOQUÉ : {exc}", file=__import__("sys").stderr)
        raise SystemExit(2)
