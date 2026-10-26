from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
from pathlib import Path
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load_module(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


translation = load_module("wikidebia_translation_review")
convergence = load_module("wikidebia_semantic_convergence")
content = sys.modules.get("wikidebia_content_review") or load_module("wikidebia_content_review")
metadata = sys.modules.get("wikidebia_editorial_review") or load_module("wikidebia_editorial_review")
common = sys.modules["wikidebia_corpus_build"]


def fake_validator(*args, **kwargs):
    return {"validator_version": "0.4.29", "result": "passed", "summary": {"errors": 0, "warnings": 0}}


metadata._run_validator = fake_validator
content._run_validator = fake_validator
translation._run_validator = fake_validator

from test_wikidebia_content_review import make_metadata_applied, complete_content_review, source_row  # noqa: E402


def test_preexisting_reviewed_pages_require_contextual_relation_labels():
    metadata_lock = {
        "debate": {"page_origin": "preexisting"},
        "arguments": [{"entity_id": "A0001", "page_origin": "preexisting"}],
    }
    content_lock = {
        "debate": {"page_origin": "preexisting"},
        "arguments": [{"id": "A0001", "page_origin": "preexisting"}],
    }

    assert translation._requires_relation_label_review(metadata_lock, content_lock) is True


def test_new_pages_do_not_require_contextual_relation_labels():
    metadata_lock = {
        "debate": {"page_origin": "new"},
        "arguments": [{"entity_id": "A0001", "page_origin": "new"}],
    }
    content_lock = {
        "debate": {"page_origin": "new"},
        "arguments": [{"id": "A0001", "page_origin": "new"}],
    }

    assert translation._requires_relation_label_review(metadata_lock, content_lock) is False


def make_french_locked(tmp_path: Path) -> tuple[Path, Path, str]:
    project, workspace, work_id = make_metadata_applied(tmp_path)
    content.prepare_review(project, "debat_test", work_id)
    complete_content_review(workspace)
    sealed = content.finalize_review(project, "debat_test", work_id)
    content.apply_review(project, "debat_test", work_id, sealed["review_sha256"])
    # The general translation fixture exercises translation of an existing
    # historical introduction. Tests for verified historical absence override
    # this source state explicitly.
    lock_path = workspace / "content-reviewed-copy/data/fr_content_lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    introduction = "{{Sous-partie|titre=Définition|contenu=Le débat test définit précisément la proposition examinée.}}"
    introduction_sha = hashlib.sha256(introduction.encode("utf-8")).hexdigest()
    lock["debate"].update({
        "introduction": introduction,
        "subsections": [{"title": "Définition", "content": "Le débat test définit précisément la proposition examinée."}],
        "introduction_provenance": "historical_existing",
        "historical_introduction_present": True,
        "historical_introduction_sha256": introduction_sha,
        "historical_final_introduction_sha256": introduction_sha,
        "historical_text_decision": "preserved",
        "historical_content_preserved": True,
    })
    lock["historical_text_decisions"]["debate"].update({
        "historical_status": "historical_existing",
        "historical_present": True,
        "historical_sha256": introduction_sha,
        "final_present": True,
        "final_sha256": introduction_sha,
    })
    common.write_json(lock_path, lock)
    meta_path = workspace / "workspace.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["content_reviewed_copy"]["tree_sha256"] = common.full_tree_sha256(workspace / "content-reviewed-copy")
    meta["workspace_sha256"] = None
    meta["workspace_sha256"] = sys.modules["wikidebia_editorial_workspace"].workspace_receipt_hash(meta)
    common.write_json(meta_path, meta)
    return project, workspace, work_id


def mark_existing_english_argument(workspace: Path, node_id: str = "A0004") -> None:
    source = workspace / "content-reviewed-copy"
    registry_path = source / "data/registre_debat.json"
    registry = common.load_json(registry_path, "registre")
    node = next(row for row in registry["graph"]["nodes"] if row["id"] == node_id)
    node["en"].update({
        "canonical_title": "Existing English argument",
        "displayed_title": "Existing English argument",
        "title_status": "locked",
    })
    node["pages"]["en"]["wiki"].update({
        "check_status": "equivalent_existing",
        "decision": "reuse_existing",
        "remote_title": "Existing English argument",
        "remote_revision_id": 42,
    })
    node["pages"]["en"]["generation"]["status"] = "obsolete"
    common.write_json(registry_path, registry)
    meta_path = workspace / "workspace.json"
    meta = common.load_json(meta_path, "workspace")
    meta["content_reviewed_copy"]["tree_sha256"] = common.full_tree_sha256(source)
    meta["workspace_sha256"] = None
    meta["workspace_sha256"] = translation.workspace_receipt_hash(meta)
    common.write_json(meta_path, meta)


def complete_semantic_convergence(project: Path, work_id: str) -> None:
    first = convergence.record_pass(
        project, "debat_test", work_id,
        method_family="proposition_by_proposition",
        method="proposition-by-proposition semantic comparison",
        reviewer="Semantic reviewer A",
        note="The first independent pass compared propositions, modalities, logical relations and scope against the sealed French source.",
        new_certain_errors=0,
    )
    assert first["status"] == "in_progress"
    second = convergence.record_pass(
        project, "debat_test", work_id,
        method_family="risk_marker_review",
        method="risk-marker and boundary-focused reread",
        reviewer="Semantic reviewer B",
        note="The second independent pass rechecked risk markers, opening and closing propositions, exclusivities and concrete anchors.",
        new_certain_errors=0,
    )
    assert second["status"] == "converged"


def en_source(source_id: str, source_type: str, usages: list[dict[str, object]]) -> dict[str, object]:
    row = source_row(source_id, source_type, usages)
    row["language"] = "en"
    row["metadata"]["authors"] = [f"English Author {int(source_id[1:])}"]
    row["metadata"]["date"] = "3 August 2026"
    if source_type == "bibliography":
        row["metadata"]["work"] = f"English Reference Work {int(source_id[1:])}"
    elif source_type == "webliography":
        row["metadata"]["page"] = f"English documentary page {int(source_id[1:])}"
        row["metadata"]["site"] = f"English documentary site {int(source_id[1:])}"
    else:
        row["metadata"]["title"] = f"English documentary video {int(source_id[1:])}"
        row["metadata"]["site"] = f"English video platform {int(source_id[1:])}"
    row["verification"]["notes"] = ["English language, notice and attribution verified."]
    row["usage"] = usages
    row["deduplication_key"] = f"en-source-{int(source_id[1:])}"
    return row


def complete_translation_review(workspace: Path) -> None:
    path = workspace / "reviews/en/translation_review.json"
    review = json.loads(path.read_text(encoding="utf-8"))
    translations = {
        "argumentation": "argumentation", "cohérence": "coherence", "confirmation": "confirmation",
        "controverse": "controversy", "désaccord": "disagreement", "justification": "justification",
        "preuve": "evidence", "raisonnement": "reasoning", "réfutation": "refutation", "thèse": "thesis",
        "test": "test",
    }
    for row in review["vocabulary"]:
        row.update({
            "en": translations[row["fr"]],
            "definition_en": f"Controlled editorial concept corresponding to {translations[row['fr']]}",
            "capitalization_verified": True,
            "capitalization_rationale_en": "",
            "status": "approved", "idiomatic_equivalent": True, "same_concept": True,
            "reviewer": "English reviewer", "reviewed_at": "2026-08-03T21:30:00+02:00",
            "note": "The English term is idiomatic and preserves the French navigation concept.",
        })
    debate = review["debate"]
    fr_meta = debate["french"]["metadata"]
    debate.update({
        "status": "approved", "canonical_title": "Test debate", "topic": "Test debate",
        "complete_topic": "the proposition of the test debate",
        "sections": sorted([translation.SECTION_MAP[x] for x in fr_meta["rubriques"]], key=str.casefold),
        "keywords": [translations[x] for x in fr_meta["keywords"]],
        "introduction": "{{Subsection|title=Definition and scope|content=The test debate contrasts two clearly delimited answers and specifies what is actually at issue.}}{{Subsection|title=Stakes of the debate|content=The answer adopted changes how the phenomenon is explained and which standards are used to accept a conclusion. It may also shape collective decisions, institutional practices, and individual choices beyond the theoretical disagreement itself. Suspending judgment shifts attention toward the limits of the available evidence and toward the degree of confidence that can reasonably be placed in each position.}}",
        "subsections": [{"title": "Definition and scope", "purpose": "Define the proposition and the exact scope required to understand the disagreement.", "necessary_for_understanding": True, "technical_or_specialized": False, "relevance_to_debate_explained": True, "stakes_section": False, "concrete_stakes": []}, {"title": "Stakes of the debate", "purpose": "Explain the intellectual, institutional, and practical consequences of the possible answers.", "necessary_for_understanding": True, "technical_or_specialized": False, "relevance_to_debate_explained": True, "stakes_section": True, "concrete_stakes": ["Changes to explanatory frameworks and standards of rational belief", "Consequences for collective decisions and institutional practices"]}],
        "wikipedia_articles": ["Argumentation theory"],
        "documentation": {
            "pro-bibliography": ["S10001"], "con-bibliography": ["S10002"], "bibliography": [],
            "pro-webliography": ["S10003"], "con-webliography": ["S10004"], "webliography": [],
            "pro-videography": ["S10005"], "con-videography": ["S10006"], "videography": [],
        },
        "documentation_family_notes": {"bibliography": "Broad English-language works cover the debate.", "webliography": "Verified English-language web sources complement the books.", "videography": "Verified English-language videos cover each position."},
        "topic_label_rationale": "The nominal label identifies the controversy without restating it as a question.",
        "metadata_equivalent_to_french": True, "content_equivalent_to_french": True,
        "canonical_title_semantic_inventory_reviewed": True,
        "canonical_title_semantic_inventory_note": "Subject, predicate, scope and force of the canonical debate title were compared against the French source.",
        "topic_semantic_equivalence_reviewed": True,
        "complete_topic_semantic_equivalence_reviewed": True,
        "introduction_claim_inventory_reviewed": True,
        "introduction_claim_inventory_note": "All substantive claims, distinctions, historical framing and stakes in the French introduction were checked against the English introduction.",
        "subsection_structure_equivalence_reviewed": True,
        "sections_exactly_mapped": True, "keywords_exactly_mapped": True,
        "keywords_order_preserved_by_relevance": True,
        "introduction_functionally_equivalent": True, "wikipedia_articles_verified": True,
        "all_debate_sources_english": True, "reviewer": "English reviewer",
        "reviewed_at": "2026-08-03T21:40:00+02:00",
        "note": "The Debate metadata, introduction and documentation are ready for the bilingual lock.",
    })
    fr_dmeta = debate["french"]["metadata"]
    fr_dcontent = debate["french"]["content"]
    debate_pairs = {
        "canonical_title": (str(fr_dmeta.get("canonical_title") or ""), debate["canonical_title"]),
        "topic": (str(fr_dcontent.get("subject") or ""), debate["topic"]),
        "complete_topic": (str(fr_dcontent.get("complete_topic") or ""), debate["complete_topic"]),
        "introduction": (str(fr_dcontent.get("introduction") or ""), debate["introduction"]),
    }
    debate_risks = []
    debate_evidence = []
    for field_name, (source_text, target_text) in debate_pairs.items():
        for risk in translation._semantic_risk_signals(source_text, target_text):
            tagged = f"{field_name}:{risk}"
            debate_risks.append(tagged)
            debate_evidence.append({"risk": tagged, "source_excerpt": source_text, "target_excerpt": target_text, "note": "The source and target field were compared directly for this semantic-risk signal."})
    debate["debate_field_semantic_risk_reviewed"] = bool(debate_risks)
    debate["debate_field_semantic_risk_note"] = "All detected Debate field-level semantic risks were checked against the locked French source." if debate_risks else ""
    debate["debate_field_semantic_risk_evidence"] = debate_evidence
    for field in translation.INTRO_TRUE_FIELDS:
        debate[field] = True
    for field in translation.HISTORICAL_INTRO_TRANSLATION_TRUE_FIELDS:
        debate[field] = True
    debate["introduction_adaptation_rationale"] = "The historical French introduction was reviewed for France-specific context and adapted only where appropriate for an international English-speaking readership."
    titles = {
        "A0001": ("Demonstration A explicitly supports the proposition of the test debate", "Evidence A supports the thesis"),
        "A0002": ("Demonstration B directly challenges the proposition of the test debate", "Evidence B challenges the thesis"),
        "A0003": ("Demonstration C specifically strengthens argument A in the test debate", "Evidence C strengthens argument A"),
        "A0004": ("Demonstration D distinctly confirms the proposition of the test debate", "Evidence D confirms the thesis"),
    }
    # The French fixture deliberately contains historical one-letter summaries
    # (A/B/C/D).  Since 2.16.17 preserves them by default instead of rewriting them in
    # fr_content_review, the translation fixture must translate the exact source
    # rather than silently expanding it.
    summaries = {"A0001": "A", "A0002": "B", "A0003": "C", "A0004": "D"}
    expressions = {"A0001": "", "A0002": "", "A0003": "", "A0004": ""}
    for item in review["arguments"]:
        nid = item["id"]
        row = item["translation"]
        fr_meta = row["french"]["metadata"]
        row.update({
            "status": "approved", "canonical_title": titles[nid][0], "displayed_title": titles[nid][1],
            "sections": sorted([translation.SECTION_MAP[x] for x in fr_meta["rubriques"]], key=str.casefold),
            "keywords": [translations[x] for x in fr_meta["keywords"]], "summary": summaries[nid],
            "sources": {"bibliography": ["S10001"], "webliography": [], "videography": []},
            "argument_name_search_queries": [f'"{titles[nid][0]}" argument', f'{titles[nid][0]} conventional name literature'],
            "argument_name_search_scope_note": "English-language academic terminology and alternative phrasings were checked.",
            "argument_name_search_provenance": "actual_log",
            "argument_name_search_provenance_note": "The two query strings above were actually used during this test review.",
            "argument_name_outcome": "none", "argument_name": None, "argument_name_evidence": [],
            "argument_name_same_reasoning_confirmed": False,
            "argument_name_non_invented_label_confirmed": True,
            "argument_name_language_fit_confirmed": True,
            "argument_name_rationale": "No sufficiently established conventional name was found for this generated argument.",
            "argument_name_page_reasoning_scope_summary": "This page presents the exact reasoning expressed by its canonical title and summary.",
            "argument_name_literature_scope_summary": "",
            "argument_name_scope_relation": "",
            "argument_name_scope_identity_confirmed": False,
            "metadata_equivalent_to_french": True, "summary_equivalent_to_french": True,
            "canonical_title_semantic_inventory_reviewed": True,
            "canonical_title_semantic_inventory_note": "Subject, predicate, polarity, modality, attribution, quantifiers, force and logical relation of the canonical title were compared.",
            "canonical_title_equivalent_to_french": True,
            "canonical_title_subject_preserved": True, "canonical_title_predicate_preserved": True,
            "canonical_title_scope_preserved": True, "canonical_title_modality_preserved": True,
            "sections_exactly_mapped": True, "keywords_exactly_mapped": True,
        "keywords_order_preserved_by_relevance": True,
            "title_is_idiomatic": True,
            "displayed_title_source_form": "proposition", "displayed_title_target_form": "proposition",
            "displayed_title_source_form_reviewed": True, "displayed_title_no_formal_regression": True,
            "displayed_title_semantic_inventory_reviewed": True,
            "displayed_title_semantic_inventory_note": "Subject, predicate, polarity, modality, attribution, quantifiers, force, temporal scope, conditions and logical relation were compared.",
            "displayed_title_subject_preserved": True, "displayed_title_predicate_preserved": True,
            "displayed_title_scope_preserved": True, "displayed_title_modality_preserved": True,
            "displayed_title_translates_french_displayed_title": True,
            "displayed_title_identity_pattern_reviewed": True,
            "displayed_title_identity_pattern_note": "The English displayed title was compared directly with the French displayed title and not regenerated from the canonical title.",
            "displayed_title_is_complete_proposition": True,
            "displayed_title_concision_reviewed": True,
            "displayed_title_semantically_equivalent": True,
            "displayed_title_improves_readability_when_distinct": True,
            "summary_ratio_reviewed": True,
            "summary_subject_predicate_scope_modality_reviewed": True,
            "summary_opening_proposition_preserved": True,
            "summary_closing_proposition_preserved": True,
            "summary_conditions_exclusivities_preserved": True,
            "summary_decisive_premises_preserved": True,
            "summary_semantic_evidence_note": "Opening and closing propositions, conditions, exclusivities and decisive premises were compared directly with the French source.",
            "semantic_risk_reviewed": True,
            "semantic_risk_note": "Any semantic marker differences were explicitly reviewed against the French source and judged equivalent.",
            "forceful_expression": expressions[nid], "quantitative_claims_verified": False,
            "quantitative_claims_note": "No quantitative claim appears in this English summary.",
            "documentation_rationale": "The selected English source supports the central mechanism without imposing an artificial quota.",
            "reviewer": "English reviewer", "reviewed_at": "2026-08-03T21:45:00+02:00",
            "note": "The English title, summary, sections, keywords and documentation preserve the French node.",
        })
        fr_row = row["french"]
        fr_meta_row = fr_row["metadata"]
        fr_content_row = fr_row["content"]
        semantic_pairs = [
            (str(fr_meta_row.get("canonical_title") or ""), row["canonical_title"]),
            (str(fr_meta_row.get("displayed_title") or ""), row["displayed_title"]),
            (str(fr_content_row.get("summary") or ""), row["summary"]),
        ]
        risks = sorted({risk for source_text, target_text in semantic_pairs for risk in translation._semantic_risk_signals(source_text, target_text)})
        row["semantic_risk_reviewed"] = bool(risks)
        row["semantic_risk_note"] = "All semantic-risk signals in this test fixture were compared directly with the French source." if risks else ""
        row["semantic_risk_evidence"] = []
        for risk in risks:
            for source_text, target_text in semantic_pairs:
                if risk in translation._semantic_risk_signals(source_text, target_text):
                    row["semantic_risk_evidence"].append({"risk": risk, "source_excerpt": source_text, "target_excerpt": target_text, "note": "The source and target excerpts were checked directly for this semantic-risk signal."})
                    break
        translated_quotes = {
            "A0001": ("Freedom consists in wanting what one wants.", "25 June 2012"),
            "A0002": ("A sufficient cause is not necessarily a constraint.", "June 2012"),
            "A0003": ("The reasoning retains its force in this case.", "1971"),
            "A0004": ("The reasoning retains its force in this case.", "1971"),
        }
        for citation in row.get("citations") or []:
            translated_text, translated_date = translated_quotes[nid]
            citation.update({
                "status": "approved",
                "translated_citation": translated_text,
                "translated_date": translated_date,
                "citation_translated": True,
                "date_translated_or_language_neutral": True,
                "preserved_parameters_unchanged": True,
                "translation_warning_appended": True,
                "quote_completeness_reviewed": True,
                "quote_completeness_note": "The full French citation was compared from beginning to end with the English translation.",
                "quote_low_ratio_reviewed": True,
                "quote_low_ratio_note": "The English wording is concise but the full source meaning and all sentences were checked.",
                "reviewer": "English citation reviewer",
                "reviewed_at": "2026-08-03T21:46:00+02:00",
                "note": "Only the citation text and date were translated; all documentary parameters were preserved.",
            })
        for field in translation.SUMMARY_TRUE_FIELDS:
            row[field] = True
    translated_by_id = {item["id"]: item["translation"] for item in review["arguments"]}
    for label in review.get("relation_labels") or []:
        label.update(translated_text=translated_by_id[label["target_node_id"]]["displayed_title"],
                     equivalent_to_french=True, review_note="The exact source occurrence was independently translated and reviewed.")
    for unit in review.get("review_units") or []:
        unit.update({
            "status": "approved", "reviewer": "Unit reviewer",
            "reviewed_at": "2026-08-03T21:59:00+02:00",
            "note": "This review unit was closed independently at the density recommended from the French source.",
        })
    for relation_label in review.get("relation_labels") or []:
        relation_label.update({
            "translated_text": f"Translated contextual label {relation_label['id']}",
            "equivalent_to_french": True,
            "review_note": "The contextual source label and its English translation were compared directly.",
        })
    review["global_review"] = {
        "reviewer": "English reviewer", "reviewed_at": "2026-08-03T22:00:00+02:00",
        "all_entities_translated": True, "all_equivalences_reviewed": True,
        "all_selected_sources_verified": True, "relations_and_occurrences_unchanged": True,
        "no_final_pages_generated": True, "remote_access_not_used": True,
        "blocking_issues": [], "note": "The English projection is complete, equivalent and ready to be locked without rendering pages.",
    }
    common.write_json(path, review)

    source_roles = {
        "S10001": "pro_reference", "S10002": "con_reference",
        "S10003": "pro_reference", "S10004": "con_reference",
        "S10005": "pro_reference", "S10006": "con_reference",
    }
    sources = []
    for sid, stype in (("S10001", "bibliography"), ("S10002", "bibliography"), ("S10003", "webliography"), ("S10004", "webliography"), ("S10005", "videography"), ("S10006", "videography")):
        usages = [{"page_id": "debat_test", "language": "en", "role": source_roles[sid], "language_fit": "native", "preferred_equivalent_source_id": None, "documentary_scope": "broad_synthesis", "selection_reason": "This verified English source documents the orientation assigned to it."}]
        if sid == "S10001":
            usages.extend({"page_id": nid, "language": "en", "role": "supports_summary", "argument_development_verified": True, "also_develops_objections": False, "objection_coverage_note": None, "language_fit": "native", "preferred_equivalent_source_id": None, "documentary_scope": "narrow_argument", "selection_reason": "This English source directly supports the mechanism stated in the argument summary."} for nid in titles)
        sources.append(en_source(sid, stype, usages))
    common.write_json(workspace / "data/sources_en_working.json", {"schema": translation.EN_SOURCES_WORKING_SCHEMA, "source_registry_version": "1.0", "debate_id": "debat_test", "work_id": review["work_id"], "status": "draft", "prepared_at": review["prepared_at"], "sources": sources})


def test_prepare_translation_is_read_only_for_french_copy(tmp_path: Path):
    project, workspace, work_id = make_french_locked(tmp_path)
    before = common.full_tree_sha256(workspace / "content-reviewed-copy")
    result = translation.prepare_review(project, "debat_test", work_id)
    assert result["status"] == "en_translation_review_ready"
    assert common.full_tree_sha256(workspace / "content-reviewed-copy") == before
    assert not (workspace / "translated-copy").exists()
    meta = json.loads((workspace / "workspace.json").read_text(encoding="utf-8"))
    assert meta["boundaries"]["english_translation_started"] is True
    assert meta["boundaries"]["final_pages_generated"] is False


def test_prepare_translation_reuses_verified_existing_english_argument(tmp_path: Path):
    project, workspace, work_id = make_french_locked(tmp_path)
    mark_existing_english_argument(workspace)

    result = translation.prepare_review(project, "debat_test", work_id)
    review = common.load_json(workspace / "reviews/en/translation_review.json", "review")
    readiness = common.load_json(workspace / "reviews/en/translation_readiness.json", "readiness")

    assert result["arguments"] == 3
    assert result["reused_existing_arguments"] == 1
    assert "A0004" not in {row["id"] for row in review["arguments"]}
    assert "A0004" not in {row["target_node_id"] for row in review["relation_labels"]}
    reused = next(row for row in readiness["items"] if row.get("entity_id") == "A0004")
    assert reused["translation_status"] == "reuse_existing_english_page"


def test_finalize_translation_seals_complete_bilingual_review(tmp_path: Path):
    project, workspace, work_id = make_french_locked(tmp_path)
    translation.prepare_review(project, "debat_test", work_id)
    complete_translation_review(workspace)
    before = common.full_tree_sha256(workspace / "content-reviewed-copy")
    result = translation.finalize_review(project, "debat_test", work_id)
    assert result["status"] == "en_translation_review_finalized"
    assert result["arguments"] == 4
    assert result["sources"] == 6
    assert common.full_tree_sha256(workspace / "content-reviewed-copy") == before
    sealed = json.loads((workspace / "reviews/en/translation_review.json").read_text(encoding="utf-8"))
    assert sealed["review_sha256"] == translation.translation_review_sha256(sealed)


def test_finalize_preserves_historically_absent_debate_introduction(tmp_path: Path):
    project, workspace, work_id = make_french_locked(tmp_path)
    lock_path = workspace / "content-reviewed-copy/data/fr_content_lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock["debate"].update({
        "introduction": "",
        "subsections": [],
        "introduction_provenance": "historical_absent",
        "historical_introduction_present": False,
        "historical_text_decision": "preserved",
        "historical_content_preserved": True,
    })
    lock["historical_text_decisions"]["debate"].update({
        "historical_status": "historical_absent",
        "historical_present": False,
        "historical_sha256": hashlib.sha256(b"").hexdigest(),
        "final_present": False,
        "final_sha256": hashlib.sha256(b"").hexdigest(),
    })
    common.write_json(lock_path, lock)
    meta_path = workspace / "workspace.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["content_reviewed_copy"]["tree_sha256"] = common.full_tree_sha256(workspace / "content-reviewed-copy")
    meta["workspace_sha256"] = None
    meta["workspace_sha256"] = sys.modules["wikidebia_editorial_workspace"].workspace_receipt_hash(meta)
    common.write_json(meta_path, meta)

    translation.prepare_review(project, "debat_test", work_id)
    complete_translation_review(workspace)
    review_path = workspace / "reviews/en/translation_review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["debate"].update({
        "introduction": "",
        "subsections": [],
        "introduction_adaptation_rationale": "The locked French debate historically contains no introduction, so the English projection preserves that verified absence.",
    })
    common.write_json(review_path, review)

    result = translation.finalize_review(project, "debat_test", work_id)
    assert result["status"] == "en_translation_review_finalized"
    finalized = json.loads(review_path.read_text(encoding="utf-8"))
    assert finalized["final_values"]["debate"]["introduction"] == ""
    assert finalized["final_values"]["debate"]["subsections"] == []


