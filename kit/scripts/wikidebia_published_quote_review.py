"""Experimental, private review of published quote provenance.

This module prepares a candidate for an editor; it does NOT approve rights,
alter a translation lock, or enable a production rendering profile. A sealed
proposal is not proof of the truth of an editorial or legal attestation.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import tempfile
import wikidebia_quote_bridge as bridge

import wikidebia_published_quote_contract as contract

# Compatibility names for callers of the private review helper.
SCHEMA = contract.SCHEMA
REVIEW = contract.REVIEW
PROJECTION = contract.PROJECTION
SOURCE_FIELDS = contract.SOURCE_FIELDS
OMISSION = contract.OMISSION
def fail(reason):
    raise bridge.QuoteBridgeError(reason)


def _check(function, *args):
    try:
        return function(*args)
    except contract.PublishedQuoteError as exc:
        raise bridge.QuoteBridgeError(str(exc)) from exc


def proposal(candidate,expected_sha,review):
    return _check(contract.proposal,candidate,expected_sha,review)


def make_evidence(candidate,expected_sha,review):
    return _check(contract.make_evidence,candidate,expected_sha,review)


blank = contract.blank


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
        fragments=_check(contract._validate_receipt,row,item)
        candidate={"schema":SCHEMA,"source_lock_sha256":lock_sha,
                   "request_sha256":summary["request_sha256"],"handoff_sha256":handoff_sha,
                   "page_id":owners[row["id"]],"item":copy.deepcopy(item),
                   "row":copy.deepcopy(row),
                   "target_url":row["published_passage"]["receipt"]["target"]["document"]["url"],
                   "plain_quote":OMISSION.join(fragments),
                   "rights":"unreviewed","publication_authorized":False}
        candidates.append(candidate)
    return candidates


def write_private(workspace, value, kind):
    """Immutable, content-addressed file inside the private audit directory."""
    if kind not in {"candidate","review-template","proposal","evidence","public-index","final-audit"}:
        fail("published_quote_invalid_artifact_kind")
    sha=bridge.digest(value)
    directory=workspace/"audits"/"quote-resolver"/"published-quotes"/kind
    directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    if not directory.resolve().is_relative_to(workspace.resolve()):
        fail("published_quote_unsafe_output_directory")
    path=directory/(sha+".json")
    if path.is_symlink():
        fail("published_quote_unsafe_output_path")
    payload=bridge.canonical_json(value)+b"\n"
    def check():
        if (path.is_symlink() or not path.is_file() or
                path.stat().st_mode & 0o077 or path.read_bytes()!=payload):
            fail("published_quote_existing_private_artifact_changed")
    if path.exists():
        check()
        return path
    fd,tmp=tempfile.mkstemp(prefix=".quote-review-",dir=directory)
    try:
        with os.fdopen(fd,"wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(tmp,path)
        except FileExistsError:
            check()
    finally:
        os.unlink(tmp)
    return path


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("debate_id")
    p.add_argument("--work-id",required=True)
    p.add_argument("--project-root",type=Path,default=Path.cwd())
    p.add_argument("--request",type=Path,required=True)
    p.add_argument("--handoff",type=Path,required=True)
    p.add_argument("--handoff-sha",required=True)
    p.add_argument("--review",type=Path)
    p.add_argument("--candidate-sha")
    a=p.parse_args(argv)
    if (a.review is None)!=(a.candidate_sha is None):
        p.error("--review and --candidate-sha are required together")
    try:
        workspace,lock,items,owners=bridge.snapshot(a.project_root.resolve(),a.debate_id,a.work_id)
        candidates=prepare(bridge.load_json(a.request),bridge.load_json(a.handoff),
                           a.handoff_sha,lock,items,owners)
        if a.review is not None:
            matches=[c for c in candidates if bridge.digest(c)==a.candidate_sha]
            if len(matches)!=1:
                fail("published_quote_candidate_not_in_current_handoff")
            evidence=make_evidence(matches[0],a.candidate_sha,bridge.load_json(a.review))
            value=evidence["proposal"]
            result={"candidate_sha256":a.candidate_sha,"proposal_sha256":bridge.digest(value),
                    "proposal_path":str(write_private(workspace,value,"proposal")),
                    "evidence_sha256":evidence["evidence_sha256"],
                    "evidence_path":str(write_private(workspace,evidence,"evidence"))}
        else:
            result={"candidates":len(candidates),"artifacts":[
                {"candidate_sha256":bridge.digest(c),
                 "candidate_path":str(write_private(workspace,c,"candidate")),
                 "review_template_path":str(write_private(workspace,blank(c),"review-template"))}
                for c in candidates]}
        result.update(publication_authorized=False,translation_mutated=False)
    except (ValueError,RuntimeError,OSError,KeyError,TypeError,AttributeError) as exc:
        print(json.dumps({"status":"blocked","reason":str(exc) if isinstance(exc,bridge.QuoteBridgeError) else type(exc).__name__}))
        return 1
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
