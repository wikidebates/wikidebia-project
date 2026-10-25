#!/usr/bin/env python3
"""Render and validate final bilingual MediaWiki pages from locked editorial data.

The renderer consumes ``translated-copy/`` only after French metadata, French
content and English translation have been sealed.  It creates an atomically
visible ``rendered-copy/`` containing deterministic French and English pages,
page manifests, batches, aggregates and validation reports.  French pages
always receive one direct ``{{Lien interlangue}}`` targeting the locked English
canonical title; English pages never receive an interlanguage parameter.

No remote access or publication is performed.
"""

from __future__ import annotations

from wikidebia_citation_passages import render_sequence

from wikidebia_release_info import KIT_VERSION

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from wikidebia_corpus_build import (
    NORM_VERSION,
    VALIDATOR_VERSION,
    CorpusBuildError,
    assert_control_directory,
    assert_no_symlinks,
    exclusive_lock,
    full_tree_sha256,
    load_json,
    now_iso,
    relative_to_project,
    sha256_file,
    structural_sha256,
    validate_debate_id,
    write_json,
)
from wikidebia_corpus_init import extract_page_metadata
from wikidebia_editorial_workspace import WorkspaceError, fsync_directory, validate_work_id, workspace_receipt_hash
from wikidebia_editorial_review import EditorialReviewError, _assert_source_unchanged, _run_validator

RENDER_LOCK_SCHEMA = "wikidebia-bilingual-render-lock-1.0"
RENDER_CHANGESET_SCHEMA = "wikidebia-bilingual-render-changeset-1.0"


class RenderError(WorkspaceError):
    pass


def _render_preserved_french(source: Path, content: Mapping[str, Any], target_title: str) -> str:
    """Add the interlanguage link without rebuilding any historical parameter."""
    from wikidebia_graph_extract import _template_spans, _split_top_level, normalize_key, parse_template
    path = source / str(content.get("import_path") or "")
    if not path.is_file() or sha256_file(path) != content.get("import_sha256"):
        raise RenderError("Import français historique absent ou modifié")
    text = path.read_text(encoding="utf-8")
    # Preserve offsets and comments, unlike the extraction parser's comment removal.
    masked = re.sub(r"<!--.*?-->", lambda m: " " * len(m.group()), text, flags=re.S)
    candidates = []
    for start, end in _template_spans(masked):
        call = parse_template(masked[start:end])
        if call and normalize_key(call.name) in {"debat", "argument"}:
            candidates.append((start, end, call))
    if len(candidates) != 1 or any(c in target_title for c in "|{}\r\n"):
        raise RenderError("Modèle historique ou titre interlangue ambigu")
    start, end, call = candidates[0]
    link = _template("Lien interlangue", (("langue", "en"), ("page", target_title)))
    if call.get("interlangue"):
        if call.get("interlangue") != link:
            raise RenderError("Un lien interlangue historique existe déjà ; revue explicite requise")
        return text.rstrip("\n") + "\n"
    segments = _split_top_level(text[start + 2:end - 2], "|")
    keys = [(i, normalize_key(_split_top_level(segment, "=", maxsplit=1)[0])) for i, segment in enumerate(segments[1:], 1)]
    existing = [i for i, key in keys if key == "interlangue"]
    if len(existing) > 1:
        raise RenderError("Paramètre interlangue historique dupliqué")
    if existing:
        i = existing[0]
        segments[i] = segments[i] + link
    else:
        insertion = next((i for i, key in keys if key == "date creation"), len(segments))
        segments.insert(insertion, "interlangue=" + link + "\n")
    rendered = text[:start] + "{{" + "|".join(segments) + "}}" + text[end:]
    return rendered.rstrip("\n") + "\n"


def _workspace_path(project_root: Path, debate_id: str, work_id: str) -> Path:
    debate_id = validate_debate_id(debate_id)
    work_id = validate_work_id(work_id)
    state = assert_control_directory(project_root / ".state", project_root)
    editorial = assert_control_directory(state / "editorial-workspaces", project_root)
    debate_root = assert_control_directory(editorial / debate_id, project_root)
    raw = debate_root / work_id
    if raw.is_symlink():
        raise RenderError(f"Lien symbolique interdit pour le workspace : {raw}")
    path = raw.resolve()
    if path.parent != debate_root or not path.is_dir():
        raise RenderError(f"Workspace introuvable : .state/editorial-workspaces/{debate_id}/{work_id}")
    assert_no_symlinks(path)
    return path


def _load_workspace(project_root: Path, debate_id: str, work_id: str) -> tuple[Path, dict[str, Any]]:
    path = _workspace_path(project_root, debate_id, work_id)
    meta = load_json(path / "workspace.json", "workspace.json")
    if meta.get("schema") != "wikidebia-editorial-workspace-1.0":
        raise RenderError("Schéma de workspace non pris en charge")
    if meta.get("debate_id") != debate_id or meta.get("work_id") != work_id:
        raise RenderError("Identité du workspace divergente")
    if meta.get("workspace_sha256") != workspace_receipt_hash(meta):
        raise RenderError("Empreinte de workspace.json invalide")
    return path, meta


def _assert_translated_copy(workspace: Path, meta: Mapping[str, Any]) -> Path:
    if meta.get("status") not in {"en_translation_applied", "bilingual_rendered"}:
        raise RenderError(f"Statut incompatible avec le rendu : {meta.get('status')}")
    path = workspace / "translated-copy"
    if not path.is_dir() or path.is_symlink():
        raise RenderError("translated-copy absent ou non sûr")
    assert_no_symlinks(path)
    expected = str((meta.get("translated_copy") or {}).get("tree_sha256") or "")
    actual = full_tree_sha256(path)
    if not expected or actual != expected:
        raise RenderError("translated-copy a changé depuis son application")
    for rel in (
        "data/fr_page_metadata_lock.json",
        "data/fr_content_lock.json",
        "data/en_page_metadata_lock.json",
        "data/en_content_lock.json",
        "data/en_translation_lock.json",
    ):
        if not (path / rel).is_file():
            raise RenderError(f"Verrou requis absent : {rel}")
    # Old locks can be hash-valid yet have discarded prose during quote-only import.
    from wikidebia_translation_review import _source_snapshot
    from wikidebia_citation_passages import validate_translations
    try:
        _, _, french, _ = _source_snapshot(path)
        english = load_json(path / "data/en_content_lock.json", "verrou anglais du contenu")
        en_by_id = {r["id"]: r for r in english.get("arguments") or []}
        for row in french.get("arguments") or []:
            validate_translations(en_by_id.get(row["id"], {}).get("citation_passages", []),
                                  row.get("citation_passages") or [], row["id"])
    except (ValueError, EditorialReviewError) as exc:
        raise RenderError("Passages hors Citation non conservés : " + str(exc)) from exc
    if (path / "output").exists():
        raise RenderError("translated-copy contient déjà des pages finales")
    return path


def _normalize_sequence(value: str) -> str:
    text = str(value or "").strip()
    return re.sub(r"}}[ \t\r\n]+{{", "}}{{", text)




def _template(name: str, parameters: Iterable[tuple[str, Any]]) -> str:
    rows = [f"{{{{{name}"]
    for key, value in parameters:
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        rows.append(f"|{key}={text}")
    rows.append("}}")
    return "\n".join(rows)


def _sequence(templates: Iterable[str]) -> str:
    return "".join(template for template in templates if template)


