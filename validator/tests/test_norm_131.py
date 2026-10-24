from .current_policy_helpers import CURRENT_NORM_FILE, CURRENT_NORM, CURRENT_VALIDATOR, CURRENT_KIT, current_norm_path
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_graph_validator_accepts_explicit_bounded_or_unbounded_policy_without_threshold_warning():
    text=(ROOT/'src/wikidebia_validator/graph.py').read_text(encoding='utf-8')
    assert 'limit_policy == "bounded"' in text
    assert 'limit_policy == "unbounded"' in text
    assert 'if norm in {' not in text
    assert 'Profondeur exceptionnelle élevée' not in text

def test_active_norm_orders_keywords_by_relevance():
    text=(ROOT / 'normative_reference/01_normes' / CURRENT_NORM_FILE).read_text(encoding='utf-8')
    assert 'du plus directement pertinent au moins directement pertinent' in text
    assert 'L’ordre chronologique' in text


def test_current_norm_does_not_warn_on_high_depth(tmp_path):
    import json
    from wikidebia_validator.validator import validate_package
    from .helpers import create_graph_package, dump
    create_graph_package(tmp_path)
    manifest_path=tmp_path/'manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest['normative_versions']['consolidated_norm']='1.2.32'
    dump(manifest_path,manifest)
    reg_path=tmp_path/'data/registre_debat.json'
    reg=json.loads(reg_path.read_text(encoding='utf-8'))
    # One node is enough to test a descriptive maximum without introducing a bad relation.
    reg['graph']['occurrences'][0]['depth']=9
    reg['graph']['depth_policy']={'limit_policy':'unbounded','maximum_observed':9}
    reg['graph']['derived_counts']['maximum_depth']=9
    reg['graph']['nodes'][0]['derived']['minimum_depth']=9
    reg['graph']['nodes'][0]['derived']['maximum_depth']=9
    dump(reg_path,reg)
    report=validate_package(tmp_path,scopes=['graph'])
    assert not any(f.level=='WARNING' and 'Profondeur exceptionnelle élevée' in f.message for f in report.findings)


def test_graph_validator_accepts_consistent_bounded_policy(tmp_path):
    import json
    from wikidebia_validator.graph import compute_derived, structural_sha256
    from wikidebia_validator.validator import validate_package
    from .helpers import create_graph_package, dump

    create_graph_package(tmp_path)
    reg_path = tmp_path / 'data/registre_debat.json'
    reg = json.loads(reg_path.read_text(encoding='utf-8'))
    reg['graph']['depth_policy'] = {
        'limit_policy': 'bounded',
        'maximum_observed': 1,
        'maximum_edge_depth': 0,
        'frontier_node_ids': ['A0001'],
        'relations_omitted_at_frontier': 1,
    }
    counts, per_node = compute_derived(reg)
    reg['graph']['derived_counts'] = counts
    for node in reg['graph']['nodes']:
        node['derived'] = per_node[node['id']]
    reg['graph']['lifecycle']['structural_sha256'] = structural_sha256(reg)
    dump(reg_path, reg)
    projection_path = tmp_path / 'graph/graphe_argumentatif.json'
    projection = json.loads(projection_path.read_text(encoding='utf-8'))
    projection['depth_policy'] = reg['graph']['depth_policy']
    projection['lifecycle'] = reg['graph']['lifecycle']
    dump(projection_path, projection)

    report = validate_package(tmp_path, scopes=['schema', 'graph'])
    assert not any(f.level == 'ERROR' for f in report.findings)


def test_graph_validator_rejects_inconsistent_bounded_frontier(tmp_path):
    import json
    from wikidebia_validator.graph import structural_sha256
    from wikidebia_validator.validator import validate_package
    from .helpers import create_graph_package, dump

    create_graph_package(tmp_path)
    reg_path = tmp_path / 'data/registre_debat.json'
    reg = json.loads(reg_path.read_text(encoding='utf-8'))
    reg['graph']['depth_policy'] = {
        'limit_policy': 'bounded',
        'maximum_observed': 1,
        'maximum_edge_depth': 1,
        'frontier_node_ids': ['A0001'],
        'relations_omitted_at_frontier': 0,
    }
    reg['graph']['lifecycle']['structural_sha256'] = structural_sha256(reg)
    dump(reg_path, reg)
    projection_path = tmp_path / 'graph/graphe_argumentatif.json'
    projection = json.loads(projection_path.read_text(encoding='utf-8'))
    projection['depth_policy'] = reg['graph']['depth_policy']
    projection['lifecycle'] = reg['graph']['lifecycle']
    dump(projection_path, projection)

    report = validate_package(tmp_path, scopes=['schema', 'graph'])
    messages = [f.message for f in report.findings if f.code == 'WDV-GRA-009']
    assert any('niveau correspondant' in message for message in messages)
    assert any('relations omises' in message for message in messages)
