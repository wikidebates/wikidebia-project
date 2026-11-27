"""Pure published quotation evidence contract (experimental v1).

Identical implementation in kit and validator packages. No workspace,
network, resolver or editorial authority is imported here. Validation checks
binding and structural integrity, not the truth of editorial attestations.
"""
from __future__ import annotations

import copy
from datetime import date
import hashlib
import json
import re
from urllib.parse import urlsplit

class PublishedQuoteError(ValueError):
    pass


def canonical_json(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),
                      allow_nan=False).encode("utf-8")


RECEIPT = "wikidebia-prepared-citation-receipt-1"
REVIEWED = "reviewed_receipt_rights_unreviewed"
def digest(value):
    return hashlib.sha256(canonical_json(value)).hexdigest()


def is_digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def parameter_pairs(parameters):
    if not isinstance(parameters, list):
        raise PublishedQuoteError("invalid_locked_parameters")
    pairs = {}
    for p in parameters:
        if (not isinstance(p, dict) or set(p) != {"name", "value"}
                or not isinstance(p["name"], str) or not isinstance(p["value"], str)):
            raise PublishedQuoteError("invalid_locked_parameter")
        key = p["name"].strip()
        if not key or key in pairs:
            raise PublishedQuoteError("duplicate_or_empty_locked_parameter")
        pairs[key] = p["value"].strip()
    if not pairs.get("citation"):
        raise PublishedQuoteError("missing_locked_citation")
    return pairs


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
UNSAFE = re.compile(r"[{}|<>]|'{2,}|[&\x00-\x1f\x7f]|\[(?!…\])|(?<!…)\]")
OMISSION = " […] "


def fail(reason):
    raise PublishedQuoteError(reason)


def keys(value, fields):
    if not isinstance(value,dict) or set(value)!=set(fields):
        fail("published_quote_invalid_fields")


def hexes(value, fields):
    if any(not is_digest(value.get(k)) for k in fields):
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


def _reviewed_fragments(row, item):
    """Check serialized integrity, not the truth of the editorial decision."""
    passage = row.get("published_passage")
    if (not isinstance(passage, dict) or passage.get("rights") != "unreviewed"
            or passage.get("auto_publish") is not False
            or passage.get("editorial_review_required") is not True):
        raise PublishedQuoteError("invalid_published_passage_scope")
    receipt = passage.get("receipt")
    if not isinstance(receipt, dict):
        raise PublishedQuoteError("missing_published_receipt")
    entry = receipt.get("entry_sha256")
    if (receipt.get("schema") != RECEIPT or not is_digest(entry)
            or digest({k: v for k, v in receipt.items() if k != "entry_sha256"}) != entry
            or receipt.get("rights") != "unreviewed" or receipt.get("auto_publish") is not False
            or receipt.get("semantic_status") != "editorial_decision_recorded"):
        raise PublishedQuoteError("published_receipt_integrity_mismatch")
    source = receipt.get("source") or {}
    params = parameter_pairs(item["source_parameters"])
    if (not is_digest(row.get("source_key")) or source.get("source_key") != row["source_key"]
            or source.get("quote_wikitext_sha256") != hashlib.sha256(
                params["citation"].encode("utf-8")).hexdigest()
            or source.get("metadata_sha256") != digest(sorted(
                (k, v) for k, v in params.items() if k != "citation"))
            or (row.get("evidence") or {}).get("receipt_sha256") != entry):
        raise PublishedQuoteError("published_receipt_source_mismatch")
    fragments = passage.get("fragments")
    expected = receipt.get("fragments")
    if (not isinstance(fragments, list) or not fragments
            or not isinstance(expected, list) or len(fragments) != len(expected)):
        raise PublishedQuoteError("invalid_published_fragments")
    for fragment, proof in zip(fragments, expected):
        if not isinstance(fragment, dict) or not isinstance(proof, dict):
            raise PublishedQuoteError("invalid_published_fragment")
        text = fragment.get("text")
        lo, hi = proof.get("char_start"), proof.get("char_end")
        if (not isinstance(text, str) or not text.strip()
                or type(lo) is not int or type(hi) is not int or not 0 <= lo < hi
                or hi - lo != len(text)
                or {k: v for k, v in fragment.items() if k != "text"} != proof
                or hashlib.sha256(text.encode("utf-8")).hexdigest() != proof.get("text_sha256")):
            raise PublishedQuoteError("published_fragment_integrity_mismatch")
    return digest([f["text"] for f in fragments])