def test_finalize_rejects_missing_vocabulary_equivalence(tmp_path: Path):
    project, workspace, work_id = make_french_locked(tmp_path)
    translation.prepare_review(project, "debat_test", work_id)
    complete_translation_review(workspace)
    path = workspace / "reviews/en/translation_review.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["vocabulary"][0]["same_concept"] = False
    common.write_json(path, data)
    try:
        translation.finalize_review(project, "debat_test", work_id)
    except translation.TranslationReviewError as exc:
        assert "Équivalence lexicale" in str(exc)
    else:
        raise AssertionError("Équivalence lexicale incomplète acceptée")


def test_finalize_rejects_established_name_injected_as_extra_keyword(tmp_path: Path):
    project, workspace, work_id = make_french_locked(tmp_path)
    translation.prepare_review(project, "debat_test", work_id)
    complete_translation_review(workspace)
    path = workspace / "reviews/en/translation_review.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    row = data["arguments"][0]["translation"]
    row.update({
        "argument_name_outcome": "known_name",
        "argument_name": "Cosmological argument",
        "argument_name_evidence": [{"source": "Academic reference", "note": "The source uses this exact label for the same reasoning."}],
        "argument_name_same_reasoning_confirmed": True,
        "argument_name_non_invented_label_confirmed": True,
        "argument_name_language_fit_confirmed": True,
        "argument_name_rationale": "The academic literature uses this exact established label for the reasoning on the page.",
        "argument_name_page_reasoning_scope_summary": "The page presents the complete causal reasoning covered by the established label.",
        "argument_name_literature_scope_summary": "The cited literature uses the label for the same complete causal reasoning.",
        "argument_name_scope_relation": "exact_match",
        "argument_name_scope_identity_confirmed": True,
    })
    row["keywords"].append("Cosmological argument")
    common.write_json(path, data)
    try:
        translation.finalize_review(project, "debat_test", work_id)
    except translation.TranslationReviewError as exc:
        assert "Keywords anglais divergents" in str(exc)
    else:
        raise AssertionError("Un established-name injecté comme keyword supplémentaire aurait dû être refusé")


