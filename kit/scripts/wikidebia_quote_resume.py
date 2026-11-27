"""Fresh read-only duplicate check before resuming unfinished English writes.

The signed semantic/authorization audit is never changed. A refreshed public
index can exempt a page only from comparison with its own selected argument,
after the current MediaWiki revision is reconciled with the authorized plan.
This cannot prove that a non-atomic wiki snapshot remains current after the
check, or distinguish identical concurrent writes by the very same account.
"""
from __future__ import annotations

from datetime import datetime,timezone
import copy

import wikidebia_quote_index_contract as q
from wikidebia_publish import sha_text,mediawiki_summary_matches,sha_object
from wikidebia_quote_index_stage import (
    _package_inputs,_checked_workspace,_selected_refresh,require_refresh_complete,
    stored_index,authorized_package_audit,
)


def _time(value):
    try:
        result=datetime.fromisoformat(value)
        if result.tzinfo is None:
            raise ValueError()
        return result
    except (ValueError,TypeError) as exc:
        raise q.QuoteIndexError("invalid_resume_quote_timestamp") from exc


def _checked_actions(arguments,plan):
    """Plan verification by the caller is required; bind every selected row."""
    if not isinstance(plan,dict) or not q.is_digest(plan.get("plan_sha256")):
        raise q.QuoteIndexError("invalid_resume_quote_plan")
    if sha_object({k:v for k,v in plan.items() if k!="plan_sha256"})!=plan["plan_sha256"]:
        raise q.QuoteIndexError("resume_quote_plan_digest_mismatch")
    selected={}
    for row in q._final_occurrences(arguments):
        selected[row["page_id"]]=row["title"]
    actions={}
    for action in plan.get("actions") or []:
        pid=action.get("page_id")
        if pid not in selected:
            continue
        if (pid in actions or action.get("language")!="en"
                or action.get("page_type")!="argument" or action.get("kind")!="full_page"
                or action.get("operation") not in {"create","update","skip"}
                or q._title(action.get("title",""))!=selected[pid]
                or not q.is_digest(action.get("desired_sha256"))):
            raise q.QuoteIndexError("resume_quote_action_scope_mismatch")
        actions[pid]=action
    if set(actions)!=set(selected):
        raise q.QuoteIndexError("resume_quote_action_scope_missing")
    return actions


def observe(arguments,index,plan,publisher,authorization,*,now=None):
    """Read only indexed destination pages; never accept progress counters.

    Current revision and content must agree with the index and plan. Existing
    authorized updates may still be at their original revision. Completed
    creations/updates require MediaWiki's parent, author, summary, tags and
    timestamp evidence. A migration's create->skip is handled as a creation
    only if its signed revision and the original authorization time agree.
    """
    now=now or datetime.now(timezone.utc)
    actions=_checked_actions(arguments,plan)
    originals={a["id"]:q._pinned_self_revision(a) for a in arguments}
    pages={q._title(p["title"]):p for p in index["pages"]}
    targets=[(pid,action,pages[q._title(action["title"])])
             for pid,action in sorted(actions.items()) if q._title(action["title"]) in pages]
    if not targets:
        return []
    authorized=_time(authorization.get("quote_duplicate_authorized_at",authorization.get("authorized_at")))
    # MediaWiki timestamps have second precision, whereas the authorization
    # is recorded with microseconds. Same-second writes are also protected
    # by the initial signed preflight and the other revision checks.
    earliest=authorized.replace(microsecond=0)
    _,user=publisher._site("en")
    adapter=publisher.adapter
    adapter.open_language("en",user)
    proofs=[]
    try:
        adapter.assert_identity(user)
        titles=[action["title"] for _,action,_ in targets]
        reader=getattr(adapter,"read_pages",None)
        observed=reader(titles) if callable(reader) else {t:adapter.read_page(t) for t in titles}
        if not isinstance(observed,dict) or set(observed)!=set(titles):
            raise q.QuoteIndexError("resume_quote_page_observation_incomplete")
        for pid,action,page in targets:
            exists,revision,raw=observed[action["title"]]
            if (exists is not True or type(revision) is not int or revision!=page["revision"]
                    or not isinstance(raw,str)):
                raise q.QuoteIndexError("resume_quote_index_target_revision_changed")
            digest=sha_text(raw)
            operation=action["operation"]
            if (operation=="update" and originals[pid]==revision
                    and action.get("remote_revision_id")==revision and action.get("remote_sha256")==digest):
                kind="verified_pinned_original"
            else:
                # A same-title page with identical quote but other content,
                # or a changed successor revision, is never exempted.
                if digest!=action["desired_sha256"]:
                    raise q.QuoteIndexError("resume_quote_plan_content_mismatch")
                if operation=="skip" and (action.get("remote_revision_id")!=revision
                                          or action.get("remote_sha256")!=digest):
                    raise q.QuoteIndexError("resume_quote_skip_revision_mismatch")
                revision_info=adapter.read_revision(action["title"],revision)
                parent=action.get("remote_revision_id") if operation=="update" else 0
                if (not isinstance(revision_info,dict)
                        or revision_info.get("revision_identity_complete") is not True
                        or revision_info.get("revision_id")!=revision
                        or revision_info.get("page_id")!=page["page_id"]
                        or q._title(revision_info.get("title",""))!=q._title(action["title"])
                        or type(parent) is not int or revision_info.get("parent_id")!=parent
                        or revision_info.get("user")!=user
                        or not isinstance(revision_info.get("text"),str)
                        or sha_text(revision_info["text"])!=digest
                        or not mediawiki_summary_matches(publisher._summary_for_action(action),
                                                        revision_info.get("summary",""))
                        or not set(publisher._tags_for_action(action)).issubset(revision_info.get("tags") or [])):
                    raise q.QuoteIndexError("resume_quote_revision_not_attributable")
                written=_time(revision_info.get("timestamp"))
                if not earliest<=written<=now:
                    raise q.QuoteIndexError("resume_quote_revision_outside_authorization")
                kind="verified_plan_update" if operation=="update" else "verified_plan_creation"
            proofs.append({"page_id":pid,"wiki_page_id":page["page_id"],
                           "wiki_revision":revision,"wiki_title":page["title"],
                           "proof_kind":kind,"content_sha256":digest})
    finally:
        adapter.close_language()
    return proofs


