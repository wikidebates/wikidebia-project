import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_manifest_preserves_all_publication_branch_declarations():
    manifest = json.loads((ROOT / "KIT_MANIFEST.json").read_text(encoding="utf-8"))
    expected_scope = ['page_specific_translation_edit_summary', 'later_interlanguage_enrichment_preservation_exception', 'page_specific_interlanguage_update_summary', 'post_update_revision_summary_verification', 'remote_interlanguage_only_update', 'retroactive_translation_change_tag', 'canonical_argument_established_name_parameters', 'english_translation_publication_without_creation_date', 'english_translation_no_cross_wiki_initialization', 'publication_plan_independent_of_civil_day']
    assert set(expected_scope).issubset(set(manifest['scope']))
    assert 'english_translation_publication_creation_date' not in manifest['scope']
    assert 'per_page_publication_day_gate' not in manifest['scope']
    expected_safety = ['immutable_revision_tagging', 'eventually_consistent_postwrite_tag_verification', 'legacy_argument_name_alias_preservation']
    assert set(expected_safety).issubset(set(manifest['safety']))
    expected_features = ['french_interlanguage_remote_overlay', 'redirect_preserving_interlanguage_enrichment', 'interlanguage_only_owner_mode']
    assert set(expected_features).issubset(set(manifest['features']))
    expected_quality_gates = ['argument_established_name_parameter_order_gate']
    assert set(expected_quality_gates).issubset(set(manifest['quality_gates']))
    expected_regression_gates = ['interlanguage_only_preserves_human_remote_content_regression', 'interlanguage_only_redirect_preservation_regression', 'argument_established_name_parameter_alias_regression', 'english_creation_date_retirement_regression', 'english_initialization_cross_wiki_rejection_regression', 'english_creation_no_midnight_rollover_regression']
    assert set(expected_regression_gates).issubset(set(manifest['regression_gates']))

def test_active_guides_use_established_name_terminology():
    guide = (ROOT / "GUIDE_TRANSLATION_REVIEW.md").read_text(encoding="utf-8")
    assert "`established-name=` est un sous-titre" in guide
    assert "## Revue structurée et `established-name=`" in guide