def test_finalize_accepts_short_historical_summary_without_rewriting_it(tmp_path: Path):
    project, workspace, work_id = make_french_locked(tmp_path)
    translation.prepare_review(project, "debat_test", work_id)
    complete_translation_review(workspace)
    sealed = translation.finalize_review(project, "debat_test", work_id)
    first = next(row for row in json.loads((workspace / "reviews/en/translation_review.json").read_text(encoding="utf-8"))["final_values"]["arguments"] if row["id"] == "A0001")
    assert first["summary"] == "A"
    assert first["summary_provenance"] == "historical_existing"
    assert first["summary_length_ratio"] == 1.0
    assert first["forceful_expression"] is None


def test_finalize_historical_summary_ratio_requires_explicit_exception_rationale(tmp_path: Path):
    project, workspace, work_id = make_french_locked(tmp_path)
    translation.prepare_review(project, "debat_test", work_id)
    complete_translation_review(workspace)
    path = workspace / "reviews/en/translation_review.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["arguments"][0]["translation"]["summary"] = "Evidence A supports the thesis with a premise."
    data["arguments"][0]["translation"]["forceful_expression"] = "Evidence A supports the thesis"
    common.write_json(path, data)
    try:
        translation.finalize_review(project, "debat_test", work_id)
    except translation.TranslationReviewError as exc:
        assert "Ratio anglais/français historique" in str(exc)
    else:
        raise AssertionError("Historical out-of-range ratio without rationale accepted")

    data = json.loads(path.read_text(encoding="utf-8"))
    data["arguments"][0]["translation"]["summary_ratio_exception_rationale"] = "The English phrase is longer because an idiomatic explicit subject is required, while the same one-letter historical proposition and scope are preserved."
    common.write_json(path, data)
    sealed = translation.finalize_review(project, "debat_test", work_id)
    assert sealed["status"] == "en_translation_review_finalized"


