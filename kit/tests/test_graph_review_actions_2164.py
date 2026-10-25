from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TESTS = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))

import wikidebia_graph_actions as ga  # noqa: E402
import wikidebia_corpus_review as review  # noqa: E402
import wikidebia_corpus_build as common  # noqa: E402
from test_wikidebia_corpus_review import make_project  # noqa: E402


def _prepare_single_occurrence_merge(build: Path) -> tuple[str, str, str]:
    # Fixture has A0003 reused.  Merge A0001 into A0002 instead: both are roots,
    # unique and child-bearing, so first remove its child link to create a safe
    # leaf-like case for the action unit test.
    registry = json.loads((build / "data/registre_debat.json").read_text(encoding="utf-8"))
    graph = registry["graph"]
    # Remove A0001 -> A0003 from graph and source page for this local unit fixture.
    graph["edges"] = [e for e in graph["edges"] if e["parent_node_id"] != "A0001"]
    graph["occurrences"] = [o for o in graph["occurrences"] if not (o["node_id"] == "A0003" and o["parent_occurrence_id"] == "O00001")]
    # O00004 becomes primary occurrence for A0003.
    for o in graph["occurrences"]:
        if o["id"] == "O00004":
            o["occurrence_role"] = "primary"
    counts, per_node = ga.compute_derived(graph["nodes"], graph["edges"], graph["occurrences"])
    graph["derived_counts"] = counts
    for n in graph["nodes"]:
        n["derived"] = per_node[n["id"]]
    common.write_json(build / "data/registre_debat.json", registry)
    projection = json.loads((build / "graph/graphe_argumentatif.json").read_text(encoding="utf-8"))
    for key in ("nodes", "edges", "occurrences", "derived_counts"):
        projection[key] = graph[key]
    common.write_json(build / "graph/graphe_argumentatif.json", projection)
    a = build / "imports/fr/arguments/A0001.wiki"
    a.write_text(a.read_text(encoding="utf-8").replace("|justifications={{Justification|page=Argument C|titre-affiché=C soutient A}}", "|justifications="), encoding="utf-8")
    return "O00001", "A0001", "A0002"


def test_legacy_owner_phrase_becomes_merge_redirect() -> None:
    entry = {
        "occurrence_id": "O00050",
        "node_id": "A0050",
        "placement_status": "needs_merge",
        "rationale": "Suppression demandée explicitement par le propriétaire : retirer le nœud A0050, son unique occurrence O00050 et la relation E00038. A0033 est conservé comme argument substantiel.",
    }
    action = ga._legacy_action(entry)
    assert action == {
        "action": "merge_redirect",
        "occurrence_id": "O00050",
        "node_id": "A0050",
        "target_node_id": "A0033",
        "reason": entry["rationale"],
    }


def test_merge_redirect_removes_parent_link_and_requires_target_in_summary(tmp_path: Path) -> None:
    _project, build = make_project(tmp_path)
    oid, nid, target = _prepare_single_occurrence_merge(build)
    plan, desired, graph_result = ga.prepare_action_plan(build, "debat_test", [{
        "action": "merge_redirect", "occurrence_id": oid, "node_id": nid, "target_node_id": target,
    }])
    parent = next(x for x in plan["mutations"] if x["page_type"] == "debate")
    child = next(x for x in plan["mutations"] if x.get("page_id") == nid)
    assert "[[Argument B]]" in parent["edit_summary"]
    assert "Argument A" not in desired[parent["source_path"]]
    assert child["operation"] == "redirect"
    assert desired[child["source_path"]] == "#REDIRECTION [[Argument B]]\n"
    assert graph_result["removed_nodes"] == ["A0001"]


def _prepare_relation_preserving_merge(build: Path) -> None:
    registry = common.load_json(build / "data/registre_debat.json", "registre")
    graph = registry["graph"]
    graph["edges"] = [e for e in graph["edges"] if e["parent_node_id"] != "A0002"]
    graph["occurrences"] = [o for o in graph["occurrences"] if o["id"] != "O00004"]
    common.write_json(build / "data/registre_debat.json", registry)
    target = build / "imports/fr/arguments/A0002.wiki"
    text = target.read_text().replace("{{Justification|page=Argument C|titre-affiché=C soutient B}}", "")
    target.write_text(text)
    # The duplicate has exactly the retained page's content.
    (build / "imports/fr/arguments/A0003.wiki").write_text(text)


