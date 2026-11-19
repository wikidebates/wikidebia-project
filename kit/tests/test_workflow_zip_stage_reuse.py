"""ZIP snapshots should be extracted once per graph stage and never trusted stale."""
from __future__ import annotations

import copy
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


def _archive(tmp_path: Path) -> tuple[Path, Path]:
    source = make_synthetic_extraction(tmp_path / "source", arguments=8, payload_bytes=80)
    archive = tmp_path / "snapshot.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for page in sorted(source.rglob("*")):
            if page.is_file():
                zf.write(page, arcname=page.relative_to(source).as_posix())
    return source, archive


def _state() -> dict:
    return {"debate_id": DEBATE_ID, "snapshot_path": "snapshot.zip", "short_code": None}


def _track_extraction(monkeypatch):
    real = corpus_init.safe_extract
    destinations = []

    def tracked(archive, destination):
        destinations.append(destination)
        return real(archive, destination)

    monkeypatch.setattr(corpus_init, "safe_extract", tracked)
    return destinations


def _setup(monkeypatch):
    monkeypatch.setattr(workflow, "_save_workflow", lambda *_args: None)


def _check_cleaned(destinations: list[Path]):
    assert len(destinations) == 1, "A ZIP must be extracted only once per stage"
    assert not destinations[0].exists(), "Temporary extracted ZIP must be cleaned"


def test_first_build_from_zip_extracts_once_then_verifies_signed_receipt(tmp_path: Path, monkeypatch):
    _, archive = _archive(tmp_path)
    dests = _track_extraction(monkeypatch)
    _setup(monkeypatch)
    monkeypatch.setattr(workflow, "run_initial_validator", lambda *_args: {"status": "passed"})
    state = _state()
    workflow._initialize_graph_stage(tmp_path, state)
    _check_cleaned(dests)
    assert state["snapshot_path"] == archive.name
    assert state["phase"] == "graph_review"
    output = tmp_path / ".state/corpus-builds" / DEBATE_ID
    assert corpus_init.inspect_existing_build(
        output, expected_debate_id=DEBATE_ID,
        expected_contract_sha256=state["initial_build_receipt"]["build_contract_sha256"],
    )["safe_to_reuse"] is True


def test_exact_verified_zip_resume_extracts_once_and_never_rebuilds(tmp_path: Path, monkeypatch):
    source, archive = _archive(tmp_path)
    output = tmp_path / ".state/corpus-builds" / DEBATE_ID
    initial = corpus_init.build_corpus(
        source, output, debate_id=DEBATE_ID, short_code=None,
        scope_summary=None, overwrite=False,
    )
    receipt = corpus_init.write_build_receipt(
        output, build_contract=initial["build_contract"], validation={"status": "passed"},
    )
    dests = _track_extraction(monkeypatch)
    _setup(monkeypatch)
    monkeypatch.setattr(
        workflow, "build_corpus",
        lambda *_args, **_kwargs: pytest.fail("Exact resume must not build"),
    )
    monkeypatch.setattr(
        workflow, "run_initial_validator",
        lambda *_args: pytest.fail("Verified receipt must not revalidate"),
    )
    state = _state()
    workflow._initialize_graph_stage(tmp_path, state)
    _check_cleaned(dests)
    assert state["snapshot_path"] == archive.name
    assert state["initial_build_receipt"]["receipt_sha256"] == receipt["receipt_sha256"]


def test_interrupted_zip_resume_extracts_once_and_revalidates(tmp_path: Path, monkeypatch):
    source, _ = _archive(tmp_path)
    output = tmp_path / ".state/corpus-builds" / DEBATE_ID
    initial = corpus_init.build_corpus(
        source, output, debate_id=DEBATE_ID, short_code=None,
        scope_summary=None, overwrite=False,
    )
    dests = _track_extraction(monkeypatch)
    _setup(monkeypatch)
    validations = []
    monkeypatch.setattr(
        workflow, "run_initial_validator",
        lambda *_args: validations.append(True) or {"status": "passed"},
    )
    monkeypatch.setattr(
        workflow, "build_corpus",
        lambda *_args, **_kwargs: pytest.fail("Partial build must not be overwritten"),
    )
    state = _state()
    workflow._initialize_graph_stage(tmp_path, state)
    _check_cleaned(dests)
    assert validations == [True]
    assert state["initial_build_receipt"]["build_contract_sha256"] == initial["build_contract_sha256"]
    assert corpus_init.inspect_existing_build(
        output, expected_debate_id=DEBATE_ID,
        expected_contract_sha256=initial["build_contract_sha256"],
    )["safe_to_reuse"] is True


