"""Public visibility is not a write-API acknowledgement or signed plan execution."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import wikidebia_final_publication as final
import wikidebia_public_visibility as visibility


EN_DEBATE = "{{Debate\n|topic=Should we agree?\n|introduction=An actual debate.\n}}\n"
EN_ARGUMENT = "{{Argument\n|summary=The substantive argument.\n}}\n"
FR_DEBATE = (
    "{{Débat\n|sujet=Faut-il être d'accord ?\n"
    "|interlangue={{Lien interlangue|langue=en|page=Should we agree?}}\n}}\n"
)
FR_ARGUMENT = (
    "{{Argument\n|résumé=Texte français.\n"
    "|interlangue={{Lien interlangue|langue=en|page=An actual argument}}\n}}\n"
)


def _plans():
    en = {
        "plan_sha256": "e" * 64,
        "actions": [
            {"operation": "create", "language": "en", "page_type": "debate",
             "page_id": "demo", "title": "Should we agree?",
             "desired_sha256": visibility._sha_text(EN_DEBATE)},
            {"operation": "skip", "language": "en", "page_type": "argument",
             "page_id": "A0001", "title": "An actual argument",
             "desired_sha256": visibility._sha_text(EN_ARGUMENT),
             "remote_sha256": visibility._sha_text(EN_ARGUMENT)},
        ],
    }
    fr = {
        "plan_sha256": "f" * 64,
        "operations": {
            "update": [
                {"language": "fr", "page_type": "debate", "page_id": "demo",
                 "title": "Faut-il être d'accord ?"},
            ],
            "skip": [
                {"language": "fr", "page_type": "argument", "page_id": "A0001",
                 "title": "Un argument réel"},
            ],
        },
    }
    return en, fr


class AnonymousFake:
    """Separate public observation, deliberately independent from writer results."""

    def __init__(self, *, missing_en=(), missing_fr=(), hide_html=(),
                 wrong_link=(), api_unavailable=False, missing_rendered_link=()):
        self.pages_by_language = {
            "en": {"Should we agree?": EN_DEBATE, "An actual argument": EN_ARGUMENT},
            "fr": {"Faut-il être d'accord ?": FR_DEBATE, "Un argument réel": FR_ARGUMENT},
        }
        self.missing_en = set(missing_en)
        self.missing_fr = set(missing_fr)
        self.hide_html = set(hide_html)
        self.wrong_link = set(wrong_link)
        self.api_unavailable = api_unavailable
        self.missing_rendered_link = set(missing_rendered_link)
        self.calls = []

    def pages(self, language, titles):
        self.calls.append(("public_api", language, tuple(titles)))
        if self.api_unavailable:
            raise visibility.PublicUnavailable("HTTP 503 API publique")
        result = {}
        for title in titles:
            if title in (self.missing_en if language == "en" else self.missing_fr):
                result[title] = {"exists": False}
                continue
            text = self.pages_by_language[language][title]
            if (language, title) in self.wrong_link:
                text = text.replace("page=Should we agree?", "page=Wrong English page")
            result[title] = {
                "exists": True, "pageid": 100,
                "revision_id": 5, "canonical_title": title,
                "text": text, "redirect": False,
            }
        return result

    def html(self, language, title):
        self.calls.append(("public_html", language, title))
        if (language, title) in self.hide_html:
            raise visibility.PublicMissing("HTTP 404")
        href = (
            '<a href="https://en.wikidebates.org/wiki/Should_we_agree%3F">EN</a>'
            if title == "Faut-il être d'accord ?"
            else '<a href="https://en.wikidebates.org/wiki/An_actual_argument">EN</a>'
        )
        if (language, title) in self.missing_rendered_link:
            href = ""
        body = (
            f'<html><h1 id="firstHeading"><span>{title}</span></h1>'
            f'<div id="mw-content-text"><div class="mw-parser-output">{href}</div></div></html>'
        )
        document = visibility._PublicDocument()
        document.feed(body)
        assert document.heading == title
        return document


def _run(client):
    en, fr = _plans()
    return visibility.verify_public_visibility(
        "demo", "EDIT-20261121-001", en, fr, client=client,
        manifest_sha256="m" * 64,
    )


def test_public_debate_and_all_pages_and_links_are_independently_verified():
    client = AnonymousFake()
    result = _run(client)
    assert result["status"] == visibility.VERIFIED
    assert result["public_debate_verified"] is True
    assert result["public_debate_url"] == "https://en.wikidebates.org/wiki/Should_we_agree%3F"
    assert result["english_pages_checked"] == result["english_pages_verified"] == 2
    assert result["french_links_checked"] == result["french_links_verified"] == 2
    assert result["issues"] == []
    assert result["report_sha256"] == visibility._sha_object({
        k: v for k, v in result.items() if k != "report_sha256"
    })
    assert sum(call[0] == "public_html" for call in client.calls) == 4


def test_write_succeeds_but_english_page_absent_in_public_api_is_partial():
    # The author of the page can see a successful API write while anonymous
    # public readers still cannot find the page. Never upgrade this to done.
    writer_result = {"action": "edit", "result": "Success", "newrevid": 4242}
    assert writer_result["result"] == "Success"
    report = _run(AnonymousFake(missing_en={"Should we agree?"}))
    assert report["status"] == visibility.PARTIAL
    assert report["public_debate_verified"] is False
    assert report["english_pages_verified"] == 1
    assert report["french_links_verified"] == 1
    assert any(x["kind"] == "english_page" and "introuvable" in x["reason"]
               for x in report["issues"])


@pytest.mark.parametrize("title", ["Should we agree?", "An actual argument"])
def test_english_404_html_after_api_success_is_publication_partial(title):
    result = _run(AnonymousFake(hide_html={("en", title)}))
    assert result["status"] == visibility.PARTIAL
    assert result["english_pages_verified"] == 1


def test_english_pages_but_wrong_french_interlanguage_target_is_partial():
    result = _run(AnonymousFake(wrong_link={("fr", "Faut-il être d'accord ?")}))
    assert result["status"] == visibility.PARTIAL
    assert result["english_pages_verified"] == 2
    assert result["french_links_verified"] == 1
    assert result["issues"][0]["kind"] == "french_link"


def test_link_existing_only_in_wikitext_but_not_html_must_fail():
    result = _run(AnonymousFake(missing_rendered_link={("fr", "Un argument réel")}))
    assert result["status"] == visibility.PARTIAL
    assert "HTML public" in result["issues"][0]["reason"]


def test_public_api_unavailable_is_unconfirmed_not_falsely_partial():
    result = _run(AnonymousFake(api_unavailable=True))
    assert result["status"] == visibility.UNCONFIRMED
    assert result["english_pages_verified"] == 0
    assert result["french_links_verified"] == 0
    assert len(result["issues"]) == 4


def test_incomplete_batch_is_unconfirmed_not_unchecked_success():
    class Incomplete(AnonymousFake):
        def pages(self, language, titles):
            return {}

    result = _run(Incomplete())
    assert result["status"] == visibility.UNCONFIRMED


def test_changed_english_content_is_partial_even_when_page_exists():
    client = AnonymousFake()
    client.pages_by_language["en"]["Should we agree?"] = "{{Debate|topic=Unrelated debate}}"
    result = _run(client)
    assert result["status"] == visibility.PARTIAL
    assert any("Contenu public différent" in x["reason"] for x in result["issues"])


@pytest.mark.parametrize("url", [
    "https://wikidebates.org/wiki/Should_we_agree",
    "http://en.wikidebates.org/wiki/Should_we_agree",
    "https://attacker.example/wiki/Should_we_agree",
    "https://en.wikidebates.org:443/wiki/Should_we_agree",
])
def test_anonymous_reader_rejects_non_exact_public_hosts_and_schemes(url):
    with pytest.raises(visibility.PublicUnavailable):
        visibility._verify_host(url, "en")


def test_url_encoding_handles_spaces_and_apostrophes():
    url = visibility._public_url("en", "Is Europe's future secure?")
    assert url.startswith("https://en.wikidebates.org/wiki/Is_Europe's_future_secure%3F")


def test_nested_first_heading_is_not_contaminated_by_page_content():
    doc = visibility._PublicDocument()
    doc.feed('<h1 id="firstHeading"><span>English</span> Debate</h1>'
             '<div class="mw-parser-output">Irrelevant text</div>')
    assert doc.heading == "English Debate"
    assert doc.content_seen is True


def test_missing_debate_or_duplicate_page_plan_blocks_instead_of_claiming_success():
    en, fr = _plans()
    en["actions"][0]["page_type"] = "argument"
    with pytest.raises(visibility.PublicVisibilityError):
        visibility.verify_public_visibility("demo", "EDIT-TEST", en, fr, client=AnonymousFake())


def test_signed_diagnostic_is_written_when_page_cannot_be_seen(tmp_path: Path):
    en, fr = _plans()
    report = visibility.check_or_record(
        tmp_path, "demo", "EDIT-TEST", en, fr,
        client=AnonymousFake(missing_en={"Should we agree?"}),
    )
    assert report["status"] == visibility.PARTIAL
    saved = json.loads((tmp_path / "public-visibility-report.json").read_text())
    assert saved["public_debate_url"] == report["public_debate_url"]
    assert saved["report_sha256"] == report["report_sha256"]
    assert not (tmp_path / "publication-receipt.json").exists()


def test_final_publisher_refuses_completion_when_writer_succeeds_but_public_page_missing(tmp_path: Path, monkeypatch):
    """Regression: successful English write != a publicly verifiable debate."""
    release = tmp_path / "release"
    release.mkdir()
    (release / "manifest.json").write_text('{"debate_id":"demo"}', encoding="utf-8")
    en, fr = _plans()
    # Keep only one page to simplify this exact orchestration test.
    en["actions"] = en["actions"][:1]
    fr["operations"]["skip"] = []
    plans = {
        "en_plan": en, "fr_plan": fr,
        "en_config": {}, "fr_config": {},
        "en_config_path": tmp_path / "en-config.json",
        "fr_config_path": tmp_path / "fr-config.json",
    }
    baseline = {"baseline_sha256": "b" * 64, "fr": {"mode": "normal"},
                "release": {"release_copy_tree_sha256": "c" * 64}}
    preflight = {"preflight_sha256": "p" * 64}
    authorization = {"authorization_sha256": "a" * 64}
    monkeypatch.setattr(final, "_verify_prepared_publication",
                        lambda *args: (baseline, plans, preflight))
    monkeypatch.setattr(final, "_authorization",
                        lambda *args: authorization)
    for name in ("_migrate_english_publication_order", "_migrate_english_plan_after_kit_change"):
        monkeypatch.setattr(final, name, lambda *args: (plans, preflight, authorization))
    monkeypatch.setattr(final, "build_adapter", lambda *args: object())

    class SuccessfulWriter:
        def __init__(self, *args):
            pass
        def publish(self, **kw):
            return {"created": 1, "updated": 0, "skipped": 0}

    class SuccessfulFrenchExecutor:
        def __init__(self, *args):
            pass
        def resume_latest_receipt(self, *args, **kwargs):
            return None
        def execute(self, *args, **kwargs):
            return {"receipt_sha256": "r" * 64, "counts": {"updated": 1}}

    monkeypatch.setattr(final, "GenericPublisher", SuccessfulWriter)
    monkeypatch.setattr(final, "PlanExecutor", SuccessfulFrenchExecutor)
    monkeypatch.setattr(
        final, "check_or_record",
        lambda state, debate, work, ep, fp, **kwargs: visibility.check_or_record(
            state, debate, work, ep, fp, client=AnonymousFake(missing_en={"Should we agree?"}),
            manifest_sha256=kwargs.get("manifest_sha256", ""),
        ),
    )
    monkeypatch.setattr(
        final, "_install_release_copy",
        lambda *args: pytest.fail("Impossible d'installer le corpus sans attestation publique"),
    )

    with pytest.raises(final.FinalPublicationError, match="publication partielle") as exc:
        final.publish_final_release(
            tmp_path, "demo", "EDIT-20261121-001", release,
            confirm_preflight_sha256="p" * 64,
        )
    assert exc.value.remote_execution_started is True
    state_dir = tmp_path / ".state/final-publication/demo/EDIT-20261121-001"
    assert (state_dir / "english-publication-receipt.json").is_file()
    assert (state_dir / "french-publication-receipt.json").is_file()
    assert json.loads((state_dir / "public-visibility-report.json").read_text())["status"] == visibility.PARTIAL
    assert not (state_dir / "publication-receipt.json").exists()
