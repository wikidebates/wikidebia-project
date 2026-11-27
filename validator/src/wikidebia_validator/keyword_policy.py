"""Deterministic French keyword rules shared by kit and validator.

The two components are distributed independently; keep these copies
byte-identical. The alias table is conservative: never infer synonymy by
stemming or removing accents, or rewrite historical terms via a diagnostic.
"""
from __future__ import annotations

import re
import unicodedata

COMPOSITIONAL_KEYWORD_FR = re.compile(
    r"^(?:(?:psychologie|sociologie|histoire|géographie|généalogie)\s+religieuse?s?|science\s+et\s+religion"
    r"|municipalités?\s+de\s+(?:gauche|droite)|femmes?\s+voilées?"
    r"|(?:port|interdiction)\s+du\s+voile(?:\s+islamique)?)$",
    flags=re.IGNORECASE,
)

REVIEWED_FR_VARIANTS = {
    "dictatures": "dictature",
    "femme": "femmes",
    "emancipation": "émancipation",
}


def keyword_identity_fr(value: str) -> str:
    key = unicodedata.normalize("NFC", " ".join(value.split())).casefold()
    return REVIEWED_FR_VARIANTS.get(key, key)


def acronym_like(value: str) -> bool:
    letters = [char for char in value if char.isalpha()]
    return len(letters) >= 2 and all(char.isupper() for char in letters)


def lowercase_keyword_initial(value: str) -> str:
    """Lowercase the first letter; semantic kind needs editorial review."""
    for index, char in enumerate(value):
        if char.isalpha():
            return value[:index] + char.lower() + value[index + 1:]
    return value
