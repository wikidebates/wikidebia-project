from wikidebia_validator.editorial import (
    keyword_atomicity_issues,
    lowercase_god_issues,
    normalized_summary_sentences,
    summary_template_issues,
)


def test_productive_thematic_keyword_is_rejected_even_with_generic_attestation():
    issues = keyword_atomicity_issues(
        "limites de la science",
        {
            "atomic_concept": True,
            "multiword_exception": True,
            "multiword_exception_rationale": "Expression décrivant un angle thématique général.",
        },
    )
    assert "productive_thematic_phrase" in issues


def test_productive_historical_keyword_requires_explicit_semantic_exception():
    assert keyword_atomicity_issues(
        "histoire du féminisme",
        {
            "atomic_concept": True,
            "compositional_intersection": False,
            "multiword_exception": True,
            "multiword_exception_rationale": "Locution historique conservée comme concept de navigation atomique.",
        },
        "fr",
        require_composition_attestation=True,
    ) == []


def test_productive_exception_without_semantic_rationale_is_rejected():
    issues = keyword_atomicity_issues(
        "history of feminism",
        {
            "atomic_concept": True,
            "compositional_intersection": False,
            "multiword_exception": True,
            "multiword_exception_rationale": "Keep this old value.",
        },
        "en",
        require_composition_attestation=True,
    )
    assert "productive_thematic_phrase" in issues


def test_lexicalized_multiword_keyword_is_accepted_with_specific_exception():
    assert keyword_atomicity_issues(
        "lois de la nature",
        {
            "atomic_concept": True,
            "multiword_exception": True,
            "multiword_exception_rationale": "Locution encyclopédique stabilisée qui désigne le concept de natural law.",
        },
    ) == []


def test_simple_atomic_keyword_is_accepted_without_exception():
    assert keyword_atomicity_issues(
        "épistémologie",
        {"atomic_concept": True, "multiword_exception": False},
    ) == []


def test_stock_summary_scaffolding_is_rejected():
    text = (
        "Plusieurs faits ou principes sont ici interprétés de manière à soutenir une conclusion. "
        "La thèse en tire une conséquence directe pour l'existence de Dieu."
    )
    assert "generic_scaffolding" in summary_template_issues(text, "fr")


def test_individual_summary_without_scaffolding_is_accepted():
    text = (
        "Le désir humain dépasse les satisfactions finies et vise un accomplissement sans limite. "
        "Cette orientation durable est interprétée comme l'indice d'une réalité transcendante capable de lui répondre."
    )
    assert summary_template_issues(text, "fr") == []


def test_lowercase_proper_name_god_is_rejected_but_generic_use_is_kept():
    assert lowercase_god_issues("L'existence de dieu expliquerait le monde.") == ["lowercase_proper_name"]
    assert lowercase_god_issues("Un dieu local pourrait être imaginé par une culture.") == []


def test_sentence_normalization_supports_corpus_wide_repetition_detection():
    first = normalized_summary_sentences(
        "La même phrase assez longue est répétée mécaniquement dans plusieurs résumés du corpus.",
        "fr",
    )
    second = normalized_summary_sentences(
        "La même phrase assez longue est répétée mécaniquement dans plusieurs résumés du corpus.",
        "fr",
    )
    assert first and first == second


def test_argument_d_authorite_remains_an_atomic_keyword():
    assert keyword_atomicity_issues(
        "argument d'autorité",
        {
            "atomic_concept": True,
            "multiword_exception": True,
            "multiword_exception_rationale": "Locution encyclopédique stabilisée désignant un type d'argument.",
        },
    ) == []
