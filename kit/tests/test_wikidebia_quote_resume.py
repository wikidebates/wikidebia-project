from copy import deepcopy
from datetime import timedelta
import hashlib
import json

import pytest

import wikidebia_quote_resume as resume
import wikidebia_quote_index_contract as q
from wikidebia_publish import sha_object,sha_text
from wikidebia_quote_index_stage import select_refresh
from test_wikidebia_quote_index_contract import NOW,LOCK,arg,snapshot


def plan_for(args,operations=None):
    operations=operations or {}
    actions=[]
    for a in args:
        raw="{{Argument|quotes={{Quote|quote="+a["citations"][0]["quote"]+"}}}}"
        action={"language":"en","page_type":"argument","kind":"full_page",
                "page_id":a["id"],"title":a["canonical_title"],"operation":"create",
                "desired_sha256":sha_text(raw),"remote_revision_id":None,
                "remote_sha256":None,"edit_summary":"Translation from French",
                "change_tags":["chatgpt","translated-fr"]}
        action.update(operations.get(a["id"],{}))
        actions.append(action)
    plan={"actions":actions}
    plan["plan_sha256"]=sha_object(plan)
    return plan


class Reader:
    def __init__(self):
        self.pages={}
        self.revisions={}
        self.opened=False
        self.read_calls=0

    def open_language(self,lang,user):
        assert lang=="en" and user=="ChatGPT"
        self.opened=True

    def close_language(self):
        self.opened=False

    def assert_identity(self,user):
        assert self.opened and user=="ChatGPT"

    def read_pages(self,titles):
        assert self.opened
        self.read_calls+=1
        return {t:self.pages[t] for t in titles}

    def read_revision(self,title,revision):
        assert self.opened
        return self.revisions[revision]

    def write_page(self,*args,**kwargs):
        pytest.fail("resume diagnostic attempted a write")


class Publisher:
    def __init__(self):
        self.adapter=Reader()

    def _site(self,lang):
        return lang,"ChatGPT"

    def _summary_for_action(self,action):
        return action["edit_summary"]

    def _tags_for_action(self,action):
        return action["change_tags"]

    def _verify_plan(self,plan,sha):
        assert plan["plan_sha256"]==sha

    def _remote_content_text(self,lang,text):
        return text


def own(publisher,action,a,*,pageid=5,rev=42,parent=0,when=NOW+timedelta(minutes=1)):
    raw="{{Argument|quotes={{Quote|quote="+a["citations"][0]["quote"]+"}}}}"
    title=action["title"]
    publisher.adapter.pages[title]=(True,rev,raw)
    publisher.adapter.revisions[rev]={"revision_identity_complete":True,"revision_id":rev,
        "page_id":pageid,"title":title,"parent_id":parent,"text":raw,
        "user":"ChatGPT","summary":action["edit_summary"],"tags":action["change_tags"],
        "timestamp":when.isoformat()}


def authorized():
    return {"authorized_at":NOW.isoformat(),"authorization_sha256":"a"*64}


def test_verified_creation_is_only_excluded_for_its_own_argument():
    a=arg("A0001","A passage.","published_translation")
    b=arg("A0002","Different passage.")
    plan=plan_for([a,b])
    idx=snapshot([(5,a["canonical_title"],42,"A passage."),
                  (6,"Unrelated page",43,"Different passage.")])
    p=Publisher()
    own(p,plan["actions"][0],a)
    proof=resume.observe([a,b],idx,plan,p,authorized(),now=NOW+timedelta(minutes=2))
    assert proof[0]["proof_kind"]=="verified_plan_creation"
    result=q.final_audit([a,b],idx,q.digest(idx),LOCK,now=NOW+timedelta(minutes=2),resume_pages=proof)
    assert result["same_pinned_page_matches_excluded"]==1
    assert result["public_exact"][0]["citation_id"]=="A0002-C001"
    assert result["status"]=="blocked_exact_duplicates"
    assert not p.adapter.opened
    with pytest.raises(q.QuoteIndexError):
        q.verify_final_audit(result,[a,b],idx,LOCK,now=NOW+timedelta(minutes=2))


@pytest.mark.parametrize("field,value",[
    ("user","Other editor"),("parent_id",41),("page_id",8),
    ("revision_id",43),("title","Other title"),("summary","Other summary"),
    ("tags",["chatgpt"]),("revision_identity_complete",False),
    ("timestamp",(NOW-timedelta(minutes=1)).isoformat()),
])
def test_matching_text_alone_cannot_establish_plan_attribution(field,value):
    a=arg("A0001","A passage.")
    plan=plan_for([a])
    idx=snapshot([(5,a["canonical_title"],42,"A passage.")])
    p=Publisher()
    own(p,plan["actions"][0],a)
    p.adapter.revisions[42][field]=value
    with pytest.raises(q.QuoteIndexError,match="resume_quote_revision_"):
        resume.observe([a],idx,plan,p,authorized(),now=NOW+timedelta(minutes=2))
    assert not p.adapter.opened


