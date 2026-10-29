from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "wikidebia_publish.py"
CURRENT_VERSIONS = json.loads((SCRIPT.parents[1] / "VERSIONS.json").read_text(encoding="utf-8"))
spec = importlib.util.spec_from_file_location("wikidebia_publish", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = module
spec.loader.exec_module(module)

TEST_VALIDATOR_PYTHON = "/usr/bin/python3" if Path("/usr/bin/python3").is_file() else sys.executable


class FakeAdapter:
    def __init__(self, pages=None):
        self.pages = dict(pages or {})
        self.revisions = {}
        self.next_revision = 100
        self.language = None
        self.spam_matches = set()

    def open_language(self, language, expected_user): self.language = language
    def close_language(self): self.language = None
    def assert_identity(self, expected_user): return None
    def available_change_tags(self): return {"chatgpt", "translated-fr"}
    def spam_blacklist_matches(self, urls): return set(self.spam_matches)
    def read_page(self, title):
        row = self.pages.get((self.language, title))
        return (False, None, "") if row is None else (True, row[0], row[1])
    def read_revision(self, title, revision_id): return self.revisions.get(revision_id)
    def write_page(self, *, title, text, summary, tags, expected_user, create_only, base_revision_id):
        key = (self.language, title)
        if create_only and key in self.pages: raise RuntimeError("create collision")
        if not create_only and (key not in self.pages or self.pages[key][0] != base_revision_id): raise RuntimeError("revision collision")
        self.next_revision += 1
        revision = self.next_revision
        parent_id = 0 if create_only else int(base_revision_id or 0)
        self.pages[key] = (revision, text)
        self.revisions[revision] = {
            "revision_id": revision, "parent_id": parent_id, "user": expected_user,
            "text": text, "summary": summary, "tags": tags,
        }
        return revision


def test_pywikibot_adapter_forwards_managed_access_token(monkeypatch, tmp_path):
    monkeypatch.setenv("WIKIDEBIA_API_TOKEN", "managed-placeholder")
    adapter = module.PywikibotAdapter("wikidebates", {"fr": "fr"}, tmp_path)
    fake = SimpleNamespace(config=SimpleNamespace(extra_headers={"Existing": "kept"}))

    adapter._configure_access_header(fake)

    assert fake.config.extra_headers == {
        "Existing": "kept",
        "X-Wikidebia-Access": "managed-placeholder",
    }


def test_pywikibot_adapter_does_not_forward_token_to_another_family(monkeypatch, tmp_path):
    monkeypatch.setenv("WIKIDEBIA_API_TOKEN", "managed-placeholder")
    adapter = module.PywikibotAdapter("wikipedia", {"fr": "fr"}, tmp_path)
    fake = SimpleNamespace(config=SimpleNamespace(extra_headers={}))

    adapter._configure_access_header(fake)

    assert fake.config.extra_headers == {}


def test_pywikibot_adapter_loads_managed_bot_username(monkeypatch, tmp_path):
    monkeypatch.setenv("WIKIDEBIA_FR_BOT_USERNAME", "ChatGPT@Codex-FR")
    adapter = module.PywikibotAdapter("wikidebates", {"fr": "fr"}, tmp_path)
    fake = SimpleNamespace(config=SimpleNamespace(usernames={"wikidebates": {}}))

    adapter._configure_managed_username(fake, "fr", "ChatGPT")

    assert fake.config.usernames["wikidebates"]["fr"] == "ChatGPT"


def test_pywikibot_adapter_rejects_unexpected_managed_identity(monkeypatch, tmp_path):
    monkeypatch.setenv("WIKIDEBIA_FR_BOT_USERNAME", "AnotherUser@Codex-FR")
    adapter = module.PywikibotAdapter("wikidebates", {"fr": "fr"}, tmp_path)
    fake = SimpleNamespace(config=SimpleNamespace(usernames={"wikidebates": {}}))

    try:
        adapter._configure_managed_username(fake, "fr", "ChatGPT")
    except module.IdentityError as exc:
        assert "ne correspond pas" in str(exc)
    else:
        raise AssertionError("identité gérée inattendue acceptée")


def test_pywikibot_adapter_injects_managed_bot_password_in_memory(monkeypatch, tmp_path):
    monkeypatch.setenv("WIKIDEBIA_FR_BOT_USERNAME", "ChatGPT@Codex-FR")
    monkeypatch.setenv("WIKIDEBIA_FR_BOT_PASSWORD", "managed-placeholder")
    captured = {}

    class FakeLoginManager:
        def __init__(self, *args, **kwargs):
            captured["password"] = kwargs.get("password")
            captured["login_name"] = None

        def login(self, *args, **kwargs):
            captured["login_name"] = self.login_name
            return True

    login_module = SimpleNamespace(ClientLoginManager=FakeLoginManager)
    fake = SimpleNamespace(login=login_module)
    adapter = module.PywikibotAdapter("wikidebates", {"fr": "fr"}, tmp_path)
    adapter.site = SimpleNamespace(login=lambda: login_module.ClientLoginManager().login())

    adapter._login(fake, "fr", "ChatGPT")

    assert captured == {
        "password": "managed-placeholder",
        "login_name": "ChatGPT@Codex-FR",
    }
    assert login_module.ClientLoginManager is FakeLoginManager


def test_pywikibot_adapter_rejects_partial_managed_credentials(monkeypatch, tmp_path):
    monkeypatch.delenv("WIKIDEBIA_FR_BOT_USERNAME", raising=False)
    monkeypatch.setenv("WIKIDEBIA_FR_BOT_PASSWORD", "managed-placeholder")
    adapter = module.PywikibotAdapter("wikidebates", {"fr": "fr"}, tmp_path)
    adapter.site = SimpleNamespace(login=lambda: None)

    try:
        adapter._login(SimpleNamespace(), "fr", "ChatGPT")
    except module.PublicationError as exc:
        assert "WIKIDEBIA_FR_BOT_USERNAME" in str(exc)
    else:
        raise AssertionError("identifiants gérés partiels acceptés")


def test_pywikibot_adapter_reports_missing_managed_write_identity(monkeypatch, tmp_path):
    monkeypatch.delenv("WIKIDEBIA_EN_BOT_USERNAME", raising=False)
    monkeypatch.delenv("WIKIDEBIA_EN_BOT_PASSWORD", raising=False)
    adapter = module.PywikibotAdapter("wikidebates", {"en": "en"}, tmp_path)
    adapter.site = SimpleNamespace(login=lambda: (_ for _ in ()).throw(AssertionError("login must not start")))
    fake = SimpleNamespace(config=SimpleNamespace(usernames={"wikidebates": {}}))

    try:
        adapter._login(fake, "en", "ChatGPT")
    except module.PublicationError as exc:
        message = str(exc)
        assert "WIKIDEBIA_EN_BOT_USERNAME" in message
        assert "WIKIDEBIA_EN_BOT_PASSWORD" in message
    else:
        raise AssertionError("identité d’écriture absente non détectée")


def test_pywikibot_adapter_read_only_open_does_not_require_credentials(monkeypatch, tmp_path):
    (tmp_path / "user-config.py").write_text("# test\n", encoding="utf-8")
    calls = []

    class FakeSite:
        pass

    fake = SimpleNamespace(
        config=SimpleNamespace(extra_headers={}, family_files={}),
        Site=lambda **kwargs: calls.append(kwargs) or FakeSite(),
    )
    monkeypatch.setitem(sys.modules, "pywikibot", fake)
    monkeypatch.delenv("WIKIDEBIA_FR_BOT_USERNAME", raising=False)
    monkeypatch.delenv("WIKIDEBIA_FR_BOT_PASSWORD", raising=False)
    adapter = module.PywikibotAdapter(
        "wikidebates", {"fr": "fr"}, tmp_path, SCRIPT.parents[1] / "families" / "wikidebates_family.py"
    )

    adapter.open_language_read_only("fr")

    assert calls == [{"code": "fr", "fam": "wikidebates"}]
    assert isinstance(adapter.site, FakeSite)


def test_managed_environment_does_not_require_server_user_config(monkeypatch, tmp_path):
    monkeypatch.setenv("WIKIDEBIA_FR_BOT_USERNAME", "ChatGPT@Codex-FR")
    monkeypatch.setenv("WIKIDEBIA_FR_BOT_PASSWORD", "managed-placeholder")
    adapter = module.PywikibotAdapter("wikidebates", {"fr": "fr"}, tmp_path)

    adapter._prepare_environment("fr")

    assert "PYWIKIBOT_DIR" not in __import__("os").environ
    assert __import__("os").environ["PYWIKIBOT_NO_USER_CONFIG"] == "2"


def test_managed_read_only_environment_needs_no_server_config_or_credentials(monkeypatch, tmp_path):
    monkeypatch.delenv("WIKIDEBIA_FR_BOT_USERNAME", raising=False)
    monkeypatch.delenv("WIKIDEBIA_FR_BOT_PASSWORD", raising=False)
    adapter = module.PywikibotAdapter("wikidebates", {"fr": "fr"}, tmp_path)

    adapter._prepare_environment("fr", read_only=True)

    assert __import__("os").environ["PYWIKIBOT_NO_USER_CONFIG"] == "2"


def test_write_without_server_config_or_managed_credentials_is_rejected(monkeypatch, tmp_path):
    monkeypatch.delenv("WIKIDEBIA_FR_BOT_USERNAME", raising=False)
    monkeypatch.delenv("WIKIDEBIA_FR_BOT_PASSWORD", raising=False)
    adapter = module.PywikibotAdapter("wikidebates", {"fr": "fr"}, tmp_path)

    try:
        adapter._prepare_environment("fr")
    except module.PublicationError as exc:
        assert "WIKIDEBIA_FR_BOT_USERNAME/PASSWORD" in str(exc)
    else:
        raise AssertionError("configuration d'écriture absente acceptée")


def test_partial_managed_credentials_are_rejected_before_pywikibot_import(monkeypatch, tmp_path):
    monkeypatch.setenv("WIKIDEBIA_FR_BOT_USERNAME", "ChatGPT@Codex-FR")
    monkeypatch.delenv("WIKIDEBIA_FR_BOT_PASSWORD", raising=False)
    adapter = module.PywikibotAdapter("wikidebates", {"fr": "fr"}, tmp_path)

    try:
        adapter._prepare_environment("fr")
    except module.PublicationError as exc:
        assert "WIKIDEBIA_FR_BOT_PASSWORD" in str(exc)
    else:
        raise AssertionError("identifiants gérés partiels acceptés")


def write_fixture(tmp_path: Path, kind: str):
    corpus = tmp_path / "corpus" / "demo"
    (corpus / "output" / "fr").mkdir(parents=True)
    (corpus / "output" / "en").mkdir(parents=True)
    (corpus / "data").mkdir(parents=True)
    fr = "{{Argument\n|résumé=Nouveau résumé.\n|rubriques=Société\n}}\n"
    en = "{{Argument\n|summary=New summary.\n|sections=Society\n|creation-date=2020-01-01\n}}\n"
    (corpus / "output" / "fr" / "A1.wiki").write_text(fr, encoding="utf-8")
    (corpus / "output" / "en" / "A1.wiki").write_text(en, encoding="utf-8")
    fr_debate = "{{Débat\n|sujet=Démo\n|sujet-développé=la démonstration\n}}\n"
    en_debate = "{{Debate\n|topic=Demo\n|expanded-topic=the demonstration\n|creation-date=2020-01-01\n}}\n"
    (corpus / "output" / "fr" / "debate.wiki").write_text(fr_debate, encoding="utf-8")
    (corpus / "output" / "en" / "debate.wiki").write_text(en_debate, encoding="utf-8")
    manifest = {
      "debate_id":"demo",
      "normative_versions":{"validator":"0.4.73"},
      "core_files":{"registry":"data/registre_debat.json"},
      "pages":[
        {"language":"fr","page_id":"A1","page_type":"argument","canonical_title":"Titre FR","file_path":"output/fr/A1.wiki","sha256":module.sha_file(corpus / "output/fr/A1.wiki")},
        {"language":"en","page_id":"A1","page_type":"argument","canonical_title":"Title EN","file_path":"output/en/A1.wiki","sha256":module.sha_file(corpus / "output/en/A1.wiki")},
        {"language":"fr","page_id":"DEBATE","page_type":"debate","canonical_title":"Débat démo","file_path":"output/fr/debate.wiki","sha256":module.sha_file(corpus / "output/fr/debate.wiki")},
        {"language":"en","page_id":"DEBATE","page_type":"debate","canonical_title":"Demo debate","file_path":"output/en/debate.wiki","sha256":module.sha_file(corpus / "output/en/debate.wiki")}
      ]
    }
    registry = {
      "debate": {"id": "demo", "pages": {"en": {"canonical_title": "Demo debate", "title_status": "locked"}}},
      "graph": {"nodes": [{"id": "A1", "en": {"canonical_title": "Title EN", "title_status": "locked"}}]}
    }
    (corpus / "data" / "registre_debat.json").write_text(json.dumps(registry), encoding="utf-8")
    (corpus / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    validator = tmp_path / "validator"
    validator.mkdir()
    validator_script = validator / "validate.py"
    validator_script.write_text("import json; print(json.dumps({'validator_version':'0.4.73','result':'passed','summary':{'errors':0,'warnings':0}}))", encoding="utf-8")
    operation = {
      "id":"test",
      "kind":kind,
      "languages":["fr","en"],
      "page_types":["argument"],
      "source_path_field":"file_path",
      "create_missing": kind == "full_page",
      "update_existing": kind == "parameter_update",
      "edit_summaries":{"fr":"Résumé FR","en":"Summary EN"}
    }
    if kind == "parameter_update": operation["parameters"]={"fr":"résumé","en":"summary"}
    config = {
      "kit_version":"2.15.54","publication_profile":"legacy","project_root":str(tmp_path),"debate_id":"demo","corpus_root":"corpus/demo",
      "validator":{"command":[TEST_VALIDATOR_PYTHON,str(validator_script),"validate"],"required_version":"0.4.73","scopes":[],"max_warnings":0,"fingerprint_path":"validator"},
      "family":"wikidebates","family_file":str(Path(__file__)),"pywikibot_dir":str(tmp_path),
      "sites":{"fr":{"code":"fr","expected_user":"ChatGPT"},"en":{"code":"en","expected_user":"ChatGPT"}},
      "logs_dir":"logs","change_tags":["chatgpt"],"verification_attempts":1,"verification_delay_seconds":0,"write_delay_seconds":0,
      "manifest_requirements":{},"operation":operation
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return config, config_path, fr, en


def test_extract_and_replace_parameter():
    text = "{{Argument\r\n|summary=Old\r\n|sections=Society\r\n}}\r\n"
    assert module.extract_parameter(text, "summary") == "Old"
    assert module.replace_parameter(text, "summary", "New") == "{{Argument\r\n|summary=New\r\n|sections=Society\r\n}}\r\n"



def test_publish_parser_preserves_complete_multiline_summary_and_quotes_with_nested_templates():
    text = """{{Argument
|summary=First line of the summary.
Second line with {{Wikipedia link|article=Modal logic|displayed-text=modal logic}} while the nested template itself contains its parameter pipes.
Final line of the summary.
|quotes={{Quote
|quote=First quoted line.
Second quoted line with {{Wikipedia link|article=Argument|displayed-text=argument}} intact.
|authors=Example Author
|date=2026
}}
|sections=Philosophy
}}
"""
    summary = module.extract_parameter(text, "summary")
    quotes = module.extract_parameter(text, "quotes")
    assert summary == "First line of the summary.\nSecond line with {{Wikipedia link|article=Modal logic|displayed-text=modal logic}} while the nested template itself contains its parameter pipes.\nFinal line of the summary."
    assert quotes.startswith("{{Quote\n|quote=First quoted line.\nSecond quoted line")
    assert "{{Wikipedia link|article=Argument|displayed-text=argument}}" in quotes
    assert "|authors=Example Author" in quotes
    replaced = module.replace_parameter(text, "summary", summary + "\nAppended publication-check line.")
    assert module.extract_parameter(replaced, "summary").endswith("Appended publication-check line.")
    assert module.extract_parameter(replaced, "quotes") == quotes

def test_full_page_creation_is_dynamic(tmp_path):
    config, path, fr, en = write_fixture(tmp_path, "full_page")
    adapter = FakeAdapter()
    publisher = module.GenericPublisher(config, adapter, path)
    plan = publisher.build_plan()
    assert plan["plan_version"] == "wikidebia-publication-plan-1.0"
    assert plan["schema"] == "wikidebia-publication-plan-1.0"
    assert plan["schema_version"] == "1.0"
    assert plan["counts"]["fr"]["create"] == 1
    assert plan["counts"]["en"]["create"] == 1
    result = publisher.publish(plan=plan, confirmation=plan["plan_sha256"])
    assert result == {"created":2,"updated":0,"skipped":0}
    assert adapter.pages[("fr","Titre FR")][1] == fr
    assert adapter.pages[("en","Title EN")][1] == en
    checkpoint = json.loads((tmp_path / "logs/test-progress.json").read_text(encoding="utf-8"))
    assert checkpoint["status"] == "completed"
    assert checkpoint["checkpoint_sha256"] == module.sha_object({k: v for k, v in checkpoint.items() if k != "checkpoint_sha256"})


def test_publication_progress_checkpoint_survives_failure_and_resume(tmp_path):
    config, path, _fr, _en = write_fixture(tmp_path, "full_page")
    adapter = FakeAdapter()
    publisher = module.GenericPublisher(config, adapter, path)
    plan = publisher.build_plan()
    original_write = adapter.write_page

    def interrupted_write(**kwargs):
        if adapter.language == "en":
            raise RuntimeError("simulated interruption")
        return original_write(**kwargs)

    adapter.write_page = interrupted_write
    try:
        publisher.publish(plan=plan, confirmation=plan["plan_sha256"])
    except RuntimeError:
        pass
    else:
        raise AssertionError("interruption simulée non propagée")
    progress_path = tmp_path / "logs/test-progress.json"
    failed = json.loads(progress_path.read_text(encoding="utf-8"))
    assert failed["status"] == "failed"
    assert failed["failed_action"]["language"] == "en"
    assert failed["completed"] == [{"language": "fr", "page_id": "A1", "result": "created"}]

    adapter.write_page = original_write
    publisher.publish(plan=plan, confirmation=plan["plan_sha256"])
    completed = json.loads(progress_path.read_text(encoding="utf-8"))
    assert completed["status"] == "completed"
    assert {row["language"]: row["result"] for row in completed["completed"]} == {"fr": "created", "en": "created"}


def test_plan_blocks_spam_blacklist_before_any_remote_write(tmp_path):
    config, path, _fr, _en = write_fixture(tmp_path, "full_page")
    source = tmp_path / "corpus/demo/output/en/A1.wiki"
    source.write_text(source.read_text(encoding="utf-8") + "https://archive.is/example\n", encoding="utf-8")
    manifest_path = tmp_path / "corpus/demo/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    next(row for row in manifest["pages"] if row["language"] == "en" and row["page_id"] == "A1")["sha256"] = module.sha_file(source)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    adapter = FakeAdapter()
    adapter.spam_matches = {"archive.is"}

    try:
        module.GenericPublisher(config, adapter, path).build_plan()
    except module.PublicationError as exc:
        assert "archive.is" in str(exc)
        assert "A1" in str(exc)
    else:
        raise AssertionError("URL anti-spam acceptée dans le plan")
    assert adapter.pages == {}


def test_parameter_update_preserves_other_content(tmp_path):
    config, path, fr, en = write_fixture(tmp_path, "parameter_update")
    old_fr = "{{Argument\n|résumé=Ancien.\n|rubriques=Société\n}}\n"
    old_en = "{{Argument\n|summary=Old.\n|sections=Society\n}}\n"
    adapter = FakeAdapter({("fr","Titre FR"):(10,old_fr),("en","Title EN"):(20,old_en)})
    publisher = module.GenericPublisher(config, adapter, path)
    plan = publisher.build_plan()
    assert plan["counts"]["fr"]["update"] == 1
    result = publisher.publish(plan=plan, confirmation=plan["plan_sha256"])
    assert result["updated"] == 2
    assert "|résumé=Nouveau résumé." in adapter.pages[("fr","Titre FR")][1]
    assert "|rubriques=Société" in adapter.pages[("fr","Titre FR")][1]
    assert "|summary=New summary." in adapter.pages[("en","Title EN")][1]


def test_existing_full_page_collision_blocks(tmp_path):
    config, path, fr, en = write_fixture(tmp_path, "full_page")
    adapter = FakeAdapter({("fr","Titre FR"):(1,"différent"),("en","Title EN"):(2,en)})
    publisher = module.GenericPublisher(config, adapter, path)
    plan = publisher.build_plan()
    assert plan["counts"]["fr"]["block"] == 1
    assert plan["blockers"]


def test_parameter_update_can_insert_missing_parameter(tmp_path):
    config, path, fr, en = write_fixture(tmp_path, "parameter_update")
    config["operation"]["languages"] = ["fr"]
    config["operation"]["parameters"] = {"fr": "interlangue"}
    config["operation"]["insert_missing_parameter"] = True

    corpus = tmp_path / "corpus" / "demo"
    local = "{{Argument\n|résumé=Nouveau résumé.\n|rubriques=Société\n|interlangue=English title\n}}\n"
    source = corpus / "output" / "fr" / "A1.wiki"
    source.write_text(local, encoding="utf-8")

    manifest_path = corpus / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["pages"] = [row for row in manifest["pages"] if row["language"] == "fr"]
    manifest["pages"][0]["sha256"] = module.sha_file(source)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    path.write_text(json.dumps(config), encoding="utf-8")
    old_fr = "{{Argument\n|résumé=Ancien.\n|rubriques=Société\n}}\n"
    adapter = FakeAdapter({("fr", "Titre FR"): (10, old_fr)})
    publisher = module.GenericPublisher(config, adapter, path)
    plan = publisher.build_plan()

    assert plan["counts"]["fr"]["update"] == 1
    assert not plan["blockers"]

    result = publisher.publish(
        plan=plan,
        confirmation=plan["plan_sha256"],
        language="fr",
    )
    assert result["updated"] == 1
    written = adapter.pages[("fr", "Titre FR")][1]
    assert "|interlangue=English title" in written
    assert "|résumé=Ancien." in written
    assert "|rubriques=Société" in written



def make_direct_profile(config, path, tmp_path):
    config["publication_profile"] = module.DIRECT_INTERLANGUAGE_PROFILE
    config["validator"]["scopes"] = sorted(module.REQUIRED_DIRECT_SCOPES)
    config["operation"]["page_types"] = []
    corpus = tmp_path / "corpus" / "demo"
    manifest_path = corpus / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["consolidated_norm"] = "1.2.20"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    fr_debate = corpus / "output" / "fr" / "debate.wiki"
    fr_debate.write_text(
        "{{Débat\n|sujet=Démo\n|sujet-développé=la démonstration\n|articles-Wikipédia={{Article Wikipédia\n|page=Démonstration\n}}\n|interlangue={{Lien interlangue\n|langue=en\n|page=Demo debate\n}}\n}}\n",
        encoding="utf-8",
    )
    en_debate = corpus / "output" / "en" / "debate.wiki"
    en_debate.write_text(
        "{{Debate\n|topic=Demo\n|expanded-topic=the demonstration\n|wikipedia-articles={{Wikipedia article\n|page=Demonstration\n}}\n}}\n",
        encoding="utf-8",
    )
    update_hash(manifest_path, "fr", "DEBATE", fr_debate)
    update_hash(manifest_path, "en", "DEBATE", en_debate)
    path.write_text(json.dumps(config), encoding="utf-8")
    return corpus, manifest_path


def update_hash(manifest_path, language, page_id, source):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for row in manifest["pages"]:
        if row["language"] == language and row["page_id"] == page_id:
            row["sha256"] = module.sha_file(source)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def test_direct_profile_accepts_locked_future_english_target(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    corpus, manifest_path = make_direct_profile(config, path, tmp_path)
    fr_path = corpus / "output" / "fr" / "A1.wiki"
    fr_path.write_text("{{Argument\n|résumé=Texte.\n|interlangue={{Lien interlangue\n|langue=en\n|page=Title EN\n}}\n|rubriques=Société\n}}\n", encoding="utf-8")
    update_hash(manifest_path, "fr", "A1", fr_path)
    publisher = module.GenericPublisher(config, FakeAdapter(), path)
    plan = publisher.build_plan()
    assert plan["publication_profile"] == module.DIRECT_INTERLANGUAGE_PROFILE
    assert plan["counts"]["fr"]["create"] == 2


def test_direct_profile_rejects_debate_interlangue_model(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    corpus, manifest_path = make_direct_profile(config, path, tmp_path)
    fr_path = corpus / "output" / "fr" / "A1.wiki"
    fr_path.write_text("{{Argument\n|résumé=Texte.\n|interlangue={{Interlangue\n|langue=en\n|page=Title EN\n}}\n|rubriques=Société\n}}\n", encoding="utf-8")
    update_hash(manifest_path, "fr", "A1", fr_path)
    try:
        module.GenericPublisher(config, FakeAdapter(), path).build_plan()
    except module.PublicationError as exc:
        assert "Lien interlangue" in str(exc)
    else:
        raise AssertionError("ancienne forme interlangue acceptée")


def test_direct_profile_rejects_references_tag(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    corpus, manifest_path = make_direct_profile(config, path, tmp_path)
    fr_path = corpus / "output" / "fr" / "A1.wiki"
    fr_path.write_text("{{Argument\n|résumé=Texte.<references />\n|interlangue={{Lien interlangue\n|langue=en\n|page=Title EN\n}}\n|rubriques=Société\n}}\n", encoding="utf-8")
    update_hash(manifest_path, "fr", "A1", fr_path)
    try:
        module.GenericPublisher(config, FakeAdapter(), path).build_plan()
    except module.PublicationError as exc:
        assert "references" in str(exc)
    else:
        raise AssertionError("balise references acceptée")


def test_direct_profile_rejects_old_english_debate_shape(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    corpus, manifest_path = make_direct_profile(config, path, tmp_path)
    fr_source = corpus / "output" / "fr" / "A1.wiki"
    fr_source.write_text("{{Argument\n|résumé=Texte.\n|interlangue={{Lien interlangue\n|langue=en\n|page=Title EN\n}}\n|rubriques=Société\n}}\n", encoding="utf-8")
    update_hash(manifest_path, "fr", "A1", fr_source)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    en = next(row for row in manifest["pages"] if row["language"] == "en" and row["page_type"] == "debate")
    source = corpus / "output" / "en" / "debate.wiki"
    source.write_text("{{Debate\n|type=Is\n|topic=should measure X be adopted?\n}}\n", encoding="utf-8")
    en["sha256"] = module.sha_file(source)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    try:
        module.GenericPublisher(config, FakeAdapter(), path).build_plan()
    except module.PublicationError as exc:
        assert "|type=" in str(exc)
    else:
        raise AssertionError("ancienne structure Debate acceptée")


def test_direct_profile_allows_interlanguage_parameter_update_after_translation_is_ready(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "parameter_update")
    config["publication_profile"] = module.DIRECT_INTERLANGUAGE_PROFILE
    config["validator"]["scopes"] = sorted(module.REQUIRED_DIRECT_SCOPES)
    config["operation"]["parameters"] = {"fr":"interlangue","en":"summary"}
    path.write_text(json.dumps(config), encoding="utf-8")
    module.GenericPublisher(config, FakeAdapter(), path)


def test_direct_profile_blocks_separate_interlanguage_update_while_translation_is_deferred(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "parameter_update")
    config["publication_profile"] = module.DIRECT_INTERLANGUAGE_PROFILE
    config["validator"]["scopes"] = sorted(module.REQUIRED_DIRECT_SCOPES)
    config["operation"]["languages"] = ["fr"]
    config["operation"]["parameters"] = {"fr":"interlangue"}
    corpus = tmp_path / "corpus" / "demo"
    manifest_path = corpus / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["translation_status"] = {"en": "deferred"}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    path.write_text(json.dumps(config), encoding="utf-8")
    try:
        module.GenericPublisher(config, FakeAdapter(), path)
    except module.PublicationError as exc:
        assert "interlangue" in str(exc) and "deferred" in str(exc)
    else:
        raise AssertionError("mise à jour interlangue séparée acceptée pendant deferred")


def test_direct_profile_rejects_parenthetical_em_dashes_in_french_summary(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    corpus, manifest_path = make_direct_profile(config, path, tmp_path)
    fr_path = corpus / "output" / "fr" / "A1.wiki"
    fr_path.write_text("{{Argument\n|résumé=Texte — précision incidente — suite.\n|interlangue={{Lien interlangue\n|langue=en\n|page=Title EN\n}}\n|rubriques=Société\n}}\n", encoding="utf-8")
    update_hash(manifest_path, "fr", "A1", fr_path)
    try:
        module.GenericPublisher(config, FakeAdapter(), path).build_plan()
    except module.PublicationError as exc:
        assert "parenthèses" in str(exc)
    else:
        raise AssertionError("tirets cadratins parenthétiques acceptés")


def test_direct_profile_allows_french_only_manifest_with_locked_registry_titles(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    corpus, manifest_path = make_direct_profile(config, path, tmp_path)
    config["operation"]["languages"] = ["fr"]
    config["operation"]["page_types"] = ["argument"]
    config["operation"]["language_order"] = ["fr"]
    config["operation"]["edit_summaries"] = {"fr": "Résumé FR"}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["pages"] = [row for row in manifest["pages"] if row["language"] == "fr"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    fr_path = corpus / "output" / "fr" / "A1.wiki"
    fr_path.write_text(
        "{{Argument\n|résumé=Texte.\n|interlangue={{Lien interlangue\n|langue=en\n|page=Title EN\n}}\n|rubriques=Société\n}}\n",
        encoding="utf-8",
    )
    update_hash(manifest_path, "fr", "A1", fr_path)
    path.write_text(json.dumps(config), encoding="utf-8")
    adapter = FakeAdapter()
    publisher = module.GenericPublisher(config, adapter, path)
    plan = publisher.build_plan()
    assert plan["counts"]["fr"]["create"] == 1
    assert not plan["blockers"]
    result = publisher.publish(plan=plan, confirmation=plan["plan_sha256"])
    assert result == {"created": 1, "updated": 0, "skipped": 0}
    assert ("fr", "Titre FR") in adapter.pages


def test_direct_profile_rejects_unlocked_registry_title_without_english_manifest(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    corpus, manifest_path = make_direct_profile(config, path, tmp_path)
    config["operation"]["languages"] = ["fr"]
    config["operation"]["page_types"] = ["argument"]
    config["operation"]["language_order"] = ["fr"]
    config["operation"]["edit_summaries"] = {"fr": "Résumé FR"}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["pages"] = [row for row in manifest["pages"] if row["language"] == "fr"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    registry_path = corpus / "data" / "registre_debat.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["graph"]["nodes"][0]["en"]["title_status"] = "draft"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    fr_path = corpus / "output" / "fr" / "A1.wiki"
    fr_path.write_text(
        "{{Argument\n|résumé=Texte.\n|interlangue={{Lien interlangue\n|langue=en\n|page=Title EN\n}}\n|rubriques=Société\n}}\n",
        encoding="utf-8",
    )
    update_hash(manifest_path, "fr", "A1", fr_path)
    path.write_text(json.dumps(config), encoding="utf-8")
    try:
        module.GenericPublisher(config, FakeAdapter(), path).build_plan()
    except module.PublicationError as exc:
        assert "non verrouillé" in str(exc)
    else:
        raise AssertionError("titre anglais non verrouillé accepté")


def _prepare_direct_plan(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    corpus, manifest_path = make_direct_profile(config, path, tmp_path)
    fr_path = corpus / "output" / "fr" / "A1.wiki"
    fr_path.write_text(
        "{{Argument\n|résumé=Texte.\n|interlangue={{Lien interlangue\n|langue=en\n|page=Title EN\n}}\n|rubriques=Société\n}}\n",
        encoding="utf-8",
    )
    update_hash(manifest_path, "fr", "A1", fr_path)
    adapter = FakeAdapter()
    publisher = module.GenericPublisher(config, adapter, path)
    return publisher, adapter, publisher.build_plan()


def test_direct_profile_publish_requires_debate_test_receipt(tmp_path):
    publisher, _, plan = _prepare_direct_plan(tmp_path)
    try:
        publisher.publish(plan=plan, confirmation=plan["plan_sha256"])
    except module.PublicationError as exc:
        assert "debate-test-receipt" in str(exc)
    else:
        raise AssertionError("publication directe acceptée sans reçu de test")


def test_canonical_debate_test_receipt_is_created_and_reverified(tmp_path):
    publisher, adapter, plan = _prepare_direct_plan(tmp_path)
    receipt = publisher.create_debate_test_receipt(
        plan=plan,
        confirmation=plan["plan_sha256"],
    )
    assert receipt["status"] == "passed"
    assert receipt["plan_sha256"] == plan["plan_sha256"]
    assert receipt["canonical_title"] == "Débat démo"
    assert receipt["page_type"] == "debate"
    result = publisher.publish(
        plan=plan,
        confirmation=plan["plan_sha256"],
        debate_test_receipt=receipt,
    )
    assert result == {"created": 3, "updated": 0, "skipped": 1}
    assert ("fr", "Débat démo") in adapter.pages
    assert not any("Utilisateur:" in title for _, title in adapter.pages)


def test_tampered_debate_test_receipt_is_rejected(tmp_path):
    publisher, _, plan = _prepare_direct_plan(tmp_path)
    receipt = publisher.create_debate_test_receipt(
        plan=plan,
        confirmation=plan["plan_sha256"],
    )
    receipt["page_id"] = "A9999"
    try:
        publisher.publish(
            plan=plan,
            confirmation=plan["plan_sha256"],
            debate_test_receipt=receipt,
        )
    except module.PublicationError as exc:
        assert "Empreinte" in str(exc)
    else:
        raise AssertionError("reçu altéré accepté")


def test_changed_remote_debate_test_revision_is_rejected(tmp_path):
    publisher, adapter, plan = _prepare_direct_plan(tmp_path)
    receipt = publisher.create_debate_test_receipt(
        plan=plan,
        confirmation=plan["plan_sha256"],
    )
    adapter.pages[("fr", receipt["canonical_title"])] = (999, "contenu modifié")
    try:
        publisher.publish(
            plan=plan,
            confirmation=plan["plan_sha256"],
            debate_test_receipt=receipt,
        )
    except module.RevisionConflict as exc:
        assert "page Débat" in str(exc)
    else:
        raise AssertionError("révision de test distante modifiée acceptée")


def test_debate_test_refuses_existing_canonical_debate(tmp_path):
    publisher, adapter, plan = _prepare_direct_plan(tmp_path)
    adapter.pages[("fr", "Débat démo")] = (42, "autre contenu")
    try:
        publisher.create_debate_test_receipt(
            plan=plan,
            confirmation=plan["plan_sha256"],
        )
    except module.CollisionError as exc:
        assert "existe déjà" in str(exc)
    else:
        raise AssertionError("page Débat canonique existante acceptée comme test")


def test_direct_plan_allows_argument_only_selection(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    corpus, manifest_path = make_direct_profile(config, path, tmp_path)
    config["operation"]["languages"] = ["fr"]
    config["operation"]["page_types"] = ["argument"]
    config["operation"]["language_order"] = ["fr"]
    config["operation"]["edit_summaries"] = {"fr": "Résumé FR"}
    fr_path = corpus / "output" / "fr" / "A1.wiki"
    fr_path.write_text(
        "{{Argument\n|résumé=Texte.\n|interlangue={{Lien interlangue\n|langue=en\n|page=Title EN\n}}\n|rubriques=Société\n}}\n",
        encoding="utf-8",
    )
    update_hash(manifest_path, "fr", "A1", fr_path)
    path.write_text(json.dumps(config), encoding="utf-8")
    plan = module.GenericPublisher(config, FakeAdapter(), path).build_plan()
    assert plan["counts"]["fr"]["create"] == 1
    assert all(action["page_type"] == "argument" for action in plan["actions"])


def test_rehashed_receipt_with_wrong_summary_is_rejected(tmp_path):
    publisher, _, plan = _prepare_direct_plan(tmp_path)
    receipt = publisher.create_debate_test_receipt(
        plan=plan,
        confirmation=plan["plan_sha256"],
    )
    receipt["summary"] = "Résumé falsifié"
    unsigned = dict(receipt)
    unsigned.pop("receipt_sha256")
    receipt["receipt_sha256"] = module.sha_object(unsigned)
    try:
        publisher.publish(
            plan=plan,
            confirmation=plan["plan_sha256"],
            debate_test_receipt=receipt,
        )
    except module.PublicationError as exc:
        assert "summary" in str(exc)
    else:
        raise AssertionError("reçu recalculé avec un mauvais résumé accepté")


def test_active_cli_has_no_user_test_mode():
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"user-test"' not in source
    assert "--user-test" not in source
    assert '"debate-test"' in source
    assert "--debate-test-receipt" in source


def test_generic_kit_contains_no_debate_specific_configs():
    root = SCRIPT.parents[1]
    assert not (root / "configs" / "legacy").exists()
    active_files = [
        root / "README.md",
        root / "GUIDE_PUBLICATION.md",
        root / "config.example.json",
        root / "configs" / "creation_bilingue_1.2.23.example.json",
        root / "scripts" / "wikidebia_publish.py",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8").casefold() for path in active_files)
    for token in (
        "parapsychologie_science",
        "reseaux_sociaux_adolescents",
        "transparent psi",
        "réseaux sociaux aux adolescents",
    ):
        assert token not in combined


def test_direct_profile_requires_editorial_scope_for_introduction_review(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    make_direct_profile(config, path, tmp_path)
    config["validator"]["scopes"] = [scope for scope in config["validator"]["scopes"] if scope != "editorial"]
    try:
        module.GenericPublisher(config, FakeAdapter(), path)
    except module.PublicationError as exc:
        assert "editorial" in str(exc)
    else:
        raise AssertionError("profil direct accepté sans portée editorial")


def _write_valid_direct_argument(corpus: Path, manifest_path: Path) -> None:
    source = corpus / "output" / "fr" / "A1.wiki"
    source.write_text(
        "{{Argument\n|résumé=Texte.\n|interlangue={{Lien interlangue\n|langue=en\n|page=Title EN\n}}\n|rubriques=Société\n}}\n",
        encoding="utf-8",
    )
    update_hash(manifest_path, "fr", "A1", source)


def test_direct_profile_rejects_unsorted_sections(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    corpus, manifest_path = make_direct_profile(config, path, tmp_path)
    _write_valid_direct_argument(corpus, manifest_path)
    source = corpus / "output" / "en" / "A1.wiki"
    source.write_text(
        "{{Argument\n|summary=Text.\n|sections=Science, Philosophy\n}}\n",
        encoding="utf-8",
    )
    update_hash(manifest_path, "en", "A1", source)
    try:
        module.GenericPublisher(config, FakeAdapter(), path).build_plan()
    except module.PublicationError as exc:
        assert "ordre alphabétique" in str(exc)
    else:
        raise AssertionError("sections non alphabétiques acceptées")


def test_direct_profile_rejects_lowercase_topic(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    corpus, manifest_path = make_direct_profile(config, path, tmp_path)
    _write_valid_direct_argument(corpus, manifest_path)
    source = corpus / "output" / "en" / "debate.wiki"
    source.write_text(
        "{{Debate\n|topic=parapsychology\n|expanded-topic=the scientific status of parapsychology\n|wikipedia-articles={{Wikipedia article\n|page=Parapsychology\n}}\n}}\n",
        encoding="utf-8",
    )
    update_hash(manifest_path, "en", "DEBATE", source)
    try:
        module.GenericPublisher(config, FakeAdapter(), path).build_plan()
    except module.PublicationError as exc:
        assert "commencer par une majuscule" in str(exc)
    else:
        raise AssertionError("topic en minuscule accepté")


def test_direct_profile_rejects_interrogative_complete_topic(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    corpus, manifest_path = make_direct_profile(config, path, tmp_path)
    _write_valid_direct_argument(corpus, manifest_path)
    source = corpus / "output" / "en" / "debate.wiki"
    source.write_text(
        "{{Debate\n|topic=Parapsychology\n|expanded-topic=whether parapsychology meets the criteria for scientific status\n|wikipedia-articles={{Wikipedia article\n|page=Parapsychology\n}}\n}}\n",
        encoding="utf-8",
    )
    update_hash(manifest_path, "en", "DEBATE", source)
    try:
        module.GenericPublisher(config, FakeAdapter(), path).build_plan()
    except module.PublicationError as exc:
        assert "forme non interrogative" in str(exc)
    else:
        raise AssertionError("expanded-topic interrogatif accepté")


def test_direct_profile_rejects_split_adjacent_templates(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    corpus, manifest_path = make_direct_profile(config, path, tmp_path)
    source = corpus / "output" / "fr" / "A1.wiki"
    source.write_text(
        "{{Argument\n|résumé=Texte.\n|références-bibliographiques={{Référence bibliographique\n"
        "|auteurs=A\n|ouvrage=O1\n|date=25 juin 2012\n}}\n{{Référence bibliographique\n"
        "|auteurs=B\n|ouvrage=O2\n|date=26 juin 2012\n}}\n"
        "|interlangue={{Lien interlangue\n|langue=en\n|page=Title EN\n}}\n|rubriques=Société\n}}\n",
        encoding="utf-8",
    )
    update_hash(manifest_path, "fr", "A1", source)
    try:
        module.GenericPublisher(config, FakeAdapter(), path).build_plan()
    except module.PublicationError as exc:
        assert "}}{{" in str(exc)
    else:
        raise AssertionError("jonction de modèles séparée par un saut de ligne acceptée")


def test_full_page_order_is_debate_then_arguments_in_both_languages(tmp_path):
    publisher, _, plan = _prepare_direct_plan(tmp_path)
    sequence = [(row["language"], row["page_type"]) for row in plan["actions"]]
    assert sequence == [
        ("fr", "debate"),
        ("fr", "argument"),
        ("en", "debate"),
        ("en", "argument"),
    ]


def test_equivalent_existing_french_debate_needs_no_test_receipt(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    corpus, manifest_path = make_direct_profile(config, path, tmp_path)
    _write_valid_direct_argument(corpus, manifest_path)
    fr_debate = (corpus / "output" / "fr" / "debate.wiki").read_text(encoding="utf-8")
    adapter = FakeAdapter({("fr", "Débat démo"): (42, fr_debate)})
    publisher = module.GenericPublisher(config, adapter, path)
    plan = publisher.build_plan()
    debate_action = next(row for row in plan["actions"] if row["language"] == "fr" and row["page_type"] == "debate")
    assert debate_action["operation"] == "skip"
    result = publisher.publish(plan=plan, confirmation=plan["plan_sha256"])
    assert result["skipped"] == 1
    assert result["created"] == 3


def test_historical_manifest_versions_do_not_block_current_validation(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    corpus = tmp_path / "corpus" / "demo"
    manifest_path = corpus / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["normative_versions"] = {
        "consolidated_norm": "1.2.10",
        "validator": "0.4.10",
        "kit": "2.1.10",
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    publisher = module.GenericPublisher(config, FakeAdapter(), path)
    plan = publisher.build_plan()
    assert not plan["blockers"]
    assert plan["required_validator_version"] == CURRENT_VERSIONS["validator"]


def test_explicit_custom_manifest_requirement_is_still_enforced(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    config["manifest_requirements"] = {"normative_versions.validator": "0.4.73"}
    path.write_text(json.dumps(config), encoding="utf-8")
    corpus = tmp_path / "corpus" / "demo"
    manifest_path = corpus / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["normative_versions"]["validator"] = "0.4.10"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    try:
        module.GenericPublisher(config, FakeAdapter(), path)
    except module.PublicationError as exc:
        assert "Exigence de manifeste divergente" in str(exc)
    else:
        raise AssertionError("exigence explicite ignorée")


def test_direct_profile_rejects_empty_wikipedia_articles(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    corpus, manifest_path = make_direct_profile(config, path, tmp_path)
    fr_debate = corpus / "output" / "fr" / "debate.wiki"
    text = fr_debate.read_text(encoding="utf-8")
    text = text.replace("|articles-Wikipédia={{Article Wikipédia\n|page=Démonstration\n}}\n", "|articles-Wikipédia=\n")
    fr_debate.write_text(text, encoding="utf-8")
    update_hash(manifest_path, "fr", "DEBATE", fr_debate)
    try:
        module.GenericPublisher(config, FakeAdapter(), path).build_plan()
    except module.PublicationError as exc:
        assert "articles-Wikipédia" in str(exc)
    else:
        raise AssertionError("paramètre Wikipédia vide accepté")


def test_direct_profile_rejects_related_debates(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    corpus, manifest_path = make_direct_profile(config, path, tmp_path)
    _write_valid_direct_argument(corpus, manifest_path)
    fr_debate = corpus / "output" / "fr" / "debate.wiki"
    text = fr_debate.read_text(encoding="utf-8").replace("|interlangue=", "|débats-connexes={{Débat connexe\n|page=Autre débat\n}}\n|interlangue=")
    fr_debate.write_text(text, encoding="utf-8")
    update_hash(manifest_path, "fr", "DEBATE", fr_debate)
    try:
        module.GenericPublisher(config, FakeAdapter(), path).build_plan()
    except module.PublicationError as exc:
        assert "débats-connexes" in str(exc)
    else:
        raise AssertionError("débats connexes acceptés")


def test_direct_profile_rejects_json_author_array(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    corpus, manifest_path = make_direct_profile(config, path, tmp_path)
    _write_valid_direct_argument(corpus, manifest_path)
    fr_debate = corpus / "output" / "fr" / "debate.wiki"
    text = fr_debate.read_text(encoding="utf-8").replace("|interlangue=", "|sitographie-ni-pour-ni-contre={{Référence sitographique\n|lien=https://example.test\n|auteurs=[\"L'Encyclopédie philosophique\"]\n|site=L'Encyclopédie philosophique\n}}\n|interlangue=")
    fr_debate.write_text(text, encoding="utf-8")
    update_hash(manifest_path, "fr", "DEBATE", fr_debate)
    try:
        module.GenericPublisher(config, FakeAdapter(), path).build_plan()
    except module.PublicationError as exc:
        assert "tableau JSON" in str(exc)
    else:
        raise AssertionError("tableau JSON auteurs accepté")


def _set_norm(manifest_path, norm):
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data.setdefault("normative_versions", {})["consolidated_norm"] = norm
    manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def _inject_author_value(tmp_path, value, norm="1.2.20"):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    corpus, manifest_path = make_direct_profile(config, path, tmp_path)
    _write_valid_direct_argument(corpus, manifest_path)
    _set_norm(manifest_path, norm)
    fr_debate = corpus / "output" / "fr" / "debate.wiki"
    text = fr_debate.read_text(encoding="utf-8").replace("|interlangue=", f"|sitographie-ni-pour-ni-contre={{{{Référence sitographique\n|lien=https://example.test\n|auteurs={value}\n|site=Exemple\n}}}}\n|interlangue=")
    fr_debate.write_text(text, encoding="utf-8")
    update_hash(manifest_path, "fr", "DEBATE", fr_debate)
    return config, path

def test_direct_profile_accepts_comma_author_separator(tmp_path):
    config, path = _inject_author_value(tmp_path, "Auteur A, Auteur B")
    module.GenericPublisher(config, FakeAdapter(), path).build_plan()

def test_direct_profile_rejects_semicolon_author_separator(tmp_path):
    config, path = _inject_author_value(tmp_path, "Auteur A ; Auteur B")
    try:
        module.GenericPublisher(config, FakeAdapter(), path).build_plan()
    except module.PublicationError as exc:
        assert "virgule" in str(exc)
    else:
        raise AssertionError("point-virgule accepté")

def test_direct_profile_rejects_bad_comma_spacing(tmp_path):
    config, path = _inject_author_value(tmp_path, "Auteur A,Auteur B")
    try:
        module.GenericPublisher(config, FakeAdapter(), path).build_plan()
    except module.PublicationError as exc:
        assert "virgule" in str(exc)
    else:
        raise AssertionError("virgule sans espace acceptée")

def test_direct_profile_rejects_fullwidth_comma(tmp_path):
    config, path = _inject_author_value(tmp_path, "Auteur A， Auteur B")
    try:
        module.GenericPublisher(config, FakeAdapter(), path).build_plan()
    except module.PublicationError as exc:
        assert "virgule" in str(exc)
    else:
        raise AssertionError("virgule pleine chasse acceptée")

def test_old_norm_metadata_does_not_disable_current_author_separator_rule(tmp_path):
    config, path = _inject_author_value(tmp_path, "Auteur A ; Auteur B", "1.2.17")
    try:
        module.GenericPublisher(config, FakeAdapter(), path).build_plan()
    except module.PublicationError as exc:
        assert "virgule" in str(exc)
    else:
        raise AssertionError("ancien séparateur d’auteurs accepté à cause du numéro de norme")


def test_direct_profile_rejects_empty_english_wikipedia_articles(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    corpus, manifest_path = make_direct_profile(config, path, tmp_path)
    _write_valid_direct_argument(corpus, manifest_path)
    en_debate = corpus / "output" / "en" / "debate.wiki"
    current = en_debate.read_text(encoding="utf-8")
    current = current.replace("|wikipedia-articles={{Wikipedia article\n|page=Demonstration\n}}\n", "|wikipedia-articles=\n")
    en_debate.write_text(current, encoding="utf-8")
    update_hash(manifest_path, "en", "DEBATE", en_debate)
    try:
        module.GenericPublisher(config, FakeAdapter(), path).build_plan()
    except module.PublicationError as exc:
        assert "wikipedia-articles" in str(exc)
    else:
        raise AssertionError("paramètre Wikipédia anglais vide accepté")


def test_direct_profile_rejects_json_author_array_in_english_reference(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    corpus, manifest_path = make_direct_profile(config, path, tmp_path)
    _write_valid_direct_argument(corpus, manifest_path)
    en_debate = corpus / "output" / "en" / "debate.wiki"
    current = en_debate.read_text(encoding="utf-8")
    body, closing = current.rsplit("\n}}\n", 1)
    current = body + "\n|webliography={{Web reference\n|link=https://example.test\n|authors=[\"Organisation A\", \"Person B\"]\n|site=Example\n}}\n}}\n" + closing
    en_debate.write_text(current, encoding="utf-8")
    update_hash(manifest_path, "en", "DEBATE", en_debate)
    try:
        module.GenericPublisher(config, FakeAdapter(), path).build_plan()
    except module.PublicationError as exc:
        assert "tableau JSON" in str(exc)
    else:
        raise AssertionError("tableau JSON authors anglais accepté")


def _make_deferred_direct_profile(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    config["publication_profile"] = module.DEFERRED_TRANSLATION_PROFILE
    config["validator"]["scopes"] = sorted(module.REQUIRED_DIRECT_SCOPES)
    config["operation"].update({"languages": ["fr"], "language_order": ["fr"], "page_types": ["argument"], "edit_summaries": {"fr": "Résumé FR"}})
    corpus = tmp_path / "corpus" / "demo"
    manifest_path = corpus / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.setdefault("normative_versions", {})["consolidated_norm"] = "1.2.34"
    manifest["translation_status"] = {"en": "deferred"}
    manifest["pages"] = [row for row in manifest["pages"] if row["language"] == "fr"]
    source = corpus / "output" / "fr" / "A1.wiki"
    source.write_text("{{Argument\n|résumé=Texte français.\n|rubriques=Société\n}}\n", encoding="utf-8")
    for row in manifest["pages"]:
        if row["page_id"] == "A1":
            row["sha256"] = module.sha_file(source)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    path.write_text(json.dumps(config), encoding="utf-8")
    return config, path, corpus, manifest_path


def test_direct_profile_1234_accepts_french_deferred_without_interlanguage(tmp_path):
    config, path, _, _ = _make_deferred_direct_profile(tmp_path)
    plan = module.GenericPublisher(config, FakeAdapter(), path).build_plan()
    assert plan["counts"]["fr"]["create"] == 1
    assert not plan["blockers"]


def test_direct_profile_1234_blocks_english_scope_while_deferred(tmp_path):
    config, path, _, _ = _make_deferred_direct_profile(tmp_path)
    config["operation"]["languages"] = ["fr", "en"]
    config["operation"]["edit_summaries"]["en"] = "English summary"
    path.write_text(json.dumps(config), encoding="utf-8")
    try:
        module.GenericPublisher(config, FakeAdapter(), path)
    except module.PublicationError as exc:
        assert "deferred" in str(exc)
    else:
        raise AssertionError("portée anglaise acceptée pendant la traduction différée")


def test_direct_profile_1234_rejects_existing_link_without_locked_title(tmp_path):
    config, path, corpus, manifest_path = _make_deferred_direct_profile(tmp_path)
    registry_path = corpus / "data" / "registre_debat.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["graph"]["nodes"][0]["en"] = {"canonical_title": None, "title_status": "unassigned"}
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    source = corpus / "output" / "fr" / "A1.wiki"
    source.write_text("{{Argument\n|résumé=Texte.\n|interlangue={{Lien interlangue\n|langue=en\n|page=Invented\n}}\n|rubriques=Société\n}}\n", encoding="utf-8")
    update_hash(manifest_path, "fr", "A1", source)
    try:
        module.GenericPublisher(config, FakeAdapter(), path).build_plan()
    except module.PublicationError as exc:
        assert "non verrouillé" in str(exc)
    else:
        raise AssertionError("lien interlangue fictif accepté")


def test_direct_profile_1234_allows_later_interlanguage_parameter_update_when_ready(tmp_path):
    config, path, _, manifest_path = _make_deferred_direct_profile(tmp_path)
    config["operation"].update({
        "kind": "parameter_update",
        "languages": ["fr"],
        "parameters": {"fr": "interlangue"},
        "create_missing": False,
        "update_existing": True,
        "insert_missing_parameter": True,
    })
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["translation_status"]["en"] = "ready"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    path.write_text(json.dumps(config), encoding="utf-8")
    module.GenericPublisher(config, FakeAdapter(), path)

def test_ready_english_translation_uses_page_specific_french_source_summary(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    corpus, manifest_path = make_direct_profile(config, path, tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["translation_status"] = {"en": "ready"}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    config["operation"]["languages"] = ["en"]
    config["operation"]["page_types"] = ["argument"]
    path.write_text(json.dumps(config), encoding="utf-8")
    adapter = FakeAdapter()
    publisher = module.GenericPublisher(config, adapter, path)
    plan = publisher.build_plan()
    assert len(plan["actions"]) == 1
    action = plan["actions"][0]
    assert action["edit_summary"] == "Translation of the French page: [[:fr:Titre FR|Titre FR]]"
    assert action["change_tags"] == ["chatgpt", "translated-fr"]
    result = publisher.publish(plan=plan, confirmation=plan["plan_sha256"])
    assert result == {"created": 1, "updated": 0, "skipped": 0}
    revision = max(adapter.revisions)
    assert adapter.revisions[revision]["summary"] == action["edit_summary"]
    assert adapter.revisions[revision]["tags"] == ["chatgpt", "translated-fr"]
    written = adapter.revisions[revision]["text"]
    assert "|initialization=" not in written
    assert f"|creation-date={publisher.publication_date}" in written
    assert "|creation-date=2020-01-01" not in written
    assert action["publication_creation_date"] == publisher.publication_date
    assert plan["publication_date"] == publisher.publication_date
    assert plan["publication_timezone"] == "Europe/Paris"


def test_ready_english_translation_rejects_initialization_from_french_parent(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    corpus, manifest_path = make_direct_profile(config, path, tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["translation_status"] = {"en": "ready"}
    for row in manifest["pages"]:
        if row["language"] == "en" and row["page_id"] == "A1":
            row["page_origin"] = "new"
    en_source = corpus / "output" / "en" / "A1.wiki"
    en_source.write_text(
        "{{Argument\n|initialization=Objection@12345\n|summary=New summary.\n|sections=Society\n|creation-date=2020-01-01\n}}\n",
        encoding="utf-8",
    )
    for row in manifest["pages"]:
        if row["language"] == "en" and row["page_id"] == "A1":
            row["sha256"] = module.sha_file(en_source)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    config["operation"]["languages"] = ["en"]
    config["operation"]["page_types"] = ["argument"]
    path.write_text(json.dumps(config), encoding="utf-8")
    try:
        module.GenericPublisher(config, FakeAdapter(), path).build_plan()
    except module.PublicationError as exc:
        assert "initialization" in str(exc)
    else:
        raise AssertionError("initialization carried from French parent was accepted")


def test_ready_english_translation_resume_keeps_original_remote_creation_date(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    corpus, manifest_path = make_direct_profile(config, path, tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["translation_status"] = {"en": "ready"}
    for row in manifest["pages"]:
        if row["language"] == "en" and row["page_id"] == "A1":
            row["page_origin"] = "new"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    config["operation"]["languages"] = ["en"]
    config["operation"]["page_types"] = ["argument"]
    path.write_text(json.dumps(config), encoding="utf-8")
    adapter = FakeAdapter()
    adapter.language = "en"
    remote = "{{Argument\n|summary=New summary.\n|sections=Society\n|creation-date=2026-08-09\n}}\n"
    adapter.pages[("en", "Title EN")] = (77, remote)
    expected_summary = "Translation of the French page: [[:fr:Titre FR|Titre FR]]"
    adapter.revisions[77] = {"revision_id": 77, "parent_id": 0, "user": "ChatGPT", "text": remote, "summary": expected_summary, "tags": ["chatgpt", "translated-fr"]}
    adapter.language = None
    publisher = module.GenericPublisher(config, adapter, path)
    plan = publisher.build_plan()
    assert plan["counts"]["en"]["skip"] == 1
    action = plan["actions"][0]
    assert action["publication_creation_date"] == "2026-08-09"
    assert action["operation"] == "skip"


def test_tampered_page_specific_translation_summary_is_rejected(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    _, manifest_path = make_direct_profile(config, path, tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["translation_status"] = {"en": "ready"}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    config["operation"]["languages"] = ["en"]
    config["operation"]["page_types"] = ["argument"]
    path.write_text(json.dumps(config), encoding="utf-8")
    publisher = module.GenericPublisher(config, FakeAdapter(), path)
    plan = publisher.build_plan()
    plan["actions"][0]["edit_summary"] = "Translation of another page"
    plan["plan_sha256"] = module.sha_object({k: v for k, v in plan.items() if k != "plan_sha256"})
    try:
        publisher.publish(plan=plan, confirmation=plan["plan_sha256"])
    except module.PublicationError as exc:
        assert "Résumé individualisé divergent" in str(exc)
    else:
        raise AssertionError("tampered per-page translation summary accepted")


def test_ready_english_translation_debate_uses_publication_date(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    corpus, manifest_path = make_direct_profile(config, path, tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["translation_status"] = {"en": "ready"}
    for row in manifest["pages"]:
        if row["language"] == "en" and row["page_id"] == "DEBATE":
            row["page_origin"] = "new"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    source = corpus / "output" / "en" / "debate.wiki"
    source.write_text(
        "{{Debate\n"
        "|topic=Demo\n"
        "|expanded-topic=the demonstration\n"
        "|wikipedia-articles={{Wikipedia article\n|page=Demonstration\n}}\n"
        "|creation-date=2020-01-01\n"
        "}}\n",
        encoding="utf-8",
    )
    update_hash(manifest_path, "en", "DEBATE", source)
    config["operation"]["languages"] = ["en"]
    config["operation"]["page_types"] = ["debate"]
    path.write_text(json.dumps(config), encoding="utf-8")
    adapter = FakeAdapter()
    publisher = module.GenericPublisher(config, adapter, path)
    plan = publisher.build_plan()
    action = plan["actions"][0]
    assert action["publication_creation_date"] == publisher.publication_date
    result = publisher.publish(plan=plan, confirmation=plan["plan_sha256"])
    assert result == {"created": 1, "updated": 0, "skipped": 0}
    written = adapter.pages[("en", "Demo debate")][1]
    assert f"|creation-date={publisher.publication_date}" in written
    assert "|creation-date=2020-01-01" not in written


def test_english_creation_rechecks_date_immediately_before_each_write(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    _, manifest_path = make_direct_profile(config, path, tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["translation_status"] = {"en": "ready"}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    config["operation"]["languages"] = ["en"]
    config["operation"]["page_types"] = ["argument"]
    path.write_text(json.dumps(config), encoding="utf-8")
    publisher = module.GenericPublisher(config, FakeAdapter(), path)
    plan = publisher.build_plan()
    planned = plan["publication_date"]
    next_day = "2099-12-31" if planned != "2099-12-31" else "2099-12-30"
    dates = iter([planned, next_day])
    publisher._current_publication_date = lambda: next(dates)
    try:
        publisher.publish(plan=plan, confirmation=plan["plan_sha256"])
    except module.PublicationError as exc:
        assert "jour de publication" in str(exc)
        assert "Title EN" in str(exc)
    else:
        raise AssertionError("une création anglaise a traversé un changement de jour sans blocage")


def test_non_english_creation_is_not_invalidated_by_publication_day_change(tmp_path):
    config, path, _, _ = write_fixture(tmp_path, "full_page")
    config["operation"]["languages"] = ["fr"]
    config["operation"]["page_types"] = ["argument"]
    path.write_text(json.dumps(config), encoding="utf-8")
    adapter = FakeAdapter()
    publisher = module.GenericPublisher(config, adapter, path)
    plan = publisher.build_plan()
    publisher._current_publication_date = lambda: "2099-12-31"
    result = publisher.publish(plan=plan, confirmation=plan["plan_sha256"])
    assert result == {"created": 1, "updated": 0, "skipped": 0}

def test_direct_profile_preserves_only_attested_french_related_debates(tmp_path):
    import pytest
    config,path,_,_=write_fixture(tmp_path,'full_page')
    corpus,manifest_path=make_direct_profile(config,path,tmp_path)
    text=(corpus/'output/fr/debate.wiki').read_text()
    value='{{Débat connexe\n|page=Autre débat\n}}'
    text=text.replace('|interlangue=','|débats-connexes='+value+'\n|interlangue=')
    publisher=module.GenericPublisher(config,FakeAdapter(),path)
    row={'page_id':'DEBATE','page_type':'debate','language':'fr','page_origin':'preexisting',
         'preserved_parameters':{'débats-connexes':{'present':True,'value':value}}}
    publisher._validate_norm_120_page(row,text)
    with pytest.raises(module.PublicationError):publisher._validate_norm_120_page(row,text.replace('Autre débat','Un ajout'))
    row['page_origin']='new'
    with pytest.raises(module.PublicationError):publisher._validate_norm_120_page(row,text)
