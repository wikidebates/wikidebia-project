#!/usr/bin/env python3
"""Extract a recursive Wikidéb'IA argument graph from a MediaWiki debate.

The script is strictly read-only. It follows:
- Debate -> pro/con arguments
- Argument -> justifications/objections

A page containing a "débat dédié" parameter or an English interlanguage link
is treated as a frontier by default. The linked target is recorded but local
argument relations are not traversed.

Designed for Pywikibot 11.x and the Wikidéb'IA ``wikidebates`` family file.
"""

from __future__ import annotations

from wikidebia_release_info import KIT_VERSION

import argparse
import csv
import dataclasses
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import time
import unicodedata
import zipfile
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, Sequence


GRAPH_EXTRACT_VERSION = "1.2.0"


# ---------------------------------------------------------------------------
# Small dependency-free wikitext template reader
# ---------------------------------------------------------------------------


def normalize_key(value: str) -> str:
    """Normalize a template/parameter name for tolerant comparisons."""
    value = html.unescape(str(value)).replace("_", " ").replace("-", " ")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"\s+", " ", value.strip().lower())
    if value.startswith("template:"):
        value = value.split(":", 1)[1].strip()
    return value


def _remove_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def _template_spans(text: str) -> list[tuple[int, int]]:
    """Return balanced ``{{...}}`` spans, including nested templates.

    Triple-brace parameters are tracked independently so their braces do not
    corrupt the template stack.
    """
    stack: list[tuple[int, int]] = []  # (brace width, start)
    spans: list[tuple[int, int]] = []
    i = 0
    while i < len(text):
        if text.startswith("{{{", i):
            stack.append((3, i))
            i += 3
            continue
        if text.startswith("{{", i):
            stack.append((2, i))
            i += 2
            continue
        if text.startswith("}}}", i) and stack and stack[-1][0] == 3:
            stack.pop()
            i += 3
            continue
        if text.startswith("}}", i) and stack and stack[-1][0] == 2:
            _, start = stack.pop()
            spans.append((start, i + 2))
            i += 2
            continue
        i += 1
    return sorted(spans, key=lambda item: (item[0], item[1] - item[0]))


def _split_top_level(text: str, delimiter: str, maxsplit: int = -1) -> list[str]:
    """Split while ignoring delimiters inside templates and wikilinks."""
    parts: list[str] = []
    start = 0
    splits = 0
    template_stack: list[int] = []
    wikilink_depth = 0
    i = 0
    while i < len(text):
        if text.startswith("{{{", i):
            template_stack.append(3)
            i += 3
            continue
        if text.startswith("{{", i):
            template_stack.append(2)
            i += 2
            continue
        if text.startswith("}}}", i) and template_stack and template_stack[-1] == 3:
            template_stack.pop()
            i += 3
            continue
        if text.startswith("}}", i) and template_stack and template_stack[-1] == 2:
            template_stack.pop()
            i += 2
            continue
        if text.startswith("[[", i):
            wikilink_depth += 1
            i += 2
            continue
        if text.startswith("]]", i) and wikilink_depth:
            wikilink_depth -= 1
            i += 2
            continue
        if (
            text.startswith(delimiter, i)
            and not template_stack
            and wikilink_depth == 0
            and (maxsplit < 0 or splits < maxsplit)
        ):
            parts.append(text[start:i])
            i += len(delimiter)
            start = i
            splits += 1
            continue
        i += 1
    parts.append(text[start:])
    return parts


CANONICAL_MEDIAWIKI_PARAMETER_ALIASES = {
    ("fr", "debate"): {"sujet-complet": "sujet-développé"},
    ("en", "debate"): {"complete-topic": "expanded-topic"},
    ("fr", "argument"): {"débat-détaillé": "débat-dédié", "nom": "nom-consacré"},
    ("en", "argument"): {"detailed-debate": "dedicated-debate", "name": "established-name"},
}

def canonical_mediawiki_parameter(language: str, page_type: str, name: str) -> str:
    mapping = CANONICAL_MEDIAWIKI_PARAMETER_ALIASES.get((language, page_type), {})
    normalized = normalize_key(name)
    for legacy, canonical in mapping.items():
        if normalized in {normalize_key(legacy), normalize_key(canonical)}:
            return canonical
    return name


@dataclasses.dataclass(frozen=True)
class TemplateCall:
    name: str
    params: Mapping[str, str]
    positional: tuple[str, ...]
    raw: str

    def get(self, *names: str) -> str:
        wanted = {normalize_key(name) for name in names}
        for key, value in self.params.items():
            if normalize_key(key) in wanted:
                return value.strip()
        return ""


def parse_template(raw: str) -> TemplateCall | None:
    if not (raw.startswith("{{") and raw.endswith("}}")):
        return None
    inner = raw[2:-2]
    segments = _split_top_level(inner, "|")
    if not segments:
        return None
    name = segments[0].strip()
    params: dict[str, str] = {}
    positional: list[str] = []
    for segment in segments[1:]:
        pair = _split_top_level(segment, "=", maxsplit=1)
        if len(pair) == 2 and pair[0].strip():
            params[pair[0].strip()] = pair[1].strip()
        else:
            positional.append(segment.strip())
    return TemplateCall(name=name, params=params, positional=tuple(positional), raw=raw)


def iter_templates(text: str) -> list[TemplateCall]:
    cleaned = _remove_comments(text)
    calls: list[TemplateCall] = []
    for start, end in _template_spans(cleaned):
        call = parse_template(cleaned[start:end])
        if call is not None:
            calls.append(call)
    return calls


def _strip_markup(value: str) -> str:
    value = _remove_comments(html.unescape(value)).strip()
    # Prefer the target of a single wikilink over its displayed text.
    match = re.fullmatch(r"\s*\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]*)?\]\]\s*", value, re.DOTALL)
    if match:
        value = match.group(1)
    value = re.sub(r"<[^>]+>", "", value)
    value = value.replace("'''", "").replace("''", "")
    value = re.sub(r"\s+", " ", value).strip().replace("_", " ")
    return unicodedata.normalize("NFC", value)


def title_from_template(call: TemplateCall) -> str:
    value = call.get("page", "argument", "titre", "title")
    if not value and call.positional:
        value = call.positional[0]
    return _strip_markup(value)


def displayed_title_from_template(call: TemplateCall) -> str:
    value = call.get(
        "titre-affiché",
        "titre affiche",
        "titre affiché",
        "displayed-title",
        "displayed title",
    )
    return _strip_markup(value)


DEBATE_TEMPLATE_KEYS = {"debat", "debate"}
ARGUMENT_TEMPLATE_KEYS = {"argument"}
PRO_LINK_KEYS = {"argument pour", "pro argument"}
CON_LINK_KEYS = {"argument contre", "con argument"}
JUSTIFICATION_KEYS = {"justification"}
OBJECTION_KEYS = {"objection"}
DETAILED_DEBATE_TEMPLATE_KEYS = {"debat detaille", "detailed debate"}
INTERLANGUAGE_TEMPLATE_KEYS = {"lien interlangue", "interlangue"}


@dataclasses.dataclass(frozen=True)
class LinkEntry:
    page: str
    displayed_title: str = ""


@dataclasses.dataclass
class ParsedDebate:
    pro: list[LinkEntry]
    con: list[LinkEntry]
    warnings: list[str]
    existing_english_title: str = ""


@dataclasses.dataclass
class ParsedArgument:
    justifications: list[LinkEntry]
    objections: list[LinkEntry]
    detailed_debate: str
    warnings: list[str]
    ignored_relations_at_frontier: int = 0
    existing_english_title: str = ""
    existing_english_translation_verified: bool = False
    ignored_relations_at_existing_english_translation: int = 0


def _find_outer(calls: Sequence[TemplateCall], names: set[str]) -> TemplateCall | None:
    matching = [call for call in calls if normalize_key(call.name) in names]
    if not matching:
        return None
    return max(matching, key=lambda call: len(call.raw))


def _entries_from_value(value: str, template_names: set[str]) -> list[LinkEntry]:
    result: list[LinkEntry] = []
    for call in iter_templates(value):
        if normalize_key(call.name) not in template_names:
            continue
        page = title_from_template(call)
        if page:
            result.append(LinkEntry(page=page, displayed_title=displayed_title_from_template(call)))
    return result


