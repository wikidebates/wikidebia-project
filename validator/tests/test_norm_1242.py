from .current_policy_helpers import CURRENT_NORM_FILE, CURRENT_NORM, CURRENT_VALIDATOR, CURRENT_KIT, current_norm_path
from pathlib import Path

from wikidebia_validator.editorial import (
    _validate_debate_docs,
    validate_individual_review_data,
    validate_introduction_review_data,
)
from wikidebia_validator.report import Report


class FakeContext:
    def __init__(self, text: str, *, historical_intro_absent: bool = False):
        self.text = text
        self.historical_intro_absent = historical_intro_absent
        self.report = Report("0.4.46", "test-fixture-1242", ["editorial"])

    def manifest(self):
        return {
            "normative_versions": {"consolidated_norm": "1.2.30"},
            "pages": [{"page_type": "debate", "language": "fr", "file_path": "output/fr/debate.wiki"}],
        }

    def exists(self, rel):
        return rel == "output/fr/debate.wiki" or (self.historical_intro_absent and rel == "data/fr_content_lock.json")

    def read_text(self, rel):
        return self.text

    def load_json(self, rel):
        assert rel == "data/fr_content_lock.json" and self.historical_intro_absent
        return {
            "historical_text_decisions": {
                "debate": {
                    "page_origin": "preexisting",
                    "historical_status": "historical_absent",
                    "decision": "preserved",
                }
            }
        }


def _debate(pro_link="https://example.org/pro", con_link="https://example.org/con", video_author=True):
    author = "\n|auteurs=Chaîne Exemple" if video_author else ""
    return f"""{{{{Débat
|sujet=Exemple
|sujet-développé=l'exemple
|avancement=Débat construit
|avertissements-débat=Débat généré par IA
|introduction={{{{Sous-partie
|titre=Définition
|contenu=Une définition utile.
}}}}
|arguments-pour={{{{Argument pour
|page=Une raison favorable complète
|titre-affiché=Une raison favorable complète
}}}}
|arguments-contre={{{{Argument contre
|page=Une raison défavorable complète
|titre-affiché=Une raison défavorable complète
}}}}
|bibliographie-pour=
|bibliographie-contre=
|bibliographie-ni-pour-ni-contre=
|sitographie-pour={{{{Référence sitographique pour
|lien={pro_link}
|page=Source favorable
|site=Exemple
}}}}
|sitographie-contre={{{{Référence sitographique contre
|lien={con_link}
|page=Source défavorable
|site=Exemple
}}}}
|sitographie-ni-pour-ni-contre=
|vidéographie-pour={{{{Référence vidéographique pour
|titre=Vidéo favorable{author}
|lien=https://www.youtube.com/watch?v=abc
}}}}
|vidéographie-contre=
|vidéographie-ni-pour-ni-contre=
|rubriques=Philosophie
|mots-clés=exemple
|date-création=2026-08-06
}}}}
"""


def _controls():
    return {
        "debate_documentation": {
            "min_subsections": 1,
            "min_references": 0,
            "reject_singleton_bucket_pattern": False,
            "profile_rationale": "La documentation est sélectionnée selon sa pertinence réelle et non selon un quota.",
        },
        "debate_documentation_policy_revision": "1.2.42",
        "video_authorship_policy_revision": "1.2.42",
    }


def test_1242_allows_empty_or_single_documentary_buckets():
    ctx = FakeContext(_debate())
    _validate_debate_docs(ctx, ctx.manifest(), _controls(), norm="1.2.30")
    assert not any(f.code == "WDV-EDT-004" for f in ctx.report.findings)


def test_1242_allows_no_subsection_for_verified_historical_absence():
    text = _debate().replace("|introduction={{Sous-partie\n|titre=Définition\n|contenu=Une définition utile.\n}}\n", "")
    ctx = FakeContext(text, historical_intro_absent=True)
    metrics = _validate_debate_docs(ctx, ctx.manifest(), _controls(), norm="1.2.30")
    assert metrics["fr"]["profile_minima"]["subsections"] == 0
    assert not any(f.code == "WDV-EDT-004" and "insuffisamment" in f.message for f in ctx.report.findings)


def test_1242_rejects_same_reference_in_pro_and_con():
    ctx = FakeContext(_debate(pro_link="https://example.org/same", con_link="https://example.org/same"))
    _validate_debate_docs(ctx, ctx.manifest(), _controls(), norm="1.2.30")
    assert any(f.code == "WDV-EDT-004" and "plusieurs orientations" in f.message for f in ctx.report.findings)


