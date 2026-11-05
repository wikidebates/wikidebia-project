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


def test_memory_objects_select_memory_test_and_integrity_check():
    result = changed.select_validations([
        "translation-memory/objects/abc.json",
    ])

    assert result["kit_test_paths"] == [
        "kit/tests/test_wikidebia_translation_memory.py",
    ]
    assert result["translation_memory_verify"] is True
