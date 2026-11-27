from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import unicodedata

import pytest
import wikidebia_quote_index_contract as q
from wikidebia_quote_index_stage import stage, stored_index

NOW = datetime(2026,11,27,10,0,tzinfo=timezone.utc)
LOCK = "a"*64


def snapshot(rows=(), age=1, status=q.COMPLETE):
    start=NOW-timedelta(hours=age)
    pages=[{"page_id":pid,"title":title,"revision":rev,"argument_template_present":True,
            "invalid_occurrences":0,"quotes":[{"ordinal":1,**q.public_fingerprints((text,))}]}
           for pid,title,rev,text in rows]
    return {"schema":q.SCHEMA,"algorithm":q.ALGORITHM,"unicode_version":unicodedata.unidata_version,
            "language":"en","status":status,"started_utc":start.isoformat(),
            "finished_utc":(start+timedelta(minutes=1)).isoformat(),
            "template_titles":[q.ROOTS["en"]],"pages_enumerated":len(pages),"pages":pages,"issues":{}}


def arg(page, text, origin="ai_translation"):
    return {"id":page,"canonical_title":"Argument "+page,
            "citations":[{"id":page+"-C001","quote":text,"translation_origin":origin,
                          "parameters":[{"name":"quote","value":text}]}]}


def run(args,idx):
    return q.final_audit(args,idx,q.digest(idx),LOCK,now=NOW)


def test_all_selected_citations_checked_including_ai_and_cross_debate():
    a=arg("A0001","A published passage.","published_translation")
    b=arg("A0002","An AI translation.")
    idx=snapshot([(1,"Unrelated existing argument",11,"An AI translation."),
                  (2,"Other page",12,"AN AI TRANSLATION")])
    audit=run([a,b],idx)
    assert audit["status"]=="blocked_exact_duplicates"
    assert audit["ai_occurrences"]==1 and audit["published_occurrences"]==1
    assert audit["public_exact"][0]["citation_id"]=="A0002-C001"
    assert audit["public_word_variants"][0]["matches"][0]["wiki_page_id"]==2
    assert "An AI translation." not in json.dumps(audit)
    with pytest.raises(q.QuoteIndexError,match="exact_duplicates"):
        q.verify_final_audit(audit,[a,b],idx,LOCK,now=NOW)


def test_exact_local_collision_includes_ai_only_and_omission_boundaries():
    a,b=arg("A0001","One passage."),arg("A0002","One  passage.")
    assert run([a,b],snapshot())["local_exact"]
    b=arg("A0002","ONE PASSAGE")
    audit=run([a,b],snapshot())
    assert not audit["local_exact"] and audit["local_word_variants"]
    a,b=arg("A0001","one […] two"),arg("A0002","one two")
    assert not run([a,b],snapshot())["local_word_variants"]


def test_pinned_update_only_excludes_its_exact_page_revision():
    a=arg("A0001","Same passage")
    idx=snapshot([(1,a["canonical_title"],17,"Same passage")])
    assert run([a],idx)["public_exact"]
    a["existing_english_update"]={"page_id":a["id"],"title":a["canonical_title"],
        "owner_approved":True,"allow_proposed_change":True,"decision":"explicit_user_request",
        "language":"en","observed_revision_id":17,"observed_sha256":"b"*64,
        "authorization_receipt_sha256":"c"*64}
    assert run([a],idx)["same_pinned_page_matches_excluded"]==1
    assert not run([a],idx)["public_exact"]
    idx["pages"][0]["revision"]=18
    assert run([a],idx)["public_exact"]
    a["existing_english_update"]["owner_approved"]=False
    idx["pages"][0]["revision"]=17
    assert run([a],idx)["public_exact"]


def test_stale_or_incomplete_index_and_modified_lock_rejected():
    a=arg("A0001","New quote")
    for idx in (snapshot(age=25),snapshot(status="incomplete")):
        with pytest.raises(q.QuoteIndexError):
            run([a],idx)
    idx=snapshot()
    audit=run([a],idx)
    q.verify_final_audit(audit,[a],idx,LOCK,now=NOW)
    with pytest.raises(q.QuoteIndexError,match="stale"):
        q.verify_final_audit(audit,[a],idx,LOCK,now=NOW+timedelta(days=2),fresh=True)
    # An archived receipt may be audited at its original time.
    q.verify_final_audit(audit,[a],idx,LOCK,now=NOW+timedelta(days=2))
    for args,lock in (([arg("A0001","Changed")],LOCK),([a],"b"*64)):
        with pytest.raises(q.QuoteIndexError,match="audit_mismatch"):
            q.verify_final_audit(audit,args,idx,lock,now=NOW)
    bad={**audit,"local_occurrences":99}
    bad["audit_sha256"]=q.digest({k:v for k,v in bad.items() if k!="audit_sha256"})
    with pytest.raises(q.QuoteIndexError,match="audit_mismatch"):
        q.verify_final_audit(bad,[a],idx,LOCK,now=NOW)


def test_private_staging_integrity(tmp_path):
    idx=snapshot()
    src=tmp_path/"source.json"
    src.write_text(json.dumps(idx),encoding="utf-8")
    sha=q.digest(idx)
    path=stage(tmp_path,src,sha,now=NOW)
    assert path.stat().st_mode & 0o077 == 0
    assert stored_index(tmp_path,sha)==idx
    assert stage(tmp_path,src,sha,now=NOW)==path
    path.write_text("{}")
    with pytest.raises(q.QuoteIndexError,match="digest_mismatch"):
        stored_index(tmp_path,sha)