def published_occurrence(row, page):
    passage = row["published_passage"]
    target = passage["receipt"].get("target")
    if not isinstance(target, dict) or not isinstance(target.get("document"), dict):
        raise PublishedQuoteError("duplicate_audit_missing_target_document")
    doc = target["document"]
    if (set(doc) != {"url", "revision", "body_sha256", "blocks_sha256"}
            or not isinstance(doc["url"], str) or not doc["url"]
            or not is_digest(doc["body_sha256"])
            or not is_digest(doc["blocks_sha256"])
            or (doc["revision"] is not None and
                (type(doc["revision"]) is not int or doc["revision"] < 1))):
        raise PublishedQuoteError("duplicate_audit_invalid_target_document")
    lo, hi = target.get("char_start"), target.get("char_end")
    if type(lo) is not int or type(hi) is not int or not 0 <= lo < hi:
        raise PublishedQuoteError("duplicate_audit_invalid_target_range")
    fragments = passage["fragments"]
    spans = tuple((f["char_start"], f["char_end"]) for f in fragments)
    previous = None
    for start, end in spans:
        if not lo <= start < end <= hi or (previous is not None and start <= previous):
            raise PublishedQuoteError("duplicate_audit_invalid_fragment_order")
        previous = end
    return tuple(f["text"] for f in fragments), spans


def canonical_source_link(value):
    """Conservative subset of resolver MIA routing: one literal link.
    Complex wikitext is not eligible for this first projection contract.
    """
    if not isinstance(value,str):
        return None
    value=value.strip()
    if value.startswith("[") and value.endswith("]"):
        value=value[1:-1].split(maxsplit=1)[0] if value[1:-1].strip() else ""
    if value.startswith("//"):
        value="https:"+value
    elif re.match(r"^(?:www\.)?marxists\.org/",value,re.I):
        value="https://"+value
    try:
        p=urlsplit(value)
        if (p.scheme in {"http","https"} and p.hostname in {"marxists.org","www.marxists.org"}
                and p.username is None and p.password is None and p.port in (None,80,443)
                and not p.query and re.fullmatch(r"/[A-Za-z0-9._~/%()+,-]+",p.path)
                and not any(x in {".",".."} for x in p.path.split("/"))):
            return "https://www.marxists.org"+p.path
    except ValueError:
        pass
    return None


def _validate_receipt(row,item):
    if (not isinstance(item,dict) or set(item)!={"id","wiki_title","revision",
            "source_template","source_parameters"} or not isinstance(row,dict)
            or row.get("id")!=item["id"] or row.get("state")!=REVIEWED
            or row.get("source_parameters_sha256")!=digest(item["source_parameters"])):
        fail("published_quote_occurrence_binding_mismatch")
    integer(item["revision"],1)
    text(item["id"],1,200)
    text(item["wiki_title"],1,250)
    if item["source_template"].strip().casefold() not in {"citation","modèle:citation","template:citation"}:
        fail("published_quote_invalid_source_template")
    _reviewed_fragments(row,item)
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
            or digest({k:source[k] for k in SOURCE_FIELDS})!=source["source_key"]):
        fail("published_quote_source_identity_mismatch")
    hexes(source,("source_key","quote_sha256","quote_wikitext_sha256","metadata_sha256"))
    https(source["mia_url"])
    params=parameter_pairs(item["source_parameters"])
    if source["mia_url"]!=canonical_source_link(params.get("lien")):
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
    fragments, spans=published_occurrence(row,item["id"])
    target=receipt["target"]
    keys(target,{"document","char_start","char_end","text_sha256","candidate_key"})
    hexes(target,("text_sha256","candidate_key"))
    if digest({k:v for k,v in target.items() if k!="candidate_key"})!=target["candidate_key"]:
        fail("published_quote_target_identity_mismatch")
    https(target["document"]["url"],provider=True)
    full=len(spans)==1 and spans[0]==(target["char_start"],target["char_end"])
    decision=receipt["decision"]
    if decision not in DECISIONS:
        fail("published_quote_unaccepted_equivalence")
    if decision=="complete_equivalent" and (
            not full or receipt["fragments"][0]["text_sha256"]!=target["text_sha256"]):
        fail("published_quote_incomplete_equivalence")
    if decision=="boundary_adjustment" and (len(spans)!=1 or full):
        fail("published_quote_invalid_boundary_adjustment")
    if decision=="omission_adjustment" and (len(spans)<2 or not source["has_explicit_ellipsis"]
            or not re.search(r"\.{3,}|…",params["citation"])):
        fail("published_quote_invalid_omission_adjustment")
    evidence=row.get("evidence")
    keys(evidence,{"origin","receipt_sha256","publication","rights"})
    if (evidence["origin"]!="revalidated_existing_receipt"
            or evidence["rights"]!="unreviewed"
            or not isinstance(evidence["publication"],dict)):
        fail("published_quote_missing_revalidation_origin")
    return fragments


