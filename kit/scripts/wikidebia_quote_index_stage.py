"""Private staging of a public fingerprint snapshot for final translation review.

This is a local file transfer, not a second registry or a network operation.
The expected digest must come from the trusted index producer.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import wikidebia_quote_index_contract as contract


def load_index(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > contract.MAX_INDEX_BYTES:
        raise contract.QuoteIndexError("invalid_public_quote_index_file")
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise contract.QuoteIndexError("duplicate_public_quote_index_key")
            result[k] = v
        return result
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream, object_pairs_hook=unique)


def stage(workspace, path, expected_sha, *, now=None):
    from wikidebia_published_quote_review import write_private
    value = load_index(path)
    contract.validate(value, expected_sha, "en", now=now)
    return write_private(workspace, value, "public-index")


def stored_index(workspace, expected_sha):
    if not contract.is_digest(expected_sha):
        raise contract.QuoteIndexError("invalid_public_quote_index_digest")
    path = (workspace/"audits/quote-resolver/published-quotes/public-index"/
            (expected_sha+".json"))
    if not path.resolve().is_relative_to(workspace.resolve()):
        raise contract.QuoteIndexError("unsafe_public_quote_index_path")
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise contract.QuoteIndexError("missing_or_nonprivate_public_quote_index")
    value = load_index(path)
    if contract.digest(value) != expected_sha:
        raise contract.QuoteIndexError("public_index_digest_mismatch")
    return value


def main(argv=None):
    from wikidebia_editorial_review import _load_workspace
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("debate_id")
    p.add_argument("--work-id", required=True)
    p.add_argument("--project-root", type=Path, default=Path.cwd())
    p.add_argument("--index", type=Path, required=True)
    p.add_argument("--sha256", required=True)
    a = p.parse_args(argv)
    try:
        workspace, meta = _load_workspace(a.project_root.resolve(),a.debate_id,a.work_id)
        path = stage(workspace,a.index,a.sha256)
    except (ValueError,RuntimeError,OSError,KeyError,TypeError,AttributeError) as exc:
        reason = str(exc) if isinstance(exc,contract.QuoteIndexError) else type(exc).__name__
        print(json.dumps({"status":"blocked","reason":reason}))
        return 1
    print(json.dumps({"status":"staged","quote_public_index_sha256":a.sha256,
                      "path":str(path),"translation_mutated":False,"publication_authorized":False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
