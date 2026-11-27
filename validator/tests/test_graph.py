from pathlib import Path

from wikidebia_validator.validator import validate_package
from .helpers import create_graph_package, dump


def test_graph_package_valid(tmp_path: Path):
    create_graph_package(tmp_path)
    report = validate_package(tmp_path, scopes=["graph"])
    assert report.errors == 0, report.to_text()


def test_duplicate_title_and_cycle_detected(tmp_path: Path):
    create_graph_package(tmp_path)
    import json
    reg_path = tmp_path / "data/registre_debat.json"
    reg = json.loads(reg_path.read_text())
    reg["graph"]["nodes"][1]["fr"]["canonical_title"] = reg["graph"]["nodes"][0]["fr"]["canonical_title"]
    reg["graph"]["edges"] = [
        {"id": "E00001", "parent_node_id": "A0001", "child_node_id": "A0002", "relation": "justification", "order": 1, "status": "active"},
        {"id": "E00002", "parent_node_id": "A0002", "child_node_id": "A0001", "relation": "objection", "order": 1, "status": "active"},
    ]
    dump(reg_path, reg)
    report = validate_package(tmp_path, scopes=["graph"])
    codes = {f.code for f in report.findings if f.level == "ERROR"}
    assert "WDV-GRA-002" in codes
    assert "WDV-GRA-005" in codes


def test_bad_derived_counts_detected(tmp_path: Path):
    create_graph_package(tmp_path)
    import json
    reg_path = tmp_path / "data/registre_debat.json"
    reg = json.loads(reg_path.read_text())
    reg["graph"]["derived_counts"]["distinct_nodes"] = 99
    dump(reg_path, reg)
    report = validate_package(tmp_path, scopes=["graph"])
    assert any(f.code == "WDV-GRA-013" and f.level == "ERROR" for f in report.findings)


def test_title_editorial_checks_are_deferred_until_french_metadata_lock(tmp_path: Path):
    create_graph_package(tmp_path)
    import json
    from wikidebia_validator.graph import structural_sha256

    reg_path = tmp_path / "data/registre_debat.json"
    graph_path = tmp_path / "graph/graphe_argumentatif.json"
    reg = json.loads(reg_path.read_text(encoding="utf-8"))
    reg["graph"]["nodes"][0]["fr"]["canonical_title"] = "Cette mesure produirait un bénéfice collectif."
    reg["graph"]["lifecycle"]["structural_sha256"] = structural_sha256(reg)
    dump(reg_path, reg)
    projection = json.loads(graph_path.read_text(encoding="utf-8"))
    projection["nodes"] = reg["graph"]["nodes"]
    projection["lifecycle"] = reg["graph"]["lifecycle"]
    dump(graph_path, projection)

    report = validate_package(tmp_path, scopes=["schema", "graph"])
    assert report.errors == 0, report.to_text()
    deferred = [f for f in report.findings if f.code in {"WDV-GRA-016", "WDV-EDT-016"}]
    assert deferred
    assert all(f.level == "WARNING" for f in deferred), report.to_text()

    dump(tmp_path / "data/fr_page_metadata_lock.json", {"schema": "test-lock"})
    report = validate_package(tmp_path, scopes=["schema", "graph"])
    enforced = [f for f in report.findings if f.code in {"WDV-GRA-016", "WDV-EDT-016"}]
    assert any(f.level == "ERROR" for f in enforced), report.to_text()


def test_typographic_apostrophe_in_english_title_is_rejected_after_lock(tmp_path: Path):
    create_graph_package(tmp_path)
    import json
    from wikidebia_validator.graph import structural_sha256

    reg_path = tmp_path / "data/registre_debat.json"
    graph_path = tmp_path / "graph/graphe_argumentatif.json"
    reg = json.loads(reg_path.read_text(encoding="utf-8"))
    reg["graph"]["nodes"][0].setdefault("en", {})["canonical_title"] = "Basic income supports women’s autonomy"
    reg["graph"]["nodes"][0]["en"]["displayed_title"] = "Basic income supports women’s autonomy"
    reg["graph"]["nodes"][0]["en"]["title_status"] = "validated"
    reg["graph"]["lifecycle"]["structural_sha256"] = structural_sha256(reg)
    dump(reg_path, reg)
    projection = json.loads(graph_path.read_text(encoding="utf-8"))
    projection["nodes"] = reg["graph"]["nodes"]
    projection["lifecycle"] = reg["graph"]["lifecycle"]
    dump(graph_path, projection)
    dump(tmp_path / "data/en_page_metadata_lock.json", {"schema": "test-lock"})

    report = validate_package(tmp_path, scopes=["graph"])
    assert any(
        f.code == "WDV-GRA-016" and f.level == "ERROR" and "women’s" in f.message
        for f in report.findings
    ), report.to_text()


