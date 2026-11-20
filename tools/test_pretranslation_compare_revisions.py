"""Regression tests for offline paired Git-revision pretranslation comparisons."""
from __future__ import annotations

import io
import json
import os
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import pretranslation_compare_revisions as compare


def _signed_report(*, contract="c" * 64, seconds=0.14, validated=True):
    scenario = {
        "sample_count": 1,
        "median_seconds": seconds,
        "stage_timings_seconds": {
            "build_corpus": {"median_seconds": seconds / 2},
        },
    }
    report = {
        "schema": "wikidebia-pretranslation-benchmark-1.0",
        "fixture": {
            "kind": "snapshot",
            "arguments": 4,
            "snapshot_manifest_sha256": "a" * 64,
            "build_contract_sha256": contract,
        },
        "scenarios": {key: dict(scenario) for key in compare.SCENARIOS},
        "quality_controls": {
            "same_build_contract": True,
            "cold_validation_passed": True,
            "interrupted_validation_passed": validated,
            "exact_receipt_verified": True,
            "translation_logic_exercised": False,
            "wiki_access_performed": False,
            "real_snapshot_used": True,
        },
    }
    report["report_sha256"] = compare._sha256(compare._canonical_json(report))
    return report


def _mock_snapshot(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / ".git").mkdir()
    source = project / ".state" / "graph-extract" / "example"
    (source / "snapshot").mkdir(parents=True)
    (source / "snapshot" / "snapshot_manifest.json").write_text("{}", encoding="utf-8")
    return project, source


def test_verified_individual_reports_reject_tampering_or_skipped_checks():
    good = _signed_report()
    assert compare._check_benchmark_report(good)["quality_controls"]["exact_receipt_verified"]

    bad = dict(good)
    bad["report_sha256"] = "f" * 64
    with pytest.raises(compare.RevisionComparisonError, match="Empreinte"):
        compare._check_benchmark_report(bad)

    unchecked = _signed_report(validated=False)
    with pytest.raises(compare.RevisionComparisonError, match="intégrité"):
        compare._check_benchmark_report(unchecked)

    unknown_fixture = _signed_report()
    unknown_fixture["fixture"]["kind"] = "synthetic"
    unknown_fixture["report_sha256"] = compare._sha256(
        compare._canonical_json({k: v for k, v in unknown_fixture.items() if k != "report_sha256"})
    )
    with pytest.raises(compare.RevisionComparisonError, match="hors-ligne"):
        compare._check_benchmark_report(unknown_fixture)


