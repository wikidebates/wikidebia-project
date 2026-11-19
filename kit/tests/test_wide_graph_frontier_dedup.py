"""Broad graph-extraction frontiers keep stable order with O(1) dedup checks."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import wikidebia_graph_extract as graph_extract


class FakeBatchClient:
    def __init__(self, pages, aliases=None):
        self.pages = pages
        self.aliases = aliases or {}
        self.batches = []

    def fetch(self, title):
        name = self.aliases.get(title, title)
        if name not in self.pages:
            raise graph_extract.PageMissingError(title)
        return graph_extract.PageRecord(
            requested_title=title, canonical_title=name,
            text=self.pages[name], url=f"https://example.invalid/wiki/{name}",
            revision_id=1,
        )

    def fetch_many(self, titles):
        self.batches.append(tuple(titles))
        results = {}
        for title in titles:
            try:
                results[title] = self.fetch(title)
            except graph_extract.PageMissingError:
                pass
        return results


def _leaf():
    return "{{Argument|justifications=|objections=}}"


def _debate(*, pro=(), con=()):
    return (
        "{{Débat|arguments-pour="
        + "".join(f"{{{{Argument pour|page={title}}}}}" for title in pro)
        + "|arguments-contre="
        + "".join(f"{{{{Argument contre|page={title}}}}}" for title in con)
        + "}}"
    )


def test_repeated_canonical_roots_keep_first_order_in_each_orientation():
    pages = {
        "Débat test": _debate(pro=("Alias A", "A", "B", "Alias A"), con=("Alias A", "A")),
        "A": _leaf(), "B": _leaf(),
    }
    client = FakeBatchClient(pages, aliases={"Alias A": "A"})
    result = graph_extract.crawl_graph(
        client, debate_title="Débat test", progress_every=0,
    )
    assert result.roots_pro == ["A", "B"]
    assert result.roots_con == ["A"]
    assert list(result.parsed_arguments) == ["A", "B"]
    assert [batch for batch in client.batches if batch] == [("Alias A", "A", "B"),]
    assert len(result.relations) == 0
    assert graph_extract.analyze_graph(result)["metadata"]["pages_arguments_uniques"] == 2


def test_shared_child_is_fetched_and_parsed_once_but_keeps_both_edges():
    pages = {
        "Débat test": _debate(pro=("A", "B")),
        "A": "{{Argument|justifications={{Justification|page=C}}|objections=}}",
        "B": "{{Argument|justifications={{Justification|page=C}}|objections=}}",
        "C": _leaf(),
    }
    client = FakeBatchClient(pages)
    result = graph_extract.crawl_graph(client, debate_title="Débat test", progress_every=0)
    assert list(result.parsed_arguments) == ["A", "B", "C"]
    assert { (edge.source, edge.target) for edge in result.relations } == {
        ("A", "C"), ("B", "C"),
    }
    assert [batch for batch in client.batches if batch] == [("A", "B"), ("C",)]
    assert graph_extract.analyze_graph(result)["metadata"]["relations_uniques"] == 2


def test_wide_root_frontier_keeps_all_pages_in_source_order():
    names = [f"Argument {i:04d}" for i in range(1, 201)]
    pages = {"Débat test": _debate(pro=names), **{n:_leaf() for n in names}}
    client = FakeBatchClient(pages)
    result = graph_extract.crawl_graph(client, debate_title="Débat test", progress_every=0)
    assert result.roots_pro == names
    assert list(result.parsed_arguments) == names
    assert client.batches[0] == tuple(names)
    assert len(result.parsed_arguments) == 200


def test_wide_child_frontier_remains_single_batched_level():
    names = [f"Argument {i:04d}" for i in range(1, 201)]
    pages = {
        "Débat test": _debate(pro=("Racine",)),
        "Racine": "{{Argument|justifications="
        + "".join(f"{{{{Justification|page={n}}}}}" for n in names)
        + "|objections=}}",
        **{n:_leaf() for n in names},
    }
    client = FakeBatchClient(pages)
    result = graph_extract.crawl_graph(client, debate_title="Débat test", progress_every=0)
    assert result.roots_pro == ["Racine"]
    assert list(result.parsed_arguments) == ["Racine", *names]
    assert [batch for batch in client.batches if batch] == [("Racine",), tuple(names)]
    assert len(result.relations) == 200


def test_max_pages_still_rejects_oversized_frontier_before_processing():
    names = [f"Argument {i:04d}" for i in range(1, 81)]
    pages = {"Débat test": _debate(pro=names), **{n:_leaf() for n in names}}
    with pytest.raises(RuntimeError, match="Limite de sécurité atteinte"):
        graph_extract.crawl_graph(
            FakeBatchClient(pages), debate_title="Débat test",
            max_pages=50, progress_every=0,
        )


def test_missing_page_provenance_not_suppressed_by_set_deduplication():
    pages = {"Débat test": _debate(pro=("A", "Missing", "A")), "A": _leaf()}
    client = FakeBatchClient(pages)
    result = graph_extract.crawl_graph(
        client, debate_title="Débat test", allow_missing=True,
        progress_every=0,
    )
    assert result.roots_pro == ["A", "Missing"]
    assert result.missing_pages == ["Missing"]
    assert len(result.missing_page_provenance) == 1
    assert result.missing_page_provenance[0]["parent"] == "Débat test"
