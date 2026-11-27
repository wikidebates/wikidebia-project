"""Private staging of a public fingerprint snapshot for final translation review.

This is a local file transfer, not a second registry or a network operation.
The expected digest must come from the trusted index producer.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

import wikidebia_quote_index_contract as contract


def load_index(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > contract.MAX_INDEX_BYTES:
        raise contract.QuoteIndexError("invalid_public_quote_index_file")
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise contract.QuoteIndexError("duplicate_public_quote_index_key")
            result[k] = v
        return result
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream, object_pairs_hook=unique)


def stage(workspace, path, expected_sha, *, now=None):
    from wikidebia_published_quote_review import write_private
    value = load_index(path)
    contract.validate(value, expected_sha, "en", now=now)
    return write_private(workspace, value, "public-index")


def stored_index(workspace, expected_sha):
    if not contract.is_digest(expected_sha):
        raise contract.QuoteIndexError("invalid_public_quote_index_digest")
    path = (workspace/"audits/quote-resolver/published-quotes/public-index"/
            (expected_sha+".json"))
    if not path.resolve().is_relative_to(workspace.resolve()):
        raise contract.QuoteIndexError("unsafe_public_quote_index_path")
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise contract.QuoteIndexError("missing_or_nonprivate_public_quote_index")
    value = load_index(path)
    if contract.digest(value) != expected_sha:
        raise contract.QuoteIndexError("public_index_digest_mismatch")
    return value


def refresh_path(workspace):
    path = workspace/"audits/quote-resolver/published-quotes/refresh-index.json"
    if not path.resolve().is_relative_to(workspace.resolve()) or path.is_symlink():
        raise contract.QuoteIndexError("unsafe_public_quote_refresh_path")
    return path


def _selected_refresh(workspace):
    path = refresh_path(workspace)
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise contract.QuoteIndexError("nonprivate_public_quote_refresh")
    value = load_index(path)
    if (not isinstance(value, dict) or set(value) != {"schema","index_sha256"}
            or value["schema"] != "wikidebia-quote-index-refresh-1"
            or not contract.is_digest(value["index_sha256"])):
        raise contract.QuoteIndexError("invalid_public_quote_refresh")
    return value["index_sha256"]


def _write_pointer(path, payload):
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd,tmp = tempfile.mkstemp(prefix=".quote-index-pointer-",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump(payload,f,sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def pending_path(workspace):
    return refresh_path(workspace).with_name("refresh-pending.json")


def pending_refresh(workspace):
    path = pending_path(workspace)
    if path.is_symlink() or not path.resolve().is_relative_to(workspace.resolve()):
        raise contract.QuoteIndexError("unsafe_public_quote_refresh_path")
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise contract.QuoteIndexError("nonprivate_public_quote_refresh")
    value = load_index(path)
    if (not isinstance(value,dict) or set(value)!={"schema","started_utc"}
            or value["schema"]!="wikidebia-quote-index-refresh-pending-1"):
        raise contract.QuoteIndexError("invalid_pending_quote_refresh")
    try:
        started = datetime.fromisoformat(value["started_utc"])
        if started.tzinfo is None:
            raise ValueError()
    except (TypeError,ValueError) as exc:
        raise contract.QuoteIndexError("invalid_pending_quote_refresh") from exc
    return started


def begin_refresh(workspace, *, now=None):
    """An attempted collection may not silently fall back to old evidence."""
    workspace = _checked_workspace(workspace)
    now = now or datetime.now(timezone.utc)
    previous = pending_refresh(workspace)
    if now.tzinfo is None or (previous is not None and now < previous):
        raise contract.QuoteIndexError("invalid_pending_quote_refresh_time")
    _write_pointer(pending_path(workspace),
                   {"schema":"wikidebia-quote-index-refresh-pending-1",
                    "started_utc":now.isoformat()})
    return now


def require_refresh_complete(workspace):
    if pending_refresh(workspace) is not None:
        raise contract.QuoteIndexError("public_quote_refresh_pending")


def latest_selected_sha(workspace, fallback=None, *, allow_pending=False):
    """Choose a verified newer selected index, not a stale draft pointer."""
    if not allow_pending:
        require_refresh_complete(workspace)
    selected = _selected_refresh(workspace)
    if selected is None:
        return fallback
    value = stored_index(workspace,selected)
    if fallback is not None and selected != fallback:
        prior = stored_index(workspace,fallback)
        finish = datetime.fromisoformat(value["finished_utc"])
        before = datetime.fromisoformat(prior["finished_utc"])
        if finish < before:
            return fallback
        if finish == before:
            raise contract.QuoteIndexError("public_quote_refresh_same_time_conflict")
    return selected


def select_refresh(workspace, path, expected_sha, *, now=None):
    """Stage a new trusted snapshot, not a new semantic approval.

    Selection is local to this Work. Reject a rollback to an older snapshot.
    No index is selected if validation or staging fails.
    """
    artifact = stage(workspace,path,expected_sha,now=now)
    value = stored_index(workspace,expected_sha)
    previous = _selected_refresh(workspace)
    if previous is not None:
        prior = stored_index(workspace,previous)
        finished = datetime.fromisoformat(value["finished_utc"])
        prior_finished = datetime.fromisoformat(prior["finished_utc"])
        if finished < prior_finished or (finished == prior_finished and expected_sha != previous):
            raise contract.QuoteIndexError("public_quote_refresh_rollback")
    started = pending_refresh(workspace)
    if started is not None and datetime.fromisoformat(value["started_utc"]) < started:
        raise contract.QuoteIndexError("public_quote_refresh_predates_attempt")
    _write_pointer(refresh_path(workspace),
                   {"schema":"wikidebia-quote-index-refresh-1","index_sha256":expected_sha})
    # A crash between selecting and clearing is conservatively blocked; a
    # retry of the same newly collected index clears it idempotently.
    if started is not None:
        pending_path(workspace).unlink()
    return artifact


def verify_current(workspace, audit, arguments, original_index, lock_sha, *, now=None):
    """Recheck the immutable audit, then use a newer snapshot if selected.

    A newer failing check is never replaced by a previous clean one. The
    historical semantic review, original audit and original index remain
    unchanged. The refreshed diagnostic is private and content-addressed.
    """
    from wikidebia_published_quote_review import write_private
    contract.verify_final_audit(audit,arguments,original_index,lock_sha,now=now)
    require_refresh_complete(workspace)
    selected = _selected_refresh(workspace)
    value, expected = original_index,audit["index_sha256"]
    if selected is not None:
        candidate = stored_index(workspace,selected)
        finish = datetime.fromisoformat(candidate["finished_utc"])
        before = datetime.fromisoformat(value["finished_utc"])
        if finish == before and selected != expected:
            raise contract.QuoteIndexError("public_quote_refresh_same_time_conflict")
        if finish >= before:
            value,expected = candidate,selected
    result = contract.final_audit(arguments,value,expected,lock_sha,now=now)
    if result["scope_sha256"] != audit["scope_sha256"]:
        raise contract.QuoteIndexError("public_quote_refresh_scope_changed")
    write_private(workspace,result,"final-audit")
    if result["status"] != "clear_exact_literal_scope":
        raise contract.QuoteIndexError("final_quote_exact_duplicates")
    return result


def _package_inputs(root):
    """Read the immutable package's selected quote scope and original audit."""
    from wikidebia_corpus_build import load_json
    path = root/"data/en_content_lock.json"
    translation_path = root/"data/en_translation_lock.json"
    en = load_json(path) if path.is_file() else {}
    translation = load_json(translation_path) if translation_path.is_file() else {}
    policy = translation.get("citation_translation_policy") or {}
    has_published = any(q.get("translation_origin")=="published_translation"
                        or "published_quote_evidence" in q
                        for a in en.get("arguments") or [] for q in a.get("citations") or [])
    audit = en.get("quote_duplicate_audit")
    sha = policy.get("quote_duplicate_audit_sha256")
    if (not has_published and audit is None and sha is None
            and en.get("published_quote_contract") is None
            and policy.get("published_quote_contract") is None):
        return None
    if not isinstance(audit,dict) or audit.get("audit_sha256") != sha:
        raise contract.QuoteIndexError("missing_or_unbound_final_quote_audit")
    return (audit,en["arguments"],load_index(root/contract.INDEX_PATH),
            hashlib.sha256((root/"data/fr_content_lock.json").read_bytes()).hexdigest())


