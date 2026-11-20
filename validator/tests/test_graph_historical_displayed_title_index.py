"""Historical French displayed titles keep exact lock/first-entry semantics."""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from wikidebia_validator.graph import (
    _locked_preexisting_displayed_title,
    structural_sha256,
)
from wikidebia_validator.package import PackageContext
from wikidebia_validator.report import Report
from wikidebia_validator.validator import validate_package

from .helpers import create_graph_package, dump, graph_projection
from .test_graph_iterative_cycles import _deep_package


LOCK_PATH = "data/fr_page_metadata_lock.json"
LOCK_SCHEMA = "wikidebia-fr-page-metadata-lock-1.0"


def _row(number, *, origin="preexisting", decision="keep", displayed=None):
    return {
        "entity_id": f"A{number:05d}",
        "page_origin": origin,
        "decisions": {"displayed_title": decision},
        "displayed_title": displayed if displayed is not None else f"L’affirmation historique {number}",
    }


def _context(root: Path, arguments, *, schema=LOCK_SCHEMA):
    create_graph_package(root)
    dump(root / LOCK_PATH, {"schema": schema, "arguments": arguments})
    return PackageContext(root, Report("test", root.name, ["graph"]))


def _lookup(ctx, number, *, value=None, language="fr", memo=None):
    title = value if value is not None else f"L’affirmation historique {number}"
    return _locked_preexisting_displayed_title(
        ctx, f"A{number:05d}", language, title, _entry_index=memo,
    )


def test_many_matching_historical_entries_are_accepted_and_indexed(tmp_path):
    ctx = _context(tmp_path, [_row(n) for n in range(1, 121)])
    memo = {}
    for number in (1, 48, 120, 6, 99):
        assert _lookup(ctx, number, memo=memo)
        assert _lookup(ctx, number, memo=memo) == _lookup(ctx, number)
    assert len(memo["rows"]) == 120
    assert ctx.report.errors == 0


def test_duplicate_historical_id_first_row_remains_authoritative(tmp_path):
    arguments = [_row(1, origin="new")] + [_row(n) for n in range(2, 90)]
    arguments.append(_row(1, origin="preexisting"))
    ctx = _context(tmp_path, arguments)
    memo = {}
    assert not _lookup(ctx, 1, memo=memo)
    assert not _lookup(ctx, 1)
    assert memo["rows"]["A00001"] is ctx.load_json(LOCK_PATH)["arguments"][0]


def test_duplicate_historical_id_keeps_first_displayed_title(tmp_path):
    arguments = [_row(1, displayed="L’autre titre historique")] + [
        _row(n) for n in range(2, 65)
    ]
    arguments.append(_row(1))
    ctx = _context(tmp_path, arguments)
    assert not _lookup(ctx, 1, memo={})
    assert not _lookup(ctx, 1)
    assert _lookup(ctx, 1, value="L’autre titre historique", memo={})


@pytest.mark.parametrize("origin,decision", [
    ("new", "keep"),
    ("preexisting", "modify"),
    ("preexisting", "review"),
])
def test_nonhistorical_or_nonpreserved_title_is_never_exempted(
    tmp_path, origin, decision,
):
    ctx = _context(
        tmp_path, [_row(1, origin=origin, decision=decision)]
        + [_row(n) for n in range(2, 90)],
    )
    assert not _lookup(ctx, 1, memo={})


def test_english_title_uses_historical_immediate_rejection(tmp_path):
    ctx = _context(tmp_path, [_row(n) for n in range(1, 90)])
    memo = {}
    assert not _lookup(ctx, 1, language="en", memo=memo)
    assert memo == {}


def test_invalid_lock_schema_never_grants_historical_exception(tmp_path):
    ctx = _context(tmp_path, [_row(n) for n in range(1, 90)], schema="invalid-schema")
    memo = {}
    assert not _lookup(ctx, 1, memo=memo)
    assert memo == {}


def test_missing_lock_keeps_rejection_without_internal_error(tmp_path):
    ctx = _context(tmp_path, [])
    (tmp_path / LOCK_PATH).unlink()
    assert not _lookup(ctx, 1, memo={})
    assert ctx.report.errors == 0


def test_small_lock_keeps_old_linear_lookup(tmp_path):
    ctx = _context(tmp_path, [_row(1), _row(2)])
    memo = {}
    assert _lookup(ctx, 2, memo=memo)
    assert memo == {}


