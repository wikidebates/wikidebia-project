"""Offline regression gates for signed French-to-English publication."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from wikidebia_update import (
    RemoteUpdatePlanner, PlanExecutor, PlanConflict, UpdateError,
    sha_object, sha_file,
)
from wikidebia_publish import GenericPublisher, PublicationError


def manifest():
    return {
        "debate_id": "demo", "translation_status": {"en": "ready"},
        "pages": [
            {"language": "fr", "page_id": "A1", "page_type": "argument",
             "canonical_title": "Titre français", "page_origin": "preexisting"},
            {"language": "en", "page_id": "A1", "page_type": "argument",
             "canonical_title": "English title", "page_origin": "new"},
        ],
    }


def test_planner_emits_source_linked_translation_summary():
    planner = object.__new__(RemoteUpdatePlanner)
    planner.manifest = manifest()
    row = {"language": "en", "page_id": "A1", "page_type": "argument"}
    planner._apply_create_summary_policy(row)
    assert row["edit_summary_policy"] == "english_translation_creation"
    assert row["edit_summary"] == (
        "Translation of the French page: [[:fr:Titre français|Titre français]]"
    )


def test_planner_requires_exact_french_source():
    planner = object.__new__(RemoteUpdatePlanner)
    planner.manifest = manifest()
    planner.manifest["pages"] = [p for p in planner.manifest["pages"] if p["language"] == "en"]
    with pytest.raises(UpdateError, match="Source française unique"):
        planner._apply_create_summary_policy(
            {"language": "en", "page_id": "A1", "page_type": "argument"}
        )


def executor_fixture(tmp_path: Path):
    executor = object.__new__(PlanExecutor)
    executor.corpus_root = tmp_path / "corpus"
    executor.corpus_root.mkdir()
    executor.config_path = tmp_path / "config.json"
    executor.manifest = manifest()
    executor.debate_id = "demo"
    (executor.corpus_root / "manifest.json").write_text(
        json.dumps(executor.manifest), encoding="utf-8"
    )
    executor.config_path.write_text("{}", encoding="utf-8")
    return executor


@pytest.mark.parametrize("operation", ["create", "update", "move", "redirect", "delete"])
def test_generic_executor_refuses_all_translation_mutations_before_remote_access(
    tmp_path: Path, operation: str
):
    executor = executor_fixture(tmp_path)
    plan = {
        "plan_version": "wikidebia-remote-update-plan-1.0",
        "debate_id": "demo",
        "new_manifest_sha256": sha_file(executor.corpus_root / "manifest.json"),
        "config_sha256": sha_file(executor.config_path),
        "operations": {
            operation: [{"language": "en", "page_id": "A1", "title": "English title"}]
        },
    }
    plan["plan_sha256"] = sha_object(plan)
    with pytest.raises(PlanConflict, match="reprise générique interdite"):
        executor.verify_plan(plan, plan["plan_sha256"])


def test_generic_executor_direct_call_is_also_blocked(tmp_path: Path):
    executor = executor_fixture(tmp_path)
    class FailOnRemoteRead:
        def read_page(self, title):
            raise AssertionError("remote read must not happen")
    executor.adapter = FailOnRemoteRead()
    with pytest.raises(PlanConflict, match="reprise générique interdite"):
        executor._execute_one(
            {"operation": "create", "language": "en", "title": "English title"},
            "ChatGPT", {},
        )


def bare_publisher(tmp_path: Path, *, operation_id: str):
    publisher = object.__new__(GenericPublisher)
    publisher.manifest = manifest()
    publisher.operation = {"id": operation_id, "kind": "full_page"}
    publisher.config = {"debate_id": "demo"}
    publisher.project_root = tmp_path
    publisher.root = tmp_path / "corpus"
    publisher.manifest_path = publisher.root / "manifest.json"
    publisher.root.mkdir(exist_ok=True)
    publisher.manifest_path.write_text(json.dumps(publisher.manifest), encoding="utf-8")
    publisher.languages = ("en",)
    publisher.publication_profile = "norm_1_2_direct_interlanguage"
    directory = tmp_path / ".state" / "final-publication" / "demo" / "EDIT-001"
    directory.mkdir(parents=True)
    publisher.config_path = directory / "english-publication-config.json"
    return publisher, directory


def plan():
    return {
        "plan_sha256": "3" * 64,
        "actions": [
            {"language": "en", "page_id": "A1", "title": "English title", "operation": "create"},
        ],
    }


def test_generic_en_only_publisher_refuses_translation(tmp_path: Path):
    publisher, _ = bare_publisher(tmp_path, operation_id="generic")
    with pytest.raises(PublicationError, match="publication générique interdite"):
        publisher._assert_paired_translation_authorization(plan())


def test_claiming_final_operation_id_without_evidence_is_not_enough(tmp_path: Path):
    publisher, _ = bare_publisher(tmp_path, operation_id="workflow_final_publish_en")
    with pytest.raises(PublicationError, match="Préflight bilingue attesté requis"):
        publisher._assert_paired_translation_authorization(plan())


def sign(directory: Path, name: str, field: str, body: dict):
    value = dict(body)
    value[field] = sha_object(value)
    (directory / name).write_text(json.dumps(value), encoding="utf-8")
    return value


def paired_evidence(publisher, directory):
    fr_config = {
        "debate_id": "demo", "languages": ["fr"], "interlanguage_only": True,
        "corpus_root": str(publisher.root),
    }
    fr_config_path = directory / "french-update-config.json"
    fr_config_path.write_text(json.dumps(fr_config), encoding="utf-8")
    fr_plan = sign(directory, "french-update-plan.json", "plan_sha256", {
        "debate_id": "demo", "languages": ["fr"],
        "edit_summary_contract": "page_specific_v1",
        "config_sha256": sha_file(fr_config_path),
        "new_manifest_sha256": sha_file(publisher.manifest_path),
        "operations": {
            "update": [
                {"language": "fr", "page_id": "A1", "title": "Titre français",
                 "edit_summary_policy": "french_interlanguage_addition",
                 "preconditions": ["only_interlanguage_addition"]}
            ],
            "skip": [],
        },
    })
    safety = sign(directory, "safety-update-plan.json", "plan_sha256", {
        "debate_id": "demo", "operations": {},
    })
    baseline = sign(directory, "baseline.json", "baseline_sha256", {
        "debate_id": "demo", "work_id": "EDIT-001",
    })
    preflight = sign(directory, "preflight.json", "preflight_sha256", {
        "status": "ready",
        "remote_write_authorized": False, "remote_write_performed": False,
        "english_plan_sha256": plan()["plan_sha256"],
        "french_plan_sha256": fr_plan["plan_sha256"],
        "safety_plan_sha256": safety["plan_sha256"],
        "remote_snapshots": [
            {"language": "en", "page_id": "A1", "title": "English title",
             "operation": "create", "exists": False},
            {"language": "fr", "page_id": "A1", "title": "Titre français",
             "operation": "update", "exists": True},
        ],
    })
    sign(directory, "authorization.json", "authorization_sha256", {
        "status": "authorized", "remote_write_authorized": True,
        "execution_started": True, "baseline_sha256": baseline["baseline_sha256"],
        "preflight_sha256": preflight["preflight_sha256"],
    })


def test_matching_signed_bilingual_pair_allows_final_publisher(tmp_path: Path):
    publisher, directory = bare_publisher(tmp_path, operation_id="workflow_final_publish_en")
    paired_evidence(publisher, directory)
    publisher._assert_paired_translation_authorization(plan())


@pytest.mark.parametrize("change", ["preflight", "french", "authorization", "snapshot"])
def test_tampering_with_signed_transaction_blocks_publication(tmp_path: Path, change: str):
    publisher, directory = bare_publisher(tmp_path, operation_id="workflow_final_publish_en")
    paired_evidence(publisher, directory)
    path_map = {
        "preflight": "preflight.json", "french": "french-update-plan.json",
        "authorization": "authorization.json", "snapshot": "preflight.json",
    }
    target = directory / path_map[change]
    value = json.loads(target.read_text(encoding="utf-8"))
    if change == "snapshot":
        value["remote_snapshots"].pop()
        value["preflight_sha256"] = sha_object({
            k: v for k, v in value.items() if k != "preflight_sha256"
        })
    else:
        value["status"] = "forged"
    target.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(PublicationError, match="Préflight bilingue attesté requis"):
        publisher._assert_paired_translation_authorization(plan())
