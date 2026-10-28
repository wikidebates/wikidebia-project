from pathlib import Path
import json
from jsonschema import Draft202012Validator

SCHEMAS = Path(__file__).resolve().parents[1] / "src" / "wikidebia_validator" / "schemas"

def test_current_manifest_schema_accepts_versions_emitted_by_current_kit():
    schema=json.loads((SCHEMAS/"debate_package.schema.json").read_text(encoding="utf-8"))
    # Inspect declared enums directly: this catches drift even without constructing a whole corpus.
    def find(o):
        if isinstance(o,dict):
            if "translation_semantic_review_schema_version" in o and "semantic_marker_engine_version" in o:
                return o
            for v in o.values():
                r=find(v)
                if r: return r
        elif isinstance(o,list):
            for v in o:
                r=find(v)
                if r: return r
    props=find(schema)
    assert "1.4" in props["translation_semantic_review_schema_version"]["enum"]
    assert "1.3" in props["semantic_marker_engine_version"]["enum"]

def test_name_review_12_allows_empty_scope_fields_when_no_name_found():
    schema=json.loads((SCHEMAS/"argument_name_discovery_review.schema.json").read_text(encoding="utf-8"))
    payload={
      "version":"wikidebia-argument-name-discovery-review-1.2", "normative_revision":"1.2.66", "debate_id":"d",
      "entries":[{"language":"en","page_id":"A1","title":"A complete claim","page_origin":"new","search_reviewed":True,
       "search_queries":["query one","query two"],"search_scope_note":"Academic terminology was checked.","outcome":"none","name":None,"evidence":[],
       "same_reasoning_confirmed":False,"non_invented_label_confirmed":True,"language_fit_confirmed":True,"rationale":"No conventional name was found.",
       "search_provenance":"actual_log","search_provenance_note":"Queries are the actual review log.","page_reasoning_scope_summary":"The page presents its exact stated reasoning.",
       "literature_name_scope_summary":"","scope_relation":"","scope_identity_confirmed":False}]}
    errors=list(Draft202012Validator(schema).iter_errors(payload))
    assert not errors, [e.message for e in errors]

def test_name_review_12_requires_exact_scope_for_known_name():
    schema=json.loads((SCHEMAS/"argument_name_discovery_review.schema.json").read_text(encoding="utf-8"))
    payload={
      "version":"wikidebia-argument-name-discovery-review-1.2", "debate_id":"d",
      "entries":[{"language":"en","page_id":"A1","title":"A complete claim","page_origin":"new","search_reviewed":True,
       "search_queries":["query one","query two"],"search_scope_note":"Academic terminology was checked.","outcome":"known_name","name":"Named argument",
       "evidence":[{"source":"Journal article","label_as_used":"Named argument","locator":"p. 1"}],"same_reasoning_confirmed":True,
       "non_invented_label_confirmed":True,"language_fit_confirmed":True,"rationale":"The conventional label is attested.",
       "search_provenance":"actual_log","search_provenance_note":"Queries are the actual review log.","page_reasoning_scope_summary":"The page presents the exact named reasoning.",
       "literature_name_scope_summary":"","scope_relation":"","scope_identity_confirmed":False}]}
    errors=list(Draft202012Validator(schema).iter_errors(payload))
    assert errors

