import json
from pathlib import Path

from wikidebia_final_publication import _english_config
from wikidebia_publish import GenericPublisher


class DummyAdapter:
    pass


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_final_publication_english_config_carries_validator_fingerprint_path(tmp_path: Path):
    project = tmp_path
    debate_id = "debat_test"
    corpus = project / "corpus" / debate_id
    source = corpus / "output/en/debate/debate.wiki"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("{{Debate|topic=Test|wikipedia-articles={{Wikipedia article|page=Test}}|pro-arguments=|con-arguments=|sections=Society|keywords=test}}\n", encoding="utf-8")
    _write_json(corpus / "manifest.json", {
        "debate_id": debate_id,
        "translation_status": {"en": "ready"},
        "pages": [{
            "language": "en",
            "page_id": "D0000",
            "page_type": "debate",
            "canonical_title": "Test debate",
            "file_path": "output/en/debate/debate.wiki",
            "page_origin": "new",
        }],
    })
    validator = project / "validator"
    validator.mkdir()
    (validator / "fingerprint.txt").write_text("validator\n", encoding="utf-8")
    run_dir = project / ".state/final-publication" / debate_id / "EDIT-1"
    run_dir.mkdir(parents=True)

    config_path, config = _english_config(project, debate_id, corpus, run_dir)
    assert config["validator"]["fingerprint_path"] == str(validator)
    assert config["validator"]["max_warnings"] == 0

    publisher = GenericPublisher(config, DummyAdapter(), config_path)
    fingerprints = publisher._package_fingerprints()
    assert len(fingerprints["validator_fingerprint"]) == 64
