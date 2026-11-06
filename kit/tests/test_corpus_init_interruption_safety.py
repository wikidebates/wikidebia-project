"""Interruption safety: an existing corpus is never silently replaced.

This regression test uses a synthetic extraction and does not touch translations.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import wikidebia_corpus_init as corpus_init


def test_existing_partial_build_is_preserved_without_overwrite(monkeypatch, tmp_path):
    output = tmp_path / "corpus"
    output.mkdir()
    marker = output / "interrupted-import.json"
    marker.write_text('{"progress": "partial"}\n', encoding="utf-8")
    original = marker.read_bytes()

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
