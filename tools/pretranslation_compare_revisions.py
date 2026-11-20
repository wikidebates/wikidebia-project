#!/usr/bin/env python3
"""Compare pretranslation/resume paths at two local Git revisions, entirely offline.

Only tracked source files are materialized into temporary directories using
local `git archive`. The frozen snapshot is only read and is never archived,
copied to GitHub, published, translated, or written to. Each benchmark report
is independently verified and the source contract must remain identical in
every run, including across revisions.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import statistics
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Sequence


# Baseline preceding the parser improvements in PR #181 and PR #182;
# the schema-validator optimizations of PR #178/#179 are already present.
PARSER_BASELINE_SHA = "ba366eb79b7dc2dc7c1cfe32a54508ed0feac20a"
# Earlier baseline before the schema and parser optimization series.
FULL_BASELINE_SHA = "065bb4af6c895a456d7a92e1c9615115f134d5d7"
SCENARIOS = (
    "cold_build_validate_receipt",
    "resume_after_build_before_receipt",
    "resume_exact_verified_receipt",
)
BENCHMARK_FILE = "kit/scripts/wikidebia_pretranslation_benchmark.py"
SCHEMA = "wikidebia-pretranslation-revision-comparison-1.0"
SHA_PATTERN = re.compile(r"[0-9a-fA-F]{40}\Z")
DIGEST_PATTERN = re.compile(r"[0-9a-fA-F]{64}\\Z")


class RevisionComparisonError(RuntimeError):
    """Fail closed on unavailable revisions, changed input, or invalid reports."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _run_git(repo: Path, *argv: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *argv],
        text=True, capture_output=True, check=False,
    )
    if result.returncode:
        # Do not echo Git's diagnostics, which may include local/private paths.
        raise RevisionComparisonError("Git local indisponible ou commit absent")
    return result.stdout.strip()


def _resolve_revision(repo: Path, revision: str) -> str:
    if revision != "HEAD" and not SHA_PATTERN.fullmatch(revision):
        raise RevisionComparisonError(
            "Les révisions doivent être HEAD ou un SHA Git complet (40 caractères)"
        )
    sha = _run_git(repo, "rev-parse", "--verify", f"{revision}^{{commit}}")
    if not SHA_PATTERN.fullmatch(sha):
        raise RevisionComparisonError("Git n'a pas retourné un identifiant de commit valide")
    return sha.lower()


def _snapshot_root(repo: Path, snapshot: Path) -> Path:
    source = snapshot.expanduser()
    if not source.is_absolute():
        source = repo / source
    if source.is_symlink() or not source.is_dir():
        raise RevisionComparisonError("Le snapshot doit être un répertoire réel non symbolique")
    source = source.resolve()
    if (source / "snapshot_manifest.json").is_file():
        source = source.parent
    if not (source / "snapshot" / "snapshot_manifest.json").is_file():
        raise RevisionComparisonError(
            "Le chemin doit viser une extraction figée ou son dossier snapshot"
        )
    if source.is_symlink() or (source / "snapshot").is_symlink():
        raise RevisionComparisonError("Une extraction via un lien symbolique est interdite")
    return source


def _output_path(repo: Path, snapshot: Path, output: Path) -> Path:
    candidate = output.expanduser()
    if not candidate.is_absolute():
        candidate = repo / candidate
    if candidate.is_symlink():
        raise RevisionComparisonError("Un rapport ne peut pas remplacer un lien symbolique")
    resolved = candidate.resolve()
    if resolved == snapshot or resolved.is_relative_to(snapshot):
        raise RevisionComparisonError("Le rapport ne peut pas être écrit dans l'extraction")
    return resolved


def _materialize_revision(repo: Path, sha: str, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=False)
    tar_path = target.parent / f"{target.name}.tar"
    try:
        with tar_path.open("wb") as archive_file:
            process = subprocess.run(
                ["git", "-C", str(repo), "archive", "--format=tar", sha],
                stdout=archive_file, stderr=subprocess.DEVNULL, check=False,
            )
        if process.returncode:
            raise RevisionComparisonError("Impossible d'archiver le commit local")
        with tarfile.open(tar_path, mode="r:") as archive:
            for member in archive.getmembers():
                name = PurePosixPath(member.name)
                if (
                    name.is_absolute() or ".." in name.parts
                    or not (member.isfile() or member.isdir())
                ):
                    raise RevisionComparisonError(
                        "L'archive Git contient un chemin ou un type de fichier non sûr"
                    )
            archive.extractall(target, filter="data")
    finally:
        tar_path.unlink(missing_ok=True)
    if not (target / BENCHMARK_FILE).is_file():
        raise RevisionComparisonError("Le commit ne contient pas le benchmark requis")


