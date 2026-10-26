#!/usr/bin/env python3
"""Project signed publication history into a portable continuity snapshot."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any, Mapping


class ContinuityError(RuntimeError):
    pass


HISTORY_NAME = re.compile(r"^\d{8}T\d{6}Z\.json$")


def _sha_object(value: Mapping[str, Any], field: str) -> str:
    body = dict(value)
    body.pop(field, None)
    return hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _load_signed(path: Path, field: str, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ContinuityError(f"{label} absent ou non régulier : {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContinuityError(f"{label} illisible : {path}") from exc
    if not isinstance(value, dict) or value.get(field) != _sha_object(value, field):
        raise ContinuityError(f"Empreinte invalide pour {label} : {path}")
    return value


def _inside(path: Path, parent: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        return resolved.relative_to(parent.resolve())
    except ValueError as exc:
        raise ContinuityError(f"{label} extérieur au périmètre autorisé : {path}") from exc


def _same_file(source: Path, target: Path) -> bool:
    return target.is_file() and not target.is_symlink() and source.read_bytes() == target.read_bytes()


def _copy_exact(source: Path, target: Path) -> None:
    if source.is_symlink() or not source.is_file():
        raise ContinuityError(f"Source de continuité non régulière : {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def _refresh_sha256sums(snapshot_root: Path) -> None:
    rows: list[str] = []
    for path in sorted(item for item in snapshot_root.rglob("*") if item.is_file() and item.name != "SHA256SUMS"):
        if path.is_symlink():
            raise ContinuityError(f"Lien symbolique interdit dans la continuité : {path}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append(f"{digest}  ./{path.relative_to(snapshot_root).as_posix()}")
    (snapshot_root / "SHA256SUMS").write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")


def _verify_sha256sums(snapshot_root: Path) -> None:
    manifest = snapshot_root / "SHA256SUMS"
    if not manifest.is_file() or manifest.is_symlink():
        raise ContinuityError("SHA256SUMS absent de la projection de continuité")
    expected: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, separator, relative = line.partition("  ./")
        if not separator or not re.fullmatch(r"[0-9a-f]{64}", digest) or not relative:
            raise ContinuityError("Ligne SHA256SUMS invalide")
        if relative in expected:
            raise ContinuityError(f"Entrée SHA256SUMS dupliquée : {relative}")
        expected[relative] = digest
    if any(path.is_symlink() for path in snapshot_root.rglob("*")):
        raise ContinuityError("Lien symbolique interdit dans la continuité")
    actual_paths = sorted(
        path.relative_to(snapshot_root).as_posix()
        for path in snapshot_root.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    )
    if actual_paths != sorted(expected):
        raise ContinuityError("SHA256SUMS ne couvre pas exactement la projection de continuité")
    for relative, digest in expected.items():
        path = snapshot_root / relative
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ContinuityError(f"Empreinte de continuité divergente : {relative}")


def _page_map(state: Mapping[str, Any], label: str) -> dict[tuple[str, str], Mapping[str, Any]]:
    pages = state.get("pages")
    if not isinstance(pages, list):
        raise ContinuityError(f"Liste de pages invalide dans {label}")
    result: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in pages:
        if not isinstance(row, dict):
            raise ContinuityError(f"Page invalide dans {label}")
        key = (str(row.get("page_type") or ""), str(row.get("page_id") or ""))
        if not all(key) or key in result:
            raise ContinuityError(f"Identifiant de page absent ou dupliqué dans {label}")
        result[key] = row
    return result


def _validate_transition(
    anchor: Mapping[str, Any],
    previous: Mapping[str, Any],
    current: Mapping[str, Any],
    label: str,
    *,
    allow_release_change: bool = False,
) -> None:
    if not allow_release_change and current.get("source_manifest_sha256") != anchor.get("source_manifest_sha256"):
        raise ContinuityError("Une correction change le manifeste source du checkpoint")
    if not allow_release_change and current.get("corpus_version") != anchor.get("corpus_version"):
        raise ContinuityError("Une correction change la version de corpus du checkpoint")
    previous_pages = _page_map(previous, "l'état précédent")
    pages = _page_map(current, label)
    if set(pages) != set(previous_pages):
        raise ContinuityError("Une correction change l'ensemble des pages du checkpoint")
    for key, before in previous_pages.items():
        after = pages[key]
        before_revision = int(before.get("revision_id") or 0)
        after_revision = int(after.get("revision_id") or 0)
        if before_revision <= 0 or after_revision < before_revision:
            raise ContinuityError("Une correction fait régresser une révision publiée")
        if after_revision == before_revision and after != before:
            raise ContinuityError("Une correction change une page sans nouvelle révision")


def _receipt_location(value: str, debate_id: str, work_id: str) -> tuple[str, Path]:
    path = Path(value.strip())
    if not value.strip() or path.is_absolute() or ".." in path.parts:
        raise ContinuityError("Chemin de reçu non portable")
    correction_prefix = Path(".state/fr-publication") / debate_id / work_id
    final_prefix = Path(".state/receipts") / debate_id
    try:
        return "correction", path.relative_to(correction_prefix)
    except ValueError:
        pass
    try:
        return "final", path.relative_to(final_prefix)
    except ValueError as exc:
        raise ContinuityError("Reçu extérieur au périmètre autorisé") from exc


def _plan_page_keys(plan: Mapping[str, Any], bucket: str) -> set[tuple[str, str]]:
    operations = plan.get("operations") or {}
    if not isinstance(operations, dict):
        raise ContinuityError("Opérations invalides dans le plan final")
    rows = operations.get(bucket) or []
    if not isinstance(rows, list):
        raise ContinuityError("Liste d'opérations invalide dans le plan final")
    result: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ContinuityError("Opération invalide dans le plan final")
        key = (str(row.get("page_type") or ""), str(row.get("page_id") or ""))
        if not all(key) or key in result:
            raise ContinuityError("Page absente ou dupliquée dans le plan final")
        result.add(key)
    return result


def _validate_final_publication_bundle(
    *,
    debate_id: str,
    work_id: str,
    french_state: Mapping[str, Any],
    final_root: Path,
    receipts_root: Path,
    english_state_root: Path,
) -> None:
    """Validate the unique terminal bilingual publication and its signed chain."""
    baseline = _load_signed(
        final_root / "baseline.json", "baseline_sha256", "baseline finale"
    )
    if baseline.get("debate_id") != debate_id or baseline.get("work_id") != work_id:
        raise ContinuityError("Baseline finale rattachée à un autre débat ou Work")
    safety_plan = _load_signed(
        final_root / "safety-update-plan.json", "plan_sha256", "plan de sécurité final"
    )
    if safety_plan.get("debate_id") != debate_id or safety_plan.get("languages") != ["fr", "en"]:
        raise ContinuityError("Plan de sécurité final rattaché à un autre périmètre")

    french_plan = _load_signed(final_root / "french-update-plan.json", "plan_sha256", "plan français final")
    if french_plan.get("debate_id") != debate_id or french_plan.get("languages") != ["fr"]:
        raise ContinuityError("Plan français final rattaché à un autre débat ou périmètre")
    if french_plan.get("plan_sha256") != french_state.get("plan_sha256"):
        raise ContinuityError("Plan français final divergent de l'état publié")
    if french_plan.get("new_manifest_sha256") != french_state.get("source_manifest_sha256"):
        raise ContinuityError("Manifeste du plan final divergent de l'état publié")
    if french_plan.get("corpus_version") != french_state.get("corpus_version"):
        raise ContinuityError("Version de corpus du plan final divergente de l'état publié")
    operations = french_plan.get("operations") or {}
    forbidden = ("create", "move", "redirect", "delete", "manual_review", "blocked")
    if any(operations.get(name) for name in forbidden):
        raise ContinuityError("Le plan français final contient une opération interdite")
    planned_keys = _plan_page_keys(french_plan, "update") | _plan_page_keys(french_plan, "skip")
    french_pages = _page_map(french_state, "l'état français final")
    if planned_keys != set(french_pages):
        raise ContinuityError("Le plan français final ne couvre pas exactement l'état publié")
    for bucket in ("update", "skip"):
        for operation in operations.get(bucket) or []:
            key = (str(operation.get("page_type") or ""), str(operation.get("page_id") or ""))
            if operation.get("new_sha256") != french_pages[key].get("content_sha256"):
                raise ContinuityError("Contenu français final divergent du plan")

    kind, french_receipt_relative = _receipt_location(
        str(french_state.get("receipt_path") or ""), debate_id, work_id
    )
    if kind != "final":
        raise ContinuityError("L'état français final ne référence pas un reçu terminal")
    underlying_french = _load_signed(
        receipts_root / french_receipt_relative, "receipt_sha256", "reçu d'exécution français final"
    )
    if underlying_french.get("debate_id") != debate_id:
        raise ContinuityError("Reçu d'exécution français rattaché à un autre débat")
    if underlying_french.get("plan_sha256") != french_state.get("plan_sha256"):
        raise ContinuityError("Reçu d'exécution français divergent du plan final")
    if underlying_french.get("receipt_sha256") != french_state.get("receipt_sha256"):
        raise ContinuityError("Reçu d'exécution français divergent de l'état publié")

    french_receipt = _load_signed(
        final_root / "french-publication-receipt.json", "receipt_sha256", "reçu français final"
    )
    if french_receipt.get("status") not in {"published", "verified_no_changes"}:
        raise ContinuityError("Reçu français final non positif")
    if french_receipt.get("plan_sha256") != french_state.get("plan_sha256"):
        raise ContinuityError("Reçu français final divergent du plan")
    if french_receipt.get("underlying_receipt_sha256") != underlying_french.get("receipt_sha256"):
        raise ContinuityError("Reçu français final divergent du reçu d'exécution")
    french_counts = french_receipt.get("counts") or {}
    french_count_values = (
        french_counts.get("already_done") if isinstance(french_counts, dict) else None,
        french_counts.get("updated") if isinstance(french_counts, dict) else None,
    )
    if (
        not isinstance(french_counts, dict)
        or any(type(value) is not int or value < 0 for value in french_count_values)
        or sum(french_count_values) != len(planned_keys)
    ):
        raise ContinuityError("Décompte du reçu français final divergent du plan")

    english_plan = _load_signed(
        final_root / "english-publication-plan.json", "plan_sha256", "plan anglais final"
    )
    if english_plan.get("debate_id") != debate_id:
        raise ContinuityError("Plan anglais final rattaché à un autre débat")
    preflight = _load_signed(
        final_root / "preflight.json", "preflight_sha256", "préflight final"
    )
    if (
        preflight.get("status") != "ready"
        or preflight.get("safety_plan_sha256") != safety_plan.get("plan_sha256")
        or preflight.get("english_plan_sha256") != english_plan.get("plan_sha256")
        or preflight.get("french_plan_sha256") != french_plan.get("plan_sha256")
    ):
        raise ContinuityError("Préflight final divergent des plans signés")
    authorization = _load_signed(
        final_root / "authorization.json", "authorization_sha256", "autorisation finale"
    )
    if (
        authorization.get("status") != "authorized"
        or authorization.get("remote_write_authorized") is not True
        or authorization.get("baseline_sha256") != baseline.get("baseline_sha256")
        or authorization.get("preflight_sha256") != preflight.get("preflight_sha256")
    ):
        raise ContinuityError("Autorisation finale divergente de la baseline ou du préflight")
    english_receipt = _load_signed(
        final_root / "english-publication-receipt.json", "receipt_sha256", "reçu anglais final"
    )
    if (
        english_receipt.get("status") != "published"
        or english_receipt.get("plan_sha256") != english_plan.get("plan_sha256")
    ):
        raise ContinuityError("Reçu anglais final divergent du plan")

    english_latest = _load_signed(
        english_state_root / "latest.json", "state_sha256", "état anglais final"
    )
    if english_latest.get("debate_id") != debate_id or english_latest.get("language") != "en":
        raise ContinuityError("État anglais final rattaché à un autre débat ou langue")
    if english_latest.get("plan_sha256") != english_plan.get("plan_sha256"):
        raise ContinuityError("État anglais final divergent du plan")
    english_pages = _page_map(english_latest, "l'état anglais final")
    if set(english_pages) != set(_page_map(french_state, "l'état français final")):
        raise ContinuityError("Les états finaux anglais et français ne couvrent pas les mêmes pages")
    english_actions = english_plan.get("actions")
    if not isinstance(english_actions, list):
        raise ContinuityError("Actions invalides dans le plan anglais final")
    english_action_keys: set[tuple[str, str]] = set()
    for action in english_actions:
        if (
            not isinstance(action, dict)
            or action.get("language") != "en"
            or action.get("operation") != "create"
        ):
            raise ContinuityError("Action interdite dans le plan anglais final")
        key = (str(action.get("page_type") or ""), str(action.get("page_id") or ""))
        if not all(key) or key in english_action_keys or key not in english_pages:
            raise ContinuityError("Page absente ou dupliquée dans le plan anglais final")
        if action.get("desired_sha256") != english_pages[key].get("content_sha256"):
            raise ContinuityError("Contenu anglais final divergent du plan")
        english_action_keys.add(key)
    if english_action_keys != set(english_pages):
        raise ContinuityError("Le plan anglais final ne couvre pas exactement l'état publié")
    english_counts = english_receipt.get("counts") or {}
    english_created = english_counts.get("created") if isinstance(english_counts, dict) else None
    if (
        not isinstance(english_counts, dict)
        or type(english_created) is not int
        or english_created != len(english_action_keys)
    ):
        raise ContinuityError("Décompte du reçu anglais final divergent du plan")
    english_history = [
        _load_signed(path, "state_sha256", f"état historique anglais {path.name}")
        for path in sorted(english_state_root.glob("*.json"))
        if HISTORY_NAME.fullmatch(path.name)
    ]
    if not english_history or english_history[-1] != english_latest:
        raise ContinuityError("L'état anglais courant n'est pas le dernier état historique signé")
    english_receipt_kind, english_receipt_relative = _receipt_location(
        str(english_latest.get("receipt_path") or ""), debate_id, work_id
    )
    if english_receipt_kind != "final":
        raise ContinuityError("L'état anglais final ne référence pas un reçu terminal")
    underlying_english = _load_signed(
        receipts_root / english_receipt_relative, "receipt_sha256", "reçu d'exécution anglais final"
    )
    if underlying_english.get("debate_id") != debate_id or underlying_english.get("language") != "en":
        raise ContinuityError("Reçu d'exécution anglais rattaché à un autre débat ou langue")
    if underlying_english.get("plan_sha256") != english_plan.get("plan_sha256"):
        raise ContinuityError("Reçu d'exécution anglais divergent du plan")
    if underlying_english.get("receipt_sha256") != english_latest.get("receipt_sha256"):
        raise ContinuityError("Reçu d'exécution anglais divergent de l'état publié")

    final_receipt = _load_signed(
        final_root / "publication-receipt.json", "receipt_sha256", "reçu bilingue final"
    )
    if (
        final_receipt.get("debate_id") != debate_id
        or final_receipt.get("work_id") != work_id
        or final_receipt.get("status") != "published"
    ):
        raise ContinuityError("Reçu bilingue final rattaché à un autre Work ou non publié")
    if final_receipt.get("french_receipt_sha256") != french_receipt.get("receipt_sha256"):
        raise ContinuityError("Reçu bilingue final divergent du reçu français")
    if final_receipt.get("english_receipt_sha256") != english_receipt.get("receipt_sha256"):
        raise ContinuityError("Reçu bilingue final divergent du reçu anglais")
    if final_receipt.get("baseline_sha256") != baseline.get("baseline_sha256"):
        raise ContinuityError("Reçu bilingue final divergent de la baseline")
    if final_receipt.get("preflight_sha256") != preflight.get("preflight_sha256"):
        raise ContinuityError("Reçu bilingue final divergent du préflight")
    if final_receipt.get("authorization_sha256") != authorization.get("authorization_sha256"):
        raise ContinuityError("Reçu bilingue final divergent de l'autorisation")


def verify_committed_snapshot(snapshot_root: Path, debate_id: str | None = None) -> dict[str, Any]:
    """Verify that a committed snapshot carries a self-contained FR succession."""
    snapshot_root = snapshot_root.resolve()
    if not snapshot_root.is_dir():
        raise ContinuityError("Racine de continuité absente")
    _verify_sha256sums(snapshot_root)
    debate_id = debate_id or snapshot_root.parent.name

    content_receipt = _load_signed(
        snapshot_root / "runtime/fr-publication/content/publication-receipt.json",
        "receipt_sha256",
        "reçu du checkpoint de contenu",
    )
    work_id = str(content_receipt.get("work_id") or "")
    if content_receipt.get("debate_id") != debate_id or not work_id:
        raise ContinuityError("Reçu du checkpoint rattaché à un autre débat ou sans Work")

    state_root = snapshot_root / "runtime/published/fr"
    latest = _load_signed(state_root / "latest.json", "state_sha256", "état français courant")
    if latest.get("debate_id") != debate_id or latest.get("language") != "fr":
        raise ContinuityError("État français courant rattaché à un autre débat ou langue")
    history: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(state_root.glob("*.json")):
        if HISTORY_NAME.fullmatch(path.name):
            history.append((path, _load_signed(path, "state_sha256", f"état historique {path.name}")))
    if not history:
        raise ContinuityError("Aucun état historique français signé dans la continuité")
    for path, state in history:
        if state.get("debate_id") != debate_id or state.get("language") != "fr":
            raise ContinuityError(f"État historique hors débat : {path.name}")
    if history[-1][1] != latest:
        raise ContinuityError("L'état courant n'est pas le dernier état historique signé")

    checkpoint_plan = str(content_receipt.get("plan_sha256") or "")
    checkpoint_receipt = str(content_receipt.get("remote_receipt_sha256") or "")
    anchor_index = next((
        index for index, (_path, state) in enumerate(history)
        if str(state.get("plan_sha256") or "") == checkpoint_plan
        and (not checkpoint_receipt or str(state.get("receipt_sha256") or "") == checkpoint_receipt)
    ), None)
    if anchor_index is None:
        raise ContinuityError("État historique du checkpoint de contenu introuvable")

    anchor = history[anchor_index][1]
    previous = anchor
    correction_count = 0
    final_count = 0
    later = history[anchor_index + 1:]
    for index, (path, state) in enumerate(later):
        kind, receipt_relative = _receipt_location(
            str(state.get("receipt_path") or ""), debate_id, work_id
        )
        if kind == "correction":
            if final_count:
                raise ContinuityError("Une correction suit déjà l'état de publication finale")
            _validate_transition(anchor, previous, state, f"l'état corrigé {path.name}")
            receipt = _load_signed(
                snapshot_root / "runtime/fr-publication" / receipt_relative,
                "receipt_sha256",
                "reçu de correction",
            )
            if receipt.get("debate_id") != debate_id or receipt.get("work_id") != work_id:
                raise ContinuityError("Reçu de correction rattaché à un autre débat ou Work")
            if receipt.get("language") not in {None, "fr"}:
                raise ContinuityError("Reçu de correction rattaché à une autre langue")
            if receipt.get("plan_sha256") != state.get("plan_sha256") or receipt.get("receipt_sha256") != state.get("receipt_sha256"):
                raise ContinuityError("Reçu de correction divergent de l'état publié")
            correction_count += 1
        else:
            if final_count or index != len(later) - 1:
                raise ContinuityError("L'état de publication finale doit être unique et terminal")
            _validate_transition(
                anchor, previous, state, f"l'état final {path.name}", allow_release_change=True
            )
            _validate_final_publication_bundle(
                debate_id=debate_id,
                work_id=work_id,
                french_state=state,
                final_root=snapshot_root / "runtime/final-publication",
                receipts_root=snapshot_root / "runtime/receipts",
                english_state_root=snapshot_root / "runtime/published/en",
            )
            final_count += 1
        previous = state

    return {
        "status": "passed",
        "debate_id": debate_id,
        "work_id": work_id,
        "history_state_count": len(history),
        "post_checkpoint_correction_count": correction_count,
        "current_state_sha256": latest.get("state_sha256"),
    }


def sync_signed_french_history(
    project_root: Path,
    debate_id: str,
    *,
    work_id: str | None = None,
    snapshot_root: Path | None = None,
    check_only: bool = False,
) -> dict[str, Any]:
    """Copy and verify all signed FR states required to resume final publication."""
    project_root = project_root.resolve()
    workflow_path = project_root / ".state/workflows" / debate_id / "workflow.json"
    if not workflow_path.is_file():
        raise ContinuityError("Workflow local absent")
    try:
        workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContinuityError("Workflow local illisible") from exc
    current_work = str(workflow.get("work_id") or "")
    if not current_work or (work_id and work_id != current_work):
        raise ContinuityError("Work demandé différent du workflow courant")
    work_id = current_work

    default_snapshot = project_root / "continuity" / debate_id / "latest"
    snapshot_root = (snapshot_root or default_snapshot)
    snapshot_root = snapshot_root.resolve() if snapshot_root.is_absolute() else (project_root / snapshot_root).resolve()
    _inside(snapshot_root, project_root / "continuity", "Projection de continuité")
    if not snapshot_root.is_dir():
        raise ContinuityError("Racine de continuité absente")

    work_root = project_root / ".state/fr-publication" / debate_id / work_id
    content_receipt_path = work_root / "content/publication-receipt.json"
    content_receipt = _load_signed(content_receipt_path, "receipt_sha256", "reçu du checkpoint de contenu")
    if content_receipt.get("debate_id") != debate_id or content_receipt.get("work_id") != work_id:
        raise ContinuityError("Reçu du checkpoint rattaché à un autre débat ou Work")

    state_root = project_root / ".state/published" / debate_id / "fr"
    latest_path = state_root / "latest.json"
    latest = _load_signed(latest_path, "state_sha256", "état français courant")
    if latest.get("debate_id") != debate_id or latest.get("language") != "fr":
        raise ContinuityError("État français courant rattaché à un autre débat ou langue")

    history: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(state_root.glob("*.json")):
        if not HISTORY_NAME.fullmatch(path.name):
            continue
        state = _load_signed(path, "state_sha256", f"état historique {path.name}")
        if state.get("debate_id") != debate_id or state.get("language") != "fr":
            raise ContinuityError(f"État historique hors débat : {path.name}")
        history.append((path, state))
    if not history:
        raise ContinuityError("Aucun état historique français signé")

    anchor_plan = str(content_receipt.get("plan_sha256") or "")
    anchor_receipt = str(content_receipt.get("remote_receipt_sha256") or "")
    anchor_index = next((
        index for index, (_path, state) in enumerate(history)
        if str(state.get("plan_sha256") or "") == anchor_plan
        and (not anchor_receipt or str(state.get("receipt_sha256") or "") == anchor_receipt)
    ), None)
    current_index = next((
        index for index, (_path, state) in enumerate(history)
        if state.get("state_sha256") == latest.get("state_sha256")
    ), None)
    if anchor_index is None:
        raise ContinuityError("État historique du checkpoint de contenu introuvable")
    if current_index is None or current_index < anchor_index or current_index != len(history) - 1:
        raise ContinuityError("L'état courant n'est pas le dernier état historique signé")

    required: list[tuple[Path, Path]] = []
    target_state_root = snapshot_root / "runtime/published/fr"
    for source, _state in history[:current_index + 1]:
        required.append((source, target_state_root / source.name))
    required.append((latest_path, target_state_root / "latest.json"))
    required.append((content_receipt_path, snapshot_root / "runtime/fr-publication/content/publication-receipt.json"))
    required.append((workflow_path, snapshot_root / "runtime/workflow/workflow.json"))

    anchor = history[anchor_index][1]
    previous = anchor
    correction_count = 0
    final_count = 0
    later = history[anchor_index + 1:current_index + 1]
    for index, (path, state) in enumerate(later):
        receipt_value = str(state.get("receipt_path") or "")
        kind, receipt_relative = _receipt_location(receipt_value, debate_id, work_id)
        if kind == "correction":
            if final_count:
                raise ContinuityError("Une correction suit déjà l'état de publication finale")
            _validate_transition(anchor, previous, state, f"l'état corrigé {path.name}")
            receipt_source = (project_root / receipt_value).resolve()
            _inside(receipt_source, work_root, "Reçu de correction")
            receipt = _load_signed(receipt_source, "receipt_sha256", "reçu de correction")
            if receipt.get("debate_id") != debate_id or receipt.get("work_id") != work_id:
                raise ContinuityError("Reçu de correction rattaché à un autre débat ou Work")
            if receipt.get("language") not in {None, "fr"}:
                raise ContinuityError("Reçu de correction rattaché à une autre langue")
            if receipt.get("plan_sha256") != state.get("plan_sha256") or receipt.get("receipt_sha256") != state.get("receipt_sha256"):
                raise ContinuityError("Reçu de correction divergent de l'état publié")
            required.append((receipt_source, snapshot_root / "runtime/fr-publication" / receipt_relative))
            correction_count += 1
        else:
            if final_count or index != len(later) - 1:
                raise ContinuityError("L'état de publication finale doit être unique et terminal")
            _validate_transition(
                anchor, previous, state, f"l'état final {path.name}", allow_release_change=True
            )
            final_root = project_root / ".state/final-publication" / debate_id / work_id
            receipts_root = project_root / ".state/receipts" / debate_id
            english_state_root = project_root / ".state/published" / debate_id / "en"
            _validate_final_publication_bundle(
                debate_id=debate_id,
                work_id=work_id,
                french_state=state,
                final_root=final_root,
                receipts_root=receipts_root,
                english_state_root=english_state_root,
            )
            for source_root, target_root in (
                (final_root, snapshot_root / "runtime/final-publication"),
                (receipts_root, snapshot_root / "runtime/receipts"),
                (english_state_root, snapshot_root / "runtime/published/en"),
            ):
                for source in sorted(source_root.rglob("*")):
                    if source.is_symlink():
                        raise ContinuityError(f"Lien symbolique interdit dans la preuve finale : {source}")
                    if source.is_file():
                        required.append((source, target_root / source.relative_to(source_root)))
            final_count += 1
        previous = state

    if check_only:
        missing = [str(target.relative_to(snapshot_root)) for source, target in required if not _same_file(source, target)]
        if missing:
            raise ContinuityError("Projection de continuité incomplète : " + ", ".join(missing))
        _verify_sha256sums(snapshot_root)
    else:
        for source, target in required:
            _copy_exact(source, target)
        _refresh_sha256sums(snapshot_root)
        for source, target in required:
            if not _same_file(source, target):
                raise ContinuityError(f"Copie de continuité divergente : {target}")
        _verify_sha256sums(snapshot_root)

    return {
        "status": "passed",
        "mode": "check" if check_only else "sync",
        "debate_id": debate_id,
        "work_id": work_id,
        "snapshot_root": snapshot_root.relative_to(project_root).as_posix(),
        "history_state_count": current_index + 1,
        "post_checkpoint_correction_count": correction_count,
        "current_state_sha256": latest.get("state_sha256"),
    }
