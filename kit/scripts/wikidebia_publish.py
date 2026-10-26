from __future__ import annotations

from wikidebia_release_info import KIT_VERSION, REQUIRED_VALIDATOR_VERSION, PUBLICATION_PLAN_SCHEMA, PUBLICATION_PLAN_SCHEMA_VERSION, publication_plan_is_compatible, require_validator_report

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
from wikidebia_title_structure import canonical_title_structure_issues
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PUBLICATION_PLAN_VERSION = PUBLICATION_PLAN_SCHEMA
DIRECT_INTERLANGUAGE_PROFILE = "norm_1_2_direct_interlanguage"
DEFERRED_TRANSLATION_PROFILE = "norm_1_2_deferred_translation"
DIRECT_PROFILES = {DIRECT_INTERLANGUAGE_PROFILE, DEFERRED_TRANSLATION_PROFILE}
REQUIRED_DIRECT_SCOPES = {"schema", "coherence", "graph", "files", "batches", "sources", "wikicode", "bilingual", "editorial", "workflow"}
PAIRED_EM_DASH_RE = re.compile(r"\s—\s[^—\n]{1,500}?\s—(?=\s|[.,;:!?])")
SPLIT_ADJACENT_TEMPLATES_RE = re.compile(r"}}[ \t\r\n]+\{\{")
LEGACY_PROFILE = "legacy"
DEFAULT_FAMILY_DIR = Path(__file__).resolve().parent.parent / "families"


class PublicationError(RuntimeError):
    pass


class PublicationDateChanged(PublicationError):
    """The verified plan has become stale solely because the civil day changed."""


class IdentityError(PublicationError):
    pass


class RevisionConflict(PublicationError):
    pass


class CollisionError(PublicationError):
    pass