def test_merge_can_reuse_retained_page_at_same_relation_without_changing_label(tmp_path: Path) -> None:
    _project, build = make_project(tmp_path)
    _prepare_relation_preserving_merge(build)
    parent = build / "imports/fr/arguments/A0001.wiki"
    original = parent.read_text()
    target = (build / "imports/fr/arguments/A0002.wiki").read_bytes()
    action = {"action": "merge_redirect", "occurrence_id": "O00003", "node_id": "A0003",
              "target_node_id": "A0002", "preserve_parent_relation": True}
    plan, desired, result = ga.prepare_action_plan(build, "debat_test", [action])
    assert desired["imports/fr/arguments/A0001.wiki"] == original.replace("page=Argument C", "page=Argument B")
    assert desired["imports/fr/arguments/A0003.wiki"] == "#REDIRECTION [[Argument B]]\n"
    assert "imports/fr/arguments/A0002.wiki" not in desired
    assert (build / "imports/fr/arguments/A0002.wiki").read_bytes() == target
    assert parent.read_text() == original  # Preparing the plan is local/read-only.
    graph = result["new_graph"]
    assert result["removed_nodes"] == ["A0003"]
    assert result["removed_occurrences"] == []
    occ = next(o for o in graph["occurrences"] if o["id"] == "O00003")
    assert occ["node_id"] == "A0002" and occ["occurrence_role"] == "secondary"
    edge = next(e for e in graph["edges"] if e["id"] == occ["edge_id"])
    assert (edge["parent_node_id"], edge["child_node_id"], edge["relation"]) == ("A0001", "A0002", "justification")
    assert len([o for o in graph["occurrences"] if o["node_id"] == "A0002"]) == 2
    parent_mutation = next(m for m in plan["mutations"] if m.get("page_id") == "A0001")
    assert "[[Argument B]]" in parent_mutation["edit_summary"]
    registry = common.load_json(build / "data/registre_debat.json", "registre")
    registry["graph"] = {**registry["graph"], **graph}
    common.write_json(build / "data/registre_debat.json", registry)
    provenance = common.load_json(build / "data/import_provenance.json", "provenance")
    donor = next(r for r in provenance["pages"] if r.get("page_id") == "A0003")
    donor.update(status="pending_redirect", pending_redirect_target_node_id="A0002")
    common.write_json(build / "data/import_provenance.json", provenance)
    from wikidebia_translation_source import relation_labels_from_source
    labels = relation_labels_from_source(build)
    label = next(r for r in labels if (r["source_page_id"], r["target_node_id"]) == ("A0001", "A0002"))
    assert label["source_text"] == "C soutient A"


@pytest.mark.parametrize("target,keep", [("A0001", True), ("A0002", "true")])
def test_preserving_merge_refuses_self_relation_and_invalid_flag(tmp_path: Path, target, keep) -> None:
    _project, build = make_project(tmp_path)
    _prepare_relation_preserving_merge(build)
    with pytest.raises(ga.GraphActionError):
        ga.prepare_action_plan(build, "debat_test", [{
            "action": "merge_redirect", "occurrence_id": "O00003", "node_id": "A0003",
            "target_node_id": target, "preserve_parent_relation": keep,
        }])


def test_preserving_merge_refuses_root_occurrence(tmp_path: Path) -> None:
    _project, build = make_project(tmp_path)
    oid, nid, target = _prepare_single_occurrence_merge(build)
    with pytest.raises(ga.GraphActionError, match="subordonnée"):
        ga.prepare_action_plan(build, "debat_test", [{
            "action": "merge_redirect", "occurrence_id": oid, "node_id": nid,
            "target_node_id": target, "preserve_parent_relation": True,
        }])


def test_relation_change_moves_model_between_parameters_without_touching_child_page(tmp_path: Path) -> None:
    _project, build = make_project(tmp_path)
    plan, desired, graph_result = ga.prepare_action_plan(build, "debat_test", [{
        "action": "relation_change", "occurrence_id": "O00003", "node_id": "A0003",
        "new_parent_occurrence_id": "O00001", "new_relation": "objection",
    }])
    touched = [x for x in plan["mutations"] if x["operation"] == "update"]
    assert len(touched) == 1
    text = desired[touched[0]["source_path"]]
    assert "|justifications=" not in text
    assert "{{Objection|page=Argument C|titre-affiché=C soutient A}}" in text
    edge = next(e for e in graph_result["new_graph"]["edges"] if e["parent_node_id"] == "A0001" and e["child_node_id"] == "A0003")
    assert edge["relation"] == "objection"
    registry = common.load_json(build / "data/registre_debat.json", "registre")
    registry["graph"].update(graph_result["new_graph"])
    common.write_json(build / "data/registre_debat.json", registry)
    from wikidebia_translation_source import relation_labels_from_source
    labels = relation_labels_from_source(build)
    label = next(r for r in labels if (r["source_page_id"], r["target_node_id"]) == ("A0001", "A0003"))
    assert label["relation"] == "objection" and label["source_text"] == "C soutient A"


