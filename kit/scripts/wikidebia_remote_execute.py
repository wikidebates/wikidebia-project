#!/usr/bin/env python3
"""Prepare and execute an accepted remote plan with a second remote preflight.

The preparation phase is strictly read-only. It reloads the signed comparison,
review and acceptance, checks effective rights, re-reads every relevant page and
seals an execution preflight. The execution phase requires the exact preflight
SHA-256, re-runs the checks immediately, writes a separate authorization record,
then delegates mutations to the existing PlanExecutor, whose revision and
content checks remain authoritative.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from wikidebia_corpus_build import (
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
from wikidebia_editorial_workspace import WorkspaceError, validate_work_id, workspace_receipt_hash
from wikidebia_render import _load_workspace
from wikidebia_remote_compare import _canonical_sha, _validate_comparison_id, _working_directory
from wikidebia_remote_plan_review import (
    ACCEPTANCE_SCHEMA,
    RECEIPT_SCHEMA as REVIEW_RECEIPT_SCHEMA,
    REVIEW_SCHEMA,
    _canonical_review_sha,
    _load_comparison,
)
from wikidebia_update import (
    KIT_VERSION,
    REQUIRED_VALIDATOR_VERSION,
    OPERATIONS,
    PlanConflict,
    PlanExecutor,
    UpdateError,
    build_adapter,
    is_generated,
    redirect_text,
    sha_object,
    sha_text,
)

PREFLIGHT_SCHEMA = "wikidebia-remote-execution-preflight-1.0"
PREFLIGHT_RECEIPT_SCHEMA = "wikidebia-remote-execution-preflight-receipt-1.0"
AUTHORIZATION_SCHEMA = "wikidebia-remote-execution-authorization-1.0"
EXECUTION_RECEIPT_SCHEMA = "wikidebia-workspace-remote-execution-receipt-1.0"
FAILURE_SCHEMA = "wikidebia-workspace-remote-execution-failure-1.0"
MUTATING_OPERATIONS = ("create", "update", "move", "redirect", "delete")
MODES = ("all", "no-delete", "only-delete")


class RemoteExecutionError(WorkspaceError):
    pass


def _canonical(value: Mapping[str, Any], excluded: str) -> str:
    body = dict(value)
    body.pop(excluded, None)
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _execution_dir(project_root: Path, debate_id: str, work_id: str, comparison_id: str) -> Path:
    state = assert_control_directory(project_root / ".state", project_root, create=True)
    root = assert_control_directory(state / "remote-executions", project_root, create=True)
    debate = assert_control_directory(root / debate_id, project_root, create=True)
    work = assert_control_directory(debate / work_id, project_root, create=True)
    return work / comparison_id


def _load_approved_handoff(project_root: Path, debate_id: str, work_id: str, comparison_id: str) -> dict[str, Any]:
    comparison = _load_comparison(project_root, debate_id, work_id, comparison_id)
    workspace = comparison["workspace"]
    meta = comparison["meta"]
    allowed = {"remote_plan_approved", "remote_execution_ready", "remote_execution_completed", "remote_execution_no_changes", "remote_execution_failed", "remote_execution_blocked"}
    if meta.get("status") not in allowed:
        raise RemoteExecutionError(f"Statut incompatible avec l’exécution distante : {meta.get('status')}")

    review_dir = project_root / ".state/remote-plan-reviews" / debate_id / work_id / comparison_id
    paths = {
        "review": review_dir / "plan-review.json",
        "acceptance": review_dir / "plan-acceptance.json",
        "review_receipt": review_dir / "review-receipt.json",
    }
    for label, path in paths.items():
        if not path.is_file() or path.is_symlink():
            raise RemoteExecutionError(f"Preuve d’approbation absente : {label}")
    review = load_json(paths["review"], "revue du plan")
    acceptance = load_json(paths["acceptance"], "acceptation du plan")
    receipt = load_json(paths["review_receipt"], "reçu de revue")
    if review.get("schema") != REVIEW_SCHEMA or review.get("status") != "approved":
        raise RemoteExecutionError("La revue du plan n’est pas approuvée")
    if review.get("review_sha256") != _canonical_review_sha(review):
        raise RemoteExecutionError("Empreinte de la revue approuvée invalide")
    if acceptance.get("schema") != ACCEPTANCE_SCHEMA or acceptance.get("status") != "accepted":
        raise RemoteExecutionError("Acceptation du plan invalide")
    if acceptance.get("acceptance_sha256") != _canonical_sha(acceptance, "acceptance_sha256"):
        raise RemoteExecutionError("Empreinte de l’acceptation invalide")
    if receipt.get("schema") != REVIEW_RECEIPT_SCHEMA or receipt.get("receipt_sha256") != _canonical_sha(receipt, "receipt_sha256"):
        raise RemoteExecutionError("Reçu de revue invalide")
    expected = {
        "plan_sha256": comparison["plan"]["plan_sha256"],
        "comparison_receipt_sha256": comparison["receipt"]["receipt_sha256"],
        "remote_inventory_sha256": comparison["inventory"]["inventory_sha256"],
        "release_copy_tree_sha256": comparison["release_sha256"],
        "review_sha256": review["review_sha256"],
    }
    for field, value in expected.items():
        if acceptance.get(field) != value:
            raise RemoteExecutionError(f"Acceptation divergente : {field}")
    if receipt.get("acceptance_sha256") != acceptance.get("acceptance_sha256"):
        raise RemoteExecutionError("Le reçu de revue ne vise pas l’acceptation chargée")
    if acceptance.get("plan_accepted") is not True or acceptance.get("execution_handoff_ready") is not True:
        raise RemoteExecutionError("Le handoff d’exécution n’est pas prêt")
    if acceptance.get("execution_started") is not False or acceptance.get("remote_write_performed") is not False:
        raise RemoteExecutionError("L’acceptation indique une exécution déjà commencée")
    if acceptance.get("remote_write_authorized") is not False:
        raise RemoteExecutionError("L’acceptation doit conserver l’écriture distante fermée")
    if receipt.get("execution_started") is not False or receipt.get("remote_write_performed") is not False:
        raise RemoteExecutionError("Le reçu de revue indique une exécution ou une écriture")

    release_copy = workspace / "release-copy"
    if not release_copy.is_dir() or release_copy.is_symlink():
        raise RemoteExecutionError("release-copy absente ou non sûre")
    assert_no_symlinks(release_copy)
    if full_tree_sha256(release_copy) != comparison["release_sha256"]:
        raise RemoteExecutionError("release-copy a changé depuis l’acceptation")

    config_path = comparison["run_dir"] / "config.json"
    if not config_path.is_file() or config_path.is_symlink():
        raise RemoteExecutionError("Configuration de comparaison absente")
    config = load_json(config_path, "configuration distante")
    # Producer release numbers are provenance only. Integrity is bound by the
    # signed plan/review hashes and supported artifact schemas.
    if config.get("remote_write_authorized") is not False or config.get("comparison_mode") != "read_only":
        raise RemoteExecutionError("La configuration de comparaison n’est pas une preuve de lecture seule")
    return {
        **comparison,
        "review": review,
        "acceptance": acceptance,
        "review_receipt": receipt,
        "approval_paths": paths,
        "release_copy": release_copy,
        "config": config,
        "config_path": config_path,
    }


def _selected_names(mode: str) -> tuple[str, ...]:
    if mode == "only-delete":
        return ("redirect", "delete")
    if mode == "no-delete":
        return ("create", "update", "move", "redirect")
    return MUTATING_OPERATIONS


def _selected_rows(plan: Mapping[str, Any], mode: str) -> list[dict[str, Any]]:
    names = _selected_names(mode)
    rows: list[dict[str, Any]] = []
    operations = plan.get("operations") or {}
    for name in names:
        rows.extend({**row, "operation": name} for row in operations.get(name) or [])
    return rows


def _required_rights(operation: str) -> set[str]:
    return {
        "create": {"edit", "createpage"},
        "update": {"edit"},
        "move": {"move"},
        "redirect": {"edit"},
        "delete": {"delete"},
    }.get(operation, set())


class ArmedRecordingAdapter:
    """Record all remote activity and block mutations until explicitly armed."""

    def __init__(self, base: Any) -> None:
        self.base = base
        self.armed = False
        self.events: list[dict[str, Any]] = []
        self.write_attempts = 0
        self.write_count = 0
        self.current_language: str | None = None

    def arm(self) -> None:
        self.armed = True
        self.events.append({"at": now_iso(), "event": "execution_armed"})

    def __getattr__(self, name: str) -> Any:
        return getattr(self.base, name)

    def open_language(self, language: str, expected_user: str) -> None:
        self.current_language = language
        self.events.append({"at": now_iso(), "event": "open_language", "language": language})
        self.base.open_language(language, expected_user)

    def close_language(self) -> None:
        self.events.append({"at": now_iso(), "event": "close_language", "language": self.current_language})
        self.base.close_language()
        self.current_language = None

    def assert_identity(self, expected_user: str) -> None:
        self.base.assert_identity(expected_user)
        self.events.append({"at": now_iso(), "event": "identity_verified", "language": self.current_language, "user": expected_user})

    def user_rights(self) -> set[str]:
        rights = set(self.base.user_rights())
        self.events.append({"at": now_iso(), "event": "rights_read", "language": self.current_language, "rights": sorted(rights)})
        return rights

    def read_page(self, title: str) -> tuple[bool, int | None, str]:
        exists, revision, text = self.base.read_page(title)
        self.events.append({
            "at": now_iso(), "event": "read_page", "language": self.current_language,
            "title": title, "exists": bool(exists), "revision_id": revision,
            "content_sha256": sha_text(text) if exists else None,
        })
        return exists, revision, text

    def backlinks(self, title: str) -> list[str]:
        values = list(self.base.backlinks(title))
        self.events.append({"at": now_iso(), "event": "backlinks", "language": self.current_language, "title": title, "count": len(values)})
        return values

    def _authorize(self, action: str, title: str) -> None:
        self.write_attempts += 1
        if not self.armed:
            raise RemoteExecutionError(f"Tentative d’écriture avant autorisation : {action} {title}")
        self.write_count += 1
        self.events.append({"at": now_iso(), "event": action, "language": self.current_language, "title": title})

    def write_page(self, **kwargs: Any) -> int:
        self._authorize("write_page", str(kwargs.get("title") or ""))
        return int(self.base.write_page(**kwargs))

    def move_page(self, **kwargs: Any) -> int | None:
        self._authorize("move_page", str(kwargs.get("old_title") or ""))
        return self.base.move_page(**kwargs)

    def delete_page(self, **kwargs: Any) -> None:
        self._authorize("delete_page", str(kwargs.get("title") or ""))
        self.base.delete_page(**kwargs)


def _check_row(adapter: ArmedRecordingAdapter, row: Mapping[str, Any], blockers: list[str], extra_markers: tuple[str, ...] = ()) -> dict[str, Any]:
    operation = str(row.get("operation"))
    title = str(row.get("title") or "")
    observed: dict[str, Any] = {"operation": operation, "language": row.get("language"), "page_id": row.get("page_id"), "title": title, "status": "ready"}
    exists, revision, text = adapter.read_page(title)
    digest = sha_text(text) if exists else None
    observed.update({"exists": exists, "revision_id": revision, "content_sha256": digest})
    if operation == "create":
        if exists and digest != row.get("new_sha256"):
            blockers.append(f"Collision apparue : {title}")
        elif exists:
            observed["status"] = "already_done"
    elif operation == "update":
        if not exists or revision is None:
            blockers.append(f"Page à mettre à jour absente : {title}")
        elif digest == row.get("new_sha256"):
            observed["status"] = "already_done"
        elif revision != row.get("expected_revision_id") or digest != row.get("old_sha256"):
            blockers.append(f"Page modifiée depuis le plan : {title}")
    elif operation == "move":
        old_title = str(row.get("old_title") or title)
        new_title = str(row.get("new_title") or "")
        source_exists, source_revision, source_text = adapter.read_page(old_title)
        target_exists, target_revision, target_text = adapter.read_page(new_title)
        observed.update({
            "old_title": old_title, "new_title": new_title,
            "source_revision_id": source_revision,
            "source_sha256": sha_text(source_text) if source_exists else None,
            "target_revision_id": target_revision,
            "target_sha256": sha_text(target_text) if target_exists else None,
        })
        if not source_exists:
            if target_exists and sha_text(target_text) == row.get("new_sha256"):
                observed["status"] = "already_done"
            else:
                blockers.append(f"Source du déplacement absente : {old_title}")
        elif target_exists:
            blockers.append(f"Cible du déplacement déjà présente : {new_title}")
        elif source_revision != row.get("expected_revision_id") or sha_text(source_text) != row.get("old_sha256"):
            blockers.append(f"Source du déplacement modifiée : {old_title}")
    elif operation == "redirect":
        desired = redirect_text(str(row.get("language") or "fr"), str(row.get("redirect_target") or ""))
        if not exists:
            observed["status"] = "already_absent"
        elif digest == sha_text(desired):
            observed["status"] = "already_done"
        elif revision != row.get("expected_revision_id") or digest != row.get("old_sha256"):
            blockers.append(f"Page à rediriger modifiée : {title}")
    elif operation == "delete":
        if not exists:
            observed["status"] = "already_absent"
        elif revision != row.get("observed_revision_id") or digest != row.get("old_sha256"):
            blockers.append(f"Page à supprimer modifiée : {title}")
        elif not is_generated(text, extra_markers):
            blockers.append(f"Marqueur Wikidéb’IA absent : {title}")
    return observed


def _check_skip(adapter: ArmedRecordingAdapter, row: Mapping[str, Any], blockers: list[str]) -> dict[str, Any]:
    title = str(row.get("title") or "")
    exists, revision, text = adapter.read_page(title)
    digest = sha_text(text) if exists else None
    expected = row.get("new_sha256") or row.get("old_sha256")
    status = "verified_unchanged"
    if not exists or (expected and digest != expected):
        status = "changed"
        blockers.append(f"Page skip modifiée depuis le plan : {title}")
    return {"operation": "skip", "language": row.get("language"), "page_id": row.get("page_id"), "title": title, "status": status, "revision_id": revision, "content_sha256": digest}


def _run_preflight(handoff: Mapping[str, Any], adapter: ArmedRecordingAdapter, mode: str) -> dict[str, Any]:
    plan = handoff["plan"]
    selected = _selected_rows(plan, mode)
    blockers: list[str] = []
    checks: list[dict[str, Any]] = []
    rights_by_language: dict[str, list[str]] = {}
    languages = list(handoff["config"].get("languages") or [])
    for language in languages:
        relevant = [row for row in selected if row.get("language") == language]
        skips = [row for row in (plan.get("operations") or {}).get("skip") or [] if row.get("language") == language]
        if not relevant and not skips:
            continue
        expected_user = str((handoff["config"].get("sites") or {}).get(language, {}).get("expected_user") or "")
        adapter.open_language(language, expected_user)
        try:
            adapter.assert_identity(expected_user)
            rights = adapter.user_rights()
            rights_by_language[language] = sorted(rights)
            required = set().union(*(_required_rights(str(row.get("operation"))) for row in relevant)) if relevant else set()
            missing = sorted(required - rights)
            if missing:
                blockers.append(f"Droits MediaWiki absents sur {language} : {', '.join(missing)}")
            for row in sorted(relevant, key=lambda item: (int(item.get("phase", 99)), str(item.get("page_id") or ""))):
                checks.append(_check_row(adapter, row, blockers, tuple(handoff["config"].get("generated_markers") or ())))
            for row in sorted(skips, key=lambda item: str(item.get("page_id") or "")):
                checks.append(_check_skip(adapter, row, blockers))
        finally:
            adapter.close_language()
    return {
        "selected_operation_count": len(selected),
        "selected_counts": {name: sum(1 for row in selected if row["operation"] == name) for name in _selected_names(mode)},
        "rights": rights_by_language,
        "checks": checks,
        "blockers": blockers,
        "status": (
            "blocked" if blockers else
            ("ready" if selected or not any((plan.get("operations") or {}).get(name) for name in MUTATING_OPERATIONS) else "no_changes_in_scope")
        ),
    }


def _write_events(path: Path, events: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in events), encoding="utf-8", newline="\n")


def _update_workspace(meta: dict[str, Any], workspace: Path, entry: dict[str, Any], status: str) -> None:
    meta["remote_execution"] = entry
    history = list(meta.get("remote_executions") or [])
    history.append(entry)
    meta["remote_executions"] = history
    meta["status"] = status
    meta["workspace_sha256"] = workspace_receipt_hash(meta)
    write_json(workspace / "workspace.json", meta)


def prepare_execution(
    project_root: Path,
    debate_id: str,
    work_id: str,
    comparison_id: str,
    confirm_acceptance_sha256: str,
    *,
    mode: str = "all",
    adapter: Any | None = None,
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    debate_id = validate_debate_id(debate_id)
    work_id = validate_work_id(work_id)
    comparison_id = _validate_comparison_id(comparison_id)
    if mode not in MODES:
        raise RemoteExecutionError("mode doit être all, no-delete ou only-delete")
    handoff = _load_approved_handoff(project_root, debate_id, work_id, comparison_id)
    if confirm_acceptance_sha256 != handoff["acceptance"].get("acceptance_sha256"):
        raise RemoteExecutionError("L’empreinte confirmée ne correspond pas à l’acceptation")
    root = _execution_dir(project_root, debate_id, work_id, comparison_id)
    if root.exists() or root.is_symlink():
        # Reuse only a complete, verified preflight for the same approved plan.
        # Never re-run checks or replace evidence after execution has begun.
        if not root.is_dir() or root.is_symlink():
            raise RemoteExecutionError("Dossier de préflight existant non sûr")
        if any((root / name).exists() or (root / name).is_symlink() for name in (
            "execution-authorization.json", "execution-failure.json",
            "execution-receipt.json", "execution-events.jsonl",
        )):
            raise RemoteExecutionError("Exécution déjà commencée ou bloquée : préflight non réutilisable")
        receipt_path = root / "preflight-receipt.json"
        if not receipt_path.is_file() or receipt_path.is_symlink():
            raise RemoteExecutionError("Préflight incomplet : intervention manuelle requise")
        existing_receipt = load_json(receipt_path, "reçu de préflight existant")
        existing_sha = existing_receipt.get("preflight_sha256")
        if not isinstance(existing_sha, str):
            raise RemoteExecutionError("Empreinte du préflight existant absente")
        _, existing, _ = _load_preflight(project_root, handoff, comparison_id, existing_sha)
        if existing.get("mode") != mode:
            raise RemoteExecutionError("Le mode du préflight existant diffère du mode demandé")
        return {
            "status": "ready", "debate_id": debate_id, "work_id": work_id,
            "comparison_id": comparison_id, "mode": mode,
            "preflight_sha256": existing_sha,
            "selected_counts": existing["selected_counts"],
            "blockers": existing["blockers"],
            "remote_write_performed": False,
            "preflight_reused": True,
        }
    # Do not reserve the immutable execution directory before the read-only
    # adapter checks succeed. An exception here must remain safely retryable.
    base = adapter if adapter is not None else build_adapter(handoff["config"], project_root)
    recorder = ArmedRecordingAdapter(base)
    result = _run_preflight(handoff, recorder, mode)
    root.mkdir(parents=False)
    preflight = {
        "schema": PREFLIGHT_SCHEMA,
        "schema_version": "1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "comparison_id": comparison_id,
        "prepared_at": now_iso(),
        "status": result["status"],
        "mode": mode,
        "kit_version": KIT_VERSION,
        "validator_version": REQUIRED_VALIDATOR_VERSION,
        "plan_sha256": handoff["plan"]["plan_sha256"],
        "acceptance_sha256": handoff["acceptance"]["acceptance_sha256"],
        "review_sha256": handoff["review"]["review_sha256"],
        "comparison_receipt_sha256": handoff["receipt"]["receipt_sha256"],
        "remote_inventory_sha256": handoff["inventory"]["inventory_sha256"],
        "release_copy_tree_sha256": handoff["release_sha256"],
        "config_file_sha256": sha256_file(handoff["config_path"]),
        "selected_counts": result["selected_counts"],
        "rights": result["rights"],
        "checks": result["checks"],
        "blockers": result["blockers"],
        "remote_access_performed": True,
        "remote_write_authorized": False,
        "remote_write_performed": False,
        "write_attempts": recorder.write_attempts,
    }
    preflight["preflight_sha256"] = _canonical(preflight, "preflight_sha256")
    write_json(root / "execution-preflight.json", preflight)
    _write_events(root / "preflight-events.jsonl", recorder.events)
    receipt = {
        "schema": PREFLIGHT_RECEIPT_SCHEMA,
        "debate_id": debate_id,
        "work_id": work_id,
        "comparison_id": comparison_id,
        "created_at": now_iso(),
        "status": result["status"],
        "mode": mode,
        "preflight_path": relative_to_project(root / "execution-preflight.json", project_root),
        "preflight_sha256": preflight["preflight_sha256"],
        "events_path": relative_to_project(root / "preflight-events.jsonl", project_root),
        "events_file_sha256": sha256_file(root / "preflight-events.jsonl"),
        "remote_access_performed": True,
        "remote_write_authorized": False,
        "remote_write_performed": False,
    }
    receipt["receipt_sha256"] = _canonical(receipt, "receipt_sha256")
    write_json(root / "preflight-receipt.json", receipt)
    entry = {
        "comparison_id": comparison_id,
        "status": result["status"],
        "mode": mode,
        "preflight_path": receipt["preflight_path"],
        "preflight_sha256": preflight["preflight_sha256"],
        "receipt_path": relative_to_project(root / "preflight-receipt.json", project_root),
        "receipt_sha256": receipt["receipt_sha256"],
        "prepared_at": preflight["prepared_at"],
    }
    status = "remote_execution_ready" if result["status"] == "ready" else "remote_execution_blocked"
    if result["status"] == "no_changes_in_scope":
        status = "remote_execution_no_changes_in_scope"
    _update_workspace(handoff["meta"], handoff["workspace"], entry, status)
    return {
        "status": result["status"],
        "debate_id": debate_id,
        "work_id": work_id,
        "comparison_id": comparison_id,
        "mode": mode,
        "preflight_sha256": preflight["preflight_sha256"],
        "selected_counts": result["selected_counts"],
        "blockers": result["blockers"],
        "remote_write_performed": False,
    }


def _load_preflight(project_root: Path, handoff: Mapping[str, Any], comparison_id: str, confirmation: str) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    root = _execution_dir(project_root, str(handoff["plan"]["debate_id"]), str(handoff["review"]["work_id"]), comparison_id)
    if not root.is_dir() or root.is_symlink():
        raise RemoteExecutionError("Dossier de préflight absent ou non sûr")
    assert_no_symlinks(root)
    preflight_path = root / "execution-preflight.json"
    receipt_path = root / "preflight-receipt.json"
    if not preflight_path.is_file() or preflight_path.is_symlink() or not receipt_path.is_file() or receipt_path.is_symlink():
        raise RemoteExecutionError("Préflight d’exécution absent")
    preflight = load_json(preflight_path, "préflight d’exécution")
    receipt = load_json(receipt_path, "reçu de préflight")
    if preflight.get("preflight_sha256") != _canonical(preflight, "preflight_sha256"):
        raise RemoteExecutionError("Empreinte du préflight invalide")
    if receipt.get("receipt_sha256") != _canonical(receipt, "receipt_sha256"):
        raise RemoteExecutionError("Empreinte du reçu de préflight invalide")
    if confirmation != preflight.get("preflight_sha256"):
        raise RemoteExecutionError("L’empreinte confirmée ne correspond pas au préflight")
    # A valid self-hash alone does not bind a receipt to this execution.
    # Reject foreign receipts and event paths before accessing the filesystem.
    identity = {
        "debate_id": str(handoff["plan"]["debate_id"]),
        "work_id": str(handoff["review"]["work_id"]),
        "comparison_id": comparison_id,
    }
    for field, expected_value in identity.items():
        if preflight.get(field) != expected_value or receipt.get(field) != expected_value:
            raise RemoteExecutionError(f"Identité du préflight divergente : {field}")
    if preflight.get("schema") != PREFLIGHT_SCHEMA or receipt.get("schema") != PREFLIGHT_RECEIPT_SCHEMA:
        raise RemoteExecutionError("Schéma de préflight ou de reçu inattendu")
    if receipt.get("preflight_path") != relative_to_project(root / "execution-preflight.json", project_root):
        raise RemoteExecutionError("Chemin de préflight divergent")
    if receipt.get("events_path") != relative_to_project(root / "preflight-events.jsonl", project_root):
        raise RemoteExecutionError("Chemin du journal de préflight divergent")
    if receipt.get("preflight_sha256") != preflight.get("preflight_sha256"):
        raise RemoteExecutionError("Le reçu ne vise pas le préflight chargé")
    if receipt.get("status") != "ready" or receipt.get("mode") != preflight.get("mode"):
        raise RemoteExecutionError("Le reçu de préflight n’autorise pas cette exécution")
    events_path = project_root / str(receipt.get("events_path") or "")
    if not events_path.is_file() or events_path.is_symlink() or sha256_file(events_path) != receipt.get("events_file_sha256"):
        raise RemoteExecutionError("Journal du préflight absent ou altéré")
    expected = {
        "status": "ready",
        "plan_sha256": handoff["plan"]["plan_sha256"],
        "acceptance_sha256": handoff["acceptance"]["acceptance_sha256"],
        "review_sha256": handoff["review"]["review_sha256"],
        "comparison_receipt_sha256": handoff["receipt"]["receipt_sha256"],
        "remote_inventory_sha256": handoff["inventory"]["inventory_sha256"],
        "release_copy_tree_sha256": handoff["release_sha256"],
        "config_file_sha256": sha256_file(handoff["config_path"]),
    }
    for field, value in expected.items():
        if preflight.get(field) != value:
            raise RemoteExecutionError(f"Préflight divergent : {field}")
    if preflight.get("remote_write_authorized") is not False or preflight.get("remote_write_performed") is not False:
        raise RemoteExecutionError("Le préflight ne porte pas les barrières attendues")
    return root, preflight, receipt


def execute_accepted_plan(
    project_root: Path,
    debate_id: str,
    work_id: str,
    comparison_id: str,
    confirm_preflight_sha256: str,
    *,
    adapter: Any | None = None,
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    debate_id = validate_debate_id(debate_id)
    work_id = validate_work_id(work_id)
    comparison_id = _validate_comparison_id(comparison_id)
    handoff = _load_approved_handoff(project_root, debate_id, work_id, comparison_id)
    root, preflight, _ = _load_preflight(project_root, handoff, comparison_id, confirm_preflight_sha256)
    if (root / "execution-receipt.json").is_file():
        existing = load_json(root / "execution-receipt.json", "reçu d’exécution")
        if existing.get("receipt_sha256") != _canonical(existing, "receipt_sha256"):
            raise RemoteExecutionError("Reçu d’exécution existant invalide")
        # A retry must never accept a signed receipt from another execution.
        expected = {
            "schema": EXECUTION_RECEIPT_SCHEMA,
            "schema_version": "1.0",
            "debate_id": debate_id,
            "work_id": work_id,
            "comparison_id": comparison_id,
            "mode": preflight.get("mode"),
            "plan_sha256": handoff["plan"]["plan_sha256"],
            "acceptance_sha256": handoff["acceptance"]["acceptance_sha256"],
            "preflight_sha256": preflight["preflight_sha256"],
            "execution_completed": True,
        }
        for field, value in expected.items():
            if existing.get(field) != value:
                raise RemoteExecutionError(f"Reçu d’exécution existant divergent : {field}")
        events_path = project_root / str(existing.get("events_path") or "")
        if (
            not events_path.is_file()
            or events_path.is_symlink()
            or sha256_file(events_path) != existing.get("events_file_sha256")
        ):
            raise RemoteExecutionError("Journal d’exécution existant absent ou altéré")
        underlying = existing.get("underlying_receipt")
        if (
            not isinstance(underlying, dict)
            or existing.get("underlying_receipt_sha256")
            != sha_object({k: v for k, v in underlying.items() if k != "receipt_sha256"})
            or underlying.get("receipt_sha256") != existing.get("underlying_receipt_sha256")
        ):
            raise RemoteExecutionError("Reçu du moteur d’exécution existant invalide")
        return existing
    # An authorization is durably written before the first remote mutation.
    # Without a completed receipt, the remote side may already have changed.
    # Never silently re-run a possibly partial execution: recovery requires
    # explicit read-only reconciliation of the original plan and receipts.
    if (root / "execution-authorization.json").exists() or (root / "execution-failure.json").exists():
        raise RemoteExecutionError(
            "Exécution antérieure potentiellement partielle sans reçu final : "
            "reprise automatique interdite ; réconciliation distante en lecture seule requise"
        )
    mode = str(preflight.get("mode") or "all")
    base = adapter if adapter is not None else build_adapter(handoff["config"], project_root)
    recorder = ArmedRecordingAdapter(base)
    immediate = _run_preflight(handoff, recorder, mode)
    if immediate["status"] != "ready":
        failure = {
            "schema": FAILURE_SCHEMA,
            "debate_id": debate_id,
            "work_id": work_id,
            "comparison_id": comparison_id,
            "failed_at": now_iso(),
            "stage": "immediate_revalidation",
            "status": immediate["status"],
            "blockers": immediate["blockers"],
            "preflight_sha256": preflight["preflight_sha256"],
            "remote_write_performed": False,
            "write_attempts": recorder.write_attempts,
        }
        failure["failure_sha256"] = _canonical(failure, "failure_sha256")
        write_json(root / "execution-failure.json", failure)
        _write_events(root / "execution-events.jsonl", recorder.events)
        entry = {"comparison_id": comparison_id, "status": "blocked", "failure_path": relative_to_project(root / "execution-failure.json", project_root), "failure_sha256": failure["failure_sha256"], "failed_at": failure["failed_at"]}
        _update_workspace(handoff["meta"], handoff["workspace"], entry, "remote_execution_blocked")
        raise RemoteExecutionError("L’état distant a changé depuis le préflight : " + " | ".join(immediate["blockers"][:10]))

    authorization = {
        "schema": AUTHORIZATION_SCHEMA,
        "debate_id": debate_id,
        "work_id": work_id,
        "comparison_id": comparison_id,
        "authorized_at": now_iso(),
        "mode": mode,
        "plan_sha256": handoff["plan"]["plan_sha256"],
        "acceptance_sha256": handoff["acceptance"]["acceptance_sha256"],
        "preflight_sha256": preflight["preflight_sha256"],
        "immediate_revalidation_status": immediate["status"],
        "remote_write_authorized": True,
        "execution_started": True,
        "remote_write_performed": False,
    }
    authorization["authorization_sha256"] = _canonical(authorization, "authorization_sha256")
    write_json(root / "execution-authorization.json", authorization)
    recorder.arm()
    plan = handoff["plan"]
    try:
        with _working_directory(project_root):
            executor = PlanExecutor(handoff["config"], recorder, handoff["config_path"])
            has_mutation = any((plan.get("operations") or {}).get(name) for name in MUTATING_OPERATIONS)
            if not has_mutation:
                underlying = executor.attest_no_changes(plan, plan["plan_sha256"])
            else:
                underlying = executor.execute(
                    plan,
                    plan["plan_sha256"],
                    only_delete=mode == "only-delete",
                    no_delete=mode == "no-delete",
                )
    except Exception as exc:
        _write_events(root / "execution-events.jsonl", recorder.events)
        failure = {
            "schema": FAILURE_SCHEMA,
            "debate_id": debate_id,
            "work_id": work_id,
            "comparison_id": comparison_id,
            "failed_at": now_iso(),
            "stage": "plan_execution",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "plan_sha256": plan["plan_sha256"],
            "acceptance_sha256": handoff["acceptance"]["acceptance_sha256"],
            "preflight_sha256": preflight["preflight_sha256"],
            "authorization_sha256": authorization["authorization_sha256"],
            "remote_write_performed": recorder.write_count > 0,
            "write_attempts": recorder.write_attempts,
            "successful_write_calls": recorder.write_count,
            "events_file_sha256": sha256_file(root / "execution-events.jsonl"),
        }
        failure["failure_sha256"] = _canonical(failure, "failure_sha256")
        write_json(root / "execution-failure.json", failure)
        entry = {"comparison_id": comparison_id, "status": "failed", "failure_path": relative_to_project(root / "execution-failure.json", project_root), "failure_sha256": failure["failure_sha256"], "failed_at": failure["failed_at"], "remote_write_performed": failure["remote_write_performed"]}
        _update_workspace(handoff["meta"], handoff["workspace"], entry, "remote_execution_failed")
        raise RemoteExecutionError(f"Exécution interrompue : {exc}") from exc

    _write_events(root / "execution-events.jsonl", recorder.events)
    if underlying.get("receipt_sha256") != sha_object({k: v for k, v in underlying.items() if k != "receipt_sha256"}):
        raise RemoteExecutionError("Le moteur a produit un reçu d’exécution invalide")
    states: dict[str, dict[str, str]] = {}
    for language in handoff["config"].get("languages") or []:
        path = project_root / ".state/published" / debate_id / language / "latest.json"
        if path.is_file():
            state = load_json(path, f"état publié {language}")
            unsigned = dict(state)
            claimed = unsigned.pop("state_sha256", None)
            if claimed != sha_object(unsigned):
                raise RemoteExecutionError(f"État publié final invalide : {language}")
            states[language] = {"path": relative_to_project(path, project_root), "state_sha256": str(claimed)}
    receipt = {
        "schema": EXECUTION_RECEIPT_SCHEMA,
        "schema_version": "1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "comparison_id": comparison_id,
        "completed_at": now_iso(),
        "status": str(underlying.get("status") or "executed"),
        "mode": mode,
        "kit_version": KIT_VERSION,
        "validator_version": REQUIRED_VALIDATOR_VERSION,
        "plan_sha256": plan["plan_sha256"],
        "acceptance_sha256": handoff["acceptance"]["acceptance_sha256"],
        "preflight_sha256": preflight["preflight_sha256"],
        "authorization_sha256": authorization["authorization_sha256"],
        "underlying_receipt_sha256": underlying["receipt_sha256"],
        "underlying_receipt": underlying,
        "published_states": states,
        "events_path": relative_to_project(root / "execution-events.jsonl", project_root),
        "events_file_sha256": sha256_file(root / "execution-events.jsonl"),
        "remote_access_performed": True,
        "remote_write_authorized": True,
        "remote_write_performed": recorder.write_count > 0,
        "write_attempts": recorder.write_attempts,
        "successful_write_calls": recorder.write_count,
        "execution_completed": True,
    }
    receipt["receipt_sha256"] = _canonical(receipt, "receipt_sha256")
    write_json(root / "execution-receipt.json", receipt)
    entry = {
        "comparison_id": comparison_id,
        "status": receipt["status"],
        "mode": mode,
        "receipt_path": relative_to_project(root / "execution-receipt.json", project_root),
        "receipt_sha256": receipt["receipt_sha256"],
        "completed_at": receipt["completed_at"],
        "remote_write_performed": receipt["remote_write_performed"],
    }
    status = "remote_execution_no_changes" if receipt["status"] == "no_changes" else "remote_execution_completed"
    _update_workspace(handoff["meta"], handoff["workspace"], entry, status)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Préparer ou exécuter un plan distant accepté")
    parser.add_argument("debate_id")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--comparison-id", required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--execute", action="store_true")
    parser.add_argument("--mode", choices=MODES, default="all")
    parser.add_argument("--confirm-acceptance-sha256")
    parser.add_argument("--confirm-preflight-sha256")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--machine-readable", action="store_true")
    args = parser.parse_args(argv)
    with exclusive_lock(args.project_root.resolve(), args.debate_id, "remote-execution"):
        if args.prepare:
            if not args.confirm_acceptance_sha256:
                raise RemoteExecutionError("--confirm-acceptance-sha256 est obligatoire avec --prepare")
            result = prepare_execution(
                args.project_root, args.debate_id, args.work_id, args.comparison_id,
                args.confirm_acceptance_sha256, mode=args.mode,
            )
        else:
            if not args.confirm_preflight_sha256:
                raise RemoteExecutionError("--confirm-preflight-sha256 est obligatoire avec --execute")
            result = execute_accepted_plan(
                args.project_root, args.debate_id, args.work_id, args.comparison_id,
                args.confirm_preflight_sha256,
            )
    if args.machine_readable:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(f"Exécution distante : {result['status']}")
        if result.get("preflight_sha256"):
            print(f"SHA-256 du préflight : {result['preflight_sha256']}")
        if result.get("receipt_sha256"):
            print(f"SHA-256 du reçu : {result['receipt_sha256']}")
    return 0 if result.get("status") in {"ready", "executed", "no_changes"} else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (WorkspaceError, UpdateError) as exc:
        print(f"EXÉCUTION DISTANTE BLOQUÉE : {exc}", file=os.sys.stderr)
        raise SystemExit(2)
