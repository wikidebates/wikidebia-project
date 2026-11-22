from __future__ import annotations

import wikidebia_test_changed as changed


def test_translation_script_selects_its_tests_and_manager():
    result = changed.select_validations([
        "kit/scripts/wikidebia_translation_packet.py",
    ])

    assert result["full_validation"] is False
    assert result["kit_test_paths"] == [
        "kit/tests/test_wikidebia_manage.py",
        "kit/tests/test_wikidebia_translation_packet.py",
    ]
    assert result["validator_tests"] is False

    verified = changed.select_validations(
        ["kit/scripts/wikidebia_translation_packet.py"],
        available_kit_tests=result["kit_test_paths"],
    )
    assert verified == result


def test_component_changes_select_only_their_suites():
    result = changed.select_validations([
        "validator/src/wikidebia_validator/editorial.py",
        "deploy/render-service.py",
    ])

    assert result["validator_tests"] is True
    assert result["deployment_tests"] is True
    assert result["kit_test_paths"] == []


def test_documentation_and_generated_metadata_need_no_pytest_suite():
    result = changed.select_validations([
        "kit/GUIDE_TRANSLATION_PACKETS.md",
        "kit/PACKAGE_RECEIPT.json",
        ".github/workflows/validate.yml",
        "docs/SESSION_HANDOFF.md",
        "docs/AGENT_PROCEDURES.md",
    ])

    assert result["full_validation"] is False
    assert result["kit_test_paths"] == []
    assert result["validator_tests"] is False
    assert result["deployment_tests"] is False


def test_shared_or_unknown_file_falls_back_to_every_suite():
    result = changed.select_validations([
        "kit/scripts/wikidebia_render.py",
    ])

    assert result["full_validation"] is True
    assert result["kit_test_paths"] == ["kit/tests"]
    assert result["validator_tests"] is True
    assert result["deployment_tests"] is True

    selected = changed.select_validations(
        ["kit/scripts/wikidebia_public_visibility.py"],
        available_kit_tests={
            "kit/tests/test_public_visibility_gate.py",
            "kit/tests/test_wikidebia_manage.py",
        },
    )
    assert selected["full_validation"] is False
    assert selected["kit_test_paths"] == [
        "kit/tests/test_public_visibility_gate.py",
        "kit/tests/test_wikidebia_manage.py",
    ]
    relay = changed.select_validations(
        ["kit/scripts/wikidebia_fr_publication_relay.py"],
        available_kit_tests={
            "kit/tests/test_fr_publication_relay.py",
            "kit/tests/test_wikidebia_manage.py",
        },
    )
    assert relay["full_validation"] is False
    assert relay["kit_test_paths"] == [
        "kit/tests/test_fr_publication_relay.py",
        "kit/tests/test_wikidebia_manage.py",
    ]
    missing = changed.select_validations(
        ["kit/scripts/wikidebia_public_visibility.py"],
        available_kit_tests={"kit/tests/test_wikidebia_manage.py"},
    )
    assert missing["full_validation"] is True
    assert missing["kit_test_paths"] == ["kit/tests"]
    assert missing["validator_tests"] is True
    assert missing["deployment_tests"] is True
    assert missing["full_validation_reasons"] == [
        "missing_direct_test:wikidebia_public_visibility.py",
    ]


def test_memory_objects_select_memory_test_and_integrity_check():
    result = changed.select_validations([
        "translation-memory/objects/abc.json",
    ])

    assert result["kit_test_paths"] == [
        "kit/tests/test_wikidebia_translation_memory.py",
    ]
    assert result["translation_memory_verify"] is True

    # The terse output does not discard the underlying signed plan or errors.
    plan = {
        "kit_test_paths": [],
        "validator_tests": False,
        "deployment_tests": False,
        "translation_memory_verify": False,
        "changed_files": ["docs/example.md"],
        "full_validation": False,
        "full_validation_reasons": [],
    }
    shown = changed.compact_summary({
        "plan": plan,
        "plan_path": ".state/changed-test-plan.json",
    })
    assert "Tests locaux : aucun" in shown
    assert "Plan complet : .state/changed-test-plan.json" in shown
    assert "prévisualisation" in shown
    assert "docs/example.md" not in shown
    plan["full_validation"] = True
    plan["full_validation_reasons"] = ["missing_direct_test:unknown.py"]
    plan["kit_test_paths"] = ["kit/tests"]
    failed = changed.compact_summary({
        "plan": plan,
        "plan_path": ".state/changed-test-plan.json",
        "receipt": {
            "status": "failed",
            "results": [{"name": "kit_tests", "returncode": 2}],
        },
    })
    assert "kit=all" in failed
    assert "missing_direct_test:unknown.py" in failed
    assert "Contrôle en échec : kit_tests (code 2)" in failed
