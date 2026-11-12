#!/usr/bin/env python3
"""Regenerate and verify the kit package manifest and signed receipt."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Mapping, Sequence


SELF_EXCLUDED = {"PACKAGE_MANIFEST_SHA256.json", "PACKAGE_RECEIPT.json"}
RUNTIME_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
RUNTIME_SUFFIXES = {".pyc", ".pyo"}
TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".toml", ".sh", ".yml", ".yaml"}


class PackageMetadataError(RuntimeError):
    pass


def assert_no_merge_conflict_markers(root: Path) -> None:
    marker = re.compile(
        rb"(?m)^(?:" + b"<" * 7 + rb" |" + b"=" * 7 + rb"$|" + b">" * 7 + rb" )"
    )
    conflicts = []
    for path in sorted(root.rglob("*")):
        if (
            not path.is_file()
            or path.suffix not in TEXT_SUFFIXES
            or any(part in RUNTIME_DIRS for part in path.relative_to(root).parts)
        ):
            continue
        if marker.search(path.read_bytes()):
            conflicts.append(path.relative_to(root).as_posix())
    if conflicts:
        raise PackageMetadataError(
            "Marqueurs de conflit Git présents : " + ", ".join(conflicts[:10])
        )


def passed_test_count(junit_xml: Path) -> int:
    try:
        root = ET.parse(junit_xml).getroot()
    except (ET.ParseError, OSError) as exc:
        raise PackageMetadataError(f"Rapport JUnit illisible : {exc}") from exc
    suites = [root] if root.get("tests") is not None else list(root.findall("./testsuite"))
    if not suites:
        raise PackageMetadataError("Compteurs absents du rapport JUnit")
    try:
        total = sum(int(row.get("tests", "0")) for row in suites)
        failures = sum(int(row.get("failures", "0")) for row in suites)
        errors = sum(int(row.get("errors", "0")) for row in suites)
        skipped = sum(int(row.get("skipped", "0")) for row in suites)
    except ValueError as exc:
        raise PackageMetadataError("Compteurs invalides dans le rapport JUnit") from exc
    passed = total - failures - errors - skipped
    if passed < 1 or failures or errors:
        raise PackageMetadataError(
            f"Suite JUnit non réussie : {passed} succès, {failures} échec(s), {errors} erreur(s)"
        )
    return passed


def canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _replace_once(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.M)
    if count != 1:
        raise PackageMetadataError(f"Champ {label} introuvable dans TEST_REPORT.txt")
    return updated


def _updated_report(raw: bytes, versions: Mapping[str, Any], test_count: int) -> bytes:
    text = raw.decode("utf-8")
    text = _replace_once(
        text,
        r"^Wikidéb’IA Kit\s+\S+\s+— rapport de tests$",
        f"Wikidéb’IA Kit {versions['kit']} — rapport de tests",
        "version du kit",
    )
    text = _replace_once(
        text, r"^Tests pytest\s*:\s*\d+\s+réussis$",
        f"Tests pytest : {test_count} réussis", "compteur de tests",
    )
    text = _replace_once(
        text, r"^Norme\s*:\s*\S+$", f"Norme : {versions['norm']}", "version de norme",
    )
    text = _replace_once(
        text, r"^Validateur\s*:\s*\S+$",
        f"Validateur : {versions['validator']}", "version du validateur",
    )
    return text.replace("\r\n", "\n").encode("utf-8")


def _package_files(root: Path, overrides: Mapping[str, bytes] | None = None) -> list[dict[str, Any]]:
    overrides = overrides or {}
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        relative_text = relative.as_posix()
        if (
            relative_text in SELF_EXCLUDED
            or any(part in RUNTIME_DIRS for part in relative.parts)
            or path.suffix in RUNTIME_SUFFIXES
        ):
            continue
        raw = overrides.get(relative_text, path.read_bytes())
        rows.append({
            "path": relative_text,
            "size_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
    return rows


def expected_metadata(
    root: Path, *, test_count: int, generated_date: str,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if test_count < 1:
        raise PackageMetadataError("Le compteur de tests doit être positif")
    assert_no_merge_conflict_markers(root)
    versions = json.loads((root / "VERSIONS.json").read_text(encoding="utf-8"))
    report_path = root / "TEST_REPORT.txt"
    report_raw = _updated_report(report_path.read_bytes(), versions, test_count)
    rows = _package_files(root, {"TEST_REPORT.txt": report_raw})
    manifest = {
        "artifact": "wikidebia-kit",
        "version": versions["kit"],
        "normative_revision": versions["norm"],
        "stable_archive_name": "wikidebia-kit.zip",
        "version_source": "VERSIONS.json",
        "declared_file_count": len(rows),
        "declared_test_count": test_count,
        "self_excluded": sorted(SELF_EXCLUDED),
        "files": rows,
    }
    manifest_raw = _json_bytes(manifest)
    receipt = {
        "artifact": "wikidebia-kit",
        "version": versions["kit"],
        "normative_revision": versions["norm"],
        "status": "passed",
        "declared_file_count": len(rows),
        "declared_test_count": test_count,
        "package_manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "generated_date": generated_date,
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    return {
        "report_raw": report_raw,
        "manifest": manifest,
        "manifest_raw": manifest_raw,
        "receipt": receipt,
        "receipt_raw": _json_bytes(receipt),
    }


def refresh(root: Path, *, test_count: int, generated_date: str) -> dict[str, Any]:
    root = root.expanduser().resolve()
    result = expected_metadata(root, test_count=test_count, generated_date=generated_date)
    _atomic_write(root / "TEST_REPORT.txt", result["report_raw"])
    _atomic_write(root / "PACKAGE_MANIFEST_SHA256.json", result["manifest_raw"])
    _atomic_write(root / "PACKAGE_RECEIPT.json", result["receipt_raw"])
    return result


def check(root: Path, *, test_count: int, generated_date: str) -> dict[str, Any]:
    root = root.expanduser().resolve()
    result = expected_metadata(root, test_count=test_count, generated_date=generated_date)
    expected = {
        "TEST_REPORT.txt": result["report_raw"],
        "PACKAGE_MANIFEST_SHA256.json": result["manifest_raw"],
        "PACKAGE_RECEIPT.json": result["receipt_raw"],
    }
    drift = [name for name, raw in expected.items() if not (root / name).is_file() or (root / name).read_bytes() != raw]
    if drift:
        raise PackageMetadataError("Métadonnées du kit périmées : " + ", ".join(drift))
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    count = parser.add_mutually_exclusive_group(required=True)
    count.add_argument("--test-count", type=int)
    count.add_argument("--junit-xml", type=Path)
    parser.add_argument("--generated-date")
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    test_count = args.test_count if args.test_count is not None else passed_test_count(args.junit_xml)
    generated_date = args.generated_date
    if generated_date is None and args.check:
        receipt_path = args.root / "PACKAGE_RECEIPT.json"
        if receipt_path.is_file():
            generated_date = json.loads(receipt_path.read_text(encoding="utf-8")).get("generated_date")
    generated_date = generated_date or dt.datetime.now(dt.timezone.utc).date().isoformat()
    result = (
        check(args.root, test_count=test_count, generated_date=generated_date)
        if args.check else
        refresh(args.root, test_count=test_count, generated_date=generated_date)
    )
    print(json.dumps({
        "status": "valid" if args.check else "refreshed",
        "declared_file_count": result["manifest"]["declared_file_count"],
        "declared_test_count": result["manifest"]["declared_test_count"],
        "package_manifest_sha256": result["receipt"]["package_manifest_sha256"],
        "receipt_sha256": result["receipt"]["receipt_sha256"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, PackageMetadataError) as exc:
        print(f"MÉTADONNÉES DU KIT BLOQUÉES : {exc}", file=os.sys.stderr)
        raise SystemExit(2)
