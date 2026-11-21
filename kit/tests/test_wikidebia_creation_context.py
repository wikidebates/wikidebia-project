from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

import wikidebia_creation_context as cc
import wikidebia_manage as manager

ROOT = Path(__file__).resolve().parents[2]


def put(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@pytest.fixture
def project(tmp_path):
    for rel in ["norms/VERSIONS.json", "kit/configs/creation_context_sections.json"]:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, path)
    version = json.loads((ROOT / "norms/VERSIONS.json").read_text())["norm"]
    rel = f"norms/normative_reference/01_normes/WIKIDEBIA_NORME_CONSOLIDEE_{version}.md"
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / rel, path)
    return tmp_path


def norm_path(project):
    return next((project / "norms/normative_reference/01_normes").glob("WIKIDEBIA_NORME_CONSOLIDEE_*.md"))


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file() and ".state" not in p.relative_to(root).parts}


@pytest.mark.parametrize("stage", cc.STAGES)
def test_exact_excerpts_coverage_determinism_and_read_only_inputs(project, stage):
    before = snapshot(project)
    result = cc.build_creation_context(project, stage)
    target = project / result["context_path"]
    saved = json.loads((target / "CONTEXT_MANIFEST.json").read_text())
    prologue, sections = cc.split_sections(norm_path(project).read_bytes())
    coverage = saved["normative_selection"]["coverage"]
    assert len(coverage) == len(sections)
    expected = prologue + b"".join(section["raw"] for section, row in zip(sections, coverage) if row["included"])
    assert (target / "NORMATIVE_CONTEXT.md").read_bytes() == expected
    assert all(row["sha256"] == cc._sha(section["raw"]) for row, section in zip(coverage, sections))
    assert cc.build_creation_context(project, stage)["status"] == "reused"
    assert snapshot(project) == before
    assert result["measurement"]["actual_billed_tokens"] is None
    assert result["measurement"]["actual_codex_cloud_credits"] is None
    assert result["measurement"]["recommended_read_bytes"] == sum((target / row["path"]).stat().st_size for row in saved["files"])
    assert result["validation_performed"] is False
    assert result["remote_access_performed"] is False
    assert result["remote_write_performed"] is False


def test_section_parser_ignores_fenced_headings():
    raw = b"Title\n## First\n```markdown\n## Not a section\n```\n### Second\nKeep all bytes.\n"
    prologue, sections = cc.split_sections(raw)
    assert [s["heading"] for s in sections] == ["## First", "### Second"]
    assert prologue + b"".join(s["raw"] for s in sections) == raw


@pytest.mark.parametrize("change", ["append", "rename", "remove", "reorder"])
def test_unknown_or_changed_section_structure_fails_closed(project, change):
    path = norm_path(project)
    raw = path.read_bytes()
    prologue, parts = cc.split_sections(raw)
    if change == "append":
        raw += b"\n## Additional active rule\nA new obligation.\n"
    elif change == "rename":
        raw = raw.replace(parts[0]["heading"].encode(), b"## Renamed section", 1)
    elif change == "remove":
        raw = prologue + b"".join(s["raw"] for s in parts[1:])
    else:
        parts[0], parts[1] = parts[1], parts[0]
        raw = prologue + b"".join(s["raw"] for s in parts)
    path.write_bytes(raw)
    with pytest.raises(cc.CreationContextError, match="sections changed"):
        cc.build_creation_context(project, "arguments-fr")
    assert not (project / ".state").exists()


def test_changed_rule_content_creates_new_context(project):
    before = cc.build_creation_context(project, "arguments-fr")
    path = norm_path(project)
    raw = path.read_bytes().replace(b"## 1. ", b"## 1. ", 1)
    # Body change under a known selected heading is copied exactly, not cached.
    prologue, sections = cc.split_sections(raw)
    sections[0]["raw"] += b"Additional body text.\n"
    path.write_bytes(prologue + b"".join(s["raw"] for s in sections))
    after = cc.build_creation_context(project, "arguments-fr")
    assert before["context_sha256"] != after["context_sha256"]
    assert b"Additional body text." in (project / after["context_path"] / "NORMATIVE_CONTEXT.md").read_bytes()


@pytest.mark.parametrize("kind", ["body", "extra", "symlink"])
def test_existing_context_tampering_is_not_silently_overwritten(project, kind):
    result = cc.build_creation_context(project, "arguments-fr")
    target = project / result["context_path"]
    if kind == "body":
        (target / "NORMATIVE_CONTEXT.md").write_text("tampered")
    elif kind == "extra":
        (target / "unexpected.txt").write_text("unexpected")
    else:
        path = target / "INSTRUCTIONS.md"
        raw = path.read_bytes()
        other = project / "other.md"
        other.write_bytes(raw)
        path.unlink()
        path.symlink_to(other)
    with pytest.raises(cc.CreationContextError):
        cc.build_creation_context(project, "arguments-fr")


