#!/usr/bin/env python3
"""Create a traceable editorial workspace from a promoted graph corpus.

This phase is deliberately non-mutating with respect to ``corpus/<debate_id>``.
It creates a complete working copy below ``.state/editorial-workspaces`` and
prepares human-review ledgers for French titles, classifications, keywords and
future English translation. Automated checks only open tasks; they never apply
editorial corrections or generate final MediaWiki pages.
"""

from __future__ import annotations

from wikidebia_release_info import KIT_VERSION
from wikidebia_keyword_policy import keyword_identity_fr, lowercase_keyword_initial
from wikidebia_title_structure import split_title_ligatures

import argparse
import collections
import datetime as dt
import json
import os
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from wikidebia_corpus_build import (
    NORM_VERSION,
    VALIDATOR_VERSION,
    CorpusBuildError,
    assert_control_directory,
    assert_graph_validated_without_final_pages,
    assert_no_symlinks,
    canonical_json,
    exclusive_lock,
    full_tree_sha256,
    load_json,
    now_iso,
    relative_to_project,
    resolve_active_corpus,
    sha256_bytes,
    sha256_file,
    validate_debate_id,
    write_json,
)
from wikidebia_corpus_init import RUBRIQUES, extract_page_metadata
from wikidebia_graph_extract import (
    ARGUMENT_TEMPLATE_KEYS,
    DEBATE_TEMPLATE_KEYS,
    _find_outer,
    iter_templates,
    normalize_key,
)

WORKSPACE_SCHEMA = "wikidebia-editorial-workspace-1.0"
AUDIT_SCHEMA = "wikidebia-editorial-audit-1.0"
TASK_SCHEMA = "wikidebia-editorial-task-ledger-1.0"
REVIEW_SCHEMA = "wikidebia-fr-page-metadata-review-1.0"
TRANSLATION_SCHEMA = "wikidebia-translation-readiness-review-1.0"
CHANGESET_SCHEMA = "wikidebia-editorial-changeset-1.0"

TYPOGRAPHIC_QUOTES = set("«»“”„‹›")
ELLIPSES = ("...", "…")
CONTEXT_DEPENDENT_STARTS = (
    "ce ", "cet ", "cette ", "ces ", "celui-ci ", "celle-ci ", "ceux-ci ",
    "celles-ci ", "il ", "elle ", "ils ", "elles ",
)
TRAILING_CONNECTORS = {
    "à", "au", "aux", "avec", "car", "chez", "comme", "contre", "dans", "de",
    "des", "du", "en", "entre", "et", "mais", "ou", "par", "pour", "que", "qui",
    "sans", "selon", "si", "sous", "sur", "vers",
}
# Conservative list used only for a human-review signal, never for acceptance.
COMMON_FINITE_VERBS = {
    "a", "agit", "améliore", "affaiblit", "autorise", "bloque", "cause", "conduit",
    "confirme", "constitue", "contredit", "crée", "dépend", "démontre", "devient",
    "doit", "empêche", "entraîne", "est", "exclut", "exige", "explique", "favorise",
    "garantit", "implique", "indique", "interdit", "justifie", "limite", "menace",
    "montre", "nuit", "permet", "peut", "prouve", "réduit", "rend", "renforce",
    "reste", "révèle", "soutient", "suppose", "viole", "sont", "ont", "font",
}


class WorkspaceError(CorpusBuildError):
    pass


def normalized_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def normalized_identity(value: Any) -> str:
    return normalized_text(value).casefold()