def test_zip_extraction_is_cleaned_when_preflight_blocks(tmp_path: Path, monkeypatch):
    _archive(tmp_path)
    dests = _track_extraction(monkeypatch)
    _setup(monkeypatch)
    state = _state()
    before = copy.deepcopy(state)
    monkeypatch.setattr(
        workflow, "_graph_translation_preflight",
        lambda *_args: (_ for _ in ()).throw(workflow.WorkflowError("Blocked preflight")),
    )
    with pytest.raises(workflow.WorkflowError, match="Blocked preflight"):
        workflow._initialize_graph_stage(tmp_path, state)
    _check_cleaned(dests)
    assert state == before


def test_zip_mutation_during_stage_restores_state_and_blocks_reuse(tmp_path: Path, monkeypatch):
    _archive(tmp_path)
    dests = _track_extraction(monkeypatch)
    _setup(monkeypatch)
    state = _state()
    before = copy.deepcopy(state)
    original = workflow._graph_translation_preflight

    def mutate_zip_after_extract(source):
        metadata = original(source)
        # Change the ZIP metadata without touching the verified extracted
        # contents. The original archive must still be treated as changed.
        archive = tmp_path / "snapshot.zip"
        with zipfile.ZipFile(archive, "a") as zf:
            zf.comment = b"changed-during-stage"
        return metadata

    monkeypatch.setattr(workflow, "_graph_translation_preflight", mutate_zip_after_extract)
    monkeypatch.setattr(workflow, "run_initial_validator", lambda *_args: {"status": "passed"})
    with pytest.raises(workflow.WorkflowError, match="Snapshot ZIP modifié"):
        workflow._initialize_graph_stage(tmp_path, state)
    _check_cleaned(dests)
    assert state == before
    # The build, if present, must not be reused without comparing it to the
    # *current* ZIP-derived contract on the next workflow invocation.
    if (tmp_path / ".state/corpus-builds" / DEBATE_ID).exists():
        assert (tmp_path / ".state/corpus-builds" / DEBATE_ID / "reports/corpus_build_receipt.json").is_file()


def test_non_zip_directory_path_does_not_allocate_temporary_extraction(tmp_path: Path, monkeypatch):
    source, _ = _archive(tmp_path)
    dests = _track_extraction(monkeypatch)
    _setup(monkeypatch)
    monkeypatch.setattr(workflow, "run_initial_validator", lambda *_args: {"status": "passed"})
    state = _state()
    state["snapshot_path"] = source.relative_to(tmp_path).as_posix()
    workflow._initialize_graph_stage(tmp_path, state)
    assert dests == []
    assert state["phase"] == "graph_review"


@pytest.mark.parametrize("failure", ["corrupt_zip", "missing_graph"])
def test_resolve_extraction_cleans_tempdir_when_zip_cannot_be_used(
    tmp_path: Path, monkeypatch, failure: str,
):
    archive = tmp_path / "invalid.zip"
    if failure == "corrupt_zip":
        archive.write_bytes(b"not a valid zip")
    else:
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("snapshot/snapshot_manifest.json", '{"schema": "test"}')
    created = []
    actual_mkdtemp = corpus_init.tempfile.mkdtemp

    def recorded(*args, **kwargs):
        path = Path(actual_mkdtemp(*args, **kwargs))
        created.append(path)
        return str(path)

    monkeypatch.setattr(corpus_init.tempfile, "mkdtemp", recorded)
    with pytest.raises(corpus_init.CorpusInitError):
        corpus_init.resolve_extraction_input(archive)
    assert len(created) == 1
    assert not created[0].exists()
