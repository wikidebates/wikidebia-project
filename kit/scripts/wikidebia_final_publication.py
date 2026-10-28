#!/usr/bin/env python3
"""Safe final MediaWiki publication for an editorial workflow release.

The normal path is intentionally mechanical once the two semantic convergence
passes and the local ``release_ready`` seal already exist.  No editorial review
is reopened.  Before the first write this module:

* seals the Work-scoped bilingual baseline;
* builds a full read-only safety comparison with the update planner;
* builds the exact English first-publication plan (runtime creation date,
  translated-fr tag, source-linked edit summaries);
* builds the exact French interlanguage update plan;
* re-reads every target and verifies rights/tags globally.

The default plan permits EN create/skip and FR interlanguage-only update/skip.
Explicit owner-approved English replacements also require a pre-existing page
in the sealed review and exact old/new hashes and base revisions. Unexpected
collisions, divergences, moves, redirects and deletions block before any write.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping

from wikidebia_corpus_build import full_tree_sha256, load_json, now_iso, sha256_file, write_json
from wikidebia_publish import GenericPublisher, PublicationError, sha_object as publish_sha_object, sha_text
from wikidebia_release_info import KIT_VERSION, VALIDATOR_VERSION
from wikidebia_update import RemoteUpdatePlanner, PlanExecutor, build_adapter, sha_object
from wikidebia_workflow_baseline import (
    WorkflowBaselineError,
    seal_workflow_release_baseline,
)

FINAL_RECEIPT_SCHEMA = "wikidebia-final-publication-receipt-1.0"
PREFLIGHT_SCHEMA = "wikidebia-final-publication-preflight-1.0"
AUTHORIZATION_SCHEMA = "wikidebia-final-publication-authorization-1.0"
ROLLOVER_SCHEMA = "wikidebia-final-publication-date-rollover-1.0"


class FinalPublicationError(RuntimeError):
    def __init__(self, message: str, *, remote_execution_started: bool = False) -> None:
        super().__init__(message)
        self.remote_execution_started = remote_execution_started


def _canonical(value: Mapping[str, Any], excluded: str) -> str:
    body = dict(value)
    body.pop(excluded, None)
    return sha_object(body)


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _settings(project_root: Path) -> dict[str, Any]:
    path = project_root / "config/wikidebia.local.json"
    return load_json(path, "configuration locale") if path.is_file() else {}


def _state_dir(project_root: Path, debate_id: str, work_id: str) -> Path:
    path = project_root / ".state/final-publication" / debate_id / work_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _common_remote(project_root: Path, debate_id: str, corpus_root: Path, run_dir: Path, languages: list[str]) -> dict[str, Any]:
    settings = _settings(project_root)
    users = settings.get("expected_users") or {"fr": "ChatGPT", "en": "ChatGPT"}
    return {
        "kit_version": KIT_VERSION,
        "project_root": str(project_root),
        "family": str(settings.get("family") or "wikidebates"),
        "family_file": str(project_root / "kit/families/wikidebates_family.py"),
        "pywikibot_dir": str(project_root / "private/pywikibot"),
        "sites": {
            language: {"code": language, "expected_user": str(users.get(language) or "ChatGPT")}
            for language in languages
        },
        "languages": languages,
        "debate_id": debate_id,
        "corpus_root": str(corpus_root),
        "logs_dir": str(project_root / "logs" / debate_id / f"final-{run_dir.name}"),
        "published_state_dir": str(project_root / ".state/published"),
        "receipts_dir": str(project_root / ".state/receipts"),
        "verification_attempts": int(settings.get("verification_attempts", 8)),
        "verification_delay_seconds": float(settings.get("verification_delay_seconds", 2)),
        "write_delay_seconds": float(settings.get("write_delay_seconds", 0.5)),
        "validator": {
            "command": [str(project_root / ".venv/bin/python"), str(project_root / "validator/scripts/wikidebia_validate.py"), "validate"],
            "required_version": VALIDATOR_VERSION,
            "scopes": ["schema", "coherence", "graph", "files", "batches", "sources", "wikicode", "bilingual", "editorial", "workflow"],
            "max_warnings": 0,
            "fingerprint_path": str(project_root / "validator"),
        },
    }


def _update_config(project_root: Path, debate_id: str, corpus_root: Path, run_dir: Path, languages: list[str], name: str) -> tuple[Path, dict[str, Any]]:
    value = _common_remote(project_root, debate_id, corpus_root, run_dir, languages)
    path = run_dir / name
    write_json(path, value)
    return path, value


def _approved_english_updates(corpus_root: Path) -> dict[str, dict[str, Any]]:
    approved: dict[str, dict[str, Any]] = {}
    for row in load_json(corpus_root / "manifest.json", "manifest").get("pages") or []:
        decision = row.get("existing_english_update")
        if not decision:
            continue
        if (row.get("language") != "en" or row.get("page_origin") != "preexisting"
                or decision.get("owner_approved") is not True
                or decision.get("decision") != "explicit_user_request"
                or decision.get("allow_proposed_change") is not True
                or decision.get("page_id") != row.get("page_id")
                or decision.get("title") != row.get("canonical_title")
                or len(str(decision.get("instruction") or "").strip()) < 24):
            raise FinalPublicationError("Décision propriétaire anglaise absente ou divergente")
        source = corpus_root / row["file_path"]
        approved[str(row["page_id"])] = {**copy.deepcopy(decision), "proposed_sha256": sha_text(source.read_text(encoding="utf-8"))}
    return approved


def _assert_approved_english_update(row: Mapping[str, Any], approved: Mapping[str, Any], *, publisher: bool = False) -> None:
    decision = approved.get(str(row.get("page_id"))) or {}
    observed_revision = row.get("remote_revision_id") if publisher else row.get("expected_revision_id")
    observed_sha = row.get("remote_sha256") if publisher else row.get("old_sha256")
    proposed_sha = row.get("desired_sha256") if publisher else row.get("new_sha256")
    if (not decision or decision.get("owner_approved") is not True
            or decision.get("decision") != "explicit_user_request"
            or decision.get("allow_proposed_change") is not True
            or len(str(decision.get("instruction") or "").strip()) < 24
            or row.get("language") != "en" or row.get("title") != decision.get("title")
            or observed_revision != decision.get("observed_revision_id")
            or not observed_sha or observed_sha != decision.get("observed_sha256")
            or not proposed_sha or proposed_sha != decision.get("proposed_sha256")):
        raise FinalPublicationError("Mise à jour anglaise sans décision propriétaire liée aux révisions et contenus exacts")


def _english_config(project_root: Path, debate_id: str, corpus_root: Path, run_dir: Path) -> tuple[Path, dict[str, Any]]:
    settings = _settings(project_root)
    value = _common_remote(project_root, debate_id, corpus_root, run_dir, ["en"])
    value.update({
        "change_tags": ["chatgpt"],
        "translation_change_tag": "translated-fr",
        "publication_timezone": str(settings.get("publication_timezone") or "Europe/Paris"),
        "publication_profile": "norm_1_2_direct_interlanguage",
        "manifest_requirements": {},
        "operation": {
            "id": "workflow_final_publish_en",
            "kind": "full_page",
            "languages": ["en"],
            "page_types": ["debate", "argument"],
            "language_order": ["en"],
            # GenericPublisher and final publication now share the active
            # Debate-before-Arguments contract.  The plan is still explicitly
            # ordered and resigned below so saved plans have a deterministic order.
            "page_type_order": ["debate", "argument"],
            "source_path_field": "file_path",
            "create_missing": True,
            "update_existing": bool(_approved_english_updates(corpus_root)),
            "approved_existing_updates": _approved_english_updates(corpus_root),
            "edit_summaries": {"en": "Content generated by ChatGPT 5.6"},
            "remote_title_overrides": {"en": {}},
        },
    })
    path = run_dir / "english-publication-config.json"
    write_json(path, value)
    return path, value


def _reorder_english_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Return the signed English plan in the owner-mandated Debate-first order."""
    value = copy.deepcopy(plan)
    actions = list(value.get("actions") or [])
    actions.sort(key=lambda row: (
        0 if row.get("page_type") == "debate" else 1,
        str(row.get("page_id") or ""),
        str(row.get("title") or ""),
    ))
    value["actions"] = actions
    value.pop("plan_sha256", None)
    value["plan_sha256"] = publish_sha_object(value)
    return value


