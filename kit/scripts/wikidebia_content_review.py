#!/usr/bin/env python3
"""Prepare, finalize and apply the French content review of a workspace.

This stage starts after the graph/title checkpoint has been applied and
published. It reviews classification (rubriques and keywords), the debate
heading, Wikipedia articles, documentary buckets and source selection.  For a
corpus imported from existing wiki pages, the historical debate introduction
and argument summaries are protected by default.  The review may inspect them,
record suggestions, and — only after an explicit owner authorization recorded by
the orchestration layer — apply a scoped change during the same content-review
phase.  A historically absent summary stays absent unless its creation is
explicitly authorized. No English text is created.
"""

from __future__ import annotations

from wikidebia_citation_passages import inventory_passages

from wikidebia_release_info import KIT_VERSION

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
from collections import Counter
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
    write_json,
)
from wikidebia_editorial_workspace import (
    WorkspaceError,
    fsync_directory,
    validate_work_id,
    workspace_receipt_hash,
)
from wikidebia_editorial_review import (
    EditorialReviewError,
    _assert_source_unchanged,
    _load_workspace,
    _run_validator,
    _validate_item as _validate_metadata_item,
    _validate_corpus_rules as _validate_metadata_corpus_rules,
    _validate_vocabulary as _validate_metadata_vocabulary,
    _coverage_against_registry as _metadata_coverage_against_registry,
    review_sha256 as metadata_review_sha256,
)
from wikidebia_graph_extract import iter_templates, normalize_key

CONTENT_REVIEW_SCHEMA = "wikidebia-fr-content-review-1.0"
CONTENT_LOCK_SCHEMA = "wikidebia-fr-content-lock-1.0"
CONTENT_CHANGESET_SCHEMA = "wikidebia-fr-content-changeset-1.0"
SOURCES_WORKING_SCHEMA = "wikidebia-source-registry-working-1.0"
CLASSIFICATION_REVIEW_PATH = "reviews/fr/classification_review.json"
HISTORICAL_TEXT_POLICY = "preserve_by_default_owner_authorized_v3"
LEGACY_HISTORICAL_TEXT_POLICIES = {
    "preserve_preexisting_exact_v1",
    "preserve_by_default_owner_authorized_v2",
}
HISTORICAL_AUTHORIZATION_SCHEMA = "wikidebia-owner-historical-text-authorization-1.0"
HISTORICAL_AUTHORIZATION_PATH = "reviews/fr/historical_text_authorization.json"
HISTORICAL_CHANGE_TYPES = {
    "orthography", "grammar", "punctuation", "typography", "typo",
    "mediawiki_syntax", "corruption", "structure", "active_rule",
    "substantive_rewrite", "create_summary", "other",
}


PAGE_PARAMETER_ALIASES = {
    "débat-dédié": ("débat-dédié", "débat-détaillé"),
}

PAGE_LIFECYCLE_PARAMETERS = {
    # Ces paramètres sont des métadonnées historiques opaques : sur une page
    # préexistante, présence ET valeur sont reprises exactement. Les profils de
    # génération ne s'appliquent qu'aux pages nouvelles.
    "debate": (
        "avancement", "avertissements-titre", "avertissements-débat",
        "avertissements-bibliographie", "avertissements-sitographie",
        "avertissements-vidéographie", "débats-connexes", "interlangue",
        "date-création",
    ),
    "argument": (
        "initialisation", "nom-consacré", "nom", "titre-affiché", "avertissements-titre",
        "avertissements-argument", "avertissements-résumé",
        "avertissements-références", "avertissements-justifications",
        "avertissements-objections", "débat-dédié", "interlangue",
        "date-création",
    ),
}

# Presence of editorial top-level parameters is independent from their value.
# On a preexisting page, an imported `|parameter=` must remain distinguishable
# from a parameter that was absent altogether.  This snapshot is intentionally
# separate from lifecycle preservation because editorial values may legitimately
# change during fr_content_review while their historical presence is retained.
PAGE_EDITORIAL_PARAMETERS = {
    "debate": (
        "introduction", "articles-Wikipédia", "arguments-pour", "arguments-contre",
        "bibliographie-pour", "bibliographie-contre", "bibliographie-ni-pour-ni-contre",
        "sitographie-pour", "sitographie-contre", "sitographie-ni-pour-ni-contre",
        "vidéographie-pour", "vidéographie-contre", "vidéographie-ni-pour-ni-contre",
        "rubriques", "mots-clés",
    ),
    "argument": (
        "résumé", "citations", "références-bibliographiques",
        "références-sitographiques", "références-vidéographiques",
        "justifications", "objections", "rubriques", "mots-clés",
    ),
}


def _page_parameter_presence_snapshot(template: Any, page_type: str) -> dict[str, Any]:
    """Capture exact historical presence of editorial top-level parameters."""
    result: dict[str, Any] = {}
    for name in PAGE_EDITORIAL_PARAMETERS[page_type]:
        result[name] = {"present": name in template.params}
    return result


def _page_lifecycle_snapshot(template: Any, page_type: str) -> dict[str, Any]:
    """Capture exact presence/value of protected parameters on an imported page."""
    names = PAGE_LIFECYCLE_PARAMETERS[page_type]
    result: dict[str, Any] = {}
    for name in names:
        aliases = PAGE_PARAMETER_ALIASES.get(name, (name,))
        present_name = next((candidate for candidate in aliases if candidate in template.params), None)
        result[name] = {
            "present": present_name is not None,
            "value": template.get(*aliases) if present_name is not None else None,
        }
    return result

DEBATE_BUCKETS: dict[str, tuple[str, str]] = {
    "bibliographie-pour": ("bibliography", "pro_reference"),
    "bibliographie-contre": ("bibliography", "con_reference"),
    "bibliographie-ni-pour-ni-contre": ("bibliography", "neutral_reference"),
    "sitographie-pour": ("webliography", "pro_reference"),
    "sitographie-contre": ("webliography", "con_reference"),
    "sitographie-ni-pour-ni-contre": ("webliography", "neutral_reference"),
    "vidéographie-pour": ("videography", "pro_reference"),
    "vidéographie-contre": ("videography", "con_reference"),
    "vidéographie-ni-pour-ni-contre": ("videography", "neutral_reference"),
}
ARGUMENT_BUCKETS = {
    "bibliography": "bibliography",
    "webliography": "webliography",
    "videography": "videography",
}
SOURCE_METADATA_FIELDS = (
    "authors", "article", "work", "volume", "issue", "location", "publisher",
    "place", "date", "link", "page", "site", "title",
)
SUMMARY_TRUE_FIELDS = (
    "summary_preserves_node_identity",
    "thesis_first",
    "general_public_style",
    "sentence_rhythm_reviewed",
    "technical_terms_reviewed",
    "opening_develops_title",
    "example_or_data_reviewed",
    "assertive_tone_reviewed",
    "no_artificial_example_or_number",
    "no_polemical_overstatement",
    "no_self_objection",
    "conviction_visible",
    "wikipedia_hover_links_reviewed",
    "specialized_terms_linked_or_explained",
    "factual_claims_documented",
)
INTRO_TRUE_FIELDS = (
    "subject_and_scope_defined",
    "stakes_explained",
    "dedicated_stakes_subsection_present",
    "stakes_consequences_concrete",
    "stakes_not_argument_catalogue",
    "debate_question_explained",
    "history_and_evolution_addressed",
    "current_state_addressed_or_not_applicable",
    "factual_claims_referenced",
    "progression_coherent",
    "no_argument_tree_mirroring",
    "no_topic_specific_checklist",
    "complete_topic_fits_heading",
    "debate_sections_precise",
    "documentation_proportionate_to_literature",
    "wikipedia_hover_links_reviewed",
    "specialized_terms_linked_or_explained",
    "common_acronym_used_or_not_applicable",
    "topic_is_nominal_label",
    "conventional_topic_label_used_or_not_applicable",
    "complete_topic_lowercase_initial_or_justified",
    "information_density_reviewed",
    "subsections_non_redundant",
    "no_generic_stakes_filler",
    "documentation_orientation_reviewed",
    "youtube_authorship_reviewed",
    "reference_note_punctuation_reviewed",
    "specialized_term_inventory_reviewed",
)
NUMBER = re.compile(r"(?<![\wÀ-ÿ])\d+(?:[.,]\d+)?(?:\s*%)?(?![\wÀ-ÿ])")
META_DISCOURSE_FR = re.compile(r"\b(?:cet argument|l['’]argument|la page|le raisonnement présenté|ce raisonnement)\b", re.I)
META_DISCOURSE_EN = re.compile(r"\b(?:this argument|the argument|this page|the page|this reasoning|the reasoning presented|the reasoning)\b", re.I)
# Backward-compatible alias used by the French content review.
META_DISCOURSE = META_DISCOURSE_FR
QUESTION_TOPIC = re.compile(r"^(?:si\b|faut[- ]il\b|doit[- ]on\b|whether\b|should\b)", re.I)
HTTP_URL = re.compile(r"^https?://", re.I)
SOURCE_ID = re.compile(r"^S[0-9]{5,}$")

CITATION_TEXT_KEYS = {"citation"}
CITATION_DATE_KEYS = {"date"}
CITATION_WARNING_KEYS = {"avertissements citation", "avertissements"}


def _citation_records(value: str, node_id: str) -> list[dict[str, Any]]:
    """Inventory imported Citation models without altering documentary fields.

    The exact parameter names, order and values are retained.  Only ``citation``,
    ``date`` and the citation warning field are later allowed to differ in the
    English translation lock.
    """
    records: list[dict[str, Any]] = []
    for call in iter_templates(value or ""):
        if normalize_key(call.name) != "citation":
            continue
        parameters = [{"name": name, "value": val} for name, val in call.params.items()]
        text_values = [val for name, val in call.params.items() if normalize_key(name) in CITATION_TEXT_KEYS]
        date_values = [val for name, val in call.params.items() if normalize_key(name) in CITATION_DATE_KEYS]
        warning_values = [val for name, val in call.params.items() if normalize_key(name) in CITATION_WARNING_KEYS and str(val).strip()]
        if len(text_values) != 1 or not str(text_values[0]).strip():
            raise ContentReviewError(f"Citation importée sans paramètre citation unique dans {node_id}")
        if len(date_values) > 1:
            raise ContentReviewError(f"Citation importée avec plusieurs paramètres date dans {node_id}")
        if len(set(str(v).strip() for v in warning_values)) > 1:
            raise ContentReviewError(f"Citation importée avec plusieurs avertissements divergents dans {node_id}")
        controlled = CITATION_TEXT_KEYS | CITATION_DATE_KEYS | CITATION_WARNING_KEYS
        preserved = [copy.deepcopy(row) for row in parameters if normalize_key(row["name"]) not in controlled]
        records.append({
            "id": f"{node_id}-C{len(records)+1:03d}",
            "source_template": call.name.strip(),
            "source_parameters": parameters,
            "citation": str(text_values[0]).strip(),
            "date": str(date_values[0]).strip() if date_values else "",
            "avertissements-citation": str(warning_values[0]).strip() if warning_values else "",
            "preserved_parameters": preserved,
        })
    return records


class ContentReviewError(EditorialReviewError):
    pass


def content_review_sha256(review: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(review))
    body.pop("review_sha256", None)
    return sha256_bytes(canonical_json(body))


def _text(value: Any, label: str, minimum: int = 1) -> str:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        raise ContentReviewError(f"{label} est absent ou trop court")
    return value.strip()


def _list_strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ContentReviewError(f"{label} doit être une liste")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ContentReviewError(f"{label} contient une valeur vide")
        clean = item.strip()
        if clean in result:
            raise ContentReviewError(f"{label} contient un doublon : {clean}")
        result.append(clean)
    return result


def _outer_template(path: Path, names: set[str]):
    text = path.read_text(encoding="utf-8")
    matches = [call for call in iter_templates(text) if normalize_key(call.name) in names]
    if not matches:
        raise ContentReviewError(f"Modèle principal introuvable dans {path.name}")
    return max(matches, key=lambda call: len(call.raw))