def test_live_row_field_edit_is_seen_without_stale_decision(tmp_path):
    ctx = _context(tmp_path, [_row(n) for n in range(1, 90)])
    memo = {}
    assert _lookup(ctx, 1, memo=memo)
    ctx.load_json(LOCK_PATH)["arguments"][0]["decisions"]["displayed_title"] = "modify"
    assert not _lookup(ctx, 1, memo=memo)


def test_document_replacement_with_same_length_rebuilds_index(tmp_path):
    ctx = _context(tmp_path, [_row(n) for n in range(1, 90)])
    memo = {}
    assert _lookup(ctx, 1, memo=memo)
    new_lock = {"schema": LOCK_SCHEMA, "arguments": [_row(n) for n in range(1, 90)]}
    new_lock["arguments"][0]["page_origin"] = "new"
    ctx.cache[LOCK_PATH] = new_lock
    assert not _lookup(ctx, 1, memo=memo)


def test_arguments_list_growth_invalidates_index(tmp_path):
    ctx = _context(tmp_path, [_row(n) for n in range(2, 90)])
    memo = {}
    assert not _lookup(ctx, 1, memo=memo)
    ctx.load_json(LOCK_PATH)["arguments"].append(_row(1))
    assert _lookup(ctx, 1, memo=memo)


@pytest.mark.parametrize("seed", range(5))
def test_seeded_lock_rows_match_historical_linear_scan(seed, tmp_path):
    rng = random.Random(seed)
    arguments = [_row(n, origin=rng.choice(["preexisting", "new"]),
                      decision=rng.choice(["keep", "modify"]))
                 for n in range(1, 110)]
    arguments += [_row(rng.randrange(1, 110)) for _ in range(40)]
    rng.shuffle(arguments)
    ctx = _context(tmp_path, arguments)
    memo = {}
    for n in range(1, 120):
        assert _lookup(ctx, n, memo=memo) == _lookup(ctx, n)


def test_valid_historical_titles_pass_complete_graph_validation(tmp_path):
    _deep_package(tmp_path, chain_length=80)
    registry_path = tmp_path / "data/registre_debat.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    arguments = []
    for index, node in enumerate(registry["graph"]["nodes"], 1):
        node["fr"]["displayed_title"] = f"L’affirmation historique sur le débat {index}"
        arguments.append({
            "entity_id": node["id"], "page_origin": "preexisting",
            "decisions": {"displayed_title": "keep"},
            "displayed_title": node["fr"]["displayed_title"],
        })
    registry["graph"]["lifecycle"]["structural_sha256"] = structural_sha256(registry)
    dump(registry_path, registry)
    dump(tmp_path / "graph/graphe_argumentatif.json", graph_projection(registry))
    dump(tmp_path / LOCK_PATH, {"schema": LOCK_SCHEMA, "arguments": arguments})
    report = validate_package(tmp_path, scopes=["graph"])
    assert report.errors == 0, report.to_text()
    assert not any(f.code == "WDV-GRA-016" for f in report.findings)


def test_mismatched_locked_title_is_rejected_by_complete_graph_validation(tmp_path):
    _deep_package(tmp_path, chain_length=40)
    registry_path = tmp_path / "data/registre_debat.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    arguments = []
    for index, node in enumerate(registry["graph"]["nodes"], 1):
        node["fr"]["displayed_title"] = f"L’affirmation historique sur le débat {index}"
        arguments.append({
            "entity_id": node["id"], "page_origin": "preexisting",
            "decisions": {"displayed_title": "keep"},
            "displayed_title": node["fr"]["displayed_title"],
        })
    arguments[15]["displayed_title"] = "L’autre titre historique non conservé"
    registry["graph"]["lifecycle"]["structural_sha256"] = structural_sha256(registry)
    dump(registry_path, registry)
    dump(tmp_path / "graph/graphe_argumentatif.json", graph_projection(registry))
    dump(tmp_path / LOCK_PATH, {"schema": LOCK_SCHEMA, "arguments": arguments})
    report = validate_package(tmp_path, scopes=["graph"])
    title_errors = [f for f in report.findings if f.code == "WDV-GRA-016"]
    assert len(title_errors) == 1, report.to_text()
    assert title_errors[0].level == "ERROR"
    assert title_errors[0].pointer.endswith(
        f"/{registry['graph']['nodes'][15]['id']}/fr/displayed_title"
    )
