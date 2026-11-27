"""Bind the French normalization review to the published source of a translation."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from wikidebia_corpus_build import (
    NORM_VERSION, active_graph, load_json, relative_to_project, write_json,
)
from wikidebia_editorial_workspace import WorkspaceError
from wikidebia_public_visibility import AnonymousMediaWiki, PublicVisibilityError
from wikidebia_publish import sha_text
from wikidebia_workflow_baseline import sha_object


REVIEW_PATH = "reviews/fr/translation_normalization.json"
RECEIPT_PATH = "reviews/fr/translation_normalization_receipt.json"
SCHEMA = "wikidebia-fr-translation-normalization-1.0"
CRITERIA = {
    "graph": "§ 3 — Couverture, fonction et ordre des arguments et objections, sens des liens et cibles canoniques directes.",
    "titles": "§ 4 — Orthographe, typographie, titres canoniques autonomes et titres affichés propres à chaque occurrence.",
    "summaries": "§ 5 — Orthographe, précision et forme des résumés, avec préservation des textes historiques protégés.",
    "sections": "§ 6 — Rubriques autorisées, pertinentes et ordonnées pour chaque page.",
    "keywords": "§ 6 — Mots-clés pertinents, ordonnés et non dupliqués, concepts atomiques, locutions et exceptions motivées.",
    "introduction": "§ 7.5 et 7.9 — Cadrage, structure, terminologie spécialisée, liens, faits et documentation de l’introduction.",
    "documentation": "§ 7 — Sources, citations, attributions, affirmations factuelles et chiffrées, liens, notices et références.",
    "wiki_structure": "§ 8 et 9 — Modèles, paramètres, éléments protégés et dates selon la provenance des pages.",
    "historical_changes": "§ 9.1 et 10 — Portée autorisée des corrections et préservation des autres données historiques.",
    "local_requirements": "§ 13 à 16 — Invariants propres au corpus, exigences éditoriales applicables et cohérence finale des pages.",
}


class FrenchNormalizationError(WorkspaceError):
    pass


class FrenchNormalizationMissing(FrenchNormalizationError):
    pass


def _load_sealed(path: Path, field: str, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise FrenchNormalizationError(f"{label} absent : {path}")
    value = load_json(path, label)
    body = dict(value)
    digest = body.pop(field, None)
    if not digest or digest != sha_object(body):
        raise FrenchNormalizationError(f"Empreinte du {label} invalide")
    return value


def _published_pages(project_root: Path, source: Path, meta: Mapping[str, Any]) -> list[dict[str, Any]]:
    debate_id, work_id = meta["debate_id"], meta["work_id"]
    registry = load_json(source / "data/registre_debat.json", "registre du débat")
    nodes, _, _ = active_graph(registry)
    expected = {"debate": registry["debate"]["pages"]["fr"]["canonical_title"]}
    expected.update({node["id"]: node["fr"]["canonical_title"] for node in nodes})
    preservation = source / "data/source_preservation_receipt.json"
    if preservation.is_file():
        frozen = _load_sealed(preservation, "receipt_sha256", "reçu de préservation française")
        if (
            frozen.get("debate_id") != debate_id or frozen.get("work_id") != work_id
            or frozen["receipt_sha256"] != (meta.get("source_preservation") or {}).get("receipt_sha256")
        ):
            raise FrenchNormalizationError("Le reçu de préservation appartient à une autre source française")
        imports = []
        for row in frozen["pages"]:
            page_path = source / row["import_path"]
            imports.append({
                "page_id": debate_id if row["kind"] == "debate" else row["page_id"],
                "page_type": row["kind"], "status": "published",
                "canonical_title": row["canonical_title"], "revision_id": row["revision_id"],
                "content_sha256": sha_text(page_path.read_text(encoding="utf-8")),
            })
    else:
        checkpoint_root = project_root / ".state/fr-publication" / debate_id / work_id
        publication_path = checkpoint_root / "content/publication-receipt.json"
        publication = _load_sealed(publication_path, "receipt_sha256", "reçu de publication du contenu français")
        checkpoint = _load_sealed(checkpoint_root / "content/checkpoint.json", "receipt_sha256", "reçu du checkpoint français")
        state = _load_sealed(
            project_root / ".state/published" / debate_id / "fr/latest.json",
            "state_sha256", "dernier état publié français",
        )
        if (
            publication.get("debate_id") != debate_id or publication.get("work_id") != work_id
            or publication.get("stage") != "content"
            or publication.get("status") not in {"published", "verified_no_changes"}
            or checkpoint.get("debate_id") != debate_id or checkpoint.get("work_id") != work_id
            or checkpoint.get("stage") != "content"
            or publication.get("checkpoint_tree_sha256") != checkpoint.get("checkpoint_tree_sha256")
            or checkpoint.get("source_tree_sha256") != meta["content_reviewed_copy"]["tree_sha256"]
            or state.get("debate_id") != debate_id or state.get("language") != "fr"
            or (publication.get("published_state") or {}).get("state_sha256") != state["state_sha256"]
        ):
            raise FrenchNormalizationError("L’état publié français ne correspond plus au checkpoint de ce Work")
        imports = state["pages"]

    pages = {}
    for row in imports:
        if row.get("status") != "published":
            continue
        key = "debate" if row["page_type"] == "debate" else row["page_id"]
        revision = row.get("revision_id")
        title = row.get("canonical_title")
        if (key in pages or key not in expected or title != expected[key]
                or type(revision) is not int or revision <= 0 or not row.get("content_sha256")):
            raise FrenchNormalizationError(f"Révision française invalide ou cible divergente pour {key}")
        pages[key] = {
            "page_id": key, "title": title, "revision_id": revision,
            "content_sha256": row["content_sha256"],
            "url": "https://fr.wikidebates.org/wiki/" + quote(title.replace(" ", "_"), safe=""),
            "revision_url": f"https://fr.wikidebates.org/w/rest.php/v1/revision/{revision}/html",
        }
    if set(pages) != set(expected) or len({row["title"] for row in pages.values()}) != len(pages):
        raise FrenchNormalizationError("L’état publié ne couvre pas exactement le débat et les arguments actifs")
    return [pages[key] for key in sorted(pages, key=lambda key: (key != "debate", key))]


def _prior_review_evidence(source: Path, meta: Mapping[str, Any], pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Reuse only complete classification decisions from the locked source.

    The preservation path is not a new approval of historical classification.
    An old or incomplete lock remains reviewable but cannot auto-discharge a
    criterion. The published-page binding and live check remain independent.
    """
    metadata = load_json(source / "data/fr_page_metadata_lock.json", "verrou des métadonnées françaises")
    vocabulary = load_json(source / "data/keyword_vocabulary.json", "vocabulaire français")
    evidence = {
        "mode": "preservation" if (source / "data/source_preservation_receipt.json").is_file() else "editorial",
        "metadata_lock_sha256": sha_object(metadata),
        "vocabulary_sha256": sha_object(vocabulary),
        "classification_review_sha256": metadata.get("classification_review_sha256") or metadata.get("review_sha256"),
        "reusable_criteria": [],
        "page_ids": [],
    }
    if evidence["mode"] != "editorial" or metadata.get("status") != "locked_for_generation":
        return evidence
    if (metadata.get("debate_id") != meta["debate_id"] or metadata.get("work_id") != meta["work_id"]
            or not evidence["classification_review_sha256"]):
        return evidence
    rows = [("debate", metadata.get("debate"))]
    rows.extend((row.get("entity_id"), row) for row in metadata.get("arguments") or [] if isinstance(row, dict))
    by_id = dict(rows)
    if len(by_id) != len(rows) or set(by_id) != {page["page_id"] for page in pages}:
        return evidence
    if any(not isinstance(by_id[page["page_id"]], dict)
           or by_id[page["page_id"]].get("canonical_title") != page["title"]
           or not by_id[page["page_id"]].get("reviewer")
           or not by_id[page["page_id"]].get("reviewed_at") for page in pages):
        return evidence

    def complete_rationales(row: Mapping[str, Any], field: str) -> bool:
        values = row.get(field)
        rationales = (row.get("rationales") or {}).get(field)
        return (isinstance(values, list) and bool(values) and isinstance(rationales, dict)
                and set(rationales) == set(values)
                and all(isinstance(note, str) and note.strip() for note in rationales.values()))

    evidence["page_ids"] = [page["page_id"] for page in pages]
    if all(complete_rationales(row, "rubriques") for row in by_id.values()):
        evidence["reusable_criteria"].append("sections")
    terms = {term for row in by_id.values() for term in row.get("keywords") or []}
    vocab_terms = {row.get("fr") for row in vocabulary.get("entries") or [] if isinstance(row, dict)}
    if (vocabulary.get("status") == "approved_fr"
            and vocabulary.get("review_sha256") == evidence["classification_review_sha256"]
            and terms == vocab_terms
            and all(complete_rationales(row, "keywords")
                    and (row.get("attestations") or {}).get("keywords_ordered_by_relevance") is True
                    and (row.get("rationales") or {}).get("keyword_order")
                    for row in by_id.values())):
        evidence["reusable_criteria"].append("keywords")
    return evidence