def _assert_safe_update_plan(plan: Mapping[str, Any], *, full: bool, approved_updates: Mapping[str, Any] | None = None) -> None:
    operations = plan.get("operations") or {}
    forbidden = [name for name in ("blocked", "manual_review", "move", "redirect", "delete") if operations.get(name)]
    if forbidden:
        raise FinalPublicationError(
            "Plan final non automatiquement publiable : opérations " + ", ".join(forbidden)
        )
    for row in operations.get("create") or []:
        if str(row.get("language") or "") != "en":
            raise FinalPublicationError("Une page française attendue par le checkpoint est désormais absente")
    for row in operations.get("update") or []:
        if full and row.get("language") == "en" and approved_updates:
            _assert_approved_english_update(row, approved_updates)
            continue
        if str(row.get("language") or "") != "fr":
            raise FinalPublicationError("Une page anglaise existante ne peut pas être mise à jour automatiquement lors de sa première publication")
        if str(row.get("edit_summary_policy") or "") != "french_interlanguage_addition":
            raise FinalPublicationError(
                f"La page française {row.get('page_id')} porte un delta autre que le seul lien interlangue"
            )
    if not full:
        if operations.get("create"):
            raise FinalPublicationError("Le plan français final contient une création inattendue")
        if any(str(row.get("language") or "") != "fr" for name in ("update", "skip") for row in operations.get(name) or []):
            raise FinalPublicationError("Le plan français final contient une autre langue")