def test_revision_selectors_are_exact_or_head(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(compare, "_run_git", lambda repo, *args: "a" * 40)
    assert compare._resolve_revision(tmp_path, "HEAD") == "a" * 40
    assert compare._resolve_revision(tmp_path, "b" * 40) == "a" * 40
    for value in ("main", "origin/main", "HEAD~1", "--upload-pack=evil", "abc"):
        with pytest.raises(compare.RevisionComparisonError, match="HEAD ou un SHA"):
            compare._resolve_revision(tmp_path, value)


def test_snapshot_output_refuses_in_source_and_symlink(tmp_path: Path):
    project, source = _mock_snapshot(tmp_path)
    assert compare._snapshot_root(project, source / "snapshot") == source
    assert compare._snapshot_root(project, source) == source
    with pytest.raises(compare.RevisionComparisonError, match="dans l'extraction"):
        compare._output_path(project, source, source / "bench.json")
    with pytest.raises(compare.RevisionComparisonError, match="dans l'extraction"):
        compare._output_path(project, source, source / "snapshot" / "benchmark.json")
    outside = compare._output_path(project, source, Path(".state/benchmarks/comparison.json"))
    assert outside == project / ".state" / "benchmarks" / "comparison.json"
    alias = project / "linked-snapshot"
    alias.symlink_to(source, target_is_directory=True)
    with pytest.raises(compare.RevisionComparisonError, match="non symbolique"):
        compare._snapshot_root(project, alias)


def test_missing_snapshot_reports_actionable_path_instead_of_generic_symlink_error(tmp_path: Path):
    project, _ = _mock_snapshot(tmp_path)
    with pytest.raises(compare.RevisionComparisonError, match="Répertoire de snapshot introuvable.*--snapshot"):
        compare._snapshot_root(project, Path("/CHEMIN/VERS/L_EXTRACTION_FIGEE"))
    with pytest.raises(compare.RevisionComparisonError, match="Répertoire de snapshot introuvable"):
        compare._snapshot_root(project, Path("does-not-exist"))


def test_snapshot_zip_and_manifest_files_are_rejected_as_non_directories(tmp_path: Path):
    project, source = _mock_snapshot(tmp_path)
    archive = project / "extraction.zip"
    archive.write_bytes(b"not-an-extraction")
    for candidate in (archive, source / "snapshot" / "snapshot_manifest.json"):
        with pytest.raises(compare.RevisionComparisonError, match="pas un fichier ou une archive ZIP"):
            compare._snapshot_root(project, candidate)


def test_snapshot_cli_help_explains_real_directory_and_no_zip():
    help_text = compare.build_parser().format_help()
    assert "extraction figée" in help_text
    assert "ZIP" in help_text


def test_benchmark_process_environment_excludes_secrets_and_user_python_paths(
    tmp_path: Path, monkeypatch,
):
    monkeypatch.setenv("WIKIDEBIA_API_TOKEN", "dummy-secret-never-share")
    monkeypatch.setenv("WIKIDEBIA_FR_BOT_PASSWORD", "dummy-other-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-third-secret")
    monkeypatch.setenv("PYTHONPATH", "untrusted")
    monkeypatch.setenv("PYTHONHOME", "/fake/runtime")
    environment = compare._isolated_environment(tmp_path)
    assert "dummy-secret" not in repr(environment)
    assert "WIKIDEBIA_API_TOKEN" not in environment
    assert "WIKIDEBIA_FR_BOT_PASSWORD" not in environment
    assert "GITHUB_TOKEN" not in environment
    assert "PYTHONHOME" not in environment
    assert environment["PYTHONPATH"] == str(tmp_path / "kit/scripts")


def test_refuses_archive_entries_that_escape_target(tmp_path: Path, monkeypatch):
    def fake_run(*args, **kwargs):
        output = kwargs["stdout"]
        with tarfile.open(fileobj=output, mode="w") as archive:
            payload = b"danger"
            info = tarfile.TarInfo("../outside.txt")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(compare.subprocess, "run", fake_run)
    target = tmp_path / "checkout"
    with pytest.raises(compare.RevisionComparisonError, match="non sûr"):
        compare._materialize_revision(tmp_path, "c" * 40, target)
    assert not (tmp_path / "outside.txt").exists()


def test_refuses_archive_symlinks(tmp_path: Path, monkeypatch):
    def fake_run(*args, **kwargs):
        with tarfile.open(fileobj=kwargs["stdout"], mode="w") as archive:
            info = tarfile.TarInfo("private-key")
            info.type = tarfile.SYMTYPE
            info.linkname = "../../private"
            archive.addfile(info)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(compare.subprocess, "run", fake_run)
    with pytest.raises(compare.RevisionComparisonError, match="non sûr"):
        compare._materialize_revision(tmp_path, "d" * 40, tmp_path / "tree")
    assert not (tmp_path / "private-key").exists()


def test_rotated_runs_keep_exact_contracts_and_disclose_no_titles(tmp_path: Path, monkeypatch):
    project, source = _mock_snapshot(tmp_path)
    stages = []
    def fake_resolve(repo, revision):
        return {"HEAD": "b" * 40, compare.PARSER_BASELINE_SHA: "a" * 40}[revision]
    def fake_archive(repo, sha, target):
        (target / "kit/scripts").mkdir(parents=True)
        (target / compare.BENCHMARK_FILE).write_text("same benchmark", encoding="utf-8")
    def fake_run(tree, snapshot, python):
        stages.append(tree.name)
        return compare._check_benchmark_report(
            _signed_report(seconds=0.25 if tree.name == "baseline" else 0.13)
        )
    monkeypatch.setattr(compare, "_resolve_revision", fake_resolve)
    monkeypatch.setattr(compare, "_materialize_revision", fake_archive)
    monkeypatch.setattr(compare, "_fingerprint_built_corpus", lambda tree, snap, python:
                        ("c" * 64, {"manifest.json": "e" * 64}))
    monkeypatch.setattr(compare, "_run_revision", fake_run)
    result = compare.compare_revisions(project, source, iterations=3)
    assert stages == ["candidate", "baseline", "baseline", "candidate", "candidate", "baseline"]
    assert result["scenarios"]["cold_build_validate_receipt"]["change"]["elapsed_reduction_percent"] == 48.0
    assert result["quality_controls"]["identical_source_manifest_and_build_contract"]
    assert result["quality_controls"]["identical_built_file_sha256"]
    assert result["identical_built_file_count"] == 1
    assert result["iterations_per_revision"] == 3
    assert all(secret not in json.dumps(result) for secret in ("requested_title", "source_path", "dummy-secret"))
    unsigned = dict(result)
    assert unsigned.pop("report_sha256") == compare._sha256(compare._canonical_json(unsigned))


def test_contract_changed_between_passes_rejects_entire_comparison(tmp_path: Path, monkeypatch):
    project, source = _mock_snapshot(tmp_path)
    count = 0
    monkeypatch.setattr(compare, "_resolve_revision", lambda repo, rev: "a" * 40)
    def fake_archive(repo, sha, target):
        (target / "kit/scripts").mkdir(parents=True)
        (target / compare.BENCHMARK_FILE).write_text("same benchmark", encoding="utf-8")
    monkeypatch.setattr(compare, "_materialize_revision", fake_archive)
    monkeypatch.setattr(compare, "_fingerprint_built_corpus", lambda tree, snap, python:
                        ("c" * 64, {"manifest.json": "e" * 64}))
    def fake_run(tree, snapshot, python):
        nonlocal count
        count += 1
        contract = "c" * 64 if count == 1 else "d" * 64
        return compare._check_benchmark_report(_signed_report(contract=contract))
    monkeypatch.setattr(compare, "_run_revision", fake_run)
    with pytest.raises(compare.RevisionComparisonError, match="changé"):
        compare.compare_revisions(project, source, iterations=3)


def test_changed_corpus_files_abort_before_benchmark(tmp_path: Path, monkeypatch):
    project, source = _mock_snapshot(tmp_path)
    monkeypatch.setattr(compare, "_resolve_revision", lambda repo, rev: "a" * 40)
    def fake_archive(repo, sha, target):
        (target / "kit/scripts").mkdir(parents=True)
        (target / compare.BENCHMARK_FILE).write_text("same benchmark", encoding="utf-8")
    monkeypatch.setattr(compare, "_materialize_revision", fake_archive)
    monkeypatch.setattr(
        compare, "_fingerprint_built_corpus",
        lambda tree, snap, python: (
            "c" * 64,
            {"manifest.json": "1" * 64 if tree.name == "baseline" else "2" * 64},
        ),
    )
    def no_benchmark(*args, **kwargs):
        raise AssertionError("The benchmark must never run after built-file parity fails")
    monkeypatch.setattr(compare, "_run_revision", no_benchmark)
    with pytest.raises(compare.RevisionComparisonError, match="fichiers construits"):
        compare.compare_revisions(project, source, iterations=3)


def test_untrusted_fingerprint_report_is_not_accepted(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        compare.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout=json.dumps({
                "status": "created",
                "build_contract_sha256": "c" * 64,
                "files": {"unsafe": "non-sha256"},
            }),
        ),
    )
    with pytest.raises(compare.RevisionComparisonError, match="Preuve SHA-256"):
        compare._fingerprint_built_corpus(tmp_path, tmp_path, Path("/usr/bin/python3"))


