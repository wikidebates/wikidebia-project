#!/usr/bin/env python3
"""Independent, anonymous HTTP verification of a bilingual MediaWiki publication.

An edit API success is NEVER a public-visibility proof. This module uses fresh
anonymous HTTPS GET requests, no Pywikibot Site, cookies, bot tokens, or shared
authenticated HTTP session. English pages must appear at their exact titles;
each French interlanguage link must be present in public wikitext AND in the
rendered, publicly accessible HTML, pointing at the same English page.

A failed or incomplete inspection produces a signed diagnostic report, never
a successful publication receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import html
from html.parser import HTMLParser
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlencode, urljoin, urlsplit
from urllib.request import Request, build_opener

from wikidebia_corpus_build import load_json, sha256_file, validate_debate_id, write_json
from wikidebia_graph_extract import iter_templates, normalize_key

REPORT_SCHEMA = "wikidebia-public-visibility-report-1.0"
PUBLIC_DOMAINS = {"en": "en.wikidebates.org", "fr": "fr.wikidebates.org"}
VERIFIED = "publié et vérifié"
PARTIAL = "publication partielle"
UNCONFIRMED = "visibilité publique non confirmée"


class PublicVisibilityError(RuntimeError):
    pass


class PublicUnavailable(PublicVisibilityError):
    pass


class PublicMissing(PublicVisibilityError):
    pass


def _sha_object(value: Mapping[str, Any]) -> str:
    data = json.dumps(dict(value), sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _sha_text(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _title(value: str) -> str:
    return unicodedata.normalize("NFC", value.replace("_", " ").strip())


def _public_url(language: str, title: str) -> str:
    if language not in PUBLIC_DOMAINS or not title or any(ch in title for ch in "#\r\n|"):
        raise PublicVisibilityError("Langue ou titre public non conforme")
    return ("https://" + PUBLIC_DOMAINS[language] + "/wiki/"
            + quote(title.replace(" ", "_"), safe="()-,.'~"))


def _verify_host(url: str, language: str) -> None:
    location = urlsplit(url)
    if (location.scheme != "https"
            or location.hostname != PUBLIC_DOMAINS[language]
            or location.username or location.password or location.port):
        raise PublicUnavailable("Redirection hors du wiki public attendu")


class _PublicDocument(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.heading_parts: list[str] = []
        self.in_heading = 0
        self.heading_seen = False
        self.content_seen = False
        self.missing_marker = False
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        properties = dict(attrs)
        ident = str(properties.get("id") or "")
        classes = str(properties.get("class") or "").split()
        if tag == "h1" and ident == "firstHeading":
            self.in_heading = 1
            self.heading_seen = True
        elif self.in_heading:
            self.in_heading += 1
        if "mw-parser-output" in classes or ident == "mw-content-text":
            self.content_seen = True
        if ident in {"noarticletext", "mw-newarticletext"} or "noarticletext" in classes:
            self.missing_marker = True
        if tag == "a" and properties.get("href"):
            self.links.append(str(properties["href"]))

    def handle_endtag(self, tag: str) -> None:
        if self.in_heading and tag in {"h1", "span", "b", "i", "em", "strong"}:
            self.in_heading = max(0, self.in_heading - 1)

    def handle_data(self, data: str) -> None:
        if self.in_heading:
            self.heading_parts.append(data)

    @property
    def heading(self) -> str:
        return _title(html.unescape("".join(self.heading_parts)))


class AnonymousMediaWiki:
    """Separate anonymous urllib opener; never imports an authenticated client."""

    def __init__(self, *, timeout: float = 15.0):
        self.timeout = timeout
        self.opener = build_opener()
        self.headers = {
            "User-Agent": "WikidebiaPublicVisibility/1.0 (anonymous read-only audit)",
            "Accept": "text/html, application/json;q=0.8",
        }

    def _read(self, language: str, url: str) -> bytes:
        _verify_host(url, language)
        request = Request(url, headers=self.headers, method="GET")
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                final_url = response.geturl()
                _verify_host(final_url, language)
                status = response.status
                if status == 404:
                    raise PublicMissing("HTTP 404")
                if status != 200:
                    raise PublicUnavailable(f"HTTP {status}")
                # Bounded read prevents pathological HTML/API replies.
                data = response.read(8_000_001)
                if len(data) > 8_000_000:
                    raise PublicUnavailable("Réponse publique trop volumineuse")
                return data
        except HTTPError as exc:
            if exc.code in {404, 410}:
                raise PublicMissing(f"HTTP {exc.code}") from exc
            raise PublicUnavailable(f"HTTP {exc.code}") from exc
        except (URLError, OSError, TimeoutError) as exc:
            raise PublicUnavailable(f"Lecture HTTPS impossible : {exc}") from exc

    def html(self, language: str, title: str) -> _PublicDocument:
        content = self._read(language, _public_url(language, title))
        try:
            value = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PublicUnavailable("HTML public non UTF-8") from exc
        document = _PublicDocument()
        document.feed(value)
        if document.missing_marker:
            raise PublicMissing("Page inexistante dans le HTML public")
        if not document.heading_seen or not document.content_seen:
            raise PublicUnavailable("HTML public incomplet ou non MediaWiki")
        if document.heading != _title(title):
            raise PublicMissing(
                f"Titre HTML inattendu : {document.heading!r} au lieu de {_title(title)!r}"
            )
        return document

    def pages(self, language: str, titles: list[str]) -> dict[str, dict[str, Any]]:
        if len(titles) > 50 or len(set(titles)) != len(titles):
            raise PublicVisibilityError("Lot public invalide (>50 ou doublons)")
        params = {
            "action": "query", "format": "json", "formatversion": "2",
            "prop": "revisions", "rvprop": "ids|content", "rvslots": "main",
            "titles": "|".join(titles),
        }
        url = ("https://" + PUBLIC_DOMAINS[language]
               + "/w/api.php?" + urlencode(params))
        try:
            result = json.loads(self._read(language, url).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise PublicUnavailable("Réponse JSON anonyme illisible") from exc
        query = result.get("query") if isinstance(result, dict) else None
        if not isinstance(query, dict) or not isinstance(query.get("pages"), list):
            raise PublicUnavailable("Réponse MediaWiki publique sans inventaire de pages")
        normalized: dict[str, str] = {}
        for item in query.get("normalized") or []:
            if not isinstance(item, dict) or not item.get("from") or not item.get("to"):
                raise PublicUnavailable("Normalisation publique malformée")
            origin, target = str(item["from"]), str(item["to"])
            if origin in normalized:
                raise PublicUnavailable("Normalisation publique en double")
            normalized[origin] = target
        by_title: dict[str, dict[str, Any]] = {}
        for page in query["pages"]:
            if not isinstance(page, dict) or not page.get("title"):
                raise PublicUnavailable("Page publique malformée")
            name = str(page["title"])
            if name in by_title:
                raise PublicUnavailable("Page publique dupliquée")
            by_title[name] = page
        output: dict[str, dict[str, Any]] = {}
        for title in titles:
            target = normalized.get(title, title)
            page = by_title.get(target)
            if page is None:
                raise PublicUnavailable(f"Réponse publique incomplète : {title}")
            exists = ("missing" not in page and "invalid" not in page
                      and type(page.get("pageid")) is int and page["pageid"] > 0)
            if not exists:
                output[title] = {"exists": False}
                continue
            revisions = page.get("revisions")
            if not isinstance(revisions, list) or len(revisions) != 1:
                raise PublicUnavailable(f"Révision publique absente : {title}")
            version = revisions[0]
            if (not isinstance(version, dict) or type(version.get("revid")) is not int
                    or version["revid"] <= 0):
                raise PublicUnavailable(f"Identifiant de révision publique absent : {title}")
            main = (version.get("slots") or {}).get("main") or {}
            raw = main.get("content", main.get("*", version.get("*")))
            if not isinstance(raw, str):
                raise PublicUnavailable(f"Wikitexte public indisponible : {title}")
            output[title] = {
                "exists": True, "pageid": page["pageid"],
                "revision_id": version["revid"], "text": raw,
                "canonical_title": target, "redirect": bool(page.get("redirect")),
            }
        return output


def _main_template_present(text: str, page_type: str, language: str) -> bool:
    model = ("débat" if language == "fr" else "debate") if page_type == "debate" else "argument"
    calls = [call for call in iter_templates(text) if normalize_key(call.name) == normalize_key(model)]
    return len(calls) == 1


def _interlanguage_target(text: str, page_type: str) -> str:
    """Read the actual French interlanguage parameter or redirect language link."""
    if re.match(r"^\s*#\s*(?:REDIRECT|REDIRECTION)\b", text, re.I):
        targets = re.findall(r"\[\[\s*en\s*:\s*([^\]|#]+)(?:\|[^\]]*)?\]\]", text, re.I)
        return _title(targets[0]) if len(targets) == 1 else ""
    model = "débat" if page_type == "debate" else "argument"
    calls = [call for call in iter_templates(text) if normalize_key(call.name) == normalize_key(model)]
    if len(calls) != 1:
        return ""
    link = calls[0].get("interlangue")
    targets = [
        call for call in iter_templates(link)
        if normalize_key(call.name) == "lien interlangue"
        and normalize_key(call.get("langue", "lang", "language")) == "en"
    ]
    if len(targets) != 1:
        return ""
    title = targets[0].get("page", "title")
    return _title(title) if title and "#" not in title else ""


def _html_links_to_english(document: _PublicDocument, source_url: str, expected_title: str) -> bool:
    target = _title(expected_title)
    for link in document.links:
        full = urlsplit(urljoin(source_url, html.unescape(link)))
        if full.hostname != PUBLIC_DOMAINS["en"] or full.scheme != "https":
            continue
        link_title: str | None = None
        if full.path.startswith("/wiki/"):
            link_title = unquote(full.path[len("/wiki/"):])
        elif full.path == "/w/index.php":
            links = parse_qs(full.query).get("title") or []
            if len(links) == 1:
                link_title = links[0]
        if link_title is not None and _title(link_title) == target:
            return True
    return False


def _expected_pages(
    english_plan: Mapping[str, Any], french_plan: Mapping[str, Any],
    late_reuse: Mapping[str, Any] | None,
) -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    english: dict[str, dict[str, str]] = {}
    for action in english_plan.get("actions") or []:
        if not isinstance(action, dict):
            raise PublicVisibilityError("Action anglaise invalide")
        page_id = str(action.get("page_id") or "")
        title = str(action.get("title") or "")
        typ = str(action.get("page_type") or "")
        if (action.get("language") != "en" or action.get("operation") not in {"create", "skip", "update"}
                or not page_id or not title or typ not in {"debate", "argument"} or page_id in english):
            raise PublicVisibilityError("Inventaire anglais invalide ou dupliqué")
        english[page_id] = {
            "page_id": page_id, "title": title, "page_type": typ,
            "expected_sha256": str(action.get("desired_sha256") or ""),
            "operation": str(action["operation"]),
            "reused_sha256": str(action.get("remote_sha256") or ""),
        }
    french: dict[str, dict[str, str]] = {}
    operations = french_plan.get("operations") or {}
    for category in ("update", "skip"):
        for row in operations.get(category) or []:
            if not isinstance(row, dict) or row.get("language") != "fr":
                raise PublicVisibilityError("Opération française non conforme")
            page_id = str(row.get("page_id") or "")
            title = str(row.get("title") or "")
            typ = str(row.get("page_type") or "")
            if not page_id or not title or typ not in {"debate", "argument"} or page_id in french:
                raise PublicVisibilityError("Page française de plan invalide ou dupliquée")
            french[page_id] = {"page_id": page_id, "title": title, "page_type": typ}
    for frontier in (late_reuse or {}).get("frontiers") or []:
        page_id = str(frontier.get("page_id") or "")
        en_title = str(frontier.get("english_title") or "")
        fr_title = str(frontier.get("french_title") or "")
        typ = str(frontier.get("page_type") or "")
        if (not page_id or not en_title or not fr_title or typ not in {"debate", "argument"}
                or page_id in english or page_id in french):
            raise PublicVisibilityError("Frontière de réutilisation ambiguë")
        english[page_id] = {
            "page_id": page_id, "title": en_title, "page_type": typ,
            "expected_sha256": str(frontier.get("english_sha256") or ""),
            "operation": "reused_existing",
            "reused_sha256": "",
        }
        french[page_id] = {"page_id": page_id, "title": fr_title, "page_type": typ}
    if not english or len([x for x in english.values() if x["page_type"] == "debate"]) != 1:
        raise PublicVisibilityError("Débat anglais unique absent du plan")
    if set(english) != set(french):
        raise PublicVisibilityError("Chaque page anglaise doit avoir exactement une page française correspondante")
    if len({x["title"] for x in english.values()}) != len(english):
        raise PublicVisibilityError("Titres anglais dupliqués dans l'inventaire")
    if len({x["title"] for x in french.values()}) != len(french):
        raise PublicVisibilityError("Titres français dupliqués dans l'inventaire")
    return sorted(english.values(), key=lambda x: (x["page_type"] != "debate", x["page_id"])), french


def verify_public_visibility(
    debate_id: str,
    work_id: str,
    english_plan: Mapping[str, Any],
    french_plan: Mapping[str, Any],
    *,
    client: Any = None,
    late_reuse: Mapping[str, Any] | None = None,
    manifest_sha256: str = "",
) -> dict[str, Any]:
    """Perform fresh independent observations; never infer visibility from writes."""
    client = client if client is not None else AnonymousMediaWiki()
    english, french = _expected_pages(english_plan, french_plan, late_reuse)
    debate = next(row for row in english if row["page_type"] == "debate")
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "debate_id": debate_id, "work_id": work_id,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "access": "independent_anonymous_https_no_bot_session",
        "english_plan_sha256": english_plan.get("plan_sha256"),
        "french_plan_sha256": french_plan.get("plan_sha256"),
        "manifest_sha256": manifest_sha256,
        "public_debate_url": _public_url("en", debate["title"]),
        "public_debate_verified": False,
        "english_pages_expected": len(english),
        "english_pages_checked": 0,
        "english_pages_verified": 0,
        "french_links_expected": len(english),
        "french_links_checked": 0,
        "french_links_verified": 0,
        "issues": [],
        "remote_writes": 0,
    }
    issues: list[dict[str, str]] = report["issues"]
    concrete_error = False
    unavailable = False
    en_verified: set[str] = set()

    def record(kind: str, row: Mapping[str, str], reason: str, *, missing: bool) -> None:
        nonlocal concrete_error, unavailable
        concrete_error |= missing
        unavailable |= not missing
        issues.append({"kind": kind, "page_id": row["page_id"],
                       "title": row["title"], "reason": reason})

    def public_api(language: str, titles: list[str]) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        for start in range(0, len(titles), 50):
            batch = titles[start:start + 50]
            try:
                observed = client.pages(language, batch)
                if not isinstance(observed, dict) or set(observed) != set(batch):
                    raise PublicUnavailable("Inventaire API public incomplet")
                results.update(observed)
            except (PublicVisibilityError, OSError) as exc:
                for title in batch:
                    results[title] = {"unavailable": str(exc)}
        return results

    en_state = public_api("en", [row["title"] for row in english])
    for row in english:
        title = row["title"]
        report["english_pages_checked"] += 1
        visible = en_state[title]
        if visible.get("unavailable"):
            record("english_page", row, str(visible["unavailable"]), missing=False)
            continue
        if not visible.get("exists"):
            record("english_page", row, "Page introuvable dans l'API de lecture publique", missing=True)
            continue
        if visible.get("redirect") or re.match(
            r"^\s*#\s*(?:REDIRECT|REDIRECTION)\b", str(visible.get("text") or ""), re.I
        ):
            record("english_page", row, "Titre anglais redirigé au lieu de contenir la page prévue", missing=True)
            continue
        if not _main_template_present(visible["text"], row["page_type"], "en"):
            record("english_page", row, "Contenu public inattendu ou modèle principal absent", missing=True)
            continue
        actual_sha = _sha_text(visible["text"])
        hashes = {row["expected_sha256"]}
        if row["operation"] == "skip" and row["reused_sha256"]:
            hashes.add(row["reused_sha256"])
        if row["expected_sha256"] and actual_sha not in hashes:
            record("english_page", row, "Contenu public différent du plan attesté", missing=True)
            continue
        try:
            client.html("en", title)
        except PublicMissing as exc:
            record("english_page", row, str(exc), missing=True)
            continue
        except (PublicVisibilityError, OSError) as exc:
            record("english_page", row, str(exc), missing=False)
            continue
        en_verified.add(row["page_id"])
        report["english_pages_verified"] += 1
        if row["page_id"] == debate["page_id"]:
            report["public_debate_verified"] = True

    fr_state = public_api("fr", [french[row["page_id"]]["title"] for row in english])
    for row in english:
        fr = french[row["page_id"]]
        report["french_links_checked"] += 1
        observed = fr_state[fr["title"]]
        if observed.get("unavailable"):
            record("french_link", fr, str(observed["unavailable"]), missing=False)
            continue
        if not observed.get("exists"):
            record("french_link", fr, "Page française introuvable en lecture publique", missing=True)
            continue
        target = _interlanguage_target(observed.get("text", ""), fr["page_type"])
        if target != _title(row["title"]):
            record("french_link", fr, "Cible interlangue absente ou différente : " + repr(target), missing=True)
            continue
        try:
            doc = client.html("fr", fr["title"])
        except PublicMissing as exc:
            record("french_link", fr, str(exc), missing=True)
            continue
        except (PublicVisibilityError, OSError) as exc:
            record("french_link", fr, str(exc), missing=False)
            continue
        if not _html_links_to_english(doc, _public_url("fr", fr["title"]), row["title"]):
            record("french_link", fr, "Lien vers la page anglaise absent du HTML public", missing=True)
            continue
        if row["page_id"] not in en_verified:
            record("french_link", fr, "Cible anglaise non vérifiée publiquement", missing=False)
            continue
        report["french_links_verified"] += 1

    if concrete_error:
        report["status"] = PARTIAL
    elif unavailable:
        report["status"] = UNCONFIRMED
    else:
        if (not report["public_debate_verified"]
                or report["english_pages_verified"] != report["english_pages_expected"]
                or report["french_links_verified"] != report["french_links_expected"]):
            report["status"] = UNCONFIRMED
        else:
            report["status"] = VERIFIED
    report["report_sha256"] = _sha_object(report)
    return report


def check_or_record(
    state_dir: Path,
    debate_id: str,
    work_id: str,
    english_plan: Mapping[str, Any],
    french_plan: Mapping[str, Any],
    *,
    late_reuse: Mapping[str, Any] | None = None,
    manifest_sha256: str = "",
    client: Any = None,
) -> dict[str, Any]:
    """Always write the full report, including failures, before returning."""
    report = verify_public_visibility(
        debate_id, work_id, english_plan, french_plan, late_reuse=late_reuse,
        manifest_sha256=manifest_sha256, client=client,
    )
    write_json(state_dir / "public-visibility-report.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("debate_id")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    root = args.project_root.expanduser().resolve()
    validate_debate_id(args.debate_id)
    state = root / ".state/final-publication" / args.debate_id / args.work_id
    en_plan = load_json(state / "english-publication-plan.json", "plan anglais")
    fr_plan = load_json(state / "french-update-plan.json", "plan français")
    reuse_path = state / "late-existing-english-reuse.json"
    reuse = load_json(reuse_path, "réutilisation anglaise") if reuse_path.is_file() else None
    manifest_path = root / ".state/editorial-workspaces" / args.debate_id / args.work_id / "release-copy/manifest.json"
    if not manifest_path.is_file():
        raise PublicVisibilityError("Manifeste de la release du Work introuvable")
    report = check_or_record(
        state, args.debate_id, args.work_id, en_plan, fr_plan,
        late_reuse=reuse, manifest_sha256=sha256_file(manifest_path),
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if report["status"] == VERIFIED else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PublicVisibilityError, OSError, ValueError, KeyError) as exc:
        print("Visibilité publique non confirmée : " + str(exc), file=sys.stderr)
        raise SystemExit(2)
