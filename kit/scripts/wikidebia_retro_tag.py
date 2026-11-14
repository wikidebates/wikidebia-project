from __future__ import annotations

from wikidebia_release_info import KIT_VERSION

import argparse
import datetime as dt
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Iterable

from wikidebia_publish import PywikibotAdapter

TAG = "translated-fr"
BASE_TAG = "chatgpt"
LANGUAGE = "en"
PLAN_VERSION = "wikidebia-retro-tag-plan-1.0"
RECEIPT_VERSION = "wikidebia-retro-tag-receipt-1.0"


class RetroTagError(RuntimeError):
    pass


def sha_object(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def normalize_wikicode(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")


def sha_text(text: str) -> str:
    return hashlib.sha256(normalize_wikicode(text).encode("utf-8")).hexdigest()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def timestamp() -> str:
    return dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RetroTagError(f"JSON illisible : {path}") from exc
    if not isinstance(value, dict):
        raise RetroTagError(f"Objet JSON attendu : {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def verify_signed_object(value: dict[str, Any], field: str, label: str) -> None:
    copy = dict(value)
    claimed = copy.pop(field, None)
    if not claimed or claimed != sha_object(copy):
        raise RetroTagError(f"Empreinte {label} divergente")


def chunks(values: list[int], size: int = 50) -> Iterable[list[int]]:
    for offset in range(0, len(values), size):
        yield values[offset:offset + size]


class PywikibotTagAdapter:
    def __init__(self, *, family: str, code: str, pywikibot_dir: Path, family_file: Path, expected_user: str) -> None:
        self.family = family
        self.code = code
        self.pywikibot_dir = pywikibot_dir.expanduser().resolve()
        self.family_file = family_file.expanduser().resolve()
        self.expected_user = expected_user
        self.site: Any | None = None
        self._authentication_adapter: PywikibotAdapter | None = None

    def open(self) -> None:
        adapter = PywikibotAdapter(
            self.family,
            {self.code: self.code},
            self.pywikibot_dir,
            self.family_file,
        )
        try:
            adapter.open_language(self.code, self.expected_user)
        except Exception as exc:
            raise RetroTagError(str(exc)) from exc
        self._authentication_adapter = adapter
        self.site = adapter.site

    def close(self) -> None:
        if self._authentication_adapter is not None:
            self._authentication_adapter.close_language()
        self._authentication_adapter = None
        self.site = None

    def _request(self, **params: Any) -> dict[str, Any]:
        if self.site is None:
            raise RetroTagError("Site non ouvert")
        return self.site.simple_request(**params).submit()

    def assert_preflight(self, tag: str) -> dict[str, Any]:
        rights_data = self._request(action="query", meta="userinfo", uiprop="rights")
        rights = set(((rights_data.get("query") or {}).get("userinfo") or {}).get("rights") or [])
        if "changetags" not in rights:
            raise RetroTagError("Le compte actif ne possède pas le droit MediaWiki changetags")
        continuation: dict[str, Any] = {}
        row: dict[str, Any] | None = None
        while True:
            data = self._request(action="query", list="tags", tglimit="max", tgprop="active|defined|source", **continuation)
            for candidate in ((data.get("query") or {}).get("tags") or []):
                if str(candidate.get("name") or "") == tag:
                    row = dict(candidate)
                    break
            if row is not None or not data.get("continue"):
                break
            continuation = data["continue"]
        if row is None:
            raise RetroTagError(f"Balise MediaWiki introuvable : {tag}")
        sources = row.get("source") or []
        if isinstance(sources, str):
            sources = [sources]
        active = ("active" in row) or row.get("active") is True
        defined = ("defined" in row) or row.get("defined") is True
        if not active or not defined or "manual" not in {str(value) for value in sources}:
            raise RetroTagError(
                f"La balise {tag} doit être active, définie et manuelle pour pouvoir être ajoutée rétroactivement"
            )
        return {"rights": sorted(rights), "tag": row}

    def read_revisions(self, revision_ids: list[int]) -> dict[int, dict[str, Any]]:
        output: dict[int, dict[str, Any]] = {}
        for batch in chunks(revision_ids, 50):
            data = self._request(
                action="query",
                prop="revisions",
                revids="|".join(str(value) for value in batch),
                rvprop="ids|content|comment|tags|user|timestamp",
                rvslots="main",
            )
            for page in ((data.get("query") or {}).get("pages") or {}).values():
                title = str(page.get("title") or "")
                for revision in page.get("revisions") or []:
                    revid = int(revision.get("revid") or 0)
                    if revid <= 0:
                        continue
                    slot = (revision.get("slots") or {}).get("main") or {}
                    text = slot.get("content", slot.get("*", revision.get("*", ""))) or ""
                    output[revid] = {
                        "revision_id": revid,
                        "parent_id": int(revision.get("parentid") or 0),
                        "title": title,
                        "text": str(text),
                        "summary": str(revision.get("comment") or ""),
                        "tags": list(revision.get("tags") or []),
                        "user": str(revision.get("user") or ""),
                        "timestamp": str(revision.get("timestamp") or ""),
                    }
        return output

    def read_first_revision(self, title: str) -> dict[str, Any] | None:
        data = self._request(
            action="query",
            prop="revisions",
            titles=title,
            rvprop="ids|content|comment|tags|user|timestamp",
            rvslots="main",
            rvdir="newer",
            rvlimit=1,
        )
        pages = ((data.get("query") or {}).get("pages") or {})
        for page in pages.values():
            page_title = str(page.get("title") or "")
            revisions = page.get("revisions") or []
            if not revisions:
                continue
            revision = revisions[0]
            revid = int(revision.get("revid") or 0)
            if revid <= 0:
                return None
            slot = (revision.get("slots") or {}).get("main") or {}
            content = slot.get("content", slot.get("*", revision.get("*", ""))) or ""
            return {
                "revision_id": revid,
                "parent_id": int(revision.get("parentid") or 0),
                "title": page_title,
                "text": str(content),
                "summary": str(revision.get("comment") or ""),
                "tags": list(revision.get("tags") or []),
                "user": str(revision.get("user") or ""),
                "timestamp": str(revision.get("timestamp") or ""),
            }
        return None

    def add_tag(self, revision_ids: list[int], tag: str) -> None:
        if self.site is None:
            raise RetroTagError("Site non ouvert")
        if not revision_ids:
            return
        for batch in chunks(revision_ids, 50):
            self._request(
                action="tag",
                revid="|".join(str(value) for value in batch),
                add=tag,
                token=self.site.tokens["csrf"],
                **{"assert": "user", "assertuser": self.expected_user},
            )


def expected_summary(fr_title: str) -> str:
    return f"Translation of the French page: [[:fr:{fr_title}|{fr_title}]]"


def legacy_expected_summary(fr_title: str) -> str:
    # Compatibility for translations published before norm 1.2.57.
    return f"Translation of the French page [[:fr:{fr_title}|{fr_title}]]"


def source_titles(manifest: dict[str, Any]) -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    for row in manifest.get("pages") or []:
        if str(row.get("language") or "") != "fr":
            continue
        key = (str(row.get("page_id") or ""), str(row.get("page_type") or ""))
        title = str(row.get("canonical_title") or "").strip()
        if key[0] and key[1] and title:
            if key in result:
                raise RetroTagError(f"Page française source dupliquée : {key[0]} / {key[1]}")
            result[key] = title
    return result


def load_published_state(project_root: Path, debate_id: str) -> tuple[Path, dict[str, Any]]:
    path = project_root / ".state" / "published" / debate_id / LANGUAGE / "latest.json"
    if not path.is_file():
        raise RetroTagError(f"État publié anglais introuvable : {path.relative_to(project_root)}")
    state = read_json(path)
    verify_signed_object(state, "state_sha256", "de l’état publié")
    if state.get("debate_id") != debate_id or state.get("language") != LANGUAGE:
        raise RetroTagError("État publié rattaché à un autre débat ou une autre langue")
    pages = state.get("pages") or []
    if not pages:
        raise RetroTagError("L’état publié anglais ne contient aucune page")
    ids = [str(row.get("page_id") or "") for row in pages]
    if len(ids) != len(set(ids)):
        raise RetroTagError("page_id dupliqué dans l’état publié anglais")
    return path, state


def build_plan(
    *,
    project_root: Path,
    debate_id: str,
    adapter: PywikibotTagAdapter,
    expected_user: str,
) -> dict[str, Any]:
    state_path, state = load_published_state(project_root, debate_id)
    manifest_path = project_root / "corpus" / debate_id / "manifest.json"
    if not manifest_path.is_file():
        raise RetroTagError(f"Manifest du corpus introuvable : {manifest_path.relative_to(project_root)}")
    manifest = read_json(manifest_path)
    if manifest.get("debate_id") != debate_id:
        raise RetroTagError("Manifest rattaché à un autre débat")
    if str(((manifest.get("translation_status") or {}).get("en") or "")) not in {"ready", "published"}:
        raise RetroTagError("Le corpus n’atteste pas une traduction anglaise ready/published")
    fr_titles = source_titles(manifest)
    preflight = adapter.assert_preflight(TAG)

    pages = list(state.get("pages") or [])
    revision_ids = [int(row.get("revision_id") or 0) for row in pages]
    if any(value <= 0 for value in revision_ids):
        raise RetroTagError("Révision invalide dans l’état publié anglais")
    observed = adapter.read_revisions(revision_ids)
    operations: list[dict[str, Any]] = []
    for row in pages:
        page_id = str(row.get("page_id") or "")
        page_type = str(row.get("page_type") or "")
        title = str(row.get("canonical_title") or "")
        state_revision_id = int(row.get("revision_id") or 0)
        fr_title = fr_titles.get((page_id, page_type))
        expected_state_sha = str(row.get("content_sha256") or "")
        op: dict[str, Any] = {
            "page_id": page_id,
            "page_type": page_type,
            "title": title,
            "revision_id": state_revision_id,
            "published_state_revision_id": state_revision_id,
            "source_fr_title": fr_title,
            "expected_summary": expected_summary(fr_title) if fr_title else None,
            "accepted_summaries": ([expected_summary(fr_title), legacy_expected_summary(fr_title)] if fr_title else []),
            "expected_content_sha256": expected_state_sha,
            "published_state_content_sha256": expected_state_sha,
            "expected_user": expected_user,
            "required_existing_tag": BASE_TAG,
            "tag_to_add": TAG,
            "revision_resolution": "published_state",
        }
        state_revision = observed.get(state_revision_id)
        blockers: list[str] = []
        if not fr_title:
            blockers.append("source_fr_missing")
        if state_revision is None:
            blockers.append("revision_missing")
        else:
            if state_revision.get("title") != title:
                blockers.append("title_mismatch")
            if sha_text(str(state_revision.get("text") or "")) != expected_state_sha:
                blockers.append("content_mismatch")

        # The published-state receipt records the revision that represented the
        # page at the end of publication. A secondary automated edit can
        # legitimately make that revision newer than the creation itself.
        # In that case resolve the immutable first revision from page history,
        # while retaining the published-state revision as the provenance anchor.
        candidate = state_revision
        if state_revision is not None and state_revision.get("parent_id") != 0 and not blockers:
            candidate = adapter.read_first_revision(title)
            if candidate is None:
                blockers.append("creation_revision_missing")
            else:
                op["revision_resolution"] = "page_creation_history"
                op["revision_id"] = int(candidate.get("revision_id") or 0)
                op["expected_content_sha256"] = sha_text(str(candidate.get("text") or ""))
                op["published_state_observed_tags"] = sorted({str(value) for value in (state_revision.get("tags") or [])})
                op["published_state_observed_timestamp"] = state_revision.get("timestamp")

        if candidate is not None:
            if candidate.get("title") != title:
                blockers.append("creation_title_mismatch" if op["revision_resolution"] == "page_creation_history" else "title_mismatch")
            if candidate.get("parent_id") != 0:
                blockers.append("not_creation_revision")
            if candidate.get("user") != expected_user:
                blockers.append("creator_mismatch")
            if fr_title and candidate.get("summary") not in set(op.get("accepted_summaries") or []):
                blockers.append("translation_summary_mismatch")
            tags = {str(value) for value in (candidate.get("tags") or [])}
            if BASE_TAG not in tags:
                blockers.append("chatgpt_tag_missing")
            op["observed_tags"] = sorted(tags)
            op["observed_timestamp"] = candidate.get("timestamp")

        if blockers:
            op["operation"] = "block"
            op["reasons"] = list(dict.fromkeys(blockers))
        elif TAG in set(op.get("observed_tags") or []):
            op["operation"] = "skip"
            op["reasons"] = ["already_tagged"]
        else:
            op["operation"] = "add"
            op["reasons"] = [
                "verified_translation_creation_from_history"
                if op["revision_resolution"] == "page_creation_history"
                else "verified_translation_creation"
            ]
        operations.append(op)

    counts = {kind: sum(1 for row in operations if row["operation"] == kind) for kind in ("add", "skip", "block")}
    plan: dict[str, Any] = {
        "plan_version": PLAN_VERSION,
        "kit_version": KIT_VERSION,
        "debate_id": debate_id,
        "language": LANGUAGE,
        "tag": TAG,
        "generated_at": now_iso(),
        "state_path": state_path.relative_to(project_root).as_posix(),
        "state_sha256": sha_file(state_path),
        "manifest_path": manifest_path.relative_to(project_root).as_posix(),
        "manifest_sha256": sha_file(manifest_path),
        "expected_user": expected_user,
        "preflight": {
            "changetags": "changetags" in set(preflight.get("rights") or []),
            "tag_active_manual": True,
        },
        "operations": operations,
        "counts": counts,
    }
    plan["plan_sha256"] = sha_object(plan)
    return plan


def verify_plan_inputs(project_root: Path, plan: dict[str, Any]) -> None:
    verify_signed_object(plan, "plan_sha256", "du plan")
    if plan.get("plan_version") != PLAN_VERSION:
        raise RetroTagError("Schéma du plan rétro-balise divergent")
    # kit_version is producer provenance only.
    state_path = project_root / str(plan.get("state_path") or "")
    manifest_path = project_root / str(plan.get("manifest_path") or "")
    if not state_path.is_file() or sha_file(state_path) != plan.get("state_sha256"):
        raise RetroTagError("État publié anglais modifié depuis le plan")
    if not manifest_path.is_file() or sha_file(manifest_path) != plan.get("manifest_sha256"):
        raise RetroTagError("Manifest du corpus modifié depuis le plan")


def execute_plan(*, project_root: Path, plan: dict[str, Any], adapter: PywikibotTagAdapter) -> dict[str, Any]:
    verify_plan_inputs(project_root, plan)
    if int((plan.get("counts") or {}).get("block", 0)):
        raise RetroTagError("Le plan contient des opérations bloquées")
    adapter.assert_preflight(TAG)
    expected_user = str(plan.get("expected_user") or "")
    add_rows = [row for row in plan.get("operations") or [] if row.get("operation") == "add"]
    revision_ids = [int(row["revision_id"]) for row in add_rows]
    current = adapter.read_revisions(revision_ids)
    actually_add: list[int] = []
    already: list[int] = []
    for row in add_rows:
        revid = int(row["revision_id"])
        revision = current.get(revid)
        if revision is None:
            raise RetroTagError(f"Révision devenue introuvable : {revid}")
        if revision.get("title") != row.get("title"):
            raise RetroTagError(f"Titre divergent pour la révision {revid}")
        if revision.get("parent_id") != 0 or revision.get("user") != expected_user:
            raise RetroTagError(f"Provenance divergente pour la révision {revid}")
        if sha_text(str(revision.get("text") or "")) != row.get("expected_content_sha256"):
            raise RetroTagError(f"Contenu divergent pour la révision {revid}")
        fr_title = str(row.get("source_fr_title") or "").strip()
        canonical_summary = expected_summary(fr_title) if fr_title else ""
        legacy_summary = legacy_expected_summary(fr_title) if fr_title else ""
        accepted_summaries = [canonical_summary, legacy_summary] if fr_title else []
        if row.get("expected_summary") != canonical_summary:
            raise RetroTagError(f"Résumé canonique divergent dans le plan pour la révision {revid}")
        if list(row.get("accepted_summaries") or []) != accepted_summaries:
            raise RetroTagError(f"Résumés acceptés divergents dans le plan pour la révision {revid}")
        if revision.get("summary") not in set(accepted_summaries):
            raise RetroTagError(f"Résumé divergent pour la révision {revid}")
        tags = {str(value) for value in (revision.get("tags") or [])}
        if BASE_TAG not in tags:
            raise RetroTagError(f"Balise chatgpt absente de la révision {revid}")
        if TAG in tags:
            already.append(revid)
        else:
            actually_add.append(revid)

    adapter.add_tag(actually_add, TAG)
    verify_ids = sorted(set(revision_ids))
    attempts = 8
    delay = 2.0
    failures = list(verify_ids)
    for index in range(attempts):
        verified = adapter.read_revisions(verify_ids)
        failures = []
        for revid in verify_ids:
            revision = verified.get(revid)
            if revision is None or TAG not in {str(value) for value in (revision.get("tags") or [])}:
                failures.append(revid)
        if not failures:
            break
        if index + 1 < attempts and delay:
            time.sleep(delay)
    if failures:
        raise RetroTagError(
            f"Vérification post-balise échouée après {attempts} relectures pour les révisions : "
            + ", ".join(map(str, failures[:20]))
        )

    receipt: dict[str, Any] = {
        "receipt_version": RECEIPT_VERSION,
        "kit_version": KIT_VERSION,
        "debate_id": plan.get("debate_id"),
        "language": LANGUAGE,
        "tag": TAG,
        "plan_sha256": plan.get("plan_sha256"),
        "executed_at": now_iso(),
        "added_revision_ids": actually_add,
        "already_tagged_revision_ids": already,
        "verified_revision_ids": verify_ids,
        "counts": {
            "added": len(actually_add),
            "already_tagged": len(already),
            "verified": len(verify_ids),
        },
    }
    receipt["receipt_sha256"] = sha_object(receipt)
    receipts_dir = project_root / ".state" / "receipts" / str(plan.get("debate_id"))
    path = receipts_dir / f"retro-tag-{TAG}-{timestamp()}.json"
    write_json(path, receipt)
    receipt["receipt_path"] = path.relative_to(project_root).as_posix()
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ajouter rétroactivement translated-fr aux révisions anglaises de traduction vérifiées")
    parser.add_argument("debate_id")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--family", default="wikidebates")
    parser.add_argument("--code", default="en")
    parser.add_argument("--pywikibot-dir", type=Path, required=True)
    parser.add_argument("--family-file", type=Path, required=True)
    parser.add_argument("--expected-user", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--plan-output", type=Path)
    parser.add_argument("--machine-readable", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = args.project_root.expanduser().resolve()
    adapter = PywikibotTagAdapter(
        family=args.family,
        code=args.code,
        pywikibot_dir=args.pywikibot_dir,
        family_file=args.family_file,
        expected_user=args.expected_user,
    )
    adapter.open()
    try:
        plan = build_plan(project_root=project_root, debate_id=args.debate_id, adapter=adapter, expected_user=args.expected_user)
        output = args.plan_output or (project_root / "plans" / args.debate_id / timestamp() / f"{TAG}-tag-plan.json")
        if not output.is_absolute():
            output = project_root / output
        output = output.resolve()
        try:
            output.relative_to(project_root)
        except ValueError as exc:
            raise RetroTagError("Le plan doit rester dans le projet") from exc
        write_json(output, plan)
        if args.dry_run:
            result = {
                "status": "blocked" if plan["counts"]["block"] else "dry_run",
                "counts": plan["counts"],
                "plan": output.relative_to(project_root).as_posix(),
                "plan_sha256": plan["plan_sha256"],
            }
        else:
            receipt = execute_plan(project_root=project_root, plan=plan, adapter=adapter)
            result = {
                "status": "executed",
                "counts": receipt["counts"],
                "plan": output.relative_to(project_root).as_posix(),
                "plan_sha256": plan["plan_sha256"],
                "receipt": receipt["receipt_path"],
            }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    finally:
        adapter.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RetroTagError as exc:
        print(f"WIKIDEBIA BLOQUÉ : {exc}", file=sys.stderr)
        raise SystemExit(2)
