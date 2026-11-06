import json
from pathlib import Path
from wikidebia_compact_index import compact_index, failure_report

def test_index_is_deterministic_and_omits_state_and_secrets(tmp_path):
    (tmp_path / "kit").mkdir()
    (tmp_path / "kit/a.py").write_text("print('ok')")
    (tmp_path / ".state").mkdir()
    (tmp_path / ".state/secret.py").write_text("secret")
    (tmp_path / ".env").write_text("SECRET=123")
    a = compact_index(tmp_path)
    assert a == compact_index(tmp_path)
    assert [row["path"] for row in a["files"]] == ["kit/a.py"]
    assert "secret" not in json.dumps(a)

def test_failure_report_only_retains_failure_lines_and_redacts_tokens():
    report = failure_report("passed test\nFAILED test_a\ntoken=abc123\nE   password=hunter2\n")
    assert len(report["failure_lines"]) == 2
    assert "hunter2" not in json.dumps(report)
    assert "passed test" not in json.dumps(report)

def test_failure_report_redacts_authorization_and_url_credentials():
    report = failure_report(
        "FAILED test_auth Bearer fake-token-123\n"
        "E   Authorization: Basic ZmFrZTpmYWtl\n"
        "ERROR https://fake-user:fake-pass@example.invalid/path\n"
    )
    output = json.dumps(report)
    assert "fake-token-123" not in output
    assert "ZmFrZTpmYWtl" not in output
    assert "fake-user:fake-pass" not in output
    assert len(report["failure_lines"]) == 3

def test_atomic_output_preserves_existing_file_on_replace_failure(tmp_path, monkeypatch):
    import sys
    import wikidebia_compact_index as module
    output = tmp_path / "index.json"
    output.write_text("original")
    monkeypatch.setattr(sys, "argv", ["index", "--project-root", str(tmp_path), "--output", str(output)])
    def fail_replace(*args):
        raise OSError("simulated interruption")
    monkeypatch.setattr(module.os, "replace", fail_replace)
    import pytest
    with pytest.raises(OSError, match="simulated interruption"):
        module.main()
    assert output.read_text() == "original"
    assert not list(tmp_path.glob(".index-*"))