def parse_debate_wikitext(text: str) -> ParsedDebate:
    calls = iter_templates(text)
    warnings: list[str] = []
    outer = _find_outer(calls, DEBATE_TEMPLATE_KEYS)
    pro: list[LinkEntry] = []
    con: list[LinkEntry] = []
    existing_english_title = ""
    if outer:
        existing_english_title = _english_translation_from_value(
            outer.get("interlangue", "interlanguage")
        )
        pro_value = outer.get("arguments-pour", "arguments pour", "pro-arguments", "pro arguments")
        con_value = outer.get("arguments-contre", "arguments contre", "con-arguments", "con arguments")
        if pro_value:
            pro = _entries_from_value(pro_value, PRO_LINK_KEYS)
        if con_value:
            con = _entries_from_value(con_value, CON_LINK_KEYS)
    if not pro:
        warnings.append("Fallback: arguments pour recherchés dans toute la page")
        pro = [
            LinkEntry(title_from_template(call), displayed_title_from_template(call))
            for call in calls
            if normalize_key(call.name) in PRO_LINK_KEYS and title_from_template(call)
        ]
    if not con:
        warnings.append("Fallback: arguments contre recherchés dans toute la page")
        con = [
            LinkEntry(title_from_template(call), displayed_title_from_template(call))
            for call in calls
            if normalize_key(call.name) in CON_LINK_KEYS and title_from_template(call)
        ]
    return ParsedDebate(
        pro=pro,
        con=con,
        warnings=warnings,
        existing_english_title=existing_english_title,
    )


def _detailed_debate_from_value(value: str) -> str:
    if not value.strip():
        return ""
    for call in iter_templates(value):
        if normalize_key(call.name) in DETAILED_DEBATE_TEMPLATE_KEYS:
            page = title_from_template(call)
            if page:
                return page
    return _strip_markup(value)


def _english_translation_from_value(value: str) -> str:
    """Return the declared English target of a standard interlanguage link."""
    if not value.strip():
        return ""
    for call in iter_templates(value):
        if normalize_key(call.name) not in INTERLANGUAGE_TEMPLATE_KEYS:
            continue
        language = normalize_key(call.get("langue", "language", "lang"))
        if language != "en":
            continue
        page = title_from_template(call)
        if page:
            return page
    return ""


def parse_argument_wikitext(
    text: str,
    *,
    stop_on_detailed_debate: bool = True,
    stop_on_existing_english_translation: bool = True,
) -> ParsedArgument:
    calls = iter_templates(text)
    warnings: list[str] = []
    outer = _find_outer(calls, ARGUMENT_TEMPLATE_KEYS)
    justifications: list[LinkEntry] = []
    objections: list[LinkEntry] = []
    detailed = ""
    existing_english_title = ""
    if outer:
        detailed = _detailed_debate_from_value(
            outer.get(
                "débat-dédié",
                "débat-détaillé",
                "débat dédié",
                "débat détaillé",
                "debat-detaille",
                "debat detaille",
                "dedicated-debate",
                "detailed-debate",
                "dedicated debate",
                "detailed debate",
            )
        )
        existing_english_title = _english_translation_from_value(
            outer.get("interlangue", "interlanguage")
        )
        just_value = outer.get("justifications")
        obj_value = outer.get("objections")
        if just_value:
            justifications = _entries_from_value(just_value, JUSTIFICATION_KEYS)
        if obj_value:
            objections = _entries_from_value(obj_value, OBJECTION_KEYS)
    else:
        warnings.append("Modèle Argument principal introuvable; fallback global")

    if outer is None or (not justifications and not objections):
        # This fallback also supports legacy pages whose relation templates are
        # outside the main Argument template. It is deliberately reported.
        global_just = [
            LinkEntry(title_from_template(call), displayed_title_from_template(call))
            for call in calls
            if normalize_key(call.name) in JUSTIFICATION_KEYS and title_from_template(call)
        ]
        global_obj = [
            LinkEntry(title_from_template(call), displayed_title_from_template(call))
            for call in calls
            if normalize_key(call.name) in OBJECTION_KEYS and title_from_template(call)
        ]
        if global_just and not justifications:
            warnings.append("Fallback global utilisé pour les justifications")
            justifications = global_just
        if global_obj and not objections:
            warnings.append("Fallback global utilisé pour les objections")
            objections = global_obj

    ignored = 0
    ignored_existing_translation = 0
    if existing_english_title and stop_on_existing_english_translation:
        ignored_existing_translation = len(justifications) + len(objections)
        justifications = []
        objections = []
    elif detailed and stop_on_detailed_debate:
        ignored = len(justifications) + len(objections)
        # Une frontière est une décision normale de périmètre, pas un avertissement.
        # Le nombre de relations locales écartées est exporté séparément afin de
        # rester visible sans être confondu avec une anomalie de parsing.
        justifications = []
        objections = []

    return ParsedArgument(
        justifications=justifications,
        objections=objections,
        detailed_debate=detailed,
        warnings=warnings,
        ignored_relations_at_frontier=ignored,
        existing_english_title=existing_english_title,
        ignored_relations_at_existing_english_translation=ignored_existing_translation,
    )


# ---------------------------------------------------------------------------
# Page backend and cache
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class PageRecord:
    requested_title: str
    canonical_title: str
    text: str
    url: str = ""
    revision_id: int | None = None
    revision_timestamp: str = ""
    redirect_chain: list[str] = dataclasses.field(default_factory=list)
    fetched_at: str = ""


class PageClient(Protocol):
    aliases: dict[str, str]

    def fetch(self, title: str) -> PageRecord:
        ...


class PageMissingError(RuntimeError):
    pass


class JsonPageCache:
    def __init__(self, directory: Path, *, force_refresh: bool = False) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.force_refresh = force_refresh

    def _path(self, title: str) -> Path:
        digest = hashlib.sha256(title.encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.json"

    def get(self, title: str) -> PageRecord | None:
        path = self._path(title)
        if self.force_refresh or not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return PageRecord(**data)

    def put(self, record: PageRecord) -> None:
        payload = dataclasses.asdict(record)
        for title in {record.requested_title, record.canonical_title, *record.redirect_chain}:
            path = self._path(title)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            tmp.replace(path)


class PywikibotPageClient:
    """Read-only Pywikibot backend with per-page persistent caching."""

    def __init__(
        self,
        *,
        family: str,
        lang: str,
        family_file: Path | None,
        pywikibot_dir: Path | None,
        cache: JsonPageCache,
        login: bool = False,
        retries: int = 4,
        retry_delay: float = 2.0,
    ) -> None:
        self.family = family
        self.lang = lang
        self.family_file = family_file
        self.pywikibot_dir = pywikibot_dir
        self.cache = cache
        self.login = login
        self.retries = retries
        self.retry_delay = retry_delay
        self.aliases: dict[str, str] = {}
        self._site: Any | None = None
        self._pywikibot: Any | None = None

    def _open(self) -> None:
        if self._site is not None:
            return
        if self.pywikibot_dir and (self.pywikibot_dir / "user-config.py").is_file():
            os.environ["PYWIKIBOT_DIR"] = str(self.pywikibot_dir.resolve())
        else:
            if self.login:
                raise RuntimeError("--login exige private/pywikibot/user-config.py")
            os.environ.setdefault("PYWIKIBOT_NO_USER_CONFIG", "2")
        try:
            import pywikibot  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "Pywikibot est absent. Installez-le avec: pip install 'pywikibot>=11.5,<12'"
            ) from exc
        access_token = os.environ.get("WIKIDEBIA_API_TOKEN")
        if access_token:
            pywikibot.config.extra_headers["x-wikidebia-access"] = access_token
        if self.family_file:
            family_files = getattr(pywikibot.config, "family_files", None)
            if family_files is None:
                raise RuntimeError("pywikibot.config.family_files est indisponible")
            family_files[self.family] = str(self.family_file.resolve())
        self._pywikibot = pywikibot
        self._site = pywikibot.Site(code=self.lang, fam=self.family)
        if self.login:
            self._site.login()

    def fetch(self, title: str) -> PageRecord:
        title = _strip_markup(title)
        cached = self.cache.get(title)
        if cached is not None:
            self.aliases[title] = cached.canonical_title
            for alias in cached.redirect_chain:
                self.aliases[alias] = cached.canonical_title
            return cached

        self._open()
        assert self._pywikibot is not None and self._site is not None
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                page = self._pywikibot.Page(self._site, title)
                if not page.exists():
                    raise PageMissingError(f"Page inexistante: {title}")
                chain: list[str] = []
                seen: set[str] = set()
                while page.isRedirectPage():
                    current = page.title(with_section=False, underscore=False)
                    if current in seen:
                        raise RuntimeError(f"Redirection circulaire détectée: {current}")
                    seen.add(current)
                    chain.append(current)
                    page = page.getRedirectTarget(ignore_section=True)
                canonical = page.title(with_section=False, underscore=False)
                text = page.get(force=self.cache.force_refresh)
                revision_id: int | None = None
                revision_timestamp = ""
                try:
                    revision = page.latest_revision
                    revision_id = int(revision.revid)
                    timestamp_value = getattr(revision, "timestamp", None)
                    if timestamp_value is not None:
                        revision_timestamp = timestamp_value.isoformat()
                except Exception:
                    pass
                record = PageRecord(
                    requested_title=title,
                    canonical_title=canonical,
                    text=text,
                    url=page.full_url(),
                    revision_id=revision_id,
                    revision_timestamp=revision_timestamp,
                    redirect_chain=chain,
                    fetched_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                )
                self.cache.put(record)
                self.aliases[title] = canonical
                for alias in chain:
                    self.aliases[alias] = canonical
                return record
            except PageMissingError:
                raise
            except Exception as exc:  # network/server errors vary by Pywikibot version
                last_error = exc
                if attempt >= self.retries:
                    break
                time.sleep(self.retry_delay * (2**attempt))
        raise RuntimeError(f"Échec de lecture de {title!r}: {last_error}") from last_error


