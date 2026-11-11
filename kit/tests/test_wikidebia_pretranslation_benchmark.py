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
