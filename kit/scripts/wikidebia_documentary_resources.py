#!/usr/bin/env python3
"""Build the deterministic corpus-wide documentary resource identity registry."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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
    parts = urlsplit(raw)
    scheme = parts.scheme.lower(); host = (parts.hostname or "").lower()
    if not host:
        return None
    port = parts.port; netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/": path = path.rstrip("/")
    query_pairs = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.casefold() not in {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid"}]
    query = urlencode(sorted(query_pairs), doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def _label(source: dict[str, Any]) -> str:
    meta = source.get("metadata") or {}; stype = source.get("type")
    if stype == "bibliography": return _text(meta.get("article") or meta.get("work") or meta.get("title") or meta.get("page"))
    if stype == "webliography": return _text(meta.get("page") or meta.get("title") or meta.get("site"))
    if stype == "videography": return _text(meta.get("title") or meta.get("page") or meta.get("site"))
    return _text(meta.get("article") or meta.get("work") or meta.get("page") or meta.get("title"))


def _identity(source: dict[str, Any]):
    meta = source.get("metadata") or {}; link = normalize_url(meta.get("link")); doi = normalize_doi(meta.get("link")) or normalize_doi(source.get("deduplication_key"))
    if doi: return "doi", f"doi:{doi}", link, doi
    if link: return "url", f"url:{link}", link, None
    authors = ";".join(_fold(x) for x in (meta.get("authors") or [])); label = _fold(_label(source)); date = _fold(meta.get("date")); publisher = _fold(meta.get("publisher") or meta.get("site"))
    digest = hashlib.sha256("|".join((str(source.get("type") or ""), label, authors, date, publisher)).encode()).hexdigest()
    return "bibliographic_fingerprint", f"bib:{digest}", None, None


def build_resource_registry(sources_doc: dict[str, Any], source_registry_sha256: str) -> dict[str, Any]:
    grouped=defaultdict(list); identities={}
    for source in sources_doc.get("sources") or []:
        if not isinstance(source,dict) or not source.get("id"): continue
        itype,key,url,doi=_identity(source); grouped[key].append(source); identities[key]=(itype,url,doi)
    resources=[]
    for key in sorted(grouped):
        rows=grouped[key]; itype,url,doi=identities[key]; variants=[]; labels=[]; by_lang=defaultdict(lambda:defaultdict(list))
        for source in sorted(rows,key=lambda x:str(x.get("id"))):
            sid=str(source.get("id")); lang=str(source.get("language") or ""); label=_label(source); meta=source.get("metadata") or {}
            if label: labels.append({"language":lang,"label":label}); by_lang[lang][_fold(label)].append(sid)
            variants.append({"source_id":sid,"language":lang,"type":str(source.get("type") or ""),"label":label,"authors":list(meta.get("authors") or []),"date":_text(meta.get("date")),"publisher_or_site":_text(meta.get("publisher") or meta.get("site"))})
        conflicts=[]; preferred_by_lang={}
        for lang,values in sorted(by_lang.items()):
            keys=[k for k in values if k]
            if len(keys)>1 and not _labels_are_compatible_variants(keys):
                source_ids=sorted({sid for k in keys for sid in values[k]}); label_values=sorted({next(v["label"] for v in variants if v["source_id"]==sid) for sid in source_ids})
                conflicts.append({"kind":"same_identity_incompatible_label","language":lang,"source_ids":source_ids,"labels":label_values})
            elif keys:
                preferred_by_lang[lang] = max(keys, key=lambda value: (len(value.split()), len(value), value))
        seen=set(); clean=[]
        for row in labels:
            sig=(row["language"],_fold(row["label"]))
            preferred = preferred_by_lang.get(row["language"])
            if preferred and sig[1] != preferred:
                continue
            if sig not in seen: seen.add(sig); clean.append(row)
        rid="R"+hashlib.sha256(key.encode()).hexdigest()[:12].upper()
        resources.append({"id":rid,"identity_type":itype,"identity_key":key,"canonical_url":url,"doi":doi,"source_ids":sorted(str(s.get("id")) for s in rows),"languages":sorted({str(s.get("language")) for s in rows if s.get("language")}),"labels":clean,"metadata_variants":variants,"conflicts":conflicts})
    return {"resource_registry_version":"1.0","debate_id":str(sources_doc.get("debate_id") or ""),"source_registry_sha256":source_registry_sha256,"resources":resources}


def build_file(sources_path: Path, output_path: Path) -> dict[str, Any]:
    sources=json.loads(sources_path.read_text(encoding="utf-8")); sha=hashlib.sha256(sources_path.read_bytes()).hexdigest(); registry=build_resource_registry(sources,sha)
    output_path.parent.mkdir(parents=True,exist_ok=True); output_path.write_text(json.dumps(registry,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")
    return registry
