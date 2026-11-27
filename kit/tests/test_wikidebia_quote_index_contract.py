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


def test_refresh_does_not_mutate_review_and_new_collision_never_falls_back(tmp_path):
    from wikidebia_quote_index_stage import select_refresh,verify_current
    old=snapshot(age=1)
    args=[arg("A0001","New quote.")]
    audit=run(args,old)
    frozen=q.digest([args,old,audit])
    current=NOW+timedelta(hours=25)
    # The same semantic review is valid but the technical check expired.
    with pytest.raises(q.QuoteIndexError,match="stale"):
        verify_current(tmp_path,audit,args,old,LOCK,now=current)
    refreshed=snapshot()
    refreshed.update(started_utc=(current-timedelta(minutes=3)).isoformat(),
                     finished_utc=(current-timedelta(minutes=1)).isoformat())
    path=tmp_path/"fresh.json"
    path.write_text(json.dumps(refreshed))
    select_refresh(tmp_path,path,q.digest(refreshed),now=current)
    check=verify_current(tmp_path,audit,args,old,LOCK,now=current)
    assert check["scope_sha256"]==audit["scope_sha256"]
    assert check["index_sha256"]==q.digest(refreshed)
    assert q.digest([args,old,audit])==frozen
    later=current+timedelta(minutes=5)
    conflict=snapshot([(1,"External page",17,"New quote.")])
    conflict.update(started_utc=(later-timedelta(minutes=3)).isoformat(),
                    finished_utc=(later-timedelta(minutes=1)).isoformat())
    path.write_text(json.dumps(conflict))
    select_refresh(tmp_path,path,q.digest(conflict),now=later)
    with pytest.raises(q.QuoteIndexError,match="exact_duplicates"):
        verify_current(tmp_path,audit,args,old,LOCK,now=later)
    path.write_text(json.dumps(refreshed))
    with pytest.raises(q.QuoteIndexError,match="rollback"):
        select_refresh(tmp_path,path,q.digest(refreshed),now=later)
    with pytest.raises(q.QuoteIndexError,match="exact_duplicates"):
        verify_current(tmp_path,audit,args,old,LOCK,now=later)


def test_package_gate_detects_missing_proof_and_preserves_immutable_files(tmp_path):
    from hashlib import sha256
    from wikidebia_quote_index_stage import package_audit
    root=tmp_path/"release"
    workspace=tmp_path/"workspace"
    workspace.mkdir()
    def write(rel,value):
        path=root/rel
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value,ensure_ascii=False)+"\n",encoding="utf-8")
        return path
    assert package_audit(workspace,root,now=NOW) is None
    fr=write("data/fr_content_lock.json",{"arguments":[]})
    args=[arg("A0001","A quote.","published_translation")]
    en=write("data/en_content_lock.json",{"arguments":args})
    with pytest.raises(q.QuoteIndexError,match="missing_or_unbound"):
        package_audit(workspace,root,now=NOW)
    index=snapshot()
    audit=q.final_audit(args,index,q.digest(index),sha256(fr.read_bytes()).hexdigest(),now=NOW)
    write(q.INDEX_PATH,index)
    write("data/en_content_lock.json",{"arguments":args,"quote_duplicate_audit":audit})
    write("data/en_translation_lock.json",{"citation_translation_policy":
        {"quote_duplicate_audit_sha256":audit["audit_sha256"]}})
    frozen={p.relative_to(root):p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert package_audit(workspace,root,now=NOW)["status"]=="clear_exact_literal_scope"
    assert frozen=={p.relative_to(root):p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert en.is_file()


def test_publication_preflight_failure_precedes_authorization(tmp_path,monkeypatch):
    import wikidebia_final_publication as publication
    from wikidebia_quote_index_contract import QuoteIndexError
    from wikidebia_quote_index_stage import package_audit
    import wikidebia_quote_index_stage as stage_module
    def blocked(*args,**kwargs):
        raise QuoteIndexError("final_quote_exact_duplicates")
    monkeypatch.setattr(stage_module,"package_audit",blocked)
    with pytest.raises(publication.FinalPublicationError,match="exact_duplicates"):
        publication.prepare_final_release(tmp_path,"test_debate","test_work",tmp_path/"release")
    state=tmp_path/".state/final-publication/test_debate/test_work"
    assert not (state/"authorization.json").exists()
    assert not (state/"publication-preparation.json").exists()
    monkeypatch.setattr(publication,"_verify_prepared_publication",lambda *args:
        ({"fr":{"mode":"ordinary"}},{},{},{}))
    with pytest.raises(publication.FinalPublicationError,match="exact_duplicates"):
        publication.publish_final_release(tmp_path,"test_debate","test_work",tmp_path/"release",
                                          confirm_preflight_sha256="a"*64)
    assert not (state/"authorization.json").exists()


def test_legacy_gate_does_not_resolve_workspace_and_opt_in_resolves_before_write(tmp_path):
    from hashlib import sha256
    from wikidebia_quote_index_stage import package_audit
    root=tmp_path/"release"
    calls=[]
    def workspace():
        calls.append("checked")
        raise q.QuoteIndexError("untrusted_workspace")
    assert package_audit(workspace,root,now=NOW) is None
    assert not calls
    def write(rel,value):
        path=root/rel
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value)+"\n",encoding="utf-8")
        return path
    fr=write("data/fr_content_lock.json",{"arguments":[]})
    args=[arg("A0001","A quote.")]
    idx=snapshot()
    audit=q.final_audit(args,idx,q.digest(idx),sha256(fr.read_bytes()).hexdigest(),now=NOW)
    write(q.INDEX_PATH,idx)
    write("data/en_content_lock.json",{"arguments":args,"quote_duplicate_audit":audit})
    write("data/en_translation_lock.json",{"citation_translation_policy":
         {"quote_duplicate_audit_sha256":audit["audit_sha256"]}})
    with pytest.raises(q.QuoteIndexError,match="untrusted_workspace"):
        package_audit(workspace,root,now=NOW)
    assert calls==["checked"]


