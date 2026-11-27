from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import wikidebia_quote_bridge as bridge
import wikidebia_quote_duplicates as dup
from test_wikidebia_quote_bridge import item, request, envelope, reviewed, row_for
from test_wikidebia_translation_review import make_french_locked, mark_existing_english_argument

O = dup.Occurrence
LOCK = "a"*64


def quote(cid, text, revision=17):
    src = item(cid, revision=revision)
    src["source_parameters"][0]["value"] = text
    return src


def published(src, text):
    row = reviewed(src)
    passage = row["published_passage"]
    entry = passage["receipt"]
    proof = {"char_start": 0, "char_end": len(text),
             "text_sha256": hashlib.sha256(text.encode()).hexdigest()}
    entry["fragments"] = [proof]
    entry["target"] = {"document": {
        "url": "https://www.marxists.org/archive/test/a.htm", "revision": None,
        "body_sha256": "a"*64, "blocks_sha256": "b"*64},
        "char_start": 0, "char_end": len(text), "text_sha256": proof["text_sha256"]}
    entry["target"]["candidate_key"] = bridge.digest(entry["target"])
    passage["fragments"] = [{**proof, "text": text}]
    entry["entry_sha256"] = bridge.digest({k:v for k,v in entry.items() if k!="entry_sha256"})
    row["evidence"]["receipt_sha256"] = entry["entry_sha256"]
    return row


def batch(src, row):
    req = request(src)
    handoff = envelope(req, [row])
    return req, handoff, bridge.digest(handoff)


def owners(items):
    return {r["id"]: r["id"].rsplit("-C",1)[0] for r in items}


def test_exact_text_across_pages_and_distinct_passages():
    rows = [O("A1","C1",("Le même passage.",)),
            O("A2","C2",("Le  même passage.\n",)),
            O("A2","C3",("Un passage différent du même livre.",))]
    result = dup.analyze(rows)
    assert len(result["exact_text_groups"]) == 1
    assert result["exact_text_groups"][0]["occurrences"] == [
        {"page_id":"A1","citation_id":"C1"},{"page_id":"A2","citation_id":"C2"}]
    assert not result["near_lexical_matches"]
    assert "Le même passage." not in json.dumps(result, ensure_ascii=False)


def test_same_page_and_duplicate_occurrence_identity():
    rows = [O("A1","C1",("Identical passage.",)),O("A1","C2",("Identical passage.",))]
    assert not dup.analyze(rows)["exact_text_groups"]
    with pytest.raises(bridge.QuoteBridgeError, match="occurrence_identity"):
        dup.analyze(rows+rows[:1])


def test_variants_near_and_partial_separate():
    original = "The first sentence contains a long passage with several clear words for review"
    rows = [O("A1","C1",(original,)), O("A2","C2",(original.upper()+".",)),
            O("A3","C3",(original.replace("clear","different"),)),
            O("A4","C4",("A separate introduction "+original+
                           " continues into an unrelated discussion with additional details about another subject.",)),
            O("A5","C5",("Unrelated sentence from the very same author.",))]
    result = dup.analyze(rows)
    assert not result["exact_text_groups"]
    assert len(result["same_words_different_form_groups"]) == 1
    assert result["near_lexical_matches"] and result["partial_lexical_overlaps"]
    assert all("A5" not in json.dumps(f) for f in
               result["near_lexical_matches"]+result["partial_lexical_overlaps"])


def test_coordinate_overlap_not_other_edition_or_adjacent():
    rows = [O("A1","C1",("abcdefghij",),"a"*64,((0,10),)),
            O("A2","C2",("fghijk",),"a"*64,((5,11),)),
            O("A3","C3",("another",),"b"*64,((5,12),)),
            O("A4","C4",("lmnopqrst",),"a"*64,((11,20),))]
    overlap, = dup.analyze(rows)["same_document_partial_overlaps"]
    assert overlap["overlap_characters"] == 5
    assert {r["page_id"] for s in ("left","right") for r in overlap[s]} == {"A1","A2"}


def test_omission_boundaries_not_joined():
    x = ("one two three four five","six seven eight nine ten")
    y = ("one two three four five six seven eight nine ten unrelated additional words at end",)
    result = dup.analyze([O("A1","C1",x),O("A2","C2",y)])
    assert not result["partial_lexical_overlaps"]
    assert not result["exact_text_groups"]
    assert not result["same_words_different_form_groups"]
    for omission in (" [...]", " […]", " (…)", " ..."):
        explicit = (x[0]+omission+" "+x[1],)
        result = dup.analyze([O("A1","C1",explicit),O("A2","C2",y)])
        assert not result["partial_lexical_overlaps"]


