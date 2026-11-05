#!/usr/bin/env python3
"""Select and optionally run local validations from the current Git diff."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

from wikidebia_corpus_build import relative_to_project, write_json
from wikidebia_update import sha_object


GENERATED_KIT_METADATA = {
    "kit/PACKAGE_MANIFEST_SHA256.json",
    "kit/PACKAGE_RECEIPT.json",
    "kit/TEST_REPORT.txt",
}
SHARED_KIT_SCRIPTS = {
    "wikidebia_corpus_build.py",
    "wikidebia_editorial_workspace.py",
    "wikidebia_render.py",
    "wikidebia_translation_review.py",
    "wikidebia_update.py",
}
DOCUMENT_NAMES = {"README.md", "AGENTS.md", "CHANGELOG.md"}


class ChangedTestError(RuntimeError):
    pass


def _git(project_root: Path, *arguments: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=project_root, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if check and result.returncode:
        raise ChangedTestError(result.stderr.strip() or "Commande Git impossible")
    return result.stdout


def changed_files(project_root: Path, base: str) -> list[str]:
    project_root = project_root.expanduser().resolve()
    _git(project_root, "rev-parse", "--verify", base)
    values: set[str] = set()
    for arguments in (
        ("diff", "--name-only", f"{base}...HEAD"),
        ("diff", "--name-only"),
        ("diff", "--name-only", "--cached"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        values.update(line for line in _git(project_root, *arguments).splitlines() if line)
    return sorted(values)


def select_validations(paths: Iterable[str]) -> dict[str, Any]:
    changed = sorted(set(paths))
    kit_tests: set[str] = set()
    validator = deploy = full = memory_verify = False
    reasons: list[str] = []
    for path in changed:
        item = Path(path)
        if path in GENERATED_KIT_METADATA:
            continue
        if path.startswith("translation-memory/"):
            kit_tests.add("kit/tests/test_wikidebia_translation_memory.py")
            memory_verify = True
            continue
        if path.startswith("kit/tests/") and path.endswith(".py"):
            kit_tests.add(path)
            continue
        if path.startswith("kit/scripts/") and path.endswith(".py"):
            name = item.name
            if name in SHARED_KIT_SCRIPTS:
                full = True
                reasons.append(f"shared_kit_script:{name}")
                continue
            candidate = f"kit/tests/test_{name}"
            kit_tests.add(candidate)
            if name == "wikidebia_manage.py" or name.startswith("wikidebia_"):
                kit_tests.add("kit/tests/test_wikidebia_manage.py")
            continue
        if path.startswith("validator/"):
            validator = True
            continue
        if path.startswith("deploy/"):
            deploy = True
            continue
        if (
            path.startswith("kit/GUIDE_")
            or item.name in DOCUMENT_NAMES
            or path.startswith(".github/workflows/")
        ):
            continue
        if path.startswith("kit/") and item.suffix in {".md", ".txt", ".json"}:
            continue
        full = True
        reasons.append(f"unknown_or_shared:{path}")
    if full:
        kit_tests = {"kit/tests"}
        validator = True
        deploy = True
    return {
        "changed_files": changed,
        "full_validation": full,
        "full_validation_reasons": reasons,
        "kit_test_paths": sorted(kit_tests),
        "validator_tests": validator,
        "deployment_tests": deploy,
        "translation_memory_verify": memory_verify,
    }


def _commands(project_root: Path, base: str, selection: dict[str, Any]) -> list[dict[str, Any]]:
    python = sys.executable
    commands: list[dict[str, Any]] = [
        {"name": "diff_base", "argv": ["git", "diff", "--check", f"{base}...HEAD"]},
        {"name": "diff_worktree", "argv": ["git", "diff", "--check"]},
    ]
    if selection["kit_test_paths"]:
        commands.append({
            "name": "kit_tests",
            "argv": [python, "-m", "pytest", "-q", *selection["kit_test_paths"]],
            "env": {"PYTHONPATH": "kit/scripts"},
        })
    if selection["validator_tests"]:
        commands.append({
            "name": "validator_tests",
            "argv": [python, "-m", "pytest", "-q", "validator/tests"],
            "env": {"PYTHONPATH": "validator/src"},
        })
    if selection["deployment_tests"]:
        commands.append({
            "name": "deployment_tests",
            "argv": [python, "-m", "unittest", "discover", "-s", "deploy/tests", "-v"],
        })
    if selection["translation_memory_verify"]:
        commands.append({
            "name": "translation_memory_verify",
            "argv": ["./wikidebia", "corpus-translation-memory", "verify"],
        })
    return commands


def build_plan(project_root: Path, base: str) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    selection = select_validations(changed_files(project_root, base))
    plan: dict[str, Any] = {
        "schema": "wikidebia-changed-test-plan-1.0",
        "base": base,
        **selection,
        "commands": _commands(project_root, base, selection),
        "remote_access_performed": False,
        "remote_write_performed": False,
    }
    plan["plan_sha256"] = sha_object(plan)
    return plan


def execute_plan(project_root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    results = []
    for command in plan["commands"]:
        environment = os.environ.copy()
        environment.update(command.get("env") or {})
        completed = subprocess.run(
            command["argv"], cwd=project_root, env=environment, check=False,
        )
        results.append({"name": command["name"], "returncode": completed.returncode})
        if completed.returncode:
            break
    receipt: dict[str, Any] = {
        "schema": "wikidebia-changed-test-receipt-1.0",
        "plan_sha256": plan["plan_sha256"],
        "status": "passed" if len(results) == len(plan["commands"]) and all(
            row["returncode"] == 0 for row in results
        ) else "failed",
        "results": results,
        "remote_access_performed": False,
        "remote_write_performed": False,
    }
    receipt["receipt_sha256"] = sha_object(receipt)
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--machine-readable", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.project_root.expanduser().resolve()
    plan = build_plan(root, args.base)
    output: dict[str, Any] = {"plan": plan}
    code = 0
    if args.execute:
        receipt = execute_plan(root, plan)
        output["receipt"] = receipt
        code = 0 if receipt["status"] == "passed" else 2
    path = root / ".state/changed-test-plan.json"
    write_json(path, output)
    output["plan_path"] = relative_to_project(path, root)
    print(json.dumps(output, ensure_ascii=False, sort_keys=True) if args.machine_readable else json.dumps(output, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ChangedTestError, OSError, ValueError) as exc:
        print(f"SÉLECTION DE TESTS BLOQUÉE : {exc}", file=os.sys.stderr)
        raise SystemExit(2)
