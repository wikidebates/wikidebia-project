from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

import wikidebia_fr_publication_relay as relay


@pytest.fixture(autouse=True)
def no_verification_sleep(monkeypatch):
    monkeypatch.setattr(relay.time, "sleep", lambda seconds: None)


def request_fixture(directory: Path, request_id="cannabis-fr-test"):
    directory.mkdir(parents=True)
    originals = {"Child": (10, "{{Argument|résumé=Source conservée}}\n"),
                 "Parent": (11, "{{Argument|justifications={{Justification|page=Child}}}}\n")}
    pages = []
    for title, (revision, before) in originals.items():
        after = before.replace("page=Child", "page=Renamed child")
        for folder, text in (("before", before), ("after", after)):
            (directory / folder).mkdir(exist_ok=True)
            (directory / folder / (title+".wiki")).write_text(text)
        pages.append({"page_id": title, "old_title": title,
                      "new_title": "Renamed child" if title == "Child" else title,
                      "source_revision_id": revision, "source_sha256": relay.digest(before.encode()),
                      "target_sha256": relay.digest(after.encode()),
                      "before_file": "before/"+title+".wiki", "after_file": "after/"+title+".wiki"})
    request = {"schema": relay.SCHEMA, "request_id": request_id, "language": "fr", "site": relay.SITE,
               "authorization": "explicit_user_request", "pages": pages}
    save_request(directory, request)
    return request, originals


def save_request(directory, request):
    request["request_sha256"] = relay.request_hash(request)
    (directory / "request.json").write_text(json.dumps(request, ensure_ascii=False)+"\n")


class FakeWiki:
    def __init__(self, pages):
        self.pages = dict(pages)
        self.writes = []
        self.revisions = {}
        self.rights = {"edit", "move"}
        self.tags = {"chatgpt"}
        self.user = "ChatGPT"
        self.fail_after_move = False
        self.opened = False

    def open_language(self, language, expected_user):
        assert language == "fr"
        self.opened = True

    def close_language(self):
        self.opened = False

    def assert_identity(self, expected_user):
        if self.user != expected_user:
            raise relay.Blocked("Identité incorrecte")

    def user_rights(self):
        return self.rights

    def available_change_tags(self):
        return self.tags

    def assert_main_namespace(self, title):
        if ":" in title:
            raise relay.Blocked("Namespace interdit")

    def read_page(self, title):
        if title not in self.pages:
            return False, None, ""
        revision, text = self.pages[title]
        return True, revision, text

    def move_page(self, *, old_title, new_title, reason, expected_user, leave_redirect):
        assert leave_redirect
        assert new_title not in self.pages
        self.assert_identity(expected_user)
        self.pages[new_title] = self.pages.pop(old_title)
        self.pages[old_title] = (100, "#REDIRECT [["+new_title+"]]\n")
        self.writes.append(("move", old_title, new_title))
        if self.fail_after_move:
            self.fail_after_move = False
            raise ConnectionError("Réponse perdue après renommage")

    def write_page(self, *, title, text, summary, tags, expected_user, create_only, base_revision_id):
        self.assert_identity(expected_user)
        assert not create_only and self.pages[title][0] == base_revision_id
        revision = 200 + len(self.writes)
        self.pages[title] = (revision, text)
        self.revisions[revision] = {"revision_id": revision, "parent_id": base_revision_id,
                                    "text": text, "user": self.user, "summary": summary, "tags": tags}
        self.writes.append(("update", title))
        return revision

    def read_revision(self, title, revision):
        return self.revisions[revision]


def publish(tmp_path, request_dir, wiki, *, execute=True):
    return relay.publish_request(tmp_path / "server", request_dir, wiki, "ChatGPT", execute=execute, delay=0)


