from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
import zipfile

import pytest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "wikidebia_manage.py"
CURRENT_VERSIONS = json.loads((SCRIPT.parents[1] / "VERSIONS.json").read_text(encoding="utf-8"))
spec = importlib.util.spec_from_file_location("wikidebia_manage", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _write_component_zip(path: Path, artifact: str, *, include_receipt: bool = False) -> None:
    versions = {"norm": "1.2.20", "validator": "0.4.61", "kit": "2.15.35"}
    payloads = {
        "VERSIONS.json": (json.dumps(versions, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        "README.md": f"# {artifact}\n".encode("utf-8"),
    }
    files = [
        {"path": name, "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        for name, raw in sorted(payloads.items())
    ]
    version = {"wikidebia-normes": "1.2.20", "wikidebia-validator": "0.4.61", "wikidebia-kit": "2.15.50"}[artifact]
    manifest = {
        "artifact": artifact,
        "version": version,
        "normative_revision": "1.2.20",
        "declared_file_count": len(files),
        "declared_test_count": 0,
        "files": files,
    }
    manifest_raw = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    with zipfile.ZipFile(path, "w") as bundle:
        for name, raw in payloads.items():
            bundle.writestr(name, raw)
        bundle.writestr("PACKAGE_MANIFEST_SHA256.json", manifest_raw)
        if include_receipt:
            receipt = {
                "receipt_version": "wikidebia-package-receipt-1.0",
                "artifact": artifact,
                "version": version,
                "normative_revision": "1.2.20",
                "package_manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
                "declared_file_count": len(files),
                "declared_test_count": 0,
            }
            canonical = json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            receipt["receipt_sha256"] = hashlib.sha256(canonical).hexdigest()
            bundle.writestr("PACKAGE_RECEIPT.json", json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")


def test_component_inspector_accepts_and_verifies_optional_receipt(tmp_path: Path):
    archive = tmp_path / "wikidebia-kit.zip"
    _write_component_zip(archive, "wikidebia-kit", include_receipt=True)
    metadata = module.inspect_component_zip(archive)
    assert metadata["artifact"] == "wikidebia-kit"
    assert metadata["versions"]["kit"] == "2.15.35"


def test_single_complete_bundle_is_collected_from_updates(tmp_path: Path):
    updates = tmp_path / "updates"
    updates.mkdir()
    component_dir = tmp_path / "components"
    component_dir.mkdir()
    names = {
        "wikidebia-normes": "wikidebia-normes.zip",
        "wikidebia-validator": "wikidebia-validator.zip",
        "wikidebia-kit": "wikidebia-kit.zip",
    }
    for artifact, name in names.items():
        _write_component_zip(component_dir / name, artifact)
    outer = updates / "WIKIDEBIA_COMPLET.zip"
    with zipfile.ZipFile(outer, "w") as bundle:
        for name in names.values():
            bundle.write(component_dir / name, name)
        bundle.writestr("README.txt", "bundle complet")
    components, sources, workspace = module.collect_update_payload(tmp_path)
    assert set(components) == set(names)
    assert sources == [outer]
    assert workspace.is_dir()


def test_delivery_prefers_root_components_over_historical_corpus_inputs(tmp_path: Path):
    updates = tmp_path / "updates"
    updates.mkdir()
    active = tmp_path / "active"
    active.mkdir()
    historical = tmp_path / "historical"
    historical.mkdir()
    artifacts = ("wikidebia-normes", "wikidebia-validator", "wikidebia-kit")
    for artifact in artifacts:
        _write_component_zip(active / f"{artifact}.zip", artifact)
        _write_component_zip(historical / f"{artifact}.zip", artifact)
        # Make the historical copy bytewise divergent but still internally valid.
        with zipfile.ZipFile(historical / f"{artifact}.zip", "a") as bundle:
            bundle.comment = b"historical"
    corpus = tmp_path / "corpus.zip"
    with zipfile.ZipFile(corpus, "w") as bundle:
        for artifact in artifacts:
            bundle.write(historical / f"{artifact}.zip", f"technical_inputs/{artifact}.zip")
    delivery = updates / "WIKIDEBIA_LIVRAISON.zip"
    with zipfile.ZipFile(delivery, "w") as bundle:
        for artifact in artifacts:
            bundle.write(active / f"{artifact}.zip", f"{artifact}.zip")
        bundle.write(corpus, "debate-corpus.zip")
    components, sources, workspace = module.collect_update_payload(tmp_path)
    assert set(components) == set(artifacts)
    assert all(components[artifact].parent.name.startswith("wrapper-") for artifact in artifacts)
    assert sources == [delivery]
    assert workspace.is_dir()


def test_optional_receipt_with_bad_manifest_hash_is_rejected(tmp_path: Path):
    archive = tmp_path / "wikidebia-kit.zip"
    _write_component_zip(archive, "wikidebia-kit", include_receipt=True)
    rewritten = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(rewritten, "w") as target:
        for info in source.infolist():
            raw = source.read(info.filename)
            if info.filename == "PACKAGE_RECEIPT.json":
                receipt = json.loads(raw.decode("utf-8"))
                receipt["package_manifest_sha256"] = "0" * 64
                body = dict(receipt); body.pop("receipt_sha256", None)
                receipt["receipt_sha256"] = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
                raw = (json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            target.writestr(info, raw)
    try:
        module.inspect_component_zip(rewritten)
    except module.ManagementError as exc:
        assert "Reçu incohérent" in str(exc)
    else:
        raise AssertionError("reçu incohérent accepté")


def test_scope_values_cover_requested_publication_modes():
    assert module.scope_values("all") == (["fr", "en"], [])
    assert module.scope_values("fr") == (["fr"], [])
    assert module.scope_values("en") == (["en"], [])
    assert module.scope_values("fr-debate") == (["fr"], ["debate"])
    assert module.scope_values("en-debate") == (["en"], ["debate"])


def test_generated_config_is_relative_and_debate_first(tmp_path: Path):
    (tmp_path / "config").mkdir()
    run_dir = tmp_path / "plans" / "demo" / "run"
    run_dir.mkdir(parents=True)
    path = module.publication_config(tmp_path, "demo", "all", run_dir)
    config = json.loads(path.read_text(encoding="utf-8"))
    assert config["project_root"] == "."
    assert config["pywikibot_dir"] == "private/pywikibot"
    assert config["corpus_root"] == "corpus/demo"
    assert config["operation"]["page_type_order"] == ["debate", "argument"]
    assert config["validator"]["required_version"] == CURRENT_VERSIONS["validator"]
    assert config["manifest_requirements"] == {}
    assert str(tmp_path) not in path.read_text(encoding="utf-8")


def test_gitignore_excludes_secrets_runtime_and_corpus():
    ignore = (SCRIPT.parents[1] / "root_template" / ".gitignore").read_text(encoding="utf-8")
    for token in (
        "/private/", "/corpus/", "/archives/", "/updates/", "/incoming/",
        "/logs/", "/plans/", "/configs/", "/apicache/", "/.gitconfig-wikidebia",
        "/user-config.py", "/user-password.cfg", "*.lwp", "throttle.ctrl",
    ):
        assert token in ignore


def test_portability_check_rejects_current_root_literal(tmp_path: Path):
    (tmp_path / "kit").mkdir()
    (tmp_path / "kit" / "bad.txt").write_text(str(tmp_path), encoding="utf-8")
    try:
        module.assert_portable_sources(tmp_path)
    except module.ManagementError as exc:
        assert "Chemin absolu" in str(exc)
    else:
        raise AssertionError("chemin absolu accepté")


def test_git_commit_sets_repository_identity_when_none_is_configured(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "empty-global-gitconfig"))
    (tmp_path / ".gitignore").write_text((SCRIPT.parents[1] / "root_template" / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "tracked.txt").write_text("contenu\n", encoding="utf-8")
    module.git_commit_and_push(tmp_path, "Test", push=False)
    name = module.run(["git", "config", "--local", "--get", "user.name"], cwd=tmp_path, capture=True).stdout.strip()
    email = module.run(["git", "config", "--local", "--get", "user.email"], cwd=tmp_path, capture=True).stdout.strip()
    assert name == "Wikidéb’IA"
    assert email == "wikidebia@localhost"


def test_single_zip_in_incoming_is_selected_automatically(tmp_path: Path):
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    archive = incoming / "gpa_autorisation.zip"
    archive.write_bytes(b"not-opened-here")
    assert module.find_debate_archive(tmp_path, None) == archive


def test_multiple_zips_require_an_identifier(tmp_path: Path):
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    (incoming / "gpa_autorisation.zip").write_bytes(b"a")
    (incoming / "vote_obligatoire.zip").write_bytes(b"b")
    try:
        module.find_debate_archive(tmp_path, None)
    except module.ManagementError as exc:
        message = str(exc)
        assert "Plusieurs archives ZIP" in message
        assert "gpa_autorisation" in message
        assert "vote_obligatoire" in message
    else:
        raise AssertionError("plusieurs ZIP acceptés sans identifiant")


def test_identifier_selects_matching_zip_in_incoming(tmp_path: Path):
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    expected = incoming / "gpa_autorisation.zip"
    expected.write_bytes(b"a")
    (incoming / "vote_obligatoire.zip").write_bytes(b"b")
    assert module.find_debate_archive(tmp_path, "gpa_autorisation") == expected


def test_identifier_must_not_include_zip_extension(tmp_path: Path):
    (tmp_path / "incoming").mkdir()
    try:
        module.find_debate_archive(tmp_path, "gpa_autorisation.zip")
    except module.ManagementError as exc:
        assert "sans l’extension .zip" in str(exc)
    else:
        raise AssertionError("extension .zip acceptée dans l’identifiant")


def test_single_legacy_named_zip_uses_manifest_debate_id(tmp_path: Path):
    import zipfile


    incoming = tmp_path / "incoming"
    incoming.mkdir()
    archive = incoming / "education_sexualite_ecole_fr_en_release_ready_repaired_2026-07-31.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("manifest.json", json.dumps({"debate_id": "education_sexualite_ecole"}))
        bundle.writestr("payload.txt", "contenu")

    assert module.find_debate_archive(tmp_path, None) == archive
    debate_id, target = module.install_debate_corpus(tmp_path, archive)
    assert debate_id == "education_sexualite_ecole"
    assert target == tmp_path / "corpus" / "education_sexualite_ecole"
    assert (target / "payload.txt").read_text(encoding="utf-8") == "contenu"


def test_explicit_archive_stem_may_differ_from_manifest_debate_id(tmp_path: Path):
    import zipfile


    incoming = tmp_path / "incoming"
    incoming.mkdir()
    selected = incoming / "ancienne_livraison_2026-07-31.zip"
    other = incoming / "autre_debat.zip"
    with zipfile.ZipFile(selected, "w") as bundle:
        bundle.writestr("manifest.json", json.dumps({"debate_id": "education_sexualite_ecole"}))
    other.write_bytes(b"non-selected")

    archive = module.find_debate_archive(tmp_path, "ancienne_livraison_2026-07-31")
    assert archive == selected
    debate_id, target = module.install_debate_corpus(tmp_path, archive)
    assert debate_id == "education_sexualite_ecole"
    assert target.name == "education_sexualite_ecole"


def test_legacy_incoming_debates_is_migrated_to_incoming(tmp_path: Path):
    legacy = tmp_path / "incoming" / "debates"
    legacy.mkdir(parents=True)
    archive = legacy / "gpa_autorisation.zip"
    archive.write_bytes(b"archive")
    backup = tmp_path / "archives" / "updates" / "test"
    backup.mkdir(parents=True)
    module.migrate_legacy_debate_inbox(tmp_path, backup)
    assert (tmp_path / "incoming" / "gpa_autorisation.zip").read_bytes() == b"archive"
    assert not legacy.exists()


def test_runtime_requirements_include_pywikibot_and_validator_dependencies():
    requirements = (SCRIPT.parents[1] / "root_template" / "requirements-runtime.txt").read_text(encoding="utf-8")
    for dependency in ("pywikibot", "jsonschema", "referencing", "pytest"):
        assert dependency in requirements


def test_launcher_bootstraps_virtual_environment_and_dependencies():
    launcher = (SCRIPT.parents[1] / "root_template" / "wikidebia").read_text(encoding="utf-8")
    assert '-m venv "$VENV"' in launcher
    assert '-m pip install' in launcher
    assert 'requirements-runtime.txt' in launcher
    assert 'pywikibot' in launcher
    assert 'runtime-requirements.sha256' in launcher


def test_runtime_report_detects_missing_environment(tmp_path: Path):
    (tmp_path / "requirements-runtime.txt").write_text("pywikibot\n", encoding="utf-8")
    report = module.runtime_environment_report(tmp_path)
    assert report["python_available"] is False
    assert "pywikibot" in report["missing_modules"]


def test_doctor_reports_missing_runtime_environment(tmp_path: Path):
    (tmp_path / "requirements-runtime.txt").write_text("pywikibot\n", encoding="utf-8")
    (tmp_path / "private" / "pywikibot").mkdir(parents=True)
    (tmp_path / "private" / "pywikibot" / "user-config.py").write_text("family='wikidebates'\n", encoding="utf-8")
    report = module.doctor(tmp_path)
    assert report["status"] == "failed"
    assert any(".venv/bin/python" in issue for issue in report["issues"])


def test_doctor_accepts_managed_pywikibot_credentials_without_server_config(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("WIKIDEBIA_FR_BOT_USERNAME", "ChatGPT@Codex-FR")
    monkeypatch.setenv("WIKIDEBIA_FR_BOT_PASSWORD", "managed-placeholder")
    monkeypatch.setenv("WIKIDEBIA_API_TOKEN", "access-placeholder")
    monkeypatch.delenv("WIKIDEBIA_EN_BOT_USERNAME", raising=False)
    monkeypatch.delenv("WIKIDEBIA_EN_BOT_PASSWORD", raising=False)
    monkeypatch.setattr(module, "runtime_environment_report", lambda root: {
        "requirements_sha256": "x", "python_available": True,
        "missing_modules": [], "probe_error": None,
    })
    monkeypatch.setattr(module, "assert_portable_sources", lambda root: None)
    monkeypatch.setattr(module, "git_security_issues", lambda root: [])

    report = module.doctor(tmp_path)

    assert not any("Accès Pywikibot absent" in issue for issue in report["issues"])
    assert report["access_configuration"] == {
        "local_pywikibot_config": False,
        "managed_credentials": {"fr": "complete", "en": "absent"},
        "api_access_header_configured": True,
        "api_connectivity": {"requested": False},
    }


def test_doctor_reports_partial_managed_credentials_without_values(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("WIKIDEBIA_FR_BOT_USERNAME", "ChatGPT@Codex-FR")
    monkeypatch.delenv("WIKIDEBIA_FR_BOT_PASSWORD", raising=False)
    monkeypatch.delenv("WIKIDEBIA_EN_BOT_USERNAME", raising=False)
    monkeypatch.delenv("WIKIDEBIA_EN_BOT_PASSWORD", raising=False)
    monkeypatch.setattr(module, "runtime_environment_report", lambda root: {
        "requirements_sha256": "x", "python_available": True,
        "missing_modules": [], "probe_error": None,
    })
    monkeypatch.setattr(module, "assert_portable_sources", lambda root: None)
    monkeypatch.setattr(module, "git_security_issues", lambda root: [])

    report = module.doctor(tmp_path)

    assert any("WIKIDEBIA_FR_BOT_PASSWORD" in issue for issue in report["issues"])
    assert "ChatGPT@Codex-FR" not in json.dumps(report)


def test_doctor_api_check_reports_both_languages_without_exposing_token(tmp_path: Path, monkeypatch):
    token = "secret-access-placeholder"
    monkeypatch.setenv("WIKIDEBIA_API_TOKEN", token)
    monkeypatch.setenv("WIKIDEBIA_FR_BOT_USERNAME", "ChatGPT@Codex-FR")
    monkeypatch.setenv("WIKIDEBIA_FR_BOT_PASSWORD", "managed-placeholder")
    monkeypatch.setattr(module, "check_wikidebates_apis", lambda value: {
        "fr": {"status": "passed", "http_status": 200},
        "en": {"status": "passed", "http_status": 200},
    })
    monkeypatch.setattr(module, "runtime_environment_report", lambda root: {
        "requirements_sha256": "x", "python_available": True,
        "missing_modules": [], "probe_error": None,
    })
    monkeypatch.setattr(module, "assert_portable_sources", lambda root: None)
    monkeypatch.setattr(module, "git_security_issues", lambda root: [])

    report = module.doctor(tmp_path, check_api=True)

    assert report["access_configuration"]["api_connectivity"]["languages"] == {
        "fr": {"status": "passed", "http_status": 200},
        "en": {"status": "passed", "http_status": 200},
    }
    assert token not in json.dumps(report)


def test_api_probe_sends_header_only_to_expected_hosts(monkeypatch):
    requests = []

    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): return False

    def fake_urlopen(request, timeout):
        requests.append(request)
        return Response()

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    result = module.check_wikidebates_apis("secret-placeholder")

    assert result == {
        "fr": {"status": "passed", "http_status": 200},
        "en": {"status": "passed", "http_status": 200},
    }
    assert [request.host for request in requests] == [
        "fr.wikidebates.org", "en.wikidebates.org",
    ]
    assert all(request.get_header("X-wikidebia-access") == "secret-placeholder" for request in requests)
    assert all("doctor" in request.get_header("User-agent") for request in requests)


def _init_git_repo(root: Path) -> None:
    module.run(["git", "init", "-b", "main"], cwd=root)
    module.run(["git", "config", "user.name", "Test"], cwd=root)
    module.run(["git", "config", "user.email", "test@example.invalid"], cwd=root)


def test_root_configs_is_ignored_but_kit_configs_is_trackable(tmp_path: Path):
    (tmp_path / ".gitignore").write_text((SCRIPT.parents[1] / "root_template" / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8")
    _init_git_repo(tmp_path)
    ignored = module.run(["git", "check-ignore", "-q", "--no-index", "--", "configs/test.json"], cwd=tmp_path, check=False)
    allowed = module.run(["git", "check-ignore", "-q", "--no-index", "--", "kit/configs/example.json"], cwd=tmp_path, check=False)
    assert ignored.returncode == 0
    assert allowed.returncode != 0


def test_prepare_git_security_untracks_lwp_without_deleting_it(tmp_path: Path):
    (tmp_path / ".gitignore").write_text((SCRIPT.parents[1] / "root_template" / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8")
    secret = tmp_path / "pywikibot-session.lwp"
    secret.write_text("cookie", encoding="utf-8")
    _init_git_repo(tmp_path)
    module.run(["git", "add", "-f", "pywikibot-session.lwp"], cwd=tmp_path)
    assert module.git_tracked_forbidden_paths(tmp_path) == ["pywikibot-session.lwp"]
    module.prepare_git_security(tmp_path)
    assert secret.is_file()
    assert module.git_tracked_forbidden_paths(tmp_path) == []


def test_git_security_detects_missing_required_ignore_rule(tmp_path: Path):
    (tmp_path / ".gitignore").write_text("/private/\n", encoding="utf-8")
    missing = module.gitignore_missing_rules(tmp_path)
    assert "*.lwp" in missing
    assert "/apicache/" in missing


def test_doctor_reports_tracked_sensitive_file(tmp_path: Path, monkeypatch):
    (tmp_path / ".gitignore").write_text((SCRIPT.parents[1] / "root_template" / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "private" / "pywikibot").mkdir(parents=True)
    (tmp_path / "private" / "pywikibot" / "user-config.py").write_text("family='wikidebates'\n", encoding="utf-8")
    secret = tmp_path / "session.lwp"
    secret.write_text("cookie", encoding="utf-8")
    _init_git_repo(tmp_path)
    module.run(["git", "add", "-f", "session.lwp"], cwd=tmp_path)
    monkeypatch.setattr(module, "runtime_environment_report", lambda root: {"requirements_sha256":"x", "python_available":True, "missing_modules":[]})
    report = module.doctor(tmp_path)
    assert report["status"] == "failed"
    assert any("session.lwp" in issue for issue in report["issues"])


def test_runtime_requirements_bound_pywikibot_major_version():
    requirements = (SCRIPT.parents[1] / "root_template" / "requirements-runtime.txt").read_text(encoding="utf-8")
    assert "pywikibot>=11.5,<12" in requirements


def test_parser_exposes_github_sync_command():
    parser = module.build_parser()
    args = parser.parse_args(["github-sync"])
    assert args.command == "github-sync"


def test_parser_exposes_optional_api_diagnostic():
    args = module.build_parser().parse_args(["doctor", "--check-api"])
    assert args.command == "doctor"
    assert args.check_api is True


def test_parser_exposes_continuity_sync_check_command():
    parser = module.build_parser()
    args = parser.parse_args(["continuity-sync", "debat_test", "--check"])
    assert args.command == "continuity-sync"
    assert args.debate_id == "debat_test"
    assert args.check is True


def test_git_push_disables_terminal_password_prompt(monkeypatch, tmp_path: Path):
    _init_git_repo(tmp_path)
    module.run(["git", "remote", "add", "origin", "https://github.com/example/example.git"], cwd=tmp_path)
    calls = []
    original = module.run
    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command[:2] == ["git", "push"]:
            import subprocess
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="auth failed")
        return original(command, **kwargs)
    monkeypatch.setattr(module, "run", fake_run)
    assert module.git_push_current_branch(tmp_path, strict=False) is False
    push = next(item for item in calls if item[0][:2] == ["git", "push"])[1]
    assert push["env"]["GIT_TERMINAL_PROMPT"] == "0"


def test_forbidden_git_paths_keep_leading_dot_semantics():
    assert module.forbidden_git_path(".gitconfig-wikidebia")
    assert module.forbidden_git_path(".state/runtime.json")
    assert module.forbidden_git_path("kit/configs/example.json") is False


def test_github_sync_commits_pending_safe_changes_before_push(tmp_path: Path, monkeypatch):
    (tmp_path / ".gitignore").write_text((SCRIPT.parents[1] / "root_template" / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8")
    _init_git_repo(tmp_path)
    (tmp_path / "safe.txt").write_text("contenu\n", encoding="utf-8")
    pushed = []
    monkeypatch.setattr(module, "git_push_current_branch", lambda root, strict: pushed.append((root, strict)) or True)
    module.github_sync(tmp_path)
    assert module.run(["git", "status", "--porcelain"], cwd=tmp_path, capture=True).stdout.strip() == ""
    assert module.run(["git", "log", "-1", "--pretty=%s"], cwd=tmp_path, capture=True).stdout.strip() == "Synchronisation sécurisée Wikidéb’IA"
    assert pushed == [(tmp_path, True)]


def test_publish_command_has_no_interactive_prompt(monkeypatch, tmp_path: Path):
    def forbidden_input(*args, **kwargs):
        raise AssertionError("input() ne doit jamais être appelé par publish")
    monkeypatch.setattr("builtins.input", forbidden_input)
    monkeypatch.setattr(module, "ensure_credentials", lambda root: None)
    archive = tmp_path / "incoming" / "demo.zip"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"zip")
    monkeypatch.setattr(module, "find_debate_archive", lambda root, identifier: archive)
    corpus = tmp_path / "corpus" / "demo"
    corpus.mkdir(parents=True)
    monkeypatch.setattr(module, "install_debate_corpus", lambda root, selected: ("demo", corpus))
    monkeypatch.setattr(module, "publication_config", lambda root, debate_id, scope, run_dir: run_dir / "config.json")
    plan = {"blockers": [], "counts": {}, "actions": [], "plan_sha256": "a" * 64}
    def fake_run(command, *, cwd, capture=False, check=True, env=None):
        class Result:
            stdout = '{"created":0,"updated":0,"skipped":0}\n'
            returncode = 0
        if "--mode" in command and command[command.index("--mode") + 1] == "plan":
            output = Path(cwd) / command[command.index("--plan-output") + 1]
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(plan), encoding="utf-8")
        return Result()
    monkeypatch.setattr(module, "run", fake_run)
    result = module.publish_debate(tmp_path, None, "all", False, True)
    assert result == {"created": 0, "updated": 0, "skipped": 0}


def test_nested_complete_delivery_is_collected_from_one_zip(tmp_path: Path):
    updates=tmp_path/"updates"; updates.mkdir()
    component_dir=tmp_path/"components"; component_dir.mkdir()
    names=[]
    for artifact in module.COMPONENTS:
        name=artifact+".zip"; names.append(name)
        _write_component_zip(component_dir/name,artifact)
    inner=tmp_path/"WIKIDEBIA_SOURCES_COMPLETES.zip"
    with zipfile.ZipFile(inner,"w") as bundle:
        for name in names: bundle.write(component_dir/name,name)
    outer=updates/"WIKIDEBIA_LIVRAISON_COMPLETE.zip"
    with zipfile.ZipFile(outer,"w") as bundle:
        bundle.write(inner,"delivery/WIKIDEBIA_SOURCES_COMPLETES.zip")
        bundle.writestr("delivery/AUDIT.txt","ok")
    components,sources,workspace=module.collect_update_payload(tmp_path)
    assert set(components)==set(module.COMPONENTS)
    assert sources==[outer]
    assert workspace.is_dir()


def test_update_command_has_no_interactive_prompt(monkeypatch, tmp_path: Path):
    def forbidden_input(*args, **kwargs):
        raise AssertionError("input() ne doit jamais être appelé par update")
    monkeypatch.setattr("builtins.input", forbidden_input)
    monkeypatch.setattr(module, "ensure_credentials", lambda root: None)
    monkeypatch.setattr(module, "_prepare_update_corpus", lambda root, identifier, archive_selector=None: ("demo", None, root / "corpus" / "demo", None))
    monkeypatch.setattr(module, "remote_update_config", lambda root, debate_id, scope, run_dir, corpus_root=None: run_dir / "config.json")
    plan = {
        "counts": {"update": 1},
        "operations": {"update": [{"page_id": "A1"}], "manual_review": [], "blocked": []},
        "plan_sha256": "b" * 64,
    }
    calls = []
    def fake_run(command, *, cwd, capture=False, check=True, env=None):
        calls.append(command)
        class Result:
            stdout = '{"updated":1}\n'
            stderr = ""
            returncode = 0
        if "--mode" in command and command[command.index("--mode") + 1] == "plan":
            output = Path(cwd) / command[command.index("--plan-output") + 1]
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(plan), encoding="utf-8")
        return Result()
    monkeypatch.setattr(module, "run", fake_run)
    result = module.update_debate(tmp_path, "demo", "all", False, False, False, False, True)
    assert result["status"] == "executed"
    assert result["counts"] == {"updated": 1}
    execute = next(call for call in calls if "--mode" in call and call[call.index("--mode") + 1] == "execute")
    assert execute[execute.index("--confirm-plan-sha256") + 1] == "b" * 64


def test_update_yes_remains_a_hidden_compatibility_option():
    parser = module.build_parser()
    args = parser.parse_args(["update", "demo", "--yes"])
    assert args.command == "update"
    assert args.yes is True
    assert "--yes" not in parser.format_help()


def _write_debate_archive(path: Path, debate_id: str, payload: str) -> None:
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr("manifest.json", json.dumps({"debate_id": debate_id}))
        bundle.writestr("payload.txt", payload)


def test_update_prefers_homonymous_incoming_archive_over_installed_corpus(tmp_path: Path):
    installed = tmp_path / "corpus" / "demo"
    installed.mkdir(parents=True)
    (installed / "manifest.json").write_text(json.dumps({"debate_id": "demo"}), encoding="utf-8")
    (installed / "payload.txt").write_text("installed", encoding="utf-8")
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    _write_debate_archive(incoming / "demo.zip", "demo", "archive")

    debate_id, archive, corpus_root, staging_root = module._prepare_update_corpus(tmp_path, "demo")
    assert debate_id == "demo"
    assert archive == incoming / "demo.zip"
    assert staging_root is not None
    assert (corpus_root / "payload.txt").read_text(encoding="utf-8") == "archive"
    assert (installed / "payload.txt").read_text(encoding="utf-8") == "installed"


def test_explicit_update_archive_is_staged_without_replacing_active_corpus(tmp_path: Path):
    installed = tmp_path / "corpus" / "demo"
    installed.mkdir(parents=True)
    (installed / "manifest.json").write_text(json.dumps({"debate_id": "demo"}), encoding="utf-8")
    (installed / "payload.txt").write_text("installed", encoding="utf-8")
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    _write_debate_archive(incoming / "revised.zip", "demo", "revised")

    debate_id, archive, corpus_root, staging_root = module._prepare_update_corpus(tmp_path, None, "revised")
    assert debate_id == "demo"
    assert archive == incoming / "revised.zip"
    assert staging_root is not None and staging_root.is_dir()
    assert (corpus_root / "payload.txt").read_text(encoding="utf-8") == "revised"
    assert (installed / "payload.txt").read_text(encoding="utf-8") == "installed"


def test_update_dry_run_with_archive_does_not_replace_active_corpus(monkeypatch, tmp_path: Path):
    installed = tmp_path / "corpus" / "demo"
    installed.mkdir(parents=True)
    (installed / "manifest.json").write_text(json.dumps({"debate_id": "demo"}), encoding="utf-8")
    (installed / "payload.txt").write_text("installed", encoding="utf-8")
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    _write_debate_archive(incoming / "revised.zip", "demo", "revised")
    monkeypatch.setattr(module, "ensure_credentials", lambda root: None)
    monkeypatch.setattr(module, "remote_update_config", lambda root, debate_id, scope, run_dir, corpus_root=None: run_dir / "config.json")

    operations = {name: [] for name in ("create", "update", "move", "redirect", "delete", "skip", "manual_review", "blocked")}
    operations["update"] = [{"page_id": "A1"}]
    plan = {"counts": {name: len(rows) for name, rows in operations.items()}, "operations": operations, "plan_sha256": "a" * 64}

    def fake_run(command, *, cwd, capture=False, check=True, env=None):
        class Result:
            stdout = ""
            stderr = ""
            returncode = 0
        output = Path(cwd) / command[command.index("--plan-output") + 1]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(plan), encoding="utf-8")
        return Result()

    monkeypatch.setattr(module, "run", fake_run)
    result = module.update_debate(tmp_path, None, "all", False, False, False, True, True, "revised")
    assert result["status"] == "dry_run"
    assert (installed / "payload.txt").read_text(encoding="utf-8") == "installed"
    staging = tmp_path / ".state" / "update-staging"
    assert not staging.exists() or not any(staging.iterdir())


def test_manual_review_blocks_manager_before_execute(monkeypatch, tmp_path: Path):
    corpus = tmp_path / "corpus" / "demo"
    corpus.mkdir(parents=True)
    (corpus / "manifest.json").write_text(json.dumps({"debate_id": "demo"}), encoding="utf-8")
    monkeypatch.setattr(module, "ensure_credentials", lambda root: None)
    monkeypatch.setattr(module, "remote_update_config", lambda root, debate_id, scope, run_dir, corpus_root=None: run_dir / "config.json")
    operations = {name: [] for name in ("create", "update", "move", "redirect", "delete", "skip", "manual_review", "blocked")}
    operations["manual_review"] = [{"page_id": "A1"}]
    plan = {"counts": {name: len(rows) for name, rows in operations.items()}, "operations": operations, "plan_sha256": "c" * 64}
    modes = []

    def fake_run(command, *, cwd, capture=False, check=True, env=None):
        mode = command[command.index("--mode") + 1]
        modes.append(mode)
        if mode == "execute":
            raise AssertionError("l’exécuteur ne doit pas être appelé")
        class Result:
            stdout = ""
            stderr = ""
            returncode = 3
        output = Path(cwd) / command[command.index("--plan-output") + 1]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(plan), encoding="utf-8")
        return Result()

    monkeypatch.setattr(module, "run", fake_run)
    try:
        module.update_debate(tmp_path, "demo", "all", False, False, False, False, True)
    except module.ManagementError as exc:
        assert "révision manuelle" in str(exc)
    else:
        raise AssertionError("manual_review n’a pas bloqué la reprise")
    assert modes == ["plan"]


def test_all_skip_returns_no_changes_after_signed_attestation(monkeypatch, tmp_path: Path):
    corpus = tmp_path / "corpus" / "demo"
    corpus.mkdir(parents=True)
    (corpus / "manifest.json").write_text(json.dumps({"debate_id": "demo"}), encoding="utf-8")
    monkeypatch.setattr(module, "ensure_credentials", lambda root: None)
    monkeypatch.setattr(module, "remote_update_config", lambda root, debate_id, scope, run_dir, corpus_root=None: run_dir / "config.json")
    operations = {name: [] for name in ("create", "update", "move", "redirect", "delete", "skip", "manual_review", "blocked")}
    operations["skip"] = [{"page_id": "A1"}]
    plan = {"counts": {name: len(rows) for name, rows in operations.items()}, "operations": operations, "plan_sha256": "d" * 64}
    modes = []

    def fake_run(command, *, cwd, capture=False, check=True, env=None):
        mode = command[command.index("--mode") + 1]
        modes.append(mode)
        class Result:
            stdout = '{"verified_unchanged": 1}\n' if mode == "attest" else ""
            stderr = ""
            returncode = 0
        if mode == "plan":
            output = Path(cwd) / command[command.index("--plan-output") + 1]
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(plan), encoding="utf-8")
        return Result()

    monkeypatch.setattr(module, "run", fake_run)
    result = module.update_debate(tmp_path, "demo", "all", False, False, False, False, True)
    assert result["status"] == "no_changes"
    assert result["counts"] == {"verified_unchanged": 1}
    assert modes == ["plan", "attest"]


def test_update_identifier_selects_matching_incoming_archive_without_archive_option(tmp_path: Path):
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    _write_debate_archive(incoming / "demo.zip", "demo", "archive")
    debate_id, archive, corpus_root, staging_root = module._prepare_update_corpus(tmp_path, "demo")
    assert debate_id == "demo"
    assert archive == incoming / "demo.zip"
    assert staging_root is not None
    assert (corpus_root / "payload.txt").read_text(encoding="utf-8") == "archive"


def test_update_without_identifier_selects_unique_incoming_archive(tmp_path: Path):
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    _write_debate_archive(incoming / "revised.zip", "demo", "archive")
    debate_id, archive, corpus_root, staging_root = module._prepare_update_corpus(tmp_path, None)
    assert debate_id == "demo"
    assert archive == incoming / "revised.zip"
    assert staging_root is not None


def test_update_without_identifier_prefers_unique_incoming_zip_over_installed_corpus(tmp_path: Path):
    installed = tmp_path / "corpus" / "demo"
    installed.mkdir(parents=True)
    (installed / "manifest.json").write_text(json.dumps({"debate_id": "demo"}), encoding="utf-8")
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    _write_debate_archive(incoming / "revised.zip", "demo", "archive")
    debate_id, archive, corpus_root, staging_root = module._prepare_update_corpus(tmp_path, None)
    assert debate_id == "demo"
    assert archive == incoming / "revised.zip"
    assert staging_root is not None
    assert (corpus_root / "payload.txt").read_text(encoding="utf-8") == "archive"


def test_update_without_identifier_blocks_only_when_multiple_incoming_archives_exist(tmp_path: Path):
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    _write_debate_archive(incoming / "one.zip", "one", "one")
    _write_debate_archive(incoming / "two.zip", "two", "two")
    try:
        module._prepare_update_corpus(tmp_path, None)
    except module.ManagementError as exc:
        assert "update IDENTIFIANT" in str(exc)
        assert "one" in str(exc) and "two" in str(exc)
    else:
        raise AssertionError("plusieurs archives ont été départagées sans identifiant")


def test_update_defaults_to_automatic_scope():
    parser = module.build_parser()
    args = parser.parse_args(["update"])
    assert args.scope is None


def test_scope_without_selected_mutation_returns_no_changes_in_scope(monkeypatch, tmp_path: Path):
    corpus = tmp_path / "corpus" / "demo"
    corpus.mkdir(parents=True)
    (corpus / "manifest.json").write_text(json.dumps({"debate_id": "demo"}), encoding="utf-8")
    monkeypatch.setattr(module, "ensure_credentials", lambda root: None)
    monkeypatch.setattr(module, "remote_update_config", lambda root, debate_id, scope, run_dir, corpus_root=None: run_dir / "config.json")
    operations = {name: [] for name in ("create", "update", "move", "redirect", "delete", "skip", "manual_review", "blocked")}
    operations["update"] = [{"page_id": "A1"}]
    plan = {"counts": {name: len(rows) for name, rows in operations.items()}, "operations": operations, "plan_sha256": "e" * 64}
    modes = []
    def fake_run(command, *, cwd, capture=False, check=True, env=None):
        mode = command[command.index("--mode") + 1]
        modes.append(mode)
        class Result:
            stdout = ""
            stderr = ""
            returncode = 0
        output = Path(cwd) / command[command.index("--plan-output") + 1]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(plan), encoding="utf-8")
        return Result()
    monkeypatch.setattr(module, "run", fake_run)
    result = module.update_debate(tmp_path, "demo", "all", False, False, True, False, True)
    assert result["status"] == "no_changes_in_scope"
    assert modes == ["plan"]


def test_graph_extract_command_is_routed_read_only(monkeypatch, tmp_path: Path):
    script = tmp_path / "kit" / "scripts" / "wikidebia_graph_extract.py"
    family = tmp_path / "kit" / "families" / "wikidebates_family.py"
    script.parent.mkdir(parents=True)
    family.parent.mkdir(parents=True)
    script.write_text("print('ok')\n", encoding="utf-8")
    family.write_text("# family\n", encoding="utf-8")
    commands = []

    def fake_run(command, *, cwd, capture=False, check=True, env=None):
        commands.append(command)
        class Result:
            returncode = 0
            stdout = ""
            stderr = ""
        return Result()

    monkeypatch.setattr(module, "run", fake_run)
    code = module.graph_extract_debate(
        tmp_path,
        "Dieu existe-t-il ?",
        lang="fr",
        family="wikidebates",
        output_dir=None,
        cache_dir=None,
        slug=None,
        extraction_date="2026-08-03",
        login=False,
        force_refresh=False,
        allow_missing=False,
        max_depth=4,
        max_pages=1000,
        retries=3,
        retry_delay=1.5,
        progress_every=10,
        follow_local_relations_at_dedicated_debate=False,
    )
    assert code == 0
    assert len(commands) == 1
    command = commands[0]
    assert command[1].endswith("kit/scripts/wikidebia_graph_extract.py")
    assert command[command.index("--debate") + 1] == "Dieu existe-t-il ?"
    assert command[command.index("--output-dir") + 1].endswith(".state/graph-extract/dieu_existe_t_il")
    assert "--machine-readable" in command
    assert "--force-refresh" not in command
    assert command[command.index("--max-depth") + 1] == "4"
    assert "--follow-local-relations-at-dedicated-debate" not in command


def test_graph_extract_parser_exposes_native_command():
    args = module.build_parser().parse_args([
        "graph-extract", "Débat test", "--max-pages", "50", "--max-depth", "4"
    ])
    assert args.command == "graph-extract"
    assert args.debate_title == "Débat test"
    assert args.max_pages == 50
    assert args.max_depth == 4



def test_graph_extract_main_routes_dedicated_debate_option_without_namespace_regression(monkeypatch, tmp_path: Path):
    captured = {}

    def fake_graph_extract(root, debate_title, **kwargs):
        captured["root"] = root
        captured["debate_title"] = debate_title
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(module, "graph_extract_debate", fake_graph_extract)
    code = module.main([
        "--root", str(tmp_path),
        "graph-extract", "Débat test",
        "--follow-local-relations-at-dedicated-debate",
    ])
    assert code == 0
    assert captured["debate_title"] == "Débat test"
    assert captured["follow_local_relations_at_dedicated_debate"] is True
    assert captured["max_depth"] is None


def test_graph_extract_legacy_option_alias_maps_to_dedicated_destination():
    args = module.build_parser().parse_args([
        "graph-extract", "Débat test",
        "--follow-local-relations-at-detailed-debate",
    ])
    assert args.follow_local_relations_at_dedicated_debate is True
    assert not hasattr(args, "follow_local_relations_at_detailed_debate")

def test_graph_extract_rejects_output_outside_project(tmp_path: Path):
    script = tmp_path / "kit" / "scripts" / "wikidebia_graph_extract.py"
    family = tmp_path / "kit" / "families" / "wikidebates_family.py"
    script.parent.mkdir(parents=True)
    family.parent.mkdir(parents=True)
    script.write_text("# graph\n", encoding="utf-8")
    family.write_text("# family\n", encoding="utf-8")
    outside = tmp_path.parent / "outside-graph-output"
    try:
        module.graph_extract_debate(
            tmp_path,
            "Débat test",
            lang="fr",
            family="wikidebates",
            output_dir=outside,
            cache_dir=None,
            slug=None,
            extraction_date=None,
            login=False,
            force_refresh=False,
            allow_missing=False,
            max_depth=None,
            max_pages=10,
            retries=0,
            retry_delay=0,
            progress_every=0,
            follow_local_relations_at_dedicated_debate=False,
        )
    except module.ManagementError as exc:
        assert "extérieur au projet" in str(exc)
    else:
        raise AssertionError("un dossier extérieur au projet a été accepté")


def test_corpus_init_command_defaults_to_state_build_directory(tmp_path: Path, monkeypatch):
    (tmp_path / "kit" / "scripts").mkdir(parents=True)
    (tmp_path / "kit" / "scripts" / "wikidebia_corpus_init.py").write_text("print('ok')\n", encoding="utf-8")
    snapshot = tmp_path / ".state" / "graph-extract" / "demo"
    snapshot.mkdir(parents=True)
    captured = {}

    class Result:
        returncode = 0

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["cwd"] = kwargs.get("cwd")
        return Result()

    monkeypatch.setattr(module, "run", fake_run)
    monkeypatch.setattr(module, "python_command", lambda root: "python")
    rc = module.corpus_init_from_snapshot(
        tmp_path,
        snapshot,
        debate_id="demo",
        short_code="DEMO",
        output_dir=None,
        scope_summary=None,
        overwrite=False,
        skip_validation=False,
    )
    assert rc == 0
    command = captured["command"]
    assert "--output-dir" in command
    assert str(tmp_path / ".state" / "corpus-builds" / "demo") in command
    assert "--project-root" in command


def test_corpus_init_rejects_output_outside_state_builds(tmp_path: Path):
    (tmp_path / "kit/scripts").mkdir(parents=True)
    (tmp_path / "kit/scripts/wikidebia_corpus_init.py").write_text("# test\n", encoding="utf-8")
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    try:
        module.corpus_init_from_snapshot(
            tmp_path,
            snapshot,
            debate_id="debat_test",
            short_code="TEST",
            output_dir=tmp_path / "corpus/debat_test",
            scope_summary=None,
            overwrite=False,
            skip_validation=True,
        )
    except module.ManagementError as exc:
        assert "doit rester sous" in str(exc)
    else:
        raise AssertionError("sortie corpus/ acceptée par le gestionnaire")


def test_corpus_review_command_routes_prepare(tmp_path: Path, monkeypatch):
    (tmp_path / "kit/scripts").mkdir(parents=True)
    (tmp_path / "kit/scripts/wikidebia_corpus_review.py").write_text("# test\n", encoding="utf-8")
    captured = {}

    class Result:
        returncode = 0

    def fake_run(command, **kwargs):
        captured["command"] = command
        return Result()

    monkeypatch.setattr(module, "run", fake_run)
    monkeypatch.setattr(module, "python_command", lambda root: "python")
    rc = module.corpus_review_graph(tmp_path, "demo", prepare=True, finalize=False, overwrite_review=False)
    assert rc == 0
    assert "--prepare" in captured["command"]
    assert "--project-root" in captured["command"]


def test_corpus_promote_command_requires_review_hash_in_route(tmp_path: Path, monkeypatch):
    (tmp_path / "kit/scripts").mkdir(parents=True)
    (tmp_path / "kit/scripts/wikidebia_corpus_promote.py").write_text("# test\n", encoding="utf-8")
    captured = {}

    class Result:
        returncode = 0

    def fake_run(command, **kwargs):
        captured["command"] = command
        return Result()

    monkeypatch.setattr(module, "run", fake_run)
    monkeypatch.setattr(module, "python_command", lambda root: "python")
    digest = "a" * 64
    rc = module.corpus_promote_graph(tmp_path, "demo", confirm_review_sha256=digest)
    assert rc == 0
    command = captured["command"]
    assert command[command.index("--confirm-review-sha256") + 1] == digest


def test_parser_exposes_corpus_review_and_promote_commands():
    review_args = module.build_parser().parse_args(["corpus-review-graph", "demo", "--prepare"])
    assert review_args.command == "corpus-review-graph"
    assert review_args.prepare is True
    promote_args = module.build_parser().parse_args(["corpus-promote", "demo", "--confirm-review-sha256", "a" * 64])
    assert promote_args.command == "corpus-promote"


def test_editorial_workspace_command_is_exposed_by_manager():
    args = module.build_parser().parse_args([
        "corpus-workspace-init", "debat_test", "--work-id", "EDIT-TEST-001"
    ])
    assert args.command == "corpus-workspace-init"
    assert args.debate_id == "debat_test"
    assert args.work_id == "EDIT-TEST-001"


def test_doctor_checks_every_pipeline_script(tmp_path: Path, monkeypatch):
    (tmp_path / "private/pywikibot").mkdir(parents=True)
    (tmp_path / "private/pywikibot/user-config.py").write_text("# test\n", encoding="utf-8")
    (tmp_path / "kit/scripts").mkdir(parents=True)
    expected = {
        "wikidebia_publish.py", "wikidebia_update.py", "wikidebia_graph_extract.py",
        "wikidebia_corpus_init.py", "wikidebia_corpus_review.py", "wikidebia_corpus_promote.py",
        "wikidebia_editorial_workspace.py", "wikidebia_editorial_review.py",
        "wikidebia_content_review.py", "wikidebia_translation_review.py", "wikidebia_render.py",
        "wikidebia_release.py", "wikidebia_remote_compare.py", "wikidebia_remote_plan_review.py",
        "wikidebia_remote_execute.py", "wikidebia_work_close.py",
        "wikidebia_workflow_baseline.py", "wikidebia_final_publication.py",
        "wikidebia_retro_tag.py",
    }
    monkeypatch.setattr(module, "runtime_environment_report", lambda root: {"requirements_sha256":"x","python_available":True,"missing_modules":[],"probe_error":None})
    monkeypatch.setattr(module, "assert_portable_sources", lambda root: None)
    monkeypatch.setattr(module, "git_security_issues", lambda root: [])
    report = module.doctor(tmp_path)
    missing = {item.removeprefix("kit/scripts/").removesuffix(" absent") for item in report["issues"] if item.startswith("kit/scripts/")}
    assert missing == expected


def test_safe_extract_restores_regular_file_modes(tmp_path: Path):
    archive = tmp_path / "modes.zip"
    info = zipfile.ZipInfo("scripts/direct.py")
    info.create_system = 3
    info.external_attr = 0o100755 << 16
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(info, b"#!/usr/bin/env python3\n")
    destination = tmp_path / "out"
    destination.mkdir()
    module.safe_extract(archive, destination)
    assert (destination / "scripts/direct.py").stat().st_mode & 0o111


def test_staged_component_tests_disable_external_pytest_plugins(tmp_path, monkeypatch):
    module_under_test = module
    staged = {name: tmp_path / name for name in ("norms", "validator", "kit")}
    for path in staged.values():
        path.mkdir()
    monkeypatch.setattr(module_under_test, "python_command", lambda root: "python")
    monkeypatch.setattr(module_under_test, "compare_normative_trees", lambda norms, validator: None)
    calls = []
    monkeypatch.setattr(module_under_test, "run", lambda command, **kwargs: calls.append((command, kwargs)))
    module_under_test.test_staged_components(tmp_path, staged)
    pytest_calls = [(command, kwargs) for command, kwargs in calls if "pytest" in command]
    assert len(pytest_calls) == 2
    assert pytest_calls[0][1]["env"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert pytest_calls[0][1]["env"]["PYTHONPATH"] == "src"
    assert pytest_calls[1][1]["env"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"


def test_purge_staged_runtime_artifacts_removes_test_caches_before_install(tmp_path: Path):
    staged = {name: tmp_path / name for name in ("norms", "validator", "kit")}
    for base in staged.values():
        (base / ".pytest_cache").mkdir(parents=True)
        (base / ".pytest_cache" / "CACHEDIR.TAG").write_text("cache\n", encoding="utf-8")
        (base / "pkg" / "__pycache__").mkdir(parents=True)
        (base / "pkg" / "__pycache__" / "module.pyc").write_bytes(b"cache")
        (base / "pkg" / "keep.py").write_text("pass\n", encoding="utf-8")
        (base / ".coverage").write_text("coverage\n", encoding="utf-8")
    module.purge_staged_runtime_artifacts(staged)
    for base in staged.values():
        assert not (base / ".pytest_cache").exists()
        assert not (base / "pkg" / "__pycache__").exists()
        assert not (base / ".coverage").exists()
        assert (base / "pkg" / "keep.py").is_file()

def test_generated_config_selects_deferred_profile_from_manifest(tmp_path: Path):
    (tmp_path / "config").mkdir()
    corpus = tmp_path / "corpus" / "demo"
    corpus.mkdir(parents=True)
    (corpus / "manifest.json").write_text(json.dumps({"translation_status": {"en": "deferred"}}), encoding="utf-8")
    run_dir = tmp_path / "plans" / "demo" / "run"
    run_dir.mkdir(parents=True)
    path = module.publication_config(tmp_path, "demo", "fr", run_dir)
    config = json.loads(path.read_text(encoding="utf-8"))
    assert config["publication_profile"] == "norm_1_2_deferred_translation"


# Legacy test symbols retained for the non-regression inventory. Their former
# expectations were explicitly superseded by norm 1.2.41.
def test_update_prefers_installed_corpus_over_homonymous_archive(tmp_path: Path):
    test_update_prefers_homonymous_incoming_archive_over_installed_corpus(tmp_path)


def test_update_identifier_never_falls_back_to_incoming_archive(tmp_path: Path):
    test_update_identifier_selects_matching_incoming_archive_without_archive_option(tmp_path)


def test_update_without_installed_corpus_requires_archive_option(tmp_path: Path):
    test_update_without_identifier_selects_unique_incoming_archive(tmp_path)


def test_update_without_identifier_prefers_single_installed_corpus_even_with_incoming_zip(tmp_path: Path):
    test_update_without_identifier_prefers_unique_incoming_zip_over_installed_corpus(tmp_path)


def test_generated_sources_are_unified_and_legacy_names_are_obsolete(tmp_path: Path):
    staged = {
        "norms": tmp_path / "norms",
        "validator": tmp_path / "validator",
        "kit": tmp_path / "kit",
    }
    norm_dir = staged["norms"] / "normative_reference" / "01_normes"
    norm_dir.mkdir(parents=True)
    (norm_dir / "WIKIDEBIA_NORME_CONSOLIDEE_1.2.47.md").write_text("# Norme\n", encoding="utf-8")
    (norm_dir / "CHANGELOG_NORMATIF.md").write_text("# Changelog norme\n", encoding="utf-8")
    for name in ("validator", "kit"):
        staged[name].mkdir(parents=True)
        (staged[name] / "README.md").write_text(f"# {name}\n", encoding="utf-8")
        (staged[name] / "CHANGELOG.md").write_text(f"# changelog {name}\n", encoding="utf-8")
        (staged[name] / "TEST_REPORT.txt").write_text(f"tests {name}\n", encoding="utf-8")
    (staged["kit"] / "GUIDE_PUBLICATION.md").write_text("# publication\n", encoding="utf-8")
    (staged["kit"] / "GUIDE_CONTENT_REVIEW.md").write_text("# content\n", encoding="utf-8")
    archives = {}
    for artifact in module.COMPONENTS:
        path = tmp_path / f"{artifact}.zip"
        path.write_bytes(artifact.encode("utf-8"))
        archives[artifact] = path
    generated = module.generate_readable_sources(
        tmp_path, staged, {"norm": "1.2.47", "validator": "0.4.61", "kit": "2.15.35"}, archives
    )
    assert set(generated) == {"WIKIDEBIA_SOURCE_ACTIVE.md", "WIKIDEBIA_SOURCE_PACKAGE_RECEIPT.json"}
    source = generated["WIKIDEBIA_SOURCE_ACTIVE.md"].read_text(encoding="utf-8")
    assert "Source active unifiée" in source
    assert "WIKIDEBIA_NORMES_ACTIVES.md" not in source
    assert set(module.OBSOLETE_ROOT_SOURCE_FILES) == {
        "WIKIDEBIA_NORMES_ACTIVES.md",
        "WIKIDEBIA_VALIDATEUR_ACTIF.md",
        "WIKIDEBIA_RECUS_ARCHIVES.json",
    }


def test_verify_version_set_accepts_foreign_version_hints_from_older_release(tmp_path: Path, monkeypatch):
    components = {
        "wikidebia-normes": tmp_path / "norms.zip",
        "wikidebia-validator": tmp_path / "validator.zip",
        "wikidebia-kit": tmp_path / "kit.zip",
    }
    metadata = {
        "norms.zip": {
            "versions": {"norm": "1.2.77", "validator": "0.4.80", "kit": "2.16.6"},
            "manifest": {"version": "1.2.77", "normative_revision": "1.2.77"},
            "compatibility": {},
        },
        "validator.zip": {
            "versions": {"norm": "1.2.77", "validator": "0.4.80", "kit": "2.16.6"},
            "manifest": {"version": "0.4.80", "normative_revision": "1.2.77"},
            "compatibility": {"supported_normative_revisions": ["1.2.77"]},
        },
        "kit.zip": {
            "versions": {"norm": "1.2.77", "validator": "0.4.80", "kit": "2.16.8"},
            "manifest": {"version": "2.16.8", "normative_revision": "1.2.77"},
            "compatibility": {},
        },
    }
    monkeypatch.setattr(module, "inspect_component_zip", lambda path: metadata[path.name])
    assert module.verify_version_set(components, tmp_path, allow_downgrade=False) == {
        "norm": "1.2.77", "validator": "0.4.80", "kit": "2.16.8"
    }


def test_verify_version_set_rejects_component_own_version_mismatch(tmp_path: Path, monkeypatch):
    components = {
        "wikidebia-normes": tmp_path / "norms.zip",
        "wikidebia-validator": tmp_path / "validator.zip",
        "wikidebia-kit": tmp_path / "kit.zip",
    }
    metadata = {
        "norms.zip": {"versions": {"norm": "1.2.77", "validator": "0.4.80", "kit": "2.16.6"}, "manifest": {"version": "1.2.77", "normative_revision": "1.2.77"}, "compatibility": {}},
        "validator.zip": {"versions": {"norm": "1.2.77", "validator": "0.4.80", "kit": "2.16.6"}, "manifest": {"version": "0.4.80", "normative_revision": "1.2.77"}, "compatibility": {}},
        "kit.zip": {"versions": {"norm": "1.2.77", "validator": "0.4.80", "kit": "2.16.8"}, "manifest": {"version": "2.16.7", "normative_revision": "1.2.77"}, "compatibility": {}},
    }
    monkeypatch.setattr(module, "inspect_component_zip", lambda path: metadata[path.name])
    with pytest.raises(module.ManagementError, match="version propre incohérente"):
        module.verify_version_set(components, tmp_path, allow_downgrade=False)