def test_changed_target_revision_requires_fresh_index():
    a=arg("A0001","A passage.")
    plan=plan_for([a])
    idx=snapshot([(5,a["canonical_title"],42,"A passage.")])
    p=Publisher()
    own(p,plan["actions"][0],a,rev=43)
    with pytest.raises(q.QuoteIndexError,match="index_target_revision_changed"):
        resume.observe([a],idx,plan,p,authorized(),now=NOW+timedelta(minutes=2))


def test_verified_update_and_migrated_skip():
    a=arg("A0001","A passage.")
    idx=snapshot([(5,a["canonical_title"],42,"A passage.")])
    p=Publisher()
    update=plan_for([a],{a["id"]:{"operation":"update","remote_revision_id":41,
                                 "remote_sha256":"b"*64}})
    own(p,update["actions"][0],a,parent=41)
    proof,=resume.observe([a],idx,update,p,authorized(),now=NOW+timedelta(minutes=2))
    assert proof["proof_kind"]=="verified_plan_update"
    skip=plan_for([a],{a["id"]:{"operation":"skip","remote_revision_id":42,
                              "remote_sha256":update["actions"][0]["desired_sha256"]}})
    own(p,skip["actions"][0],a)
    proof,=resume.observe([a],idx,skip,p,authorized(),now=NOW+timedelta(minutes=2))
    assert proof["proof_kind"]=="verified_plan_creation"


def test_resume_gate_requires_new_snapshot_and_preserves_release(tmp_path):
    root=tmp_path/"release"
    workspace=tmp_path/"work"
    workspace.mkdir()
    def write(rel,value):
        path=root/rel
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value,ensure_ascii=False)+"\n",encoding="utf-8")
        return path
    a=arg("A0001","A passage.","published_translation")
    args=[a]
    fr=write("data/fr_content_lock.json",{"arguments":[]})
    lock=hashlib.sha256(fr.read_bytes()).hexdigest()
    original=snapshot()
    historical=q.final_audit(args,original,q.digest(original),lock,now=NOW)
    write(q.INDEX_PATH,original)
    write("data/en_content_lock.json",{"arguments":args,"quote_duplicate_audit":historical})
    write("data/en_translation_lock.json",{"citation_translation_policy":{
        "quote_duplicate_audit_sha256":historical["audit_sha256"]}})
    authorization={**authorized(),"quote_duplicate_preflight":historical}
    p=Publisher()
    plan=plan_for(args)
    at=NOW+timedelta(days=2)
    with pytest.raises(q.QuoteIndexError,match="fresh_index_required"):
        resume.audit(workspace,root,authorization,plan,p,now=at)
    index=snapshot([(5,a["canonical_title"],42,"A passage.")])
    index.update(started_utc=(at-timedelta(minutes=2)).isoformat(),
                 finished_utc=(at-timedelta(minutes=1)).isoformat())
    path=tmp_path/"index.json"
    path.write_text(json.dumps(index))
    select_refresh(workspace,path,q.digest(index),now=at)
    own(p,plan["actions"][0],a)
    before={f.relative_to(root):f.read_bytes() for f in root.rglob("*") if f.is_file()}
    sealed=deepcopy(authorization)
    result=resume.audit(workspace,root,authorization,plan,p,now=at)
    assert result["audit"]["status"]=="clear_exact_literal_scope"
    assert result["authorization_sha256"]==authorization["authorization_sha256"]
    assert authorization==sealed
    assert before=={f.relative_to(root):f.read_bytes() for f in root.rglob("*") if f.is_file()}
    later=at+timedelta(minutes=3)
    index["pages"].append({"page_id":6,"title":"External duplicate","revision":43,
                           "argument_template_present":True,"invalid_occurrences":0,
                           "quotes":[{"ordinal":1,**q.public_fingerprints(("A passage.",))}]})
    index.update(pages_enumerated=2,started_utc=(later-timedelta(minutes=2)).isoformat(),
                 finished_utc=(later-timedelta(minutes=1)).isoformat())
    path.write_text(json.dumps(index))
    select_refresh(workspace,path,q.digest(index),now=later)
    with pytest.raises(q.QuoteIndexError,match="exact_duplicates"):
        resume.audit(workspace,root,authorization,plan,p,now=later)
    assert len(list((workspace/"audits/quote-resolver/published-quotes/resume-audit").glob("*.json")))==2


def test_legacy_publication_gate_avoids_adapter(tmp_path,monkeypatch):
    import wikidebia_final_publication as final
    monkeypatch.setattr(final,"build_adapter",lambda *args:pytest.fail("legacy adapter opened"))
    assert final._fresh_quote_resume(tmp_path,"debate","work",tmp_path/"legacy",{}, {}) is None