def audit(workspace,root,authorization,plan,publisher,*,now=None):
    """Reproduce historic authorization and independently refresh its scope.

    Only the write-resume path calls this gate. No network collection is
    performed here: an explicitly selected complete post-authorization
    index is mandatory. Save a private diagnostic, never a new permission.
    """
    from wikidebia_published_quote_review import write_private
    inputs=_package_inputs(root)
    if inputs is None:
        return None
    workspace=_checked_workspace(workspace)
    now=now or datetime.now(timezone.utc)
    saved=authorized_package_audit(workspace,root,authorization,now=now)
    require_refresh_complete(workspace)
    selected=_selected_refresh(workspace)
    if selected is None:
        raise q.QuoteIndexError("resume_quote_fresh_index_required")
    index=stored_index(workspace,selected)
    q.validate(index,selected,"en",now=now)
    if (_time(index["started_utc"]) < _time(authorization.get("quote_duplicate_authorized_at",authorization.get("authorized_at")))
            or selected==saved["index_sha256"]):
        raise q.QuoteIndexError("resume_quote_post_authorization_index_required")
    original,arguments,_,lock_sha=inputs
    # Do not certify a quotation altered by a remote-content replacement.
    # The renderer already verified the locked literal values; this guard
    # prevents subsequent publication-layer rewrites from changing them.
    for arg in arguments:
        for quote in arg.get("citations") or []:
            if publisher._remote_content_text("en",quote["quote"])!=quote["quote"]:
                raise q.QuoteIndexError("resume_quote_remote_replacement_changes_quote")
    publisher._verify_plan(plan,plan["plan_sha256"])
    proofs=observe(arguments,index,plan,publisher,authorization,now=now)
    result=q.final_audit(arguments,index,selected,lock_sha,now=now,resume_pages=proofs)
    if result["scope_sha256"]!=saved["scope_sha256"]:
        raise q.QuoteIndexError("resume_quote_scope_mismatch")
    diagnostic={"schema":"wikidebia-resume-quote-check-1",
                "authorization_sha256":authorization["authorization_sha256"],
                "english_plan_sha256":plan["plan_sha256"],
                "historical_audit_sha256":saved["audit_sha256"],
                "audit":result,"publication_authorized":False}
    write_private(workspace,diagnostic,"resume-audit")
    if result["status"]!="clear_exact_literal_scope":
        raise q.QuoteIndexError("resume_quote_exact_duplicates")
    return diagnostic
