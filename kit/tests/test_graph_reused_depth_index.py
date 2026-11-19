"""The level-indexed reuse report preserves path multiplicity and page identity."""
from __future__ import annotations

import random
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import wikidebia_graph_extract as graph_extract
from test_graph_analyze_dag_suffix_counts import synthetic_result


def _legacy_reuse(result):
    """Independent oracle: visit every node for every occupied level."""
    nodes = set(result.parsed_arguments) | set(result.missing_pages)
    roots = result.roots_pro + result.roots_con
    adjacency = defaultdict(list)
    for edge in result.relations:
        adjacency[edge.source].append(edge.target)
    minimum = {title: 10**9 for title in nodes}
    queue = deque()
    for root in roots:
        minimum[root] = 1
        queue.append(root)
    while queue:
        source = queue.popleft()
        for child in adjacency[source]:
            if minimum[child] > minimum[source] + 1:
                minimum[child] = minimum[source] + 1
                queue.append(child)
    topo, cycles = graph_extract._topological_order(nodes, result.relations)
    if cycles:
        return {}, {}
    counters = {title: Counter() for title in nodes}
    for root in roots:
        counters[root][1] += 1
    for source in topo:
        for child in adjacency[source]:
            for level, count in counters[source].items():
                counters[child][level + 1] += count
    all_levels = Counter()
    for counter in counters.values():
        all_levels.update(counter)
    minimum_pages = Counter(v for v in minimum.values() if v != 10**9)
    reused_counts = {}
    reused_titles = {}
    for level in sorted(all_levels):
        surplus = all_levels[level] - minimum_pages.get(level, 0)
        if surplus:
            reused_counts[level] = surplus
            reused_titles[level] = sorted(
                [title for title, counter in counters.items()
                 if counter.get(level, 0) and
                    (minimum.get(title, 10**9) < level or counter.get(level, 0) > 1)],
                key=str.casefold,
            )
    return reused_counts, reused_titles


def _verify(result):
    metadata = graph_extract.analyze_graph(result)["metadata"]
    counts, names = _legacy_reuse(result)
    assert metadata["occurrences_reutilisees_par_niveau"] == counts
    assert metadata["pages_concernees_par_reutilisation_au_niveau"] == names
    return metadata


def test_diamond_shared_descendant_has_repeated_paths_at_same_level():
    result = synthetic_result(
        ["Root", "Left", "Right", "Common"], ["Root"], [],
        [("Root", "justification", "Left"),
         ("Root", "objection", "Right"),
         ("Left", "justification", "Common"),
         ("Right", "justification", "Common")],
    )
    meta = _verify(result)
    assert meta["occurrences_reutilisees_par_niveau"] == {3: 1}
    assert meta["pages_concernees_par_reutilisation_au_niveau"] == {3: ["Common"]}


def test_descendant_is_also_root_at_multiple_levels():
    result = synthetic_result(
        ["A", "B", "C"], ["A", "B"], [],
        [("A", "justification", "B"), ("B", "objection", "C")],
    )
    meta = _verify(result)
    assert meta["occurrences_reutilisees_par_niveau"] == {2: 1, 3: 1}
    assert meta["pages_concernees_par_reutilisation_au_niveau"] == {2: ["B"], 3: ["C"]}


def test_parallel_relations_count_as_two_occurrences_not_two_pages():
    result = synthetic_result(
        ["A", "B"], ["A"], [],
        [("A", "justification", "B"), ("A", "objection", "B")],
    )
    meta = _verify(result)
    assert meta["occurrences_reutilisees_par_niveau"] == {2: 1}
    assert meta["pages_concernees_par_reutilisation_au_niveau"] == {2: ["B"]}


def test_cycle_preserves_empty_reuse_reports():
    result = synthetic_result(
        ["A", "B"], ["A"], [],
        [("A", "justification", "B"), ("B", "objection", "A")],
    )
    meta = _verify(result)
    assert meta["graphe_sans_cycle"] is False
    assert meta["occurrences_reutilisees_par_niveau"] == {}
    assert meta["pages_concernees_par_reutilisation_au_niveau"] == {}


