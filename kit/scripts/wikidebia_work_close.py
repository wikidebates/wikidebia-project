#!/usr/bin/env python3
"""Close a completed editorial Work after a verified remote execution.

The command is local-only.  It verifies the complete signed chain from the
release copy to the remote execution receipt and the latest published states,
archives the comparison/review/execution evidence, atomically exchanges the
active corpus with the exact release copy, preserves the previous corpus, and
writes an end-to-end closure receipt.
"""
from __future__ import annotations

import argparse
import copy
import ctypes
import errno
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from wikidebia_corpus_build import (
    NORM_VERSION,
    VALIDATOR_VERSION,
    assert_control_directory,
    assert_no_symlinks,
    exclusive_lock,
    full_tree_sha256,
    load_json,
    now_iso,
    relative_to_project,
    sha256_file,
    validate_debate_id,
    write_json,
)
from wikidebia_editorial_review import _run_validator
from wikidebia_editorial_workspace import WorkspaceError, fsync_directory, validate_work_id, workspace_receipt_hash
from wikidebia_remote_compare import _validate_comparison_id
from wikidebia_remote_execute import (
    AUTHORIZATION_SCHEMA,
    EXECUTION_RECEIPT_SCHEMA,
    PREFLIGHT_SCHEMA,
    _canonical,
)
from wikidebia_render import _load_workspace
from wikidebia_update import KIT_VERSION, sha_object, sha_text

CLOSURE_SCHEMA = "wikidebia-work-closure-receipt-1.0"
CLOSURE_PREFLIGHT_SCHEMA = "wikidebia-work-closure-preflight-1.0"
EVIDENCE_MANIFEST_SCHEMA = "wikidebia-work-evidence-manifest-1.0"
COMPLETED_INDEX_SCHEMA = "wikidebia-completed-work-index-1.0"


class WorkClosureError(WorkspaceError):
    pass


def _canonical_sha(value: Mapping[str, Any], excluded: str) -> str:
    body = dict(value)
    body.pop(excluded, None)
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _closure_dir(project_root: Path, debate_id: str, work_id: str, comparison_id: str) -> Path:
    state = assert_control_directory(project_root / ".state", project_root, create=True)
    closures = assert_control_directory(state / "work-closures", project_root, create=True)
    debate = assert_control_directory(closures / debate_id, project_root, create=True)
    work = assert_control_directory(debate / work_id, project_root, create=True)
    return work / comparison_id


def _archive_dir(project_root: Path, debate_id: str, work_id: str, comparison_id: str) -> Path:
    archives = assert_control_directory(project_root / "archives", project_root, create=True)
    completed = assert_control_directory(archives / "completed-works", project_root, create=True)
    debate = assert_control_directory(completed / debate_id, project_root, create=True)
    work = assert_control_directory(debate / work_id, project_root, create=True)
    return work / comparison_id