@pytest.mark.parametrize("has_unexpanded_children", [False, True])
def test_moved_frontier_requires_extraction_unless_source_is_terminal(tmp_path: Path, has_unexpanded_children) -> None:
    _project, build = make_project(tmp_path)
    graph = {"nodes": [{"id": "A0003", "derived": {"minimum_depth": 2}},
                       {"id": "A0002", "derived": {"minimum_depth": 3}}]}
    policy = {"limit_policy": "bounded", "maximum_edge_depth": 2,
              "frontier_node_ids": ["A0003", "A0002"]}
    if has_unexpanded_children:
        p = build / "imports/fr/arguments/A0003.wiki"
        p.write_text(p.read_text().replace("|objections=", "|objections={{Objection|page=Unexpanded}}"))
        with pytest.raises(ga.GraphActionError, match="extraction"):
            ga._refresh_terminal_frontiers(build, {}, graph, policy)
        assert policy["frontier_node_ids"] == ["A0003", "A0002"]
    else:
        ga._refresh_terminal_frontiers(build, {}, graph, policy)
        assert policy["frontier_node_ids"] == ["A0002"]


def test_successive_local_corrections_retain_pending_redirect_for_checkpoint(tmp_path: Path) -> None:
    project, build = make_project(tmp_path)
    oid, nid, target = _prepare_single_occurrence_merge(build)
    review.make_review_template(build, "debat_test", overwrite=True)
    path = build / common.PLACEMENT_REVIEW
    placement = common.load_json(path, "placements")
    next(r for r in placement["entries"] if r["occurrence_id"] == oid)["correction"] = {
        "action": "merge_redirect", "target_node_id": target,
    }
    common.write_json(path, placement)
    ga.apply_review_actions_locally(project, build, "debat_test")
    first = common.load_json(build / "reviews/graph_action_decisions.json", "décisions")
    review.make_review_template(build, "debat_test", overwrite=True)
    placement = common.load_json(path, "placements")
    next(r for r in placement["entries"] if r["node_id"] == "A0003")["correction"] = {
        "action": "relation_change", "new_relation": "objection",
    }
    common.write_json(path, placement)
    ga.apply_review_actions_locally(project, build, "debat_test")
    audit = common.load_json(build / "reviews/graph_action_decisions.json", "décisions")
    assert [a["action"] for a in audit["actions"]] == ["merge_redirect", "relation_change"]
    assert audit["previous_decision_sha256"] == first["decision_sha256"]
    assert audit["decision_sha256"] == ga._sha_object(audit, "decision_sha256")
    from wikidebia_french_checkpoint import _graph_migrations
    assert _graph_migrations(build, "debat_test")[0]["old_page_id"] == nid


class FakeRemote:
    def __init__(self, pages: dict[str, tuple[int, str]]) -> None:
        self.pages = dict(pages)
        self.deleted: list[tuple[str, str]] = []
        self.writes: list[tuple[str, str, str]] = []
        self.rev = 100
    def open_language(self, language, expected_user): pass
    def close_language(self): pass
    def assert_identity(self, expected_user): pass
    def user_rights(self): return {"edit", "delete"}
    def available_change_tags(self): return {"chatgpt"}
    def read_page(self, title):
        if title not in self.pages: return False, None, ""
        rev, text = self.pages[title]; return True, rev, text
    def write_page(self, *, title, text, summary, tags, expected_user, create_only, base_revision_id):
        assert not create_only and tags == ["chatgpt"]
        assert self.pages[title][0] == base_revision_id
        self.rev += 1; self.pages[title] = (self.rev, text); self.writes.append((title, text, summary)); return self.rev
    def read_revision(self, title, revision_id):
        rev, text = self.pages[title]
        if rev != revision_id: return None
        summary = next(s for t, _x, s in reversed(self.writes) if t == title)
        return {"revision_id": rev, "text": text, "summary": summary, "tags": ["chatgpt"]}
    def delete_page(self, *, title, reason, expected_user):
        self.deleted.append((title, reason)); self.pages.pop(title, None)


