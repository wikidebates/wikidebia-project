from __future__ import annotations

import json
from pathlib import Path

import pytest

import wikidebia_fr_alias_pageids as aliases
import wikidebia_offline_bilingual as offline
from wikidebia_corpus_build import full_tree_sha256
from wikidebia_editorial_workspace import workspace_receipt_hash
from wikidebia_update import sha_object, sha_text
from test_wikidebia_offline_bilingual import _fixture, _write, DEBATE, WORK


OLD = "{{Débat\n|arguments-pour={{Argument pour|page=Ancien titre|titre-affiché=Libellé historique}}\n|arguments-contre={{Argument contre|page=Argument fixe|titre-affiché=Autre libellé}}\n|interlangue={{Lien interlangue|langue=en|page=Should we agree?}}\n}}"
NEW = OLD.replace("page=Ancien titre", "page=Nouveau titre")


def test_alias_only_changes_only_one_target_and_preserves_all_labels_and_order():
    assert aliases.changed_aliases(OLD, NEW, "debate") == [
        {"occurrence_index": 0, "relation": "arguments-pour",
         "original_title": "Ancien titre", "release_title": "Nouveau titre"}
    ]


@pytest.mark.parametrize("mutation", [
    NEW.replace("Libellé historique", "Autre libellé"),
    NEW.replace("{{Débat", "{{AutreModèle"),
    NEW.replace("arguments-pour", "arguments-contre"),
    NEW.replace("page=Nouveau titre", "page=Nouveau titre#Section"),
    NEW.replace("|interlangue=", "|introduction=Texte nouveau\n|interlangue="),
    NEW.replace("Argument contre|page", "Argument pour|page"),
])
def test_alias_proof_refuses_unrelated_french_edits(mutation: str):
    with pytest.raises(aliases.RelationPageIdError):
        aliases.changed_aliases(OLD, mutation, "debate")


def test_relation_anchors_must_remain_exact():
    old = OLD.replace("page=Ancien titre", "page=Ancien titre#Ancre")
    new = old.replace("page=Ancien titre#Ancre", "page=Nouveau titre#Ancre")
    assert aliases.changed_aliases(old, new, "debate")[0]["original_title"] == "Ancien titre"
    with pytest.raises(aliases.RelationPageIdError):
        aliases.changed_aliases(old, new.replace("#Ancre", "#Autre"), "debate")


def test_relations_that_live_outside_the_main_model_are_not_silently_accepted():
    old = "{{Argument|résumé=Texte}}\n{{Justification|page=Ancien titre|titre-affiché=Libellé}}"
    with pytest.raises(aliases.RelationPageIdError):
        aliases.changed_aliases(old, old.replace("Ancien titre", "Nouveau titre"), "argument")


def test_changed_graph_relation_without_pageid_proof_blocks(tmp_path: Path):
    selector, workspace, _ = _fixture(tmp_path)
    source = workspace / "release-copy/output/fr/debate.wiki"
    original = source.read_text(encoding="utf-8")
    source.write_text(NEW, encoding="utf-8")
    metadata = json.loads((workspace / "workspace.json").read_text())
    metadata["release_copy"]["tree_sha256"] = full_tree_sha256(workspace / "release-copy")
    metadata["workspace_sha256"] = workspace_receipt_hash(metadata)
    _write(workspace / "workspace.json", metadata)
    with pytest.raises(offline.PostPublicationError, match="pageid"):
        offline.reconcile_offline_bilingual(tmp_path, DEBATE, WORK, selector)
    assert (tmp_path / "corpus" / DEBATE / "previous.wiki").is_file()


