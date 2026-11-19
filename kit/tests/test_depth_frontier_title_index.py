"""Bounded-depth aliases remain semantically identical with a linear fallback index."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import wikidebia_corpus_init as corpus


def policy(frontiers, titles, *, depth=4):
    graph = {
        "metadata": {
            "limite_profondeur": depth,
            "relations_ignorees_limite_profondeur": 7,
        },
        "frontières_profondeur": frontiers,
    }
    return corpus._depth_policy(graph, titles, maximum_observed=6)


def test_bounded_frontier_exact_match_keeps_priority_over_normalized_alias():
    result = policy({"A B": 1}, {"A_B": "A0001", "A B": "A0002"})
    assert result["frontier_node_ids"] == ["A0002"]
    assert result["maximum_edge_depth"] == 4
    assert result["relations_omitted_at_frontier"] == 7


def test_bounded_frontier_first_normalized_collision_wins():
    result = policy({"A B": 1}, {"A_B": "A0001", "A__B": "A0002"})
    assert result["frontier_node_ids"] == ["A0001"]


@pytest.mark.parametrize("invalid_before_match", [True, False])
def test_bounded_frontier_malformed_source_keeps_old_exception_order(
    invalid_before_match: bool,
):
    titles = (
        {"": "A0001", "A_B": "A0002"}
        if invalid_before_match
        else {"A_B": "A0001", "": "A0002"}
    )
    if invalid_before_match:
        with pytest.raises(corpus.CorpusInitError, match="Titre vide après normalisation"):
            policy({"A B": 1}, titles)
    else:
        assert policy({"A B": 1}, titles)["frontier_node_ids"] == ["A0001"]


def test_unknown_bounded_frontier_is_rejected_without_fallback_guessing():
    with pytest.raises(corpus.CorpusInitError, match="Frontière de profondeur sans nœud actif"):
        policy({"Other": 1}, {"A_B": "A0001"})


def test_bounded_frontiers_deduplicate_and_sort_node_identifiers():
    frontiers = {"C D": 1, "A B": 1, "A_B": 2}
    mapping = {"A_B": "A0001", "C_D": "A0003"}
    result = policy(frontiers, mapping)
    assert result == {
        "limit_policy": "bounded",
        "maximum_observed": 6,
        "maximum_edge_depth": 4,
        "frontier_node_ids": ["A0001", "A0003"],
        "relations_omitted_at_frontier": 7,
    }


def test_unbounded_policy_never_normalizes_titles(monkeypatch):
    monkeypatch.setattr(
        corpus, "normalize_title",
        lambda *_args: pytest.fail("Unbounded policy must not normalize titles"),
    )
    assert corpus._depth_policy({"metadata": {}}, {"": "A0001"}, 8) == {
        "limit_policy": "unbounded", "maximum_observed": 8,
    }


def test_repeated_bounded_frontier_aliases_have_linear_normalization_calls(monkeypatch):
    titles = {f"Argument_{i:04d}": f"A{i:04d}" for i in range(1, 601)}
    frontiers = {f"Argument {i:04d}": 1 for i in range(1, 601)}
    original = corpus.normalize_title
    calls = []

    def count(value):
        calls.append(value)
        return original(value)

    monkeypatch.setattr(corpus, "normalize_title", count)
    actual = policy(frontiers, titles)
    assert len(actual["frontier_node_ids"]) == 600
    assert len(calls) <= 2 * len(frontiers) + 2


def test_invalid_frontier_structure_is_still_rejected():
    graph = {"metadata": {"limite_profondeur": 3}, "frontières_profondeur": ["wrong"]}
    with pytest.raises(corpus.CorpusInitError, match="Frontières de profondeur invalides"):
        corpus._depth_policy(graph, {}, 2)
