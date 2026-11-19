"""In-call SHA reuse must never weaken signed build receipt validation."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import wikidebia_corpus_init as corpus_init


def verified_build(tmp_path: Path):
    root = tmp_path / "corpus"
    debate_id = "debat-test"
    files = {
        "manifest.json": {"debate_id": debate_id, "global_status": "graph_draft"},
        "scope.json": {"debate_id": debate_id},
        "data/registre_debat.json": {
            "debate": {"id": debate_id},
            "arguments": [{"id": f"A{i:04d}", "text": "x" * 300} for i in range(100)],
        },
        "data/import_provenance.json": {"pages": []},
        "graph/graphe_argumentatif.json": {"debate": {"id": debate_id}},
        "reports/initial_validation.json": {"status": "passed"},
    }
    for rel, doc in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(doc, ensure_ascii=False) + "\n", encoding="utf-8")
    contract = {
        "schema": corpus_init.BUILD_CONTRACT_SCHEMA,
        "corpus_init_version": corpus_init.CORPUS_INIT_VERSION,
        "kit_version": "test", "norm_version": "test", "validator_version": "test",
        "debate_id": debate_id, "short_code": "DT",
        "scope_summary": "Frozen synthetic test corpus",
        "source": {"schema": "synthetic", "sha256": "a" * 64},
    }
    corpus_init.write_build_contract_record(root, contract)
    corpus_init.write_build_receipt(
        root, build_contract=contract, validation={"status": "passed"},
    )
    return root, corpus_init.canonical_json_sha256(contract)


def inspection(root: Path, expected_sha: str):
    return corpus_init.inspect_existing_build(
        root, expected_debate_id="debat-test",
        expected_contract_sha256=expected_sha,
    )


def test_exact_resume_reads_manifest_and_registry_only_once(tmp_path: Path, monkeypatch):
    root, contract_sha = verified_build(tmp_path)
    original_read = Path.read_bytes
    counts = Counter()

    def tracked(path):
        if path == root / "manifest.json":
            counts["manifest"] += 1
        if path == root / "data/registre_debat.json":
            counts["registry"] += 1
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", tracked)
    result = inspection(root, contract_sha)
    assert result["status"] == "valid_and_matching"
    assert result["safe_to_reuse"] is True
    # Reading JSON and hashing its identical bytes happens in the same pass.
    assert counts == {"manifest": 1, "registry": 1}


def test_file_modified_between_json_read_and_tree_hash_is_rehashed(
    tmp_path: Path, monkeypatch,
):
    root, contract_sha = verified_build(tmp_path)
    target = root / "data/registre_debat.json"
    original_tree = corpus_init.build_tree_fingerprint
    original_sha = corpus_init.sha256_file
    rehashed = []

    def mutate_then_fingerprint(folder, *, _verified_digests=None):
        target.write_text('{"debate":{"id":"debat-test"},"tampered":true}\n', encoding="utf-8")
        return original_tree(folder, _verified_digests=_verified_digests)

    def tracked_sha(path):
        if path == target:
            rehashed.append(True)
        return original_sha(path)

    monkeypatch.setattr(corpus_init, "build_tree_fingerprint", mutate_then_fingerprint)
    monkeypatch.setattr(corpus_init, "sha256_file", tracked_sha)
    assert inspection(root, contract_sha) == {"status": "invalid", "safe_to_reuse": False}
    assert rehashed, "Changed registry must never use its old digest"


def test_manifest_modified_between_json_read_and_tree_hash_is_rejected(
    tmp_path: Path, monkeypatch,
):
    root, contract_sha = verified_build(tmp_path)
    target = root / "manifest.json"
    original_tree = corpus_init.build_tree_fingerprint

    def mutate_then_fingerprint(folder, *, _verified_digests=None):
        target.write_text('{"debate_id":"debat-test","extra":"changed"}\n', encoding="utf-8")
        return original_tree(folder, _verified_digests=_verified_digests)

    monkeypatch.setattr(corpus_init, "build_tree_fingerprint", mutate_then_fingerprint)
    assert inspection(root, contract_sha) == {"status": "invalid", "safe_to_reuse": False}


def test_file_modified_during_first_read_fails_closed(tmp_path: Path, monkeypatch):
    root, contract_sha = verified_build(tmp_path)
    target = root / "data/registre_debat.json"
    original_read = Path.read_bytes
    modified = []

    def mutate_after_read(path):
        data = original_read(path)
        if path == target and not modified:
            modified.append(True)
            target.write_text('{"debate":{"id":"debat-test"},"changed":true}\n', encoding="utf-8")
        return data

    monkeypatch.setattr(Path, "read_bytes", mutate_after_read)
    assert inspection(root, contract_sha) == {"status": "invalid", "safe_to_reuse": False}
    assert modified


def test_direct_receipt_verification_still_reads_all_files(tmp_path: Path, monkeypatch):
    root, contract_sha = verified_build(tmp_path)
    target = root / "data/registre_debat.json"
    original_read = Path.read_bytes
    seen = []

    def tracked(path):
        if path == target:
            seen.append(True)
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", tracked)
    result = corpus_init.verify_build_receipt(
        root, expected_contract_sha256=contract_sha,
    )
    assert result["safe_to_reuse"] is True
    assert seen == [True]
