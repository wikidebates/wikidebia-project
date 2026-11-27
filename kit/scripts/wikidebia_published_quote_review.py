"""Experimental, private review of published quote provenance.

This module prepares a candidate for an editor; it does NOT approve rights,
alter a translation lock, or enable a production rendering profile. A sealed
proposal is not proof of the truth of an editorial or legal attestation.
"""
from __future__ import annotations

import argparse
import copy
from datetime import date
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

import wikidebia_quote_bridge as bridge
from wikidebia_quote_duplicates import published_occurrence

SCHEMA = "wikidebia-published-quote-candidate-1"
REVIEW = "wikidebia-published-quote-editorial-review-1"
PROJECTION = "wikidebia-published-quote-proposal-1"
DECISIONS = {"complete_equivalent", "boundary_adjustment", "omission_adjustment"}
SOURCE_FIELDS = {"schema", "provider", "mia_url", "quote_sha256",
                 "quote_wikitext_sha256", "metadata_sha256"}
EDITION_FIELDS = ("authors","article","work","volume","issue","location",
                  "page","publisher","place","date","link")
RIGHTS_BASES = {"public_domain", "compatible_license", "explicit_permission",
                "reviewed_quotation_exception"}
# Deliberately reject wikitext requiring escaping until the rendering
# contract has been exercised independently. Never strip or rewrite it.
UNSAFE = re.compile(r"[{}|<>]|\[\[|\]\]|'{2,}|[\x00-\x1f\x7f]")
OMISSION = " […] "


def fail(reason):
    raise bridge.QuoteBridgeError(reason)


def keys(value, fields):
    if not isinstance(value,dict) or set(value)!=set(fields):
        fail("published_quote_invalid_fields")


def hexes(value, fields):
    if any(not bridge.is_digest(value.get(k)) for k in fields):
        fail("published_quote_invalid_digest")


def text(value, minimum=1, maximum=4000):
    if not isinstance(value,str) or not minimum<=len(value.strip())<=maximum:
        fail("published_quote_missing_review_text")
    return value.strip()


def integer(value, minimum):
    if type(value) is not int or value<minimum:
        fail("published_quote_invalid_integer")


def review_date(value):
    try:
        if not isinstance(value,str) or date.fromisoformat(value).isoformat()!=value:
            raise ValueError()
    except ValueError:
        fail("published_quote_invalid_review_date")


def https(value, *, provider=False):
    if not isinstance(value,str) or any(c.isspace() for c in value):
        fail("published_quote_invalid_url")
    try:
        p=urlsplit(value)
        if (p.scheme!="https" or not p.hostname or p.username is not None
                or p.password is not None or p.port not in (None,443)
                or not p.path or p.path=="/"):
            fail("published_quote_invalid_url")
    except ValueError:
        fail("published_quote_invalid_url")
    if provider:
        if p.hostname in {"marxists.org","www.marxists.org"} and "/francais/" not in p.path:
            return
        if p.hostname=="wikirouge.net" and p.path.startswith("/texts/en/"):
            return
        # Exceptional mirror URLs may be supported by retrieval, but are not
        # admitted by this first projection contract without an edition review.
        fail("published_quote_unsupported_target_provider")


def validate_reference(ref):
    keys(ref,{"revision","template_index","template_sha256","quote_sha256"})
    integer(ref["revision"],1)
    integer(ref["template_index"],0)
    hexes(ref,("template_sha256","quote_sha256"))


def _validate_receipt(row,item):
    bridge._reviewed_fragments(row,item)
    passage=row["published_passage"]
    receipt=passage["receipt"]
    keys(receipt,{"schema","source","target","decision","fragments",
                  "review_packet_sha256","reviewer","semantic_status","rights",
                  "auto_publish","entry_sha256"})
    hexes(receipt,("review_packet_sha256","entry_sha256"))
    text(receipt["reviewer"],1,120)
    source=receipt["source"]
    keys(source,SOURCE_FIELDS|{"source_key","has_explicit_ellipsis","occurrence"})
    if (source["schema"]!="wikidebia-mia-prepared-source-1"
            or source["provider"]!="mia"
            or type(source["has_explicit_ellipsis"]) is not bool
            or bridge.digest({k:source[k] for k in SOURCE_FIELDS})!=source["source_key"]):
        fail("published_quote_source_identity_mismatch")
    hexes(source,("source_key","quote_sha256","quote_wikitext_sha256","metadata_sha256"))
    https(source["mia_url"])
    if urlsplit(source["mia_url"]).hostname!="www.marxists.org":
        fail("published_quote_source_provider_mismatch")
    old=source["occurrence"]
    keys(old,{"revision","template_index","template_sha256"})
    integer(old["revision"],1)
    integer(old["template_index"],0)
    hexes(old,("template_sha256",))
    current=row.get("citation_ref")
    validate_reference(current)
    if current["revision"]!=item["revision"] or current["quote_sha256"]!=source["quote_sha256"]:
        fail("published_quote_current_occurrence_mismatch")
    # Historical receipt occurrence may differ: the stable source identity is
    # re-bound to the actual current occurrence by the resolver.
    occurrence=published_occurrence(row,item["id"])
    target=receipt["target"]
    keys(target,{"document","char_start","char_end","text_sha256","candidate_key"})
    hexes(target,("text_sha256","candidate_key"))
    if bridge.digest({k:v for k,v in target.items() if k!="candidate_key"})!=target["candidate_key"]:
        fail("published_quote_target_identity_mismatch")
    https(target["document"]["url"],provider=True)
    spans=occurrence.spans
    full=len(spans)==1 and spans[0]==(target["char_start"],target["char_end"])
    decision=receipt["decision"]
    if decision not in DECISIONS:
        fail("published_quote_unaccepted_equivalence")
    if decision=="complete_equivalent" and (
            not full or receipt["fragments"][0]["text_sha256"]!=target["text_sha256"]):
        fail("published_quote_incomplete_equivalence")
    if decision=="boundary_adjustment" and (len(spans)!=1 or full):
        fail("published_quote_invalid_boundary_adjustment")
    if decision=="omission_adjustment" and (len(spans)<2 or not source["has_explicit_ellipsis"]):
        fail("published_quote_invalid_omission_adjustment")
    evidence=row.get("evidence")
    keys(evidence,{"origin","receipt_sha256","publication","rights"})
    if (evidence["origin"]!="revalidated_existing_receipt"
            or evidence["rights"]!="unreviewed"
            or not isinstance(evidence["publication"],dict)):
        fail("published_quote_missing_revalidation_origin")
    return occurrence