def test_full_request_and_repeat_are_idempotent(tmp_path):
    directory = tmp_path / "request"
    _, pages = request_fixture(directory)
    wiki = FakeWiki(pages)
    receipt = publish(tmp_path, directory, wiki)
    assert receipt["status"] == "completed"
    assert wiki.pages["Renamed child"][1] == pages["Child"][1]
    assert "page=Renamed child" in wiki.pages["Parent"][1]
    assert relay.redirect_to(wiki.pages["Child"][1], "Renamed child")
    count = len(wiki.writes)
    assert publish(tmp_path, directory, wiki) == receipt
    assert len(wiki.writes) == count and not wiki.opened


def test_preflight_performs_no_mutations(tmp_path):
    directory = tmp_path / "request"
    _, pages = request_fixture(directory)
    wiki = FakeWiki(pages)
    assert publish(tmp_path, directory, wiki, execute=False)["status"] == "ready"
    assert not wiki.writes
    assert not (tmp_path / "server/.state/fr-publication-relay").exists()


def replace_request_text(directory, request, row, before, after):
    for path_key, hash_key, text in (
        ("before_file", "source_sha256", before), ("after_file", "target_sha256", after),
    ):
        (directory / row[path_key]).write_text(text)
        row[hash_key] = relay.digest(text.encode())
    save_request(directory, request)


@pytest.mark.parametrize("before,after", [
    ("{{Argument|citations=Source}}", "{{Argument|résumé=Ajout|citations=Source}}"),
    ("{{Argument|résumé=|citations=Source}}", "{{Argument|résumé=Ajout|citations=Source}}"),
    ("{{Argument|résumé=Ancien}}", "{{Argument|résumé=Nouveau}}"),
    ("{{Argument|résumé=Ancien}}", "{{Argument}}"),
])
@pytest.mark.parametrize("authorization", [None, {"decision": "explicit_user_request"}])
def test_summary_changes_require_specific_permission_before_any_move_or_write(tmp_path, before, after, authorization):
    directory = tmp_path / "request"
    request, pages = request_fixture(directory)
    row = request["pages"][0]
    row["summary_change_authorization"] = authorization
    replace_request_text(directory, request, row, before, after)
    pages["Child"] = (10, before)
    wiki = FakeWiki(pages)
    with pytest.raises(relay.Blocked, match="résumé"):
        publish(tmp_path, directory, wiki)
    assert not wiki.writes
    # Enqueue must reject the same request before touching Git or the server.
    with pytest.raises(relay.Blocked, match="résumé"):
        relay.enqueue(tmp_path, directory, request["request_sha256"])


def test_explicit_summary_restoration_is_allowed_and_comment_matches_actual_diff(tmp_path):
    directory = tmp_path / "request"
    request, pages = request_fixture(directory)
    row = request["pages"][0]
    row["new_title"] = row["old_title"]
    row["summary_change_authorization"] = {
        "decision": "explicit_user_request", "action": "restore",
        "instruction": "Restaure le résumé antérieur de cet argument.",
    }
    before, after = "{{Argument|résumé=Ajout indu|citations=Source}}", "{{Argument|citations=Source}}"
    replace_request_text(directory, request, row, before, after)
    # Keep the second row unchanged: this test only restores a summary.
    parent = request["pages"][1]
    replace_request_text(directory, request, parent, pages["Parent"][1], pages["Parent"][1])
    pages["Child"] = (10, before)
    wiki = FakeWiki(pages)
    assert publish(tmp_path, directory, wiki)["status"] == "completed"
    assert wiki.pages["Child"][1] == after
    summary = next(iter(wiki.revisions.values()))["summary"]
    assert summary == "Restauration du résumé antérieur ; annulation des changements non demandés"
    assert "titres" not in summary and "liens" not in summary


