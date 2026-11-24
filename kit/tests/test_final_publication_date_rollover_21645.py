"""The retired midnight transition cannot silently authorize legacy plans."""
import pytest
import wikidebia_final_publication as final


@pytest.mark.parametrize("operation", ["create", "skip", "update"])
def test_legacy_dated_plan_is_refused_without_migration(operation):
    plan = {"actions": [{"operation": operation, "publication_creation_date": "2026-08-20"}]}
    with pytest.raises(final.FinalPublicationError, match="Plan anglais historique daté"):
        final._assert_no_historical_dated_plan(plan)


def test_current_plan_has_no_civil_day_dependency():
    final._assert_no_historical_dated_plan({"actions": [{"operation": "create"}]})
