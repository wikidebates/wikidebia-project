"""Exact branch statistics with reused nodes and many primary roots."""
from __future__ import annotations

import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import wikidebia_graph_extract as mod


def synthetic_result(
    nodes, roots_pro, roots_con, edges, *,
    missing=(), depth_frontiers=None, existing_english=False,
):
    missing = set(missing)
    parsed = {
        title: mod.ParsedArgument([], [], "", [])
        for title in nodes if title not in missing
    }
    pages = {
        title: mod.PageRecord(title, title, "{{Argument}}", revision_id=1)
        for title in parsed
    }
    return mod.CrawlResult(
        debate_record=mod.PageRecord("Débat test", "Débat test", "{{Débat}}"),
        debate_title="Débat test", debate_url="https://example.invalid/debat",
        roots_pro=list(roots_pro), roots_con=list(roots_con),
        root_displayed_titles={},
        page_records=pages,
        parsed_arguments=parsed,
        relations=[
            mod.RelationDraft(source, kind, target, order)
            for order, (source, kind, target) in enumerate(edges, 1)
        ],
        aliases={}, warnings=[], frontier_information=[],
        existing_english_debate_title="Existing English Debate" if existing_english else "",
        existing_english_translation_frontiers={},
        existing_english_page_records={},
        depth_frontiers=depth_frontiers or {},
        missing_pages=sorted(missing),
        missing_page_provenance=[], crawl_options={"max_depth": None},
    )


def expected_branch_counts(result):
    """Independent path-count oracle, purposefully retaining per-level Counters."""
    graph_nodes = set(result.parsed_arguments) | set(result.missing_pages)
    ordered, cycles = mod._topological_order(graph_nodes, result.relations)
    if cycles:
        return []
    adjacency = defaultdict(list)
    for edge in result.relations:
        adjacency[edge.source].append(edge.target)
    roots = result.roots_pro + result.roots_con
    orientation = {r: "pour" for r in result.roots_pro}
    orientation.update({r: "contre" for r in result.roots_con})
    rows = []
    for root in roots:
        visited = set()
        stack = [root]
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            stack.extend(adjacency[current])
        levels = {node: Counter() for node in graph_nodes}
        levels[root][1] = 1
        for node in ordered:
            for child in adjacency[node]:
                for depth, ways in levels[node].items():
                    levels[child][depth + 1] += ways
        nonzero_levels = [depth for counts in levels.values() for depth in counts]
        longest = max(nonzero_levels, default=1)
        rows.append({
            "orientation": orientation[root],
            "argument": root,
            "enfants_directs": len(adjacency[root]),
            "pages_uniques_branche_racine_incluse": len(visited),
            "occurrences_branche_racine_incluse": sum(sum(x.values()) for x in levels.values()),
            "niveau_maximal_occurrences": longest,
            "profondeur_maximale_en_aretes": longest - 1,
            "profondeur_maximale": longest,
        })
    return rows


def test_diamond_reuse_counts_unique_pages_not_only_paths():
    result = synthetic_result(
        "ABCD", ["A"], [],
        [("A","justification","B"), ("A","objection","C"),
         ("B","justification","D"), ("C","justification","D")],
    )
    graph = mod.analyze_graph(result)
    assert graph["branches_niveau_1"] == expected_branch_counts(result)
    assert graph["branches_niveau_1"][0]["pages_uniques_branche_racine_incluse"] == 4
    assert graph["branches_niveau_1"][0]["occurrences_branche_racine_incluse"] == 5
    assert graph["branches_niveau_1"][0]["niveau_maximal_occurrences"] == 3
    assert graph["metadata"]["pages_réutilisées_plusieurs_fois"] == 1


def test_root_reused_by_other_root_keeps_per_root_counts():
    result = synthetic_result(
        "ABC", ["A", "B"], [],
        [("A","justification","B"), ("B","justification","C")],
    )
    rows = mod.analyze_graph(result)["branches_niveau_1"]
    assert rows == expected_branch_counts(result)
    assert [x["occurrences_branche_racine_incluse"] for x in rows] == [3, 2]


def test_duplicate_parallel_edges_count_two_paths_but_one_distinct_child():
    result = synthetic_result(
        ["A", "B"], ["A"], [],
        [("A","justification","B"), ("A","objection","B")],
    )
    actual = mod.analyze_graph(result)["branches_niveau_1"][0]
    assert actual["occurrences_branche_racine_incluse"] == 3
    assert actual["pages_uniques_branche_racine_incluse"] == 2
    assert actual == expected_branch_counts(result)[0]