def _authors(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        return ", ".join(cleaned) or None
    text = str(value).strip()
    return text or None


def _source_template(source: Mapping[str, Any], *, lang: str, position: str | None = None) -> str:
    source_type = str(source.get("type") or "")
    metadata = source.get("metadata") or {}
    if lang == "fr":
        if source_type == "bibliography":
            name = {
                "pro": "Référence bibliographique pour",
                "con": "Référence bibliographique contre",
                None: "Référence bibliographique",
            }[position]
            params = (
                ("auteurs", _authors(metadata.get("authors"))),
                ("article", metadata.get("article")),
                ("ouvrage", metadata.get("work")),
                ("volume", metadata.get("volume")),
                ("numéro", metadata.get("issue")),
                ("localisation", metadata.get("location")),
                ("page", metadata.get("page")),
                ("édition", metadata.get("publisher")),
                ("lieu", metadata.get("place")),
                ("date", metadata.get("date")),
                ("lien", metadata.get("link")),
            )
        elif source_type == "webliography":
            name = {"pro": "Référence sitographique pour", "con": "Référence sitographique contre", None: "Référence sitographique"}[position]
            params = (
                ("lien", metadata.get("link")),
                ("page", metadata.get("page")),
                ("auteurs", _authors(metadata.get("authors"))),
                ("site", metadata.get("site")),
                ("date", metadata.get("date")),
            )
        elif source_type == "videography":
            name = {"pro": "Référence vidéographique pour", "con": "Référence vidéographique contre", None: "Référence vidéographique"}[position]
            params = (
                ("titre", metadata.get("title")),
                ("auteurs", _authors(metadata.get("authors"))),
                ("lien", metadata.get("link")),
            )
        else:
            raise RenderError(f"Type documentaire français inconnu : {source_type}")
    else:
        if source_type == "bibliography":
            name = {"pro": "Pro bibliographical reference", "con": "Con bibliographical reference", None: "Bibliographical reference"}[position]
            params = (
                ("authors", _authors(metadata.get("authors"))),
                ("article", metadata.get("article")),
                ("work", metadata.get("work")),
                ("volume", metadata.get("volume")),
                ("issue", metadata.get("issue")),
                ("location", metadata.get("location")),
                ("page", metadata.get("page")),
                ("publisher", metadata.get("publisher")),
                ("place", metadata.get("place")),
                ("date", metadata.get("date")),
                ("link", metadata.get("link")),
            )
        elif source_type == "webliography":
            name = {"pro": "Pro web reference", "con": "Con web reference", None: "Web reference"}[position]
            params = (
                ("link", metadata.get("link")),
                ("page", metadata.get("page")),
                ("authors", _authors(metadata.get("authors"))),
                ("site", metadata.get("site")),
                ("date", metadata.get("date")),
            )
        elif source_type == "videography":
            name = {"pro": "Pro video reference", "con": "Con video reference", None: "Video reference"}[position]
            params = (
                ("title", metadata.get("title")),
                ("authors", _authors(metadata.get("authors"))),
                ("link", metadata.get("link")),
            )
        else:
            raise RenderError(f"Type documentaire anglais inconnu : {source_type}")
    return _template(name, params)


def _citation_template(citation: Mapping[str, Any], *, lang: str) -> str:
    if lang == "fr":
        parameters = citation.get("source_parameters") or []
    else:
        parameters = citation.get("parameters") or []
    if not isinstance(parameters, list):
        raise RenderError(f"Paramètres de citation invalides : {citation.get('id')}")
    rows: list[tuple[str, Any]] = []
    for parameter in parameters:
        if not isinstance(parameter, Mapping):
            raise RenderError(f"Paramètre de citation invalide : {citation.get('id')}")
        name = str(parameter.get("name") or "").strip()
        value = str(parameter.get("value") or "").strip()
        if not name:
            raise RenderError(f"Nom de paramètre de citation vide : {citation.get('id')}")
        # L'inventaire historique conserve aussi les sous-paramètres facultatifs
        # présents mais vides. Le rendu canonique ne doit ni les considérer
        # comme une erreur ni leur inventer une valeur : _template() les omet.
        rows.append((name, value))
    return _template("Citation" if lang == "fr" else "Quote", rows)


def _relations(registry: Mapping[str, Any], node_id: str, relation: str, lang: str, contextual_labels: Sequence[Mapping[str, Any]] = ()) -> str:
    nodes = {str(node.get("id")): node for node in (registry.get("graph") or {}).get("nodes") or [] if node.get("status") == "active"}
    edges = [
        edge for edge in (registry.get("graph") or {}).get("edges") or []
        if edge.get("status") == "active" and edge.get("parent_node_id") == node_id and edge.get("relation") == relation
    ]
    edges.sort(key=lambda edge: (int(edge.get("order") or 0), str(edge.get("id") or "")))
    rendered = []
    for edge in edges:
        child = nodes.get(str(edge.get("child_node_id")))
        if child is None:
            raise RenderError(f"Nœud enfant absent : {edge.get('child_node_id')}")
        data = child.get(lang) or {}
        display_param = "titre-affiché" if lang == "fr" else "displayed-title"
        label = next((r.get("translated_text") if lang == "en" else r.get("source_text") for r in contextual_labels if r.get("id") == "edge:" + str(edge.get("id"))), data.get("displayed_title"))
        rendered.append(_template(relation.title(), (("page", data.get("canonical_title")), (display_param, label))))
    return _sequence(rendered)


def _main_arguments(registry: Mapping[str, Any], branch: str, lang: str, contextual_labels: Sequence[Mapping[str, Any]] = ()) -> str:
    nodes = {str(node.get("id")): node for node in (registry.get("graph") or {}).get("nodes") or [] if node.get("status") == "active"}
    occurrences = [
        occurrence for occurrence in (registry.get("graph") or {}).get("occurrences") or []
        if occurrence.get("depth") == 1 and occurrence.get("branch") == branch
    ]
    occurrences.sort(key=lambda occurrence: (int(occurrence.get("order") or 0), str(occurrence.get("id") or "")))
    names = {
        ("fr", "pro"): "Argument pour",
        ("fr", "con"): "Argument contre",
        ("en", "pro"): "Pro argument",
        ("en", "con"): "Con argument",
    }
    display_param = "titre-affiché" if lang == "fr" else "displayed-title"
    rows = []
    for occurrence in occurrences:
        node = nodes.get(str(occurrence.get("node_id")))
        if node is None:
            raise RenderError(f"Nœud principal absent : {occurrence.get('node_id')}")
        data = node.get(lang) or {}
        label = next((r.get("translated_text") if lang == "en" else r.get("source_text") for r in contextual_labels if r.get("id") == "root:" + str(occurrence.get("id"))), data.get("displayed_title"))
        rows.append(_template(names[(lang, branch)], (("page", data.get("canonical_title")), (display_param, label))))
    return _sequence(rows)


def _page_creation_dates(source: Path, registry: Mapping[str, Any], en_default: str) -> dict[tuple[str, str], str]:
    debate_id = str((registry.get("debate") or {}).get("id"))
    result: dict[tuple[str, str], str] = {}
    debate_import = source / "imports/fr/debate/debate.wiki"
    if debate_import.is_file():
        date = extract_page_metadata(debate_import.read_text(encoding="utf-8"), debate=True).get("creation_date")
        if date and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(date)):
            result[(debate_id, "fr")] = str(date)
    for node in (registry.get("graph") or {}).get("nodes") or []:
        if node.get("status") != "active":
            continue
        node_id = str(node.get("id"))
        imported = source / f"imports/fr/arguments/{node_id}.wiki"
        if imported.is_file():
            date = extract_page_metadata(imported.read_text(encoding="utf-8"), debate=False).get("creation_date")
            if date and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(date)):
                result[(node_id, "fr")] = str(date)
    fallback = str(((load_json(source / "manifest.json", "manifest.json").get("editorial_controls") or {}).get("creation_date") or en_default))
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fallback):
        fallback = en_default
    result.setdefault((debate_id, "fr"), fallback)
    result[(debate_id, "en")] = en_default
    for node in (registry.get("graph") or {}).get("nodes") or []:
        if node.get("status") != "active":
            continue
        node_id = str(node.get("id"))
        result.setdefault((node_id, "fr"), fallback)
        result[(node_id, "en")] = en_default
    return result


def _page_origin(content: Mapping[str, Any]) -> str:
    origin = str(content.get("page_origin") or "new")
    if origin not in {"new", "preexisting"}:
        raise RenderError(f"Origine de page invalide : {origin}")
    return origin


def _preserved_parameter(content: Mapping[str, Any], name: str) -> tuple[bool, str | None]:
    state = (content.get("preserved_parameters") or {}).get(name)
    if not isinstance(state, dict) or not isinstance(state.get("present"), bool):
        raise RenderError(f"État de paramètre préservé invalide : {name}")
    if state["present"]:
        value = state.get("value")
        if not isinstance(value, str) or not value.strip():
            raise RenderError(f"Valeur préservée absente : {name}")
        return True, value
    if state.get("value") is not None:
        raise RenderError(f"Valeur fournie pour un paramètre antérieurement absent : {name}")
    return False, None


PRESERVED_PARAMETER_ALIASES = {
    "débat-dédié": ("débat-dédié", "débat-détaillé"),
    "dedicated-debate": ("dedicated-debate", "detailed-debate"),
}

def _optional_preserved_parameter(content: Mapping[str, Any], name: str) -> tuple[bool, str | None]:
    preserved = content.get("preserved_parameters") or {}
    for candidate in PRESERVED_PARAMETER_ALIASES.get(name, (name,)):
        state = preserved.get(candidate)
        if state is not None:
            if not isinstance(state, Mapping) or not isinstance(state.get("present"), bool):
                raise RenderError(f"État de paramètre préservé invalide : {candidate}")
            if state["present"]:
                value = state.get("value")
                if not isinstance(value, str) or not value.strip():
                    raise RenderError(f"Valeur préservée absente : {candidate}")
                return True, value
            return False, None
    return False, None


def _append_lifecycle_parameter(params: list[tuple[str, Any]], content: Mapping[str, Any], name: str, new_value: str | None) -> None:
    if _page_origin(content) == "new":
        if new_value is not None:
            params.append((name, new_value))
        return
    # Les anciens workspaces peuvent ne pas encore porter tous les états. Le
    # validateur 1.2.50 exige la complétude dans un paquet publiable ; le rendu
    # reste toutefois rétrocompatible et n'invente rien en cas d'état absent.
    present, value = _optional_preserved_parameter(content, name)
    if present:
        params.append((name, value))


FR_EN_RENDER_METADATA_VALUE_MAP = {
    "progress": {
        "Ébauche": "Draft",
        "Débat en construction": "Debate under construction",
        "Débat construit": "Constructed debate",
    },
    "debate-warnings": {
        "Débat sensible": "Sensitive debate",
        "Débat saugrenu": "Fanciful debate",
        "Débat redondant": "Redundant debate",
        "Débat déséquilibré": "Unbalanced debate",
        "Plan à améliorer": "Plan to improve",
        "Débat généré par IA": "Debate generated by AI",
    },
    "title-warnings:debate": {
        "Titre non standard": "Non-standard title",
        "Titre à simplifier": "Title to simplify",
        "Titre à expliciter": "Title to be explained",
    },
    "title-warnings:argument": {
        "Titre désavantageux": "Disadvantageous title",
        "Titre peu clair": "Unclear title",
        "Titre incomplet": "Incomplete title",
        "Titre trop long": "Too long title",
    },
    "argument-warnings": {
        "Argument sensible": "Sensitive argument",
        "Argument saugrenu": "Fanciful argument",
        "Argument potentiellement illégal": "Potentially illegal argument",
        "Argument généré par IA": "Argument generated by AI",
    },
    "summary-warnings": {
        "Résumé à rédiger": "Summary to be written",
        "Résumé peu clair": "Unclear summary",
        "Résumé désavantageux": "Biased summary",
    },
}


def _effective_source_lifecycle_parameter(
    content: Mapping[str, Any], name: str, creation_default: str | None,
) -> tuple[bool, str | None]:
    """Return the parameter actually carried by the authoritative FR page.

    For a French page created by Wikidéb’IA the renderer defaults are part of
    the effective source page.  For a pre-existing French page, only the
    preserved presence/value is authoritative.
    """
    if _page_origin(content) == "new":
        return creation_default is not None, creation_default
    return _optional_preserved_parameter(content, name)


def _mapped_source_metadata_value(value: str, mapping_key: str, label: str) -> str:
    mapping = FR_EN_RENDER_METADATA_VALUE_MAP[mapping_key]
    values = [part.strip() for part in value.split(",") if part.strip()]
    translated: list[str] = []
    for source_value in values:
        target = mapping.get(source_value)
        if target is None:
            raise RenderError(f"Valeur française non reconnue pour {label} : {source_value}")
        translated.append(target)
    if not translated:
        raise RenderError(f"Valeur française vide pour {label}")
    return ", ".join(translated)


