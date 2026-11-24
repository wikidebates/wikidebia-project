#!/usr/bin/env python3
"""Export the three verified component ZIPs and their matching unified source.

Run from a Git checkout. Only the exact tracked component inventories are
exported; private data, corpus files and runtime caches are never included.
"""
from __future__ import annotations

import argparse
import json
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kit" / "scripts"))

from wikidebia_manage import (
    COMPONENTS, compare_normative_trees, generate_readable_sources,
    inspect_component_zip, verify_version_set,
)

METADATA = {"PACKAGE_MANIFEST_SHA256.json", "PACKAGE_RECEIPT.json"}


def component_zip(root: Path, component: str, target: Path) -> None:
    base = root / component
    manifest = json.loads((base / "PACKAGE_MANIFEST_SHA256.json").read_text(encoding="utf-8"))
    declared = [row["path"] for row in manifest["files"]]
    if len(set(declared)) != len(declared) or len(declared) != manifest["declared_file_count"]:
        raise ValueError(f"{component}: invalid manifest inventory")
    expected = set(declared) | METADATA
    raw = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z", "--", component])
    tracked = {name.decode("utf-8").removeprefix(component + "/") for name in raw.split(b"\0") if name}
    if tracked != expected:
        raise ValueError(f"{component}: Git inventory differs from manifest")
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(expected):
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts or relative.as_posix() != name:
                raise ValueError(f"Unsafe component member: {name}")
            source = base / relative
            if not source.is_file() or source.is_symlink() or source.resolve() != source:
                raise ValueError(f"Not an ordinary component file: {source}")
            # Stable timestamps and explicit Git-style executable modes.
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            mode = 0o755 if source.stat().st_mode & stat.S_IXUSR else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            archive.writestr(info, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    info = inspect_component_zip(target)
    if info["artifact"] not in COMPONENTS or COMPONENTS[info["artifact"]] != component:
        raise ValueError(f"{component}: wrong component identity")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New output directory")
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if any(output.is_relative_to(ROOT / name) for name in COMPONENTS.values()):
        raise ValueError("Output must be outside the component directories")
    subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", "HEAD", "--", *COMPONENTS.values()], check=True)
    compare_normative_trees(ROOT / "norms", ROOT / "validator")
    output.mkdir(parents=True, exist_ok=False)
    staged = {name: ROOT / name for name in COMPONENTS.values()}
    archives = {artifact: output / f"{artifact}.zip" for artifact in COMPONENTS}
    for artifact, component in COMPONENTS.items():
        component_zip(ROOT, component, archives[artifact])
    versions = verify_version_set(archives, ROOT, allow_downgrade=False)
    with tempfile.TemporaryDirectory() as temp:
        sources = generate_readable_sources(Path(temp), staged, versions, archives)
        for name, source in sources.items():
            (output / name).write_bytes(source.read_bytes())
    # The receipt contains hashes of actual ZIP bytes, never estimates.
    receipt = json.loads((output / "WIKIDEBIA_SOURCE_PACKAGE_RECEIPT.json").read_text(encoding="utf-8"))
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
