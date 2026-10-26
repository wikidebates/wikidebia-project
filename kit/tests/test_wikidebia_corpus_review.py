from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

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


init = load_module("wikidebia_corpus_init")
review = load_module("wikidebia_corpus_review")
promote = load_module("wikidebia_corpus_promote")
common = sys.modules["wikidebia_corpus_build"]


def _fake_validator(project_root, package, json_output, text_output, *, previous_status=None):
    report = {
        "result": "passed",
        "validator_version": common.VALIDATOR_VERSION,
        "summary": {"errors": 0, "warnings": 0},
        "previous_status": previous_status,
    }
    common.write_json(json_output, report)
    text_output.parent.mkdir(parents=True, exist_ok=True)
    text_output.write_text("Validation de test : RÉUSSIE\n", encoding="utf-8", newline="\n")
    return report


# These unit tests cover the graph-review and promotion state machine. The real
# validator is exercised once in the clean end-to-end bundle verification.
review.run_validator = _fake_validator
promote.run_validator = _fake_validator

# Reuse the extraction fixture already maintained for corpus-init.
from test_wikidebia_corpus_init import make_extraction  # noqa: E402


def make_project(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "project"
    (project / ".state" / "corpus-builds").mkdir(parents=True)
    validator_source = Path(__file__).resolve().parents[2] / "validator_src"
    # The standalone kit test tree used in the bundle build has validator_src as a sibling.
    if not validator_source.is_dir():
        validator_source = Path(__file__).resolve().parents[2] / "validator"
    (project / "validator").mkdir()
    shutil.copytree(validator_source / "src", project / "validator" / "src")
    source = make_extraction(tmp_path / "source")
    build = project / ".state" / "corpus-builds" / "debat_test"
    init.build_corpus(source, build, debate_id="debat_test", short_code="TEST", scope_summary=None, overwrite=False)
    return project, build


def complete_reviews(build: Path, *, decision: str = "approved") -> str:
    placement_path = build / common.PLACEMENT_REVIEW
    placement = json.loads(placement_path.read_text(encoding="utf-8"))
    for entry in placement["entries"]:
        entry["placement_status"] = "approved"
        entry["direct_fit"] = True
        entry["rationale"] = "Cette occurrence vise exactement sa cible logique immédiate et conserve sa fonction argumentative."
        if entry["declared_depth"] == 1:
            block = entry["main_argument_review"]
            block["direct_answer_to_debate"] = True
            block["autonomous_without_parent"] = True
            block["organizes_distinct_argument_family"] = True
            block["more_general_nonduplicate_parent_available"] = False
            block["principally_supports_or_attacks_specific_argument"] = False
            block["principally_example_or_specialization"] = False
        else:
            entry["subordinate_review"]["parent_is_best_immediate_target"] = True
            entry["subordinate_review"]["relation_to_parent_explicit"] = True
    common.write_json(placement_path, placement)

    envelope_path = build / common.REVIEW_ENVELOPE
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    envelope["decision"] = decision
    envelope["reviewer"] = "Relecteur test"
    envelope["reviewed_at"] = "2026-08-03T19:00:00+00:00"
    envelope["attestations"] = {key: True for key in common.REQUIRED_ATTESTATIONS}
    envelope["blocking_issues"] = [] if decision == "approved" else ["Le graphe doit être repris."]
    envelope["notes"] = "Revue formelle complète du graphe importé."
    common.write_json(envelope_path, envelope)
    return envelope["source_build_sha256"]


def test_prepare_creates_occurrence_ledger_without_changing_status(tmp_path: Path):
    project, build = make_project(tmp_path)
    result = review.make_review_template(build, "debat_test", overwrite=False)
    assert result["status"] == "review_prepared"
    manifest = json.loads((build / "manifest.json").read_text(encoding="utf-8"))
    placement = json.loads((build / common.PLACEMENT_REVIEW).read_text(encoding="utf-8"))
    assert manifest["global_status"] == "graph_draft"
    assert len(placement["entries"]) == 4
    assert {entry["placement_status"] for entry in placement["entries"]} == {"pending"}
    assert not (build / "output").exists()


def test_finalize_approved_review_sets_graph_validated_only(tmp_path: Path):
    project, build = make_project(tmp_path)
    review.make_review_template(build, "debat_test", overwrite=False)
    complete_reviews(build)
    result = review.finalize_review(project, build, "debat_test")
    manifest = json.loads((build / "manifest.json").read_text(encoding="utf-8"))
    registry = json.loads((build / "data/registre_debat.json").read_text(encoding="utf-8"))
    assert result["status"] == "approved"
    assert manifest["global_status"] == "graph_validated"
    assert registry["graph"]["lifecycle"]["status"] == "validated"
    assert registry["graph"]["lifecycle"]["locked_at"] is None
    assert manifest["pages"] == []
    assert not (build / "output").exists()
    assert (build / common.PROMOTION_READY).is_file()


def test_finalize_rejects_incomplete_occurrence_review(tmp_path: Path):
    project, build = make_project(tmp_path)
    review.make_review_template(build, "debat_test", overwrite=False)
    complete_reviews(build)
    placement = json.loads((build / common.PLACEMENT_REVIEW).read_text(encoding="utf-8"))
    placement["entries"][0]["direct_fit"] = False
    common.write_json(build / common.PLACEMENT_REVIEW, placement)
    try:
        review.finalize_review(project, build, "debat_test")
    except common.CorpusBuildError as exc:
        assert "Revue incomplète" in str(exc)
    else:
        raise AssertionError("revue de placement incomplète acceptée")
    assert json.loads((build / "manifest.json").read_text())["global_status"] == "graph_draft"


def test_graph_review_fingerprint_is_portable_across_sanitized_execution_paths(tmp_path: Path):
    project, build = make_project(tmp_path)
    execution_path = build / "reports/initial_validation_execution.json"
    common.write_json(execution_path, {
        "status": "passed",
        "returncode": 0,
        "stdout": "ok",
        "stderr": "",
        "report_json": str((build / "reports/initial_validation.json").resolve()),
        "report_text": str((build / "reports/initial_validation.txt").resolve()),
    })
    portable_before = common.build_payload_sha256(build)
    legacy_sha = next(
        value for value in common.compatible_legacy_build_payload_sha256s(build)
        if value != portable_before
    )

    review.make_review_template(build, "debat_test", overwrite=False)
    complete_reviews(build)
    envelope_path = build / common.REVIEW_ENVELOPE
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    envelope["source_build_sha256"] = legacy_sha
    common.write_json(envelope_path, envelope)

    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    execution["report_json"] = "reports/initial_validation.json"
    execution["report_text"] = "reports/initial_validation.txt"
    common.write_json(execution_path, execution)
    assert common.build_payload_sha256(build) == portable_before

    result = review.finalize_review(project, build, "debat_test")
    assert result["status"] == "approved"


def test_finalize_rejects_graph_changed_after_prepare(tmp_path: Path):
    project, build = make_project(tmp_path)
    review.make_review_template(build, "debat_test", overwrite=False)
    complete_reviews(build)
    scope = json.loads((build / "scope.json").read_text(encoding="utf-8"))
    scope["scope_summary_fr"] = "Modification postérieure non revue."
    common.write_json(build / "scope.json", scope)
    try:
        review.finalize_review(project, build, "debat_test")
    except common.CorpusBuildError as exc:
        assert "Revue incomplète" in str(exc)
    else:
        raise AssertionError("build modifié après préparation accepté")


def test_rejected_review_stays_graph_draft_and_cannot_promote(tmp_path: Path):
    project, build = make_project(tmp_path)
    review.make_review_template(build, "debat_test", overwrite=False)
    complete_reviews(build, decision="rejected")
    result = review.finalize_review(project, build, "debat_test")
    assert result["status"] == "rejected"
    assert json.loads((build / "manifest.json").read_text())["global_status"] == "graph_draft"
    try:
        promote.promote(project, "debat_test", "0" * 64)
    except common.CorpusBuildError as exc:
        assert "graph_validated" in str(exc)
    else:
        raise AssertionError("build rejeté promu")


def test_atomic_promotion_moves_build_and_writes_external_receipt(tmp_path: Path):
    project, build = make_project(tmp_path)
    review.make_review_template(build, "debat_test", overwrite=False)
    complete_reviews(build)
    review.finalize_review(project, build, "debat_test")
    envelope = json.loads((build / common.REVIEW_ENVELOPE).read_text(encoding="utf-8"))
    result = promote.promote(project, "debat_test", envelope["review_sha256"])
    target = project / "corpus" / "debat_test"
    assert result["status"] == "promoted"
    assert not build.exists()
    assert target.is_dir()
    assert json.loads((target / "manifest.json").read_text())["global_status"] == "graph_validated"
    assert not (target / "output").exists()
    receipt = project / result["receipt"]
    assert receipt.is_file()
    receipt_data = json.loads(receipt.read_text())
    assert receipt_data["atomic_rename"] is True
    assert receipt_data["final_pages_generated"] is False


def test_promotion_refuses_existing_target_and_wrong_confirmation(tmp_path: Path):
    project, build = make_project(tmp_path)
    review.make_review_template(build, "debat_test", overwrite=False)
    complete_reviews(build)
    review.finalize_review(project, build, "debat_test")
    envelope = json.loads((build / common.REVIEW_ENVELOPE).read_text(encoding="utf-8"))
    try:
        promote.promote(project, "debat_test", "0" * 64)
    except common.CorpusBuildError as exc:
        assert "empreinte confirmée" in str(exc)
    else:
        raise AssertionError("mauvaise confirmation acceptée")
    target = project / "corpus" / "debat_test"
    target.mkdir(parents=True)
    try:
        promote.promote(project, "debat_test", envelope["review_sha256"])
    except common.CorpusBuildError as exc:
        assert "existe déjà" in str(exc)
    else:
        raise AssertionError("cible existante remplacée")


def test_prepare_rejects_any_final_output_file(tmp_path: Path):
    project, build = make_project(tmp_path)
    output = build / "output/fr/debate"
    output.mkdir(parents=True)
    (output / "debate.wiki").write_text("{{Débat}}", encoding="utf-8")
    try:
        review.make_review_template(build, "debat_test", overwrite=False)
    except common.CorpusBuildError as exc:
        assert "sorties finales" in str(exc)
    else:
        raise AssertionError("sortie finale acceptée dans graph_draft")


def test_build_symlink_is_rejected(tmp_path: Path):
    project, build = make_project(tmp_path)
    (build / "imports/fr/link").symlink_to(build / "manifest.json")
    try:
        common.resolve_build(project, "debat_test")
    except common.CorpusBuildError as exc:
        assert "Lien symbolique" in str(exc)
    else:
        raise AssertionError("lien symbolique accepté")


def test_promotion_rejects_post_approval_tampering(tmp_path: Path):
    project, build = make_project(tmp_path)
    review.make_review_template(build, "debat_test", overwrite=False)
    complete_reviews(build)
    review.finalize_review(project, build, "debat_test")
    envelope = json.loads((build / common.REVIEW_ENVELOPE).read_text(encoding="utf-8"))
    scope = json.loads((build / "scope.json").read_text(encoding="utf-8"))
    scope["residual_ambiguities"].append("Altération après approbation")
    common.write_json(build / "scope.json", scope)
    try:
        promote.promote(project, "debat_test", envelope["review_sha256"])
    except common.CorpusBuildError as exc:
        assert "changé depuis l'approbation" in str(exc)
    else:
        raise AssertionError("build altéré après approbation promu")


def test_exclusive_lock_blocks_concurrent_corpus_operation(tmp_path: Path):
    project, _ = make_project(tmp_path)
    with common.exclusive_lock(project, "debat_test", "first"):
        try:
            with common.exclusive_lock(project, "debat_test", "second"):
                pass
        except common.CorpusBuildError as exc:
            assert "déjà en cours" in str(exc)
        else:
            raise AssertionError("deux opérations concurrentes acceptées")