def _binding(source: Path, meta: Mapping[str, Any], pages: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": SCHEMA, "normative_revision": NORM_VERSION,
        "debate_id": meta["debate_id"], "work_id": meta["work_id"],
        "french_source_tree_sha256": meta["content_reviewed_copy"]["tree_sha256"],
        "pages": pages,
        "prior_review_evidence": _prior_review_evidence(source, meta, pages),
        "normative_reference": "norms/normative_reference/01_normes/WIKIDEBIA_NORME_ACTIVE.md",
    }


def verify_live_pages(pages: list[dict[str, Any]]) -> None:
    reader = AnonymousMediaWiki()
    reader.headers["Cache-Control"] = "no-cache"
    for start in range(0, len(pages), 50):
        batch = pages[start:start + 50]
        try:
            observed = reader.pages("fr", [page["title"] for page in batch])
        except PublicVisibilityError as exc:
            raise FrenchNormalizationError("Impossible de vérifier les révisions actuelles sur le wiki français") from exc
        for page in batch:
            row = observed.get(page["title"], {})
            if (row.get("exists") is not True or row.get("redirect") is not False
                    or row.get("revision_id") != page["revision_id"]
                    or not isinstance(row.get("text"), str)
                    or sha_text(row["text"]) != page["content_sha256"]):
                raise FrenchNormalizationError(
                    f"Révision française non confirmée pour « {page['title']} » "
                    f"(révision revue {page['revision_id']}, révision actuelle {row.get('revision_id')})"
                )