def _assert_safe_english_plan(plan: Mapping[str, Any], approved_updates: Mapping[str, Any] | None = None) -> None:
    blockers = list(plan.get("blockers") or [])
    if blockers:
        raise FinalPublicationError(
            "Collision anglaise avant publication finale : " + "; ".join(
                str(row.get("title") or row.get("page_id") or "page") for row in blockers[:8]
            )
        )
    for action in plan.get("actions") or []:
        if action.get("operation") == "update" and approved_updates:
            _assert_approved_english_update(action, approved_updates, publisher=True)
            continue
        if str(action.get("language") or "") != "en" or str(action.get("operation") or "") not in {"create", "skip"}:
            raise FinalPublicationError("Le plan anglais final contient une opération autre que create/skip")


def _remote_snapshot_for_update(adapter: Any, plan: Mapping[str, Any], languages: Iterable[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ops = plan.get("operations") or {}
    selected = []
    for name in ("create", "update", "skip"):
        for row in ops.get(name) or []:
            selected.append((name, row))
    by_language = {lang: [(name, row) for name, row in selected if row.get("language") == lang] for lang in languages}
    for language, items in by_language.items():
        if not items:
            continue
        expected_user = str(adapter.base and "") if False else None
        # identity is checked by the caller; keep this routine data-only.
        for name, row in items:
            exists, revision_id, text = adapter.read_page(str(row.get("title") or ""))
            digest = sha_text(text) if exists else None
            if name == "create":
                if exists:
                    raise FinalPublicationError(f"Une cible de création est apparue avant autorisation : {row.get('title')}")
            elif name == "update":
                if not exists or revision_id != row.get("expected_revision_id") or digest != row.get("old_sha256"):
                    raise FinalPublicationError(f"Une page française a changé depuis le plan : {row.get('title')}")
            elif name == "skip":
                if not exists or digest != row.get("new_sha256"):
                    raise FinalPublicationError(f"Une page équivalente a changé depuis le plan : {row.get('title')}")
            rows.append({
                "language": language,
                "page_id": row.get("page_id"),
                "title": row.get("title"),
                "operation": name,
                "exists": bool(exists),
                "revision_id": revision_id,
                "remote_sha256": digest,
            })
    return rows


def _remote_snapshot_for_english(adapter: Any, plan: Mapping[str, Any], expected_user: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    adapter.open_language("en", expected_user)
    try:
        adapter.assert_identity(expected_user)
        available_tags = set(adapter.available_change_tags())
        for tag in ("chatgpt", "translated-fr"):
            if tag not in available_tags:
                raise FinalPublicationError(f"Balise MediaWiki anglaise indisponible avant publication : {tag}")
        rights = set(adapter.user_rights())
        missing = sorted({"edit", "createpage"} - rights)
        if missing:
            raise FinalPublicationError("Droits anglais absents avant publication : " + ", ".join(missing))
        for action in plan.get("actions") or []:
            exists, revision_id, text = adapter.read_page(str(action.get("title") or ""))
            digest = sha_text(text) if exists else None
            operation = str(action.get("operation") or "")
            if operation == "create" and exists:
                raise FinalPublicationError(f"Une page anglaise est apparue depuis le plan : {action.get('title')}")
            if operation == "skip" and (not exists or digest != action.get("desired_sha256")):
                raise FinalPublicationError(f"Une page anglaise équivalente a changé depuis le plan : {action.get('title')}")
            if operation == "update" and (not exists or revision_id != action.get("remote_revision_id") or digest != action.get("remote_sha256")):
                raise FinalPublicationError(f"Une page anglaise autorisée a changé depuis le plan : {action.get('title')}")
            rows.append({
                "language": "en", "page_id": action.get("page_id"), "title": action.get("title"),
                "operation": operation, "exists": bool(exists), "revision_id": revision_id, "remote_sha256": digest,
            })
    finally:
        adapter.close_language()
    return rows


def _remote_snapshot_for_french(adapter: Any, plan: Mapping[str, Any], expected_user: str) -> list[dict[str, Any]]:
    adapter.open_language("fr", expected_user)
    try:
        adapter.assert_identity(expected_user)
        rights = set(adapter.user_rights())
        if (plan.get("operations") or {}).get("update") and "edit" not in rights:
            raise FinalPublicationError("Droit edit français absent avant publication")
        return _remote_snapshot_for_update(adapter, plan, ["fr"])
    finally:
        adapter.close_language()


def _install_release_copy(project_root: Path, debate_id: str, release_copy: Path, expected_tree_sha: str) -> dict[str, Any]:
    if full_tree_sha256(release_copy) != expected_tree_sha:
        raise FinalPublicationError("Le release-copy a changé avant son installation")
    target = project_root / "corpus" / debate_id
    if target.is_dir() and full_tree_sha256(target) == expected_tree_sha:
        return {"status": "already_installed", "path": _relative(target, project_root), "tree_sha256": expected_tree_sha}
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{debate_id}.final-install-", dir=target.parent))
    backup: Path | None = None
    try:
        shutil.rmtree(temp)
        shutil.copytree(release_copy, temp)
        if full_tree_sha256(temp) != expected_tree_sha:
            raise FinalPublicationError("La copie locale finale diverge du release-copy")
        if target.exists():
            stamp = dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
            backup = project_root / "archives/debates" / f"{stamp}-{debate_id}" / "previous-corpus"
            backup.parent.mkdir(parents=True, exist_ok=True)
            os.replace(target, backup)
        os.replace(temp, target)
    except Exception:
        if target.exists() and full_tree_sha256(target) == expected_tree_sha:
            pass
        elif backup is not None and backup.exists() and not target.exists():
            os.replace(backup, target)
        shutil.rmtree(temp, ignore_errors=True)
        raise
    return {
        "status": "installed", "path": _relative(target, project_root), "tree_sha256": expected_tree_sha,
        "previous_corpus": _relative(backup, project_root) if backup is not None and backup.exists() else None,
    }


def _load_or_build_plans(
    project_root: Path,
    debate_id: str,
    work_id: str,
    release_copy: Path,
    state_dir: Path,
) -> dict[str, Any]:
    # Initial safety plan: full bilingual update semantics against Work baseline.
    safety_config_path, safety_config = _update_config(
        project_root, debate_id, release_copy, state_dir, ["fr", "en"], "safety-update-config.json"
    )
    safety_adapter = build_adapter(safety_config, project_root)
    # Pages that belonged to an earlier, broader graph remain valid wiki pages
    # even when the current Work no longer references them.  Final publication
    # must therefore leave them untouched instead of planning remote deletions.
    safety_plan = RemoteUpdatePlanner(safety_config, safety_adapter, safety_config_path).build_plan(mode="no_delete")
    approved_updates = _approved_english_updates(release_copy)
    write_json(state_dir / "safety-update-plan.json", safety_plan)
    # Preserve the signed read-only diagnostic even when the automatic gate
    # rejects it.  Authorization has not been created at this point, so saving
    # the plan cannot start a remote write and exposes the exact blocker for a
    # deterministic repair/resume.
    _assert_safe_update_plan(safety_plan, full=True, approved_updates=approved_updates)

    # Exact FR execution plan, rebuilt separately so its signed state contains only
    # the interlanguage updates and cannot accidentally execute EN create rows.
    fr_config_path, fr_config = _update_config(
        project_root, debate_id, release_copy, state_dir, ["fr"], "french-update-config.json"
    )
    fr_adapter = build_adapter(fr_config, project_root)
    fr_plan = RemoteUpdatePlanner(fr_config, fr_adapter, fr_config_path).build_plan(mode="no_delete")
    _assert_safe_update_plan(fr_plan, full=False)
    write_json(state_dir / "french-update-plan.json", fr_plan)

    en_config_path, en_config = _english_config(project_root, debate_id, release_copy, state_dir)
    en_adapter = build_adapter(en_config, project_root)
    en_publisher = GenericPublisher(en_config, en_adapter, en_config_path)
    en_plan = _reorder_english_plan(en_publisher.build_plan())
    _assert_safe_english_plan(en_plan, approved_updates)
    write_json(state_dir / "english-publication-plan.json", en_plan)

    return {
        "safety_config_path": safety_config_path, "safety_config": safety_config, "safety_plan": safety_plan,
        "fr_config_path": fr_config_path, "fr_config": fr_config, "fr_plan": fr_plan,
        "en_config_path": en_config_path, "en_config": en_config, "en_plan": en_plan,
    }


def _load_saved_plans(project_root: Path, state_dir: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    mapping = {
        "safety": ("safety-update-config.json", "safety-update-plan.json"),
        "fr": ("french-update-config.json", "french-update-plan.json"),
        "en": ("english-publication-config.json", "english-publication-plan.json"),
    }
    for key, (config_name, plan_name) in mapping.items():
        config_path = state_dir / config_name
        plan_path = state_dir / plan_name
        if not config_path.is_file() or not plan_path.is_file():
            raise FinalPublicationError("État partiel de publication finale : plans signés manquants")
        result[f"{key}_config_path"] = config_path
        result[f"{key}_config"] = load_json(config_path, f"configuration finale {key}")
        result[f"{key}_plan"] = load_json(plan_path, f"plan final {key}")
    approved_updates = (result["en_config"].get("operation") or {}).get("approved_existing_updates") or {}
    _assert_safe_update_plan(result["safety_plan"], full=True, approved_updates=approved_updates)
    _assert_safe_update_plan(result["fr_plan"], full=False)
    _assert_safe_english_plan(result["en_plan"], approved_updates)
    return result


def _preflight(project_root: Path, state_dir: Path, plans: Mapping[str, Any]) -> dict[str, Any]:
    fr_adapter = build_adapter(dict(plans["fr_config"]), project_root)
    en_adapter = build_adapter(dict(plans["en_config"]), project_root)
    settings = _settings(project_root)
    users = settings.get("expected_users") or {"fr": "ChatGPT", "en": "ChatGPT"}
    snapshots = []
    snapshots.extend(_remote_snapshot_for_english(en_adapter, plans["en_plan"], str(users.get("en") or "ChatGPT")))
    snapshots.extend(_remote_snapshot_for_french(fr_adapter, plans["fr_plan"], str(users.get("fr") or "ChatGPT")))
    preflight = {
        "schema": PREFLIGHT_SCHEMA,
        "schema_version": "1.0",
        "checked_at": now_iso(),
        "status": "ready",
        "safety_plan_sha256": plans["safety_plan"].get("plan_sha256"),
        "english_plan_sha256": plans["en_plan"].get("plan_sha256"),
        "french_plan_sha256": plans["fr_plan"].get("plan_sha256"),
        "remote_snapshots": snapshots,
        "remote_write_performed": False,
        "remote_write_authorized": False,
    }
    preflight["preflight_sha256"] = _canonical(preflight, "preflight_sha256")
    write_json(state_dir / "preflight.json", preflight)
    return preflight



def _publication_date_from_config(config: Mapping[str, Any]) -> str:
    from zoneinfo import ZoneInfo

    timezone = str(config.get("publication_timezone") or "Europe/Paris")
    return dt.datetime.now(ZoneInfo(timezone)).date().isoformat()


def _rollover_history_dir(state_dir: Path) -> Path:
    path = state_dir / "publication-date-rollovers"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _next_rollover_dir(state_dir: Path, old_date: str, new_date: str) -> Path:
    root = _rollover_history_dir(state_dir)
    index = 1
    while True:
        candidate = root / f"{index:03d}-{old_date}-to-{new_date}"
        if not candidate.exists():
            candidate.mkdir(parents=True)
            return candidate
        index += 1


def _copy_if_present(source: Path, target: Path) -> None:
    if source.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _english_plan_rollover_transition(
    publisher: GenericPublisher,
    old_plan: Mapping[str, Any],
    new_plan: Mapping[str, Any],
    current_date: str,
) -> dict[str, Any]:
    from wikidebia_publication_dates import (
        PublicationDateTransitionError,
        english_plan_rollover_transition,
    )

    try:
        return english_plan_rollover_transition(publisher, old_plan, new_plan, current_date)
    except PublicationDateTransitionError as exc:
        raise FinalPublicationError(str(exc), remote_execution_started=True) from exc


def _rollover_english_publication_date(
    project_root: Path,
    debate_id: str,
    release_copy: Path,
    state_dir: Path,
    baseline: Mapping[str, Any],
    plans: Mapping[str, Any],
    preflight: Mapping[str, Any],
    authorization: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    old_plan = dict(plans["en_plan"])
    current_date = _publication_date_from_config(plans["en_config"])
    old_date = str(old_plan.get("publication_date") or "")
    if current_date == old_date:
        return dict(plans), dict(preflight), dict(authorization)
    if not any(str(row.get("operation") or "") == "create" for row in old_plan.get("actions") or []):
        return dict(plans), dict(preflight), dict(authorization)

    history = _next_rollover_dir(state_dir, old_date or "unknown", current_date)
    tracked = (
        "english-publication-config.json", "english-publication-plan.json",
        "preflight.json", "authorization.json",
    )
    for name in tracked:
        _copy_if_present(state_dir / name, history / name)

    old_preflight_sha = preflight.get("preflight_sha256")
    old_authorization_sha = authorization.get("authorization_sha256")
    try:
        en_config_path, en_config = _english_config(project_root, debate_id, release_copy, state_dir)
        en_adapter = build_adapter(en_config, project_root)
        publisher = GenericPublisher(en_config, en_adapter, en_config_path)
        new_plan = _reorder_english_plan(publisher.build_plan())
        _assert_safe_english_plan(new_plan, (en_config.get("operation") or {}).get("approved_existing_updates") or {})
        transition = _english_plan_rollover_transition(publisher, old_plan, new_plan, current_date)
        write_json(state_dir / "english-publication-plan.json", new_plan)

        new_plans = dict(plans)
        new_plans.update({
            "en_config_path": en_config_path,
            "en_config": en_config,
            "en_plan": new_plan,
        })
        new_preflight = _preflight(project_root, state_dir, new_plans)
        new_authorization = _authorization(state_dir, baseline, new_preflight)

        audit = {
            "schema": ROLLOVER_SCHEMA,
            "schema_version": "1.0",
            "debate_id": debate_id,
            "rolled_over_at": now_iso(),
            "reason": "publication_day_changed_during_partial_english_creation",
            "publication_timezone": en_config.get("publication_timezone"),
            "remote_execution_already_started": True,
            "previous_english_plan_sha256": old_plan.get("plan_sha256"),
            "successor_english_plan_sha256": new_plan.get("plan_sha256"),
            "previous_preflight_sha256": old_preflight_sha,
            "successor_preflight_sha256": new_preflight.get("preflight_sha256"),
            "previous_authorization_sha256": old_authorization_sha,
            "successor_authorization_sha256": new_authorization.get("authorization_sha256"),
            **transition,
        }
        audit["rollover_sha256"] = _canonical(audit, "rollover_sha256")
        write_json(history / "rollover.json", audit)
        return new_plans, new_preflight, new_authorization
    except Exception:
        # No remote write is performed by the rollover itself.  Restore the
        # previous signed local state atomically if plan rebuilding/preflight fails.
        for name in tracked:
            saved = history / name
            target = state_dir / name
            if saved.is_file():
                shutil.copy2(saved, target)
            elif target.exists():
                target.unlink()
        raise


def _english_plan_needs_debate_first_migration(plan: Mapping[str, Any]) -> bool:
    creates = [row for row in (plan.get("actions") or []) if str(row.get("operation") or "") == "create"]
    debate_indexes = [i for i, row in enumerate(creates) if str(row.get("page_type") or "") == "debate"]
    if not debate_indexes:
        return False
    first_debate = debate_indexes[0]
    return any(str(row.get("page_type") or "") == "argument" for row in creates[:first_debate])


def _english_plan_order_transition(old_plan: Mapping[str, Any], new_plan: Mapping[str, Any]) -> dict[str, Any]:
    def keyed(plan: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
        return {(str(row.get("language") or ""), str(row.get("page_id") or "")): row for row in (plan.get("actions") or [])}

    old_actions = keyed(old_plan)
    new_actions = keyed(new_plan)
    if set(old_actions) != set(new_actions):
        raise FinalPublicationError("Le plan successeur Debate-first ne couvre pas exactement les mêmes pages", remote_execution_started=True)
    invariant_fields = (
        "operation_id", "kind", "language", "page_id", "page_type", "title", "source_path",
        "parameter", "local_file_sha256", "local_target_sha256", "edit_summary", "change_tags",
        "publication_creation_date", "desired_sha256",
    )
    completed: list[dict[str, Any]] = []
    remaining: list[dict[str, Any]] = []
    unchanged_skips: list[dict[str, Any]] = []
    for key in sorted(old_actions):
        old = old_actions[key]
        new = new_actions[key]
        for field in invariant_fields:
            if field == "desired_sha256" and str(old.get("operation") or "") == "create" and str(new.get("operation") or "") == "skip":
                # An already-created translation must preserve exactly the old desired content.
                if old.get(field) != new.get(field):
                    raise FinalPublicationError(f"Une page déjà créée diverge pendant la migration d'ordre : {old.get('title')}", remote_execution_started=True)
                continue
            if old.get(field) != new.get(field):
                raise FinalPublicationError(f"Le plan Debate-first modifie {field} pour {old.get('page_id')}", remote_execution_started=True)
        old_op = str(old.get("operation") or "")
        new_op = str(new.get("operation") or "")
        if old_op == "skip":
            if new_op != "skip":
                raise FinalPublicationError(f"Une page skip redevient mutable pendant la migration d'ordre : {old.get('title')}", remote_execution_started=True)
            unchanged_skips.append({"page_id": old.get("page_id"), "title": old.get("title")})
        elif old_op == "create" and new_op == "skip":
            completed.append({"page_id": old.get("page_id"), "title": old.get("title"), "desired_sha256": old.get("desired_sha256"), "remote_revision_id": new.get("remote_revision_id")})
        elif old_op == "create" and new_op == "create":
            remaining.append({"page_id": old.get("page_id"), "title": old.get("title"), "page_type": old.get("page_type")})
        else:
            raise FinalPublicationError("Le plan Debate-first contient une transition d'opération non autorisée", remote_execution_started=True)

    pending_creates = [row for row in (new_plan.get("actions") or []) if str(row.get("operation") or "") == "create"]
    if any(str(row.get("page_type") or "") == "debate" for row in pending_creates):
        if str(pending_creates[0].get("page_type") or "") != "debate":
            raise FinalPublicationError("Le plan successeur ne place pas Debate avant les Arguments restants", remote_execution_started=True)
    return {"completed_before_order_migration": completed, "remaining_after_order_migration": remaining, "unchanged_skips": unchanged_skips}


def _migrate_english_publication_order(
    project_root: Path, debate_id: str, release_copy: Path, state_dir: Path, baseline: Mapping[str, Any],
    plans: Mapping[str, Any], preflight: Mapping[str, Any], authorization: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    old_plan = dict(plans["en_plan"])
    if not _english_plan_needs_debate_first_migration(old_plan):
        return dict(plans), dict(preflight), dict(authorization)
    history_root = state_dir / "publication-order-migrations"
    history_root.mkdir(parents=True, exist_ok=True)
    index = 1
    while (history_root / f"{index:03d}-arguments-before-debate-to-debate-first").exists():
        index += 1
    history = history_root / f"{index:03d}-arguments-before-debate-to-debate-first"
    history.mkdir(parents=True)
    tracked = ("english-publication-config.json", "english-publication-plan.json", "preflight.json", "authorization.json")
    for name in tracked:
        _copy_if_present(state_dir / name, history / name)
    try:
        en_config_path, en_config = _english_config(project_root, debate_id, release_copy, state_dir)
        en_adapter = build_adapter(en_config, project_root)
        publisher = GenericPublisher(en_config, en_adapter, en_config_path)
        new_plan = _reorder_english_plan(publisher.build_plan())
        _assert_safe_english_plan(new_plan, (en_config.get("operation") or {}).get("approved_existing_updates") or {})
        transition = _english_plan_order_transition(old_plan, new_plan)
        write_json(state_dir / "english-publication-plan.json", new_plan)
        new_plans = dict(plans)
        new_plans.update({"en_config_path": en_config_path, "en_config": en_config, "en_plan": new_plan})
        new_preflight = _preflight(project_root, state_dir, new_plans)
        new_authorization = _authorization(state_dir, baseline, new_preflight)
        audit = {
            "schema": "wikidebia-final-publication-order-migration-1.0", "schema_version": "1.0",
            "debate_id": debate_id, "migrated_at": now_iso(),
            "reason": "owner_decision_debate_before_arguments",
            "previous_english_plan_sha256": old_plan.get("plan_sha256"),
            "successor_english_plan_sha256": new_plan.get("plan_sha256"),
            "previous_preflight_sha256": preflight.get("preflight_sha256"),
            "successor_preflight_sha256": new_preflight.get("preflight_sha256"),
            "previous_authorization_sha256": authorization.get("authorization_sha256"),
            "successor_authorization_sha256": new_authorization.get("authorization_sha256"),
            "remote_execution_already_started": True,
            **transition,
        }
        audit["migration_sha256"] = _canonical(audit, "migration_sha256")
        write_json(history / "migration.json", audit)
        return new_plans, new_preflight, new_authorization
    except Exception:
        for name in tracked:
            saved = history / name
            target = state_dir / name
            if saved.is_file():
                shutil.copy2(saved, target)
            elif target.exists():
                target.unlink()
        raise


def _publication_day_change_error(exc: Exception) -> bool:
    text = str(exc)
    return "jour de publication a changé" in text or "day of publication" in text.lower()


def _authorization(state_dir: Path, baseline: Mapping[str, Any], preflight: Mapping[str, Any]) -> dict[str, Any]:
    value = {
        "schema": AUTHORIZATION_SCHEMA,
        "schema_version": "1.0",
        "authorized_at": now_iso(),
        "status": "authorized",
        "baseline_sha256": baseline.get("baseline_sha256"),
        "preflight_sha256": preflight.get("preflight_sha256"),
        "remote_write_authorized": True,
        "execution_started": True,
    }
    value["authorization_sha256"] = _canonical(value, "authorization_sha256")
    write_json(state_dir / "authorization.json", value)
    return value


def publish_final_release(
    project_root: Path,
    debate_id: str,
    work_id: str,
    release_copy: Path,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    release_copy = release_copy.resolve()
    state_dir = _state_dir(project_root, debate_id, work_id)
    completion_path = state_dir / "publication-receipt.json"
    if completion_path.is_file():
        existing = load_json(completion_path, "reçu de publication finale")
        if existing.get("receipt_sha256") != _canonical(existing, "receipt_sha256"):
            raise FinalPublicationError("Reçu de publication finale existant invalide", remote_execution_started=True)
        return existing

    authorization_path = state_dir / "authorization.json"
    remote_started = authorization_path.is_file()
    try:
        if remote_started:
            baseline = load_json(state_dir / "baseline.json", "baseline finale")
            if baseline.get("baseline_sha256") != _canonical(baseline, "baseline_sha256"):
                raise FinalPublicationError("Baseline finale sauvegardée invalide", remote_execution_started=True)
            plans = _load_saved_plans(project_root, state_dir)
            preflight = load_json(state_dir / "preflight.json", "préflight final")
            authorization = load_json(authorization_path, "autorisation finale")
            if authorization.get("authorization_sha256") != _canonical(authorization, "authorization_sha256"):
                raise FinalPublicationError("Autorisation finale sauvegardée invalide", remote_execution_started=True)
        else:
            try:
                baseline = seal_workflow_release_baseline(project_root, debate_id, work_id, release_copy)
            except WorkflowBaselineError as exc:
                raise FinalPublicationError(str(exc)) from exc
            plans = _load_or_build_plans(project_root, debate_id, work_id, release_copy, state_dir)
            preflight = _preflight(project_root, state_dir, plans)
            authorization = _authorization(state_dir, baseline, preflight)
            remote_started = True

        en_receipt_path = state_dir / "english-publication-receipt.json"
        if not en_receipt_path.is_file():
            plans, preflight, authorization = _migrate_english_publication_order(
                project_root, debate_id, release_copy, state_dir, baseline, plans, preflight, authorization
            )
            plans, preflight, authorization = _rollover_english_publication_date(
                project_root, debate_id, release_copy, state_dir, baseline, plans, preflight, authorization
            )
        if en_receipt_path.is_file():
            en_receipt = load_json(en_receipt_path, "reçu anglais final")
        else:
            en_adapter = build_adapter(dict(plans["en_config"]), project_root)
            publisher = GenericPublisher(dict(plans["en_config"]), en_adapter, Path(plans["en_config_path"]))
            try:
                en_counts = publisher.publish(
                    plan=dict(plans["en_plan"]), confirmation=str(plans["en_plan"].get("plan_sha256"))
                )
            except PublicationError as exc:
                if not _publication_day_change_error(exc):
                    raise
                plans, preflight, authorization = _rollover_english_publication_date(
                    project_root, debate_id, release_copy, state_dir, baseline, plans, preflight, authorization
                )
                en_adapter = build_adapter(dict(plans["en_config"]), project_root)
                publisher = GenericPublisher(dict(plans["en_config"]), en_adapter, Path(plans["en_config_path"]))
                en_counts = publisher.publish(
                    plan=dict(plans["en_plan"]), confirmation=str(plans["en_plan"].get("plan_sha256"))
                )
            en_receipt = {
                "status": "published", "completed_at": now_iso(), "counts": en_counts,
                "plan_sha256": plans["en_plan"].get("plan_sha256"),
            }
            en_receipt["receipt_sha256"] = _canonical(en_receipt, "receipt_sha256")
            write_json(en_receipt_path, en_receipt)

        fr_receipt_path = state_dir / "french-publication-receipt.json"
        if fr_receipt_path.is_file():
            fr_receipt = load_json(fr_receipt_path, "reçu français final")
        else:
            fr_adapter = build_adapter(dict(plans["fr_config"]), project_root)
            executor = PlanExecutor(dict(plans["fr_config"]), fr_adapter, Path(plans["fr_config_path"]))
            operations = plans["fr_plan"].get("operations") or {}
            mutations = sum(len(operations.get(name) or []) for name in ("create", "update", "move", "redirect", "delete"))
            if mutations:
                underlying = executor.execute(dict(plans["fr_plan"]), str(plans["fr_plan"].get("plan_sha256")))
                status = "published"
            else:
                underlying = executor.attest_no_changes(dict(plans["fr_plan"]), str(plans["fr_plan"].get("plan_sha256")))
                status = "verified_no_changes"
            fr_receipt = {
                "status": status, "completed_at": now_iso(), "plan_sha256": plans["fr_plan"].get("plan_sha256"),
                "underlying_receipt_sha256": underlying.get("receipt_sha256"), "counts": copy.deepcopy(underlying.get("counts") or {}),
            }
            fr_receipt["receipt_sha256"] = _canonical(fr_receipt, "receipt_sha256")
            write_json(fr_receipt_path, fr_receipt)

        release_tree_sha = str((baseline.get("release") or {}).get("release_copy_tree_sha256") or "")
        installed = _install_release_copy(project_root, debate_id, release_copy, release_tree_sha)
        receipt = {
            "schema": FINAL_RECEIPT_SCHEMA,
            "schema_version": "1.0",
            "debate_id": debate_id,
            "work_id": work_id,
            "completed_at": now_iso(),
            "status": "published",
            "kit_version": KIT_VERSION,
            "validator_version": VALIDATOR_VERSION,
            "baseline_sha256": baseline.get("baseline_sha256"),
            "preflight_sha256": preflight.get("preflight_sha256"),
            "authorization_sha256": authorization.get("authorization_sha256"),
            "english_receipt_sha256": en_receipt.get("receipt_sha256"),
            "french_receipt_sha256": fr_receipt.get("receipt_sha256"),
            "installed_release": installed,
            "semantic_convergence_reused_without_rerun": True,
            "publication_date_rollovers": [
                load_json(path, "audit de changement de jour").get("rollover_sha256")
                for path in sorted((state_dir / "publication-date-rollovers").glob("*/rollover.json"))
            ] if (state_dir / "publication-date-rollovers").is_dir() else [],
            "remote_write_performed": True,
        }
        receipt["receipt_sha256"] = _canonical(receipt, "receipt_sha256")
        write_json(completion_path, receipt)
        return receipt
    except FinalPublicationError:
        raise
    except Exception as exc:
        raise FinalPublicationError(str(exc), remote_execution_started=remote_started) from exc
