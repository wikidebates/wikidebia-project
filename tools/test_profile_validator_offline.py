"""Safety, report parity, and read-only tests for local validator profiling."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import profile_validator_offline as profile


def _frozen_snapshot(tmp_path: Path) -> Path:
    from wikidebia_pretranslation_benchmark import make_synthetic_extraction

    return make_synthetic_extraction(
        tmp_path / "frozen", arguments=4, payload_bytes=64,
    )


def test_complete_normalization_only_removes_runtime_attestation():
    raw = {
        "findings": [{"code": "WDV-DOC-001", "message": "keep"}],
        "scopes": ["schema", "coherence"],
        "metrics": {"runtime_attestation": {"cli_sha256": "a" * 64}, "graph": {"count": 2}},
    }
    result = profile._normalize_report(raw)
    assert result == {
        "findings": raw["findings"],
        "scopes": raw["scopes"],
        "metrics": {"graph": {"count": 2}},
    }
    assert raw["metrics"]["runtime_attestation"]["cli_sha256"] == "a" * 64


def test_environment_never_passes_credentials(monkeypatch):
    monkeypatch.setenv("WIKIDEBIA_API_TOKEN", "sensitive-placeholder")
    monkeypatch.setenv("WIKIDEBIA_FR_BOT_PASSWORD", "sensitive-placeholder")
    monkeypatch.setenv("GITHUB_TOKEN", "sensitive-placeholder")
    monkeypatch.setenv("PYTHONPATH", "/private/source")
    monkeypatch.setenv("PYTHONHOME", "/private/home")
    env = profile._isolated_env()
    assert not any(k in env for k in (
        "WIKIDEBIA_API_TOKEN", "WIKIDEBIA_FR_BOT_PASSWORD", "GITHUB_TOKEN",
        "PYTHONPATH", "PYTHONHOME",
    ))
    assert "sensitive-placeholder" not in repr(env)
    assert env["PYTHONNOUSERSITE"] == "1"


def test_snapshot_output_must_be_outside_and_not_symlink(tmp_path: Path):
    snapshot = tmp_path / "frozen"
    snapshot.mkdir()
    with pytest.raises(profile.ProfileError, match="extraction"):
        profile._output_path(snapshot, snapshot / "profile.json")
    elsewhere = tmp_path / "outside.json"
    assert profile._output_path(snapshot, elsewhere) == elsewhere
    alias = tmp_path / "alias.json"
    alias.symlink_to(elsewhere)
    with pytest.raises(profile.ProfileError, match="symbolique"):
        profile._output_path(snapshot, alias)


def test_source_digest_detects_changes_and_rejects_symlinks(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "page.wiki").write_text("{{Argument|résumé=Texte}}", encoding="utf-8")
    first = profile._source_digest(source)
    (source / "page.wiki").write_text("{{Argument|résumé=Texte changé}}", encoding="utf-8")
    assert profile._source_digest(source) != first
    (source / "alias.wiki").symlink_to(source / "page.wiki")
    with pytest.raises(profile.ProfileError, match="symbolique"):
        profile._source_digest(source)


@pytest.mark.parametrize("n,top", [(0, 10), (1, 10), (13, 10), (3, -1), (3, 51)])
def test_out_of_bounds_iterations_or_hotspots_rejected(tmp_path: Path, n: int, top: int):
    with pytest.raises(profile.ProfileError):
        profile.profile_snapshot(tmp_path, iterations=n, top=top)


def test_profile_has_real_complete_cli_and_direct_report_parity(tmp_path: Path):
    frozen = _frozen_snapshot(tmp_path)
    before = profile._source_digest(frozen)
    result = profile.profile_snapshot(frozen, iterations=2, top=5)
    assert result["schema"] == profile.REPORT_SCHEMA
    assert result["arguments"] == 4
    assert result["source_file_count"] == before[0]
    assert profile._source_digest(frozen) == before
    assert result["quality_controls"] == {
        "source_unchanged": True,
        "official_cli_attestation_verified": True,
        "complete_reports_equal": True,
        "schema_validation_not_skipped": True,
        "wiki_access_performed": False,
        "translation_logic_exercised": False,
        "real_source_exported": False,
    }
    assert len(result["validator_subprocess"]["samples_seconds"]) == 2
    assert len(result["validator_inprocess_instrumented"]["samples_seconds"]) == 2
    assert "scope:schema" in result["breakdown"]
    assert "method:SchemaStore.validate" in result["breakdown"]
    assert "schema:argument_registry.schema.json" in result["breakdown"]
    assert result["cprofile"]
    assert all("/" not in item["symbol"] for item in result["cprofile"])
    signed = dict(result)
    assert signed.pop("report_sha256") == profile._hash(signed)
    as_text = json.dumps(result, ensure_ascii=False)
    assert str(frozen) not in as_text
    assert "Argument synthétique" not in as_text
    assert "page.wiki" not in as_text


def test_detects_mutation_during_profiling_and_refuses_report(
    tmp_path: Path, monkeypatch,
):
    frozen = _frozen_snapshot(tmp_path)
    real = profile._source_digest
    calls = 0

    def fake_digest(source):
        nonlocal calls
        calls += 1
        n, digest = real(source)
        if calls > 1:
            return n, "f" * 64
        return n, digest

    monkeypatch.setattr(profile, "_source_digest", fake_digest)
    with pytest.raises(profile.ProfileError, match="changé"):
        profile.profile_snapshot(frozen, iterations=2, top=0)


def test_no_wiki_or_source_data_in_hotspot_names():
    class Stub:
        stats = {
            ("/home/username/private/validator.py", 42, "validate_package"):
                (1, 1, 0.0001, 0.0100, {}),
        }
    # cProfile.Stats is constructed against a real profile; test the
    # sanitization with a patched Stats provider.
    from unittest.mock import patch
    with patch.object(profile.pstats, "Stats", return_value=Stub()):
        rows = profile._safe_hotspots(object(), 10)
    assert rows == [{
        "symbol": "validator.py:42:validate_package", "calls": 1,
        "self_seconds": 0.0001, "cumulative_seconds": 0.01,
    }]