def test_finalize_rejects_non_english_debate_source(tmp_path: Path):
    project, workspace, work_id = make_french_locked(tmp_path)
    translation.prepare_review(project, "debat_test", work_id)
    complete_translation_review(workspace)
    path = workspace / "data/sources_en_working.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["sources"][0]["language"] = "fr"
    common.write_json(path, data)
    try:
        translation.finalize_review(project, "debat_test", work_id)
    except translation.TranslationReviewError as exc:
        assert "doit être en" in str(exc)
    else:
        raise AssertionError("Source française acceptée dans la projection anglaise")


def test_apply_translation_creates_distinct_bilingual_copy(tmp_path: Path):
    project, workspace, work_id = make_french_locked(tmp_path)
    translation.prepare_review(project, "debat_test", work_id)
    complete_translation_review(workspace)
    sealed = translation.finalize_review(project, "debat_test", work_id)
    corpus_hash = common.full_tree_sha256(project / "corpus/debat_test")
    content_hash = common.full_tree_sha256(workspace / "content-reviewed-copy")
    fr_meta = (workspace / "content-reviewed-copy/data/fr_page_metadata_lock.json").read_bytes()
    fr_content = (workspace / "content-reviewed-copy/data/fr_content_lock.json").read_bytes()
    complete_semantic_convergence(project, work_id)
    result = translation.apply_review(project, "debat_test", work_id, sealed["review_sha256"])
    target = workspace / "translated-copy"
    assert result["status"] == "en_translation_applied"
    assert target.is_dir()
    assert common.full_tree_sha256(project / "corpus/debat_test") == corpus_hash
    assert common.full_tree_sha256(workspace / "content-reviewed-copy") == content_hash
    assert (target / "data/fr_page_metadata_lock.json").read_bytes() == fr_meta
    assert (target / "data/fr_content_lock.json").read_bytes() == fr_content
    assert (target / "data/en_page_metadata_lock.json").is_file()
    assert (target / "data/en_content_lock.json").is_file()
    assert (target / "data/en_translation_lock.json").is_file()
    assert (target / "data/keyword_vocabulary_bilingual.json").is_file()
    assert not (target / "output").exists()
    registry = json.loads((target / "data/registre_debat.json").read_text(encoding="utf-8"))
    assert registry["debate"]["pages"]["en"]["canonical_title"] == "Test debate"
    assert all(node["en"]["title_status"] == "validated" for node in registry["graph"]["nodes"] if node["status"] == "active")
    name_review = json.loads((target / "reviews/argument_name_discovery_review.json").read_text(encoding="utf-8"))
    assert name_review["normative_revision"] == translation.NORM_VERSION
    assert name_review["version"] == "wikidebia-argument-name-discovery-review-1.2"
    assert all(row.get("search_provenance") in {"actual_log", "fresh_recheck"} for row in name_review["entries"] if row.get("language") == "en")
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert "argument_name_discovery_revision" not in manifest["editorial_controls"]
    assert manifest["editorial_controls"]["argument_name_discovery_path"] == "reviews/argument_name_discovery_review.json"



def test_finalize_translation_preserves_citation_metadata_and_appends_warning(tmp_path: Path):
    project, workspace, work_id = make_french_locked(tmp_path)
    translation.prepare_review(project, "debat_test", work_id)
    complete_translation_review(workspace)
    sealed = translation.finalize_review(project, "debat_test", work_id)
    complete_semantic_convergence(project, work_id)
    translation.apply_review(project, "debat_test", work_id, sealed["review_sha256"])
    lock = json.loads((workspace / "translated-copy/data/en_content_lock.json").read_text(encoding="utf-8"))
    by_id = {row["id"]: row for row in lock["arguments"]}
    a = by_id["A0001"]["citations"][0]
    source_preserved = {row["name"]: row["value"] for row in a["source"]["preserved_parameters"]}
    output = {row["name"]: row["value"] for row in a["parameters"]}
    assert source_preserved["auteurs"] == "Harry G. Frankfurt"
    assert output["authors"] == "Harry G. Frankfurt"
    assert output["work"] == "The Importance of What We Care About"
    assert output["article"] == "Freedom of the Will and the Concept of a Person"
    assert output["quote"] == "Freedom consists in wanting what one wants."
    assert output["date"] == "25 June 2012"
    assert output["warnings"] == "Texte abrégé, AI-translated quote"
    assert a["output_template"] == "Quote"
    assert a["quote_completeness_reviewed"] is True
    assert a["source_word_count"] > 0 and a["translated_word_count"] > 0
    assert isinstance(a["lexical_ratio"], float)
    assert all(row["name"] not in {"citation", "auteurs", "ouvrage", "numéro", "localisation", "édition", "lieu", "lien", "avertissements-citation"} for row in a["parameters"])
    b = by_id["A0002"]["citations"][0]
    output_b = {row["name"]: row["value"] for row in b["parameters"]}
    assert output_b["warnings"] == "AI-translated quote"
    assert by_id["A0004"]["citations"][0]["date"] == "1971"


def test_finalize_translation_rejects_wrong_citation_date(tmp_path: Path):
    project, workspace, work_id = make_french_locked(tmp_path)
    translation.prepare_review(project, "debat_test", work_id)
    complete_translation_review(workspace)
    path = workspace / "reviews/en/translation_review.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["arguments"][0]["translation"]["citations"][0]["translated_date"] = "26 June 2012"
    common.write_json(path, data)
    try:
        translation.finalize_review(project, "debat_test", work_id)
    except translation.TranslationReviewError as exc:
        assert "même date" in str(exc)
    else:
        raise AssertionError("Date de citation divergente acceptée")


@pytest.mark.parametrize(("source", "target"), [
    ("29 sep 2021", "29 September 2021"),
    ("23 jan 2023", "23 January 2023"),
    ("08 Mar 2022", "8 March 2022"),
    ("29/05/18", "29 May 2018"),
    ("janvier-février 2023", "January–February 2023"),
])
def test_historical_citation_date_formats_match_english_translation(source: str, target: str):
    assert translation._date_signature(source, "fr") == translation._date_signature(target, "en")


def test_finalize_translation_rejects_mutated_citation_source_parameters(tmp_path: Path):
    project, workspace, work_id = make_french_locked(tmp_path)
    translation.prepare_review(project, "debat_test", work_id)
    complete_translation_review(workspace)
    path = workspace / "reviews/en/translation_review.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["arguments"][0]["translation"]["citations"][0]["source"]["preserved_parameters"][0]["value"] = "Auteur modifié"
    common.write_json(path, data)
    try:
        translation.finalize_review(project, "debat_test", work_id)
    except translation.TranslationReviewError as exc:
        assert "paramètres source" in str(exc)
    else:
        raise AssertionError("Altération des paramètres documentaires acceptée")

def test_apply_requires_exact_translation_hash(tmp_path: Path):
    project, workspace, work_id = make_french_locked(tmp_path)
    translation.prepare_review(project, "debat_test", work_id)
    complete_translation_review(workspace)
    translation.finalize_review(project, "debat_test", work_id)
    complete_semantic_convergence(project, work_id)
    try:
        translation.apply_review(project, "debat_test", work_id, "0" * 64)
    except translation.TranslationReviewError as exc:
        assert "empreinte confirmée" in str(exc)
    else:
        raise AssertionError("Mauvaise empreinte anglaise acceptée")
    assert not (workspace / "translated-copy").exists()


def test_finalize_rejects_french_copy_changed_after_prepare(tmp_path: Path):
    project, workspace, work_id = make_french_locked(tmp_path)
    translation.prepare_review(project, "debat_test", work_id)
    complete_translation_review(workspace)
    (workspace / "content-reviewed-copy/scope.json").write_text("{}\n", encoding="utf-8")
    try:
        translation.finalize_review(project, "debat_test", work_id)
    except translation.TranslationReviewError as exc:
        assert "content-reviewed-copy" in str(exc)
    else:
        raise AssertionError("Base française altérée acceptée")