def _check_benchmark_report(raw: dict[str, Any]) -> dict[str, Any]:
    report = dict(raw)
    claimed = report.pop("report_sha256", None)
    if not isinstance(claimed, str) or claimed != _sha256(_canonical_json(report)):
        raise RevisionComparisonError("Empreinte du rapport de benchmark invalide")
    if report.get("schema") != "wikidebia-pretranslation-benchmark-1.0":
        raise RevisionComparisonError("Schéma de rapport incompatible")
    fixture = report.get("fixture", {})
    quality = report.get("quality_controls", {})
    expected = {
        "same_build_contract": True,
        "cold_validation_passed": True,
        "interrupted_validation_passed": True,
        "exact_receipt_verified": True,
        "translation_logic_exercised": False,
        "wiki_access_performed": False,
        "real_snapshot_used": True,
    }
    if fixture.get("kind") != "snapshot" or quality != expected:
        raise RevisionComparisonError("Contrôle d'intégrité, de reprise ou de hors-ligne non satisfait")
    for name in SCENARIOS:
        item = report.get("scenarios", {}).get(name)
        if not isinstance(item, dict) or item.get("sample_count") != 1:
            raise RevisionComparisonError("Scénario manquant ou incomplet : " + name)
        if not isinstance(item.get("median_seconds"), (int, float)):
            raise RevisionComparisonError("Durée de scénario absente")
        if not isinstance(item.get("stage_timings_seconds"), dict):
            raise RevisionComparisonError("Détail d'étape manquant")
    if not isinstance(fixture.get("build_contract_sha256"), str):
        raise RevisionComparisonError("Empreinte de contrat absente")
    if not isinstance(fixture.get("snapshot_manifest_sha256"), str):
        raise RevisionComparisonError("Empreinte de snapshot absente")
    return report


def _isolated_environment(tree: Path) -> dict[str, str]:
    # No API tokens, Pywikibot passwords, cloud credentials, or home-directory
    # user configuration are passed into the measured benchmark processes.
    allowed = ("PATH", "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE",
               "SYSTEMROOT", "WINDIR", "TMPDIR", "TMP", "TEMP",
               "VIRTUAL_ENV", "LD_LIBRARY_PATH")
    result = {key: os.environ[key] for key in allowed if key in os.environ}
    result["PYTHONPATH"] = str(tree / "kit" / "scripts")
    result["PYTHONNOUSERSITE"] = "1"
    result["PYTHONDONTWRITEBYTECODE"] = "1"
    return result


