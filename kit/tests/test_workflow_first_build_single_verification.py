"""A first corpus build must validate the extraction exactly once.

These regressions are strictly local; no translation or MediaWiki operations.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import wikidebia_corpus_init as corpus_init
import wikidebia_review_workflow as workflow
from wikidebia_pretranslation_benchmark import make_synthetic_extraction


DEBATE_ID = "benchmark_pretranslation"


def _source(tmp_path: Path, *, archive: bool = False) -> Path:
    root = make_synthetic_extraction(tmp_path / "source", arguments=6, payload_bytes=80)
    if not archive:
        return root
    target = tmp_path / "source.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for entry in sorted(root.rglob("*")):
            if entry.is_file():
                zf.write(entry, arcname=entry.relative_to(root).as_posix())
    return target


def _state(tmp_path: Path, source: Path) -> dict:
    return {
        "debate_id": DEBATE_ID,
        "short_code": None,
        "snapshot_path": source.relative_to(tmp_path).as_posix(),
    }


def _local_preflight(monkeypatch):
    monkeypatch.setattr(
        workflow, "_graph_translation_preflight",
        lambda _source: {"traduction_du_débat_requise": True},
    )
    monkeypatch.setattr(
        workflow, "_stop_for_existing_english_debate",
        lambda _project, _state, _metadata: False,
    )
    monkeypatch.setattr(workflow, "_save_workflow", lambda *_args: None)


@pytest.mark.parametrize("archive", [False, True])
def test_first_build_does_not_recompute_contract_but_records_verifiable_receipt(
    monkeypatch, tmp_path: Path, archive: bool,
):
    source = _source(tmp_path, archive=archive)
    state = _state(tmp_path, source)
    _local_preflight(monkeypatch)
    monkeypatch.setattr(
        workflow, "compute_build_contract",
        lambda *_a, **_k: pytest.fail("First build must not compute a redundant contract"),
    )
    monkeypatch.setattr(
        workflow, "run_initial_validator",
        lambda *_a: {"status": "passed"},
    )
    calls: list[str] = []
    actual_build = workflow.build_corpus

    def tracked_build(source_path, destination, **kwargs):
        calls.append("build")
        return actual_build(source_path, destination, **kwargs)

    monkeypatch.setattr(workflow, "build_corpus", tracked_build)
    workflow._initialize_graph_stage(tmp_path, state)

    output = tmp_path / ".state/corpus-builds" / DEBATE_ID
    attestation = state["initial_build_receipt"]
    inspection = corpus_init.inspect_existing_build(
        output,
        expected_debate_id=DEBATE_ID,
        expected_contract_sha256=attestation["build_contract_sha256"],
    )
    assert calls == ["build"]
    assert inspection["safe_to_reuse"] is True
    assert inspection["receipt_sha256"] == attestation["receipt_sha256"]
    assert state["phase"] == "graph_review"
    assert state["short_code"] == corpus_init.derive_short_code(DEBATE_ID)


def test_first_build_still_rejects_modified_extraction_without_creating_output(
    monkeypatch, tmp_path: Path,
):
    source = _source(tmp_path)
    broken = source / "snapshot/pages/arguments/a0001.wiki"
    broken.write_text("{{Argument|résumé=ALTÉRÉ}}\n", encoding="utf-8")
    _local_preflight(monkeypatch)
    monkeypatch.setattr(
        workflow, "compute_build_contract",
        lambda *_a, **_k: pytest.fail("No redundant preliminary contract"),
    )
    with pytest.raises(corpus_init.CorpusInitError, match="Empreinte invalide"):
        workflow._initialize_graph_stage(tmp_path, _state(tmp_path, source))
    assert not (tmp_path / ".state/corpus-builds" / DEBATE_ID).exists()


def test_existing_partial_build_still_requires_exact_snapshot_contract(
    monkeypatch, tmp_path: Path,
):
    source = _source(tmp_path)
    output = tmp_path / ".state/corpus-builds" / DEBATE_ID
    output.mkdir(parents=True)
    marker = output / "interrupted.marker"
    marker.write_text("do not overwrite", encoding="utf-8")
    _local_preflight(monkeypatch)
    computed: list[bool] = []
    original = workflow.compute_build_contract

    def counted(*args, **kwargs):
        computed.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(workflow, "compute_build_contract", counted)
    monkeypatch.setattr(
        workflow, "build_corpus",
        lambda *_args, **_kwargs: pytest.fail("An existing build must not be overwritten"),
    )
    with pytest.raises(workflow.WorkflowError, match="aucun écrasement automatique"):
        workflow._initialize_graph_stage(tmp_path, _state(tmp_path, source))
    assert computed == [True]
    assert marker.read_text(encoding="utf-8") == "do not overwrite"


def test_verified_existing_build_reuses_without_rebuilding(
    monkeypatch, tmp_path: Path,
):
    source = _source(tmp_path)
    output = tmp_path / ".state/corpus-builds" / DEBATE_ID
    result = corpus_init.build_corpus(
        source, output, debate_id=DEBATE_ID, short_code=None,
        scope_summary=None, overwrite=False,
    )
    receipt = corpus_init.write_build_receipt(
        output, build_contract=result["build_contract"], validation={"status": "passed"},
    )
    _local_preflight(monkeypatch)
    computed: list[bool] = []
    original = workflow.compute_build_contract

    def counted(*args, **kwargs):
        computed.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(workflow, "compute_build_contract", counted)
    monkeypatch.setattr(
        workflow, "build_corpus",
        lambda *_args, **_kwargs: pytest.fail("Matching receipt must be reused"),
    )
    monkeypatch.setattr(
        workflow, "run_initial_validator",
        lambda *_args: pytest.fail("A verified build must not be revalidated"),
    )
    state = _state(tmp_path, source)
    workflow._initialize_graph_stage(tmp_path, state)
    assert computed == [True]
    assert state["phase"] == "graph_review"
    assert state["initial_build_receipt"]["receipt_sha256"] == receipt["receipt_sha256"]
    assert state["short_code"] == corpus_init.derive_short_code(DEBATE_ID)