# ---------------------------------------------------------------------------
# Crawling and graph analytics
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class RelationDraft:
    source: str
    relation: str
    target: str
    order: int
    displayed_titles: set[str] = dataclasses.field(default_factory=set)


@dataclasses.dataclass
class CrawlResult:
    debate_record: PageRecord
    debate_title: str
    debate_url: str
    roots_pro: list[str]
    roots_con: list[str]
    root_displayed_titles: dict[str, set[str]]
    page_records: dict[str, PageRecord]
    parsed_arguments: dict[str, ParsedArgument]
    relations: list[RelationDraft]
    aliases: dict[str, str]
    warnings: list[str]
    frontier_information: list[str]
    existing_english_debate_title: str
    existing_english_translation_frontiers: dict[str, str]
    existing_english_page_records: dict[str, PageRecord]
    depth_frontiers: dict[str, int]
    missing_pages: list[str]
    crawl_options: dict[str, Any]


def _add_relation(
    relation_map: dict[tuple[str, str, str], RelationDraft],
    *,
    source: str,
    relation: str,
    target: str,
    order: int,
    displayed_title: str,
) -> None:
    key = (source, relation, target)
    if key not in relation_map:
        relation_map[key] = RelationDraft(source, relation, target, order)
    if displayed_title:
        relation_map[key].displayed_titles.add(displayed_title)


def crawl_graph(
    client: PageClient,
    *,
    debate_title: str,
    english_client: PageClient | None = None,
    stop_on_detailed_debate: bool = True,
    stop_on_existing_english_translation: bool = True,
    max_depth: int | None = None,
    max_pages: int = 5000,
    allow_missing: bool = False,
    progress_every: int = 25,
) -> CrawlResult:
    if max_depth is not None and max_depth < 0:
        raise RuntimeError("--max-depth doit être positif ou nul")
    debate_record = client.fetch(debate_title)
    parsed_debate = parse_debate_wikitext(debate_record.text)
    warnings = [f"Débat: {warning}" for warning in parsed_debate.warnings]
    frontier_information: list[str] = []
    existing_english_debate_title = ""
    existing_english_translation_frontiers: dict[str, str] = {}
    existing_english_page_records: dict[str, PageRecord] = {}
    depth_frontiers: dict[str, int] = {}
    if parsed_debate.existing_english_title and stop_on_existing_english_translation:
        if english_client is None:
            raise RuntimeError(
                "La cible interlangue anglaise du débat doit être vérifiée avec un client anglais"
            )
        try:
            english_debate_record = english_client.fetch(parsed_debate.existing_english_title)
        except PageMissingError:
            warnings.append(
                "Débat: cible anglaise inexistante; traduction française poursuivie: "
                + parsed_debate.existing_english_title
            )
        else:
            existing_english_debate_title = english_debate_record.canonical_title
            existing_english_page_records[debate_record.canonical_title] = english_debate_record
            frontier_information.append(
                f"{debate_record.canonical_title}: débat déjà traduit en anglais: "
                f"{existing_english_debate_title}; graphe argumentatif non parcouru"
            )
    if (
        not existing_english_debate_title
        and not parsed_debate.pro
        and not parsed_debate.con
    ):
        raise RuntimeError("Aucun argument principal n'a été trouvé dans la page Débat")

    page_records: dict[str, PageRecord] = {}
    parsed_arguments: dict[str, ParsedArgument] = {}
    roots_pro: list[str] = []
    roots_con: list[str] = []
    root_displayed: dict[str, set[str]] = defaultdict(set)
    missing: list[str] = []
    relation_map: dict[tuple[str, str, str], RelationDraft] = {}
    queue: deque[tuple[str, int]] = deque()
    queued_depth: dict[str, int] = {}

    def resolve(entry: LinkEntry, *, context: str, depth: int) -> str | None:
        try:
            record = client.fetch(entry.page)
        except PageMissingError:
            missing.append(entry.page)
            warnings.append(f"Page manquante ({context}): {entry.page}")
            if allow_missing:
                return entry.page
            return None
        canonical = record.canonical_title
        page_records[canonical] = record
        if entry.displayed_title:
            root_displayed[canonical].add(entry.displayed_title)
        if canonical not in queued_depth or depth < queued_depth[canonical]:
            queued_depth[canonical] = depth
            queue.append((canonical, depth))
        return canonical

    if not existing_english_debate_title:
        for entry in parsed_debate.pro:
            canonical = resolve(entry, context="argument pour", depth=0)
            if canonical and canonical not in roots_pro:
                roots_pro.append(canonical)
        for entry in parsed_debate.con:
            canonical = resolve(entry, context="argument contre", depth=0)
            if canonical and canonical not in roots_con:
                roots_con.append(canonical)

    processed = 0
    while queue:
        title, depth = queue.popleft()
        if title in parsed_arguments:
            continue
        if len(parsed_arguments) >= max_pages:
            raise RuntimeError(f"Limite de sécurité atteinte: {max_pages} pages")
        record = page_records.get(title) or client.fetch(title)
        page_records[record.canonical_title] = record
        parsed = parse_argument_wikitext(
            record.text,
            stop_on_detailed_debate=stop_on_detailed_debate,
            stop_on_existing_english_translation=stop_on_existing_english_translation,
        )
        if parsed.existing_english_title and stop_on_existing_english_translation:
            if english_client is None:
                raise RuntimeError(
                    "Une cible interlangue anglaise doit être vérifiée avec un client anglais"
                )
            declared_english_title = parsed.existing_english_title
            try:
                english_record = english_client.fetch(declared_english_title)
            except PageMissingError:
                warnings.append(
                    f"{record.canonical_title}: cible anglaise inexistante; "
                    f"parcours français poursuivi: {declared_english_title}"
                )
                parsed = parse_argument_wikitext(
                    record.text,
                    stop_on_detailed_debate=stop_on_detailed_debate,
                    stop_on_existing_english_translation=False,
                )
            else:
                parsed.existing_english_title = english_record.canonical_title
                parsed.existing_english_translation_verified = True
                existing_english_page_records[record.canonical_title] = english_record
        parsed_arguments[record.canonical_title] = parsed
        warnings.extend(f"{record.canonical_title}: {warning}" for warning in parsed.warnings)
        if parsed.existing_english_translation_verified:
            existing_english_translation_frontiers[record.canonical_title] = (
                parsed.existing_english_title
            )
            if stop_on_existing_english_translation:
                frontier_information.append(
                    f"{record.canonical_title}: traduction anglaise existante "
                    f"{parsed.existing_english_title}; "
                    f"{parsed.ignored_relations_at_existing_english_translation} "
                    "relation(s) locale(s) non suivie(s)"
                )
        if parsed.detailed_debate and parsed.ignored_relations_at_frontier:
            frontier_information.append(
                f"{record.canonical_title}: frontière vers {parsed.detailed_debate}; "
                f"{parsed.ignored_relations_at_frontier} relation(s) locale(s) non suivie(s)"
            )

        relation_order = Counter()
        for relation_type, entries in (
            ("justification", parsed.justifications),
            ("objection", parsed.objections),
        ):
            if max_depth is not None and depth >= max_depth:
                if entries:
                    depth_frontiers[record.canonical_title] = (
                        depth_frontiers.get(record.canonical_title, 0) + len(entries)
                    )
                continue
            for entry in entries:
                relation_order[relation_type] += 1
                try:
                    child_record = client.fetch(entry.page)
                    child = child_record.canonical_title
                    page_records[child] = child_record
                    child_depth = depth + 1
                    if child not in queued_depth or child_depth < queued_depth[child]:
                        queued_depth[child] = child_depth
                        queue.append((child, child_depth))
                except PageMissingError:
                    missing.append(entry.page)
                    warnings.append(
                        f"Page manquante ({record.canonical_title} -> {relation_type}): {entry.page}"
                    )
                    if not allow_missing:
                        continue
                    child = entry.page
                _add_relation(
                    relation_map,
                    source=record.canonical_title,
                    relation=relation_type,
                    target=child,
                    order=relation_order[relation_type],
                    displayed_title=entry.displayed_title,
                )
        processed += 1
        if progress_every and processed % progress_every == 0:
            print(
                f"[progression] {processed} pages analysées, "
                f"{len(queue)} en file, {len(relation_map)} relations",
                file=sys.stderr,
            )

    if missing and not allow_missing:
        unique = sorted(set(missing))
        raise RuntimeError(
            f"{len(unique)} page(s) manquante(s); relancez avec --allow-missing pour exporter malgré tout: "
            + "; ".join(unique[:10])
        )

    return CrawlResult(
        debate_record=debate_record,
        debate_title=debate_record.canonical_title,
        debate_url=debate_record.url,
        roots_pro=roots_pro,
        roots_con=roots_con,
        root_displayed_titles={key: set(value) for key, value in root_displayed.items()},
        page_records=page_records,
        parsed_arguments=parsed_arguments,
        relations=sorted(
            relation_map.values(),
            key=lambda r: (r.source.casefold(), r.relation, r.order, r.target.casefold()),
        ),
        aliases=dict(sorted(client.aliases.items())),
        warnings=warnings,
        frontier_information=frontier_information,
        existing_english_debate_title=existing_english_debate_title,
        existing_english_translation_frontiers=dict(
            sorted(
                existing_english_translation_frontiers.items(),
                key=lambda item: item[0].casefold(),
            )
        ),
        existing_english_page_records=existing_english_page_records,
        depth_frontiers=dict(sorted(depth_frontiers.items(), key=lambda item: item[0].casefold())),
        missing_pages=sorted(set(missing)),
        crawl_options={
            "stop_on_detailed_debate": stop_on_detailed_debate,
            "stop_on_existing_english_translation": stop_on_existing_english_translation,
            "max_depth": max_depth,
            "max_pages": max_pages,
            "allow_missing": allow_missing,
        },
    )


