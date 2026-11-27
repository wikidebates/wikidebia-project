"""Pure public quote index and final translation duplicate gate.

Identical implementation in the kit and independently installed validator.
No network, editorial authority or wiki mutation. An index digest checks
integrity, not authenticity or the current state of a non-atomic snapshot.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import unicodedata


class QuoteIndexError(ValueError):
    pass


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def is_digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


SCHEMA = "wikidebia-public-quote-index-1"
ALGORITHM = "literal-nfc-space-and-omission-aware-words-1"
COMPLETE = "complete_for_enumerated_raw_scope"
ROOTS = {"fr": "Modèle:Citation", "en": "Template:Quote"}
MAX_PAGES = 100_000
MAX_MATCHES = 100


def _integer(value, minimum=1):
    if type(value) is not int or value < minimum:
        raise QuoteIndexError("invalid_public_index_integer")


def _title(value):
    return " ".join(unicodedata.normalize("NFC", value).replace("_", " ").split())


def validate(value, expected_sha, lang, *, allow_partial=False, now=None,
             max_age_hours=24):
    if (not is_digest(expected_sha) or not isinstance(value, dict)
            or digest(value) != expected_sha):
        raise QuoteIndexError("public_index_digest_mismatch")
    if (lang not in ROOTS or set(value) != {
            "schema", "algorithm", "unicode_version", "language", "status",
            "started_utc", "finished_utc", "template_titles", "pages_enumerated",
            "pages", "issues"}
            or value["schema"] != SCHEMA or value["algorithm"] != ALGORITHM
            or value["unicode_version"] != unicodedata.unidata_version
            or value["language"] != lang or value["status"] not in {COMPLETE, "incomplete"}):
        raise QuoteIndexError("invalid_public_index_schema")
    if not 0 < max_age_hours <= 168:
        raise QuoteIndexError("invalid_public_index_age_limit")
    now = now or datetime.now(timezone.utc)
    try:
        start, finish = (datetime.fromisoformat(value[k]) for k in ("started_utc", "finished_utc"))
        if (start.tzinfo is None or finish.tzinfo is None or now.tzinfo is None
                or start > finish or finish > now + timedelta(minutes=5)):
            raise ValueError()
        age = max(timedelta(0), now-start)
    except (ValueError, TypeError, AttributeError):
        raise QuoteIndexError("invalid_public_index_timestamps") from None
    stale = age > timedelta(hours=max_age_hours)
    titles = value["template_titles"]
    if (not isinstance(titles, list) or len(titles) > 100
            or not all(isinstance(t,str) and t for t in titles)
            or titles != sorted(set(titles))):
        raise QuoteIndexError("invalid_public_index_aliases")
    _integer(value["pages_enumerated"], 0)
    issues = value["issues"]
    if not isinstance(issues, dict):
        raise QuoteIndexError("invalid_public_index_issues")
    for k,v in issues.items():
        if not isinstance(k,str) or not k:
            raise QuoteIndexError("invalid_public_index_issue")
        _integer(v, 0)
    pages = value["pages"]
    if not isinstance(pages,list) or len(pages) > min(MAX_PAGES,value["pages_enumerated"]):
        raise QuoteIndexError("invalid_public_index_pages")
    previous, invalid = 0, 0
    seen_titles = set()
    for p in pages:
        if not isinstance(p,dict) or set(p) != {
                "page_id","title","revision","argument_template_present",
                "quotes","invalid_occurrences"}:
            raise QuoteIndexError("invalid_public_index_page")
        for field in ("page_id","revision"):
            _integer(p[field])
        _integer(p["invalid_occurrences"], 0)
        invalid += p["invalid_occurrences"]
        if (p["page_id"] <= previous or not isinstance(p["title"],str)
                or not _title(p["title"]) or _title(p["title"]) in seen_titles
                or type(p["argument_template_present"]) is not bool
                or not isinstance(p["quotes"],list)):
            raise QuoteIndexError("invalid_public_index_page_identity")
        previous = p["page_id"]
        seen_titles.add(_title(p["title"]))
        last = 0
        for q in p["quotes"]:
            if not isinstance(q,dict) or set(q) != {"ordinal","literal_sha256","words_sha256"}:
                raise QuoteIndexError("invalid_public_index_quote")
            _integer(q["ordinal"])
            if (q["ordinal"] <= last or q["ordinal"] > len(p["quotes"])+p["invalid_occurrences"]
                    or not is_digest(q["literal_sha256"])
                    or (q["words_sha256"] is not None and not is_digest(q["words_sha256"]))):
                raise QuoteIndexError("invalid_public_index_quote_identity")
            last = q["ordinal"]
    complete = value["status"] == COMPLETE
    if complete and (ROOTS[lang] not in titles or len(pages)!=value["pages_enumerated"]
                     or any(issues.values()) or invalid):
        raise QuoteIndexError("contradictory_public_index_coverage")
    if (not complete or stale) and not allow_partial:
        raise QuoteIndexError("public_index_stale" if stale else "public_index_incomplete")
    return {"index_sha256": expected_sha, "status": value["status"],
            "started_utc": value["started_utc"], "finished_utc": value["finished_utc"],
            "age_hours_at_check": round(age.total_seconds()/3600,3), "stale": stale,
            "pages_enumerated": value["pages_enumerated"], "pages_indexed": len(pages),
            "invalid_occurrences": invalid, "issues": issues,
            "complete_fresh_literal_scope": complete and not stale,
            "non_atomic": True, "publication_authorized": False}


OMISSION = re.compile(r'\[\s*(?:\.{3,}|…)+\s*\]|\(\s*(?:\.{3,}|…)+\s*\)|\.{3,}|…')

def normalized(text):
    return " ".join(unicodedata.normalize("NFC", text).split())


def words(fragments):
    # An explicit sentinel prevents joining non-contiguous selected excerpts.
    result = []
    pieces = [part for fragment in fragments for part in OMISSION.split(normalized(fragment))]
    for i, text in enumerate(pieces):
        if i:
            result.append("\0")
        result.extend(re.findall(r"[^\W_]+(?:'[^\W_]+)*",
                      text.casefold().replace("’", "'")))
    return tuple(result)


def public_fingerprints(fragments):
    """Exchange contract with public_quote_index.py, version 1."""
    form = tuple(normalized(s) for s in fragments)
    if not form or not all(form):
        raise QuoteIndexError("empty_duplicate_audit_fragment")
    seq = words(form)
    return {"literal_sha256":digest(list(form)),
            "words_sha256":digest(list(seq)) if any(w!="\0" for w in seq) else None}



GATE = "wikidebia-final-quote-duplicate-audit-1"
INDEX_PATH = "reviews/en/public_quote_index.json"
MAX_INDEX_BYTES = 64 * 1024 * 1024


def _pinned_self_revision(argument):
    """Do not exclude a public page merely because its title matches.

    The existing owner-approved update contract is checked separately by the
    normal workflow. Here require its exact revision and title binding.
    A successor or an unpinned same-title page is conservatively not exempt.
    """
    update = argument.get("existing_english_update")
    if not isinstance(update, dict):
        return None
    if (update.get("owner_approved") is True and update.get("allow_proposed_change") is True
            and update.get("decision") == "explicit_user_request"
            and update.get("language") == "en" and update.get("page_id") == argument["id"]
            and update.get("title") == argument["canonical_title"]
            and type(update.get("observed_revision_id")) is int
            and update["observed_revision_id"] > 0
            and is_digest(update.get("observed_sha256"))
            and is_digest(update.get("authorization_receipt_sha256"))):
        return update["observed_revision_id"]
    return None


def _final_occurrences(arguments):
    if not isinstance(arguments, list):
        raise QuoteIndexError("invalid_final_quote_arguments")
    pages, titles, ids, scope = set(), set(), set(), []
    for a in arguments:
        if not isinstance(a, dict) or not isinstance(a.get("id"), str) or not a["id"]:
            raise QuoteIndexError("invalid_final_quote_page")
        title = a.get("canonical_title")
        if (not isinstance(title, str) or not _title(title) or a["id"] in pages
                or _title(title) in titles):
            raise QuoteIndexError("duplicate_or_invalid_final_quote_page")
        pages.add(a["id"])
        titles.add(_title(title))
        quotes = a.get("citations", [])
        if not isinstance(quotes, list):
            raise QuoteIndexError("invalid_final_quote_list")
        for q in quotes:
            if (not isinstance(q, dict) or not isinstance(q.get("id"), str)
                    or not q["id"].startswith(a["id"]+"-C") or q["id"] in ids):
                raise QuoteIndexError("duplicate_or_invalid_final_quote_identity")
            ids.add(q["id"])
            params = q.get("parameters")
            if not isinstance(params, list) or any(not isinstance(p, dict) for p in params):
                raise QuoteIndexError("invalid_final_quote_parameters")
            values = [p.get("value") for p in params if p.get("name") == "quote"]
            if (len(values) != 1 or not isinstance(values[0], str)
                    or not values[0].strip() or values[0].strip() != q.get("quote", "").strip()):
                raise QuoteIndexError("final_quote_parameter_mismatch")
            origin = q.get("translation_origin", "ai_translation")
            if origin not in {"ai_translation", "published_translation"}:
                raise QuoteIndexError("invalid_final_quote_origin")
            scope.append({"page_id":a["id"], "citation_id":q["id"],
                          "title":_title(title), "own_revision":_pinned_self_revision(a),
                          "origin":origin, **public_fingerprints((values[0],))})
    return sorted(scope, key=lambda r:(r["page_id"],r["citation_id"]))


def _ref(row):
    return {"page_id":row["page_id"],"citation_id":row["citation_id"]}


def final_audit(arguments, index, expected_sha, source_lock_sha, *, now=None):
    """Audit ALL selected EN quotes, not just retrieved published passages.

    Exact literal collisions block new selections; token-identical variants
    are separate editorial signals. Historical duplicates unrelated to the
    current selection do not prevent translation. No absence proof for
    partial overlaps, transclusion-expanded text, or paraphrases.
    """
    if not is_digest(source_lock_sha):
        raise QuoteIndexError("invalid_final_quote_source_lock")
    now = now or datetime.now(timezone.utc)
    coverage = validate(index, expected_sha, "en", now=now)
    scope = _final_occurrences(arguments)
    literal, token = defaultdict(list), defaultdict(list)
    for row in scope:
        literal[row["literal_sha256"]].append(row)
        if row["words_sha256"] is not None:
            token[row["words_sha256"]].append(row)

    def groups(index, variant=False):
        result = []
        for key, rows in sorted(index.items()):
            if len({r["page_id"] for r in rows}) <= 1:
                continue
            if variant and len({r["literal_sha256"] for r in rows}) <= 1:
                continue
            result.append({"sha256":key,"occurrences":[_ref(r) for r in rows]})
        return result

    local_exact = groups(literal)
    local_variants = groups(token, variant=True)
    public_literal, public_words = defaultdict(list), defaultdict(list)
    for p in index["pages"]:
        for q in p["quotes"]:
            ref = {"wiki_page_id":p["page_id"],"wiki_revision":p["revision"],
                   "wiki_title":p["title"],"quote_ordinal":q["ordinal"],
                   "literal_sha256":q["literal_sha256"]}
            public_literal[q["literal_sha256"]].append(ref)
            if q["words_sha256"] is not None:
                public_words[q["words_sha256"]].append(ref)
    public_exact, public_variants = [], []
    self_excluded = 0
    for row in scope:
        def own(p):
            return (row["own_revision"] is not None and row["own_revision"] == p["wiki_revision"]
                    and row["title"] == _title(p["wiki_title"]))
        exact = public_literal.get(row["literal_sha256"], [])
        variants = [p for p in public_words.get(row["words_sha256"], [])
                    if p["literal_sha256"] != row["literal_sha256"]]
        for matches, out in ((exact,public_exact),(variants,public_variants)):
            self_excluded += sum(own(p) for p in matches)
            hits = [p for p in matches if not own(p)]
            if hits:
                out.append({**_ref(row),"matching_occurrences":len(hits),
                            "matches":hits[:MAX_MATCHES],"matches_truncated":len(hits)>MAX_MATCHES})
    status = "blocked_exact_duplicates" if local_exact or public_exact else "clear_exact_literal_scope"
    value = {"schema":GATE, "status":status, "source_lock_sha256":source_lock_sha,
             "index_sha256":expected_sha,"scope_sha256":digest(scope),
             "checked_at":now.isoformat(),"local_occurrences":len(scope),
             "published_occurrences":sum(r["origin"]=="published_translation" for r in scope),
             "ai_occurrences":sum(r["origin"]=="ai_translation" for r in scope),
             "local_exact":local_exact,"public_exact":public_exact,
             "local_word_variants":local_variants,"public_word_variants":public_variants,
             "same_pinned_page_matches_excluded":self_excluded,
             "public_pages_indexed":coverage["pages_indexed"],
             "partial_overlap_across_wiki_checked":False,
             "publication_authorized":False}
    return {**value,"audit_sha256":digest(value)}


def verify_final_audit(audit, arguments, index, source_lock_sha, *, fresh=False, now=None):
    if not isinstance(audit, dict) or not is_digest(audit.get("index_sha256")):
        raise QuoteIndexError("missing_final_quote_audit")
    try:
        checked = datetime.fromisoformat(audit["checked_at"])
    except (ValueError, TypeError, KeyError):
        raise QuoteIndexError("invalid_final_quote_audit_timestamp") from None
    current = now or datetime.now(timezone.utc)
    if (checked.tzinfo is None or current.tzinfo is None
            or checked > current + timedelta(minutes=5)):
        raise QuoteIndexError("invalid_final_quote_audit_timestamp")
    derived = final_audit(arguments,index,audit["index_sha256"],source_lock_sha,now=checked)
    if derived != audit:
        raise QuoteIndexError("final_quote_audit_mismatch")
    if derived["status"] != "clear_exact_literal_scope":
        raise QuoteIndexError("final_quote_exact_duplicates")
    if fresh:
        validate(index,audit["index_sha256"],"en",now=current)
    return derived
