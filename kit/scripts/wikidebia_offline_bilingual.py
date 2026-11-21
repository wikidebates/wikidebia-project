#!/usr/bin/env python3
"""Offline closure of a bilingual Work using *existing* signed linguistic proofs.

No MediaWiki client is imported or contacted.  A selector lists four immutable
kit artifacts (EN publication plan/receipt, FR update plan/receipt).  Two signed
published states independently attest each final page.  This route never
synthesizes a missing remote publication receipt.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping

from wikidebia_corpus_build import (
    validate_debate_id, exclusive_lock, assert_control_directory, assert_no_symlinks, full_tree_sha256,
    now_iso, relative_to_project, sha256_file, write_json,
)
from wikidebia_editorial_workspace import validate_work_id, workspace_receipt_hash
from wikidebia_post_publication import (
    PostPublicationError, _regular_json, _signed,
)
from wikidebia_render import _load_workspace
from wikidebia_update import sha_object


SCHEMA = "wikidebia-offline-bilingual-evidence-1.0"
INSTALL_SCHEMA = "wikidebia-offline-bilingual-install-1.0"
RECEIPT_SCHEMA = "wikidebia-offline-bilingual-reconciliation-receipt-1.0"
HEX64 = re.compile(r"[0-9a-f]{64}")


def _fail(reason: str) -> None:
    raise PostPublicationError(reason)


def _proof_path(project: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        _fail(f"Chemin relatif obligatoire pour {label}")
    path = project / value
    # _regular_json validates parent symlinks and project containment.
    _regular_json(path, label, project)
    return path


def _page_map(rows: Any, label: str) -> dict[tuple[str, str], dict[str, Any]]:
    if not isinstance(rows, list) or not rows:
        _fail(f"Pages absentes de {label}")
    pages: dict[tuple[str, str], dict[str, Any]] = {}
    for item in rows:
        if not isinstance(item, dict):
            _fail(f"Page illisible dans {label}")
        kind, ident = str(item.get("page_type") or ""), str(item.get("page_id") or "")
        key = (kind, ident)
        if kind not in {"debate", "argument"} or not ident or key in pages:
            _fail(f"Identité de page absente ou dupliquée dans {label}")
        pages[key] = item
    return pages


def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or HEX64.fullmatch(value) is None:
        _fail(f"SHA-256 manquant ou invalide : {label}")
    return value


def _revision(value: Any, label: str) -> int:
    if type(value) is not int or value < 1:
        _fail(f"Révision invalide : {label}")
    return value


def verify_bilingual_proofs(
    project: Path, debate_id: str, work_id: str, release: Path, selector: Path,
) -> dict[str, Any]:
    """Verify one exact page-by-page proof chain, without remote calls."""
    evidence = _regular_json(selector, "sélecteur des preuves bilingues", project)
    if (evidence.get("schema") != SCHEMA or evidence.get("debate_id") != debate_id
            or evidence.get("work_id") != work_id):
        _fail("Identité ou schéma du sélecteur des preuves divergent")
    expected_names = {"english_plan", "english_receipt", "french_plan", "french_receipt"}
    if set(evidence) != expected_names | {"schema", "debate_id", "work_id"}:
        _fail("Sélecteur incomplet ou contenant des chemins non prévus")
    proof_paths = {name: _proof_path(project, evidence[name], name) for name in expected_names}
    if len({path.resolve() for path in proof_paths.values()}) != 4:
        _fail("Deux preuves distinctes désignent le même fichier")
    en_plan = _signed(proof_paths["english_plan"], "plan anglais", "plan_sha256", project)
    fr_plan = _signed(proof_paths["french_plan"], "plan français", "plan_sha256", project)
    en_receipt = _signed(proof_paths["english_receipt"], "reçu anglais", "receipt_sha256", project)
    fr_receipt = _signed(proof_paths["french_receipt"], "reçu français", "receipt_sha256", project)
    states: dict[str, dict[str, Any]] = {}
    for language in ("en", "fr"):
        state_path = project / ".state/published" / debate_id / language / "latest.json"
        state = _signed(state_path, f"état publié {language}", "state_sha256", project)
        if state.get("debate_id") != debate_id or state.get("language") != language:
            _fail(f"État publié étranger au débat : {language}")
        states[language] = state

    if (en_plan.get("debate_id") != debate_id
            or en_plan.get("schema") != "wikidebia-publication-plan-1.0"
            or en_plan.get("blockers") not in ([], None)
            or fr_plan.get("debate_id") != debate_id
            or fr_plan.get("plan_version") != "wikidebia-remote-update-plan-1.0"
            or (fr_plan.get("operations") or {}).get("blocked")
            or (fr_plan.get("operations") or {}).get("manual_review")):
        _fail("Plans linguistiques non conformes ou comportant des blocages")
    if (en_receipt.get("debate_id") != debate_id
            or en_receipt.get("receipt_version") != "wikidebia-publication-state-receipt-1.0"
            or en_receipt.get("language") != "en"
            or fr_receipt.get("debate_id") != debate_id
            or fr_receipt.get("status") not in {"executed", "no_changes"}):
        _fail("Reçus linguistiques absents, étrangers ou non terminaux")
    if (en_receipt.get("plan_sha256") != en_plan.get("plan_sha256")
            or fr_receipt.get("plan_sha256") != fr_plan.get("plan_sha256")
            or states["en"].get("plan_sha256") != en_plan.get("plan_sha256")
            or states["fr"].get("plan_sha256") != fr_plan.get("plan_sha256")
            or states["en"].get("receipt_sha256") != en_receipt.get("receipt_sha256")
            or states["fr"].get("receipt_sha256") != fr_receipt.get("receipt_sha256")):
        _fail("Chaînage plan/reçu/état publié divergent")

    manifest_path = release / "manifest.json"
    manifest = _regular_json(manifest_path, "manifeste de release", project)
    manifest_sha = sha256_file(manifest_path)
    if (manifest.get("debate_id") not in (None, debate_id)
            or (en_plan.get("package_fingerprints") or {}).get("manifest_sha256") != manifest_sha
            or fr_plan.get("new_manifest_sha256") != manifest_sha
            or any(state.get("source_manifest_sha256") != manifest_sha for state in states.values())):
        _fail("Les plans et états ne correspondent pas au manifeste exact de release")
    expected = {
        language: _page_map(
            [row for row in manifest.get("pages") or [] if row.get("language") == language],
            f"manifeste {language}",
        ) for language in ("en", "fr")
    }
    for language in ("en", "fr"):
        if not expected[language]:
            _fail(f"Release sans pages {language}")

    en_actions = en_plan.get("actions")
    en_rows = _page_map(en_actions, "plan anglais")
    if set(en_rows) != set(expected["en"]):
        _fail("Le plan anglais ne couvre pas exactement les pages de release")
    en_final = _page_map(en_receipt.get("pages"), "reçu anglais")
    if set(en_final) != set(en_rows):
        _fail("Le reçu anglais ne couvre pas exactement le plan")
    final_states = {
        language: _page_map(states[language].get("pages"), f"état publié {language}")
        for language in ("fr", "en")
    }
    if set(final_states["en"]) != set(en_rows) or set(final_states["fr"]) != set(expected["fr"]):
        _fail("L'inventaire publié ne couvre pas exactement les deux langues")

    for key, action in en_rows.items():
        record, state, manifest_row = en_final[key], final_states["en"][key], expected["en"][key]
        title = str(action.get("title") or "")
        desired = _sha(action.get("desired_sha256"), f"en {key}")
        revision = _revision(record.get("revision_id"), f"en {key}")
        if (action.get("language") != "en"
                or action.get("operation") not in {"create", "skip"}
                or not title or action.get("page_type") != manifest_row.get("page_type")
                or title != manifest_row.get("canonical_title")
                or title != record.get("canonical_title")
                or title != state.get("canonical_title")
                or record.get("revision_id") != state.get("revision_id")
                or revision != _revision(state.get("revision_id"), f"état en {key}")
                or record.get("content_sha256") != desired
                or state.get("content_sha256") != desired
                or state.get("status") != "published"):
            _fail(f"Preuves anglaises divergentes pour {key}")

    operations = fr_plan.get("operations")
    if not isinstance(operations, dict) or any(
        operations.get(name) for name in ("create", "move", "redirect", "delete", "blocked", "manual_review")
    ):
        _fail("Le plan français autorise autre chose que l'interlangue")
    fr_updates = _page_map((operations.get("update") or []) + (operations.get("skip") or []), "plan français")
    if set(fr_updates) != set(expected["fr"]):
        _fail("Le plan français ne couvre pas exactement les pages de release")
    for key, op in fr_updates.items():
        state = final_states["fr"][key]
        desired = _sha(op.get("new_sha256"), f"fr {key}")
        if (op.get("language") != "fr"
                or op.get("title") != state.get("canonical_title")
                or state.get("status") != "published"
                or state.get("content_sha256") != desired):
            _fail(f"Plan ou état français divergent pour {key}")
        _revision(state.get("revision_id"), f"état fr {key}")
        if op in operations.get("update", []):
            if (op.get("edit_summary_policy") != "french_interlanguage_addition"
                    or "only_interlanguage_addition" not in (op.get("preconditions") or [])):
                _fail(f"Édition française hors interlangue : {key}")

    results = fr_receipt.get("results")
    if not isinstance(results, list):
        _fail("Résultats de page absents du reçu français")
    receipt_results: dict[tuple[str, str], dict[str, Any]] = {}
    for result in results:
        if not isinstance(result, dict):
            _fail("Résultat de publication français illisible")
        key = (str(result.get("operation") or ""), str(result.get("page_id") or ""))
        if key in receipt_results or result.get("language") != "fr":
            _fail("Résultat français dupliqué ou de mauvaise langue")
        receipt_results[key] = result
    updates = {(str(row.get("operation") or "update"), str(row["page_id"])) for row in operations.get("update") or []}
    skips = {("skip", str(row["page_id"])) for row in operations.get("skip") or []}
    if fr_receipt.get("status") == "executed":
        if fr_receipt.get("execution_mode") != "full_update" or set(receipt_results) != updates | skips:
            _fail("Reçu français incomplet ou mode d'exécution divergent")
    elif (fr_receipt.get("execution_mode") != "no_changes"
          or set(receipt_results) != skips or updates):
        _fail("Attestation sans changements française incomplète")
    for key, result in receipt_results.items():
        page_id = key[1]
        matches = [k for k in fr_updates if k[1] == page_id]
        if len(matches) != 1:
            _fail(f"Résultat français orphelin : {page_id}")
        op, state = fr_updates[matches[0]], final_states["fr"][matches[0]]
        allowed = {"updated", "already_done"} if key[0] == "update" else {"verified_unchanged"}
        if (result.get("title") != op.get("title")
                or result.get("status") not in allowed
                or result.get("revision_id") != state.get("revision_id")):
            _fail(f"Révision française finale sans preuve : {page_id}")
        if result.get("content_sha256") not in (None, state.get("content_sha256")):
            _fail(f"Contenu français final divergent : {page_id}")
    return {
        "selector_sha256": sha256_file(selector),
        "manifest_sha256": manifest_sha,
        "english_plan_sha256": en_plan["plan_sha256"],
        "french_plan_sha256": fr_plan["plan_sha256"],
        "english_receipt_sha256": en_receipt["receipt_sha256"],
        "french_receipt_sha256": fr_receipt["receipt_sha256"],
        "english_state_sha256": states["en"]["state_sha256"],
        "french_state_sha256": states["fr"]["state_sha256"],
        "page_counts": {"en": len(en_rows), "fr": len(fr_updates)},
    }


def _install_offline(
    project: Path, debate_id: str, work_id: str, release: Path,
    tree_sha: str, proof_sha: str, directory: Path,
) -> dict[str, Any]:
    """Install with a sealed write-ahead backup checkpoint; crash-safe on retry."""
    target = project / "corpus" / debate_id
    backup = project / "archives/debates" / f"offline-{debate_id}-{work_id}-{proof_sha[:12]}" / "previous-corpus"
    checkpoint_path = directory / "install-checkpoint.json"
    if checkpoint_path.is_file() or checkpoint_path.is_symlink():
        checkpoint = _signed(checkpoint_path, "checkpoint d'installation", "checkpoint_sha256", project)
        if (checkpoint.get("schema") != INSTALL_SCHEMA or checkpoint.get("debate_id") != debate_id
                or checkpoint.get("work_id") != work_id or checkpoint.get("release_tree_sha256") != tree_sha
                or checkpoint.get("proof_sha256") != proof_sha
                or checkpoint.get("backup_path") != relative_to_project(backup, project)):
            _fail("Checkpoint d'installation d'un autre corpus ou d'une autre preuve")
    else:
        if target.is_symlink() or backup.exists() or backup.is_symlink():
            _fail("Cible symbolique ou sauvegarde d'installation non attribuable")
        if target.exists():
            if not target.is_dir():
                _fail("Corpus précédent non répertoire")
            assert_no_symlinks(target)
        old_sha = full_tree_sha256(target) if target.exists() else None
        checkpoint = {
            "schema": INSTALL_SCHEMA, "debate_id": debate_id, "work_id": work_id,
            "release_tree_sha256": tree_sha, "proof_sha256": proof_sha,
            "previous_corpus_tree_sha256": old_sha if old_sha != tree_sha else None,
            "previous_corpus_already_identical": old_sha == tree_sha,
            "backup_path": relative_to_project(backup, project),
        }
        checkpoint["checkpoint_sha256"] = sha_object(checkpoint)
        write_json(checkpoint_path, checkpoint)

    prior = checkpoint["previous_corpus_tree_sha256"]
    if target.is_symlink() or backup.is_symlink():
        _fail("Lien symbolique dans le chemin d'installation")
    if backup.exists():
        if not backup.is_dir():
            _fail("Sauvegarde du corpus précédent invalide")
        assert_no_symlinks(backup)
        if prior is None or full_tree_sha256(backup) != prior:
            _fail("Sauvegarde du corpus précédent divergente")
    current = full_tree_sha256(target) if target.is_dir() else None
    if current == tree_sha:
        if prior and not backup.is_dir():
            _fail("Corpus installé mais sauvegarde précédente absente")
        return {"status": "already_installed", "path": f"corpus/{debate_id}",
                "tree_sha256": tree_sha, "backup_path": relative_to_project(backup, project) if prior else None}
    if current is not None and current != prior:
        _fail("Corpus actif modifié depuis le checkpoint")
    if current is None and prior and not backup.is_dir():
        _fail("Corpus précédent absent sans sauvegarde")
    if current is not None and prior:
        if backup.exists():
            _fail("Deux exemplaires incompatibles du corpus précédent")
        backup.parent.mkdir(parents=True, exist_ok=True)
        os.replace(target, backup)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = Path(tempfile.mkdtemp(prefix=f".{debate_id}.offline-", dir=target.parent))
        try:
            temp.rmdir()
            shutil.copytree(release, temp, symlinks=False)
            if full_tree_sha256(temp) != tree_sha:
                _fail("La copie temporaire diverge de release-copy")
            os.replace(temp, target)
        finally:
            if temp.exists():
                shutil.rmtree(temp)
    if full_tree_sha256(target) != tree_sha:
        _fail("Corpus installé divergent de la release attendue")
    return {"status": "installed", "path": f"corpus/{debate_id}",
            "tree_sha256": tree_sha, "backup_path": relative_to_project(backup, project) if prior else None}


def reconcile_offline_bilingual(
    project: Path, debate_id: str, work_id: str, selector: Path,
) -> dict[str, Any]:
    """Close a Work locally; no remote proof or receipt can be manufactured."""
    project = project.expanduser().resolve()
    debate_id = validate_debate_id(debate_id)
    work_id = validate_work_id(work_id)
    workspace, meta = _load_workspace(project, debate_id, work_id)
    if meta.get("status") not in {"release_ready", "remote_plan_ready", "published"}:
        _fail("Statut du workspace incompatible avec la clôture hors ligne")
    workflow = _regular_json(
        project / ".state/workflows" / debate_id / "workflow.json", "workflow", project,
    )
    if (workflow.get("debate_id") != debate_id or workflow.get("work_id") != work_id
            or workflow.get("schema") != "wikidebia-editorial-orchestration-1.0"):
        _fail("Workflow sans rattachement au Work demandé")
    release = workspace / "release-copy"
    if not release.is_dir() or release.is_symlink():
        _fail("Release gelée absente")
    assert_no_symlinks(release)
    tree = _sha((meta.get("release_copy") or {}).get("tree_sha256"), "release-copy")
    if full_tree_sha256(release) != tree:
        _fail("Release gelée modifiée")
    selector = selector if selector.is_absolute() else project / selector
    proofs = verify_bilingual_proofs(project, debate_id, work_id, release, selector)
    anchor = sha_object(proofs)
    state_root = assert_control_directory(project / ".state", project)
    root = assert_control_directory(state_root / "post-publication", project, create=True)
    debate_root = assert_control_directory(root / debate_id, project, create=True)
    directory = assert_control_directory(debate_root / work_id, project, create=True)
    receipt_path = directory / "offline-bilingual-receipt.json"
    existing = (
        _signed(receipt_path, "reçu local de clôture bilingue", "receipt_sha256", project)
        if receipt_path.exists() or receipt_path.is_symlink() else None
    )
    if existing is not None:
        if (existing.get("schema") != RECEIPT_SCHEMA
                or existing.get("debate_id") != debate_id or existing.get("work_id") != work_id
                or existing.get("proofs") != proofs or existing.get("release_copy_tree_sha256") != tree):
            _fail("Reçu de clôture antérieur incompatible")
    if meta["status"] == "published" and existing is None:
        _fail("Workspace déjà publié sous un autre contrat")

    installed = _install_offline(project, debate_id, work_id, release, tree, anchor, directory)
    sealed_at = str(existing["reconciled_at"]) if existing else now_iso()
    desired = dict(meta)
    desired["status"] = "published"
    desired["final_publication"] = {
        "status": "published",
        "mode": "offline_bilingual_attested_plans_v1",
        "reconciled_at": sealed_at,
        "receipt_path": relative_to_project(receipt_path, project),
        "receipt_sha256": existing["receipt_sha256"] if existing else None,
        "installed_corpus_path": installed["path"],
        "installed_corpus_tree_sha256": tree,
        "remote_access_performed_during_reconciliation": False,
        "remote_write_performed_during_reconciliation": False,
    }
    # Receipt hash cannot depend cyclically on the workspace receipt field.
    # The terminal state anchors the immutable proof chain; its local receipt
    # is signed separately and may be verified using the exact workspace SHA.
    desired["final_publication"]["receipt_sha256"] = None
    desired["workspace_sha256"] = None
    desired["workspace_sha256"] = workspace_receipt_hash(desired)
    if existing is None:
        receipt = {
            "schema": RECEIPT_SCHEMA, "debate_id": debate_id, "work_id": work_id,
            "status": "published", "reconciled_at": sealed_at,
            "previous_workspace_sha256": meta["workspace_sha256"],
            "workspace_sha256": desired["workspace_sha256"],
            "release_copy_tree_sha256": tree, "proofs": proofs,
            "installation": installed,
            "remote_access_performed": False, "remote_write_performed": False,
        }
        receipt["receipt_sha256"] = sha_object(receipt)
        write_json(receipt_path, receipt)
    else:
        if existing.get("workspace_sha256") != desired["workspace_sha256"]:
            _fail("État de clôture divergent du reçu signé")
        if meta["status"] != "published" and existing.get("previous_workspace_sha256") != meta["workspace_sha256"]:
            _fail("Le workspace a changé après une clôture interrompue")
        receipt = existing
    if meta["status"] == "published":
        if meta != desired:
            _fail("Workspace publié différent du reçu hors ligne")
        status = "reused"
    else:
        write_json(workspace / "workspace.json", desired)
        status = "resumed" if existing is not None else "completed"
    return {
        "status": "published", "reconciliation": status,
        "debate_id": debate_id, "work_id": work_id, "page_counts": proofs["page_counts"],
        "receipt_path": relative_to_project(receipt_path, project),
        "receipt_sha256": receipt["receipt_sha256"],
        "remote_access_performed": False, "remote_write_performed": False,
        "previous_corpus_backup": installed["backup_path"],
    }

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("debate_id")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--evidence", type=Path, required=True,
                        help="Sélecteur local des quatre preuves signées, sans accès wiki")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--machine-readable", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project = args.project_root.expanduser().resolve()
    with exclusive_lock(project, args.debate_id, "post-publication"):
        result = reconcile_offline_bilingual(
            project, args.debate_id, args.work_id, args.evidence,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True,
                     indent=None if args.machine_readable else 2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PostPublicationError, OSError, ValueError, KeyError) as exc:
        print(f"CLÔTURE BILINGUE HORS LIGNE BLOQUÉE : {exc}", file=os.sys.stderr)
        raise SystemExit(2)
