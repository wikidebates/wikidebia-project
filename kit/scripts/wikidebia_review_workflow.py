#!/usr/bin/env python3
"""High-level orchestration for editorial workflows with ChatGPT review handoffs.

The low-level commands remain authoritative primitives. This module only chains
mechanical transitions, creates minimal review packages, validates their return,
and stops at genuine editorial decision points.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping, Sequence

from wikidebia_release_info import KIT_VERSION, NORM_VERSION, VALIDATOR_VERSION
from wikidebia_corpus_build import (
    REVIEW_ENVELOPE,
    PLACEMENT_REVIEW,
    GRAPH_CORRECTION_REVIEW,
    GRAPH_TITLE_REVIEW,
    build_payload_sha256,
    full_tree_sha256,
    load_json,
    now_iso,
    resolve_build,
    review_sha256 as graph_review_sha256,
    validate_debate_id,
    write_json,
)
from wikidebia_corpus_init import (
    build_corpus, canonical_debate_id, derive_short_code, validate_short_code,
    run_validator as run_initial_validator,
)
from wikidebia_corpus_review import make_review_template, finalize_review as finalize_graph_review
from wikidebia_graph_correction import make_correction_template as make_graph_correction_template, apply_correction as apply_graph_correction
from wikidebia_graph_actions import (
    execute_review_actions as execute_graph_review_actions,
    apply_review_actions_locally as apply_graph_review_actions_locally,
    extract_actions_from_review,
    repair_graph_action_import_provenance,
)
from wikidebia_corpus_promote import promote as promote_graph
from wikidebia_editorial_workspace import (
    create_workspace, validate_work_id, workspace_receipt_hash, next_work_id,
    page_review_item, read_import_metadata, fallback_map,
)
from wikidebia_editorial_review import (
    finalize_title_review,
    apply_title_review,
    review_sha256 as metadata_review_sha256,
)
from wikidebia_content_review import (
    prepare_review as prepare_content_review,
    finalize_review as finalize_content_review,
    apply_review as apply_content_review,
    content_review_sha256,
    normalize_historical_review_document,
    collect_historical_change_requests,
    HISTORICAL_AUTHORIZATION_SCHEMA,
    HISTORICAL_AUTHORIZATION_PATH,
)
from wikidebia_translation_review import (
    prepare_review as prepare_translation_review,
    finalize_review as finalize_translation_review,
    apply_review as apply_translation_review,
    translation_review_sha256,
    collect_english_title_format_findings,
    collect_english_documentary_findings,
)
from wikidebia_semantic_convergence import record_pass as record_semantic_pass
from wikidebia_render import render_workspace
from wikidebia_release import release_workspace
from wikidebia_final_publication import publish_final_release, FinalPublicationError
from wikidebia_french_checkpoint import publish_checkpoint, FrenchCheckpointError

# Compatibility aliases: the historical CLI/tests used the metadata names.
# Their semantics are now title-only; classification moved to the content review.
finalize_metadata_review = finalize_title_review
apply_metadata_review = apply_title_review

PACKAGE_SCHEMA = "wikidebia-chatgpt-review-package-1.0"
WORKFLOW_SCHEMA = "wikidebia-editorial-orchestration-1.0"
SEMANTIC_RESPONSE_SCHEMA = "wikidebia-semantic-review-response-1.0"
DIAGNOSTIC_SCHEMA = "wikidebia-workflow-diagnostic-package-1.0"
ALLOWED_METHOD_FAMILIES = {
    "proposition_by_proposition",
    "risk_marker_review",
    "reverse_source_target",
    "field_boundary_review",
    "independent_bilingual_reread",
}


@dataclass(frozen=True)
class ReviewTypeSpec:
    key: str
    label: str
    user_message: str


REVIEW_TYPES: dict[str, ReviewTypeSpec] = {
    "graph_review": ReviewTypeSpec("graph_review", "Revue du graphe, des positions et des titres", "Revue du graphe et des titres préparée."),
    "graph_correction": ReviewTypeSpec("graph_correction", "Correction du graphe après rejet", "Correction du graphe préparée."),
    "fr_metadata_review": ReviewTypeSpec("fr_metadata_review", "Revue du graphe et des titres français", "Revue des titres canoniques et affichés préparée."),
    "fr_content_review": ReviewTypeSpec("fr_content_review", "Revue du contenu français, des rubriques et des mots-clés", "Revue du contenu français préparée."),
    "en_translation_review": ReviewTypeSpec("en_translation_review", "Traduction et revue documentaire anglaises", "Revue de traduction anglaise préparée."),
    "en_translation_correction": ReviewTypeSpec("en_translation_correction", "Correction de traduction après convergence sémantique", "Correction de traduction anglaise préparée."),
    "en_documentation_correction": ReviewTypeSpec("en_documentation_correction", "Correction documentaire anglaise après préflight", "Correction documentaire anglaise préparée."),
    "semantic_convergence_1": ReviewTypeSpec("semantic_convergence_1", "Première passe de convergence sémantique", "Première passe de convergence sémantique préparée."),
    "semantic_convergence_2": ReviewTypeSpec("semantic_convergence_2", "Deuxième passe indépendante de convergence sémantique", "Deuxième passe de convergence sémantique préparée."),
}


class WorkflowError(RuntimeError):
    pass


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_zip_name(name: str) -> bool:
    pure = PurePosixPath(name)
    return not pure.is_absolute() and ".." not in pure.parts and not (len(name) >= 2 and name[1] == ":")


def _assert_regular_file(path: Path, label: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise WorkflowError(f"{label} absent ou non régulier : {path}")


def _workflow_root(project_root: Path, debate_id: str) -> Path:
    return project_root / ".state" / "workflows" / debate_id


def _workflow_path(project_root: Path, debate_id: str) -> Path:
    return _workflow_root(project_root, debate_id) / "workflow.json"


def _load_workflow(project_root: Path, debate_id: str) -> dict[str, Any]:
    path = _workflow_path(project_root, debate_id)
    if not path.is_file():
        raise WorkflowError(f"Workflow introuvable pour {debate_id}")
    data = load_json(path, "workflow")
    if data.get("schema") != WORKFLOW_SCHEMA or data.get("debate_id") != debate_id:
        raise WorkflowError("Identité ou schéma du workflow invalide")
    return data


def _save_workflow(project_root: Path, state: Mapping[str, Any]) -> None:
    path = _workflow_path(project_root, str(state["debate_id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, dict(state))


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _relative_or_external(path: Path, root: Path) -> str:
    try:
        return _relative(path, root)
    except ValueError:
        return f"external:{path.name}"


def _workspace_path(project_root: Path, debate_id: str, work_id: str) -> Path:
    return project_root / ".state" / "editorial-workspaces" / debate_id / work_id


def _current_workspace_meta(project_root: Path, state: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
    work_id = str(state.get("work_id") or "")
    if not work_id:
        raise WorkflowError("Le workflow n'a pas encore de work_id")
    workspace = _workspace_path(project_root, str(state["debate_id"]), work_id)
    meta = load_json(workspace / "workspace.json", "workspace")
    return workspace, meta


def _copy_context_files(base: Path, explicit: Iterable[str], globs: Iterable[str]) -> list[Path]:
    found: dict[str, Path] = {}
    for rel in explicit:
        p = base / rel
        if not p.is_file() or p.is_symlink():
            raise WorkflowError(f"Fichier de contexte requis absent : {rel}")
        found[p.relative_to(base).as_posix()] = p
    for pattern in globs:
        for p in base.glob(pattern):
            if p.is_file() and not p.is_symlink():
                found[p.relative_to(base).as_posix()] = p
    return [found[key] for key in sorted(found)]


def _instructions(review_type: str, debate_id: str, work_id: str | None, editable: Sequence[str]) -> str:
    spec = REVIEW_TYPES.get(review_type)
    lines = [
        f"# {spec.label if spec else review_type}",
        "",
        f"Débat : `{debate_id}`",
    ]
    if work_id:
        lines.append(f"Work : `{work_id}`")
    lines += [
        "",
        "Ce paquet a été préparé par Wikidéb’IA pour une intervention éditoriale externe.",
        "Ne modifiez que les fichiers placés sous `editable/`. Les fichiers sous `context/` sont des sources en lecture seule.",
        "Ne renommez, n'ajoutez et ne supprimez aucun fichier du ZIP.",
        "Le fichier `REVIEW_PACKAGE.json` ne doit jamais être modifié.",
    ]
    if review_type == "graph_review":
        lines += [
            "",
            "Cette revue couvre en une seule étape les positions/relations du graphe, les suppressions/fusions/déplacements éventuels, les titres canoniques et les titres affichés.",
            "Complétez aussi `reviews/fr/graph_title_review.json` pour tous les titres ; les rubriques, mots-clés, résumés et références restent hors de cette première revue.",
            "Si la revue exige une modification structurelle, renseignez pour l'occurrence concernée l'objet `correction`.",
            "Actions prises en charge : `remove`, `merge_redirect`, `move` et `relation_change`.",
            "Pour `merge_redirect`, indiquez `target_node_id` : la page doublon deviendra `#REDIRECTION [[Titre de destination]]` et son lien sera retiré de la page mère.",
            "Si le doublon intervient dans une autre branche qui doit conserver sa relation, ajoutez `preserve_parent_relation=true` : la cible du lien est remplacée, son titre affiché et sa position sont conservés, et le nœud retenu est réutilisé.",
            "Pour `remove`, indiquez `page_disposition=delete` : le lien sera retiré de la page mère avant suppression de la page.",
            "Les décisions structurelles sont d’abord appliquées localement au graphe puis soumises à une nouvelle revue complète. Aucune page distante n’est modifiée pendant cette boucle.",
            "Après réimport approuvé de ce même ZIP, toutes les mutations structurelles et de titres validées sont publiées immédiatement au premier checkpoint français, avec un résumé MediaWiki individualisé par page.",
            "Pour un doublon, le résumé de la page mère mentionne la page conservée sous la forme `[[Titre de destination]]`.",
        ]
    if review_type == "fr_metadata_review":
        lines += [
            "",
            "Cette revue clôt le premier ensemble français : graphe + titres. Elle porte exclusivement sur les titres canoniques / noms de pages et les titres affichés.",
            "Pour un Argument préexistant du wiki, conservez par défaut `titre-affiché`, même s’il est nominal ou non propositionnel. Ne le modifiez que pour une faute ou un problème flagrant, ou sur décision explicite du propriétaire.",
            "Le titre canonique / nom de page reste à corriger lorsqu’il est incomplet, contextuel, ambigu ou fautif.",
            "Un renommage canonique modifie les cibles `page=`, sans recopier le nouveau nom dans `titre-affiché`. Un libellé court, nominal ou sans verbe se conserve : ces seules caractéristiques ne constituent pas un défaut d’une page existante.",
            "Ne modifiez pas ici les rubriques ni les mots-clés : ils seront revus et publiés avec le contenu au second checkpoint français.",
            "Après réimport validé, Wikidéb’IA publie automatiquement les changements structurels et de titres sur le wiki français avant de préparer la revue de contenu.",
        ]
    if review_type == "graph_correction":
        lines += [
            "",
            "Cette phase corrige le graphe après une revue rejetée. Elle ne constitue pas une approbation du graphe.",
            "Modifiez uniquement les placements nécessaires à partir des motifs de rejet présents dans le contexte.",
            "Renseignez le statut `corrected`, le relecteur, la date de revue et les notes dans le fichier de correction.",
            "Après réimport, Wikidéb’IA reconstruira et validera mécaniquement le graphe puis préparera une nouvelle revue complète.",
        ]
    if review_type == "fr_content_review":
        lines += [
            "",
            "Cette revue porte sur les rubriques, mots-clés, documentation et autres contenus explicitement ouverts à la reprise.",
            "Sur une page française préexistante, conservez les rubriques historiques autant que possible. Une correction (ajout/retrait) reste admise lorsqu’elle améliore réellement la classification ; consignez-la dans `preexisting_rubrique_change_rationale`. Le seul dépassement du profil 1–3/4 rubriques n’est pas un motif de correction.",
            "Les quotas de mots-clés (2–4 pour un Argument, 5–8 pour un Débat) sont des profils de création et ne justifient jamais la suppression d’un mot-clé historique. En revanche, les règles qualitatives intrinsèques restent applicables : un mauvais mot-clé historique peut être corrigé, remplacé ou décomposé via `preexisting_keyword_corrections` avec une justification explicite.",
            "Pour toute page préexistante importée du wiki, l’introduction du débat et les résumés des arguments sont préservés par défaut ; un résumé historiquement absent reste absent par défaut.",
            "Vous pouvez signaler une anomalie et remplir `suggested_change` sans appliquer la suggestion : conservez alors `decision=keep`, `historical_text_status=preserved` et la valeur historique dans `proposed_*`.",
            "Si le propriétaire a explicitement approuvé un changement, renseignez `decision=change`, la valeur finale dans `proposed_*`, `historical_text_status=authorization_requested` et un objet `historical_change_request` limité à ce champ, avec `field_key`, `final_value`, `change_type`, `rationale` et `owner_instruction_reference`.",
            "Pour une introduction modifiée structurellement, ajoutez de préférence `change_scope` avec le delta exact des sous-parties (`added`, `modified`, `removed`, `reordered`). Ainsi une autorisation d’ajouter `Enjeux du débat` ne peut pas couvrir silencieusement une réécriture d’une autre sous-partie historique. Une réécriture explicitement large peut utiliser une portée `whole_field`.",
            "Après autorisation, l’introduction ou le résumé final proposé devient la valeur éditoriale effective : tous les contrôles structurels, le verrou, le changeset, le rendu, le checkpoint 2 et la traduction doivent utiliser cette valeur finale. Les règles de création restent différentielles et ne s’appliquent qu’aux portions réellement ajoutées ou réécrites.",
            "Une simple déclaration dans le ZIP ne vaut jamais consentement : sans preuve locale, `review-import` bloque. Après accord explicite du propriétaire, utilisez `./wikidebia review-import --authorize-historical-changes` (avec l’identifiant du débat seulement si nécessaire). Le kit scelle alors localement le ZIP exact et les SHA avant/après de chaque champ demandé.",
            "N’étendez jamais une autorisation à un autre résumé ou à l’introduction entière si la décision propriétaire ne le couvre pas. Une correction locale autorisée ne déclenche pas rétroactivement toutes les préférences stylistiques de création.",
            "Le checkpoint français n°2 publie normalement les rubriques, mots-clés, documentation et, lorsqu’ils sont autorisés, les deltas d’introduction/résumé ; aucune troisième frontière française n’est créée.",
        ]
    if review_type in {"en_translation_review", "en_translation_correction", "en_documentation_correction"}:
        lines += [
            "",
            "Distinguez `page_origin` (cycle de vie de la page anglaise cible) de `source_page_origin` (provenance éditoriale de la source française). Ne modifiez jamais `source_page_origin` : il est dérivé des verrous français.",
            "La traduction respecte la forme du `titre-affiché` français validé, quelle que soit sa provenance : un libellé court ou nominal reste traduisible comme tel. Les exigences de génération (longueur, verbe, proposition complète, gain de concision) ne justifient aucune réécriture de la source ni aucun allongement de sa traduction. Vérifiez uniquement la fidélité et les dégradations introduites par la traduction.",
            "Lorsque `source_page_origin=preexisting`, ne ramenez pas les keywords historiques aux quotas de création et ne transformez pas un `displayed-title` historique nominal en proposition pour satisfaire une préférence de génération. Traduisez la classification et les mots-clés français finalement validés dans le même ordre conceptuel.",
            "Les règles qualitatives intrinsèques des keywords restent applicables : la version anglaise doit utiliser les équivalents idiomatiques du vocabulaire français final, y compris après une correction ou une décomposition historique validée.",
            "Pour une introduction française historique, produisez une adaptation anglaise autonome : examinez explicitement le contexte franco-français et condensez, contextualisez ou omettez ce qui ne doit pas être traduit mécaniquement, sans changer la substance du débat. `Stakes of the debate` et les autres contraintes de profil d’une introduction nouvellement créée ne sont pas obligatoires pour les sous-parties historiques inchangées.",
            "Pour un résumé historique, un ratio EN/FR hors 0,60–1,45 est un signal de revue et non un objectif de réécriture ; attestez l’équivalence et fournissez `summary_ratio_exception_rationale` lorsque le ratio reste hors plage.",
            "Dans tous les titres anglais, utilisez exclusivement l’apostrophe droite ASCII `'` pour les possessifs et contractions. Les apostrophes typographiques `’`, `‘`, `ʼ` ou `＇` sont non conformes, y compris dans la traduction d’un titre historique.",
            "Pour toute nouvelle source ajoutée dans `data/sources_en_working.json`, renseignez `verification.verified_at`, `verification.primary_source` (booléen explicite) et `verification.notes` en plus des attestations de langue/auteur. Les anciennes clés `checked_at`, `method` et `note` ne doivent plus être émises par un nouveau paquet ; elles restent lisibles uniquement pour compatibilité avec une revue déjà préparée.",
            "Toute référence bibliographique utilisée sur la page Debate doit renseigner `document_kind` et, dans l’usage Debate, `documentary_scope=foundational_work` ou `broad_synthesis`, avec une justification de sélection spécifique. Une source trop étroite doit être retirée de la bibliographie générale plutôt que requalifiée artificiellement.",
            "Pour une source Web ou vidéo ayant un auteur, renseignez `verification.authorship_verified=true` uniquement après vérification explicite. Si `authors` reproduit le nom du site, revérifiez l’attribution : omettez l’auteur lorsqu’aucune responsabilité distincte n’est créditée au lieu de recopier mécaniquement le site.",
        ]
    if review_type == "en_documentation_correction":
        lines += [
            "",
            "Cette correction est strictement documentaire. Ne modifiez aucun titre, résumé, champ Debate, section, keyword, citation ou preuve sémantique.",
            "Corrigez uniquement `data/sources_en_working.json` selon l’inventaire présent dans `context/reviews/en/semantic_convergence_findings.json`.",
            "Le paquet rend `translation_review.json` en lecture seule. Après réimport, Wikidéb’IA refinalise la revue avec les mêmes valeurs sémantiques et redémarre la convergence parce que le reçu précédent était lié à l’ancienne empreinte complète de revue.",
        ]
    lines += [
        "",
        "## Fichiers à compléter",
        "",
    ]
    lines.extend(f"- `{path}`" for path in editable)
    lines += [
        "",
        "Après la revue, rendez un ZIP conservant exactement la même structure, placez-le dans `incoming/`, puis lancez `./wikidebia review-import`. S'il y a plusieurs ZIP de revue dans `incoming/`, utilisez `./wikidebia review-import <debate_id>`.",
        "",
    ]
    return "\n".join(lines)


def _package_manifest_hash(manifest: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(manifest))
    body.pop("manifest_sha256", None)
    return _sha256_bytes(_canonical_json(body))


def _write_deterministic_zip(staging: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for p in sorted((x for x in staging.rglob("*") if x.is_file()), key=lambda x: x.relative_to(staging).as_posix()):
            rel = p.relative_to(staging).as_posix()
            info = zipfile.ZipInfo(rel, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, p.read_bytes())


def create_review_package(
    project_root: Path,
    state: dict[str, Any],
    *,
    review_type: str,
    base: Path,
    editable_paths: Sequence[str],
    context_paths: Sequence[str],
    context_globs: Sequence[str] = (),
    counts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if review_type not in REVIEW_TYPES:
        raise WorkflowError(f"Type de revue non enregistré : {review_type}")
    debate_id = str(state["debate_id"])
    work_id = state.get("work_id")
    pending = state.get("pending_review")
    if isinstance(pending, dict) and pending.get("review_type") == review_type:
        existing = project_root / str(pending.get("package_path") or "")
        if existing.is_file() and _sha256_file(existing) == pending.get("archive_sha256"):
            return dict(pending)
        raise WorkflowError("Le paquet de revue en attente a disparu ou a été altéré")

    editable_abs: list[Path] = []
    for rel in editable_paths:
        p = base / rel
        _assert_regular_file(p, f"Fichier éditable {rel}")
        editable_abs.append(p)
    context_abs = _copy_context_files(base, context_paths, context_globs)
    editable_set = {p.resolve() for p in editable_abs}
    context_abs = [p for p in context_abs if p.resolve() not in editable_set]

    package_id = str(uuid.uuid4())
    outgoing = project_root / "outgoing"
    filename = f"{debate_id}_{review_type}.zip"
    target = outgoing / filename
    staging = Path(tempfile.mkdtemp(prefix=f".{debate_id}-{review_type}-", dir=str(outgoing) if outgoing.is_dir() else None))
    try:
        if staging.parent != outgoing and not outgoing.exists():
            outgoing.mkdir(parents=True, exist_ok=True)
            shutil.rmtree(staging)
            staging = Path(tempfile.mkdtemp(prefix=f".{debate_id}-{review_type}-", dir=outgoing))
        editable_entries = []
        context_entries = []
        for source in editable_abs:
            target_rel = source.relative_to(base).as_posix()
            package_rel = f"editable/{target_rel}"
            dest = staging / package_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            editable_entries.append({
                "package_path": package_rel,
                "target_path": target_rel,
                "sha256_at_prepare": _sha256_file(source),
            })
        for source in context_abs:
            target_rel = source.relative_to(base).as_posix()
            package_rel = f"context/{target_rel}"
            dest = staging / package_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            context_entries.append({
                "package_path": package_rel,
                "target_path": target_rel,
                "sha256": _sha256_file(source),
            })
        source_anchor = full_tree_sha256(base) if base.is_dir() else None
        manifest = {
            "schema": PACKAGE_SCHEMA,
            "schema_version": "1.0",
            "package_id": package_id,
            "review_type": review_type,
            "debate_id": debate_id,
            "work_id": work_id,
            "normative_revision": NORM_VERSION,
            "validator_version": VALIDATOR_VERSION,
            "kit_version": KIT_VERSION,
            "prepared_at": now_iso(),
            "source_anchor_sha256": source_anchor,
            "editable_files": editable_entries,
            "context_files": context_entries,
            "counts": dict(counts or {}),
            "manifest_sha256": None,
        }
        instructions = _instructions(review_type, debate_id, str(work_id) if work_id else None, [x["package_path"] for x in editable_entries])
        manifest["instructions_sha256"] = _sha256_bytes(instructions.encode("utf-8"))
        manifest["manifest_sha256"] = _package_manifest_hash(manifest)
        write_json(staging / "REVIEW_PACKAGE.json", manifest)
        (staging / "INSTRUCTIONS.md").write_text(instructions, encoding="utf-8", newline="\n")
        _write_deterministic_zip(staging, target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    pending_record = {
        "package_id": package_id,
        "review_type": review_type,
        "package_path": _relative(target, project_root),
        "archive_sha256": _sha256_file(target),
        "manifest_sha256": manifest["manifest_sha256"],
        "base_path": _relative(base, project_root),
        "work_id": work_id,
        "created_at": manifest["prepared_at"],
        "counts": dict(counts or {}),
    }
    state["status"] = "awaiting_review"
    state["pending_review"] = pending_record
    state["updated_at"] = now_iso()
    _save_workflow(project_root, state)
    return pending_record


def _read_returned_package(archive: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    if not archive.is_file():
        raise WorkflowError(f"ZIP de revue introuvable : {archive}")
    files: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(archive) as bundle:
            seen: set[str] = set()
            for info in bundle.infolist():
                name = PurePosixPath(info.filename).as_posix()
                if not _safe_zip_name(name) or name in seen:
                    raise WorkflowError(f"Entrée ZIP dangereuse ou dupliquée : {info.filename}")
                seen.add(name)
                mode = (info.external_attr >> 16) & 0o170000
                if mode == stat.S_IFLNK:
                    raise WorkflowError(f"Lien symbolique interdit dans le ZIP : {name}")
                if info.is_dir():
                    continue
                files[name] = bundle.read(info)
    except zipfile.BadZipFile as exc:
        raise WorkflowError("Archive de revue invalide") from exc
    if "REVIEW_PACKAGE.json" not in files or "INSTRUCTIONS.md" not in files:
        raise WorkflowError("Le ZIP ne contient pas le manifeste de revue attendu")
    try:
        manifest = json.loads(files["REVIEW_PACKAGE.json"].decode("utf-8"))
    except Exception as exc:
        raise WorkflowError("REVIEW_PACKAGE.json est illisible") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != PACKAGE_SCHEMA or manifest.get("schema_version") != "1.0":
        raise WorkflowError("Schéma de paquet de revue non pris en charge")
    if manifest.get("manifest_sha256") != _package_manifest_hash(manifest):
        raise WorkflowError("REVIEW_PACKAGE.json a été modifié ou corrompu")
    if _sha256_bytes(files["INSTRUCTIONS.md"]) != manifest.get("instructions_sha256"):
        raise WorkflowError("INSTRUCTIONS.md a été modifié; seuls les fichiers sous editable/ peuvent changer")
    allowed = {"REVIEW_PACKAGE.json", "INSTRUCTIONS.md"}
    allowed.update(str(x.get("package_path")) for x in manifest.get("editable_files") or [])
    allowed.update(str(x.get("package_path")) for x in manifest.get("context_files") or [])
    extras = set(files) - allowed
    missing = allowed - set(files)
    if extras:
        raise WorkflowError(f"Fichiers non autorisés dans le ZIP : {sorted(extras)[:5]}")
    if missing:
        raise WorkflowError(f"Fichiers manquants dans le ZIP : {sorted(missing)[:5]}")
    for row in manifest.get("context_files") or []:
        name = str(row.get("package_path"))
        if _sha256_bytes(files[name]) != row.get("sha256"):
            raise WorkflowError(f"Un fichier de contexte en lecture seule a été modifié : {name}")
    return manifest, files


def _atomic_restore_dir(target: Path, backup: Path) -> None:
    failed = target.with_name(target.name + ".failed-import")
    shutil.rmtree(failed, ignore_errors=True)
    if target.exists():
        os.replace(target, failed)
    os.replace(backup, target)
    shutil.rmtree(failed, ignore_errors=True)


def _direct_children(path: Path) -> set[str]:
    if not path.is_dir():
        return set()
    return {child.name for child in path.iterdir()}


def _french_checkpoint_stage_for_review(review_type: str) -> str | None:
    if review_type in {"graph_review", "fr_metadata_review"}:
        return "graph"
    if review_type == "fr_content_review":
        return "content"
    return None


def _capture_import_transaction(
    project_root: Path, debate_id: str, *, work_id: str | None = None, review_type: str = ""
) -> dict[str, Any]:
    workflow_path = _workflow_path(project_root, debate_id)
    fr_root = project_root / ".state" / "fr-publication" / debate_id
    stage = _french_checkpoint_stage_for_review(review_type)
    normalized_work_id = str(work_id or "").strip()
    fr_stage = fr_root / normalized_work_id / stage if normalized_work_id and stage else None
    transaction_temp_root: Path | None = None
    fr_stage_backup: Path | None = None
    fr_stage_existed = bool(fr_stage and fr_stage.is_dir() and not fr_stage.is_symlink())
    if fr_stage_existed and fr_stage is not None:
        temp_parent = project_root / ".state" / "review-import-transactions"
        temp_parent.mkdir(parents=True, exist_ok=True)
        transaction_temp_root = Path(tempfile.mkdtemp(prefix=f"{debate_id}-", dir=temp_parent))
        fr_stage_backup = transaction_temp_root / "fr-publication-stage"
        shutil.copytree(fr_stage, fr_stage_backup, symlinks=False)
    return {
        "workflow_bytes": workflow_path.read_bytes(),
        "build_existed": (project_root / ".state" / "corpus-builds" / debate_id).is_dir(),
        "corpus_existed": (project_root / "corpus" / debate_id).is_dir(),
        "editorial_root_existed": (project_root / ".state" / "editorial-workspaces" / debate_id).is_dir(),
        "editorial_children": _direct_children(project_root / ".state" / "editorial-workspaces" / debate_id),
        "promotion_root_existed": (project_root / ".state" / "corpus-promotions" / debate_id).is_dir(),
        "promotion_children": _direct_children(project_root / ".state" / "corpus-promotions" / debate_id),
        "release_root_existed": (project_root / ".state" / "corpus-releases" / debate_id).is_dir(),
        "release_children": _direct_children(project_root / ".state" / "corpus-releases" / debate_id),
        "outgoing_root_existed": (project_root / "outgoing").is_dir(),
        "outgoing_children": _direct_children(project_root / "outgoing"),
        "fr_publication_root_existed": fr_root.is_dir(),
        "fr_publication_children": _direct_children(fr_root),
        "fr_publication_work_id": normalized_work_id or None,
        "fr_publication_stage": stage,
        "fr_publication_stage_existed": fr_stage_existed,
        "fr_publication_stage_backup": str(fr_stage_backup) if fr_stage_backup is not None else None,
        "transaction_temp_root": str(transaction_temp_root) if transaction_temp_root is not None else None,
    }


def _is_persistent_validation_diagnostic(path: Path) -> bool:
    """Return True only for a complete, self-identifying validation diagnostic ZIP.

    review-import rolls local/mechanical work back on failure, but diagnostics are
    deliberately user-facing evidence of that failure and must survive the
    transaction cleanup.  Filename matching alone is not sufficient: require the
    diagnostic manifest and schema before exempting a new file from rollback.
    """
    if not path.is_file() or path.is_symlink() or not path.name.endswith("_diagnostic.zip"):
        return False
    try:
        with zipfile.ZipFile(path) as bundle:
            payload = json.loads(bundle.read("DIAGNOSTIC_PACKAGE.json").decode("utf-8"))
    except Exception:
        return False
    return (
        isinstance(payload, dict)
        and payload.get("schema") == DIAGNOSTIC_SCHEMA
        and payload.get("schema_version") == "1.0"
        and int(payload.get("error_count") or 0) > 0
    )


def _remove_new_children(
    path: Path, before: set[str], existed_before: bool, *, preserve: Callable[[Path], bool] | None = None
) -> None:
    if not path.exists():
        return
    if not path.is_dir() or path.is_symlink():
        return
    for child in list(path.iterdir()):
        if child.name in before:
            continue
        if preserve is not None and preserve(child):
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)
    if not existed_before:
        try:
            path.rmdir()
        except OSError:
            pass


def _cleanup_import_transaction_snapshot(snapshot: Mapping[str, Any]) -> None:
    temp_root = str(snapshot.get("transaction_temp_root") or "").strip()
    if temp_root:
        shutil.rmtree(Path(temp_root), ignore_errors=True)


def _restore_french_publication_stage(
    project_root: Path, debate_id: str, snapshot: Mapping[str, Any]
) -> None:
    fr_root = project_root / ".state" / "fr-publication" / debate_id
    work_id = str(snapshot.get("fr_publication_work_id") or "").strip()
    stage = str(snapshot.get("fr_publication_stage") or "").strip()
    if work_id and stage:
        stage_path = fr_root / work_id / stage
        if stage_path.exists():
            if stage_path.is_dir() and not stage_path.is_symlink():
                shutil.rmtree(stage_path)
            else:
                stage_path.unlink(missing_ok=True)
        if bool(snapshot.get("fr_publication_stage_existed")):
            backup_value = str(snapshot.get("fr_publication_stage_backup") or "").strip()
            backup_path = Path(backup_value) if backup_value else None
            if backup_path is None or not backup_path.is_dir():
                raise WorkflowError("Sauvegarde transactionnelle du checkpoint français introuvable")
            stage_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(backup_path, stage_path, symlinks=False)
        work_root = fr_root / work_id
        if work_root.is_dir() and not any(work_root.iterdir()):
            work_root.rmdir()
    _remove_new_children(
        fr_root,
        set(snapshot.get("fr_publication_children") or set()),
        bool(snapshot.get("fr_publication_root_existed")),
    )


def _rollback_import_transaction(
    project_root: Path, debate_id: str, base: Path, backup: Path, snapshot: Mapping[str, Any]
) -> None:
    """Restore a local review import if the following mechanical transition fails.

    Review imports are local transactions until a remote write boundary is crossed.
    This rollback restores the reviewed control tree, orchestration state, French
    checkpoint stage, and per-debate mechanical artifacts created after the review
    was accepted.  Callers must never invoke it after remote execution has begun.
    """
    build = project_root / ".state" / "corpus-builds" / debate_id
    corpus = project_root / "corpus" / debate_id

    # A graph approval may have atomically moved the reviewed build into corpus/.
    # The backup is a complete pre-import copy, so remove only a corpus that did
    # not exist before this transaction, then restore the original base path.
    if bool(snapshot.get("build_existed")) and not bool(snapshot.get("corpus_existed")) and corpus.is_dir():
        shutil.rmtree(corpus)
    if backup.exists():
        _atomic_restore_dir(base, backup)

    _remove_new_children(
        project_root / ".state" / "editorial-workspaces" / debate_id,
        set(snapshot.get("editorial_children") or set()),
        bool(snapshot.get("editorial_root_existed")),
    )
    _remove_new_children(
        project_root / ".state" / "corpus-promotions" / debate_id,
        set(snapshot.get("promotion_children") or set()),
        bool(snapshot.get("promotion_root_existed")),
    )
    _remove_new_children(
        project_root / ".state" / "corpus-releases" / debate_id,
        set(snapshot.get("release_children") or set()),
        bool(snapshot.get("release_root_existed")),
    )
    _remove_new_children(
        project_root / "outgoing",
        set(snapshot.get("outgoing_children") or set()),
        bool(snapshot.get("outgoing_root_existed")),
        preserve=_is_persistent_validation_diagnostic,
    )
    _restore_french_publication_stage(project_root, debate_id, snapshot)

    workflow_path = _workflow_path(project_root, debate_id)
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    temp = workflow_path.with_name(workflow_path.name + ".rollback")
    temp.write_bytes(bytes(snapshot["workflow_bytes"]))
    os.replace(temp, workflow_path)
    _cleanup_import_transaction_snapshot(snapshot)


def _install_editable_files(base: Path, manifest: Mapping[str, Any], files: Mapping[str, bytes]) -> None:
    for row in manifest.get("editable_files") or []:
        target_rel = str(row.get("target_path") or "")
        package_rel = str(row.get("package_path") or "")
        if not target_rel or not _safe_zip_name(target_rel):
            raise WorkflowError(f"Chemin éditable invalide : {target_rel}")
        target = (base / target_rel).resolve()
        try:
            target.relative_to(base.resolve())
        except ValueError as exc:
            raise WorkflowError(f"Chemin éditable hors base : {target_rel}") from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + ".importing")
        temp.write_bytes(files[package_rel])
        os.replace(temp, target)




def _validation_errors(validation: Mapping[str, Any]) -> list[dict[str, Any]]:
    report_path = validation.get("report_json")
    if not report_path:
        return []
    path = Path(str(report_path))
    if not path.is_file():
        return []
    try:
        report = load_json(path, "rapport de validation initiale")
    except Exception:
        return []
    return [
        dict(item) for item in (report.get("findings") or report.get("issues") or [])
        if str(item.get("level") or item.get("severity") or "").upper() == "ERROR"
    ]


def _create_initial_validation_diagnostic(
    project_root: Path, state: dict[str, Any], build_dir: Path, validation: Mapping[str, Any]
) -> dict[str, Any]:
    debate_id = str(state["debate_id"])
    outgoing = project_root / "outgoing"
    outgoing.mkdir(parents=True, exist_ok=True)
    target = outgoing / f"{debate_id}_initial_validation_diagnostic.zip"
    explicit = [
        "manifest.json",
        "scope.json",
        "data/registre_debat.json",
        "graph/graphe_argumentatif.json",
        "graph/graphe_argumentatif.md",
        "reports/import_report.md",
        "reports/initial_validation.json",
        "reports/initial_validation.txt",
        "reports/initial_validation_execution.json",
    ]
    files = _copy_context_files(build_dir, [rel for rel in explicit if (build_dir / rel).is_file()], ["imports/fr/**/*.wiki", "imports/fr/**/*.json"])
    entries = []
    staging = Path(tempfile.mkdtemp(prefix=f".{debate_id}-initial-validation-", dir=outgoing))
    try:
        for source in files:
            rel = source.relative_to(build_dir).as_posix()
            dest = staging / "context" / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            entries.append({
                "path": f"context/{rel}",
                "sha256": _sha256_file(source),
                "size_bytes": source.stat().st_size,
            })
        errors = _validation_errors(validation)
        manifest = {
            "schema": DIAGNOSTIC_SCHEMA,
            "schema_version": "1.0",
            "debate_id": debate_id,
            "debate_title": state.get("debate_title"),
            "phase": "initial_validation",
            "normative_revision": NORM_VERSION,
            "validator_version": VALIDATOR_VERSION,
            "kit_version": KIT_VERSION,
            "created_at": now_iso(),
            "build_tree_sha256": full_tree_sha256(build_dir),
            "error_count": len(errors),
            "errors": errors,
            "files": sorted(entries, key=lambda row: row["path"]),
        }
        write_json(staging / "DIAGNOSTIC_PACKAGE.json", manifest)
        _write_deterministic_zip(staging, target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return {
        "diagnostic_path": _relative(target, project_root),
        "diagnostic_sha256": _sha256_file(target),
        "errors": _validation_errors(validation),
    }


def _record_initial_validation_block(
    project_root: Path, state: dict[str, Any], build_dir: Path, validation: Mapping[str, Any]
) -> None:
    diagnostic = _create_initial_validation_diagnostic(project_root, state, build_dir, validation)
    state["phase"] = "initial_validation_blocked"
    state["status"] = "blocked_technical"
    state["last_block"] = {
        "kind": "initial_validation",
        "created_at": now_iso(),
        **diagnostic,
    }
    state["updated_at"] = now_iso()
    _save_workflow(project_root, state)

def _semantic_response_template(review_type: str) -> dict[str, Any]:
    pass_no = 1 if review_type.endswith("_1") else 2
    return {
        "schema": SEMANTIC_RESPONSE_SCHEMA,
        "schema_version": "1.0",
        "pass_number": pass_no,
        "method_family": "",
        "method": "",
        "reviewer": "",
        "note": "",
        "new_certain_errors": None,
        "findings": [],
    }


def _prepare_semantic_package(project_root: Path, state: dict[str, Any], pass_number: int) -> dict[str, Any]:
    workspace, meta = _current_workspace_meta(project_root, state)
    response_rel = "reviews/en/semantic_review_response.json"
    write_json(workspace / response_rel, _semantic_response_template(f"semantic_convergence_{pass_number}"))
    context = [
        "reviews/en/translation_review.json",
        "audits/en_translation_inventory.json",
        "data/sources_en_working.json",
        "content-reviewed-copy/data/fr_page_metadata_lock.json",
        "content-reviewed-copy/data/fr_content_lock.json",
        "content-reviewed-copy/data/sources.json",
        "content-reviewed-copy/data/registre_debat.json",
    ]
    if pass_number == 2:
        context.append("reviews/en/semantic_convergence_review.json")
    return create_review_package(
        project_root, state,
        review_type=f"semantic_convergence_{pass_number}",
        base=workspace,
        editable_paths=[response_rel],
        context_paths=context,
        counts={"pass_number": pass_number},
    )



def _reserve_graph_review_work_id(project_root: Path, state: dict[str, Any]) -> str:
    """Reserve the Work id before the combined graph/title handoff is created."""
    existing = str(state.get("work_id") or "").strip()
    if existing:
        return validate_work_id(existing)
    editorial_root = project_root / ".state" / "editorial-workspaces" / str(state["debate_id"])
    editorial_root.mkdir(parents=True, exist_ok=True)
    work_id = next_work_id(editorial_root)
    state["work_id"] = work_id
    state["updated_at"] = now_iso()
    _save_workflow(project_root, state)
    return work_id


def _make_graph_title_review(build: Path, debate_id: str, work_id: str) -> dict[str, Any]:
    """Prepare the title part of the combined graph review on graph_draft input.

    Classification fields are present only as source context and are ignored by
    the title finalizer. They are deliberately reviewed later with page content.
    """
    registry = load_json(build / "data" / "registre_debat.json", "registre du débat")
    provenance = load_json(build / "data" / "import_provenance.json", "provenance d'import")
    fallback_by_title = fallback_map(provenance)
    page_rows = provenance.get("pages") or []
    debate_rows = [row for row in page_rows if isinstance(row, dict) and row.get("kind") == "debate"]
    if len(debate_rows) != 1:
        raise WorkflowError(f"Une page Débat importée est requise, trouvée : {len(debate_rows)}")
    argument_rows = {
        str(row.get("page_id")): row for row in page_rows
        if isinstance(row, dict) and row.get("kind") == "argument" and row.get("page_id")
        and str(row.get("provenance_status") or "") not in {"retired_redirect", "retired_deleted", "pending_redirect", "pending_delete"}
    }
    items: list[dict[str, Any]] = []
    debate_row = debate_rows[0]
    debate_import = read_import_metadata(build, debate_row)
    debate_title = str((((registry.get("debate") or {}).get("pages") or {}).get("fr") or {}).get("canonical_title") or debate_row.get("canonical_title") or "")
    items.append(page_review_item(
        entity_type="debate", entity_id="debate", canonical_title=debate_title,
        displayed_title=None, rubriques=list(debate_import.get("rubriques") or []),
        keywords=list(debate_import.get("keywords") or []), import_row=debate_row,
        import_metadata=debate_import, fallback_kinds=fallback_by_title.get(debate_title, set()),
    ))
    active_nodes = [node for node in (registry.get("graph") or {}).get("nodes") or [] if node.get("status") == "active"]
    for node in sorted(active_nodes, key=lambda row: str(row.get("id"))):
        node_id = str(node.get("id"))
        import_row = argument_rows.get(node_id)
        if import_row is None:
            raise WorkflowError(f"Provenance importée absente pour le nœud actif {node_id}")
        import_metadata = read_import_metadata(build, import_row)
        fr = ((node.get("pages") or {}).get("fr") or {})
        canonical_title = str(fr.get("canonical_title") or import_row.get("canonical_title") or "")
        displayed_title = str(fr.get("displayed_title") or canonical_title)
        items.append(page_review_item(
            entity_type="argument", entity_id=node_id, canonical_title=canonical_title,
            displayed_title=displayed_title, rubriques=list(import_metadata.get("rubriques") or []),
            keywords=list(import_metadata.get("keywords") or []), import_row=import_row,
            import_metadata=import_metadata, fallback_kinds=fallback_by_title.get(canonical_title, set()),
        ))
    ledger = {
        "schema": "wikidebia-fr-page-metadata-review-1.1",
        "schema_version": "1.1",
        "normative_revision": NORM_VERSION,
        "debate_id": debate_id,
        "work_id": work_id,
        "review_scope": "graph_and_titles",
        "status": "pending",
        "generated_at": now_iso(),
        "items": items,
    }
    write_json(build / GRAPH_TITLE_REVIEW, ledger)
    return ledger


def _install_combined_graph_title_review(workspace: Path, promoted_corpus: Path) -> None:
    source = promoted_corpus / GRAPH_TITLE_REVIEW
    if not source.is_file():
        raise WorkflowError("La revue combinée du graphe ne contient pas le registre des titres")
    target = workspace / "reviews" / "fr" / "page_metadata_review.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)

def _prepare_graph_package(project_root: Path, state: dict[str, Any]) -> dict[str, Any]:
    build = resolve_build(project_root, str(state["debate_id"]))
    overwrite = bool(state.pop("overwrite_graph_review", False))
    work_id = _reserve_graph_review_work_id(project_root, state)
    title_review = _make_graph_title_review(build, str(state["debate_id"]), work_id)
    result = make_review_template(build, str(state["debate_id"]), overwrite=overwrite)
    return create_review_package(
        project_root, state,
        review_type="graph_review", base=build,
        editable_paths=[REVIEW_ENVELOPE, PLACEMENT_REVIEW, GRAPH_TITLE_REVIEW],
        context_paths=["manifest.json", "scope.json", "data/registre_debat.json", "graph/graphe_argumentatif.json", "graph/graphe_argumentatif.md", "reports/import_report.md"],
        context_globs=["imports/fr/**/*.wiki", "imports/fr/**/*.json"],
        counts={"placements": result.get("occurrences"), "pages": len(title_review.get("items") or [])},
    )


def _prepare_graph_correction_package(project_root: Path, state: dict[str, Any]) -> dict[str, Any]:
    build = resolve_build(project_root, str(state["debate_id"]))
    result = make_graph_correction_template(build, str(state["debate_id"]))
    return create_review_package(
        project_root, state,
        review_type="graph_correction", base=build,
        editable_paths=[GRAPH_CORRECTION_REVIEW],
        context_paths=[REVIEW_ENVELOPE, PLACEMENT_REVIEW, "reports/graph_build_review_report.json", "manifest.json", "scope.json", "data/registre_debat.json", "graph/graphe_argumentatif.json", "graph/graphe_argumentatif.md", "reports/import_report.md"],
        context_globs=["imports/fr/**/*.wiki", "imports/fr/**/*.json"],
        counts={"placements": result.get("occurrences")},
    )


def _prepare_metadata_package(project_root: Path, state: dict[str, Any]) -> dict[str, Any]:
    workspace, meta = _current_workspace_meta(project_root, state)
    review = load_json(workspace / "reviews/fr/page_metadata_review.json", "revue française")
    return create_review_package(
        project_root, state,
        review_type="fr_metadata_review", base=workspace,
        editable_paths=["reviews/fr/page_metadata_review.json"],
        context_paths=["audits/editorial_inventory.json", "audits/editorial_inventory.md", "tasks/editorial_tasks.json", "working-copy/scope.json", "working-copy/data/registre_debat.json", "working-copy/graph/graphe_argumentatif.json"],
        context_globs=["working-copy/imports/fr/**/*.wiki", "working-copy/imports/fr/**/*.json"],
        counts={"pages": len(review.get("items") or [])},
    )


def _prepare_content_package(project_root: Path, state: dict[str, Any]) -> dict[str, Any]:
    workspace, _ = _current_workspace_meta(project_root, state)
    result = prepare_content_review(project_root, str(state["debate_id"]), str(state["work_id"]), overwrite=False)
    review = load_json(workspace / "reviews/fr/content_review.json", "revue contenu")
    return create_review_package(
        project_root, state,
        review_type="fr_content_review", base=workspace,
        editable_paths=["reviews/fr/content_review.json", "data/sources_working.json", "reviews/fr/classification_review.json", "data/keyword_vocabulary_working.json"],
        context_paths=["audits/fr_content_inventory.json", "audits/fr_content_inventory.md", "reviewed-copy/data/fr_page_metadata_lock.json", "reviewed-copy/data/registre_debat.json", "reviewed-copy/data/sources.json", "reviewed-copy/scope.json"],
        context_globs=["reviewed-copy/imports/fr/**/*.wiki", "reviewed-copy/imports/fr/**/*.json"],
        counts={"arguments": len(review.get("arguments") or [])},
    )


def _prepare_translation_package(project_root: Path, state: dict[str, Any], *, correction: bool = False) -> dict[str, Any]:
    workspace, meta = _current_workspace_meta(project_root, state)
    if not correction:
        prepare_translation_review(project_root, str(state["debate_id"]), str(state["work_id"]), overwrite=False)
    review = load_json(workspace / "reviews/en/translation_review.json", "revue anglaise")
    context = [
        "audits/en_translation_inventory.json", "audits/en_translation_inventory.md",
        "content-reviewed-copy/data/fr_page_metadata_lock.json", "content-reviewed-copy/data/fr_content_lock.json",
        "content-reviewed-copy/data/registre_debat.json", "content-reviewed-copy/data/sources.json",
        "content-reviewed-copy/data/keyword_vocabulary.json",
        "reviews/en/translation_readiness.json",
    ]
    if correction:
        context.append("reviews/en/semantic_convergence_findings.json")
    return create_review_package(
        project_root, state,
        review_type="en_translation_correction" if correction else "en_translation_review",
        base=workspace,
        editable_paths=["reviews/en/translation_review.json", "data/sources_en_working.json"],
        context_paths=context,
        context_globs=["content-reviewed-copy/imports/fr/**/*.wiki", "content-reviewed-copy/imports/fr/**/*.json"],
        counts={"arguments": len(review.get("arguments") or []), "review_units": len(review.get("review_units") or [])},
    )


def _prepare_documentation_correction_package(project_root: Path, state: dict[str, Any]) -> dict[str, Any]:
    workspace, _ = _current_workspace_meta(project_root, state)
    review = load_json(workspace / "reviews/en/translation_review.json", "revue anglaise")
    return create_review_package(
        project_root, state,
        review_type="en_documentation_correction",
        base=workspace,
        editable_paths=["data/sources_en_working.json"],
        context_paths=[
            "reviews/en/translation_review.json",
            "reviews/en/semantic_convergence_findings.json",
            "audits/en_translation_inventory.json",
            "content-reviewed-copy/data/fr_page_metadata_lock.json",
            "content-reviewed-copy/data/fr_content_lock.json",
            "content-reviewed-copy/data/registre_debat.json",
            "content-reviewed-copy/data/sources.json",
        ],
        counts={
            "arguments": len(review.get("arguments") or []),
            "source_findings": len((load_json(workspace / "reviews/en/semantic_convergence_findings.json", "constats documentaires").get("findings") or [])),
        },
    )


def _reopen_translation_after_findings(project_root: Path, state: dict[str, Any], findings: Mapping[str, Any]) -> None:
    workspace, meta = _current_workspace_meta(project_root, state)
    review_path = workspace / "reviews/en/translation_review.json"
    review = load_json(review_path, "revue anglaise")
    for key in ("review_sha256", "finalized_at", "semantic_content_sha256", "summary", "final_values", "semantic_review"):
        review.pop(key, None)
    review["status"] = "draft"
    write_json(review_path, review)
    write_json(workspace / "reviews/en/semantic_convergence_findings.json", dict(findings))
    convergence = workspace / "reviews/en/semantic_convergence_review.json"
    if convergence.exists():
        convergence.unlink()
    meta = copy.deepcopy(meta)
    meta["status"] = "en_translation_review_ready"
    meta["english_translation_review"] = {
        "status": "prepared",
        "prepared_at": now_iso(),
        "prepared_content_reviewed_copy_sha256": review.get("prepared_content_reviewed_copy_sha256"),
        "reopened_after_semantic_findings": True,
    }
    meta["workspace_sha256"] = None
    meta["workspace_sha256"] = workspace_receipt_hash(meta)
    write_json(workspace / "workspace.json", meta)


def _mechanical_advance(project_root: Path, state: dict[str, Any]) -> dict[str, Any]:
    """Advance until a ChatGPT review, a blocked final preflight, or publication completion."""
    debate_id = str(state["debate_id"])
    while True:
        phase = str(state.get("phase") or "graph_review")
        pending = state.get("pending_review")
        # Migration/resume guard for workflows created before the two-checkpoint
        # contract. An already completed legacy French publication cannot be split
        # retroactively; otherwise publish graph/title first, then content, before
        # allowing any English review to continue.
        if state.get("french_publication") and not state.get("french_content_publication"):
            state["french_graph_publication"] = copy.deepcopy(state["french_publication"])
            state["french_content_publication"] = copy.deepcopy(state["french_publication"])
            state["updated_at"] = now_iso(); _save_workflow(project_root, state)
        if isinstance(pending, dict):
            pending_type = str(pending.get("review_type") or "")
            if pending_type in {"en_translation_review", "en_translation_correction", "en_documentation_correction", "semantic_convergence_1", "semantic_convergence_2"} and state.get("work_id"):
                if not state.get("french_graph_publication"):
                    publication = publish_checkpoint(project_root, debate_id, str(state["work_id"]), stage="graph")
                    state["french_graph_publication"] = copy.deepcopy(publication)
                    state["updated_at"] = now_iso(); _save_workflow(project_root, state)
                if not state.get("french_content_publication"):
                    publication = publish_checkpoint(project_root, debate_id, str(state["work_id"]), stage="content")
                    state["french_content_publication"] = copy.deepcopy(publication)
                    state["french_publication"] = copy.deepcopy(publication)  # legacy alias
                    state["updated_at"] = now_iso(); _save_workflow(project_root, state)
        if state.get("pending_review"):
            return state
        if phase == "initialize_graph":
            _initialize_graph_stage(project_root, state)
            continue
        if phase == "initial_validation_blocked":
            return state
        if phase == "graph_review":
            _prepare_graph_package(project_root, state)
            return state
        if phase == "graph_correction":
            _prepare_graph_correction_package(project_root, state)
            return state
        if phase == "promote_and_workspace":
            build = project_root / ".state" / "corpus-builds" / debate_id
            corpus = project_root / "corpus" / debate_id
            if build.is_dir() and corpus.exists():
                raise WorkflowError("Le build et le corpus promu existent simultanément; une décision humaine est requise")
            source = build if build.is_dir() else corpus
            if not source.is_dir():
                raise WorkflowError("Ni build validé ni corpus promu disponible pour reprendre le workflow")
            # Historical graph-action states may contain post-action import snapshots
            # whose raw provenance hash was not refreshed. Repair only exact,
            # action-attested files before workspace creation; unrelated drift
            # remains blocking. Compatibility is evidence/schema based, not tied
            # to the producer kit version.
            repair_graph_action_import_provenance(source, project_root=project_root, debate_id=debate_id)
            review = load_json(source / REVIEW_ENVELOPE, "revue graphe")
            review_sha = str(review.get("review_sha256") or "")
            if not review_sha or review_sha != graph_review_sha256(review):
                raise WorkflowError("La revue du graphe finalisée n'a pas d'empreinte valide")
            if build.is_dir():
                promote_graph(project_root, debate_id, review_sha)
                corpus = project_root / "corpus" / debate_id
            if not corpus.is_dir():
                raise WorkflowError("La promotion du corpus n'a pas produit le corpus actif attendu")

            editorial_root = project_root / ".state" / "editorial-workspaces" / debate_id
            work_id = state.get("work_id")
            if not work_id:
                editorial_root.mkdir(parents=True, exist_ok=True)
                work_id = next_work_id(editorial_root)
                state["work_id"] = work_id
                state["updated_at"] = now_iso()
                _save_workflow(project_root, state)
            workspace = editorial_root / str(work_id)
            if workspace.is_dir():
                meta = load_json(workspace / "workspace.json", "workspace")
                if meta.get("debate_id") != debate_id or meta.get("work_id") != work_id:
                    raise WorkflowError("Le workspace de reprise ne correspond pas au workflow")
            else:
                create_workspace(project_root, debate_id, str(work_id))
            # New combined-review contract: the graph ZIP already contains the
            # title decisions. Install them into the freshly promoted workspace,
            # finalize/apply them, then cross the first French publication
            # checkpoint immediately. Older workflows without this artifact keep
            # the historical standalone title-review phase for compatibility.
            if (corpus / GRAPH_TITLE_REVIEW).is_file():
                _install_combined_graph_title_review(workspace, corpus)
                title_result = finalize_metadata_review(project_root, debate_id, str(work_id))
                apply_metadata_review(project_root, debate_id, str(work_id), str(title_result["review_sha256"]))
                state["phase"] = "graph_publication_resume"
                state["updated_at"] = now_iso()
                _save_workflow(project_root, state)
                continue
            state["phase"] = "fr_metadata_review"
            state["updated_at"] = now_iso()
            _save_workflow(project_root, state)
            continue
        if phase == "graph_publication_resume":
            if not state.get("french_graph_publication"):
                state["remote_publication_stage"] = "graph"
                state["updated_at"] = now_iso()
                _save_workflow(project_root, state)
                publication = publish_checkpoint(project_root, debate_id, str(state["work_id"]), stage="graph")
                state["french_graph_publication"] = copy.deepcopy(publication)
                state.pop("remote_publication_stage", None)
            state["phase"] = "fr_content_review"
            state["updated_at"] = now_iso()
            _save_workflow(project_root, state)
            continue
        if phase == "fr_metadata_review":
            _prepare_metadata_package(project_root, state)
            return state
        if phase == "fr_content_review":
            _prepare_content_package(project_root, state)
            return state
        if phase == "en_translation_review":
            if not state.get("work_id"):
                raise WorkflowError("Work éditorial absent avant les publications françaises")
            if not state.get("french_graph_publication"):
                publication = publish_checkpoint(project_root, debate_id, str(state["work_id"]), stage="graph")
                state["french_graph_publication"] = copy.deepcopy(publication)
                state["updated_at"] = now_iso(); _save_workflow(project_root, state)
            if not state.get("french_content_publication"):
                publication = publish_checkpoint(project_root, debate_id, str(state["work_id"]), stage="content")
                state["french_content_publication"] = copy.deepcopy(publication)
                state["french_publication"] = copy.deepcopy(publication)  # legacy alias
                state["updated_at"] = now_iso(); _save_workflow(project_root, state)
            _prepare_translation_package(project_root, state)
            return state
        if phase == "semantic_convergence_1":
            _prepare_semantic_package(project_root, state, 1)
            return state
        if phase == "semantic_convergence_2":
            _prepare_semantic_package(project_root, state, 2)
            return state
        if phase == "en_translation_correction":
            _prepare_translation_package(project_root, state, correction=True)
            return state
        if phase == "en_documentation_correction":
            _prepare_documentation_correction_package(project_root, state)
            return state
        if phase == "apply_render_release":
            workspace, meta = _current_workspace_meta(project_root, state)
            review = load_json(workspace / "reviews/en/translation_review.json", "revue anglaise")
            # Compatibility guard for already-finalized reviews produced by an
            # older kit that allowed typographic apostrophes in English titles.
            # Never silently normalize a converged value: reopen the translation
            # explicitly, invalidate the old convergence receipt and let the two
            # independent passes restart on the corrected semantic hash.
            title_findings = collect_english_title_format_findings(review)
            documentary_findings = collect_english_documentary_findings(review)
            if title_findings or documentary_findings:
                all_findings = [*title_findings, *documentary_findings]
                if title_findings and documentary_findings:
                    source_review_type = "post_convergence_title_and_documentary_preflight"
                elif title_findings:
                    source_review_type = "post_convergence_title_preflight"
                else:
                    source_review_type = "post_convergence_documentary_preflight"
                _reopen_translation_after_findings(project_root, state, {
                    "schema": "wikidebia-semantic-convergence-findings-1.0",
                    "debate_id": debate_id,
                    "work_id": state.get("work_id"),
                    "recorded_at": now_iso(),
                    "source_review_type": source_review_type,
                    "new_certain_errors": len(all_findings),
                    "findings": all_findings,
                })
                # A title defect changes semantic content and therefore exposes the
                # full translation correction.  A source-only defect gets a narrower
                # package where translation_review.json is read-only.
                state["phase"] = "en_translation_correction" if title_findings else "en_documentation_correction"
                state["status"] = "running"
                state["updated_at"] = now_iso()
                _save_workflow(project_root, state)
                continue
            review_sha = str(review.get("review_sha256") or "")
            apply_translation_review(project_root, debate_id, str(state["work_id"]), review_sha)
            render = render_workspace(project_root, debate_id, str(state["work_id"]), review_sha)
            release = release_workspace(project_root, debate_id, str(state["work_id"]), str(render["rendered_copy_tree_sha256"]))
            state["phase"] = "final_publication"
            state["status"] = "final_publication"
            state["release"] = release
            state["updated_at"] = now_iso()
            _save_workflow(project_root, state)
            continue
        if phase == "release_ready":
            # Resume Work states produced by 2.16.37/2.16.38 without rerunning
            # rendering, release packaging or either semantic convergence pass.
            state["phase"] = "final_publication"
            state["status"] = "final_publication"
            state["updated_at"] = now_iso()
            _save_workflow(project_root, state)
            continue
        if phase in {"final_publication", "final_publication_resume"}:
            workspace, meta = _current_workspace_meta(project_root, state)
            release_copy = workspace / "release-copy"
            try:
                publication = publish_final_release(
                    project_root, debate_id, str(state["work_id"]), release_copy
                )
            except FinalPublicationError as exc:
                state["phase"] = "final_publication"
                state["status"] = "blocked_final_publication"
                state["final_publication"] = {
                    "status": "blocked",
                    "state_path": _relative(project_root / ".state/final-publication" / debate_id / str(state["work_id"]), project_root),
                    "remote_execution_started": bool(exc.remote_execution_started),
                    "error": str(exc),
                    "recorded_at": now_iso(),
                }
                state["updated_at"] = now_iso()
                _save_workflow(project_root, state)
                return state
            state["phase"] = "published"
            state["status"] = "published"
            state["final_publication"] = copy.deepcopy(publication)
            state["updated_at"] = now_iso()
            _save_workflow(project_root, state)
            return state
        if phase == "published":
            return state
        raise WorkflowError(f"Phase d'orchestration inconnue : {phase}")


def _run_graph_extract(project_root: Path, title: str, *, force_refresh: bool = False) -> Path:
    from wikidebia_graph_extract import slugify
    slug = slugify(title)
    output = project_root / ".state" / "graph-extract" / slug
    if not force_refresh and (output / "snapshot" / "snapshot_manifest.json").is_file():
        return output
    script = project_root / "kit" / "scripts" / "wikidebia_graph_extract.py"
    if not script.is_file():
        raise WorkflowError("Extracteur de graphe absent")
    python = project_root / ".venv" / "bin" / "python"
    if not python.is_file():
        python = Path(sys.executable)
    command = [
        str(python), str(script), "--debate", title, "--family", "wikidebates", "--lang", "fr",
        "--pywikibot-dir", str(project_root / "private" / "pywikibot"),
        "--family-file", str(project_root / "kit" / "families" / "wikidebates_family.py"),
        "--output-dir", str(output), "--slug", slug, "--machine-readable",
    ]
    if force_refresh:
        command.append("--force-refresh")
    completed = subprocess.run(command, cwd=project_root, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise WorkflowError("graph-extract a échoué : " + (completed.stderr or completed.stdout)[-2000:])
    if not (output / "snapshot" / "snapshot_manifest.json").is_file():
        raise WorkflowError("graph-extract n'a pas produit le snapshot attendu")
    return output



def _stage_snapshot_input(project_root: Path, debate_id: str, snapshot: Path | None) -> str | None:
    if snapshot is None:
        return None
    source = snapshot.expanduser().resolve()
    if not source.exists() or source.is_symlink():
        raise WorkflowError(f"Snapshot invalide : {snapshot}")
    work_root = _workflow_root(project_root, debate_id)
    work_root.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        target = work_root / "snapshot-input"
        if not target.exists():
            shutil.copytree(source, target, symlinks=False)
        return _relative(target, project_root)
    target = work_root / "snapshot-input.zip"
    if not target.exists():
        shutil.copy2(source, target)
    return _relative(target, project_root)


def _initialize_graph_stage(project_root: Path, state: dict[str, Any]) -> None:
    debate_id = str(state["debate_id"])
    build_dir = project_root / ".state" / "corpus-builds" / debate_id
    if build_dir.is_dir():
        manifest = load_json(build_dir / "manifest.json", "manifest build")
        if manifest.get("debate_id") != debate_id or manifest.get("global_status") not in {"graph_draft", "graph_validated"}:
            raise WorkflowError("Un build existant incompatible empêche la reprise automatique")
        if manifest.get("global_status") == "graph_draft":
            validation = run_initial_validator(project_root, build_dir)
            if validation.get("status") == "failed":
                _record_initial_validation_block(project_root, state, build_dir, validation)
                return
            state["phase"] = "graph_review"
            state["status"] = "running"
            state.pop("last_block", None)
        else:
            state["phase"] = "promote_and_workspace"
        state["updated_at"] = now_iso()
        _save_workflow(project_root, state)
        return
    staged = state.get("snapshot_path")
    if staged:
        source = project_root / str(staged)
    else:
        source = _run_graph_extract(project_root, str(state["debate_title"]), force_refresh=bool(state.get("force_refresh")))
        state["snapshot_path"] = _relative(source, project_root)
        state["updated_at"] = now_iso()
        _save_workflow(project_root, state)
    result = build_corpus(
        source, build_dir, debate_id=debate_id, short_code=state.get("short_code"),
        scope_summary=None, overwrite=False,
    )
    state["short_code"] = result.get("short_code")
    validation = run_initial_validator(project_root, build_dir)
    if validation.get("status") == "failed":
        _record_initial_validation_block(project_root, state, build_dir, validation)
        return
    state["phase"] = "graph_review"
    state["status"] = "running"
    state.pop("last_block", None)
    state["updated_at"] = now_iso()
    _save_workflow(project_root, state)


def start_workflow(
    project_root: Path,
    debate_title: str,
    *, debate_id: str | None = None,
    short_code: str | None = None,
    snapshot: Path | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    selected_id = validate_debate_id(debate_id or canonical_debate_id(debate_title))
    try:
        requested_short_code = validate_short_code(short_code) if short_code else None
        automatic_short_code = derive_short_code(selected_id)
    except Exception as exc:
        raise WorkflowError(str(exc)) from exc
    state_path = _workflow_path(project_root, selected_id)
    if state_path.is_file():
        state = _load_workflow(project_root, selected_id)
        if state.get("debate_title") != debate_title:
            raise WorkflowError("Le debate_id demandé appartient déjà à un autre titre")
        existing_short_code = str(state.get("short_code") or "").strip()
        try:
            existing_valid = validate_short_code(existing_short_code) if existing_short_code else None
        except Exception:
            existing_valid = None
        if requested_short_code:
            if existing_valid and existing_valid != requested_short_code:
                raise WorkflowError(
                    f"Le workflow utilise déjà le short_code {existing_valid}; "
                    f"le code demandé {requested_short_code} est différent"
                )
            if existing_valid != requested_short_code:
                state["short_code"] = requested_short_code
                state["updated_at"] = now_iso()
                _save_workflow(project_root, state)
        elif not existing_valid:
            state["short_code"] = automatic_short_code
            state["updated_at"] = now_iso()
            _save_workflow(project_root, state)
        if state.get("phase") == "initial_validation_blocked":
            state["phase"] = "initialize_graph"
            state["status"] = "running"
            state["updated_at"] = now_iso()
            _save_workflow(project_root, state)
        return _mechanical_advance(project_root, state)

    state = {
        "schema": WORKFLOW_SCHEMA,
        "schema_version": "1.0",
        "normative_revision": NORM_VERSION,
        "validator_version": VALIDATOR_VERSION,
        "kit_version": KIT_VERSION,
        "debate_id": selected_id,
        "debate_title": debate_title,
        "short_code": requested_short_code or automatic_short_code,
        "phase": "initialize_graph",
        "status": "running",
        "work_id": None,
        "pending_review": None,
        "snapshot_path": None,
        "force_refresh": bool(force_refresh),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    _save_workflow(project_root, state)
    state["snapshot_path"] = _stage_snapshot_input(project_root, selected_id, snapshot)
    state["updated_at"] = now_iso()
    _save_workflow(project_root, state)
    return _mechanical_advance(project_root, state)


def _validate_pending_identity(state: Mapping[str, Any], manifest: Mapping[str, Any]) -> None:
    pending = state.get("pending_review") or {}
    if manifest.get("debate_id") != state.get("debate_id"):
        raise WorkflowError("Le ZIP appartient à un autre corpus")
    if manifest.get("work_id") != state.get("work_id"):
        raise WorkflowError("Le ZIP appartient à un autre Work")
    if manifest.get("package_id") != pending.get("package_id"):
        raise WorkflowError("Le ZIP ne correspond pas au paquet de revue actuellement attendu")
    if manifest.get("review_type") != pending.get("review_type"):
        raise WorkflowError("Type de revue inattendu")
    if manifest.get("manifest_sha256") != pending.get("manifest_sha256"):
        raise WorkflowError("La provenance locale du paquet ne correspond pas")



def _review_editable_row(manifest: Mapping[str, Any], target_path: str) -> Mapping[str, Any] | None:
    for row in manifest.get("editable_files") or []:
        if isinstance(row, dict) and str(row.get("target_path") or "") == target_path:
            return row
    return None


def _json_review_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(dict(value), ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _prepare_historical_consent_import(
    archive: Path, state: Mapping[str, Any], manifest: Mapping[str, Any], files: dict[str, bytes],
    *, authorize_historical_changes: bool,
) -> tuple[dict[str, bytes], dict[str, Any] | None, dict[str, Any] | None]:
    """Normalize a French content review and optionally create owner authorization.

    The authorization is intentionally absent from the returned ZIP.  It is
    generated only by the local kit when the owner invokes review-import with
    ``--authorize-historical-changes``.  Therefore ChatGPT can request an exact
    scope but cannot manufacture the proof that opens it.
    """
    if str(manifest.get("review_type") or "") != "fr_content_review":
        if authorize_historical_changes:
            raise WorkflowError("--authorize-historical-changes est réservé à une revue française de contenu")
        return files, None, None
    row = _review_editable_row(manifest, "reviews/fr/content_review.json")
    if not isinstance(row, Mapping):
        if authorize_historical_changes:
            raise WorkflowError("Le paquet de revue de contenu ne contient pas reviews/fr/content_review.json ; aucun périmètre historique ne peut être autorisé")
        return files, None, None
    package_path = str(row.get("package_path") or "")
    try:
        raw = json.loads(files[package_path].decode("utf-8"))
    except Exception as exc:
        raise WorkflowError("reviews/fr/content_review.json est illisible dans le ZIP rendu") from exc
    if not isinstance(raw, dict):
        raise WorkflowError("reviews/fr/content_review.json doit être un objet JSON")
    normalized, migration = normalize_historical_review_document(raw)
    if migration.get("legacy_format_detected"):
        normalized["compatibility_migration"] = {
            "schema": "wikidebia-fr-content-review-compatibility-migration-1.0",
            "normalized_by_kit": KIT_VERSION,
            "normalized_at": now_iso(),
            **migration,
        }
    mutable_files = dict(files)
    mutable_files[package_path] = _json_review_bytes(normalized)
    try:
        requested = collect_historical_change_requests(normalized)
    except Exception as exc:
        raise WorkflowError(str(exc)) from exc
    if requested and not authorize_historical_changes:
        fields = ", ".join(row["field_key"] for row in requested[:6])
        suffix = "…" if len(requested) > 6 else ""
        raise WorkflowError(
            "Le ZIP demande des modifications de textes historiques qui nécessitent le consentement explicite du propriétaire. "
            f"Champs : {fields}{suffix}. Après accord, relancez exactement le même ZIP avec "
            "./wikidebia review-import --authorize-historical-changes"
        )
    if authorize_historical_changes and not requested:
        raise WorkflowError("Aucun changement historique explicitement demandé n’est présent dans ce ZIP ; rien à autoriser")
    if not requested:
        return mutable_files, normalized, None

    authorization_id = str(uuid.uuid4())
    package_id = str(manifest.get("package_id") or "")
    manifest_sha = str(manifest.get("manifest_sha256") or "")
    archive_sha = _sha256_file(archive)
    changes = []
    for change in requested:
        enriched = copy.deepcopy(change)
        enriched.update({
            "authorization_id": authorization_id,
            "package_id": package_id,
            "manifest_sha256": manifest_sha,
            "returned_archive_sha256": archive_sha,
        })
        changes.append(enriched)
    authorization = {
        "schema": HISTORICAL_AUTHORIZATION_SCHEMA,
        "schema_version": "1.0",
        "authorization_id": authorization_id,
        "debate_id": state.get("debate_id"),
        "work_id": state.get("work_id"),
        "review_type": "fr_content_review",
        "package_id": package_id,
        "manifest_sha256": manifest_sha,
        "returned_archive_sha256": archive_sha,
        "review_payload_sha256": content_review_sha256(normalized),
        "authorization_method": "owner_explicit_cli_flag",
        "authorization_command": "review-import --authorize-historical-changes",
        "authorized_at": now_iso(),
        "changes": changes,
        "authorization_sha256": None,
    }
    body = copy.deepcopy(authorization)
    body.pop("authorization_sha256", None)
    authorization["authorization_sha256"] = _sha256_bytes(_canonical_json(body))
    return mutable_files, normalized, authorization

def import_review(
    project_root: Path, debate_id: str, archive: Path, *, execute_graph_actions: bool = False,
    authorize_historical_changes: bool = False,
) -> dict[str, Any]:
    debate_id = validate_debate_id(debate_id)
    state = _load_workflow(project_root, debate_id)
    pending = state.get("pending_review")
    if not isinstance(pending, dict):
        raise WorkflowError("Aucune revue ChatGPT n'est actuellement attendue")
    manifest, files = _read_returned_package(archive)
    _validate_pending_identity(state, manifest)
    base = project_root / str(pending["base_path"])
    if not base.is_dir():
        raise WorkflowError("La base locale de la revue n'existe plus")

    files, normalized_content_review, owner_authorization = _prepare_historical_consent_import(
        archive, state, manifest, files, authorize_historical_changes=authorize_historical_changes,
    )

    # Context is validated against both the returned package and current local files.
    for row in manifest.get("context_files") or []:
        local = base / str(row.get("target_path"))
        _assert_regular_file(local, "Contexte local")
        if _sha256_file(local) != row.get("sha256"):
            raise WorkflowError(f"Le contexte local a changé depuis la préparation : {row.get('target_path')}")
    for row in manifest.get("editable_files") or []:
        local = base / str(row.get("target_path"))
        _assert_regular_file(local, "Fichier éditable local")
        if _sha256_file(local) != row.get("sha256_at_prepare"):
            raise WorkflowError(f"Un fichier éditable local a changé hors réimport : {row.get('target_path')}")

    transaction = _capture_import_transaction(
        project_root, debate_id, work_id=str(state.get("work_id") or "") or None,
        review_type=str(manifest.get("review_type") or ""),
    )
    backup = base.with_name(base.name + f".review-import-backup-{uuid.uuid4().hex[:8]}")
    if backup.exists():
        shutil.rmtree(backup)
    shutil.copytree(base, backup, symlinks=False)
    irreversible_graph_actions = False
    irreversible_french_publication = False
    try:
        _install_editable_files(base, manifest, files)
        review_type = str(manifest["review_type"])
        if review_type == "fr_content_review":
            auth_path = base / HISTORICAL_AUTHORIZATION_PATH
            if owner_authorization is not None:
                write_json(auth_path, owner_authorization)
            elif auth_path.exists():
                # A stale authorization can never silently authorize a new ZIP.
                auth_path.unlink()
        if execute_graph_actions and review_type != "graph_review":
            raise WorkflowError("--execute-graph-actions est réservé aux paquets de revue du graphe")
        if review_type == "graph_review":
            result = finalize_graph_review(project_root, base, debate_id)
            if result.get("status") == "approved":
                state["phase"] = "promote_and_workspace"
            elif result.get("status") == "rejected":
                state.setdefault("graph_rejections", []).append({
                    "review_sha256": result.get("review_sha256"),
                    "blocking_issues": copy.deepcopy(result.get("blocking_issues") or []),
                    "recorded_at": now_iso(),
                })
                actions = extract_actions_from_review(base)
                if execute_graph_actions:
                    # Legacy explicit path retained for compatibility. Normal workflows
                    # defer all remote writes to the first French graph/title checkpoint.
                    action_result = execute_graph_review_actions(
                        project_root, base, debate_id,
                        preflight_validator=lambda preview: run_initial_validator(project_root, preview),
                    )
                    irreversible_graph_actions = True
                    state.setdefault("graph_action_executions", []).append(copy.deepcopy(action_result))
                    state["phase"] = "graph_review"
                    state["overwrite_graph_review"] = True
                elif actions:
                    action_result = apply_graph_review_actions_locally(
                        project_root, base, debate_id,
                        preflight_validator=lambda preview: run_initial_validator(project_root, preview),
                    )
                    state.setdefault("pending_graph_actions", []).append(copy.deepcopy(action_result))
                    state["phase"] = "graph_review"
                    state["overwrite_graph_review"] = True
                else:
                    state["phase"] = "graph_correction"
            else:
                raise WorkflowError(f"Statut final de revue du graphe inattendu : {result.get('status')!r}")
        elif review_type == "graph_correction":
            result = apply_graph_correction(project_root, base, debate_id)
            validation = run_initial_validator(project_root, base)
            if validation.get("status") == "failed":
                raise WorkflowError("La correction du graphe reste structurellement invalide; elle n'a pas été acceptée")
            state["phase"] = "graph_review"
            state["overwrite_graph_review"] = True
        elif review_type == "fr_metadata_review":
            result = finalize_metadata_review(project_root, debate_id, str(state["work_id"]))
            apply_metadata_review(project_root, debate_id, str(state["work_id"]), str(result["review_sha256"]))
            try:
                publication = publish_checkpoint(project_root, debate_id, str(state["work_id"]), stage="graph")
            except FrenchCheckpointError as exc:
                irreversible_french_publication = bool(exc.remote_execution_started)
                state["remote_publication_stage"] = "graph"
                raise
            irreversible_french_publication = True
            state["french_graph_publication"] = copy.deepcopy(publication)
            state["phase"] = "fr_content_review"
        elif review_type == "fr_content_review":
            result = finalize_content_review(project_root, debate_id, str(state["work_id"]))
            apply_content_review(project_root, debate_id, str(state["work_id"]), str(result["review_sha256"]))
            try:
                publication = publish_checkpoint(project_root, debate_id, str(state["work_id"]), stage="content")
            except FrenchCheckpointError as exc:
                irreversible_french_publication = bool(exc.remote_execution_started)
                state["remote_publication_stage"] = "content"
                raise
            irreversible_french_publication = True
            state["french_content_publication"] = copy.deepcopy(publication)
            state["french_publication"] = copy.deepcopy(publication)  # legacy alias
            state["phase"] = "en_translation_review"
        elif review_type in {"en_translation_review", "en_translation_correction", "en_documentation_correction"}:
            result = finalize_translation_review(project_root, debate_id, str(state["work_id"]))
            state["phase"] = "semantic_convergence_1"
        elif review_type in {"semantic_convergence_1", "semantic_convergence_2"}:
            response = load_json(base / "reviews/en/semantic_review_response.json", "réponse de convergence")
            if response.get("schema") != SEMANTIC_RESPONSE_SCHEMA:
                raise WorkflowError("Réponse de convergence sémantique invalide")
            family = str(response.get("method_family") or "")
            if family not in ALLOWED_METHOD_FAMILIES:
                raise WorkflowError("Famille de méthode de convergence invalide")
            if not str(response.get("method") or "").strip() or not str(response.get("reviewer") or "").strip():
                raise WorkflowError("Méthode et relecteur sont obligatoires pour la convergence")
            try:
                errors = int(response.get("new_certain_errors"))
            except Exception as exc:
                raise WorkflowError("new_certain_errors doit être un entier") from exc
            if errors < 0:
                raise WorkflowError("new_certain_errors ne peut pas être négatif")
            result = record_semantic_pass(
                project_root, debate_id, str(state["work_id"]), method_family=family,
                method=str(response["method"]), reviewer=str(response["reviewer"]),
                note=str(response.get("note") or ""), new_certain_errors=errors,
            )
            findings = response.get("findings") or []
            if errors > 0:
                _reopen_translation_after_findings(project_root, state, {
                    "schema": "wikidebia-semantic-convergence-findings-1.0",
                    "debate_id": debate_id,
                    "work_id": state.get("work_id"),
                    "recorded_at": now_iso(),
                    "source_review_type": review_type,
                    "new_certain_errors": errors,
                    "findings": findings,
                })
                state["phase"] = "en_translation_correction"
            elif review_type == "semantic_convergence_1":
                state["phase"] = "semantic_convergence_2"
            else:
                if result.get("status") != "converged":
                    raise WorkflowError("Deux passes propres et indépendantes sont requises avant l'application")
                state["phase"] = "apply_render_release"
        else:
            raise WorkflowError(f"Type de revue non pris en charge : {review_type}")

        # The review is consumed only inside the transaction.  If the following
        # local/mechanical transition fails, both this state change and the
        # reviewed control tree are rolled back, so the same review package can
        # safely be retried.  Remote graph actions are the explicit exception:
        # once written, their post-action state is retained for deterministic resume.
        state["pending_review"] = None
        state["status"] = "running"
        state["updated_at"] = now_iso()
        _save_workflow(project_root, state)
        advanced = _mechanical_advance(project_root, state)
    except Exception as exc:
        # A French checkpoint can now be crossed by the mechanical continuation
        # of the combined graph/title review. Detect that irreversible boundary
        # even when it was not entered directly in the review-type branch.
        try:
            current_state = _load_workflow(project_root, debate_id)
        except Exception:
            current_state = state
        if isinstance(exc, FrenchCheckpointError) and bool(exc.remote_execution_started):
            irreversible_french_publication = True
        try:
            previous_state = json.loads(bytes(transaction["workflow_bytes"]).decode("utf-8"))
        except Exception:
            previous_state = {}
        if current_state.get("french_graph_publication") and not previous_state.get("french_graph_publication"):
            irreversible_french_publication = True
            state = current_state
        if current_state.get("french_content_publication") and not previous_state.get("french_content_publication"):
            irreversible_french_publication = True
            state = current_state
        if irreversible_graph_actions:
            # Keep the exact local projection and action receipt that correspond
            # to already committed remote writes.  The workflow remains resumable
            # from its post-action phase and the old review cannot be replayed.
            state["pending_review"] = None
            state["status"] = "running"
            state["updated_at"] = now_iso()
            _save_workflow(project_root, state)
            shutil.rmtree(backup, ignore_errors=True)
            _cleanup_import_transaction_snapshot(transaction)
        elif irreversible_french_publication:
            # Never roll local state back across a remote write. For the first
            # combined graph/title checkpoint the review has already been
            # consumed and promotion completed, so resume from the signed remote
            # checkpoint state. The content checkpoint keeps its historical
            # retry-through-review-import behavior because its workspace base is
            # still the same editable review base.
            state = current_state
            state["status"] = "blocked_remote_publication"
            failed_stage = str(state.get("remote_publication_stage") or ("content" if state.get("french_content_publication") or str((pending or {}).get("review_type") or "") == "fr_content_review" else "graph"))
            if failed_stage == "graph":
                state["phase"] = "graph_publication_resume" if not state.get("french_graph_publication") else "fr_content_review"
                state["pending_review"] = None
            else:
                state["phase"] = "fr_content_review"
                state["pending_review"] = copy.deepcopy(pending) if str((pending or {}).get("review_type") or "") == "fr_content_review" else None
            state["last_remote_publication_error"] = str(exc)
            state["updated_at"] = now_iso()
            _save_workflow(project_root, state)
            shutil.rmtree(backup, ignore_errors=True)
            _cleanup_import_transaction_snapshot(transaction)
        else:
            _rollback_import_transaction(project_root, debate_id, base, backup, transaction)
        raise
    else:
        shutil.rmtree(backup, ignore_errors=True)
        _cleanup_import_transaction_snapshot(transaction)
        return advanced


def status_summary(project_root: Path, debate_id: str) -> dict[str, Any]:
    state = _load_workflow(project_root, validate_debate_id(debate_id))
    return state


def _print_user_result(state: Mapping[str, Any]) -> None:
    pending = state.get("pending_review")
    if isinstance(pending, dict):
        spec = REVIEW_TYPES.get(str(pending.get("review_type")))
        print(spec.user_message if spec else "Revue éditoriale préparée.")
        counts = pending.get("counts") or {}
        if counts.get("placements") is not None:
            print(f"{counts['placements']} placements doivent être analysés par ChatGPT.")
        elif counts.get("arguments") is not None:
            print(f"{counts['arguments']} arguments sont inclus dans cette revue.")
        print("\nEnvoyez ce fichier à ChatGPT :")
        print(pending.get("package_path"))
        print("\nAprès correction, réimportez le ZIP rendu avec :")
        print("Placez le ZIP corrigé dans incoming/, puis lancez :")
        print("./wikidebia review-import")
        print(f"S'il y a plusieurs ZIP de revue : ./wikidebia review-import {state.get('debate_id')}")
        return
    if state.get("status") == "blocked_technical":
        block = state.get("last_block") or {}
        print("Le workflow s’est arrêté sur une incohérence technique avant la prochaine revue éditoriale.")
        errors = block.get("errors") or []
        if errors:
            print("\nErreurs détectées :")
            for item in errors[:8]:
                code = item.get("code") or "ERREUR"
                message = item.get("message") or "Erreur sans libellé"
                print(f"- {code} — {message}")
            if len(errors) > 8:
                print(f"- … {len(errors) - 8} autre(s) erreur(s)")
        print("\nEnvoyez ce fichier à ChatGPT pour diagnostic :")
        print(block.get("diagnostic_path"))
        print("\nAprès mise à jour/correction du kit ou du corpus, relancez simplement la même commande workflow.")
        return
    if state.get("status") == "blocked_final_publication":
        final = state.get("final_publication") or {}
        print("Publication finale bloquée avant achèvement du workflow.")
        print(f"État/diagnostic : {final.get('state_path')}")
        print(f"Écriture distante déjà commencée : {'oui' if final.get('remote_execution_started') else 'non'}")
        print(f"Cause : {final.get('error')}")
        print("Après résolution du conflit ou correction du kit, relancez simplement ./wikidebia workflow avec le même débat.")
        return
    if state.get("status") == "published":
        release = state.get("release") or {}
        final = state.get("final_publication") or {}
        print("Workflow Wikidéb’IA terminé : corpus bilingue publié.")
        print(f"Archive release_ready conservée : {release.get('archive')}")
        installed = final.get("installed_release") or {}
        if installed.get("path"):
            print(f"Corpus actif installé : {installed.get('path')}")
        return
    if state.get("status") == "release_ready":
        release = state.get("release") or {}
        print("Corpus bilingue release_ready; la publication finale reprendra automatiquement à la prochaine relance.")
        print(f"Archive : {release.get('archive')}")
        return
    print(json.dumps(dict(state), ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Orchestration Wikidéb’IA des revues éditoriales jusqu'à la publication finale sûre.")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--machine-readable", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("workflow")
    start.add_argument("debate_title")
    start.add_argument("--debate-id")
    start.add_argument("--short-code")
    start.add_argument("--snapshot", type=Path)
    start.add_argument("--force-refresh", action="store_true")
    imp = sub.add_parser("review-import")
    imp.add_argument("debate_id")
    imp.add_argument("archive", type=Path)
    imp.add_argument("--execute-graph-actions", action="store_true", help="Appliquer et publier immédiatement les décisions structurelles explicites de la revue du graphe")
    imp.add_argument("--authorize-historical-changes", action="store_true", help="Enregistrer le consentement propriétaire pour les seuls deltas historiques explicitement déclarés dans ce ZIP")
    status = sub.add_parser("workflow-status")
    status.add_argument("debate_id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.project_root.expanduser().resolve()
    try:
        if args.command == "workflow":
            snapshot = args.snapshot
            if snapshot is not None and not snapshot.is_absolute():
                snapshot = (root / snapshot).resolve()
            state = start_workflow(root, args.debate_title, debate_id=args.debate_id, short_code=args.short_code, snapshot=snapshot, force_refresh=args.force_refresh)
        elif args.command == "review-import":
            archive = args.archive if args.archive.is_absolute() else (root / args.archive)
            state = import_review(
                root, args.debate_id, archive.resolve(), execute_graph_actions=args.execute_graph_actions,
                authorize_historical_changes=args.authorize_historical_changes,
            )
        else:
            state = status_summary(root, args.debate_id)
    except Exception as exc:
        if args.machine_readable:
            print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False, sort_keys=True))
        else:
            print(f"WIKIDEBIA BLOQUÉ : {exc}", file=sys.stderr)
        return 2
    if args.machine_readable:
        print(json.dumps(state, ensure_ascii=False, sort_keys=True))
    else:
        _print_user_result(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
