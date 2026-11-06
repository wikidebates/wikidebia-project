from __future__ import annotations

import pytest

import wikidebia_token_budget as budget


def test_offline_measurement_is_deterministic_for_multilingual_json():
    value = {"fr": "L’égalité complète", "en": "Complete equality", "items": [1, 2, 3]}

    first = budget.plan_token_budget(value)
    second = budget.plan_token_budget(value)

    assert first == second
    assert first["payload_tokens"] > 0
    assert first["planned_input_tokens"] == (
        first["conservative_payload_tokens"] + budget.WRAPPER_RESERVE_TOKENS
    )
    assert first["estimator"] == "unicode_conservative_v1"
    assert first["network_required"] is False
    assert first["safety_multiplier"] > 1
    assert first["truncated"] is False


def test_budget_reports_excess_without_truncation():
    result = budget.plan_token_budget(
        {"large": "argument " * 5000},
        max_context_tokens=1024,
        response_reserve_tokens=512,
    )

    assert result["fits"] is False
    assert result["remaining_input_tokens"] < 0
    assert result["truncated"] is False


@pytest.mark.parametrize(
    ("maximum", "reserve"),
    [(1000, 0), (4096, -1), (4096, 4096), (4096, 5000)],
)
def test_invalid_budgets_are_rejected(maximum: int, reserve: int):
    with pytest.raises(budget.TokenBudgetError):
        budget.plan_token_budget(
            {"value": "test"},
            max_context_tokens=maximum,
            response_reserve_tokens=reserve,
        )
