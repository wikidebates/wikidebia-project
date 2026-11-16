from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from . import __version__
from .report import Report, portable_display_path
from .schema_validation import SchemaStore, pointer

OPERATIONS = ("create", "update", "move", "redirect", "delete", "skip", "manual_review", "blocked")
MUTATING = {"create", "update", "move", "redirect", "delete"}


def sha_object(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_remote_plan(path: str | Path) -> Report:
    source = Path(path)
    report = Report(__version__, portable_display_path(source), ["remote_plan"])
    try:
        plan = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError:
        report.error("WDV-FS-001", "Plan de reprise introuvable", path=portable_display_path(source))
        return report
    except json.JSONDecodeError as exc:
        report.error("WDV-SCH-001", f"Plan JSON illisible : {exc}", path=portable_display_path(source))
        return report
    if not isinstance(plan, dict):
        report.error("WDV-SCH-003", "Le plan doit être un objet JSON", path=portable_display_path(source))
        return report
    try:
        errors = SchemaStore().validate(plan, "remote_update_plan.schema.json")
    except Exception as exc:
        report.error("WDV-SCH-002", f"Schéma de plan inapplicable : {exc}", path=portable_display_path(source))
        return report
    for error in errors:
        report.error("WDV-SCH-003", error.message, path=portable_display_path(source), pointer=pointer(error.absolute_path), details={"schema": "remote_update_plan.schema.json"})

    unsigned = dict(plan)
    claimed = unsigned.pop("plan_sha256", None)
    if claimed != sha_object(unsigned):
        report.error("WDV-RMT-001", "Empreinte SHA-256 du plan divergente", path=portable_display_path(source))

    operations = plan.get("operations") or {}
    counts = plan.get("counts") or {}
    for name in OPERATIONS:
        rows = operations.get(name) or []
        if counts.get(name) != len(rows):
            report.error("WDV-RMT-002", f"Compteur incohérent pour {name}", path=portable_display_path(source), pointer=f"/counts/{name}")

    individualized_contract = str(plan.get("edit_summary_contract") or "")
    allowed_summary_policies = {
        "create": {"corpus_page_creation", "english_translation_creation"},
        "update": {"content_diff_v1", "french_interlanguage_addition"},
        "move": {"canonical_title_move_v1"},
        "redirect": {"merge_redirect_v1"},
        "delete": {"retirement_v1"},
    }

    seen_mutating: dict[tuple[str, str], str] = {}
    for name in OPERATIONS:
        for index, row in enumerate(operations.get(name) or []):
            if not isinstance(row, dict):
                continue
            key = (str(row.get("language")), str(row.get("title")))
            if name in MUTATING:
                previous = seen_mutating.get(key)
                if previous:
                    report.error("WDV-RMT-003", f"Titre présent dans plusieurs opérations mutantes : {previous} et {name}", pointer=f"/operations/{name}/{index}")
                seen_mutating[key] = name
                if individualized_contract == "page_specific_v1":
                    policy = str(row.get("edit_summary_policy") or "")
                    summary = str(row.get("edit_summary") or "").strip()
                    translation_invalid = (
                        policy == "english_translation_creation"
                        and (
                            row.get("language") != "en"
                            or not summary.startswith("Translation of the French page: [[:fr:")
                            or not summary.endswith("]]")
                        )
                    )
                    if policy not in allowed_summary_policies.get(name, set()) or not summary or summary.casefold() == "corrections" or translation_invalid:
                        report.error(
                            "WDV-RMT-008",
                            "Opération mutante sans résumé MediaWiki individualisé conforme au contrat page_specific_v1",
                            pointer=f"/operations/{name}/{index}",
                            details={"operation": name, "policy": policy, "summary": summary},
                        )
            if name == "delete":
                required = {"attested_in_previous_state", "absent_from_new_corpus", "remote_matches_published_state", "generated_marker_present", "delete_right"}
                if not row.get("old_sha256") or not required.issubset(set(row.get("preconditions") or [])):
                    report.error("WDV-RMT-004", "Suppression dépourvue de preuve d’ancien état ou de préconditions de sécurité", pointer=f"/operations/delete/{index}")
            if name == "update" and (not row.get("old_sha256") or not row.get("new_sha256")):
                report.error("WDV-RMT-005", "Mise à jour dépourvue d’empreinte ancienne ou nouvelle", pointer=f"/operations/update/{index}")

    comparisons = {str(row.get("comparison_id")) for row in plan.get("comparisons") or [] if isinstance(row, dict)}
    for name in ("manual_review",):
        for index, row in enumerate(operations.get(name) or []):
            if str(row.get("comparison_id")) not in comparisons:
                report.error("WDV-RMT-006", "Opération manual_review sans comparaison correspondante", pointer=f"/operations/{name}/{index}")

    report.metrics["operation_counts"] = {name: len(operations.get(name) or []) for name in OPERATIONS}
    report.metrics["comparison_count"] = len(plan.get("comparisons") or [])
    return report