def test_historical_french_displayed_title_is_preserved_after_lock(tmp_path: Path):
    create_graph_package(tmp_path)
    import json
    from wikidebia_validator.graph import structural_sha256

    reg_path = tmp_path / "data/registre_debat.json"
    graph_path = tmp_path / "graph/graphe_argumentatif.json"
    reg = json.loads(reg_path.read_text(encoding="utf-8"))
    historical = "L’autonomie économique des femmes"
    reg["graph"]["nodes"][0]["fr"]["displayed_title"] = historical
    reg["graph"]["lifecycle"]["structural_sha256"] = structural_sha256(reg)
    dump(reg_path, reg)
    projection = json.loads(graph_path.read_text(encoding="utf-8"))
    projection["nodes"] = reg["graph"]["nodes"]
    projection["lifecycle"] = reg["graph"]["lifecycle"]
    dump(graph_path, projection)
    dump(tmp_path / "data/fr_page_metadata_lock.json", {
        "schema": "wikidebia-fr-page-metadata-lock-1.0",
        "arguments": [{
            "entity_id": "A0001",
            "page_origin": "preexisting",
            "displayed_title": historical,
            "decisions": {"displayed_title": "keep"},
        }],
    })

    report = validate_package(tmp_path, scopes=["graph"])
    assert not any(
        f.code == "WDV-GRA-016" and f.level == "ERROR" and historical in f.message
        for f in report.findings
    ), report.to_text()


def test_french_ligatures_are_deferred_then_blocked_even_in_historical_titles(tmp_path):
    import json
    from wikidebia_validator.graph import structural_sha256

    create_graph_package(tmp_path)
    path = tmp_path / 'data/registre_debat.json'
    reg = json.loads(path.read_text())
    reg['debate']['pages']['fr']['canonical_title'] = 'Une œuvre collective ?'
    node = reg['graph']['nodes'][0]
    node['fr']['canonical_title'] = 'Le cœur du débat est éclairé'
    node['fr']['displayed_title'] = 'Œuvre et æsthétique'
    reg['graph']['lifecycle']['structural_sha256'] = structural_sha256(reg)
    dump(path, reg)
    before = validate_package(tmp_path, scopes=['graph'])
    findings = [f for f in before.findings if f.code == 'WDV-GRA-016']
    assert len(findings) == 3 and all(f.level == 'WARNING' for f in findings), before.to_text()
    dump(tmp_path / 'data/fr_page_metadata_lock.json', {
        'schema': 'wikidebia-fr-page-metadata-lock-1.0',
        'arguments': [{'entity_id': node['id'], 'page_origin': 'preexisting',
                       'displayed_title': node['fr']['displayed_title'], 'decisions': {'displayed_title': 'keep'}}],
    })
    after = validate_package(tmp_path, scopes=['graph'])
    findings = [f for f in after.findings if f.code == 'WDV-GRA-016']
    assert len(findings) == 3 and all(f.level == 'ERROR' for f in findings), after.to_text()
    assert {f.details['suggested_title'] for f in findings} == {'Une oeuvre collective ?', 'Le coeur du débat est éclairé', 'OEuvre et aesthétique'}
    reg['debate']['pages']['fr']['canonical_title'] = 'Une oeuvre collective ?'
    node['fr'].update(canonical_title='Le coeur du débat est éclairé', displayed_title='OEuvre et aesthétique')
    reg['graph']['lifecycle']['structural_sha256'] = structural_sha256(reg)
    dump(path, reg)
    assert not any(f.code == 'WDV-GRA-016' for f in validate_package(tmp_path, scopes=['graph']).findings)


def test_french_rendered_relation_ligatures_are_checked_without_touching_citations(tmp_path):
    from wikidebia_validator.package import PackageContext
    from wikidebia_validator.report import Report
    from wikidebia_validator.wikicode import parse_template, _validate_french_title_ligatures

    report = Report('test', str(tmp_path), ['wikicode'])
    ctx = PackageContext(tmp_path, report)
    manifest = {'page_type': 'argument', 'canonical_title': 'Le coeur est éclairé'}
    template = parse_template('{{Argument|résumé=Une œuvre.|citations={{Citation|citation=Le cœur.}}|justifications={{Justification|page=Une œuvre|titre-affiché=Un eﬀet}}}}')
    _validate_french_title_ligatures(ctx, template, 'test.wiki', manifest)
    assert report.errors == 2 and all(f.code == 'WDV-GRA-016' for f in report.findings)
    report.findings.clear()
    template = parse_template('{{Argument|résumé=Une œuvre.|citations={{Citation|citation=Le cœur.}}|justifications={{Justification|page=Une oeuvre|titre-affiché=Un effet}}}}')
    _validate_french_title_ligatures(ctx, template, 'test.wiki', manifest)
    assert report.errors == 0