def test_remote_executor_preflights_then_uses_individual_summaries(tmp_path: Path, monkeypatch) -> None:
    project, build = make_project(tmp_path)
    oid, nid, target = _prepare_single_occurrence_merge(build)
    plan, desired, _ = ga.prepare_action_plan(build, "debat_test", [{
        "action": "merge_redirect", "occurrence_id": oid, "node_id": nid, "target_node_id": target,
    }])
    pages = {}
    for row in plan["mutations"]:
        source = (build / row["source_path"]).read_text(encoding="utf-8")
        pages[row["title"]] = (int(row["expected_revision_id"]), source)
    fake = FakeRemote(pages)
    monkeypatch.setattr(ga, "_adapter", lambda _root: (fake, "ChatGPT"))
    receipt = ga.execute_remote_plan(project, build, plan, desired)
    assert receipt["schema"] == ga.ACTION_RECEIPT_SCHEMA
    assert len(fake.writes) == 2  # parent + redirect
    assert all(summary != "Corrections" for _title, _text, summary in fake.writes)
    parent_summary = next(summary for title, _text, summary in fake.writes if title == "Débat test")
    assert "[[Argument B]]" in parent_summary


def test_prospective_validation_failure_prevents_any_remote_write(tmp_path: Path, monkeypatch) -> None:
    project, build = make_project(tmp_path)
    oid, nid, target = _prepare_single_occurrence_merge(build)
    review_path = build / "reviews/graph_placement_review.json"
    common.write_json(review_path, {"entries": [{
        "occurrence_id": oid, "node_id": nid,
        "correction": {"action": "merge_redirect", "target_node_id": target},
    }]})

    called = {"remote": False}
    def forbidden_remote(*args, **kwargs):
        called["remote"] = True
        raise AssertionError("remote execution must not start")
    monkeypatch.setattr(ga, "execute_remote_plan", forbidden_remote)

    try:
        ga.execute_review_actions(
            project, build, "debat_test",
            preflight_validator=lambda preview: {"status": "failed", "package": str(preview)},
        )
    except ga.GraphActionError as exc:
        assert "aucune écriture distante" in str(exc)
    else:
        raise AssertionError("a failed prospective validation must block")
    assert called["remote"] is False


def test_explicit_duplicate_parent_summary_must_link_destination(tmp_path: Path) -> None:
    _project, build = make_project(tmp_path)
    oid, nid, target = _prepare_single_occurrence_merge(build)
    try:
        ga.prepare_action_plan(build, "debat_test", [{
            "action": "merge_redirect", "occurrence_id": oid, "node_id": nid,
            "target_node_id": target, "edit_summary_parent": "Retrait d'un doublon",
        }])
    except ga.GraphActionError as exc:
        assert "[[Titre]]" in str(exc)
    else:
        raise AssertionError("duplicate summary without target wikilink must be rejected")

class LaggyRemote(FakeRemote):
    def __init__(self, pages):
        super().__init__(pages)
        self.read_revision_calls = 0
    def read_revision(self, title, revision_id):
        self.read_revision_calls += 1
        # Simulate MediaWiki replica/tag propagation after a successful edit:
        # first the revision is not visible, then metadata lacks the tag, then complete.
        if self.read_revision_calls == 1:
            return None
        observed = super().read_revision(title, revision_id)
        if self.read_revision_calls == 2 and observed is not None:
            observed = dict(observed)
            observed["tags"] = []
        return observed


def test_remote_executor_retries_exact_revision_after_replica_lag(tmp_path: Path, monkeypatch) -> None:
    project, build = make_project(tmp_path)
    oid, nid, target = _prepare_single_occurrence_merge(build)
    plan, desired, _ = ga.prepare_action_plan(build, "debat_test", [{
        "action": "merge_redirect", "occurrence_id": oid, "node_id": nid, "target_node_id": target,
    }])
    pages = {}
    for row in plan["mutations"]:
        source = (build / row["source_path"]).read_text(encoding="utf-8")
        pages[row["title"]] = (int(row["expected_revision_id"]), source)
    fake = LaggyRemote(pages)
    monkeypatch.setattr(ga, "_adapter", lambda _root: (fake, "ChatGPT"))
    monkeypatch.setattr(ga.time, "sleep", lambda _seconds: None)
    receipt = ga.execute_remote_plan(project, build, plan, desired)
    assert receipt["schema"] == ga.ACTION_RECEIPT_SCHEMA
    assert len(fake.writes) == 2
    assert fake.read_revision_calls >= 4


