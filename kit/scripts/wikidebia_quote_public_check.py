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

SCHEMA = "wikidebia-public-quote-index-1"
ALGORITHM = "literal-nfc-space-and-omission-aware-words-1"
COMPLETE = "complete_for_enumerated_raw_scope"
ROOTS = {"fr": "Modèle:Citation", "en": "Template:Quote"}
MAX_PAGES = 100_000
MAX_MATCHES = 100


def _integer(value, minimum=1):
    if type(value) is not int or value < minimum:
        raise bridge.QuoteBridgeError("invalid_public_index_integer")


def _title(value):
    return " ".join(unicodedata.normalize("NFC", value).replace("_", " ").split())


def validate(value, expected_sha, lang, *, allow_partial=False, now=None,
             max_age_hours=24):
    if (not bridge.is_digest(expected_sha) or not isinstance(value, dict)
            or bridge.digest(value) != expected_sha):
        raise bridge.QuoteBridgeError("public_index_digest_mismatch")
    if (lang not in ROOTS or set(value) != {
            "schema", "algorithm", "unicode_version", "language", "status",
            "started_utc", "finished_utc", "template_titles", "pages_enumerated",
            "pages", "issues"}
            or value["schema"] != SCHEMA or value["algorithm"] != ALGORITHM
            or value["unicode_version"] != unicodedata.unidata_version
            or value["language"] != lang or value["status"] not in {COMPLETE, "incomplete"}):
        raise bridge.QuoteBridgeError("invalid_public_index_schema")
    if not 0 < max_age_hours <= 168:
        raise bridge.QuoteBridgeError("invalid_public_index_age_limit")
    now = now or datetime.now(timezone.utc)
    try:
        start, finish = (datetime.fromisoformat(value[k]) for k in ("started_utc", "finished_utc"))
        if (start.tzinfo is None or finish.tzinfo is None or now.tzinfo is None
                or start > finish or finish > now + timedelta(minutes=5)):
            raise ValueError()
        age = max(timedelta(0), now-start)
    except (ValueError, TypeError, AttributeError):
        raise bridge.QuoteBridgeError("invalid_public_index_timestamps") from None
    stale = age > timedelta(hours=max_age_hours)
    titles = value["template_titles"]
    if (not isinstance(titles, list) or len(titles) > 100
            or not all(isinstance(t,str) and t for t in titles)
            or titles != sorted(set(titles))):
        raise bridge.QuoteBridgeError("invalid_public_index_aliases")
    _integer(value["pages_enumerated"], 0)
    issues = value["issues"]
    if not isinstance(issues, dict):
        raise bridge.QuoteBridgeError("invalid_public_index_issues")
    for k,v in issues.items():
        if not isinstance(k,str) or not k:
            raise bridge.QuoteBridgeError("invalid_public_index_issue")
        _integer(v, 0)
    pages = value["pages"]
    if not isinstance(pages,list) or len(pages) > min(MAX_PAGES,value["pages_enumerated"]):
        raise bridge.QuoteBridgeError("invalid_public_index_pages")
    previous, invalid = 0, 0
    seen_titles = set()
    for p in pages:
        if not isinstance(p,dict) or set(p) != {
                "page_id","title","revision","argument_template_present",
                "quotes","invalid_occurrences"}:
            raise bridge.QuoteBridgeError("invalid_public_index_page")
        for field in ("page_id","revision"):
            _integer(p[field])
        _integer(p["invalid_occurrences"], 0)
        invalid += p["invalid_occurrences"]
        if (p["page_id"] <= previous or not isinstance(p["title"],str)
                or not _title(p["title"]) or _title(p["title"]) in seen_titles
                or type(p["argument_template_present"]) is not bool
                or not isinstance(p["quotes"],list)):
            raise bridge.QuoteBridgeError("invalid_public_index_page_identity")
        previous = p["page_id"]
        seen_titles.add(_title(p["title"]))
        last = 0
        for q in p["quotes"]:
            if not isinstance(q,dict) or set(q) != {"ordinal","literal_sha256","words_sha256"}:
                raise bridge.QuoteBridgeError("invalid_public_index_quote")
            _integer(q["ordinal"])
            if (q["ordinal"] <= last or q["ordinal"] > len(p["quotes"])+p["invalid_occurrences"]
                    or not bridge.is_digest(q["literal_sha256"])
                    or (q["words_sha256"] is not None and not bridge.is_digest(q["words_sha256"]))):
                raise bridge.QuoteBridgeError("invalid_public_index_quote_identity")
            last = q["ordinal"]
    complete = value["status"] == COMPLETE
    if complete and (ROOTS[lang] not in titles or len(pages)!=value["pages_enumerated"]
                     or any(issues.values()) or invalid):
        raise bridge.QuoteBridgeError("contradictory_public_index_coverage")
    if (not complete or stale) and not allow_partial:
        raise bridge.QuoteBridgeError("public_index_stale" if stale else "public_index_incomplete")
    return {"index_sha256": expected_sha, "status": value["status"],
            "started_utc": value["started_utc"], "finished_utc": value["finished_utc"],
            "age_hours_at_check": round(age.total_seconds()/3600,3), "stale": stale,
            "pages_enumerated": value["pages_enumerated"], "pages_indexed": len(pages),
            "invalid_occurrences": invalid, "issues": issues,
            "complete_fresh_literal_scope": complete and not stale,
            "non_atomic": True, "publication_authorized": False}


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