def test_finalize_translation_rejects_french_template_in_english_introduction(tmp_path: Path):
    project, workspace, work_id = make_french_locked(tmp_path)
    translation.prepare_review(project, "debat_test", work_id)
    complete_translation_review(workspace)
    path = workspace / "reviews/en/translation_review.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["debate"]["introduction"] = "{{Sous-partie|titre=Definition|contenu=This English paragraph explains the debate in sufficient detail for a general reader.}}"
    common.write_json(path, data)
    try:
        translation.finalize_review(project, "debat_test", work_id)
    except translation.TranslationReviewError as exc:
        assert "Modèle français interdit" in str(exc)
    else:
        raise AssertionError("Un modèle français a été accepté dans l’introduction anglaise")


def test_finalize_translation_rejects_french_parameter_in_english_summary(tmp_path: Path):
    project, workspace, work_id = make_french_locked(tmp_path)
    translation.prepare_review(project, "debat_test", work_id)
    complete_translation_review(workspace)
    path = workspace / "reviews/en/translation_review.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    summary = data["arguments"][0]["translation"]["summary"]
    data["arguments"][0]["translation"]["summary"] = summary + " {{Wikipedia link|article=Free will|texte-affiché=free will}}"
    common.write_json(path, data)
    try:
        translation.finalize_review(project, "debat_test", work_id)
    except translation.TranslationReviewError as exc:
        assert "Paramètre français interdit" in str(exc)
    else:
        raise AssertionError("Un paramètre français a été accepté dans le summary anglais")


def test_vocabulary_accepts_justified_english_proper_name_and_rejects_common_capital():
    french = [{
        "fr": "Dieu", "kind": "proper_name",
        "capitalization_policy": "canonical_proper_name",
    }]
    rows = [{
        "fr": "Dieu", "en": "God", "definition_en": "The proper name used for the deity.",
        "kind": "proper_name", "capitalization_policy": "canonical_proper_name",
        "capitalization_verified": True,
        "capitalization_rationale_en": "Canonical English proper name for the deity.",
        "status": "approved", "idiomatic_equivalent": True, "same_concept": True,
        "reviewer": "English reviewer", "reviewed_at": "2026-08-04T14:00:00+02:00",
        "note": "The term preserves the same concept and canonical spelling.",
    }]
    result, mapping = translation._validate_vocabulary(rows, french)
    assert mapping == {"Dieu": "God"}
    bad_french = [{"fr": "revenu", "kind": "noun", "capitalization_policy": "lowercase_common"}]
    bad_rows = [dict(rows[0], fr="revenu", en="Income", kind="noun", capitalization_policy="lowercase_common", capitalization_rationale_en="")]
    try:
        translation._validate_vocabulary(bad_rows, bad_french)
    except translation.TranslationReviewError as exc:
        assert "Capitalisation anglaise non canonique" in str(exc)
    else:
        raise AssertionError("Capitalized English common noun accepted")


def test_finalize_translation_accepts_historical_introduction_without_stakes_subsection(tmp_path: Path):
    project, workspace, work_id = make_french_locked(tmp_path)
    translation.prepare_review(project, "debat_test", work_id)
    complete_translation_review(workspace)
    review_path = workspace / "reviews/en/translation_review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    debate = review["debate"]
    debate["introduction"] = "{{Subsection|title=Definition and scope|content=This historical introduction defines the scope and the precise disagreement for an international readership without adding a newly generated stakes subsection.}}"
    debate["subsections"] = [debate["subsections"][0]]
    debate["introduction_claim_inventory_note"] = "The historical source claims and the localized English scope were reviewed without imposing a creation-only stakes subsection."
    common.write_json(review_path, review)
    sealed = translation.finalize_review(project, "debat_test", work_id)
    assert sealed["status"] == "en_translation_review_finalized"




def nominal_argument_translation():
    row = {
        "status": "approved", "page_origin": "new", "source_page_origin": "preexisting", "preserved_parameters": {},
        "french": {
            "metadata": {"page_origin": "preexisting", "canonical_title": "Titre canonique historique complet", "displayed_title": "Liberté et revenu", "rubriques": ["Économie"], "keywords": ["revenu", "liberté", "travail", "autonomie", "justice"]},
            "content": {"page_origin": "preexisting", "summary": None, "summary_provenance": "historical_absent", "citations": []},
        },
        "canonical_title": "A complete historical canonical argument about basic income",
        "displayed_title": "Freedom and income",
        "sections": ["Economy"], "keywords": ["income", "freedom", "work", "autonomy", "justice"], "summary": "",
        "citations": [], "sources": {"bibliography": [], "webliography": [], "videography": []},
        "argument_name_search_queries": ["historical name one", "historical name two"], "argument_name_search_scope_note": "Not used for historical source provenance.",
        "argument_name_search_provenance": "fresh_recheck", "argument_name_search_provenance_note": "Not used for historical source provenance.",
        "argument_name_outcome": "none", "argument_name": None, "argument_name_evidence": [], "argument_name_same_reasoning_confirmed": False,
        "argument_name_non_invented_label_confirmed": True, "argument_name_language_fit_confirmed": True, "argument_name_rationale": "No name needed for this provenance test.",
        "argument_name_page_reasoning_scope_summary": "Historical page scope.", "argument_name_literature_scope_summary": "", "argument_name_scope_relation": "", "argument_name_scope_identity_confirmed": False,
        "metadata_equivalent_to_french": True, "summary_equivalent_to_french": True, "canonical_title_semantic_inventory_reviewed": True,
        "canonical_title_semantic_inventory_note": "Canonical subject, predicate, scope and modality were reviewed against the French source.", "canonical_title_equivalent_to_french": True,
        "canonical_title_subject_preserved": True, "canonical_title_predicate_preserved": True, "canonical_title_scope_preserved": True, "canonical_title_modality_preserved": True,
        "sections_exactly_mapped": True, "keywords_exactly_mapped": True, "keywords_order_preserved_by_relevance": True, "title_is_idiomatic": True,
        "displayed_title_source_form": "nominal_phrase", "displayed_title_target_form": "nominal_phrase", "displayed_title_source_form_reviewed": True, "displayed_title_no_formal_regression": True,
        "displayed_title_semantic_inventory_reviewed": True, "displayed_title_semantic_inventory_note": "Historical nominal form and meaning were reviewed directly.",
        "displayed_title_subject_preserved": True, "displayed_title_predicate_preserved": True, "displayed_title_scope_preserved": True, "displayed_title_modality_preserved": True,
        "displayed_title_translates_french_displayed_title": True, "displayed_title_identity_pattern_reviewed": True, "displayed_title_identity_pattern_note": "Historical canonical/display relation preserved.",
        "displayed_title_is_complete_proposition": False, "displayed_title_concision_reviewed": True, "displayed_title_semantically_equivalent": True, "displayed_title_improves_readability_when_distinct": False,
        "documentation_rationale": "No documentary source is selected in this focused provenance unit test.", "reviewer": "Reviewer", "reviewed_at": "2026-08-12T22:00:00+02:00", "note": "Historical source provenance test."
    }
    mapping = {"revenu": "income", "liberté": "freedom", "travail": "work", "autonomie": "autonomy", "justice": "justice"}
    return row, mapping


def test_historical_source_origin_allows_nominal_displayed_title_and_keyword_count():
    row, mapping = nominal_argument_translation()
    result = translation._validate_argument({"id": "A-HIST", "translation": row}, mapping, {}, authoritative_source_page_origin="preexisting")
    assert result["source_page_origin"] == "preexisting"
    assert len(result["keywords"]) == 5
    assert result["displayed_title"] == "Freedom and income"


@pytest.mark.parametrize("origin", ("new", "preexisting"))
@pytest.mark.parametrize("source,target", [("Liberté", "Freedom"), ("Réduction de la consommation", "Reduced consumption")])
def test_translation_preserves_short_nominal_source_for_any_source_origin(origin, source, target):
    row, mapping = nominal_argument_translation()
    row["source_page_origin"] = origin
    row["french"]["metadata"].update(page_origin=origin, displayed_title=source, keywords=["revenu", "liberté"])
    row["french"]["content"]["page_origin"] = origin
    row.update(displayed_title=target, keywords=["income", "freedom"], displayed_title_improves_readability_when_distinct=False)
    result = translation._validate_argument({"id": "A-HIST", "translation": row}, mapping, {}, authoritative_source_page_origin=origin)
    assert result["displayed_title"] == target
    assert result["displayed_title_is_complete_proposition"] is False
    assert row["french"]["metadata"]["displayed_title"] == source


@pytest.mark.parametrize("origin", ("new", "preexisting"))
def test_translation_still_rejects_loss_of_source_proposition(origin):
    row, mapping = nominal_argument_translation()
    row["source_page_origin"] = origin
    row["french"]["metadata"].update(page_origin=origin, displayed_title="Le revenu favorise la liberté")
    row["french"]["content"]["page_origin"] = origin
    row["displayed_title_source_form"] = "proposition"
    row.update(displayed_title_form_change_reviewed=True, displayed_title_speech_act_preserved=True,
               displayed_title_form_change_note="A manual attestation must not waive loss of the source proposition.")
    with pytest.raises(translation.TranslationReviewError, match="proposition française"):
        translation._validate_argument({"id": "A-HIST", "translation": row}, mapping, {}, authoritative_source_page_origin=origin)


