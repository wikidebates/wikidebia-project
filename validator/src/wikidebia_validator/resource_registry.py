from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .package import PackageContext

DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.I)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFKC", _text(value)).replace("’", "'").casefold()
    return re.sub(r"[^\w]+", " ", text, flags=re.UNICODE).strip()


def _labels_are_compatible_variants(values: list[str]) -> bool:
    """Accept a substantial short title embedded in a fuller headline."""
    unique = sorted({value for value in values if value})
    if len(unique) <= 1:
        return True
    longest = max(unique, key=lambda value: (len(value.split()), len(value), value))
    padded_longest = f" {longest} "
    return all(
        value == longest
        or (len(value.split()) >= 5 and f" {value} " in padded_longest)
        for value in unique
    )


def normalize_doi(value: Any) -> str | None:
    raw = _text(value)
    if not raw:
        return None
    raw = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", raw, flags=re.I)
    match = DOI_RE.search(raw)
    return match.group(0).rstrip(".,;)").lower() if match else None


def normalize_url(value: Any) -> str | None:
    raw = _text(value)
    if not re.match(r"^https?://", raw, re.I):
        return None
    try:
        parts = urlsplit(raw)
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if not host:
        return None
    port = parts.port
    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query_pairs = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.casefold() not in {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid"}]
    query = urlencode(sorted(query_pairs), doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def source_label(source: dict[str, Any]) -> str:
    meta = source.get("metadata") or {}
    stype = source.get("type")
    if stype == "bibliography":
        return _text(meta.get("article") or meta.get("work") or meta.get("title") or meta.get("page"))
    if stype == "webliography":
        return _text(meta.get("page") or meta.get("title") or meta.get("site"))
    if stype == "videography":
        return _text(meta.get("title") or meta.get("page") or meta.get("site"))
    return _text(meta.get("article") or meta.get("work") or meta.get("page") or meta.get("title"))


def source_identity(source: dict[str, Any]) -> tuple[str, str, str | None, str | None]:
    meta = source.get("metadata") or {}
    link = normalize_url(meta.get("link"))
    doi = normalize_doi(meta.get("link")) or normalize_doi(source.get("deduplication_key"))
    if doi:
        return "doi", f"doi:{doi}", link, doi
    if link:
        return "url", f"url:{link}", link, None
    authors = ";".join(_fold(x) for x in (meta.get("authors") or []))
    label = _fold(source_label(source))
    date = _fold(meta.get("date"))
    publisher = _fold(meta.get("publisher") or meta.get("site"))
    raw = "|".join((str(source.get("type") or ""), label, authors, date, publisher))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return "bibliographic_fingerprint", f"bib:{digest}", None, None


def resource_id(identity_key: str) -> str:
    return "R" + hashlib.sha256(identity_key.encode("utf-8")).hexdigest()[:12].upper()


def build_resource_registry(sources_doc: dict[str, Any], source_registry_sha256: str) -> dict[str, Any]:
    debate_id = str(sources_doc.get("debate_id") or "")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    identities: dict[str, tuple[str, str | None, str | None]] = {}
    for source in sources_doc.get("sources") or []:
        if not isinstance(source, dict) or not source.get("id"):
            continue
        itype, key, url, doi = source_identity(source)
        grouped[key].append(source)
        identities[key] = (itype, url, doi)
    resources: list[dict[str, Any]] = []
    for key in sorted(grouped):
        rows = grouped[key]
        itype, url, doi = identities[key]
        labels: list[dict[str, str]] = []
        variants: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []
        by_lang: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        for source in sorted(rows, key=lambda x: str(x.get("id"))):
            sid = str(source.get("id"))
            lang = str(source.get("language") or "")
            label = source_label(source)
            if label:
                labels.append({"language": lang, "label": label})
                by_lang[lang][_fold(label)].append(sid)
            meta = source.get("metadata") or {}
            variants.append({
                "source_id": sid,
                "language": lang,
                "type": str(source.get("type") or ""),
                "label": label,
                "authors": list(meta.get("authors") or []),
                "date": _text(meta.get("date")),
                "publisher_or_site": _text(meta.get("publisher") or meta.get("site")),
            })
        preferred_by_lang: dict[str, str] = {}
        for lang, values in sorted(by_lang.items()):
            nonempty = [k for k in values if k]
            if len(nonempty) > 1 and not _labels_are_compatible_variants(nonempty):
                conflicts.append({
                    "kind": "same_identity_incompatible_label",
                    "language": lang,
                    "source_ids": sorted({sid for key2 in nonempty for sid in values[key2]}),
                    "labels": sorted({next(v["label"] for v in variants if v["source_id"] == sid) for key2 in nonempty for sid in values[key2]}),
                })
            elif nonempty:
                preferred_by_lang[lang] = max(
                    nonempty,
                    key=lambda value: (len(value.split()), len(value), value),
                )
        # Deduplicate identical language/label rows while preserving exact presentation.
        seen_label: set[tuple[str, str]] = set()
        clean_labels = []
        for row in labels:
            sig = (row["language"], _fold(row["label"]))
            preferred = preferred_by_lang.get(row["language"])
            if preferred and sig[1] != preferred:
                continue
            if sig not in seen_label:
                seen_label.add(sig)
                clean_labels.append(row)
        resources.append({
            "id": resource_id(key),
            "identity_type": itype,
            "identity_key": key,
            "canonical_url": url,
            "doi": doi,
            "source_ids": sorted(str(s.get("id")) for s in rows),
            "languages": sorted({str(s.get("language")) for s in rows if s.get("language")}),
            "labels": clean_labels,
            "metadata_variants": variants,
            "conflicts": conflicts,
        })
    return {
        "resource_registry_version": "1.0",
        "debate_id": debate_id,
        "source_registry_sha256": source_registry_sha256,
        "resources": resources,
    }


def validate_resource_registry(ctx: PackageContext) -> None:
    manifest = ctx.manifest() or {}
    controls = manifest.get("editorial_controls") or {}
    rel = controls.get("documentary_resource_registry_path")
    schema_version = controls.get("documentary_resource_registry_schema_version")
    if not rel and not schema_version:
        return
    if schema_version != "1.0" or not isinstance(rel, str):
        ctx.report.error("WDV-DOC-010", "Configuration du registre global des ressources incomplète", path="manifest.json")
        return
    doc = ctx.load_json(rel, required=True)
    sources_doc = ctx.sources()
    if not isinstance(doc, dict) or not isinstance(sources_doc, dict):
        return
    source_sha = ctx.sha256(ctx.core_paths()["sources"])
    if doc.get("source_registry_sha256") != source_sha:
        ctx.report.error("WDV-DOC-010", "Le registre global des ressources n’est pas lié à la version exacte de sources.json", path=rel, details={"expected": source_sha, "actual": doc.get("source_registry_sha256")})
        return
    expected = build_resource_registry(sources_doc, source_sha or "")
    # generated_at is intentionally absent: the artifact is deterministic from sources.json.
    if doc != expected:
        ctx.report.error("WDV-DOC-010", "Le registre global normalisé des ressources diverge de sources.json", path=rel)
        return
    conflicts = [
        {"resource_id": resource.get("id"), **conflict}
        for resource in doc.get("resources") or []
        for conflict in resource.get("conflicts") or []
    ]
    if conflicts:
        ctx.report.error("WDV-DOC-009", "Une même ressource canonique possède des métadonnées incompatibles", path=rel, details={"conflict_count": len(conflicts), "conflicts": conflicts[:25]})
    ctx.report.metrics["documentary_resources"] = {
        "count": len(doc.get("resources") or []),
        "conflicts": len(conflicts),
        "doi_identities": sum(r.get("identity_type") == "doi" for r in doc.get("resources") or []),
        "url_identities": sum(r.get("identity_type") == "url" for r in doc.get("resources") or []),
        "bibliographic_fingerprints": sum(r.get("identity_type") == "bibliographic_fingerprint" for r in doc.get("resources") or []),
    }
