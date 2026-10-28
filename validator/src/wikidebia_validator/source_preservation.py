"""Exact preservation checks; these never attest historical factual accuracy."""
from __future__ import annotations
import hashlib
from typing import Any
from .package import PackageContext
from .schema_validation import _valid_translation_source_preservation

def preserved_french_page(ctx: PackageContext, page: dict[str, Any], text: str) -> bool:
    if page.get('language') != 'fr':
        return False
    kind = page.get('page_type')
    if ctx.exists('data/fr_render_source_provenance.json'):
        provenance = ctx.load_json('data/fr_render_source_provenance.json') or {}
        rows = provenance.get('pages') or []
    elif _valid_translation_source_preservation(ctx):
        receipt = ctx.load_json('data/source_preservation_receipt.json') or {}
        rows = receipt.get('pages') or []
    elif page.get('page_origin') == 'preexisting' and ctx.exists('data/import_provenance.json'):
        provenance = ctx.load_json('data/import_provenance.json') or {}
        rows = provenance.get('pages') or []
    else:
        return False
    row = next((r for r in rows if (r.get('page_id') == page.get('page_id') or kind == 'debate' and r.get('kind') == 'debate')), None)
    if not row:
        return False
    from .wikicode import _split_top_level, parse_template, WikiParseError
    try:
        source_path = ctx.safe_path(row['import_path'])
        original_bytes = source_path.read_bytes()
        expected_sha = row.get('sha256')
        if expected_sha and hashlib.sha256(original_bytes).hexdigest() != expected_sha:
            return False
        original = original_bytes.decode('utf-8')
        source = parse_template(original)
        target = parse_template(text)
        if source.name != target.name:
            return False
        source_links = source.values('interlangue')
        if source_links:
            # A prior bilingual publication may already have inserted the
            # reviewed link.  Preservation then means byte-for-byte identity;
            # the renderer is not allowed to replace or duplicate it.
            return (
                len(source_links) == 1
                and target.values('interlangue') == source_links
                and target.raw == source.raw
                and text.strip() == target.raw
            )
        parts = _split_top_level(target.raw[2:-2])
        links = [p for p in parts[1:] if p.split('=', 1)[0].strip() == 'interlangue']
        without = '{{' + '|'.join(p for p in parts if p not in links) + '}}'
        return len(links) == 1 and without == source.raw and text.strip() == target.raw
    except (OSError, ValueError, KeyError, WikiParseError):
        return False

def source_keywords(ctx: PackageContext) -> set[str]:
    if not _valid_translation_source_preservation(ctx):
        return set()
    lock = ctx.load_json('data/fr_page_metadata_lock.json') or {}
    return {term for row in [lock.get('debate') or {}, *lock.get('arguments', [])] for term in row.get('keywords', [])}
