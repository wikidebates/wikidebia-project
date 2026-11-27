"""Conservative sentence-boundary checks for canonical page titles.

These checks supplement editorial review; they cannot establish semantic quality.
They never rewrite a title or apply creation rules to historical displayed labels.
"""
from __future__ import annotations

import re


# Explicit keyboard-friendly expansions; never apply Unicode compatibility
# normalization to arbitrary text or strip French accents.
TITLE_LIGATURES = str.maketrans({
    "œ": "oe", "Œ": "OE", "æ": "ae", "Æ": "AE",
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
    "ﬅ": "st", "ﬆ": "st",
})


def split_title_ligatures(value: str) -> str:
    return value.translate(TITLE_LIGATURES)


_ABBREVIATIONS = re.compile(
    r"\b(?:(?:[A-Za-z]\.){2,}|(?:Mr|Mrs|Ms|Dr|Prof|St|Mme|Mlle|Pr|vs|etc)\.)",
    re.IGNORECASE,
)
_INITIAL = re.compile(r"\b[A-Z]\.(?=\s+[A-Z][a-z])")
_SENTENCE_BOUNDARY = re.compile(r"[.!?]\s+\S")


def canonical_title_structure_issues(value: str) -> list[str]:
    """Find obvious joined statements, tolerating initials and abbreviations.

    Commas and conjunctions are not parsed as sentence boundaries. Their sense,
    the title's concision and its argumentative scope still require actual review.
    """
    text = str(value or "").strip()
    issues = []
    if ";" in text:
        issues.append("semicolon_joined_statements")
    protected = _ABBREVIATIONS.sub(lambda match: match.group().replace(".", ""), text)
    protected = _INITIAL.sub(lambda match: match.group().replace(".", ""), protected)
    if _SENTENCE_BOUNDARY.search(protected):
        issues.append("multiple_sentences")
    return issues