@pytest.mark.parametrize("before,after,expected", [
    ("{{Argument|citations=Ancien}}", "{{Argument|citations=Nouveau}}", "Mise à jour des citations"),
    ("{{Argument|références-sitographiques=Ancien}}", "{{Argument|références-sitographiques=Nouveau}}", "Mise à jour des références"),
    ("{{Débat|introduction=Ancienne}}", "{{Débat|introduction=Nouvelle}}", "Mise à jour de l'introduction"),
])
def test_relay_comments_are_computed_from_changed_fields(tmp_path, before, after, expected):
    directory = tmp_path / "request"
    request, _ = request_fixture(directory)
    row = request["pages"][0]
    replace_request_text(directory, request, row, before, after)
    assert relay.request_editorial_checks(request, directory)[row["page_id"]] == expected
    row["edit_summary"] = "Corrections des titres et liens"
    save_request(directory, request)
    with pytest.raises(relay.Blocked, match="Commentaire"):
        relay.request_editorial_checks(request, directory)


def test_historical_completed_request_is_not_replayed_or_blocked_by_new_scope(tmp_path):
    directory = tmp_path / "request"
    request, pages = request_fixture(directory)
    request["schema"] = "wikidebia-fr-publication-request-1.0"
    row = request["pages"][0]
    before, after = "{{Argument}}", "{{Argument|résumé=Ancien ajout indu}}"
    replace_request_text(directory, request, row, before, after)
    state = relay.state_file(tmp_path / "server", request["request_id"])
    completed = {"request_sha256": request["request_sha256"], "status": "completed"}
    relay.write_json(state, completed)
    wiki = FakeWiki(pages)
    assert publish(tmp_path, directory, wiki) == completed
    assert not wiki.writes and not wiki.opened


def test_pending_legacy_request_cannot_bypass_summary_scope(tmp_path):
    directory = tmp_path / "request"
    request, pages = request_fixture(directory)
    request["schema"] = "wikidebia-fr-publication-request-1.0"
    row = request["pages"][0]
    replace_request_text(directory, request, row, "{{Argument}}", "{{Argument|résumé=Ajout non demandé}}")
    wiki = FakeWiki(pages)
    with pytest.raises(relay.Blocked, match="résumé"):
        publish(tmp_path, directory, wiki)
    assert not wiki.writes


@pytest.mark.parametrize("after", [
    "{{Argument}}",
    "{{Argument|citations={{Citation|citation=Texte réécrit|auteurs=Auteur|lien=https://example.org}}}}",
    "{{Argument|citations={{Citation|citation=Texte original|auteurs=Autre auteur|lien=https://example.org}}}}",
    "{{Argument|citations={{Citation|citation=Texte original|auteurs=Auteur}}}}",
])
def test_existing_citations_cannot_be_removed_or_rewritten_without_permission(tmp_path, after):
    directory = tmp_path / "request"
    request, pages = request_fixture(directory)
    row = request["pages"][0]
    before = "{{Argument|citations={{Citation|citation=Texte original|auteurs=Auteur|lien=https://example.org}}}}"
    replace_request_text(directory, request, row, before, after)
    pages["Child"] = (10, before)
    wiki = FakeWiki(pages)
    with pytest.raises(relay.Blocked, match="citation existante"):
        publish(tmp_path, directory, wiki)
    assert not wiki.writes
    with pytest.raises(relay.Blocked, match="citation existante"):
        relay.enqueue(tmp_path, directory, request["request_sha256"])


def test_citation_restoration_has_a_specific_accurate_edit_comment(tmp_path):
    directory = tmp_path / "request"
    request, pages = request_fixture(directory)
    row = request["pages"][0]
    row["citation_change_authorization"] = {
        "decision":"explicit_user_request", "action":"restore",
        "instruction":"Rétablis les citations supprimées sur cette page.",
    }
    before="{{Argument|résumé=Historique}}"
    after="{{Argument|résumé=Historique|citations={{Citation|citation=Texte original|auteurs=Auteur}}}}"
    replace_request_text(directory, request, row, before, after)
    pages["Child"]=(10,before)
    wiki=FakeWiki(pages)
    assert publish(tmp_path,directory,wiki)["status"]=="completed"
    assert wiki.pages["Renamed child"][1]==after
    comments={revision["text"]:revision["summary"] for revision in wiki.revisions.values()}
    assert comments[after] == "Restauration des citations antérieures ; annulation des retraits non demandés"
    assert "Mise à jour des justifications" in comments.values()


