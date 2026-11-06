#!/usr/bin/env python3
"""Measure deterministic offline estimates for JSON context token budgets."""
from __future__ import annotations

import argparse
import json
import math
import os
import re
from pathlib import Path
from typing import Any, Sequence

from wikidebia_corpus_build import canonical_json, load_json


SUPPORTED_ESTIMATORS = ("unicode_conservative_v1",)
DEFAULT_MAX_CONTEXT_TOKENS = 32_000
DEFAULT_RESPONSE_RESERVE_TOKENS = 8_000
WRAPPER_RESERVE_TOKENS = 256
SAFETY_MULTIPLIER = 1.15


class TokenBudgetError(RuntimeError):
    pass


def measure_json_tokens(
    value: Any, *, estimator: str = "unicode_conservative_v1",
) -> int:
    if estimator not in SUPPORTED_ESTIMATORS:
        raise TokenBudgetError("Estimateur de tokens non pris en charge")
    raw = canonical_json(value)
    text = raw.decode("utf-8")
    byte_estimate = math.ceil(len(raw) / 3)
    lexical_estimate = 0
    for token in re.findall(r"\s+|[\w]+|[^\w\s]", text, flags=re.UNICODE):
        if token.isspace():
            lexical_estimate += max(1, math.ceil(len(token) / 4))
        elif token.isascii() and token.isalnum():
            lexical_estimate += max(1, math.ceil(len(token) / 4))
        elif token.isalnum() or token.replace("_", "").isalnum():
            lexical_estimate += max(1, math.ceil(len(token.encode("utf-8")) / 2))
        else:
            lexical_estimate += len(token)
    return max(byte_estimate, lexical_estimate)


def plan_token_budget(
    value: Any,
    *,
    max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
    response_reserve_tokens: int = DEFAULT_RESPONSE_RESERVE_TOKENS,
    estimator: str = "unicode_conservative_v1",
) -> dict[str, Any]:
    if max_context_tokens < 1024:
        raise TokenBudgetError("Le budget de contexte doit être d’au moins 1024 tokens")
    if response_reserve_tokens < 0 or response_reserve_tokens >= max_context_tokens:
        raise TokenBudgetError("La réserve de réponse doit être positive ou nulle et inférieure au budget")
    payload_tokens = measure_json_tokens(value, estimator=estimator)
    conservative_payload_tokens = math.ceil(payload_tokens * SAFETY_MULTIPLIER)
    planned_input_tokens = conservative_payload_tokens + WRAPPER_RESERVE_TOKENS
    available_input_tokens = max_context_tokens - response_reserve_tokens
    fits = planned_input_tokens <= available_input_tokens
    return {
        "schema": "wikidebia-token-budget-1.0",
        "estimator": estimator,
        "estimator_version": "1.0",
        "estimated": True,
        "network_required": False,
        "safety_multiplier": SAFETY_MULTIPLIER,
        "max_context_tokens": max_context_tokens,
        "response_reserve_tokens": response_reserve_tokens,
        "wrapper_reserve_tokens": WRAPPER_RESERVE_TOKENS,
        "payload_tokens": payload_tokens,
        "conservative_payload_tokens": conservative_payload_tokens,
        "planned_input_tokens": planned_input_tokens,
        "available_input_tokens": available_input_tokens,
        "remaining_input_tokens": available_input_tokens - planned_input_tokens,
        "fits": fits,
        "truncated": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_file", type=Path)
    parser.add_argument(
        "--estimator", choices=SUPPORTED_ESTIMATORS,
        default="unicode_conservative_v1",
    )
    parser.add_argument("--max-context-tokens", type=int, default=DEFAULT_MAX_CONTEXT_TOKENS)
    parser.add_argument("--response-reserve-tokens", type=int, default=DEFAULT_RESPONSE_RESERVE_TOKENS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    value = load_json(args.json_file, "JSON à mesurer")
    result = plan_token_budget(
        value,
        max_context_tokens=args.max_context_tokens,
        response_reserve_tokens=args.response_reserve_tokens,
        estimator=args.estimator,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["fits"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (TokenBudgetError, OSError, ValueError, KeyError) as exc:
        print(f"BUDGET DE TOKENS BLOQUÉ : {exc}", file=os.sys.stderr)
        raise SystemExit(2)
