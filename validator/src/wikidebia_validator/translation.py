from __future__ import annotations

from typing import Any


def reuses_existing_english_page(node: dict[str, Any] | None) -> bool:
    if not isinstance(node, dict):
        return False
    wiki = ((((node.get("pages") or {}).get("en") or {}).get("wiki") or {}))
    en = node.get("en") or {}
    return (
        wiki.get("check_status") == "equivalent_existing"
        and wiki.get("decision") == "reuse_existing"
        and bool(en.get("canonical_title"))
        and en.get("title_status") == "locked"
    )


def english_translation_status(manifest: dict[str, Any] | None) -> str:
    """Return the explicit English translation state.

    The workflow state is read directly from ``translation_status.en``. Absence of
    the field remains strict and does not depend on the declared norm version.
    """
    if not isinstance(manifest, dict):
        return "pending"
    status = ((manifest.get("translation_status") or {}).get("en"))
    return str(status or "pending")


def english_translation_deferred(manifest: dict[str, Any] | None) -> bool:
    """Return whether English production is explicitly deferred.

    The status is an operational workflow declaration, not a migration of the
    corpus' editorial norm.  It therefore applies to legacy 1.2.x corpora when
    explicitly present; absence of the field remains strict for backwards
    compatibility.
    """
    if not isinstance(manifest, dict):
        return False
    return english_translation_status(manifest) == "deferred"
