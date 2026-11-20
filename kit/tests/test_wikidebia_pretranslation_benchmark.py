from __future__ import annotations

from pathlib import Path

import pytest

import wikidebia_pretranslation_benchmark as benchmark
from wikidebia_corpus_build import canonical_json


def test_benchmark_measures_three_local_resume_paths(tmp_path: Path):
    project_root = Path(__file__).resolve().parents[2]

    report = benchmark.run_benchmark(
        project_root,
        arguments=4,
        payload_bytes=64,
        iterations=1,
    )

    assert report["schema"] == benchmark.REPORT_SCHEMA
    assert report["fixture"]["arguments"] == 4
    assert report["fixture"]["kind"] == "synthetic"
    assert set(report["scenarios"]) == {
        "cold_build_validate_receipt",
        "resume_after_build_before_receipt",
        "resume_exact_verified_receipt",
    }
    assert report["quality_controls"] == {
        "same_build_contract": True,
        "cold_validation_passed": True,
        "interrupted_validation_passed": True,
        "exact_receipt_verified": True,
        "translation_logic_exercised": False,
        "wiki_access_performed": False,
        "real_snapshot_used": False,
    }
    assert report["billing"]["llm_calls_performed"] == 0
    assert report["billing"]["actual_billed_tokens"] is None
    assert report["billing"]["actual_codex_cloud_credits"] is None
    signed = dict(report)
    claimed = signed.pop("report_sha256")
    assert claimed == benchmark._sha256(canonical_json(signed))


@pytest.mark.parametrize(
    ("arguments", "payload_bytes", "iterations", "message"),
    [
        (1, 64, 1, "au moins deux arguments"),
        (2, 63, 1, "supérieur ou égal à 64"),
        (2, 64, 0, "iterations"),
    ],
)
def test_benchmark_rejects_non_representative_parameters(
    tmp_path: Path,
    arguments: int,
    payload_bytes: int,
    iterations: int,
    message: str,
):
    project_root = Path(__file__).resolve().parents[2]
    with pytest.raises(benchmark.PretranslationBenchmarkError, match=message):
        benchmark.run_benchmark(
            project_root,
            arguments=arguments,
            payload_bytes=payload_bytes,
            iterations=iterations,
        )


def test_benchmark_accepts_frozen_real_snapshot_without_modifying_it(tmp_path: Path):
    project_root = Path(__file__).resolve().parents[2]
    source = benchmark.make_synthetic_extraction(
        tmp_path / "real-extraction", arguments=5, payload_bytes=64,
    )
    before = benchmark._tree_metrics(source)

    report = benchmark.run_benchmark(
        project_root,
        arguments=250,
        payload_bytes=1024,
        iterations=1,
        snapshot=source / "snapshot",
    )

    assert report["fixture"]["kind"] == "snapshot"
    assert report["fixture"]["arguments"] == 5
    assert report["fixture"]["root_arguments"] == 5
    assert report["fixture"]["source"] == before
    assert report["quality_controls"]["real_snapshot_used"] is True
    assert report["quality_controls"]["wiki_access_performed"] is False
    assert benchmark._tree_metrics(source) == before


def test_benchmark_rejects_directory_without_snapshot_manifest(tmp_path: Path):
    project_root = Path(__file__).resolve().parents[2]
    with pytest.raises(benchmark.PretranslationBenchmarkError, match="extraction"):
        benchmark.run_benchmark(
            project_root,
            arguments=2,
            payload_bytes=64,
            iterations=1,
            snapshot=tmp_path,
        )


def test_snapshot_benchmark_output_cannot_modify_measured_extraction(tmp_path: Path):
    source = benchmark.make_synthetic_extraction(
        tmp_path / "real-extraction", arguments=5, payload_bytes=64,
    )
    with pytest.raises(benchmark.PretranslationBenchmarkError, match="modifier l’extraction"):
        benchmark._output_path(tmp_path, source / "benchmark-report.json", source)

    outside = benchmark._output_path(
        tmp_path, tmp_path / "reports/benchmark-report.json", source / "snapshot",
    )
    assert outside == (tmp_path / "reports/benchmark-report.json").resolve()


def test_stage_profiles_cover_each_resume_path(tmp_path: Path):
    project_root = Path(__file__).resolve().parents[2]
    report = benchmark.run_benchmark(
        project_root, arguments=4, payload_bytes=64, iterations=2,
    )
    scenarios = report["scenarios"]
    assert set(scenarios["cold_build_validate_receipt"]["stage_timings_seconds"]) == {
        "build_corpus", "initial_validator", "write_receipt",
    }
    assert set(scenarios["resume_after_build_before_receipt"]["stage_timings_seconds"]) == {
        "verify_source_contract", "inspect_unverified_build", "initial_validator",
        "write_receipt", "verify_written_receipt",
    }
    assert set(scenarios["resume_exact_verified_receipt"]["stage_timings_seconds"]) == {
        "verify_source_contract", "verify_build_receipt",
    }
    for scenario in scenarios.values():
        assert scenario["sample_count"] == 2
        assert scenario["population_stddev_seconds"] >= 0
        assert scenario["median_absolute_deviation_seconds"] >= 0
        for stage in scenario["stage_timings_seconds"].values():
            assert stage["sample_count"] == 2
            assert len(stage["samples_seconds"]) == 2
            assert stage["median_seconds"] >= 0
            assert stage["population_stddev_seconds"] >= 0


