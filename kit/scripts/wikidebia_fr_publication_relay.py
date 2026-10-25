#!/usr/bin/env python3
"""Explicit French publication requests transported as data through Git."""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import time


BRANCH = "wiki-fr-publication"
SCHEMA = "wikidebia-fr-publication-request-1.2"
SUPPORTED_SCHEMAS = {SCHEMA, "wikidebia-fr-publication-request-1.1", "wikidebia-fr-publication-request-1.0"}
SITE = "https://fr.wikidebates.org"
VERIFICATION_ATTEMPTS = 8
VERIFICATION_DELAY_SECONDS = 2


class Blocked(RuntimeError):
    pass


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def target_content_matches(text: str, row: dict) -> bool:
    """Match the signed target, allowing one terminal LF removed on save.

    Request files retain their exact signed hashes. Only remote target reads
    accept this observed MediaWiki normalization; source preconditions and all
    revision metadata remain strict. Do not strip other whitespace or newlines.
    """
    expected = row["target_sha256"]
    return digest(text.encode()) == expected or (
        not text.endswith("\n") and digest((text + "\n").encode()) == expected
    )


def request_hash(request: dict) -> str:
    body = {k: v for k, v in request.items() if k != "request_sha256"}
    return digest(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def state_file(root: Path, request_id: str) -> Path:
    path = root / ".state/fr-publication-relay" / (request_id+".json")
    if any(p.is_symlink() for p in (root / ".state", path.parent, path)):
        raise Blocked("Le journal de publication ne doit pas être un lien symbolique")
    return path


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def safe_file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str):
        raise Blocked("Chemin de demande invalide")
    path = PurePosixPath(relative)
    if path.is_absolute() or not path.parts or ".." in path.parts or "\\" in relative:
        raise Blocked("Chemin de demande non portable")
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise Blocked("Lien symbolique interdit dans une demande")
    if not current.is_file() or current.stat().st_size > 2_000_000:
        raise Blocked("Fichier de demande absent ou trop volumineux")
    return current


def load_request(root: Path) -> dict:
    if root.is_symlink():
        raise Blocked("Dossier de demande symbolique interdit")
    request = json.loads(safe_file(root, "request.json").read_text(encoding="utf-8"))
    if request.get("schema") not in SUPPORTED_SCHEMAS or request.get("language") != "fr" or request.get("site") != SITE:
        raise Blocked("Seules les demandes françaises Wikidébates sont acceptées")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,79}", request.get("request_id", "")):
        raise Blocked("Identifiant de demande invalide")
    if request.get("authorization") != "explicit_user_request":
        raise Blocked("Autorisation explicite absente")
    if request.get("request_sha256") != request_hash(request):
        raise Blocked("Empreinte de demande divergente")
    pages = request.get("pages")
    if not isinstance(pages, list) or not 1 <= len(pages) <= 200:
        raise Blocked("Nombre de pages invalide")
    for field in ("old_title", "new_title", "page_id"):
        values = [row.get(field) for row in pages]
        if any(not isinstance(v, str) or not v for v in values) or len(values) != len(set(values)):
            raise Blocked(f"Champ de page absent ou dupliqué : {field}")
    for row in pages:
        if type(row.get("source_revision_id")) is not int or row["source_revision_id"] <= 0:
            raise Blocked("Révision source absente")
        for field in ("old_title", "new_title"):
            title = row[field]
            if len(title.encode()) > 255 or re.search(r"[\x00-\x1f\x7f\[\]{}<>|#]", title):
                raise Blocked("Titre MediaWiki invalide")
        for field, expected in (("before_file", "source_sha256"), ("after_file", "target_sha256")):
            raw = safe_file(root, row[field]).read_bytes()
            if digest(raw) != row[expected]:
                raise Blocked("Empreinte de contenu divergente")
            if not re.match(r"\s*\{\{(?:Argument|Débat)\s*(?:\||\}\})", raw.decode("utf-8")):
                raise Blocked("Le contenu doit être une page Argument ou Débat")
    return request


def redirect_to(text: str, target: str) -> bool:
    match = re.fullmatch(r"\s*#(?:REDIRECT|REDIRECTION)\s*\[\[([^\]]+)\]\]\s*", text, re.I)
    return bool(match and match.group(1).replace("_", " ") == target.replace("_", " "))