@pytest.mark.parametrize("problem", ("stale_parent", "changed_parent", "collision", "rights", "identity", "tag"))
def test_all_pages_are_checked_before_any_write(tmp_path, problem):
    directory = tmp_path / "request"
    _, pages = request_fixture(directory)
    wiki = FakeWiki(pages)
    if problem == "stale_parent":
        wiki.pages["Parent"] = (12, pages["Parent"][1])
    elif problem == "changed_parent":
        wiki.pages["Parent"] = (11, "{{Argument|résumé=Édition tierce}}\n")
    elif problem == "collision":
        wiki.pages["Renamed child"] = (15, pages["Child"][1])
    elif problem == "rights":
        wiki.rights = {"edit"}
    elif problem == "identity":
        wiki.user = "Other"
    else:
        wiki.tags = set()
    with pytest.raises(relay.Blocked):
        publish(tmp_path, directory, wiki)
    assert not wiki.writes and not wiki.opened


def test_interruption_after_move_resumes_without_duplicate_move(tmp_path):
    directory = tmp_path / "request"
    _, pages = request_fixture(directory)
    wiki = FakeWiki(pages)
    wiki.fail_after_move = True
    with pytest.raises(ConnectionError):
        publish(tmp_path, directory, wiki)
    receipt = publish(tmp_path, directory, wiki)
    assert receipt["status"] == "completed" and receipt["attempt"] == 2
    assert sum(event[0] == "move" for event in wiki.writes) == 1
    assert any(event["operation"] == "move_requested" for event in receipt["events"])


@pytest.mark.parametrize("problem", ("before", "after", "hash", "path", "authorization", "language", "revision", "namespace"))
def test_invalid_requests_are_rejected(tmp_path, problem):
    directory = tmp_path / "request"
    request, pages = request_fixture(directory)
    if problem in {"before", "after"}:
        (directory / problem / "Child.wiki").write_text("tampered")
    elif problem == "hash":
        request["request_sha256"] = "0"*64
        (directory / "request.json").write_text(json.dumps(request))
    else:
        if problem == "path":
            request["pages"][0]["before_file"] = "../outside"
        elif problem == "authorization":
            request["authorization"] = "automatic_merge"
        elif problem == "language":
            request["language"] = "en"
        elif problem == "revision":
            request["pages"][0]["source_revision_id"] = True
        else:
            request["pages"][0]["new_title"] = "User:Renamed child"
        save_request(directory, request)
    wiki = FakeWiki(pages)
    with pytest.raises(relay.Blocked):
        publish(tmp_path, directory, wiki)
    assert not wiki.writes


def test_completed_request_id_cannot_be_reused(tmp_path):
    directory = tmp_path / "request"
    request, pages = request_fixture(directory)
    wiki = FakeWiki(pages)
    publish(tmp_path, directory, wiki)
    request["note"] = "different request"
    save_request(directory, request)
    with pytest.raises(relay.Blocked, match="réécrite"):
        publish(tmp_path, directory, wiki)


