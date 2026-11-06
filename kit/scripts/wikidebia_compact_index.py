#!/usr/bin/env python3
"""Offline compact repository map and failure-focused test report (#65)."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import os
import tempfile
from pathlib import Path

SKIP = {".git", ".venv", ".state", "private", "corpus", "archives",
        "updates", "incoming", "outgoing", "logs", "plans", "__pycache__",
        ".pytest_cache", "translation-memory"}
SECRET_NAMES = {"user-password.cfg", "wikidebia.local.json", ".env"}

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
            safe = re.sub(r"(?i)(password|token|secret|api[_-]?key)\s*[=:]\s*\S+",
                          r"\1=[REDACTED]", line)
            safe = re.sub(r"(?i)\bBearer\s+[^\s]+", "Bearer [REDACTED]", safe)
            safe = re.sub(r"(?i)(authorization\s*[=:]\s*)(?:Basic\s+|Bearer\s+)?\S+", r"\1[REDACTED]", safe)
            safe = re.sub(r"(https?://)[^/@\s:]+:[^/@\s]+@", r"\1[REDACTED]@", safe)
            selected.append({"line": number, "text": safe[:300]})
    return {"schema": "wikidebia-test-failures-1.0",
            "total_lines": len(lines), "failure_lines": selected[:200],
            "truncated": len(selected) > 200}

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project-root", type=Path, default=Path.cwd())
    p.add_argument("--test-log", type=Path)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    result = failure_report(args.test_log.read_text(encoding="utf-8", errors="replace")) if args.test_log else compact_index(args.project_root)
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