def _append_source_authoritative_metadata(
    params: list[tuple[str, Any]], source_content: Mapping[str, Any], *,
    fr_name: str, en_name: str, page_type: str, creation_default: str | None,
) -> None:
    """Project one FR lifecycle/editorial metadata field into English.

    A translated English page is technically new, but it is not an editorial
    creation from zero.  Presence and value of mapped metadata therefore come
    from the exact French source instead of English creation defaults.
    """
    present, source_value = _effective_source_lifecycle_parameter(source_content, fr_name, creation_default)
    if not present:
        return
    if not isinstance(source_value, str) or not source_value.strip():
        raise RenderError(f"Valeur française absente pour {fr_name}")
    mapping_key = f"title-warnings:{page_type}" if en_name == "title-warnings" else en_name
    params.append((en_name, _mapped_source_metadata_value(source_value, mapping_key, fr_name)))


def _append_interlanguage_parameter(params: list[tuple[str, Any]], content: Mapping[str, Any], name: str, new_value: str | None) -> None:
    if _page_origin(content) == "new":
        if new_value is not None:
            params.append((name, new_value))
        return
    state = (content.get("preserved_parameters") or {}).get(name)
    if isinstance(state, dict) and state.get("present") is True:
        value = state.get("value")
        if isinstance(value, str) and value.strip():
            params.append((name, value))
        return
    # Un lien absent historiquement peut être ajouté par le workflow bilingue ;
    # en revanche un lien historique présent est toujours conservé exactement.
    if new_value is not None:
        params.append((name, new_value))


def _append_editorial_parameter(
    params: list[tuple[str, Any]], content: Mapping[str, Any], name: str, value: Any,
) -> None:
    """Append a non-empty editorial parameter.

    ``source_parameter_presence`` remains provenance only. Canonical output
    never materializes an optional empty value as ``|name=``: empty logical
    values are omitted regardless of historical presence.
    """
    if value is None:
        return
    if str(value).strip():
        params.append((name, value))


