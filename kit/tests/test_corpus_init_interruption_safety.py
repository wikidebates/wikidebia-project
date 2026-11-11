"""Interruption safety: an existing corpus is never silently replaced.

This regression test uses a synthetic extraction and does not touch translations.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import wikidebia_corpus_init as corpus_init


def _complete_build(output: Path, debate_id: str = "debat-test") -> None:
    values = {
        "manifest.json": {"debate_id": debate_id},
        "scope.json": {"debate_id": debate_id},
        "data/registre_debat.json": {"debate": {"id": debate_id}},
        "data/import_provenance.json": {"debate_id": debate_id},
        "graph/graphe_argumentatif.json": {"debate": {"id": debate_id}},
        "reports/initial_validation.json": {"status": "passed"},
    }
    for name, value in values.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def _contract(debate_id: str = "debat-test") -> dict:
    return {
        "schema": corpus_init.BUILD_CONTRACT_SCHEMA,
        "corpus_init_version": corpus_init.CORPUS_INIT_VERSION,
        "kit_version": "test",
        "norm_version": "test",
        "validator_version": "test",
        "debate_id": debate_id,
        "short_code": "TEST",
        "scope_summary": "Test",
        "source": {"schema": "test", "sha256": "1" * 64},
    }


def test_existing_partial_build_is_preserved_without_overwrite(monkeypatch, tmp_path):
    output = tmp_path / "corpus"
    output.mkdir()
    marker = output / "interrupted-import.json"
    marker.write_text('{"progress": "partial"}\n', encoding="utf-8")
    original = marker.read_bytes()

    source = tmp_path / "snapshot"
    source.mkdir()
    calls = []
    monkeypatch.setattr(
        corpus_init, "resolve_extraction_input",
        lambda _source: calls.append("resolve") or None,
    )

    with pytest.raises(corpus_init.CorpusInitError, match="existe déjà"):
        corpus_init.build_corpus(
            source, output,
            debate_id="debat-test",
            short_code=None,
            scope_summary=None,
            overwrite=False,
        )

    assert marker.read_bytes() == original
    assert sorted(path.name for path in output.iterdir()) == [marker.name]
    assert calls == []


@pytest.mark.parametrize("layout, expected", [
    ("missing", "absent"),
    ("partial", "incomplete"),
    ("broken", "invalid"),
    ("wrong_id", "mismatch"),
    ("matching_legacy", "unverified"),
])
def test_inspection_is_read_only(tmp_path, layout, expected):
    output = tmp_path / "corpus"
    if layout != "missing":
        output.mkdir()
        if layout != "partial":
            for name in (
                "manifest.json", "scope.json", "data/registre_debat.json",
                "data/import_provenance.json", "graph/graphe_argumentatif.json",
            ):
                path = output / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n", encoding="utf-8")
            if layout == "broken":
                (output / "manifest.json").write_text("{broken", encoding="utf-8")
            else:
                import json
                debate_id = "other" if layout == "wrong_id" else "debat-test"
                (output / "manifest.json").write_text(json.dumps({"debate_id": debate_id}), encoding="utf-8")
                (output / "data/registre_debat.json").write_text(
                    json.dumps({"debate": {"id": debate_id}}), encoding="utf-8"
                )
    before = {
        p.relative_to(output).as_posix(): p.read_bytes()
        for p in output.rglob("*") if p.is_file()
    } if output.exists() else {}
    result = corpus_init.inspect_existing_build(output, expected_debate_id="debat-test")
    after = {
        p.relative_to(output).as_posix(): p.read_bytes()
        for p in output.rglob("*") if p.is_file()
    } if output.exists() else {}
    assert result["status"] == expected
    assert result["safe_to_reuse"] is False
    assert after == before


def test_inspection_rejects_non_object_metadata(tmp_path):
    output = tmp_path / "corpus"
    for name in (
        "manifest.json", "scope.json", "data/registre_debat.json",
        "data/import_provenance.json", "graph/graphe_argumentatif.json",
    ):
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]", encoding="utf-8")
    result = corpus_init.inspect_existing_build(output, expected_debate_id="debat-test")
    assert result == {"status": "invalid", "safe_to_reuse": False}


def test_verified_receipt_allows_only_exact_contract_reuse(tmp_path):
    output = tmp_path / "corpus"
    _complete_build(output)
    contract = _contract()
    receipt = corpus_init.write_build_receipt(
        output,
        build_contract=contract,
        validation={"status": "passed"},
    )

    matching = corpus_init.inspect_existing_build(
        output,
        expected_debate_id="debat-test",
        expected_contract_sha256=corpus_init.canonical_json_sha256(contract),
    )
    stale = corpus_init.inspect_existing_build(
        output,
        expected_debate_id="debat-test",
        expected_contract_sha256="0" * 64,
    )

    assert matching == {
        "status": "valid_and_matching",
        "safe_to_reuse": True,
        "build_contract_sha256": receipt["build_contract_sha256"],
        "receipt_sha256": receipt["receipt_sha256"],
    }
    assert stale["status"] == "stale"
    assert stale["safe_to_reuse"] is False


def test_receipt_detects_build_changed_after_validation(tmp_path):
    output = tmp_path / "corpus"
    _complete_build(output)
    contract = _contract()
    corpus_init.write_build_receipt(
        output,
        build_contract=contract,
        validation={"status": "passed"},
    )
    (output / "scope.json").write_text('{"tampered": true}\n', encoding="utf-8")

    result = corpus_init.inspect_existing_build(
        output,
        expected_debate_id="debat-test",
        expected_contract_sha256=corpus_init.canonical_json_sha256(contract),
    )

    assert result == {"status": "invalid", "safe_to_reuse": False}


def test_failed_validation_cannot_create_receipt(tmp_path):
    output = tmp_path / "corpus"
    _complete_build(output)

    with pytest.raises(corpus_init.CorpusInitError, match="validation initiale réussie"):
        corpus_init.write_build_receipt(
            output,
            build_contract=_contract(),
            validation={"status": "failed"},
        )

    assert not (output / corpus_init.BUILD_RECEIPT_PATH).exists()


def test_inspection_rejects_symlinked_output(tmp_path):
    target = tmp_path / "real"
    target.mkdir()
    output = tmp_path / "linked"
    try:
        output.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    result = corpus_init.inspect_existing_build(output, expected_debate_id="debat-test")
    assert result == {"status": "invalid", "safe_to_reuse": False}
    assert target.is_dir()


def test_inspection_rejects_symlinked_required_directory(tmp_path):
    output = tmp_path / "corpus"
    output.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "registre_debat.json").write_text("{}\n", encoding="utf-8")
    try:
        (output / "data").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")

    result = corpus_init.inspect_existing_build(
        output,
        expected_debate_id="debat-test",
    )

    assert result == {"status": "invalid", "safe_to_reuse": False}


def test_build_rejects_symlink_even_with_overwrite(monkeypatch, tmp_path):
    target = tmp_path / "real"
    target.mkdir()
    marker = target / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    output = tmp_path / "linked"
    try:
        output.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    source = tmp_path / "snapshot"
    source.mkdir()
    monkeypatch.setattr(
        corpus_init, "resolve_extraction_input",
        lambda _source: corpus_init.ExtractionInput(
            root=source,
            graph_path=source / "graph.json",
            snapshot_manifest_path=source / "snapshot_manifest.json",
        ),
    )
    monkeypatch.setattr(
        corpus_init, "verify_extraction",
        lambda _input: (
            {"metadata": {"débat": "Un débat de test"}},
            {"debate": {"canonical_title": "Un débat de test"}},
        ),
    )
    with pytest.raises(corpus_init.CorpusInitError, match="lien symbolique"):
        corpus_init.build_corpus(
            source, output,
            debate_id="debat-test",
            short_code=None,
            scope_summary=None,
            overwrite=True,
        )
    assert marker.read_text(encoding="utf-8") == "keep"


def test_build_rejects_intermediate_symlink_before_reading_source(monkeypatch, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    linked_parent = tmp_path / "linked-parent"
    try:
        linked_parent.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    output = linked_parent / "corpus"
    source = tmp_path / "snapshot"
    source.mkdir()
    calls = []
    monkeypatch.setattr(
        corpus_init,
        "resolve_extraction_input",
        lambda _source: calls.append("resolve") or None,
    )

    with pytest.raises(corpus_init.CorpusInitError, match="lien symbolique"):
        corpus_init.build_corpus(
            source,
            output,
            debate_id="debat-test",
            short_code=None,
            scope_summary=None,
            overwrite=True,
        )

    assert calls == []
    assert list(outside.iterdir()) == []