def _topological_order(nodes: set[str], edges: Sequence[RelationDraft]) -> tuple[list[str], list[str]]:
    adjacency: dict[str, list[str]] = defaultdict(list)
    indegree = {node: 0 for node in nodes}
    for edge in edges:
        if edge.source not in nodes or edge.target not in nodes:
            continue
        adjacency[edge.source].append(edge.target)
        indegree[edge.target] += 1
    queue = deque(sorted((node for node, deg in indegree.items() if deg == 0), key=str.casefold))
    order: list[str] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for child in adjacency[node]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    cycle_nodes = sorted((node for node, deg in indegree.items() if deg > 0), key=str.casefold)
    return order, cycle_nodes


def analyze_graph(result: CrawlResult) -> dict[str, Any]:
    roots = result.roots_pro + result.roots_con
    nodes = set(result.parsed_arguments)
    if result.missing_pages:
        nodes.update(result.missing_pages)
    adjacency: dict[str, list[tuple[str, str]]] = defaultdict(list)
    reverse: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for edge in result.relations:
        adjacency[edge.source].append((edge.target, edge.relation))
        reverse[edge.target].append((edge.source, edge.relation))

    # Le niveau commence à 1 pour une racine. La profondeur en arêtes vaut
    # donc toujours niveau - 1. Les deux métriques sont exportées séparément.
    minimum_level = {node: 10**9 for node in nodes}
    queue: deque[str] = deque()
    for root in roots:
        minimum_level[root] = 1
        queue.append(root)
    while queue:
        source = queue.popleft()
        for target, _ in adjacency[source]:
            if minimum_level[target] > minimum_level[source] + 1:
                minimum_level[target] = minimum_level[source] + 1
                queue.append(target)

    topo, cycle_nodes = _topological_order(nodes, result.relations)
    occurrences_by_level_for_node: dict[str, Counter[int]] = {
        node: Counter() for node in nodes
    }
    roots_reaching: dict[str, set[str]] = {node: set() for node in nodes}
    if not cycle_nodes:
        for root in roots:
            occurrences_by_level_for_node[root][1] += 1
            roots_reaching[root].add(root)
        for source in topo:
            for target, _ in adjacency[source]:
                roots_reaching[target].update(roots_reaching[source])
                for source_level, count in occurrences_by_level_for_node[source].items():
                    occurrences_by_level_for_node[target][source_level + 1] += count

    orientation = {root: "pour" for root in result.roots_pro}
    orientation.update({root: "contre" for root in result.roots_con})
    displayed_by_node: dict[str, set[str]] = defaultdict(set)
    for root, values in result.root_displayed_titles.items():
        displayed_by_node[root].update(values)
    for edge in result.relations:
        displayed_by_node[edge.target].update(edge.displayed_titles)

    node_rows: list[dict[str, Any]] = []
    for title in sorted(nodes, key=str.casefold):
        parsed = result.parsed_arguments.get(title)
        detailed = parsed.detailed_debate if parsed else ""
        ignored_at_frontier = parsed.ignored_relations_at_frontier if parsed else 0
        existing_english_title = parsed.existing_english_title if parsed else ""
        existing_english_translation_verified = (
            parsed.existing_english_translation_verified if parsed else False
        )
        existing_english_record = result.existing_english_page_records.get(title)
        ignored_at_existing_translation = (
            parsed.ignored_relations_at_existing_english_translation if parsed else 0
        )
        out_count = len({target for target, _ in adjacency[title]})
        if title in result.depth_frontiers:
            status = "frontière_profondeur"
        elif existing_english_translation_verified and result.crawl_options.get(
            "stop_on_existing_english_translation"
        ):
            status = "frontière_traduction_anglaise_existante"
        elif detailed:
            status = "frontière_débat_détaillé"
        elif out_count:
            status = "branche"
        elif title in result.missing_pages:
            status = "page_manquante"
        else:
            status = "terminal"
        root_set = roots_reaching.get(title, set())
        orientation_set = sorted({orientation[root] for root in root_set})
        occurrence_levels = occurrences_by_level_for_node.get(title, Counter())
        level = None if minimum_level[title] >= 10**9 else minimum_level[title]
        edge_depth = None if level is None else level - 1
        occurrences_by_edge_depth = {
            occurrence_level - 1: count
            for occurrence_level, count in sorted(occurrence_levels.items())
        }
        node_rows.append(
            {
                "titre": title,
                "niveau_minimal": level,
                "profondeur_minimale_en_aretes": edge_depth,
                "profondeur_minimale": level,
                "occurrences_totales": sum(occurrence_levels.values()) if not cycle_nodes else None,
                "occurrences_par_niveau": dict(sorted(occurrence_levels.items())),
                "occurrences_par_profondeur_en_aretes": occurrences_by_edge_depth,
                "occurrences_par_profondeur": dict(sorted(occurrence_levels.items())),
                "orientations_racines": orientation_set,
                "arguments_racines": sorted(root_set, key=str.casefold),
                "nombre_parents": len({parent for parent, _ in reverse[title]}),
                "nombre_enfants": out_count,
                "relations_locales_ignorees_frontiere": ignored_at_frontier,
                "relations_locales_ignorees_traduction_anglaise": (
                    ignored_at_existing_translation
                ),
                "statut": status,
                "débat_détaillé": detailed,
                "traduction_anglaise_existante": existing_english_title,
                "traduction_anglaise_existante_vérifiée": (
                    existing_english_translation_verified
                ),
                "traduction_anglaise_requise": not (
                    existing_english_translation_verified
                    and result.crawl_options.get("stop_on_existing_english_translation")
                ),
                "url_traduction_anglaise_existante": (
                    existing_english_record.url if existing_english_record else ""
                ),
                "revision_traduction_anglaise_existante": (
                    existing_english_record.revision_id if existing_english_record else None
                ),
                "vérification_traduction_anglaise_effectuée_le": (
                    existing_english_record.fetched_at if existing_english_record else ""
                ),
                "titres_affichés_observés": sorted(displayed_by_node[title], key=str.casefold),
                "url": result.page_records.get(title).url if title in result.page_records else "",
                "revision_id": (
                    result.page_records[title].revision_id if title in result.page_records else None
                ),
            }
        )

    relation_rows: list[dict[str, Any]] = []
    for edge in result.relations:
        source_level = (
            None if minimum_level.get(edge.source, 10**9) >= 10**9 else minimum_level[edge.source]
        )
        target_level = (
            None if minimum_level.get(edge.target, 10**9) >= 10**9 else minimum_level[edge.target]
        )
        source_depth = None if source_level is None else source_level - 1
        target_depth = None if target_level is None else target_level - 1
        relation_rows.append(
            {
                "source": edge.source,
                "relation": edge.relation,
                "cible": edge.target,
                "ordre": edge.order,
                "titres_affichés_observés": sorted(edge.displayed_titles, key=str.casefold),
                "niveau_source_minimal": source_level,
                "niveau_cible_minimal": target_level,
                "profondeur_source_minimale_en_aretes": source_depth,
                "profondeur_cible_minimale_en_aretes": target_depth,
                "profondeur_source_minimale": source_level,
                "profondeur_cible_minimale": target_level,
            }
        )

    pages_by_minimum_level = Counter(
        row["niveau_minimal"]
        for row in node_rows
        if row["niveau_minimal"] is not None
    )
    occurrences_by_level: Counter[int] = Counter()
    if not cycle_nodes:
        for counter in occurrences_by_level_for_node.values():
            occurrences_by_level.update(counter)

    maximum_occurrence_level = max(occurrences_by_level, default=0)
    maximum_minimum_level = max(pages_by_minimum_level, default=0)
    maximum_edge_depth = maximum_occurrence_level - 1 if maximum_occurrence_level else 0

    reused_occurrences_by_level: dict[int, int] = {}
    reused_pages_by_level: dict[int, list[str]] = {}
    if not cycle_nodes:
        for level in sorted(occurrences_by_level):
            reused_count = occurrences_by_level[level] - pages_by_minimum_level.get(level, 0)
            if reused_count:
                reused_occurrences_by_level[level] = reused_count
                reused_pages_by_level[level] = sorted(
                    [
                        title
                        for title, counter in occurrences_by_level_for_node.items()
                        if counter.get(level, 0)
                        and (
                            minimum_level.get(title, 10**9) < level
                            or counter.get(level, 0) > 1
                        )
                    ],
                    key=str.casefold,
                )

    branch_rows: list[dict[str, Any]] = []
    if not cycle_nodes:
        for root in roots:
            reachable: set[str] = set()
            stack = [root]
            while stack:
                node = stack.pop()
                if node in reachable:
                    continue
                reachable.add(node)
                stack.extend(child for child, _ in adjacency[node])
            branch_occ: dict[str, Counter[int]] = {node: Counter() for node in nodes}
            branch_occ[root][1] = 1
            for source in topo:
                for target, _ in adjacency[source]:
                    for source_level, count in branch_occ[source].items():
                        branch_occ[target][source_level + 1] += count
            total_occ = sum(sum(counter.values()) for counter in branch_occ.values())
            max_level = max(
                (level for counter in branch_occ.values() for level in counter),
                default=1,
            )
            max_depth = max_level - 1
            branch_rows.append(
                {
                    "orientation": orientation[root],
                    "argument": root,
                    "enfants_directs": len(adjacency[root]),
                    "pages_uniques_branche_racine_incluse": len(reachable),
                    "occurrences_branche_racine_incluse": total_occ,
                    "niveau_maximal_occurrences": max_level,
                    "profondeur_maximale_en_aretes": max_depth,
                    "profondeur_maximale": max_level,
                }
            )

    boundaries = {
        row["titre"]: row["débat_détaillé"]
        for row in node_rows
        if row["débat_détaillé"]
    }
    ignored_frontier_relations = sum(
        row["relations_locales_ignorees_frontiere"] for row in node_rows
    )
    existing_english_translations = {
        row["titre"]: row["traduction_anglaise_existante"]
        for row in node_rows
        if row["traduction_anglaise_existante_vérifiée"]
    }
    ignored_existing_translation_relations = sum(
        row["relations_locales_ignorees_traduction_anglaise"] for row in node_rows
    )
    reused = sum((row["occurrences_totales"] or 0) > 1 for row in node_rows)
    pages_without_outgoing = sum(row["nombre_enfants"] == 0 for row in node_rows)
    actual_terminals = sum(row["statut"] == "terminal" for row in node_rows)
    unfolded_occurrences = sum(occurrences_by_level.values()) if not cycle_nodes else None
    existing_english_debate_record = result.existing_english_page_records.get(
        result.debate_title
    )
    metadata = {
        "kit_version": KIT_VERSION,
        "extracteur_version": GRAPH_EXTRACT_VERSION,
        "débat": result.debate_title,
        "url_débat": result.debate_url,
        "traduction_anglaise_débat_existante": result.existing_english_debate_title,
        "traduction_anglaise_débat_vérifiée": bool(result.existing_english_debate_title),
        "traduction_du_débat_requise": not bool(result.existing_english_debate_title),
        "url_traduction_anglaise_débat": (
            existing_english_debate_record.url if existing_english_debate_record else ""
        ),
        "revision_traduction_anglaise_débat": (
            existing_english_debate_record.revision_id
            if existing_english_debate_record
            else None
        ),
        "vérification_traduction_anglaise_débat_effectuée_le": (
            existing_english_debate_record.fetched_at
            if existing_english_debate_record
            else ""
        ),
        "arguments_niveau_1_pour": len(result.roots_pro),
        "arguments_niveau_1_contre": len(result.roots_con),
        "arguments_niveau_1_total": len(roots),
        "pages_arguments_uniques": len(nodes),
        "pages_arguments_a_traduire": sum(
            row["traduction_anglaise_requise"] for row in node_rows
        ),
        "occurrences_argumentatives_depliees_par_chemins": unfolded_occurrences,
        "occurrences_argumentatives": unfolded_occurrences,
        "relations_uniques": len(result.relations),
        "justifications": sum(edge.relation == "justification" for edge in result.relations),
        "objections": sum(edge.relation == "objection" for edge in result.relations),
        "niveau_minimal_maximal_pages_uniques": maximum_minimum_level,
        "niveau_maximal_occurrences": maximum_occurrence_level,
        "profondeur_maximale_en_aretes": maximum_edge_depth,
        "profondeur_maximale": maximum_minimum_level,
        "pages_uniques_par_niveau_minimal": dict(sorted(pages_by_minimum_level.items())),
        "arguments_par_niveau": dict(sorted(pages_by_minimum_level.items())),
        "occurrences_depliees_par_niveau": dict(sorted(occurrences_by_level.items())),
        "occurrences_par_niveau": dict(sorted(occurrences_by_level.items())),
        "occurrences_reutilisees_par_niveau": reused_occurrences_by_level,
        "pages_concernees_par_reutilisation_au_niveau": reused_pages_by_level,
        "pages_avec_relations_sortantes": sum(row["nombre_enfants"] > 0 for row in node_rows),
        "pages_sans_sortie_dans_graphe_extrait": pages_without_outgoing,
        "pages_terminales_reelles": actual_terminals,
        "pages_terminales": pages_without_outgoing,
        "pages_réutilisées_plusieurs_fois": reused if not cycle_nodes else None,
        "frontières_débat_détaillé": boundaries,
        "nombre_frontières_débat_détaillé": len(boundaries),
        "relations_locales_ignorees_aux_frontières": ignored_frontier_relations,
        "frontières_traduction_anglaise_existante": existing_english_translations,
        "nombre_frontières_traduction_anglaise_existante": len(
            existing_english_translations
        ),
        "relations_locales_ignorees_traductions_anglaises_existantes": (
            ignored_existing_translation_relations
        ),
        "limite_profondeur": result.crawl_options.get("max_depth"),
        "relations_ignorees_limite_profondeur": sum(result.depth_frontiers.values()),
        "graphe_sans_cycle": not cycle_nodes,
        "nœuds_dans_cycles": cycle_nodes,
        "pages_manquantes": result.missing_pages,
        "avertissements": len(result.warnings),
        "informations_frontières": len(result.frontier_information),
    }
    return {
        "metadata": metadata,
        "arguments_pour_niveau_1": result.roots_pro,
        "arguments_contre_niveau_1": result.roots_con,
        "aliases_et_redirections_observés": {
            alias: canonical
            for alias, canonical in sorted(result.aliases.items(), key=lambda item: item[0].casefold())
            if alias != canonical
        },
        "noeuds": node_rows,
        "relations": relation_rows,
        "branches_niveau_1": branch_rows,
        "informations_frontières": result.frontier_information,
        "frontières_traduction_anglaise_existante": (
            result.existing_english_translation_frontiers
        ),
        "frontières_profondeur": result.depth_frontiers,
        "warnings": result.warnings,
    }

