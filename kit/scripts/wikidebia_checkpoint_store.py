#!/usr/bin/env python3
"""Conservative, offline checkpoint deduplication and inventory (issue #65).

Default is read-only. --apply uses copy-on-write reflinks where supported.
Hardlinks are forbidden. --prune is disabled pending a safe redesign.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import fcntl
import tempfile
from collections import defaultdict
from pathlib import Path

class StoreError(RuntimeError):
    pass

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def _safe(path: Path, root: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise StoreError(f"Fichier non sûr : {path}")
    if not path.resolve().is_relative_to(root.resolve()):
        raise StoreError(f"Chemin extérieur : {path}")

def inventory(project_root: Path, *, apply: bool = False, prune: bool = False) -> dict:
    root = project_root / ".state/resume-checkpoints"
    objects = project_root / ".state/checkpoint-objects"
    if (project_root / ".state").is_symlink() or root.is_symlink() or objects.is_symlink():
        raise StoreError("Racine symbolique interdite")
    groups = defaultdict(list)
    logical_bytes = 0
    if root.exists():
        for path in sorted(root.rglob("*.zip")):
            _safe(path, root)
            if any(parent.is_symlink() for parent in path.parents if parent != project_root):
                raise StoreError("Répertoire symbolique interdit")
            size = path.stat().st_size
            logical_bytes += size
            groups[(digest(path), size)].append(path)
    # Reflinks share extents with copy-on-write, not mutable inodes.
    # Never fall back to hardlinks on unsupported filesystems.
    FICLONE = 0x40049409
    linked = 0
    saved_bytes = 0
    if apply and prune:
        raise StoreError("--prune indisponible avec les reflinks")
    for (sha, size), paths in sorted(groups.items()):
        if not apply or len(paths) < 2:
            continue
        source = paths[0]
        for path in paths[1:]:
            if os.stat(source).st_ino == os.stat(path).st_ino and os.stat(source).st_dev == os.stat(path).st_dev:
                raise StoreError("Liens physiques existants : réparation manuelle requise")
            if digest(source) != sha or digest(path) != sha:
                raise StoreError("Checkpoint modifié pendant l'inventaire")
            fd, tmp_name = tempfile.mkstemp(prefix=".reflink-", dir=path.parent)
            try:
                with os.fdopen(fd, "wb") as target, source.open("rb") as original:
                    try:
                        fcntl.ioctl(target.fileno(), FICLONE, original.fileno())
                    except OSError as exc:
                        raise StoreError("Reflink non pris en charge : aucun checkpoint modifié") from exc
                    target.flush()
                    os.fsync(target.fileno())
                if digest(Path(tmp_name)) != sha or digest(path) != sha:
                    raise StoreError("Empreinte divergente : remplacement refusé")
                os.chmod(tmp_name, stat.S_IMODE(path.stat().st_mode))
                os.replace(tmp_name, path)
            finally:
                if os.path.exists(tmp_name):
                    os.unlink(tmp_name)
            linked += 1
            saved_bytes += size
    removed = 0
    rows = [{"sha256": sha, "size": size, "copies": len(paths)}
            for (sha, size), paths in sorted(groups.items())]
    return {
        "schema": "wikidebia-checkpoint-dedup-inventory-1.0",
        "mode": "apply" if apply else "dry_run",
        "files": sum(len(paths) for paths in groups.values()),
        "unique_contents": len(groups),
        "logical_bytes": logical_bytes,
        "potential_duplicate_bytes": sum((len(paths) - 1) * size for (_, size), paths in groups.items()),
        "linked_files": linked,
        "linked_bytes": saved_bytes,
        "pruned_objects": removed,
        "objects": rows,
        "remote_access_performed": False,
        "remote_write_performed": False,
    }

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--prune", action="store_true")
    args = parser.parse_args()
    if args.prune and not args.apply:
        parser.error("--prune requires --apply")
    try:
        result = inventory(args.project_root.resolve(), apply=args.apply, prune=args.prune)
    except (StoreError, OSError) as exc:
        parser.exit(2, f"INVENTAIRE BLOQUÉ : {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