def _load_execution(project_root: Path, debate_id: str, work_id: str, comparison_id: str, confirmation: str) -> dict[str, Any]:
    workspace, meta = _load_workspace(project_root, debate_id, work_id)
    if meta.get("status") not in {"remote_execution_completed", "remote_execution_no_changes", "work_closed"}:
        raise WorkClosureError(f"Statut incompatible avec la clôture : {meta.get('status')}")
    release_copy = workspace / "release-copy"
    if not release_copy.is_dir() or release_copy.is_symlink():
        raise WorkClosureError("release-copy absente ou non sûre")
    assert_no_symlinks(release_copy)
    release_sha = full_tree_sha256(release_copy)
    expected_release_sha = str((meta.get("release_copy") or {}).get("tree_sha256") or "")
    if not expected_release_sha or release_sha != expected_release_sha:
        raise WorkClosureError("release-copy a changé depuis sa libération")

    execution_dir = project_root / ".state" / "remote-executions" / debate_id / work_id / comparison_id
    if not execution_dir.is_dir() or execution_dir.is_symlink():
        raise WorkClosureError("Dossier d’exécution distante absent ou non sûr")
    assert_no_symlinks(execution_dir)
    paths = {
        "receipt": execution_dir / "execution-receipt.json",
        "preflight": execution_dir / "execution-preflight.json",
        "authorization": execution_dir / "execution-authorization.json",
        "events": execution_dir / "execution-events.jsonl",
    }
    for label, path in paths.items():
        if not path.is_file() or path.is_symlink():
            raise WorkClosureError(f"Preuve d’exécution absente : {label}")
    receipt = load_json(paths["receipt"], "reçu d’exécution")
    preflight = load_json(paths["preflight"], "préflight d’exécution")
    authorization = load_json(paths["authorization"], "autorisation d’exécution")
    if receipt.get("schema") != EXECUTION_RECEIPT_SCHEMA or receipt.get("receipt_sha256") != _canonical(receipt, "receipt_sha256"):
        raise WorkClosureError("Reçu d’exécution invalide")
    if confirmation != receipt.get("receipt_sha256"):
        raise WorkClosureError("L’empreinte confirmée ne correspond pas au reçu d’exécution")
    if receipt.get("status") not in {"executed", "no_changes"} or receipt.get("execution_completed") is not True:
        raise WorkClosureError("L’exécution distante n’est pas terminée avec succès")
    # Producer release versions are provenance. The execution receipt schema,
    # signed hashes and release-copy identity are the compatibility/integrity gates.
    if preflight.get("schema") != PREFLIGHT_SCHEMA or preflight.get("preflight_sha256") != _canonical(preflight, "preflight_sha256"):
        raise WorkClosureError("Préflight d’exécution invalide")
    if authorization.get("schema") != AUTHORIZATION_SCHEMA or authorization.get("authorization_sha256") != _canonical(authorization, "authorization_sha256"):
        raise WorkClosureError("Autorisation d’exécution invalide")
    expected_links = {
        "preflight_sha256": preflight.get("preflight_sha256"),
        "authorization_sha256": authorization.get("authorization_sha256"),
        "plan_sha256": preflight.get("plan_sha256"),
        "acceptance_sha256": preflight.get("acceptance_sha256"),
    }
    for field, value in expected_links.items():
        if receipt.get(field) != value:
            raise WorkClosureError(f"Chaîne d’exécution divergente : {field}")
    if preflight.get("release_copy_tree_sha256") != release_sha:
        raise WorkClosureError("Le préflight ne vise pas la release-copy actuelle")
    if authorization.get("preflight_sha256") != preflight.get("preflight_sha256") or authorization.get("plan_sha256") != preflight.get("plan_sha256"):
        raise WorkClosureError("L’autorisation ne vise pas le préflight chargé")
    if authorization.get("remote_write_authorized") is not True or authorization.get("execution_started") is not True:
        raise WorkClosureError("L’autorisation d’exécution n’a pas été armée")
    if sha256_file(paths["events"]) != receipt.get("events_file_sha256"):
        raise WorkClosureError("Journal d’exécution absent ou altéré")
    underlying = receipt.get("underlying_receipt") or {}
    if receipt.get("underlying_receipt_sha256") != underlying.get("receipt_sha256"):
        raise WorkClosureError("Reçu sous-jacent divergent")
    unsigned_underlying = dict(underlying)
    claimed_underlying = unsigned_underlying.pop("receipt_sha256", None)
    if claimed_underlying != sha_object(unsigned_underlying):
        raise WorkClosureError("Empreinte du reçu sous-jacent invalide")
    return {
        "workspace": workspace,
        "meta": meta,
        "release_copy": release_copy,
        "release_sha256": release_sha,
        "execution_dir": execution_dir,
        "execution_receipt": receipt,
        "preflight": preflight,
        "authorization": authorization,
        "paths": paths,
    }


def _release_pages(release_copy: Path) -> dict[str, dict[str, dict[str, Any]]]:
    manifest = load_json(release_copy / "manifest.json", "manifest du corpus final")
    pages: dict[str, dict[str, dict[str, Any]]] = {}
    for row in manifest.get("pages") or []:
        language = str(row.get("language") or "")
        page_id = str(row.get("page_id") or "")
        file_path = str(row.get("file_path") or row.get("source_path") or "")
        path = release_copy / file_path
        if language not in {"fr", "en"} or not page_id or not path.is_file() or path.is_symlink():
            raise WorkClosureError(f"Page finale invalide dans le manifeste : {language}/{page_id}")
        content_sha = sha_text(path.read_text(encoding="utf-8"))
        declared = str(row.get("sha256") or "")
        if declared and declared not in {content_sha, sha256_file(path)}:
            raise WorkClosureError(f"Empreinte de page divergente dans release-copy : {language}/{page_id}")
        pages.setdefault(language, {})[page_id] = {
            "page_id": page_id,
            "page_type": str(row.get("page_type") or "unknown"),
            "canonical_title": str(row.get("canonical_title") or ""),
            "content_sha256": content_sha,
            "file_path": file_path,
        }
    if not pages:
        raise WorkClosureError("Le corpus final ne contient aucune page")
    return pages


