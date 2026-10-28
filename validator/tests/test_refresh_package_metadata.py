from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "refresh_package_metadata.py"
spec = importlib.util.spec_from_file_location("refresh_package_metadata", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def test_refresh_updates_reports_manifest_and_signed_receipt(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "VERSIONS.json").write_text(
        json.dumps({"norm": "1.2.3", "validator": "0.4.5", "kit": "2.6.7"}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "docs/TEST_REPORT.txt").write_text(
        "Tests pytest : 10 réussis\n", encoding="utf-8",
    )
    (tmp_path / "docs/SELF_AUDIT_REPORT.txt").write_text(
        "Tests : 10 réussis\n", encoding="utf-8",
    )
    (tmp_path / "src/module.py").write_text("VALUE = 1\n", encoding="utf-8")

    result = module.refresh(tmp_path, test_count=11, generated_date="2026-10-28")

    manifest = result["manifest"]
    receipt = result["receipt"]
    assert manifest["declared_test_count"] == 11
    assert manifest["declared_file_count"] == len(manifest["files"])
    assert {row["path"] for row in manifest["files"]} == {
        "VERSIONS.json", "docs/SELF_AUDIT_REPORT.txt", "docs/TEST_REPORT.txt", "src/module.py",
    }
    assert receipt["package_manifest_sha256"] == hashlib.sha256(
        (tmp_path / "PACKAGE_MANIFEST_SHA256.json").read_bytes()
    ).hexdigest()
    body = dict(receipt)
    assert body.pop("receipt_sha256") == module.canonical_sha256(body)
    assert "Tests pytest : 11 réussis" in (tmp_path / "docs/TEST_REPORT.txt").read_text()