def prepare_normalization(
    project_root: Path, workspace: Path, source: Path, meta: Mapping[str, Any], *, overwrite: bool,
) -> dict[str, Any]:
    binding = _binding(source, meta, _published_pages(project_root, source, meta))
    path = workspace / REVIEW_PATH
    verify_live_pages(binding["pages"])
    if path.exists() and not overwrite:
        existing = load_json(path, "revue de normalisation française")
        if any(existing.get(key) != value for key, value in binding.items()):
            raise FrenchNormalizationError("La base française a changé. Régénérer la revue avec --prepare-normalization --overwrite-review")
    else:
        write_json(path, {
            **binding, "reviewer": "",
            "criteria": {
                key: {
                    "rule": rule,
                    "status": "reused" if key in binding["prior_review_evidence"]["reusable_criteria"] else "pending",
                    "note": ("Décisions individuelles verrouillées ; couverture exacte des pages publiées."
                             if key in binding["prior_review_evidence"]["reusable_criteria"] else ""),
                }
                for key, rule in CRITERIA.items()
            },
        })
    return {
        "status": "french_normalization_review_required",
        "review_path": relative_to_project(path, project_root),
        "pages": binding["pages"],
    }


def verify_normalization(
    project_root: Path, workspace: Path, source: Path, meta: Mapping[str, Any],
) -> dict[str, Any]:
    path = workspace / REVIEW_PATH
    command = (
        f"./wikidebia corpus-workspace-translation {meta['debate_id']} --work-id {meta['work_id']}"
        " --prepare-normalization"
    )
    if not path.is_file() or path.is_symlink():
        raise FrenchNormalizationMissing(f"Revue de normalisation française obligatoire. Préparer la revue avec {command}")
    report = load_json(path, "revue de normalisation française")
    binding = _binding(source, meta, _published_pages(project_root, source, meta))
    _validate_report(report, binding, command)
    return {**report, "receipt_sha256": sha_object(report)}


def _validate_report(
    report: Mapping[str, Any], binding: Mapping[str, Any], prepare_command: str,
) -> None:
    if set(report) != {*binding, "reviewer", "criteria"}:
        raise FrenchNormalizationError("Structure de la revue de normalisation française invalide")
    if any(report.get(key) != value for key, value in binding.items()):
        raise FrenchNormalizationError(f"La revue française porte sur une autre source. Relancer {prepare_command} --overwrite-review")
    results = report.get("criteria")
    if not isinstance(results, dict) or set(results) != set(CRITERIA):
        raise FrenchNormalizationError("La revue française doit couvrir exactement la liste des critères de normalisation")
    reviewer = report.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise FrenchNormalizationError("Indiquer le relecteur de la normalisation française")
    incomplete = []
    reusable = binding["prior_review_evidence"]["reusable_criteria"]
    for key, rule in CRITERIA.items():
        row = results[key]
        allowed = {"checked", "exception", "not_applicable"}
        if key in reusable:
            allowed.add("reused")
        if (not isinstance(row, dict) or row.get("rule") != rule
                or row.get("status") not in allowed
                or not isinstance(row.get("note"), str) or not row["note"].strip()):
            incomplete.append(key)
    if incomplete:
        raise FrenchNormalizationError("Critères français sans résultat ou décision motivée : " + ", ".join(incomplete))


def verify_bound_normalization(
    project_root: Path, workspace: Path, source: Path, meta: Mapping[str, Any],
    english_review: Mapping[str, Any],
) -> None:
    receipt_path = workspace / RECEIPT_PATH
    if not receipt_path.is_file():
        raise FrenchNormalizationError("Reçu de normalisation française absent. Relancer la préparation anglaise")
    sealed = _load_sealed(receipt_path, "receipt_sha256", "reçu de normalisation française")
    receipt_sha = sealed.pop("receipt_sha256")
    report = load_json(workspace / REVIEW_PATH, "revue de normalisation française")
    if sealed != report or english_review.get("french_normalization_receipt_sha256") != receipt_sha:
        raise FrenchNormalizationError("Le reçu français diverge de la revue anglaise. Relancer la préparation anglaise")
    command = (
        f"./wikidebia corpus-workspace-translation {meta['debate_id']} --work-id {meta['work_id']}"
        " --prepare-normalization"
    )
    # A local translation checkpoint carries the sealed pages. If an installed
    # publication state is present, ensure it still describes those revisions.
    publication = project_root / ".state/published" / meta["debate_id"] / "fr/latest.json"
    pages = _published_pages(project_root, source, meta) if publication.exists() else sealed["pages"]
    _validate_report(report, _binding(source, meta, pages), command)
