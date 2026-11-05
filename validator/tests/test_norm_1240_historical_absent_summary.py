import json
from pathlib import Path

from wikidebia_validator.validator import validate_package
from .test_norm_1239_legacy_preservation import _package, _field, _enable_inventory_verification
from .helpers import dump


def _remove_summary_everywhere(root: Path, page: dict, path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    summary_line = f"|résumé={_field(text, 'résumé')}\n"
    text = text.replace(summary_line, "")
    path.write_text(text, encoding="utf-8")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    batch = next(b for b in manifest["batches"] if page["page_id"] in b["node_ids"])
    aggregate_path = root / batch["outputs"]["aggregate_path"]
    aggregate = aggregate_path.read_text(encoding="utf-8")
    marker = f"===== PAGE : {page['canonical_title']} =====\n"
    block_start = aggregate.index(marker) + len(marker)
    next_marker = aggregate.find("\n===== PAGE : ", block_start)
    block_end = len(aggregate) if next_marker < 0 else next_marker + 1
    aggregate = aggregate[:block_start] + text.rstrip() + "\n" + aggregate[block_end:]
    aggregate_path.write_text(aggregate, encoding="utf-8")


def _activate_absence_policy(root: Path, manifest: dict, page: dict, path: Path) -> None:
    source_text = path.read_text(encoding="utf-8")
    source_text = source_text.replace(f"|résumé={_field(source_text, 'résumé')}\n", "")
    _enable_inventory_verification(root, manifest, page, source_text)
    current = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    cfg = current["editorial_controls"]["legacy_content_preservation"]
    cfg["verification_revision"] = "0.4.43"
    cfg["historical_summary_absence_revision"] = "1.2.40"
    current["editorial_controls"]["summary_policy_revision"] = "1.2.40"
    dump(root / "manifest.json", current)
    lock = json.loads((root / "data/historical_content_lock.json").read_text(encoding="utf-8"))
    lock["schema_version"] = "1.1"
    entry = lock["arguments"][0]
    entry["summary_provenance"] = "historical_absent"
    entry.pop("summary_sha256", None)
    entry.pop("summary_length", None)
    dump(root / "data/historical_content_lock.json", lock)


def test_verified_historical_absence_allows_omitted_summary(tmp_path: Path):
    manifest, page, path = _package(tmp_path)
    _activate_absence_policy(tmp_path, manifest, page, path)
    _remove_summary_everywhere(tmp_path, page, path)
    report = validate_package(tmp_path, scopes=["schema", "wikicode"])
    assert not any(f.code in {"WDV-MWK-004", "WDV-EDT-027"} and (f.path == page["file_path"] or f.details.get("page_id") == page["page_id"]) for f in report.findings)


def test_historical_absent_summary_cannot_be_reintroduced_silently(tmp_path: Path):
    manifest, page, path = _package(tmp_path)
    _activate_absence_policy(tmp_path, manifest, page, path)
    report = validate_package(tmp_path, scopes=["schema", "wikicode"])
    assert any(f.code == "WDV-EDT-027" and "ajouté" in f.message for f in report.findings)


def test_new_page_still_requires_summary(tmp_path: Path):
    manifest, page, path = _package(tmp_path)
    _activate_absence_policy(tmp_path, manifest, page, path)
    other = manifest["pages"][2]
    other_path = tmp_path / other["file_path"]
    _remove_summary_everywhere(tmp_path, other, other_path)
    report = validate_package(tmp_path, scopes=["schema", "wikicode"])
    assert any(f.code == "WDV-MWK-004" and f.path == other["file_path"] for f in report.findings)


def test_generated_after_import_summary_still_required(tmp_path: Path):
    manifest, page, path = _package(tmp_path)
    _activate_absence_policy(tmp_path, manifest, page, path)
    lock = json.loads((tmp_path / "data/historical_content_lock.json").read_text(encoding="utf-8"))
    lock["arguments"][0]["summary_provenance"] = "generated_after_import"
    dump(tmp_path / "data/historical_content_lock.json", lock)
    _remove_summary_everywhere(tmp_path, page, path)
    report = validate_package(tmp_path, scopes=["schema", "wikicode"])
    assert any(f.code in {"WDV-MWK-004", "WDV-EDT-027"} for f in report.findings)

    # Une décision explicite du propriétaire peut, à l'inverse, supprimer un résumé
    # historiquement présent sans désactiver la protection des autres pages.
    manifest2, page2, path2 = _package(tmp_path / "owner_removed")
    source_text = path2.read_text(encoding="utf-8")
    _enable_inventory_verification(tmp_path / "owner_removed", manifest2, page2, source_text)
    owner_root = tmp_path / "owner_removed"
    current = json.loads((owner_root / "manifest.json").read_text(encoding="utf-8"))
    current["editorial_controls"]["legacy_content_preservation"]["verification_revision"] = "0.4.51"
    dump(owner_root / "manifest.json", current)
    lock2 = json.loads((owner_root / "data/historical_content_lock.json").read_text(encoding="utf-8"))
    lock2["schema_version"] = "1.2"
    entry2 = lock2["arguments"][0]
    entry2["summary_provenance"] = "owner_removed"
    entry2.pop("summary_sha256", None)
    entry2.pop("summary_length", None)
    entry2["owner_decision"] = "Le propriétaire demande explicitement la suppression de ce résumé historique."
    entry2["owner_decision_recorded_at"] = "2026-08-07T11:43:00+02:00"
    dump(owner_root / "data/historical_content_lock.json", lock2)
    _remove_summary_everywhere(owner_root, page2, path2)
    report2 = validate_package(owner_root, scopes=["schema", "wikicode"])
    assert not any(f.code in {"WDV-MWK-004", "WDV-EDT-027", "WDV-EDT-030"} and (f.path == page2["file_path"] or f.details.get("page_id") == page2["page_id"]) for f in report2.findings)


def test_preexisting_empty_classification_metadata_can_remain_absent(tmp_path: Path):
    manifest, page, path = _package(tmp_path)
    current = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    stored_page = next(row for row in current["pages"] if row["page_id"] == page["page_id"] and row["language"] == "fr")
    stored_page["page_origin"] = "preexisting"
    dump(tmp_path / "manifest.json", current)

    registry_path = tmp_path / "data/registre_debat.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    node = next(row for row in registry["graph"]["nodes"] if row["id"] == page["page_id"])
    node["fr"]["rubriques"] = []
    node["fr"]["keywords"] = []
    dump(registry_path, registry)

    rendered = path.read_text(encoding="utf-8")
    rendered = rendered.replace(f"|rubriques={_field(rendered, 'rubriques')}\n", "")
    rendered = rendered.replace(f"|mots-clés={_field(rendered, 'mots-clés')}\n", "")
    path.write_text(rendered, encoding="utf-8")

    report = validate_package(tmp_path, scopes=["wikicode"])
    missing = [
        finding for finding in report.findings
        if finding.code == "WDV-MWK-004" and finding.path == page["file_path"]
    ]
    assert not any("rubriques" in finding.message or "mots-clés" in finding.message for finding in missing)