def test_same_root_in_both_orientations_retains_historical_contre_precedence():
    result = synthetic_result(["A"], ["A"], ["A"], [])
    actual = mod.analyze_graph(result)["branches_niveau_1"]
    assert actual == expected_branch_counts(result)
    assert [row["orientation"] for row in actual] == ["contre", "contre"]


def test_many_roots_shared_deep_subgraph_keep_exact_counts():
    roots = [f"R{i:02d}" for i in range(12)]
    shared = [f"S{i:02d}" for i in range(45)]
    edges = [(r, "justification", shared[0]) for r in roots]
    edges += [(shared[i], "objection", shared[i + 1]) for i in range(len(shared)-1)]
    edges += [(shared[i], "justification", shared[i + 2]) for i in range(len(shared)-2)]
    result = synthetic_result(
        [*roots, *shared], roots[:7], roots[7:], edges,
    )
    graph = mod.analyze_graph(result)
    assert graph["metadata"]["graphe_sans_cycle"]
    assert graph["branches_niveau_1"] == expected_branch_counts(result)
    assert len(graph["branches_niveau_1"]) == 12


def test_cycle_still_skips_branch_counts_instead_of_recursing():
    result = synthetic_result(
        ["A", "B"], ["A"], [],
        [("A","justification","B"), ("B","objection","A")],
    )
    graph = mod.analyze_graph(result)
    assert not graph["metadata"]["graphe_sans_cycle"]
    assert graph["branches_niveau_1"] == []
    assert graph["metadata"]["nœuds_dans_cycles"]


def test_missing_page_is_still_counted_as_a_reachable_node():
    result = synthetic_result(
        ["A", "Gone"], ["A"], [], [("A","justification","Gone")],
        missing={"Gone"},
    )
    graph = mod.analyze_graph(result)
    assert graph["branches_niveau_1"] == expected_branch_counts(result)
    assert graph["branches_niveau_1"][0]["pages_uniques_branche_racine_incluse"] == 2
    assert graph["metadata"]["pages_manquantes"] == ["Gone"]


def test_unbounded_single_root_deep_chain_uses_dfs_without_bitsets():
    nodes = [f"N{i:04d}" for i in range(250)]
    result = synthetic_result(
        nodes, nodes[:1], [],
        [(nodes[i], "justification", nodes[i+1]) for i in range(len(nodes)-1)],
    )
    graph = mod.analyze_graph(result)
    assert graph["branches_niveau_1"] == expected_branch_counts(result)
    assert graph["branches_niveau_1"][0]["niveau_maximal_occurrences"] == 250
    assert graph["branches_niveau_1"][0]["occurrences_branche_racine_incluse"] == 250


@pytest.mark.parametrize("seed", range(6))
def test_random_reused_dags_match_independent_level_counter_oracle(seed):
    rng = random.Random(seed)
    nodes = [f"N{i:03d}" for i in range(38)]
    roots = nodes[:12]
    edges = []
    for i in range(11):
        for j in range(i + 1, len(nodes)):
            if rng.random() < 0.08:
                edges.append((nodes[i], "justification", nodes[j]))
    for i in range(11, len(nodes)-1):
        for j in range(i + 1, len(nodes)):
            if rng.random() < 0.09:
                edges.append((nodes[i], "objection", nodes[j]))
    result = synthetic_result(nodes, roots[:6], roots[6:], edges)
    graph = mod.analyze_graph(result)
    assert graph["branches_niveau_1"] == expected_branch_counts(result)
    assert all(x["occurrences_branche_racine_incluse"] >= 1 for x in graph["branches_niveau_1"])


def test_debate_already_in_english_with_zero_roots_keeps_empty_branches():
    result = synthetic_result([], [], [], [], existing_english=True)
    graph = mod.analyze_graph(result)
    assert graph["branches_niveau_1"] == []
    assert graph["metadata"]["traduction_du_débat_requise"] is False
    assert graph["metadata"]["pages_arguments_uniques"] == 0


def test_more_than_bitset_limit_preserves_linear_path_counts():
    nodes = [f"R{i:04d}" for i in range(8010)]
    roots = nodes[:8]
    result = synthetic_result(nodes, roots[:4], roots[4:], [])
    graph = mod.analyze_graph(result)
    assert len(graph["branches_niveau_1"]) == 8
    assert all(
        row["pages_uniques_branche_racine_incluse"] == 1
        and row["occurrences_branche_racine_incluse"] == 1
        and row["niveau_maximal_occurrences"] == 1
        for row in graph["branches_niveau_1"]
    )