def test_english_argument_established_name_parameters_are_preserved_import_parameters():
    assert 'established-name' in translation.EN_PAGE_LIFECYCLE_PARAMETERS['argument']
    assert 'name' in translation.EN_PAGE_LIFECYCLE_PARAMETERS['argument']


def test_validate_argument_preserves_historical_absent_summary(monkeypatch):
    row = {
        "status": "approved", "page_origin": "new", "preserved_parameters": {},
        "french": {"metadata": {"rubriques": ["Philosophie"], "keywords": ["cause", "existence"]}, "content": {"summary": None, "citations": []}},
        "canonical_title": "A complete argument is valid", "displayed_title": "A complete argument is valid",
        "sections": ["Philosophy"], "keywords": ["cause", "existence"], "summary": "",
        "citations": [], "sources": {"bibliography": [], "webliography": [], "videography": []},
        "argument_name_search_queries": ["complete argument name", "complete argument terminology"],
        "argument_name_search_scope_note": "Academic English terminology was reviewed.",
        "argument_name_search_provenance": "fresh_recheck",
        "argument_name_search_provenance_note": "The test models an actual fresh terminology recheck with the two recorded queries.",
        "argument_name_outcome": "none", "argument_name": None, "argument_name_evidence": [],
        "argument_name_same_reasoning_confirmed": False, "argument_name_non_invented_label_confirmed": True,
        "argument_name_language_fit_confirmed": True, "argument_name_rationale": "No conventional name is sufficiently established.",
        "argument_name_page_reasoning_scope_summary": "This page presents the exact reasoning expressed by its canonical title and summary.",
        "argument_name_literature_scope_summary": "", "argument_name_scope_relation": "",
        "argument_name_scope_identity_confirmed": False,
        "metadata_equivalent_to_french": True, "summary_equivalent_to_french": True,
        "canonical_title_semantic_inventory_reviewed": True,
        "canonical_title_semantic_inventory_note": "The canonical title subject, predicate, polarity, modality and logical scope were compared with the French source.",
        "canonical_title_equivalent_to_french": True,
        "canonical_title_subject_preserved": True, "canonical_title_predicate_preserved": True,
        "canonical_title_scope_preserved": True, "canonical_title_modality_preserved": True,
        "sections_exactly_mapped": True, "keywords_exactly_mapped": True, "keywords_order_preserved_by_relevance": True,
        "title_is_idiomatic": True,
        "displayed_title_source_form": "proposition", "displayed_title_target_form": "proposition",
        "displayed_title_source_form_reviewed": True, "displayed_title_no_formal_regression": True,
        "displayed_title_semantic_inventory_reviewed": True,
        "displayed_title_semantic_inventory_note": "The test explicitly reviews subject, predicate, polarity, modality, attribution and logical scope.",
        "displayed_title_subject_preserved": True, "displayed_title_predicate_preserved": True,
        "displayed_title_scope_preserved": True, "displayed_title_modality_preserved": True,
        "displayed_title_translates_french_displayed_title": True,
        "displayed_title_identity_pattern_reviewed": True,
        "displayed_title_identity_pattern_note": "The displayed-title is directly tied to the French displayed-title in this historical-absence test.",
        "displayed_title_is_complete_proposition": True,
        "displayed_title_concision_reviewed": True, "displayed_title_semantically_equivalent": True,
        "displayed_title_improves_readability_when_distinct": True, "summary_ratio_reviewed": False,
        "forceful_expression": "", "quantitative_claims_verified": False, "quantitative_claims_note": "",
        "documentation_rationale": "No English documentary source is selected for this test page.",
        "reviewer": "Reviewer", "reviewed_at": "2026-08-07T22:00:00+02:00",
        "note": "French source summary is historically absent and must remain absent in English.",
    }
    result = translation._validate_argument({"id": "A9999", "translation": row}, {"cause": "cause", "existence": "existence"}, {})
    assert result["summary"] is None
    assert result["summary_length_ratio"] is None
    assert result["forceful_expression"] is None


def test_validate_argument_requires_canonical_semantic_review():
    item = {
        "id": "A9998",
        "translation": {
            "status": "approved", "page_origin": "new", "preserved_parameters": {},
            "french": {"metadata": {"rubriques": ["Philosophie"], "keywords": ["cause", "existence"]}, "content": {"summary": None, "citations": []}},
            "canonical_title": "A complete translated claim is valid", "displayed_title": "A complete translated claim is valid",
            "sections": ["Philosophy"], "keywords": ["cause", "existence"], "summary": "",
            "citations": [], "sources": {"bibliography": [], "webliography": [], "videography": []},
            "argument_name_search_queries": ["query one", "query two"],
            "argument_name_search_scope_note": "English academic naming was checked across multiple phrasings.",
            "argument_name_search_provenance": "fresh_recheck",
            "argument_name_search_provenance_note": "These two queries were actually used in the fresh recheck.",
            "argument_name_outcome": "none", "argument_name": None, "argument_name_evidence": [],
            "argument_name_same_reasoning_confirmed": False, "argument_name_non_invented_label_confirmed": True,
            "argument_name_language_fit_confirmed": True, "argument_name_rationale": "No conventional name was found.",
            "metadata_equivalent_to_french": True, "summary_equivalent_to_french": True,
            "canonical_title_semantic_inventory_reviewed": False,
            "canonical_title_semantic_inventory_note": "", "canonical_title_equivalent_to_french": False,
            "sections_exactly_mapped": True, "keywords_exactly_mapped": True, "keywords_order_preserved_by_relevance": True,
            "title_is_idiomatic": True, "displayed_title_source_form": "proposition", "displayed_title_target_form": "proposition",
            "displayed_title_source_form_reviewed": True, "displayed_title_no_formal_regression": True,
            "displayed_title_semantic_inventory_reviewed": True,
            "displayed_title_semantic_inventory_note": "Subject, predicate, polarity, modality and scope were reviewed.",
            "displayed_title_translates_french_displayed_title": True,
            "displayed_title_identity_pattern_reviewed": True,
            "displayed_title_identity_pattern_note": "The displayed-title is directly tied to its French source for this negative canonical-title test.",
            "displayed_title_is_complete_proposition": True, "displayed_title_concision_reviewed": True,
            "displayed_title_semantically_equivalent": True, "displayed_title_improves_readability_when_distinct": True,
            "summary_ratio_reviewed": False, "forceful_expression": "", "quantitative_claims_verified": False, "quantitative_claims_note": "",
            "documentation_rationale": "No source is selected in this unit test.", "reviewer": "Reviewer",
            "reviewed_at": "2026-08-09T19:30:00+02:00", "note": "The row is intentionally missing canonical semantic approval."
        }
    }
    import pytest
    with pytest.raises(translation.TranslationReviewError, match="titre canonique"):
        translation._validate_argument(item, {"cause": "cause", "existence": "existence"}, {})


def test_validate_debate_requires_claim_inventory():
    row = translation._blank_debate({"rubriques": [], "keywords": []}, {"subject": "Test", "complete_topic": "test", "introduction": "source"})
    row.update({"status": "approved", "canonical_title": "A complete test debate", "topic": "Test debate", "complete_topic": "the complete test debate",
                "canonical_title_semantic_inventory_reviewed": True,
                "canonical_title_semantic_inventory_note": "The canonical title was compared semantically with its source.",
                "topic_semantic_equivalence_reviewed": True, "complete_topic_semantic_equivalence_reviewed": True,
                "introduction_claim_inventory_reviewed": False, "subsection_structure_equivalence_reviewed": True})
    import pytest
    with pytest.raises(translation.TranslationReviewError, match="introduction_claim_inventory_reviewed"):
        translation._validate_debate(row, {}, {}, "debate_test")


def test_finalize_translation_requires_second_completeness_review_for_low_quote_ratio(tmp_path: Path):
    project, workspace, work_id = make_french_locked(tmp_path)
    translation.prepare_review(project, "debat_test", work_id)
    complete_translation_review(workspace)
    path = workspace / "reviews/en/translation_review.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    citation = data["arguments"][0]["translation"]["citations"][0]
    citation["translated_citation"] = "Short translation."
    citation["quote_low_ratio_reviewed"] = False
    citation["quote_low_ratio_note"] = ""
    common.write_json(path, data)
    try:
        translation.finalize_review(project, "debat_test", work_id)
    except translation.TranslationReviewError as exc:
        assert "seconde revue explicite" in str(exc)
    else:
        raise AssertionError("Une Quote très courte sans seconde revue de complétude a été acceptée")


def test_translation_risk_profile_shrinks_dense_review_units():
    dense = translation._translation_risk_profile(
        {"preserved_parameters": {"name": "Argument cosmologique"}},
        {
            "summary": ("Si tous les faits doivent être expliqués, alors cette conclusion peut être nécessaire; " * 30),
            "citations": [{"citation": "mot " * 140}, {"citation": "mot " * 150}, {"citation": "court"}],
            "sources": {"bibliography": ["S1", "S2", "S3"], "webliography": ["S4"], "videography": []},
        },
    )
    assert dense["level"] in {"high", "very_high"}
    assert dense["recommended_unit_size"] <= 6


def test_translation_risk_profile_keeps_simple_page_at_default_ten():
    simple = translation._translation_risk_profile({}, {"summary": "Une prémisse simple conduit à une conclusion simple.", "citations": [], "sources": {}})
    assert simple["level"] == "low"
    assert simple["recommended_unit_size"] == 10