def token_words(value: str) -> list[str]:
    return re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9]+(?:['’-][A-Za-zÀ-ÖØ-öø-ÿ0-9]+)?", value)


def title_diagnostics(canonical: str, displayed: str, *, enforce_creation_form: bool = True) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    canonical = str(canonical or "")
    displayed = str(displayed or "")
    if not canonical.strip():
        issues.append({"code": "TITLE_CANONICAL_MISSING", "severity": "blocking", "field": "canonical_title"})
    else:
        if canonical != normalized_text(canonical):
            issues.append({"code": "TITLE_CANONICAL_SPACING", "severity": "correction", "field": "canonical_title"})
        if canonical.rstrip().endswith("."):
            issues.append({"code": "TITLE_CANONICAL_TRAILING_PERIOD", "severity": "correction", "field": "canonical_title"})
        if any(char in canonical for char in TYPOGRAPHIC_QUOTES):
            issues.append({"code": "TITLE_CANONICAL_NON_ASCII_QUOTES", "severity": "correction", "field": "canonical_title"})
        if any(mark in canonical for mark in ELLIPSES):
            issues.append({"code": "TITLE_CANONICAL_ELLIPSIS", "severity": "blocking", "field": "canonical_title"})
        if canonical.casefold().startswith(CONTEXT_DEPENDENT_STARTS):
            issues.append({"code": "TITLE_CANONICAL_POSSIBLE_CONTEXT_DEPENDENCY", "severity": "review", "field": "canonical_title"})
        if split_title_ligatures(canonical) != canonical:
            issues.append({"code": "TITLE_CANONICAL_OE_LIGATURE", "severity": "blocking", "field": "canonical_title"})
    if not displayed.strip():
        issues.append({"code": "TITLE_DISPLAYED_MISSING", "severity": "blocking", "field": "displayed_title"})
    else:
        if displayed != normalized_text(displayed):
            issues.append({"code": "TITLE_DISPLAYED_SPACING", "severity": "correction", "field": "displayed_title"})
        if displayed.rstrip().endswith("."):
            issues.append({"code": "TITLE_DISPLAYED_TRAILING_PERIOD", "severity": "correction", "field": "displayed_title"})
        if any(char in displayed for char in TYPOGRAPHIC_QUOTES):
            issues.append({"code": "TITLE_DISPLAYED_NON_ASCII_QUOTES", "severity": "correction", "field": "displayed_title"})
        if any(mark in displayed for mark in ELLIPSES):
            issues.append({"code": "TITLE_DISPLAYED_ELLIPSIS", "severity": "blocking", "field": "displayed_title"})
        if split_title_ligatures(displayed) != displayed:
            issues.append({"code": "TITLE_DISPLAYED_OE_LIGATURE", "severity": "blocking", "field": "displayed_title"})
        words = token_words(displayed)
        if words and words[-1].casefold() in TRAILING_CONNECTORS:
            issues.append({"code": "TITLE_DISPLAYED_TRAILING_CONNECTOR", "severity": "blocking", "field": "displayed_title"})
        lower_tokens = {word.casefold().replace("’", "'") for word in words}
        if enforce_creation_form and words and not (lower_tokens & COMMON_FINITE_VERBS):
            issues.append({
                "code": "TITLE_DISPLAYED_PROPOSITIONALITY_REVIEW",
                "severity": "review",
                "field": "displayed_title",
                "heuristic": True,
            })
    return issues


def rubrique_diagnostics(values: Iterable[str], fallback: bool, *, enforce_creation_count: bool = True) -> list[dict[str, Any]]:
    rows = [normalized_text(value) for value in values if normalized_text(value)]
    issues: list[dict[str, Any]] = []
    if not rows:
        issues.append({"code": "RUBRIQUES_MISSING", "severity": "blocking", "field": "rubriques"})
    invalid = [value for value in rows if value not in RUBRIQUES]
    if invalid:
        issues.append({"code": "RUBRIQUES_INVALID", "severity": "blocking", "field": "rubriques", "values": invalid})
    if len(rows) != len(set(rows)):
        issues.append({"code": "RUBRIQUES_DUPLICATE", "severity": "correction", "field": "rubriques"})
    if rows != sorted(rows, key=_alphabetical_key):
        issues.append({"code": "RUBRIQUES_NOT_ALPHABETICAL", "severity": "correction", "field": "rubriques"})
    if enforce_creation_count and len(rows) > 4:
        issues.append({"code": "RUBRIQUES_TOO_MANY", "severity": "blocking", "field": "rubriques", "count": len(rows)})
    elif enforce_creation_count and len(rows) == 4:
        issues.append({"code": "RUBRIQUES_FOUR_REQUIRE_JUSTIFICATION", "severity": "review", "field": "rubriques"})
    if fallback:
        issues.append({"code": "RUBRIQUES_IMPORTED_FALLBACK", "severity": "review", "field": "rubriques"})
    return issues


def _alphabetical_key(value: str) -> str:
    folded = unicodedata.normalize("NFKD", str(value).casefold())
    return "".join(char for char in folded if not unicodedata.combining(char))


def first_alphabetic(value: str) -> str:
    return next((char for char in str(value) if char.isalpha()), "")


def capitalization_policy_for_kind(kind: str) -> str | None:
    return {
        "noun": "lowercase_common",
        "noun_phrase": "lowercase_common",
        "proper_name": "canonical_proper_name",
        "acronym": "canonical_acronym",
    }.get(kind)


def keyword_capitalization_issues(value: str, kind: str) -> list[str]:
    first = first_alphabetic(value)
    if kind in {"noun", "noun_phrase"} and first and first.isupper():
        return ["common_keyword_initial_uppercase"]
    if kind == "acronym":
        letters = [char for char in value if char.isalpha()]
        if not letters or any(char.islower() for char in letters):
            return ["acronym_not_uppercase"]
    return []


def keyword_diagnostics(values: Iterable[str], fallback: bool, entity_type: str = "argument") -> list[dict[str, Any]]:
    rows = [normalized_text(value) for value in values if normalized_text(value)]
    issues: list[dict[str, Any]] = []
    minimum, maximum = (5, 8) if entity_type == "debate" else (2, 4)
    if len(rows) < minimum:
        issues.append({"code": "KEYWORDS_TOO_FEW", "severity": "correction", "field": "keywords", "count": len(rows), "minimum": minimum})
    if len(rows) > maximum:
        issues.append({"code": "KEYWORDS_TOO_MANY", "severity": "correction", "field": "keywords", "count": len(rows), "maximum": maximum})
    keyword_identities = {keyword_identity_fr(value) for value in rows}
    if len(rows) != len(keyword_identities):
        issues.append({"code": "KEYWORDS_DUPLICATE", "severity": "correction", "field": "keywords"})
    long_values = [value for value in rows if len(value) > 40]
    if long_values:
        issues.append({"code": "KEYWORDS_TOO_LONG", "severity": "review", "field": "keywords", "values": long_values})
    verbose_values = [value for value in rows if len(token_words(value)) > 4]
    if verbose_values:
        issues.append({"code": "KEYWORDS_TOO_MANY_WORDS", "severity": "review", "field": "keywords", "values": verbose_values})
    sentence_values = [value for value in rows if value.endswith((".", "!", "?", ";", ":"))]
    if sentence_values:
        issues.append({"code": "KEYWORDS_SENTENCE_LIKE", "severity": "correction", "field": "keywords", "values": sentence_values})
    uppercase_values = [value for value in rows if first_alphabetic(value) and first_alphabetic(value).isupper()]
    if uppercase_values:
        issues.append({"code": "KEYWORDS_CAPITALIZATION_REVIEW", "severity": "review", "field": "keywords", "values": uppercase_values})
    if fallback:
        issues.append({"code": "KEYWORDS_IMPORTED_FALLBACK", "severity": "review", "field": "keywords"})
    return issues


def read_import_metadata(working_copy: Path, row: Mapping[str, Any]) -> dict[str, Any]:
    relative = str(row.get("import_path") or "")
    if not relative:
        raise WorkspaceError("Une page importée ne déclare pas import_path")
    path = working_copy / relative
    if not path.is_file():
        raise WorkspaceError(f"Page importée absente dans la copie de travail : {relative}")
    if row.get("sha256") and sha256_file(path) != row.get("sha256"):
        raise WorkspaceError(f"Empreinte de provenance divergente : {relative}")
    text = path.read_text(encoding="utf-8")
    is_debate = row.get("kind") == "debate"
    metadata = extract_page_metadata(text, debate=is_debate)
    calls = iter_templates(text)
    outer = _find_outer(calls, DEBATE_TEMPLATE_KEYS if is_debate else ARGUMENT_TEMPLATE_KEYS)
    if outer is None:
        raise WorkspaceError(f"Modèle principal introuvable : {relative}")
    parameters = []
    empty_parameters = []
    for key, value in outer.params.items():
        normalized = normalize_key(key)
        parameters.append(normalized)
        if not str(value).strip():
            empty_parameters.append(normalized)
    return {
        **metadata,
        "parameters_present": sorted(set(parameters)),
        "empty_parameters": sorted(set(empty_parameters)),
        "source_size_bytes": path.stat().st_size,
        "source_sha256": sha256_file(path),
    }


def fallback_map(provenance: Mapping[str, Any]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = collections.defaultdict(set)
    for row in provenance.get("normalizations") or []:
        if not isinstance(row, dict):
            continue
        title = normalized_text(row.get("registry_title") or row.get("source_title"))
        for item in row.get("metadata_fallbacks") or []:
            kind, _, _ = str(item).partition(":")
            if kind:
                result[title].add(kind)
    return result


def issue_summary(issues: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = collections.Counter(str(issue.get("severity") or "unknown") for issue in issues)
    return dict(sorted(counts.items()))


def page_review_item(
    *,
    entity_type: str,
    entity_id: str,
    canonical_title: str,
    displayed_title: str | None,
    rubriques: list[str],
    keywords: list[str],
    import_row: Mapping[str, Any],
    import_metadata: Mapping[str, Any],
    fallback_kinds: set[str],
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    if entity_type == "argument":
        issues.extend(title_diagnostics(canonical_title, displayed_title or "", enforce_creation_form=False))
    elif split_title_ligatures(canonical_title) != canonical_title:
        issues.append({"code": "TITLE_CANONICAL_OE_LIGATURE", "severity": "blocking", "field": "canonical_title"})
    issues.extend(rubrique_diagnostics(rubriques, "rubrique" in fallback_kinds, enforce_creation_count=False))
    issues.extend(keyword_diagnostics(keywords, "mot-clé" in fallback_kinds, entity_type))
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "source": {
            "canonical_title": canonical_title,
            "displayed_title": displayed_title,
            "rubriques": rubriques,
            "keywords": keywords,
            "import_path": import_row.get("import_path"),
            "revision_id": import_row.get("revision_id"),
            "revision_timestamp": import_row.get("revision_timestamp"),
            "source_sha256": import_metadata.get("source_sha256"),
            "parameters_present": import_metadata.get("parameters_present"),
            "empty_parameters": import_metadata.get("empty_parameters"),
            "metadata_fallbacks": sorted(fallback_kinds),
            "page_origin": "preexisting",
        },
        "diagnostics": issues,
        "diagnostic_summary": issue_summary(issues),
        "review": {
            "status": "pending",
            "canonical_title_decision": "pending" if entity_type == "argument" or split_title_ligatures(canonical_title) != canonical_title else "not_applicable",
            "proposed_canonical_title": None,
            "canonical_title_rationale": "",
            "displayed_title_decision": "keep" if entity_type == "argument" else "not_applicable",
            "proposed_displayed_title": displayed_title,
            "displayed_title_rationale": "",
            "rubriques_decision": "pending",
            "proposed_rubriques": [],
            "rubriques_rationales": {},
            "keywords_decision": "pending",
            "proposed_keywords": [],
            "keywords_rationales": {},
            "keywords_ordered_by_relevance": False,
            "keyword_order_rationale": "",
            "canonical_referents_explicit": False if entity_type == "argument" else None,
            "displayed_title_complete_proposition": False if entity_type == "argument" else None,
            "displayed_title_argument_intelligible": False if entity_type == "argument" else None,
            "displayed_title_concision_reviewed": False if entity_type == "argument" else None,
            "displayed_title_semantically_equivalent": False if entity_type == "argument" else None,
            "displayed_title_improves_readability_when_distinct": False if entity_type == "argument" else None,
            "displayed_title_identity_justification": "",
            "fourth_rubrique_exception_rationale": "",
            "preexisting_rubrique_change_rationale": "",
            "preexisting_keyword_corrections": {},
            "removed_preexisting_keywords": {},
            "reviewer": "",
            "reviewed_at": None,
            "notes": "",
        },
    }


def make_tasks(items: Sequence[Mapping[str, Any]], debate_id: str, work_id: str) -> dict[str, Any]:
    tasks: list[dict[str, Any]] = []
    serial = 0
    for item in items:
        grouped: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
        for issue in item.get("diagnostics") or []:
            field = str(issue.get("field") or "general")
            area = "titles" if field in {"canonical_title", "displayed_title"} else field
            grouped[area].append(dict(issue))
        mandatory_areas = ["rubriques", "keywords"]
        if item.get("entity_type") == "argument":
            mandatory_areas.insert(0, "titles")
        for area in mandatory_areas:
            serial += 1
            area_issues = grouped.get(area, [])
            tasks.append({
                "task_id": f"T{serial:05d}",
                "entity_type": item.get("entity_type"),
                "entity_id": item.get("entity_id"),
                "area": area,
                "status": "open",
                "priority": "blocking" if any(row.get("severity") == "blocking" for row in area_issues) else ("correction" if area_issues else "review"),
                "issue_codes": [row.get("code") for row in area_issues],
                "review_path": "reviews/fr/page_metadata_review.json",
                "dependencies": [],
                "assignee": None,
                "completed_at": None,
            })
    serial += 1
    tasks.append({
        "task_id": f"T{serial:05d}",
        "entity_type": "corpus",
        "entity_id": debate_id,
        "area": "keyword_vocabulary",
        "status": "open",
        "priority": "review",
        "issue_codes": ["KEYWORD_VOCABULARY_REBUILD_REQUIRED"],
        "review_path": "data/keyword_vocabulary_working.json",
        "dependencies": [task["task_id"] for task in tasks if task["area"] == "keywords"],
        "assignee": None,
        "completed_at": None,
    })
    serial += 1
    tasks.append({
        "task_id": f"T{serial:05d}",
        "entity_type": "corpus",
        "entity_id": debate_id,
        "area": "english_translation_readiness",
        "status": "blocked_by_french_review",
        "priority": "review",
        "issue_codes": ["ENGLISH_TRANSLATION_AFTER_FRENCH_LOCK"],
        "review_path": "reviews/en/translation_readiness.json",
        "dependencies": [task["task_id"] for task in tasks if task["area"] in {"titles", "rubriques", "keywords"}],
        "assignee": None,
        "completed_at": None,
    })
    counts = collections.Counter(task["status"] for task in tasks)
    return {
        "schema": TASK_SCHEMA,
        "schema_version": "1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "generated_at": now_iso(),
        "counts": dict(sorted(counts.items())),
        "tasks": tasks,
    }


def keyword_vocabulary_working(items: Sequence[Mapping[str, Any]], debate_id: str, work_id: str) -> dict[str, Any]:
    usage: dict[str, list[dict[str, str]]] = collections.defaultdict(list)
    original_forms: dict[str, str] = {}
    for item in items:
        for keyword in item.get("source", {}).get("keywords") or []:
            normalized = normalized_identity(keyword)
            if not normalized:
                continue
            original_forms.setdefault(normalized, str(keyword))
            usage[normalized].append({
                "entity_type": str(item.get("entity_type")),
                "entity_id": str(item.get("entity_id")),
            })
    entries = []
    for normalized in sorted(usage):
        term = original_forms[normalized]
        multiword = len(token_words(term)) > 1
        entries.append({
            "fr": term,
            "en": None,
            "definition": "",
            "kind": None,
            "capitalization_policy": None,
            "capitalization_rationale": "",
            "atomic_concept": None if multiword else True,
            "compositional_intersection": None if multiword else False,
            "multiword_exception": None if multiword else False,
            "multiword_exception_rationale": "",
            "status": "pending_review",
            "usages": usage[normalized],
            "decision": "pending",
            "rationale": "",
        })
    return {
        "schema": "wikidebia-keyword-vocabulary-working-1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "status": "draft",
        "entries": entries,
    }


def translation_readiness(items: Sequence[Mapping[str, Any]], registry: Mapping[str, Any], debate_id: str, work_id: str) -> dict[str, Any]:
    nodes = {str(node.get("id")): node for node in (registry.get("graph") or {}).get("nodes") or [] if node.get("status") == "active"}
    rows = []
    for item in items:
        if item.get("entity_type") == "debate":
            en = (((registry.get("debate") or {}).get("pages") or {}).get("en") or {})
        else:
            en = (nodes.get(str(item.get("entity_id"))) or {}).get("en") or {}
        rows.append({
            "entity_type": item.get("entity_type"),
            "entity_id": item.get("entity_id"),
            "french_metadata_review_status": "pending",
            "english_canonical_title": en.get("canonical_title"),
            "english_displayed_title": en.get("displayed_title"),
            "english_sections": en.get("sections", []),
            "english_keywords": en.get("keywords", []),
            "translation_status": "blocked_by_french_review",
            "equivalence_review_status": "not_started",
            "notes": "",
        })
    return {
        "schema": TRANSLATION_SCHEMA,
        "schema_version": "1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "source_language": "fr",
        "target_language": "en",
        "policy": "La traduction ne commence qu'après validation et verrouillage des métadonnées françaises.",
        "items": rows,
    }


def build_audit(working_copy: Path, debate_id: str, work_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest, registry, _ = assert_graph_validated_without_final_pages(working_copy)
    provenance = load_json(working_copy / "data" / "import_provenance.json", "provenance d'import")
    fallback_by_title = fallback_map(provenance)
    page_rows = provenance.get("pages") or []
    if not isinstance(page_rows, list):
        raise WorkspaceError("data/import_provenance.json: pages doit être une liste")
    debate_rows = [row for row in page_rows if isinstance(row, dict) and row.get("kind") == "debate"]
    if len(debate_rows) != 1:
        raise WorkspaceError(f"Une page Débat importée est requise, trouvée : {len(debate_rows)}")
    argument_rows = {
        str(row.get("page_id")): row for row in page_rows
        if isinstance(row, dict) and row.get("kind") == "argument" and row.get("page_id")
    }
    items: list[dict[str, Any]] = []
    debate_row = debate_rows[0]
    debate_import = read_import_metadata(working_copy, debate_row)
    debate_title = str((((registry.get("debate") or {}).get("pages") or {}).get("fr") or {}).get("canonical_title") or debate_row.get("canonical_title") or "")
    items.append(page_review_item(
        entity_type="debate",
        entity_id="debate",
        canonical_title=debate_title,
        displayed_title=None,
        rubriques=list(debate_import.get("rubriques") or []),
        keywords=list(debate_import.get("keywords") or []),
        import_row=debate_row,
        import_metadata=debate_import,
        fallback_kinds=fallback_by_title.get(debate_title, set()),
    ))
    active_nodes = [node for node in (registry.get("graph") or {}).get("nodes") or [] if node.get("status") == "active"]
    for node in sorted(active_nodes, key=lambda row: str(row.get("id"))):
        node_id = str(node.get("id"))
        import_row = argument_rows.get(node_id)
        if import_row is None:
            raise WorkspaceError(f"Provenance importée absente pour le nœud {node_id}")
        import_metadata = read_import_metadata(working_copy, import_row)
        fr = node.get("fr") or {}
        title = str(fr.get("canonical_title") or "")
        items.append(page_review_item(
            entity_type="argument",
            entity_id=node_id,
            canonical_title=title,
            displayed_title=str(fr.get("displayed_title") or ""),
            rubriques=list(fr.get("rubriques") or []),
            keywords=list(fr.get("keywords") or []),
            import_row=import_row,
            import_metadata=import_metadata,
            fallback_kinds=fallback_by_title.get(title, set()),
        ))
    all_issues = [issue for item in items for issue in item["diagnostics"]]
    argument_items = [item for item in items if item["entity_type"] == "argument"]
    identical = sum(
        normalized_identity(item["source"]["canonical_title"]) == normalized_identity(item["source"]["displayed_title"])
        for item in argument_items
    )
    exact_keyword_sets = collections.Counter(
        tuple(sorted(normalized_identity(value) for value in item["source"]["keywords"]))
        for item in argument_items if item["source"]["keywords"]
    )
    dominant_set_count = max(exact_keyword_sets.values(), default=0)
    corpus_issues: list[dict[str, Any]] = []
    identity_ratio = (identical / len(argument_items)) if argument_items else 0.0
    dominant_ratio = (dominant_set_count / len(argument_items)) if argument_items else 0.0
    if dominant_ratio > 0.25:
        corpus_issues.append({
            "code": "DOMINANT_EXACT_KEYWORD_SET_OVER_25_PERCENT",
            "severity": "blocking",
            "count": dominant_set_count,
            "total": len(argument_items),
            "ratio": round(dominant_ratio, 6),
        })
    all_issues.extend(corpus_issues)
    audit = {
        "schema": AUDIT_SCHEMA,
        "schema_version": "1.0",
        "normative_revision": NORM_VERSION,
        "validator_version": VALIDATOR_VERSION,
        "kit_version": KIT_VERSION,
        "debate_id": debate_id,
        "work_id": work_id,
        "generated_at": now_iso(),
        "source_global_status": manifest.get("global_status"),
        "scope": {
            "automatic_checks": ["titles", "rubriques", "keywords", "import_provenance", "translation_readiness"],
            "automatic_corrections_applied": False,
            "final_pages_generated": False,
            "remote_access": False,
        },
        "counts": {
            "pages": len(items),
            "debate_pages": 1,
            "argument_pages": len(argument_items),
            "issues": len(all_issues),
            "issues_by_severity": issue_summary(all_issues),
            "displayed_title_identity_count": identical,
            "displayed_title_identity_ratio": round(identity_ratio, 6),
            "dominant_keyword_set_count": dominant_set_count,
            "dominant_keyword_set_ratio": round(dominant_ratio, 6),
        },
        "corpus_diagnostics": corpus_issues,
        "items": items,
        "limitations": [
            "Les diagnostics de propositionnalité et d'autonomie des titres sont heuristiques et exigent une revue humaine.",
            "La pertinence sémantique des rubriques et mots-clés ne peut pas être décidée automatiquement.",
            "Aucune traduction anglaise et aucun wikicode final ne sont produits dans cette phase.",
        ],
    }
    return audit, items


def audit_markdown(audit: Mapping[str, Any]) -> str:
    counts = audit.get("counts") or {}
    lines = [
        f"# Inventaire éditorial — {audit.get('debate_id')}",
        "",
        f"Work : `{audit.get('work_id')}`",
        "",
        "Ce rapport ouvre des tâches de revue. Il n'applique aucune correction et ne génère aucune page finale.",
        "",
        f"- Pages examinées : {counts.get('pages', 0)}",
        f"- Pages Argument : {counts.get('argument_pages', 0)}",
        f"- Diagnostics : {counts.get('issues', 0)}",
        f"- Titres affichés identiques : {counts.get('displayed_title_identity_count', 0)} ({counts.get('displayed_title_identity_ratio', 0):.1%})",
        f"- Jeu exact de mots-clés dominant : {counts.get('dominant_keyword_set_count', 0)} ({counts.get('dominant_keyword_set_ratio', 0):.1%})",
        "",
        "## Pages",
        "",
    ]
    for item in audit.get("items") or []:
        title = item.get("source", {}).get("canonical_title") or item.get("entity_id")
        codes = [issue.get("code") for issue in item.get("diagnostics") or []]
        lines.append(f"- `{item.get('entity_id')}` — {title} : {', '.join(codes) if codes else 'revue obligatoire sans anomalie automatique'}")
    lines.extend(["", "## Limites", ""])
    for row in audit.get("limitations") or []:
        lines.append(f"- {row}")
    return "\n".join(lines) + "\n"


def next_work_id(base: Path) -> str:
    date = dt.date.today().strftime("%Y%m%d")
    pattern = re.compile(rf"^EDIT-{date}-(\d{{3}})$")
    numbers = []
    if base.is_dir():
        for path in base.iterdir():
            match = pattern.fullmatch(path.name)
            if match:
                numbers.append(int(match.group(1)))
    return f"EDIT-{date}-{max(numbers, default=0) + 1:03d}"


def validate_work_id(value: str) -> str:
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{2,63}", value):
        raise WorkspaceError("work_id invalide; utiliser 3 à 64 caractères A-Z, 0-9, _ ou -")
    return value


def fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def workspace_receipt_hash(value: Mapping[str, Any]) -> str:
    body = dict(value)
    body.pop("workspace_sha256", None)
    return sha256_bytes(canonical_json(body))


def create_workspace(project_root: Path, debate_id: str, work_id: str | None = None) -> dict[str, Any]:
    debate_id = validate_debate_id(debate_id)
    source = resolve_active_corpus(project_root, debate_id)
    source_tree_before = full_tree_sha256(source)
    manifest, registry, _ = assert_graph_validated_without_final_pages(source)
    structural_sha = (((registry.get("graph") or {}).get("lifecycle") or {}).get("structural_sha256"))
    if not structural_sha:
        raise WorkspaceError("Le corpus promu ne contient pas d'empreinte structurelle validée")

    state = assert_control_directory(project_root / ".state", project_root, create=True)
    editorial_root = assert_control_directory(state / "editorial-workspaces", project_root, create=True)
    debate_root = assert_control_directory(editorial_root / debate_id, project_root, create=True)
    selected_work_id = validate_work_id(work_id) if work_id else next_work_id(debate_root)
    target = debate_root / selected_work_id
    if target.exists() or target.is_symlink():
        raise WorkspaceError(f"Le workspace existe déjà : {relative_to_project(target, project_root)}")

    temporary = Path(tempfile.mkdtemp(prefix=f".{selected_work_id}.tmp-", dir=debate_root))
    try:
        working_copy = temporary / "working-copy"
        shutil.copytree(source, working_copy, symlinks=False, copy_function=shutil.copy2)
        assert_no_symlinks(working_copy)
        copied_tree_sha = full_tree_sha256(working_copy)
        if copied_tree_sha != source_tree_before:
            raise WorkspaceError("La copie de travail ne correspond pas exactement au corpus source")

        audit, review_items = build_audit(working_copy, debate_id, selected_work_id)
        tasks = make_tasks(review_items, debate_id, selected_work_id)
        vocabulary = keyword_vocabulary_working(review_items, debate_id, selected_work_id)
        translation = translation_readiness(review_items, registry, debate_id, selected_work_id)
        review_ledger = {
            "schema": REVIEW_SCHEMA,
            "schema_version": "1.0",
            "normative_revision": NORM_VERSION,
            "debate_id": debate_id,
            "work_id": selected_work_id,
            "status": "pending",
            "generated_at": now_iso(),
            "items": review_items,
        }
        changeset = {
            "schema": CHANGESET_SCHEMA,
            "schema_version": "1.0",
            "debate_id": debate_id,
            "work_id": selected_work_id,
            "status": "empty",
            "operations": [],
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        write_json(temporary / "audits" / "editorial_inventory.json", audit)
        (temporary / "audits" / "editorial_inventory.md").write_text(audit_markdown(audit), encoding="utf-8", newline="\n")
        write_json(temporary / "reviews" / "fr" / "page_metadata_review.json", review_ledger)
        write_json(temporary / "reviews" / "en" / "translation_readiness.json", translation)
        write_json(temporary / "tasks" / "editorial_tasks.json", tasks)
        write_json(temporary / "data" / "keyword_vocabulary_working.json", vocabulary)
        write_json(temporary / "changes" / "changeset.json", changeset)

        workspace = {
            "schema": WORKSPACE_SCHEMA,
            "schema_version": "1.0",
            "normative_revision": NORM_VERSION,
            "validator_version": VALIDATOR_VERSION,
            "kit_version": KIT_VERSION,
            "debate_id": debate_id,
            "work_id": selected_work_id,
            "status": "audit_ready",
            "source": {
                "path": f"corpus/{debate_id}",
                "global_status": manifest.get("global_status"),
                "tree_sha256": source_tree_before,
                "structural_sha256": structural_sha,
            },
            "working_copy": {
                "path": "working-copy",
                "initial_tree_sha256": copied_tree_sha,
                "current_status": "unchanged",
            },
            "artifacts": {
                "audit_json": "audits/editorial_inventory.json",
                "audit_markdown": "audits/editorial_inventory.md",
                "french_metadata_review": "reviews/fr/page_metadata_review.json",
                "translation_readiness": "reviews/en/translation_readiness.json",
                "task_ledger": "tasks/editorial_tasks.json",
                "keyword_vocabulary": "data/keyword_vocabulary_working.json",
                "changeset": "changes/changeset.json",
            },
            "boundaries": {
                "source_corpus_mutated": False,
                "automatic_editorial_corrections_applied": False,
                "final_pages_generated": False,
                "english_translation_started": False,
                "remote_access": False,
                "publication_started": False,
            },
            "created_at": now_iso(),
            "workspace_sha256": None,
        }
        workspace["workspace_sha256"] = workspace_receipt_hash(workspace)
        write_json(temporary / "workspace.json", workspace)

        # The working copy must remain byte-for-byte identical after all ledgers are built.
        if full_tree_sha256(working_copy) != copied_tree_sha:
            raise WorkspaceError("L'initialisation du workspace a modifié la copie éditoriale du corpus")
        if full_tree_sha256(source) != source_tree_before:
            raise WorkspaceError("Le corpus source a changé pendant l'initialisation du workspace")

        os.replace(temporary, target)
        fsync_directory(debate_root)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    return {
        "status": "audit_ready",
        "debate_id": debate_id,
        "work_id": selected_work_id,
        "workspace": relative_to_project(target, project_root),
        "source_tree_sha256": source_tree_before,
        "working_copy_tree_sha256": copied_tree_sha,
        "pages": audit["counts"]["pages"],
        "diagnostics": audit["counts"]["issues"],
        "tasks": len(tasks["tasks"]),
        "automatic_corrections_applied": False,
        "final_pages_generated": False,
        "english_translation_started": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Créer un workspace éditorial depuis un corpus graph_validated promu.")
    parser.add_argument("debate_id")
    parser.add_argument("--work-id")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--machine-readable", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = args.project_root.expanduser().resolve()
    debate_id = validate_debate_id(args.debate_id)
    with exclusive_lock(project_root, debate_id, "editorial_workspace_init"):
        result = create_workspace(project_root, debate_id, args.work_id)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True) if args.machine_readable else json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except WorkspaceError as exc:
        print(f"WIKIDEBIA BLOQUÉ : {exc}", file=__import__("sys").stderr)
        raise SystemExit(2)