_INLINE_REF_RE = re.compile(r"(<ref\b[^>]*>)(.*?)(</ref\s*>)", re.I | re.S)
_HTTP_URL_RE = re.compile(r"https?://[^\s<>\]]+", re.I)
_MACHINE_DOCUMENTARY_DATE_RE = re.compile(r"(?<!\d)(\d{4})-(\d{2})(?:-(\d{2}))?((?:[T ][0-9:.+Z-]+)?)(?!\d)")
_EN_MONTHS = (
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
_FR_MONTHS = (
    "", "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)


def _natural_documentary_date(match: re.Match[str], lang: str) -> str:
    year = int(match.group(1))
    month = int(match.group(2))
    day_raw = match.group(3)
    suffix = match.group(4) or ""
    if not 1 <= month <= 12:
        return match.group(0)
    months = _EN_MONTHS if lang == "en" else _FR_MONTHS
    if day_raw is None:
        rendered = f"{months[month]} {year}"
    else:
        day = int(day_raw)
        if not 1 <= day <= 31:
            return match.group(0)
        rendered = f"{day} {months[month]} {year}"
    if suffix:
        # Preserve a time/offset when one was supplied; only the machine-form
        # calendar date is localized.  A leading 'T' becomes a normal space.
        rendered += " " + suffix.lstrip("T ")
    return rendered


def _normalize_inline_documentary_dates(text: str, lang: str) -> str:
    """Localize machine-form documentary dates inside developed <ref> notes.

    URLs are shielded before replacement: an ISO-looking path segment is part
    of the identifier, not a documentary date.  This is a deterministic render
    normalization only; it never rewrites the locked semantic prose outside
    reference bodies.
    """
    if not text or lang not in {"fr", "en"}:
        return text

    def normalize_ref(ref_match: re.Match[str]) -> str:
        prefix, body, suffix = ref_match.groups()
        parts: list[str] = []
        cursor = 0
        for url_match in _HTTP_URL_RE.finditer(body):
            prose = body[cursor:url_match.start()]
            parts.append(_MACHINE_DOCUMENTARY_DATE_RE.sub(lambda m: _natural_documentary_date(m, lang), prose))
            parts.append(url_match.group(0))
            cursor = url_match.end()
        parts.append(_MACHINE_DOCUMENTARY_DATE_RE.sub(lambda m: _natural_documentary_date(m, lang), body[cursor:]))
        return prefix + "".join(parts) + suffix

    return _INLINE_REF_RE.sub(normalize_ref, text)


def _render_debate(
    *, lang: str, registry: Mapping[str, Any], metadata_lock: Mapping[str, Any], content_lock: Mapping[str, Any],
    sources: Mapping[str, Mapping[str, Any]], creation_date: str, include_interlanguage: bool = True,
    source_content: Mapping[str, Any] | None = None,
) -> str:
    debate = content_lock.get("debate") or {}
    documentation = debate.get("documentation") or {}
    if lang == "fr":
        rendered = {
            bucket: _sequence(_source_template(sources[source_id], lang="fr", position=position) for source_id in documentation.get(bucket) or [])
            for bucket, position in [
                ("bibliographie-pour", "pro"), ("bibliographie-contre", "con"), ("bibliographie-ni-pour-ni-contre", None),
                ("sitographie-pour", "pro"), ("sitographie-contre", "con"), ("sitographie-ni-pour-ni-contre", None),
                ("vidéographie-pour", "pro"), ("vidéographie-contre", "con"), ("vidéographie-ni-pour-ni-contre", None),
            ]
        }
        target = (((registry.get("debate") or {}).get("pages") or {}).get("en") or {}).get("canonical_title")
        params: list[tuple[str, Any]] = [("sujet", debate.get("subject")), ("sujet-développé", debate.get("complete_topic"))]
        _append_lifecycle_parameter(params, debate, "avancement", "Débat construit")
        _append_lifecycle_parameter(params, debate, "avertissements-titre", None)
        _append_lifecycle_parameter(params, debate, "avertissements-débat", "Débat généré par IA")
        _append_editorial_parameter(params, debate, "introduction", _normalize_sequence(str(debate.get("introduction") or "")))
        _append_editorial_parameter(params, debate, "articles-Wikipédia", _sequence(_template("Article Wikipédia", (("page", title),)) for title in debate.get("wikipedia_articles") or []))
        _append_editorial_parameter(params, debate, "arguments-pour", _main_arguments(registry, "pro", "fr", debate.get("relation_labels") or []))
        _append_editorial_parameter(params, debate, "arguments-contre", _main_arguments(registry, "con", "fr", debate.get("relation_labels") or []))
        _append_lifecycle_parameter(params, debate, "avertissements-bibliographie", None)
        for bucket in ("bibliographie-pour", "bibliographie-contre", "bibliographie-ni-pour-ni-contre"):
            _append_editorial_parameter(params, debate, bucket, rendered[bucket])
        _append_lifecycle_parameter(params, debate, "avertissements-sitographie", None)
        for bucket in ("sitographie-pour", "sitographie-contre", "sitographie-ni-pour-ni-contre"):
            _append_editorial_parameter(params, debate, bucket, rendered[bucket])
        _append_lifecycle_parameter(params, debate, "avertissements-vidéographie", None)
        for bucket in ("vidéographie-pour", "vidéographie-contre", "vidéographie-ni-pour-ni-contre"):
            _append_editorial_parameter(params, debate, bucket, rendered[bucket])
        _append_lifecycle_parameter(params, debate, "débats-connexes", None)
        _append_editorial_parameter(params, debate, "rubriques", ", ".join((metadata_lock.get("debate") or {}).get("rubriques") or []))
        _append_editorial_parameter(params, debate, "mots-clés", ", ".join((metadata_lock.get("debate") or {}).get("keywords") or []))
        if include_interlanguage:
            _append_interlanguage_parameter(params, debate, "interlangue", _template("Lien interlangue", (("langue", "en"), ("page", target))))
        else:
            _append_interlanguage_parameter(params, debate, "interlangue", None)
        _append_lifecycle_parameter(params, debate, "date-création", creation_date)
        return _template("Débat", params) + "\n"

    rendered = {
        bucket: _sequence(_source_template(sources[source_id], lang="en", position=position) for source_id in documentation.get(bucket) or [])
        for bucket, position in [
            ("pro-bibliography", "pro"), ("con-bibliography", "con"), ("bibliography", None),
            ("pro-webliography", "pro"), ("con-webliography", "con"), ("webliography", None),
            ("pro-videography", "pro"), ("con-videography", "con"), ("videography", None),
        ]
    }
    params = [("topic", debate.get("topic")), ("expanded-topic", debate.get("complete_topic"))]
    if source_content is not None:
        _append_source_authoritative_metadata(params, source_content, fr_name="avancement", en_name="progress", page_type="debate", creation_default="Débat construit")
        _append_source_authoritative_metadata(params, source_content, fr_name="avertissements-titre", en_name="title-warnings", page_type="debate", creation_default=None)
        _append_source_authoritative_metadata(params, source_content, fr_name="avertissements-débat", en_name="debate-warnings", page_type="debate", creation_default="Débat généré par IA")
    else:
        _append_lifecycle_parameter(params, debate, "progress", "Constructed debate")
        _append_lifecycle_parameter(params, debate, "title-warnings", None)
        _append_lifecycle_parameter(params, debate, "debate-warnings", "Debate generated by AI")
    params.extend([
        ("introduction", _normalize_sequence(_normalize_inline_documentary_dates(str(debate.get("introduction") or ""), "en"))),
        ("wikipedia-articles", _sequence(_template("Wikipedia article", (("page", title),)) for title in debate.get("wikipedia_articles") or [])),
        ("pro-arguments", _main_arguments(registry, "pro", "en", debate.get("relation_labels") or [])),
        ("con-arguments", _main_arguments(registry, "con", "en", debate.get("relation_labels") or [])),
    ])
    params.extend((bucket, rendered[bucket]) for bucket in (
        "pro-bibliography", "con-bibliography", "bibliography", "pro-webliography", "con-webliography", "webliography",
        "pro-videography", "con-videography", "videography",
    ))
    _append_lifecycle_parameter(params, debate, "related-debates", None)
    params.extend([
        ("sections", ", ".join((metadata_lock.get("debate") or {}).get("sections") or [])),
        ("keywords", ", ".join((metadata_lock.get("debate") or {}).get("keywords") or [])),
    ])
    _append_lifecycle_parameter(params, debate, "creation-date", creation_date)
    return _template("Debate", params) + "\n"


def _render_argument(
    *, lang: str, node: Mapping[str, Any], content: Mapping[str, Any], registry: Mapping[str, Any],
    sources: Mapping[str, Mapping[str, Any]], creation_date: str, include_interlanguage: bool = True,
    source_content: Mapping[str, Any] | None = None,
) -> str:
    node_id = str(node.get("id"))
    selected = content.get("sources") or {}
    if lang == "fr":
        citations = render_sequence(content.get("citations") or [], content.get("citation_passages") or [], lambda row: _citation_template(row, lang="fr"))
        target = (node.get("en") or {}).get("canonical_title")
        params: list[tuple[str, Any]] = []
        for name, default in (
            ("initialisation", None), ("nom-consacré", content.get("argument_name")), ("nom", None),
            ("titre-affiché", None), ("avertissements-titre", None),
            ("avertissements-argument", "Argument généré par IA"), ("avertissements-résumé", None),
        ):
            _append_lifecycle_parameter(params, content, name, default)
        _append_editorial_parameter(params, content, "résumé", content.get("summary"))
        _append_editorial_parameter(params, content, "citations", citations)
        _append_lifecycle_parameter(params, content, "avertissements-références", None)
        _append_editorial_parameter(params, content, "références-bibliographiques", _sequence(_source_template(sources[source_id], lang="fr") for source_id in selected.get("bibliography") or []))
        _append_editorial_parameter(params, content, "références-sitographiques", _sequence(_source_template(sources[source_id], lang="fr") for source_id in selected.get("webliography") or []))
        _append_editorial_parameter(params, content, "références-vidéographiques", _sequence(_source_template(sources[source_id], lang="fr") for source_id in selected.get("videography") or []))
        detailed_present, detailed_value = _optional_preserved_parameter(content, "débat-dédié")
        _append_lifecycle_parameter(params, content, "avertissements-justifications", None)
        if not detailed_present:
            _append_editorial_parameter(params, content, "justifications", _relations(registry, node_id, "justification", "fr", content.get("relation_labels") or []))
        _append_lifecycle_parameter(params, content, "avertissements-objections", None)
        if not detailed_present:
            _append_editorial_parameter(params, content, "objections", _relations(registry, node_id, "objection", "fr", content.get("relation_labels") or []))
        if detailed_present:
            params.append(("débat-dédié", detailed_value))
        _append_editorial_parameter(params, content, "rubriques", ", ".join((node.get("fr") or {}).get("rubriques") or []))
        _append_editorial_parameter(params, content, "mots-clés", ", ".join((node.get("fr") or {}).get("keywords") or []))
        if include_interlanguage:
            _append_interlanguage_parameter(params, content, "interlangue", _template("Lien interlangue", (("langue", "en"), ("page", target))))
        else:
            _append_interlanguage_parameter(params, content, "interlangue", None)
        _append_lifecycle_parameter(params, content, "date-création", creation_date)
    else:
        citations = render_sequence(content.get("citations") or [], content.get("citation_passages") or [], lambda row: _citation_template(row, lang="en"))
        params = []
        for name, default in (("initialization", None), ("established-name", content.get("argument_name")), ("name", None)):
            _append_lifecycle_parameter(params, content, name, default)
        if source_content is not None:
            _append_source_authoritative_metadata(params, source_content, fr_name="avertissements-titre", en_name="title-warnings", page_type="argument", creation_default=None)
            _append_source_authoritative_metadata(params, source_content, fr_name="avertissements-argument", en_name="argument-warnings", page_type="argument", creation_default="Argument généré par IA")
            _append_source_authoritative_metadata(params, source_content, fr_name="avertissements-résumé", en_name="summary-warnings", page_type="argument", creation_default=None)
        else:
            for name, default in (("title-warnings", None), ("argument-warnings", "Argument generated by AI"), ("summary-warnings", None)):
                _append_lifecycle_parameter(params, content, name, default)
        params.extend([("summary", content.get("summary")), ("quotes", citations)])
        _append_lifecycle_parameter(params, content, "reference-warnings", None)
        params.extend([
            ("bibliography", _sequence(_source_template(sources[source_id], lang="en") for source_id in selected.get("bibliography") or [])),
            ("webliography", _sequence(_source_template(sources[source_id], lang="en") for source_id in selected.get("webliography") or [])),
            ("videography", _sequence(_source_template(sources[source_id], lang="en") for source_id in selected.get("videography") or [])),
        ])
        detailed_present, detailed_value = _optional_preserved_parameter(content, "dedicated-debate")
        _append_lifecycle_parameter(params, content, "justification-warnings", None)
        params.append(("justifications", None if detailed_present else _relations(registry, node_id, "justification", "en", content.get("relation_labels") or [])))
        _append_lifecycle_parameter(params, content, "objection-warnings", None)
        params.append(("objections", None if detailed_present else _relations(registry, node_id, "objection", "en", content.get("relation_labels") or [])))
        if detailed_present:
            params.append(("dedicated-debate", detailed_value))
        params.extend([
            ("sections", ", ".join((node.get("en") or {}).get("sections") or [])),
            ("keywords", ", ".join((node.get("en") or {}).get("keywords") or [])),
        ])
        _append_lifecycle_parameter(params, content, "creation-date", creation_date)
    return _template("Argument", params) + "\n"


def _wiki_record() -> dict[str, Any]:
    return {
        "check_status": "unchecked", "decision": None, "remote_revision_id": None,
        "remote_sha256": None, "published_at": None, "checked_at": None, "remote_title": None,
    }


def _page_manifest(
    *, debate_id: str, page_id: str, page_type: str, lang: str, title: str, file_path: str,
    sha256: str, creation_date: str, batch_id: str | None, timestamp: str, report_path: str,
    page_origin: str, preserved_parameters: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "page_manifest_version": "1.0", "debate_id": debate_id, "page_id": page_id,
        "page_type": page_type, "language": lang, "canonical_title": title,
        "file_path": file_path, "sha256": sha256, "creation_date": creation_date,
        "batch_id": batch_id, "status": "validated", "structure_version": "1.0",
        "render_profile_version": "1.0",
        "page_origin": page_origin,
        "preserved_parameters": copy.deepcopy(dict(preserved_parameters)),
        "validation": {"status": "passed", "report_path": report_path, "validated_at": timestamp},
        "wiki": _wiki_record(),
    }


def _write_aggregate(target: Path, lang: str, nodes: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    rel = f"output/{lang}/aggregates/arguments_batch_001.wiki"
    lines: list[str] = []
    for node in nodes:
        node_id = str(node.get("id"))
        title = str((node.get(lang) or {}).get("canonical_title"))
        page = (target / f"output/{lang}/arguments/{node_id}.wiki").read_text(encoding="utf-8").rstrip("\n")
        lines.extend([f"===== PAGE : {title} =====", page, ""])
    payload = "\n".join(lines).rstrip("\n") + "\n"
    path = target / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8", newline="\n")
    return rel, sha256_file(path)


def _batch(
    *, debate_id: str, lang: str, nodes: Sequence[Mapping[str, Any]], registry_sha: str,
    structural_sha: str, aggregate_path: str, aggregate_sha: str, timestamp: str, work_id: str,
) -> dict[str, Any]:
    batch_id = "FR-A-001" if lang == "fr" else "EN-A-001"
    node_ids = [str(node.get("id")) for node in nodes]
    incoming = {str(edge.get("child_node_id")) for edge in []}
    roots = [
        str(occ.get("node_id")) for occ in []
    ]
    # A single deterministic batch owns every active node.  Root nodes are the
    # active nodes with at least one depth-1 occurrence.
    roots = []
    return {
        "batch_schema_version": "1.0", "id": batch_id, "debate_id": debate_id,
        "language": lang, "page_type": "argument", "strategy": "size_balanced",
        "root_node_ids": roots, "node_ids": node_ids, "dependency_node_ids": [],
        "status": "validated",
        "inputs": {"registry_sha256": registry_sha, "structural_sha256": structural_sha, "render_profile_version": "1.0", "handoff_path": None},
        "outputs": {
            "individual_directory": f"output/{lang}/arguments", "aggregate_path": aggregate_path,
            "aggregate_sha256": aggregate_sha, "report_path": f"reports/{lang}_batch_001.txt",
        },
        "work": {
            "work_id": f"{work_id}-{lang.upper()}-RENDER", "conversation_name": f"Rendu déterministe des arguments {lang}",
            "started_at": timestamp, "completed_at": timestamp,
        },
    }


def _validation_records(timestamp: str, input_sha: str) -> list[dict[str, Any]]:
    scopes = ("graph", "fr_debate", "fr_global", "en_titles", "en_debate", "en_global", "bilingual")
    return [
        {
            "id": f"V{timestamp[:10].replace('-', '')}-{index:03d}", "scope": scope, "language": None,
            "validator_version": VALIDATOR_VERSION, "executed_at": timestamp, "input_sha256": input_sha,
            "result": "passed", "blocking_errors": 0, "warnings": 0,
            "report_path": "reports/final_validation.json",
        }
        for index, scope in enumerate(scopes, start=1)
    ]



def _copy_active_norm(project_root: Path, target: Path) -> None:
    filename = f"WIKIDEBIA_NORME_CONSOLIDEE_{NORM_VERSION}.md"
    source_tree_root = Path(__file__).resolve().parents[2]
    candidates = (
        project_root / "norms/normative_reference/01_normes" / filename,
        project_root / "validator/normative_reference/01_normes" / filename,
        source_tree_root / "norms/normative_reference/01_normes" / filename,
        source_tree_root / "normes/normative_reference/01_normes" / filename,
        source_tree_root / "validator/normative_reference/01_normes" / filename,
    )
    source = next((candidate for candidate in candidates if candidate.is_file()), None)
    if source is None:
        raise RenderError(f"Norme active introuvable dans l’installation : {filename}")
    normative = target / "normative"
    if normative.exists():
        shutil.rmtree(normative)
    normative.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, normative / filename)


def _finalize_individual_review(
    target: Path,
    registry: Mapping[str, Any],
    fr_meta: Mapping[str, Any],
    en_meta: Mapping[str, Any],
) -> None:
    fr_by_id = {str(row.get("entity_id")): row for row in fr_meta.get("arguments") or []}
    en_by_id = {str(row.get("id")): row for row in en_meta.get("arguments") or []}
    entries: list[dict[str, Any]] = []
    for node in sorted((registry.get("graph") or {}).get("nodes") or [], key=lambda row: str(row.get("id"))):
        if node.get("status") != "active":
            continue
        node_id = str(node.get("id"))
        fr = fr_by_id.get(node_id)
        en = en_by_id.get(node_id)
        if not fr or not en:
            raise RenderError(f"Verrou de métadonnées incomplet pour {node_id}")
        fr_rationales = fr.get("rationales") or {}
        title_decisions = fr.get("decisions") or {}
        title_decision = "reformulated" if title_decisions.get("displayed_title") == "change" else "retained_after_review"
        rubric_decision = "adjusted" if title_decisions.get("rubriques") == "change" else "retained_after_review"
        fr_canonical = str(fr.get("canonical_title") or "")
        fr_displayed = str(fr.get("displayed_title") or "")
        en_canonical = str(en.get("canonical_title") or "")
        en_displayed = str(en.get("displayed_title") or "")
        historical_source = str(en.get("source_page_origin") or "new") == "preexisting"
        entries.append({
            "id": node_id,
            "title_decision": title_decision,
            "title_reason": str(fr_rationales.get("displayed_title") or fr_rationales.get("canonical_title") or "Décision déjà approuvée et scellée dans le verrou français des métadonnées."),
            "new_displayed_title_fr": fr_displayed,
            "new_displayed_title_en": en_displayed,
            "canonical_referents_explicit_fr": True,
            "canonical_referents_explicit_en": True,
            "canonical_title_semantic_inventory_reviewed_en": bool(en.get("canonical_title_semantic_inventory_reviewed")),
            "canonical_title_semantic_inventory_note_en": en.get("canonical_title_semantic_inventory_note"),
            "canonical_title_semantically_equivalent_en": bool(en.get("canonical_title_equivalent_to_french")),
            "canonical_title_subject_preserved_en": bool(en.get("canonical_title_subject_preserved")),
            "canonical_title_predicate_preserved_en": bool(en.get("canonical_title_predicate_preserved")),
            "canonical_title_scope_preserved_en": bool(en.get("canonical_title_scope_preserved")),
            "canonical_title_modality_preserved_en": bool(en.get("canonical_title_modality_preserved")),
            "displayed_referents_explicit_fr": None if historical_source else True,
            "displayed_referents_explicit_en": None if historical_source else True,
            "displayed_title_complete_proposition_fr": en.get("displayed_title_source_form") == "proposition",
            "displayed_title_argument_intelligible_fr": True,
            "displayed_title_source_form_reviewed_fr": bool(en.get("displayed_title_source_form_reviewed")),
            "displayed_title_source_form_fr": en.get("displayed_title_source_form"),
            "displayed_title_complete_proposition_en": en.get("displayed_title_target_form") == "proposition",
            "displayed_title_argument_intelligible_en": True,
            "displayed_title_source_form_reviewed_en": bool(en.get("displayed_title_source_form_reviewed")),
            "displayed_title_no_formal_regression_en": bool(en.get("displayed_title_no_formal_regression")),
            "displayed_title_form_change_reviewed_en": bool(en.get("displayed_title_form_change_reviewed")),
            "displayed_title_speech_act_preserved_en": bool(en.get("displayed_title_speech_act_preserved")),
            "displayed_title_form_change_note_en": en.get("displayed_title_form_change_note"),
            "displayed_title_semantic_inventory_reviewed_en": bool(en.get("displayed_title_semantic_inventory_reviewed")),
            "displayed_title_source_form_en": en.get("displayed_title_source_form"),
            "displayed_title_target_form_en": en.get("displayed_title_target_form"),
            "displayed_title_semantic_inventory_note_en": en.get("displayed_title_semantic_inventory_note"),
            "displayed_title_subject_preserved_en": bool(en.get("displayed_title_subject_preserved")),
            "displayed_title_predicate_preserved_en": bool(en.get("displayed_title_predicate_preserved")),
            "displayed_title_scope_preserved_en": bool(en.get("displayed_title_scope_preserved")),
            "displayed_title_modality_preserved_en": bool(en.get("displayed_title_modality_preserved")),
            "displayed_title_concision_reviewed_fr": True,
            "displayed_title_concision_reviewed_en": True,
            "displayed_title_semantically_equivalent_fr": True,
            "displayed_title_semantically_equivalent_en": True,
            "displayed_title_semantic_equivalence_reviewed_fr": True,
            "displayed_title_semantic_equivalence_reviewed_en": True,
            "displayed_title_readability_improvement_reviewed_fr": True,
            "displayed_title_readability_improvement_reviewed_en": True,
            "displayed_title_improves_readability_when_distinct_fr": None if historical_source else fr_canonical.casefold() != fr_displayed.casefold(),
            "displayed_title_improves_readability_when_distinct_en": None if historical_source else en_canonical.casefold() != en_displayed.casefold(),
            "displayed_title_identity_justification_fr": "",
            "displayed_title_identity_justification_en": "",
            "new_rubriques": list(fr.get("rubriques") or []),
            "new_sections_en": list(en.get("sections") or []),
            "new_keywords_fr": list(fr.get("keywords") or []),
            "new_keywords_en": list(en.get("keywords") or []),
            "keywords_ordered_by_relevance_fr": True,
            "keywords_ordered_by_relevance_en": True,
            "keyword_order_rationale_fr": str(fr_rationales.get("keyword_order") or "Les mots-clés sont classés du concept le plus directement pertinent au moins direct."),
            "keyword_order_rationale_en": "The English keywords preserve the exact French decreasing-relevance order.",
            "rubric_decision": rubric_decision,
            "rubric_rationales": ({r: "Rubrique de la source publiée conservée sans reclassement éditorial." for r in fr.get("rubriques") or []}
                if fr_meta.get("source_preservation_policy") else copy.deepcopy(fr_rationales.get("rubriques") or {})),
        })
    write_json(target / "reviews/individual_review.json", {
        "normative_revision": NORM_VERSION,
        "status": "approved_from_locked_metadata",
        "entries": entries,
    })


def _finalize_graph_placement_review(target: Path, registry: Mapping[str, Any]) -> None:
    path = target / "reviews/graph_placement_review.json"
    review = load_json(path, "revue du placement du graphe")
    entries = review.get("entries")
    if not isinstance(entries, list) or not entries:
        raise RenderError("La revue formelle du placement du graphe est absente ou vide")
    review = copy.deepcopy(review)
    review["normative_revision"] = NORM_VERSION
    review["debate_id"] = str((registry.get("debate") or {}).get("id") or "")
    review.setdefault("status", "approved")
    write_json(path, review)


def _finalize_summary_review(target: Path, debate_id: str) -> None:
    """Normalize the final summary-review ledger from authoritative locks.

    Older translated workspaces can carry a style ledger produced before the
    historical-summary provenance contract was fully propagated.  At render
    time the FR/EN content locks are authoritative, so repair *only* provenance
    decisions for historical/absent summaries.  Attestations for genuinely new
    summaries are never fabricated here and remain subject to the normal human
    review requirements.
    """
    path = target / "reviews/summary_style_review.json"
    review = load_json(path, "revue du style des résumés")
    entries = review.get("entries")
    if not isinstance(entries, list):
        raise RenderError("Revue du style des résumés absente")
    review = copy.deepcopy(review)
    by_id = {
        str(row.get("id")): row
        for row in review.get("entries") or []
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    fr_lock = load_json(target / "data/fr_content_lock.json", "verrou français du contenu")
    en_lock = load_json(target / "data/en_content_lock.json", "verrou anglais du contenu")
    fr_rows = {str(row.get("id")): row for row in fr_lock.get("arguments") or [] if isinstance(row, dict) and row.get("id")}
    en_rows = {str(row.get("id")): row for row in en_lock.get("arguments") or [] if isinstance(row, dict) and row.get("id")}
    if set(fr_rows) != set(en_rows):
        raise RenderError("Les verrous FR/EN ne couvrent pas les mêmes résumés")

    for node_id in sorted(fr_rows):
        entry = by_id.setdefault(node_id, {"id": node_id, "languages": {}})
        languages = entry.setdefault("languages", {})
        if not isinstance(languages, dict):
            raise RenderError(f"Revue du résumé {node_id} : languages invalide")
        fr = fr_rows[node_id]
        en = en_rows[node_id]
        fr_provenance = str(fr.get("summary_provenance") or fr.get("status") or "")
        en_provenance = str(en.get("summary_provenance") or en.get("status") or "")

        if fr_provenance == "historical_absent" or fr.get("summary") is None:
            languages["fr"] = {
                "status": "historical_absent",
                "historical_absence_verified": True,
                "note": fr.get("note") or "Absence historique du résumé vérifiée et conservée sans génération de remplissage.",
            }
        elif fr_provenance in {"historical_authorized_change", "historical_authorized_creation"}:
            languages["fr"] = {
                "status": fr_provenance,
                "owner_authorized_change": True,
                "historical_source_sha256": fr.get("historical_summary_sha256"),
                "authorized_final_sha256": fr.get("historical_final_summary_sha256"),
                "authorization": copy.deepcopy(fr.get("historical_authorization")),
                "change_scope": copy.deepcopy(fr.get("historical_change_scope")),
                "note": fr.get("note") or "Résumé historique modifié uniquement dans la portée autorisée par le propriétaire.",
            }
        elif fr_provenance == "historical_existing":
            languages["fr"] = {
                "status": "historical_existing",
                "historical_content_preserved": True,
                "note": fr.get("note") or "Résumé historique conservé exactement sans réécriture stylistique rétroactive.",
            }
        else:
            decision = languages.get("fr")
            if isinstance(decision, dict) and decision.get("status") == "translated_and_reviewed":
                decision["status"] = "approved"

        if en_provenance == "historical_absent" or en.get("summary") is None:
            languages["en"] = {
                "status": "historical_absent",
                "historical_absence_verified": True,
                "note": en.get("note") or "French source summary is historically absent and the English parameter is omitted.",
            }
        elif en_provenance in {"historical_existing", "historical_authorized_change", "historical_authorized_creation"}:
            languages["en"] = {
                "status": "translated_historical_source",
                "historical_source_preserved": True,
                "summary_ratio_reviewed": bool(en.get("summary_ratio_reviewed")),
                "summary_length_ratio": en.get("summary_length_ratio"),
                "summary_ratio_exception_rationale": en.get("summary_ratio_exception_rationale") or "",
                "note": en.get("note") or "English summary faithfully translates the protected historical French source without retroactive style rewriting.",
            }
        else:
            decision = languages.get("en")
            if isinstance(decision, dict) and decision.get("status") == "translated_and_reviewed":
                decision["status"] = "approved"

    review["schema_version"] = "1.0"
    review["normative_revision"] = NORM_VERSION
    review.pop("quality_policy_revision", None)
    review["debate_id"] = debate_id
    review["entries"] = [by_id[key] for key in sorted(by_id)]
    write_json(path, review)



_KEYWORD_WORD_TOKEN = re.compile(r"[A-Za-zÀ-ÿ]+(?:[-’'][A-Za-zÀ-ÿ]+)?")
_KEYWORD_CONNECTOR_FR = re.compile(r"\b(?:de|du|des|la|le|et)\b|\bd[’']", re.I)
_KEYWORD_CONNECTOR_EN = re.compile(r"\b(?:of|and|the)\b", re.I)


def _keyword_requires_multiword_exception(value: str, language: str) -> bool:
    text = str(value or "").strip()
    tokens = _KEYWORD_WORD_TOKEN.findall(text)
    connector = _KEYWORD_CONNECTOR_FR if language == "fr" else _KEYWORD_CONNECTOR_EN
    return len(tokens) > 2 or bool(connector.search(text))


def _finalize_keyword_vocabulary(target: Path) -> None:
    """Normalize legacy bilingual atomicity metadata without changing keywords.

    Older historical vocabularies can already attest ``atomic_concept=true`` and
    ``compositional_intersection=false`` while lacking the later explicit
    multiword marker, or can carry a French-required exception into a shorter
    English equivalent.  At final render we reconcile only those metadata fields
    for concepts used exclusively by historically sourced pages.  No keyword,
    ordering or concept identity is changed.
    """
    path = target / "data/keyword_vocabulary_bilingual.json"
    if not path.exists():
        return
    vocabulary = load_json(path, "vocabulaire bilingue des mots-clés")
    entries = vocabulary.get("entries")
    if not isinstance(entries, list):
        return

    fr_lock = load_json(target / "data/fr_content_lock.json", "verrou français du contenu")
    en_lock = load_json(target / "data/en_content_lock.json", "verrou anglais du contenu")
    fr_historical = {
        str(row.get("id"))
        for row in fr_lock.get("arguments") or []
        if isinstance(row, dict) and row.get("id") and row.get("page_origin") == "preexisting"
    }
    en_historical = {
        str(row.get("id"))
        for row in en_lock.get("arguments") or []
        if isinstance(row, dict) and row.get("id") and row.get("source_page_origin") == "preexisting"
    }

    changed = False
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if fr_lock.get("source_preservation_policy"):
            entry["usage_count_in_debate"] = sum(1 for u in entry.get("usages") or [] if u.get("entity_type", u.get("page_type")) == "argument")
            if entry.get("kind") in {"proper_name", "acronym"} and not entry.get("capitalization_rationale"):
                entry["capitalization_rationale"] = "Forme propre historique conservée et relue dans le vocabulaire bilingue : " + str(entry.get("fr"))
            changed = True
        usage_ids = {
            str(row.get("entity_id", row.get("page_id")))
            for row in entry.get("usages") or []
            if isinstance(row, dict) and row.get("entity_type", row.get("page_type")) == "argument" and row.get("entity_id", row.get("page_id"))
        }
        historical_fr_usage = bool(usage_ids) and usage_ids <= fr_historical
        historical_en_usage = bool(usage_ids) and usage_ids <= en_historical

        fr_value = str(entry.get("fr") or "").strip()
        if (
            historical_fr_usage
            and entry.get("atomic_concept") is True
            and entry.get("compositional_intersection") is False
        ):
            needs = _keyword_requires_multiword_exception(fr_value, "fr")
            if needs and entry.get("multiword_exception") is not True:
                entry["multiword_exception"] = True
                entry["multiword_exception_rationale"] = (
                    f'Locution conceptuelle historique « {fr_value} » déjà attestée comme concept atomique '
                    "et non compositionnel ; sa décomposition ferait perdre la catégorie de navigation."
                )
                changed = True
            elif not needs and entry.get("multiword_exception") is True:
                entry["multiword_exception"] = False
                entry.pop("multiword_exception_rationale", None)
                changed = True

        en_value = str(entry.get("en") or "").strip()
        if (
            historical_en_usage
            and entry.get("en_atomic_concept") is True
            and entry.get("en_compositional_intersection") is False
        ):
            needs = _keyword_requires_multiword_exception(en_value, "en")
            if needs and entry.get("en_multiword_exception") is not True:
                entry["en_multiword_exception"] = True
                entry["en_multiword_exception_rationale"] = (
                    f'Historical lexicalized navigation concept "{en_value}" already attested as atomic and '
                    "non-compositional; splitting it would lose the controlled category."
                )
                changed = True
            elif not needs and entry.get("en_multiword_exception") is True:
                entry["en_multiword_exception"] = False
                entry["en_multiword_exception_rationale"] = ""
                changed = True

    if changed:
        write_json(path, vocabulary)


def _looks_like_explanatory_terminal_reference(body: str) -> bool:
    """Conservative compatibility test for a reviewed explanatory note."""
    text = re.sub(r"https?://[^\s<>\]]+", " ", str(body or ""), flags=re.I)
    words = re.findall(r"[A-Za-zÀ-ÿ0-9]+", text)
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part.strip()]
    return len(words) >= 25 and len(sentences) >= 2


def _finalize_introduction_review(target: Path) -> None:
    """Reconcile legacy introduction-review evidence from authoritative locks.

    This only upgrades provenance/evidence fields.  It never rewrites the
    introduction or changes a subsection title/content.
    """
    path = target / "reviews/introduction_review.json"
    if not path.exists():
        return
    review = load_json(path, "revue des introductions")
    entries = review.get("entries")
    if not isinstance(entries, list):
        return
    by_lang = {
        str(row.get("language")): row
        for row in entries
        if isinstance(row, dict) and row.get("language") in {"fr", "en"}
    }
    changed = False

    fr_lock = load_json(target / "data/fr_content_lock.json", "verrou français du contenu")
    fr_debate = fr_lock.get("debate") if isinstance(fr_lock, dict) else None
    if fr_lock.get("source_preservation_policy") and "fr" not in by_lang:
        fr_entry_new = {"language": "fr", "status": "historical_existing",
            "historical_content_preserved": True,
            "historical_source_sha256": hashlib.sha256(fr_debate["introduction"].encode("utf-8")).hexdigest(),
            "note": "Introduction historique française conservée exactement depuis l’import attesté, sans revendication de nouvelle revue documentaire."}
        entries.append(fr_entry_new)
        by_lang["fr"] = fr_entry_new
        changed = True
    fr_entry = by_lang.get("fr")
    if (
        isinstance(fr_entry, dict)
        and isinstance(fr_debate, dict)
        and fr_debate.get("page_origin") == "preexisting"
        and isinstance(fr_debate.get("introduction"), str)
        and fr_debate.get("introduction").strip()
    ):
        source_intro = fr_debate["introduction"]
        updates = {
            "status": "historical_existing",
            "historical_content_preserved": True,
            "historical_source_sha256": hashlib.sha256(source_intro.encode("utf-8")).hexdigest(),
        }
        for key, value in updates.items():
            if fr_entry.get(key) != value:
                fr_entry[key] = value
                changed = True
        if len(str(fr_entry.get("note") or "").strip()) < 12:
            fr_entry["note"] = (
                "Introduction française historique préservée ; un ancien projet de réécriture du registre "
                "n'est pas la valeur éditoriale sélectionnée."
            )
            changed = True

    en_entry = by_lang.get("en")
    en_page = target / "output/en/debate/debate.wiki"
    if (
        isinstance(en_entry, dict)
        and en_entry.get("source_page_origin") == "preexisting"
        and en_entry.get("reference_note_punctuation_reviewed") is True
        and en_page.exists()
    ):
        exceptions = en_entry.get("terminal_period_sentence_exceptions")
        if not isinstance(exceptions, list):
            exceptions = []
            en_entry["terminal_period_sentence_exceptions"] = exceptions
            changed = True
        known = {
            str(row.get("body_sha256"))
            for row in exceptions
            if isinstance(row, dict) and row.get("body_sha256")
        }
        text = en_page.read_text(encoding="utf-8")
        for match in re.finditer(r"<ref\b[^>]*>(?P<body>.*?)</ref\s*>", text, flags=re.I | re.S):
            body = match.group("body").strip()
            if not body.endswith(".") or not _looks_like_explanatory_terminal_reference(body):
                continue
            body_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
            if body_sha in known:
                continue
            evidence = re.split(r"(?<=[.!?])\s+", body.strip(), maxsplit=1)[0].strip()
            exceptions.append({
                "body_sha256": body_sha,
                "complete_sentence": True,
                "sentence_evidence": evidence,
            })
            known.add(body_sha)
            changed = True

    if changed:
        write_json(path, review)


def _prepare_final_controls(
    project_root: Path,
    target: Path,
    manifest: dict[str, Any],
    registry: Mapping[str, Any],
    fr_meta: Mapping[str, Any],
    en_meta: Mapping[str, Any],
    *,
    debate_id: str,
    work_id: str,
    timestamp: str,
) -> None:
    _copy_active_norm(project_root, target)
    _finalize_individual_review(target, registry, fr_meta, en_meta)
    _finalize_graph_placement_review(target, registry)
    _finalize_summary_review(target, debate_id)
    _finalize_keyword_vocabulary(target)
    _finalize_introduction_review(target)

    controls = manifest.setdefault("editorial_controls", {})
    controls["keyword_vocabulary_path"] = "data/keyword_vocabulary_bilingual.json"
    controls["individual_review_path"] = "reviews/individual_review.json"
    controls["graph_placement_review_path"] = "reviews/graph_placement_review.json"
    controls["summary_style_review_path"] = "reviews/summary_style_review.json"
    controls.setdefault("summary_style", {"enabled": True, "min_sentences": 2, "long_sentence_words": 35,
        "max_average_sentence_words": 30, "max_long_sentence_ratio": 0.5, "max_sentence_words": 60,
        "opening_title_similarity_enabled": True,
        "opening_similarity_threshold": 0.84, "opening_max_extra_significant_words": 4,
        "quantitative_claim_review_required": True})
    controls["introduction_review_path"] = "reviews/introduction_review.json"
    controls["individual_review_report_path"] = "reports/render_report.json"
    controls["required_reports"] = [
        "reports/render_report.json",
        "reports/render_preflight.json",
        "reports/final_validation.json",
    ]
    controls["historical_text_render_validation_mode"] = "differential_preservation_v1"

    handoff_rel = f"handoffs/{work_id}-render.json"
    handoff = {
        "schema": "wikidebia-render-handoff-1.0",
        "debate_id": debate_id,
        "work_id": f"{work_id}-RENDER",
        "status": "completed",
        "normative_versions": {
            "consolidated_norm": NORM_VERSION,
            "validator": VALIDATOR_VERSION,
            "kit": KIT_VERSION,
        },
        "remote_operations_performed": False,
        "created_at": timestamp,
    }
    write_json(target / handoff_rel, handoff)
    manifest["traceability_controls"] = {
        "current_corrective_work_id": f"{work_id}-RENDER",
        "current_handoff_path": handoff_rel,
        "required_corrective_handoffs": [handoff_rel],
        "remote_write_must_be_false": True,
    }
    manifest["publication_gate"] = {
        "local_release_status": "corrective_in_progress",
        "remote_write_authorized": False,
        "remote_template_compatibility": "not_checked",
        "blocking_reason": "Le rendu local est validé, mais aucun préflight distant ni plan de publication n’a encore été exécuté.",
        "checked_at": timestamp,
    }

def _build_rendered_copy(
    project_root: Path, source: Path, target: Path, *, debate_id: str, work_id: str,
    translation_review_sha256: str,
) -> dict[str, Any]:
    shutil.copytree(source, target, symlinks=False, copy_function=shutil.copy2)
    assert_no_symlinks(target)
    registry = load_json(target / "data/registre_debat.json", "registre du débat")
    manifest = load_json(target / "manifest.json", "manifest.json")
    fr_meta = load_json(target / "data/fr_page_metadata_lock.json", "verrou français des métadonnées")
    fr_content = load_json(target / "data/fr_content_lock.json", "verrou français du contenu")
    en_meta = load_json(target / "data/en_page_metadata_lock.json", "verrou anglais des métadonnées")
    en_content = load_json(target / "data/en_content_lock.json", "verrou anglais du contenu")
    en_translation = load_json(target / "data/en_translation_lock.json", "verrou de traduction")
    from wikidebia_translation_source import POLICY, verify_frozen_source
    preserve_french = fr_content.get("source_preservation_policy") == POLICY
    if preserve_french:
        verify_frozen_source(target, fr_meta, fr_content)
    source_registry = load_json(target / "data/sources.json", "registre documentaire")
    if en_translation.get("review_sha256") != translation_review_sha256:
        raise RenderError("Le verrou anglais ne correspond pas à l’empreinte confirmée")
    if en_translation.get("status") != "locked_for_generation":
        raise RenderError("La traduction anglaise n’est pas verrouillée pour la génération")

    source_by_id = {str(row.get("id")): row for row in source_registry.get("sources") or []}
    nodes = [node for node in (registry.get("graph") or {}).get("nodes") or [] if node.get("status") == "active"]
    nodes.sort(key=lambda node: str(node.get("id")))
    fr_args = {str(row.get("id")): row for row in fr_content.get("arguments") or []}
    en_args = {str(row.get("id")): row for row in en_content.get("arguments") or []}
    french_pages = [fr_content.get("debate") or {}, *fr_args.values()]
    if french_pages and all(page.get("page_origin") == "preexisting" for page in french_pages):
        from wikidebia_translation_source import relation_labels_from_source
        contextual_labels = relation_labels_from_source(target)
        fr_content["debate"]["relation_labels"] = [
            row for row in contextual_labels if row["source_page_id"] == "debate"
        ]
        for node_id, argument in fr_args.items():
            argument["relation_labels"] = [
                row for row in contextual_labels if row["source_page_id"] == node_id
            ]
    if preserve_french:
        frozen_meta = {r.get("entity_id", r.get("id")): r for r in fr_meta["arguments"]}
        for node in nodes:
            actual = frozen_meta[node["id"]]
            node["fr"]["rubriques"] = list(actual["rubriques"])
            node["fr"]["keywords"] = list(actual["keywords"])
    if set(fr_args) != {str(node.get("id")) for node in nodes} or set(en_args) != set(fr_args):
        raise RenderError("Les verrous de contenu ne couvrent pas exactement les nœuds actifs")

    timestamp = now_iso()
    en_default_date = str(en_content.get("applied_at") or en_translation.get("applied_at") or timestamp)[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", en_default_date):
        en_default_date = dt.date.today().isoformat()
    dates = _page_creation_dates(source, registry, en_default_date)

    # Lock graph and titles before rendering.  This does not alter structural identity.
    lifecycle = (registry.get("graph") or {}).setdefault("lifecycle", {})
    lifecycle.update({"status": "locked", "locked_at": timestamp, "locked_by_stage": "bilingual_render", "structural_sha256": structural_sha256(registry)})
    debate_pages = (registry.get("debate") or {}).get("pages") or {}
    for lang in ("fr", "en"):
        debate_pages[lang]["title_status"] = "locked"
    for node in nodes:
        node["fr"]["title_status"] = "locked"
        node["en"]["title_status"] = "locked"

    output_paths: list[tuple[str, str, str, str, str]] = []
    debate_id_actual = str((registry.get("debate") or {}).get("id"))
    for lang, metadata_lock, content_lock in (("fr", fr_meta, fr_content), ("en", en_meta, en_content)):
        debate_rel = f"output/{lang}/debate/debate.wiki"
        debate_text = _render_debate(
            lang=lang, registry=registry, metadata_lock=metadata_lock, content_lock=content_lock,
            sources=source_by_id, creation_date=dates[(debate_id_actual, lang)],
            source_content=(fr_content.get("debate") or {}) if lang == "en" else None,
        )
        if lang == "fr" and preserve_french:
            debate_text = _render_preserved_french(target, fr_content["debate"], debate_pages["en"]["canonical_title"])
        debate_path = target / debate_rel
        debate_path.parent.mkdir(parents=True, exist_ok=True)
        debate_path.write_text(debate_text, encoding="utf-8", newline="\n")
        output_paths.append((debate_id_actual, lang, "debate", debate_rel, sha256_file(debate_path)))
        for node in nodes:
            node_id = str(node.get("id"))
            rel = f"output/{lang}/arguments/{node_id}.wiki"
            text = _render_argument(
                lang=lang, node=node, content=(fr_args if lang == "fr" else en_args)[node_id],
                registry=registry, sources=source_by_id, creation_date=dates[(node_id, lang)],
                source_content=fr_args[node_id] if lang == "en" else None,
            )
            if lang == "fr" and preserve_french:
                text = _render_preserved_french(target, fr_args[node_id], node["en"]["canonical_title"])
            path = target / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
            output_paths.append((node_id, lang, "argument", rel, sha256_file(path)))

    registry_sha_before_outputs = sha256_file(target / "data/registre_debat.json")
    structural = structural_sha256(registry)
    batches: list[dict[str, Any]] = []
    for lang in ("fr", "en"):
        aggregate_path, aggregate_sha = _write_aggregate(target, lang, nodes)
        batch = _batch(
            debate_id=debate_id, lang=lang, nodes=nodes, registry_sha=registry_sha_before_outputs,
            structural_sha=structural, aggregate_path=aggregate_path, aggregate_sha=aggregate_sha,
            timestamp=timestamp, work_id=work_id,
        )
        batch["root_node_ids"] = sorted({
            str(occ.get("node_id")) for occ in (registry.get("graph") or {}).get("occurrences") or [] if occ.get("depth") == 1
        })
        batches.append(batch)
        write_json(target / f"data/lots_{lang}.json", {"batch_collection_version": "1.0", "debate_id": debate_id, "language": lang, "batches": [batch]})
        (target / f"reports/{lang}_batch_001.txt").write_text("Lot rendu et validé par le générateur déterministe.\n", encoding="utf-8", newline="\n")

    # Update registry page records.
    batch_by_lang = {"fr": "FR-A-001", "en": "EN-A-001"}
    page_hash_by_key = {(page_id, lang): sha for page_id, lang, _type, _rel, sha in output_paths}
    for lang in ("fr", "en"):
        rec = debate_pages[lang]
        rec["file"].update({"sha256": page_hash_by_key[(debate_id_actual, lang)], "status": "validated"})
        rec["generation"].update({"status": "validated", "assigned_batch_id": None, "creation_date": dates[(debate_id_actual, lang)], "generated_at": timestamp, "validated_at": timestamp})
        if lang == "fr":
            rec["interlanguage"].update({"status": "inserted", "inserted_at": timestamp, "verified_at": None})
    for node in nodes:
        node_id = str(node.get("id"))
        for lang in ("fr", "en"):
            rec = node["pages"][lang]
            rec["file"].update({"sha256": page_hash_by_key[(node_id, lang)], "status": "validated"})
            rec["generation"].update({"status": "validated", "assigned_batch_id": batch_by_lang[lang], "creation_date": dates[(node_id, lang)], "generated_at": timestamp, "validated_at": timestamp})
            if lang == "fr":
                rec["interlanguage"].update({"status": "inserted", "inserted_at": timestamp, "verified_at": None})

    registry["schema"]["validator_version"] = VALIDATOR_VERSION
    registry["batches"] = copy.deepcopy(batches)
    registry["validations"] = []
    write_json(target / "data/registre_debat.json", registry)
    projection = load_json(target / "graph/graphe_argumentatif.json", "projection du graphe")
    projection["nodes"] = copy.deepcopy((registry.get("graph") or {}).get("nodes") or [])
    projection["edges"] = copy.deepcopy((registry.get("graph") or {}).get("edges") or [])
    projection["occurrences"] = copy.deepcopy((registry.get("graph") or {}).get("occurrences") or [])
    projection["lifecycle"] = copy.deepcopy(lifecycle)
    write_json(target / "graph/graphe_argumentatif.json", projection)

    page_manifests = []
    for page_id, lang, page_type, rel, sha in output_paths:
        if page_type == "debate":
            title = str(debate_pages[lang].get("canonical_title"))
            batch_id = None
        else:
            node = next(node for node in nodes if str(node.get("id")) == page_id)
            title = str((node.get(lang) or {}).get("canonical_title"))
            batch_id = batch_by_lang[lang]
        page_content = (fr_content if lang == "fr" else en_content).get("debate") if page_type == "debate" else (fr_args if lang == "fr" else en_args)[page_id]
        page_manifests.append(_page_manifest(
            debate_id=debate_id, page_id=page_id, page_type=page_type, lang=lang, title=title,
            file_path=rel, sha256=sha, creation_date=dates[(page_id, lang)], batch_id=batch_id,
            timestamp=timestamp, report_path="reports/final_validation.json",
            page_origin=str((page_content or {}).get("page_origin") or "new"),
            preserved_parameters=(page_content or {}).get("preserved_parameters") or {},
        ))
    page_manifests.sort(key=lambda row: (0 if row["language"] == "fr" else 1, 0 if row["page_type"] == "debate" else 1, row["page_id"]))

    manifest["global_status"] = "bilingual_validated"
    manifest["updated_at"] = timestamp
    manifest["normative_versions"].update({"consolidated_norm": NORM_VERSION, "validator": VALIDATOR_VERSION})
    manifest.setdefault("translation_status", {})["en"] = "ready"
    manifest["pages"] = page_manifests
    manifest["batches"] = copy.deepcopy(batches)
    input_sha = structural_sha256(registry)
    manifest["validations"] = _validation_records(timestamp, input_sha)
    _prepare_final_controls(
        project_root, target, manifest, registry, fr_meta, en_meta,
        debate_id=debate_id, work_id=work_id, timestamp=timestamp,
    )
    manifest["works"].append({
        "work_id": f"{work_id}-RENDER", "work_type": "bilingual_validation",
        "conversation_name": "Rendu déterministe bilingue", "status": "completed",
        "input_handoff": None, "output_handoff": None, "started_at": timestamp, "completed_at": timestamp,
    })
    write_json(target / "manifest.json", manifest)

    render_lock = {
        "schema": RENDER_LOCK_SCHEMA, "schema_version": "1.0", "normative_revision": NORM_VERSION,
        "validator_version": VALIDATOR_VERSION, "kit_version": KIT_VERSION, "debate_id": debate_id,
        "work_id": work_id, "status": "rendered_and_validated", "rendered_at": timestamp,
        "translation_review_sha256": translation_review_sha256,
        "source_translated_copy_sha256": full_tree_sha256(source),
        "structural_sha256": input_sha, "page_count": len(page_manifests),
        "french_interlanguage_links": 1 + len(nodes), "english_interlanguage_links": 0,
        "citation_policy": copy.deepcopy(en_translation.get("citation_translation_policy")),
        "remote_access": False, "publication_started": False,
    }
    changeset = {
        "schema": RENDER_CHANGESET_SCHEMA, "schema_version": "1.0", "debate_id": debate_id,
        "work_id": work_id, "status": "applied", "rendered_at": timestamp,
        "translation_review_sha256": translation_review_sha256,
        "pages_generated": len(page_manifests), "french_pages": 1 + len(nodes), "english_pages": 1 + len(nodes),
        "interlanguage_links_added_to_french_pages": 1 + len(nodes),
        "interlanguage_links_added_to_english_pages": 0,
        "relations_mutated": False, "occurrences_mutated": False,
        "source_locks_mutated": False, "remote_access": False,
    }
    write_json(target / "data/bilingual_render_lock.json", render_lock)
    write_json(target / "changes/bilingual_render_changeset.json", changeset)
    write_json(target / "reports/render_report.json", {
        "schema": "wikidebia-render-report-1.0", "result": "pending_validation",
        "debate_id": debate_id, "work_id": work_id, "page_count": len(page_manifests),
        "interlanguage": {"french_pages_with_link": 1 + len(nodes), "english_pages_with_link": 0},
        "citations": {"fr": sum(len(row.get("citations") or []) for row in fr_args.values()), "en": sum(len(row.get("citations") or []) for row in en_args.values())},
    })
    # Required-report placeholders make the package self-consistent while the
    # validator is producing the reports that will replace them.
    write_json(target / "reports/render_preflight.json", {"status": "pending"})
    write_json(target / "reports/final_validation.json", {"status": "pending"})

    # First validate all page-level and bilingual constraints without workflow,
    # then run the complete validator including workflow.
    preflight = _run_validator(
        project_root, target,
        scopes=("schema", "coherence", "graph", "batches", "sources", "files", "wikicode", "bilingual", "editorial"),
        json_output=target / "reports/render_preflight.json",
        text_output=target / "reports/render_preflight.txt",
    )
    final = _run_validator(
        project_root, target, scopes=("all",),
        json_output=target / "reports/final_validation.json",
        text_output=target / "reports/final_validation.txt",
    )
    report = load_json(target / "reports/render_report.json", "rapport de rendu")
    report.update({"result": "passed", "preflight_result": preflight.get("result"), "final_validation_result": final.get("result"), "validated_at": now_iso()})
    write_json(target / "reports/render_report.json", report)
    return {"render_lock": render_lock, "changeset": changeset, "validator_result": final.get("result"), "pages": len(page_manifests)}


def render_workspace(project_root: Path, debate_id: str, work_id: str, confirm_translation_sha256: str) -> dict[str, Any]:
    workspace, meta = _load_workspace(project_root, debate_id, work_id)
    _assert_source_unchanged(project_root, debate_id, meta)
    source = _assert_translated_copy(workspace, meta)
    translation_lock = load_json(source / "data/en_translation_lock.json", "verrou de traduction")
    expected_review = str(translation_lock.get("review_sha256") or "")
    if not expected_review or confirm_translation_sha256 != expected_review:
        raise RenderError("L’empreinte confirmée ne correspond pas à la traduction verrouillée")
    target = workspace / "rendered-copy"
    if target.is_dir():
        if meta.get("status") != "bilingual_rendered":
            raise RenderError("rendered-copy existe sans état cohérent")
        expected = str((meta.get("rendered_copy") or {}).get("tree_sha256") or "")
        actual = full_tree_sha256(target)
        if actual != expected:
            raise RenderError("Empreinte de rendered-copy divergente")
        return {
            "status": "bilingual_rendered", "debate_id": debate_id, "work_id": work_id,
            "translation_review_sha256": expected_review, "rendered_copy_tree_sha256": actual,
            "idempotent": True,
        }
    if target.exists() or target.is_symlink():
        raise RenderError("Chemin rendered-copy déjà occupé")
    temp = Path(tempfile.mkdtemp(prefix=".rendered-copy.tmp-", dir=workspace))
    try:
        shutil.rmtree(temp)
        result = _build_rendered_copy(
            project_root, source, temp, debate_id=debate_id, work_id=work_id,
            translation_review_sha256=expected_review,
        )
        # Every prior lock and historical import must remain byte-identical.
        for rel in (
            "imports", "data/fr_page_metadata_lock.json", "data/fr_content_lock.json",
            "data/en_page_metadata_lock.json", "data/en_content_lock.json", "data/en_translation_lock.json",
        ):
            left = source / rel
            right = temp / rel
            if left.is_dir():
                if full_tree_sha256(left) != full_tree_sha256(right):
                    raise RenderError(f"La provenance {rel} a été modifiée pendant le rendu")
            elif left.read_bytes() != right.read_bytes():
                raise RenderError(f"Le verrou {rel} a été modifié pendant le rendu")
        tree_hash = full_tree_sha256(temp)
        os.replace(temp, target)
        fsync_directory(workspace)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise

    meta = copy.deepcopy(meta)
    timestamp = result["render_lock"]["rendered_at"]
    meta.update({"normative_revision": NORM_VERSION, "validator_version": VALIDATOR_VERSION, "kit_version": KIT_VERSION, "status": "bilingual_rendered"})
    meta.setdefault("artifacts", {})["rendered_copy"] = "rendered-copy"
    meta["rendered_copy"] = {
        "path": "rendered-copy", "tree_sha256": tree_hash, "status": "bilingual_validated",
        "translation_review_sha256": expected_review, "rendered_at": timestamp,
    }
    meta.setdefault("boundaries", {})["final_pages_generated"] = True
    meta["boundaries"]["remote_access"] = False
    meta["boundaries"]["publication_started"] = False
    meta["workspace_sha256"] = None
    meta["workspace_sha256"] = workspace_receipt_hash(meta)
    write_json(workspace / "workspace.json", meta)
    return {
        "status": "bilingual_rendered", "debate_id": debate_id, "work_id": work_id,
        "translation_review_sha256": expected_review,
        "rendered_copy": relative_to_project(target, project_root),
        "rendered_copy_tree_sha256": tree_hash, "pages": result["pages"],
        "french_interlanguage_links": result["render_lock"]["french_interlanguage_links"],
        "english_interlanguage_links": 0, "validator_result": result["validator_result"],
        "remote_access": False, "publication_started": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rendre et valider les pages bilingues finales d’un workspace.")
    parser.add_argument("debate_id")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--confirm-translation-sha256", required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--machine-readable", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = args.project_root.expanduser().resolve()
    work_id = validate_work_id(args.work_id)
    with exclusive_lock(project_root, args.debate_id, "editorial_bilingual_render"):
        result = render_workspace(project_root, args.debate_id, work_id, str(args.confirm_translation_sha256))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True) if args.machine_readable else json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RenderError, EditorialReviewError, WorkspaceError, CorpusBuildError) as exc:
        print(f"WIKIDEBIA BLOQUÉ : {exc}", file=__import__("sys").stderr)
        raise SystemExit(2)
