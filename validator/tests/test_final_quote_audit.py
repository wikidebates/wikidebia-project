from datetime import datetime, timezone
import json
import hashlib
import unicodedata

from wikidebia_validator import quote_index_contract as q
from wikidebia_validator.bilingual import _validate_final_quote_audit
from wikidebia_validator.package import PackageContext
from wikidebia_validator.report import Report


def test_independent_validator_recomputes_final_quote_audit(tmp_path):
    def write(rel,value):
        path=tmp_path/rel
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value,ensure_ascii=False)+"\n",encoding="utf-8")
        return path
    fr=write("data/fr_content_lock.json",{"arguments":[]})
    lock_sha=hashlib.sha256(fr.read_bytes()).hexdigest()
    now=datetime.now(timezone.utc)
    idx={"schema":q.SCHEMA,"algorithm":q.ALGORITHM,
         "unicode_version":unicodedata.unidata_version,"language":"en","status":q.COMPLETE,
         "started_utc":now.isoformat(),"finished_utc":now.isoformat(),
         "template_titles":[q.ROOTS["en"]],"pages_enumerated":0,"pages":[],"issues":{}}
    args=[{"id":"A0001","canonical_title":"A title","citations":[
        {"id":"A0001-C001","quote":"New quote.","parameters":[{"name":"quote","value":"New quote."}]}]}]
    audit=q.final_audit(args,idx,q.digest(idx),lock_sha,now=now)
    en={"arguments":args,"quote_duplicate_audit":audit}
    write("data/en_translation_lock.json",{"citation_translation_policy":{
        "quote_duplicate_audit_sha256":audit["audit_sha256"]}})
    write(q.INDEX_PATH,idx)
    def validate(value):
        write("data/en_content_lock.json",value)
        ctx=PackageContext(root=tmp_path,report=Report("test",tmp_path.name,["bilingual"]),cache={})
        _validate_final_quote_audit(ctx)
        return [f for f in ctx.report.findings if f.code=="WDV-MWK-021"]
    assert not validate(en)
    # The newly declared AI-only profile requires both lock markers and a
    # independently recomputable audit, even if there is no published quote.
    policy = {"quote_uniqueness_policy": q.UNIQUENESS_POLICY,
              "quote_duplicate_audit_sha256": audit["audit_sha256"]}
    write("data/en_translation_lock.json", {"citation_translation_policy": policy})
    assert not validate({**en, "quote_uniqueness_policy": q.UNIQUENESS_POLICY})
    assert validate(en)
    assert validate({"arguments": args, "quote_uniqueness_policy": q.UNIQUENESS_POLICY})
    write("data/en_translation_lock.json", {"citation_translation_policy": {
        "quote_duplicate_audit_sha256": audit["audit_sha256"]}})
    args[0]["citations"][0].update(quote="Changed",parameters=[{"name":"quote","value":"Changed"}])
    assert validate(en)
    assert validate({"arguments":args})
    # No opt-in on a legacy Work: no new mandatory snapshot.
    write("data/en_translation_lock.json",{})
    assert not validate({"arguments":args})
