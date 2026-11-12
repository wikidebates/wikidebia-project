import json
from pathlib import Path
from wikidebia_compact_index import compact_index, failure_report, junit_failure_report

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


def test_junit_report_is_structured_compact_and_omits_tracebacks(tmp_path):
    junit = tmp_path / "kit-tests.xml"
    junit.write_text("""<?xml version="1.0" encoding="utf-8"?>
<testsuite tests="3" failures="1" errors="1" skipped="1">
  <testcase classname="tests.test_auth" name="test_token=visible-secret">
    <failure type="AssertionError" message="Bearer fake-token-123 rejected">TRACEBACK_PRIVATE_VALUE_987</failure>
  </testcase>
  <testcase classname="tests.test_url" name="test_url">
    <error type="RuntimeError" message="https://fake-user:fake-pass@example.invalid/path">ANOTHER_PRIVATE_TRACE</error>
  </testcase>
  <testcase classname="tests.test_skip" name="test_skip"><skipped /></testcase>
</testsuite>
""", encoding="utf-8")

    report = junit_failure_report([junit])
    output = json.dumps(report)

    assert report["failure_count"] == 2
    assert report["sources"] == [{
        "source": "kit-tests.xml", "tests": 3, "failures": 1, "errors": 1, "skipped": 1,
    }]
    assert report["raw_tracebacks_included"] is False
    assert "TRACEBACK_PRIVATE_VALUE_987" not in output
    assert "ANOTHER_PRIVATE_TRACE" not in output
    assert "visible-secret" not in output
    assert "fake-token-123" not in output
    assert "fake-user:fake-pass" not in output


def test_junit_report_tolerates_missing_and_partial_sources(tmp_path):
    broken = tmp_path / "broken.xml"
    broken.write_text("<testsuite><testcase>", encoding="utf-8")
    report = junit_failure_report([tmp_path / "missing.xml", broken])
    assert report["missing_sources"] == ["missing.xml"]
    assert report["parse_errors"] == [{
        "source": "broken.xml", "error_type": "ParseError",
    }]
    assert report["failure_count"] == 0
