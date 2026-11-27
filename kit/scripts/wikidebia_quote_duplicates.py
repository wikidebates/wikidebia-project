"""Read-only cross-batch duplicate diagnostics; no text in reports.

Exact normalized text is not proof of the same edition or author. Lexical
similarity and coordinate overlap are review signals, never authorizations.
Scope: locked French Citation templates and inspected published EN passages,
not all public pages or AI drafts. No automatic deletion or replacement.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import combinations
import json
from pathlib import Path
import re
import unicodedata

import wikidebia_quote_bridge as bridge

SCHEMA = "wikidebia-quote-duplicate-audit-1"
MAX_PAIRS = 50_000
MAX_TOKENS = 512
MAX_COMPARISON_CELLS = 10_000_000
OMISSION = re.compile(r'\[\s*(?:\.{3,}|…)+\s*\]|\(\s*(?:\.{3,}|…)+\s*\)|\.{3,}|…')


@dataclass(frozen=True)
class Occurrence:
    page: str
    citation: str
    fragments: tuple[str, ...]
    document: str | None = None
    spans: tuple[tuple[int, int], ...] = ()


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


def refs(rows):
    return [{"page_id": p, "citation_id": c}
            for p, c in sorted({(r.page, r.citation) for r in rows})]


def cross_pages(a, b=()):
    return len({r.page for r in a} | {r.page for r in b}) > 1


def pair_refs(a, b):
    return {"left": refs(a), "right": refs(b)}


def analyze(rows, *, max_pairs=MAX_PAIRS, max_tokens=MAX_TOKENS,
            max_comparison_cells=MAX_COMPARISON_CELLS):
    rows = list(rows)
    if min(max_pairs, max_tokens, max_comparison_cells) < 1:
        raise bridge.QuoteBridgeError("invalid_duplicate_comparison_limits")
    identities, forms, docs = set(), defaultdict(list), defaultdict(list)
    for r in rows:
        identity = (r.page, r.citation)
        if identity in identities or not r.page or not r.citation:
            raise bridge.QuoteBridgeError("duplicate_audit_occurrence_identity")
        identities.add(identity)
        form = tuple(normalized(s) for s in r.fragments)
        if not form or not all(form):
            raise bridge.QuoteBridgeError("empty_duplicate_audit_fragment")
        forms[form].append(r)
        if r.document is not None:
            docs[r.document].append((form, r))
    exact = [{"text_sha256": bridge.digest(list(form)), "occurrences": refs(forms[form])}
             for form in sorted(forms) if cross_pages(forms[form])]
    tokens = {form: words(form) for form in forms}
    word_groups = defaultdict(list)
    for form, seq in tokens.items():
        if seq:
            word_groups[seq].append(form)
    variants = []
    for seq, group in sorted(word_groups.items()):
        if len(group) > 1:
            combined = [r for form in group for r in forms[form]]
            if cross_pages(combined):
                variants.append({"token_sha256": bridge.digest(list(seq)),
                                 "occurrences": refs(combined)})

    coordinate, doc_pairs = [], 0
    doc_limited = False
    for document, group in sorted(docs.items()):
        group.sort(key=lambda v: (v[1].page, v[1].citation))
        for (left, a), (right, b) in combinations(group, 2):
            # Bound all iterations, even those skipped as identical or same-page.
            if doc_pairs >= max_pairs:
                doc_limited = True
                break
            doc_pairs += 1
            if a.page == b.page or left == right:
                continue
            overlap = sum(max(0, min(hi, end)-max(lo, start))
                          for lo, hi in a.spans for start, end in b.spans)
            if overlap:
                coordinate.append({**pair_refs([a], [b]), "document_sha256": document,
                                   "overlap_characters": overlap})
        if doc_limited:
            break

    # Compare only distinct forms sharing a four-word gram. Identical texts
    # are grouped above, not expanded into quadratic pair lists. Explicit
    # caps apply to iteration as well as unique pairs, with visible diagnostics.
    index = defaultdict(list)
    too_long = 0
    for form, seq in sorted(tokens.items()):
        if len(seq) > max_tokens:
            too_long += 1
            continue
        if len(seq) >= 6:
            for gram in sorted({seq[i:i+4] for i in range(len(seq)-3)
                                if "\0" not in seq[i:i+4]}):
                index[gram].append(form)
    pairs, attempts = set(), 0
    lexical_limited = False
    for gram in sorted(index):
        for a, b in combinations(index[gram], 2):
            if attempts >= max_pairs:
                lexical_limited = True
                break
            attempts += 1
            if tokens[a] != tokens[b] and cross_pages(forms[a], forms[b]):
                pairs.add((a,b))
        if lexical_limited:
            break
    near, partial = [], []
    cells, compared = 0, 0
    cells_limited = False
    for a, b in sorted(pairs):
        x, y = tokens[a], tokens[b]
        cost = len(x)*len(y)
        if cells + cost > max_comparison_cells:
            cells_limited = True
            break
        cells += cost
        compared += 1
        matcher = SequenceMatcher(None, x, y, autojunk=False)
        longest, matched = 0, 0
        for block in matcher.get_matching_blocks():
            run = 0
            for token in x[block.a:block.a+block.size]:
                run = 0 if token == "\0" else run+1
                matched += token != "\0"
                longest = max(longest, run)
        shorter, longer = sorted((sum(t != "\0" for t in x), sum(t != "\0" for t in y)))
        data = pair_refs(forms[a], forms[b])
        ratio = 2*matched/(shorter+longer) if shorter else 0
        if shorter >= 8 and shorter/longer >= .8 and ratio >= .85:
            near.append({**data, "token_similarity": round(ratio, 4)})
        elif longest >= 8 and (longest >= 20 or longest/shorter >= .5):
            partial.append({**data, "shared_consecutive_words": longest})
    return {"occurrences": len(identities), "pages": len({r.page for r in rows}),
            "exact_text_groups": exact, "same_words_different_form_groups": variants,
            "same_document_partial_overlaps": coordinate,
            "near_lexical_matches": near, "partial_lexical_overlaps": partial,
            "lexical_candidate_pairs_compared": compared,
            "lexical_pair_iterations": attempts, "document_pair_iterations": doc_pairs,
            "lexical_comparison_cells": cells, "lexical_cell_limit_reached": cells_limited,
            "forms_exceeding_token_limit": too_long,
            "lexical_pair_limit_reached": lexical_limited,
            "document_pair_limit_reached": doc_limited,
            "bounded_similarity_scan_complete": not (too_long or lexical_limited or doc_limited or cells_limited)}


def published_occurrence(row, page):
    passage = row["published_passage"]
    target = passage["receipt"].get("target")
    if not isinstance(target, dict) or not isinstance(target.get("document"), dict):
        raise bridge.QuoteBridgeError("duplicate_audit_missing_target_document")
    doc = target["document"]
    if (set(doc) != {"url", "revision", "body_sha256", "blocks_sha256"}
            or not isinstance(doc["url"], str) or not doc["url"]
            or not bridge.is_digest(doc["body_sha256"])
            or not bridge.is_digest(doc["blocks_sha256"])
            or (doc["revision"] is not None and
                (type(doc["revision"]) is not int or doc["revision"] < 1))):
        raise bridge.QuoteBridgeError("duplicate_audit_invalid_target_document")
    lo, hi = target.get("char_start"), target.get("char_end")
    if type(lo) is not int or type(hi) is not int or not 0 <= lo < hi:
        raise bridge.QuoteBridgeError("duplicate_audit_invalid_target_range")
    fragments = passage["fragments"]
    spans = tuple((f["char_start"], f["char_end"]) for f in fragments)
    previous = None
    for start, end in spans:
        if not lo <= start < end <= hi or (previous is not None and start <= previous):
            raise bridge.QuoteBridgeError("duplicate_audit_invalid_fragment_order")
        previous = end
    return Occurrence(page, row["id"], tuple(f["text"] for f in fragments),
                      bridge.digest(doc), spans)


def audit_batches(lock_sha, all_items, owners, eligible, batches, *, allow_partial=False):
    source_rows = bridge.unique_rows(all_items, "id")
    eligible_rows = bridge.unique_rows(eligible, "id")
    if (set(source_rows) != set(owners) or
            any(source_rows.get(cid) != item for cid, item in eligible_rows.items())):
        raise bridge.QuoteBridgeError("duplicate_audit_invalid_source_scope")
    if not bridge.is_digest(lock_sha):
        raise bridge.QuoteBridgeError("duplicate_audit_invalid_source_lock")
    french = [Occurrence(owners[cid], cid,
                         (bridge.parameter_pairs(item["source_parameters"])["citation"],))
              for cid, item in sorted(source_rows.items())]
    english, seen, summaries = [], set(), []
    states = Counter()
    for request, handoff, handoff_sha in batches:
        summary = bridge.inspect_handoff(request, handoff, handoff_sha,
                                         lock_sha, eligible, owners)
        ids = {row["id"] for row in request["items"]}
        if seen & ids:
            raise bridge.QuoteBridgeError("duplicate_audit_repeated_batch_occurrence")
        seen.update(ids)
        summaries.append({"request_sha256": summary["request_sha256"],
                          "handoff_sha256": summary["handoff_sha256"]})
        states.update(summary["states"])
        for row in handoff["rows"]:
            if row["state"] == bridge.REVIEWED:
                english.append(published_occurrence(row, owners[row["id"]]))
    missing = set(eligible_rows) - seen
    if missing and not allow_partial:
        raise bridge.QuoteBridgeError("duplicate_audit_incomplete_batch_coverage")
    return {"schema": SCHEMA, "source_lock_sha256": lock_sha,
            "batches": sorted(summaries, key=lambda s: s["request_sha256"]),
            "coverage": {"active_locked_french_citations": len(french),
                         "eligible_translation_citations": len(eligible_rows),
                         "french_citations_on_reused_english_pages": len(french)-len(eligible_rows),
                         "returned_occurrences": len(seen),
                         "missing_occurrences": sorted(missing),
                         "all_eligible_batches_covered": not missing,
                         "states": dict(sorted(states.items())),
                         "reviewed_published_english_occurrences": len(english),
                         "french_scope": "active_locked_Citation_templates",
                         "english_scope": "reviewed_published_passages_only",
                         "public_wiki_wide_coverage": False},
            "french": analyze(french), "english": analyze(english),
            "editorial_review_required": True, "rights": "unreviewed",
            "publication_authorized": False, "translation_mutated": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("debate_id")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--batch", nargs=3, action="append", default=[],
                        metavar=("REQUEST", "HANDOFF", "SHA256"))
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args(argv)
    try:
        _, lock_sha, items, owners, eligible = bridge.duplicate_snapshot(
            args.project_root.resolve(), args.debate_id, args.work_id)
        batches = [(bridge.load_json(Path(req)), bridge.load_json(Path(ret)), sha)
                   for req, ret, sha in args.batch]
        result = audit_batches(lock_sha, items, owners, eligible, batches,
                               allow_partial=args.allow_partial)
    except (ValueError, RuntimeError, OSError, KeyError, TypeError, AttributeError) as exc:
        reason = str(exc) if isinstance(exc, bridge.QuoteBridgeError) else type(exc).__name__
        print(json.dumps({"status": "blocked", "reason": reason}))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
