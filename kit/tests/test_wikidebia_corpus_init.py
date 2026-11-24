from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import zipfile
import pytest
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
        "|rubriques=Philosophie|mots-clés=test}}",
        encoding="utf-8",
    )
    pages = {
        "a.wiki": "{{Argument|résumé=A|citations={{Citation|citation=La liberté consiste à vouloir ce que l'on veut.|auteurs=Harry G. Frankfurt|article=Freedom of the Will and the Concept of a Person|ouvrage=The Importance of What We Care About|page=11-25|date=25 juin 2012|avertissements-citation=Texte abrégé}}|justifications={{Justification|page=Argument C|titre-affiché=C soutient A}}|objections=|rubriques=Philosophie|mots-clés=test}}",
        "b.wiki": "{{Argument|résumé=B|citations={{Citation|citation=Une cause suffisante n'est pas nécessairement une contrainte.|auteurs=Jane Doe|ouvrage=Original Work|date=juin 2012}}|justifications={{Justification|page=Argument C|titre-affiché=C soutient B}}|objections=|rubriques=Philosophie|mots-clés=test}}",
        "c.wiki": "{{Argument|résumé=C|citations={{Citation|citation=Le raisonnement conserve sa portée dans ce cas.|auteurs=John Smith|article=An Original Article|date=1971}}|justifications=|objections=|rubriques=Philosophie|mots-clés=test}}",
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
    expected_contract = mod.compute_build_contract(
        source,
        debate_id="debat_test",
        short_code="TEST",
        scope_summary=None,
    )
    result = mod.build_corpus(source, output, debate_id="debat_test", short_code="TEST", scope_summary=None, overwrite=False)
    assert result["status"] == "created"
    assert result["build_contract"] == expected_contract
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


def test_cli_writes_verifiable_receipt_after_validation(tmp_path: Path, monkeypatch, capsys):
    project = tmp_path / "project"
    source = make_extraction(tmp_path / "source")
    output = project / ".state/corpus-builds/debat_test"
    monkeypatch.setattr(mod, "run_validator", lambda *_args: {"status": "passed"})

    result_code = mod.main([
        str(source),
        "--output-dir", str(output),
        "--debate-id", "debat_test",
        "--short-code", "TEST",
        "--project-root", str(project),
        "--machine-readable",
    ])

    result = json.loads(capsys.readouterr().out)
    assert result_code == 0
    assert result["build_receipt"]["path"] == mod.BUILD_RECEIPT_PATH.as_posix()
    inspected = mod.inspect_existing_build(
        output,
        expected_debate_id="debat_test",
        expected_contract_sha256=result["build_contract_sha256"],
    )
    assert inspected["status"] == "valid_and_matching"
    assert inspected["safe_to_reuse"] is True


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


def test_extraction_reuses_snapshot_page_digests_within_one_verification(tmp_path: Path, monkeypatch):
    source = make_extraction(tmp_path / "source")
    original_read = Path.read_bytes
    read_counts = {}

    def counted_read(path):
        if path.suffix == ".wiki":
            read_counts[path.resolve()] = read_counts.get(path.resolve(), 0) + 1
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", counted_read)
    inp = mod.resolve_extraction_input(source)
    graph, snapshot = mod.verify_extraction(inp)

    assert graph["metadata"]["débat"] == "Débat test"
    assert len(snapshot["arguments"]) == 3
    assert len(read_counts) == 4
    assert set(read_counts.values()) == {1}


def test_extraction_invalidates_digest_if_page_changes_between_manifests(tmp_path: Path, monkeypatch):
    source = make_extraction(tmp_path / "source")
    victim = source / "snapshot/pages/arguments/a.wiki"
    package_manifest = source / "test_manifest_sha256_2026-08-03.json"
    original_read_text = Path.read_text
    changed = False

    def changed_on_manifest(path, *args, **kwargs):
        nonlocal changed
        if path == package_manifest and not changed:
            changed = True
            victim.write_bytes(b"altered after first verification")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", changed_on_manifest)
    inp = mod.resolve_extraction_input(source)
    try:
        mod.verify_extraction(inp)
    except mod.CorpusInitError as exc:
        assert "Taille invalide" in str(exc) or "Empreinte invalide" in str(exc)
    else:
        raise AssertionError("Une page modifiée entre les manifestes a été acceptée")


def test_import_rejects_source_modified_after_manifest_verification(tmp_path: Path):
    source = make_extraction(tmp_path / "source")
    inp = mod.resolve_extraction_input(source)
    _, snapshot = mod.verify_extraction(inp)
    victim = source / "snapshot/pages/arguments/a.wiki"
    victim.write_bytes(b"modified after verified source was accepted")

    ids = {row["canonical_title"]: f"A{i:04d}" for i, row in enumerate(snapshot["arguments"], 1)}
    target_root = tmp_path / "build"
    try:
        mod.copy_import_pages(inp, snapshot, target_root, ids)
    except mod.CorpusInitError as exc:
        assert "modifiée entre la vérification et l'import" in str(exc)
    else:
        raise AssertionError("La page altérée après vérification a été importée")
    assert not (target_root / "imports/fr/arguments/A0001.wiki").exists()


def test_import_uses_exact_verified_bytes_even_if_source_changes_during_copy(tmp_path: Path, monkeypatch):
    source = make_extraction(tmp_path / "source")
    inp = mod.resolve_extraction_input(source)
    _, snapshot = mod.verify_extraction(inp)
    victim = source / "snapshot/pages/arguments/a.wiki"
    original_read = Path.read_bytes
    modified = False

    def mutate_after_read(path):
        nonlocal modified
        payload = original_read(path)
        if path == victim and not modified:
            modified = True
            victim.write_bytes(b"tampered after original bytes were read")
        return payload

    monkeypatch.setattr(Path, "read_bytes", mutate_after_read)
    ids = {row["canonical_title"]: f"A{i:04d}" for i, row in enumerate(snapshot["arguments"], 1)}
    output = tmp_path / "build"
    metadata, provenance = mod.copy_import_pages(inp, snapshot, output, ids)
    imported = output / "imports/fr/arguments/A0001.wiki"
    verified_payload = imported.read_bytes()
    assert modified
    assert hashlib.sha256(verified_payload).hexdigest() == snapshot["arguments"][0]["sha256"]
    assert verified_payload != victim.read_bytes()
    assert "Argument A" in metadata
    assert any(row.get("page_id") == "A0001" and row.get("sha256") == snapshot["arguments"][0]["sha256"]
               for row in provenance["provenance"]["pages"])


def test_import_does_not_reread_copied_target_for_metadata(tmp_path: Path, monkeypatch):
    source = make_extraction(tmp_path / "source")
    inp = mod.resolve_extraction_input(source)
    _, snapshot = mod.verify_extraction(inp)
    ids = {row["canonical_title"]: f"A{i:04d}" for i, row in enumerate(snapshot["arguments"], 1)}
    output = tmp_path / "build"
    previous_read_text = Path.read_text

    def forbid_target_read(path, *args, **kwargs):
        if output in path.parents:
            raise AssertionError("Imported page should be parsed from verified source bytes")
        return previous_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", forbid_target_read)
    metadata, provenance = mod.copy_import_pages(inp, snapshot, output, ids)
    assert len(metadata) == 3
    assert len(provenance["provenance"]["pages"]) == 4


def _rewrite_snapshot_page_path(source: Path, relative: str, payload: bytes) -> None:
    """Produce a consistently SHA-audited manifest with a chosen page locator."""
    snapshot_path = source / "snapshot/snapshot_manifest.json"
    manifest = json.loads(snapshot_path.read_text(encoding="utf-8"))
    manifest["arguments"][0]["relative_path"] = relative
    manifest["arguments"][0]["sha256"] = hashlib.sha256(payload).hexdigest()
    manifest["arguments"][0]["size_bytes"] = len(payload)
    snapshot_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    audit_path = source / "test_manifest_sha256_2026-08-03.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    snapshot_payload = snapshot_path.read_bytes()
    for row in audit["files"]:
        if row["path"] == "snapshot/snapshot_manifest.json":
            row["sha256"] = hashlib.sha256(snapshot_payload).hexdigest()
            row["size_bytes"] = len(snapshot_payload)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@pytest.mark.parametrize("kind", ("traversal", "absolute", "backslash"))
def test_snapshot_rejects_unportable_and_outside_page_paths(tmp_path: Path, kind: str):
    source = make_extraction(tmp_path / "source")
    outside = tmp_path / "outside.wiki"
    outside.write_text("{{Argument|résumé=Outside snapshot}}\n", encoding="utf-8")
    relative = {
        "traversal": "../../outside.wiki",
        "absolute": outside.as_posix(),
        "backslash": "pages\\arguments\\a.wiki",
    }[kind]
    _rewrite_snapshot_page_path(source, relative, outside.read_bytes())
    inp = mod.resolve_extraction_input(source)
    with pytest.raises(mod.CorpusInitError, match="Chemin de page invalide"):
        mod.verify_extraction(inp)


def test_snapshot_rejects_symlink_page_outside_root_even_without_audit_manifest(tmp_path: Path):
    source = make_extraction(tmp_path / "source")
    victim = source / "snapshot/pages/arguments/a.wiki"
    outside = tmp_path / "outside.wiki"
    outside.write_bytes(victim.read_bytes())
    victim.unlink()
    victim.symlink_to(outside)
    (source / "test_manifest_sha256_2026-08-03.json").unlink()
    with pytest.raises(mod.CorpusInitError, match="extérieure à son dossier"):
        mod.verify_extraction(mod.resolve_extraction_input(source))


def test_extraction_rejects_symlink_graph_outside_source_tree(tmp_path: Path):
    source = make_extraction(tmp_path / "source")
    graph = source / "test_graphe_recursif_2026-08-03.json"
    outside = tmp_path / "other-graph.json"
    graph.rename(outside)
    graph.symlink_to(outside)
    with pytest.raises(mod.CorpusInitError, match="Fichier d'extraction extérieur"):
        mod.verify_extraction(mod.resolve_extraction_input(source))


def test_extraction_rejects_symlink_audit_manifest_outside_source_tree(tmp_path: Path):
    source = make_extraction(tmp_path / "source")
    audit = source / "test_manifest_sha256_2026-08-03.json"
    outside = tmp_path / "outside-manifest.json"
    audit.rename(outside)
    audit.symlink_to(outside)
    with pytest.raises(mod.CorpusInitError, match="Manifeste d'extraction extérieur"):
        mod.verify_extraction(mod.resolve_extraction_input(source))


def test_snapshot_accepts_internal_symlink_when_verified_bytes_are_unchanged(tmp_path: Path):
    source = make_extraction(tmp_path / "source")
    victim = source / "snapshot/pages/arguments/a.wiki"
    duplicate = victim.with_name("copy_a.wiki")
    duplicate.write_bytes(victim.read_bytes())
    victim.unlink()
    victim.symlink_to(duplicate.name)
    inp = mod.resolve_extraction_input(source)
    _, snapshot = mod.verify_extraction(inp)
    assert len(snapshot["arguments"]) == 3
    ids = {row["canonical_title"]: f"A{i:04d}" for i, row in enumerate(snapshot["arguments"], 1)}
    output = tmp_path / "build"
    mod.copy_import_pages(inp, snapshot, output, ids)
    assert (output / "imports/fr/arguments/A0001.wiki").read_bytes() == duplicate.read_bytes()


def test_import_rechecks_page_path_boundary_without_prior_verification(tmp_path: Path):
    source = make_extraction(tmp_path / "source")
    inp = mod.resolve_extraction_input(source)
    snapshot = json.loads(inp.snapshot_manifest_path.read_text(encoding="utf-8"))
    snapshot["arguments"][0]["relative_path"] = "../../outside.wiki"
    ids = {row["canonical_title"]: f"A{i:04d}" for i, row in enumerate(snapshot["arguments"], 1)}
    output = tmp_path / "build"
    with pytest.raises(mod.CorpusInitError, match="Chemin de page invalide"):
        mod.copy_import_pages(inp, snapshot, output, ids)
    assert not (output / "imports/fr/arguments/A0001.wiki").exists()


def test_copy_import_matches_normalized_snapshot_titles_without_rewriting_pages(tmp_path: Path):
    source = make_extraction(tmp_path / "source")
    inp = mod.resolve_extraction_input(source)
    _, snapshot = mod.verify_extraction(inp)
    for row in snapshot["arguments"]:
        row["canonical_title"] = row["canonical_title"].replace(" ", "_")
    ids = {"Argument A": "A0001", "Argument B": "A0002", "Argument C": "A0003"}
    copied, import_data = mod.copy_import_pages(inp, snapshot, tmp_path / "build", ids)

    assert set(copied) == set(ids)
    for row, title in zip(snapshot["arguments"], ids):
        expected = inp.snapshot_manifest_path.parent / row["relative_path"]
        actual = tmp_path / "build" / f"imports/fr/arguments/{ids[title]}.wiki"
        assert actual.read_bytes() == expected.read_bytes()
    assert [row["source_graph_title"] for row in import_data["provenance"]["pages"][1:]] == list(ids)


def test_exact_snapshot_title_takes_precedence_over_earlier_normalized_alias(tmp_path: Path):
    source = make_extraction(tmp_path / "source")
    inp = mod.resolve_extraction_input(source)
    _, snapshot = mod.verify_extraction(inp)
    snapshot["arguments"][0]["canonical_title"] = "Argument_A"
    snapshot["arguments"][1]["canonical_title"] = "Argument A"
    ids = {"Argument A": "A0001"}

    _, import_data = mod.copy_import_pages(inp, snapshot, tmp_path / "build", ids)
    expected = source / "snapshot/pages/arguments/b.wiki"
    assert (tmp_path / "build/imports/fr/arguments/A0001.wiki").read_bytes() == expected.read_bytes()
    assert import_data["provenance"]["pages"][1]["relative_path"] == "pages/arguments/b.wiki"


def test_first_normalized_snapshot_match_is_preserved_on_alias_collision(tmp_path: Path):
    source = make_extraction(tmp_path / "source")
    inp = mod.resolve_extraction_input(source)
    _, snapshot = mod.verify_extraction(inp)
    snapshot["arguments"][0]["canonical_title"] = "Argument_A"
    snapshot["arguments"][1]["canonical_title"] = "Argument__A"
    ids = {"Argument A": "A0001"}
    _, import_data = mod.copy_import_pages(inp, snapshot, tmp_path / "build", ids)
    assert (tmp_path / "build/imports/fr/arguments/A0001.wiki").read_bytes() == (
        source / "snapshot/pages/arguments/a.wiki"
    ).read_bytes()
    assert import_data["provenance"]["pages"][1]["relative_path"] == "pages/arguments/a.wiki"


@pytest.mark.parametrize("invalid_before_match", [True, False])
def test_normalized_lookup_retains_historical_invalid_title_error_order(
    tmp_path: Path, invalid_before_match: bool,
):
    source = make_extraction(tmp_path / "source")
    inp = mod.resolve_extraction_input(source)
    _, snapshot = mod.verify_extraction(inp)
    snapshot["arguments"][0]["canonical_title"] = "" if invalid_before_match else "Argument_A"
    snapshot["arguments"][1]["canonical_title"] = "Argument_A" if invalid_before_match else ""
    ids = {"Argument A": "A0001"}

    if invalid_before_match:
        with pytest.raises(mod.CorpusInitError, match="Titre vide après normalisation"):
            mod.copy_import_pages(inp, snapshot, tmp_path / "build", ids)
    else:
        _, imported = mod.copy_import_pages(inp, snapshot, tmp_path / "build", ids)
        assert imported["provenance"]["pages"][1]["relative_path"] == "pages/arguments/a.wiki"


def test_normalization_is_linear_for_many_snapshot_aliases(tmp_path: Path, monkeypatch):
    from wikidebia_pretranslation_benchmark import make_synthetic_extraction

    source = make_synthetic_extraction(tmp_path / "source", arguments=100, payload_bytes=80)
    inp = mod.resolve_extraction_input(source)
    _, snapshot = mod.verify_extraction(inp)
    ids = {}
    for i, row in enumerate(snapshot["arguments"], start=1):
        ids[row["canonical_title"]] = f"A{i:04d}"
        row["canonical_title"] = row["canonical_title"].replace(" ", "_")

    original = mod.normalize_title
    normalized_count = []

    def counted(value):
        normalized_count.append(value)
        return original(value)

    monkeypatch.setattr(mod, "normalize_title", counted)
    copied, _ = mod.copy_import_pages(inp, snapshot, tmp_path / "build", ids)
    assert len(copied) == 100
    assert len(normalized_count) <= 2 * len(ids) + 2  # old scan: 5050+ normalizations



def test_source_verification_resolves_snapshot_root_only_once(tmp_path: Path, monkeypatch):
    """Every page is still individually resolved; only the common root is reused."""
    source = make_extraction(tmp_path / "source")
    inp = mod.resolve_extraction_input(source)
    snapshot_root = inp.snapshot_manifest_path.parent
    original_resolve = Path.resolve
    root_resolutions: list[Path] = []
    page_resolutions: list[Path] = []

    def counted_resolve(path, *args, **kwargs):
        if path == snapshot_root:
            root_resolutions.append(path)
        if path.parent.name in {"arguments", "pages"}:
            page_resolutions.append(path)
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", counted_resolve)
    _, snapshot = mod.verify_extraction(inp)
    assert len(snapshot["arguments"]) == 3
    assert len(root_resolutions) == 1
    assert len(page_resolutions) >= len(snapshot["arguments"]) + 1


def test_import_resolves_snapshot_root_only_once_and_copies_verified_bytes(
    tmp_path: Path, monkeypatch,
):
    source = make_extraction(tmp_path / "source")
    inp = mod.resolve_extraction_input(source)
    _, snapshot = mod.verify_extraction(inp)
    snapshot_root = inp.snapshot_manifest_path.parent
    ids = {row["canonical_title"]: f"A{i:04d}" for i, row in enumerate(snapshot["arguments"], 1)}
    original_resolve = Path.resolve
    root_count = 0

    def counted_resolve(path, *args, **kwargs):
        nonlocal root_count
        if path == snapshot_root:
            root_count += 1
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", counted_resolve)
    target = tmp_path / "build"
    copied, _ = mod.copy_import_pages(inp, snapshot, target, ids)
    assert root_count == 1
    assert len(copied) == 3
    for row, node_id in zip(snapshot["arguments"], ids.values()):
        actual = (target / f"imports/fr/arguments/{node_id}.wiki").read_bytes()
        assert actual == (snapshot_root / row["relative_path"]).read_bytes()


def test_cached_snapshot_root_preserves_portability_and_symlink_rejection(tmp_path: Path):
    source = make_extraction(tmp_path / "source")
    root = source / "snapshot"
    cached_root = root.resolve()
    for relative in ("pages/debate.wiki", "pages/arguments/a.wiki"):
        assert mod._snapshot_page_path(root, relative) == mod._snapshot_page_path(
            root, relative, _resolved_root=cached_root,
        )
    for relative in ("../outside.wiki", "/etc/passwd", "pages\\bad.wiki", ""):
        with pytest.raises(mod.CorpusInitError) as normal:
            mod._snapshot_page_path(root, relative)
        with pytest.raises(mod.CorpusInitError) as accelerated:
            mod._snapshot_page_path(root, relative, _resolved_root=cached_root)
        assert str(normal.value) == str(accelerated.value)

    outside = tmp_path / "outside.wiki"
    outside.write_text("unsafe", encoding="utf-8")
    victim = root / "pages/arguments/a.wiki"
    victim.unlink()
    victim.symlink_to(outside)
    with pytest.raises(mod.CorpusInitError, match="extérieure"):
        mod._snapshot_page_path(
            root, "pages/arguments/a.wiki", _resolved_root=cached_root,
        )


def test_cached_root_fails_closed_if_snapshot_directory_is_repointed(tmp_path: Path):
    source = make_extraction(tmp_path / "source")
    root = source / "snapshot"
    resolved_root = root.resolve()
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "pages/arguments").mkdir(parents=True)
    (foreign / "pages/arguments/a.wiki").write_text("tampered", encoding="utf-8")
    root.rename(tmp_path / "old_snapshot")
    root.symlink_to(foreign, target_is_directory=True)
    with pytest.raises(mod.CorpusInitError, match="extérieure"):
        mod._snapshot_page_path(
            root, "pages/arguments/a.wiki", _resolved_root=resolved_root,
        )