# ---------------------------------------------------------------------------
# Export and independent checks
# ---------------------------------------------------------------------------


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return value or "debat"


def _csv_value(value: Any) -> str | int | None:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def audit_graph(graph: Mapping[str, Any]) -> list[dict[str, Any]]:
    metadata = graph["metadata"]
    nodes = {row["titre"]: row for row in graph["noeuds"]}
    relations = graph["relations"]
    roots = graph["arguments_pour_niveau_1"] + graph["arguments_contre_niveau_1"]
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: Any = "") -> None:
        checks.append({"contrôle": name, "ok": bool(ok), "détail": detail})

    edge_keys = {(r["source"], r["relation"], r["cible"]) for r in relations}
    check("racines uniques", len(roots) == len(set(roots)), len(roots))
    check(
        "débat déjà traduit sans parcours argumentatif",
        not metadata.get("traduction_anglaise_débat_vérifiée")
        or (not roots and not nodes and not relations),
        metadata.get("traduction_anglaise_débat_existante"),
    )
    check("racines présentes", all(root in nodes for root in roots))
    check("nœuds uniques", len(nodes) == len(graph["noeuds"]), len(nodes))
    check("relations uniques", len(edge_keys) == len(relations), len(edge_keys))
    check(
        "types de relation",
        all(r["relation"] in {"justification", "objection"} for r in relations),
    )
    missing_endpoints = [
        (r["source"], r["cible"])
        for r in relations
        if r["source"] not in nodes or r["cible"] not in nodes
    ]
    check("endpoints présents", not missing_endpoints, missing_endpoints[:10])
    check("graphe sans cycle", bool(metadata["graphe_sans_cycle"]), metadata["nœuds_dans_cycles"])
    boundary_bad = [
        row["titre"]
        for row in graph["noeuds"]
        if row["débat_détaillé"] and row["nombre_enfants"] != 0
    ]
    check("frontières sans sorties", not boundary_bad, boundary_bad)
    depth_boundary_bad = [
        row["titre"]
        for row in graph["noeuds"]
        if row["statut"] == "frontière_profondeur" and row["nombre_enfants"] != 0
    ]
    check("frontières de profondeur sans sorties", not depth_boundary_bad, depth_boundary_bad)
    existing_translation_boundary_bad = [
        row["titre"]
        for row in graph["noeuds"]
        if row["statut"] == "frontière_traduction_anglaise_existante"
        and row["nombre_enfants"] != 0
    ]
    check(
        "frontières de traduction anglaise sans sorties",
        not existing_translation_boundary_bad,
        existing_translation_boundary_bad,
    )
    check(
        "compteur nœuds",
        metadata["pages_arguments_uniques"] == len(nodes),
        f"{metadata['pages_arguments_uniques']}/{len(nodes)}",
    )
    check(
        "compteur relations",
        metadata["relations_uniques"] == len(relations),
        f"{metadata['relations_uniques']}/{len(relations)}",
    )
    check(
        "compteurs justification/objection",
        metadata["justifications"] + metadata["objections"] == len(relations),
    )
    pages_by_level = metadata["pages_uniques_par_niveau_minimal"]
    check(
        "compteur des arguments par niveau",
        metadata["arguments_par_niveau"] == pages_by_level,
        metadata["arguments_par_niveau"],
    )
    occurrences_by_level = metadata["occurrences_depliees_par_niveau"]
    check(
        "somme des pages par niveau minimal",
        sum(pages_by_level.values()) == len(nodes),
        f"{sum(pages_by_level.values())}/{len(nodes)}",
    )
    unfolded = metadata["occurrences_argumentatives_depliees_par_chemins"]
    check(
        "somme des occurrences dépliées par niveau",
        sum(occurrences_by_level.values()) == unfolded,
        f"{sum(occurrences_by_level.values())}/{unfolded}",
    )
    max_occurrence_level = metadata["niveau_maximal_occurrences"]
    max_edge_depth = metadata["profondeur_maximale_en_aretes"]
    check(
        "cohérence niveau maximal et profondeur en arêtes",
        max_edge_depth == max(max_occurrence_level - 1, 0),
        f"niveau={max_occurrence_level}; profondeur={max_edge_depth}",
    )
    check(
        "niveau minimal maximal inférieur ou égal au niveau maximal des occurrences",
        metadata["niveau_minimal_maximal_pages_uniques"] <= max_occurrence_level,
        (
            metadata["niveau_minimal_maximal_pages_uniques"],
            max_occurrence_level,
        ),
    )
    check(
        "compteur des pages sans sortie",
        metadata["pages_sans_sortie_dans_graphe_extrait"]
        == sum(row["nombre_enfants"] == 0 for row in graph["noeuds"]),
        metadata["pages_sans_sortie_dans_graphe_extrait"],
    )
    check(
        "compteur des feuilles réelles",
        metadata["pages_terminales_reelles"]
        == sum(row["statut"] == "terminal" for row in graph["noeuds"]),
        metadata["pages_terminales_reelles"],
    )
    check(
        "relations locales ignorées aux frontières",
        metadata["relations_locales_ignorees_aux_frontières"]
        == sum(row["relations_locales_ignorees_frontiere"] for row in graph["noeuds"]),
        metadata["relations_locales_ignorees_aux_frontières"],
    )
    check(
        "traductions anglaises existantes",
        metadata["frontières_traduction_anglaise_existante"]
        == {
            row["titre"]: row["traduction_anglaise_existante"]
            for row in graph["noeuds"]
            if row["traduction_anglaise_existante_vérifiée"]
        },
        metadata["frontières_traduction_anglaise_existante"],
    )
    check(
        "compteur des arguments à traduire",
        metadata["pages_arguments_a_traduire"]
        == sum(row["traduction_anglaise_requise"] for row in graph["noeuds"]),
        metadata["pages_arguments_a_traduire"],
    )
    check(
        "relations ignorées aux traductions anglaises existantes",
        metadata["relations_locales_ignorees_traductions_anglaises_existantes"]
        == sum(
            row["relations_locales_ignorees_traduction_anglaise"]
            for row in graph["noeuds"]
        ),
        metadata["relations_locales_ignorees_traductions_anglaises_existantes"],
    )
    check(
        "relations ignorées à la limite de profondeur",
        metadata["relations_ignorees_limite_profondeur"]
        == sum(graph.get("frontières_profondeur", {}).values()),
        metadata["relations_ignorees_limite_profondeur"],
    )
    check("aucune page manquante", not metadata["pages_manquantes"], metadata["pages_manquantes"])
    return checks


