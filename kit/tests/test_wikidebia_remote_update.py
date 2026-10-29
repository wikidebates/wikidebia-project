from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "wikidebia_update.py"
spec = importlib.util.spec_from_file_location("wikidebia_update_test", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = module
spec.loader.exec_module(module)

TEST_VALIDATOR_PYTHON = "/usr/bin/python3" if Path("/usr/bin/python3").is_file() else sys.executable

MARKER = "|avertissements-argument=Argument généré par IA\n"


def test_relation_rendering_guard_rejects_empty_parameters():
    with pytest.raises(module.UpdateError, match="Paramètre relationnel vide interdit"):
        module.assert_relation_rendering_safe(
            None,
            "{{Argument\n|résumé=Texte.\n|justifications=\n}}\n",
            "fr",
            "argument",
        )


def test_relation_rendering_guard_allows_removing_legacy_empty_parameter():
    module.assert_relation_rendering_safe(
        "{{Argument\n|résumé=Texte.\n|objections=\n}}\n",
        "{{Argument\n|résumé=Texte.\n}}\n",
        "fr",
        "argument",
    )


def test_relation_rendering_guard_rejects_silent_displayed_title_rewrite():
    old = (
        "{{Argument\n|objections={{Objection|page=Ancienne cible"
        "|titre-affiché=Libellé historique}}\n}}\n"
    )
    rewritten = (
        "{{Argument\n|objections={{Objection|page=Nouvelle cible"
        "|titre-affiché=Titre global}}\n}}\n"
    )
    with pytest.raises(module.UpdateError, match="Modification silencieuse de titre-affiché"):
        module.assert_relation_rendering_safe(old, rewritten, "fr", "argument")


def test_relation_rendering_guard_allows_target_change_with_preserved_label():
    old = (
        "{{Argument\n|objections={{Objection|page=Ancienne cible"
        "|titre-affiché=Libellé historique}}\n}}\n"
    )
    moved = (
        "{{Argument\n|objections={{Objection|page=Nouvelle cible"
        "|titre-affiché=Libellé historique}}\n}}\n"
    )
    module.assert_relation_rendering_safe(old, moved, "fr", "argument")


class FakeAdapter:
    def __init__(self, pages=None, rights=None):
        self.pages = dict(pages or {})
        self.rights = set(rights or {"edit", "createpage", "move", "delete", "browsearchive"})
        self.language = None
        self.next_revision = 100
        self.events = []
        self.fail_after_writes = None
        self.write_count = 0
        self.revisions = {}

    def open_language(self, language, expected_user):
        assert self.language is None
        self.language = language
        self.events.append(("open", language))

    def close_language(self):
        self.events.append(("close", self.language))
        self.language = None

    def assert_identity(self, expected_user):
        return None

    def user_rights(self):
        return set(self.rights)

    def read_page(self, title):
        row = self.pages.get((self.language, title))
        return (False, None, "") if row is None else (True, row[0], row[1])

    def write_page(self, *, title, text, summary, tags, expected_user, create_only, base_revision_id):
        if self.fail_after_writes is not None and self.write_count >= self.fail_after_writes:
            raise RuntimeError("interruption")
        key = (self.language, title)
        if create_only and key in self.pages:
            raise RuntimeError("create collision")
        if not create_only and (key not in self.pages or self.pages[key][0] != base_revision_id):
            raise RuntimeError("revision collision")
        self.next_revision += 1
        self.write_count += 1
        self.pages[key] = (self.next_revision, text)
        self.revisions[(self.language, title, self.next_revision)] = {
            "revision_id": self.next_revision, "text": text, "summary": summary, "tags": list(tags)
        }
        self.events.append(("write", self.language, title, summary))
        return self.next_revision

    def read_revision(self, title, revision_id):
        return self.revisions.get((self.language, title, revision_id))

    def move_page(self, *, old_title, new_title, reason, expected_user, leave_redirect):
        old = (self.language, old_title)
        new = (self.language, new_title)
        rev, text = self.pages.pop(old)
        self.next_revision += 1
        self.pages[new] = (self.next_revision, text)
        if leave_redirect:
            self.next_revision += 1
            self.pages[old] = (self.next_revision, module.redirect_text(self.language, new_title))
        self.events.append(("move", self.language, old_title, new_title))
        return self.next_revision

    def delete_page(self, *, title, reason, expected_user):
        self.pages.pop((self.language, title), None)
        self.events.append(("delete", self.language, title))

    def backlinks(self, title):
        return ["Page entrante"]


def argument(text: str) -> str:
    return "{{Argument\n" + MARKER + f"|résumé={text}\n|rubriques=Société\n}}}}\n"


def make_fixture(tmp_path: Path, *, languages=("fr",), old_pages=None, new_pages=None, migrations=None, remote_adoptions=None, authorize_summary_changes=True):
    root = tmp_path
    corpus = root / "corpus" / "demo"
    corpus.mkdir(parents=True)
    manifest_pages = []
    for language in languages:
        (corpus / "output" / language).mkdir(parents=True)
    for row in new_pages or []:
        language, page_id, title, text = row[:4]
        page_type = row[4] if len(row) > 4 else "argument"
        path = corpus / "output" / language / f"{page_id}.wiki"
        path.write_text(text, encoding="utf-8")
        manifest_pages.append({
            "language": language,
            "page_id": page_id,
            "page_type": page_type,
            "canonical_title": title,
            "file_path": path.relative_to(corpus).as_posix(),
            "sha256": module.sha_file(path),
        })
        if authorize_summary_changes:
            # Existing update tests deliberately change their argument prose.
            # Scope regressions below explicitly omit this permission.
            manifest_pages[-1]["summary_change_authorization"] = {
                "decision": "explicit_user_request", "action": "edit",
                "instruction": "Réécris le résumé de cet argument pour ce scénario de test.",
            }
    manifest = {"debate_id": "demo", "release_version": "2026-07-31", "pages": manifest_pages}
    if remote_adoptions:
        manifest["editorial_controls"] = {
            "manual_remote_adoption_revision": "1.2.48",
            "manual_remote_adoption_path": "data/manual_remote_adoptions.json",
        }
    (corpus / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    if migrations:
        (corpus / "data").mkdir(exist_ok=True)
        (corpus / "data" / "remote_migrations.json").write_text(json.dumps({"version":"1.0","debate_id":"demo","entries":migrations}), encoding="utf-8")
    if remote_adoptions:
        (corpus / "data").mkdir(exist_ok=True)
        (corpus / "data" / "manual_remote_adoptions.json").write_text(json.dumps({"version":"1.0","debate_id":"demo","decision":"Décision explicite du propriétaire", "entries":remote_adoptions}), encoding="utf-8")
    for language in languages:
        pages = []
        for row in old_pages or []:
            if row[0] != language:
                continue
            _, page_id, title, text = row[:4]
            page_type = row[4] if len(row) > 4 else "argument"
            revision = row[5] if len(row) > 5 else 10
            pages.append({"page_id": page_id, "page_type": page_type, "canonical_title": title, "content_sha256": module.sha_text(text), "revision_id": revision, "status":"published"})
        state = {"state_version":module.STATE_VERSION,"debate_id":"demo","language":language,"corpus_version":"old","publication_date":"2026-07-30T00:00:00Z","source_manifest_sha256":"0"*64,"plan_sha256":"1"*64,"pages":pages}
        state["state_sha256"] = module.sha_object(state)
        path = root / ".state" / "published" / "demo" / language / "latest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state), encoding="utf-8")
    validator = root / "validator.py"
    validator.write_text("import json; print(json.dumps({'validator_version':'0.4.73','result':'passed','summary':{'errors':0,'warnings':0}}))", encoding="utf-8")
    config = {
        "kit_version":"2.15.54","project_root":str(root),"debate_id":"demo","corpus_root":"corpus/demo","languages":list(languages),
        "family":"wikidebates","pywikibot_dir":"private/pywikibot","sites":{lang:{"code":lang,"expected_user":"ChatGPT"} for lang in languages},
        "validator":{"command":[TEST_VALIDATOR_PYTHON,str(validator),"validate"],"required_version":"0.4.73","scopes":[]},
        "published_state_dir":".state/published","receipts_dir":".state/receipts","logs_dir":"logs",
    }
    config_path = root / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return config, config_path


def plan(tmp_path, *, remote_pages=None, remote_revisions=None, rights=None, **fixture):
    config, path = make_fixture(tmp_path, **fixture)
    adapter = FakeAdapter(remote_pages, rights)
    adapter.revisions.update(remote_revisions or {})
    planner = module.RemoteUpdatePlanner(config, adapter, path)
    return planner.build_plan(), config, path, adapter


def test_01_new_page_is_create(tmp_path):
    p, *_ = plan(tmp_path, old_pages=[], new_pages=[("fr","A1","Titre",argument("Nouveau"))])
    assert p["counts"]["create"] == 1
    row = p["operations"]["create"][0]
    assert row["edit_summary_policy"] == "corpus_page_creation"
    assert row["edit_summary"] == "Création de l'argument à partir du corpus validé"


def test_02_unchanged_page_is_skip(tmp_path):
    text = argument("Même")
    p, *_ = plan(tmp_path, old_pages=[("fr","A1","Titre",text)], new_pages=[("fr","A1","Titre",text)], remote_pages={("fr","Titre"):(10,text)})
    assert p["counts"]["skip"] == 1


def test_03_published_page_changed_in_corpus_is_update(tmp_path):
    old, new = argument("Ancien"), argument("Nouveau")
    p, *_ = plan(tmp_path, old_pages=[("fr","A1","Titre",old)], new_pages=[("fr","A1","Titre",new)], remote_pages={("fr","Titre"):(10,old)})
    assert p["counts"]["update"] == 1


def test_04_human_modified_page_is_manual_review(tmp_path):
    old, human, new = argument("Ancien"), argument("Modification humaine"), argument("Nouveau")
    p, *_ = plan(tmp_path, old_pages=[("fr","A1","Titre",old)], new_pages=[("fr","A1","Titre",new)], remote_pages={("fr","Titre"):(11,human)})
    assert p["counts"]["manual_review"] == 1
    assert p["comparisons"]


def test_05_removed_argument_is_delete(tmp_path):
    old = argument("Ancien")
    p, *_ = plan(tmp_path, old_pages=[("fr","A1","Titre",old)], new_pages=[("fr","A2","Conservé",argument("Présent"))], remote_pages={("fr","Titre"):(10,old),("fr","Conservé"):(20,argument("Présent"))})
    assert p["counts"]["delete"] == 1
    row = p["operations"]["delete"][0]
    assert row["edit_summary_policy"] == "retirement_v1"
    assert row["edit_summary"].startswith("Suppression de la page retirée du corpus")


def test_06_already_deleted_is_idempotent_skip(tmp_path):
    p, *_ = plan(tmp_path, old_pages=[("fr","A1","Titre",argument("Ancien"))], new_pages=[("fr","A2","Conservé",argument("Présent"))], remote_pages={("fr","Conservé"):(20,argument("Présent"))})
    assert any(row["page_id"] == "A1" for row in p["operations"]["skip"])


def test_07_renamed_argument_is_move(tmp_path):
    old, new = argument("Ancien"), argument("Nouveau")
    p, *_ = plan(tmp_path, old_pages=[("fr","A1","Ancien titre",old)], new_pages=[("fr","A1","Nouveau titre",new)], remote_pages={("fr","Ancien titre"):(10,old)})
    assert p["counts"]["move"] == 1
    row = p["operations"]["move"][0]
    assert row["edit_summary_policy"] == "canonical_title_move_v1"
    assert row["edit_summary"] == "Renommage du titre canonique et mise à jour du résumé"


def test_08_merged_argument_can_redirect(tmp_path):
    old, target = argument("Fusionné"), argument("Cible")
    migrations=[{"language":"fr","old_page_id":"A1","kind":"merge","target_page_id":"A2","policy":"redirect"}]
    p, *_ = plan(tmp_path, old_pages=[("fr","A1","Ancien",old),("fr","A2","Cible",target)], new_pages=[("fr","A2","Cible",target)], migrations=migrations, remote_pages={("fr","Ancien"):(10,old),("fr","Cible"):(20,target)})
    assert p["counts"]["redirect"] == 1
    row = p["operations"]["redirect"][0]
    assert row["backlinks"] == ["Page entrante"]
    assert row["edit_summary_policy"] == "merge_redirect_v1"
    assert row["edit_summary"] == "Fusion en redirection vers [[Cible]]"


def test_09_never_published_page_is_not_deleted(tmp_path):
    p, *_ = plan(tmp_path, old_pages=[], new_pages=[("fr","A2","Conservé",argument("Présent"))], remote_pages={("fr","Étrangère"):(9,argument("Autre"))})
    assert p["counts"]["delete"] == 0


def test_10_page_owned_by_other_debate_is_blocked(tmp_path):
    old = argument("Ancien")
    p, config, path, adapter = plan(tmp_path, old_pages=[("fr","A1","Partagé",old)], new_pages=[("fr","A2","Conservé",argument("Présent"))], remote_pages={("fr","Partagé"):(10,old),("fr","Conservé"):(20,argument("Présent"))})
    other = {"state_version":module.STATE_VERSION,"debate_id":"autre","language":"fr","corpus_version":"x","publication_date":"x","source_manifest_sha256":"0"*64,"plan_sha256":"1"*64,"pages":[{"page_id":"Z","page_type":"argument","canonical_title":"Partagé","content_sha256":module.sha_text(old),"revision_id":10,"status":"published"}]}
    other["state_sha256"] = module.sha_object(other)
    op = tmp_path / ".state/published/autre/fr/latest.json"; op.parent.mkdir(parents=True); op.write_text(json.dumps(other),encoding="utf-8")
    p = module.RemoteUpdatePlanner(config, adapter, path).build_plan()
    assert p["counts"]["blocked"] == 1


def test_11_missing_delete_right_stops_before_write(tmp_path):
    old, kept = argument("Ancien"), argument("Présent")
    p, config, path, adapter = plan(tmp_path, rights={"edit","createpage"}, old_pages=[("fr","A1","Retiré",old),("fr","A2","Conservé",kept)], new_pages=[("fr","A2","Conservé",kept)], remote_pages={("fr","Retiré"):(10,old),("fr","Conservé"):(20,kept)})
    executor = module.PlanExecutor(config, adapter, path)
    try:
        executor.execute(p, p["plan_sha256"], only_delete=True)
    except module.PermissionDenied:
        pass
    else:
        raise AssertionError("delete sans droit accepté")
    assert not any(event[0] in {"write","delete","move"} for event in adapter.events)


def test_12_french_then_english_sessions_are_sequential(tmp_path):
    old_fr, old_en = argument("FR"), argument("EN")
    p, _, _, adapter = plan(tmp_path, languages=("fr","en"), old_pages=[("fr","A1","FR",old_fr),("en","A1","EN",old_en)], new_pages=[("fr","A1","FR",old_fr),("en","A1","EN",old_en)], remote_pages={("fr","FR"):(10,old_fr),("en","EN"):(11,old_en)})
    assert adapter.events[:4] == [("open","fr"),("close","fr"),("open","en"),("close","en")]


def test_13_interruption_then_resume_is_idempotent(tmp_path):
    one, two = argument("Un"), argument("Deux")
    p, config, path, adapter = plan(tmp_path, old_pages=[], new_pages=[("fr","A1","Un",one),("fr","A2","Deux",two)])
    executor = module.PlanExecutor(config, adapter, path)
    adapter.fail_after_writes = 1
    try:
        executor.execute(p, p["plan_sha256"])
    except RuntimeError:
        pass
    adapter.fail_after_writes = None
    receipt = executor.execute(p, p["plan_sha256"])
    assert receipt["counts"]["already_done"] == 1
    assert receipt["counts"]["created"] == 1


def test_14_remote_change_after_plan_is_conflict(tmp_path):
    old, new = argument("Ancien"), argument("Nouveau")
    p, config, path, adapter = plan(tmp_path, old_pages=[("fr","A1","Titre",old)], new_pages=[("fr","A1","Titre",new)], remote_pages={("fr","Titre"):(10,old)})
    adapter.pages[("fr","Titre")] = (11,argument("Changé après plan"))
    try:
        module.PlanExecutor(config, adapter, path).execute(p, p["plan_sha256"])
    except module.PlanConflict:
        pass
    else:
        raise AssertionError("conflit distant non détecté")


def test_15_only_delete_after_new_pages_already_published(tmp_path):
    retired, kept = argument("Retiré"), argument("Conservé")
    p, config, path, adapter = plan(tmp_path, old_pages=[("fr","A1","Retiré",retired),("fr","A2","Conservé",kept)], new_pages=[("fr","A2","Conservé",kept)], remote_pages={("fr","Retiré"):(10,retired),("fr","Conservé"):(20,kept)})
    receipt = module.PlanExecutor(config, adapter, path).execute(p, p["plan_sha256"], only_delete=True)
    assert receipt["counts"]["deleted"] == 1
    assert ("fr","Retiré") not in adapter.pages


def test_signed_read_only_remote_inventory_is_last_resort(tmp_path):
    text = argument("Inventorié")
    config, path = make_fixture(tmp_path, old_pages=[], new_pages=[("fr", "A1", "Titre", text)])
    state_path = tmp_path / ".state/published/demo/fr/latest.json"
    state_path.unlink()
    inventory = {
        "inventory_version": "1.0",
        "inventory_mode": "explicit_debate_pages_read_only",
        "debate_id": "demo",
        "language": "fr",
        "generated_at": "2026-07-31T20:00:00Z",
        "pages": [{
            "page_id": "A1",
            "page_type": "argument",
            "canonical_title": "Titre",
            "content_sha256": module.sha_text(text),
            "revision_id": 10,
            "status": "published",
            "content": text,
        }],
    }
    inventory["inventory_sha256"] = module.sha_object(inventory)
    inv_path = tmp_path / ".state/inventories/demo/fr.json"
    inv_path.parent.mkdir(parents=True)
    inv_path.write_text(json.dumps(inventory), encoding="utf-8")
    adapter = FakeAdapter({("fr", "Titre"): (10, text)})
    planner = module.RemoteUpdatePlanner(config, adapter, path)
    plan_data = planner.build_plan()
    assert plan_data["state_source"]["kind"] == "remote_inventory"
    assert plan_data["counts"]["skip"] == 1


def test_default_update_summary_is_concise(tmp_path):
    config, config_path = make_fixture(tmp_path, old_pages=[], new_pages=[])
    executor = module.PlanExecutor(config, FakeAdapter(), config_path)
    assert executor._summary("fr", "update", {"corpus_version":"manifest-deadbeef"}) == "Corrections"
    assert executor._summary("en", "update", {"corpus_version":"manifest-deadbeef"}) == "Corrections"


def test_16_manual_review_plan_cannot_be_executed_or_rewrite_state(tmp_path):
    old, human, new = argument("Ancien"), argument("Modification humaine"), argument("Nouveau")
    p, config, path, adapter = plan(
        tmp_path,
        old_pages=[("fr", "A1", "Titre", old)],
        new_pages=[("fr", "A1", "Titre", new)],
        remote_pages={("fr", "Titre"): (11, human)},
    )
    assert p["counts"]["manual_review"] == 1
    executor = module.PlanExecutor(config, adapter, path)
    try:
        executor.execute(p, p["plan_sha256"])
    except module.PlanConflict as exc:
        assert "révision manuelle" in str(exc)
    else:
        raise AssertionError("un plan manual_review a été exécuté")
    assert not (tmp_path / ".state" / "receipts").exists()
    latest = tmp_path / ".state" / "published" / "demo" / "fr" / "latest.json"
    state = json.loads(latest.read_text(encoding="utf-8"))
    assert state["pages"][0]["content_sha256"] == module.sha_text(old)


def test_17_all_skip_plan_cannot_create_false_success_receipt(tmp_path):
    text = argument("Même")
    p, config, path, adapter = plan(
        tmp_path,
        old_pages=[("fr", "A1", "Titre", text)],
        new_pages=[("fr", "A1", "Titre", text)],
        remote_pages={("fr", "Titre"): (10, text)},
    )
    executor = module.PlanExecutor(config, adapter, path)
    try:
        executor.execute(p, p["plan_sha256"])
    except module.PlanConflict as exc:
        assert "aucune opération exécutable" in str(exc)
    else:
        raise AssertionError("un plan entièrement skip a créé un faux succès")
    assert not (tmp_path / ".state" / "receipts").exists()


def test_18_no_changes_attestation_refreshes_state_for_next_update(tmp_path):
    old = argument("Ancien état")
    current = argument("Déjà présent à distance")
    p, config, path, adapter = plan(
        tmp_path,
        old_pages=[("fr", "A1", "Titre", old)],
        new_pages=[("fr", "A1", "Titre", current)],
        remote_pages={("fr", "Titre"): (20, current)},
    )
    assert p["counts"]["skip"] == 1
    receipt = module.PlanExecutor(config, adapter, path).attest_no_changes(p, p["plan_sha256"])
    assert receipt["status"] == "no_changes"
    assert receipt["counts"] == {"verified_unchanged": 1}
    state_path = tmp_path / ".state" / "published" / "demo" / "fr" / "latest.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["pages"][0]["content_sha256"] == module.sha_text(current)
    assert state["pages"][0]["revision_id"] == 20

    proposed = argument("Modification suivante")
    (tmp_path / "corpus" / "demo" / "output" / "fr" / "A1.wiki").write_text(proposed, encoding="utf-8")
    next_plan = module.RemoteUpdatePlanner(config, adapter, path).build_plan()
    assert next_plan["counts"]["update"] == 1
    assert next_plan["counts"]["manual_review"] == 0


def test_19_no_changes_attestation_detects_remote_change_after_plan(tmp_path):
    text = argument("Même contenu")
    p, config, path, adapter = plan(
        tmp_path,
        old_pages=[("fr", "A1", "Titre", text)],
        new_pages=[("fr", "A1", "Titre", text)],
        remote_pages={("fr", "Titre"): (10, text)},
    )
    adapter.pages[("fr", "Titre")] = (11, argument("Changement concurrent"))
    try:
        module.PlanExecutor(config, adapter, path).attest_no_changes(p, p["plan_sha256"])
    except module.PlanConflict as exc:
        assert "modifié depuis le plan" in str(exc)
    else:
        raise AssertionError("une attestation obsolète a été acceptée")
    assert not (tmp_path / ".state" / "receipts").exists()


def test_20_no_delete_preserves_pending_pages_for_later_only_delete(tmp_path):
    retired = argument("Retiré")
    old_kept = argument("Ancienne version")
    new_kept = argument("Nouvelle version")
    p, config, path, adapter = plan(
        tmp_path,
        old_pages=[
            ("fr", "A1", "Retiré", retired),
            ("fr", "A2", "Conservé", old_kept),
        ],
        new_pages=[("fr", "A2", "Conservé", new_kept)],
        remote_pages={
            ("fr", "Retiré"): (10, retired),
            ("fr", "Conservé"): (20, old_kept),
        },
    )
    receipt = module.PlanExecutor(config, adapter, path).execute(p, p["plan_sha256"], no_delete=True)
    assert receipt["counts"]["updated"] == 1
    assert ("fr", "Retiré") in adapter.pages
    state_path = tmp_path / ".state" / "published" / "demo" / "fr" / "latest.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    statuses = {row["page_id"]: row["status"] for row in state["pages"]}
    assert statuses == {"A1": "pending_delete", "A2": "published"}

    delete_plan = module.RemoteUpdatePlanner(config, adapter, path).build_plan()
    assert delete_plan["counts"]["delete"] == 1
    assert delete_plan["counts"]["manual_review"] == 0
    delete_receipt = module.PlanExecutor(config, adapter, path).execute(
        delete_plan,
        delete_plan["plan_sha256"],
        only_delete=True,
    )
    assert delete_receipt["counts"]["deleted"] == 1
    assert ("fr", "Retiré") not in adapter.pages
    final_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert [row["page_id"] for row in final_state["pages"]] == ["A2"]


def test_no_delete_plan_omits_retired_pages_even_when_the_remote_page_changed(tmp_path):
    retired = argument("Retiré")
    kept = argument("Conservé")
    config, path = make_fixture(
        tmp_path,
        old_pages=[("fr", "A1", "Retiré", retired), ("fr", "A2", "Conservé", kept)],
        new_pages=[("fr", "A2", "Conservé", kept)],
    )
    adapter = FakeAdapter({
        ("fr", "Retiré"): (11, argument("Retiré modifié")),
        ("fr", "Conservé"): (20, kept),
    })
    planned = module.RemoteUpdatePlanner(config, adapter, path).build_plan(mode="no_delete")
    retired_rows = [
        row
        for rows in planned["operations"].values()
        for row in rows
        if row.get("page_id") == "A1"
    ]
    assert retired_rows == []


def test_move_preserves_protected_warning_instead_of_blocking(tmp_path):
    old = argument('Ancien')
    new = argument('Nouveau').replace(MARKER, '')
    p, *_ = plan(
        tmp_path,
        old_pages=[('fr','A1','Ancien titre',old)],
        new_pages=[('fr','A1','Nouveau titre',new)],
        remote_pages={('fr','Ancien titre'):(10,old)},
    )
    assert p['counts']['move'] == 1
    assert p['counts']['blocked'] == 0
    operation = p['operations']['move'][0]
    assert operation['lifecycle_preservation']['effective']['avertissements-argument'] == (True, 'Argument généré par IA')
    effective = tmp_path / operation['source_path']
    assert MARKER.strip() in effective.read_text(encoding='utf-8')


def test_update_preserves_absent_ai_warning_on_historical_page(tmp_path):
    old = argument('Ancien').replace(MARKER, '')
    new = argument('Nouveau')
    p, *_ = plan(
        tmp_path,
        old_pages=[('fr','A1','Titre',old)],
        new_pages=[('fr','A1','Titre',new)],
        remote_pages={('fr','Titre'):(10,old)},
    )
    assert p['counts']['update'] == 1
    assert p['counts']['blocked'] == 0
    operation = p['operations']['update'][0]
    effective = tmp_path / operation['source_path']
    text = effective.read_text(encoding='utf-8')
    assert 'Argument généré par IA' not in text
    assert '|résumé=Nouveau' in text


def test_update_preserves_remote_creation_date_instead_of_current_corpus_date(tmp_path):
    old = argument('Ancien').replace('|rubriques=Société', '|date-création=2017-04-09\n|rubriques=Société')
    new = argument('Nouveau').replace('|rubriques=Société', '|date-création=2026-08-05\n|rubriques=Société')
    p, *_ = plan(
        tmp_path,
        old_pages=[('fr','A1','Titre',old)],
        new_pages=[('fr','A1','Titre',new)],
        remote_pages={('fr','Titre'):(10,old)},
    )
    assert p['counts']['update'] == 1
    operation = p['operations']['update'][0]
    text = (tmp_path / operation['source_path']).read_text(encoding='utf-8')
    assert '|date-création=2017-04-09' in text
    assert '|date-création=2026-08-05' not in text


def test_update_adopts_only_remote_preservable_metadata_drift(tmp_path):
    old = argument("Ancien")
    remote = old.replace(
        "|rubriques=Société",
        "|rubriques=Société, Politique\n|mots-clés=liberté d'expression, censure",
    )
    proposed = argument("Nouveau")
    p, *_ = plan(
        tmp_path,
        old_pages=[("fr", "A1", "Titre", old)],
        new_pages=[("fr", "A1", "Titre", proposed)],
        remote_pages={("fr", "Titre"): (11, remote)},
        remote_revisions={("fr", "Titre", 10): {
            "revision_id": 10, "text": old, "summary": "", "tags": [],
        }},
    )
    assert p["counts"]["update"] == 1
    assert p["counts"]["blocked"] == 0
    assert p["counts"]["manual_review"] == 0
    operation = p["operations"]["update"][0]
    assert operation["preserved_remote_metadata_drift"]["parameters"] == [
        "mots-clés", "rubriques",
    ]
    effective = (tmp_path / operation["source_path"]).read_text(encoding="utf-8")
    assert "|résumé=Nouveau" in effective
    assert "|rubriques=Société, Politique" in effective
    assert "|mots-clés=liberté d'expression, censure" in effective


def test_metadata_drift_adoption_rejects_outside_template_change(tmp_path):
    old = argument("Ancien")
    remote = old.replace("|rubriques=Société", "|rubriques=Politique") + "[[Catégorie:Ajout humain]]\n"
    proposed = argument("Nouveau")
    p, *_ = plan(
        tmp_path,
        old_pages=[("fr", "A1", "Titre", old)],
        new_pages=[("fr", "A1", "Titre", proposed)],
        remote_pages={("fr", "Titre"): (11, remote)},
        remote_revisions={("fr", "Titre", 10): {
            "revision_id": 10, "text": old, "summary": "", "tags": [],
        }},
    )
    assert p["counts"]["update"] == 0
    assert p["counts"]["manual_review"] == 1


def test_explicit_retirement_can_delete_attested_historical_page_without_ai_marker(tmp_path):
    old = argument('Ancien').replace(MARKER, '')
    kept = argument('Conservé')
    migrations=[{'language':'fr','old_page_id':'A1','kind':'remove','reason':'Retrait éditorial explicite'}]
    p, config, path, adapter = plan(
        tmp_path,
        old_pages=[('fr','A1','Retiré',old),('fr','A2','Conservé',kept)],
        new_pages=[('fr','A2','Conservé',kept)],
        migrations=migrations,
        remote_pages={('fr','Retiré'):(10,old),('fr','Conservé'):(20,kept)},
    )
    assert p['counts']['delete'] == 1
    assert p['counts']['blocked'] == 0
    assert p['operations']['delete'][0]['historical_page_without_generated_marker'] is True
    receipt = module.PlanExecutor(config, adapter, path).execute(p, p['plan_sha256'], only_delete=True)
    assert receipt['counts']['deleted'] == 1


def test_deferred_translation_blocks_english_remote_update_scope(tmp_path):
    config, path = make_fixture(
        tmp_path,
        languages=("en",),
        old_pages=[],
        new_pages=[("en", "A1", "English title", argument("English"))],
    )
    manifest_path = tmp_path / "corpus" / "demo" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["normative_versions"] = {"consolidated_norm": "1.2.34"}
    manifest["translation_status"] = {"en": "deferred"}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    try:
        module.RemoteUpdatePlanner(config, FakeAdapter(), path)
    except module.UpdateError as exc:
        assert "deferred" in str(exc)
    else:
        raise AssertionError("reprise anglaise acceptée pendant la traduction différée")


def test_authorized_manual_remote_adoption_allows_controlled_update(tmp_path):
    old, human, proposed = argument("Ancien"), argument("Modification humaine"), argument("Nouveau")
    adoption = [{
        "language": "fr", "page_id": "A1", "title": "Titre",
        "observed_revision_id": 11, "observed_sha256": module.sha_text(human),
        "allow_proposed_change": True, "reason": "Modification manuelle fournie par le propriétaire",
        "allowed_lifecycle_parameter_changes": [],
    }]
    p, *_ = plan(
        tmp_path, old_pages=[("fr", "A1", "Titre", old)],
        new_pages=[("fr", "A1", "Titre", proposed)],
        remote_pages={("fr", "Titre"): (11, human)}, remote_adoptions=adoption,
    )
    assert p["counts"]["update"] == 1
    assert p["counts"]["manual_review"] == 0
    assert p["operations"]["update"][0]["expected_revision_id"] == 11


def test_authorized_existing_unowned_page_can_be_adopted_and_updated(tmp_path):
    remote, proposed = argument("Manuel"), argument("Normalisé")
    adoption = [{
        "language": "fr", "page_id": "A1", "title": "Titre",
        "observed_revision_id": 21, "allow_proposed_change": True,
        "reason": "Page créée manuellement puis intégrée au corpus",
        "allowed_lifecycle_parameter_changes": [],
    }]
    p, *_ = plan(
        tmp_path, old_pages=[], new_pages=[("fr", "A1", "Titre", proposed)],
        remote_pages={("fr", "Titre"): (21, remote)}, remote_adoptions=adoption,
    )
    assert p["counts"]["update"] == 1
    assert p["counts"]["blocked"] == 0


def test_adoption_can_authorize_removing_out_of_scope_relations(tmp_path):
    remote = "{{Argument|justifications={{Justification|page=Outside}}|sections=Politics}}"
    proposed = "{{Argument|sections=Politics}}"
    adoption = [{
        "language": "en", "page_id": "A1", "title": "Title",
        "observed_revision_id": 21, "observed_sha256": module.sha_text(remote),
        "allow_proposed_change": True,
        "reason": "The relation lies outside the explicitly bounded graph.",
        "allowed_lifecycle_parameter_changes": [],
        "allowed_parameter_deletions": ["justifications"],
    }]
    p, *_ = plan(
        tmp_path, languages=("en",), old_pages=[],
        new_pages=[("en", "A1", "Title", proposed)],
        remote_pages={("en", "Title"): (21, remote)}, remote_adoptions=adoption,
    )
    assert p["counts"]["update"] == 1
    assert p["counts"]["blocked"] == 0


def test_remote_adoption_rejects_changed_revision(tmp_path):
    old, human, proposed = argument("Ancien"), argument("Modification humaine"), argument("Nouveau")
    adoption = [{
        "language": "fr", "page_id": "A1", "title": "Titre",
        "observed_revision_id": 10, "allow_proposed_change": True,
        "reason": "Révision attendue", "allowed_lifecycle_parameter_changes": [],
    }]
    p, *_ = plan(
        tmp_path, old_pages=[("fr", "A1", "Titre", old)],
        new_pages=[("fr", "A1", "Titre", proposed)],
        remote_pages={("fr", "Titre"): (11, human)}, remote_adoptions=adoption,
    )
    assert p["counts"]["blocked"] == 1
    assert "ne correspond plus" in p["operations"]["blocked"][0]["justification"]


def test_dieu_manual_sync_plan_has_no_blocked_or_manual_review(tmp_path):
    old_religions = "{{Argument\n|débat-dédié=Les religions se rejoignent-elles ?\n|rubriques=Religion et spiritualité\n|mots-clés=Dieu, religion, contradiction, pluralisme religieux\n|date-création=2021-02-17\n}}\n"
    proposed_religions = old_religions.replace("{{Argument\n", "{{Argument\n|résumé=Résumé vérifié. Deuxième phrase.\n", 1)
    new_parent_remote = "{{Argument\n|justifications={{Justification\n|page=Les religions se contredisent\n|titre-affiché=Les religions se contredisent\n}}\n|rubriques=Culture, Religion et spiritualité\n|mots-clés=Dieu, religion, contradiction\n}}\n"
    new_parent_proposed = new_parent_remote.replace("\n}}\n", "\n|date-création=2026-08-06\n}}\n", 1)
    reinc_remote = "{{Argument\n|initialisation=Objection@30833\n|débat-dédié=La réincarnation existe-t-elle ?\n|rubriques=Religion et spiritualité\n|mots-clés=réincarnation\n|date-création=2026-08-06\n}}\n"
    reinc_proposed = reinc_remote.replace("|mots-clés=réincarnation\n", "|mots-clés=réincarnation, scepticisme\n")
    fatima_remote = "{{Argument\n|initialisation=Objection@6604\n|débat-dédié=Le miracle du soleil de Fatima est-il fondé ?\n|rubriques=Religion et spiritualité, Science\n|mots-clés=miracle, soleil, Fatima, illusion, charlatanisme\n|date-création=2026-08-06\n}}\n"
    fatima_proposed = fatima_remote.replace("miracle, soleil, Fatima", "miracle, Fatima")
    external = "Argument externe"
    aseity_old = "{{Argument\n|résumé=Texte. Deuxième phrase.\n|objections={{Objection\n|page=Objection interne\n|titre-affiché=Objection interne\n}}\n|rubriques=Philosophie\n|date-création=2026-08-05\n}}\n"
    aseity_remote = aseity_old.replace(
        "|objections={{Objection\n|page=Objection interne\n|titre-affiché=Objection interne\n}}",
        f"|objections={{{{Objection\n|page=Objection interne\n|titre-affiché=Objection interne\n}}}}{{{{Objection\n|page={external}\n|titre-affiché={external}\n}}}}",
        1,
    )
    debate_remote = "{{Débat\n|arguments-contre={{Argument contre\n|page=Argument retiré\n|titre-affiché=Argument retiré\n}}\n|date-création=2017-01-29\n}}\n"
    debate_proposed = "{{Débat\n|date-création=2017-01-29\n}}\n"
    new_pages = [
        ("fr", "dieu", "Dieu existe-t-il ?", debate_proposed, "debate"),
        ("fr", "A0016", "Les religions se contredisent", proposed_religions),
        ("fr", "A0755", "Dieu n'existe pas car les religions se contredisent", new_parent_proposed),
        ("fr", "A0756", "La réincarnation n'existe pas", reinc_proposed),
        ("fr", "A0757", "Le miracle du soleil de Fatima n'est pas fondé", fatima_proposed),
        ("fr", "A0752", "L'aséité divine est menacée", aseity_remote),
    ]
    old_pages = [
        ("fr", "dieu", "Dieu existe-t-il ?", debate_remote, "debate", 1),
        ("fr", "A0016", "Les religions se contredisent", old_religions, "argument", 2),
        ("fr", "A0752", "L'aséité divine est menacée", aseity_old, "argument", 3),
    ]
    adoptions = [
        {"language":"fr","page_id":"dieu","title":"Dieu existe-t-il ?","observed_revision_id":11,"observed_sha256":module.sha_text(debate_remote),"reason":"Révision manuelle adoptée.","allow_proposed_change":True,"allowed_lifecycle_parameter_changes":[],"allowed_parameter_deletions":["arguments-contre"]},
        {"language":"fr","page_id":"A0016","title":"Les religions se contredisent","observed_revision_id":12,"observed_sha256":module.sha_text(old_religions),"reason":"Révision manuelle adoptée.","allow_proposed_change":True,"allowed_lifecycle_parameter_changes":[]},
        {"language":"fr","page_id":"A0755","title":"Dieu n'existe pas car les religions se contredisent","observed_revision_id":13,"observed_sha256":module.sha_text(new_parent_remote),"reason":"Révision manuelle adoptée.","allow_proposed_change":True,"allowed_lifecycle_parameter_changes":["date-création"]},
        {"language":"fr","page_id":"A0756","title":"La réincarnation n'existe pas","observed_revision_id":14,"observed_sha256":module.sha_text(reinc_remote),"reason":"Révision manuelle adoptée.","allow_proposed_change":True,"allowed_lifecycle_parameter_changes":[]},
        {"language":"fr","page_id":"A0757","title":"Le miracle du soleil de Fatima n'est pas fondé","observed_revision_id":15,"observed_sha256":module.sha_text(fatima_remote),"reason":"Révision manuelle adoptée.","allow_proposed_change":True,"allowed_lifecycle_parameter_changes":[]},
        {"language":"fr","page_id":"A0752","title":"L'aséité divine est menacée","observed_revision_id":16,"observed_sha256":module.sha_text(aseity_remote),"reason":"Relation externe conservée.","allow_proposed_change":False,"allowed_lifecycle_parameter_changes":[],"external_relations":[{"relation":"objection","page":external,"displayed_title":external}]},
    ]
    remote = {
        ("fr", "Dieu existe-t-il ?"):(11, debate_remote),
        ("fr", "Les religions se contredisent"):(12, old_religions),
        ("fr", "Dieu n'existe pas car les religions se contredisent"):(13, new_parent_remote),
        ("fr", "La réincarnation n'existe pas"):(14, reinc_remote),
        ("fr", "Le miracle du soleil de Fatima n'est pas fondé"):(15, fatima_remote),
        ("fr", "L'aséité divine est menacée"):(16, aseity_remote),
    }
    result, *_ = plan(tmp_path, remote_pages=remote, old_pages=old_pages, new_pages=new_pages, remote_adoptions=adoptions)
    assert result["counts"]["blocked"] == 0
    assert result["counts"]["manual_review"] == 0
    assert result["counts"]["update"] == 5
    assert result["counts"]["skip"] == 1
    assert result["counts"]["move"] == 0


def test_interlanguage_explicit_assignment_survives_historical_restoration():
    remote = "{{Argument\n|résumé=Texte.\n|rubriques=Philosophie\n|date-création=2020-01-01\n}}\n"
    link = "{{Lien interlangue\n|langue=en\n|page=English title\n}}"
    proposed = remote.replace("|rubriques=", f"|interlangue={link}\n|rubriques=", 1)
    snapshot = module.protected_lifecycle_snapshot(remote, "fr", "argument")
    states = {
        key: {"present": present, "value": value}
        for key, (present, value) in snapshot.items()
    }
    effective, audit = module.preserve_remote_lifecycle_parameters(
        remote,
        proposed,
        "fr",
        "argument",
        desired_preserved_parameters=states,
        allow_historical_restoration=True,
        explicit_parameter_assignments={"interlangue": link},
    )
    assert f"|interlangue={link}" in effective
    assert audit["explicit_parameter_assignments"] == {"interlangue": link}


def test_french_interlanguage_addition_gets_page_specific_summary_and_executes(tmp_path):
    old = "{{Argument\n|résumé=Texte.\n|rubriques=Philosophie\n|date-création=2020-01-01\n}}\n"
    en_title = "English title"
    link = f"{{{{Lien interlangue\n|langue=en\n|page={en_title}\n}}}}"
    new = old.replace("|rubriques=", f"|interlangue={link}\n|rubriques=", 1)
    config, path = make_fixture(
        tmp_path,
        languages=("fr",),
        old_pages=[("fr", "A1", "Titre français", old)],
        new_pages=[("fr", "A1", "Titre français", new)],
    )
    manifest_path = tmp_path / "corpus" / "demo" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["translation_status"] = {"en": "ready"}
    manifest["pages"].append({
        "language": "en", "page_id": "A1", "page_type": "argument",
        "canonical_title": en_title, "file_path": "output/en/A1.wiki", "sha256": "0" * 64,
    })
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    adapter = FakeAdapter({("fr", "Titre français"): (10, old)})
    planner = module.RemoteUpdatePlanner(config, adapter, path)
    planned = planner.build_plan()
    assert planned["counts"]["update"] == 1
    row = planned["operations"]["update"][0]
    expected = f"Ajout du lien interlangue vers la page anglaise : [[:en:{en_title}|{en_title}]]"
    assert row["edit_summary_policy"] == "french_interlanguage_addition"
    assert row["edit_summary"] == expected
    executor = module.PlanExecutor(config, adapter, path)
    receipt = executor.execute(planned, planned["plan_sha256"])
    assert receipt["results"][0]["edit_summary"] == expected
    assert any(event[0] == "write" and event[3] == expected for event in adapter.events)


def test_non_interlanguage_french_update_gets_diff_specific_summary(tmp_path):
    old, new = argument("Ancien"), argument("Nouveau")
    p, config, path, adapter = plan(
        tmp_path,
        old_pages=[("fr", "A1", "Titre", old)],
        new_pages=[("fr", "A1", "Titre", new)],
        remote_pages={("fr", "Titre"): (10, old)},
    )
    assert p["edit_summary_contract"] == "page_specific_v1"
    row = p["operations"]["update"][0]
    assert row["edit_summary_policy"] == "content_diff_v1"
    assert row["edit_summary"] == "Mise à jour du résumé"
    executor = module.PlanExecutor(config, adapter, path)
    receipt = executor.execute(p, p["plan_sha256"])
    assert receipt["results"][0]["edit_summary"] == "Mise à jour du résumé"
    assert receipt["results"][0]["edit_summary"] != "Corrections"


@pytest.mark.parametrize("operation", ["update", "move"])
@pytest.mark.parametrize("old,new", [
    ("{{Argument|citations=Source}}", "{{Argument|résumé=Ajout|citations=Source}}"),
    (argument(""), argument("Ajout")),
    (argument("Ancien"), argument("Nouveau")),
    (argument("Ancien"), argument("")),
])
def test_existing_summary_cannot_change_under_a_generic_update_scope(tmp_path, operation, old, new):
    p, _, _, adapter = plan(
        tmp_path, authorize_summary_changes=False,
        old_pages=[("fr", "A1", "Titre", old)],
        new_pages=[("fr", "A1", "Renommé" if operation == "move" else "Titre", new)],
        remote_pages={("fr", "Titre"): (10, old)},
    )
    assert p["counts"]["blocked"] == 1
    assert "résumé" in p["operations"]["blocked"][0]["justification"]
    assert not any(e[0] in {"write", "move"} for e in adapter.events)


def test_citation_fix_preserves_existing_summary_without_summary_permission(tmp_path):
    old = "{{Argument|résumé=Résumé historique|citations=Ancienne source}}"
    new = old.replace("Ancienne source", "Source corrigée")
    p, config, path, adapter = plan(
        tmp_path, authorize_summary_changes=False,
        old_pages=[("fr", "A1", "Titre", old)], new_pages=[("fr", "A1", "Titre", new)],
        remote_pages={("fr", "Titre"): (10, old)},
    )
    assert p["operations"]["update"][0]["edit_summary"] == "Mise à jour des citations"
    module.PlanExecutor(config, adapter, path).execute(p, p["plan_sha256"])
    assert module.top_level_parameter_map(adapter.pages[("fr", "Titre")][1], "fr", "argument")[2] == module.top_level_parameter_map(new, "fr", "argument")[2]


def test_legacy_plan_without_specific_summary_permission_is_blocked_before_first_write(tmp_path):
    old, new = argument("Ancien"), argument("Nouveau")
    p, config, path, adapter = plan(
        tmp_path, old_pages=[("fr", "A1", "Titre", old)],
        new_pages=[("fr", "A1", "Titre", new), ("fr", "A0", "Nouvelle page", argument("Création"))],
        remote_pages={("fr", "Titre"): (10, old)},
    )
    p["operations"]["update"][0].pop("summary_change_authorization")
    p.pop("plan_sha256")
    p["plan_sha256"] = module.sha_object(p)
    with pytest.raises(module.PlanConflict, match="résumé"):
        module.PlanExecutor(config, adapter, path).execute(p, p["plan_sha256"])
    assert not any(e[0] in {"write", "move"} for e in adapter.events)


def test_english_argument_summary_has_the_same_default_protection(tmp_path):
    old, new = "{{Argument|summary=Original}}", "{{Argument|summary=Rewritten}}"
    p, *_ = plan(
        tmp_path, languages=("en",), authorize_summary_changes=False,
        old_pages=[("en", "A1", "Title", old)], new_pages=[("en", "A1", "Title", new)],
        remote_pages={("en", "Title"): (10, old)},
    )
    assert p["counts"]["blocked"] == 1


@pytest.mark.parametrize("language,model,field,text_key", [
    ("fr","Citation","citations","citation"), ("en","Quote","quotes","quote"),
])
@pytest.mark.parametrize("operation", ["update","move"])
def test_update_and_move_protect_existing_citations(tmp_path,language,model,field,text_key,operation):
    quote="{{"+model+"|"+text_key+"=Citation historique}}"
    old="{{Argument|"+field+"="+quote+"}}"
    new="{{Argument|"+field+"=}}"
    p,*_=plan(tmp_path,languages=(language,),
        old_pages=[(language,"A1","Titre",old)],
        new_pages=[(language,"A1","Renommé" if operation=="move" else "Titre",new)],
        remote_pages={(language,"Titre"):(10,old)})
    assert p["counts"]["blocked"]==1
    assert "citation existante" in p["operations"]["blocked"][0]["justification"]


def test_duplicate_or_unlocated_quote_is_not_a_deletion_permission():
    quote="{{Citation|citation=Texte historique|auteurs=Auteur}}"
    with pytest.raises(module.UpdateError,match="citation existante"):
        module.assert_citation_change_authorized(quote+quote,quote)
    with pytest.raises(module.UpdateError,match="citation existante"):
        module.assert_citation_change_authorized(quote,"",{"decision":"explicit_user_request"})
    module.assert_citation_change_authorized(quote,quote+"{{Citation|citation=Nouvelle source}}")


def test_retired_french_quote_warning_alias_is_not_a_citation_rewrite():
    old = "{{Argument|citations={{Citation|citation=Texte historique|avertissements=Citation trop courte}}}}"
    new = "{{Argument|citations={{Citation|citation=Texte historique|avertissements-citation=Citation trop courte}}}}"
    module.assert_citation_change_authorized(old, new)
    with pytest.raises(module.UpdateError, match="citation existante"):
        module.assert_citation_change_authorized(
            old,
            new.replace("Citation trop courte", "Texte abrégé"),
        )


def test_quote_protection_covers_quotes_inside_debate_introduction():
    old="{{Débat|introduction={{Citation|citation=Historique}}}}"
    with pytest.raises(module.UpdateError,match="citation existante"):
        module.assert_citation_change_authorized(old,"{{Débat|introduction=Autre texte}}")


def test_old_plan_cannot_remove_a_quote_before_or_after_other_page_creations(tmp_path):
    old="{{Argument|citations={{Citation|citation=Historique}}}}"
    new="{{Argument|citations=}}"
    config,path=make_fixture(tmp_path,old_pages=[("fr","A1","Titre",old)],
        new_pages=[("fr","A1","Titre",new),("fr","A0","Création",argument("Création"))])
    manifest_path=tmp_path/"corpus/demo/manifest.json"
    manifest=json.loads(manifest_path.read_text())
    manifest["pages"][0]["citation_change_authorization"]={
        "decision":"explicit_user_request","action":"edit","instruction":"Retire cette citation pour ce test."
    }
    manifest_path.write_text(json.dumps(manifest))
    adapter=FakeAdapter({("fr","Titre"):(10,old)})
    p=module.RemoteUpdatePlanner(config,adapter,path).build_plan()
    manifest["pages"][0].pop("citation_change_authorization")
    manifest_path.write_text(json.dumps(manifest))
    p["operations"]["update"][0].pop("citation_change_authorization")
    p["new_manifest_sha256"]=module.sha_file(manifest_path)
    p.pop("plan_sha256");p["plan_sha256"]=module.sha_object(p)
    with pytest.raises(module.PlanConflict,match="citation existante"):
        module.PlanExecutor(config,adapter,path).execute(p,p["plan_sha256"])
    assert not any(e[0] in {"write","move"} for e in adapter.events)


def test_remote_page_without_expected_main_template_is_page_specific_manual_review(tmp_path):
    old = argument("Ancien")
    proposed = argument("Nouveau")
    remote = "#REDIRECT [[Autre titre]]\n"
    p, *_ = plan(
        tmp_path,
        old_pages=[("fr", "A1", "Titre", old)],
        new_pages=[("fr", "A1", "Titre", proposed)],
        remote_pages={("fr", "Titre"): (11, remote)},
    )
    assert p["counts"]["manual_review"] == 1
    row = p["operations"]["manual_review"][0]
    assert row["title"] == "Titre"
    assert "Modèle principal introuvable" in row["remote_structure_error"]
    assert row["remote_excerpt"].startswith("#REDIRECT")


def test_56_interlanguage_only_preserves_human_changes(tmp_path):
    remote = argument("Modification humaine conservée")
    proposed = argument("Version du corpus différente")
    config, path = make_fixture(
        tmp_path,
        languages=("fr",),
        old_pages=[("fr", "A1", "Titre", argument("Ancien"))],
        new_pages=[("fr", "A1", "Titre", proposed)],
    )
    corpus = tmp_path / "corpus" / "demo"
    en_dir = corpus / "output" / "en"; en_dir.mkdir(parents=True, exist_ok=True)
    en_file = en_dir / "A1.wiki"; en_file.write_text("{{Argument\n|summary=English\n}}\n", encoding="utf-8")
    manifest = json.loads((corpus / "manifest.json").read_text())
    manifest["translation_status"] = {"en": "ready"}
    manifest["pages"].append({"language":"en","page_id":"A1","page_type":"argument","canonical_title":"English title","file_path":"output/en/A1.wiki","sha256":module.sha_file(en_file)})
    (corpus / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    config["interlanguage_only"] = True
    path.write_text(json.dumps(config), encoding="utf-8")
    adapter = FakeAdapter({("fr", "Titre"):(11, remote)})
    planner = module.RemoteUpdatePlanner(config, adapter, path)
    p = planner.build_plan()
    assert p["counts"]["update"] == 1
    assert p["counts"]["manual_review"] == 0
    row = p["operations"]["update"][0]
    desired = Path(tmp_path / row["source_path"]).read_text(encoding="utf-8")
    assert "Modification humaine conservée" in desired
    assert "Version du corpus différente" not in desired
    assert "|interlangue={{Lien interlangue\n|langue=en\n|page=English title\n}}" in desired
    assert row["edit_summary"] == "Ajout du lien interlangue vers la page anglaise : [[:en:English title|English title]]"


def test_57_interlanguage_only_preserves_external_parameter(tmp_path):
    remote = "{{Argument\n|résumé=Texte\n|objections={{Objection\n|page=Ajout humain\n|titre-affiché=Ajout humain\n}}\n|rubriques=Philosophie\n}}\n"
    proposed = "{{Argument\n|résumé=Texte\n|rubriques=Philosophie\n}}\n"
    config, path = make_fixture(tmp_path, languages=("fr",), old_pages=[], new_pages=[("fr","A1","Titre",proposed)])
    corpus = tmp_path / "corpus" / "demo"; en_dir=corpus/"output"/"en"; en_dir.mkdir(parents=True,exist_ok=True)
    en_file=en_dir/"A1.wiki"; en_file.write_text("{{Argument\n|summary=x\n}}\n",encoding="utf-8")
    manifest=json.loads((corpus/"manifest.json").read_text()); manifest["translation_status"]={"en":"ready"}; manifest["pages"].append({"language":"en","page_id":"A1","page_type":"argument","canonical_title":"English title","file_path":"output/en/A1.wiki","sha256":module.sha_file(en_file)}); (corpus/"manifest.json").write_text(json.dumps(manifest),encoding="utf-8")
    config["interlanguage_only"]=True; path.write_text(json.dumps(config),encoding="utf-8")
    adapter=FakeAdapter({("fr","Titre"):(25,remote)})
    p=module.RemoteUpdatePlanner(config,adapter,path).build_plan()
    assert p["counts"]["update"]==1 and p["counts"]["blocked"]==0
    row=p["operations"]["update"][0]; desired=(tmp_path/row["source_path"]).read_text(encoding="utf-8")
    assert "Ajout humain" in desired


def test_58_interlanguage_only_keeps_redirect_and_adds_direct_language_link(tmp_path):
    remote = "#REDIRECTION [[L'homme est déterminé]]\n"
    proposed = argument("Page complète du corpus")
    config, path = make_fixture(tmp_path, languages=("fr",), old_pages=[], new_pages=[("fr","A1","Il n'existe pas de libre arbitre",proposed)])
    corpus=tmp_path/"corpus"/"demo"; en_dir=corpus/"output"/"en"; en_dir.mkdir(parents=True,exist_ok=True)
    en_file=en_dir/"A1.wiki"; en_file.write_text("{{Argument\n|summary=x\n}}\n",encoding="utf-8")
    manifest=json.loads((corpus/"manifest.json").read_text()); manifest["translation_status"]={"en":"ready"}; manifest["pages"].append({"language":"en","page_id":"A1","page_type":"argument","canonical_title":"There is no free will","file_path":"output/en/A1.wiki","sha256":module.sha_file(en_file)}); (corpus/"manifest.json").write_text(json.dumps(manifest),encoding="utf-8")
    config["interlanguage_only"]=True; path.write_text(json.dumps(config),encoding="utf-8")
    adapter=FakeAdapter({("fr","Il n'existe pas de libre arbitre"):(30,remote)})
    p=module.RemoteUpdatePlanner(config,adapter,path).build_plan(); assert p["counts"]["update"]==1
    row=p["operations"]["update"][0]; desired=(tmp_path/row["source_path"]).read_text(encoding="utf-8")
    assert desired.startswith("#REDIRECTION [[L'homme est déterminé]]")
    assert "[[en:There is no free will]]" in desired
    assert row["interlanguage_representation"] == "redirect_added"


def test_59_interlanguage_only_executor_rechecks_pure_overlay(tmp_path):
    remote = argument("Modification humaine conservée")
    proposed = argument("Version corpus")
    config, path = make_fixture(tmp_path, languages=("fr",), old_pages=[("fr","A1","Titre",argument("Ancien"))], new_pages=[("fr","A1","Titre",proposed)])
    corpus=tmp_path/"corpus"/"demo"; en_dir=corpus/"output"/"en"; en_dir.mkdir(parents=True,exist_ok=True)
    en_file=en_dir/"A1.wiki"; en_file.write_text("{{Argument\n|summary=x\n}}\n",encoding="utf-8")
    manifest=json.loads((corpus/"manifest.json").read_text()); manifest["translation_status"]={"en":"ready"}; manifest["pages"].append({"language":"en","page_id":"A1","page_type":"argument","canonical_title":"English title","file_path":"output/en/A1.wiki","sha256":module.sha_file(en_file)}); (corpus/"manifest.json").write_text(json.dumps(manifest),encoding="utf-8")
    config["interlanguage_only"]=True; path.write_text(json.dumps(config),encoding="utf-8")
    adapter=FakeAdapter({("fr","Titre"):(11,remote)})
    planner=module.RemoteUpdatePlanner(config,adapter,path); p=planner.build_plan()
    executor=module.PlanExecutor(config,adapter,path); receipt=executor.execute(p,p["plan_sha256"])
    assert receipt["counts"]["updated"] == 1
    final = adapter.pages[("fr", "Titre")][1]
    assert "Modification humaine conservée" in final
    assert "|page=English title" in final


def test_59b_interlanguage_only_explicitly_retargets_superseded_title(tmp_path):
    remote = argument("Texte humain").replace(
        "|rubriques=Société",
        "|interlangue={{Lien interlangue\n|langue=en\n|page=Old English title\n}}\n|rubriques=Société",
    )
    proposed = argument("Version corpus")
    config, path = make_fixture(tmp_path, languages=("fr",), old_pages=[], new_pages=[("fr", "A1", "Titre", proposed)])
    corpus = tmp_path / "corpus" / "demo"; en_dir = corpus / "output" / "en"; en_dir.mkdir(parents=True, exist_ok=True)
    en_file = en_dir / "A1.wiki"; en_file.write_text("{{Argument\n|summary=x\n}}\n", encoding="utf-8")
    manifest = json.loads((corpus / "manifest.json").read_text()); manifest["translation_status"] = {"en": "ready"}; manifest["pages"].append({"language":"en","page_id":"A1","page_type":"argument","canonical_title":"Final English title","file_path":"output/en/A1.wiki","sha256":module.sha_file(en_file)}); (corpus / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    config["interlanguage_only"] = True
    config["interlanguage_retargets"] = {"A1": "Old English title"}
    path.write_text(json.dumps(config), encoding="utf-8")
    adapter = FakeAdapter({("fr", "Titre"): (11, remote)})
    plan = module.RemoteUpdatePlanner(config, adapter, path).build_plan()
    assert plan["counts"]["update"] == 1 and plan["counts"]["blocked"] == 0
    row = plan["operations"]["update"][0]
    assert row["previous_interlanguage_title"] == "Old English title"
    receipt = module.PlanExecutor(config, adapter, path).execute(plan, plan["plan_sha256"])
    assert receipt["counts"]["updated"] == 1
    final = adapter.pages[("fr", "Titre")][1]
    assert "Texte humain" in final and "|page=Final English title" in final


def test_60_postwrite_verification_retries_until_chatgpt_tag_is_visible(tmp_path):
    old = argument("Ancien")
    new = argument("Nouveau")
    config, path = make_fixture(
        tmp_path,
        old_pages=[("fr", "A1", "Titre", old)],
        new_pages=[("fr", "A1", "Titre", new)],
    )
    config["verification_attempts"] = 4
    config["verification_delay_seconds"] = 0
    path.write_text(json.dumps(config), encoding="utf-8")

    class LaggingTagAdapter(FakeAdapter):
        def __init__(self, pages):
            super().__init__(pages)
            self.postwrite_reads = 0

        def read_revision(self, title, revision_id):
            row = super().read_revision(title, revision_id)
            if row is None:
                return None
            self.postwrite_reads += 1
            copy = dict(row)
            if self.postwrite_reads < 3:
                copy["tags"] = []
            return copy

    adapter = LaggingTagAdapter({("fr", "Titre"): (10, old)})
    planned = module.RemoteUpdatePlanner(config, adapter, path).build_plan()
    receipt = module.PlanExecutor(config, adapter, path).execute(planned, planned["plan_sha256"])
    assert receipt["counts"]["updated"] == 1
    assert adapter.postwrite_reads == 3


def test_page_specific_summary_is_recomputed_and_tampering_is_blocked(tmp_path):
    old, new = argument("Ancien"), argument("Nouveau")
    planned, config, path, adapter = plan(
        tmp_path,
        old_pages=[("fr", "A1", "Titre", old)],
        new_pages=[("fr", "A1", "Titre", new)],
        remote_pages={("fr", "Titre"): (10, old)},
    )
    row = planned["operations"]["update"][0]
    row["edit_summary"] = "Corrections"
    unsigned = dict(planned)
    unsigned.pop("plan_sha256", None)
    planned["plan_sha256"] = module.sha_object(unsigned)
    executor = module.PlanExecutor(config, adapter, path)
    try:
        executor.execute(planned, planned["plan_sha256"])
    except module.PlanConflict as exc:
        assert "Résumé individualisé divergent" in str(exc) or "Résumé générique interdit" in str(exc)
    else:
        raise AssertionError("Un résumé falsifié ne doit jamais être exécuté")


def test_first_english_publication_uses_french_receipt_and_deferred_installed_manifest(tmp_path):
    fr_text = argument("Français déjà publié")
    en_text = argument("English first publication")
    config, config_path = make_fixture(
        tmp_path,
        languages=("fr", "en"),
        old_pages=[("fr", "A1", "Titre FR", fr_text)],
        new_pages=[
            ("fr", "A1", "Titre FR", fr_text),
            ("en", "A1", "EN title", en_text),
        ],
    )

    # Simulate ./wikidebia update with a new archive staged outside corpus/.
    staged = tmp_path / ".state" / "update-staging" / "candidate"
    staged.parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "corpus" / "demo").rename(staged)
    config["corpus_root"] = str(staged.relative_to(tmp_path))
    config_path.write_text(json.dumps(config), encoding="utf-8")

    # The currently installed corpus is the previous French-only release.  Its
    # explicit deferred status is the attestation that the English baseline was
    # intentionally empty before this first bilingual publication.
    installed = tmp_path / "corpus" / "demo"
    (installed / "output" / "fr").mkdir(parents=True)
    installed_fr = installed / "output" / "fr" / "A1.wiki"
    installed_fr.write_text(fr_text, encoding="utf-8")
    (installed / "manifest.json").write_text(json.dumps({
        "debate_id": "demo",
        "release_version": "previous",
        "translation_status": {"en": "deferred"},
        "pages": [{
            "language": "fr",
            "page_id": "A1",
            "page_type": "argument",
            "canonical_title": "Titre FR",
            "file_path": "output/fr/A1.wiki",
            "sha256": module.sha_file(installed_fr),
        }],
    }), encoding="utf-8")

    # French checkpoint state exists; English has never been published.
    (tmp_path / ".state" / "published" / "demo" / "en" / "latest.json").unlink()
    adapter = FakeAdapter({("fr", "Titre FR"): (10, fr_text)})
    planner = module.RemoteUpdatePlanner(config, adapter, config_path)
    plan_data = planner.build_plan()

    assert plan_data["counts"]["skip"] == 1
    assert plan_data["counts"]["create"] == 1
    assert plan_data["counts"]["manual_review"] == 0
    assert plan_data["counts"]["blocked"] == 0
    source = plan_data["state_source"]
    assert source["resolution"] == "per_language_attested_v1"
    assert source["per_language"]["fr"]["kind"] == "published_state_receipt"
    assert source["per_language"]["en"]["kind"] == "previous_installed_manifest"
    assert source["per_language"]["en"]["empty_baseline"] is True


def test_missing_english_state_still_blocks_without_deferred_prior_evidence(tmp_path):
    fr_text = argument("Français")
    en_text = argument("English")
    config, config_path = make_fixture(
        tmp_path,
        languages=("fr", "en"),
        old_pages=[("fr", "A1", "Titre FR", fr_text)],
        new_pages=[
            ("fr", "A1", "Titre FR", fr_text),
            ("en", "A1", "EN title", en_text),
        ],
    )
    (tmp_path / ".state" / "published" / "demo" / "en" / "latest.json").unlink()
    try:
        module.RemoteUpdatePlanner(config, FakeAdapter({("fr", "Titre FR"): (10, fr_text)}), config_path)
    except module.UpdateError as exc:
        assert "Langue(s) sans preuve : en" in str(exc)
    else:
        raise AssertionError("une baseline anglaise inconnue a été acceptée sans preuve")


def test_signed_plan_producer_versions_are_provenance_on_resume(tmp_path):
    text = argument("Même")
    p, config, path, adapter = plan(
        tmp_path,
        old_pages=[("fr", "A1", "Titre", text)],
        new_pages=[("fr", "A1", "Titre", text)],
        remote_pages={("fr", "Titre"): (10, text)},
    )
    # Simulate a plan signed by the immediately preceding installed components.
    p["kit_version"] = "2.16.45"
    p["required_validator_version"] = "0.4.104"
    p.pop("plan_sha256", None)
    p["plan_sha256"] = module.sha_object(p)

    executor = module.PlanExecutor(config, adapter, path)
    executor.verify_plan(p, p["plan_sha256"])


def test_signed_plan_still_blocks_manifest_divergence_across_versions(tmp_path):
    text = argument("Même")
    p, config, path, adapter = plan(
        tmp_path,
        old_pages=[("fr", "A1", "Titre", text)],
        new_pages=[("fr", "A1", "Titre", text)],
        remote_pages={("fr", "Titre"): (10, text)},
    )
    p["kit_version"] = "2.16.45"
    p["required_validator_version"] = "0.4.104"
    p["new_manifest_sha256"] = "f" * 64
    p.pop("plan_sha256", None)
    p["plan_sha256"] = module.sha_object(p)

    executor = module.PlanExecutor(config, adapter, path)
    try:
        executor.verify_plan(p, p["plan_sha256"])
    except module.PlanConflict as exc:
        assert "new_manifest_sha256" in str(exc)
    else:
        raise AssertionError("un plan signé pour un autre manifeste a été accepté")


def test_signed_plan_still_blocks_config_divergence_across_versions(tmp_path):
    text = argument("Même")
    p, config, path, adapter = plan(
        tmp_path,
        old_pages=[("fr", "A1", "Titre", text)],
        new_pages=[("fr", "A1", "Titre", text)],
        remote_pages={("fr", "Titre"): (10, text)},
    )
    p["kit_version"] = "2.16.45"
    p["required_validator_version"] = "0.4.104"
    p["config_sha256"] = "e" * 64
    p.pop("plan_sha256", None)
    p["plan_sha256"] = module.sha_object(p)

    executor = module.PlanExecutor(config, adapter, path)
    try:
        executor.verify_plan(p, p["plan_sha256"])
    except module.PlanConflict as exc:
        assert "config_sha256" in str(exc)
    else:
        raise AssertionError("un plan signé pour une autre configuration a été accepté")
