"""Select verified published quotations in an OPEN English translation draft.

No rights, completeness or editorial approval is created here. The existing
French locks, resolved receipts and independent edition/rights reviews are
read-only inputs. The command only copies an explicitly selected, fully
reviewed proposal into an otherwise untouched draft citation row.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import tempfile

import wikidebia_quote_bridge as bridge
import wikidebia_published_quote_contract as contract
import wikidebia_quote_index_contract as index_contract
from wikidebia_quote_index_stage import load_index, stored_index, latest_selected_sha, require_refresh_complete
from wikidebia_translation_review import TRANSLATION_REVIEW_SCHEMA, _blank_citation


def fail(reason):
    raise bridge.QuoteBridgeError(reason)


def read_evidence(workspace, path):
    directory = workspace/"audits/quote-resolver/published-quotes/evidence"
    path = Path(path)
    if (not directory.resolve().is_relative_to(workspace.resolve())
            or path.is_symlink() or path.resolve().parent != directory.resolve()
            or not path.is_file() or path.stat().st_mode & 0o077
            or path.suffix != ".json" or not bridge.is_digest(path.stem)):
        fail("published_quote_selection_invalid_private_evidence_path")
    value = load_index(path)
    if bridge.digest(value) != path.stem:
        fail("published_quote_selection_evidence_file_digest_mismatch")
    return value


def select_draft(review, lock_sha, items, owners, french_arguments, evidence_rows):
    """Return a new draft after ALL selections validate; never modify input.

    Idempotent for an already selected identical proposal. Never overwrite a
    partially translated/approved row, never select a winner between two
    receipts, and never change the source or the status of an argument.
    """
    if (review.get("schema") != TRANSLATION_REVIEW_SCHEMA
            or review.get("status") != "draft" or review.get("review_sha256") is not None
            or any(k in review for k in ("final_values","semantic_content_sha256","quote_duplicate_audit"))):
        fail("published_quote_selection_requires_unsealed_draft")
    if review.get("published_quote_contract") not in (None, contract.EVIDENCE):
        fail("published_quote_selection_unknown_contract")
    source_items = bridge.unique_rows(items,"id")
    source_pages = bridge.unique_rows(french_arguments,"id")
    result = copy.deepcopy(review)
    draft_pages = bridge.unique_rows(result.get("arguments") or [],"id")
    selected, unchanged, seen = [], [], set()
    for evidence in evidence_rows:
        if not isinstance(evidence,dict) or not isinstance(evidence.get("candidate"),dict):
            fail("published_quote_selection_invalid_evidence")
        candidate = evidence["candidate"]
        item = candidate.get("item")
        cid = item.get("id") if isinstance(item,dict) else None
        if not isinstance(cid,str) or cid in seen:
            fail("published_quote_selection_duplicate_or_invalid_occurrence")
        seen.add(cid)
        if cid not in source_items or cid not in owners:
            fail("published_quote_selection_occurrence_not_eligible")
        page = owners[cid]
        if page not in source_pages or page not in draft_pages:
            fail("published_quote_selection_page_not_eligible")
        source = bridge.unique_rows(source_pages[page].get("citations") or [],"id").get(cid)
        translation = draft_pages[page].get("translation")
        if (source is None or not isinstance(translation,dict)
                or (translation.get("french") or {}).get("content") != source_pages[page]):
            fail("published_quote_selection_authoritative_source_changed")
        row = bridge.unique_rows(translation.get("citations") or [],"id").get(cid)
        if row is None or row.get("source") != source:
            fail("published_quote_selection_draft_source_changed")
        projection = contract.verify_evidence(evidence,lock_sha,source_items[cid],page)
        if any(entry.get("citation_id") == cid and entry.get("evidence_sha256") == evidence["evidence_sha256"]
               for entry in result.get("published_quote_withdrawals") or []):
            fail("published_quote_selection_previously_withdrawn_evidence")
        params = {r["name"]:r["value"] for r in projection["parameters"]}
        updates = {"translation_origin":"published_translation",
                   "published_quote_evidence":copy.deepcopy(evidence),
                   "translated_citation":params["quote"],
                   "translated_date":params.get("date","")}
        if all(row.get(k)==v for k,v in updates.items()):
            unchanged.append(cid)
            continue
        if translation.get("status") != "pending" or row != _blank_citation(source):
            fail("published_quote_selection_existing_editorial_work")
        row.update(updates)
        selected.append(cid)
    if not seen:
        fail("published_quote_selection_empty")
    result["published_quote_contract"] = contract.EVIDENCE
    return result, {"selected":sorted(selected),"already_selected":sorted(unchanged)}


def withdraw_draft(review, lock_sha, items, owners, french_arguments, citation_id,
                   expected_evidence_sha, reviewer, reason):
    """Explicitly withdraw one selected passage, preserving its complete audit.

    This is not an approval of the AI fallback or of a replacement passage.
    The returned draft must undergo the normal editorial and uniqueness checks.
    """
    if (review.get("schema") != TRANSLATION_REVIEW_SCHEMA
            or review.get("status") != "draft" or review.get("review_sha256") is not None
            or any(k in review for k in ("final_values", "semantic_content_sha256", "quote_duplicate_audit"))):
        fail("published_quote_withdrawal_requires_unsealed_draft")
    if (review.get("published_quote_contract") != contract.EVIDENCE
            or not bridge.is_digest(expected_evidence_sha)
            or not isinstance(reviewer, str) or len(reviewer.strip()) < 3
            or not isinstance(reason, str) or len(reason.strip()) < 12):
        fail("published_quote_withdrawal_missing_explicit_decision")
    source_items = bridge.unique_rows(items, "id")
    source_pages = bridge.unique_rows(french_arguments, "id")
    result = copy.deepcopy(review)
    pages = bridge.unique_rows(result.get("arguments") or [], "id")
    page = owners.get(citation_id)
    if citation_id not in source_items or page not in source_pages or page not in pages:
        fail("published_quote_withdrawal_occurrence_not_eligible")
    source = bridge.unique_rows(source_pages[page].get("citations") or [], "id").get(citation_id)
    translation = pages[page].get("translation")
    if (source is None or not isinstance(translation, dict)
            or (translation.get("french") or {}).get("content") != source_pages[page]):
        fail("published_quote_withdrawal_authoritative_source_changed")
    row = bridge.unique_rows(translation.get("citations") or [], "id").get(citation_id)
    if (row is None or row.get("source") != source
            or row.get("translation_origin") != "published_translation"):
        fail("published_quote_withdrawal_selection_missing")
    evidence = row.get("published_quote_evidence")
    if not isinstance(evidence, dict) or evidence.get("evidence_sha256") != expected_evidence_sha:
        fail("published_quote_withdrawal_evidence_changed")
    projection = contract.verify_evidence(evidence, lock_sha, source_items[citation_id], page)
    params = {p["name"]: p["value"] for p in projection["parameters"]}
    if (row.get("translated_citation") != params["quote"]
            or row.get("translated_date", "") != params.get("date", "")):
        fail("published_quote_withdrawal_projection_changed")
    decision = {
        "schema": "wikidebia-published-quote-withdrawal-1",
        "source_lock_sha256": lock_sha, "page_id": page, "citation_id": citation_id,
        "evidence_sha256": expected_evidence_sha, "previous_row": copy.deepcopy(row),
        "reviewer": reviewer.strip(), "reason": reason.strip(),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    decision["withdrawal_sha256"] = bridge.digest(decision)
    result.setdefault("published_quote_withdrawals", []).append(decision)
    row.clear()
    row.update(_blank_citation(source))
    translation["status"] = "pending"
    for unit in result.get("review_units") or []:
        if page in (unit.get("page_ids") or []):
            unit.update(status="pending", reviewer="", reviewed_at=None, note="")
    if isinstance(result.get("global_review"), dict):
        result["global_review"].update(all_entities_translated=False,
                                       all_equivalences_reviewed=False,
                                       all_selected_sources_verified=False,
                                       reviewer="", reviewed_at=None, note="")
    if not any(c.get("translation_origin") == "published_translation"
               for a in result["arguments"]
               for c in (a.get("translation") or {}).get("citations") or []):
        result.pop("published_quote_contract")
    # Even after withdrawal of the last published passage, a Work that opted
    # into the experimental route cannot evade the global uniqueness gate.
    result["quote_uniqueness_policy"] = index_contract.UNIQUENESS_POLICY
    return result, {"withdrawn": [citation_id], "withdrawal_sha256": decision["withdrawal_sha256"]}


def _write_draft(path, value, expected_bytes):
    """One atomic replacement under the corpus lock, with a last-byte check."""
    fd,tmp = tempfile.mkstemp(prefix=".quote-selection-",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if path.is_symlink() or path.read_bytes()!=expected_bytes:
            fail("published_quote_selection_concurrent_draft_change")
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _commit_selection(project, debate_id, work_id, workspace, path, before, updated, *, replace_pending_package=False):
    """Keep the normal high-level ZIP workflow compatible with local selection.

    An existing outgoing ZIP is immutable until the operator explicitly opts
    into its replacement. Reissue precisely the same file allowlist under a
    new package identity; on local failure restore the draft, ZIP and state.
    The caller holds the corpus lock.
    """
    import wikidebia_review_workflow as wf

    workflow_path = wf._workflow_path(project, debate_id)
    if not workflow_path.exists():
        _write_draft(path, updated, before)
        return None
    state = wf._load_workflow(project, debate_id)
    pending = state.get("pending_review")
    if not pending:
        _write_draft(path, updated, before)
        return None
    review_type = pending.get("review_type")
    if (state.get("work_id") != work_id or pending.get("work_id") != work_id
            or review_type not in {"en_translation_review", "en_translation_correction"}
            or state.get("phase") != review_type or state.get("status") != "awaiting_review"
            or (project / pending["base_path"]).resolve() != workspace.resolve()):
        fail("published_quote_selection_other_pending_review")
    if not replace_pending_package:
        fail("published_quote_selection_pending_package_use_--replace-pending-package")
    archive = project / pending["package_path"]
    if (archive.resolve() != (project / "outgoing" / f"{debate_id}_{review_type}.zip").resolve()
            or archive.is_symlink() or not archive.is_file()
            or wf._sha256_file(archive) != pending["archive_sha256"]):
        fail("published_quote_selection_pending_package_changed")
    manifest, files = wf._read_returned_package(archive)
    wf._validate_pending_identity(state, manifest)
    for group, hash_key in (("editable_files", "sha256_at_prepare"), ("context_files", "sha256")):
        for row in manifest[group]:
            local = workspace / row["target_path"]
            wf._assert_regular_file(local, "Fichier du paquet de revue")
            if (not local.resolve().is_relative_to(workspace.resolve())
                    or wf._sha256_file(local) != row[hash_key]
                    or wf._sha256_bytes(files[row["package_path"]]) != row[hash_key]):
                fail("published_quote_selection_pending_package_baseline_changed")
    if path.relative_to(workspace).as_posix() not in {row["target_path"] for row in manifest["editable_files"]}:
        fail("published_quote_selection_pending_package_missing_draft")
    candidate = copy.deepcopy(state)
    candidate.setdefault("superseded_reviews", []).append({
        "reason": "local_published_quote_selection",
        "pending_review": copy.deepcopy(pending),
        "recorded_at": wf.now_iso(),
    })
    candidate["pending_review"] = None
    # Backups stay private and on the same filesystem. No remote action.
    with tempfile.TemporaryDirectory(prefix=".quote-package-", dir=workflow_path.parent) as temporary:
        backups = []
        for i, original in enumerate((path, archive, workflow_path)):
            saved = Path(temporary) / str(i)
            shutil.copy2(original, saved)
            backups.append((saved, original))
        # A failed compare-and-swap must not roll back an external edit.
        _write_draft(path, updated, before)
        try:
            replacement = wf.create_review_package(
                project, candidate, review_type=review_type, base=workspace,
                editable_paths=[row["target_path"] for row in manifest["editable_files"]],
                context_paths=[row["target_path"] for row in manifest["context_files"]],
                counts=manifest["counts"],
            )
        except Exception:
            for saved, original in backups:
                os.replace(saved, original)
            raise
    return {"package_id": replacement["package_id"], "package_path": replacement["package_path"],
            "superseded_package_id": pending["package_id"]}


def select_workspace(project, debate_id, work_id, evidence_paths, index_sha=None, *, replace_pending_package=False, withdrawal=None):
    from wikidebia_corpus_build import full_tree_sha256
    from wikidebia_editorial_review import _load_workspace
    workspace,meta = _load_workspace(project,debate_id,work_id)
    if meta.get("status")!="en_translation_review_ready" or (workspace/"translated-copy").exists():
        fail("published_quote_selection_requires_open_workspace")
    checked_workspace,lock_sha,inputs = bridge._snapshot_inputs(project,debate_id,work_id)
    if checked_workspace!=workspace:
        fail("published_quote_selection_workspace_changed")
    source,registry,metadata,content,provenance = inputs
    items,owners = bridge.locked_items(*inputs)
    path = workspace/"reviews/en/translation_review.json"
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(workspace.resolve()):
        fail("published_quote_selection_invalid_draft_path")
    before = path.read_bytes()
    current = load_index(path)
    if (current.get("debate_id")!=debate_id or current.get("work_id")!=work_id
            or current.get("prepared_content_reviewed_copy_sha256")!=full_tree_sha256(source)):
        fail("published_quote_selection_draft_identity_mismatch")
    if withdrawal is not None:
        if evidence_paths:
            fail("published_quote_selection_and_withdrawal_conflict")
        updated,summary = withdraw_draft(current,lock_sha,items,owners,content.get("arguments") or [],*withdrawal)
    else:
        evidence = [read_evidence(workspace,p) for p in evidence_paths]
        updated,summary = select_draft(current,lock_sha,items,owners,content.get("arguments") or [],evidence)
    prior_sha = current.get("quote_public_index_sha256")
    require_refresh_complete(workspace)
    newest = latest_selected_sha(workspace,prior_sha)
    chosen = index_sha if index_sha is not None else newest
    if index_sha is not None and newest is not None and index_sha != newest:
        newest_value = stored_index(workspace,newest)
        requested = stored_index(workspace,index_sha)
        if datetime.fromisoformat(requested["finished_utc"]) <= datetime.fromisoformat(newest_value["finished_utc"]):
            fail("published_quote_selection_index_rollback")
    if chosen is not None:
        value = stored_index(workspace,chosen)
        index_contract.validate(value,chosen,"en")
        if prior_sha is not None and prior_sha != chosen:
            prior = stored_index(workspace,prior_sha)
            if datetime.fromisoformat(value["finished_utc"]) <= datetime.fromisoformat(prior["finished_utc"]):
                fail("published_quote_selection_index_rollback")
        updated["quote_public_index_sha256"] = chosen
    # Do not require an index merely to fill an editorial draft. Finalization
    # requires a fresh complete index before accepting any published citation.
    replacement = None
    if updated!=current:
        replacement = _commit_selection(project, debate_id, work_id, workspace, path, before, updated,
                                        replace_pending_package=replace_pending_package)
    return {**summary,"status":"draft_withdrawn" if withdrawal is not None else "draft_selected","review_status":"draft",
            "replacement_review_package":replacement,
            "quote_public_index_sha256":chosen,"requires_fresh_index_before_finalize":chosen is None,
            "translation_draft_mutated":updated!=current,"source_locks_mutated":False,
            "editorial_approval_created":False,"publication_authorized":False}


def main(argv=None):
    from wikidebia_corpus_build import exclusive_lock, validate_debate_id
    from wikidebia_editorial_workspace import validate_work_id
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("debate_id")
    parser.add_argument("--work-id",required=True)
    parser.add_argument("--project-root",type=Path,default=Path.cwd())
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--evidence",type=Path,action="append")
    action.add_argument("--withdraw", nargs=2, metavar=("CITATION_ID", "EVIDENCE_SHA256"),
                        help="Withdraw one exact selection; retain its evidence and require a fresh review.")
    parser.add_argument("--reviewer")
    parser.add_argument("--reason")
    parser.add_argument("--index-sha256")
    parser.add_argument("--replace-pending-package", action="store_true",
                        help="Reissue an outstanding English review ZIP; its old identity will no longer be accepted.")
    args = parser.parse_args(argv)
    if args.withdraw and (not args.reviewer or not args.reason):
        parser.error("--withdraw requires --reviewer and --reason")
    if not args.withdraw and (args.reviewer is not None or args.reason is not None):
        parser.error("--reviewer and --reason are reserved for --withdraw")
    withdrawal = (*args.withdraw, args.reviewer, args.reason) if args.withdraw else None
    try:
        project = args.project_root.resolve()
        debate = validate_debate_id(args.debate_id)
        work = validate_work_id(args.work_id)
        with exclusive_lock(project,debate,"published_quote_selection"):
            summary = select_workspace(project,debate,work,args.evidence or [],args.index_sha256,
                                       replace_pending_package=args.replace_pending_package,
                                       withdrawal=withdrawal)
    except (ValueError,RuntimeError,OSError,KeyError,TypeError,AttributeError) as exc:
        reason = str(exc) if isinstance(exc,(bridge.QuoteBridgeError,contract.PublishedQuoteError,
                                               index_contract.QuoteIndexError)) else type(exc).__name__
        print(json.dumps({"status":"blocked","reason":reason}))
        return 1
    print(json.dumps(summary,sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