def test_missing_and_unreachable_page_preserve_reuse_identity():
    result = synthetic_result(
        ["A", "B", "Missing", "Orphan"], ["A"], [],
        [("A", "justification", "B"), ("A", "objection", "Missing"),
         ("B", "justification", "Missing")],
        missing=["Missing"],
    )
    meta = _verify(result)
    assert meta["pages_concernees_par_reutilisation_au_niveau"] == {3: ["Missing"]}
    assert meta["pages_arguments_uniques"] == 4


def test_distinct_casefold_ties_have_no_added_or_lost_arguments():
    result = synthetic_result(
        ["A", "Case", "case"], ["A"], [],
        [("A", "justification", "Case"), ("A", "objection", "Case"),
         ("A", "justification", "case"), ("A", "objection", "case")],
    )
    meta = _verify(result)
    assert meta["occurrences_reutilisees_par_niveau"] == {2: 2}
    assert set(meta["pages_concernees_par_reutilisation_au_niveau"][2]) == {"Case", "case"}


def test_deep_chain_with_one_long_range_shortcut_only_marks_late_reuse():
    names = [f"N{i:04d}" for i in range(300)]
    edges = [
        (names[i], "justification", names[i + 1])
        for i in range(len(names) - 1)
    ]
    edges.append((names[0], "objection", names[-1]))
    result = synthetic_result(names, [names[0]], [], edges)
    meta = _verify(result)
    assert names[-1] in meta["pages_concernees_par_reutilisation_au_niveau"][300]


@pytest.mark.parametrize("seed", range(7))
def test_random_dags_with_overlapping_paths_match_per_level_oracle(seed):
    rng = random.Random(seed + 100)
    names = [f"N{i:03d}" for i in range(48)]
    roots = names[:8]
    edges = [
        (names[i], rng.choice(["justification", "objection"]), names[j])
        for i in range(48)
        for j in range(i + 1, 48)
        if rng.random() < 0.046
    ]
    result = synthetic_result(names, roots[:4], roots[4:], edges)
    _verify(result)


def test_no_roots_no_reuse():
    result = synthetic_result(["Orphan"], [], [], [])
    meta = _verify(result)
    assert meta["occurrences_reutilisees_par_niveau"] == {}


def test_deep_exact_chain_without_reuse_does_not_invent_candidates():
    names = [f"N{i:04d}" for i in range(240)]
    edges = [(names[i], "justification", names[i+1]) for i in range(239)]
    result = synthetic_result(names, names[:1], [], edges)
    meta = _verify(result)
    assert meta["occurrences_reutilisees_par_niveau"] == {}
    assert meta["niveau_maximal_occurrences"] == 240


def test_long_shared_chain_reports_one_reused_page_at_every_downstream_level():
    roots = ["Root A", "Root B"]
    shared = [f"S{i:03d}" for i in range(75)]
    edges = [(root, "justification", shared[0]) for root in roots]
    edges.extend(
        (shared[i], "objection", shared[i+1])
        for i in range(len(shared)-1)
    )
    meta = _verify(synthetic_result([*roots, *shared], roots, [], edges))
    assert meta["occurrences_reutilisees_par_niveau"] == {
        level: 1 for level in range(2, 77)
    }
    assert meta["pages_concernees_par_reutilisation_au_niveau"] == {
        level: [shared[level - 2]] for level in range(2, 77)
    }


def test_eight_roots_sharing_long_branch_keep_exact_surplus_and_titles():
    roots = [f"Root {i}" for i in range(8)]
    shared = [f"S{i:03d}" for i in range(120)]
    edges = [(root, "justification", shared[0]) for root in roots]
    edges.extend(
        (shared[i], "justification", shared[i+1])
        for i in range(len(shared)-1)
    )
    meta = _verify(synthetic_result([*roots, *shared], roots[:4], roots[4:], edges))
    assert meta["occurrences_reutilisees_par_niveau"] == {
        level: 7 for level in range(2, 122)
    }
    assert meta["pages_concernees_par_reutilisation_au_niveau"] == {
        level: [shared[level - 2]] for level in range(2, 122)
    }