def _checked_workspace(workspace):
    # Resolve the trusted workspace only after discovering the opt-in.
    workspace = workspace() if callable(workspace) else workspace
    if not workspace.is_dir() or workspace.is_symlink():
        raise contract.QuoteIndexError("invalid_public_quote_workspace")
    return workspace


def package_audit(workspace, root, *, now=None):
    """Check an applied/rendered/release copy, leaving every byte intact."""
    inputs = _package_inputs(root)
    if inputs is None:
        return None
    return verify_current(_checked_workspace(workspace),*inputs,now=now)


def authorized_package_audit(workspace, root, authorization, *, now=None):
    """Reproduce a prior authorization's exact quotation decision on resume.

    Unlike a fresh preflight, this does not compare an interrupted plan's
    own newly created public pages against itself. It does not assert that
    the current public wiki is unchanged; that would need a new snapshot
    and independent identification of pages already written by this plan.
    No workspace or network is used for legacy Works.
    """
    inputs = _package_inputs(root)
    saved = authorization.get("quote_duplicate_preflight")
    if inputs is None:
        if "quote_duplicate_preflight" in authorization:
            raise contract.QuoteIndexError("unexpected_authorized_quote_audit")
        return None
    if not isinstance(saved,dict) or not contract.is_digest(saved.get("index_sha256")):
        raise contract.QuoteIndexError("missing_authorized_quote_audit")
    original,arguments,index,lock_sha = inputs
    contract.verify_final_audit(original,arguments,index,lock_sha,now=now)
    if saved["index_sha256"] != original["index_sha256"]:
        candidate = stored_index(_checked_workspace(workspace),saved["index_sha256"])
        if datetime.fromisoformat(candidate["finished_utc"]) < datetime.fromisoformat(index["finished_utc"]):
            raise contract.QuoteIndexError("authorized_quote_index_rollback")
        index = candidate
    try:
        checked = datetime.fromisoformat(saved["checked_at"])
        authorized = datetime.fromisoformat(authorization.get(
            "quote_duplicate_authorized_at",authorization["authorized_at"]))
        reissued = datetime.fromisoformat(authorization["authorized_at"])
        original_check = datetime.fromisoformat(original["checked_at"])
        if (any(t.tzinfo is None for t in (checked,authorized,original_check,reissued))
                or not original_check <= checked <= authorized <= reissued
                or (authorized-checked).total_seconds() > 300):
            raise ValueError()
    except (ValueError,TypeError,KeyError) as exc:
        raise contract.QuoteIndexError("authorized_quote_audit_timestamp_mismatch") from exc
    derived = contract.verify_final_audit(saved,arguments,index,lock_sha,now=now)
    if derived["scope_sha256"] != original["scope_sha256"]:
        raise contract.QuoteIndexError("authorized_quote_scope_mismatch")
    return derived