def test_remote_executor_resumes_verified_partial_write_without_rewriting(tmp_path: Path, monkeypatch) -> None:
    project, build = make_project(tmp_path)
    oid, nid, target = _prepare_single_occurrence_merge(build)
    plan, desired, _ = ga.prepare_action_plan(build, "debat_test", [{
        "action": "merge_redirect", "occurrence_id": oid, "node_id": nid, "target_node_id": target,
    }])
    pages = {}
    for row in plan["mutations"]:
        source = (build / row["source_path"]).read_text(encoding="utf-8")
        pages[row["title"]] = (int(row["expected_revision_id"]), source)
    fake = FakeRemote(pages)
    parent = next(row for row in plan["mutations"] if row["page_type"] == "debate")
    parent_desired = desired[parent["source_path"]]
    # Simulate the first write having succeeded before the prior process aborted.
    first_rev = fake.write_page(
        title=parent["title"], text=parent_desired, summary=parent["edit_summary"], tags=["chatgpt"],
        expected_user="ChatGPT", create_only=False, base_revision_id=int(parent["expected_revision_id"]),
    )
    assert first_rev > int(parent["expected_revision_id"])
    prior_writes = len(fake.writes)
    monkeypatch.setattr(ga, "_adapter", lambda _root: (fake, "ChatGPT"))
    receipt = ga.execute_remote_plan(project, build, plan, desired)
    parent_result = next(row for row in receipt["results"] if row["title"] == parent["title"])
    assert parent_result["status"] == "already_done"
    # Only the duplicate page redirect is newly written during the restart.
    assert len(fake.writes) == prior_writes + 1


def _receipt_for_local_apply(plan: dict) -> dict:
    results = []
    next_rev = 1000
    for mutation in plan["mutations"]:
        next_rev += 1
        results.append({
            "title": mutation["title"],
            "operation": mutation["operation"],
            "status": "written" if mutation["operation"] in {"update", "redirect"} else "deleted",
            "old_revision_id": mutation.get("expected_revision_id"),
            "revision_id": next_rev if mutation["operation"] != "delete" else None,
            "edit_summary": mutation["edit_summary"],
        })
    receipt = {
        "schema": ga.ACTION_RECEIPT_SCHEMA,
        "schema_version": "1.0",
        "debate_id": plan["debate_id"],
        "plan_sha256": plan["plan_sha256"],
        "executed_at": common.now_iso(),
        "results": results,
        "receipt_sha256": None,
    }
    receipt["receipt_sha256"] = ga._sha_object(receipt, "receipt_sha256")
    return receipt


def test_local_graph_action_refreshes_import_provenance_hash(tmp_path: Path) -> None:
    _project, build = make_project(tmp_path)
    oid, nid, target = _prepare_single_occurrence_merge(build)
    plan, desired, graph_result = ga.prepare_action_plan(build, "debat_test", [{
        "action": "merge_redirect", "occurrence_id": oid, "node_id": nid, "target_node_id": target,
    }])
    receipt = _receipt_for_local_apply(plan)
    ga.apply_local_result(build, plan, desired, graph_result, receipt)
    provenance = json.loads((build / "data/import_provenance.json").read_text(encoding="utf-8"))
    rows = {row["import_path"]: row for row in provenance["pages"]}
    for mutation in plan["mutations"]:
        if mutation["operation"] not in {"update", "redirect"}:
            continue
        path = build / mutation["source_path"]
        assert rows[mutation["source_path"]]["sha256"] == ga._sha256_file_bytes(path)
        assert rows[mutation["source_path"]]["size_bytes"] == path.stat().st_size