def test_name_discovery_uses_pre_render_content_lock_when_manifest_pages_are_empty(tmp_path):
    from wikidebia_validator.package import PackageContext
    from wikidebia_validator.report import Report
    from wikidebia_validator.coherence import validate_argument_name_discovery
    manifest={
      "debate_id":"d", "pages":[],
      "editorial_controls":{"argument_name_discovery_path":"reviews/argument_name_discovery_review.json"},
      "core_files":{"registry":"data/registre_debat.json"}
    }
    (tmp_path/"data").mkdir(); (tmp_path/"reviews").mkdir()
    (tmp_path/"manifest.json").write_text(json.dumps(manifest)+"\n",encoding="utf-8")
    (tmp_path/"data/en_content_lock.json").write_text(json.dumps({"arguments":[{"id":"A1","page_origin":"new","canonical_title":"A complete claim"}]})+"\n",encoding="utf-8")
    review={"version":"wikidebia-argument-name-discovery-review-1.2","debate_id":"d","entries":[{
      "language":"en","page_id":"A1","title":"A complete claim","page_origin":"new","search_reviewed":True,
      "search_queries":["query one","query two"],"search_scope_note":"Academic terminology was checked.","outcome":"none","name":None,"evidence":[],
      "same_reasoning_confirmed":False,"non_invented_label_confirmed":True,"language_fit_confirmed":True,"rationale":"No conventional name was found.",
      "search_provenance":"actual_log","search_provenance_note":"Queries are the actual review log.","page_reasoning_scope_summary":"The page presents its exact stated reasoning.",
      "literature_name_scope_summary":"","scope_relation":"","scope_identity_confirmed":False
    }]}
    (tmp_path/"reviews/argument_name_discovery_review.json").write_text(json.dumps(review)+"\n",encoding="utf-8")
    report=Report("0.4.73",str(tmp_path),["coherence"]); ctx=PackageContext(tmp_path,report)
    validate_argument_name_discovery(ctx,manifest)
    assert report.errors==0, [f.to_dict() for f in report.findings]

def test_name_discovery_accepts_revision_bound_adoption_of_work_created_argument(tmp_path):
    from wikidebia_validator.package import PackageContext
    from wikidebia_validator.report import Report
    from wikidebia_validator.coherence import validate_argument_name_discovery
    adoption = {
      "language":"en", "page_id":"A1", "title":"A complete claim",
      "owner_approved":True, "decision":"explicit_user_request",
      "instruction":"Publish the reviewed translation to this exact existing revision.",
      "authorization_receipt_sha256":"a"*64,
      "reason":"An earlier partial publication created this page from the same Work.",
      "allow_proposed_change":True, "observed_revision_id":12,
      "observed_sha256":"b"*64, "allowed_lifecycle_parameter_changes":[]
    }
    manifest={
      "debate_id":"d",
      "pages":[{"language":"en","page_id":"A1","page_type":"argument",
                "page_origin":"preexisting","canonical_title":"A complete claim",
                "existing_english_update":adoption}],
      "editorial_controls":{"argument_name_discovery_path":"reviews/argument_name_discovery_review.json"},
      "core_files":{"registry":"data/registre_debat.json"}
    }
    (tmp_path/"data").mkdir(); (tmp_path/"reviews").mkdir()
    (tmp_path/"manifest.json").write_text(json.dumps(manifest)+"\n",encoding="utf-8")
    review={"version":"wikidebia-argument-name-discovery-review-1.2","debate_id":"d","entries":[{
      "language":"en","page_id":"A1","title":"A complete claim","page_origin":"new","search_reviewed":True,
      "search_queries":["query one","query two"],"search_scope_note":"Academic terminology was checked.","outcome":"none","name":None,"evidence":[],
      "same_reasoning_confirmed":False,"non_invented_label_confirmed":True,"language_fit_confirmed":True,"rationale":"No conventional name was found.",
      "search_provenance":"actual_log","search_provenance_note":"Queries are the actual review log.","page_reasoning_scope_summary":"The page presents its exact stated reasoning.",
      "literature_name_scope_summary":"","scope_relation":"","scope_identity_confirmed":False
    }]}
    (tmp_path/"reviews/argument_name_discovery_review.json").write_text(json.dumps(review)+"\n",encoding="utf-8")
    report=Report("0.4.105",str(tmp_path),["coherence"]); ctx=PackageContext(tmp_path,report)
    validate_argument_name_discovery(ctx,manifest)
    assert report.errors==0, [f.to_dict() for f in report.findings]