def _safe_snapshot_filename(index: int, title: str) -> str:
    short_slug = slugify(title)[:72] or "argument"
    digest = hashlib.sha256(title.encode("utf-8")).hexdigest()[:12]
    return f"{index:04d}_{short_slug}_{digest}.wiki"


def _record_manifest_row(record: PageRecord, relative_path: str, payload: bytes) -> dict[str, Any]:
    return {
        "requested_title": record.requested_title,
        "canonical_title": record.canonical_title,
        "relative_path": relative_path,
        "revision_id": record.revision_id,
        "revision_timestamp": record.revision_timestamp,
        "url": record.url,
        "redirect_chain": record.redirect_chain,
        "fetched_at": record.fetched_at,
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _write_snapshot(result: CrawlResult, snapshot_dir: Path, extraction_date: str) -> Path:
    pages_dir = snapshot_dir / "pages"
    arguments_dir = pages_dir / "arguments"
    arguments_dir.mkdir(parents=True, exist_ok=True)

    debate_path = pages_dir / "debate.wiki"
    debate_payload = result.debate_record.text.encode("utf-8")
    debate_path.write_bytes(debate_payload)
    debate_row = _record_manifest_row(
        result.debate_record,
        debate_path.relative_to(snapshot_dir).as_posix(),
        debate_payload,
    )

    argument_rows: list[dict[str, Any]] = []
    for index, title in enumerate(sorted(result.page_records, key=str.casefold), start=1):
        record = result.page_records[title]
        filename = _safe_snapshot_filename(index, title)
        path = arguments_dir / filename
        payload = record.text.encode("utf-8")
        path.write_bytes(payload)
        argument_rows.append(
            _record_manifest_row(record, path.relative_to(snapshot_dir).as_posix(), payload)
        )

    manifest = {
        "schema": "wikidebia-graph-snapshot-1.0",
        "kit_version": KIT_VERSION,
        "extractor_version": GRAPH_EXTRACT_VERSION,
        "extraction_date": extraction_date,
        "debate": debate_row,
        "arguments": argument_rows,
        "crawl_options": result.crawl_options,
        "counts": {
            "debate_pages": 1,
            "argument_pages": len(argument_rows),
            "total_pages": len(argument_rows) + 1,
        },
    }
    manifest_path = snapshot_dir / "snapshot_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest_path


def _iter_generated_files(output_dir: Path, *, exclude: set[Path]) -> list[Path]:
    files: list[Path] = []
    for path in output_dir.rglob("*"):
        if not path.is_file() or path in exclude:
            continue
        relative = path.relative_to(output_dir)
        if relative.parts and relative.parts[0] == ".cache_pages":
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(output_dir).as_posix())