def test_queue_transport_uses_git_without_modifying_application_checkout(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "--quiet", str(remote)], check=True)
    repo = tmp_path / "repo"
    repo.mkdir()
    relay.git(repo, "init", "--quiet", "--initial-branch=main")
    relay.git(repo, "config", "user.name", "Test")
    relay.git(repo, "config", "user.email", "test@example.invalid")
    relay.git(repo, "remote", "add", "origin", str(remote))
    (repo / "file").write_text("application remains unchanged\n")
    relay.git(repo, "add", "file")
    relay.git(repo, "commit", "-m", "application")
    head = relay.git(repo, "rev-parse", "HEAD")
    directory = tmp_path / "request"
    request, _ = request_fixture(directory)
    assert relay.enqueue(repo, directory, request["request_sha256"]) == "queued"
    assert relay.enqueue(repo, directory, request["request_sha256"]) == "already_queued"
    second = tmp_path / "second"
    other, _ = request_fixture(second, "cannabis-fr-second")
    assert relay.enqueue(repo, second, other["request_sha256"]) == "queued"
    extracted = relay.fetch_requests(repo, tmp_path / "extracted")
    assert {p.name for p in extracted} == {request["request_id"], other["request_id"]}
    assert all(relay.load_request(path) for path in extracted)
    assert relay.git(repo, "rev-parse", "HEAD") == head
    assert relay.git(repo, "status", "--porcelain") == ""


def test_queue_submission_requires_the_exact_approved_hash(tmp_path):
    directory = tmp_path / "request"
    request_fixture(directory)
    with pytest.raises(relay.Blocked, match="empreinte exacte"):
        relay.enqueue(tmp_path, directory, "wrong")


def test_missing_source_is_not_treated_as_a_successful_rename(tmp_path):
    directory = tmp_path / "request"
    _, pages = request_fixture(directory)
    wiki = FakeWiki(pages)
    wiki.pages["Renamed child"] = wiki.pages.pop("Child")
    with pytest.raises(relay.Blocked, match="Collision"):
        publish(tmp_path, directory, wiki)
    assert not wiki.writes


def test_receipt_symlink_does_not_overwrite_an_existing_file(tmp_path):
    directory = tmp_path / "request"
    _, pages = request_fixture(directory)
    target = tmp_path / "preserve"
    target.write_text("existing data")
    journal = tmp_path / "server/.state/fr-publication-relay"
    journal.mkdir(parents=True)
    (journal / "cannabis-fr-test.json").symlink_to(target)
    wiki = FakeWiki(pages)
    with pytest.raises(relay.Blocked, match="symbolique"):
        publish(tmp_path, directory, wiki)
    assert target.read_text() == "existing data" and not wiki.writes


def test_concurrent_edit_after_move_is_preserved(tmp_path):
    directory = tmp_path / "request"
    _, pages = request_fixture(directory)
    wiki = FakeWiki(pages)
    original_move = wiki.move_page
    def move_and_edit(**kwargs):
        original_move(**kwargs)
        wiki.pages["Parent"] = (40, "{{Argument|résumé=Édition concurrente}}\n")
    wiki.move_page = move_and_edit
    with pytest.raises(relay.Blocked, match="modifiée"):
        publish(tmp_path, directory, wiki)
    assert wiki.pages["Parent"] == (40, "{{Argument|résumé=Édition concurrente}}\n")
    assert sum(event[0] == "update" for event in wiki.writes) == 0


def test_remote_readback_must_confirm_user_tag_and_content(tmp_path):
    directory = tmp_path / "request"
    _, pages = request_fixture(directory)
    wiki = FakeWiki(pages)
    original_read = wiki.read_revision
    wiki.read_revision = lambda title, revision: {**original_read(title, revision), "user": "Other"}
    with pytest.raises(relay.Blocked, match="Relecture"):
        publish(tmp_path, directory, wiki)
    state = json.loads((tmp_path / "server/.state/fr-publication-relay/cannabis-fr-test.json").read_text())
    assert state["status"] == "blocked"