def blank(candidate):
    return {"schema":REVIEW,"candidate_sha256":digest(candidate),
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
    if not is_digest(expected_sha) or digest(candidate)!=expected_sha:
        fail("published_quote_candidate_digest_mismatch")
    keys(candidate,{"schema","source_lock_sha256","request_sha256","handoff_sha256",
                    "page_id","item","row","target_url","plain_quote","rights",
                    "publication_authorized"})
    if (candidate["schema"]!=SCHEMA or candidate["rights"]!="unreviewed"
            or candidate["publication_authorized"] is not False
            or candidate["row"].get("state")!=REVIEWED
            or candidate["item"]["id"]!=candidate["row"]["id"]):
        fail("published_quote_candidate_scope_mismatch")
    hexes(candidate,("source_lock_sha256","request_sha256","handoff_sha256"))
    row,item=candidate["row"],candidate["item"]
    fragments=_validate_receipt(row,item)
    expected=OMISSION.join(fragments)
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
    source=parameter_pairs(item["source_parameters"])
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
            "review_sha256":digest(review),"citation_id":item["id"],
            "receipt_sha256":row["published_passage"]["receipt"]["entry_sha256"],
            "translation_origin":"published_translation","parameters":params,
            "rights_status":"editorial_attestation_recorded_not_independently_verified",
            "publication_authorized":False,"translation_mutated":False}



EVIDENCE = "wikidebia-published-quote-evidence-1"


def make_evidence(candidate,expected_sha,review):
    """Keep the complete per-occurrence proof rather than only its digest."""
    projection=proposal(candidate,expected_sha,review)
    value={"schema":EVIDENCE,"candidate_sha256":expected_sha,
           "candidate":copy.deepcopy(candidate),"review":copy.deepcopy(review),
           "proposal":projection}
    return {**value,"evidence_sha256":digest(value)}


def item_from_source(page_id, source, imported):
    """Reconstruct the expected request item from authoritative FR data."""
    if (not isinstance(source,dict) or not isinstance(imported,dict)
            or imported.get("kind")!="argument" or imported.get("page_id")!=page_id
            or not isinstance(source.get("id"),str)
            or not source["id"].startswith(page_id+"-C")):
        fail("published_quote_authoritative_occurrence_missing")
    integer(imported.get("revision_id"),1)
    text(imported.get("canonical_title"),1,250)
    params=source.get("source_parameters")
    if parameter_pairs(params)["citation"]!=source.get("citation"):
        fail("published_quote_authoritative_text_mismatch")
    return {"id":source["id"],"wiki_title":imported["canonical_title"],
            "revision":imported["revision_id"],"source_template":source.get("source_template"),
            "source_parameters":copy.deepcopy(params)}


def verify_evidence(value,lock_sha,item,page_id):
    """The caller MUST supply the current FR lock hash and imported occurrence.

    A self-consistent proof from another Work or occurrence is insufficient.
    The expected request and handoff hashes recorded by the trusted resolver
    still require the ordinary provenance and review workflow.
    """
    keys(value,{"schema","candidate_sha256","candidate","review","proposal","evidence_sha256"})
    if (value["schema"]!=EVIDENCE or not is_digest(lock_sha)
            or not is_digest(value["evidence_sha256"])
            or digest({k:v for k,v in value.items() if k!="evidence_sha256"})!=value["evidence_sha256"]):
        fail("published_quote_evidence_digest_mismatch")
    candidate=value["candidate"]
    if (not isinstance(candidate,dict) or candidate.get("source_lock_sha256")!=lock_sha
            or candidate.get("page_id")!=page_id or candidate.get("item")!=item):
        fail("published_quote_authoritative_binding_mismatch")
    derived=proposal(candidate,value["candidate_sha256"],value["review"])
    if value["proposal"]!=derived:
        fail("published_quote_projection_mismatch")
    return derived
