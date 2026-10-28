#!/usr/bin/env python3
"""Regenerate validator package reports, manifest and signed receipt."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any


SELF_EXCLUDED = {"PACKAGE_MANIFEST_SHA256.json", "PACKAGE_RECEIPT.json"}
RUNTIME_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
RUNTIME_SUFFIXES = {".pyc", ".pyo"}


def canonical_sha256(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _replace_test_count(path: Path, pattern: str, replacement: str) -> None:
    import re

    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.M)
    if count != 1:
        raise RuntimeError(f"Compteur de tests introuvable dans {path}")
    path.write_text(updated, encoding="utf-8", newline="\n")


def _package_files(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        rel_text = rel.as_posix()
        if (
            rel_text in SELF_EXCLUDED
            or any(part in RUNTIME_DIRS for part in rel.parts)
            or path.suffix in RUNTIME_SUFFIXES
        ):
            continue
        raw = path.read_bytes()
        rows.append({
            "path": rel_text,
            "size_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
    return rows


def refresh(root: Path, *, test_count: int, generated_date: str) -> dict[str, Any]:
    root = root.resolve()
    versions = json.loads((root / "VERSIONS.json").read_text(encoding="utf-8"))
    _replace_test_count(
        root / "docs/TEST_REPORT.txt",
        r"^Tests pytest\s*:\s*\d+\s+réussis$",
        f"Tests pytest : {test_count} réussis",
    )
    _replace_test_count(
        root / "docs/SELF_AUDIT_REPORT.txt",
        r"^Tests\s*:\s*\d+\s+réussis$",
        f"Tests : {test_count} réussis",
    )

    rows = _package_files(root)
    manifest = {
        "artifact": "wikidebia-validator",
        "version": versions["validator"],
        "normative_revision": versions["norm"],
        "stable_archive_name": "wikidebia-validator.zip",
        "version_source": "VERSIONS.json",
        "declared_file_count": len(rows),
        "declared_test_count": test_count,
        "self_excluded": sorted(SELF_EXCLUDED),
        "files": rows,
    }
    manifest_path = root / "PACKAGE_MANIFEST_SHA256.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    receipt = {
        "artifact": "wikidebia-validator",
        "version": versions["validator"],
        "normative_revision": versions["norm"],
        "status": "passed",
        "declared_file_count": len(rows),
        "declared_test_count": test_count,
        "package_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "generated_date": generated_date,
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    (root / "PACKAGE_RECEIPT.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return {"manifest": manifest, "receipt": receipt}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--test-count", type=int, required=True)
    parser.add_argument(
        "--generated-date",
        default=dt.datetime.now(dt.timezone.utc).date().isoformat(),
    )
    args = parser.parse_args()
    if args.test_count < 1:
        parser.error("--test-count doit être positif")
    result = refresh(
        args.root, test_count=args.test_count, generated_date=args.generated_date,
    )
    print(json.dumps({
        "declared_file_count": result["manifest"]["declared_file_count"],
        "declared_test_count": result["manifest"]["declared_test_count"],
        "package_manifest_sha256": result["receipt"]["package_manifest_sha256"],
        "receipt_sha256": result["receipt"]["receipt_sha256"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
