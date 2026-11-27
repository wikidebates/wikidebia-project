"""Collection tests use a local Git fixture; no network or model calls."""
from datetime import datetime,timedelta,timezone
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import wikidebia_quote_index_collect as collect
import wikidebia_quote_index_contract as q
from wikidebia_quote_index_stage import (
    begin_refresh, latest_selected_sha, pending_refresh, require_refresh_complete,
    select_refresh, stage, stored_index, verify_current,
)
from test_wikidebia_quote_index_contract import NOW, LOCK, arg, snapshot


def write_snapshot(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False),encoding="utf-8")
    return q.digest(value)


def fresh(at,rows=()):
    value=snapshot(rows)
    value["started_utc"]=(at-timedelta(minutes=2)).isoformat()
    value["finished_utc"]=(at-timedelta(minutes=1)).isoformat()
    return value


def test_materialize_exact_git_tree_not_mutable_checkout(tmp_path,monkeypatch):
    root=tmp_path/"resolver"
    root.mkdir()
    def git(*args):
        return subprocess.check_output(["git","-C",str(root),*args],text=True).strip()
    git("init","-q")
    git("config","user.email","fixture@example.invalid")
    git("config","user.name","Fixture")
    (root/"public_quote_index.py").write_text("import helper\nassert helper.VALUE == 7\n",encoding="utf-8")
    (root/"helper.py").write_text("VALUE = 7\n",encoding="utf-8")
    git("add",".")
    git("commit","-qm","fixture")
    monkeypatch.setattr(collect,"RESOLVER_COMMIT",git("rev-parse","HEAD"))
    (root/"helper.py").write_text("raise RuntimeError('dirty file')\n",encoding="utf-8")
    (root/"requests.py").write_text("raise RuntimeError('untracked file')\n",encoding="utf-8")
    temp=tmp_path/"temp"
    temp.mkdir()
    script=collect.materialize(root,temp)
    assert script.parent.joinpath("helper.py").read_text()=="VALUE = 7\n"
    assert not script.parent.joinpath("requests.py").exists()
    monkeypatch.setenv("WIKIDEBIA_API_TOKEN","fixture-not-a-secret")
    assert "WIKIDEBIA_API_TOKEN" not in collect._env(temp)
    assert collect._run(script,temp,[],10)==0
    monkeypatch.setattr(collect,"RESOLVER_COMMIT","0"*40)
    with pytest.raises(q.QuoteIndexError,match="pinned_commit_unavailable"):
        collect.materialize(root,temp)


def test_collection_reuses_fresh_then_incrementally_refreshes(tmp_path,monkeypatch):
    old=fresh(NOW,[(1,"Existing",10,"A quote.")])
    path=tmp_path/"old.json"
    old_sha=write_snapshot(path,old)
    select_refresh(tmp_path,path,old_sha,now=NOW)
    def forbidden(*args,**kwargs):
        pytest.fail("fresh selected index should not execute resolver")
    monkeypatch.setattr(collect,"materialize",forbidden)
    result=collect.collect(tmp_path,tmp_path,now=NOW)
    assert result["status"]=="reused_fresh_index" and result["wiki_requests"]==0
    at=NOW+timedelta(days=2)
    monkeypatch.setattr(collect,"materialize",lambda *args:Path("fake.py"))
    calls=[]
    def producer(script,temp,args,timeout):
        calls.append(args)
        previous=Path(args[args.index("--previous")+1])
        assert json.loads(previous.read_text())==old
        assert args[args.index("--previous-sha256")+1]==old_sha
        new=fresh(at+timedelta(minutes=2),[(1,"Existing",10,"A quote.")])
        sha=write_snapshot(Path(args[args.index("--out")+1]),new)
        summary={"snapshot_sha256":sha,"language":"en","status":q.COMPLETE,
                 "hosted_model_calls":0,"cited_url_requests":0,"publication_authorized":False,
                 "wiki_requests":2,"decoded_bytes":500,"pages_reused_same_revision":1,
                 "pages_fetched_content":0,"pages_checked_revision_only":1,
                 "pages_inspected":1,"citations":1}
        Path(args[args.index("--summary")+1]).write_text(json.dumps(summary))
        return 0
    monkeypatch.setattr(collect,"_run",producer)
    result=collect.collect(tmp_path,tmp_path,now=at)
    assert result["status"]=="refreshed"
    assert result["pages_reused_same_revision"]==1 and result["pages_fetched_content"]==0
    assert latest_selected_sha(tmp_path)==result["quote_public_index_sha256"]
    assert stored_index(tmp_path,old_sha)==old
    assert pending_refresh(tmp_path) is None
    assert len(calls)==1


def test_failed_collection_blocks_old_index_until_new_complete_snapshot(tmp_path,monkeypatch):
    old=fresh(NOW)
    path=tmp_path/"old.json"
    sha=write_snapshot(path,old)
    select_refresh(tmp_path,path,sha,now=NOW)
    args=[arg("A0001","New quote.")]
    audit=q.final_audit(args,old,sha,LOCK,now=NOW)
    monkeypatch.setattr(collect,"materialize",lambda *args:Path("fake.py"))
    monkeypatch.setattr(collect,"_run",lambda *args:1)
    with pytest.raises(q.QuoteIndexError,match="failed_or_incomplete"):
        collect.collect(tmp_path,tmp_path,force=True,now=NOW)
    assert pending_refresh(tmp_path)==NOW
    with pytest.raises(q.QuoteIndexError,match="refresh_pending"):
        verify_current(tmp_path,audit,args,old,LOCK,now=NOW)
    with pytest.raises(q.QuoteIndexError,match="predates_attempt"):
        select_refresh(tmp_path,path,sha,now=NOW)
    at=NOW+timedelta(minutes=3)
    new=fresh(at)
    new_sha=write_snapshot(path,new)
    select_refresh(tmp_path,path,new_sha,now=at)
    assert verify_current(tmp_path,audit,args,old,LOCK,now=at)["index_sha256"]==new_sha
    assert pending_refresh(tmp_path) is None


def test_wrong_digest_and_incomplete_summary_do_not_select(tmp_path,monkeypatch):
    monkeypatch.setattr(collect,"materialize",lambda *args:Path("fake.py"))
    def producer(script,temp,args,timeout):
        value=fresh(NOW+timedelta(minutes=2))
        write_snapshot(Path(args[args.index("--out")+1]),value)
        Path(args[args.index("--summary")+1]).write_text(json.dumps({"snapshot_sha256":"0"*64}))
        return 0
    monkeypatch.setattr(collect,"_run",producer)
    with pytest.raises(q.QuoteIndexError,match="digest_mismatch"):
        collect.collect(tmp_path,tmp_path,now=NOW)
    with pytest.raises(q.QuoteIndexError,match="refresh_pending"):
        latest_selected_sha(tmp_path)


def test_latest_selected_sha_never_replaces_newer_draft_index(tmp_path):
    older=fresh(NOW)
    newer=fresh(NOW+timedelta(minutes=2))
    path=tmp_path/"snapshot.json"
    old_sha=write_snapshot(path,older)
    select_refresh(tmp_path,path,old_sha,now=NOW)
    new_sha=write_snapshot(path,newer)
    stage(tmp_path,path,new_sha,now=NOW+timedelta(minutes=2))
    assert latest_selected_sha(tmp_path,new_sha)==new_sha
