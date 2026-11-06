#!/usr/bin/env python3
"""Export and restore minimal signed translation resume checkpoints."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from wikidebia_corpus_build import (
    CorpusBuildError,
    canonical_json,
    load_json,
    relative_to_project,
    sha256_bytes,
    sha256_file,
    validate_debate_id,
    write_json,
)
from wikidebia_editorial_workspace import WorkspaceError, validate_work_id
from wikidebia_release_info import KIT_VERSION, NORM_VERSION, VALIDATOR_VERSION
from wikidebia_render import _load_workspace
from wikidebia_translation_packet import verified_fragment_coverage
from wikidebia_update import sha_object


MANIFEST_NAME = "CHECKPOINT_MANIFEST.json"
CHECKPOINT_SCHEMA = "wikidebia-portable-translation-checkpoint-1.0"
MAX_EXPANDED_BYTES = 64 * 1024 * 1024


class TranslationCheckpointError(WorkspaceError):
    pass


def _safe_relative(value: str) -> Path:
    pure = PurePosixPath(value)
    if (
        not value
        or pure.is_absolute()
        or ".." in pure.parts
        or any(part in {"", "."} for part in pure.parts)
    ):
        raise TranslationCheckpointError(f"Chemin de checkpoint dangereux : {value}")
    return Path(*pure.parts)


def _signed(value: Mapping[str, Any], field: str) -> bool:
    body = dict(value)
    claimed = body.pop(field, None)
    return bool(claimed) and claimed == sha_object(body)


def _assert_safe_under(root: Path, path: Path) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise TranslationCheckpointError(f"Chemin extérieur au Work : {path}") from exc
    current = root
    if current.is_symlink():
        raise TranslationCheckpointError(f"Racine symbolique interdite : {root}")
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise TranslationCheckpointError(f"Lien symbolique interdit : {current}")


def _optional_identity(path: Path, field: str) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    value = load_json(path, path.name)
    if not _signed(value, field):
        raise TranslationCheckpointError(f"Artefact actif non signé : {path.name}")
    return value


def _checkpoint_files(workspace: Path) -> list[Path]:
    required = [
        workspace / "workspace.json",
        workspace / "reviews/en/translation_review.json",
    ]
    for path in required:
        if not path.is_file():
            raise TranslationCheckpointError(f"Fichier requis absent : {path}")
    files = list(required)
    content = workspace / "content-reviewed-copy"
    if not content.is_dir() or content.is_symlink():
        raise TranslationCheckpointError("Source française verrouillée absente ou non sûre")
    for path in sorted(content.rglob("*")):
        if path.is_symlink():
            raise TranslationCheckpointError(f"Lien symbolique interdit : {path}")
        if path.is_file():
            files.append(path)

    fixed = [
        "audits/translation-resume.json",
        "audits/translation-fragment-next.json",
        "audits/translation-next.json",
        "audits/en_translation_worklist.json",
        "audits/translation-memory/reuse.json",
        "audits/translation-memory/field-reuse.json",
    ]
    files.extend(workspace / rel for rel in fixed if (workspace / rel).is_file())
    review = load_json(required[1], "revue anglaise du checkpoint")
    review_by_id = {
        str(row.get("id")): row
        for row in review.get("arguments") or []
        if isinstance(row, dict) and row.get("id")
    }
    fragment_coverage = verified_fragment_coverage(workspace, review_by_id)
    files.extend(
        workspace / "audits/translation-fragments" / f"{page_id}-application.json"
        for page_id in sorted(fragment_coverage)
    )
    fragment_selection = _optional_identity(
        workspace / "audits/translation-fragment-next.json", "selection_sha256",
    )
    unit_id = str((fragment_selection or {}).get("unit_id") or "")
    page_id = str((fragment_selection or {}).get("page_id") or "")
    active = []
    if unit_id:
        active.extend([
            f"audits/translation-packets/{unit_id}.json",
            f"reviews/en/unit-patches/{unit_id}.json",
            f"audits/translation-patches/{unit_id}-application.json",
        ])
    if page_id:
        active.extend([
            f"reviews/en/argument-fragments/{page_id}.json",
            f"audits/translation-fragments/{page_id}-context.json",
            f"audits/translation-fragments/{page_id}-application.json",
        ])
    files.extend(workspace / rel for rel in active if (workspace / rel).is_file())
    unique = sorted(set(files), key=lambda path: path.relative_to(workspace).as_posix())
    for path in unique:
        _assert_safe_under(workspace, path)
        if path.is_symlink() or not path.is_file():
            raise TranslationCheckpointError(f"Fichier de checkpoint non sûr : {path}")
    return unique


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    info.create_system = 3
    return info


def export_checkpoint(
    project_root: Path, debate_id: str, work_id: str,
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    debate_id = validate_debate_id(debate_id)
    work_id = validate_work_id(work_id)
    workspace, meta = _load_workspace(project_root, debate_id, work_id)
    files = _checkpoint_files(workspace)
    entries = []
    payloads: dict[str, bytes] = {}
    for path in files:
        relative = path.relative_to(workspace).as_posix()
        archive_path = "workspace/" + relative
        raw = path.read_bytes()
        payloads[archive_path] = raw
        entries.append({
            "path": archive_path,
            "size": len(raw),
            "sha256": sha256_bytes(raw),
        })
    review_path = workspace / "reviews/en/translation_review.json"
    manifest: dict[str, Any] = {
        "schema": CHECKPOINT_SCHEMA,
        "kit_version": KIT_VERSION,
        "normative_revision": NORM_VERSION,
        "validator_version": VALIDATOR_VERSION,
        "debate_id": debate_id,
        "work_id": work_id,
        "workspace_sha256": meta.get("workspace_sha256"),
        "translation_review_sha256": sha256_file(review_path),
        "fragment_application_receipt_count": sum(
            path.parent.name == "translation-fragments"
            and path.name.endswith("-application.json")
            for path in files
        ),
        "files": entries,
        "expanded_bytes": sum(row["size"] for row in entries),
        "contains_secrets": False,
        "remote_access_performed": False,
        "remote_write_performed": False,
    }
    manifest["checkpoint_sha256"] = sha_object(manifest)
    manifest_raw = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, indent=2,
    ).encode("utf-8") + b"\n"
    output_dir = project_root / ".state/resume-checkpoints" / debate_id / work_id
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"{manifest['checkpoint_sha256']}.zip"
    temporary = archive_path.with_name(f".{archive_path.name}.tmp-{os.getpid()}")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr(_zip_info(MANIFEST_NAME), manifest_raw, compresslevel=9)
        for name in sorted(payloads):
            archive.writestr(_zip_info(name), payloads[name], compresslevel=9)
    os.replace(temporary, archive_path)
    latest: dict[str, Any] = {
        "schema": "wikidebia-portable-translation-checkpoint-latest-1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "checkpoint_sha256": manifest["checkpoint_sha256"],
        "archive_path": relative_to_project(archive_path, project_root),
        "archive_sha256": sha256_file(archive_path),
        "archive_bytes": archive_path.stat().st_size,
        "expanded_bytes": manifest["expanded_bytes"],
        "remote_access_performed": False,
        "remote_write_performed": False,
    }
    latest["receipt_sha256"] = sha_object(latest)
    write_json(output_dir / "latest.json", latest)
    return {**latest, "receipt_path": relative_to_project(output_dir / "latest.json", project_root)}


def _read_archive(archive_path: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    if not archive_path.is_file() or archive_path.is_symlink():
        raise TranslationCheckpointError("Archive de checkpoint absente ou non sûre")
    payloads: dict[str, bytes] = {}
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)) or MANIFEST_NAME not in names:
            raise TranslationCheckpointError("Inventaire ZIP du checkpoint invalide")
        total = 0
        for info in infos:
            _safe_relative(info.filename)
            mode = (info.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK or info.is_dir():
                raise TranslationCheckpointError("Lien ou répertoire ZIP interdit")
            total += info.file_size
            if total > MAX_EXPANDED_BYTES:
                raise TranslationCheckpointError("Checkpoint décompressé trop volumineux")
            payloads[info.filename] = archive.read(info)
    try:
        manifest = json.loads(payloads.pop(MANIFEST_NAME).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError) as exc:
        raise TranslationCheckpointError("Manifeste du checkpoint illisible") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != CHECKPOINT_SCHEMA
        or not _signed(manifest, "checkpoint_sha256")
        or manifest.get("contains_secrets") is not False
    ):
        raise TranslationCheckpointError("Manifeste du checkpoint invalide")
    declared = manifest.get("files")
    if not isinstance(declared, list):
        raise TranslationCheckpointError("Liste de fichiers du checkpoint invalide")
    declared_by_path = {str(row.get("path")): row for row in declared if isinstance(row, dict)}
    if len(declared_by_path) != len(declared) or set(declared_by_path) != set(payloads):
        raise TranslationCheckpointError("Le contenu ZIP diverge du manifeste")
    for name, raw in payloads.items():
        row = declared_by_path[name]
        if row.get("size") != len(raw) or row.get("sha256") != sha256_bytes(raw):
            raise TranslationCheckpointError(f"Empreinte de fichier divergente : {name}")
        if not name.startswith("workspace/"):
            raise TranslationCheckpointError(f"Chemin hors workspace interdit : {name}")
    return manifest, payloads


def restore_checkpoint(project_root: Path, archive_path: Path) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    archive_path = archive_path.expanduser().resolve()
    manifest, payloads = _read_archive(archive_path)
    debate_id = validate_debate_id(str(manifest.get("debate_id") or ""))
    work_id = validate_work_id(str(manifest.get("work_id") or ""))
    target = project_root / ".state/editorial-workspaces" / debate_id / work_id
    relative_payloads = {
        _safe_relative(name.removeprefix("workspace/")): raw
        for name, raw in payloads.items()
    }
    workspace_json = json.loads(relative_payloads[Path("workspace.json")].decode("utf-8"))
    if (
        workspace_json.get("debate_id") != debate_id
        or workspace_json.get("work_id") != work_id
        or workspace_json.get("workspace_sha256") != manifest.get("workspace_sha256")
    ):
        raise TranslationCheckpointError("Identité du workspace archivé divergente")

    restored_files = 0
    if target.exists():
        if target.is_symlink() or not target.is_dir():
            raise TranslationCheckpointError("Cible de restauration non sûre")
        for relative, raw in relative_payloads.items():
            destination = target / relative
            _assert_safe_under(target, destination)
            if destination.exists():
                if destination.is_symlink() or not destination.is_file():
                    raise TranslationCheckpointError(f"Cible existante non sûre : {relative}")
                if destination.read_bytes() != raw:
                    raise TranslationCheckpointError(
                        f"Le Work local diverge du checkpoint : {relative}"
                    )
        for relative, raw in relative_payloads.items():
            destination = target / relative
            _assert_safe_under(target, destination)
            if destination.exists():
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(f".{destination.name}.tmp-{os.getpid()}")
            temporary.write_bytes(raw)
            os.replace(temporary, destination)
            restored_files += 1
        mode = "completed_existing_workspace"
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{work_id}-restore-", dir=target.parent))
        try:
            for relative, raw in relative_payloads.items():
                destination = staging / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
                restored_files += 1
            os.replace(staging, target)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        mode = "created_workspace"
    _workspace, meta = _load_workspace(project_root, debate_id, work_id)
    if meta.get("workspace_sha256") != manifest.get("workspace_sha256"):
        raise TranslationCheckpointError("Workspace restauré non conforme au manifeste")
    return {
        "status": "restored",
        "mode": mode,
        "debate_id": debate_id,
        "work_id": work_id,
        "checkpoint_sha256": manifest["checkpoint_sha256"],
        "archive_sha256": sha256_file(archive_path),
        "restored_files": restored_files,
        "workspace_path": relative_to_project(target, project_root),
        "remote_access_performed": False,
        "remote_write_performed": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--export", action="store_true")
    actions.add_argument("--restore", type=Path, metavar="ARCHIVE")
    parser.add_argument("--debate-id")
    parser.add_argument("--work-id")
    parser.add_argument("--machine-readable", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.export:
        if not args.debate_id or not args.work_id:
            raise TranslationCheckpointError("--export exige --debate-id et --work-id")
        result = export_checkpoint(args.project_root, args.debate_id, args.work_id)
    else:
        result = restore_checkpoint(args.project_root, args.restore)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True) if args.machine_readable else json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        TranslationCheckpointError, WorkspaceError, CorpusBuildError,
        OSError, ValueError, KeyError, zipfile.BadZipFile,
    ) as exc:
        print(f"CHECKPOINT DE TRADUCTION BLOQUÉ : {exc}", file=os.sys.stderr)
        raise SystemExit(2)