@pytest.mark.parametrize("iterations", [0, 1, 2, 21])
def test_comparison_requires_repeated_measures(tmp_path: Path, iterations: int):
    with pytest.raises(compare.RevisionComparisonError, match="3 et 20"):
        compare.compare_revisions(tmp_path, tmp_path, iterations=iterations)


@pytest.mark.skipif(
    os.environ.get("WIKIDEBIA_COMPARE_INTEGRATION") != "1",
    reason="Full local Git history is required; exercised explicitly by offline CI workflow",
)
def test_real_git_archive_and_frozen_synthetic_snapshot_integration(tmp_path: Path):
    """Exercise the exact local-snapshot path without a real page or network."""
    import sys

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "kit/scripts"))
    from wikidebia_pretranslation_benchmark import make_synthetic_extraction

    extraction = make_synthetic_extraction(
        tmp_path / "frozen-source", arguments=4, payload_bytes=64,
    )
    before = {
        path.relative_to(extraction).as_posix(): compare._sha256(path.read_bytes())
        for path in extraction.rglob("*") if path.is_file()
    }
    result = compare.compare_revisions(
        root, extraction, baseline=compare.PARSER_BASELINE_SHA,
        candidate="HEAD", iterations=3,
    )
    assert result["quality_controls"]["signed_individual_reports_verified"]
    assert result["quality_controls"]["identical_source_manifest_and_build_contract"]
    assert result["quality_controls"]["identical_built_file_sha256"]
    assert result["identical_built_file_count"] > 0
    assert result["argument_count"] == 4
    assert all(len(result["scenarios"][key]["baseline"]["samples_seconds"]) == 3 for key in compare.SCENARIOS)
    after = {
        path.relative_to(extraction).as_posix(): compare._sha256(path.read_bytes())
        for path in extraction.rglob("*") if path.is_file()
    }
    assert before == after