def _changed_fixture(tmp_path: Path):
    selector, workspace, fixture = _fixture(tmp_path)
    source = workspace / "release-copy/output/fr/debate.wiki"
    old = source.read_text(encoding="utf-8")
    src_new = "{{Débat|interlangue={{Lien interlangue|langue=en|page=Should we agree?}}|arguments-pour={{Argument pour|page=Nouveau titre|titre-affiché=Libellé historique}}}}"
    src_old = src_new.replace("Nouveau titre", "Ancien titre")
    source.write_text(src_new, encoding="utf-8")
    metadata = json.loads((workspace / "workspace.json").read_text())
    metadata["release_copy"]["tree_sha256"] = full_tree_sha256(workspace / "release-copy")
    metadata["workspace_sha256"] = workspace_receipt_hash(metadata)
    _write(workspace / "workspace.json", metadata)

    # The published-state FR proof must reference the actual remote spelling.
    state_path = tmp_path / ".state/published" / DEBATE / "fr/latest.json"
    state = json.loads(state_path.read_text())
    state["pages"][0]["content_sha256"] = sha_text(src_old)
    state.pop("state_sha256")
    state["state_sha256"] = sha_object(state)
    _write(state_path, state)
    op_path = fixture["paths"]["french_plan"]
    plan = json.loads(op_path.read_text())
    plan["operations"]["update"][0]["new_sha256"] = sha_text(src_old)
    plan.pop("plan_sha256")
    plan["plan_sha256"] = sha_object(plan)
    _write(op_path, plan)
    # Real FR receipts and signed states both refer to the final plan / content.
    receipt_path = fixture["paths"]["french_receipt"]
    receipt = json.loads(receipt_path.read_text())
    receipt["plan_sha256"] = plan["plan_sha256"]
    receipt["results"][0]["content_sha256"] = sha_text(src_old)
    receipt.pop("receipt_sha256")
    receipt["receipt_sha256"] = sha_object(receipt)
    _write(receipt_path, receipt)
    state["plan_sha256"] = plan["plan_sha256"]
    state["receipt_sha256"] = receipt["receipt_sha256"]
    state.pop("state_sha256")
    state["state_sha256"] = sha_object(state)
    _write(state_path, state)

    proof = {
        "schema": aliases.SCHEMA, "debate_id": DEBATE, "work_id": WORK,
        "release_copy_tree_sha256": metadata["release_copy"]["tree_sha256"],
        "manifest_sha256": sha_text((workspace / "release-copy/manifest.json").read_text()),
        "french_state_sha256": state["state_sha256"],
        "remote_access_mode": "read_only", "remote_writes": 0,
        "page_count": 1, "alias_count": 1,
        "pages": [{
            "page_type": "debate", "page_id": "debate",
            "title": "Faut-il être d'accord ?", "revision_id": 21,
            "content_sha256": sha_text(src_old), "remote_text": src_old,
            "release_sha256": sha_text(src_new),
            "changes": aliases.changed_aliases(src_old, src_new, "debate"),
        }],
        "title_resolutions": {
            "Ancien titre": {"pageid": 12345, "resolved_title": "Titre final"},
            "Nouveau titre": {"pageid": 12345, "resolved_title": "Titre final"},
        },
    }
    proof["proof_sha256"] = sha_object(proof)
    proof_path = tmp_path / ".state" / "evidence" / DEBATE / WORK / "pageids.json"
    _write(proof_path, proof)
    sel = json.loads(selector.read_text())
    sel["relation_pageids_proof"] = proof_path.relative_to(tmp_path).as_posix()
    _write(selector, sel)
    return selector, workspace, proof_path


def test_offline_close_accepts_only_signed_pageid_equivalent_aliases(tmp_path: Path):
    selector, workspace, _ = _changed_fixture(tmp_path)
    result = offline.reconcile_offline_bilingual(tmp_path, DEBATE, WORK, selector)
    assert result["status"] == "published"
    assert (workspace / "release-copy/output/fr/debate.wiki").read_text().find("Nouveau titre") >= 0
    receipt = json.loads((tmp_path / result["receipt_path"]).read_text())
    assert receipt["proofs"]["relation_pageids_changes"] == {"page_count": 1, "alias_count": 1}


def test_offline_close_rejects_different_mediawiki_target_identity(tmp_path: Path):
    selector, _, proof_path = _changed_fixture(tmp_path)
    value = json.loads(proof_path.read_text())
    value["title_resolutions"]["Nouveau titre"]["pageid"] = 90000
    value.pop("proof_sha256")
    value["proof_sha256"] = sha_object(value)
    _write(proof_path, value)
    with pytest.raises(offline.PostPublicationError, match="pageid"):
        offline.reconcile_offline_bilingual(tmp_path, DEBATE, WORK, selector)


def test_offline_close_rejects_missing_or_unbound_alias_evidence(tmp_path: Path):
    selector, workspace, proof_path = _changed_fixture(tmp_path)
    proof_path.unlink()
    with pytest.raises(offline.PostPublicationError):
        offline.reconcile_offline_bilingual(tmp_path, DEBATE, WORK, selector)
    assert (tmp_path / "corpus" / DEBATE / "previous.wiki").is_file()


class _Site:
    def __init__(self, *, altered=False, missing=False):
        self.calls = 0
        self.altered = altered
        self.missing = missing

    def simple_request(self, **kw):
        assert kw["action"] == "query"
        assert kw["prop"] == "info"
        assert kw["redirects"] == 1
        self.calls += 1
        titles = kw["titles"].split("|")
        pages = []
        normalized = []
        for title in titles:
            if title == "Vieux titre":
                normalized.append({"from": title, "to": "Titre canonique"})
            pages.append({
                "title": "Titre canonique" if title == "Vieux titre" else title,
                "pageid": (222 if self.altered and title == "Nouveau titre" else 111),
                **({"missing": True} if self.missing else {}),
            })
        return type("_Request", (), {"submit": lambda self: {
            "query": {"normalized": normalized,
                      "pages": {str(i): row for i, row in enumerate(pages)}},
        }})()


def test_readonly_resolver_records_normalization_and_pageids():
    result = aliases.resolve_titles_pageids(_Site(), ["Vieux titre", "Nouveau titre"])
    assert result["Vieux titre"] == {"pageid": 111, "resolved_title": "Titre canonique"}
    assert result["Nouveau titre"] == {"pageid": 111, "resolved_title": "Nouveau titre"}


def test_readonly_resolver_rejects_missing_page():
    with pytest.raises(aliases.RelationPageIdError):
        aliases.resolve_titles_pageids(_Site(missing=True), ["Vieux titre"])


def test_readonly_resolver_exposes_different_ids_not_fake_equivalence():
    result = aliases.resolve_titles_pageids(_Site(altered=True), ["Vieux titre", "Nouveau titre"])
    assert result["Vieux titre"]["pageid"] != result["Nouveau titre"]["pageid"]