# Historical test-name alias retained for non-regression traceability.
def test_english_argument_name_is_a_preserved_import_parameter():
    assert 'name' in translation.EN_PAGE_LIFECYCLE_PARAMETERS['argument']

def test_21625_legacy_english_source_verification_is_normalized_without_inventing_primary_source():
    row = en_source("S10009", "webliography", [{
        "page_id": "debat_test", "language": "en", "role": "neutral_reference",
        "language_fit": "native", "preferred_equivalent_source_id": None,
        "documentary_scope": "context", "selection_reason": "This source documents the historical context used in the debate."
    }])
    row["verification"] = {
        "status": "verified",
        "language_verified": True,
        "authorship_checked": True,
        "checked_at": "2026-08-13T01:21:24+02:00",
        "method": "Direct recheck of the English-language publisher page.",
        "note": "English-language availability and attribution were rechecked.",
    }
    normalized = translation._canonical_source_for_registry(row)
    verification = normalized["verification"]
    assert verification["verified_at"] == "2026-08-13T01:21:24+02:00"
    assert verification["primary_source"] is None
    assert verification["notes"] == [
        "English-language availability and attribution were rechecked.",
        "Verification method: Direct recheck of the English-language publisher page.",
    ]
    assert "checked_at" not in verification
    assert "method" not in verification
    assert "note" not in verification



def test_english_title_validation_rejects_non_ascii_apostrophes():
    assert translation._validate_title("Basic income supports women's autonomy", "canonical") == "Basic income supports women's autonomy"
    for bad in (
        "Basic income supports women’s autonomy",
        "Basic income supports women‘s autonomy",
        "Basic income supports womenʼs autonomy",
        "Basic income supports women＇s autonomy",
    ):
        try:
            translation._validate_title(bad, "canonical")
        except translation.TranslationReviewError as exc:
            assert "non_ascii_apostrophe" in str(exc)
        else:
            raise AssertionError(f"non-ASCII apostrophe accepted: {bad!r}")


def test_collect_title_format_findings_covers_all_argument_title_fields():
    review = {
        "debate_id": "debat_test",
        "final_values": {
            "debate": {"canonical_title": "Should basic income be introduced?"},
            "arguments": [
                {
                    "id": "A0004",
                    "canonical_title": "Basic income is good for the national economy",
                    "displayed_title": "A good thing for the country’s economy",
                },
                {
                    "id": "A0045",
                    "canonical_title": "Basic income gives everyone a stake in the country’s wealth",
                    "displayed_title": "Giving everyone a stake in the country’s wealth",
                },
            ],
        },
    }
    findings = translation.collect_english_title_format_findings(review)
    assert [(row["entity_id"], row["field"]) for row in findings] == [
        ("A0004", "displayed_title"),
        ("A0045", "canonical_title"),
        ("A0045", "displayed_title"),
    ]
    assert all(row["issues"] == ["non_ascii_apostrophe"] for row in findings)


def test_21627_documentary_guard_reports_all_final_registry_requirements_before_apply():
    def legacy_source(sid, stype, *, authors, site=None, debate_biblio=False):
        metadata = {
            "authors": authors, "article": None, "work": None, "volume": None, "issue": None,
            "location": None, "publisher": None, "place": None, "date": None,
            "link": f"https://example.org/{sid}", "page": None, "site": site, "title": None,
        }
        if stype == "bibliography":
            metadata["work"] = f"Reference {sid}"
        else:
            metadata["title"] = f"Page {sid}"
        usage = [{
            "page_id": "debat_test", "language": "en", "role": "neutral_reference",
            "selection_reason": "This source was selected for the English debate documentation.",
        }]
        return {
            "id": sid, "type": stype, "language": "en", "metadata": metadata,
            "verification": {
                "status": "verified", "language_verified": True, "authorship_checked": True,
                "checked_at": "2026-08-13T01:21:24+02:00", "method": "Direct check", "note": "Checked.",
            },
            "usage": usage, "deduplication_key": sid.lower(),
        }

    review = {
        "debate_id": "debat_test",
        "final_values": {"sources": [
            legacy_source("S10001", "bibliography", authors=["Author One"], debate_biblio=True),
            legacy_source("S10002", "webliography", authors=["Example Site"], site="Example Site"),
            legacy_source("S10003", "webliography", authors=["Named Author"], site="Another Site"),
        ]},
    }
    findings = translation.collect_english_documentary_findings(review)
    keys = {(row["entity_id"], row["issue"]) for row in findings}
    assert ("S10001", "debate_bibliography_document_kind_missing_or_invalid") in keys
    assert ("S10001", "debate_bibliography_scope_missing_or_invalid") in keys
    assert ("S10002", "authorship_not_explicitly_verified") in keys
    assert ("S10002", "author_duplicates_site") in keys
    assert ("S10003", "authorship_not_explicitly_verified") in keys


def test_21627_validate_sources_rejects_late_debate_bibliography_contract():
    source = en_source("S10001", "bibliography", [{
        "page_id": "debat_test", "language": "en", "role": "neutral_reference",
        "language_fit": "native", "preferred_equivalent_source_id": None,
        "documentary_scope": None,
        "selection_reason": "A long enough reason for selecting this debate bibliography source.",
    }])
    source.pop("document_kind", None)
    data = {
        "schema": translation.EN_SOURCES_WORKING_SCHEMA,
        "debate_id": "debat_test", "sources": [source],
    }
    try:
        translation._validate_sources(data, "debat_test", set())
    except translation.TranslationReviewError as exc:
        assert "document_kind" in str(exc)
    else:
        raise AssertionError("A Debate bibliography without document_kind was accepted")


def test_21627_validate_sources_rejects_unverified_web_author():
    source = en_source("S10003", "webliography", [{
        "page_id": "debat_test", "language": "en", "role": "neutral_reference",
        "language_fit": "native", "preferred_equivalent_source_id": None,
        "documentary_scope": "context",
        "selection_reason": "A long enough reason for selecting this English Web source.",
    }])
    source["verification"].pop("authorship_verified", None)
    data = {
        "schema": translation.EN_SOURCES_WORKING_SCHEMA,
        "debate_id": "debat_test", "sources": [source],
    }
    try:
        translation._validate_sources(data, "debat_test", set())
    except translation.TranslationReviewError as exc:
        assert "non explicitement vérifiée" in str(exc)
    else:
        raise AssertionError("A Web source with an unverified listed author was accepted")


def test_21628_documentary_guard_accepts_legal_text_when_scope_is_broad_and_justified():
    source = en_source("S10002", "bibliography", [{
        "page_id": "debat_test", "language": "en", "role": "neutral_reference",
        "language_fit": "native", "preferred_equivalent_source_id": None,
        "documentary_scope": "broad_synthesis",
        "selection_reason": "This official legal text provides the broad normative framework governing the debate.",
    }])
    source["document_kind"] = "legal_text"
    review = {"debate_id": "debat_test", "final_values": {"sources": [source]}}
    findings = translation.collect_english_documentary_findings(review)
    assert not any(row["entity_id"] == "S10002" and row["field"] == "document_kind" for row in findings)
    assert not any(row["entity_id"] == "S10002" and row["issue"] == "debate_bibliography_scope_missing_or_invalid" for row in findings)


def test_21628_validate_sources_accepts_legal_text_for_broad_debate_bibliography():
    source = en_source("S10002", "bibliography", [{
        "page_id": "debat_test", "language": "en", "role": "neutral_reference",
        "language_fit": "native", "preferred_equivalent_source_id": None,
        "documentary_scope": "broad_synthesis",
        "selection_reason": "This official legal text provides the broad normative framework governing the debate.",
    }])
    source["document_kind"] = "legal_text"
    data = {
        "schema": translation.EN_SOURCES_WORKING_SCHEMA,
        "debate_id": "debat_test", "sources": [source],
    }
    rows, by_id = translation._validate_sources(data, "debat_test", set())
    assert rows[0]["id"] == "S10002"
    assert by_id["S10002"]["document_kind"] == "legal_text"


def test_english_keyword_form_metadata_is_localized_per_target_form():
    source = {
        "kind": "noun_phrase",
        "capitalization_policy": "lowercase_common",
        "atomic_concept": True,
        "compositional_intersection": False,
        "multiword_exception": True,
        "multiword_exception_rationale": "Locution française conventionnelle désignant un concept atomique.",
    }
    compact = translation._english_keyword_form_metadata("ballot stuffing", source)
    assert compact["en_kind"] == "noun_phrase"
    assert compact["en_atomic_concept"] is True
    assert compact["en_compositional_intersection"] is False
    assert compact["en_multiword_exception"] is False
    assert compact["en_multiword_exception_rationale"] == ""

    long_form = translation._english_keyword_form_metadata("overseas French voters", source)
    assert long_form["en_kind"] == "noun_phrase"
    assert long_form["en_multiword_exception"] is True
    assert "concept" in long_form["en_multiword_exception_rationale"].casefold()
    assert "overseas French voters" in long_form["en_multiword_exception_rationale"]


def test_apply_translation_emits_english_localized_keyword_quality_metadata(tmp_path: Path):
    project, workspace, work_id = make_french_locked(tmp_path)
    translation.prepare_review(project, "debat_test", work_id)
    complete_translation_review(workspace)
    sealed = translation.finalize_review(project, "debat_test", work_id)
    complete_semantic_convergence(project, work_id)
    translation.apply_review(project, "debat_test", work_id, sealed["review_sha256"])
    vocabulary = json.loads((workspace / "translated-copy/data/keyword_vocabulary_bilingual.json").read_text(encoding="utf-8"))
    assert vocabulary["entries"]
    for row in vocabulary["entries"]:
        assert row["en_atomic_concept"] is True
        assert row["en_compositional_intersection"] is False
        assert "en_multiword_exception" in row
        assert "en_multiword_exception_rationale" in row
        assert row["en_kind"] in {"noun", "noun_phrase", "proper_name", "acronym"}
        assert row["en_capitalization_policy"] in {"lowercase_common", "canonical_proper_name", "canonical_acronym"}

