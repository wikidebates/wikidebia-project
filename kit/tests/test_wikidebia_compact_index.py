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
