from wikidebia_validator.editorial import (
    displayed_title_issues,
    keyword_form_issues,
    summary_word_ratio,
)


def test_displayed_title_rejects_ellipsis():
    assert "ellipsis" in displayed_title_issues("Les comparaisons multiples peuvent...", "fr")


def test_displayed_title_rejects_truncated_article():
    reasons = displayed_title_issues(
        "S comparaisons multiples et les arrêts flexibles peuvent produire un faux positif",
        "fr",
    )
    assert "malformed_article" in reasons


def test_displayed_title_rejects_dangling_connector():
    assert "dangling_connector" in displayed_title_issues("Une explication fondée sur", "fr")
    assert "dangling_connector" in displayed_title_issues("An explanation based on", "en")


def test_displayed_title_accepts_phrasal_verb_ending_in_with():
    assert "dangling_connector" not in displayed_title_issues(
        "Men who make that accusation were not allies to begin with", "en"
    )


def test_displayed_title_accepts_complete_french_sentence():
    assert displayed_title_issues(
        "L'enregistrement préalable d'une méta-analyse réduit la flexibilité analytique",
        "fr",
    ) == []


def test_keyword_form_accepts_two_to_four_unique_terms():
    assert keyword_form_issues(["méta-analyse", "préinscription"]) == []
    assert "duplicates" in keyword_form_issues(["méta-analyse", "préinscription", "méta-analyse"])
    assert "count" in keyword_form_issues(["a", "b", "c", "d", "e"])


def test_summary_word_ratio_detects_large_asymmetry():
    fr = " ".join(["preuve"] * 100)
    en = " ".join(["evidence"] * 30)
    assert summary_word_ratio(fr, en) == 0.3