def test_benchmark_stage_measurement_rethrows_failure():
    expected = RuntimeError("stage failed")

    def fail():
        raise expected

    with pytest.raises(RuntimeError) as raised:
        benchmark._measure(fail)
    assert raised.value is expected


def test_opt_in_io_profile_counts_reads_and_hash_inputs_per_stage(tmp_path: Path):
    project_root = Path(__file__).resolve().parents[2]
    report = benchmark.run_benchmark(
        project_root, arguments=4, payload_bytes=64, iterations=1,
        profile_file_io=True,
    )
    profile = report["file_io_profile"]
    assert "subprocess" in " ".join(profile["limitations"])
    assert "Python parent process" in profile["scope"]
    assert set(profile["counters"]) == set(report["scenarios"])
    for scenario, row in profile["counters"].items():
        assert set(row) == set(report["scenarios"][scenario]["stage_timings_seconds"])
        for stage in row.values():
            assert set(stage) == set(benchmark.IO_METRICS)
            for metric in stage.values():
                assert metric["sample_count"] == 1
                assert len(metric["samples"]) == 1
                assert metric["samples"][0] >= 0
    cold = profile["counters"]["cold_build_validate_receipt"]["build_corpus"]
    assert cold["read_bytes_calls"]["median"] > 0
    assert cold["read_bytes_total_bytes"]["median"] > 0
    assert cold["kit_sha256_input_bytes"]["median"] > 0
    # The graph and snapshot are deliberately re-read after verification, to
    # prevent time-of-check/time-of-use acceptance of mutated source contents.
    assert cold["read_bytes_repeated_calls"]["median"] >= 2
    signed = dict(report)
    claimed = signed.pop("report_sha256")
    assert claimed == benchmark._sha256(canonical_json(signed))


def test_default_benchmark_does_not_install_io_telemetry(tmp_path: Path):
    project_root = Path(__file__).resolve().parents[2]
    report = benchmark.run_benchmark(
        project_root, arguments=4, payload_bytes=64, iterations=1,
    )
    assert "file_io_profile" not in report


def test_io_trace_counts_exact_successful_bytes_and_hash_inputs(tmp_path: Path):
    import wikidebia_corpus_init as corpus_init

    path = tmp_path / "source.txt"
    raw = "Écriture française".encode("utf-8")
    path.write_bytes(raw)
    with benchmark._profile_python_io() as counts:
        assert path.read_bytes() == raw
        assert path.read_bytes() == raw
        assert path.read_text(encoding="utf-8") == "Écriture française"
        assert corpus_init.sha256_bytes(raw) == benchmark._sha256(raw)
    assert counts["read_bytes_calls"] == 2
    assert counts["read_bytes_total_bytes"] == 2 * len(raw)
    assert counts["read_bytes_distinct_paths"] == 1
    assert counts["read_bytes_repeated_calls"] == 1
    assert counts["read_text_calls"] == 1
    assert counts["read_text_total_characters"] == len("Écriture française")
    assert counts["kit_sha256_calls"] == 1
    assert counts["kit_sha256_input_bytes"] == len(raw)


def test_io_trace_restores_path_methods_after_exception(tmp_path: Path):
    import wikidebia_corpus_init as corpus_init

    before_bytes = Path.read_bytes
    before_text = Path.read_text
    before_hash = corpus_init.sha256_bytes
    error = RuntimeError("benchmark operation failed")
    with pytest.raises(RuntimeError) as raised:
        with benchmark._profile_python_io():
            raise error
    assert raised.value is error
    assert Path.read_bytes is before_bytes
    assert Path.read_text is before_text
    assert corpus_init.sha256_bytes is before_hash


def test_io_trace_does_not_count_failed_reads(tmp_path: Path):
    with benchmark._profile_python_io() as counts:
        with pytest.raises(FileNotFoundError):
            (tmp_path / "missing.txt").read_bytes()
    assert all(value == 0 for value in counts.values())


def test_io_profile_count_summary_has_no_seconds_labels():
    assert benchmark._count_summary([2, 7, 3]) == {
        "sample_count": 3, "samples": [2, 7, 3],
        "median": 3, "minimum": 2, "maximum": 7,
    }


def test_cli_enables_io_profile_only_when_explicit():
    assert benchmark.build_parser().parse_args([]).profile_file_io is False
    assert benchmark.build_parser().parse_args(["--profile-file-io"]).profile_file_io is True