def _subsections(value: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for call in iter_templates(value or ""):
        if normalize_key(call.name) != "sous partie":
            continue
        result.append({
            "title": call.get("titre").strip(),
            "content": call.get("contenu").strip(),
        })
    return result


def _historical_policy_supported(value: Any) -> bool:
    return value == HISTORICAL_TEXT_POLICY or value in LEGACY_HISTORICAL_TEXT_POLICIES


def _subsection_change_scope(historical: str, final: str) -> dict[str, Any]:
    """Describe the editorial delta between historical and selected introductions.

    The scope is deliberately structural and deterministic.  Unchanged
    historical subsections remain historical even when another subsection is
    added or rewritten.  Duplicate subsection titles are handled by occurrence
    number so historical corpora are not rejected merely because their titles
    are imperfect.
    """
    before = _subsections(historical)
    after = _subsections(final)

    def keyed(rows: list[dict[str, Any]]) -> list[tuple[tuple[str, int], dict[str, Any]]]:
        counts: dict[str, int] = {}
        result: list[tuple[tuple[str, int], dict[str, Any]]] = []
        for row in rows:
            title = str(row.get("title") or "")
            counts[title] = counts.get(title, 0) + 1
            result.append(((title, counts[title]), row))
        return result

    b = keyed(before); a = keyed(after)
    bmap = {key: row for key, row in b}; amap = {key: row for key, row in a}
    bkeys = [key for key, _ in b]; akeys = [key for key, _ in a]
    added = [key for key in akeys if key not in bmap]
    removed = [key for key in bkeys if key not in amap]
    modified = [key for key in akeys if key in bmap and str(amap[key].get("content") or "") != str(bmap[key].get("content") or "")]
    common_before = [key for key in bkeys if key in amap]
    common_after = [key for key in akeys if key in bmap]
    reordered = common_before != common_after

    def rows(keys: list[tuple[str, int]]) -> list[dict[str, Any]]:
        return [{"title": title, "occurrence": occurrence} for title, occurrence in keys]

    return {
        "mode": "subsections",
        "historical_titles": [row.get("title") for row in before],
        "final_titles": [row.get("title") for row in after],
        "added": rows(added),
        "modified": rows(modified),
        "removed": rows(removed),
        "reordered": reordered,
    }


def _canonical_scope(value: Any) -> dict[str, Any] | None:
    if value in (None, {}):
        return None
    if not isinstance(value, Mapping):
        raise ContentReviewError("Portée structurée de modification historique invalide")
    mode = str(value.get("mode") or "")
    if mode == "whole_field":
        return {"mode": "whole_field"}
    if mode != "subsections":
        raise ContentReviewError(f"Mode de portée historique inconnu : {mode!r}")
    result = {"mode": "subsections"}
    for key in ("historical_titles", "final_titles"):
        raw = value.get(key)
        if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
            raise ContentReviewError(f"Portée historique invalide : {key}")
        result[key] = list(raw)
    for key in ("added", "modified", "removed"):
        raw = value.get(key)
        if not isinstance(raw, list):
            raise ContentReviewError(f"Portée historique invalide : {key}")
        clean=[]
        for item in raw:
            if not isinstance(item, Mapping) or not isinstance(item.get("title"), str) or not isinstance(item.get("occurrence"), int) or int(item.get("occurrence")) < 1:
                raise ContentReviewError(f"Portée historique invalide dans {key}")
            clean.append({"title": str(item["title"]), "occurrence": int(item["occurrence"])})
        result[key]=clean
    if not isinstance(value.get("reordered"), bool):
        raise ContentReviewError("Portée historique invalide : reordered")
    result["reordered"] = bool(value["reordered"])
    return result


def _changed_final_subsection_keys(scope: Mapping[str, Any]) -> set[tuple[str, int]]:
    if scope.get("mode") != "subsections":
        return set()
    result=set()
    for key in ("added", "modified"):
        for row in scope.get(key) or []:
            if isinstance(row, Mapping):
                result.add((str(row.get("title") or ""), int(row.get("occurrence") or 0)))
    return result


def _keyed_subsections(value: str) -> list[tuple[tuple[str, int], dict[str, Any]]]:
    counts: dict[str, int] = {}
    result=[]
    for row in _subsections(value):
        title=str(row.get("title") or "")
        counts[title]=counts.get(title,0)+1
        result.append(((title, counts[title]), row))
    return result


def _wikipedia_articles(value: str) -> list[str]:
    result: list[str] = []
    for call in iter_templates(value or ""):
        if normalize_key(call.name) != "article wikipedia":
            continue
        page = call.get("page").strip()
        if page and page not in result:
            result.append(page)
    return result


def _assert_reviewed_copy(workspace: Path, meta: Mapping[str, Any]) -> Path:
    reviewed = workspace / "reviewed-copy"
    if not reviewed.is_dir() or reviewed.is_symlink():
        raise ContentReviewError("reviewed-copy absent ou non sûr")
    expected = str((meta.get("reviewed_copy") or {}).get("tree_sha256") or "")
    actual = full_tree_sha256(reviewed)
    if not expected or actual != expected:
        raise ContentReviewError("reviewed-copy a changé depuis l’application des métadonnées")
    if (reviewed / "output").exists():
        raise ContentReviewError("Des pages finales existent déjà dans reviewed-copy")
    return reviewed


def _source_imports(reviewed: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    registry = load_json(reviewed / "data/registre_debat.json", "registre du débat")
    provenance = load_json(reviewed / "data/import_provenance.json", "provenance d’import")
    debate_row = next((row for row in provenance.get("pages") or [] if row.get("kind") == "debate"), None)
    if not debate_row:
        raise ContentReviewError("Page Débat absente de la provenance")
    debate_path = reviewed / str(debate_row.get("import_path"))
    debate = _outer_template(debate_path, {"debat"})
    debate_source = {
        "import_path": str(debate_row.get("import_path")),
        "import_sha256": debate_row.get("sha256"),
        "subject": debate.get("sujet").strip(),
        "complete_topic": debate.get("sujet-développé", "sujet-complet").strip(),
        "introduction": debate.get("introduction").strip(),
        "subsections": _subsections(debate.get("introduction")),
        "wikipedia_articles": _wikipedia_articles(debate.get("articles-Wikipédia")),
        "documentation_raw": {bucket: debate.get(bucket).strip() for bucket in DEBATE_BUCKETS},
        "page_origin": "preexisting",
        "preserved_parameters": _page_lifecycle_snapshot(debate, "debate"),
        "source_parameter_presence": _page_parameter_presence_snapshot(debate, "debate"),
    }
    nodes = {
        str(node.get("id")): node
        for node in ((registry.get("graph") or {}).get("nodes") or [])
        if node.get("status") == "active"
    }
    arguments: list[dict[str, Any]] = []
    argument_rows = [
        row for row in provenance.get("pages") or []
        if isinstance(row, dict) and row.get("kind") == "argument" and row.get("page_id")
    ]
    row_ids = [str(row.get("page_id")) for row in argument_rows]
    if len(row_ids) != len(set(row_ids)):
        raise ContentReviewError("La provenance contient plusieurs lignes pour un même argument")
    rows = {str(row.get("page_id")): row for row in argument_rows}
    missing = set(nodes) - set(rows)
    if missing:
        raise ContentReviewError(
            "La provenance ne couvre pas tous les arguments actifs : " + ", ".join(sorted(missing))
        )
    extras = set(rows) - set(nodes)
    invalid_extras = sorted(
        node_id for node_id in extras
        if str(rows[node_id].get("status") or "") not in {"retired_redirect", "retired_deleted", "pending_redirect", "pending_delete"}
    )
    if invalid_extras:
        raise ContentReviewError(
            "La provenance contient des arguments non actifs qui ne sont pas explicitement retirés : "
            + ", ".join(invalid_extras)
        )
    # Retired provenance rows are intentionally retained for auditability after
    # graph-owner actions.  They are not source pages for the active content
    # review, whose coverage is defined by the active registry nodes only.
    for node_id in sorted(nodes):
        row = rows[node_id]
        path = reviewed / str(row.get("import_path"))
        tmpl = _outer_template(path, {"argument"})
        arguments.append({
            "id": node_id,
            "canonical_title": ((nodes[node_id].get("fr") or {}).get("canonical_title")),
            "displayed_title": ((nodes[node_id].get("fr") or {}).get("displayed_title")),
            "import_path": str(row.get("import_path")),
            "import_sha256": row.get("sha256"),
            "summary": tmpl.get("résumé").strip(),
            "citations": _citation_records(tmpl.get("citations"), node_id),
            "citation_passages": inventory_passages(tmpl.get("citations"), node_id),
            "documentation_raw": {
                "bibliography": tmpl.get("références-bibliographiques").strip(),
                "webliography": tmpl.get("références-sitographiques").strip(),
                "videography": tmpl.get("références-vidéographiques").strip(),
            },
            "page_origin": "preexisting",
            "preserved_parameters": _page_lifecycle_snapshot(tmpl, "argument"),
            "source_parameter_presence": _page_parameter_presence_snapshot(tmpl, "argument"),
        })
    return registry, debate_source, arguments


def _blank_intro_review(source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": "pending",
        "subject_decision": "pending",
        "proposed_subject": source.get("subject"),
        "complete_topic_decision": "pending",
        "proposed_complete_topic": source.get("complete_topic"),
        "topic_label_rationale": "",
        "common_acronym": None,
        "complete_topic_initial_capital_justification": None,
        # Historical text is preserved by default.  Reviewers may record a
        # suggestion without applying it.  A changed proposed value is accepted
        # only when an owner authorization receipt generated locally by the
        # orchestration layer covers this exact field and before/after hash.
        "historical_text_policy": HISTORICAL_TEXT_POLICY,
        "historical_text_status": "preserved",
        "suggested_change": None,
        "historical_change_request": None,
        "introduction_decision": "keep",
        "proposed_introduction": source.get("introduction"),
        "introduction_rationale": "Introduction historique préservée par défaut ; une suggestion peut être enregistrée sans être appliquée, et toute modification exige un consentement propriétaire explicite et traçable.",
        "subsections": [
            {
                "title": row.get("title"),
                "purpose": "",
                "necessary_for_understanding": False,
                "technical_or_specialized": False,
                "relevance_to_debate_explained": False,
                "stakes_section": False,
                "concrete_stakes": [],
            }
            for row in source.get("subsections") or []
        ],
        "wikipedia_articles_decision": "pending",
        "proposed_wikipedia_articles": list(source.get("wikipedia_articles") or []),
        "wikipedia_articles_verified": False,
        "documentation_decisions": {bucket: "pending" for bucket in DEBATE_BUCKETS},
        "proposed_documentation": {bucket: [] for bucket in DEBATE_BUCKETS},
        "documentation_rationales": {bucket: "" for bucket in DEBATE_BUCKETS},
        "documentation_family_notes": {"bibliography": "", "webliography": "", "videography": ""},
        **{field: False for field in INTRO_TRUE_FIELDS},
        "terminal_period_sentence_exceptions": [],
        "specialized_term_inventory": [],
        "reviewer": "",
        "reviewed_at": None,
        "note": "",
    }


def _blank_summary_review(source: Mapping[str, Any]) -> dict[str, Any]:
    historical_summary = str(source.get("summary") or "")
    return {
        "status": "pending",
        "historical_text_policy": HISTORICAL_TEXT_POLICY,
        "historical_text_status": "preserved",
        "suggested_change": None,
        "historical_change_request": None,
        "historical_summary_present": bool(historical_summary.strip()),
        "historical_summary_sha256": hashlib.sha256(historical_summary.encode("utf-8")).hexdigest(),
        "summary_decision": "keep",
        "proposed_summary": source.get("summary"),
        "summary_rationale": "Résumé historique préservé par défaut ; son absence historique reste une absence sauf création explicitement autorisée pour ce champ.",
        "documentation_decisions": {bucket: "pending" for bucket in ARGUMENT_BUCKETS},
        "proposed_sources": {bucket: [] for bucket in ARGUMENT_BUCKETS},
        "documentation_rationale": "",
        **{field: False for field in SUMMARY_TRUE_FIELDS},
        "forceful_expression": "",
        "quantitative_claims_verified": False,
        "quantitative_claims_note": "",
        "reviewer": "",
        "reviewed_at": None,
        "note": "",
    }



def _historical_text_sha256(value: Any) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _historical_change_request(
    review: Mapping[str, Any], *, field_key: str, historical_value: Any, final_value: Any,
) -> dict[str, Any] | None:
    request = review.get("historical_change_request")
    if request in (None, {}):
        return None
    if not isinstance(request, dict):
        raise ContentReviewError(f"Demande de modification historique invalide pour {field_key}")
    if str(request.get("field_key") or "") != field_key:
        raise ContentReviewError(f"Portée de la demande historique invalide pour {field_key}")
    change_type = str(request.get("change_type") or "")
    if change_type not in HISTORICAL_CHANGE_TYPES:
        raise ContentReviewError(f"Type de modification historique invalide pour {field_key} : {change_type!r}")
    rationale = str(request.get("rationale") or "").strip()
    owner_ref = str(request.get("owner_instruction_reference") or "").strip()
    if len(rationale) < 12 or len(owner_ref) < 3:
        raise ContentReviewError(f"Justification ou référence à la décision propriétaire absente pour {field_key}")
    requested_final = request.get("final_value")
    if str(requested_final or "") != str(final_value or ""):
        raise ContentReviewError(f"La valeur finale demandée ne correspond pas à la proposition pour {field_key}")
    historical_sha = _historical_text_sha256(historical_value)
    final_sha = _historical_text_sha256(final_value)
    if request.get("historical_sha256") not in (None, historical_sha):
        raise ContentReviewError(f"Empreinte historique déclarée incohérente pour {field_key}")
    if request.get("final_sha256") not in (None, final_sha):
        raise ContentReviewError(f"Empreinte finale déclarée incohérente pour {field_key}")

    actual_scope: dict[str, Any]
    if field_key.endswith(":introduction"):
        actual_scope = _subsection_change_scope(str(historical_value or ""), str(final_value or ""))
        declared_scope = _canonical_scope(request.get("change_scope"))
        if declared_scope is not None:
            if declared_scope.get("mode") == "subsections" and declared_scope != actual_scope:
                raise ContentReviewError(
                    f"Le delta réel de l’introduction dépasse la portée structurée déclarée pour {field_key}"
                )
            if declared_scope.get("mode") == "whole_field":
                actual_scope = {"mode": "whole_field", "observed_subsection_delta": actual_scope}
        else:
            # Compatibility with 2.16.17: the exact final-value hash remains a
            # valid broad field authorization when no narrower scope was declared.
            actual_scope = {"mode": "whole_field", "observed_subsection_delta": actual_scope}
    else:
        declared_scope = _canonical_scope(request.get("change_scope"))
        if declared_scope not in (None, {"mode": "whole_field"}):
            raise ContentReviewError(f"Une portée de sous-parties ne peut pas viser {field_key}")
        actual_scope = {"mode": "whole_field"}

    return {
        "field_key": field_key,
        "change_type": change_type,
        "rationale": rationale,
        "owner_instruction_reference": owner_ref,
        "historical_sha256": historical_sha,
        "final_sha256": final_sha,
        "historical_present": bool(str(historical_value or "").strip()),
        "final_present": bool(str(final_value or "").strip()),
        "change_scope": actual_scope,
    }


def normalize_historical_review_document(review_doc: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Normalize old content-review payloads without discarding editorial work.

    A review prepared before the consent-aware format may contain proposed
    introduction/summary deltas created by the old workflow.  Such deltas are
    retained as ``suggested_change`` but are reset to ``keep`` unless the
    returned payload contains a new explicit ``historical_change_request``.
    New-format payloads are never silently normalized: arbitrary historical
    deltas remain visible and will be rejected if not covered by a request and
    a locally generated owner authorization.
    """
    doc = copy.deepcopy(dict(review_doc))
    migration = {
        "legacy_format_detected": False,
        "suggestions_recovered": 0,
        "requests_preserved": 0,
        "fields_normalized": 0,
    }

    def normalize_one(
        holder: dict[str, Any], source: Mapping[str, Any], *, decision_key: str,
        proposed_key: str, historical_key: str, field_key: str,
        present_key: str | None = None, hash_key: str | None = None,
    ) -> None:
        if str(source.get("page_origin") or "preexisting") != "preexisting":
            return
        historical = source.get(historical_key)
        historical_text = str(historical or "")
        legacy = not isinstance(holder.get("historical_text_status"), str)
        if legacy:
            migration["legacy_format_detected"] = True
        holder["historical_text_policy"] = HISTORICAL_TEXT_POLICY
        holder.setdefault("historical_text_status", "preserved")
        holder.setdefault("suggested_change", None)
        holder.setdefault("historical_change_request", None)
        if present_key:
            holder[present_key] = bool(historical_text.strip())
        if hash_key:
            holder[hash_key] = _historical_text_sha256(historical_text)

        proposed = holder.get(proposed_key)
        decision = str(holder.get(decision_key) or "")
        delta = decision == "change" and str(proposed or "") != historical_text
        request = holder.get("historical_change_request")
        if legacy and delta and not isinstance(request, dict):
            # Preserve the old proposal as a suggestion rather than silently
            # applying a rewrite that predates the consent-aware contract.
            holder["suggested_change"] = {
                "value": proposed,
                "change_type": "other",
                "rationale": str(holder.get("summary_rationale") or holder.get("introduction_rationale") or "Proposition héritée d’une revue préparée avant le contrat de consentement explicite.").strip(),
                "migrated_from_legacy_review": True,
            }
            holder[decision_key] = "keep"
            holder[proposed_key] = historical
            holder["historical_text_status"] = "preserved"
            migration["suggestions_recovered"] += 1
            migration["fields_normalized"] += 1
        elif legacy and not delta:
            # An old keep/pending decision is normalized to the safe default.
            holder[decision_key] = "keep"
            holder[proposed_key] = historical
            holder["historical_text_status"] = "preserved"
            migration["fields_normalized"] += 1
        elif isinstance(request, dict):
            migration["requests_preserved"] += 1

    debate = doc.get("debate")
    if isinstance(debate, dict) and isinstance(debate.get("source"), dict) and isinstance(debate.get("review"), dict):
        normalize_one(
            debate["review"], debate["source"], decision_key="introduction_decision",
            proposed_key="proposed_introduction", historical_key="introduction",
            field_key=f"debate:{doc.get('debate_id')}:introduction",
        )
    arguments = doc.get("arguments")
    if isinstance(arguments, list):
        for item in arguments:
            if not isinstance(item, dict) or not isinstance(item.get("source"), dict) or not isinstance(item.get("review"), dict):
                continue
            node_id = str(item.get("id") or item["source"].get("id") or "")
            normalize_one(
                item["review"], item["source"], decision_key="summary_decision",
                proposed_key="proposed_summary", historical_key="summary",
                field_key=f"argument:{node_id}:summary",
                present_key="historical_summary_present", hash_key="historical_summary_sha256",
            )
    return doc, migration


def collect_historical_change_requests(review_doc: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return exact historical deltas requested by the editable review payload."""
    changes: list[dict[str, Any]] = []
    debate = review_doc.get("debate") or {}
    if isinstance(debate, dict):
        source = debate.get("source") or {}
        rev = debate.get("review") or {}
        if isinstance(source, dict) and isinstance(rev, dict) and str(source.get("page_origin") or "preexisting") == "preexisting":
            historical = source.get("introduction")
            final = rev.get("proposed_introduction") if rev.get("introduction_decision") == "change" else historical
            if str(final or "") != str(historical or ""):
                field_key = f"debate:{review_doc.get('debate_id')}:introduction"
                request = _historical_change_request(rev, field_key=field_key, historical_value=historical, final_value=final)
                if request is None:
                    raise ContentReviewError(f"Modification de l’introduction historique non couverte par une demande d’autorisation : {field_key}")
                changes.append(request)
    arguments = review_doc.get("arguments") or []
    if isinstance(arguments, list):
        for item in arguments:
            if not isinstance(item, dict):
                continue
            source = item.get("source") or {}
            rev = item.get("review") or {}
            if not isinstance(source, dict) or not isinstance(rev, dict) or str(source.get("page_origin") or "preexisting") != "preexisting":
                continue
            node_id = str(item.get("id") or source.get("id") or "")
            historical = source.get("summary")
            final = rev.get("proposed_summary") if rev.get("summary_decision") == "change" else historical
            if str(final or "") != str(historical or ""):
                field_key = f"argument:{node_id}:summary"
                request = _historical_change_request(rev, field_key=field_key, historical_value=historical, final_value=final)
                if request is None:
                    raise ContentReviewError(f"Modification du résumé historique non couverte par une demande d’autorisation : {field_key}")
                changes.append(request)
    return changes


def _authorization_hash(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("authorization_sha256", None)
    return sha256_bytes(canonical_json(body))


def _load_historical_authorization(workspace: Path, review: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    path = workspace / HISTORICAL_AUTHORIZATION_PATH
    requested = collect_historical_change_requests(review)
    if not requested:
        return {}
    if not path.is_file():
        raise ContentReviewError(
            "Une ou plusieurs modifications de texte historique ont été demandées sans autorisation propriétaire locale ; "
            "réimportez le même paquet avec --authorize-historical-changes après accord explicite du propriétaire"
        )
    auth = load_json(path, "autorisation propriétaire des textes historiques")
    if auth.get("schema") != HISTORICAL_AUTHORIZATION_SCHEMA or auth.get("debate_id") != review.get("debate_id") or auth.get("work_id") != review.get("work_id"):
        raise ContentReviewError("Autorisation propriétaire de texte historique invalide")
    if auth.get("authorization_sha256") != _authorization_hash(auth):
        raise ContentReviewError("Empreinte de l’autorisation propriétaire invalide")
    if auth.get("review_payload_sha256") != content_review_sha256(review):
        raise ContentReviewError("L’autorisation propriétaire ne correspond plus au contenu exact de la revue")
    auth_rows = auth.get("changes")
    if not isinstance(auth_rows, list):
        raise ContentReviewError("Portée de l’autorisation propriétaire absente")
    by_key = {str(row.get("field_key")): row for row in auth_rows if isinstance(row, dict)}
    if set(by_key) != {row["field_key"] for row in requested}:
        raise ContentReviewError("La portée autorisée ne correspond pas exactement aux changements historiques demandés")
    for req in requested:
        row = by_key[req["field_key"]]
        for key in ("historical_sha256", "final_sha256", "change_type", "change_scope"):
            if row.get(key) != req.get(key):
                raise ContentReviewError(f"Autorisation propriétaire divergente pour {req['field_key']} ({key})")
    return by_key


def _classification_review_template(reviewed: Path, debate_id: str, work_id: str) -> dict[str, Any]:
    lock = load_json(reviewed / "data/fr_page_metadata_lock.json", "verrou français des titres")
    rows = [copy.deepcopy(lock.get("debate") or {})] + [copy.deepcopy(row) for row in (lock.get("arguments") or [])]
    items: list[dict[str, Any]] = []
    for row in rows:
        entity_type = str(row.get("entity_type") or "")
        entity_id = str(row.get("entity_id") or "")
        if entity_type not in {"debate", "argument"} or not entity_id:
            raise ContentReviewError("Le verrou de titres ne couvre pas correctement les pages françaises")
        source = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "page_origin": row.get("page_origin") or "preexisting",
            "canonical_title": row.get("canonical_title"),
            "displayed_title": row.get("displayed_title"),
            "rubriques": copy.deepcopy(row.get("rubriques") or []),
            "keywords": copy.deepcopy(row.get("keywords") or []),
        }
        attest = row.get("attestations") or {}
        review = {
            "status": "pending",
            "canonical_title_decision": "not_applicable" if entity_type == "debate" else "keep",
            "proposed_canonical_title": None,
            "canonical_title_rationale": "Titre canonique déjà validé et verrouillé lors du checkpoint graphe et titres.",
            "displayed_title_decision": "not_applicable" if entity_type == "debate" else "keep",
            "proposed_displayed_title": None,
            "displayed_title_rationale": "Titre affiché déjà validé et verrouillé lors du checkpoint graphe et titres.",
            "rubriques_decision": "pending",
            "proposed_rubriques": [],
            "rubriques_rationales": {},
            "keywords_decision": "pending",
            "proposed_keywords": [],
            "keywords_rationales": {},
            "keywords_ordered_by_relevance": False,
            "keyword_order_rationale": "",
            "canonical_referents_explicit": True if entity_type == "argument" else None,
            "displayed_title_complete_proposition": attest.get("displayed_title_complete_proposition") if entity_type == "argument" else None,
            "displayed_title_argument_intelligible": True if entity_type == "argument" else None,
            "displayed_title_concision_reviewed": True if entity_type == "argument" else None,
            "displayed_title_semantically_equivalent": True if entity_type == "argument" else None,
            "displayed_title_improves_readability_when_distinct": attest.get("displayed_title_improves_readability_when_distinct") if entity_type == "argument" else None,
            "displayed_title_identity_justification": str((row.get("rationales") or {}).get("displayed_title_identity") or ""),
            "fourth_rubrique_exception_rationale": "",
            "preexisting_rubrique_change_rationale": "",
            "preexisting_keyword_corrections": {},
            "removed_preexisting_keywords": {},
            "reviewer": "",
            "reviewed_at": None,
            "notes": "",
        }
        # Historical displayed titles do not need the creation-only proposition attestation.
        if source["page_origin"] == "new" and entity_type == "argument" and review["displayed_title_complete_proposition"] is not True:
            review["displayed_title_complete_proposition"] = True
        items.append({"entity_type": entity_type, "entity_id": entity_id, "source": source, "review": review})
    return {
        "schema": "wikidebia-fr-page-metadata-review-1.1",
        "schema_version": "1.1",
        "normative_revision": NORM_VERSION,
        "kit_version": KIT_VERSION,
        "debate_id": debate_id,
        "work_id": work_id,
        "review_scope": "classification_and_content",
        "status": "draft",
        "prepared_at": now_iso(),
        "prepared_reviewed_copy_sha256": full_tree_sha256(reviewed),
        "items": items,
        "review_sha256": None,
    }

def prepare_review(project_root: Path, debate_id: str, work_id: str, *, overwrite: bool = False) -> dict[str, Any]:
    workspace, meta = _load_workspace(project_root, debate_id, work_id)
    if meta.get("status") not in {"fr_titles_applied", "fr_metadata_applied", "fr_content_review_ready"}:
        raise ContentReviewError(f"Statut incompatible avec la préparation du contenu : {meta.get('status')}")
    legacy_classification_locked = meta.get("status") == "fr_metadata_applied"
    _assert_source_unchanged(project_root, debate_id, meta)
    reviewed = _assert_reviewed_copy(workspace, meta)
    review_path = workspace / "reviews/fr/content_review.json"
    sources_path = workspace / "data/sources_working.json"
    classification_path = workspace / CLASSIFICATION_REVIEW_PATH
    vocabulary_path = workspace / "data/keyword_vocabulary_working.json"
    if review_path.exists() and not overwrite:
        existing = load_json(review_path, "revue de contenu")
        return {
            "status": "fr_content_review_ready",
            "debate_id": debate_id,
            "work_id": work_id,
            "review_path": relative_to_project(review_path, project_root),
            "arguments": len(existing.get("arguments") or []),
            "idempotent": True,
        }
    if overwrite and (workspace / "content-reviewed-copy").exists():
        raise ContentReviewError("Impossible de régénérer une revue déjà appliquée")
    registry, debate_source, arguments = _source_imports(reviewed)
    now = now_iso()
    review = {
        "schema": CONTENT_REVIEW_SCHEMA,
        "schema_version": "1.1",
        "normative_revision": NORM_VERSION,
        "kit_version": KIT_VERSION,
        "debate_id": debate_id,
        "work_id": work_id,
        "status": "draft",
        "prepared_at": now,
        "prepared_reviewed_copy_sha256": full_tree_sha256(reviewed),
        "debate": {"source": debate_source, "review": _blank_intro_review(debate_source)},
        "arguments": [
            {"id": row["id"], "source": row, "review": _blank_summary_review(row)}
            for row in arguments
        ],
        "global_review": {
            "reviewer": "",
            "reviewed_at": None,
            "all_french_content_reviewed": False,
            "all_selected_sources_verified": False,
            "no_final_pages_generated": True,
            "english_translation_not_started": True,
            "blocking_issues": [],
            "note": "",
        },
        "review_sha256": None,
    }
    write_json(review_path, review)
    current_sources = load_json(reviewed / "data/sources.json", "registre documentaire")
    working_sources = {
        "schema": SOURCES_WORKING_SCHEMA,
        "source_registry_version": current_sources.get("source_registry_version", "1.0"),
        "debate_id": debate_id,
        "work_id": work_id,
        "status": "draft",
        "prepared_at": now,
        "sources": copy.deepcopy(current_sources.get("sources") or []),
    }
    write_json(sources_path, working_sources)
    if not classification_path.is_file() or overwrite:
        classification_doc = _classification_review_template(reviewed, debate_id, work_id)
        if legacy_classification_locked:
            lock = load_json(reviewed / "data/fr_page_metadata_lock.json", "verrou français des métadonnées")
            final_values = [copy.deepcopy(lock.get("debate") or {})] + [copy.deepcopy(row) for row in (lock.get("arguments") or [])]
            vocabulary_doc = load_json(reviewed / "data/keyword_vocabulary.json", "vocabulaire français")
            classification_doc.update({
                "status": "approved", "finalized_at": now,
                "summary": {"pages": len(final_values), "arguments": max(0, len(final_values)-1), "legacy_metadata_lock_reused": True},
                "final_values": final_values, "finalized_vocabulary": copy.deepcopy(vocabulary_doc.get("entries") or []),
                "review_sha256": None,
            })
            classification_doc["review_sha256"] = metadata_review_sha256(classification_doc)
        write_json(classification_path, classification_doc)
    if not vocabulary_path.is_file():
        raise ContentReviewError("data/keyword_vocabulary_working.json absent du workspace")
    audit = {
        "schema": "wikidebia-fr-content-inventory-1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "generated_at": now,
        "debate": {
            "subject_present": bool(debate_source["subject"]),
            "complete_topic_present": bool(debate_source["complete_topic"]),
            "introduction_present": bool(debate_source["introduction"]),
            "subsections": len(debate_source["subsections"]),
            "wikipedia_articles": len(debate_source["wikipedia_articles"]),
            "documentary_buckets_nonempty": sum(bool(v) for v in debate_source["documentation_raw"].values()),
            "historical_introduction_preserved_by_default": True,
            "historical_introduction_sha256": hashlib.sha256(str(debate_source["introduction"] or "").encode("utf-8")).hexdigest(),
        },
        "arguments": {
            "count": len(arguments),
            "summaries_missing": sum(not bool(row["summary"]) for row in arguments),
            "summaries_under_80_chars": sum(len(row["summary"]) < 80 for row in arguments),
            "arguments_with_any_documentation": sum(any(row["documentation_raw"].values()) for row in arguments),
            "citations": sum(len(row.get("citations") or []) for row in arguments),
            "arguments_with_citations": sum(bool(row.get("citations")) for row in arguments),
            "historical_summaries_preserved_by_default": len(arguments),
        },
        "boundaries": {
            "automatic_rewriting": False,
            "historical_introduction_rewriting": False,
            "historical_summary_rewriting": False,
            "historical_absent_summary_generation": False,
            "final_pages_generated": False,
            "english_translation_started": False,
        },
    }
    write_json(workspace / "audits/fr_content_inventory.json", audit)
    markdown = [
        "# Inventaire du contenu français", "",
        f"- Débat : `{debate_id}`", f"- Arguments : {len(arguments)}",
        f"- Sous-parties importées : {len(debate_source['subsections'])}",
        f"- Articles Wikipédia importés : {len(debate_source['wikipedia_articles'])}",
        f"- Résumés absents : {audit['arguments']['summaries_missing']}",
        f"- Résumés de moins de 80 caractères : {audit['arguments']['summaries_under_80_chars']}",
        f"- Citations importées : {audit['arguments']['citations']}",
        "", "L’introduction historique et les résumés historiques sont protégés : la revue ordinaire ne peut ni les réécrire ni créer un résumé historiquement absent.",
        "", "Aucune correction automatique n’a été appliquée.", "",
    ]
    (workspace / "audits/fr_content_inventory.md").write_text("\n".join(markdown), encoding="utf-8", newline="\n")
    meta = copy.deepcopy(meta)
    meta["kit_version"] = KIT_VERSION
    meta["status"] = "fr_content_review_ready"
    meta.setdefault("artifacts", {})["french_content_review"] = "reviews/fr/content_review.json"
    meta["artifacts"]["sources_working"] = "data/sources_working.json"
    meta["artifacts"]["classification_review"] = CLASSIFICATION_REVIEW_PATH
    meta["artifacts"]["keyword_vocabulary_working"] = "data/keyword_vocabulary_working.json"
    meta["artifacts"]["content_reviewed_copy"] = "content-reviewed-copy"
    meta["french_content_review"] = {
        "status": "prepared",
        "prepared_at": now,
        "prepared_reviewed_copy_sha256": review["prepared_reviewed_copy_sha256"],
    }
    meta["workspace_sha256"] = None
    meta["workspace_sha256"] = workspace_receipt_hash(meta)
    write_json(workspace / "workspace.json", meta)
    # Metadata application declared translation readiness; content review now becomes the remaining gate.
    translation_path = workspace / "reviews/en/translation_readiness.json"
    if translation_path.is_file():
        translation = load_json(translation_path, "préparation anglaise")
        translation["status"] = "blocked_by_french_content_review"
        for item in translation.get("items") or []:
            item["translation_status"] = "blocked_by_french_content_review"
        write_json(translation_path, translation)
    return {
        "status": "fr_content_review_ready",
        "debate_id": debate_id,
        "work_id": work_id,
        "review_path": relative_to_project(review_path, project_root),
        "sources_path": relative_to_project(sources_path, project_root),
        "classification_review_path": relative_to_project(classification_path, project_root),
        "keyword_vocabulary_path": relative_to_project(vocabulary_path, project_root),
        "arguments": len(arguments),
        "reviewed_copy_mutated": False,
        "final_pages_generated": False,
        "english_translation_started": False,
    }


def _select(decision: Mapping[str, Any], field: str, source: Any, proposed: str) -> Any:
    value = decision.get(field)
    if value == "keep":
        return copy.deepcopy(source)
    if value == "change":
        return copy.deepcopy(decision.get(proposed))
    raise ContentReviewError(f"Décision absente ou invalide : {field}")


def _plain(value: str) -> str:
    value = re.sub(r"<ref\b[^>]*>.*?</ref>|<ref\b[^>]*/>", " ", value or "", flags=re.I | re.S)
    value = re.sub(r"\{\{[^{}]*\}\}|\[\[[^\]]+\]\]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _validate_source_registry(data: Mapping[str, Any], debate_id: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if data.get("schema") != SOURCES_WORKING_SCHEMA or data.get("debate_id") != debate_id:
        raise ContentReviewError("Identité ou schéma du registre documentaire de travail invalide")
    raw = data.get("sources")
    if not isinstance(raw, list):
        raise ContentReviewError("Le registre documentaire ne contient pas de liste sources")
    sources: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    dedup: set[str] = set()
    for index, source in enumerate(raw, start=1):
        if not isinstance(source, dict):
            raise ContentReviewError(f"Source #{index} invalide")
        source_id = _text(source.get("id"), f"identifiant de la source #{index}")
        if not SOURCE_ID.fullmatch(source_id) or source_id in by_id:
            raise ContentReviewError(f"Identifiant documentaire invalide ou dupliqué : {source_id}")
        source_type = source.get("type")
        if source_type not in {"bibliography", "webliography", "videography"}:
            raise ContentReviewError(f"Type documentaire invalide pour {source_id}")
        allowed_document_kinds = {
            "book", "monograph", "handbook", "edited_volume", "synthesis_report",
            "review_article", "journal_article", "book_chapter", "conference_paper",
            "thesis", "legal_text", "other", None,
        }
        document_kind = source.get("document_kind")
        if document_kind not in allowed_document_kinds:
            allowed = ", ".join(sorted(value for value in allowed_document_kinds if value is not None))
            raise ContentReviewError(
                f"document_kind invalide pour {source_id} : {document_kind!r}; valeurs admises : {allowed} ou null"
            )
        language = _text(source.get("language"), f"langue de {source_id}", 2)
        metadata = source.get("metadata")
        if not isinstance(metadata, dict) or set(metadata) != set(SOURCE_METADATA_FIELDS):
            raise ContentReviewError(f"Métadonnées incomplètes pour {source_id}")
        authors = metadata.get("authors")
        if not isinstance(authors, list) or any(not isinstance(a, str) or not a.strip() for a in authors):
            raise ContentReviewError(f"Liste d’auteurs invalide pour {source_id}")
        if source_type == "bibliography" and (not authors or not (metadata.get("article") or metadata.get("work"))):
            raise ContentReviewError(f"Référence bibliographique incomplète : {source_id}")
        if source_type in {"webliography", "videography"} and not HTTP_URL.match(str(metadata.get("link") or "")):
            raise ContentReviewError(f"Lien HTTP(S) obligatoire pour {source_id}")
        if source_type == "videography" and re.search(r"(?:youtube\.com/(?:watch|live)|youtu\.be/)", str(metadata.get("link") or ""), re.I) and not authors:
            raise ContentReviewError(f"Une vidéo YouTube doit indiquer le créateur ou la chaîne : {source_id}")
        date = metadata.get("date")
        if isinstance(date, str) and re.fullmatch(r"\d{4}-\d{2}(?:-\d{2})?", date.strip()):
            raise ContentReviewError(f"Date documentaire au format machine interdite : {source_id}")
        verification = source.get("verification")
        if not isinstance(verification, dict) or verification.get("status") != "verified":
            raise ContentReviewError(f"Source non vérifiée : {source_id}")
        if verification.get("language_verified") is not True:
            raise ContentReviewError(f"Langue non vérifiée pour {source_id}")
        if source_type in {"webliography", "videography"}:
            if verification.get("authorship_checked") is not True:
                raise ContentReviewError(f"Attribution non vérifiée pour {source_id}")
            if authors and verification.get("authorship_verified") is not True:
                raise ContentReviewError(f"Auteurs renseignés mais non vérifiés pour {source_id}")
        usage = source.get("usage")
        if not isinstance(usage, list) or not usage:
            raise ContentReviewError(f"Aucun usage déclaré pour {source_id}")
        for use in usage:
            if not isinstance(use, dict) or not use.get("page_id") or use.get("language") != "fr":
                raise ContentReviewError(f"Usage documentaire invalide pour {source_id}")
            if use.get("role") not in {"supports_summary", "supports_introduction", "pro_reference", "con_reference", "neutral_reference", "context"}:
                raise ContentReviewError(f"Rôle documentaire invalide pour {source_id}")
            if use.get("role") == "supports_summary":
                if use.get("argument_development_verified") is not True:
                    raise ContentReviewError(f"Le développement de l’argument n’est pas vérifié pour {source_id}")
                if not isinstance(use.get("also_develops_objections"), bool):
                    raise ContentReviewError(f"La couverture éventuelle d’objections doit être attestée pour {source_id}")
            if len(str(use.get("selection_reason") or "").strip()) < 12:
                raise ContentReviewError(f"Justification de sélection insuffisante pour {source_id}")
        key = _text(source.get("deduplication_key"), f"clé de dédoublonnage de {source_id}")
        if key.casefold() in dedup:
            raise ContentReviewError(f"Clé de dédoublonnage dupliquée : {key}")
        dedup.add(key.casefold())
        clean = copy.deepcopy(source)
        by_id[source_id] = clean
        sources.append(clean)
    return sources, by_id


def _has_usage(source: Mapping[str, Any], page_id: str, roles: set[str]) -> bool:
    return any(
        use.get("page_id") == page_id and use.get("language") == "fr" and use.get("role") in roles
        for use in source.get("usage") or []
        if isinstance(use, dict)
    )


REF_PAIR_RE = re.compile(r"<ref\b[^>]*>(.*?)</ref\s*>", re.I | re.S)


def _validated_terminal_period_exceptions(introduction: str, raw_exceptions: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_exceptions, list):
        raise ContentReviewError("La liste terminal_period_sentence_exceptions est absente")
    period_bodies = {hashlib.sha256(body.strip().encode("utf-8")).hexdigest(): body.strip() for body in REF_PAIR_RE.findall(introduction) if body.strip().endswith(".")}
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_exceptions:
        if not isinstance(item, dict):
            raise ContentReviewError("Exception de ponctuation de note invalide")
        body_sha = str(item.get("body_sha256") or "")
        evidence = str(item.get("sentence_evidence") or "").strip()
        body = period_bodies.get(body_sha)
        if not re.fullmatch(r"[0-9a-f]{64}", body_sha) or body_sha in seen or item.get("complete_sentence") is not True or len(evidence) < 12 or body is None or evidence not in body:
            raise ContentReviewError("Toute note terminée par un point doit être une phrase complète attestée par son empreinte et un extrait réel")
        seen.add(body_sha)
        validated.append({"body_sha256": body_sha, "complete_sentence": True, "sentence_evidence": evidence})
    missing = sorted(set(period_bodies) - seen)
    if missing:
        raise ContentReviewError("Une simple notice de référence se termine par un point; retirez-le ou attestez une véritable phrase complète")
    return validated


def _normalize_hover_article(value: Any) -> str:
    return re.sub(r"[_\s]+", " ", str(value or "")).strip().casefold()


def _normalize_visible(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("’", "'")).strip().casefold()


def _hover_entries(content: str, lang: str = "fr") -> list[dict[str, str]]:
    model = r"Lien\s+Wikipédia" if lang == "fr" else r"Wikipedia\s+link"
    display_key = "texte-affiché" if lang == "fr" else "displayed-text"
    pattern = re.compile(r"\{\{\s*" + model + r"\s*\|(?P<body>.*?)\}\}", re.I | re.S)
    result=[]
    for match in pattern.finditer(content or ""):
        params={}
        for chunk in match.group("body").split("|"):
            if "=" in chunk:
                k,v=chunk.split("=",1); params[k.strip().casefold()]=v.strip()
        article=params.get("article","")
        display=params.get(display_key.casefold()) or article
        if article: result.append({"article":_normalize_hover_article(article),"display":_normalize_visible(display)})
    return result


def _visible_text(content: str, lang: str = "fr") -> str:
    model = r"Lien\s+Wikipédia" if lang == "fr" else r"Wikipedia\s+link"
    display_key = "texte-affiché" if lang == "fr" else "displayed-text"
    pattern = re.compile(r"\{\{\s*" + model + r"\s*\|(?P<body>.*?)\}\}", re.I | re.S)
    def repl(m):
        params={}
        for chunk in m.group("body").split("|"):
            if "=" in chunk:
                k,v=chunk.split("=",1); params[k.strip().casefold()]=v.strip()
        return params.get(display_key.casefold()) or params.get("article","")
    text=pattern.sub(repl,content or "")
    text=re.sub(r"<ref(?:\s[^>]*)?>.*?</ref>|<ref(?:\s[^>]*)?\s*/>"," ",text,flags=re.I|re.S)
    text=re.sub(r"\{\{.*?\}\}"," ",text,flags=re.S)
    return _normalize_visible(text)


def _validated_specialized_term_inventory(introduction: str, raw_inventory: Any, subsection_ledger: Any, lang: str = "fr") -> list[dict[str, Any]]:
    if not isinstance(raw_inventory, list):
        raise ContentReviewError("L’inventaire des notions spécialisées est absent")
    subsections=_subsections(introduction)
    titles=[row["title"] for row in subsections]
    if [str(x.get("subsection_title") or "").strip() for x in raw_inventory if isinstance(x,dict)] != titles or len(raw_inventory)!=len(titles):
        raise ContentReviewError("L’inventaire des notions spécialisées ne couvre pas exactement les sous-parties")
    ledger={str(x.get("title") or "").strip():x for x in (subsection_ledger or []) if isinstance(x,dict)}
    by_title={x["title"]:x["content"] for x in subsections}
    prior={}
    clean=[]
    for index,inv in enumerate(raw_inventory,start=1):
        title=titles[index-1]
        if not isinstance(inv,dict) or inv.get("scan_complete") is not True or len(str(inv.get("scan_note") or "").strip())<30 or not isinstance(inv.get("terms"),list):
            raise ContentReviewError(f"Inventaire spécialisé incomplet pour {title}")
        terms=inv["terms"]
        if (ledger.get(title) or {}).get("technical_or_specialized") is True and not terms:
            raise ContentReviewError(f"La sous-partie technique {title} ne peut avoir un inventaire vide")
        visible=_visible_text(by_title[title],lang); hover=_hover_entries(by_title[title],lang); actual={(x['article'],x['display']) for x in hover}; declared=set(); seen=set(); rows=[]
        for term_index,row in enumerate(terms,start=1):
            if not isinstance(row,dict): raise ContentReviewError(f"Notion #{term_index} invalide dans {title}")
            term=str(row.get('term') or '').strip(); nt=_normalize_visible(term); treatment=row.get('treatment')
            if not term or nt in seen or treatment not in {'wikipedia_link','explained_inline','prior_treatment','context_sufficient'}: raise ContentReviewError(f"Notion #{term_index} invalide dans {title}")
            seen.add(nt)
            if nt not in visible: raise ContentReviewError(f"La notion {term} est absente de {title}")
            out={'term':term,'treatment':treatment}
            if treatment=='wikipedia_link':
                article=str(row.get('article') or '').strip(); key=(_normalize_hover_article(article),nt)
                if not article or key not in actual: raise ContentReviewError(f"Le lien déclaré pour {term} est absent de {title}")
                out['article']=article; declared.add(key); prior[(title,nt)]='wikipedia_link'
            elif treatment=='explained_inline':
                excerpt=str(row.get('explanation_excerpt') or '').strip()
                if len(excerpt)<20 or _normalize_visible(excerpt) not in visible: raise ContentReviewError(f"L’explication de {term} est absente de {title}")
                out['explanation_excerpt']=excerpt; prior[(title,nt)]='explained_inline'
            elif treatment=='prior_treatment':
                pt=str(row.get('prior_subsection_title') or '').strip(); pterm=str(row.get('prior_term') or '').strip(); np=_normalize_visible(pterm)
                if pt not in titles[:index-1] or prior.get((pt,np)) not in {'wikipedia_link','explained_inline'}: raise ContentReviewError(f"Le traitement antérieur de {term} est invalide")
                out.update({'prior_subsection_title':pt,'prior_term':pterm})
            else:
                justification=str(row.get('justification') or '').strip()
                if len(justification)<30: raise ContentReviewError(f"Le contexte suffisant pour {term} n’est pas justifié")
                out['justification']=justification
            rows.append(out)
        if actual-declared: raise ContentReviewError(f"Des liens Wikipédia de {title} ne figurent pas dans l’inventaire : {sorted(actual-declared)!r}")
        clean.append({'subsection_title':title,'scan_complete':True,'scan_note':str(inv['scan_note']).strip(),'terms':rows})
    return clean

def _validated_specialized_term_inventory_differential(
    introduction: str, raw_inventory: Any, subsection_ledger: Any,
    changed_keys: set[tuple[str, int]], lang: str = "fr",
) -> list[dict[str, Any]]:
    """Validate inventories only for newly added/rewritten subsections.

    The returned inventory is intentionally limited to the changed scope.
    Historical subsections may still be represented in a legacy/full review
    package, but incomplete attestations for those unchanged texts cannot make
    an authorized local edit fail retroactively.
    """
    if not changed_keys:
        return []
    if not isinstance(raw_inventory, list):
        raise ContentReviewError("L’inventaire des notions spécialisées est absent pour les sous-parties modifiées")
    keyed = _keyed_subsections(introduction)
    ledger_counts: dict[str, int] = {}
    ledger_by_key: dict[tuple[str, int], Mapping[str, Any]] = {}
    for row in subsection_ledger or []:
        if not isinstance(row, Mapping):
            continue
        title=str(row.get("title") or "")
        ledger_counts[title]=ledger_counts.get(title,0)+1
        ledger_by_key[(title,ledger_counts[title])]=row
    inventory_counts: dict[str, int] = {}
    inventory_by_key: dict[tuple[str, int], Mapping[str, Any]] = {}
    for row in raw_inventory:
        if not isinstance(row, Mapping):
            continue
        title=str(row.get("subsection_title") or "").strip()
        inventory_counts[title]=inventory_counts.get(title,0)+1
        inventory_by_key[(title,inventory_counts[title])]=row
    key_positions={key:index for index,(key,_row) in enumerate(keyed)}
    clean=[]
    for key, subsection in keyed:
        if key not in changed_keys:
            continue
        inv=inventory_by_key.get(key)
        title=key[0]
        if not isinstance(inv, Mapping) or inv.get("scan_complete") is not True or len(str(inv.get("scan_note") or "").strip()) < 30 or not isinstance(inv.get("terms"), list):
            raise ContentReviewError(f"Inventaire spécialisé incomplet pour la sous-partie modifiée {title}")
        terms=inv.get("terms") or []
        if (ledger_by_key.get(key) or {}).get("technical_or_specialized") is True and not terms:
            raise ContentReviewError(f"La sous-partie technique modifiée {title} ne peut avoir un inventaire vide")
        visible=_visible_text(str(subsection.get("content") or ""),lang)
        hover=_hover_entries(str(subsection.get("content") or ""),lang)
        actual={(x['article'],x['display']) for x in hover}; declared=set(); seen=set(); rows=[]
        for term_index,row in enumerate(terms,start=1):
            if not isinstance(row,Mapping):
                raise ContentReviewError(f"Notion #{term_index} invalide dans {title}")
            term=str(row.get('term') or '').strip(); nt=_normalize_visible(term); treatment=row.get('treatment')
            if not term or nt in seen or treatment not in {'wikipedia_link','explained_inline','prior_treatment','context_sufficient'}:
                raise ContentReviewError(f"Notion #{term_index} invalide dans {title}")
            seen.add(nt)
            if nt not in visible:
                raise ContentReviewError(f"La notion {term} est absente de {title}")
            out={'term':term,'treatment':treatment}
            if treatment=='wikipedia_link':
                article=str(row.get('article') or '').strip(); pair=(_normalize_hover_article(article),nt)
                if not article or pair not in actual:
                    raise ContentReviewError(f"Le lien déclaré pour {term} est absent de {title}")
                out['article']=article; declared.add(pair)
            elif treatment=='explained_inline':
                excerpt=str(row.get('explanation_excerpt') or '').strip()
                if len(excerpt)<20 or _normalize_visible(excerpt) not in visible:
                    raise ContentReviewError(f"L’explication de {term} est absente de {title}")
                out['explanation_excerpt']=excerpt
            elif treatment=='prior_treatment':
                pt=str(row.get('prior_subsection_title') or '').strip(); pterm=str(row.get('prior_term') or '').strip(); np=_normalize_visible(pterm)
                current_position=key_positions[key]
                prior_candidates=[r for pos,(k,r) in enumerate(keyed) if k[0]==pt and pos < current_position]
                if not prior_candidates or not any(np in _visible_text(str(r.get('content') or ''),lang) for r in prior_candidates):
                    raise ContentReviewError(f"Le traitement antérieur de {term} est invalide")
                out.update({'prior_subsection_title':pt,'prior_term':pterm})
            else:
                justification=str(row.get('justification') or '').strip()
                if len(justification)<30:
                    raise ContentReviewError(f"Le contexte suffisant pour {term} n’est pas justifié")
                out['justification']=justification
            rows.append(out)
        if actual-declared:
            raise ContentReviewError(f"Des liens Wikipédia de {title} ne figurent pas dans l’inventaire : {sorted(actual-declared)!r}")
        clean.append({'subsection_title':title,'scan_complete':True,'scan_note':str(inv['scan_note']).strip(),'terms':rows})
    return clean


def _validated_terminal_period_exceptions_differential(changed_content: str, raw_exceptions: Any) -> list[dict[str, Any]]:
    if not changed_content:
        return []
    if not isinstance(raw_exceptions, list):
        raise ContentReviewError("La liste terminal_period_sentence_exceptions est absente pour le contenu modifié")
    relevant_hashes={hashlib.sha256(body.strip().encode("utf-8")).hexdigest() for body in REF_PAIR_RE.findall(changed_content) if body.strip().endswith(".")}
    filtered=[row for row in raw_exceptions if isinstance(row, Mapping) and row.get("body_sha256") in relevant_hashes]
    return _validated_terminal_period_exceptions(changed_content, filtered)


def _validate_debate(
    review: Mapping[str, Any], source: Mapping[str, Any], sources: Mapping[str, Mapping[str, Any]],
    debate_id: str, authorization: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if review.get("status") != "approved":
        raise ContentReviewError("La revue de la page Débat n’est pas approuvée")
    subject = _text(_select(review, "subject_decision", source.get("subject"), "proposed_subject"), "sujet", 2)
    complete = _text(_select(review, "complete_topic_decision", source.get("complete_topic"), "proposed_complete_topic"), "sujet-développé", 2)
    if QUESTION_TOPIC.search(complete):
        raise ContentReviewError("sujet-développé ne doit pas être une question")
    first_alpha = next((char for char in complete if char.isalpha()), "")
    if first_alpha and first_alpha.isupper() and len(str(review.get("complete_topic_initial_capital_justification") or "").strip()) < 12:
        raise ContentReviewError("La majuscule initiale de sujet-développé n’est pas justifiée")
    historical_intro = str(source.get("introduction") or "")
    historical_intro_protected = source.get("page_origin") == "preexisting"
    historical_intro_authorized = False
    authorization_row: Mapping[str, Any] | None = None
    if historical_intro_protected:
        if not _historical_policy_supported(review.get("historical_text_policy")):
            raise ContentReviewError("Politique de consentement de l’introduction historique absente ou invalide")
        decision = str(review.get("introduction_decision") or "")
        field_key = f"debate:{debate_id}:introduction"
        if decision == "keep":
            if str(review.get("proposed_introduction") or "") != historical_intro:
                raise ContentReviewError("Une introduction historique déclarée préservée doit rester identique à la source")
            if review.get("historical_text_status") not in {"preserved", None}:
                raise ContentReviewError("Statut de l’introduction historique incohérent avec decision=keep")
            introduction = historical_intro
        elif decision == "change":
            introduction = str(review.get("proposed_introduction") or "")
            request = _historical_change_request(
                review, field_key=field_key, historical_value=historical_intro, final_value=introduction,
            )
            if request is None:
                raise ContentReviewError("Modification d’introduction historique sans demande d’autorisation structurée")
            authorization_row = (authorization or {}).get(field_key)
            if not isinstance(authorization_row, Mapping):
                raise ContentReviewError("Modification d’introduction historique sans consentement propriétaire local")
            if authorization_row.get("historical_sha256") != request["historical_sha256"] or authorization_row.get("final_sha256") != request["final_sha256"]:
                raise ContentReviewError("Le consentement propriétaire ne couvre pas la valeur exacte de l’introduction")
            if review.get("historical_text_status") not in {"authorization_requested", "authorized_change"}:
                raise ContentReviewError("Le statut d’une introduction historique modifiée doit signaler une autorisation demandée")
            historical_intro_authorized = True
        else:
            raise ContentReviewError("Décision invalide pour l’introduction historique : keep ou change attendu")
    else:
        introduction = _text(_select(review, "introduction_decision", source.get("introduction"), "proposed_introduction"), "introduction", 30)
    subsection_values = _subsections(introduction)
    if (not historical_intro_protected or historical_intro_authorized) and not subsection_values:
        raise ContentReviewError("L’introduction doit contenir au moins une Sous-partie")
    ledger = review.get("subsections")
    if not isinstance(ledger, list) or [row.get("title") for row in ledger if isinstance(row, dict)] != [row["title"] for row in subsection_values]:
        raise ContentReviewError("La revue des sous-parties ne correspond pas à l’introduction retenue")
    stakes_title = "Enjeux du débat"
    if historical_intro_protected and not historical_intro_authorized:
        # Pure preservation: the historical introduction remains provenance and
        # selected value. Creation-only editorial gates are not retroactive.
        specialized_term_inventory = []
        terminal_period_sentence_exceptions = []
        historical_change_scope = None
        changed_final_keys: set[tuple[str, int]] = set()
    elif historical_intro_protected and historical_intro_authorized:
        # Once authorized, the selected final introduction is the effective
        # editorial value. Global structural checks already use it. Creation
        # gates apply only to subsections actually added/rewritten, never to
        # unchanged historical subsections.
        historical_change_scope = copy.deepcopy((authorization_row or {}).get("change_scope") or _subsection_change_scope(historical_intro, introduction))
        observed_scope = historical_change_scope.get("observed_subsection_delta") if isinstance(historical_change_scope, Mapping) else None
        if not isinstance(observed_scope, Mapping):
            observed_scope = historical_change_scope if isinstance(historical_change_scope, Mapping) and historical_change_scope.get("mode") == "subsections" else _subsection_change_scope(historical_intro, introduction)
        changed_final_keys = _changed_final_subsection_keys(observed_scope)
        keyed_final = _keyed_subsections(introduction)
        ledger_by_key: dict[tuple[str, int], Mapping[str, Any]] = {}
        title_counts: dict[str, int] = {}
        for row in ledger:
            title = str((row or {}).get("title") or "") if isinstance(row, Mapping) else ""
            title_counts[title] = title_counts.get(title, 0) + 1
            if isinstance(row, Mapping):
                ledger_by_key[(title, title_counts[title])] = row
        changed_sections=[]
        change_type = str((authorization_row or {}).get("change_type") or "")
        creation_like_scope = change_type in {"structure", "substantive_rewrite"}
        if creation_like_scope:
            for index, (key, subsection) in enumerate(keyed_final, start=1):
                if key not in changed_final_keys:
                    continue
                row = ledger_by_key.get(key) or {}
                if len(str(row.get("purpose") or "").strip()) < 12 or row.get("necessary_for_understanding") is not True:
                    raise ContentReviewError(f"Sous-partie modifiée #{index} insuffisamment justifiée")
                if row.get("technical_or_specialized") is True and row.get("relevance_to_debate_explained") is not True:
                    raise ContentReviewError(f"Pertinence technique non attestée pour la sous-partie modifiée #{index}")
                if subsection["title"] == stakes_title:
                    if row.get("stakes_section") is not True:
                        raise ContentReviewError("La revue doit identifier explicitement la sous-partie Enjeux du débat ajoutée ou modifiée")
                    concrete_stakes = row.get("concrete_stakes")
                    if not isinstance(concrete_stakes, list):
                        raise ContentReviewError("Les conséquences concrètes de la sous-partie Enjeux du débat sont absentes")
                    normalized_stakes = [str(item).strip() for item in concrete_stakes if str(item).strip()]
                    if len(normalized_stakes) < 2 or len({item.casefold() for item in normalized_stakes}) < 2 or any(len(item) < 20 for item in normalized_stakes):
                        raise ContentReviewError("La sous-partie Enjeux du débat doit consigner au moins deux conséquences concrètes distinctes")
                    stakes_content = subsection["content"]
                    if len(re.findall(r"\b[\wÀ-ÿ'-]+\b", stakes_content)) < 45 or len(re.findall(r"[.!?](?:\s|$)", stakes_content)) < 3:
                        raise ContentReviewError("La sous-partie Enjeux du débat est trop brève ou symbolique")
                changed_sections.append(subsection)
            specialized_term_inventory = _validated_specialized_term_inventory_differential(
                introduction, review.get("specialized_term_inventory"), ledger, changed_final_keys, "fr"
            )
            changed_content = "".join(str(row.get("content") or "") for key, row in keyed_final if key in changed_final_keys)
            terminal_period_sentence_exceptions = _validated_terminal_period_exceptions_differential(
                changed_content, review.get("terminal_period_sentence_exceptions")
            )
        else:
            specialized_term_inventory = []
            terminal_period_sentence_exceptions = []
    else:
        historical_change_scope = None
        changed_final_keys = set()
        stakes_rows = []
        stakes_contents = []
        for index, (row, subsection) in enumerate(zip(ledger, subsection_values), start=1):
            if len(str(row.get("purpose") or "").strip()) < 12 or row.get("necessary_for_understanding") is not True:
                raise ContentReviewError(f"Sous-partie #{index} insuffisamment justifiée")
            if row.get("technical_or_specialized") is True and row.get("relevance_to_debate_explained") is not True:
                raise ContentReviewError(f"Pertinence technique non attestée pour la sous-partie #{index}")
            if subsection["title"] == stakes_title:
                stakes_rows.append(row)
                stakes_contents.append(subsection["content"])
        if len(stakes_rows) != 1:
            raise ContentReviewError('L’introduction française doit contenir exactement une sous-partie intitulée "Enjeux du débat"')
        stakes_row = stakes_rows[0]
        if stakes_row.get("stakes_section") is not True:
            raise ContentReviewError("La revue doit identifier explicitement la sous-partie Enjeux du débat")
        concrete_stakes = stakes_row.get("concrete_stakes")
        if not isinstance(concrete_stakes, list):
            raise ContentReviewError("Les conséquences concrètes de la sous-partie Enjeux du débat sont absentes")
        normalized_stakes = [str(item).strip() for item in concrete_stakes if str(item).strip()]
        if len(normalized_stakes) < 2 or len({item.casefold() for item in normalized_stakes}) < 2 or any(len(item) < 20 for item in normalized_stakes):
            raise ContentReviewError("La sous-partie Enjeux du débat doit consigner au moins deux conséquences concrètes distinctes")
        stakes_content = stakes_contents[0]
        if len(re.findall(r"\b[\wÀ-ÿ'-]+\b", stakes_content)) < 45 or len(re.findall(r"[.!?](?:\s|$)", stakes_content)) < 3:
            raise ContentReviewError("La sous-partie Enjeux du débat est trop brève ou symbolique")
        for field in INTRO_TRUE_FIELDS:
            if review.get(field) is not True:
                raise ContentReviewError(f"Attestation d’introduction manquante : {field}")
        specialized_term_inventory = _validated_specialized_term_inventory(introduction, review.get("specialized_term_inventory"), ledger, "fr")
        terminal_period_sentence_exceptions = _validated_terminal_period_exceptions(introduction, review.get("terminal_period_sentence_exceptions"))
    if len(str(review.get("topic_label_rationale") or "").strip()) < 12:
        raise ContentReviewError("Justification du libellé de sujet insuffisante")
    family_notes = review.get("documentation_family_notes")
    if not isinstance(family_notes, dict) or set(family_notes) != {"bibliography", "webliography", "videography"}:
        raise ContentReviewError("Notes par famille documentaire absentes")
    for family, note in family_notes.items():
        if len(str(note).strip()) < 20:
            raise ContentReviewError(f"Note documentaire trop courte pour {family}")
    wikipedia = _list_strings(_select(review, "wikipedia_articles_decision", source.get("wikipedia_articles") or [], "proposed_wikipedia_articles"), "articles Wikipédia")
    if not wikipedia or review.get("wikipedia_articles_verified") is not True:
        raise ContentReviewError("Au moins un article Wikipédia français vérifié est requis")
    documentation: dict[str, list[str]] = {}
    raw_decisions = review.get("documentation_decisions")
    proposed = review.get("proposed_documentation")
    rationales = review.get("documentation_rationales")
    if not isinstance(raw_decisions, dict) or not isinstance(proposed, dict) or not isinstance(rationales, dict):
        raise ContentReviewError("Décisions documentaires de la page Débat absentes")
    selected_roles: dict[str, set[str]] = {}
    for bucket, (source_type, role) in DEBATE_BUCKETS.items():
        if raw_decisions.get(bucket) != "change":
            raise ContentReviewError(f"Le bucket {bucket} doit être reconstruit sous forme de sources contrôlées")
        selected = _list_strings(proposed.get(bucket), bucket)
        if len(str(rationales.get(bucket) or "").strip()) < 12:
            raise ContentReviewError(f"Justification documentaire absente pour {bucket}")
        for source_id in selected:
            source_row = sources.get(source_id)
            if not source_row or source_row.get("type") != source_type:
                raise ContentReviewError(f"Type de source incompatible dans {bucket} : {source_id}")
            if source_row.get("language") != "fr":
                raise ContentReviewError(f"Une page Débat française ne peut utiliser une source non française : {source_id}")
            if not _has_usage(source_row, debate_id, {role}):
                raise ContentReviewError(f"Usage documentaire manquant pour {source_id} dans {bucket}")
            selected_roles.setdefault(source_id, set()).add(role)
        documentation[bucket] = selected
    conflicts = {sid: sorted(roles) for sid, roles in selected_roles.items() if len(roles) > 1}
    if conflicts:
        raise ContentReviewError(
            "Une même référence ne peut figurer dans plusieurs orientations; une source couvrant les deux camps doit être classée ni pour ni contre : "
            + repr(conflicts)
        )
    for source_id, source_row in sources.items():
        roles = {
            use.get("role") for use in source_row.get("usage") or []
            if isinstance(use, dict) and use.get("page_id") == debate_id and use.get("language") == "fr"
            and use.get("role") in {"pro_reference", "con_reference", "neutral_reference"}
        }
        if "pro_reference" in roles and "con_reference" in roles:
            raise ContentReviewError(
                f"La référence {source_id} est déclarée à la fois pour et contre; elle doit recevoir uniquement le rôle neutral_reference"
            )
    if review.get("reviewer") is None or len(str(review.get("reviewer") or "").strip()) < 3:
        raise ContentReviewError("Relecteur de l’introduction absent")
    _text(review.get("reviewed_at"), "date de revue de l’introduction", 10)
    _text(review.get("note"), "note de revue de l’introduction", 12)
    return {
        "subject": subject,
        "complete_topic": complete,
        "common_acronym": review.get("common_acronym"),
        "introduction": introduction,
        "subsections": ledger,
        "wikipedia_articles": wikipedia,
        "documentation": documentation,
        "documentation_family_notes": copy.deepcopy(family_notes),
        "reviewer": review.get("reviewer"),
        "reviewed_at": review.get("reviewed_at"),
        "note": review.get("note"),
        "attestations": ({field: True for field in INTRO_TRUE_FIELDS} if not historical_intro_protected else {}),
        "terminal_period_sentence_exceptions": terminal_period_sentence_exceptions,
        "specialized_term_inventory": specialized_term_inventory,
        "introduction_provenance": (
            "historical_authorized_change" if historical_intro_protected and historical_intro_authorized
            else "historical_existing" if historical_intro_protected and bool(historical_intro.strip())
            else "historical_absent" if historical_intro_protected
            else "reviewed_or_generated"
        ),
        "historical_introduction_present": bool(historical_intro.strip()) if historical_intro_protected else None,
        "historical_introduction_sha256": (
            hashlib.sha256(historical_intro.encode("utf-8")).hexdigest() if historical_intro_protected else None
        ),
        "historical_final_introduction_sha256": (
            hashlib.sha256(str(introduction or "").encode("utf-8")).hexdigest() if historical_intro_protected else None
        ),
        "historical_text_decision": ("authorized_change" if historical_intro_authorized else "preserved") if historical_intro_protected else None,
        "historical_authorization": copy.deepcopy(dict(authorization_row)) if historical_intro_authorized and authorization_row else None,
        "historical_change_scope": copy.deepcopy(historical_change_scope) if historical_intro_authorized else None,
        "historical_content_preserved": historical_intro_protected and not historical_intro_authorized,
        "page_origin": source.get("page_origin", "preexisting"),
        "preserved_parameters": copy.deepcopy(source.get("preserved_parameters") or {}),
        "source_parameter_presence": copy.deepcopy(source.get("source_parameter_presence") or {}),
    }


def _validate_argument(
    item: Mapping[str, Any], sources: Mapping[str, Mapping[str, Any]],
    authorization: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    node_id = _text(item.get("id"), "identifiant d’argument")
    source = item.get("source") or {}
    review = item.get("review") or {}
    if review.get("status") != "approved":
        raise ContentReviewError(f"Revue non approuvée pour {node_id}")
    historical_summary = str(source.get("summary") or "")
    historical_summary_protected = source.get("page_origin") == "preexisting"
    historical_summary_authorized = False
    authorization_row: Mapping[str, Any] | None = None
    if historical_summary_protected:
        if not _historical_policy_supported(review.get("historical_text_policy")):
            raise ContentReviewError(f"Politique de consentement du résumé historique absente ou invalide pour {node_id}")
        expected_hash = hashlib.sha256(historical_summary.encode("utf-8")).hexdigest()
        if review.get("historical_summary_sha256") != expected_hash:
            raise ContentReviewError(f"Empreinte du résumé historique divergente pour {node_id}")
        if bool(review.get("historical_summary_present")) != bool(historical_summary.strip()):
            raise ContentReviewError(f"Présence historique du résumé incohérente pour {node_id}")
        decision = str(review.get("summary_decision") or "")
        field_key = f"argument:{node_id}:summary"
        if decision == "keep":
            if str(review.get("proposed_summary") or "") != historical_summary:
                raise ContentReviewError(f"Un résumé historique déclaré préservé doit rester identique pour {node_id}")
            if review.get("historical_text_status") not in {"preserved", None}:
                raise ContentReviewError(f"Statut historique incohérent avec decision=keep pour {node_id}")
            summary = historical_summary if historical_summary.strip() else None
        elif decision == "change":
            proposed_summary = str(review.get("proposed_summary") or "")
            request = _historical_change_request(
                review, field_key=field_key, historical_value=historical_summary, final_value=proposed_summary,
            )
            if request is None:
                raise ContentReviewError(f"Modification du résumé historique sans demande d’autorisation structurée pour {node_id}")
            authorization_row = (authorization or {}).get(field_key)
            if not isinstance(authorization_row, Mapping):
                raise ContentReviewError(f"Modification du résumé historique sans consentement propriétaire local pour {node_id}")
            if authorization_row.get("historical_sha256") != request["historical_sha256"] or authorization_row.get("final_sha256") != request["final_sha256"]:
                raise ContentReviewError(f"Le consentement propriétaire ne couvre pas la valeur exacte du résumé {node_id}")
            if review.get("historical_text_status") not in {"authorization_requested", "authorized_change"}:
                raise ContentReviewError(f"Le statut d’un résumé historique modifié doit signaler une autorisation demandée pour {node_id}")
            historical_summary_authorized = True
            summary = proposed_summary if proposed_summary.strip() else None
        else:
            raise ContentReviewError(f"Décision invalide pour le résumé historique {node_id} : keep ou change attendu")
        # A scoped authorized correction does not retroactively activate the
        # creation-style checklist for the whole historical summary. Even a
        # substantive rewrite remains a historical field with explicit owner
        # provenance; broader stylistic review may be recorded, but is not used
        # as a pretext to rewrite unrelated historical wording.
        expression = None
        numbers = NUMBER.findall(_plain(summary or ""))
    else:
        summary = _text(_select(review, "summary_decision", source.get("summary"), "proposed_summary"), f"résumé de {node_id}", 40)
        if META_DISCOURSE.search(_plain(summary)):
            raise ContentReviewError(f"Métadiscours interdit dans le résumé de {node_id}")
        for field in SUMMARY_TRUE_FIELDS:
            if review.get(field) is not True:
                raise ContentReviewError(f"Attestation manquante pour {node_id} : {field}")
        expression = _text(review.get("forceful_expression"), f"expression de force de {node_id}", 12)
        if len(re.findall(r"[A-Za-zÀ-ÿ]+", expression)) < 3 or _plain(expression).casefold() not in _plain(summary).casefold():
            raise ContentReviewError(f"L’expression de force n’est pas présente dans le résumé de {node_id}")
        numbers = NUMBER.findall(_plain(summary))
        if numbers:
            if review.get("quantitative_claims_verified") is not True or len(str(review.get("quantitative_claims_note") or "").strip()) < 12:
                raise ContentReviewError(f"Donnée chiffrée non documentée dans {node_id}")
    decisions = review.get("documentation_decisions")
    proposed = review.get("proposed_sources")
    if not isinstance(decisions, dict) or not isinstance(proposed, dict):
        raise ContentReviewError(f"Décisions documentaires absentes pour {node_id}")
    selected_by_type: dict[str, list[str]] = {}
    for bucket, source_type in ARGUMENT_BUCKETS.items():
        if decisions.get(bucket) != "change":
            raise ContentReviewError(f"La documentation de {node_id}/{bucket} doit être reconstruite")
        selected = _list_strings(proposed.get(bucket), f"sources {bucket} de {node_id}")
        for source_id in selected:
            source_row = sources.get(source_id)
            if not source_row or source_row.get("type") != source_type:
                raise ContentReviewError(f"Type de source incompatible pour {node_id} : {source_id}")
            if not _has_usage(source_row, node_id, {"supports_summary"}):
                raise ContentReviewError(f"Usage supports_summary absent pour {node_id} : {source_id}")
        selected_by_type[bucket] = selected
    _text(review.get("summary_rationale"), f"justification du résumé de {node_id}", 12)
    _text(review.get("documentation_rationale"), f"justification documentaire de {node_id}", 12)
    _text(review.get("reviewer"), f"relecteur de {node_id}", 3)
    _text(review.get("reviewed_at"), f"date de revue de {node_id}", 10)
    _text(review.get("note"), f"note de revue de {node_id}", 12)
    return {
        "id": node_id,
        "canonical_title": source.get("canonical_title"),
        "displayed_title": source.get("displayed_title"),
        "summary": summary,
        "citations": copy.deepcopy(source.get("citations") or []),
        "citation_passages": copy.deepcopy(source.get("citation_passages") or []),
        "sources": selected_by_type,
        "status": (
            "historical_authorized_creation" if historical_summary_protected and historical_summary_authorized and not bool(historical_summary.strip()) and bool(str(summary or "").strip())
            else "historical_authorized_change" if historical_summary_protected and historical_summary_authorized
            else "historical_existing" if historical_summary_protected and bool(historical_summary.strip())
            else "historical_absent" if historical_summary_protected
            else "revised" if review.get("summary_decision") == "change" else "approved"
        ),
        "summary_provenance": (
            "historical_authorized_creation" if historical_summary_protected and historical_summary_authorized and not bool(historical_summary.strip()) and bool(str(summary or "").strip())
            else "historical_authorized_change" if historical_summary_protected and historical_summary_authorized
            else "historical_existing" if historical_summary_protected and bool(historical_summary.strip())
            else "historical_absent" if historical_summary_protected
            else "reviewed_or_generated"
        ),
        "historical_summary_present": bool(historical_summary.strip()) if historical_summary_protected else None,
        "historical_summary_sha256": (
            hashlib.sha256(historical_summary.encode("utf-8")).hexdigest() if historical_summary_protected else None
        ),
        "historical_final_summary_sha256": (
            hashlib.sha256(str(summary or "").encode("utf-8")).hexdigest() if historical_summary_protected else None
        ),
        "historical_text_decision": ("authorized_change" if historical_summary_authorized else "preserved") if historical_summary_protected else None,
        "historical_authorization": copy.deepcopy(dict(authorization_row)) if historical_summary_authorized and authorization_row else None,
        "historical_change_scope": copy.deepcopy((authorization_row or {}).get("change_scope")) if historical_summary_authorized else None,
        "historical_content_preserved": historical_summary_protected and not historical_summary_authorized,
        "forceful_expression": expression,
        "quantitative_claims": numbers,
        "quantitative_claims_verified": bool(review.get("quantitative_claims_verified")),
        "quantitative_claims_note": review.get("quantitative_claims_note"),
        "reviewer": review.get("reviewer"),
        "reviewed_at": review.get("reviewed_at"),
        "note": review.get("note"),
        "attestations": ({field: True for field in SUMMARY_TRUE_FIELDS} if not historical_summary_protected else {}),
        "page_origin": source.get("page_origin", "preexisting"),
        "preserved_parameters": copy.deepcopy(source.get("preserved_parameters") or {}),
        "source_parameter_presence": copy.deepcopy(source.get("source_parameter_presence") or {}),
    }


def finalize_review(project_root: Path, debate_id: str, work_id: str) -> dict[str, Any]:
    workspace, meta = _load_workspace(project_root, debate_id, work_id)
    if meta.get("status") not in {"fr_content_review_ready", "fr_content_review_finalized"}:
        raise ContentReviewError(f"Statut incompatible avec la finalisation du contenu : {meta.get('status')}")
    _assert_source_unchanged(project_root, debate_id, meta)
    reviewed = _assert_reviewed_copy(workspace, meta)
    review_path = workspace / "reviews/fr/content_review.json"
    review = load_json(review_path, "revue de contenu")
    if review.get("status") == "approved" and review.get("review_sha256"):
        if review.get("review_sha256") != content_review_sha256(review):
            raise ContentReviewError("Empreinte de revue de contenu invalide")
        if review.get("prepared_reviewed_copy_sha256") != full_tree_sha256(reviewed):
            raise ContentReviewError("reviewed-copy a changé depuis la finalisation")
        return {"status": "fr_content_review_finalized", "debate_id": debate_id, "work_id": work_id, "review_sha256": review["review_sha256"], "idempotent": True}
    if review.get("schema") != CONTENT_REVIEW_SCHEMA or review.get("debate_id") != debate_id or review.get("work_id") != work_id:
        raise ContentReviewError("Identité ou schéma de la revue de contenu invalide")
    if review.get("prepared_reviewed_copy_sha256") != full_tree_sha256(reviewed):
        raise ContentReviewError("reviewed-copy a changé depuis la préparation")
    working_sources = load_json(workspace / "data/sources_working.json", "sources de travail")
    source_rows, by_source = _validate_source_registry(working_sources, debate_id)
    classification_path = workspace / CLASSIFICATION_REVIEW_PATH
    classification = load_json(classification_path, "revue des rubriques et mots-clés")
    if classification.get("review_scope") != "classification_and_content" or classification.get("debate_id") != debate_id or classification.get("work_id") != work_id:
        raise ContentReviewError("Revue des rubriques et mots-clés invalide")
    raw_classification_items = classification.get("items")
    if not isinstance(raw_classification_items, list):
        raise ContentReviewError("La revue des rubriques et mots-clés ne contient pas de liste items")
    if classification.get("status") == "approved" and classification.get("review_sha256"):
        if classification.get("review_sha256") != metadata_review_sha256(classification):
            raise ContentReviewError("Empreinte de la classification française invalide")
        final_classification_items = copy.deepcopy(classification.get("final_values") or [])
        finalized_vocabulary = copy.deepcopy(classification.get("finalized_vocabulary") or [])
        classification_summary = copy.deepcopy(classification.get("summary") or {})
        _metadata_coverage_against_registry(reviewed, final_classification_items)
        classification_final = copy.deepcopy(classification)
    else:
        try:
            final_classification_items = [_validate_metadata_item(item) for item in raw_classification_items]
            classification_summary = _validate_metadata_corpus_rules(final_classification_items)
            _metadata_coverage_against_registry(reviewed, final_classification_items)
            vocabulary_working = load_json(workspace / "data/keyword_vocabulary_working.json", "vocabulaire de travail")
            finalized_vocabulary = _validate_metadata_vocabulary(vocabulary_working, final_classification_items)
        except EditorialReviewError as exc:
            raise ContentReviewError(str(exc)) from exc
        classification_final = copy.deepcopy(classification)
        classification_final.update({
            "status": "approved", "finalized_at": now_iso(), "summary": classification_summary,
            "final_values": final_classification_items, "finalized_vocabulary": finalized_vocabulary,
            "review_sha256": None,
        })
        classification_final["review_sha256"] = metadata_review_sha256(classification_final)
        write_json(classification_path, classification_final)
    authorization = _load_historical_authorization(workspace, review)
    debate_block = review.get("debate") or {}
    final_debate = _validate_debate(
        debate_block.get("review") or {}, debate_block.get("source") or {}, by_source, debate_id, authorization,
    )
    argument_items = review.get("arguments")
    if not isinstance(argument_items, list):
        raise ContentReviewError("Liste des arguments absente de la revue de contenu")
    registry = load_json(reviewed / "data/registre_debat.json", "registre du débat")
    active_ids = {
        str(node.get("id")) for node in ((registry.get("graph") or {}).get("nodes") or []) if node.get("status") == "active"
    }
    if {str(item.get("id")) for item in argument_items if isinstance(item, dict)} != active_ids:
        raise ContentReviewError("La revue de contenu ne couvre pas exactement les arguments actifs")
    final_arguments = [_validate_argument(item, by_source, authorization) for item in argument_items]
    global_review = review.get("global_review")
    if not isinstance(global_review, dict):
        raise ContentReviewError("Revue globale absente")
    for field in ("all_french_content_reviewed", "all_selected_sources_verified", "no_final_pages_generated", "english_translation_not_started"):
        if global_review.get(field) is not True:
            raise ContentReviewError(f"Attestation globale manquante : {field}")
    if global_review.get("blocking_issues") not in ([], None):
        raise ContentReviewError("La revue globale contient encore des blocages")
    _text(global_review.get("reviewer"), "relecteur global", 3)
    _text(global_review.get("reviewed_at"), "date de revue globale", 10)
    _text(global_review.get("note"), "note de revue globale", 12)
    selected_ids: set[str] = set()
    for ids in final_debate["documentation"].values():
        selected_ids.update(ids)
    for argument in final_arguments:
        for ids in argument["sources"].values():
            selected_ids.update(ids)
    if selected_ids != set(by_source):
        raise ContentReviewError(f"Le registre documentaire doit couvrir exactement les sources retenues; inutilisées={sorted(set(by_source)-selected_ids)}, absentes={sorted(selected_ids-set(by_source))}")
    finalized = copy.deepcopy(review)
    finalized.update({
        "kit_version": KIT_VERSION,
        "status": "approved",
        "finalized_at": now_iso(),
        "prepared_reviewed_copy_sha256": full_tree_sha256(reviewed),
        "source_registry_sha256": sha256_bytes(canonical_json({"source_registry_version": working_sources.get("source_registry_version"), "debate_id": debate_id, "sources": source_rows})),
        "classification_review_sha256": classification_final["review_sha256"],
        "classification": {
            "review_sha256": classification_final["review_sha256"],
            "summary": copy.deepcopy(classification_final.get("summary") or {}),
            "source_items": copy.deepcopy(raw_classification_items),
            "final_values": copy.deepcopy(final_classification_items),
            "finalized_vocabulary": copy.deepcopy(finalized_vocabulary),
        },
        "final_values": {"debate": final_debate, "arguments": final_arguments, "sources": source_rows},
        "summary": {
            "arguments": len(final_arguments),
            "sources": len(source_rows),
            "debate_documentary_references": sum(len(v) for v in final_debate["documentation"].values()),
            "argument_documentary_references": sum(len(ids) for arg in final_arguments for ids in arg["sources"].values()),
            "citations": sum(len(arg.get("citations") or []) for arg in final_arguments),
            "authorized_historical_text_changes": len(authorization),
        },
        "historical_authorization": {
            "path": HISTORICAL_AUTHORIZATION_PATH if authorization else None,
            "changes": sorted(authorization),
        },
        "review_sha256": None,
    })
    finalized["review_sha256"] = content_review_sha256(finalized)
    write_json(review_path, finalized)
    meta = copy.deepcopy(meta)
    meta["kit_version"] = KIT_VERSION
    meta["status"] = "fr_content_review_finalized"
    meta["french_content_review"] = {
        "status": "finalized",
        "review_sha256": finalized["review_sha256"],
        "finalized_at": finalized["finalized_at"],
        "prepared_reviewed_copy_sha256": finalized["prepared_reviewed_copy_sha256"],
    }
    meta["workspace_sha256"] = None
    meta["workspace_sha256"] = workspace_receipt_hash(meta)
    write_json(workspace / "workspace.json", meta)
    return {
        "status": "fr_content_review_finalized",
        "debate_id": debate_id,
        "work_id": work_id,
        "review_sha256": finalized["review_sha256"],
        **finalized["summary"],
        "reviewed_copy_mutated": False,
        "final_pages_generated": False,
        "english_translation_started": False,
    }


def _introduction_review(final: Mapping[str, Any]) -> dict[str, Any]:
    provenance = str(final.get("introduction_provenance") or "reviewed_or_generated")
    historical = provenance in {"historical_existing", "historical_absent", "historical_authorized_change"}
    entry: dict[str, Any] = {
        "language": "fr",
        "status": provenance if historical else "approved",
        "documentation_family_notes": copy.deepcopy(final["documentation_family_notes"]),
        "common_acronym": final.get("common_acronym"),
        "topic_label_rationale": "Le sujet retenu est le libellé nominal validé par la revue française.",
        "complete_topic_initial_capital_justification": None,
        "subsections": copy.deepcopy(final["subsections"]),
        "terminal_period_sentence_exceptions": copy.deepcopy(final.get("terminal_period_sentence_exceptions") or []),
        "specialized_term_inventory": copy.deepcopy(final.get("specialized_term_inventory") or []),
    }
    if historical:
        authorized = provenance == "historical_authorized_change"
        entry.update({
            "historical_content_preserved": not authorized,
            "owner_authorized_change": authorized,
            "historical_source_sha256": final.get("historical_introduction_sha256"),
            "authorized_final_sha256": final.get("historical_final_introduction_sha256") if authorized else None,
            "authorization": copy.deepcopy(final.get("historical_authorization")) if authorized else None,
            "change_scope": copy.deepcopy(final.get("historical_change_scope")) if authorized else None,
            "historical_absence_verified": provenance == "historical_absent",
            "note": (
                "Introduction française historique modifiée dans la portée exacte autorisée par le propriétaire ; les règles de création ne sont pas appliquées rétroactivement au reste du texte."
                if authorized else
                "Introduction française historique conservée exactement ; les règles de réécriture ne sont pas appliquées rétroactivement."
            ),
            # Non-introduction controls remain traceable and true because they
            # were validated independently during content finalization.
            "complete_topic_fits_heading": True,
            "debate_sections_precise": True,
            "documentation_proportionate_to_literature": True,
            "common_acronym_used_or_not_applicable": True,
            "topic_is_nominal_label": True,
            "conventional_topic_label_used_or_not_applicable": True,
            "complete_topic_lowercase_initial_or_justified": True,
        })
    else:
        entry.update({field: True for field in INTRO_TRUE_FIELDS})
    return {
        "normative_revision": NORM_VERSION,
        "entries": [entry],
    }


def _mechanism_excerpt(summary: Any) -> str:
    text = str(summary or "").strip()
    if not text:
        return "Le résumé validé expose explicitement le mécanisme central de la thèse."
    first = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0].strip()
    if len(first) >= 30:
        return first
    return text


def _summary_style_review(arguments: Sequence[Mapping[str, Any]], debate_id: str) -> dict[str, Any]:
    entries = []
    for arg in arguments:
        status = str(arg.get("status") or "")
        if status == "historical_absent":
            language = {
                "status": "historical_absent",
                "historical_absence_verified": True,
                "note": arg.get("note") or "Absence historique du résumé vérifiée et conservée sans génération de remplissage.",
            }
            entries.append({"id": arg.get("id"), "languages": {"fr": language}})
            continue
        if status in {"historical_authorized_change", "historical_authorized_creation"}:
            language = {
                "status": status,
                "owner_authorized_change": True,
                "historical_source_sha256": arg.get("historical_summary_sha256"),
                "authorized_final_sha256": arg.get("historical_final_summary_sha256"),
                "authorization": copy.deepcopy(arg.get("historical_authorization")),
                "change_scope": copy.deepcopy(arg.get("historical_change_scope")),
                "note": arg.get("note") or "Résumé historique modifié uniquement dans la portée autorisée par le propriétaire, sans application rétroactive de la checklist de création.",
            }
            entries.append({"id": arg.get("id"), "languages": {"fr": language}})
            continue
        if status == "historical_existing":
            language = {
                "status": "historical_existing",
                "historical_content_preserved": True,
                "note": arg.get("note") or "Résumé historique conservé exactement sans réécriture stylistique rétroactive.",
            }
            entries.append({"id": arg.get("id"), "languages": {"fr": language}})
            continue
        attestations = arg.get("attestations") or {}
        language = {
            "status": status,
            "thesis_first": attestations.get("thesis_first") is True,
            "general_public_style": attestations.get("general_public_style") is True,
            "sentence_rhythm_reviewed": attestations.get("sentence_rhythm_reviewed") is True,
            "technical_terms_reviewed": attestations.get("technical_terms_reviewed") is True,
            "opening_develops_title": attestations.get("opening_develops_title") is True,
            "example_or_data_reviewed": attestations.get("example_or_data_reviewed") is True,
            "assertive_tone_reviewed": attestations.get("assertive_tone_reviewed") is True,
            "no_artificial_example_or_number": attestations.get("no_artificial_example_or_number") is True,
            "no_polemical_overstatement": attestations.get("no_polemical_overstatement") is True,
            "conviction_visible": attestations.get("conviction_visible") is True,
            "wikipedia_hover_links_reviewed": attestations.get("wikipedia_hover_links_reviewed") is True,
            "specialized_terms_linked_or_explained": attestations.get("specialized_terms_linked_or_explained") is True,
            "forceful_expression": arg.get("forceful_expression"),
            "originality_reviewed": True,
            "mechanism_statement": _mechanism_excerpt(arg.get("summary")),
            "quantitative_claims_verified": arg.get("quantitative_claims_verified"),
            "quantitative_claims_note": arg.get("quantitative_claims_note"),
            "note": arg.get("note"),
        }
        entries.append({"id": arg.get("id"), "languages": {"fr": language}})
    return {
        "schema_version": "1.0",
        "normative_revision": NORM_VERSION,
        "debate_id": debate_id,
        "entries": entries,
    }


def _build_content_copy(project_root: Path, source: Path, target: Path, review: Mapping[str, Any], debate_id: str, work_id: str) -> dict[str, Any]:
    shutil.copytree(source, target, symlinks=False, copy_function=shutil.copy2)
    final = copy.deepcopy(review["final_values"])

    # A review finalized before 2.16.22 may not carry the historical top-level
    # parameter-presence inventory in final_values.  Re-derive that evidence
    # from reviewed-copy, which is immutable and already provenance-checked, so
    # an old approved review can be reconstructed without changing its editorial
    # decisions or review hash.
    _, source_debate_presence, source_argument_presence_rows = _source_imports(source)
    if final["debate"].get("page_origin") == "preexisting":
        final["debate"]["source_parameter_presence"] = copy.deepcopy(
            source_debate_presence.get("source_parameter_presence") or {}
        )
    source_argument_presence = {
        str(row.get("id")): row
        for row in source_argument_presence_rows
        if isinstance(row, Mapping)
    }
    for argument in final["arguments"]:
        original = source_argument_presence.get(str(argument.get("id"))) or {}
        if (argument.get("citation_passages") or []) != (original.get("citation_passages") or []):
            raise ContentReviewError("Passages hors Citation non conservés ; reprendre la revue française : " + str(argument.get("id")))
        if argument.get("page_origin") != "preexisting":
            continue
        argument_id = str(argument.get("id"))
        source_row = source_argument_presence.get(argument_id)
        if source_row is None:
            raise ContentReviewError(
                f"Présence des paramètres source introuvable pour {argument_id}"
            )
        argument["source_parameter_presence"] = copy.deepcopy(
            source_row.get("source_parameter_presence") or {}
        )
    registry = load_json(target / "data/registre_debat.json", "registre du débat")
    classification = review.get("classification") or {}
    class_items = classification.get("final_values") or []
    class_by_id = {str(item.get("entity_id")): item for item in class_items if item.get("entity_type") == "argument"}
    class_debate = next((item for item in class_items if item.get("entity_type") == "debate"), None)
    active_ids = {str(node.get("id")) for node in ((registry.get("graph") or {}).get("nodes") or []) if node.get("status") == "active"}
    if set(class_by_id) != active_ids or class_debate is None:
        raise ContentReviewError("La classification finalisée ne couvre pas exactement le corpus actif")
    for node in ((registry.get("graph") or {}).get("nodes") or []):
        if node.get("status") != "active":
            continue
        item = class_by_id[str(node.get("id"))]
        fr = node.setdefault("fr", {})
        fr["rubriques"] = copy.deepcopy(item.get("rubriques") or [])
        fr["keywords"] = copy.deepcopy(item.get("keywords") or [])
    metadata_lock_path = target / "data/fr_page_metadata_lock.json"
    legacy_classification = bool((classification.get("summary") or {}).get("legacy_metadata_lock_reused"))
    if not legacy_classification:
        metadata_lock = load_json(metadata_lock_path, "verrou français des métadonnées")
        metadata_lock["status"] = "locked_for_generation"
        metadata_lock["classification_review_sha256"] = classification.get("review_sha256")
        metadata_lock["debate"] = copy.deepcopy(class_debate)
        metadata_lock["arguments"] = [copy.deepcopy(class_by_id[key]) for key in sorted(class_by_id)]
        write_json(metadata_lock_path, metadata_lock)
        vocabulary = {
            "schema": "wikidebia-keyword-vocabulary-1.0",
            "normative_revision": NORM_VERSION,
            "debate_id": debate_id,
            "status": "approved_fr",
            "language_status": "fr_locked_en_pending",
            "review_sha256": classification.get("review_sha256"),
            "entries": copy.deepcopy(classification.get("finalized_vocabulary") or []),
        }
        write_json(target / "data/keyword_vocabulary.json", vocabulary)
    by_id = {arg["id"]: arg for arg in final["arguments"]}
    for node in ((registry.get("graph") or {}).get("nodes") or []):
        if node.get("status") != "active":
            continue
        arg = by_id[str(node.get("id"))]
        node.setdefault("sources", {}).setdefault("fr", {})["bibliography"] = copy.deepcopy(arg["sources"]["bibliography"])
        node["sources"]["fr"]["webliography"] = copy.deepcopy(arg["sources"]["webliography"])
        node["sources"]["fr"]["videography"] = copy.deepcopy(arg["sources"]["videography"])
    sources_registry = {
        "source_registry_version": "1.0",
        "debate_id": debate_id,
        "sources": copy.deepcopy(final["sources"]),
    }
    timestamp = now_iso()
    authorization_source = source.parent / HISTORICAL_AUTHORIZATION_PATH
    authorization_receipt_sha256 = None
    authorization_receipt = None
    if authorization_source.is_file():
        authorization_receipt = load_json(authorization_source, "autorisation propriétaire des textes historiques")
        authorization_receipt_sha256 = sha256_bytes(authorization_source.read_bytes())
        authorization_target = target / HISTORICAL_AUTHORIZATION_PATH
        authorization_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(authorization_source, authorization_target)
    content_lock = {
        "schema": CONTENT_LOCK_SCHEMA,
        "schema_version": "1.1",
        "normative_revision": NORM_VERSION,
        "kit_version": KIT_VERSION,
        "debate_id": debate_id,
        "work_id": work_id,
        "language": "fr",
        "status": "locked_for_translation_and_generation",
        "review_sha256": review["review_sha256"],
        "source_registry_sha256": review["source_registry_sha256"],
        "applied_at": timestamp,
        "debate": copy.deepcopy(final["debate"]),
        "arguments": copy.deepcopy(final["arguments"]),
        "historical_text_decisions": {
            "policy": HISTORICAL_TEXT_POLICY,
            "authorization_receipt_path": HISTORICAL_AUTHORIZATION_PATH if authorization_receipt else None,
            "authorization_receipt_sha256": authorization_receipt_sha256,
            "debate": {
                "field_key": f"debate:{debate_id}:introduction",
                "page_origin": final["debate"].get("page_origin"),
                "historical_status": (
                    "historical_existing" if final["debate"].get("historical_introduction_present")
                    else "historical_absent"
                ) if final["debate"].get("page_origin") == "preexisting" else None,
                "historical_present": final["debate"].get("historical_introduction_present"),
                "historical_sha256": final["debate"].get("historical_introduction_sha256"),
                "final_present": bool(str(final["debate"].get("introduction") or "").strip()),
                "final_sha256": final["debate"].get("historical_final_introduction_sha256"),
                "decision": final["debate"].get("historical_text_decision"),
                "authorization": copy.deepcopy(final["debate"].get("historical_authorization")),
                "change_scope": copy.deepcopy(final["debate"].get("historical_change_scope")),
            },
            "arguments": [
                {
                    "id": arg.get("id"),
                    "field_key": f"argument:{arg.get('id')}:summary",
                    "page_origin": arg.get("page_origin"),
                    "historical_status": (
                        "historical_existing" if arg.get("historical_summary_present")
                        else "historical_absent"
                    ) if arg.get("page_origin") == "preexisting" else None,
                    "historical_present": arg.get("historical_summary_present"),
                    "historical_sha256": arg.get("historical_summary_sha256"),
                    "final_present": bool(str(arg.get("summary") or "").strip()),
                    "final_sha256": arg.get("historical_final_summary_sha256"),
                    "decision": arg.get("historical_text_decision"),
                    "authorization": copy.deepcopy(arg.get("historical_authorization")),
                    "change_scope": copy.deepcopy(arg.get("historical_change_scope")),
                }
                for arg in final["arguments"]
            ],
        },
    }
    operations: list[dict[str, Any]] = []
    source_debate = (review.get("debate") or {}).get("source") or {}
    for field, before, after in (
        ("subject", source_debate.get("subject"), final["debate"]["subject"]),
        ("complete_topic", source_debate.get("complete_topic"), final["debate"]["complete_topic"]),
        ("introduction", source_debate.get("introduction"), final["debate"]["introduction"]),
        ("wikipedia_articles", source_debate.get("wikipedia_articles"), final["debate"]["wikipedia_articles"]),
        ("documentation", None, final["debate"]["documentation"]),
    ):
        if before != after:
            operations.append({"entity_type": "debate", "entity_id": debate_id, "field": field, "before": before, "after": after})
    class_source_items = classification.get("source_items") or []
    # Classification changes are recorded against the title-checkpoint values.
    for item in class_items:
        entity_id = str(item.get("entity_id"))
        before = next((raw.get("source") for raw in class_source_items if str(raw.get("entity_id")) == entity_id), None)
        if before is None:
            # The source values are the rubriques/keywords carried by reviewed-copy.
            before = {}
        for field in ("rubriques", "keywords"):
            if before.get(field) != item.get(field):
                operations.append({"entity_type": item.get("entity_type"), "entity_id": entity_id, "field": field, "before": copy.deepcopy(before.get(field)), "after": copy.deepcopy(item.get(field))})
    source_arguments = {str(item.get("id")): (item.get("source") or {}) for item in review.get("arguments") or []}
    for arg in final["arguments"]:
        src = source_arguments[arg["id"]]
        before_summary = str(src.get("summary") or "")
        after_summary = str(arg.get("summary") or "")
        if before_summary != after_summary:
            operations.append({"entity_type": "argument", "entity_id": arg["id"], "field": "summary", "before": src.get("summary"), "after": arg["summary"]})
        operations.append({"entity_type": "argument", "entity_id": arg["id"], "field": "sources", "before": None, "after": copy.deepcopy(arg["sources"])})
    changeset = {
        "schema": CONTENT_CHANGESET_SCHEMA,
        "schema_version": "1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "status": "applied",
        "review_sha256": review["review_sha256"],
        "applied_at": timestamp,
        "operation_count": len(operations),
        "operations": operations,
        "source_imports_mutated": False,
        "metadata_lock_mutated": not legacy_classification,
        "final_pages_generated": False,
        "english_translation_started": False,
    }
    write_json(target / "data/registre_debat.json", registry)
    projection = load_json(target / "graph/graphe_argumentatif.json", "projection du graphe")
    projection["nodes"] = copy.deepcopy(((registry.get("graph") or {}).get("nodes") or []))
    write_json(target / "graph/graphe_argumentatif.json", projection)
    write_json(target / "data/sources.json", sources_registry)
    write_json(target / "data/fr_content_lock.json", content_lock)
    write_json(target / "changes/fr_content_changeset.json", changeset)
    write_json(target / "reviews/introduction_review.json", _introduction_review(final["debate"]))
    write_json(target / "reviews/summary_style_review.json", _summary_style_review(final["arguments"], debate_id))
    write_json(target / "reviews/fr/content_review.json", copy.deepcopy(review))
    classification_doc = {
        "schema": "wikidebia-fr-page-metadata-review-1.1",
        "schema_version": "1.1",
        "debate_id": debate_id,
        "work_id": work_id,
        "review_scope": "classification_and_content",
        "status": "approved",
        "review_sha256": classification.get("review_sha256"),
        "final_values": copy.deepcopy(class_items),
        "finalized_vocabulary": copy.deepcopy(classification.get("finalized_vocabulary") or []),
    }
    write_json(target / CLASSIFICATION_REVIEW_PATH, classification_doc)
    manifest = load_json(target / "manifest.json", "manifest.json")
    controls = manifest.setdefault("editorial_controls", {})
    controls["summary_style_review_path"] = "reviews/summary_style_review.json"
    controls["summary_style"] = {
        "enabled": True,
        "min_sentences": 2,
        "long_sentence_words": 35,
        "max_average_sentence_words": 30,
        "max_long_sentence_ratio": 0.5,
        "max_sentence_words": 60,
        "opening_title_similarity_enabled": True,
        "opening_similarity_threshold": 0.84,
        "opening_max_extra_significant_words": 4,
        "quantitative_claim_review_required": True,
    }
    required_reports = controls.setdefault("required_reports", [])
    for rel in ("reports/fr_content_preflight.json", "reports/fr_content_validation.json"):
        if rel not in required_reports:
            required_reports.append(rel)
    manifest["updated_at"] = timestamp
    write_json(target / "manifest.json", manifest)
    preflight = _run_validator(
        project_root, target, scopes=("schema", "coherence", "graph", "files"),
        json_output=target / "reports/fr_content_preflight.json",
        text_output=target / "reports/fr_content_preflight.txt",
    )
    final_validation = _run_validator(
        project_root, target, scopes=("schema", "coherence", "graph", "files", "workflow"),
        json_output=target / "reports/fr_content_validation.json",
        text_output=target / "reports/fr_content_validation.txt",
    )
    return {
        "content_lock": content_lock,
        "changeset": changeset,
        "validator_result": final_validation.get("result"),
        "preflight_result": preflight.get("result"),
    }


def apply_review(project_root: Path, debate_id: str, work_id: str, confirm_review_sha256: str) -> dict[str, Any]:
    workspace, meta = _load_workspace(project_root, debate_id, work_id)
    if meta.get("status") not in {"fr_content_review_finalized", "fr_content_applied"}:
        raise ContentReviewError(f"Statut incompatible avec l’application du contenu : {meta.get('status')}")
    _assert_source_unchanged(project_root, debate_id, meta)
    reviewed = _assert_reviewed_copy(workspace, meta)
    review = load_json(workspace / "reviews/fr/content_review.json", "revue de contenu")
    if review.get("status") != "approved" or review.get("review_sha256") != content_review_sha256(review):
        raise ContentReviewError("La revue de contenu n’est pas finalisée ou son empreinte est invalide")
    if confirm_review_sha256 != review.get("review_sha256"):
        raise ContentReviewError("L’empreinte confirmée ne correspond pas à la revue de contenu")
    if review.get("prepared_reviewed_copy_sha256") != full_tree_sha256(reviewed):
        raise ContentReviewError("reviewed-copy a changé depuis la finalisation")
    target = workspace / "content-reviewed-copy"
    if target.is_dir():
        if meta.get("status") != "fr_content_applied":
            raise ContentReviewError("content-reviewed-copy existe sans état cohérent")
        expected = str((meta.get("content_reviewed_copy") or {}).get("tree_sha256") or "")
        actual = full_tree_sha256(target)
        if actual != expected:
            raise ContentReviewError("Empreinte de content-reviewed-copy divergente")

        existing_lock = load_json(
            target / "data/fr_content_lock.json",
            "verrou français du contenu",
        )

        def presence_complete(row: Mapping[str, Any], page_type: str) -> bool:
            if row.get("page_origin") != "preexisting":
                return True
            states = row.get("source_parameter_presence")
            if not isinstance(states, Mapping):
                return False
            return all(
                isinstance(states.get(name), Mapping)
                and isinstance(states[name].get("present"), bool)
                for name in PAGE_EDITORIAL_PARAMETERS[page_type]
            )

        needs_presence_migration = (
            not presence_complete(existing_lock.get("debate") or {}, "debate")
            or any(
                not presence_complete(row, "argument")
                for row in (existing_lock.get("arguments") or [])
                if isinstance(row, Mapping)
            )
        )
        if not needs_presence_migration:
            return {
                "status": "fr_content_applied",
                "debate_id": debate_id,
                "work_id": work_id,
                "review_sha256": review["review_sha256"],
                "content_reviewed_copy_tree_sha256": actual,
                "idempotent": True,
            }

        content_stage = (
            project_root / ".state" / "fr-publication" / debate_id / work_id / "content"
        )
        if content_stage.exists():
            raise ContentReviewError(
                "Migration de source_parameter_presence refusée : un état de checkpoint "
                "français content existe déjà; le workflow doit d'abord le reprendre ou "
                "le restaurer transactionnellement"
            )

        # content-reviewed-copy is a deterministic local derivative.  Before any
        # content checkpoint state exists it is safe to rebuild it under the
        # current kit from reviewed-copy + the exact approved review.
        shutil.rmtree(target)
    if target.exists() or target.is_symlink():
        raise ContentReviewError("Chemin content-reviewed-copy déjà occupé")
    temp = Path(tempfile.mkdtemp(prefix=".content-reviewed-copy.tmp-", dir=workspace))
    try:
        shutil.rmtree(temp)
        result = _build_content_copy(project_root, reviewed, temp, review, debate_id, work_id)
        if full_tree_sha256(temp / "imports") != full_tree_sha256(reviewed / "imports"):
            raise ContentReviewError("Les imports ont été modifiés pendant l’application du contenu")
        legacy_classification = bool((((review.get("classification") or {}).get("summary") or {}).get("legacy_metadata_lock_reused")))
        if legacy_classification and (temp / "data/fr_page_metadata_lock.json").read_bytes() != (reviewed / "data/fr_page_metadata_lock.json").read_bytes():
            raise ContentReviewError("Le verrou de métadonnées françaises historique a été modifié")
        tree_hash = full_tree_sha256(temp)
        os.replace(temp, target)
        fsync_directory(workspace)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    applied_at = result["content_lock"]["applied_at"]
    translation_path = workspace / "reviews/en/translation_readiness.json"
    if translation_path.is_file():
        translation = load_json(translation_path, "préparation anglaise")
        translation["status"] = "ready_for_translation"
        translation["french_content_locked_at"] = applied_at
        translation["french_content_review_sha256"] = review["review_sha256"]
        for item in translation.get("items") or []:
            item["translation_status"] = "ready_for_translation"
            item["french_content_review_status"] = "locked"
        write_json(translation_path, translation)
    meta = copy.deepcopy(meta)
    meta["kit_version"] = KIT_VERSION
    meta["status"] = "fr_content_applied"
    meta["content_reviewed_copy"] = {
        "path": "content-reviewed-copy",
        "tree_sha256": tree_hash,
        "status": "fr_content_locked",
        "review_sha256": review["review_sha256"],
        "applied_at": applied_at,
    }
    meta["french_content_review"]["status"] = "applied"
    meta["french_content_review"]["applied_at"] = applied_at
    meta["boundaries"]["final_pages_generated"] = False
    meta["boundaries"]["english_translation_started"] = False
    meta["workspace_sha256"] = None
    meta["workspace_sha256"] = workspace_receipt_hash(meta)
    write_json(workspace / "workspace.json", meta)
    return {
        "status": "fr_content_applied",
        "debate_id": debate_id,
        "work_id": work_id,
        "review_sha256": review["review_sha256"],
        "content_reviewed_copy": relative_to_project(target, project_root),
        "content_reviewed_copy_tree_sha256": tree_hash,
        "sources": len(review["final_values"]["sources"]),
        "arguments": len(review["final_values"]["arguments"]),
        "source_corpus_mutated": False,
        "working_copy_mutated": False,
        "reviewed_copy_mutated": False,
        "imports_mutated": False,
        "metadata_lock_mutated": False,
        "final_pages_generated": False,
        "english_translation_started": False,
        "translation_readiness": "ready_for_translation",
        "validator_result": result["validator_result"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Préparer, finaliser ou appliquer la revue du contenu français.")
    parser.add_argument("debate_id")
    parser.add_argument("--work-id", required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--finalize", action="store_true")
    action.add_argument("--apply", action="store_true")
    parser.add_argument("--overwrite-review", action="store_true")
    parser.add_argument("--confirm-review-sha256")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--machine-readable", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = args.project_root.expanduser().resolve()
    work_id = validate_work_id(args.work_id)
    if args.apply and not args.confirm_review_sha256:
        raise ContentReviewError("--confirm-review-sha256 est obligatoire avec --apply")
    with exclusive_lock(project_root, args.debate_id, "editorial_content_review"):
        if args.prepare:
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
    except (ContentReviewError, EditorialReviewError, WorkspaceError, CorpusBuildError) as exc:
        print(f"WIKIDEBIA BLOQUÉ : {exc}", file=__import__("sys").stderr)
        raise SystemExit(2)
