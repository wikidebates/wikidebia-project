#!/usr/bin/env python3
"""Early, strictly read-only authentication preflight for bilingual workflows."""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from typing import Any, Mapping

from wikidebia_corpus_build import load_json
from wikidebia_publish import PywikibotAdapter, sha_object
from wikidebia_release_info import KIT_VERSION
from wikidebia_update import UpdateAdapter


ACCESS_PREFLIGHT_SCHEMA = "wikidebia-access-preflight-1.0"
DEFAULT_LANGUAGES = ("fr", "en")
DEFAULT_REQUIRED_RIGHTS = ("createpage", "edit")
DEFAULT_REQUIRED_TAGS = ("chatgpt",)
DEFAULT_MAX_AGE_SECONDS = 6 * 60 * 60


class AccessPreflightError(RuntimeError):
    pass


def _settings(project_root: Path) -> dict[str, Any]:
    path = project_root / "config/wikidebia.local.json"
    return load_json(path, "configuration locale") if path.is_file() else {}


def access_contract(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    settings = _settings(project_root)
    users = settings.get("expected_users") or {"fr": "ChatGPT", "en": "ChatGPT"}
    configured_languages = settings.get("access_preflight_languages") or DEFAULT_LANGUAGES
    languages = tuple(str(language) for language in configured_languages)
    if not languages or len(set(languages)) != len(languages):
        raise AccessPreflightError("Langues du diagnostic d’accès invalides")
    if any(language not in {"fr", "en"} for language in languages):
        raise AccessPreflightError("Le diagnostic d’accès accepte uniquement fr et en")
    required_rights = sorted({
        str(value) for value in (settings.get("access_preflight_required_rights") or DEFAULT_REQUIRED_RIGHTS)
        if str(value)
    })
    required_tags = sorted({
        str(value) for value in (settings.get("access_preflight_required_tags") or DEFAULT_REQUIRED_TAGS)
        if str(value)
    })
    if not required_rights:
        raise AccessPreflightError("Droits minimaux du diagnostic d’accès absents")
    try:
        max_age_seconds = int(
            settings.get("access_preflight_max_age_seconds", DEFAULT_MAX_AGE_SECONDS)
        )
    except (TypeError, ValueError) as exc:
        raise AccessPreflightError("Durée de validité du diagnostic d’accès invalide") from exc
    if not 300 <= max_age_seconds <= 24 * 60 * 60:
        raise AccessPreflightError("La durée de validité du diagnostic doit être comprise entre 300 et 86400 secondes")
    credential_configuration = {
        "local_pywikibot_config_present": (
            project_root / "private/pywikibot/user-config.py"
        ).is_file(),
        "managed_variables": {
            language: {
                "username_present": bool(os.environ.get(f"WIKIDEBIA_{language.upper()}_BOT_USERNAME")),
                "password_present": bool(os.environ.get(f"WIKIDEBIA_{language.upper()}_BOT_PASSWORD")),
            }
            for language in languages
        },
    }
    return {
        "family": str(settings.get("family") or "wikidebates"),
        "languages": list(languages),
        "sites": {
            language: {
                "code": language,
                "expected_user": str(users.get(language) or "ChatGPT"),
            }
            for language in languages
        },
        "required_rights": required_rights,
        "required_tags": required_tags,
        "max_age_seconds": max_age_seconds,
        "credential_configuration": credential_configuration,
    }


def access_contract_sha256(project_root: Path) -> str:
    return sha_object(access_contract(project_root))


def verify_access_receipt(
    receipt: Mapping[str, Any],
    contract_sha256: str,
    *,
    now: dt.datetime | None = None,
) -> bool:
    value = dict(receipt)
    claimed = value.pop("receipt_sha256", None)
    structurally_valid = bool(
        claimed
        and claimed == sha_object(value)
        and receipt.get("schema") == ACCESS_PREFLIGHT_SCHEMA
        and receipt.get("schema_version") == "1.0"
        and receipt.get("status") == "ready"
        and receipt.get("contract_sha256") == contract_sha256
        and receipt.get("remote_write_performed") is False
    )
    if not structurally_valid:
        return False
    try:
        checked_at = dt.datetime.fromisoformat(str(receipt.get("checked_at") or "").replace("Z", "+00:00"))
        max_age_seconds = int((receipt.get("contract") or {})["max_age_seconds"])
    except (TypeError, ValueError, KeyError):
        return False
    if checked_at.tzinfo is None:
        return False
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    age_seconds = (current.astimezone(dt.timezone.utc) - checked_at.astimezone(dt.timezone.utc)).total_seconds()
    return -300 <= age_seconds <= max_age_seconds


def run_access_preflight(
    project_root: Path,
    *,
    adapter: Any | None = None,
    checked_at: str | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    contract = access_contract(project_root)
    contract_sha = sha_object(contract)
    if adapter is None:
        base = PywikibotAdapter(
            contract["family"],
            {language: str(contract["sites"][language]["code"]) for language in contract["languages"]},
            project_root / "private/pywikibot",
            project_root / "kit/families/wikidebates_family.py",
        )
        adapter = UpdateAdapter(base)

    results: list[dict[str, Any]] = []
    for language in contract["languages"]:
        expected_user = str(contract["sites"][language]["expected_user"])
        opened = False
        try:
            adapter.open_language(language, expected_user)
            opened = True
            adapter.assert_identity(expected_user)
            rights = {str(value) for value in adapter.user_rights()}
            missing_rights = sorted(set(contract["required_rights"]) - rights)
            if missing_rights:
                raise AccessPreflightError(
                    f"Droits MediaWiki absents sur {language} : {', '.join(missing_rights)}"
                )
            available_tags = {str(value) for value in adapter.available_change_tags()}
            missing_tags = sorted(set(contract["required_tags"]) - available_tags)
            if missing_tags:
                raise AccessPreflightError(
                    f"Balises MediaWiki absentes sur {language} : {', '.join(missing_tags)}"
                )
            results.append({
                "language": language,
                "expected_user": expected_user,
                "required_rights": list(contract["required_rights"]),
                "required_tags": list(contract["required_tags"]),
                "status": "ready",
            })
        except AccessPreflightError:
            raise
        except Exception as exc:
            raise AccessPreflightError(
                f"Authentification ou diagnostic MediaWiki refusé sur {language} : {exc}"
            ) from exc
        finally:
            if opened:
                adapter.close_language()

    receipt: dict[str, Any] = {
        "schema": ACCESS_PREFLIGHT_SCHEMA,
        "schema_version": "1.0",
        "kit_version": KIT_VERSION,
        "checked_at": checked_at or dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "status": "ready",
        "contract": contract,
        "contract_sha256": contract_sha,
        "results": results,
        "remote_write_performed": False,
    }
    receipt["receipt_sha256"] = sha_object(receipt)
    return receipt
