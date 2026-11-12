#!/usr/bin/env python3
"""Offline compact repository map and failure-focused test report (#65)."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

SKIP = {".git", ".venv", ".state", "private", "corpus", "archives",
        "updates", "incoming", "outgoing", "logs", "plans", "__pycache__",
        ".pytest_cache", "translation-memory"}
SECRET_NAMES = {"user-password.cfg", "wikidebia.local.json", ".env"}


def _redact(value: str) -> str:
    safe = re.sub(
        r"(?i)(password|token|secret|api[_-]?key)\s*[=:]\s*\S+",
        r"\1=[REDACTED]", value,
    )
    safe = re.sub(r"(?i)\bBearer\s+[^\s]+", "Bearer [REDACTED]", safe)
    safe = re.sub(
        r"(?i)(authorization\s*[=:]\s*)(?:Basic\s+|Bearer\s+)?\S+",
        r"\1[REDACTED]", safe,
    )
    safe = re.sub(r"(https?://)[^/@\s:]+:[^/@\s]+@", r"\1[REDACTED]@", safe)
    safe = re.sub(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b", "[REDACTED_AWS_KEY]", safe)
    safe = re.sub(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b", "[REDACTED_GITHUB_TOKEN]", safe)
    safe = re.sub(
        r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",
        "[REDACTED_JWT]", safe,
    )
    safe = re.sub(
        r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*",
        "[REDACTED_PRIVATE_KEY]", safe,
    )
    return safe

def compact_index(root: Path) -> dict:
    root = root.resolve()
    rows = []
    for path in sorted(root.rglob("*")):
        if any(part in SKIP or part.startswith(".env") for part in path.relative_to(root).parts):
            continue
        if path.is_symlink() or not path.is_file() or path.name in SECRET_NAMES:
            continue
        rel = path.relative_to(root).as_posix()
        if not (rel.endswith((".py", ".md", ".sh", ".json", ".yml", ".yaml"))
                or rel in {"wikidebia", ".gitignore"}):
            continue
        if path.stat().st_size > 512_000:
            continue
        data = path.read_bytes()
        rows.append({"path": rel, "bytes": len(data),
                     "sha256": hashlib.sha256(data).hexdigest()[:16]})
    return {"schema": "wikidebia-repository-index-1.0",
            "file_count": len(rows), "files": rows,
            "remote_access_performed": False, "remote_write_performed": False}

def failure_report(log: str) -> dict:
    lines = log.splitlines()
    selected = []
    markers = ("FAILED ", "ERROR ", "AssertionError", "Traceback (most recent",
               "E   ", "short test summary info", "tests failed", "test failed")
    for number, line in enumerate(lines, 1):
        if any(marker in line for marker in markers):
            # Redact likely secrets from test diagnostics.
            safe = _redact(line)
            selected.append({"line": number, "text": safe[:300]})
    return {"schema": "wikidebia-test-failures-1.0",
            "total_lines": len(lines), "failure_lines": selected[:200],
            "truncated": len(selected) > 200}


def junit_failure_report(paths: list[Path]) -> dict:
    """Return only structured failing test identities and short safe messages."""
    sources = []
    failures = []
    missing_sources = []
    parse_errors = []
    for path in paths:
        if not path.is_file() or path.is_symlink():
            missing_sources.append(path.name)
            continue
        try:
            root = ET.parse(path).getroot()
        except (ET.ParseError, OSError) as exc:
            parse_errors.append({"source": path.name, "error_type": type(exc).__name__})
            continue
        cases = list(root.iter("testcase"))
        source_failures = 0
        source_errors = 0
        source_skipped = 0
        for case in cases:
            source_skipped += int(case.find("skipped") is not None)
            for kind in ("failure", "error"):
                node = case.find(kind)
                if node is None:
                    continue
                if kind == "failure":
                    source_failures += 1
                else:
                    source_errors += 1
                if len(failures) >= 100:
                    continue
                classname = str(case.get("classname") or "")
                name = str(case.get("name") or "unknown")
                test_id = f"{classname}::{name}" if classname else name
                message = _redact(str(node.get("message") or "").replace("\n", " "))
                failures.append({
                    "source": path.name,
                    "test_id": _redact(test_id)[:300],
                    "kind": kind,
                    "exception_type": _redact(str(node.get("type") or ""))[:120] or None,
                    "message": message[:300] or None,
                })
        sources.append({
            "source": path.name,
            "tests": len(cases),
            "failures": source_failures,
            "errors": source_errors,
            "skipped": source_skipped,
        })
    total_failures = sum(row["failures"] + row["errors"] for row in sources)
    return {
        "schema": "wikidebia-structured-ci-failures-1.0",
        "sources": sources,
        "missing_sources": sorted(missing_sources),
        "parse_errors": parse_errors,
        "failure_count": total_failures,
        "failures": failures,
        "truncated": total_failures > len(failures),
        "raw_tracebacks_included": False,
        "arbitrary_log_lines_included": False,
        "remote_access_performed": False,
        "remote_write_performed": False,
    }

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project-root", type=Path, default=Path.cwd())
    source = p.add_mutually_exclusive_group()
    source.add_argument("--test-log", type=Path)
    source.add_argument("--junit-xml", type=Path, action="append")
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    if args.junit_xml:
        result = junit_failure_report(args.junit_xml)
    elif args.test_log:
        result = failure_report(args.test_log.read_text(encoding="utf-8", errors="replace"))
    else:
        result = compact_index(args.project_root)
    data = json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".index-", dir=args.output.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, args.output)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    else:
        print(data, end="")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