def test_prior_authorization_reproduces_exact_scope_without_self_duplicate_refresh(tmp_path):
    from hashlib import sha256
    from wikidebia_quote_index_stage import authorized_package_audit,select_refresh,verify_current
    root=tmp_path/"release"
    workspace=tmp_path/"work"
    workspace.mkdir()
    def write(rel,value):
        path=root/rel
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value)+"\n",encoding="utf-8")
        return path
    def no_workspace():
        raise AssertionError("Legacy or original-index check must not load a workspace")
    assert authorized_package_audit(no_workspace,root,{},now=NOW) is None
    with pytest.raises(q.QuoteIndexError,match="unexpected_authorized"):
        authorized_package_audit(no_workspace,root,{"quote_duplicate_preflight":{}},now=NOW)
    fr=write("data/fr_content_lock.json",{"arguments":[]})
    lock=sha256(fr.read_bytes()).hexdigest()
    args=[arg("A0001","A quote.","published_translation")]
    original=snapshot()
    audit=q.final_audit(args,original,q.digest(original),lock,now=NOW)
    write(q.INDEX_PATH,original)
    write("data/en_content_lock.json",{"arguments":args,"quote_duplicate_audit":audit})
    write("data/en_translation_lock.json",{"citation_translation_policy":
         {"quote_duplicate_audit_sha256":audit["audit_sha256"]}})
    with pytest.raises(q.QuoteIndexError,match="missing_authorized"):
        authorized_package_audit(no_workspace,root,{},now=NOW)
    # Resume later using the original, bound historical proof.
    auth={"authorized_at":(NOW+timedelta(seconds=1)).isoformat(),
          "quote_duplicate_preflight":audit}
    later=NOW+timedelta(days=2)
    assert authorized_package_audit(no_workspace,root,auth,now=later)==audit
    # Migration re-signs the plan without changing the original quote decision.
    migrated={**auth,"quote_duplicate_authorized_at":auth["authorized_at"],
              "authorized_at":later.isoformat()}
    assert authorized_package_audit(no_workspace,root,migrated,now=later)==audit
    wrong={**auth,"authorized_at":(NOW-timedelta(seconds=1)).isoformat()}
    with pytest.raises(q.QuoteIndexError,match="timestamp_mismatch"):
        authorized_package_audit(no_workspace,root,wrong,now=later)
    bad=deepcopy(auth)
    bad["quote_duplicate_preflight"]["scope_sha256"]="f"*64
    bad["quote_duplicate_preflight"]["audit_sha256"]=q.digest(
        {k:v for k,v in bad["quote_duplicate_preflight"].items() if k!="audit_sha256"})
    with pytest.raises(q.QuoteIndexError,match="audit_mismatch"):
        authorized_package_audit(no_workspace,root,bad,now=later)
    refreshed=snapshot()
    refreshed.update(started_utc=(later-timedelta(minutes=3)).isoformat(),
                     finished_utc=(later-timedelta(minutes=1)).isoformat())
    p=tmp_path/"fresh.json"
    p.write_text(json.dumps(refreshed))
    select_refresh(workspace,p,q.digest(refreshed),now=later)
    new=verify_current(workspace,audit,args,original,lock,now=later)
    auth={"authorized_at":(later+timedelta(seconds=1)).isoformat(),
          "quote_duplicate_preflight":new}
    assert authorized_package_audit(workspace,root,auth,now=later+timedelta(days=1))==new
    # Missing refreshed proof is not silently replaced by the older index.
    refreshed_path=(workspace/"audits/quote-resolver/published-quotes/public-index"/
                    (q.digest(refreshed)+".json"))
    refreshed_path.unlink()
    with pytest.raises(q.QuoteIndexError,match="missing_or_nonprivate"):
        authorized_package_audit(workspace,root,auth,now=later+timedelta(days=1))


def test_authorization_uses_precise_clock_and_keeps_initial_quote_timestamp(tmp_path):
    import wikidebia_final_publication as publication
    idx=snapshot()
    args=[arg("A0001","A quote.")]
    audit=q.final_audit(args,idx,q.digest(idx),LOCK,now=NOW)
    state=tmp_path
    legacy=publication._authorization(state,{"baseline_sha256":"base"},{"preflight_sha256":"pre"})
    assert "quote_duplicate_preflight" not in legacy
    assert "quote_duplicate_authorized_at" not in legacy
    first=publication._authorization(state,{"baseline_sha256":"base"},{"preflight_sha256":"pre"},quote_check=audit)
    assert first["quote_duplicate_authorized_at"]==first["authorized_at"]
    assert first["quote_duplicate_preflight"]==audit
    assert datetime.fromisoformat(first["authorized_at"])>=datetime.fromisoformat(audit["checked_at"])
    later=publication._authorization(state,{"baseline_sha256":"base"},{"preflight_sha256":"new"},quote_check=audit,
                                    quote_authorized_at=first["quote_duplicate_authorized_at"])
    assert later["quote_duplicate_authorized_at"]==first["quote_duplicate_authorized_at"]
    assert datetime.fromisoformat(later["authorized_at"])>=datetime.fromisoformat(first["authorized_at"])
