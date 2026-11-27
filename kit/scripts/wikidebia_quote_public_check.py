"""Compare verified local quotation occurrences with a public hash snapshot.

Independent consumer checks the exchange format and its coverage, not the
truth of the remote content. The expected hash must come from the trusted
census execution. Exact literal and same-word signals only; never treat a
missing match as permission to publish.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import unicodedata

import wikidebia_quote_bridge as bridge

from wikidebia_quote_index_contract import (
    SCHEMA, ALGORITHM, COMPLETE, ROOTS, MAX_PAGES, MAX_MATCHES,
    QuoteIndexError, validate as _validate, _title,
)


def validate(*args, **kwargs):
    try:
        return _validate(*args, **kwargs)
    except QuoteIndexError as exc:
        raise bridge.QuoteBridgeError(str(exc)) from exc


def compare(rows, value, expected_sha, lang, *, fingerprints, source_items=(),
            allow_partial=False, now=None, max_age_hours=24):
    """Use the same literal/word algorithm as the local duplicate audit.

    FR source references exclude only their own exact pinned revision.
    A title can be reused after deletion or a move: title equality alone
    cannot identify the same page. EN target identity may not exist yet.
    """
    coverage = validate(value,expected_sha,lang,allow_partial=allow_partial,
                        now=now,max_age_hours=max_age_hours)
    literal, words = defaultdict(list), defaultdict(list)
    for p in value["pages"]:
        for q in p["quotes"]:
            ref = {"wiki_page_id":p["page_id"],"wiki_title":p["title"],
                   "wiki_revision":p["revision"],"quote_ordinal":q["ordinal"],
                   "argument_template_present":p["argument_template_present"],
                   "literal_sha256":q["literal_sha256"]}
            literal[q["literal_sha256"]].append(ref)
            if q["words_sha256"] is not None:
                words[q["words_sha256"]].append(ref)
    sources = bridge.unique_rows(list(source_items),"id") if lang=="fr" else {}
    findings = []
    exclusions = 0
    for row in sorted(rows,key=lambda r:(r.page,r.citation)):
        h = fingerprints(row.fragments)
        src = sources.get(row.citation)
        def own(ref):
            return (src is not None and type(src.get("revision")) is int
                    and src["revision"]==ref["wiki_revision"])
        exact = literal.get(h["literal_sha256"],[])
        variants = [ref for ref in words.get(h["words_sha256"],[])
                    if ref["literal_sha256"] != h["literal_sha256"]]
        exclusions += sum(own(ref) for ref in exact+variants)
        for kind, matches in (("exact_literal",exact),("same_words_different_form",variants)):
            matches = [ref for ref in matches if not own(ref)]
            if matches:
                findings.append({"page_id":row.page,"citation_id":row.citation,
                                 "kind":kind,"matching_occurrences":len(matches),
                                 "matching_pages":len({ref["wiki_page_id"] for ref in matches}),
                                 "matches":matches[:MAX_MATCHES],
                                 "matches_truncated":len(matches)>MAX_MATCHES})
    def groups(index, *, variants=False):
        return sum(len({r["wiki_page_id"] for r in refs})>1
                   and (not variants or len({r["literal_sha256"] for r in refs})>1)
                   for refs in index.values())
    return {"language":lang,"coverage":coverage,"local_occurrences":len(rows),
            "existing_exact_groups_across_pages":groups(literal),
            "existing_same_words_different_form_groups_across_pages":groups(words,variants=True),
            "same_imported_page_matches_excluded":exclusions,"findings":findings,
            "lexical_partial_overlap_across_wiki_checked":False,
            "editorial_review_required":True,"publication_authorized":False}