def test_output_parent_symlink_rejected(project, tmp_path):
    (project / ".state").symlink_to(project / "norms", target_is_directory=True)
    with pytest.raises(cc.CreationContextError, match="Symlink"):
        cc.build_creation_context(project, "graphe")


@pytest.mark.parametrize("bad", ["../private/secret.json", "/etc/passwd", "private/secret.json", "a\\b", "C:/test"])
def test_unsafe_corpus_path_rejected(project, bad):
    with pytest.raises(cc.CreationContextError):
        cc.build_creation_context(project, "arguments-fr", corpus_path=bad, node_ids=["A1"])


def fixture_corpus(project):
    corpus = project / "corpus/example"
    nodes = [{"id": f"A{i}", "status": "active", "fr": {"canonical_title": f"Reason {i}", "displayed_title": f"Context {i}"},
              "sources": {"fr": {"bibliography": ["S1"] if i == 1 else []}}} for i in range(1, 5)]
    pages = [{"page_id": node_id, "page_type": "debate" if node_id == "example" else "argument",
              "page_origin": "new", "language": "fr", "status": "generated",
              "file_path": f"output/fr/{node_id}.wiki", "sha256": cc._sha(node_id.encode())}
             for node_id in ["example", "A1", "A2", "A3", "A4"]]
    for row in pages:
        path = corpus / row["file_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(row["page_id"].encode())
    put(corpus / "manifest.json", {"debate_id": "example", "pages": pages,
                                   "core_files": {"scope": "scope.json", "registry": "data/registre_debat.json", "sources": "data/sources.json"}})
    put(corpus / "scope.json", {"debate_id": "example", "proposition_fr": "A well-scoped question"})
    put(corpus / "data/registre_debat.json", {
        "schema": {"registry_version": "1.0"}, "debate": {"id": "example", "pages": {"fr": {"canonical_title": "A question"}}},
        "graph": {"nodes": nodes, "edges": [{"id": "E1", "parent_node_id": "A1", "child_node_id": "A2", "relation": "objection"}],
                  "occurrences": [{"id": f"O{i}", "node_id": f"A{i}", "parent_occurrence_id": None,
                                   "displayed_title": f"Occurrence label {i}"} for i in range(1, 5)]},
        "batches": [{"id": "FR-A-001", "debate_id": "example", "language": "fr", "page_type": "argument",
                     "node_ids": ["A1"], "dependency_node_ids": ["A3"]}],
    })
    put(corpus / "data/sources.json", {"source_registry_version": "1.0", "debate_id": "example", "sources": [
        {"id": "S1", "equivalence_group": "G1", "language": "en", "metadata": {"title": "Original"},
         "usage": [{"page_id": "A1", "language": "fr", "argument_development_verified": True},
                   {"page_id": "A2", "language": "fr", "argument_development_verified": False}]},
        {"id": "S2", "equivalence_group": "G1", "language": "fr", "metadata": {"title": "French equivalent"}, "usage": []},
        {"id": "S3", "language": "fr", "usage": [{"page_id": "A4", "language": "fr"}]},
    ]})
    return corpus


def load_corpus_context(project, **kwargs):
    result = cc.build_creation_context(project, "arguments-fr", corpus_path="corpus/example", **kwargs)
    value = json.loads((project / result["context_path"] / "CORPUS_CONTEXT.json").read_text())
    return result, value


def test_target_batch_keeps_global_graph_direct_dependencies_and_source_equivalents(project):
    corpus = fixture_corpus(project)
    before = snapshot(corpus)
    result, value = load_corpus_context(project, batch_id="FR-A-001")
    assert value["selected_node_ids"] == ["A1"]
    assert value["dependency_node_ids"] == ["A2", "A3"]
    assert set(value["page_texts"]) == {"A1", "A2", "A3"}
    assert len(value["graph_overview"]["nodes"]) == 4
    assert value["graph_overview"]["occurrences"][0]["displayed_title"] == "Occurrence label 1"
    assert {s["id"] for s in value["sources"]} == {"S1", "S2"}
    assert len(value["sources"][0]["usage"]) == 2
    assert value["sources"][0]["usage"][1]["argument_development_verified"] is False
    assert value["editorial_validation_performed"] is False
    assert snapshot(corpus) == before
    assert load_corpus_context(project, batch_id="FR-A-001")[0]["status"] == "reused"
    assert result["status"] == "prepared"


def test_single_node_selection_does_not_read_unrelated_page_text(project):
    fixture_corpus(project)
    result, value = load_corpus_context(project, node_ids=["A1"])
    assert set(value["page_texts"]) == {"A1", "A2"}
    manifest = json.loads((project / result["context_path"] / "CONTEXT_MANIFEST.json").read_text())
    assert not any(row["path"].endswith("A4.wiki") for row in manifest["inputs"])


@pytest.mark.parametrize("kind", ["preexisting", "unknown", "imported", "foreign", "duplicate_node", "missing_source", "missing_page", "tampered_page", "core_symlink", "bad_core_path", "english_batch"])
def test_bad_corpus_fails_without_source_mutation(project, kind):
    corpus = fixture_corpus(project)
    path = corpus / "manifest.json"
    manifest = json.loads(path.read_text())
    registry_path = corpus / "data/registre_debat.json"
    registry = json.loads(registry_path.read_text())
    if kind == "preexisting": manifest["pages"][1]["page_origin"] = "preexisting"
    if kind == "unknown": manifest["pages"][0].pop("page_origin")
    if kind == "imported": put(corpus / "data/import_provenance.json", {})
    if kind == "foreign": registry["debate"]["id"] = "other"
    if kind == "duplicate_node": registry["graph"]["nodes"].append(registry["graph"]["nodes"][0])
    if kind == "missing_source": registry["graph"]["nodes"][0]["sources"]["fr"]["bibliography"] = ["absent"]
    if kind == "missing_page": (corpus / "output/fr/A1.wiki").unlink()
    if kind == "tampered_page": (corpus / "output/fr/A1.wiki").write_text("changed")
    if kind == "english_batch": registry["batches"][0]["language"] = "en"
    if kind == "bad_core_path": manifest["core_files"]["sources"] = "../../private/secret.json"
    put(path, manifest)
    put(registry_path, registry)
    if kind == "core_symlink":
        p = corpus / "data/sources.json"
        p.unlink()
        p.symlink_to(corpus / "scope.json")
    before = snapshot(corpus)
    with pytest.raises(cc.CreationContextError):
        load_corpus_context(project, batch_id="FR-A-001")
    assert snapshot(corpus) == before


def test_unknown_empty_duplicate_or_conflicting_selection_rejected(project):
    fixture_corpus(project)
    for kwargs in [{}, {"batch_id": "missing"}, {"node_ids": ["missing"]}, {"node_ids": ["A1", "A1"]},
                   {"batch_id": "FR-A-001", "node_ids": ["A1"]}]:
        with pytest.raises(cc.CreationContextError):
            load_corpus_context(project, **kwargs)


def test_registry_change_invalidates_derived_context(project):
    corpus = fixture_corpus(project)
    before, _ = load_corpus_context(project, node_ids=["A1"])
    path = corpus / "data/registre_debat.json"
    doc = json.loads(path.read_text())
    doc["graph"]["nodes"][3]["fr"]["canonical_title"] = "Changed distant branch"
    put(path, doc)
    after, _ = load_corpus_context(project, node_ids=["A1"])
    assert after["context_sha256"] != before["context_sha256"]


def test_real_manager_dispatch_and_error_handling(project, capsys):
    assert manager.main(["--root", str(project), "creation-context", "--stage", "graphe"]) == 0
    assert json.loads(capsys.readouterr().out)["stage"] == "graphe"
    assert cc.main(["--project-root", str(project), "--stage", "graphe", "--node-id", "A1"]) == 2
    assert "BLOQUE" in capsys.readouterr().err


def test_argument_stage_keeps_editorial_guards_and_defers_english_rendering(project):
    result = cc.build_creation_context(project, "arguments-fr")
    manifest = json.loads((project / result["context_path"] / "CONTEXT_MANIFEST.json").read_text())
    coverage = manifest["normative_selection"]["coverage"]
    included = {row["heading"].split(" ", 2)[1] for row in coverage if row["included"]}
    assert {"1.", "2.", "3.", "3.1", "4.", "4.1", "4.2", "5.", "5.0", "5.1", "5.2", "6.",
            "7.1", "7.2", "7.3", "7.4", "7.7", "7.8", "8.0", "8.2", "9.", "11.", "13.", "18.", "20.", "1.2.87"} <= included
    assert not {"8.3", "8.4", "17.", "19."} & included


def test_changed_input_between_read_and_save_is_rejected(project, monkeypatch):
    original = cc.Inputs.verify
    def mutate(self):
        path = norm_path(project)
        path.write_bytes(path.read_bytes() + b"changed after read\n")
        return original(self)
    monkeypatch.setattr(cc.Inputs, "verify", mutate)
    with pytest.raises(cc.CreationContextError, match="changed during"):
        cc.build_creation_context(project, "arguments-fr")
    assert not any((project / ".state").rglob("CONTEXT_MANIFEST.json"))