def test_1242_requires_youtube_creator_or_channel():
    ctx = FakeContext(_debate(video_author=False))
    _validate_debate_docs(ctx, ctx.manifest(), _controls(), norm="1.2.30")
    assert any(f.code == "WDV-DOC-004" and "YouTube" in f.message for f in ctx.report.findings)


def _review_entry(displayed: str):
    return {
        "id": "A0001",
        "title_decision": "retained_after_review" if displayed == "Le titre canonique est déjà clair" else "reformulated",
        "canonical_referents_explicit_fr": True,
        "displayed_referents_explicit_fr": True,
        "displayed_title_complete_proposition_fr": True,
        "displayed_title_argument_intelligible_fr": True,
        "displayed_title_concision_reviewed_fr": True,
        "displayed_title_identity_justification_fr": "",
        "title_reason": "Le titre canonique est déjà clair, complet et ne gagne rien à être reformulé artificiellement.",
        "new_displayed_title_fr": displayed,
        "new_rubriques": ["Philosophie"],
        "rubric_decision": "retained_after_review",
        "rubric_rationales": {"Philosophie": "Le raisonnement est directement philosophique."},
    }


def test_1242_accepts_canonical_title_as_displayed_without_exception():
    nodes = [{
        "id": "A0001",
        "status": "active",
        "fr": {
            "canonical_title": "Le titre canonique est déjà clair",
            "displayed_title": "Le titre canonique est déjà clair",
            "rubriques": ["Philosophie"],
        },
        "en": {},
    }]
    review = {"normative_revision": "1.2.30", "entries": [_review_entry("Le titre canonique est déjà clair")]}
    issues = validate_individual_review_data(
        review,
        nodes,
        norm="1.2.30",
        english_deferred=True,
        displayed_title_policy_revision="1.2.42",
    )
    assert not any(i["reason"] == "displayed_title_identity_justification_fr" for i in issues)


def test_old_1242_revision_does_not_disable_current_dedicated_stakes_rule():
    entry = {
        "language": "fr",
        "subject_and_scope_defined": True,
        "debate_question_explained": True,
        "history_and_evolution_addressed": True,
        "current_state_addressed_or_not_applicable": True,
        "stakes_explained": False,
        "factual_claims_referenced": True,
        "progression_coherent": True,
        "no_argument_tree_mirroring": True,
        "no_topic_specific_checklist": True,
        "information_density_reviewed": True,
        "subsections_non_redundant": True,
        "no_generic_stakes_filler": True,
        "documentation_orientation_reviewed": True,
        "youtube_authorship_reviewed": True,
        "complete_topic_fits_heading": True,
        "debate_sections_precise": True,
        "documentation_proportionate_to_literature": True,
        "documentation_family_notes": {
            "bibliography": "La sélection couvre les ouvrages réellement panoramiques.",
            "webliography": "La sélection couvre les ressources générales réellement utiles.",
            "videography": "La sélection couvre les vidéos substantielles et attribuées.",
        },
        "common_acronym": None,
        "common_acronym_used_or_not_applicable": True,
        "topic_is_nominal_label": True,
        "conventional_topic_label_used_or_not_applicable": True,
        "complete_topic_lowercase_initial_or_justified": True,
        "topic_label_rationale": "Le libellé nominal est conventionnel et clair.",
        "subsections": [{
            "title": "Définition",
            "purpose": "Définir précisément le sujet.",
            "necessary_for_understanding": True,
            "technical_or_specialized": False,
            "relevance_to_debate_explained": True,
        }],
    }
    review = {"normative_revision": "1.2.30", "entries": [entry]}
    issues = validate_introduction_review_data(
        review,
        {"fr": ["Définition"]},
        norm="1.2.30",
        complete_topics={"fr": "l'exemple"},
        topics={"fr": "Exemple"},
        introduction_policy_revision="1.2.42",
    )
    assert any(i.get("field") == "stakes_explained" for i in issues)
    assert any(i.get("reason") == "missing_dedicated_stakes_subsection" for i in issues)


def test_active_norm_is_1242():
    root = Path(__file__).parents[1] / "normative_reference" / "01_normes"
    assert sorted(p.name for p in root.glob("WIKIDEBIA_NORME_CONSOLIDEE_*.md")) == [CURRENT_NORM_FILE]