def test_archive_wrapper_can_be_replaced_by_its_exact_original_url():
    archived = "https://archive.is/20240506074406/https://example.org/article"
    source = {"source_parameters": [{"name": "lien", "value": archived}]}
    row = {"documentary_parameter_overrides": [{
        "source_name": "lien", "output_name": "link", "source_value": archived,
        "translated_value": "https://example.org/article",
        "reason": "The target wiki spam filter rejects the archive wrapper domain.",
    }]}
    assert translation._citation_documentary_overrides(row, source, "A1-C1")["lien"]["translated_value"] == "https://example.org/article"


def test_archive_wrapper_override_rejects_a_different_destination():
    archived = "https://archive.is/20240506074406/https://example.org/article"
    source = {"source_parameters": [{"name": "lien", "value": archived}]}
    row = {"documentary_parameter_overrides": [{
        "source_name": "lien", "output_name": "link", "source_value": archived,
        "translated_value": "https://other.example/article",
        "reason": "The target wiki spam filter rejects the archive wrapper domain.",
    }]}
    try:
        translation._citation_documentary_overrides(row, source, "A1-C1")
    except translation.TranslationReviewError as exc:
        assert "exactement" in str(exc)
    else:
        raise AssertionError("A documentary override to a different URL was accepted")


@pytest.mark.parametrize('mutation', ['missing', 'source_text', 'target_node_id'])
def test_ordinary_historical_review_requires_exact_contextual_label_inventory(tmp_path, mutation):
    project, workspace, work_id = make_french_locked(tmp_path)
    translation.prepare_review(project, 'debat_test', work_id)
    complete_translation_review(workspace)
    path = workspace / 'reviews/en/translation_review.json'
    review = json.loads(path.read_text())
    assert review['relation_labels']
    if mutation == 'missing':
        review['relation_labels'].pop()
    else:
        review['relation_labels'][0][mutation] = 'Forged source scope'
    common.write_json(path, review)
    with pytest.raises(translation.TranslationReviewError, match='libellé|Source'):
        translation.finalize_review(project, 'debat_test', work_id)


@pytest.mark.parametrize('entity', ['debate', 'argument'])
def test_ordinary_review_cannot_forge_embedded_french_source(tmp_path, entity):
    project, workspace, work_id = make_french_locked(tmp_path)
    translation.prepare_review(project, 'debat_test', work_id)
    complete_translation_review(workspace)
    path = workspace / 'reviews/en/translation_review.json'
    review = json.loads(path.read_text())
    row = review['debate'] if entity == 'debate' else review['arguments'][0]['translation']
    row['french']['content']['page_origin'] = 'new'
    common.write_json(path, review)
    with pytest.raises(translation.TranslationReviewError, match='snapshot autoritatif'):
        translation.finalize_review(project, 'debat_test', work_id)


@pytest.mark.parametrize('fr,en,en_kind,policy', [
    ('nazisme', 'Nazism', 'proper_name', 'canonical_proper_name'),
    ('procédure-bâillon', 'SLAPP', 'acronym', 'canonical_acronym'),
])
def test_english_lexical_form_is_reviewed_without_changing_french_kind(fr, en, en_kind, policy):
    source = {'fr': fr, 'kind': 'noun', 'capitalization_policy': 'lowercase_common', 'atomic_concept': True}
    row = {**source, 'en': en, 'en_kind': en_kind, 'en_capitalization_policy': policy,
        'definition_en': 'The same controlled concept expressed idiomatically in English.',
        'capitalization_verified': True, 'capitalization_rationale_en': 'Established English spelling and lexical form, independently reviewed.',
        'status': 'approved', 'idiomatic_equivalent': True, 'same_concept': True,
        'reviewer': 'Test reviewer', 'reviewed_at': '2026-10-25T22:00:00Z', 'note': 'English lexical form checked against the source concept.'}
    result, _ = translation._validate_vocabulary([row], [source])
    assert result[0]['kind'] == 'noun'
    assert translation._english_keyword_form_metadata(en, result[0])['en_kind'] == en_kind
    row['capitalization_rationale_en'] = ''
    with pytest.raises(translation.TranslationReviewError, match='non justifié'):
        translation._validate_vocabulary([row], [source])


def test_ordinary_historical_labels_survive_projection(tmp_path):
    project, workspace, work_id = make_french_locked(tmp_path)
    translation.prepare_review(project, 'debat_test', work_id)
    complete_translation_review(workspace)
    sealed = translation.finalize_review(project, 'debat_test', work_id)
    review = json.loads((workspace / 'reviews/en/translation_review.json').read_text())
    labels = review['final_values']['debate']['relation_labels']
    assert labels and labels[0]['equivalent_to_french']
    complete_semantic_convergence(project, work_id)
    translation.apply_review(project, 'debat_test', work_id, sealed['review_sha256'])
    lock = json.loads((workspace / 'translated-copy/data/en_content_lock.json').read_text())
    assert lock['debate']['relation_labels'] == labels


def test_ordinary_historical_number_transfer_does_not_certify_truth():
    row, mapping = nominal_argument_translation()
    row['french']['content'].update(summary='260 000 emplois en 2018.', summary_provenance='historical_existing')
    row.update(summary='260,000 jobs in 2018.', summary_ratio_reviewed=True,
        summary_subject_predicate_scope_modality_reviewed=True, summary_opening_proposition_preserved=True,
        summary_closing_proposition_preserved=True, summary_conditions_exclusivities_preserved=True,
        summary_decisive_premises_preserved=True, summary_semantic_evidence_note='The historical numerical assertion has the same value, date and scope in both languages.',
        historical_quantitative_transfer_reviewed=True, historical_quantitative_transfer_note='260 000 -> 260,000, year 2018 unchanged; claim truth has not been newly certified.',
        quantitative_claims_verified=False, quantitative_claims_note='')
    result = translation._validate_argument({'id': 'A-HIST', 'translation': row}, mapping, {}, authoritative_source_page_origin='preexisting')
    assert result['historical_quantitative_transfer_reviewed'] is True
    assert result['quantitative_claims_verified'] is False
    row['summary'] = '26,000 jobs in 2018.'
    with pytest.raises(translation.TranslationReviewError, match='chiffrée'):
        translation._validate_argument({'id': 'A-HIST', 'translation': row}, mapping, {}, authoritative_source_page_origin='preexisting')
    row['summary'] = '260,000 jobs in 2018.'
    row['historical_quantitative_transfer_reviewed'] = False
    with pytest.raises(translation.TranslationReviewError, match='chiffrée'):
        translation._validate_argument({'id': 'A-HIST', 'translation': row}, mapping, {}, authoritative_source_page_origin='preexisting')

@pytest.mark.parametrize('value,language,expected', [
    ('Mar 9, 2021', 'en', (2021, 3, 9)),
    ('Nov 14, 2016', 'en', (2016, 11, 14)),
    ('1er/10/2024', 'fr', (2024, 10, 1)),
    ('1er juin 2023', 'fr', (2023, 6, 1)),
    ('Feb 31, 2024', 'en', None),
])
def test_source_date_localization_retains_actual_calendar_value(value, language, expected):
    assert translation._date_signature(value, language) == expected


@pytest.mark.parametrize('date', ['1981 (1979)', '2007 / 2', '24/05/21'])
def test_opaque_numeric_bibliographic_date_is_preserved_without_guessing(tmp_path, date):
    project, workspace, work_id = make_french_locked(tmp_path)
    translation.prepare_review(project, 'debat_test', work_id)
    complete_translation_review(workspace)
    review = json.loads((workspace / 'reviews/en/translation_review.json').read_text())
    row = next(q for i in review['arguments'] for q in i['translation']['citations'])
    row['source']['date'] = date
    for parameter in row['source']['source_parameters']:
        if parameter['name'] == 'date':
            parameter['value'] = date
    row['translated_date'] = date
    result = translation._validate_citations([row], [row['source']], 'A-DATE')
    assert result[0]['date'] == date
    row['translated_date'] = '2 February 2007'
    with pytest.raises(translation.TranslationReviewError, match='Format de date source'):
        translation._validate_citations([row], [row['source']], 'A-DATE')

def test_dedicated_debate_is_reviewed_source_metadata_not_new_page_lifecycle():
    from wikidebia_translation_review import _validate_dedicated_debate, TranslationReviewError
    row={'french':{'content':{'preserved_parameters':{'débat-dédié':{'present':True,'value':'La censure est-elle juste ?'}}}}}
    with pytest.raises(TranslationReviewError):_validate_dedicated_debate(row,'A1')
    row.update(dedicated_debate='Is censorship fair?',dedicated_debate_equivalence_reviewed=True,
               dedicated_debate_review_note='The same evaluative question about censorship is preserved without inventing another debate.')
    assert _validate_dedicated_debate(row,'A1')['dedicated_debate']=='Is censorship fair?'
    row['french']['content']['preserved_parameters']={}
    with pytest.raises(TranslationReviewError):_validate_dedicated_debate(row,'A1')
    row['dedicated_debate']=None
    assert _validate_dedicated_debate(row,'A1')['dedicated_debate'] is None
