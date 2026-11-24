from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import wikidebia_update as update
import wikidebia_render as render


def test_top_level_deletion_guard_covers_warnings_and_content_parameters():
    remote = """{{Argument
|avertissements-titre=Titre peu clair
|résumé=Résumé existant.
|citations={{Citation|citation=Texte}}
|rubriques=Philosophie
|mots-clés=Dieu
|date-création=2026-08-01
}}
"""
    proposed = """{{Argument
|résumé=Résumé modifié.
|rubriques=Philosophie
|mots-clés=Dieu
|date-création=2026-08-01
}}
"""
    assert update.top_level_parameter_deletions(remote, proposed, "fr", "argument") == [
        "avertissements-titre",
        "citations",
    ]


def test_historical_restoration_can_remove_only_attested_wrong_ai_marker():
    remote = """{{Argument
|avertissements-argument=Argument généré par IA
|résumé=Résumé.
|rubriques=Philosophie
|mots-clés=Dieu
|date-création=2026-08-01
}}
"""
    proposed = remote
    states = {
        "initialisation": {"present": False, "value": None},
        "nom-consacré": {"present": False, "value": None},
        "nom": {"present": False, "value": None},
        "avertissements-titre": {"present": False, "value": None},
        "avertissements-argument": {"present": False, "value": None},
        "avertissements-résumé": {"present": False, "value": None},
        "avertissements-références": {"present": False, "value": None},
        "avertissements-justifications": {"present": False, "value": None},
        "avertissements-objections": {"present": False, "value": None},
        "débat-dédié": {"present": False, "value": None},
        "interlangue": {"present": False, "value": None},
        "date-création": {"present": True, "value": "2026-08-01"},
    }
    effective, audit = update.preserve_remote_lifecycle_parameters(
        remote,
        proposed,
        "fr",
        "argument",
        desired_preserved_parameters=states,
        allow_historical_restoration=True,
    )
    assert "|avertissements-argument=" not in effective
    assert "|date-création=" not in effective
    assert audit["historical_restoration"] is True


def test_existing_argument_renderer_preserves_all_historical_warning_slots():
    node = {
        "id": "A0001",
        "fr": {"rubriques": ["Philosophie"], "keywords": ["Dieu"]},
        "en": {"canonical_title": "Argument"},
    }
    registry = {"graph": {"edges": [], "occurrences": [], "nodes": [node]}}
    preserved = {
        "initialisation": {"present": True, "value": "Objection@1"},
        "nom": {"present": True, "value": "Nom historique"},
        "avertissements-titre": {"present": True, "value": "Titre peu clair"},
        "avertissements-argument": {"present": True, "value": "Argument saugrenu"},
        "avertissements-résumé": {"present": True, "value": "Résumé à revoir"},
        "avertissements-références": {"present": True, "value": "Références incomplètes"},
        "avertissements-justifications": {"present": True, "value": "Justifications incomplètes"},
        "avertissements-objections": {"present": True, "value": "Objections incomplètes"},
        "débat-dédié": {"present": False, "value": None},
        "interlangue": {"present": False, "value": None},
        "date-création": {"present": True, "value": "2020-01-01"},
    }
    content = {
        "summary": "Résumé édité sans nettoyage des métadonnées historiques.",
        "citations": [],
        "sources": {},
        "page_origin": "preexisting",
        "preserved_parameters": preserved,
    }
    text = render._render_argument(
        lang="fr", node=node, content=content, registry=registry, sources={}
    )
    for fragment in [
        "|initialisation=Objection@1",
        "|nom=Nom historique",
        "|avertissements-titre=Titre peu clair",
        "|avertissements-argument=Argument saugrenu",
        "|avertissements-résumé=Résumé à revoir",
        "|avertissements-références=Références incomplètes",
        "|avertissements-justifications=Justifications incomplètes",
        "|avertissements-objections=Objections incomplètes",
    ]:
        assert fragment in text
    assert "|date-création=" not in text
    assert "Argument généré par IA" not in text


def test_new_argument_renderer_still_uses_restricted_creation_profile():
    node = {
        "id": "A9999",
        "fr": {"rubriques": ["Philosophie"], "keywords": ["Dieu"]},
        "en": {"canonical_title": "Argument"},
    }
    registry = {"graph": {"edges": [], "occurrences": [], "nodes": [node]}}
    content = {
        "summary": "Résumé d'une page réellement nouvelle.",
        "citations": [],
        "sources": {},
        "page_origin": "new",
        "preserved_parameters": {},
    }
    text = render._render_argument(
        lang="fr", node=node, content=content, registry=registry, sources={}
    )
    assert "|avertissements-argument=Argument généré par IA" in text
    assert "|nom-consacré=" not in text
    assert "|nom=" not in text
    assert "|avertissements-titre=" not in text


