from __future__ import annotations

from typing import Any

from .graph import state_at_least
from .package import PackageContext
from .translation import english_translation_deferred, english_translation_status, reuses_existing_english_page
from .wikicode import alphabetically_sorted


SECTION_MAP = {
    "Aménagement": "Planning", "Culture": "Culture", "Droit": "Law", "Écologie": "Ecology",
    "Économie": "Economy", "Éducation": "Education", "Éthique": "Ethics", "Géopolitique": "Geopolitics",
    "Histoire": "History", "Philosophie": "Philosophy", "Politique": "Politics", "Psychologie": "Psychology",
    "Religion et spiritualité": "Religion and spirituality", "Santé": "Health", "Science": "Science",
    "Société": "Society", "Sport et loisirs": "Sport and leisure", "Technologie": "Technology",
}


def _validate_final_quote_audit(ctx: PackageContext) -> None:
    """Recompute the sealed audit without trusting a kit-generated success flag.

    Check freshness at the recorded audit time for archived Works. The kit
    also checks present freshness before apply/render; publication needs its
    own fresh preflight. Historical Works without this opt-in are unchanged.
    """
    from .quote_index_contract import INDEX_PATH, QuoteIndexError, verify_final_audit, MAX_INDEX_BYTES
    if not ctx.exists("data/en_content_lock.json"):
        return
    lock = ctx.load_json("data/en_content_lock.json") or {}
    if not isinstance(lock,dict):
        return
    translation = ctx.load_json("data/en_translation_lock.json") or {}
    policy = translation.get("citation_translation_policy") or {}
    audit = lock.get("quote_duplicate_audit")
    sha = policy.get("quote_duplicate_audit_sha256")
    if (audit is None and sha is None and lock.get("published_quote_contract") is None
            and policy.get("published_quote_contract") is None):
        return
    try:
        if not isinstance(audit,dict) or audit.get("audit_sha256") != sha:
            raise QuoteIndexError("missing_or_unbound_final_quote_audit")
        raw = ctx.read_bytes(INDEX_PATH,required=True)
        if raw is None or len(raw)>MAX_INDEX_BYTES:
            raise QuoteIndexError("invalid_public_quote_index_file")
        def unique(pairs):
            out = {}
            for key,value in pairs:
                if key in out:
                    raise QuoteIndexError("duplicate_public_quote_index_key")
                out[key]=value
            return out
        import json
        value=json.loads(raw.decode("utf-8"),object_pairs_hook=unique)
        verify_final_audit(audit,lock["arguments"],value,ctx.sha256("data/fr_content_lock.json"))
    except (ValueError,OSError,KeyError,TypeError,AttributeError) as exc:
        reason=str(exc) if isinstance(exc,QuoteIndexError) else type(exc).__name__
        ctx.report.error("WDV-MWK-021","Contrôle des doublons anglais invalide : "+reason,
                         path="data/en_content_lock.json")


def validate_bilingual(ctx: PackageContext) -> None:
    registry = ctx.registry()
    manifest = ctx.manifest()
    if not registry or not manifest:
        return
    _validate_final_quote_audit(ctx)
    english_deferred = english_translation_deferred(manifest)
    strict = state_at_least(manifest.get("global_status"), "bilingual_validated") and not english_deferred
    nodes = [n for n in registry.get("graph", {}).get("nodes", []) if n.get("status") == "active"]
    pages = {(p.get("page_id"), p.get("language")): p for p in manifest.get("pages", [])}
    from .schema_validation import _valid_translation_source_preservation
    preserved = _valid_translation_source_preservation(ctx)
    frozen = {}
    if preserved:
        lock = ctx.load_json("data/fr_page_metadata_lock.json") or {}
        frozen = {r.get("entity_id", r.get("id")): r for r in lock.get("arguments", [])}
    for node in nodes:
        nid = node.get("id")
        fr = node.get("fr") or {}
        en = node.get("en") or {}
        reused_existing = reuses_existing_english_page(node)
        if strict:
            if en.get("title_status") != "locked" or not en.get("canonical_title"):
                ctx.report.error("WDV-BIL-001", f"Titre anglais non verrouillé pour {nid}", path=ctx.core_paths()["registry"])
            if (nid, "fr") not in pages or ((nid, "en") not in pages and not reused_existing):
                ctx.report.error("WDV-BIL-001", f"Paire de pages bilingues incomplète pour {nid}", path="manifest.json")
        if english_deferred:
            continue
        rubriques = frozen.get(nid, {}).get("rubriques", []) if preserved else fr.get("rubriques", [])
        expected_sections = [SECTION_MAP[x] for x in rubriques if x in SECTION_MAP]
        expected_sections = alphabetically_sorted(expected_sections)
        if en.get("sections") and en.get("sections") != expected_sections:
            ctx.report.warning("WDV-BIL-004", f"Sections anglaises divergentes pour {nid}; une justification éditoriale est requise", path=ctx.core_paths()["registry"], details={"expected": expected_sections, "actual": en.get("sections")})
        fr_primary = (node.get("derived") or {}).get("primary_occurrence_id")
        # Same registry means relations/occurrences are language-neutral; still check page records exist symmetrically.
        if strict:
            fr_rec = ((node.get("pages") or {}).get("fr") or {})
            en_rec = ((node.get("pages") or {}).get("en") or {})
            if (fr_rec.get("generation") or {}).get("status") != "validated" or (not reused_existing and (en_rec.get("generation") or {}).get("status") != "validated"):
                ctx.report.error("WDV-BIL-001", f"Pages bilingues non validées dans le registre pour {nid}")
            if not fr_primary:
                ctx.report.error("WDV-BIL-003", f"Occurrence primaire dérivée absente pour {nid}")
    # Debate pair.
    debate = registry.get("debate") or {}
    if strict:
        en_debate = ((debate.get("pages") or {}).get("en") or {})
        if en_debate.get("title_status") != "locked" or not en_debate.get("canonical_title"):
            ctx.report.error("WDV-BIL-001", "Titre canonique anglais de la page Debate non verrouillé")
    ctx.report.metrics["bilingual"] = {"active_nodes": len(nodes), "strict": strict, "english_translation_status": english_translation_status(manifest), "skipped_for_deferred_translation": english_deferred}
