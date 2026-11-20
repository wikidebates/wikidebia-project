"""Parser hot-path optimization must preserve the legacy state machine exactly.

This file retains an independent oracle taken from the pre-optimization
implementation. It covers malformed/nested wikitext as well as complete page
metadata extraction, so performance work cannot silently change parse results.
"""
from __future__ import annotations

import random
from unittest.mock import patch

import pytest

import wikidebia_graph_extract as graph
from wikidebia_corpus_init import extract_page_metadata


def _legacy_template_spans(text: str) -> list[tuple[int, int]]:
    stack: list[tuple[int, int]] = []
    spans: list[tuple[int, int]] = []
    i = 0
    while i < len(text):
        if text.startswith("{{{", i):
            stack.append((3, i))
            i += 3
            continue
        if text.startswith("{{", i):
            stack.append((2, i))
            i += 2
            continue
        if text.startswith("}}}", i) and stack and stack[-1][0] == 3:
            stack.pop()
            i += 3
            continue
        if text.startswith("}}", i) and stack and stack[-1][0] == 2:
            _, start = stack.pop()
            spans.append((start, i + 2))
            i += 2
            continue
        i += 1
    return sorted(spans, key=lambda item: (item[0], item[1] - item[0]))


def _legacy_split_top_level(text: str, delimiter: str, maxsplit: int = -1) -> list[str]:
    parts: list[str] = []
    start = 0
    splits = 0
    template_stack: list[int] = []
    wikilink_depth = 0
    i = 0
    while i < len(text):
        if text.startswith("{{{", i):
            template_stack.append(3)
            i += 3
            continue
        if text.startswith("{{", i):
            template_stack.append(2)
            i += 2
            continue
        if text.startswith("}}}", i) and template_stack and template_stack[-1] == 3:
            template_stack.pop()
            i += 3
            continue
        if text.startswith("}}", i) and template_stack and template_stack[-1] == 2:
            template_stack.pop()
            i += 2
            continue
        if text.startswith("[[", i):
            wikilink_depth += 1
            i += 2
            continue
        if text.startswith("]]", i) and wikilink_depth:
            wikilink_depth -= 1
            i += 2
            continue
        if (
            text.startswith(delimiter, i)
            and not template_stack
            and wikilink_depth == 0
            and (maxsplit < 0 or splits < maxsplit)
        ):
            parts.append(text[start:i])
            i += len(delimiter)
            start = i
            splits += 1
            continue
        i += 1
    parts.append(text[start:])
    return parts


CASES = (
    "{{Argument|résumé=Texte [[Lien|affiché]] et {{Citation|a|b=c}}|rubriques=Science}}",
    "{{Débat|sujet=Le sujet|arguments-pour={{Argument pour|page=[[Titre|Autre]]}}}}",
    "{{{paramètre|{{Modèle|clé=valeur}}}}}",
    "Texte <!-- {{Faux|page=Invalide}} --> {{Argument|rubriques=Éthique}}",
    "{{Argument|résumé=avec {{{clé|valeur}}} et [[lien|label]]}}",
    "texte {{ incomplet [[lien non fermé | valeur }} autre",
    "{{{{{{A|B=C}}}}}}|fin ]] [[",
    "}}} }} [[ ][ {{|||}} == | = }}}} {{{{",
    "|=||[[a|b]]{{c|d=e}}|||fin",
    "a" * 2048 + "{{Argument|résumé=" + "b" * 2048 + "|rubriques=Science}}",
)