def test_explicit_argument_name_assignment_overrides_historical_absence_only_for_name():
    remote = """{{Argument
|résumé=Résumé historique.
|rubriques=Philosophie
|mots-clés=Dieu
|date-création=2020-01-01
}}
"""
    proposed = """{{Argument
|nom-consacré=Argument moral
|résumé=Résumé historique.
|rubriques=Philosophie
|mots-clés=Dieu
|date-création=2020-01-01
}}
"""
    states = {
        "initialisation": {"present": False, "value": None},
        "nom-consacré": {"present": False, "value": None},
        "nom": {"present": False, "value": None},
        "avertissements-titre": {"present": False, "value": None},
        "avertissements-argument": {"present": False, "value": None},
        "avertissements-résumé": {"present": False, "value": None},
        "avertissements-références": {"present": False, "value": None},
        "avertissements-justifications": {"present": False, "value": None},
        "avertissements-objections": {"present": False, "value": None},
        "débat-dédié": {"present": False, "value": None},
        "interlangue": {"present": False, "value": None},
        "date-création": {"present": True, "value": "2020-01-01"},
    }
    effective, audit = update.preserve_remote_lifecycle_parameters(
        remote, proposed, "fr", "argument",
        desired_preserved_parameters=states,
        allow_historical_restoration=True,
        explicit_parameter_assignments={"nom-consacré": "Argument moral"},
    )
    assert "|nom-consacré=Argument moral" in effective
    assert audit["explicit_parameter_assignments"] == {"nom-consacré": "Argument moral"}
    assert "|avertissements-argument=" not in effective


def test_explicit_argument_name_assignment_rejects_other_protected_parameter():
    remote = "{{Argument\n|date-création=2020-01-01\n}}"
    try:
        update.preserve_remote_lifecycle_parameters(
            remote, remote, "fr", "argument",
            explicit_parameter_assignments={"avertissements-argument": "X"},
        )
    except update.UpdateError as exc:
        assert "nom-consacré/established-name" in str(exc)
    else:
        raise AssertionError("Une attribution explicite hors nom-consacré/established-name aurait dû être refusée")


def test_new_argument_renderer_emits_reviewed_conventional_name():
    node = {
        "id": "A9998",
        "fr": {"rubriques": ["Philosophie"], "keywords": ["Dieu"]},
        "en": {"canonical_title": "Argument"},
    }
    registry = {"graph": {"edges": [], "occurrences": [], "nodes": [node]}}
    content = {
        "summary": "Résumé d'une page réellement nouvelle.",
        "citations": [],
        "sources": {},
        "argument_name": "Argument cosmologique",
        "page_origin": "new",
        "preserved_parameters": {},
    }
    text = render._render_argument(
        lang="fr", node=node, content=content, registry=registry, sources={}
    )
    assert "|nom-consacré=Argument cosmologique" in text


def test_pre_1258_restoration_manifest_with_only_legacy_nom_remains_compatible():
    remote = """{{Argument
|nom=Argument historique
|résumé=Résumé historique.
|rubriques=Philosophie
|mots-clés=Dieu
|date-création=2020-01-01
}}
"""
    states = {
        "initialisation": {"present": False, "value": None},
        "nom": {"present": True, "value": "Argument historique"},
        "avertissements-titre": {"present": False, "value": None},
        "avertissements-argument": {"present": False, "value": None},
        "avertissements-résumé": {"present": False, "value": None},
        "avertissements-références": {"present": False, "value": None},
        "avertissements-justifications": {"present": False, "value": None},
        "avertissements-objections": {"present": False, "value": None},
        "débat-dédié": {"present": False, "value": None},
        "interlangue": {"present": False, "value": None},
        "date-création": {"present": True, "value": "2020-01-01"},
    }
    effective, audit = update.preserve_remote_lifecycle_parameters(
        remote, remote, "fr", "argument",
        desired_preserved_parameters=states,
        allow_historical_restoration=True,
    )
    assert "|nom=Argument historique" in effective
    assert "|nom-consacré=" not in effective
    assert set(audit["effective"]) == set(states)


def test_pre_1258_restoration_manifest_with_only_legacy_english_name_remains_compatible():
    remote = """{{Argument
|name=Cosmological argument
|summary=Historical summary.
|sections=Philosophy
|keywords=God
|creation-date=2020-01-01
}}
"""
    states = {
        "initialization": {"present": False, "value": None},
        "name": {"present": True, "value": "Cosmological argument"},
        "title-warnings": {"present": False, "value": None},
        "argument-warnings": {"present": False, "value": None},
        "summary-warnings": {"present": False, "value": None},
        "reference-warnings": {"present": False, "value": None},
        "justification-warnings": {"present": False, "value": None},
        "objection-warnings": {"present": False, "value": None},
        "dedicated-debate": {"present": False, "value": None},
        "creation-date": {"present": True, "value": "2020-01-01"},
    }
    effective, audit = update.preserve_remote_lifecycle_parameters(
        remote, remote, "en", "argument",
        desired_preserved_parameters=states,
        allow_historical_restoration=True,
    )
    assert "|name=Cosmological argument" in effective
    assert "|established-name=" not in effective
    assert set(audit["effective"]) == set(states)
