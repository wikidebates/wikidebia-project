#!/usr/bin/env python3
"""Build a signed read-only remote comparison plan from a sealed release copy.

The command never mutates MediaWiki.  It verifies ``release-copy/``, constructs
an explicit historical inventory (published receipts when available, otherwise
the graph-extraction snapshot), records every remote read, builds the existing
remote-update plan, validates it locally and seals a comparison receipt.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import contextlib
from pathlib import Path
from typing import Any, Mapping

from wikidebia_corpus_build import (
    assert_control_directory,
    assert_no_symlinks,
    exclusive_lock,
    full_tree_sha256,
    load_json as load_corpus_json,
    now_iso,
    relative_to_project,
    sha256_file,
    validate_debate_id,
    write_json,
)
from wikidebia_editorial_workspace import WorkspaceError, validate_work_id, workspace_receipt_hash
from wikidebia_external_deletions import apply_external_deletions
from wikidebia_render import _load_workspace
from wikidebia_update import (
    KIT_VERSION,
    REQUIRED_VALIDATOR_VERSION,
    RemoteUpdatePlanner,
    UpdateError,
    build_adapter,
    sha_object,
    sha_text,
)

COMPARISON_SCHEMA = "wikidebia-read-only-remote-comparison-1.0"
RECEIPT_SCHEMA = "wikidebia-read-only-remote-comparison-receipt-1.0"
INVENTORY_SCHEMA = "wikidebia-remote-inventory-1.0"
READ_CHECKPOINT_SCHEMA = "wikidebia-remote-read-checkpoint-1.0"
COMPARISON_ID_RE = re.compile(r"REMOTE-\d{8}-\d{3}")


class RemoteComparisonError(WorkspaceError):
    pass


def _canonical_sha(value: Mapping[str, Any], excluded: str) -> str:
    body = dict(value)
    body.pop(excluded, None)
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_settings(project_root: Path) -> dict[str, Any]:
    path = project_root / "config/wikidebia.local.json"
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RemoteComparisonError("config/wikidebia.local.json doit être un objet JSON")
    return value


def _comparison_parent(project_root: Path, debate_id: str, work_id: str) -> Path:
    state = assert_control_directory(project_root / ".state", project_root, create=True)
    root = assert_control_directory(state / "remote-comparisons", project_root, create=True)
    debate = assert_control_directory(root / validate_debate_id(debate_id), project_root, create=True)
    return assert_control_directory(debate / validate_work_id(work_id), project_root, create=True)


def _next_comparison_id(parent: Path) -> str:
    day = dt.datetime.now().astimezone().strftime("%Y%m%d")
    used = {item.name for item in parent.iterdir() if item.is_dir()}
    index = 1
    while f"REMOTE-{day}-{index:03d}" in used:
        index += 1
    return f"REMOTE-{day}-{index:03d}"


def _validate_comparison_id(value: str) -> str:
    value = value.strip()
    if not COMPARISON_ID_RE.fullmatch(value):
        raise RemoteComparisonError("comparison_id doit suivre REMOTE-AAAAMMJJ-NNN")
    return value


def _verify_release(project_root: Path, debate_id: str, work_id: str, confirmed: str) -> tuple[Path, dict[str, Any]]:
    workspace, meta = _load_workspace(project_root, debate_id, work_id)
    if meta.get("workspace_sha256") != workspace_receipt_hash(meta):
        raise RemoteComparisonError("Empreinte du workspace invalide")
    allowed_statuses = {
        "release_ready", "remote_plan_ready", "remote_plan_manual_review", "remote_plan_blocked",
        "remote_plan_review_ready", "remote_plan_approved", "remote_plan_rejected",
        "remote_execution_ready", "remote_execution_completed", "remote_execution_no_changes",
        "remote_execution_failed", "remote_execution_blocked", "remote_execution_no_changes_in_scope",
    }
    if meta.get("status") not in allowed_statuses:
        raise RemoteComparisonError(f"Statut incompatible avec la comparaison distante : {meta.get('status')}")
    release_copy = workspace / "release-copy"
    if not release_copy.is_dir() or release_copy.is_symlink():
        raise RemoteComparisonError("release-copy absent ou non sûr")
    assert_no_symlinks(release_copy)
    expected = str((meta.get("release_copy") or {}).get("tree_sha256") or "")
    actual = full_tree_sha256(release_copy)
    if not expected or actual != expected:
        raise RemoteComparisonError("release-copy a changé depuis son scellement")
    if confirmed != expected:
        raise RemoteComparisonError("L’empreinte confirmée ne correspond pas à release-copy")
    manifest = load_corpus_json(release_copy / "manifest.json", "manifest de libération")
    if manifest.get("global_status") != "release_ready":
        raise RemoteComparisonError("Le corpus n’est pas release_ready")
    gate = manifest.get("publication_gate") or {}
    if gate.get("remote_write_authorized") is not False:
        raise RemoteComparisonError("Le verrou d’écriture distante doit rester fermé")
    receipt_path = project_root / ".state/corpus-releases" / debate_id / work_id / "release-receipt.json"
    receipt = load_corpus_json(receipt_path, "reçu de libération")
    if receipt.get("receipt_sha256") != _canonical_sha(receipt, "receipt_sha256"):
        raise RemoteComparisonError("Empreinte du reçu de libération invalide")
    if receipt.get("release_copy_tree_sha256") != expected:
        raise RemoteComparisonError("Le reçu de libération ne correspond pas à release-copy")
    return release_copy, {"workspace": workspace, "meta": meta, "manifest": manifest, "receipt": receipt, "receipt_path": receipt_path}


def _published_state(project_root: Path, debate_id: str, language: str) -> dict[str, Any] | None:
    path = project_root / ".state/published" / debate_id / language / "latest.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    unsigned = dict(data)
    claimed = unsigned.pop("state_sha256", None)
    if claimed != sha_object(unsigned):
        raise RemoteComparisonError(f"Empreinte d’état publié divergente : {relative_to_project(path, project_root)}")
    if data.get("debate_id") != debate_id or data.get("language") != language:
        raise RemoteComparisonError("État publié rattaché à un autre débat ou une autre langue")
    return {"path": path, "data": data}


def _import_baseline(release_copy: Path, debate_id: str) -> list[dict[str, Any]]:
    provenance_path = release_copy / "data/import_provenance.json"
    provenance = load_corpus_json(provenance_path, "provenance d’import")
    rows: list[dict[str, Any]] = []
    for source in provenance.get("pages") or []:
        language = str(source.get("language") or "fr")
        if language != "fr":
            continue
        rel = str(source.get("import_path") or "")
        path = release_copy / rel
        if not rel or not path.is_file():
            raise RemoteComparisonError(f"Source importée absente : {rel or '<vide>'}")
        page_type = "debate" if source.get("kind") == "debate" else "argument"
        page_id = debate_id if page_type == "debate" else str(source.get("page_id") or "")
        if not page_id:
            raise RemoteComparisonError("page_id absent dans la provenance d’import")
        title = str(source.get("canonical_title") or source.get("requested_title") or "").strip()
        if not title:
            raise RemoteComparisonError("Titre historique absent dans la provenance d’import")
        text = path.read_text(encoding="utf-8")
        rows.append({
            "page_id": page_id,
            "page_type": page_type,
            "canonical_title": title,
            "content_sha256": sha_text(text),
            "revision_id": int(source["revision_id"]) if source.get("revision_id") is not None else None,
            "status": "published",
            "source_path": rel,
            "content": text,
        })
    if not rows:
        raise RemoteComparisonError("La provenance d’import ne contient aucune page française")
    return rows


def _write_inventory(path: Path, *, debate_id: str, language: str, pages: list[dict[str, Any]], source: dict[str, Any]) -> dict[str, Any]:
    value = {
        "inventory_version": INVENTORY_SCHEMA,
        "debate_id": debate_id,
        "language": language,
        "inventory_mode": "explicit_debate_pages_read_only",
        "created_at": now_iso(),
        "source": source,
        "pages": pages,
    }
    value["inventory_sha256"] = sha_object(value)
    write_json(path, value)
    return value


def _build_baseline(project_root: Path, release_copy: Path, run_dir: Path, debate_id: str, languages: list[str]) -> dict[str, Any]:
    baseline_dir = run_dir / "baseline"
    baseline_dir.mkdir(parents=True, exist_ok=False)
    imported = _import_baseline(release_copy, debate_id)
    summary: dict[str, Any] = {"languages": {}}
    for language in languages:
        published = _published_state(project_root, debate_id, language)
        if published:
            pages = []
            for row in published["data"].get("pages") or []:
                pages.append({
                    "page_id": str(row.get("page_id")),
                    "page_type": str(row.get("page_type") or "unknown"),
                    "canonical_title": str(row.get("canonical_title")),
                    "content_sha256": str(row.get("content_sha256")),
                    "revision_id": int(row["revision_id"]) if row.get("revision_id") is not None else None,
                    "status": str(row.get("status") or "published"),
                    "source_path": relative_to_project(published["path"], project_root),
                })
            source = {"kind": "published_state_receipt", "path": relative_to_project(published["path"], project_root)}
        elif language == "fr":
            pages = [dict(row) for row in imported]
            source = {"kind": "graph_extraction_snapshot", "path": "data/import_provenance.json"}
        else:
            pages = []
            source = {"kind": "new_language_empty_baseline", "reason": "Aucun état anglais signé ni import anglais n’existe."}
        inventory = _write_inventory(baseline_dir / f"{language}.json", debate_id=debate_id, language=language, pages=pages, source=source)
        summary["languages"][language] = {
            "source": source,
            "page_count": len(pages),
            "inventory_sha256": inventory["inventory_sha256"],
        }
    return summary


class RemoteReadCheckpoint:
    """Atomically seal each completed read batch for an exact comparison."""

    def __init__(self, path: Path, identity: Mapping[str, Any]) -> None:
        self.path = path
        self.identity = dict(identity)
        self.value: dict[str, Any]
        self._pages: dict[tuple[str, str], tuple[bool, int | None, str]] = {}
        if path.is_file() and not path.is_symlink():
            self.value = load_corpus_json(path, "checkpoint de lecture distante")
            self._verify()
        elif path.exists() or path.is_symlink():
            raise RemoteComparisonError("Chemin de checkpoint distant non sûr")
        else:
            timestamp = now_iso()
            self.value = {
                "schema": READ_CHECKPOINT_SCHEMA,
                **self.identity,
                "created_at": timestamp,
                "updated_at": timestamp,
                "title_sets": {},
                "pages": [],
                "page_count": 0,
                "completed_batches": 0,
                "remote_write_performed": False,
            }
            self._write()

    def _verify(self) -> None:
        value = self.value
        if value.get("schema") != READ_CHECKPOINT_SCHEMA:
            raise RemoteComparisonError("Schéma du checkpoint de lecture inconnu")
        if value.get("checkpoint_sha256") != _canonical_sha(value, "checkpoint_sha256"):
            raise RemoteComparisonError("Empreinte du checkpoint de lecture invalide")
        for field, expected in self.identity.items():
            if value.get(field) != expected:
                raise RemoteComparisonError(f"Checkpoint de lecture rattaché à une autre identité : {field}")
        if value.get("remote_write_performed") is not False:
            raise RemoteComparisonError("Le checkpoint de lecture indique une écriture distante")
        rows = value.get("pages")
        if not isinstance(rows, list) or type(value.get("page_count")) is not int or value["page_count"] != len(rows):
            raise RemoteComparisonError("Compteur de pages du checkpoint divergent")
        if type(value.get("completed_batches")) is not int or value["completed_batches"] < 0:
            raise RemoteComparisonError("Compteur de lots du checkpoint divergent")
        if not isinstance(value.get("title_sets"), dict):
            raise RemoteComparisonError("Jeux de titres du checkpoint invalides")
        for row in rows:
            if not isinstance(row, dict):
                raise RemoteComparisonError("Page invalide dans le checkpoint de lecture")
            language = str(row.get("language") or "")
            title = str(row.get("canonical_title") or "")
            key = (language, title)
            if not language or not title or key in self._pages:
                raise RemoteComparisonError("Identité de page invalide ou dupliquée dans le checkpoint")
            exists = row.get("exists") is True
            revision = row.get("revision_id")
            text = str(row.get("content") or "")
            if exists:
                if type(revision) is not int or revision <= 0 or row.get("content_sha256") != sha_text(text):
                    raise RemoteComparisonError("Contenu de page invalide dans le checkpoint")
            elif revision is not None or text or row.get("content_sha256") is not None:
                raise RemoteComparisonError("Page absente incohérente dans le checkpoint")
            self._pages[key] = (exists, revision if exists else None, text)

    def _write(self) -> None:
        self.value["page_count"] = len(self.value.get("pages") or [])
        self.value["updated_at"] = now_iso()
        self.value.pop("checkpoint_sha256", None)
        self.value["checkpoint_sha256"] = _canonical_sha(self.value, "checkpoint_sha256")
        write_json(self.path, self.value)

    def begin_language(self, language: str, titles: list[str]) -> None:
        digest = sha_object({"language": language, "titles": titles})
        sets = self.value.setdefault("title_sets", {})
        existing = sets.get(language)
        expected = {"title_count": len(titles), "titles_sha256": digest}
        if existing is not None and existing != expected:
            raise RemoteComparisonError(
                f"Le jeu de titres {language} a changé depuis le checkpoint"
            )
        if existing is None:
            sets[language] = expected
            self._write()

    def cached(self, language: str, title: str) -> tuple[bool, int | None, str] | None:
        return self._pages.get((language, title))

    def record_batch(
        self,
        language: str,
        titles: list[str],
        observed: Mapping[str, tuple[bool, int | None, str]],
    ) -> None:
        missing = sorted(set(titles) - set(observed))
        unexpected = sorted(set(observed) - set(titles))
        if missing or unexpected:
            raise RemoteComparisonError(
                "Lecture MediaWiki groupée incohérente : "
                + ", ".join(missing + unexpected)
            )
        rows = self.value.setdefault("pages", [])
        observed_at = now_iso()
        for title in titles:
            key = (language, title)
            if key in self._pages:
                raise RemoteComparisonError("Page déjà scellée dans le checkpoint : " + title)
            exists, revision_id, text = observed[title]
            exists = bool(exists)
            normalized_revision = int(revision_id) if revision_id is not None else None
            normalized_text = str(text or "")
            if exists and (normalized_revision is None or normalized_revision <= 0):
                raise RemoteComparisonError("Révision distante absente pour " + title)
            if not exists:
                normalized_revision = None
                normalized_text = ""
            row = {
                "language": language,
                "canonical_title": title,
                "exists": exists,
                "revision_id": normalized_revision,
                "content": normalized_text,
                "content_sha256": sha_text(normalized_text) if exists else None,
                "observed_at": observed_at,
            }
            rows.append(row)
            self._pages[key] = (exists, normalized_revision, normalized_text)
        rows.sort(key=lambda row: (str(row["language"]), str(row["canonical_title"])))
        self.value["completed_batches"] = int(self.value.get("completed_batches", 0)) + 1
        self._write()

    @property
    def checkpoint_sha256(self) -> str:
        return str(self.value.get("checkpoint_sha256") or "")

    @property
    def page_count(self) -> int:
        return len(self._pages)


class ReadOnlyRecordingAdapter:
    """Allow only the methods used by the planner and record every remote read."""

    def __init__(self, base: Any, checkpoint: RemoteReadCheckpoint | None = None) -> None:
        self.base = base
        self.checkpoint = checkpoint
        self.current_language: str | None = None
        self.events: list[dict[str, Any]] = []
        self.pages: dict[tuple[str, str], dict[str, Any]] = {}
        self.backlink_rows: list[dict[str, Any]] = []
        self.write_attempts = 0
        self.prefetched_pages: dict[tuple[str, str], tuple[bool, int | None, str]] = {}
        self.checkpoint_pages_reused = 0
        self.network_pages_read = 0

    def open_language(self, language: str, expected_user: str) -> None:
        self.base.open_language(language, expected_user)
        self.current_language = language
        self.events.append({"event": "open_language", "language": language, "expected_user": expected_user})

    def assert_identity(self, expected_user: str) -> None:
        self.base.assert_identity(expected_user)
        self.events.append({"event": "identity_verified", "language": self.current_language, "expected_user": expected_user})

    def close_language(self) -> None:
        try:
            self.base.close_language()
        finally:
            self.events.append({"event": "close_language", "language": self.current_language})
            self.current_language = None

    def read_page(self, title: str):
        language = str(self.current_language or "")
        key = (language, title)
        if key in self.prefetched_pages:
            exists, revision_id, text = self.prefetched_pages[key]
        else:
            cached = self.checkpoint.cached(language, title) if self.checkpoint else None
            if cached is not None:
                exists, revision_id, text = cached
                self.checkpoint_pages_reused += 1
            else:
                exists, revision_id, text = self.base.read_page(title)
                self.network_pages_read += 1
                if self.checkpoint is not None:
                    self.checkpoint.record_batch(
                        language, [title], {title: (exists, revision_id, text)}
                    )
        row = {
            "language": language,
            "canonical_title": title,
            "exists": bool(exists),
            "revision_id": int(revision_id) if revision_id is not None else None,
            "content_sha256": sha_text(text) if exists else None,
            "observed_at": now_iso(),
        }
        self.pages[(language, title)] = row
        self.events.append({"event": "read_page", **row})
        return exists, revision_id, text

    def prefetch_pages(self, titles: list[str]) -> None:
        reader = getattr(self.base, "read_pages", None)
        if not callable(reader):
            return
        requested = list(dict.fromkeys(str(title) for title in titles if str(title)))
        language = str(self.current_language or "")
        if self.checkpoint is not None:
            self.checkpoint.begin_language(language, requested)
        cached: dict[str, tuple[bool, int | None, str]] = {}
        for title in requested:
            value = self.checkpoint.cached(language, title) if self.checkpoint else None
            if value is not None:
                cached[title] = value
        pending = [title for title in requested if title not in cached]
        network_batches = 0
        for index in range(0, len(pending), 50):
            batch = pending[index:index + 50]
            observed = reader(batch)
            missing = sorted(set(batch) - set(observed))
            if missing:
                raise RemoteComparisonError(
                    "Lecture MediaWiki groupée incomplète : " + ", ".join(missing)
                )
            if self.checkpoint is not None:
                self.checkpoint.record_batch(language, batch, observed)
            cached.update(observed)
            network_batches += 1
        self.prefetched_pages.update({(language, title): value for title, value in cached.items()})
        self.checkpoint_pages_reused += len(requested) - len(pending)
        self.network_pages_read += len(pending)
        self.events.append({
            "event": "prefetch_pages",
            "language": language,
            "page_count": len(requested),
            "network_page_count": len(pending),
            "checkpoint_page_count": len(requested) - len(pending),
            "batch_count": network_batches,
            "observed_at": now_iso(),
        })

    def backlinks(self, title: str) -> list[str]:
        rows = list(self.base.backlinks(title))
        item = {"language": self.current_language, "canonical_title": title, "backlinks": rows, "observed_at": now_iso()}
        self.backlink_rows.append(item)
        self.events.append({"event": "read_backlinks", **item})
        return rows

    def user_rights(self) -> set[str]:
        return set()

    def _blocked_write(self, *args: Any, **kwargs: Any) -> None:
        self.write_attempts += 1
        raise RemoteComparisonError("Toute écriture distante est interdite pendant la comparaison")

    write_page = _blocked_write
    move_page = _blocked_write
    delete_page = _blocked_write

    def inventory(self, debate_id: str, comparison_id: str) -> dict[str, Any]:
        rows = sorted(self.pages.values(), key=lambda row: (str(row["language"]), str(row["canonical_title"])))
        value = {
            "schema": "wikidebia-observed-remote-inventory-1.0",
            "debate_id": debate_id,
            "comparison_id": comparison_id,
            "created_at": now_iso(),
            "mode": "read_only",
            "page_count": len(rows),
            "pages": rows,
            "backlink_queries": self.backlink_rows,
            "write_attempts": self.write_attempts,
            "remote_write_performed": False,
        }
        value["inventory_sha256"] = sha_object(value)
        return value


@contextlib.contextmanager
def _working_directory(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _config(project_root: Path, release_copy: Path, run_dir: Path, debate_id: str, languages: list[str]) -> dict[str, Any]:
    settings = _load_settings(project_root)
    users = settings.get("expected_users") or {"fr": "ChatGPT", "en": "ChatGPT"}
    sites = {language: {"code": language, "expected_user": str(users.get(language) or "ChatGPT")} for language in languages}
    return {
        "kit_version": KIT_VERSION,
        "project_root": ".",
        "family": str(settings.get("family") or "wikidebates"),
        "family_file": "kit/families/wikidebates_family.py",
        "pywikibot_dir": "private/pywikibot",
        "sites": sites,
        "languages": languages,
        "debate_id": debate_id,
        "corpus_root": relative_to_project(release_copy, project_root),
        "state_inventory_root": relative_to_project(run_dir / "baseline", project_root),
        "logs_dir": relative_to_project(run_dir / "logs", project_root),
        "published_state_dir": ".state/published",
        "receipts_dir": ".state/receipts",
        "validator": {
            "command": [".venv/bin/python", "validator/scripts/wikidebia_validate.py", "validate"],
            "required_version": REQUIRED_VALIDATOR_VERSION,
            "scopes": ["schema", "coherence", "graph", "files", "batches", "sources", "wikicode", "bilingual", "editorial", "workflow"],
            "fingerprint_path": "validator",
            "cache_dir": ".state/validation-cache/remote-update",
        },
        "comparison_mode": "read_only",
        "remote_write_authorized": False,
    }


def _validate_plan(project_root: Path, plan_path: Path, json_path: Path, text_path: Path) -> dict[str, Any]:
    command = [
        str(project_root / ".venv/bin/python"),
        str(project_root / "validator/scripts/wikidebia_validate.py"),
        "validate-plan", str(plan_path), "--format", "json",
        "--json-output", str(json_path), "--text-output", str(text_path),
    ]
    completed = subprocess.run(command, cwd=project_root, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RemoteComparisonError("Validation locale du plan refusée :\n" + completed.stdout + completed.stderr)
    report = json.loads(json_path.read_text(encoding="utf-8"))
    if int((report.get("summary") or {}).get("errors", 0)):
        raise RemoteComparisonError("Le validateur signale des erreurs dans le plan")
    return report


def compare_workspace(
    project_root: Path,
    debate_id: str,
    work_id: str,
    confirm_release_sha256: str,
    *,
    scope: str = "all",
    comparison_id: str | None = None,
    adapter: Any | None = None,
    validate_plan_fn: Any = _validate_plan,
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    debate_id = validate_debate_id(debate_id)
    work_id = validate_work_id(work_id)
    languages = ["fr", "en"] if scope == "all" else [scope]
    if scope not in {"all", "fr", "en"}:
        raise RemoteComparisonError("scope doit être all, fr ou en")
    release_copy, release = _verify_release(project_root, debate_id, work_id, confirm_release_sha256)
    parent = _comparison_parent(project_root, debate_id, work_id)
    comparison_id = _validate_comparison_id(comparison_id) if comparison_id else _next_comparison_id(parent)
    run_dir = parent / comparison_id
    checkpoint_identity = {
        "debate_id": debate_id,
        "work_id": work_id,
        "comparison_id": comparison_id,
        "scope": scope,
        "release_copy_tree_sha256": confirm_release_sha256,
    }
    checkpoint_path = run_dir / "read-checkpoint.json"
    resumed = False
    if run_dir.is_symlink():
        raise RemoteComparisonError("Dossier de comparaison non sûr")
    if run_dir.is_dir():
        if (run_dir / "comparison-receipt.json").exists():
            raise RemoteComparisonError("L’identifiant de comparaison est déjà finalisé")
        checkpoint = RemoteReadCheckpoint(checkpoint_path, checkpoint_identity)
        resumed = True
        for item in list(run_dir.iterdir()):
            if item == checkpoint_path:
                continue
            if item.is_dir() and not item.is_symlink():
                shutil.rmtree(item)
            else:
                item.unlink()
    elif run_dir.exists():
        raise RemoteComparisonError("Chemin de comparaison déjà occupé")
    else:
        run_dir.mkdir(parents=False)
        checkpoint = RemoteReadCheckpoint(checkpoint_path, checkpoint_identity)
    try:
        baseline_summary = _build_baseline(project_root, release_copy, run_dir, debate_id, languages)
        config = _config(project_root, release_copy, run_dir, debate_id, languages)
        config_path = run_dir / "config.json"
        write_json(config_path, config)
        base_adapter = adapter if adapter is not None else build_adapter(config, project_root)
        recorder = ReadOnlyRecordingAdapter(base_adapter, checkpoint)
        with _working_directory(project_root):
            planner = RemoteUpdatePlanner(config, recorder, config_path)
            plan = planner.build_plan(mode="all")
        inventory = recorder.inventory(debate_id, comparison_id)
        inventory_path = run_dir / "remote-inventory.json"
        write_json(inventory_path, inventory)
        external_deletions = apply_external_deletions(
            project_root, debate_id, plan, inventory,
        )
        plan.setdefault("preconditions", []).extend(["read_only_comparison_completed", "plan_not_executed"])
        plan.pop("plan_sha256", None)
        plan["plan_sha256"] = sha_object(plan)
        plan_path = run_dir / "update-plan.json"
        write_json(plan_path, plan)
        validation_json = run_dir / "plan-validation.json"
        validation_txt = run_dir / "plan-validation.txt"
        validation = validate_plan_fn(project_root, plan_path, validation_json, validation_txt)
        if recorder.write_attempts:
            raise RemoteComparisonError("Une tentative d’écriture distante a été détectée")
        counts = dict(plan.get("counts") or {})
        status = "blocked" if counts.get("blocked") else ("manual_review" if counts.get("manual_review") else "plan_ready")
        events_path = run_dir / "read-only-events.jsonl"
        events_path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in recorder.events), encoding="utf-8", newline="\n")
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "schema_version": "1.0",
            "comparison_schema": COMPARISON_SCHEMA,
            "debate_id": debate_id,
            "work_id": work_id,
            "comparison_id": comparison_id,
            "created_at": now_iso(),
            "status": status,
            "scope": scope,
            "kit_version": KIT_VERSION,
            "validator_version": REQUIRED_VALIDATOR_VERSION,
            "release_copy_tree_sha256": confirm_release_sha256,
            "release_receipt_sha256": str(release["receipt"].get("receipt_sha256") or ""),
            "baseline_summary": baseline_summary,
            "external_deletions": external_deletions,
            "plan_path": relative_to_project(plan_path, project_root),
            "plan_sha256": plan["plan_sha256"],
            "remote_inventory_path": relative_to_project(inventory_path, project_root),
            "remote_inventory_sha256": inventory["inventory_sha256"],
            "plan_validation_path": relative_to_project(validation_json, project_root),
            "plan_validation_sha256": sha256_file(validation_json),
            "read_checkpoint_path": relative_to_project(checkpoint_path, project_root),
            "read_checkpoint_sha256": checkpoint.checkpoint_sha256,
            "read_checkpoint_page_count": checkpoint.page_count,
            "checkpoint_pages_reused": recorder.checkpoint_pages_reused,
            "network_pages_read": recorder.network_pages_read,
            "comparison_resumed": resumed,
            "validation_cache_status": planner.validation_cache_status,
            "validation_cache_key": planner.validation_cache_key,
            "counts": counts,
            "remote_access_performed": True,
            "remote_write_performed": False,
            "execution_authorized": False,
        }
        receipt["receipt_sha256"] = _canonical_sha(receipt, "receipt_sha256")
        write_json(run_dir / "comparison-receipt.json", receipt)
        meta = release["meta"]
        comparison_meta = {
            "comparison_id": comparison_id,
            "status": status,
            "plan_path": receipt["plan_path"],
            "plan_sha256": plan["plan_sha256"],
            "receipt_path": relative_to_project(run_dir / "comparison-receipt.json", project_root),
            "receipt_sha256": receipt["receipt_sha256"],
            "completed_at": receipt["created_at"],
        }
        meta["remote_comparison"] = comparison_meta
        history = list(meta.get("remote_comparisons") or [])
        history.append(comparison_meta)
        meta["remote_comparisons"] = history
        meta["status"] = "remote_plan_ready" if status == "plan_ready" else ("remote_plan_manual_review" if status == "manual_review" else "remote_plan_blocked")
        meta["workspace_sha256"] = workspace_receipt_hash(meta)
        write_json(release["workspace"] / "workspace.json", meta)
        return {
            "status": status,
            "debate_id": debate_id,
            "work_id": work_id,
            "comparison_id": comparison_id,
            "plan": receipt["plan_path"],
            "plan_sha256": plan["plan_sha256"],
            "counts": counts,
            "comparison_resumed": resumed,
            "checkpoint_pages_reused": recorder.checkpoint_pages_reused,
            "network_pages_read": recorder.network_pages_read,
            "validation_cache_status": planner.validation_cache_status,
            "validation_cache_key": planner.validation_cache_key,
            "external_deletions": external_deletions,
            "remote_write_performed": False,
        }
    except Exception as exc:
        # Keep failed evidence only when a plan or remote inventory exists; otherwise
        # retain a signed read checkpoint so the exact comparison ID can resume.
        if not checkpoint_path.is_file() and not (run_dir / "remote-inventory.json").exists() and not (run_dir / "update-plan.json").exists():
            shutil.rmtree(run_dir, ignore_errors=True)
        if checkpoint_path.is_file():
            resume = (
                f"./wikidebia corpus-workspace-finalize {debate_id} --work-id {work_id} "
                f"--scope {scope} --refresh-remote --comparison-id {comparison_id}"
            )
            raise RemoteComparisonError(
                f"{exc}\nReprise exacte : {resume}"
            ) from exc
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Comparer un corpus release_ready au wiki en lecture seule")
    parser.add_argument("debate_id")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--confirm-release-sha256", required=True)
    parser.add_argument("--scope", choices=("all", "fr", "en"), default="all")
    parser.add_argument("--comparison-id")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--machine-readable", action="store_true")
    args = parser.parse_args(argv)
    with exclusive_lock(args.project_root.resolve(), args.debate_id, "remote-compare"):
        result = compare_workspace(
            args.project_root, args.debate_id, args.work_id, args.confirm_release_sha256,
            scope=args.scope, comparison_id=args.comparison_id,
        )
    if args.machine_readable:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(f"Comparaison distante : {result['status']}")
        print(f"Plan : {result['plan']}")
        print(f"SHA-256 : {result['plan_sha256']}")
        print(json.dumps(result["counts"], ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "plan_ready" else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RemoteComparisonError, UpdateError) as exc:
        print(f"COMPARAISON DISTANTE BLOQUÉE : {exc}", file=os.sys.stderr)
        raise SystemExit(2)