def prepare(request,handoff,handoff_sha,lock_sha,items,owners):
    """Return one candidate per strictly verified reviewed handoff row.

    The evidence from a real resolver run is private and still advisory.
    Do not manufacture metadata or review rights from license signals.
    """
    summary=bridge.inspect_handoff(request,handoff,handoff_sha,lock_sha,items,owners)
    wanted=bridge.validate_request(request,lock_sha,items)
    candidates=[]
    for row in handoff["rows"]:
        if row["state"]!=bridge.REVIEWED:
            continue
        item=wanted[row["id"]]
        occurrence=_validate_receipt(row,item)
        candidate={"schema":SCHEMA,"source_lock_sha256":lock_sha,
                   "request_sha256":summary["request_sha256"],"handoff_sha256":handoff_sha,
                   "page_id":owners[row["id"]],"item":copy.deepcopy(item),
                   "row":copy.deepcopy(row),
                   "target_url":row["published_passage"]["receipt"]["target"]["document"]["url"],
                   "plain_quote":OMISSION.join(occurrence.fragments),
                   "rights":"unreviewed","publication_authorized":False}
        candidates.append(candidate)
    return candidates


def blank(candidate):
    return {"schema":REVIEW,"candidate_sha256":bridge.digest(candidate),
            "status":"pending","edition":{k:None for k in EDITION_FIELDS},
            "edition_review":{"reviewer":"","reviewed_on":"","evidence_urls":[],
                              "same_work_and_authorship_confirmed":False,
                              "english_edition_metadata_verified":False,
                              "missing_metadata_reviewed":False,
                              "attribution_and_translation_credit_preserved":False,
                              "note":""},
            "rights_review":{"status":"pending","basis":None,"reviewer":"",
                             "reviewed_on":"","evidence_urls":[],"note":"",
                             "exact_passage_and_target_site_reviewed":False,
                             "all_conditions_representable":False},
            "completeness_review":{"reviewer":"","reviewed_on":"","note":"",
                                   "full_meaning_and_boundaries_confirmed":False}}


def _urls(urls):
    if not isinstance(urls,list) or not urls or len(urls)>20 or len(set(urls))!=len(urls):
        fail("published_quote_missing_evidence_urls")
    for url in urls:
        https(url)


def _reviewer(record):
    text(record["reviewer"],3,120)
    review_date(record["reviewed_on"])
    text(record["note"],20)


