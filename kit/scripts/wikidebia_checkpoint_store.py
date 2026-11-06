#!/usr/bin/env python3
"""Conservative, offline checkpoint deduplication and inventory (issue #65).

Default is read-only. --apply replaces identical ZIPs with hard links to a
verified canonical ZIP on the same filesystem. --prune only removes unreferenced
objects from this tool's private object store, never user checkpoints.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
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
    if root.is_symlink() or objects.is_symlink():
        raise StoreError("Racine symbolique interdite")
    groups = defaultdict(list)
    logical_bytes = 0
    if root.exists():
        for path in sorted(root.rglob("*.zip")):
            _safe(path, root)
            size = path.stat().st_size
            logical_bytes += size
            groups[(digest(path), size)].append(path)
    # A private, content-addressed object is only created during explicit apply.
    linked = 0
    saved_bytes = 0
    for (sha, size), paths in sorted(groups.items()):
        if len(paths) < 2 or not apply:
            continue
        obj = objects / sha[:2] / sha
        obj.parent.mkdir(parents=True, exist_ok=True)
        if obj.exists():
            _safe(obj, objects)
            if digest(obj) != sha or obj.stat().st_size != size:
                raise StoreError("Objet existant altéré")
        else:
            source = paths[0]
            fd, tmp_name = tempfile.mkstemp(prefix=".object-", dir=obj.parent)
            try:
                with os.fdopen(fd, "wb") as target, source.open("rb") as original:
                    while True:
                        chunk = original.read(1024 * 1024)
                        if not chunk:
                            break
                        target.write(chunk)
                    target.flush()
                    os.fsync(target.fileno())
                if digest(Path(tmp_name)) != sha:
                    raise StoreError("Empreinte divergente durant la copie")
                os.replace(tmp_name, obj)
            finally:
                if os.path.exists(tmp_name):
                    os.unlink(tmp_name)
        for path in paths:
            if os.stat(path).st_ino == os.stat(obj).st_ino and os.stat(path).st_dev == os.stat(obj).st_dev:
                continue
            if digest(path) != sha:
                raise StoreError("Checkpoint modifié pendant l'inventaire")
            fd, tmp_name = tempfile.mkstemp(prefix=".link-", dir=path.parent)
            os.close(fd)
            os.unlink(tmp_name)
            try:
                os.link(obj, tmp_name)
                if os.stat(path).st_dev != os.stat(obj).st_dev:
                    raise StoreError("Volumes différents")
                if digest(path) != sha:
                    raise StoreError("Checkpoint modifié avant remplacement")
                os.replace(tmp_name, path)
            finally:
                if os.path.lexists(tmp_name):
                    os.unlink(tmp_name)
            linked += 1
            saved_bytes += size
    removed = 0
    if prune and apply and objects.exists():
        for path in sorted(objects.glob("*/*")):
            _safe(path, objects)
            if not (len(path.name) == 64 and path.parent.name == path.name[:2]):
                raise StoreError("Objet non reconnu : nettoyage refusé")
            if digest(path) != path.name:
                raise StoreError("Objet altéré : nettoyage refusé")
            # The object itself has one link; references keep nlink > 1.
            if path.stat().st_nlink == 1:
                path.unlink()
                removed += 1
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
