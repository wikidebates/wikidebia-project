import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_reconciliation_manifest_and_publication_literals():
    manifest = json.loads((ROOT / 'KIT_MANIFEST.json').read_text(encoding='utf-8'))
    assert manifest['version'] == '2.16.49'
    assert manifest['validator_version'] == '0.4.107'
    assert manifest['normative_revision'] == '1.2.90'
    assert manifest['translation_change_tag'] == 'translated-fr'
    publish = (ROOT / 'scripts' / 'wikidebia_publish.py').read_text(encoding='utf-8')
    update = (ROOT / 'scripts' / 'wikidebia_update.py').read_text(encoding='utf-8')
    review = (ROOT / 'scripts' / 'wikidebia_translation_review.py').read_text(encoding='utf-8')
    render = (ROOT / 'scripts' / 'wikidebia_render.py').read_text(encoding='utf-8')
    assert 'Translation of the French page: [[:fr:{source_title}|{source_title}]]' in publish
    assert 'Ajout du lien interlangue vers la page anglaise : [[:en:{title}|{title}]]' in update
    assert 'TRANSLATED_CITATION_WARNING = "AI-translated quote"' in review
    assert '"established-name"' in render


def test_reconciliation_preserves_translation_quality_tools_and_publication_tools():
    expected = [
        'wikidebia_documentary_resources.py',
        'wikidebia_release.py',
        'wikidebia_retro_tag.py',
        'wikidebia_translation_review.py',
        'wikidebia_publish.py',
        'wikidebia_update.py',
    ]
    for name in expected:
        assert (ROOT / 'scripts' / name).is_file(), name
    retro = (ROOT / 'scripts' / 'wikidebia_retro_tag.py').read_text(encoding='utf-8')
    assert 'translated-fr' in retro
    assert 'Translation of the French page:' in retro


def test_reconciliation_versions_are_coherent():
    versions = json.loads((ROOT / 'VERSIONS.json').read_text(encoding='utf-8'))
    assert versions['norm'] == '1.2.90'
    assert versions['validator'] == '0.4.107'
    assert versions['kit'] == '2.16.49'