@pytest.mark.parametrize("lag", ("missing_revision", "missing_tag", "missing_summary"))
def test_delayed_revision_metadata_retries_reads_without_repeating_the_edit(tmp_path, lag, monkeypatch):
    directory = tmp_path / "request"
    _, pages = request_fixture(directory)
    wiki = FakeWiki(pages)
    original_read = wiki.read_revision
    reads, sleeps = [], []
    monkeypatch.setattr(relay.time, "sleep", sleeps.append)

    def delayed_read(title, revision):
        reads.append((title, revision))
        actual = original_read(title, revision)
        if len(reads) <= 2:
            if lag == "missing_revision":
                return None
            if lag == "missing_tag":
                return {**actual, "tags": []}
            return {**actual, "summary": ""}
        return actual

    wiki.read_revision = delayed_read
    receipt = publish(tmp_path, directory, wiki)
    assert receipt["status"] == "completed"
    assert len(reads) == 3 and len(set(reads)) == 1
    assert sleeps.count(relay.VERIFICATION_DELAY_SECONDS) == 2
    assert sum(event[0] == "update" for event in wiki.writes) == 1
    assert sum(event[0] == "move" for event in wiki.writes) == 1


@pytest.mark.parametrize("field,value,label", [
    ("revision_id", 999, "identifiant de révision"),
    ("parent_id", 999, "révision parente"),
    ("user", "Other", "auteur"),
    ("summary", "Other summary", "résumé"),
    ("tags", [], "balise chatgpt"),
    ("text", "{{Argument|résumé=Divergence}}", "contenu"),
])
def test_persistent_readback_mismatch_is_bounded_and_preserves_written_revision(tmp_path, field, value, label):
    directory = tmp_path / "request"
    _, pages = request_fixture(directory)
    wiki = FakeWiki(pages)
    original_read = wiki.read_revision
    reads = []

    def divergent_read(title, revision):
        reads.append(revision)
        return {**original_read(title, revision), field: value}

    wiki.read_revision = divergent_read
    with pytest.raises(relay.Blocked, match=label):
        publish(tmp_path, directory, wiki)
    assert len(reads) == relay.VERIFICATION_ATTEMPTS
    assert sum(event[0] == "update" for event in wiki.writes) == 1
    state = json.loads(relay.state_file(tmp_path / "server", "cannabis-fr-test").read_text())
    assert state["status"] == "blocked"
    assert state["events"][-1] == {"operation": "update_written", "title": "Parent", "revision_id": reads[0]}


def interrupt_after_edit(tmp_path, *, legacy):
    directory = tmp_path / "request"
    _, pages = request_fixture(directory)
    wiki = FakeWiki(pages)
    original_read = wiki.read_revision
    wiki.read_revision = lambda title, revision: {**original_read(title, revision), "tags": []}
    with pytest.raises(relay.Blocked, match="balise chatgpt"):
        publish(tmp_path, directory, wiki)
    wiki.read_revision = original_read
    state_path = relay.state_file(tmp_path / "server", "cannabis-fr-test")
    if legacy:
        state = json.loads(state_path.read_text())
        state["events"] = [e for e in state["events"] if e["operation"] != "update_written"]
        state_path.write_text(json.dumps(state))
    return directory, wiki, state_path


@pytest.mark.parametrize("legacy", (False, True))
def test_interrupted_edit_is_verified_and_journaled_without_duplicate_writes(tmp_path, legacy):
    directory, wiki, state_path = interrupt_after_edit(tmp_path, legacy=legacy)
    previous = json.loads(state_path.read_text())
    writes = list(wiki.writes)
    receipt = publish(tmp_path, directory, wiki)
    assert receipt["status"] == "completed" and receipt["attempt"] == 2
    assert wiki.writes == writes
    assert receipt["events"][:len(previous["events"])] == previous["events"]
    assert receipt["events"][-1] == {"operation": "update", "title": "Parent",
                                     "revision_id": wiki.pages["Parent"][0], "recovered": True}


def test_mediawiki_removing_terminal_lf_completes_without_repeated_edit(tmp_path):
    directory = tmp_path / "request"
    _, pages = request_fixture(directory)
    wiki = FakeWiki(pages)
    original_write = wiki.write_page

    def save_without_terminal_lf(**kwargs):
        revision = original_write(**{**kwargs, "text": kwargs["text"].removesuffix("\n")})
        return revision

    wiki.write_page = save_without_terminal_lf
    receipt = publish(tmp_path, directory, wiki)
    assert receipt["status"] == "completed"
    assert not wiki.pages["Parent"][1].endswith("\n")
    writes = list(wiki.writes)
    assert publish(tmp_path, directory, wiki) == receipt
    assert wiki.writes == writes