def test_comparison_caps_do_not_remove_exact_duplicates():
    common = "one two three four five six seven eight nine ten "
    rows = [O(str(i),str(i),(common+str(i),)) for i in range(6)]
    rows.append(O("extra","extra",(common+"0",)))
    result = dup.analyze(rows,max_pairs=1)
    assert result["lexical_pair_limit_reached"] is True
    assert result["bounded_similarity_scan_complete"] is False
    assert len(result["exact_text_groups"]) == 1
    result = dup.analyze(rows,max_tokens=5)
    assert result["forms_exceeding_token_limit"] == 6
    assert len(result["exact_text_groups"]) == 1
    result = dup.analyze(rows,max_comparison_cells=1)
    assert result["lexical_cell_limit_reached"] is True
    assert result["lexical_candidate_pairs_compared"] == 0
    assert result["bounded_similarity_scan_complete"] is False
    assert len(result["exact_text_groups"]) == 1


def test_cross_batch_and_reused_french_scope_no_text_output():
    a = quote("A0001-C001","Un passage français.")
    b = quote("A0002-C001","Une autre citation française.",18)
    reused = quote("A0003-C001","Un passage français.",19)
    items = [a,b,reused]
    en = "A synthetic published passage."
    batches = [batch(a,published(a,en)),batch(b,published(b,en))]
    result = dup.audit_batches(LOCK,items,owners(items),[a,b],batches)
    assert len(result["french"]["exact_text_groups"]) == 1
    assert len(result["english"]["exact_text_groups"]) == 1
    assert result["coverage"]["all_eligible_batches_covered"] is True
    assert result["coverage"]["french_citations_on_reused_english_pages"] == 1
    assert result["coverage"]["public_wiki_wide_coverage"] is False
    assert result["publication_authorized"] is False and result["translation_mutated"] is False
    report = json.dumps(result,ensure_ascii=False)
    assert en not in report and "Un passage français." not in report


def test_missing_overlapping_and_reused_batch_refused():
    a,b = item(),item("A0002-C001")
    items = [a,b]
    only = batch(a,row_for(a,"ai_translation_required"))
    with pytest.raises(bridge.QuoteBridgeError,match="incomplete_batch_coverage"):
        dup.audit_batches(LOCK,items,owners(items),items,[only])
    result = dup.audit_batches(LOCK,items,owners(items),items,[only],allow_partial=True)
    assert result["coverage"]["missing_occurrences"] == [b["id"]]
    with pytest.raises(bridge.QuoteBridgeError,match="repeated_batch_occurrence"):
        dup.audit_batches(LOCK,items,owners(items),items,[only,only],allow_partial=True)
    with pytest.raises(bridge.QuoteBridgeError,match="request_occurrence_changed"):
        dup.audit_batches(LOCK,items,owners(items),[b],[only],allow_partial=True)


def test_tampered_fragments_or_missing_document_refused():
    a = item()
    req,handoff,sha = batch(a,published(a,"Synthetic passage."))
    changed = copy.deepcopy(handoff)
    changed["rows"][0]["published_passage"]["fragments"][0]["text"] = "Changed"
    for digest in (sha,bridge.digest(changed)):
        with pytest.raises(bridge.QuoteBridgeError):
            dup.audit_batches(LOCK,[a],owners([a]),[a],[(req,changed,digest)])
    with pytest.raises(bridge.QuoteBridgeError,match="missing_target_document"):
        dup.audit_batches(LOCK,[a],owners([a]),[a],[batch(a,reviewed(a))])


def test_real_lock_snapshot_includes_reused_without_exporting_them(tmp_path):
    project,workspace,work_id = make_french_locked(tmp_path)
    mark_existing_english_argument(workspace)
    _,lock,items,own,eligible = bridge.duplicate_snapshot(project,"debat_test",work_id)
    _,ordinary_lock,ordinary,ordinary_owners = bridge.snapshot(project,"debat_test",work_id)
    assert lock == ordinary_lock and ordinary == eligible
    assert set(ordinary_owners) == {r["id"] for r in eligible}
    assert "A0004" in set(own.values()) and "A0004" not in set(ordinary_owners.values())
    result = dup.audit_batches(lock,items,own,eligible,[],allow_partial=True)
    assert result["coverage"]["active_locked_french_citations"] > len(ordinary)
