"""Cross-repository contract test; run only with the pinned resolver checkout.

All source texts, revisions, retrieval results and decisions are synthetic
test fixtures. No public wiki or model is contacted, and no state survives.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import argparse
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def exercise(resolver_root):
    sys.path[:0] = [str(ROOT / "kit/scripts"), str(ROOT / "validator/src"), str(resolver_root), str(resolver_root / "tests")]
    import wikidebia_quote_bridge as bridge
    from wikidebia_content_review import _citation_records
    from citation_registry import CitationRegistry, fingerprint
    from grouped_review import REPLY
    from registry_transfer import export_bundle, import_bundle, read_private_json
    from public_quote_index import hashes, scan
    import wikidebia_quote_duplicates as dup
    import wikidebia_quote_public_check as public_check
    import wikidebia_published_quote_review as published_review
    from wikidebia_validator import published_quote_contract as independent_contract
    from wikidebia_published_quote_review import contract as kit_contract
    assert Path(kit_contract.__file__).read_bytes() == Path(independent_contract.__file__).read_bytes()
    import wikidebia_quote_index_contract as final_index
    import wikidebia_quote_index_collect as collector
    from wikidebia_validator import quote_index_contract as independent_index
    assert Path(final_index.__file__).read_bytes() == Path(independent_index.__file__).read_bytes()
    from test_citation_registry import RAW, QUOTE, ENGLISH, FR, candidate, document, ref, review
    from test_public_quote_index import Fake
    from translation_handoff import prepare_handoff, apply_handoff_reply
    from work_library import WorkLibrary

    with TemporaryDirectory(prefix="quote-bridge-contract-") as tmp:
        base = Path(tmp)
        # Exercise the actual pinned Git object materialization and isolated
        # producer entrypoint, not just the synthetic Git fixture.
        producer_dir = base/"producer"
        producer_dir.mkdir()
        script = collector.materialize(resolver_root,producer_dir)
        assert script.read_bytes() == (resolver_root/"public_quote_index.py").read_bytes()
        assert collector._run(script,producer_dir,["--help"],30) == 0
        # The two explicit preparation modes use the actual pinned entrypoint.
        # Only integrated retrieval needs bibliographic assets.
        for integrated in (False, True):
            handoff_dir = base / ("integrated" if integrated else "prepared")
            handoff_dir.mkdir()
            handoff_script = collector.materialize(resolver_root, handoff_dir,
                entrypoint="translation_handoff.py", include_search_data=integrated)
            assert handoff_script.read_bytes() == (resolver_root / "translation_handoff.py").read_bytes()
            assert (handoff_script.parent / "data/wikirouge/manifest.json").exists() == integrated
            if integrated:
                manifest = json.loads((handoff_script.parent / "data/wikirouge/manifest.json").read_text())
                archive = "data/wikirouge/" + manifest["archive"]["filename"]
                assert bridge.sha256_file(handoff_script.parent / archive) == bridge.sha256_file(resolver_root / archive)
            assert collector._run(handoff_script, handoff_dir, ["--help"], 30) == 0
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
        # Real private files produced by the kit, split into distinct batches.
        batches = bridge.requests_for(lock_sha, items, owners, batch_size=1)
        request_paths = [bridge.write_private_request(base, r) for r in batches]
        selector_path = base / "selection.json"
        cmd = [sys.executable, str(resolver_root / "registry_transfer.py"), "select"]
        for path in request_paths:
            cmd += ["--request", str(path)]
        selected = subprocess.run(cmd + ["--out", str(selector_path)],
                                  check=True, capture_output=True, text=True)
        select_summary = json.loads(selected.stdout)
        selection = read_private_json(selector_path)
        assert select_summary["sha256"] == fingerprint(selection)
        assert len(selection["selectors"]) == 1
        assert selection["request_sha256s"] == sorted(bridge.digest(r) for r in batches)
        assert selector_path.stat().st_mode & 0o077 == 0
        assert QUOTE not in str(selection) and "Argument A" not in str(selection)
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
            # Lookup-only is safe even without any prepared receipt. A miss
            # is not proof of absence and must not initiate retrieval.
            cold_lookup = prepare_handoff(request, registry, retrieval, load_raw,
                                          audit, search_missing=False)
            summary = bridge.inspect_handoff(request, cold_lookup, fingerprint(cold_lookup),
                                             lock_sha, items, owners)
            assert summary["states"] == {"insufficient_evidence": 1, "ai_translation_required": 1}
            assert calls == []
            cold_row = next(r for r in cold_lookup["rows"] if r["id"] == "A0001-C001")
            assert cold_row["evidence"]["reason"] == "prepared_receipt_not_found_search_not_run"
            assert "published_passage" not in cold_row and not cold_lookup["packets"]

            # Integrated route: search now and apply the review in this state.
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
            direct = prepare_handoff(request, registry, retrieval, load_raw, audit)
            summary = bridge.inspect_handoff(request, direct, fingerprint(direct),
                                             lock_sha, items, owners)
            assert summary["states"] == {"reviewed_receipt_rights_unreviewed": 1,
                                         "ai_translation_required": 1}
            direct_row = next(r for r in direct["rows"] if r["id"] == "A0001-C001")
            direct_candidate, = published_review.prepare(request, direct, fingerprint(direct),
                                                          lock_sha, items, owners)
            assert direct_candidate["plain_quote"] == ENGLISH
            assert direct_candidate["publication_authorized"] is False
            assert calls == ["A0001-C001"]
            # Include an unrelated receipt in the source registry: it must not
            # leave this environment, even if it resolves to the same passage.
            unrelated = RAW.replace(QUOTE, "Autre citation de test, sans rapport.")
            unrelated_ref = ref(unrelated, 99)
            c = candidate(doc)
            registry.record(unrelated, unrelated_ref, doc, c,
                            review(unrelated, unrelated_ref, doc, c))
            bundle = export_bundle(registry, selection=selection,
                                   selection_sha=select_summary["sha256"])
            assert len(bundle["entries"]) == 1
            assert QUOTE not in str(bundle) and ENGLISH not in str(bundle)
            with WorkLibrary(base / "translation.sqlite3") as destination:
                target_registry = CitationRegistry(destination.db)
                receipt = import_bundle(target_registry, bundle, fingerprint(bundle))
                assert receipt["inserted"] == 1
                assert target_registry.lookup(unrelated, unrelated_ref)["status"] == "miss"
                assert import_bundle(target_registry, bundle, fingerprint(bundle))["already_present"] == 1
                states = {}
                for batch in batches:
                    restored = prepare_handoff(batch, target_registry, retrieval, load_raw,
                                               audit, search_missing=False)
                    summary = bridge.inspect_handoff(batch, restored, fingerprint(restored),
                                                     lock_sha, items, owners)
                    states.update(summary["states"])
                    assert summary["publication_authorized"] is False
                    assert summary["translation_mutated"] is False
                    assert QUOTE not in str(summary) and ENGLISH not in str(summary)
                    if "reviewed_receipt_rights_unreviewed" in summary["states"]:
                        row, = restored["rows"]
                        assert row["published_passage"]["fragments"][0]["text"] == ENGLISH
                        prepared_candidate, = published_review.prepare(batch, restored, fingerprint(restored),
                            lock_sha, items, owners)
                        # Different request/batch and transport envelopes are
                        # legitimate; the occurrence, receipt and passage must
                        # nevertheless be identical to the integrated route.
                        assert row["source_key"] == direct_row["source_key"]
                        assert row["citation_ref"] == direct_row["citation_ref"]
                        assert row["published_passage"] == direct_row["published_passage"]
                        assert prepared_candidate["plain_quote"] == direct_candidate["plain_quote"] == ENGLISH
                        assert published_review.blank(prepared_candidate)["rights_review"]["status"] == "pending"
                        assert prepared_candidate["publication_authorized"] is False
                        # The independent validator can verify the actual
                        # resolver-produced source/target evidence, not merely
                        # a kit-generated digest or approval boolean.
                        assert independent_contract._validate_receipt(prepared_candidate["row"],prepared_candidate["item"]) == (ENGLISH,)
                assert states == {"reviewed_receipt_rights_unreviewed": 1,
                                  "ai_translation_required": 1}
                assert calls == ["A0001-C001"]
                # Change the target's body: neither the transport nor its hash
                # authorizes reuse of stale English text.
                changed = SimpleNamespace(document=lambda *_: document(digest="c"*64),
                                          publication={})
                stale = prepare_handoff(batches[0], target_registry, retrieval, load_raw,
                                       changed, search_missing=False)
                assert stale["rows"][0]["state"] == "retry_documentary"
                assert "published_passage" not in stale["rows"][0]
                bridge.inspect_handoff(batches[0], stale, fingerprint(stale),
                                       lock_sha, items, owners)
                assert calls == ["A0001-C001"]
    # Check the actual producer/consumer hash and snapshot contracts, not
    # just a duplicated synthetic JSON fixture.
    for fragments in (("Un texte très précis.",),("One [...] two",),
                      ("One","two"),("...",),("a\u0301   b",)):
        assert hashes(fragments)==dup.public_fingerprints(fragments)
    for lang in ("fr","en"):
        value,summary = scan(Fake(lang),lang)
        result = public_check.compare([dup.Occurrence("A0001","C1",("A test passage.",))],
                 value,summary["snapshot_sha256"],lang,fingerprints=dup.public_fingerprints)
        assert result["coverage"]["complete_fresh_literal_scope"] is True
        assert result["findings"][0]["matching_pages"]==2
        if lang=="en":
            args=[{"id":"A0001","canonical_title":"New argument","citations":[
                {"id":"A0001-C001","quote":"A test passage.",
                 "parameters":[{"name":"quote","value":"A test passage."}]}]}]
            final=final_index.final_audit(args,value,summary["snapshot_sha256"],"a"*64)
            assert final["status"]=="blocked_exact_duplicates"
            assert final["public_exact"][0]["matching_occurrences"]==2
            assert final==independent_index.final_audit(args,value,summary["snapshot_sha256"],
                    "a"*64,now=__import__("datetime").datetime.fromisoformat(final["checked_at"]))
    print("Cross-repository contract: passed (cold lookup abstention, integrated search, equivalent transferred receipt, pinned producer isolation, selective transfer, separate DBs, public fingerprint exchange; no wiki/model access)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resolver-root", type=Path, required=True)
    exercise(parser.parse_args().resolver_root.resolve())
