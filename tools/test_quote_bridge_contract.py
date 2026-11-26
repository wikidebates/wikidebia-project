"""Cross-repository contract test; run only with the pinned resolver checkout.

All source texts, revisions, retrieval results and decisions are synthetic
test fixtures. No public wiki or model is contacted, and no state survives.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]


def exercise(resolver_root):
    sys.path[:0] = [str(ROOT / "kit/scripts"), str(resolver_root), str(resolver_root / "tests")]
    import wikidebia_quote_bridge as bridge
    from wikidebia_content_review import _citation_records
    from citation_registry import CitationRegistry, fingerprint
    from grouped_review import REPLY
    from test_citation_registry import RAW, QUOTE, ENGLISH, FR, candidate, document
    from translation_handoff import prepare_handoff, apply_handoff_reply
    from work_library import WorkLibrary

    with TemporaryDirectory(prefix="quote-bridge-contract-") as tmp:
        base = Path(tmp)
        raws = [RAW, RAW.replace(FR, "https://example.org/article")]
        pages = {"Argument A": (17, raws[0]), "Argument B": (18, raws[1])}
        nodes, metadata, content, provenance = [], [], [], []
        for i, (title, (revision, raw)) in enumerate(pages.items(), 1):
            node_id = f"A{i:04d}"
            nodes.append({"id": node_id, "status": "active"})
            metadata.append({"entity_id": node_id, "canonical_title": title})
            content.append({"id": node_id, "citations": _citation_records(raw, node_id)})
            rel = Path("imports/fr/arguments") / (node_id + ".wiki")
            path = base / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            provenance.append({"kind": "argument", "page_id": node_id,
                               "canonical_title": title, "revision_id": revision,
                               "import_path": str(rel), "sha256": bridge.sha256_file(path)})
        items, owners = bridge.locked_items(base, {"graph": {"nodes": nodes}},
                                            {"arguments": metadata}, {"arguments": content},
                                            {"pages": provenance})
        lock_sha = bridge.digest({"synthetic_fixture": content})
        request, = bridge.requests_for(lock_sha, items, owners)
        assert fingerprint(request) == bridge.digest(request)
        doc = document()
        calls = []

        def load_raw(title, revision):
            expected, raw = pages[title]
            assert expected == revision
            return raw

        def retrieve(case):
            calls.append(case["id"])
            return {"id": case["id"], "status": "candidate_review_required",
                    "review_packet": {"candidates": [candidate(doc)]}}

        audit = SimpleNamespace(document=lambda *_: doc, publication={})
        retrieval = SimpleNamespace(client=SimpleNamespace(events=[]), retrieve=retrieve)
        with WorkLibrary(base / "works.sqlite3") as library:
            registry = CitationRegistry(library.db)
            handoff = prepare_handoff(request, registry, retrieval, load_raw, audit)
            summary = bridge.inspect_handoff(request, handoff, fingerprint(handoff),
                                             lock_sha, items, owners)
            assert summary["states"] == {"review_pending": 1, "ai_translation_required": 1}
            assert calls == ["A0001-C001"]
            entry, = handoff["packets"]
            packet = entry["packet"]
            qid, = packet["sources"]
            pid, = packet["sources"][qid]["candidates"]
            reply = {"schema": REPLY, "packet_sha256": entry["packet_sha256"],
                     "reviewer": "synthetic cross-repository fixture",
                     "decisions": [{"id": qid, "decision": "complete_equivalent",
                                    "candidate": pid, "ranges": [[0, len(ENGLISH)]]}]}
            result = apply_handoff_reply(handoff, fingerprint(handoff), reply,
                                         registry, load_raw, audit)
            assert result["recorded"] == 1
            restored = prepare_handoff(request, registry, retrieval, load_raw, audit,
                                         search_missing=False)
            summary = bridge.inspect_handoff(request, restored, fingerprint(restored),
                                             lock_sha, items, owners)
            assert summary["states"] == {
                "reviewed_receipt_rights_unreviewed": 1, "ai_translation_required": 1}
            assert calls == ["A0001-C001"]
            row = restored["rows"][0]
            assert row["published_passage"]["fragments"][0]["text"] == ENGLISH
            assert summary["publication_authorized"] is False
            assert summary["translation_mutated"] is False
            assert QUOTE not in str(summary) and ENGLISH not in str(summary)
    print("Cross-repository contract: passed (synthetic fixtures, no wiki/model access)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resolver-root", type=Path, required=True)
    exercise(parser.parse_args().resolver_root.resolve())
