"""Explicit, credential-free refresh of the public English quote fingerprint index.

Reuse the existing resolver producer at a reviewed Git commit. No clone,
installation, model, cited-site or wiki write. The producer runs in a
temporary private directory, never from mutable checkout contents. The
normal translation/rendering gates remain offline.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile

import wikidebia_quote_index_contract as contract
from wikidebia_quote_index_stage import (
    begin_refresh, latest_selected_sha, load_index, pending_refresh,
    select_refresh, stored_index,
)

# Tested producer version; update together with the cross-repository CI pin.
RESOLVER_COMMIT = "488f05ac1d787a4abd9d9630b3b25eb75648eb53"
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_MODULES = 200
RUN_TIMEOUT_SECONDS = 600
BOOTSTRAP = (
    "import runpy,sys; from pathlib import Path; "
    "script=sys.argv[1]; sys.argv=sys.argv[1:]; "
    "sys.path.insert(0,str(Path(script).parent)); "
    "runpy.run_path(script,run_name='__main__')"
)


def _env(home):
    # No bot, proxy, model or GitHub credentials are inherited. The
    # resolver's HTTP client also explicitly disables trust_env.
    return {"HOME":str(home),"PATH":os.defpath,"LANG":"C.UTF-8","LC_ALL":"C.UTF-8",
            "TZ":"UTC","GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":os.devnull,
            "GIT_OPTIONAL_LOCKS":"0"}


def _git(root, home, *args, stdout=subprocess.PIPE):
    try:
        result = subprocess.run(["git","-C",str(root),*args],env=_env(home),cwd=home,
                                stdout=stdout,stderr=subprocess.DEVNULL,
                                check=False,timeout=30)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise contract.QuoteIndexError("public_quote_resolver_git_unavailable") from exc
    if result.returncode:
        raise contract.QuoteIndexError("public_quote_resolver_pinned_commit_unavailable")
    return result.stdout


def materialize(root, temporary, *, entrypoint="public_quote_index.py", include_search_data=False):
    """Extract and verify the pinned Python modules and selected search assets.

    Using the object tree allows a checkout to have a different HEAD and
    avoids accidentally importing changed or ignored local files.
    """
    if (entrypoint not in {"public_quote_index.py", "translation_handoff.py"}
            or (include_search_data and entrypoint != "translation_handoff.py")):
        raise contract.QuoteIndexError("public_quote_resolver_invalid_entrypoint")
    root = Path(root).resolve()
    if not root.is_dir():
        raise contract.QuoteIndexError("public_quote_resolver_checkout_missing")
    if _git(root,temporary,"rev-parse","--verify",RESOLVER_COMMIT+"^{commit}").decode().strip()!=RESOLVER_COMMIT:
        raise contract.QuoteIndexError("public_quote_resolver_pinned_commit_unavailable")
    tree = _git(root,temporary,"ls-tree","-r","-z",RESOLVER_COMMIT)
    wanted = {}
    for row in tree.split(b"\0"):
        if not row:
            continue
        header,name = row.split(b"\t",1)
        root_module = re.fullmatch(rb"[A-Za-z_][A-Za-z0-9_]*\.py", name)
        search_asset = include_search_data and (
            name in {b"bibliographic-catalog.json", b"chapter-catalog.json",
                     b"data/wikirouge/manifest.json", b"data/works/research.json"}
            or re.fullmatch(rb"data/wikirouge/wikirouge-index-\d{8}\.zip", name)
            or re.fullmatch(rb"data/wikirouge/deltas/(?:manifest|\d{4})\.json", name)
        )
        if not root_module and not search_asset:
            continue
        mode,kind,oid = header.split()
        if mode not in (b"100644",b"100755") or kind!=b"blob" or not re.fullmatch(rb"[0-9a-f]{40}",oid):
            raise contract.QuoteIndexError("public_quote_resolver_invalid_source_tree")
        wanted[name.decode("ascii")] = oid.decode("ascii")
    required = {entrypoint}
    if include_search_data:
        required.update({"bibliographic-catalog.json", "chapter-catalog.json",
                         "data/wikirouge/manifest.json"})
    if not required <= set(wanted) or len(wanted)>MAX_MODULES:
        raise contract.QuoteIndexError("public_quote_resolver_invalid_source_tree")
    archive = temporary/"source.tar"
    with archive.open("wb") as stream:
        _git(root,temporary,"archive","--format=tar",RESOLVER_COMMIT,"--",*sorted(wanted),stdout=stream)
    if archive.stat().st_size > MAX_SOURCE_BYTES:
        raise contract.QuoteIndexError("public_quote_resolver_source_limit")
    src = temporary/"src"
    src.mkdir(mode=0o700)
    seen = set()
    parents = {parent.as_posix() for name in wanted for parent in Path(name).parents
               if parent != Path(".")}
    with tarfile.open(archive,"r:") as bundle:
        for member in bundle:
            if member.isdir() and member.name in parents:
                continue
            if (not member.isfile() or member.name not in wanted or member.name in seen
                    or member.size>MAX_SOURCE_BYTES):
                raise contract.QuoteIndexError("public_quote_resolver_invalid_archive")
            data = bundle.extractfile(member).read()
            oid = hashlib.sha1(b"blob "+str(len(data)).encode("ascii")+b"\0"+data).hexdigest()
            if oid != wanted[member.name]:
                raise contract.QuoteIndexError("public_quote_resolver_source_digest_mismatch")
            destination = src/member.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            seen.add(member.name)
    if seen != set(wanted):
        raise contract.QuoteIndexError("public_quote_resolver_missing_source")
    archive.unlink()
    return src/entrypoint


def _run(script,temporary,args,timeout):
    try:
        return subprocess.run([sys.executable,"-I","-B","-c",BOOTSTRAP,str(script),*args],
                              cwd=temporary,env=_env(temporary),timeout=timeout,check=False,
                              stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise contract.QuoteIndexError("public_quote_collection_interrupted") from exc


def collect(workspace,resolver_root,*,previous_sha=None,budget=1200,batch_size=30,
            timeout=RUN_TIMEOUT_SECONDS,force=False,now=None):
    """Return a safe aggregate and select the verified index for this Work.

    Reuse a fresh already selected index unless forced or an attempt is
    pending. A stale index is an incremental input, never a fresh proof.
    Failure leaves the pending marker; only a new complete census clears it.
    """
    if (type(budget) is not int or not 1<=budget<=5000 or type(batch_size) is not int
            or not 1<=batch_size<=50 or type(timeout) is not int or not 1<=timeout<=1800):
        raise contract.QuoteIndexError("public_quote_collection_invalid_limits")
    if not workspace.is_dir() or workspace.is_symlink():
        raise contract.QuoteIndexError("invalid_public_quote_workspace")
    old_sha = latest_selected_sha(workspace,previous_sha,allow_pending=True)
    old = stored_index(workspace,old_sha) if old_sha is not None else None
    current = now or datetime.now(timezone.utc)
    if old is not None:
        coverage = contract.validate(old,old_sha,"en",allow_partial=True,now=current)
        if (coverage["complete_fresh_literal_scope"] and not force
                and pending_refresh(workspace) is None):
            if latest_selected_sha(workspace) != old_sha:
                # An explicitly supplied staged index may be fresher than
                # the selected pointer, or no pointer may exist yet.
                artifact = (workspace/"audits/quote-resolver/published-quotes/public-index"/
                            (old_sha+".json"))
                select_refresh(workspace,artifact,old_sha,now=current)
            return {"status":"reused_fresh_index","quote_public_index_sha256":old_sha,
                    "wiki_requests":0,"pages_fetched_content":0,
                    "hosted_model_calls":0,"publication_authorized":False,
                    "translation_mutated":False,"resolver_commit":RESOLVER_COMMIT}
    with tempfile.TemporaryDirectory(prefix="wikidebia-index-") as directory:
        temporary = Path(directory)
        script = materialize(resolver_root,temporary)
        out,summary = temporary/"index.json",temporary/"summary.json"
        args = ["--language","en","--out",str(out),"--summary",str(summary),
                "--budget",str(budget),"--batch-size",str(batch_size)]
        if old is not None:
            previous = temporary/"previous.json"
            previous.write_bytes(json.dumps(old,ensure_ascii=False,sort_keys=True,
                                separators=(",",":"),allow_nan=False).encode("utf-8")+b"\n")
            args += ["--previous",str(previous),"--previous-sha256",old_sha]
        started = begin_refresh(workspace,now=now)
        code = _run(script,temporary,args,timeout)
        if code != 0:
            raise contract.QuoteIndexError("public_quote_collection_failed_or_incomplete")
        value = load_index(out)
        result = load_index(summary)
        if not isinstance(result,dict):
            raise contract.QuoteIndexError("public_quote_collection_summary_mismatch")
        sha = result.get("snapshot_sha256")
        coverage = contract.validate(value,sha,"en",now=now)
        if (result.get("language")!="en" or result.get("status")!=contract.COMPLETE
                or result.get("hosted_model_calls")!=0 or result.get("cited_url_requests")!=0
                or result.get("publication_authorized") is not False
                or result.get("pages_inspected")!=coverage["pages_indexed"]
                or datetime.fromisoformat(value["started_utc"]) < started):
            raise contract.QuoteIndexError("public_quote_collection_summary_mismatch")
        counts = {}
        for key in ("wiki_requests","decoded_bytes","pages_reused_same_revision",
                    "pages_fetched_content","pages_checked_revision_only","pages_inspected","citations"):
            v = result.get(key)
            if type(v) is not int or v<0:
                raise contract.QuoteIndexError("public_quote_collection_summary_mismatch")
            counts[key] = v
        if (counts["wiki_requests"]>budget
                or counts["pages_reused_same_revision"]+counts["pages_fetched_content"]!=counts["pages_inspected"]
                or counts["citations"]!=sum(len(p["quotes"]) for p in value["pages"])):
            raise contract.QuoteIndexError("public_quote_collection_summary_mismatch")
        select_refresh(workspace,out,sha,now=now)
    return {"status":"refreshed","quote_public_index_sha256":sha,
            "resolver_commit":RESOLVER_COMMIT,"previous_sha256":old_sha,**counts,
            "hosted_model_calls":0,"publication_authorized":False,"translation_mutated":False}


def main(argv=None):
    from wikidebia_corpus_build import exclusive_lock,validate_debate_id
    from wikidebia_editorial_workspace import validate_work_id
    from wikidebia_editorial_review import _load_workspace
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("debate_id")
    p.add_argument("--work-id",required=True)
    p.add_argument("--project-root",type=Path,default=Path.cwd())
    p.add_argument("--resolver-root",type=Path,required=True)
    p.add_argument("--previous-sha256")
    p.add_argument("--budget",type=int,default=1200)
    p.add_argument("--batch-size",type=int,default=30)
    p.add_argument("--timeout",type=int,default=RUN_TIMEOUT_SECONDS)
    p.add_argument("--force",action="store_true")
    a=p.parse_args(argv)
    try:
        project=a.project_root.resolve()
        debate,work=validate_debate_id(a.debate_id),validate_work_id(a.work_id)
        with exclusive_lock(project,debate,"quote_index_collect"):
            workspace,_=_load_workspace(project,debate,work)
            result=collect(workspace,a.resolver_root,previous_sha=a.previous_sha256,
                           budget=a.budget,batch_size=a.batch_size,timeout=a.timeout,force=a.force)
    except (ValueError,RuntimeError,OSError,KeyError,TypeError,AttributeError,tarfile.TarError) as exc:
        reason=str(exc) if isinstance(exc,contract.QuoteIndexError) else type(exc).__name__
        print(json.dumps({"status":"blocked","reason":reason,"publication_authorized":False}))
        return 1
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
