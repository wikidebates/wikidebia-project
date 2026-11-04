from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "refresh_package_metadata.py"
spec = importlib.util.spec_from_file_location("refresh_kit_package_metadata", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def _fixture(root: Path) -> None:
    (root / "scripts").mkdir()
    (root / "tests").mkdir()
    (root / ".pytest_cache").mkdir()
    (root / "VERSIONS.json").write_text(
        json.dumps({"norm": "1.2.3", "validator": "0.4.5", "kit": "2.6.7"}) + "\n",
        encoding="utf-8",
    )
    (root / "TEST_REPORT.txt").write_text(
        "Wikidéb’IA Kit 2.0.0 — rapport de tests\n\n"
        "Tests pytest : 10 réussis\nNorme : 1.0.0\nValidateur : 0.1.0\n",
        encoding="utf-8",
    )
    (root / "scripts/tool.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / ".pytest_cache/runtime").write_text("ignored\n", encoding="utf-8")


def test_refresh_updates_report_manifest_and_signed_receipt(tmp_path: Path):
    _fixture(tmp_path)

    result = module.refresh(tmp_path, test_count=11, generated_date="2026-11-04")

    manifest = result["manifest"]
    receipt = result["receipt"]
    assert manifest["declared_test_count"] == 11
    assert {row["path"] for row in manifest["files"]} == {
        "TEST_REPORT.txt", "VERSIONS.json", "scripts/tool.py",
    }
    assert receipt["package_manifest_sha256"] == hashlib.sha256(
        (tmp_path / "PACKAGE_MANIFEST_SHA256.json").read_bytes()
    ).hexdigest()
    unsigned = dict(receipt)
    assert unsigned.pop("receipt_sha256") == module.canonical_sha256(unsigned)
    report = (tmp_path / "TEST_REPORT.txt").read_text(encoding="utf-8")
    assert "Kit 2.6.7" in report
    assert "Tests pytest : 11 réussis" in report
    assert "Norme : 1.2.3" in report
    assert "Validateur : 0.4.5" in report


def test_check_is_read_only_and_detects_drift(tmp_path: Path):
    _fixture(tmp_path)
    module.refresh(tmp_path, test_count=11, generated_date="2026-11-04")
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir() if path.is_file()}

    result = module.check(tmp_path, test_count=11, generated_date="2026-11-04")

    assert result["manifest"]["declared_test_count"] == 11
    assert before == {path.name: path.read_bytes() for path in tmp_path.iterdir() if path.is_file()}
    (tmp_path / "scripts/tool.py").write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(module.PackageMetadataError, match="périmées"):
        module.check(tmp_path, test_count=11, generated_date="2026-11-04")