def inspect_page(adapter, row: dict) -> dict:
    old, new = row["old_title"], row["new_title"]
    exists, revision, text = adapter.read_page(old)
    if old != new:
        target_exists, target_revision, target_text = adapter.read_page(new)
        if target_exists:
            if not exists or not redirect_to(text, new):
                raise Blocked(f"Collision de titre : {new}")
            if digest(target_text.encode()) != row["source_sha256"] and not target_content_matches(target_text, row):
                raise Blocked(f"Cible modifiée : {new}")
            return {"title": new, "revision": target_revision, "text": target_text, "move": False}
    if not exists or revision != row["source_revision_id"] or digest(text.encode()) != row["source_sha256"]:
        if old == new and exists and target_content_matches(text, row):
            return {"title": old, "revision": revision, "text": text, "move": False}
        raise Blocked(f"Page modifiée depuis la préparation : {old}")
    return {"title": old, "revision": revision, "text": text, "move": old != new}


def request_editorial_checks(request: dict, request_dir: Path) -> dict[str, str]:
    from wikidebia_update import (
        UpdateError, assert_summary_change_authorized, assert_citation_change_authorized, changed_top_level_parameters,
        content_diff_edit_summary,
    )
    summaries = {}
    for row in request["pages"]:
        before = safe_file(request_dir, row["before_file"]).read_text(encoding="utf-8")
        after = safe_file(request_dir, row["after_file"]).read_text(encoding="utf-8")
        page_type = "debate" if re.match(r"\s*\{\{Débat\s*(?:\||\}\})", before) else "argument"
        try:
            assert_summary_change_authorized(
                before, after, "fr", page_type, row.get("summary_change_authorization"),
            )
            assert_citation_change_authorized(before, after, row.get("citation_change_authorization"))
            summaries[row["page_id"]] = content_diff_edit_summary(before, after, "fr", page_type)
            if (isinstance(row.get("summary_change_authorization"), dict)
                    and row["summary_change_authorization"].get("action") == "restore"
                    and changed_top_level_parameters(before, after, "fr", page_type) == ["résumé"]):
                summaries[row["page_id"]] = "Restauration du résumé antérieur ; annulation des changements non demandés"
            if (isinstance(row.get("citation_change_authorization"), dict)
                    and row["citation_change_authorization"].get("action") == "restore"
                    and changed_top_level_parameters(before, after, "fr", page_type) == ["citations"]):
                summaries[row["page_id"]] = "Restauration des citations antérieures ; annulation des retraits non demandés"
        except UpdateError as exc:
            raise Blocked(f"{row['new_title']} : {exc}") from exc
        if "edit_summary" in row and row["edit_summary"] != summaries[row["page_id"]]:
            raise Blocked(f"Commentaire d’édition divergent du contenu : {row['new_title']}")
    return summaries


def verify_update(adapter, row: dict, revision: int, base_revision: int, expected_user: str, summary: str) -> None:
    # Change tags and other revision metadata may briefly lag behind the edit.
    # Retry reads of the exact revision, never the edit itself.
    for attempt in range(VERIFICATION_ATTEMPTS):
        actual = adapter.read_revision(row["new_title"], revision)
        if not actual:
            mismatches = ["révision introuvable"]
        else:
            checks = {
                "identifiant de révision": actual.get("revision_id") == revision,
                "révision parente": actual.get("parent_id") == base_revision,
                "auteur": actual.get("user") == expected_user,
                "résumé": actual.get("summary") == summary,
                "balise chatgpt": "chatgpt" in (actual.get("tags") or []),
                "contenu": target_content_matches(actual.get("text", ""), row),
            }
            mismatches = [name for name, matches in checks.items() if not matches]
        if not mismatches:
            return
        if attempt + 1 < VERIFICATION_ATTEMPTS:
            time.sleep(VERIFICATION_DELAY_SECONDS)
    raise Blocked(f"Relecture de la modification divergente : {row['new_title']} "
                  f"(révision {revision}, après {VERIFICATION_ATTEMPTS} relectures) : {', '.join(mismatches)}")


def pending_updates(events: list[dict]) -> dict[str, dict]:
    pending = {}
    for event in events:
        operation, title = event.get("operation"), event.get("title")
        if operation == "update_requested":
            pending[title] = dict(event)
        elif operation == "update_written" and title in pending:
            pending[title]["revision_id"] = event["revision_id"]
        elif operation == "update":
            pending.pop(title, None)
    return pending