def proposal(candidate,expected_sha,review):
    """Validate a separately completed proposal, never grant publishing rights.

    Metadata comes from the identified English edition, not the French fields.
    The explicit reviewer is accountable for evidence; this code checks the
    structure and exact binding, not the independent legal conclusion.
    """
    if not bridge.is_digest(expected_sha) or bridge.digest(candidate)!=expected_sha:
        fail("published_quote_candidate_digest_mismatch")
    keys(candidate,{"schema","source_lock_sha256","request_sha256","handoff_sha256",
                    "page_id","item","row","target_url","plain_quote","rights",
                    "publication_authorized"})
    if (candidate["schema"]!=SCHEMA or candidate["rights"]!="unreviewed"
            or candidate["publication_authorized"] is not False
            or candidate["row"].get("state")!=bridge.REVIEWED
            or candidate["item"]["id"]!=candidate["row"]["id"]):
        fail("published_quote_candidate_scope_mismatch")
    hexes(candidate,("source_lock_sha256","request_sha256","handoff_sha256"))
    row,item=candidate["row"],candidate["item"]
    occurrence=_validate_receipt(row,item)
    expected=OMISSION.join(occurrence.fragments)
    if (candidate["plain_quote"]!=expected or candidate["target_url"]!=
            row["published_passage"]["receipt"]["target"]["document"]["url"]):
        fail("published_quote_candidate_changed")
    keys(review,{"schema","candidate_sha256","status","edition","edition_review",
                 "rights_review","completeness_review"})
    if (review["schema"]!=REVIEW or review["candidate_sha256"]!=expected_sha
            or review["status"]!="reviewed_for_proposal"):
        fail("published_quote_editorial_review_required")
    edition=review["edition"]
    keys(edition,EDITION_FIELDS)
    for name,value in edition.items():
        if value is not None and (text(value)!=value or UNSAFE.search(value)):
            fail("published_quote_unsafe_or_invalid_metadata")
    if not edition["authors"] or not (edition["article"] or edition["work"]):
        fail("published_quote_missing_attribution")
    if edition["link"]!=candidate["target_url"]:
        fail("published_quote_link_not_evidenced_target")
    ed=review["edition_review"]
    keys(ed,{"reviewer","reviewed_on","evidence_urls","same_work_and_authorship_confirmed",
             "english_edition_metadata_verified","missing_metadata_reviewed",
             "attribution_and_translation_credit_preserved","note"})
    _reviewer(ed)
    _urls(ed["evidence_urls"])
    if edition["link"] not in ed["evidence_urls"] or any(ed[k] is not True for k in (
            "same_work_and_authorship_confirmed","english_edition_metadata_verified",
            "missing_metadata_reviewed","attribution_and_translation_credit_preserved")):
        fail("published_quote_edition_review_incomplete")
    rights=review["rights_review"]
    keys(rights,{"status","basis","reviewer","reviewed_on","evidence_urls","note",
                 "exact_passage_and_target_site_reviewed","all_conditions_representable"})
    _reviewer(rights)
    _urls(rights["evidence_urls"])
    if (rights["status"]!="reuse_reviewed" or rights["basis"] not in RIGHTS_BASES
            or rights["exact_passage_and_target_site_reviewed"] is not True
            or rights["all_conditions_representable"] is not True):
        fail("published_quote_rights_review_required")
    comp=review["completeness_review"]
    keys(comp,{"reviewer","reviewed_on","note","full_meaning_and_boundaries_confirmed"})
    _reviewer(comp)
    if comp["full_meaning_and_boundaries_confirmed"] is not True:
        fail("published_quote_completeness_review_required")
    if expected.strip()!=expected or UNSAFE.search(expected):
        fail("published_quote_requires_safe_rendering_review")
    source=bridge.parameter_pairs(item["source_parameters"])
    warning_values=[source[k] for k in ("avertissements-citation","avertissements citation","avertissements") if k in source]
    if len(set(v for v in warning_values if v))>1:
        fail("published_quote_ambiguous_source_warnings")
    warnings=[part.strip() for part in ",".join(dict.fromkeys(warning_values)).split(",") if part.strip()]
    # Do not attach AI-translated quote to a published translation. An existing
    # ambiguous AI warning must be reviewed, never silently removed.
    if "AI-translated quote" in warnings or UNSAFE.search(", ".join(warnings)):
        fail("published_quote_existing_warning_requires_review")
    params=[{"name":"quote","value":expected}]
    params.extend({"name":k,"value":edition[k]} for k in EDITION_FIELDS if edition[k] is not None)
    if warnings:
        params.append({"name":"warnings","value":", ".join(warnings)})
    return {"schema":PROJECTION,"candidate_sha256":expected_sha,
            "review_sha256":bridge.digest(review),"citation_id":item["id"],
            "receipt_sha256":row["published_passage"]["receipt"]["entry_sha256"],
            "translation_origin":"published_translation","parameters":params,
            "rights_status":"editorial_attestation_recorded_not_independently_verified",
            "publication_authorized":False,"translation_mutated":False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("debate_id")
    p.add_argument("--work-id",required=True)
    p.add_argument("--project-root",type=Path,default=Path.cwd())
    p.add_argument("--request",type=Path,required=True)
    p.add_argument("--handoff",type=Path,required=True)
    p.add_argument("--handoff-sha",required=True)
    a=p.parse_args(argv)
    try:
        _,lock,items,owners=bridge.snapshot(a.project_root.resolve(),a.debate_id,a.work_id)
        candidates=prepare(bridge.load_json(a.request),bridge.load_json(a.handoff),
                           a.handoff_sha,lock,items,owners)
        # Only a safe aggregate. Candidate text stays in process; no active
        # review files or locks are written by this experimental CLI.
        result={"candidate_sha256s":[bridge.digest(c) for c in candidates],
                "candidates":len(candidates),"publication_authorized":False,
                "translation_mutated":False}
    except (ValueError,RuntimeError,OSError,KeyError,TypeError,AttributeError) as exc:
        print(json.dumps({"status":"blocked","reason":str(exc) if isinstance(exc,bridge.QuoteBridgeError) else type(exc).__name__}))
        return 1
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