def _run_revision(tree: Path, snapshot: Path, python: Path) -> dict[str, Any]:
    argv = [
        str(python), str(tree / BENCHMARK_FILE),
        "--project-root", str(tree),
        "--snapshot", str(snapshot),
        "--iterations", "1",
        "--machine-readable",
    ]
    result = subprocess.run(
        argv, cwd=tree, env=_isolated_environment(tree),
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        raise RevisionComparisonError(
            "Le benchmark hors ligne a échoué (code "
            f"{result.returncode}); aucun résultat n'est accepté"
        )
    try:
        raw = json.loads(result.stdout)
        if not isinstance(raw, dict):
            raise ValueError("not an object")
    except (json.JSONDecodeError, ValueError) as exc:
        raise RevisionComparisonError("Le benchmark n'a pas renvoyé un rapport JSON") from exc
    return _check_benchmark_report(raw)


# Executed only in archived, trusted local Git code and the temporary directory.
# The caller receives file digests, never page contents, and never logs paths.
_FINGERPRINT_BUILD_SCRIPT = """
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
import wikidebia_corpus_init as ci

source = Path(sys.argv[1])
with tempfile.TemporaryDirectory(prefix="wikidebia-frozen-build-parity-") as tmp:
    root = Path(tmp) / "build"
    with patch.object(ci, "now_iso", lambda: "2026-11-20T12:00:00+00:00"):
        build = ci.build_corpus(
            source, root, debate_id="benchmark_pretranslation",
            short_code="BENCH", scope_summary=None, overwrite=False,
        )
    fingerprints = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*")) if path.is_file()
    }
    print(json.dumps({
        "status": build["status"],
        "build_contract_sha256": build["build_contract_sha256"],
        "files": fingerprints,
    }, ensure_ascii=False, sort_keys=True))
"""


def _fingerprint_built_corpus(
    tree: Path, snapshot: Path, python: Path,
) -> tuple[str, dict[str, str]]:
    result = subprocess.run(
        [str(python), "-c", _FINGERPRINT_BUILD_SCRIPT, str(snapshot)],
        cwd=tree, env=_isolated_environment(tree),
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        raise RevisionComparisonError(
            "La reconstruction temporaire hors ligne a échoué ; parité non démontrée"
        )
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RevisionComparisonError("La reconstruction n'a pas produit de preuve JSON") from exc
    if (
        not isinstance(report, dict) or report.get("status") != "created"
        or not isinstance(report.get("build_contract_sha256"), str)
        or not isinstance(report.get("files"), dict)
        or not report["files"]
        or any(
            not isinstance(path, str) or not isinstance(digest, str)
            or not DIGEST_PATTERN.fullmatch(digest)
            for path, digest in report["files"].items()
        )
    ):
        raise RevisionComparisonError("Preuve SHA-256 des fichiers construits invalide")
    return report["build_contract_sha256"], report["files"]


def _summary(values: list[float]) -> dict[str, Any]:
    return {
        "samples_seconds": [round(item, 6) for item in values],
        "median_seconds": round(statistics.median(values), 6),
        "population_stddev_seconds": round(statistics.pstdev(values), 6),
        "minimum_seconds": round(min(values), 6),
        "maximum_seconds": round(max(values), 6),
    }


def _library_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def compare_revisions(
    repo: Path, snapshot: Path, *,
    baseline: str = PARSER_BASELINE_SHA, candidate: str = "HEAD",
    iterations: int = 3, python: Path | None = None,
) -> dict[str, Any]:
    if not (3 <= iterations <= 20):
        raise RevisionComparisonError("Le nombre de passages doit être compris entre 3 et 20")
    repo = repo.expanduser().resolve()
    if not (repo / ".git").exists():
        raise RevisionComparisonError("Le dossier n'est pas un dépôt Git local")
    source = _snapshot_root(repo, snapshot)
    before = _resolve_revision(repo, baseline)
    after = _resolve_revision(repo, candidate)
    interpreter = python or Path(sys.executable)
    if not interpreter.is_file():
        raise RevisionComparisonError("L'interpréteur Python courant est introuvable")
    samples: dict[str, list[dict[str, Any]]] = {"baseline": [], "candidate": []}
    manifest_sha: str | None = None
    contract_sha: str | None = None
    fixture_count: int | None = None

    with tempfile.TemporaryDirectory(prefix="wikidebia-real-pretranslation-pair-") as folder:
        temporary = Path(folder).resolve()
        if temporary == source or temporary.is_relative_to(source):
            raise RevisionComparisonError("Le répertoire temporaire ne peut pas être dans le snapshot")
        folders = {"baseline": temporary / "baseline", "candidate": temporary / "candidate"}
        for label, revision in (("baseline", before), ("candidate", after)):
            _materialize_revision(repo, revision, folders[label])
        source_hashes = {
            label: _sha256((tree / BENCHMARK_FILE).read_bytes())
            for label, tree in folders.items()
        }
        if source_hashes["baseline"] != source_hashes["candidate"]:
            raise RevisionComparisonError(
                "Le programme de benchmark diffère entre les commits ; comparaison refusée"
            )
        # A matching source contract is not enough to prove that parsed page
        # content is identical: compare EVERY generated byte under a frozen
        # timestamp. Filename-level evidence never leaves this process.
        built = {
            label: _fingerprint_built_corpus(tree, source, interpreter)
            for label, tree in folders.items()
        }
        if built["baseline"] != built["candidate"]:
            raise RevisionComparisonError(
                "Les fichiers construits par les deux révisions diffèrent ; comparaison annulée"
            )
        parity_contract, parity_files = built["baseline"]
        for i in range(iterations):
            order = ("baseline", "candidate") if i % 2 else ("candidate", "baseline")
            for label in order:
                report = _run_revision(folders[label], source, interpreter)
                fixture = report["fixture"]
                current_manifest = fixture["snapshot_manifest_sha256"]
                current_contract = fixture["build_contract_sha256"]
                current_count = fixture["arguments"]
                if manifest_sha is None:
                    manifest_sha = current_manifest
                    contract_sha = current_contract
                    fixture_count = current_count
                elif (
                    manifest_sha != current_manifest or
                    contract_sha != current_contract or
                    fixture_count != current_count
                ):
                    raise RevisionComparisonError(
                        "Le snapshot ou le contrat a changé pendant la comparaison ; résultats annulés"
                    )
                samples[label].append(report)

    if parity_contract != contract_sha:
        raise RevisionComparisonError(
            "Le contrat de reconstruction ne correspond pas aux rapports de benchmark"
        )
    overview: dict[str, Any] = {}
    for name in SCENARIOS:
        rows = {}
        for label in ("baseline", "candidate"):
            reports = samples[label]
            values = [r["scenarios"][name]["median_seconds"] for r in reports]
            stage_names = set(reports[0]["scenarios"][name]["stage_timings_seconds"])
            if any(set(r["scenarios"][name]["stage_timings_seconds"]) != stage_names for r in reports):
                raise RevisionComparisonError("Liste d'étapes incohérente entre répétitions")
            stages = {
                stage: _summary([
                    r["scenarios"][name]["stage_timings_seconds"][stage]["median_seconds"]
                    for r in reports
                ])
                for stage in sorted(stage_names)
            }
            rows[label] = {**_summary(values), "stage_timings_seconds": stages}
        previous = rows["baseline"]["median_seconds"]
        newer = rows["candidate"]["median_seconds"]
        rows["change"] = {
            "seconds_avoided": round(previous - newer, 6),
            "elapsed_reduction_percent": round(100 * (1 - newer / previous), 2)
            if previous else None,
        }
        overview[name] = rows

    result = {
        "schema": SCHEMA,
        "baseline_sha": before,
        "candidate_sha": after,
        "same_revision": before == after,
        "benchmark_sha256": source_hashes["baseline"],
        "snapshot_manifest_sha256": manifest_sha,
        "build_contract_sha256": contract_sha,
        "argument_count": fixture_count,
        "identical_built_file_count": len(parity_files),
        "iterations_per_revision": iterations,
        "ordering": "rotated and alternating, candidate first on even rounds",
        "environment": {
            "python_version": sys.version.split()[0],
            "jsonschema_version": _library_version("jsonschema"),
            "referencing_version": _library_version("referencing"),
        },
        "scenarios": overview,
        "quality_controls": {
            "signed_individual_reports_verified": True,
            "identical_source_manifest_and_build_contract": True,
            "identical_built_file_sha256": True,
            "initial_and_interrupted_validations_passed": True,
            "exact_receipts_verified": True,
            "wiki_access_performed": False,
            "translation_logic_exercised": False,
            "llm_calls_performed": 0,
            "snapshot_read_only": True,
        },
        "limitations": [
            "Les gains ne concernent que la préparation technique, pas la traduction ni la publication.",
            "La charge système et les caches disque influencent les durées.",
            "Une extraction modifiée pendant le benchmark invalide la comparaison.",
            "Aucune économie de tokens ou de crédits Codex n'est calculée.",
            "Le programme de benchmark est strictement identique dans les deux révisions.",
        ],
    }
    result["report_sha256"] = _sha256(_canonical_json(result))
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--baseline", default=PARSER_BASELINE_SHA,
                        help="SHA complet du commit de référence, par défaut avant les PR #181/#182")
    parser.add_argument("--candidate", default="HEAD",
                        help="SHA complet du candidat ou HEAD (par défaut)")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--output", type=Path,
                        help="Rapport JSON local, hors du snapshot; par défaut stdout uniquement")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = args.project_root.expanduser().resolve()
    snapshot = _snapshot_root(repo, args.snapshot)
    output = _output_path(repo, snapshot, args.output) if args.output else None
    report = compare_revisions(
        repo, snapshot, baseline=args.baseline, candidate=args.candidate,
        iterations=args.iterations,
    )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.is_symlink() or output.resolve().is_relative_to(snapshot):
            raise RevisionComparisonError("Le rapport ne peut pas modifier le snapshot")
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RevisionComparisonError as exc:
        print(f"COMPARAISON PRÉTRADUCTION BLOQUÉE : {exc}", file=sys.stderr)
        raise SystemExit(2)