@pytest.mark.parametrize("legacy", (False, True))
def test_resume_terminal_lf_difference_verifies_existing_revision_without_writing(tmp_path, legacy):
    directory, wiki, state_path = interrupt_after_edit(tmp_path, legacy=legacy)
    revision, text = wiki.pages["Parent"]
    wiki.pages["Parent"] = revision, text.removesuffix("\n")
    wiki.revisions[revision]["text"] = text.removesuffix("\n")
    writes = list(wiki.writes)
    old_events = json.loads(state_path.read_text())["events"]
    receipt = publish(tmp_path, directory, wiki)
    assert receipt["status"] == "completed"
    assert wiki.writes == writes
    assert receipt["events"][:len(old_events)] == old_events
    assert receipt["events"][-1] == {
        "operation": "update", "title": "Parent", "revision_id": revision, "recovered": True,
    }


@pytest.mark.parametrize("field,value", [
    ("user", "Other"), ("parent_id", 999), ("tags", []),
    ("summary", "Autre commentaire"), ("revision_id", 999),
])
def test_terminal_lf_recovery_still_requires_exact_revision_metadata(tmp_path, field, value):
    directory, wiki, _ = interrupt_after_edit(tmp_path, legacy=False)
    revision, text = wiki.pages["Parent"]
    wiki.pages["Parent"] = revision, text.removesuffix("\n")
    wiki.revisions[revision].update(text=text.removesuffix("\n"))
    wiki.revisions[revision][field] = value
    writes = list(wiki.writes)
    with pytest.raises(relay.Blocked, match="Relecture"):
        publish(tmp_path, directory, wiki)
    assert wiki.writes == writes


@pytest.mark.parametrize("change", [
    lambda text: text.replace("page=Renamed child", "page=Other"),
    lambda text: text.replace("|", "\n|", 1),
    lambda text: text.removesuffix("\n") + " ",
    lambda text: text + "\n",
])
def test_terminal_lf_recovery_does_not_accept_other_content_changes(tmp_path, change):
    directory, wiki, _ = interrupt_after_edit(tmp_path, legacy=False)
    revision, text = wiki.pages["Parent"]
    changed = change(text)
    wiki.pages["Parent"] = revision, changed
    wiki.revisions[revision]["text"] = changed
    writes = list(wiki.writes)
    with pytest.raises(relay.Blocked):
        publish(tmp_path, directory, wiki)
    assert wiki.writes == writes


@pytest.mark.parametrize("legacy", (False, True))
@pytest.mark.parametrize("field,value", [("user", "Other"), ("tags", []), ("parent_id", 999)])
def test_resume_cannot_skip_unverified_edit_metadata(tmp_path, legacy, field, value):
    directory, wiki, _ = interrupt_after_edit(tmp_path, legacy=legacy)
    writes = list(wiki.writes)
    original_read = wiki.read_revision
    wiki.read_revision = lambda title, revision: {**original_read(title, revision), field: value}
    with pytest.raises(relay.Blocked, match="Relecture"):
        publish(tmp_path, directory, wiki)
    assert wiki.writes == writes


def test_preflight_of_interrupted_edit_does_not_change_receipt(tmp_path):
    directory, wiki, state_path = interrupt_after_edit(tmp_path, legacy=True)
    previous = state_path.read_bytes()
    writes = list(wiki.writes)
    assert publish(tmp_path, directory, wiki, execute=False)["status"] == "ready"
    assert state_path.read_bytes() == previous and wiki.writes == writes