def test_repair_legacy_2165_provenance_only_for_exact_attested_graph_action(tmp_path: Path) -> None:
    from wikidebia_editorial_workspace import read_import_metadata, WorkspaceError

    _project, build = make_project(tmp_path)
    oid, nid, target = _prepare_single_occurrence_merge(build)
    plan, desired, graph_result = ga.prepare_action_plan(build, "debat_test", [{
        "action": "merge_redirect", "occurrence_id": oid, "node_id": nid, "target_node_id": target,
    }])
    parent = next(m for m in plan["mutations"] if m["page_type"] == "debate")
    prov_before = json.loads((build / "data/import_provenance.json").read_text(encoding="utf-8"))
    old_parent_sha = next(r["sha256"] for r in prov_before["pages"] if r["import_path"] == parent["source_path"])

    receipt = _receipt_for_local_apply(plan)
    ga.apply_local_result(build, plan, desired, graph_result, receipt)

    # Recreate the precise 2.16.5 defect: post-action file and remote revision are
    # correct, but the raw import-provenance hash still points to the old snapshot.
    prov_path = build / "data/import_provenance.json"
    provenance = json.loads(prov_path.read_text(encoding="utf-8"))
    parent_row = next(r for r in provenance["pages"] if r["import_path"] == parent["source_path"])
    parent_row["sha256"] = old_parent_sha
    common.write_json(prov_path, provenance)
    try:
        read_import_metadata(build, parent_row)
    except WorkspaceError as exc:
        assert "Empreinte de provenance divergente" in str(exc)
    else:
        raise AssertionError("the simulated 2.16.5 provenance defect must block")

    repaired = ga.repair_graph_action_import_provenance(build)
    assert parent["source_path"] in repaired["repaired_paths"]
    provenance = json.loads(prov_path.read_text(encoding="utf-8"))
    parent_row = next(r for r in provenance["pages"] if r["import_path"] == parent["source_path"])
    read_import_metadata(build, parent_row)  # no exception after exact attested repair

    # A different, non-attested local drift must remain blocked.
    unrelated_row = next(r for r in provenance["pages"] if r.get("page_id") == "A0002")
    unrelated_path = build / unrelated_row["import_path"]
    unrelated_path.write_text(unrelated_path.read_text(encoding="utf-8") + "\nDérive locale\n", encoding="utf-8")
    again = ga.repair_graph_action_import_provenance(build)
    assert unrelated_row["import_path"] not in again["repaired_paths"]
    try:
        read_import_metadata(build, unrelated_row)
    except WorkspaceError as exc:
        assert "Empreinte de provenance divergente" in str(exc)
    else:
        raise AssertionError("unattested drift must remain blocked")


def test_repair_legacy_multiround_provenance_uses_historical_state_plans(tmp_path: Path) -> None:
    from wikidebia_editorial_workspace import read_import_metadata

    project, build = make_project(tmp_path)
    oid, nid, target = _prepare_single_occurrence_merge(build)
    plan, desired, graph_result = ga.prepare_action_plan(build, "debat_test", [{
        "action": "merge_redirect", "occurrence_id": oid, "node_id": nid, "target_node_id": target,
    }])
    parent = next(m for m in plan["mutations"] if m["page_type"] == "debate")
    prov_before = json.loads((build / "data/import_provenance.json").read_text(encoding="utf-8"))
    old_parent_sha = next(r["sha256"] for r in prov_before["pages"] if r["import_path"] == parent["source_path"])

    receipt = _receipt_for_local_apply(plan)
    ga.apply_local_result(build, plan, desired, graph_result, receipt)

    # Persist the immutable first-round state artifacts, as real executions do.
    run_dir = project / ".state/graph-actions/debat_test/20260811-120000"
    run_dir.mkdir(parents=True)
    common.write_json(run_dir / "plan.json", plan)
    common.write_json(run_dir / "execution-receipt.json", receipt)

    # Recreate the 2.16.5 hash omission for a page touched in round 1.
    prov_path = build / "data/import_provenance.json"
    provenance = json.loads(prov_path.read_text(encoding="utf-8"))
    parent_row = next(r for r in provenance["pages"] if r["import_path"] == parent["source_path"])
    parent_row["sha256"] = old_parent_sha
    common.write_json(prov_path, provenance)

    # Simulate a later correction round overwriting graph_action_decisions.json,
    # which is exactly why 2.16.6 could no longer attest the first-round page.
    common.write_json(build / "reviews/graph_action_decisions.json", {
        "schema": ga.ACTION_DECISIONS_SCHEMA,
        "schema_version": "1.0",
        "debate_id": "debat_test",
        "applied_at": common.now_iso(),
        "plan_sha256": "later",
        "receipt_sha256": "later",
        "actions": [],
        "mutations": [{
            "operation": "update",
            "source_path": "imports/fr/arguments/A0002.wiki",
            "desired_sha256": "0" * 64,
            "expected_revision_id": 999,
        }],
        "historical_snapshot_path": "history/graph-actions/later",
    })

    repaired = ga.repair_graph_action_import_provenance(
        build, project_root=project, debate_id="debat_test"
    )
    assert parent["source_path"] in repaired["repaired_paths"]
    provenance = json.loads(prov_path.read_text(encoding="utf-8"))
    parent_row = next(r for r in provenance["pages"] if r["import_path"] == parent["source_path"])
    read_import_metadata(build, parent_row)