@pytest.mark.parametrize("text", CASES)
def test_realistic_and_malformed_template_and_metadata_parity(text: str):
    assert graph._template_spans(text) == _legacy_template_spans(text)
    for delimiter in ("|", "=", "||", "::", "[[", "}}", "é"):
        for limit in (-2, -1, 0, 1, 2, 3, 5):
            assert graph._split_top_level(text, delimiter, limit) == (
                _legacy_split_top_level(text, delimiter, limit)
            )
    with (
        patch.object(graph, "_template_spans", _legacy_template_spans),
        patch.object(graph, "_split_top_level", _legacy_split_top_level),
    ):
        historical = graph.iter_templates(text)
        argument_meta = None
        if "Argument" in text:
            try:
                argument_meta = ("ok", extract_page_metadata(text))
            except Exception as error:
                argument_meta = ("error", type(error).__name__, str(error))
    assert graph.iter_templates(text) == historical
    if argument_meta is not None:
        try:
            actual = ("ok", extract_page_metadata(text))
        except Exception as error:
            actual = ("error", type(error).__name__, str(error))
        assert actual == argument_meta


@pytest.mark.parametrize("seed", range(24))
def test_seeded_malformed_and_nested_differential_parser(seed: int):
    rng = random.Random(104979 + seed)
    alphabet = ["{", "}", "[", "]", "|", "=", "a", "z", " ", "\n", "é", "#", "<", ">"]
    delimiters = ("|", "=", "||", "::", "[[", "}}", "é", "a")
    for _ in range(48):
        size = rng.randrange(0, 180)
        text = "".join(rng.choices(alphabet, k=size))
        assert graph._template_spans(text) == _legacy_template_spans(text)
        delimiter = rng.choice(delimiters)
        maxsplit = rng.choice((-2, -1, 0, 1, 2, 4))
        assert graph._split_top_level(text, delimiter, maxsplit) == (
            _legacy_split_top_level(text, delimiter, maxsplit)
        )
        with (
            patch.object(graph, "_template_spans", _legacy_template_spans),
            patch.object(graph, "_split_top_level", _legacy_split_top_level),
        ):
            historical = graph.iter_templates(text)
        assert graph.iter_templates(text) == historical


def test_empty_delimiter_fails_fast_instead_of_looping_forever():
    with pytest.raises(ValueError, match="séparateur"):
        graph._split_top_level("texte", "")


@pytest.mark.parametrize("maxsplit", [0, 1, 2])
def test_bounded_split_never_scans_a_tail_after_its_last_allowed_delimiter(maxsplit: int):
    """Large historical summaries must stay intact after a key=value split."""
    class TrackedText(str):
        reads = 0

        def __getitem__(self, key):
            if isinstance(key, int):
                self.reads += 1
            return super().__getitem__(key)

    prefix = "key=" if maxsplit == 1 else ("one|two|" if maxsplit == 2 else "")
    tail = ("texte \u00e9clairci [[A|affich\u00e9]] {{Mod\u00e8le|a=b}} "
            + "x" * 20000 + "}}} {{|=||[[") * 2
    source = TrackedText(prefix + tail)
    delimiter = "=" if maxsplit == 1 else "|"
    expected = _legacy_split_top_level(source, delimiter, maxsplit)
    assert graph._split_top_level(source, delimiter, maxsplit) == expected
    assert source.reads <= len(prefix) + 4


def test_bounded_split_keeps_unmatched_or_nested_rest_verbatim():
    suffix = "}}} {{broken|a=b [[unterminated | x " + ("*" * 8192)
    examples = (
        ("nom=" + suffix, "=", 1),
        ("name=[[a|b]]|value=" + suffix, "|", 1),
        ("one|two|" + suffix, "|", 2),
        ("word[[a=b]]|" + suffix, "|", 1),
        ("no separator " + suffix, "=", 1),
    )
    for text, delimiter, maxsplit in examples:
        assert graph._split_top_level(text, delimiter, maxsplit) == (
            _legacy_split_top_level(text, delimiter, maxsplit)
        )


@pytest.mark.parametrize("delimiter", ["|", "=", "||"])
def test_zero_split_returns_identical_string_without_any_character_scans(delimiter: str):
    class NoIndexText(str):
        def __getitem__(self, key):
            raise AssertionError("zero-split path must not scan the string")

    text = NoIndexText("{{{not closed [[strange ]] |= " + "z" * 30000)
    assert graph._split_top_level(text, delimiter, maxsplit=0) == [text]
    assert _legacy_split_top_level(text, delimiter, maxsplit=0) == [text]
