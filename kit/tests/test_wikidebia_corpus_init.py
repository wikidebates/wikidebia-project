from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
MODULE_PATH = SCRIPTS / "wikidebia_corpus_init.py"
spec = importlib.util.spec_from_file_location("corpusinit", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def test_initial_validator_execution_uses_portable_report_paths(tmp_path, monkeypatch):
    project = tmp_path / "project"
    package = project / ".state/corpus-builds/debat_test"
    (project / "validator/src").mkdir(parents=True)
    script = project / "validator/scripts/wikidebia_validate.py"
    script.parent.mkdir(parents=True)
    script.write_text("# fixture\n", encoding="utf-8")
    (package / "reports").mkdir(parents=True)

    def fake_run(command, **kwargs):
        json_output = Path(command[command.index("--json-output") + 1])
        text_output = Path(command[command.index("--text-output") + 1])
        json_output.write_text('{"result":"passed"}\n', encoding="utf-8")
        text_output.write_text("passed\n", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    result = mod.run_validator(project, package)
    assert result["report_json"] == "reports/initial_validation.json"
    assert result["report_text"] == "reports/initial_validation.txt"
    execution = (package / "reports/initial_validation_execution.json").read_text(encoding="utf-8")
    assert str(tmp_path) not in execution


def _row(root: Path, title: str, rel: str, revision: int) -> dict:
    payload = (root / rel).read_bytes()
    return {
        "requested_title": title,
        "canonical_title": title,
        "relative_path": rel,
        "revision_id": revision,
        "revision_timestamp": "2026-08-03T00:00:00+00:00",
        "url": f"https://example.invalid/{title}",
        "redirect_chain": [],
        "fetched_at": "2026-08-03T00:00:00+00:00",
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def make_extraction(root: Path) -> Path:
    snapshot = root / "snapshot"
    args = snapshot / "pages" / "arguments"
    args.mkdir(parents=True)
    (snapshot / "pages" / "debate.wiki").write_text(
        "{{Débat|arguments-pour={{Argument pour|page=Argument A|titre-affiché=A soutient le débat}}"
        "|arguments-contre={{Argument contre|page=Argument B|titre-affiché=B contredit le débat}}"
        "|rubriques=Philosophie|mots-clés=test|date-création=2026-08-03}}",
        encoding="utf-8",
    )
    pages = {
        "a.wiki": "{{Argument|résumé=A|citations={{Citation|citation=La liberté consiste à vouloir ce que l'on veut.|auteurs=Harry G. Frankfurt|article=Freedom of the Will and the Concept of a Person|ouvrage=The Importance of What We Care About|page=11-25|date=25 juin 2012|avertissements-citation=Texte abrégé}}|justifications={{Justification|page=Argument C|titre-affiché=C soutient A}}|objections=|rubriques=Philosophie|mots-clés=test|date-création=2026-08-03}}",
        "b.wiki": "{{Argument|résumé=B|citations={{Citation|citation=Une cause suffisante n'est pas nécessairement une contrainte.|auteurs=Jane Doe|ouvrage=Original Work|date=juin 2012}}|justifications={{Justification|page=Argument C|titre-affiché=C soutient B}}|objections=|rubriques=Philosophie|mots-clés=test|date-création=2026-08-03}}",
        "c.wiki": "{{Argument|résumé=C|citations={{Citation|citation=Le raisonnement conserve sa portée dans ce cas.|auteurs=John Smith|article=An Original Article|date=1971}}|justifications=|objections=|rubriques=Philosophie|mots-clés=test|date-création=2026-08-03}}",
    }
    for name, text in pages.items():
        (args / name).write_text(text, encoding="utf-8")
    manifest = {
        "schema": "wikidebia-graph-snapshot-1.0",
        "kit_version": "2.15.56",
        "extractor_version": "1.0.0",
        "extraction_date": "2026-08-03",
        "debate": _row(snapshot, "Débat test", "pages/debate.wiki", 1),
        "arguments": [
            _row(snapshot, "Argument A", "pages/arguments/a.wiki", 2),
            _row(snapshot, "Argument B", "pages/arguments/b.wiki", 3),
            _row(snapshot, "Argument C", "pages/arguments/c.wiki", 4),
        ],
        "crawl_options": {},
        "counts": {"debate_pages": 1, "argument_pages": 3, "total_pages": 4},
    }
    (snapshot / "snapshot_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    graph = {
        "metadata": {
            "débat": "Débat test",
            "occurrences_argumentatives": 5,
            "frontières_débat_détaillé": {},
            "traduction_du_débat_requise": True,
            "traduction_anglaise_débat_vérifiée": False,
        },
        "arguments_pour_niveau_1": ["Argument A"],
        "arguments_contre_niveau_1": ["Argument B"],
        "noeuds": [
            {"titre": "Argument A", "titres_affichés_observés": ["A soutient le débat"]},
            {"titre": "Argument B", "titres_affichés_observés": ["B contredit le débat"]},
            {"titre": "Argument C", "titres_affichés_observés": ["C soutient A", "C soutient B"]},
        ],
        "relations": [
            {"source": "Argument A", "relation": "justification", "cible": "Argument C", "ordre": 1},
            {"source": "Argument B", "relation": "justification", "cible": "Argument C", "ordre": 1},
        ],
    }
    graph_path = root / "test_graphe_recursif_2026-08-03.json"
    graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    declared = []
    for path in sorted([graph_path, snapshot / "snapshot_manifest.json", snapshot / "pages/debate.wiki", *args.glob("*.wiki")]):
        payload = path.read_bytes()
        declared.append({
            "path": path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
        })
    package_manifest = {
        "schema": "wikidebia-graph-extraction-package-1.0",
        "kit_version": "2.15.56",
        "extractor_version": "1.0.0",
        "debate": "Débat test",
        "extraction_date": "2026-08-03",
        "audit_status": "passed",
        "declared_file_count": len(declared),
        "files": declared,
    }
    (root / "test_manifest_sha256_2026-08-03.json").write_text(
        json.dumps(package_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return root


def test_builds_graph_draft_and_preserves_imports(tmp_path: Path):
    source = make_extraction(tmp_path / "source")
    output = tmp_path / "build"
    result = mod.build_corpus(source, output, debate_id="debat_test", short_code="TEST", scope_summary=None, overwrite=False)
    assert result["status"] == "created"
    assert result["source_unfolded_occurrences"] == 5
    assert result["normative_occurrences"] == 4
    assert result["occurrences"] == 4
    assert "chemins" in result["occurrence_semantics"]
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    registry = json.loads((output / "data/registre_debat.json").read_text(encoding="utf-8"))
    assert manifest["global_status"] == "graph_draft"
    assert manifest["pages"] == []
    assert (output / "imports/fr/debate/debate.wiki").is_file()
    assert len(list((output / "imports/fr/arguments").glob("*.wiki"))) == 3
    assert not (output / "output/fr/debate/debate.wiki").exists()
    assert registry["graph"]["derived_counts"]["total_occurrences"] == 4
    secondary = [o for o in registry["graph"]["occurrences"] if o["occurrence_role"] == "secondary"]
    assert len(secondary) == 1 and secondary[0]["render_children"] is False


def test_existing_english_argument_is_registered_for_remote_reuse(tmp_path: Path):
    source = make_extraction(tmp_path / "source")
    graph_path = source / "test_graphe_recursif_2026-08-03.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    row = next(item for item in graph["noeuds"] if item["titre"] == "Argument C")
    row.update(
        {
            "traduction_anglaise_existante": "Existing argument C",
            "traduction_anglaise_existante_vérifiée": True,
            "traduction_anglaise_requise": False,
            "revision_traduction_anglaise_existante": 42,
            "vérification_traduction_anglaise_effectuée_le": "2026-08-03T12:00:00+00:00",
        }
    )
    graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path = source / "test_manifest_sha256_2026-08-03.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    graph_rel = graph_path.relative_to(source).as_posix()
    for item in manifest["files"]:
        if item["path"] == graph_rel:
            payload = graph_path.read_bytes()
            item.update(sha256=hashlib.sha256(payload).hexdigest(), size_bytes=len(payload))
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    output = tmp_path / "build"
    mod.build_corpus(source, output, debate_id="debat_test", short_code="TEST", scope_summary=None, overwrite=False)
    registry = json.loads((output / "data/registre_debat.json").read_text(encoding="utf-8"))
    node = next(item for item in registry["graph"]["nodes"] if item["fr"]["canonical_title"] == "Argument C")
    assert node["en"]["canonical_title"] == "Existing argument C"
    assert node["en"]["title_status"] == "locked"
    assert node["pages"]["en"]["wiki"]["check_status"] == "equivalent_existing"
    assert node["pages"]["en"]["wiki"]["decision"] == "reuse_existing"
    assert node["pages"]["en"]["generation"]["status"] == "obsolete"


def test_identifiers_are_deterministic(tmp_path: Path):
    source = make_extraction(tmp_path / "source")
    first = tmp_path / "first"
    second = tmp_path / "second"
    mod.build_corpus(source, first, debate_id="debat_test", short_code="TEST", scope_summary=None, overwrite=False)
    mod.build_corpus(source, second, debate_id="debat_test", short_code="TEST", scope_summary=None, overwrite=False)
    a = json.loads((first / "graph/graphe_argumentatif.json").read_text(encoding="utf-8"))
    b = json.loads((second / "graph/graphe_argumentatif.json").read_text(encoding="utf-8"))
    for graph in (a, b):
        graph["lifecycle"] = {"status": "draft", "validated_at": None, "locked_at": None, "locked_by_stage": None, "structural_sha256": None}
    assert a == b


def test_accepts_audited_zip(tmp_path: Path):
    source = make_extraction(tmp_path / "source")
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for path in source.rglob("*"):
            if path.is_file():
                bundle.write(path, path.relative_to(source).as_posix())
    result = mod.build_corpus(archive, tmp_path / "build", debate_id="debat_test", short_code="TEST", scope_summary=None, overwrite=False)
    assert result["imports"] == 4


def test_rejects_corrupted_snapshot_page(tmp_path: Path):
    source = make_extraction(tmp_path / "source")
    (source / "snapshot/pages/arguments/a.wiki").write_text("corrompu", encoding="utf-8")
    try:
        mod.build_corpus(source, tmp_path / "build", debate_id="debat_test", short_code="TEST", scope_summary=None, overwrite=False)
    except mod.CorpusInitError as exc:
        assert "Empreinte invalide" in str(exc)
    else:
        raise AssertionError("snapshot corrompu accepté")


def test_source_contains_no_mediawiki_write_call():
    source = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = ("page.save(", "page.put(", "page.delete(", "page.move(", "editpage(", "submit(")
    assert not [token for token in forbidden if token in source]

def test_rejects_tampered_graph_covered_by_package_manifest(tmp_path: Path):
    source = make_extraction(tmp_path / "source")
    graph_path = source / "test_graphe_recursif_2026-08-03.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    graph["relations"][0]["cible"] = "Argument B"
    graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        mod.build_corpus(source, tmp_path / "build", debate_id="debat_test", short_code="TEST", scope_summary=None, overwrite=False)
    except mod.CorpusInitError as exc:
        assert "Empreinte invalide dans le paquet d'extraction" in str(exc)
    else:
        raise AssertionError("graphe altéré accepté")


def test_rejects_zip_symlink_entry(tmp_path: Path):
    archive = tmp_path / "source.zip"
    info = zipfile.ZipInfo("snapshot/link")
    info.create_system = 3
    info.external_attr = (0o120777 << 16)
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(info, "target")
    try:
        mod.resolve_extraction_input(archive)
    except mod.CorpusInitError as exc:
        assert "Lien symbolique interdit" in str(exc)
    else:
        raise AssertionError("lien symbolique ZIP accepté")


def test_rejects_title_collision_after_normalization(tmp_path: Path):
    source = make_extraction(tmp_path / "source")
    graph_path = source / "test_graphe_recursif_2026-08-03.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    graph["noeuds"].append({"titre": "Argument A.", "titres_affichés_observés": []})
    graph["relations"].append({"source": "Argument B", "relation": "objection", "cible": "Argument A.", "ordre": 2})
    graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path = source / "test_manifest_sha256_2026-08-03.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for row in manifest["files"]:
        if row["path"] == graph_path.relative_to(source).as_posix():
            payload = graph_path.read_bytes()
            row["sha256"] = hashlib.sha256(payload).hexdigest()
            row["size_bytes"] = len(payload)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        mod.build_corpus(source, tmp_path / "build", debate_id="debat_test", short_code="TEST", scope_summary=None, overwrite=False)
    except mod.CorpusInitError as exc:
        assert "Collision de titres après normalisation" in str(exc)
    else:
        raise AssertionError("collision de titres acceptée")


def test_cli_rejects_output_outside_corpus_builds(tmp_path: Path):
    try:
        mod.assert_build_output_path(tmp_path / "corpus/debat", tmp_path)
    except mod.CorpusInitError as exc:
        assert "La sortie doit rester" in str(exc)
    else:
        raise AssertionError("sortie extérieure à .state/corpus-builds acceptée")



def test_default_short_code_is_derived_from_ascii_debate_id(tmp_path: Path):
    source = make_extraction(tmp_path / "source")
    result = mod.build_corpus(
        source,
        tmp_path / "build",
        debate_id="revenu_de_base",
        short_code=None,
        scope_summary=None,
        overwrite=False,
    )
    assert result["short_code"] == "RDB"


def test_short_code_derivation_never_reintroduces_title_accents():
    debate_id = mod.canonical_debate_id("Un revenu de base doit-il être instauré ?")
    assert debate_id == "un_revenu_de_base_doit_il_etre_instaure"
    code = mod.derive_short_code(debate_id)
    assert code == "URDBDIEI"
    assert code.isascii()