def main(argv=None):
    from wikidebia_editorial_review import _load_workspace
    from wikidebia_corpus_build import exclusive_lock, validate_debate_id
    from wikidebia_editorial_workspace import validate_work_id
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("debate_id")
    p.add_argument("--work-id", required=True)
    p.add_argument("--project-root", type=Path, default=Path.cwd())
    p.add_argument("--index", type=Path, required=True)
    p.add_argument("--sha256", required=True)
    p.add_argument("--refresh",action="store_true",
                   help="Select a fresh index for subsequent technical gates; do not reopen translation")
    a = p.parse_args(argv)
    try:
        project = a.project_root.resolve()
        debate,work = validate_debate_id(a.debate_id),validate_work_id(a.work_id)
        with exclusive_lock(project,debate,"quote_index_stage"):
            workspace, meta = _load_workspace(project,debate,work)
            path = (select_refresh if a.refresh else stage)(workspace,a.index,a.sha256)
    except (ValueError,RuntimeError,OSError,KeyError,TypeError,AttributeError) as exc:
        reason = str(exc) if isinstance(exc,contract.QuoteIndexError) else type(exc).__name__
        print(json.dumps({"status":"blocked","reason":reason}))
        return 1
    print(json.dumps({"status":"staged","quote_public_index_sha256":a.sha256,
                      "path":str(path),"selected_for_refresh":a.refresh,
                      "translation_mutated":False,"publication_authorized":False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