def _effective_remote_pages(
    project_root: Path,
    execution: Mapping[str, Any],
    release_pages: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> dict[str, dict[str, dict[str, Any]]]:
    """Return the exact page identities attested by the executed update plan.

    Most plan operations publish the release file byte for byte.  An adopted
    pre-existing page can instead use a signed effective file to retain remote
    lifecycle metadata (for example its original creation date).  The release
    remains the editorial artifact, while the effective file is the content
    that the execution receipt proves was actually published.
    """
    receipt = execution["execution_receipt"]
    plan_path = (
        project_root
        / ".state"
        / "remote-comparisons"
        / str(receipt["debate_id"])
        / str(receipt["work_id"])
        / str(receipt["comparison_id"])
        / "update-plan.json"
    )
    if not plan_path.is_file() or plan_path.is_symlink():
        raise WorkClosureError("Plan d’exécution final absent ou non sûr")
    plan = load_json(plan_path, "plan d’exécution final")
    unsigned = dict(plan)
    claimed = unsigned.pop("plan_sha256", None)
    if claimed != sha_object(unsigned) or claimed != receipt.get("plan_sha256"):
        raise WorkClosureError("Plan d’exécution final invalide ou divergent")

    expected = copy.deepcopy(release_pages)
    for category, rows in (plan.get("operations") or {}).items():
        if not isinstance(rows, list):
            raise WorkClosureError(f"Opérations invalides dans le plan final : {category}")
        for row in rows:
            if not isinstance(row, dict):
                raise WorkClosureError(f"Opération invalide dans le plan final : {category}")
            language = str(row.get("language") or row.get("wiki") or "")
            page_id = str(row.get("page_id") or "")
            page = expected.get(language, {}).get(page_id)
            if page is None:
                continue
            if str(row.get("title") or "") != page["canonical_title"]:
                raise WorkClosureError(f"Titre effectif divergent dans le plan final : {language}/{page_id}")
            effective_sha = str(row.get("new_sha256") or "")
            if not effective_sha or effective_sha == page["content_sha256"]:
                continue

            # A differing effective page is accepted only when the signed plan
            # explicitly ties it back to this exact release page and to an
            # adopted remote revision.  This prevents an unrelated plan file
            # from weakening the release-copy comparison during closure.
            if category != "update" or not isinstance(row.get("remote_adoption"), dict):
                raise WorkClosureError(f"Contenu effectif non autorisé dans le plan final : {language}/{page_id}")
            if str(row.get("original_new_sha256") or "") != page["content_sha256"]:
                raise WorkClosureError(f"Origine du contenu effectif divergente : {language}/{page_id}")
            original_path = project_root / str(row.get("original_source_path") or "")
            release_path = execution["release_copy"] / page["file_path"]
            if original_path.resolve() != release_path.resolve():
                raise WorkClosureError(f"Source originale effective divergente : {language}/{page_id}")
            effective_path = project_root / str(row.get("source_path") or "")
            effective_root = project_root / ".state" / "update-effective"
            try:
                effective_path.resolve().relative_to(effective_root.resolve())
            except ValueError as exc:
                raise WorkClosureError(f"Source effective hors périmètre : {language}/{page_id}") from exc
            if not effective_path.is_file() or effective_path.is_symlink():
                raise WorkClosureError(f"Source effective absente ou non sûre : {language}/{page_id}")
            if sha_text(effective_path.read_text(encoding="utf-8")) != effective_sha:
                raise WorkClosureError(f"Empreinte du contenu effectif divergente : {language}/{page_id}")
            lifecycle = row.get("lifecycle_preservation") or {}
            if str(lifecycle.get("effective_source_path") or "") != str(row.get("source_path") or ""):
                raise WorkClosureError(f"Preuve de préservation effective absente : {language}/{page_id}")
            page["content_sha256"] = effective_sha
            page["effective_source_path"] = str(row.get("source_path"))
    return expected


def _verify_published_states(project_root: Path, debate_id: str, execution: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    release_pages = _release_pages(execution["release_copy"])
    expected = _effective_remote_pages(project_root, execution, release_pages)
    receipt = execution["execution_receipt"]
    receipt_states = receipt.get("published_states") or {}
    states: dict[str, dict[str, Any]] = {}
    for language, expected_pages in sorted(expected.items()):
        path = project_root / ".state" / "published" / debate_id / language / "latest.json"
        if not path.is_file() or path.is_symlink():
            raise WorkClosureError(f"État publié final absent : {language}")
        state = load_json(path, f"état publié {language}")
        unsigned = dict(state)
        claimed = unsigned.pop("state_sha256", None)
        if claimed != sha_object(unsigned):
            raise WorkClosureError(f"État publié final non signé : {language}")
        if state.get("debate_id") != debate_id or state.get("language") != language:
            raise WorkClosureError(f"État publié rattaché au mauvais corpus : {language}")
        # A bilingual release can be published in ordered checkpoints.  Only
        # languages covered by this final execution must link to its plan and
        # receipt; earlier languages retain their own signed publication state.
        if language in receipt_states:
            if state.get("plan_sha256") != receipt.get("plan_sha256"):
                raise WorkClosureError(f"État publié lié à un autre plan : {language}")
            if state.get("receipt_sha256") != receipt.get("underlying_receipt_sha256"):
                raise WorkClosureError(f"État publié lié à un autre reçu : {language}")
        actual_pages = {str(row.get("page_id")): row for row in state.get("pages") or []}
        pending = [row for row in actual_pages.values() if row.get("status") == "pending_delete"]
        if pending:
            raise WorkClosureError(f"Clôture interdite : {len(pending)} suppression(s) restent différées en {language}")
        if set(actual_pages) != set(expected_pages):
            missing = sorted(set(expected_pages) - set(actual_pages))
            extra = sorted(set(actual_pages) - set(expected_pages))
            raise WorkClosureError(f"État publié incomplet en {language}; absents={missing[:3]}, supplémentaires={extra[:3]}")
        for page_id, expected_page in expected_pages.items():
            actual = actual_pages[page_id]
            if actual.get("status") != "published":
                raise WorkClosureError(f"Page non publiée dans l’état final : {language}/{page_id}")
            if actual.get("canonical_title") != expected_page["canonical_title"] or actual.get("content_sha256") != expected_page["content_sha256"]:
                raise WorkClosureError(f"État publié divergent de release-copy : {language}/{page_id}")
            if not isinstance(actual.get("revision_id"), int):
                raise WorkClosureError(f"Révision distante absente : {language}/{page_id}")
        states[language] = {
            "path": relative_to_project(path, project_root),
            "state_sha256": claimed,
            "page_count": len(actual_pages),
        }
    if not receipt_states or not set(receipt_states).issubset(states):
        raise WorkClosureError("Le reçu d’exécution ne couvre aucune langue finale valide")
    for language, attested in receipt_states.items():
        value = states[language]
        if attested.get("state_sha256") != value["state_sha256"]:
            raise WorkClosureError(f"Le reçu d’exécution ne vise pas l’état publié actuel : {language}")
    return states


def _copy_evidence_file(project_root: Path, source: Path, destination_root: Path) -> None:
    if not source.is_file() or source.is_symlink():
        raise WorkClosureError(f"Preuve absente ou non sûre : {source}")
    relative = relative_to_project(source, project_root)
    destination = destination_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _copy_evidence_tree(project_root: Path, source: Path, destination_root: Path) -> None:
    if not source.is_dir() or source.is_symlink():
        raise WorkClosureError(f"Dossier de preuves absent ou non sûr : {source}")
    assert_no_symlinks(source)
    destination = destination_root / relative_to_project(source, project_root)
    shutil.copytree(source, destination, copy_function=shutil.copy2)


def _inventory(root: Path, excluded: set[str]) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rel = path.relative_to(root).as_posix()
        if rel in excluded:
            continue
        rows.append({"path": rel, "size_bytes": path.stat().st_size, "sha256": sha256_file(path)})
    return rows


def _zip_tree(source: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            rel = path.relative_to(source).as_posix()
            info = zipfile.ZipInfo(rel, date_time=(2026, 8, 4, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def _build_evidence_archive(project_root: Path, execution: Mapping[str, Any], closure_root: Path, archive_root: Path, states: Mapping[str, Any]) -> dict[str, Any]:
    temp = Path(tempfile.mkdtemp(prefix=".evidence.tmp-", dir=archive_root.parent))
    try:
        evidence = temp / "evidence"
        evidence.mkdir()
        workspace = execution["workspace"]
        _copy_evidence_file(project_root, workspace / "workspace.json", evidence)
        _copy_evidence_file(project_root, execution["release_copy"] / "manifest.json", evidence)
        _copy_evidence_file(project_root, execution["release_copy"] / "release" / "release_manifest.json", evidence)
        release_artifact = project_root / ".state" / "corpus-releases" / execution["execution_receipt"]["debate_id"] / execution["execution_receipt"]["work_id"]
        if release_artifact.is_dir():
            _copy_evidence_tree(project_root, release_artifact, evidence)
        comparison = project_root / ".state" / "remote-comparisons" / execution["execution_receipt"]["debate_id"] / execution["execution_receipt"]["work_id"] / execution["execution_receipt"]["comparison_id"]
        review = project_root / ".state" / "remote-plan-reviews" / execution["execution_receipt"]["debate_id"] / execution["execution_receipt"]["work_id"] / execution["execution_receipt"]["comparison_id"]
        _copy_evidence_tree(project_root, comparison, evidence)
        _copy_evidence_tree(project_root, review, evidence)
        _copy_evidence_tree(project_root, execution["execution_dir"], evidence)
        for value in states.values():
            _copy_evidence_file(project_root, project_root / value["path"], evidence)
        manifest_rel = "evidence-manifest.json"
        manifest = {
            "schema": EVIDENCE_MANIFEST_SCHEMA,
            "debate_id": execution["execution_receipt"]["debate_id"],
            "work_id": execution["execution_receipt"]["work_id"],
            "comparison_id": execution["execution_receipt"]["comparison_id"],
            "created_at": now_iso(),
            "files": _inventory(evidence, {manifest_rel}),
            "self_excluded": [manifest_rel],
        }
        manifest["manifest_sha256"] = _canonical_sha(manifest, "manifest_sha256")
        write_json(evidence / manifest_rel, manifest)
        archive_root.mkdir(parents=True, exist_ok=False)
        archive_path = archive_root / "work-evidence.zip"
        _zip_tree(evidence, archive_path)
        write_json(archive_root / "evidence-manifest.json", manifest)
        return {
            "archive": archive_path,
            "archive_sha256": sha256_file(archive_path),
            "archive_size_bytes": archive_path.stat().st_size,
            "manifest": archive_root / "evidence-manifest.json",
            "manifest_sha256": sha256_file(archive_root / "evidence-manifest.json"),
        }
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def _rename_exchange(first: Path, second: Path) -> None:
    if first.stat().st_dev != second.stat().st_dev:
        raise WorkClosureError("Échange atomique impossible entre systèmes de fichiers différents")
    libc = ctypes.CDLL(None, use_errno=True)
    function = getattr(libc, "renameat2", None)
    if function is None:
        raise WorkClosureError("Le système ne fournit pas renameat2; clôture atomique refusée")
    function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    function.restype = ctypes.c_int
    result = function(-100, os.fsencode(first), -100, os.fsencode(second), 2)
    if result != 0:
        error = ctypes.get_errno()
        if error in {errno.ENOSYS, errno.EINVAL, errno.EXDEV, errno.ENOTSUP}:
            raise WorkClosureError("Le système de fichiers ne prend pas en charge l’échange atomique de dossiers")
        raise WorkClosureError(f"Échec de l’échange atomique : {os.strerror(error)}")


def _verify_active_source(project_root: Path, debate_id: str, meta: Mapping[str, Any]) -> tuple[Path, str]:
    active = project_root / "corpus" / debate_id
    if not active.is_dir() or active.is_symlink():
        raise WorkClosureError("Le corpus actif d’origine est absent ou non sûr")
    assert_no_symlinks(active)
    actual = full_tree_sha256(active)
    expected = str((meta.get("source") or {}).get("tree_sha256") or "")
    if expected and actual != expected:
        raise WorkClosureError("Le corpus actif a changé depuis l’ouverture du Work")
    return active, actual


def _chain_hashes(meta: Mapping[str, Any], execution: Mapping[str, Any]) -> dict[str, Any]:
    keys = [
        "source", "working_copy", "reviewed_copy", "content_reviewed_copy",
        "translated_copy", "rendered_copy", "release_copy", "local_release",
        "remote_comparison", "remote_plan_review", "remote_execution",
    ]
    result: dict[str, Any] = {}
    for key in keys:
        value = meta.get(key)
        if isinstance(value, dict):
            selected = {name: item for name, item in value.items() if "sha256" in name or name in {"path", "status", "comparison_id", "mode"}}
            if selected:
                result[key] = selected
    result["execution_receipt_sha256"] = execution["execution_receipt"]["receipt_sha256"]
    return result


def close_work(project_root: Path, debate_id: str, work_id: str, comparison_id: str, confirm_execution_sha256: str) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    debate_id = validate_debate_id(debate_id)
    work_id = validate_work_id(work_id)
    comparison_id = _validate_comparison_id(comparison_id)
    closure_root = _closure_dir(project_root, debate_id, work_id, comparison_id)
    final_receipt_path = closure_root / "work-closure-receipt.json"
    if final_receipt_path.is_file():
        receipt = load_json(final_receipt_path, "reçu de clôture")
        if receipt.get("receipt_sha256") != _canonical_sha(receipt, "receipt_sha256"):
            raise WorkClosureError("Reçu de clôture existant invalide")
        if confirm_execution_sha256 != receipt.get("execution_receipt_sha256"):
            raise WorkClosureError("La confirmation ne correspond pas à la clôture existante")
        active = project_root / "corpus" / debate_id
        if not active.is_dir() or full_tree_sha256(active) != receipt.get("active_corpus_tree_sha256"):
            raise WorkClosureError("Le corpus actif a changé après la clôture")
        return {**receipt, "idempotent": True}
    if closure_root.exists() or closure_root.is_symlink():
        raise WorkClosureError("Une clôture partielle existe déjà pour cette comparaison")

    execution = _load_execution(project_root, debate_id, work_id, comparison_id, confirm_execution_sha256)
    active, old_tree_sha = _verify_active_source(project_root, debate_id, execution["meta"])
    states = _verify_published_states(project_root, debate_id, execution)
    closure_root.mkdir(parents=False)

    validation_json = closure_root / "closure-validation.json"
    validation_txt = closure_root / "closure-validation.txt"
    validation = _run_validator(project_root, execution["release_copy"], scopes=("all",), json_output=validation_json, text_output=validation_txt)
    if validation.get("result") not in {"passed", "passed_with_warnings"} or int((validation.get("summary") or {}).get("errors", 0)) != 0:
        raise WorkClosureError("La validation fraîche du corpus publié a échoué")

    archive_root = _archive_dir(project_root, debate_id, work_id, comparison_id)
    if archive_root.exists() or archive_root.is_symlink():
        raise WorkClosureError("Le dossier d’archive du Work existe déjà")
    evidence = _build_evidence_archive(project_root, execution, closure_root, archive_root, states)

    corpus_parent = active.parent
    if corpus_parent.stat().st_dev != archive_root.parent.stat().st_dev:
        raise WorkClosureError("La sauvegarde du corpus précédent ne peut pas rester sur le même système de fichiers")
    staging = Path(tempfile.mkdtemp(prefix=f".{debate_id}.published.tmp-", dir=corpus_parent))
    shutil.rmtree(staging)
    shutil.copytree(execution["release_copy"], staging, copy_function=shutil.copy2)
    assert_no_symlinks(staging)
    new_tree_sha = full_tree_sha256(staging)
    if new_tree_sha != execution["release_sha256"]:
        raise WorkClosureError("La copie de promotion ne correspond pas à release-copy")

    preflight = {
        "schema": CLOSURE_PREFLIGHT_SCHEMA,
        "debate_id": debate_id,
        "work_id": work_id,
        "comparison_id": comparison_id,
        "prepared_at": now_iso(),
        "execution_receipt_sha256": execution["execution_receipt"]["receipt_sha256"],
        "release_copy_tree_sha256": execution["release_sha256"],
        "active_corpus_tree_sha256_before": old_tree_sha,
        "published_states": states,
        "validation_result": validation.get("result"),
        "validation_report_sha256": sha256_file(validation_json),
        "evidence_archive_sha256": evidence["archive_sha256"],
        "atomic_exchange_required": True,
        "remote_access_performed": False,
        "remote_write_performed": False,
    }
    preflight["preflight_sha256"] = _canonical_sha(preflight, "preflight_sha256")
    write_json(closure_root / "closure-preflight.json", preflight)

    backup = archive_root / "previous-corpus"
    try:
        _rename_exchange(active, staging)
        fsync_directory(corpus_parent)
        if full_tree_sha256(active) != new_tree_sha or full_tree_sha256(staging) != old_tree_sha:
            _rename_exchange(active, staging)
            raise WorkClosureError("Empreinte divergente après échange atomique; échange annulé")
        os.replace(staging, backup)
        fsync_directory(archive_root)
    except Exception:
        if staging.exists() and not backup.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise

    meta = copy.deepcopy(execution["meta"])
    closed_at = now_iso()
    closure_entry = {
        "comparison_id": comparison_id,
        "status": "closed",
        "closed_at": closed_at,
        "active_corpus_path": f"corpus/{debate_id}",
        "active_corpus_tree_sha256": new_tree_sha,
        "previous_corpus_archive": relative_to_project(backup, project_root),
        "evidence_archive": relative_to_project(evidence["archive"], project_root),
    }
    meta["status"] = "work_closed"
    meta["work_closure"] = closure_entry
    meta.setdefault("boundaries", {}).update({
        "remote_execution_completed": True,
        "published_state_verified": True,
        "active_corpus_promoted": True,
        "work_closed": True,
    })
    meta["workspace_sha256"] = workspace_receipt_hash(meta)
    write_json(execution["workspace"] / "workspace.json", meta)

    receipt = {
        "schema": CLOSURE_SCHEMA,
        "schema_version": "1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "comparison_id": comparison_id,
        "closed_at": closed_at,
        "normative_revision": NORM_VERSION,
        "validator_version": VALIDATOR_VERSION,
        "kit_version": KIT_VERSION,
        "status": "work_closed",
        "execution_status": execution["execution_receipt"]["status"],
        "execution_receipt_sha256": execution["execution_receipt"]["receipt_sha256"],
        "plan_sha256": execution["execution_receipt"]["plan_sha256"],
        "acceptance_sha256": execution["execution_receipt"]["acceptance_sha256"],
        "preflight_sha256": execution["execution_receipt"]["preflight_sha256"],
        "authorization_sha256": execution["execution_receipt"]["authorization_sha256"],
        "release_copy_tree_sha256": execution["release_sha256"],
        "active_corpus_tree_sha256": new_tree_sha,
        "previous_corpus_tree_sha256": old_tree_sha,
        "previous_corpus_archive": relative_to_project(backup, project_root),
        "evidence_archive": relative_to_project(evidence["archive"], project_root),
        "evidence_archive_sha256": evidence["archive_sha256"],
        "evidence_manifest_sha256": evidence["manifest_sha256"],
        "closure_validation_result": validation.get("result"),
        "closure_validation_sha256": sha256_file(validation_json),
        "published_states": states,
        "workspace_sha256": meta["workspace_sha256"],
        "chain": _chain_hashes(meta, execution),
        "atomic_exchange": True,
        "remote_access_performed_during_closure": False,
        "remote_write_performed_during_closure": False,
        "publication_completed_before_closure": True,
        "work_completed": True,
    }
    receipt["receipt_sha256"] = _canonical_sha(receipt, "receipt_sha256")
    write_json(final_receipt_path, receipt)

    completed_root = assert_control_directory(project_root / ".state" / "completed-works", project_root, create=True)
    completed_debate = assert_control_directory(completed_root / debate_id, project_root, create=True)
    index = {
        "schema": COMPLETED_INDEX_SCHEMA,
        "debate_id": debate_id,
        "work_id": work_id,
        "comparison_id": comparison_id,
        "status": "work_closed",
        "closed_at": closed_at,
        "receipt_path": relative_to_project(final_receipt_path, project_root),
        "receipt_sha256": receipt["receipt_sha256"],
        "active_corpus_tree_sha256": new_tree_sha,
    }
    index["index_sha256"] = _canonical_sha(index, "index_sha256")
    write_json(completed_debate / f"{work_id}.json", index)
    write_json(completed_debate / "latest.json", index)
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Clôturer un Work après exécution distante vérifiée.")
    parser.add_argument("debate_id")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--comparison-id", required=True)
    parser.add_argument("--confirm-execution-sha256", required=True)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--machine-readable", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = args.project_root.expanduser().resolve()
    with exclusive_lock(project_root, args.debate_id, "work-closure"):
        result = close_work(project_root, args.debate_id, args.work_id, args.comparison_id, args.confirm_execution_sha256)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True) if args.machine_readable else json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except WorkClosureError as exc:
        print(f"CLÔTURE DU WORK BLOQUÉE : {exc}", file=__import__("sys").stderr)
        raise SystemExit(2)
