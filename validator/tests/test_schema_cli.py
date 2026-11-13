from pathlib import Path
import json

from wikidebia_validator.cli import main
from wikidebia_validator.validator import validate_package
from .helpers import create_graph_package, dump


def test_schema_violation(tmp_path: Path):
    create_graph_package(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    manifest["unexpected"] = True
    dump(tmp_path / "manifest.json", manifest)
    report = validate_package(tmp_path, scopes=["schema"])
    assert any(f.code == "WDV-SCH-003" for f in report.findings)


def test_schema_does_not_treat_self_identifying_build_receipt_as_archive_receipt(tmp_path: Path):
    create_graph_package(tmp_path)
    dump(tmp_path / "reports/corpus_build_receipt.json", {
        "schema": "wikidebia-corpus-build-receipt-1.0",
        "build_contract": {"debate_id": "exemple"},
        "build_contract_sha256": "0" * 64,
        "build_file_count": 7,
        "build_tree_sha256": "1" * 64,
        "created_at": "2026-07-23T18:00:00+02:00",
        "receipt_sha256": "2" * 64,
        "validation_status": "passed",
    })

    report = validate_package(tmp_path, scopes=["schema"])

    assert not any(
        finding.code == "WDV-SCH-003"
        and finding.path == "reports/corpus_build_receipt.json"
        for finding in report.findings
    ), report.to_text()


def test_schema_still_validates_legacy_archive_receipt_without_schema_discriminator(tmp_path: Path):
    create_graph_package(tmp_path)
    dump(tmp_path / "reports/archive_receipt.json", {"archive_receipt_version": "1.0"})

    report = validate_package(tmp_path, scopes=["schema"])

    assert any(
        finding.code == "WDV-SCH-003"
        and finding.path == "reports/archive_receipt.json"
        for finding in report.findings
    ), report.to_text()


def test_cli_json_output(tmp_path: Path):
    create_graph_package(tmp_path)
    output = tmp_path / "report.json"
    rc = main(["validate", str(tmp_path), "--scope", "graph", "--format", "json", "--json-output", str(output)])
    assert rc == 0
    data = json.loads(output.read_text())
    assert data["result"] in {"passed", "passed_with_warnings"}


def test_video_source_without_author_requires_verification_note():
    from wikidebia_validator.schema_validation import SchemaStore

    store = SchemaStore()
    base = {
        "source_registry_version": "1.0",
        "debate_id": "exemple",
        "sources": [{
            "id": "S00001",
            "type": "videography",
            "language": "fr",
            "metadata": {
                "authors": [], "article": None, "work": None, "volume": None,
                "issue": None, "location": None, "publisher": None, "place": None,
                "date": None, "link": "https://example.org/video", "page": None,
                "site": None, "title": "Vidéo documentaire",
            },
            "verification": {
                "status": "verified", "verified_at": "2026-07-23T18:00:00+02:00",
                "primary_source": False, "notes": [],
            },
            "usage": [{"page_id": "A0001", "language": "fr", "role": "supports_summary"}],
            "deduplication_key": "video-documentaire",
        }],
    }
    assert store.validate(base, "source_registry.schema.json")
    base["sources"][0]["verification"]["notes"] = [
        "La page, la description et les crédits ont été vérifiés sans permettre d'identifier un responsable éditorial."
    ]
    assert not store.validate(base, "source_registry.schema.json")


def _editorial_controls_124():
    return {
        "creation_date": "2026-07-23",
        "individual_review_path": "reports/individual_review.json",
        "individual_review_report_path": "reports/individual_review_report.json",
        "keyword_vocabulary_path": "data/keyword_vocabulary.json",
        "required_reports": [],
        "debate_documentation": {
            "min_subsections": 1,
            "min_references": 0,
            "reject_singleton_bucket_pattern": True,
            "profile_rationale": "Profil local minimal pour le paquet d'exemple.",
        },
        "introduction_references": {"required": True, "min_subsections": 1},
        "introduction_review_path": "reports/introduction_review.json",
    }


def test_old_norm_metadata_does_not_schema_gate_introduction_review_or_profile_rationale(tmp_path: Path):
    create_graph_package(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    manifest["normative_versions"]["consolidated_norm"] = "1.2.4"
    controls = _editorial_controls_124()
    controls.pop("introduction_review_path")
    controls["debate_documentation"].pop("profile_rationale")
    manifest["editorial_controls"] = controls
    dump(tmp_path / "manifest.json", manifest)
    report = validate_package(tmp_path, scopes=["schema"])
    assert not any(f.code == "WDV-SCH-003" for f in report.findings)


def test_norm_124_schema_accepts_declared_introduction_review_and_rationale(tmp_path: Path):
    create_graph_package(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    manifest["normative_versions"]["consolidated_norm"] = "1.2.4"
    manifest["editorial_controls"] = _editorial_controls_124()
    dump(tmp_path / "manifest.json", manifest)
    report = validate_package(tmp_path, scopes=["schema"])
    assert not any(f.code == "WDV-SCH-003" for f in report.findings)


def test_schema_accepts_final_publication_control_registry_paths(tmp_path: Path):
    create_graph_package(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    controls = _editorial_controls_124()
    controls["publication_url_replacements_path"] = "data/publication_url_replacements.json"
    controls["english_successor_revisions_path"] = "data/english_successor_revisions.json"
    manifest["editorial_controls"] = controls
    dump(tmp_path / "manifest.json", manifest)

    report = validate_package(tmp_path, scopes=["schema"])

    assert not any(f.code == "WDV-SCH-003" for f in report.findings)



def test_old_1220_metadata_does_not_schema_gate_graph_placement_review_path(tmp_path: Path):
    create_graph_package(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    manifest["normative_versions"]["consolidated_norm"] = "1.2.20"
    manifest["editorial_controls"] = _editorial_controls_124()
    dump(tmp_path / "manifest.json", manifest)
    report = validate_package(tmp_path, scopes=["schema"])
    assert not any(f.code == "WDV-SCH-003" for f in report.findings)


def test_norm_1220_schema_accepts_graph_placement_review_path(tmp_path: Path):
    create_graph_package(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    manifest["normative_versions"]["consolidated_norm"] = "1.2.20"
    controls = _editorial_controls_124()
    controls["graph_placement_review_path"] = "reports/graph_placement_review.json"
    manifest["editorial_controls"] = controls
    dump(tmp_path / "manifest.json", manifest)
    report = validate_package(tmp_path, scopes=["schema"])
    assert not any(f.code == "WDV-SCH-003" for f in report.findings)


def test_norm_1219_schema_does_not_require_graph_placement_review_path(tmp_path: Path):
    create_graph_package(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    manifest["normative_versions"]["consolidated_norm"] = "1.2.19"
    manifest["editorial_controls"] = _editorial_controls_124()
    dump(tmp_path / "manifest.json", manifest)
    report = validate_package(tmp_path, scopes=["schema"])
    assert not any(f.code == "WDV-SCH-003" and "graph_placement_review_path" in str(f.details) for f in report.findings)


def test_old_1221_metadata_does_not_schema_gate_graph_placement_review_path(tmp_path: Path):
    create_graph_package(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    manifest["normative_versions"]["consolidated_norm"] = "1.2.21"
    manifest["editorial_controls"] = _editorial_controls_124()
    dump(tmp_path / "manifest.json", manifest)
    report = validate_package(tmp_path, scopes=["schema"])
    assert not any(f.code == "WDV-SCH-003" for f in report.findings)

def test_source_registry_accepts_null_primary_source_for_legacy_normalization(tmp_path: Path):
    from wikidebia_validator.schema_validation import SchemaStore

    store = SchemaStore()
    source = {
        "source_registry_version": "1.0",
        "debate_id": "debat_test",
        "sources": [{
            "id": "S10001",
            "type": "webliography",
            "language": "en",
            "metadata": {
                "authors": ["Example Organization"], "article": None, "work": None, "volume": None,
                "issue": None, "location": None, "publisher": None, "place": None, "date": "2026",
                "link": "https://example.org/source", "page": "Source", "site": "Example", "title": None
            },
            "verification": {
                "status": "verified", "verified_at": "2026-08-13T01:21:24+02:00",
                "primary_source": None, "notes": ["Legacy review did not record primary-source classification."],
                "language_verified": True, "authorship_checked": True, "authorship_verified": True
            },
            "usage": [{
                "page_id": "debat_test", "language": "en", "role": "context",
                "selection_reason": "This verified source documents the context used in the debate."
            }],
            "deduplication_key": "https://example.org/source",
            "document_kind": "other", "equivalence_group": None
        }]
    }
    assert not store.validate(source, "source_registry.schema.json")



def test_schema_accepts_historical_text_render_validation_mode(tmp_path: Path):
    create_graph_package(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    controls = _editorial_controls_124()
    controls["historical_text_render_validation_mode"] = "differential_preservation_v1"
    manifest["editorial_controls"] = controls
    dump(manifest_path, manifest)
    report = validate_package(tmp_path, scopes=["schema"])
    assert not any(f.code == "WDV-SCH-003" for f in report.findings), report.to_text()


def test_schema_rejects_unknown_historical_text_render_validation_mode(tmp_path: Path):
    create_graph_package(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    controls = _editorial_controls_124()
    controls["historical_text_render_validation_mode"] = "unknown_mode"
    manifest["editorial_controls"] = controls
    dump(manifest_path, manifest)
    report = validate_package(tmp_path, scopes=["schema"])
    assert any(f.code == "WDV-SCH-003" for f in report.findings), report.to_text()
