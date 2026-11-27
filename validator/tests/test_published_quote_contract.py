"""Independent consumer tests: no kit imports."""
from copy import deepcopy
import hashlib
import pytest
from wikidebia_validator import published_quote_contract as p


def sample():
    source={"id":"A0001-C001","source_template":"Citation","citation":"Texte original.",
            "source_parameters":[{"name":"citation","value":"Texte original."},
                                 {"name":"lien","value":"https://www.marxists.org/francais/test/a.htm"}]}
    imported={"kind":"argument","page_id":"A0001","canonical_title":"French fixture","revision_id":7}
    item=p.item_from_source("A0001",source,imported)
    identity={"schema":"wikidebia-mia-prepared-source-1","provider":"mia",
              "mia_url":source["source_parameters"][1]["value"],
              "quote_sha256":hashlib.sha256(b"Texte original.").hexdigest(),
              "quote_wikitext_sha256":hashlib.sha256(b"Texte original.").hexdigest(),
              "metadata_sha256":p.digest([("lien",source["source_parameters"][1]["value"])])}
    stable=p.digest(identity)
    identity.update(source_key=stable,has_explicit_ellipsis=False,
                    occurrence={"revision":5,"template_index":0,"template_sha256":"c"*64})
    quote="Exact English quotation."
    fragment={"char_start":4,"char_end":4+len(quote),"text_sha256":hashlib.sha256(quote.encode()).hexdigest()}
    doc={"url":"https://www.marxists.org/archive/test/a.htm","revision":None,
         "body_sha256":"d"*64,"blocks_sha256":"e"*64}
    target={"document":doc,"char_start":fragment["char_start"],"char_end":fragment["char_end"],
            "text_sha256":fragment["text_sha256"]}
    target["candidate_key"]=p.digest(target)
    receipt={"schema":p.RECEIPT,"source":identity,"target":target,
             "decision":"complete_equivalent","fragments":[fragment],"review_packet_sha256":"f"*64,
             "reviewer":"Synthetic reviewer","semantic_status":"editorial_decision_recorded",
             "rights":"unreviewed","auto_publish":False}
    receipt["entry_sha256"]=p.digest(receipt)
    row={"id":item["id"],"state":p.REVIEWED,"source_parameters_sha256":p.digest(item["source_parameters"]),
         "source_key":stable,"citation_ref":{"revision":7,"template_index":0,"template_sha256":"b"*64,
                                               "quote_sha256":identity["quote_sha256"]},
         "evidence":{"origin":"revalidated_existing_receipt","receipt_sha256":receipt["entry_sha256"],
                     "publication":{},"rights":"unreviewed"},
         "published_passage":{"receipt":receipt,"fragments":[{**fragment,"text":quote}],
                              "editorial_review_required":True,"rights":"unreviewed","auto_publish":False}}
    c={"schema":p.SCHEMA,"source_lock_sha256":"a"*64,"request_sha256":"1"*64,"handoff_sha256":"2"*64,
       "page_id":"A0001","item":item,"row":row,"plain_quote":quote,"target_url":doc["url"],
       "rights":"unreviewed","publication_authorized":False}
    r=p.blank(c)
    r["status"]="reviewed_for_proposal"
    r["edition"].update(authors="Synthetic author",work="English edition",link=doc["url"])
    common={"reviewer":"Synthetic editor","reviewed_on":"2026-11-27","note":"Synthetic test only, not documentary proof."}
    r["edition_review"].update(common,evidence_urls=[doc["url"]],
         same_work_and_authorship_confirmed=True,english_edition_metadata_verified=True,
         missing_metadata_reviewed=True,attribution_and_translation_credit_preserved=True)
    r["rights_review"].update(common,status="reuse_reviewed",basis="public_domain",
         evidence_urls=["https://example.org/rights"],exact_passage_and_target_site_reviewed=True,
         all_conditions_representable=True)
    r["completeness_review"].update(common,full_meaning_and_boundaries_confirmed=True)
    return c,r,source,imported


def test_independent_proof_validation_and_rederived_parameters():
    c,r,s,i=sample()
    evidence=p.make_evidence(c,p.digest(c),r)
    result=p.verify_evidence(evidence,"a"*64,p.item_from_source("A0001",s,i),"A0001")
    assert result["parameters"]==[{"name":"quote","value":c["plain_quote"]},
        {"name":"authors","value":"Synthetic author"},{"name":"work","value":"English edition"},
        {"name":"link","value":c["target_url"]}]
    assert not result["publication_authorized"]


@pytest.mark.parametrize("mutation",["wrong_revision","wrong_lock","wrong_page","wrong_edition","wrong_quote","rights_pending"])
def test_independent_consumer_refuses_mutated_or_rebound_evidence(mutation):
    c,r,s,i=sample()
    value=p.make_evidence(c,p.digest(c),r)
    lock="a"*64
    page="A0001"
    if mutation=="wrong_revision":
        i["revision_id"]=9
    elif mutation=="wrong_lock":
        lock="e"*64
    elif mutation=="wrong_page":
        page="A0002"
    elif mutation=="wrong_edition":
        value["proposal"]["parameters"][2]["value"]="Other work"
    elif mutation=="wrong_quote":
        value["proposal"]["parameters"][0]["value"]="Invented text"
    else:
        value["review"]["rights_review"]["status"]="pending"
    value["evidence_sha256"]=p.digest({k:v for k,v in value.items() if k!="evidence_sha256"})
    with pytest.raises(p.PublishedQuoteError):
        p.verify_evidence(value,lock,p.item_from_source("A0001",s,i),page)
