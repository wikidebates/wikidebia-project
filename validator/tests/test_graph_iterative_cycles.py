"""Depth-first cycle reporting must be stable and safe past Python recursion limits."""
from __future__ import annotations

import copy
import json
import random
import sys
from pathlib import Path

import pytest

from wikidebia_validator.graph import (
    _iter_cycle_paths,
    compute_derived,
    structural_sha256,
)
from wikidebia_validator.validator import validate_package

from .helpers import create_graph_package, dump, graph_projection


def _recursive_oracle(node_ids: list[str], outgoing: dict[str, list[str]]) -> list[list[str]]:
    """Original recursive DFS, used only for bounded test graphs."""
    colors = {name: 0 for name in node_ids}
    stack: list[str] = []
    cycles: list[list[str]] = []

    def visit(name: str) -> None:
        colors[name] = 1
        stack.append(name)
        for child in outgoing.get(name, []):
            if colors.get(child) == 0:
                visit(child)
            elif colors.get(child) == 1:
                start = stack.index(child) if child in stack else 0
                cycles.append(stack[start:] + [child])
        stack.pop()
        colors[name] = 2

    for name in sorted(node_ids):
        if colors[name] == 0:
            visit(name)
    return cycles


@pytest.mark.parametrize("arcs", [
    [],
    [("A", "A")],
    [("A", "B"), ("B", "C"), ("C", "A")],
    [("A", "B"), ("A", "B"), ("B", "A")],
    [("B", "A"), ("A", "B"), ("C", "D"), ("D", "C")],
    [("A", "C"), ("A", "B"), ("B", "C"), ("C", "B")],
    [("C", "Outside"), ("C", "B"), ("B", "A")],
])
def test_iterative_dfs_matches_original_cycle_order(arcs):
    nodes = ["A", "B", "C", "D", "E"]
    outgoing = {name: [] for name in nodes}
    for parent, child in arcs:
        outgoing[parent].append(child)
    assert list(_iter_cycle_paths(dict.fromkeys(nodes), outgoing)) == _recursive_oracle(
        nodes, outgoing
    )


@pytest.mark.parametrize("seed", range(5))
def test_deterministic_random_cyclic_graphs_match_original_reporting(seed):
    rng = random.Random(seed)
    nodes = [f"N{i:03d}" for i in range(38)]
    outgoing = {name: [] for name in nodes}
    for parent in nodes:
        for _ in range(rng.randrange(0, 5)):
            outgoing[parent].append(rng.choice(nodes))
    assert list(_iter_cycle_paths(dict.fromkeys(nodes), outgoing)) == _recursive_oracle(
        nodes, outgoing
    )


def _deep_package(root: Path, *, chain_length: int, add_cycle: bool = False) -> None:
    """Extend a standard valid package with an unbounded, fully formed chain."""
    create_graph_package(root)
    registry_path = root / "data/registre_debat.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    graph = registry["graph"]
    exemplar = graph["nodes"][0]
    previous_node = "A0001"
    previous_occurrence = "O00001"
    graph["occurrences"][0]["render_children"] = True

    for number in range(3, chain_length + 3):
        node_id = f"A{number:05d}"
        previous_id = f"A{number - 1:05d}"
        node = copy.deepcopy(exemplar)
        node["id"] = node_id
        node["fr"]["canonical_title"] = f"La mesure X apporte un résultat argumentatif numéro {number}"
        node["fr"]["displayed_title"] = f"Résultat argumentatif {number}"
        node["pages"]["fr"]["file"]["path"] = f"output/fr/arguments/{node_id}.wiki"
        node["pages"]["en"]["file"]["path"] = f"output/en/arguments/{node_id}.wiki"
        graph["nodes"].append(node)

        edge_id = f"E{number - 2:05d}"
        graph["edges"].append({
            "id": edge_id, "parent_node_id": previous_node, "child_node_id": node_id,
            "relation": "justification", "order": 1, "status": "active",
        })
        next_occurrence = f"O{number:05d}"
        graph["occurrences"].append({
            "id": next_occurrence, "node_id": node_id,
            "parent_occurrence_id": previous_occurrence, "edge_id": edge_id,
            "branch": "pro", "depth": number - 1, "order": 1,
            "occurrence_role": "primary", "render_children": number < chain_length + 2,
        })
        previous_node = node_id
        previous_occurrence = next_occurrence

    if add_cycle:
        graph["edges"].append({
            "id": "E99999", "parent_node_id": previous_node,
            "child_node_id": "A0001", "relation": "objection",
            "order": 2, "status": "active",
        })
    graph["depth_policy"]["maximum_observed"] = max(
        occ["depth"] for occ in graph["occurrences"]
    )
    counts, per_node = compute_derived(registry)
    graph["derived_counts"] = counts
    for node in graph["nodes"]:
        node["derived"] = per_node[node["id"]]
    graph["lifecycle"]["structural_sha256"] = structural_sha256(registry)
    dump(registry_path, registry)
    dump(root / "graph/graphe_argumentatif.json", graph_projection(registry))


def test_unbounded_deep_graph_is_validated_without_internal_recursion_error(tmp_path):
    length = max(1150, sys.getrecursionlimit() + 50)
    _deep_package(tmp_path, chain_length=length)
    report = validate_package(tmp_path, scopes=["graph"])
    assert not any(f.code == "WDV-INT-001" for f in report.findings), report.to_text()
    assert report.errors == 0, report.to_text()
    assert report.metrics["graph"]["maximum_depth"] == length + 1
    assert report.metrics["graph"]["distinct_nodes"] == length + 2


def test_deep_cycle_reports_graph_error_not_internal_error(tmp_path):
    _deep_package(tmp_path, chain_length=1150, add_cycle=True)
    report = validate_package(tmp_path, scopes=["graph"])
    codes = [f.code for f in report.findings if f.level == "ERROR"]
    assert "WDV-GRA-005" in codes, report.to_text()
    assert "WDV-INT-001" not in codes, report.to_text()
    cycle = next(f.message for f in report.findings if f.code == "WDV-GRA-005")
    assert cycle.startswith("Cycle détecté : A0001 -> A00003")
    assert cycle.endswith(" -> A0001")


def test_original_dfs_does_not_skip_disconnected_or_parallel_cycles():
    nodes = ["B", "A", "D", "C", "E"]
    outgoing = {
        "A": ["B", "B"],
        "B": ["A", "A"],
        "C": ["D"],
        "D": ["C", "D"],
        "E": [],
    }
    cycles = list(_iter_cycle_paths(dict.fromkeys(nodes), outgoing))
    assert cycles == _recursive_oracle(nodes, outgoing)
    assert cycles == [["A", "B", "A"], ["A", "B", "A"], ["C", "D", "C"], ["D", "D"]]