def write_outputs(
    graph: Mapping[str, Any],
    result: CrawlResult,
    *,
    output_dir: Path,
    slug: str,
    extraction_date: str,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{slug}_graphe_recursif_{extraction_date}"
    graph_path = output_dir / f"{prefix}.json"
    nodes_path = output_dir / f"{slug}_noeuds_{extraction_date}.csv"
    relations_path = output_dir / f"{slug}_relations_{extraction_date}.csv"
    report_path = output_dir / f"{slug}_rapport_graphe_{extraction_date}.md"
    audit_path = output_dir / f"{slug}_audit_graphe_{extraction_date}.md"
    manifest_path = output_dir / f"{slug}_manifest_sha256_{extraction_date}.json"
    zip_path = output_dir / f"{prefix}_audite.zip"
    snapshot_dir = output_dir / "snapshot"

    if snapshot_dir.exists():
        import shutil
        shutil.rmtree(snapshot_dir)
    snapshot_manifest_path = _write_snapshot(result, snapshot_dir, extraction_date)

    graph_payload = dict(graph)
    graph_payload["metadata"] = dict(graph_payload["metadata"])
    graph_payload["metadata"]["date_extraction"] = extraction_date
    graph_payload["metadata"]["snapshot_manifest"] = snapshot_manifest_path.relative_to(output_dir).as_posix()
    graph_path.write_text(
        json.dumps(graph_payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    node_fields = list(graph["noeuds"][0].keys()) if graph["noeuds"] else []
    with nodes_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=node_fields)
        writer.writeheader()
        for row in graph["noeuds"]:
            writer.writerow({key: _csv_value(value) for key, value in row.items()})

    relation_fields = list(graph["relations"][0].keys()) if graph["relations"] else []
    with relations_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=relation_fields)
        writer.writeheader()
        for row in graph["relations"]:
            writer.writerow({key: _csv_value(value) for key, value in row.items()})

    m = graph["metadata"]
    report_lines = [
        f"# Graphe argumentatif — « {m['débat']} »",
        "",
        f"Date d’extraction : {extraction_date}",
        f"Extracteur : {GRAPH_EXTRACT_VERSION} (kit {KIT_VERSION})",
        "",
        "## Vérification préalable de la page Débat",
        "",
        (
            "La page Débat est déjà traduite : "
            f"**{m['traduction_anglaise_débat_existante']}**. "
            "Aucun argument n'a été programmé pour traduction."
            if m["traduction_anglaise_débat_vérifiée"]
            else "Aucune traduction anglaise existante de la page Débat n'a été vérifiée."
        ),
        "",
        "## Statistiques",
        "",
        "### Nombre d’arguments par niveau",
        "",
        "| Niveau | Pages uniques | Occurrences |",
        "|---:|---:|---:|",
    ]
    levels = sorted(
        set(m["pages_uniques_par_niveau_minimal"]) | set(m["occurrences_par_niveau"]),
        key=int,
    )
    for level in levels:
        unique = m["pages_uniques_par_niveau_minimal"].get(level, 0)
        occurrences = m["occurrences_par_niveau"].get(level, 0)
        report_lines.append(f"| {level} | {unique} | {occurrences} |")
    report_lines.extend(
        [
            "",
            f"- Pages uniques : **{m['pages_arguments_uniques']}**",
            f"- Pages Argument restant à traduire : **{m['pages_arguments_a_traduire']}**",
            (
                "- Occurrences dépliées par chemins : "
                f"**{m['occurrences_argumentatives_depliees_par_chemins']}**"
            ),
            f"- Relations uniques : **{m['relations_uniques']}**",
            f"- Justifications : **{m['justifications']}**",
            f"- Objections : **{m['objections']}**",
            (
                "- Niveau minimal maximal d’une page unique : "
                f"**{m['niveau_minimal_maximal_pages_uniques']}**"
            ),
            f"- Niveau maximal d’une occurrence : **{m['niveau_maximal_occurrences']}**",
            (
                "- Profondeur maximale en nombre d’arêtes : "
                f"**{m['profondeur_maximale_en_aretes']}**"
            ),
            (
                "- Pages sans sortie dans le graphe extrait : "
                f"**{m['pages_sans_sortie_dans_graphe_extrait']}**"
            ),
            f"- Feuilles réelles : **{m['pages_terminales_reelles']}**",
            f"- Pages réutilisées : **{m['pages_réutilisées_plusieurs_fois']}**",
            (
                "- Frontières avec traduction anglaise existante : "
                f"**{m['nombre_frontières_traduction_anglaise_existante']}**"
            ),
            f"- Graphe sans cycle : **{'oui' if m['graphe_sans_cycle'] else 'non'}**",
            "",
            (
                "Une occurrence dépliée correspond à un chemin depuis un argument de niveau 1. "
                "Une même page peut donc produire plusieurs occurrences et apparaître à un niveau "
                "supérieur à son niveau minimal. La profondeur compte les arêtes : une occurrence "
                "de niveau 8 se trouve à une profondeur de 7."
            ),
        ]
    )
    report_lines.extend(["", "## Frontières de profondeur", ""])
    if m["limite_profondeur"] is None:
        report_lines.append("Aucune limite de profondeur demandée.")
    else:
        report_lines.extend(
            [
                f"Limite demandée : **{m['limite_profondeur']} arête(s)**.",
                (
                    "Relations vers le niveau suivant non suivies : "
                    f"**{m['relations_ignorees_limite_profondeur']}**."
                ),
            ]
        )
        if result.depth_frontiers:
            report_lines.append("")
            for page, count in result.depth_frontiers.items():
                report_lines.append(f"- **{page}** — {count} relation(s) non suivie(s)")
    report_lines.extend(
        [
            "",
            "## Réutilisations sans nouvelle page au niveau considéré",
            "",
        ]
    )
    reused_by_level = m["occurrences_reutilisees_par_niveau"]
    if reused_by_level:
        for level, count in reused_by_level.items():
            pages = m["pages_concernees_par_reutilisation_au_niveau"].get(level, [])
            sample = "; ".join(pages[:8])
            suffix = "" if len(pages) <= 8 else f"; … ({len(pages)} pages concernées)"
            report_lines.append(
                f"- Niveau {level} : **{count}** occurrence(s) réutilisée(s)"
                + (f" — {sample}{suffix}" if sample else "")
            )
    else:
        report_lines.append("Aucune réutilisation supplémentaire.")
    report_lines.extend(
        [
            "",
            "## Snapshot de provenance",
            "",
            f"Le wikicode de la page Débat et des {m['pages_arguments_uniques']} pages Argument est conservé dans `snapshot/pages/`.",
            "Le fichier `snapshot/snapshot_manifest.json` associe chaque titre à sa révision, son URL, son empreinte SHA-256 et son fichier local.",
            "",
            "## Frontières « traduction anglaise existante »",
            "",
        ]
    )
    if m["frontières_traduction_anglaise_existante"]:
        for page, english_title in m["frontières_traduction_anglaise_existante"].items():
            ignored = next(
                row["relations_locales_ignorees_traduction_anglaise"]
                for row in graph["noeuds"]
                if row["titre"] == page
            )
            detail = f" — {ignored} relation(s) locale(s) non suivie(s)" if ignored else ""
            report_lines.append(f"- **{page}** → {english_title}{detail}")
        report_lines.extend(
            [
                "",
                (
                    "Total des relations locales non suivies à ces frontières : "
                    f"**{m['relations_locales_ignorees_traductions_anglaises_existantes']}**."
                ),
            ]
        )
    else:
        report_lines.append("Aucune.")
    report_lines.extend(
        [
            "",
            "## Frontières « débat détaillé »",
            "",
        ]
    )
    if m["frontières_débat_détaillé"]:
        for page, debate in m["frontières_débat_détaillé"].items():
            ignored = next(
                row["relations_locales_ignorees_frontiere"]
                for row in graph["noeuds"]
                if row["titre"] == page
            )
            detail = f" — {ignored} relation(s) locale(s) non suivie(s)" if ignored else ""
            report_lines.append(f"- **{page}** → {debate}{detail}")
        report_lines.append("")
        report_lines.append(
            "Total des relations locales non suivies aux frontières : "
            f"**{m['relations_locales_ignorees_aux_frontières']}**."
        )
    else:
        report_lines.append("Aucune.")
    report_lines.extend(["", "## Informations sur les frontières", ""])
    frontier_information = graph.get("informations_frontières", [])
    if frontier_information:
        report_lines.extend(f"- {info}" for info in frontier_information)
    else:
        report_lines.append("Aucune.")
    report_lines.extend(["", "## Avertissements réels", ""])
    warnings = graph.get("warnings", [])
    if warnings:
        report_lines.extend(f"- {warning}" for warning in warnings)
    else:
        report_lines.append("Aucun.")
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8", newline="\n")

    checks = audit_graph(graph)
    snapshot_data = json.loads(snapshot_manifest_path.read_text(encoding="utf-8"))
    snapshot_rows = [snapshot_data["debate"], *snapshot_data["arguments"]]
    snapshot_hashes_ok = all(
        hashlib.sha256((snapshot_dir / row["relative_path"]).read_bytes()).hexdigest() == row["sha256"]
        for row in snapshot_rows
    )
    checks.extend(
        [
            {
                "contrôle": "snapshot complet",
                "ok": snapshot_data["counts"]["argument_pages"] == m["pages_arguments_uniques"],
                "détail": snapshot_data["counts"],
            },
            {
                "contrôle": "empreintes du snapshot",
                "ok": snapshot_hashes_ok,
                "détail": len(snapshot_rows),
            },
        ]
    )
    audit_ok = all(check["ok"] for check in checks)
    audit_lines = [
        f"# Audit du graphe — « {m['débat']} »",
        "",
        f"**Résultat : {'RÉUSSI' if audit_ok else 'ÉCHEC'}**",
        "",
        "| Contrôle | Résultat | Détail |",
        "|---|---:|---|",
    ]
    for check in checks:
        detail = str(check["détail"]).replace("|", "\\|").replace("\n", " ")
        audit_lines.append(
            f"| {check['contrôle']} | {'OK' if check['ok'] else 'ÉCHEC'} | {detail} |"
        )
    audit_path.write_text("\n".join(audit_lines) + "\n", encoding="utf-8", newline="\n")

    generated_before_manifest = _iter_generated_files(output_dir, exclude={manifest_path, zip_path})
    manifest_rows: list[dict[str, Any]] = []
    for path in generated_before_manifest:
        payload = path.read_bytes()
        manifest_rows.append(
            {
                "path": path.relative_to(output_dir).as_posix(),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size_bytes": len(payload),
            }
        )
    package_manifest = {
        "schema": "wikidebia-graph-extraction-package-1.0",
        "kit_version": KIT_VERSION,
        "extractor_version": GRAPH_EXTRACT_VERSION,
        "debate": m["débat"],
        "extraction_date": extraction_date,
        "audit_status": "passed" if audit_ok else "failed",
        "declared_file_count": len(manifest_rows),
        "files": manifest_rows,
    }
    manifest_path.write_text(
        json.dumps(package_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    generated_for_zip = _iter_generated_files(output_dir, exclude={zip_path})
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in generated_for_zip:
            archive.write(path, arcname=path.relative_to(output_dir).as_posix())

    return {
        "graph": graph_path,
        "nodes": nodes_path,
        "relations": relations_path,
        "report": report_path,
        "audit": audit_path,
        "snapshot_manifest": snapshot_manifest_path,
        "manifest": manifest_path,
        "zip": zip_path,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Construire récursivement un graphe argumentatif Wikidéb'IA (lecture seule)."
    )
    parser.add_argument("--debate", required=True, help="Titre exact de la page Débat")
    parser.add_argument("--family", default="wikidebates")
    parser.add_argument("--lang", default="fr")
    parser.add_argument("--family-file", type=Path)
    parser.add_argument("--pywikibot-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("graph-output"))
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--slug", help="Préfixe des fichiers de sortie")
    parser.add_argument("--date", dest="extraction_date", default=dt.date.today().isoformat())
    parser.add_argument("--login", action="store_true", help="Se connecter avant les lectures")
    parser.add_argument("--force-refresh", action="store_true", help="Ignorer le cache local")
    parser.add_argument("--allow-missing", action="store_true")
    parser.add_argument(
        "--max-depth",
        type=int,
        help="Profondeur maximale en arêtes; 0 conserve uniquement les arguments de niveau 1",
    )
    parser.add_argument("--max-pages", type=int, default=5000)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--retry-delay", type=float, default=2.0)
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument(
        "--machine-readable",
        action="store_true",
        help="Émettre une seule ligne JSON sur la sortie standard",
    )
    parser.add_argument(
        "--follow-local-relations-at-dedicated-debate",
        "--follow-local-relations-at-detailed-debate",
        action="store_true",
        help=(
            "Ne traite pas les pages 'débat dédié' comme des feuilles. "
            "Le débat sous-jacent n'est toutefois jamais ouvert automatiquement."
        ),
    )
    parser.add_argument(
        "--follow-local-relations-at-existing-english-translation",
        action="store_true",
        help=(
            "Mode de diagnostic : suit les relations locales même lorsqu'une page "
            "déclare déjà une traduction anglaise."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = args.output_dir.resolve()
    cache_dir = (args.cache_dir or (output_dir / ".cache_pages")).resolve()
    cache = JsonPageCache(cache_dir, force_refresh=args.force_refresh)
    client = PywikibotPageClient(
        family=args.family,
        lang=args.lang,
        family_file=args.family_file,
        pywikibot_dir=args.pywikibot_dir,
        cache=cache,
        login=args.login,
        retries=args.retries,
        retry_delay=args.retry_delay,
    )
    english_client = PywikibotPageClient(
        family=args.family,
        lang="en",
        family_file=args.family_file,
        pywikibot_dir=args.pywikibot_dir,
        cache=JsonPageCache(cache_dir / "_english", force_refresh=args.force_refresh),
        login=args.login,
        retries=args.retries,
        retry_delay=args.retry_delay,
    )
    result = crawl_graph(
        client,
        debate_title=args.debate,
        english_client=english_client,
        stop_on_detailed_debate=not args.follow_local_relations_at_dedicated_debate,
        stop_on_existing_english_translation=(
            not args.follow_local_relations_at_existing_english_translation
        ),
        max_depth=args.max_depth,
        max_pages=args.max_pages,
        allow_missing=args.allow_missing,
        progress_every=args.progress_every,
    )
    graph = analyze_graph(result)
    slug = args.slug or slugify(result.debate_title)
    paths = write_outputs(
        graph,
        result,
        output_dir=output_dir,
        slug=slug,
        extraction_date=args.extraction_date,
    )
    package_manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    audit_ok = package_manifest.get("audit_status") == "passed"
    payload = {
        "status": "passed" if audit_ok else "failed",
        "kit_version": KIT_VERSION,
        "extractor_version": GRAPH_EXTRACT_VERSION,
        "metadata": graph["metadata"],
        "output_dir": str(output_dir),
        "files": {name: str(path) for name, path in paths.items()},
    }
    if args.machine_readable:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if audit_ok else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrompu. Le cache par page permet de reprendre la même commande.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"ERREUR: {exc}", file=sys.stderr)
        raise SystemExit(1)
