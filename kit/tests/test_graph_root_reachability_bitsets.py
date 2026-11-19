"""Root reachability is exact even when many roots converge into shared DAGs."""
from __future__ import annotations

import random
import sys
from collections import defaultdict
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import wikidebia_graph_extract as graph
from test_graph_analyze_dag_suffix_counts import synthetic_result


def oracle(result):
    """Independent root-by-root DFS; no bitsets or topological propagation."""
    nodes = set(result.parsed_arguments) | set(result.missing_pages)
    ordered, cycles = graph._topological_order(nodes, result.relations)
    if cycles:
        return {node: ([], []) for node in nodes}
    adjacency = defaultdict(list)
    for edge in result.relations:
        adjacency[edge.source].append(edge.target)
    reached = {node: set() for node in nodes}
    roots = result.roots_pro + result.roots_con
    for root in roots:
        seen = set()
        stack = [root]
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            reached[node].add(root)
            stack.extend(adjacency[node])
    orientation = {root: "pour" for root in result.roots_pro}
    orientation.update({root: "contre" for root in result.roots_con})
    return {
        node: (
            sorted(roots_set, key=str.casefold),
            sorted({orientation[root] for root in roots_set}),
        )
        for node, roots_set in reached.items()
    }


def assert_matches_oracle(result):
    result_graph = graph.analyze_graph(result)
    expected = oracle(result)
    for row in result_graph["noeuds"]:
        assert (
            row["arguments_racines"],
            row["orientations_racines"],
        ) == expected[row["titre"]]
    return result_graph


def shared_graph(roots_count=32, shared_count=120):
    roots = [f"Root {i:03d}" for i in range(roots_count)]
    common = [f"Shared {i:03d}" for i in range(shared_count)]
    edges = [(root, "justification", common[0]) for root in roots]
    edges += [
        (common[i], "objection", common[i+1])
        for i in range(len(common)-1)
    ]
    return synthetic_result([*roots,*common],roots[:roots_count//2],roots[roots_count//2:],edges)


def test_all_roots_on_deep_shared_chain_are_reported_once_each():
    result = shared_graph(32,120)
    output = assert_matches_oracle(result)
    last = next(row for row in output["noeuds"] if row["titre"] == "Shared 119")
    assert len(last["arguments_racines"]) == 32
    assert last["orientations_racines"] == ["contre","pour"]
    assert last["arguments_racines"][0] == "Root 000"


def test_shared_root_lists_are_not_aliased_between_node_rows():
    output = assert_matches_oracle(shared_graph(24,35))
    a = next(row for row in output["noeuds"] if row["titre"] == "Shared 000")
    b = next(row for row in output["noeuds"] if row["titre"] == "Shared 001")
    a["arguments_racines"].append("Bad")
    a["orientations_racines"].append("Bad")
    assert "Bad" not in b["arguments_racines"]
    assert "Bad" not in b["orientations_racines"]


def test_two_root_clusters_merge_without_dropping_any_contributors():
    roots = [f"R{i:02d}" for i in range(32)]
    nodes = [*roots,"Left","Right","Merged","Terminal"]
    edges = [
        (root,"justification","Left" if i<16 else "Right")
        for i,root in enumerate(roots)
    ] + [
        ("Left","justification","Merged"),
        ("Right","objection","Merged"),
        ("Merged","justification","Terminal"),
    ]
    output = assert_matches_oracle(
        synthetic_result(nodes,roots[:16],roots[16:],edges)
    )
    by_title = {row["titre"]:row for row in output["noeuds"]}
    assert len(by_title["Left"]["arguments_racines"])==16
    assert len(by_title["Right"]["arguments_racines"])==16
    assert len(by_title["Merged"]["arguments_racines"])==32


def test_duplicate_root_in_both_orientations_keeps_contre_precedence():
    result=shared_graph(24,40)
    result.roots_con.append(result.roots_pro[0])
    output=assert_matches_oracle(result)
    by_title={row["titre"]:row for row in output["noeuds"]}
    target=by_title["Shared 039"]
    assert target["arguments_racines"].count(result.roots_pro[0])==1
    assert target["orientations_racines"]==["contre","pour"]


def test_casefold_colliding_root_titles_keep_historical_sorting():
    roots=["ROOT","root",*[f"Root {i:02d}" for i in range(20)]]
    nodes=[*roots,"Common","Final"]
    edges=[(root,"justification","Common") for root in roots]
    edges.append(("Common","objection","Final"))
    result=synthetic_result(nodes,roots[:11],roots[11:],edges)
    assert_matches_oracle(result)


def test_sparse_roots_keep_exact_labels_when_no_large_shared_target():
    roots=[f"R{i:03d}" for i in range(80)]
    leaves=[f"L{i:03d}" for i in range(80)]
    edges=[(roots[i],"justification",leaves[i]) for i in range(80)]
    output=assert_matches_oracle(
        synthetic_result([*roots,*leaves],roots[:40],roots[40:],edges)
    )
    assert output["metadata"]["pages_arguments_uniques"]==160


def test_empty_graph_and_english_debate_still_have_no_roots():
    output=assert_matches_oracle(
        synthetic_result([],[],[],[],existing_english=True)
    )
    assert output["noeuds"]==[]
    assert output["metadata"]["traduction_du_débat_requise"] is False


def test_cycle_retains_original_empty_root_provenance():
    roots=[f"R{i:02d}" for i in range(20)]
    edges=[(r,"justification","A") for r in roots]
    edges += [("A","justification","B"),("B","objection","A")]
    output=assert_matches_oracle(
        synthetic_result([*roots,"A","B"],roots[:10],roots[10:],edges)
    )
    assert not output["metadata"]["graphe_sans_cycle"]
    assert all(not row["arguments_racines"] for row in output["noeuds"])


def test_missing_and_unreachable_nodes_get_exact_provenance():
    roots=[f"R{i:02d}" for i in range(20)]
    edges=[(r,"justification","Missing") for r in roots]
    result=synthetic_result(
        [*roots,"Missing","Orphan"],roots[:10],roots[10:],edges,
        missing=["Missing"],
    )
    output=assert_matches_oracle(result)
    row=next(row for row in output["noeuds"] if row["titre"]=="Missing")
    assert len(row["arguments_racines"])==20
    orphan=next(row for row in output["noeuds"] if row["titre"]=="Orphan")
    assert orphan["arguments_racines"]==[]


@pytest.mark.parametrize("seed",range(7))
def test_seeded_shared_dags_match_independent_reachability_oracle(seed):
    rng=random.Random(seed+500)
    roots=[f"R{i:02d}" for i in range(20)]
    shared=[f"S{i:03d}" for i in range(65)]
    edges=[(root,"justification",shared[rng.randrange(3)]) for root in roots]
    for i in range(65):
        for j in range(i+1,65):
            if rng.random()<0.045:
                edges.append((shared[i],"objection",shared[j]))
    assert_matches_oracle(synthetic_result(
        [*roots,*shared],roots[:10],roots[10:],edges
    ))