def publish_request(root: Path, request_dir: Path, adapter, expected_user: str, *, execute: bool = False, delay: float = 0.5) -> dict:
    request = load_request(request_dir)
    state_path = state_file(root, request["request_id"])
    previous = json.loads(state_path.read_text()) if state_path.is_file() else {}
    if previous and previous.get("request_sha256") != request["request_sha256"]:
        raise Blocked("Une demande existante ne peut pas être réécrite ; utiliser un nouvel identifiant")
    if previous.get("status") == "completed":
        return previous
    receipt = {"request_id": request["request_id"], "request_sha256": request["request_sha256"],
               "site": SITE, "expected_user": expected_user, "status": "preflight", "events": list(previous.get("events") or []),
               "attempt": int(previous.get("attempt", 0)) + 1,
               "started_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    try:
        # Completed immutable requests are skipped above, including historical
        # requests created before this stricter editorial scope existed.
        summaries = request_editorial_checks(request, request_dir)
        adapter.open_language("fr", expected_user)
        adapter.assert_identity(expected_user)
        required = {"edit"}
        if any(row["old_title"] != row["new_title"] for row in request["pages"]):
            required.add("move")
        if not required <= adapter.user_rights():
            raise Blocked("Droits MediaWiki insuffisants")
        if "chatgpt" not in adapter.available_change_tags():
            raise Blocked("Balise chatgpt indisponible")
        # Validate the complete request, including interrupted writes, before
        # the first new mutation. Older receipts only recorded update_requested.
        pending = pending_updates(receipt["events"])
        recovered = []
        for row in request["pages"]:
            adapter.assert_main_namespace(row["old_title"])
            adapter.assert_main_namespace(row["new_title"])
            current = inspect_page(adapter, row)
            interrupted = pending.get(row["new_title"])
            if interrupted:
                at_target = target_content_matches(current["text"], row)
                if interrupted.get("revision_id") is not None and not at_target:
                    raise Blocked(f"Contenu modifié après une écriture interrompue : {row['new_title']}")
                if at_target:
                    revision = interrupted.get("revision_id", current["revision"])
                    verify_update(adapter, row, revision, interrupted["base_revision_id"], expected_user, summaries[row["page_id"]])
                    recovered.append({"operation": "update", "title": row["new_title"],
                                      "revision_id": revision, "recovered": True})
        if not execute:
            return {**receipt, "status": "ready", "remote_write_performed": False}
        receipt["events"].extend(recovered)
        receipt["status"] = "running"
        write_json(state_path, receipt)
        for row in sorted(request["pages"], key=lambda r: r["old_title"] == r["new_title"]):
            current = inspect_page(adapter, row)
            if not current["move"]:
                continue
            adapter.assert_identity(expected_user)
            summary = f"Correction du titre : [[{row['old_title']}]] → [[{row['new_title']}]]"
            receipt["events"].append({"operation": "move_requested", "old_title": row["old_title"], "title": row["new_title"]})
            write_json(state_path, receipt)
            adapter.move_page(old_title=row["old_title"], new_title=row["new_title"], reason=summary,
                              expected_user=expected_user, leave_redirect=True)
            current = inspect_page(adapter, row)
            if current["move"]:
                raise Blocked("Renommage non confirmé")
            receipt["events"].append({"operation": "move", "old_title": row["old_title"], "title": row["new_title"]})
            write_json(state_path, receipt)
            time.sleep(delay)
        for row in request["pages"]:
            current = inspect_page(adapter, row)
            desired = safe_file(request_dir, row["after_file"]).read_text(encoding="utf-8")
            if target_content_matches(current["text"], row):
                continue
            summary = summaries[row["page_id"]]
            adapter.assert_identity(expected_user)
            receipt["events"].append({"operation": "update_requested", "title": row["new_title"], "base_revision_id": current["revision"]})
            write_json(state_path, receipt)
            revision = adapter.write_page(title=row["new_title"], text=desired, summary=summary,
                tags=["chatgpt"], expected_user=expected_user, create_only=False, base_revision_id=current["revision"])
            receipt["events"].append({"operation": "update_written", "title": row["new_title"],
                                      "revision_id": revision})
            write_json(state_path, receipt)
            verify_update(adapter, row, revision, current["revision"], expected_user, summary)
            receipt["events"].append({"operation": "update", "title": row["new_title"], "revision_id": revision})
            write_json(state_path, receipt)
            time.sleep(delay)
        for row in request["pages"]:
            current = inspect_page(adapter, row)
            if current["move"] or not target_content_matches(current["text"], row):
                raise Blocked("État final divergent")
        receipt.update(status="completed", completed_at=dt.datetime.now(dt.timezone.utc).isoformat())
        write_json(state_path, receipt)
        return receipt
    except Exception as exc:
        if execute:
            receipt.update(status="blocked" if isinstance(exc, Blocked) else "failed", error=f"{type(exc).__name__}: {exc}")
            write_json(state_path, receipt)
        raise
    finally:
        adapter.close_language()


def build_adapter(root: Path):
    from wikidebia_publish import PywikibotAdapter
    from wikidebia_update import UpdateAdapter

    class FrenchAdapter(UpdateAdapter):
        def assert_main_namespace(self, title):
            import pywikibot
            if pywikibot.Page(self.base.site, title).namespace() != 0:
                raise Blocked("Seules les pages de contenu sont autorisées")

        def move_page(self, *, old_title, new_title, reason, expected_user, leave_redirect):
            if not leave_redirect:
                raise Blocked("Les redirections doivent être conservées")
            self.assert_identity(expected_user)
            site = self.base.site
            return site.simple_request(**{
                "action": "move", "from": old_title, "to": new_title,
                "reason": reason, "movetalk": 1, "tags": "chatgpt",
                "assert": "user", "assertuser": expected_user,
                "token": site.tokens["csrf"],
            }).submit()

    path = root / "config/wikidebia.local.json"
    if not path.is_file():
        path = root / "config/wikidebia.example.json"
    config = json.loads(path.read_text())
    user = (config.get("expected_users") or {}).get("fr")
    if not isinstance(user, str) or not user:
        raise Blocked("Compte français attendu non configuré")
    if not (root / "private/pywikibot/user-config.py").is_file():
        raise Blocked("Configuration Pywikibot absente")
    adapter = FrenchAdapter(PywikibotAdapter("wikidebates", {"fr": "fr"}, root / "private/pywikibot",
                                             root / "kit/families/wikidebates_family.py"))
    return adapter, user


@contextlib.contextmanager
def deployment_lock(root: Path):
    path = Path(git(root, "rev-parse", "--path-format=absolute", "--git-path", "wikidebia-deploy.lock"))
    with path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Blocked("Déploiement ou publication déjà en cours")
        yield


def fetch_requests(root: Path, destination: Path) -> list[Path]:
    # Never check out or execute anything from the request branch.
    found = subprocess.run(["git", "-C", str(root), "ls-remote", "--exit-code", "origin", "refs/heads/"+BRANCH], capture_output=True)
    if found.returncode == 2:
        return []
    if found.returncode:
        raise Blocked("Lecture de la branche de demandes impossible")
    git(root, "fetch", "--no-tags", "origin", "refs/heads/"+BRANCH)
    commit = git(root, "rev-parse", "FETCH_HEAD^{commit}")
    listing = subprocess.check_output(["git", "-C", str(root), "ls-tree", "-rz", commit])
    if len(listing) > 2_000_000 or listing.count(b"\0") > 5000:
        raise Blocked("Trop de fichiers dans la branche de demandes")
    total = 0
    request_ids = set()
    for entry in listing.split(b"\0"):
        if not entry:
            continue
        header, raw_path = entry.split(b"\t", 1)
        mode, kind, oid = header.decode().split()
        relative = raw_path.decode("utf-8")
        path = PurePosixPath(relative)
        if (mode != "100644" or kind != "blob" or len(path.parts) < 3 or path.parts[0] != "requests"
                or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,79}", path.parts[1]) or ".." in path.parts or "\\" in relative):
            raise Blocked("La branche de demandes doit contenir uniquement des fichiers de données requests/IDENTIFIANT/")
        size = int(git(root, "cat-file", "-s", oid))
        total += size
        if size > 2_000_000 or total > 50_000_000 or (path.parts[1] not in request_ids and len(request_ids) >= 200):
            raise Blocked("File de demandes trop volumineuse")
        payload = subprocess.check_output(["git", "-C", str(root), "cat-file", "blob", oid])
        target = destination.joinpath(*path.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        request_ids.add(path.parts[1])
    return [destination / "requests" / name for name in sorted(request_ids)]


def enqueue(root: Path, request_dir: Path, confirmation: str) -> str:
    request = load_request(request_dir)
    if confirmation != request["request_sha256"]:
        raise Blocked("L'envoi exige l'empreinte exacte de la demande approuvée")
    request_editorial_checks(request, request_dir)
    remote = git(root, "remote", "get-url", "origin")
    identity = re.fullmatch(r"(.+) <([^<>]+)> \d+ [+-]\d{4}", git(root, "var", "GIT_AUTHOR_IDENT"))
    if not identity:
        raise Blocked("Identité Git non configurée")
    with tempfile.TemporaryDirectory(prefix="wikidebia-fr-enqueue-") as directory:
        checkout = Path(directory)
        git(checkout, "init", "--quiet", "--initial-branch="+BRANCH)
        git(checkout, "remote", "add", "origin", remote)
        found = subprocess.run(["git", "-C", str(checkout), "ls-remote", "--exit-code", "origin", "refs/heads/"+BRANCH], capture_output=True)
        if found.returncode == 0:
            fetch_requests(checkout, checkout)
            # Preserve the queue parent/index without checking out untrusted files.
            git(checkout, "read-tree", "FETCH_HEAD")
            git(checkout, "update-ref", "HEAD", git(checkout, "rev-parse", "FETCH_HEAD"))
        elif found.returncode != 2:
            raise Blocked("Accès à la file de publication impossible")
        target = checkout / "requests" / request["request_id"]
        if target.exists():
            existing = load_request(target)
            if existing["request_sha256"] != confirmation:
                raise Blocked("Identifiant de demande déjà utilisé")
            return "already_queued"
        paths = {"request.json"}
        for row in request["pages"]:
            paths.update((row["before_file"], row["after_file"]))
        for relative in paths:
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(safe_file(request_dir, relative).read_bytes())
        git(checkout, "config", "user.name", identity.group(1))
        git(checkout, "config", "user.email", identity.group(2))
        git(checkout, "add", "--", "requests/"+request["request_id"])
        git(checkout, "commit", "-m", "Publication française explicite : "+request["request_id"])
        # A normal push preserves concurrent requests and refuses divergent tips.
        git(checkout, "push", "origin", "HEAD:refs/heads/"+BRANCH)
    return "queued"


def work_once(root: Path, *, execute: bool, retry: str | None = None) -> list[dict]:
    if git(root, "symbolic-ref", "--short", "HEAD") != "main" or git(root, "status", "--porcelain", "--untracked-files=all"):
        raise Blocked("Le checkout Debian doit être propre et sur main")
    results = []
    with deployment_lock(root), tempfile.TemporaryDirectory(prefix="wikidebia-fr-requests-") as directory:
        requests = fetch_requests(root, Path(directory))
        for request_dir in requests:
            request = load_request(request_dir)
            if request_dir.name != request["request_id"]:
                raise Blocked("Identifiant du dossier divergent")
            if retry and retry != request["request_id"]:
                continue
            state = state_file(root, request["request_id"])
            previous = json.loads(state.read_text()) if state.is_file() else {}
            if previous and previous.get("request_sha256") != request["request_sha256"]:
                raise Blocked("Une demande déjà observée a été réécrite")
            if previous.get("status") in {"completed", "blocked"} and retry != request["request_id"]:
                continue
            adapter, user = build_adapter(root)
            results.append(publish_request(root, request_dir, adapter, user, execute=execute))
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description="Relais explicite de publication française via Git")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--execute", action="store_true", help="Exécuter les demandes explicites de la branche dédiée")
    parser.add_argument("--retry", help="Retenter explicitement une demande bloquée")
    parser.add_argument("--enqueue", type=Path, help="Envoyer un dossier de demande explicitement approuvée")
    parser.add_argument("--confirm-request-sha256")
    args = parser.parse_args(argv)
    os.umask(0o077)
    if args.enqueue:
        if args.execute or args.retry or not args.confirm_request_sha256:
            raise Blocked("L'envoi exige seulement --enqueue et --confirm-request-sha256")
        print(enqueue(args.root.resolve(), args.enqueue.resolve(), args.confirm_request_sha256))
        return 0
    results = work_once(args.root.resolve(), execute=args.execute, retry=args.retry)
    for receipt in results:
        print(f"{receipt['request_id']} : {receipt['status']}")
    if not results:
        print("Aucune nouvelle demande de publication française.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Publication française arrêtée : {error}", file=__import__('sys').stderr)
        raise SystemExit(2)