def test_lost_edit_response_recovers_without_duplicate_write(tmp_path):
    directory = tmp_path / "request"
    _, pages = request_fixture(directory)
    wiki = FakeWiki(pages)
    original_write = wiki.write_page

    def lost_response(**kwargs):
        original_write(**kwargs)
        raise ConnectionError("Réponse perdue après édition")

    wiki.write_page = lost_response
    with pytest.raises(ConnectionError):
        publish(tmp_path, directory, wiki)
    wiki.write_page = original_write
    writes = list(wiki.writes)
    receipt = publish(tmp_path, directory, wiki)
    assert receipt["status"] == "completed" and wiki.writes == writes
    assert receipt["events"][-1]["recovered"] is True


def test_resume_verifies_interrupted_edit_before_publishing_remaining_pages(tmp_path):
    directory = tmp_path / "request"
    request, pages = request_fixture(directory)
    before = "{{Argument|justifications={{Justification|page=Child}}}}\n"
    after = before.replace("page=Child", "page=Renamed child")
    (directory / "before/Remaining.wiki").write_text(before)
    (directory / "after/Remaining.wiki").write_text(after)
    request["pages"].append({"page_id": "Remaining", "old_title": "Remaining", "new_title": "Remaining",
        "source_revision_id": 12, "source_sha256": relay.digest(before.encode()),
        "target_sha256": relay.digest(after.encode()), "before_file": "before/Remaining.wiki",
        "after_file": "after/Remaining.wiki"})
    save_request(directory, request)
    wiki = FakeWiki({**pages, "Remaining": (12, before)})
    original_read = wiki.read_revision
    wiki.read_revision = lambda title, revision: {**original_read(title, revision), "tags": []}
    with pytest.raises(relay.Blocked):
        publish(tmp_path, directory, wiki)
    writes = list(wiki.writes)
    with pytest.raises(relay.Blocked):
        publish(tmp_path, directory, wiki)
    assert wiki.writes == writes and wiki.pages["Remaining"] == (12, before)
    wiki.read_revision = original_read
    receipt = publish(tmp_path, directory, wiki)
    assert receipt["status"] == "completed"
    assert wiki.pages["Remaining"][1] == after
    assert wiki.writes == writes + [("update", "Remaining")]


def test_worker_does_not_retry_editorial_conflicts_without_explicit_request(tmp_path, monkeypatch):
    import contextlib
    directory = tmp_path / "cannabis-fr-test"
    _, pages = request_fixture(directory)
    wiki = FakeWiki(pages)
    wiki.pages["Parent"] = (12, pages["Parent"][1])
    root = tmp_path / "server"
    monkeypatch.setattr(relay, "git", lambda root, *args: "main" if args[0] == "symbolic-ref" else "")
    monkeypatch.setattr(relay, "deployment_lock", lambda root: contextlib.nullcontext())
    monkeypatch.setattr(relay, "fetch_requests", lambda root, destination: [directory])
    monkeypatch.setattr(relay, "build_adapter", lambda root: (wiki, "ChatGPT"))
    with pytest.raises(relay.Blocked):
        relay.work_once(root, execute=True)
    wiki.pages["Parent"] = pages["Parent"]
    assert relay.work_once(root, execute=True) == []
    assert not wiki.writes
    assert relay.work_once(root, execute=True, retry="cannabis-fr-test")[0]["status"] == "completed"


def test_request_branch_cannot_supply_symlinks(tmp_path, monkeypatch):
    monkeypatch.setattr(relay, "git", lambda root, *args: "0"*40)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess([], 0))
    tree = b"120000 blob " + b"0"*40 + b"\trequests/cannabis-fr-test/before/link\0"
    monkeypatch.setattr(subprocess, "check_output", lambda *args, **kwargs: tree)
    with pytest.raises(relay.Blocked, match="fichiers de données"):
        relay.fetch_requests(tmp_path, tmp_path / "extracted")
    assert not (tmp_path / "extracted").exists()
