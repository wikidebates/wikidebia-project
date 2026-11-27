from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import sys
from pathlib import Path
import unicodedata

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import wikidebia_quote_bridge as bridge
import wikidebia_quote_duplicates as dup
import wikidebia_quote_public_check as pub
from test_wikidebia_quote_duplicates import quote, published, batch, owners, LOCK

NOW = datetime(2026,11,27,6,0,tzinfo=timezone.utc)
O = dup.Occurrence


def snapshot(lang, rows, *, status=pub.COMPLETE, age=1):
    started = NOW-timedelta(hours=age)
    pages = []
    for pid,title,revision,text in rows:
        pages.append({"page_id":pid,"title":title,"revision":revision,
                      "argument_template_present":True,"invalid_occurrences":0,
                      "quotes":[{"ordinal":1,**dup.public_fingerprints((text,))}]})
    return {"schema":pub.SCHEMA,"algorithm":pub.ALGORITHM,
            "unicode_version":unicodedata.unidata_version,"language":lang,
            "status":status,"started_utc":started.isoformat(),
            "finished_utc":(started+timedelta(minutes=1)).isoformat(),
            "template_titles":[pub.ROOTS[lang]],"pages_enumerated":len(pages),
            "pages":pages,"issues":{}}


def compare(rows,index,lang,**kwargs):
    return pub.compare(rows,index,bridge.digest(index),lang,
                       fingerprints=dup.public_fingerprints,now=NOW,**kwargs)


def test_global_french_excludes_own_imported_page_but_not_other_arguments():
    item = quote("A0001-C001","Un passage français.",17)
    item["wiki_title"] = "Argument A"
    idx = snapshot("fr",[(1,"Argument_A",30,"Un passage français."),
                         (2,"Argument B",18,"Un passage français."),
                         (3,"Argument C",19,"UN PASSAGE FRANÇAIS"),
                         (4,"Argument D",20,"Autre passage.")])
    result = compare([O("A0001",item["id"],("Un passage français.",))],idx,"fr",
                     source_items=[item])
    assert result["same_imported_page_matches_excluded"] == 1
    assert result["existing_exact_groups_across_pages"] == 1
    assert result["existing_same_words_different_form_groups_across_pages"] == 1
    exact,variant = result["findings"]
    assert exact["kind"]=="exact_literal" and exact["matches"][0]["wiki_page_id"]==2
    assert variant["kind"]=="same_words_different_form" and variant["matches"][0]["wiki_page_id"]==3
    assert "Un passage français." not in json.dumps(result,ensure_ascii=False)
    assert result["publication_authorized"] is False


def test_moved_page_same_revision_and_unpinned_not_exempted():
    item = quote("A0001-C001","same quote",17)
    idx = snapshot("fr",[(1,"Renamed argument",17,"same quote")])
    rows = [O("A0001",item["id"],("same quote",))]
    assert not compare(rows,idx,"fr",source_items=[item])["findings"]
    item["revision"] = None
    assert compare(rows,idx,"fr",source_items=[item])["findings"][0]["matching_pages"]==1


def test_both_wikis_and_across_batches():
    a,b = quote("A0001-C001","Un texte.",17),quote("A0002-C001","Un autre texte.",18)
    items = [a,b]
    fr = snapshot("fr",[(1,"External FR",30,"Un texte.")])
    en = snapshot("en",[(1,"External EN",40,"English text."),
                         (2,"Other English argument",41,"English text.")])
    batches = [batch(a,published(a,"English text.")),batch(b,published(b,"Different text."))]
    result = dup.audit_batches(LOCK,items,owners(items),items,batches,
                public_indexes=[("fr",fr,bridge.digest(fr)),("en",en,bridge.digest(en))],now=NOW)
    assert result["public_comparison"]["fr"]["findings"][0]["matching_pages"]==1
    assert result["public_comparison"]["en"]["findings"][0]["matching_pages"]==2
    assert result["public_comparison"]["en"]["local_occurrences"]==2
    assert result["coverage"]["public_wiki_wide_coverage"] is False
    assert result["translation_mutated"] is False


def test_old_and_incomplete_indexes_are_explicitly_limited():
    idx = snapshot("en",[(1,"A",20,"English text.")],age=48)
    rows = [O("A0001","C1",("English text.",))]
    with pytest.raises(bridge.QuoteBridgeError,match="public_index_stale"):
        compare(rows,idx,"en")
    result = compare(rows,idx,"en",allow_partial=True)
    assert result["coverage"]["stale"] and not result["coverage"]["complete_fresh_literal_scope"]
    idx = snapshot("en",[],status="incomplete")
    idx["pages_enumerated"] = 100
    idx["issues"] = {"request_budget_exhausted":100}
    with pytest.raises(bridge.QuoteBridgeError,match="public_index_incomplete"):
        compare(rows,idx,"en")
    result = compare(rows,idx,"en",allow_partial=True)
    assert not result["findings"] and not result["coverage"]["complete_fresh_literal_scope"]


def test_integrity_schema_and_coverage_errors_fail_closed():
    idx = snapshot("en",[(1,"A",20,"English text.")])
    rows = [O("A0001","C1",("English text.",))]
    for change in (lambda v:v.update(pages_enumerated=2),
                   lambda v:v.update(issues={"failed":1}),
                   lambda v:v.update(language="fr"),
                   lambda v:v.update(algorithm="unknown"),
                   lambda v:v["pages"][0]["quotes"][0].update(text="wrong"),
                   lambda v:v["pages"][0]["quotes"][0].update(ordinal=2)):
        value = deepcopy(idx)
        change(value)
        with pytest.raises(bridge.QuoteBridgeError):
            compare(rows,value,"en",allow_partial=True)
    with pytest.raises(bridge.QuoteBridgeError,match="digest_mismatch"):
        pub.validate(idx,"0"*64,"en",now=NOW)


def test_omission_matches_words_but_not_contiguous_quote():
    idx = snapshot("en",[(1,"A",20,"one [...] two"),(2,"B",21,"one two")])
    result = compare([O("A0001","C1",("one","two"))],idx,"en")
    finding, = result["findings"]
    assert finding["kind"]=="same_words_different_form"
    assert finding["matches"][0]["wiki_page_id"]==1


def test_no_match_not_proof_and_duplicate_index_language_rejected():
    idx = snapshot("fr",[(1,"External",22,"Other text.")])
    a = quote("A0001-C001","Un texte.")
    with pytest.raises(bridge.QuoteBridgeError,match="language_scope"):
        dup.audit_batches(LOCK,[a],owners([a]),[a],[],allow_partial=True,
            public_indexes=[("fr",idx,bridge.digest(idx))]*2,now=NOW)
