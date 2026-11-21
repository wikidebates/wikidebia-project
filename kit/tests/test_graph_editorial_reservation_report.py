"""Read-only placement reservations and signed keep-decision regression tests."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from wikidebia_corpus_build import (
    REQUIRED_ATTESTATIONS,
    placement_reservations_report,
    placement_reservations_text,
    placement_review_issues,
    review_sha256,
    PLACEMENT_RESERVATIONS_JSON,
    PLACEMENT_RESERVATIONS_TXT,
)
from wikidebia_corpus_review import _write_placement_reservations


def example():
    """The same argument occurs in two branches, with distinct link roles."""
    registry = {
        "debate": {
            "id": "immigration",
            "pages": {"fr": {"canonical_title": "Faut-il accepter l’immigration ?"}},
        },
        "graph": {
            "nodes": [
                {"id": "A1", "status": "active", "fr": {"canonical_title": "Première thèse"}},
                {"id": "A2", "status": "active", "fr": {"canonical_title": "Argument partagé"}},
                {"id": "A3", "status": "active", "fr": {"canonical_title": "Thèse opposée"}},
            ],
            "edges": [
                {"id": "E2", "status": "active", "relation": "justification"},
                {"id": "E4", "status": "active", "relation": "objection"},
            ],
            "occurrences": [
                {"id": "O1", "node_id": "A1", "depth": 1, "branch": "pro",
                 "parent_occurrence_id": None, "edge_id": None},
                {"id": "O2", "node_id": "A2", "depth": 2, "branch": "pro",
                 "parent_occurrence_id": "O1", "edge_id": "E2",
                 "editorial_reservation": {"reason": "La citation ne développe qu'une partie de l'argument"}},
                {"id": "O3", "node_id": "A3", "depth": 1, "branch": "con",
                 "parent_occurrence_id": None, "edge_id": None},
                {"id": "O4", "node_id": "A2", "depth": 2, "branch": "con",
                 "parent_occurrence_id": "O3", "edge_id": "E4",
                 "editorial_reservation": {"reason": "Le lien vise une objection distincte"}},
            ],
        },
    }
    entries = []
    for occurrence in registry["graph"]["occurrences"]:
        root = occurrence["depth"] == 1
        entry = {
            "occurrence_id": occurrence["id"],
            "node_id": occurrence["node_id"],
            "declared_depth": occurrence["depth"],
            "placement_status": "pending",
            "direct_fit": False,
            "rationale": "",
            "declared_function": "main_argument" if root else (
                "justification" if occurrence["edge_id"] == "E2" else "objection"
            ),
            "semantic_target": "debate" if root else occurrence["parent_occurrence_id"],
            "correction": {"action": "none"},
        }
        if root:
            entry["main_argument_review"] = {
                "direct_answer_to_debate": False,
                "autonomous_without_parent": False,
                "organizes_distinct_argument_family": False,
                "more_general_nonduplicate_parent_available": None,
                "principally_supports_or_attacks_specific_argument": None,
                "principally_example_or_specialization": None,
            }
        else:
            entry["subordinate_review"] = {
                "parent_is_best_immediate_target": False,
                "relation_to_parent_explicit": False,
            }
        entries.append(entry)
    return registry, {"debate_id": "immigration", "entries": entries}


def approve(placement):
    for entry in placement["entries"]:
        entry["placement_status"] = "approved"
        entry["direct_fit"] = True
        entry["rationale"] = "Ce lien reste pertinent dans son contexte immédiat, sans modifier l'argument partagé."
        if "main_argument_review" in entry:
            entry["main_argument_review"].update({
                "direct_answer_to_debate": True,
                "autonomous_without_parent": True,
                "organizes_distinct_argument_family": True,
                "more_general_nonduplicate_parent_available": False,
                "principally_supports_or_attacks_specific_argument": False,
                "principally_example_or_specialization": False,
            })
        else:
            entry["subordinate_review"].update({
                "parent_is_best_immediate_target": True,
                "relation_to_parent_explicit": True,
            })


def signed_approved():
    envelope = {
        "decision": "approved",
        "reviewer": "Relecteur attesté",
        "reviewed_at": "2026-11-21T12:00:00+00:00",
        "attestations": {key: True for key in REQUIRED_ATTESTATIONS},
        "blocking_issues": [],
    }
    envelope["review_sha256"] = review_sha256(envelope)
    return envelope


def test_explicit_reservation_first_shows_parent_child_role_and_required_decision():
    registry, placement = example()
    before = copy.deepcopy(registry), copy.deepcopy(placement)
    report = placement_reservations_report(registry, placement)
    assert report["summary"] == {"arbitrations": 2, "routine": 2, "attested_maintains": 0, "total": 4}
    cases = report["cases"]
    assert [row["occurrence_id"] for row in cases[:2]] == ["O2", "O4"]
    assert cases[0]["parent_argument"] == "Première thèse"
    assert cases[0]["argument"] == "Argument partagé"
    assert cases[0]["link_role"] == "justification"
    assert cases[0]["reason"] == "La citation ne développe qu'une partie de l'argument"
    assert "Arbitrer" in cases[0]["decision_requested"]
    assert cases[1]["parent_argument"] == "Thèse opposée"
    assert cases[1]["link_role"] == "objection"
    root = next(x for x in cases if x["occurrence_id"] == "O1")
    assert root["parent_argument"] == "Faut-il accepter l’immigration ?"
    assert root["link_role"] == "argument principal pro"
    assert (registry, placement) == before


def test_readable_report_includes_every_required_editorial_field():
    registry, placement = example()
    report = placement_reservations_report(registry, placement)
    text = placement_reservations_text(report)
    for label in ("Argument parent :", "Argument concerné :", "Rôle du lien :", "Motif :", "Décision demandée :"):
        assert label in text
    assert text.index("ARBITRAGES PRIORITAIRES") < text.index("CONTRÔLES ORDINAIRES")
    assert "La citation ne développe qu'une partie" in text


def test_signed_keep_retains_each_original_reservation_without_graph_mutations():
    registry, placement = example()
    approve(placement)
    assert placement_review_issues(placement, registry) == []
    original = copy.deepcopy(registry), copy.deepcopy(placement)
    envelope = signed_approved()
    report = placement_reservations_report(registry, placement, envelope)
    assert report["summary"]["attested_maintains"] == 4
    assert report["summary"]["arbitrations"] == 0
    by_occurrence = {row["occurrence_id"]: row for row in report["cases"]}
    for oid, reason in (
        ("O2", "La citation ne développe qu'une partie de l'argument"),
        ("O4", "Le lien vise une objection distincte"),
    ):
        case = by_occurrence[oid]
        assert case["priority"] == "maintien_atteste"
        assert case["original_reservation"]["reason"] == reason
        assert case["attesting_review_sha256"] == envelope["review_sha256"]
        assert case["current_correction_action"] == "none"
    assert report["no_automatic_graph_mutation"] is True
    assert (registry, placement) == original


def test_forged_or_incomplete_approval_never_reuses_keep_decision():
    registry, placement = example()
    approve(placement)
    forged = signed_approved()
    forged["review_sha256"] = "0" * 64
    report = placement_reservations_report(registry, placement, forged)
    assert report["source_review_attested"] is False
    assert report["summary"]["arbitrations"] == 2
    incomplete = signed_approved()
    incomplete["attestations"]["reuse_and_occurrences_reviewed"] = False
    incomplete["review_sha256"] = review_sha256(incomplete)
    report = placement_reservations_report(registry, placement, incomplete)
    assert report["summary"]["attested_maintains"] == 0


def test_unapproved_relation_fit_cannot_be_reused_even_with_valid_hash():
    registry, placement = example()
    approve(placement)
    placement["entries"][1]["direct_fit"] = False
    report = placement_reservations_report(registry, placement, signed_approved())
    assert report["source_review_attested"] is False
    assert report["summary"]["attested_maintains"] == 0


def test_report_files_are_written_without_editing_review_or_registry(tmp_path: Path):
    registry, placement = example()
    envelope = {"decision": "pending", "blocking_issues": []}
    original = copy.deepcopy(registry), copy.deepcopy(placement), copy.deepcopy(envelope)
    output = _write_placement_reservations(tmp_path, registry, placement, envelope)
    assert output["schema"] == "wikidebia-graph-placement-reservations-report-1.0"
    assert (tmp_path / PLACEMENT_RESERVATIONS_JSON).is_file()
    report_text = (tmp_path / PLACEMENT_RESERVATIONS_TXT).read_text(encoding="utf-8")
    assert "Argument partagé" in report_text
    assert "ARBITRAGES PRIORITAIRES" in report_text
    assert (registry, placement, envelope) == original
