from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


render = load("wikidebia_render")
update = load("wikidebia_update")


def test_render_debate_uses_sujet_developpe_and_expanded_topic_only():
    registry = {"debate": {"pages": {"en": {"canonical_title": "Demo debate"}}}, "graph": {"edges": [], "nodes": [], "occurrences": []}}
    fr = render._render_debate(
        lang="fr", registry=registry,
        metadata_lock={"debate": {"rubriques": ["Philosophie"], "keywords": ["démonstration"]}},
        content_lock={"debate": {"subject": "Démo", "complete_topic": "la démonstration", "page_origin": "new", "preserved_parameters": {}, "introduction": "{{Sous-partie|titre=Définition|contenu=Texte.}}", "wikipedia_articles": ["Démonstration"], "sources": {}, "documentation": {}}},
        sources={},
    )
    en = render._render_debate(
        lang="en", registry=registry,
        metadata_lock={"debate": {"sections": ["Philosophy"], "keywords": ["demonstration"]}},
        content_lock={"debate": {"topic": "Demonstration", "complete_topic": "demonstration", "page_origin": "new", "preserved_parameters": {}, "introduction": "{{Subsection|title=Definition|content=Text.}}", "wikipedia_articles": ["Proof"], "sources": {}, "documentation": {}}},
        sources={},
    )
    assert "|sujet-développé=la démonstration" in fr and "|sujet-complet=" not in fr
    assert "|expanded-topic=demonstration" in en and "|complete-topic=" not in en


def test_render_normalizes_legacy_detailed_debate_preserved_key():
    child = {"id": "A2", "fr": {"canonical_title": "Enfant", "displayed_title": "Un enfant soutient la thèse", "rubriques": ["Philosophie"], "keywords": ["test"]}}
    node = {"id": "A1", "fr": {"rubriques": ["Philosophie"], "keywords": ["test"]}, "en": {"canonical_title": "Argument"}}
    registry = {"graph": {"edges": [{"id": "E1", "parent_node_id": "A1", "child_node_id": "A2", "relation": "justification", "order": 1, "status": "active"}], "occurrences": [], "nodes": [node, child]}}
    content = {"summary": "Résumé.", "citations": [], "sources": {}, "page_origin": "preexisting", "preserved_parameters": {"avertissements-argument": {"present": False, "value": None}, "débat-détaillé": {"present": True, "value": "Débat source"}}}
    text = render._render_argument(lang="fr", node=node, content=content, registry=registry, sources={})
    assert "|débat-dédié=Débat source" in text
    assert "|débat-détaillé=" not in text
    assert "|justifications=" not in text


def test_remote_update_treats_parameter_rename_as_same_top_level_field():
    remote = "{{Argument\n|débat-détaillé=Débat source\n|rubriques=Philosophie\n}}\n"
    proposed = "{{Argument\n|débat-dédié=Débat source\n|rubriques=Philosophie\n}}\n"
    assert update.top_level_parameter_deletions(remote, proposed, "fr", "argument") == []


def test_render_normalizes_legacy_detailed_debate_preserved_key_in_english():
    child = {"id": "A2", "en": {"canonical_title": "Child", "displayed_title": "A child supports the claim", "sections": ["Philosophy"], "keywords": ["test"]}}
    node = {"id": "A1", "en": {"sections": ["Philosophy"], "keywords": ["test"]}, "fr": {"canonical_title": "Argument"}}
    registry = {"graph": {"edges": [{"id": "E1", "parent_node_id": "A1", "child_node_id": "A2", "relation": "justification", "order": 1, "status": "active"}], "occurrences": [], "nodes": [node, child]}}
    content = {"summary": "Summary.", "quotes": [], "sources": {}, "page_origin": "preexisting", "preserved_parameters": {"argument-warnings": {"present": False, "value": None}, "detailed-debate": {"present": True, "value": "Source debate"}}}
    text = render._render_argument(lang="en", node=node, content=content, registry=registry, sources={})
    assert "|dedicated-debate=Source debate" in text
    assert "|detailed-debate=" not in text
    assert "|justifications=" not in text


def test_remote_update_treats_all_four_parameter_renames_as_same_top_level_field():
    cases = [
        ("fr", "debate", "sujet-complet", "sujet-développé", "le sujet"),
        ("en", "debate", "complete-topic", "expanded-topic", "the topic"),
        ("fr", "argument", "débat-détaillé", "débat-dédié", "Débat source"),
        ("en", "argument", "detailed-debate", "dedicated-debate", "Source debate"),
    ]
    for lang, page_type, old_name, new_name, value in cases:
        remote = f"{{{{{'Débat' if page_type == 'debate' and lang == 'fr' else 'Debate' if page_type == 'debate' else 'Argument'}\n|{old_name}={value}\n}}}}\n"
        proposed = f"{{{{{'Débat' if page_type == 'debate' and lang == 'fr' else 'Debate' if page_type == 'debate' else 'Argument'}\n|{new_name}={value}\n}}}}\n"
        assert update.top_level_parameter_deletions(remote, proposed, lang, page_type) == []


def test_kit_manifest_declares_parameter_rename_guards():
    import json
    manifest = json.loads((Path(__file__).resolve().parents[1] / "KIT_MANIFEST.json").read_text(encoding="utf-8"))
    assert "mediawiki_parameter_rename_1269" in manifest["scope"]
    assert "legacy_mediawiki_parameter_alias_migration" in manifest["safety"]
    assert "canonical_expanded_topic_and_dedicated_debate_parameters" in manifest["features"]
    assert "current_mediawiki_parameter_name_gate" in manifest["quality_gates"]
    assert "mediawiki_parameter_rename_1269_regression" in manifest["regression_gates"]
    assert "historical_parameter_alias_preservation_1269" in manifest["regression_gates"]