def normalize_wikicode(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")

def _alphabetical_key(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.casefold())
    return "".join(c for c in folded if not unicodedata.combining(c))


def alphabetical_values(value: str) -> list[str]:
    items = [item.strip() for item in value.split(",") if item.strip()]
    return sorted(items, key=_alphabetical_key)


def _first_alpha_is_upper(value: str) -> bool:
    first = next((c for c in value.strip() if c.isalpha()), "")
    return bool(first and first.isupper())


def _complete_topic_is_interrogative(value: str, language: str) -> bool:
    clean = value.strip()
    if not clean or "?" in clean:
        return True
    if language == "fr":
        return bool(re.match(r"^(?:si\b|faut[- ]?il\b|est[- ]?ce\s+que\b|doit[- ]?on\b|peut[- ]?on\b)", clean, flags=re.I))
    return bool(re.match(r"^(?:whether\b|if\b|should\b|can\b|could\b|is\b|are\b|do\b|does\b|must\b)", clean, flags=re.I))


def sha_text(text: str) -> str:
    return hashlib.sha256(normalize_wikicode(text).encode("utf-8")).hexdigest()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def portable(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def sha_object(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sha_tree(path: Path) -> str:
    path = path.resolve()
    if path.is_file():
        return sha_file(path)
    if not path.is_dir():
        raise PublicationError(f"Chemin à empreinter introuvable : {path}")
    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        relative = item.relative_to(path).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(bytes.fromhex(sha_file(item)))
    return digest.hexdigest()


def dotted_get(value: Any, dotted_path: str) -> Any:
    current = value
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            raise PublicationError(f"Champ introuvable : {dotted_path}")
        current = current[part]
    return current


def recursive_find_version(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("validator_version", "version"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
        for child in value.values():
            found = recursive_find_version(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = recursive_find_version(child)
            if found:
                return found
    return None


@dataclass(frozen=True)
class ParameterSpan:
    name: str
    value_start: int
    value_end: int


def _main_template_parameter_spans(text: str) -> list[ParameterSpan]:
    start = text.find("{{")
    if start < 0:
        raise PublicationError("Aucun modèle principal trouvé")
    template_depth = 0
    link_depth = 0
    in_comment = False
    pipes: list[int] = []
    main_close: int | None = None
    index = start
    while index < len(text):
        if in_comment:
            end = text.find("-->", index)
            if end < 0:
                raise PublicationError("Commentaire HTML non fermé")
            index = end + 3
            in_comment = False
            continue
        if text.startswith("<!--", index):
            in_comment = True
            index += 4
            continue
        if text.startswith("[[", index):
            link_depth += 1
            index += 2
            continue
        if text.startswith("]]", index) and link_depth:
            link_depth -= 1
            index += 2
            continue
        if text.startswith("{{", index):
            template_depth += 1
            index += 2
            continue
        if text.startswith("}}", index):
            if template_depth == 1:
                main_close = index
                break
            if template_depth > 1:
                template_depth -= 1
                index += 2
                continue
            raise PublicationError("Fermeture de modèle inattendue")
        if text[index] == "|" and template_depth == 1 and link_depth == 0:
            pipes.append(index)
        index += 1
    if main_close is None:
        raise PublicationError("Modèle principal non fermé")
    boundaries = pipes + [main_close]
    spans: list[ParameterSpan] = []
    for position, pipe in enumerate(pipes):
        segment_end = boundaries[position + 1]
        segment = text[pipe + 1 : segment_end]
        equal = segment.find("=")
        if equal < 0:
            continue
        name = segment[:equal].strip()
        if not name:
            continue
        spans.append(
            ParameterSpan(
                name=name,
                value_start=pipe + 1 + equal + 1,
                value_end=segment_end,
            )
        )
    return spans



def _main_template_close_index(text: str) -> int:
    """Retourne la position du }} fermant le modèle principal."""
    start = text.find("{{")
    if start < 0:
        raise PublicationError("Aucun modèle principal trouvé")

    template_depth = 0
    link_depth = 0
    in_comment = False
    index = start

    while index < len(text):
        if in_comment:
            end = text.find("-->", index)
            if end < 0:
                raise PublicationError("Commentaire HTML non fermé")
            index = end + 3
            in_comment = False
            continue

        if text.startswith("<!--", index):
            in_comment = True
            index += 4
            continue

        if text.startswith("[[", index):
            link_depth += 1
            index += 2
            continue

        if text.startswith("]]", index) and link_depth:
            link_depth -= 1
            index += 2
            continue

        if text.startswith("{{", index):
            template_depth += 1
            index += 2
            continue

        if text.startswith("}}", index):
            if template_depth == 1:
                return index

            if template_depth > 1:
                template_depth -= 1
                index += 2
                continue

            raise PublicationError(
                "Fermeture de modèle inattendue"
            )

        index += 1

    raise PublicationError("Modèle principal non fermé")


def extract_parameter(text: str, parameter: str) -> str:
    matches = [
        span
        for span in _main_template_parameter_spans(text)
        if span.name == parameter
    ]

    if len(matches) != 1:
        raise PublicationError(
            f"Le paramètre |{parameter}= doit apparaître exactement "
            f"une fois ; trouvé : {len(matches)}"
        )

    span = matches[0]

    return text[
        span.value_start:span.value_end
    ].rstrip(" \t\r\n")


def replace_parameter(
    text: str,
    parameter: str,
    value: str,
    *,
    insert_if_missing: bool = False,
) -> str:
    matches = [
        span
        for span in _main_template_parameter_spans(text)
        if span.name == parameter
    ]

    if len(matches) == 0 and insert_if_missing:
        close = _main_template_close_index(text)
        clean = value.rstrip(" \t\r\n")

        if close > 0 and text[close - 1] in "\r\n":
            insertion = f"|{parameter}={clean}\n"
        else:
            insertion = f"\n|{parameter}={clean}\n"

        return text[:close] + insertion + text[close:]

    if len(matches) != 1:
        raise PublicationError(
            f"Le paramètre |{parameter}= doit apparaître exactement "
            f"une fois ; trouvé : {len(matches)}"
        )

    span = matches[0]
    old_value = text[span.value_start:span.value_end]
    suffix = old_value[
        len(old_value.rstrip(" \t\r\n")):
    ]
    clean = value.rstrip(" \t\r\n")

    return (
        text[:span.value_start]
        + clean
        + suffix
        + text[span.value_end:]
    )

@dataclass
class PageAction:
    operation_id: str
    kind: str
    language: str
    page_id: str
    page_type: str
    title: str
    source_path: str
    parameter: str | None
    local_file_sha256: str
    local_target_sha256: str
    remote_revision_id: int | None
    remote_sha256: str | None
    remote_target_sha256: str | None
    desired_sha256: str | None
    classification: str
    operation: str
    publication_creation_date: str | None = None
    edit_summary: str = ""
    change_tags: list[str] | None = None
    note: str | None = None


class Adapter(Protocol):
    def open_language(self, language: str, expected_user: str) -> None: ...
    def close_language(self) -> None: ...
    def assert_identity(self, expected_user: str) -> None: ...
    def available_change_tags(self) -> set[str]: ...
    def read_page(self, title: str) -> tuple[bool, int | None, str]: ...
    def read_revision(self, title: str, revision_id: int) -> dict[str, Any] | None: ...
    def write_page(
        self,
        *,
        title: str,
        text: str,
        summary: str,
        tags: list[str],
        expected_user: str,
        create_only: bool,
        base_revision_id: int | None,
    ) -> int: ...


class PywikibotAdapter:
    def __init__(
        self,
        family: str,
        codes: dict[str, str],
        pywikibot_dir: str | Path,
        family_file: str | Path | None = None,
    ) -> None:
        self.family = family
        self.codes = codes
        self.pywikibot_dir = Path(pywikibot_dir).expanduser().resolve()
        self.family_file = (
            Path(family_file).expanduser().resolve()
            if family_file
            else (DEFAULT_FAMILY_DIR / f"{family}_family.py").resolve()
        )
        self.site: Any | None = None

    def _prepare_environment(self) -> None:
        if not self.pywikibot_dir.is_dir():
            raise PublicationError(f"Dossier Pywikibot introuvable : {self.pywikibot_dir}")
        if not (self.pywikibot_dir / "user-config.py").is_file():
            raise PublicationError(f"user-config.py absent dans : {self.pywikibot_dir}")
        os.environ["PYWIKIBOT_DIR"] = str(self.pywikibot_dir)

    def _register_family(self, pywikibot: Any) -> None:
        family_files = getattr(getattr(pywikibot, "config", None), "family_files", None)
        if family_files is None:
            raise PublicationError("Configuration des familles Pywikibot indisponible")
        if self.family not in family_files:
            if not self.family_file.is_file():
                raise PublicationError(f"Fichier de famille introuvable : {self.family_file}")
            family_files[self.family] = str(self.family_file)

    def open_language(self, language: str, expected_user: str) -> None:
        self._prepare_environment()
        import pywikibot
        access_token = os.environ.get("WIKIDEBIA_API_TOKEN")
        if access_token:
            pywikibot.config.extra_headers["x-wikidebia-access"] = access_token
        self._register_family(pywikibot)
        self.site = pywikibot.Site(code=self.codes[language], fam=self.family)
        if self.site.user() is not None:
            self.site.logout()
        self.site.login()
        self.assert_identity(expected_user)

    def close_language(self) -> None:
        try:
            if self.site is not None and self.site.user() is not None:
                self.site.logout()
        finally:
            self.site = None

    def assert_identity(self, expected_user: str) -> None:
        actual = None if self.site is None else self.site.user()
        if actual != expected_user:
            raise IdentityError(f"Compte actif inattendu : {actual!r}")

    def available_change_tags(self) -> set[str]:
        if self.site is None:
            raise PublicationError("Site non ouvert")
        tags: set[str] = set()
        continuation: dict[str, Any] = {}
        while True:
            data = self.site.simple_request(
                action="query",
                list="tags",
                tglimit="max",
                tgprop="active|defined",
                **continuation,
            ).submit()
            for row in ((data.get("query") or {}).get("tags") or []):
                if row.get("name") and ("active" in row or row.get("active") is True):
                    tags.add(str(row["name"]))
            if not data.get("continue"):
                break
            continuation = data["continue"]
        return tags

    def read_page(self, title: str) -> tuple[bool, int | None, str]:
        if self.site is None:
            raise PublicationError("Site non ouvert")
        import pywikibot
        page = pywikibot.Page(self.site, title)
        if not page.exists():
            return False, None, ""
        return True, int(page.latest_revision_id), page.text

    def read_revision(self, title: str, revision_id: int) -> dict[str, Any] | None:
        if self.site is None:
            raise PublicationError("Site non ouvert")
        data = self.site.simple_request(
            action="query",
            prop="revisions",
            revids=int(revision_id),
            rvprop="ids|content|comment|tags|user",
            rvslots="main",
        ).submit()
        for page in ((data.get("query") or {}).get("pages") or {}).values():
            revisions = page.get("revisions") or []
            if not revisions:
                continue
            revision = revisions[0]
            slot = (revision.get("slots") or {}).get("main") or {}
            return {
                "revision_id": int(revision.get("revid", revision_id)),
                "parent_id": int(revision.get("parentid", 0) or 0),
                "user": str(revision.get("user") or ""),
                "text": slot.get("content", slot.get("*", revision.get("*", ""))),
                "summary": revision.get("comment", "") or "",
                "tags": list(revision.get("tags") or []),
            }
        return None

    def write_page(
        self,
        *,
        title: str,
        text: str,
        summary: str,
        tags: list[str],
        expected_user: str,
        create_only: bool,
        base_revision_id: int | None,
    ) -> int:
        if self.site is None:
            raise PublicationError("Site non ouvert")
        self.assert_identity(expected_user)
        parameters: dict[str, Any] = {
            "action": "edit",
            "title": title,
            "text": text,
            "summary": summary,
            "bot": 1,
            "assert": "user",
            "assertuser": expected_user,
            "md5": hashlib.md5(text.encode("utf-8")).hexdigest(),
        }
        if tags:
            parameters["tags"] = "|".join(tags)
        if create_only:
            parameters["createonly"] = 1
        else:
            if base_revision_id is None:
                raise RevisionConflict("baserevid absent pour une modification")
            parameters["baserevid"] = int(base_revision_id)
            parameters["nocreate"] = 1
        parameters["token"] = self.site.tokens["csrf"]
        data = self.site.simple_request(**parameters).submit()
        return int(data["edit"]["newrevid"])


class GenericPublisher:
    def __init__(self, config: dict[str, Any], adapter: Adapter, config_path: Path) -> None:
        self.config = config
        self.adapter = adapter
        self.config_path = config_path.resolve()
        self.project_root = Path(config.get("project_root") or Path.cwd()).expanduser().resolve()
        self.root = self._resolve(config["corpus_root"])
        self.manifest_path = self.root / str(config.get("manifest_file", "manifest.json"))
        if not self.manifest_path.is_file():
            raise PublicationError(f"Manifest introuvable : {self.manifest_path}")
        self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.operation = dict(config["operation"])
        self.publication_profile = str(config.get("publication_profile") or LEGACY_PROFILE)
        self.languages = tuple(self.operation.get("languages") or config.get("languages") or ())
        self.tags = list(config.get("change_tags") or ["chatgpt"])
        self.translation_tag = str(config.get("translation_change_tag") or "translated-fr")
        self.publication_timezone = str(config.get("publication_timezone") or "Europe/Paris")
        try:
            ZoneInfo(self.publication_timezone)
        except ZoneInfoNotFoundError as exc:
            raise PublicationError(f"Fuseau horaire de publication inconnu : {self.publication_timezone}") from exc
        self.publication_date = self._current_publication_date()
        logs_dir = self._resolve(config["logs_dir"])
        operation_id = str(self.operation.get("id") or self.operation.get("kind") or "publication")
        self.log_path = logs_dir / f"{operation_id}.jsonl"
        self._tag_cache: dict[str, set[str]] = {}
        self._registry_cache: dict[str, Any] | None | bool = False
        self._validate_configuration()

    def _resolve(self, value: str | Path) -> Path:
        path = Path(value).expanduser()
        return path.resolve() if path.is_absolute() else (self.project_root / path).resolve()

    def _english_translation_status(self) -> str:
        return str(((self.manifest.get("translation_status") or {}).get("en") or "pending"))

    def _english_translation_deferred(self) -> bool:
        return self._english_translation_status() == "deferred"

    def _current_publication_date(self) -> str:
        return dt.datetime.now(ZoneInfo(self.publication_timezone)).date().isoformat()

    def _is_new_english_translation_page(self, row: dict[str, Any]) -> bool:
        return (
            str(row.get("language") or "") == "en"
            and str(row.get("page_origin") or "new") == "new"
            and self.operation.get("kind") == "full_page"
            and self._english_translation_status() in {"ready", "published"}
        )

    def _english_translation_creation_text(
        self,
        row: dict[str, Any],
        text: str,
        publication_date: str,
    ) -> str:
        """Apply publication-time metadata to a newly translated English page."""
        if not self._is_new_english_translation_page(row):
            return text
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", publication_date):
            raise PublicationError(f"Date de publication invalide : {publication_date!r}")
        names = [span.name for span in _main_template_parameter_spans(text)]
        if str(row.get("page_type") or "") == "argument" and "initialization" in names:
            raise PublicationError(
                "Une nouvelle traduction anglaise d’Argument ne doit pas contenir |initialization= : "
                + str(row.get("page_id") or "")
            )
        if names.count("creation-date") != 1:
            raise PublicationError(
                "Une nouvelle traduction anglaise doit contenir exactement un |creation-date= avant publication : "
                + str(row.get("page_id") or "")
            )
        return replace_parameter(text, "creation-date", publication_date)

    def _verified_existing_translation_creation(
        self,
        *,
        row: dict[str, Any],
        title: str,
        revision_id: int,
        remote_text: str,
        summary: str,
        tags: list[str],
    ) -> bool:
        if not self._is_new_english_translation_page(row):
            return True
        observed = self.adapter.read_revision(title, revision_id)
        if not observed:
            return False
        expected_user = self._site("en")[1]
        return (
            int(observed.get("parent_id", -1)) == 0
            and str(observed.get("user") or "") == expected_user
            and sha_text(str(observed.get("text", ""))) == sha_text(remote_text)
            and str(observed.get("summary") or "") == summary
            and all(tag in (observed.get("tags") or []) for tag in tags)
        )

    def _validate_configuration(self) -> None:
        # kit_version is producer provenance only. Compatibility is governed by
        # the schemas/capabilities consumed below. Historical config value "2"
        # therefore remains readable without a release-number gate.
        if self.manifest.get("debate_id") != self.config.get("debate_id"):
            raise PublicationError("debate_id divergent entre la configuration et le manifeste")
        validator = self.config.get("validator") or {}
        # required_version is retained as provenance for historical configs;
        # the executed validator is accepted by report schema/capability.
        if self.publication_profile in DIRECT_PROFILES:
            scopes = {str(value) for value in (validator.get("scopes") or [])}
            missing_scopes = sorted(REQUIRED_DIRECT_SCOPES - scopes)
            if missing_scopes:
                raise PublicationError(
                    "Portées obligatoires du validateur absentes : " + ", ".join(missing_scopes)
                )
        if self.tags != ["chatgpt"]:
            raise PublicationError("La balise obligatoire doit être exactement : chatgpt")
        if not self.languages:
            raise PublicationError("Aucune langue sélectionnée")
        if self._english_translation_deferred() and "en" in self.languages:
            raise PublicationError("La portée anglaise est interdite tant que translation_status.en vaut deferred")
        sites = self.config.get("sites") or {}
        summaries = self.operation.get("edit_summaries") or {}
        for language in self.languages:
            site = sites.get(language) or {}
            if not str(site.get("code") or "").strip():
                raise PublicationError(f"Code de site absent pour {language}")
            if not str(site.get("expected_user") or "").strip():
                raise PublicationError(f"expected_user absent pour {language}")
            if not str(summaries.get(language) or "").strip():
                raise PublicationError(f"Résumé de modification absent pour {language}")
        if self.publication_profile not in {*DIRECT_PROFILES, LEGACY_PROFILE}:
            raise PublicationError(
                "publication_profile doit être norm_1_2_direct_interlanguage, norm_1_2_deferred_translation ou legacy"
            )
        kind = self.operation.get("kind")
        if kind not in {"full_page", "parameter_update"}:
            raise PublicationError("operation.kind doit être full_page ou parameter_update")
        if kind == "full_page":
            configured_order = list(self.operation.get("page_type_order") or [])
            if "debate" in configured_order and "argument" in configured_order:
                if configured_order.index("debate") > configured_order.index("argument"):
                    raise PublicationError(
                        "page_type_order doit placer debate avant argument dans chaque langue"
                    )
        if kind == "parameter_update":
            parameters = self.operation.get("parameters") or {}
            for language in self.languages:
                if not str(parameters.get(language) or "").strip():
                    raise PublicationError(f"Paramètre cible absent pour {language}")
            if self.operation.get("create_missing") is True:
                raise PublicationError("parameter_update ne peut pas créer une page absente")
            if (
                self.publication_profile in DIRECT_PROFILES
                and any(str(parameters.get(language) or "") == "interlangue" for language in self.languages)
            ):
                if self._english_translation_deferred():
                    raise PublicationError(
                        "La mise à jour séparée de |interlangue= n'est autorisée qu'après sortie du mode deferred."
                    )
        requirements = self.config.get("manifest_requirements") or {}
        for field, expected in requirements.items():
            actual = dotted_get(self.manifest, field)
            if actual != expected:
                raise PublicationError(
                    f"Exigence de manifeste divergente pour {field} : {actual!r} au lieu de {expected!r}"
                )

    def _prepare_logging(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        probe = self.log_path.parent / ".wikidebia_write_probe"
        try:
            probe.write_text("ok\n", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            raise PublicationError(f"Répertoire de journaux inaccessible : {exc}") from exc

    def _log(self, event: dict[str, Any]) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    def _site(self, language: str) -> tuple[str, str]:
        site = self.config["sites"][language]
        return str(site["code"]), str(site["expected_user"])

    def _summary(self, language: str) -> str:
        return str(self.operation["edit_summaries"][language])

    def _french_source_title(self, page_id: str, page_type: str) -> str:
        matches = [
            row for row in (self.manifest.get("pages") or [])
            if str(row.get("language")) == "fr"
            and str(row.get("page_id")) == page_id
            and str(row.get("page_type") or "") == page_type
        ]
        if len(matches) != 1:
            raise PublicationError(
                f"Impossible de résoudre la page française source pour {page_type} {page_id}"
            )
        title = str(matches[0].get("canonical_title") or "").strip()
        if not title:
            raise PublicationError(
                f"Titre français source absent pour {page_type} {page_id}"
            )
        return title

    def _summary_for_page(self, language: str, page_id: str, page_type: str) -> str:
        # A translated English page receives a page-specific cross-wiki source link.
        # The source title comes from the locked French page manifest with the same
        # logical page id; it is never inferred from the English title.
        if (
            language == "en"
            and self.operation.get("kind") == "full_page"
            and self._english_translation_status() in {"ready", "published"}
        ):
            source_title = self._french_source_title(page_id, page_type)
            return f"Translation of the French page: [[:fr:{source_title}|{source_title}]]"
        return self._summary(language)

    def _summary_for_action(self, action: dict[str, Any]) -> str:
        expected = self._summary_for_page(
            str(action.get("language") or ""),
            str(action.get("page_id") or ""),
            str(action.get("page_type") or ""),
        )
        planned = str(action.get("edit_summary") or "")
        if planned != expected:
            raise PublicationError(
                f"Résumé individualisé divergent dans le plan : {action.get('page_id')}"
            )
        return planned

    def _tags_for_page(self, language: str, page_id: str, page_type: str) -> list[str]:
        tags = list(self.tags)
        if (
            language == "en"
            and self.operation.get("kind") == "full_page"
            and self._english_translation_status() in {"ready", "published"}
            and self.translation_tag not in tags
        ):
            tags.append(self.translation_tag)
        return tags

    def _tags_for_action(self, action: dict[str, Any]) -> list[str]:
        expected = self._tags_for_page(
            str(action.get("language") or ""),
            str(action.get("page_id") or ""),
            str(action.get("page_type") or ""),
        )
        planned = list(action.get("change_tags") or [])
        if planned != expected:
            raise PublicationError(
                f"Balises individualisées divergentes dans le plan : {action.get('page_id')}"
            )
        return planned

    def _required_tags_for_language(self, language: str) -> list[str]:
        tags = list(self.tags)
        if (
            language == "en"
            and self.operation.get("kind") == "full_page"
            and self._english_translation_status() in {"ready", "published"}
            and self.translation_tag not in tags
        ):
            tags.append(self.translation_tag)
        return tags

    def _parameter(self, language: str) -> str | None:
        if self.operation["kind"] != "parameter_update":
            return None
        return str(self.operation["parameters"][language])

    def _change_tag_gate(self, language: str, required_tags: list[str] | None = None) -> None:
        if language not in self._tag_cache:
            self._tag_cache[language] = self.adapter.available_change_tags()
        tags = required_tags or self._required_tags_for_language(language)
        missing = [tag for tag in tags if tag not in self._tag_cache[language]]
        if missing:
            raise PublicationError(
                f"Balise(s) inactive(s) sur {language} : {', '.join(missing)}"
            )

    def _selected_pages(self) -> list[dict[str, Any]]:
        page_types = set(self.operation.get("page_types") or [])
        excluded = set(self.operation.get("exclude_page_types") or [])
        selected = []
        for row in self.manifest.get("pages", []):
            if row.get("language") not in self.languages:
                continue
            if page_types and row.get("page_type") not in page_types:
                continue
            if row.get("page_type") in excluded:
                continue
            selected.append(row)
        if not selected:
            raise PublicationError("Aucune page du manifeste ne correspond à l'opération")
        identities = [(row.get("language"), row.get("page_id")) for row in selected]
        if len(identities) != len(set(identities)):
            raise PublicationError("Identifiants de pages dupliqués dans la sélection")
        language_order = {
            value: index
            for index, value in enumerate(self.operation.get("language_order") or self.languages)
        }
        configured_type_order = list(self.operation.get("page_type_order") or [])
        if self.operation.get("kind") == "full_page":
            # Invariant de publication : la page Débat/Debate précède toujours
            # toutes les pages Argument de la même langue.
            type_order = {"debate": 0, "argument": 1}
        else:
            type_order = {value: index for index, value in enumerate(configured_type_order)}
        selected.sort(
            key=lambda row: (
                language_order.get(row.get("language"), 9999),
                type_order.get(row.get("page_type"), 9999),
                str(row.get("page_id", "")),
                str(row.get("canonical_title", "")),
            )
        )
        expected = self.operation.get("expected_counts") or {}
        if expected:
            for language, count in expected.items():
                actual = sum(1 for row in selected if row.get("language") == language)
                if actual != int(count):
                    raise PublicationError(
                        f"Nombre de pages {language} inattendu : {actual} au lieu de {count}"
                    )
        return selected

    def _source_path(self, row: dict[str, Any]) -> Path:
        template = self.operation.get("source_path_template")
        if template:
            relative = str(template).format(**row)
        else:
            field = str(self.operation.get("source_path_field") or "file_path")
            relative = row.get(field)
            if not relative:
                raise PublicationError(
                    f"Chemin source absent pour {row.get('language')}/{row.get('page_id')}"
                )
        return self.root / str(relative)

    def _remote_title(self, row: dict[str, Any]) -> str:
        overrides = self.operation.get("remote_title_overrides") or self.config.get("remote_title_overrides") or {}
        by_language = overrides.get(row["language"], {})
        return str(by_language.get(row["page_id"], row["canonical_title"]))

    def _manifest_page(self, language: str, page_id: str) -> dict[str, Any] | None:
        for row in self.manifest.get("pages", []):
            if row.get("language") == language and str(row.get("page_id")) == page_id:
                return row
        return None

    def _registry(self) -> dict[str, Any] | None:
        """Charge le registre maître une seule fois, s'il est déclaré par le manifeste."""
        if self._registry_cache is not False:
            return self._registry_cache if isinstance(self._registry_cache, dict) else None
        relative = str(((self.manifest.get("core_files") or {}).get("registry")) or "").strip()
        if not relative:
            self._registry_cache = None
            return None
        path = self.root / relative
        if not path.is_file():
            raise PublicationError(f"Registre maître introuvable : {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PublicationError(f"Registre maître illisible : {path}") from exc
        if not isinstance(data, dict):
            raise PublicationError(f"Registre maître invalide : {path}")
        self._registry_cache = data
        return data

    def _locked_english_title(self, page_id: str, page_type: str) -> str:
        """Résout une cible anglaise verrouillée et cohérente avec le manifeste."""
        registry = self._registry()
        record: dict[str, Any] | None = None
        if registry is not None and page_type == "debate":
            debate = registry.get("debate") or {}
            if str(debate.get("id") or "") in {"", page_id, str(self.manifest.get("debate_id") or "")}:
                candidate = ((debate.get("pages") or {}).get("en") or {})
                if isinstance(candidate, dict):
                    record = candidate
        elif registry is not None and page_type == "argument":
            for node in ((registry.get("graph") or {}).get("nodes") or []):
                if isinstance(node, dict) and str(node.get("id") or "") == page_id:
                    candidate = node.get("en") or {}
                    if isinstance(candidate, dict):
                        record = candidate
                    break
        if record is None:
            english = self._manifest_page("en", page_id)
            manifest_title = str((english or {}).get("canonical_title") or "").strip()
            if english is not None and manifest_title and not self._english_translation_deferred():
                return manifest_title
            raise PublicationError(f"Entrée anglaise introuvable dans le registre maître : {page_id}")
        status = str(record.get("title_status") or "").strip()
        title = str(record.get("canonical_title") or "").strip()
        if status != "locked" or not title:
            raise PublicationError(f"Titre canonique anglais non verrouillé dans le registre maître : {page_id}")
        english = self._manifest_page("en", page_id)
        if english is not None:
            manifest_title = str(english.get("canonical_title") or "").strip()
            if not manifest_title or manifest_title != title:
                raise PublicationError(f"Titre anglais du manifeste divergent du registre maître : {page_id}")
        return title

    def _uses_renamed_template_parameters(self) -> bool:
        value = str(((self.manifest.get("normative_versions") or {}).get("consolidated_norm") or "")).strip()
        match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value)
        if not match:
            return True
        return tuple(map(int, match.groups())) >= (1, 2, 69)

    def _validate_norm_120_page(self, row: dict[str, Any], text: str) -> None:
        language = str(row.get("language") or "")
        page_id = str(row.get("page_id") or "")
        page_type = str(row.get("page_type") or "")
        if SPLIT_ADJACENT_TEMPLATES_RE.search(text):
            raise PublicationError(
                "Deux modèles MediaWiki adjacents doivent être accolés sous la forme }}{{ : " + f"{language}/{page_id}"
            )
        if re.search(r"<\s*references\b", text, flags=re.IGNORECASE):
            raise PublicationError(
                f"Balise <references /> interdite par les règles éditoriales actives : {language}/{page_id}"
            )
        names = [span.name for span in _main_template_parameter_spans(text)]
        json_author = re.search(r"(?m)^\s*\|\s*(?:auteurs|authors)\s*=\s*\[", text)
        if json_author:
            raise PublicationError(
                f"Un champ auteurs/authors contient un tableau JSON au lieu de texte MediaWiki : {language}/{page_id}"
            )
        for match in re.finditer(r"(?m)^\s*\|\s*(?:auteurs|authors)\s*=\s*(.*?)\s*$", text):
            author_value = match.group(1).strip()
            malformed_separator = (
                ";" in author_value
                or "，" in author_value
                or bool(re.search(r"\s+,|,(?! )|, {2,}|,$", author_value))
            )
            if malformed_separator:
                raise PublicationError(
                    "Plusieurs auteurs doivent être séparés exactement par une virgule suivie d’une espace : "
                    f"{language}/{page_id}"
                )
        section_param = "rubriques" if language == "fr" else "sections"
        if section_param in names:
            actual_sections = [item.strip() for item in extract_parameter(text, section_param).split(",") if item.strip()]
            expected_sections = alphabetical_values(extract_parameter(text, section_param))
            if actual_sections != expected_sections:
                raise PublicationError(
                    f"{section_param} doit être rangé par ordre alphabétique : {language}/{page_id}"
                )
        if language == "en":
            if "interlangue" in names:
                raise PublicationError(f"Lien interlangue interdit en anglais : {page_id}")
            if self._is_new_english_translation_page(row):
                if page_type == "argument" and "initialization" in names:
                    raise PublicationError(
                        f"Une nouvelle traduction anglaise d’Argument ne doit pas contenir |initialization= : {page_id}"
                    )
                if names.count("creation-date") != 1:
                    raise PublicationError(
                        f"Une nouvelle traduction anglaise doit contenir exactement un |creation-date= : {page_id}"
                    )
            if page_type == "debate":
                if "type" in names:
                    raise PublicationError("Le paramètre anglais |type= est interdit par les règles éditoriales actives")
                if "expanded-topic" in names and "complete-topic" not in names:
                    expanded_parameter = "expanded-topic"
                else:
                    expanded_parameter = "expanded-topic" if self._uses_renamed_template_parameters() else "complete-topic"
                if names.count("topic") != 1 or names.count(expanded_parameter) != 1:
                    raise PublicationError(
                        f"La page Debate anglaise doit contenir exactement |topic= et |{expanded_parameter}="
                    )
        if page_type == "debate":
            wikipedia_parameter = "articles-Wikipédia" if language == "fr" else "wikipedia-articles"
            wikipedia_model = "Article Wikipédia" if language == "fr" else "Wikipedia article"
            related_parameter = "débats-connexes" if language == "fr" else "related-debates"
            if names.count(wikipedia_parameter) != 1:
                raise PublicationError(
                    f"La page de débat doit contenir exactement un |{wikipedia_parameter}= non vide : {language}/{page_id}"
                )
            wikipedia_value = extract_parameter(text, wikipedia_parameter)
            article_pattern = rf"\{{\{{\s*{re.escape(wikipedia_model)}\b(?:(?!\}}\}}).)*\|\s*page\s*=\s*[^|{{}}\r\n]+(?:(?!\}}\}}).)*\}}\}}"
            if not wikipedia_value.strip() or not re.search(article_pattern, wikipedia_value, flags=re.IGNORECASE | re.DOTALL):
                raise PublicationError(
                    f"|{wikipedia_parameter}= doit contenir au moins un sous-modèle {wikipedia_model} avec un titre vérifié : {language}/{page_id}"
                )
            old_related = (row.get("preserved_parameters") or {}).get(related_parameter) or {}
            historical_french_related = (
                language == "fr" and row.get("page_origin") == "preexisting"
                and old_related.get("present") is True
                and old_related.get("value") == extract_parameter(text, related_parameter)
            )
            if related_parameter in names and not historical_french_related:
                raise PublicationError(
                    f"Le paramètre |{related_parameter}= ne doit pas être publié : {language}/{page_id}"
                )
            topic_param = "sujet" if language == "fr" else "topic"
            current_complete = "sujet-développé" if language == "fr" else "expanded-topic"
            legacy_complete = "sujet-complet" if language == "fr" else "complete-topic"
            if current_complete in names and legacy_complete not in names:
                complete_param = current_complete
            else:
                complete_param = current_complete if self._uses_renamed_template_parameters() else legacy_complete
            topic_value = extract_parameter(text, topic_param) if topic_param in names else ""
            complete_value = extract_parameter(text, complete_param) if complete_param in names else ""
            if not _first_alpha_is_upper(topic_value):
                raise PublicationError(f"{topic_param} doit commencer par une majuscule : {language}/{page_id}")
            if _complete_topic_is_interrogative(complete_value, language):
                raise PublicationError(
                    f"{complete_param} doit compléter l’en-tête sous une forme non interrogative : {language}/{page_id}"
                )
        if language == "en":
            return
        if language != "fr":
            return
        prose = ""
        if page_type == "argument" and "résumé" in names:
            prose = extract_parameter(text, "résumé")
        elif page_type == "debate" and "introduction" in names:
            prose = extract_parameter(text, "introduction")
        prose_without_refs = re.sub(r"<ref\b[^>]*>.*?</ref>", "", prose, flags=re.IGNORECASE | re.DOTALL)
        if PAIRED_EM_DASH_RE.search(prose_without_refs):
            raise PublicationError(
                f"Incise française entre tirets cadratins interdite; utiliser des parenthèses : {page_id}"
            )
        interlanguage_count = names.count("interlangue")
        if self._english_translation_deferred():
            if interlanguage_count == 0:
                return
            if interlanguage_count != 1:
                raise PublicationError(f"La page française ne peut contenir qu'un seul |interlangue= : {page_id}")
        elif interlanguage_count != 1:
            raise PublicationError(f"La page française doit contenir exactement un |interlangue= : {page_id}")
        value = extract_parameter(text, "interlangue")
        if not value.strip():
            raise PublicationError(f"Le paramètre |interlangue= ne peut pas être vide : {page_id}")
        if not re.search(r"\{\{\s*Lien interlangue\b", value):
            raise PublicationError(f"Le lien français doit utiliser {{{{Lien interlangue}}}} : {page_id}")
        target = self._locked_english_title(page_id, page_type)
        target_value = extract_parameter(value, "page")
        language_value = extract_parameter(value, "langue")
        if language_value.strip() != "en" or target_value.strip() != target:
            raise PublicationError(f"Cible interlangue divergente pour {page_id} : {target_value!r} au lieu de {target!r}")


    def _validate_local_files(self) -> None:
        parameter_kind = self.operation["kind"] == "parameter_update"
        for row in self._selected_pages():
            if self.operation["kind"] == "full_page":
                title_issues = canonical_title_structure_issues(str(row.get("canonical_title") or ""))
                if title_issues:
                    raise PublicationError(
                        f"Titre canonique à revoir : {row['language']}/{row['page_id']} ({', '.join(title_issues)})"
                    )
            path = self._source_path(row)
            if not path.is_file():
                raise PublicationError(f"Fichier local absent : {path}")
            declared = row.get("sha256")
            if declared and sha_file(path) != declared and not self.operation.get("allow_source_sha_mismatch", False):
                raise PublicationError(f"Empreinte locale divergente : {path}")
            text = path.read_text(encoding="utf-8")
            if self.publication_profile in DIRECT_PROFILES:
                self._validate_norm_120_page(row, text)
            if parameter_kind:
                value = extract_parameter(text, str(self._parameter(row["language"])))
                if not value.strip():
                    raise PublicationError(
                        f"Paramètre local vide : {row['language']}/{row['page_id']}"
                    )

    def _validator_command(self) -> list[str]:
        validator = self.config["validator"]
        command = [str(item) for item in validator["command"]]
        if not command:
            raise PublicationError("Commande du validateur vide")
        scopes = list(validator.get("scopes") or [])
        if "validate" in command:
            index = command.index("validate")
            command = command[: index + 1] + [str(self.root)] + command[index + 1 :]
        else:
            command.append(str(self.root))
        for scope in scopes:
            command.extend(["--scope", str(scope)])
        command.extend(["--format", "json"])
        return command

    def _validate_structural_scopes(self) -> dict[str, Any]:
        validator = self.config["validator"]
        result = subprocess.run(
            self._validator_command(),
            cwd=self.project_root,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise PublicationError("Validation structurelle refusée :\n" + result.stdout + result.stderr)
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise PublicationError("Sortie JSON du validateur illisible") from exc
        require_validator_report(report, PublicationError)
        summary = report.get("summary") or {}
        errors = int(summary.get("errors", 0))
        warnings = int(summary.get("warnings", 0))
        if report.get("result") != "passed" or errors != 0:
            raise PublicationError("Validation structurelle non positive")
        max_warnings = int(validator.get("max_warnings", 0))
        if warnings > max_warnings:
            raise PublicationError(
                f"Trop d'avertissements du validateur : {warnings} > {max_warnings}"
            )
        for field, expected in (validator.get("expected_metrics") or {}).items():
            actual = dotted_get(report, field)
            if actual != expected:
                raise PublicationError(
                    f"Métrique divergente pour {field} : {actual!r} au lieu de {expected!r}"
                )
        return report

    def _validate_local(self) -> dict[str, Any]:
        self._validate_local_files()
        return self._validate_structural_scopes()

    def _package_fingerprints(self) -> dict[str, str]:
        validator_path = self._resolve(self.config["validator"]["fingerprint_path"])
        selected = []
        for row in self._selected_pages():
            path = self._source_path(row)
            selected.append(
                {
                    "language": row["language"],
                    "page_id": row["page_id"],
                    "page_type": row.get("page_type"),
                    "source_path": str(path.relative_to(self.root)),
                    "sha256": sha_file(path),
                }
            )
        return {
            "manifest_sha256": sha_file(self.manifest_path),
            "selected_sources_fingerprint": sha_object(selected),
            "validator_fingerprint": sha_tree(validator_path),
            "kit_script_sha256": sha_file(Path(__file__).resolve()),
            "publication_date_rules_sha256": sha_file(Path(__file__).with_name("wikidebia_publication_dates.py")),
            "title_structure_rules_sha256": sha_file(Path(__file__).with_name("wikidebia_title_structure.py")),
            "config_sha256": sha_file(self.config_path),
        }

    def inspect(self) -> dict[str, Any]:
        report = self._validate_local()
        counts: dict[str, dict[str, int]] = {}
        for row in self._selected_pages():
            language = str(row["language"])
            page_type = str(row.get("page_type") or "unknown")
            language_counts = counts.setdefault(language, {})
            language_counts[page_type] = language_counts.get(page_type, 0) + 1
        return {
            "kit_version": KIT_VERSION,
            "debate_id": self.config["debate_id"],
            "operation": self.operation["id"],
            "kind": self.operation["kind"],
            "validator_version": recursive_find_version(report),
            "counts": counts,
        }

    def build_plan(self) -> dict[str, Any]:
        report = self._validate_local()
        actions: list[dict[str, Any]] = []
        blockers: list[dict[str, Any]] = []
        selected = self._selected_pages()
        for language in self.languages:
            rows = [row for row in selected if row["language"] == language]
            if not rows:
                continue
            _, user = self._site(language)
            self.adapter.open_language(language, user)
            try:
                self.adapter.assert_identity(user)
                self._change_tag_gate(language)
                for row in rows:
                    action = self._plan_row(row)
                    action_dict = asdict(action)
                    actions.append(action_dict)
                    if action.operation == "block":
                        blockers.append(
                            {
                                "language": action.language,
                                "page_id": action.page_id,
                                "page_type": action.page_type,
                                "title": action.title,
                                "classification": action.classification,
                                "note": action.note,
                            }
                        )
            finally:
                self.adapter.close_language()
        counts: dict[str, dict[str, int]] = {}
        for language in self.languages:
            language_actions = [item for item in actions if item["language"] == language]
            counts[language] = {
                operation: sum(1 for item in language_actions if item["operation"] == operation)
                for operation in ("create", "update", "skip", "block")
            }
            counts[language]["total"] = len(language_actions)
        plan: dict[str, Any] = {
            "schema": PUBLICATION_PLAN_SCHEMA,
            "schema_version": PUBLICATION_PLAN_SCHEMA_VERSION,
            "plan_version": PUBLICATION_PLAN_VERSION,
            "publication_profile": self.publication_profile,
            "kit_version": KIT_VERSION,
            "debate_id": self.config["debate_id"],
            "operation_id": self.operation["id"],
            "operation_kind": self.operation["kind"],
            "required_validator_version": REQUIRED_VALIDATOR_VERSION,
            "validator_report_sha256": sha_object(report),
            "package_fingerprints": self._package_fingerprints(),
            "change_tags": self.tags,
            "translation_change_tag": self.translation_tag,
            "publication_timezone": self.publication_timezone,
            "publication_date": self.publication_date,
            "edit_summaries": self.operation["edit_summaries"],
            "actions": actions,
            "blockers": blockers,
            "counts": counts,
        }
        plan["plan_sha256"] = sha_object(plan)
        return plan

    def _plan_row(self, row: dict[str, Any]) -> PageAction:
        language = str(row["language"])
        page_id = str(row["page_id"])
        page_type = str(row.get("page_type") or "unknown")
        source_path = self._source_path(row)
        local_text = source_path.read_text(encoding="utf-8")
        parameter = self._parameter(language)
        local_target = local_text if parameter is None else extract_parameter(local_text, parameter)
        title = self._remote_title(row)
        exists, revision_id, remote_text = self.adapter.read_page(title)
        page_summary = self._summary_for_page(language, page_id, page_type)
        page_tags = self._tags_for_page(language, page_id, page_type)
        publication_creation_date: str | None = None
        common = dict(
            operation_id=str(self.operation["id"]),
            kind=str(self.operation["kind"]),
            language=language,
            page_id=page_id,
            page_type=page_type,
            title=title,
            source_path=str(source_path.relative_to(self.root)),
            parameter=parameter,
            local_file_sha256=sha_file(source_path),
            local_target_sha256=sha_text(local_target),
            edit_summary=page_summary,
            change_tags=page_tags,
        )
        if not exists:
            if self.operation["kind"] == "full_page" and self.operation.get("create_missing", True):
                desired_create_text = local_text
                if self._is_new_english_translation_page(row):
                    publication_creation_date = self.publication_date
                    desired_create_text = self._english_translation_creation_text(
                        row, local_text, publication_creation_date
                    )
                return PageAction(
                    **common,
                    publication_creation_date=publication_creation_date,
                    remote_revision_id=None,
                    remote_sha256=None,
                    remote_target_sha256=None,
                    desired_sha256=sha_text(desired_create_text),
                    classification="remote_absent",
                    operation="create",
                )
            return PageAction(
                **common,
                remote_revision_id=None,
                remote_sha256=None,
                remote_target_sha256=None,
                desired_sha256=None,
                classification="remote_absent",
                operation="block",
                note="La page distante est absente et l'opération ne l'autorise pas.",
            )
        if revision_id is None:
            raise PublicationError(f"Révision distante absente : {title}")
        try:
            if self.operation["kind"] == "full_page":
                remote_target = remote_text
                desired_text = local_text
                if self._is_new_english_translation_page(row):
                    if not self._verified_existing_translation_creation(
                        row=row,
                        title=title,
                        revision_id=revision_id,
                        remote_text=remote_text,
                        summary=page_summary,
                        tags=page_tags,
                    ):
                        return PageAction(
                            **common,
                            remote_revision_id=revision_id,
                            remote_sha256=sha_text(remote_text),
                            remote_target_sha256=sha_text(remote_text),
                            desired_sha256=None,
                            classification="unverified_existing_translation",
                            operation="block",
                            note="La page anglaise existe mais sa révision courante ne peut pas être prouvée comme création de traduction Wikidéb’IA.",
                        )
                    remote_date = extract_parameter(remote_text, "creation-date").strip()
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", remote_date):
                        return PageAction(
                            **common,
                            remote_revision_id=revision_id,
                            remote_sha256=sha_text(remote_text),
                            remote_target_sha256=sha_text(remote_text),
                            desired_sha256=None,
                            classification="invalid_existing_creation_date",
                            operation="block",
                            note="La page anglaise existante a une |creation-date= invalide.",
                        )
                    publication_creation_date = remote_date
                    desired_text = self._english_translation_creation_text(row, local_text, remote_date)
            else:
                assert parameter is not None
                insert_missing = bool(
                    self.operation.get("insert_missing_parameter", False)
                )

                matches = [
                    span
                    for span in _main_template_parameter_spans(remote_text)
                    if span.name == parameter
                ]

                if len(matches) == 0 and insert_missing:
                    remote_target = ""
                else:
                    remote_target = extract_parameter(
                        remote_text,
                        parameter,
                    )

                desired_text = replace_parameter(
                    remote_text,
                    parameter,
                    local_target,
                    insert_if_missing=insert_missing,
                )
        except PublicationError as exc:
            return PageAction(
                **common,
                remote_revision_id=revision_id,
                remote_sha256=sha_text(remote_text),
                remote_target_sha256=None,
                desired_sha256=None,
                classification="remote_content_invalid",
                operation="block",
                note=str(exc),
            )
        if normalize_wikicode(remote_text) == normalize_wikicode(desired_text):
            operation = "skip"
            classification = "already_equivalent"
        elif self.operation["kind"] == "parameter_update" or self.operation.get("update_existing", False):
            operation = "update"
            classification = "content_differs"
        else:
            operation = "block"
            classification = "existing_page_collision"
        note = None
        if operation == "block":
            note = "La page existe avec un contenu différent et update_existing=false."
        return PageAction(
            **common,
            publication_creation_date=publication_creation_date,
            remote_revision_id=revision_id,
            remote_sha256=sha_text(remote_text),
            remote_target_sha256=sha_text(remote_target),
            desired_sha256=sha_text(desired_text),
            classification=classification,
            operation=operation,
            note=note,
        )

    def _verify_plan(self, plan: dict[str, Any], confirmation: str, *, check_publication_date: bool = True) -> None:
        copy = dict(plan)
        claimed = copy.pop("plan_sha256", None)
        if not claimed or claimed != sha_object(copy) or confirmation != claimed:
            raise PublicationError("SHA-256 du plan divergent")
        if not publication_plan_is_compatible(plan):
            raise PublicationError("Schéma du plan de publication incompatible")
        if plan.get("publication_profile") != self.publication_profile:
            raise PublicationError("Profil de publication divergent dans le plan")
        if plan.get("debate_id") != self.config.get("debate_id"):
            raise PublicationError("Plan rattaché à un autre débat")
        if plan.get("operation_id") != self.operation.get("id"):
            raise PublicationError("Plan rattaché à une autre opération")
        if plan.get("package_fingerprints") != self._package_fingerprints():
            raise PublicationError("Corpus, configuration, validateur ou kit modifié depuis le plan")
        if plan.get("change_tags") != self.tags:
            raise PublicationError("Balises divergentes du plan")
        if plan.get("translation_change_tag") != self.translation_tag:
            raise PublicationError("Balise de traduction divergente du plan")
        if plan.get("publication_timezone") != self.publication_timezone:
            raise PublicationError("Fuseau horaire de publication divergent dans le plan")
        english_creates = [
            action for action in plan.get("actions", [])
            if action.get("language") == "en"
            and action.get("operation") == "create"
            and action.get("publication_creation_date")
        ]
        if english_creates:
            for action in english_creates:
                if action.get("publication_creation_date") != plan.get("publication_date"):
                    raise PublicationError(
                        f"Date de création anglaise divergente dans le plan : {action.get('page_id')}"
                    )
        if plan.get("edit_summaries") != self.operation.get("edit_summaries"):
            raise PublicationError("Résumés de modification divergents du plan")
        for action in plan.get("actions", []):
            self._summary_for_action(action)
            self._tags_for_action(action)
        if plan.get("blockers"):
            raise CollisionError("Le plan contient des bloqueurs")
        if (
            english_creates
            and check_publication_date
            and self._current_publication_date() != plan.get("publication_date")
        ):
            raise PublicationDateChanged(
                "Le jour de publication a changé depuis le plan ; régénérez le plan avant de créer les pages anglaises"
            )

    def _desired_text(self, action: dict[str, Any], remote_text: str) -> tuple[str, str]:
        source_path = self.root / action["source_path"]
        if sha_file(source_path) != action["local_file_sha256"]:
            raise PublicationError(f"Fichier local modifié depuis le plan : {action['source_path']}")
        local_text = source_path.read_text(encoding="utf-8")
        parameter = action.get("parameter")
        local_target = local_text if not parameter else extract_parameter(local_text, str(parameter))
        if sha_text(local_target) != action["local_target_sha256"]:
            raise PublicationError(f"Cible locale modifiée depuis le plan : {action['page_id']}")
        if not parameter and action.get("publication_creation_date"):
            row = self._manifest_page(str(action["language"]), str(action["page_id"]))
            if row is None:
                raise PublicationError(f"Page absente du manifeste : {action['page_id']}")
            local_text = self._english_translation_creation_text(
                row, local_text, str(action["publication_creation_date"])
            )
        desired = (
            local_text
            if not parameter
            else replace_parameter(
                remote_text,
                str(parameter),
                local_target,
                insert_if_missing=bool(
                    self.operation.get(
                        "insert_missing_parameter",
                        False,
                    )
                ),
            )
        )
        return desired, local_target

    def _verify_written_revision(
        self,
        *,
        title: str,
        revision_id: int,
        desired_text: str,
        summary: str,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        attempts = max(1, int(self.config.get("verification_attempts", 8)))
        delay = max(0.0, float(self.config.get("verification_delay_seconds", 2)))
        expected_tags = list(tags or self.tags)
        observed: dict[str, Any] | None = None
        for index in range(attempts):
            observed = self.adapter.read_revision(title, revision_id)
            if (
                observed
                and sha_text(str(observed.get("text", ""))) == sha_text(desired_text)
                and observed.get("summary") == summary
                and all(tag in (observed.get("tags") or []) for tag in expected_tags)
            ):
                return observed
            if index + 1 < attempts and delay:
                time.sleep(delay)
        self._log(
            {
                "event": "verification_failure",
                "title": title,
                "revision_id": revision_id,
                "expected_content_sha256": sha_text(desired_text),
                "expected_summary": summary,
                "expected_tags": expected_tags,
                "observed": observed,
            }
        )
        raise RevisionConflict(f"Échec de vérification de la révision {revision_id} pour {title}")

    def create_debate_test_receipt(
        self,
        *,
        plan: dict[str, Any],
        confirmation: str,
    ) -> dict[str, Any]:
        """Crée et vérifie la page Débat française canonique liée au plan signé."""
        self._verify_plan(plan, confirmation)
        self._validate_local()
        self._prepare_logging()
        if self.publication_profile not in DIRECT_PROFILES:
            raise PublicationError("Le test de la page Débat est réservé au profil de publication directe")
        if self.operation.get("kind") != "full_page":
            raise PublicationError("Le test de la page Débat exige une opération full_page")
        actions = [
            action
            for action in plan.get("actions", [])
            if action.get("language") == "fr" and action.get("page_type") == "debate"
        ]
        if len(actions) != 1:
            raise PublicationError(
                "Le plan doit contenir exactement une page Débat française canonique"
            )
        action = actions[0]
        if action.get("operation") != "create" or action.get("classification") != "remote_absent":
            raise CollisionError(
                "Le test canonique exige que la page Débat française soit absente dans le plan"
            )
        current_language = "fr"
        title = str(action["title"])
        _, user = self._site(current_language)
        summary = self._summary_for_page(current_language, str(action["page_id"]), "debate")
        action_tags = self._tags_for_action(action)
        source_path = self.root / str(action["source_path"])
        if sha_file(source_path) != action["local_file_sha256"]:
            raise PublicationError("Fichier local modifié depuis le plan")
        desired_text = source_path.read_text(encoding="utf-8")
        self.adapter.open_language(current_language, user)
        try:
            self.adapter.assert_identity(user)
            self._change_tag_gate(current_language)
            exists, _, _ = self.adapter.read_page(title)
            if exists:
                raise CollisionError("La page Débat française existe déjà depuis la simulation")
            revision_id = self.adapter.write_page(
                title=title, text=desired_text, summary=summary, tags=action_tags,
                expected_user=user, create_only=True, base_revision_id=None,
            )
            self._verify_written_revision(
                title=title, revision_id=revision_id, desired_text=desired_text, summary=summary, tags=action_tags
            )
        finally:
            self.adapter.close_language()
        receipt: dict[str, Any] = {
            "receipt_version": "wikidebia-debate-test-receipt-1",
            "status": "passed",
            "kit_version": KIT_VERSION,
            "validator_version": REQUIRED_VALIDATOR_VERSION,
            "plan_sha256": plan["plan_sha256"],
            "package_fingerprints": plan["package_fingerprints"],
            "debate_id": self.config["debate_id"],
            "operation_id": self.operation["id"],
            "language": current_language,
            "page_id": action["page_id"],
            "page_type": "debate",
            "canonical_title": title,
            "source_path": action["source_path"],
            "local_file_sha256": action["local_file_sha256"],
            "desired_sha256": action["desired_sha256"],
            "content_sha256": sha_text(desired_text),
            "revision_id": revision_id,
            "expected_user": user,
            "summary": summary,
            "tags": action_tags,
        }
        receipt["receipt_sha256"] = sha_object(receipt)
        self._log({"event": "canonical_debate_test_verified", **receipt})
        return receipt

    def _verify_debate_test_receipt(self, plan: dict[str, Any], receipt: dict[str, Any] | None) -> None:
        if (
            self.publication_profile not in DIRECT_PROFILES
            or self.operation.get("kind") != "full_page"
        ):
            return
        french_debate_actions = [
            action
            for action in plan.get("actions", [])
            if action.get("language") == "fr"
            and action.get("page_type") == "debate"
            and action.get("operation") == "create"
        ]
        # Le reçu canonique n'est requis que lorsqu'une page Débat française doit
        # réellement être créée. Une page déjà strictement équivalente est un skip
        # sûr et ne doit pas empêcher la commande intégrée de reprendre.
        if not french_debate_actions:
            return
        if not isinstance(receipt, dict):
            raise PublicationError("Le profil de publication directe exige --debate-test-receipt")
        copy = dict(receipt)
        claimed = copy.pop("receipt_sha256", None)
        if not claimed or claimed != sha_object(copy):
            raise PublicationError("Empreinte du reçu de test de la page Débat divergente")
        checks = {
            "receipt_version": "wikidebia-debate-test-receipt-1",
            "status": "passed",
            "kit_version": KIT_VERSION,
            "validator_version": REQUIRED_VALIDATOR_VERSION,
            "plan_sha256": plan.get("plan_sha256"),
            "package_fingerprints": plan.get("package_fingerprints"),
            "debate_id": self.config.get("debate_id"),
            "operation_id": self.operation.get("id"),
            "language": "fr",
            "page_type": "debate",
            "tags": self._tags_for_action(french_debate_actions[0]),
        }
        for field, expected in checks.items():
            if receipt.get(field) != expected:
                raise PublicationError(f"Reçu de test de la page Débat divergent : {field}")
        title = str(receipt.get("canonical_title") or "")
        language = "fr"
        matching_actions = [
            action
            for action in plan.get("actions", [])
            if action.get("language") == language
            and action.get("page_type") == "debate"
            and action.get("page_id") == receipt.get("page_id")
            and action.get("title") == title
        ]
        if len(matching_actions) != 1:
            raise PublicationError("La page Débat du reçu ne correspond pas au plan")
        action = matching_actions[0]
        if action.get("operation") != "create" or action.get("classification") != "remote_absent":
            raise PublicationError("L'action Débat du reçu n'est pas une création distante absente")
        action_checks = {
            "source_path": action.get("source_path"),
            "local_file_sha256": action.get("local_file_sha256"),
            "desired_sha256": action.get("desired_sha256"),
            "content_sha256": action.get("desired_sha256"),
            "summary": self._summary_for_action(action),
        }
        for field, expected in action_checks.items():
            if receipt.get(field) != expected:
                raise PublicationError(f"Reçu de test de la page Débat divergent : {field}")
        _, user = self._site(language)
        if receipt.get("expected_user") != user:
            raise PublicationError("Identité attendue divergente dans le reçu")
        revision_id = int(receipt.get("revision_id") or 0)
        if revision_id <= 0:
            raise PublicationError("Identifiant de révision invalide dans le reçu Débat")
        self.adapter.open_language(language, user)
        try:
            self.adapter.assert_identity(user)
            self._change_tag_gate(language)
            exists, latest_revision_id, latest_text = self.adapter.read_page(title)
            if not exists or latest_revision_id != revision_id:
                raise RevisionConflict(
                    "La page Débat testée n'est plus à la révision attestée"
                )
            if sha_text(latest_text) != receipt.get("content_sha256"):
                raise RevisionConflict("Le contenu courant de la page Débat testée diverge")
            observed = self.adapter.read_revision(title, revision_id)
            if not observed:
                raise RevisionConflict("Révision du test de la page Débat introuvable")
            if sha_text(str(observed.get("text", ""))) != receipt.get("content_sha256"):
                raise RevisionConflict("Contenu du test de la page Débat divergent")
            if observed.get("summary") != receipt.get("summary"):
                raise RevisionConflict("Résumé du test de la page Débat divergent")
            if any(tag not in (observed.get("tags") or []) for tag in (receipt.get("tags") or [])):
                raise RevisionConflict("Balise du test de la page Débat divergente")
        finally:
            self.adapter.close_language()

    def _corpus_version(self) -> str:
        for value in (
            self.manifest.get("release_version"),
            (self.manifest.get("release") or {}).get("version") if isinstance(self.manifest.get("release"), dict) else None,
            self.manifest.get("generated_date"),
        ):
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "manifest-" + sha_file(self.manifest_path)[:16]

    def _save_published_state(self, language: str, actions: list[dict[str, Any]], plan: dict[str, Any]) -> None:
        base_value = self.config.get("published_state_dir") or ".state/published"
        base = self._resolve(base_value) / str(self.config["debate_id"]) / language
        latest = base / "latest.json"
        previous_pages: dict[str, dict[str, Any]] = {}
        if latest.is_file():
            try:
                previous = json.loads(latest.read_text(encoding="utf-8"))
                unsigned = dict(previous)
                claimed = unsigned.pop("state_sha256", None)
                if claimed == sha_object(unsigned) and previous.get("debate_id") == self.config["debate_id"]:
                    previous_pages = {str(row.get("page_id")): dict(row) for row in previous.get("pages") or []}
            except (OSError, json.JSONDecodeError):
                previous_pages = {}
        for action in actions:
            exists, revision_id, remote_text = self.adapter.read_page(action["title"])
            if not exists or revision_id is None:
                continue
            previous_pages[str(action["page_id"])] = {
                "page_id": str(action["page_id"]),
                "page_type": str(action.get("page_type") or "unknown"),
                "canonical_title": str(action["title"]),
                "content_sha256": sha_text(remote_text),
                "revision_id": int(revision_id),
                "status": "published",
            }
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        pages = sorted(previous_pages.values(), key=lambda row: (row.get("page_type", ""), row.get("page_id", "")))
        receipt: dict[str, Any] = {
            "receipt_version": "wikidebia-publication-state-receipt-1.0",
            "kit_version": KIT_VERSION,
            "debate_id": self.config["debate_id"],
            "language": language,
            "corpus_version": self._corpus_version(),
            "published_at": now,
            "plan_sha256": plan["plan_sha256"],
            "pages": pages,
        }
        receipt["receipt_sha256"] = sha_object(receipt)
        receipt_base = self._resolve(self.config.get("receipts_dir") or ".state/receipts") / str(self.config["debate_id"])
        receipt_path = receipt_base / f"publication-{language}-{now.replace(':', '').replace('-', '')}.json"
        receipt_base.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        state: dict[str, Any] = {
            "state_version": "wikidebia-published-state-1.0",
            "debate_id": self.config["debate_id"],
            "language": language,
            "corpus_version": self._corpus_version(),
            "publication_date": now,
            "source_manifest_sha256": sha_file(self.manifest_path),
            "plan_sha256": plan["plan_sha256"],
            "receipt_path": portable(receipt_path, self.project_root),
            "receipt_sha256": receipt["receipt_sha256"],
            "pages": pages,
        }
        state["state_sha256"] = sha_object(state)
        base.mkdir(parents=True, exist_ok=True)
        latest.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        stamped = base / (now.replace(":", "").replace("-", "") + ".json")
        stamped.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    def publish(
        self,
        *,
        plan: dict[str, Any],
        confirmation: str,
        language: str | None = None,
        page_id: str | None = None,
        page_type: str | None = None,
        debate_test_receipt: dict[str, Any] | None = None,
        _progress: dict[tuple[str, str], str] | None = None,
    ) -> dict[str, int]:
        self._verify_plan(plan, confirmation)
        self._verify_debate_test_receipt(plan, debate_test_receipt)
        self._validate_local()
        self._prepare_logging()
        actions = list(plan["actions"])
        if language:
            actions = [item for item in actions if item["language"] == language]
        if page_id:
            actions = [item for item in actions if item["page_id"] == page_id]
        if page_type:
            actions = [item for item in actions if item["page_type"] == page_type]
        if not actions:
            raise PublicationError("Aucune action ne correspond aux filtres")
        counts = {"created": 0, "updated": 0, "skipped": 0}
        for current_language in self.languages:
            language_actions = [item for item in actions if item["language"] == current_language]
            if not language_actions:
                continue
            _, user = self._site(current_language)
            self.adapter.open_language(current_language, user)
            try:
                self.adapter.assert_identity(user)
                self._change_tag_gate(current_language)
                for action in language_actions:
                    summary = self._summary_for_action(action)
                    result = self._execute_action(action, user, summary)
                    if _progress is not None:
                        key = (str(action["language"]), str(action["page_id"]))
                        if key not in _progress or result != "skipped":
                            _progress[key] = result
                    counts[result] += 1
                    delay = max(0.0, float(self.config.get("write_delay_seconds", 0.5)))
                    if result in {"created", "updated"} and delay:
                        time.sleep(delay)
                self._save_published_state(current_language, language_actions, plan)
            finally:
                self.adapter.close_language()
        return counts

    def publish_with_date_refresh(
        self,
        *,
        plan: dict[str, Any],
        confirmation: str,
        rollover_dir: Path | None = None,
        language: str | None = None,
        page_id: str | None = None,
        page_type: str | None = None,
        debate_test_receipt: dict[str, Any] | None = None,
    ) -> dict[str, int]:
        """Resume a date-only successor, retaining all other signed constraints.

        Strict ``publish`` stays available to orchestrators that seal additional
        preflight/authorization artifacts. The standalone CLI uses this wrapper.
        """
        from wikidebia_publication_dates import (
            PublicationDateTransitionError,
            publication_plan_rollover_transition,
        )

        self._verify_plan(plan, confirmation, check_publication_date=False)
        progress: dict[tuple[str, str], str] = {}
        while True:
            try:
                self.publish(
                    plan=plan,
                    confirmation=confirmation,
                    language=language,
                    page_id=page_id,
                    page_type=page_type,
                    debate_test_receipt=debate_test_receipt,
                    _progress=progress,
                )
                return {
                    name: sum(result == name for result in progress.values())
                    for name in ("created", "updated", "skipped")
                }
            except PublicationDateChanged:
                # Check the original authorization again before inspecting a successor.
                self._verify_plan(plan, confirmation, check_publication_date=False)
                old_date = str(plan.get("publication_date") or "")
                new_date = self._current_publication_date()
                if new_date <= old_date:
                    raise PublicationError(f"Changement de jour non croissant : {old_date!r} -> {new_date!r}")
                self.publication_date = new_date
                self._tag_cache.clear()
                successor = self.build_plan()
                self._verify_plan(successor, successor["plan_sha256"], check_publication_date=False)
                try:
                    transition = publication_plan_rollover_transition(self, plan, successor, new_date)
                except PublicationDateTransitionError as exc:
                    raise PublicationError(str(exc)) from exc
                parent = (
                    rollover_dir
                    if rollover_dir is not None
                    else self.log_path.parent / "publication-date-rollovers"
                )
                parent.mkdir(parents=True, exist_ok=True)
                history = Path(tempfile.mkdtemp(prefix=f"{old_date}-to-{new_date}-", dir=parent))
                audit = {
                    "schema": "wikidebia-publication-date-rollover-1.0",
                    "debate_id": self.config["debate_id"],
                    "publication_timezone": self.publication_timezone,
                    "previous_plan_sha256": confirmation,
                    "successor_plan_sha256": successor["plan_sha256"],
                    **transition,
                }
                audit["rollover_sha256"] = sha_object(audit)
                for name, value in (
                    ("previous-plan.json", plan),
                    ("successor-plan.json", successor),
                    ("rollover.json", audit),
                ):
                    (history / name).write_text(
                        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                    )
                self._log({"event": "publication_date_refreshed", **audit, "history_path": str(history)})
                print(f"Date de publication actualisée automatiquement : {old_date} → {new_date}", file=sys.stderr)
                plan = successor
                confirmation = successor["plan_sha256"]

    def _execute_action(self, action: dict[str, Any], user: str, summary: str) -> str:
        action_tags = self._tags_for_action(action)
        exists, revision_id, remote_text = self.adapter.read_page(action["title"])
        if action["operation"] == "create":
            source_path = self.root / action["source_path"]
            if sha_file(source_path) != action["local_file_sha256"]:
                raise PublicationError(f"Fichier local modifié : {action['source_path']}")
            desired_text = source_path.read_text(encoding="utf-8")
            row = self._manifest_page(str(action.get("language") or ""), str(action.get("page_id") or ""))
            if row is None:
                raise PublicationError(f"Page absente du manifeste : {action.get('language')}/{action.get('page_id')}")
            publication_creation_date = action.get("publication_creation_date")
            if publication_creation_date:
                current_publication_date = self._current_publication_date()
                if current_publication_date != str(publication_creation_date):
                    raise PublicationDateChanged(
                        "Le jour de publication a changé avant la création de "
                        f"{action['title']} ; régénérez le plan pour dater correctement les pages restantes"
                    )
                desired_text = self._english_translation_creation_text(
                    row, desired_text, str(publication_creation_date)
                )
            if sha_text(desired_text) != action["desired_sha256"]:
                raise PublicationError(f"Contenu de création divergent du plan : {action['title']}")
            if exists:
                if revision_id is None:
                    raise RevisionConflict(f"Révision distante absente : {action['title']}")
                if publication_creation_date and not self._verified_existing_translation_creation(
                    row=row,
                    title=action["title"],
                    revision_id=revision_id,
                    remote_text=remote_text,
                    summary=summary,
                    tags=action_tags,
                ):
                    raise RevisionConflict(f"Collision anglaise non vérifiée depuis le plan : {action['title']}")
                if sha_text(remote_text) == action["desired_sha256"]:
                    self._log({"event": "resume_skip_equivalent", **self._identity(action), "revision_id": revision_id})
                    return "skipped"
                raise RevisionConflict(f"Collision créée depuis le plan : {action['title']}")
            new_revision = self.adapter.write_page(
                title=action["title"],
                text=desired_text,
                summary=summary,
                tags=action_tags,
                expected_user=user,
                create_only=True,
                base_revision_id=None,
            )
            self._verify_written_revision(
                title=action["title"], revision_id=new_revision, desired_text=desired_text, summary=summary, tags=action_tags
            )
            self._log({
                "event": "page_creation_verified",
                **self._identity(action),
                "new_revision_id": new_revision,
                "content_sha256": sha_text(desired_text),
                "summary": summary,
                "tags": action_tags,
            })
            return "created"
        if not exists or revision_id is None:
            raise RevisionConflict(f"Page distante absente : {action['title']}")
        desired_text, _ = self._desired_text(action, remote_text)
        current_sha = sha_text(remote_text)
        desired_sha = sha_text(desired_text)
        if action.get("publication_creation_date") and desired_sha != action["desired_sha256"]:
            raise PublicationError(f"Contenu daté divergent du plan : {action['title']}")
        if desired_sha == current_sha:
            self._log({"event": "skip_equivalent", **self._identity(action), "revision_id": revision_id})
            return "skipped"
        if action["operation"] == "skip":
            raise RevisionConflict(f"La page n'est plus équivalente : {action['title']}")
        if action["operation"] != "update":
            raise PublicationError(f"Opération non exécutable : {action['operation']}")
        if revision_id != action["remote_revision_id"] or current_sha != action["remote_sha256"]:
            raise RevisionConflict(f"Révision distante divergente depuis le plan : {action['title']}")
        if desired_sha != action["desired_sha256"]:
            raise PublicationError(f"Résultat local divergent du plan : {action['title']}")
        new_revision = self.adapter.write_page(
            title=action["title"],
            text=desired_text,
            summary=summary,
            tags=action_tags,
            expected_user=user,
            create_only=False,
            base_revision_id=revision_id,
        )
        self._verify_written_revision(
            title=action["title"], revision_id=new_revision, desired_text=desired_text, summary=summary
        )
        event = "parameter_update_verified" if action["kind"] == "parameter_update" else "page_update_verified"
        self._log({
            "event": event,
            **self._identity(action),
            "old_revision_id": revision_id,
            "new_revision_id": new_revision,
            "old_content_sha256": current_sha,
            "new_content_sha256": desired_sha,
            "parameter": action.get("parameter"),
            "summary": summary,
            "tags": action_tags,
        })
        return "updated"

    @staticmethod
    def _identity(action: dict[str, Any]) -> dict[str, Any]:
        return {
            "operation_id": action["operation_id"],
            "language": action["language"],
            "page_id": action["page_id"],
            "page_type": action["page_type"],
            "title": action["title"],
        }


def load_config(path: str | Path) -> tuple[dict[str, Any], Path]:
    config_path = Path(path).expanduser().resolve()
    return json.loads(config_path.read_text(encoding="utf-8")), config_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Kit générique de publication Wikidéb'IA : pages complètes ou paramètres ciblés."
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--pywikibot-dir")
    parser.add_argument("--mode", choices=("inspect", "plan", "debate-test", "publish"), default="plan")
    parser.add_argument("--plan-output", default="wikidebia_plan.json")
    parser.add_argument("--plan-input")
    parser.add_argument("--confirm-plan-sha256")
    parser.add_argument("--debate-test-receipt-output", default="wikidebia_debate_test_receipt.json")
    parser.add_argument("--debate-test-receipt")
    parser.add_argument("--language")
    parser.add_argument("--page-id")
    parser.add_argument("--page-type")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    config, config_path = load_config(args.config)
    if args.pywikibot_dir:
        config["pywikibot_dir"] = args.pywikibot_dir
    project_root = Path(config.get("project_root") or Path.cwd()).expanduser().resolve()
    def resolve(value: str | Path) -> Path:
        candidate = Path(value).expanduser()
        return candidate.resolve() if candidate.is_absolute() else (project_root / candidate).resolve()
    family_file = config.get("family_file")
    operation_languages = config["operation"].get("languages") or config.get("languages") or []
    adapter = PywikibotAdapter(
        str(config["family"]),
        {language: str(config["sites"][language]["code"]) for language in operation_languages},
        resolve(config["pywikibot_dir"]),
        resolve(family_file) if family_file else None,
    )
    publisher = GenericPublisher(config, adapter, config_path)

    if args.mode == "inspect":
        if args.execute:
            raise PublicationError("inspect est strictement en lecture seule")
        print(json.dumps(publisher.inspect(), ensure_ascii=False, indent=2))
        return 0
    if args.mode == "plan":
        if args.execute:
            raise PublicationError("plan est strictement en lecture seule")
        plan = publisher.build_plan()
        Path(args.plan_output).write_text(
            json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(plan["plan_sha256"])
        print(json.dumps(plan["counts"], ensure_ascii=False, sort_keys=True))
        return 3 if plan["blockers"] else 0
    if args.mode == "debate-test":
        if not args.execute or not args.plan_input or not args.confirm_plan_sha256:
            raise PublicationError(
                "debate-test exige --execute, --plan-input et --confirm-plan-sha256"
            )
        plan = json.loads(Path(args.plan_input).read_text(encoding="utf-8"))
        receipt = publisher.create_debate_test_receipt(
            plan=plan,
            confirmation=args.confirm_plan_sha256,
        )
        Path(args.debate_test_receipt_output).write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(receipt["receipt_sha256"])
        return 0
    if not args.execute or not args.plan_input or not args.confirm_plan_sha256:
        raise PublicationError(
            "publish exige --execute, --plan-input et --confirm-plan-sha256"
        )
    plan = json.loads(Path(args.plan_input).read_text(encoding="utf-8"))
    receipt = None
    if args.debate_test_receipt:
        receipt = json.loads(Path(args.debate_test_receipt).read_text(encoding="utf-8"))
    counts = publisher.publish_with_date_refresh(
        plan=plan,
        confirmation=args.confirm_plan_sha256,
        rollover_dir=Path(args.plan_input).resolve().parent / "publication-date-rollovers",
        language=args.language,
        page_id=args.page_id,
        page_type=args.page_type,
        debate_test_receipt=receipt,
    )
    print(json.dumps(counts, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PublicationError as exc:
        print(f"PUBLICATION BLOQUÉE : {exc}", file=sys.stderr)
        raise SystemExit(2)
