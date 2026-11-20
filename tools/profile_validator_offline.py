#!/usr/bin/env python3
"""Profile Wikidéb'IA's unchanged validator on a frozen local extraction.

The historical source and the active repository are read only. A temporary
corpus is built using the normal signed-snapshot import checks. Timings and
function names are aggregated; page text, titles, findings and private paths
are never included in the report. Nothing is sent over the network.
"""
from __future__ import annotations

import argparse
import cProfile
import contextlib
import hashlib
import json
import os
import pstats
import statistics
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Sequence
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for _source in (ROOT / "kit/scripts", ROOT / "validator/src"):
    if str(_source) not in sys.path:
        sys.path.insert(0, str(_source))

from wikidebia_pretranslation_benchmark import _snapshot_source  # noqa: E402
from wikidebia_corpus_init import build_corpus  # noqa: E402
from wikidebia_validator import package as package_mod  # noqa: E402
from wikidebia_validator import schema_validation as schema_mod  # noqa: E402
from wikidebia_validator import validator as validator_mod  # noqa: E402

SCOPES = ("schema", "coherence", "graph", "files", "workflow")
STAGES = (
    "validate_all_schemas",
    "validate_coherence",
    "validate_graph",
    "validate_files",
    "validate_workflow",
)
METHODS = (
    (schema_mod.SchemaStore, "__init__"),
    (schema_mod.SchemaStore, "validate"),
    (package_mod.PackageContext, "safe_path"),
    (package_mod.PackageContext, "read_bytes"),
    (package_mod.PackageContext, "load_json"),
    (package_mod.PackageContext, "sha256"),
)
REPORT_SCHEMA = "wikidebia-validator-local-profile-1.0"


class ProfileError(RuntimeError):
    pass


def _canonical(data: Any) -> bytes:
    return json.dumps(
        data, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def _hash(data: Any) -> str:
    return hashlib.sha256(_canonical(data)).hexdigest()


def _seconds(values: list[float]) -> dict[str, Any]:
    if not values:
        raise ProfileError("Échantillons de profilage absents")
    return {
        "count": len(values),
        "median_seconds": round(statistics.median(values), 6),
        "min_seconds": round(min(values), 6),
        "max_seconds": round(max(values), 6),
        "samples_seconds": [round(value, 6) for value in values],
    }


def _normalize_report(raw: dict[str, Any]) -> dict[str, Any]:
    """Remove only the CLI's launcher-specific runtime attestation."""
    result = dict(raw)
    metrics = dict(result.get("metrics") or {})
    metrics.pop("runtime_attestation", None)
    result["metrics"] = metrics
    return result


def _isolated_env() -> dict[str, str]:
    # Credentials and Pywikibot configuration do not leave this process.
    names = (
        "PATH", "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE",
        "SYSTEMROOT", "WINDIR", "LD_LIBRARY_PATH",
    )
    env = {name: os.environ[name] for name in names if name in os.environ}
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _source_digest(source: Path) -> tuple[int, str]:
    """Check every source byte before and after, without emitting paths."""
    paths = sorted(path for path in source.rglob("*") if path.is_file())
    fingerprint = hashlib.sha256()
    for path in paths:
        if path.is_symlink():
            raise ProfileError("Lien symbolique interdit dans l'extraction")
        rel = path.relative_to(source).as_posix().encode("utf-8")
        payload = path.read_bytes()
        fingerprint.update(len(rel).to_bytes(8, "big"))
        fingerprint.update(rel)
        fingerprint.update(len(payload).to_bytes(8, "big"))
        fingerprint.update(hashlib.sha256(payload).digest())
    return len(paths), fingerprint.hexdigest()


def _normal_cli(package: Path) -> tuple[float, dict[str, Any]]:
    script = ROOT / "validator/scripts/wikidebia_validate.py"
    argv = [
        sys.executable, "-I", str(script), "validate", str(package),
        *(piece for scope in SCOPES for piece in ("--scope", scope)),
        "--format", "json",
    ]
    started = time.perf_counter()
    process = subprocess.run(
        argv, text=True, capture_output=True, env=_isolated_env(), check=False,
    )
    elapsed = time.perf_counter() - started
    try:
        report = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise ProfileError("Le sous-processus n'a pas produit un rapport JSON") from exc
    if not isinstance(report, dict) or process.returncode not in (0, 1):
        raise ProfileError("Le sous-processus n'a pas achevé la validation normalement")
    expected_code = 1 if (report.get("summary") or {}).get("errors", 0) else 0
    if expected_code != process.returncode:
        raise ProfileError("Le code retour et le rapport du validateur divergent")
    proof = (report.get("metrics") or {}).get("runtime_attestation")
    if not isinstance(proof, dict) or not proof.get("cli_sha256"):
        raise ProfileError("Attestation du lanceur officiel absente")
    return elapsed, _normalize_report(report)


def _timed_validation(
    package: Path, measures: dict[str, list[float]],
) -> tuple[float, dict[str, Any]]:
    def wrap(func: Callable[..., Any], name: str) -> Callable[..., Any]:
        def measured(*args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                measures[name].append(time.perf_counter() - started)
        return measured

    with contextlib.ExitStack() as stack:
        for name in STAGES:
            stack.enter_context(patch.object(
                validator_mod, name,
                wrap(getattr(validator_mod, name), "scope:" + name.removeprefix("validate_")),
            ))
        for cls, method in METHODS:
            label = "method:" + cls.__name__ + "." + method
            stack.enter_context(patch.object(
                cls, method, wrap(getattr(cls, method), label),
            ))
        started = time.perf_counter()
        data = validator_mod.validate_package(package, scopes=list(SCOPES)).to_dict()
        elapsed = time.perf_counter() - started
    return elapsed, _normalize_report(data)


def _safe_hotspots(profile: cProfile.Profile, top: int) -> list[dict[str, Any]]:
    # Only library code symbol names, never absolute paths or JSON values.
    rows = []
    for (filename, line, function), (_, calls, own, cumulative, _) in pstats.Stats(profile).stats.items():
        if cumulative < 0.0005:
            continue
        rows.append({
            "symbol": f"{Path(filename).name}:{line}:{function}",
            "calls": calls,
            "self_seconds": round(own, 6),
            "cumulative_seconds": round(cumulative, 6),
        })
    return sorted(rows, key=lambda row: row["cumulative_seconds"], reverse=True)[:top]


def _output_path(snapshot: Path, requested: Path) -> Path:
    candidate = requested if requested.is_absolute() else ROOT / requested
    if candidate.is_symlink():
        raise ProfileError("Le rapport ne peut pas remplacer un lien symbolique")
    target = candidate.expanduser().resolve()
    if target == snapshot or target.is_relative_to(snapshot):
        raise ProfileError("Le rapport ne peut pas être écrit dans l'extraction")
    return target


def profile_snapshot(
    requested: Path, *, iterations: int = 3, top: int = 20,
) -> dict[str, Any]:
    if not 2 <= iterations <= 12:
        raise ProfileError("Le nombre de répétitions doit être entre 2 et 12")
    if not 0 <= top <= 50:
        raise ProfileError("Le nombre de fonctions doit être entre 0 et 50")
    try:
        source, fixture = _snapshot_source(ROOT, requested)
    except (OSError, ValueError, RuntimeError) as exc:
        raise ProfileError("L'extraction figée est absente, incomplète ou non sûre") from exc
    source = source.resolve()
    before = _source_digest(source)
    measures: dict[str, list[float]] = defaultdict(list)
    cli_times: list[float] = []
    inprocess_times: list[float] = []
    expected: dict[str, Any] | None = None

    # Ensure tempfile itself cannot modify the source even with unusual TMPDIR.
    if Path(tempfile.gettempdir()).resolve().is_relative_to(source):
        raise ProfileError("Le dossier temporaire est à l'intérieur de l'extraction")
    with tempfile.TemporaryDirectory(prefix="wikidebia-validator-private-profile-") as folder:
        output = Path(folder).resolve() / "corpus"
        try:
            build = build_corpus(
                source, output,
                debate_id="benchmark_pretranslation",
                short_code="BENCH", scope_summary=None, overwrite=False,
            )
        except (OSError, ValueError, RuntimeError) as exc:
            raise ProfileError("La construction temporaire du corpus a échoué") from exc
        if build.get("status") != "created":
            raise ProfileError("Le corpus temporaire n'a pas été construit")
        for attempt in range(iterations):
            # Rotate order to reduce warm-cache and thermal bias.
            if attempt % 2:
                elapsed, direct = _timed_validation(output, measures)
                inprocess_times.append(elapsed)
                wall, child = _normal_cli(output)
                cli_times.append(wall)
            else:
                wall, child = _normal_cli(output)
                cli_times.append(wall)
                elapsed, direct = _timed_validation(output, measures)
                inprocess_times.append(elapsed)
            if child != direct:
                raise ProfileError("Les résultats du validateur officiel et instrumenté diffèrent")
            if expected is None:
                expected = direct
            elif expected != direct:
                raise ProfileError("Les résultats du validateur changent entre passages")

        hotspots: list[dict[str, Any]] = []
        if top:
            cprof = cProfile.Profile()
            cprof.enable()
            checked = validator_mod.validate_package(output, scopes=list(SCOPES)).to_dict()
            cprof.disable()
            if _normalize_report(checked) != expected:
                raise ProfileError("Le profilage détaillé a modifié le rapport")
            hotspots = _safe_hotspots(cprof, top)
    if before != _source_digest(source):
        raise ProfileError("L'extraction a changé pendant le profilage")

    breakdown = {
        label: {
            "calls": len(values),
            "cumulative_seconds": round(sum(values), 6),
            "median_per_call_seconds": round(statistics.median(values), 6),
        }
        for label, values in sorted(measures.items()) if values
    }
    result = {
        "schema": REPORT_SCHEMA,
        "arguments": fixture["arguments"],
        "source_file_count": before[0],
        "iterations": iterations,
        "python_version": sys.version.split()[0],
        "validation_scopes": list(SCOPES),
        "validator_subprocess": _seconds(cli_times),
        "validator_inprocess_instrumented": _seconds(inprocess_times),
        "breakdown": breakdown,
        "cprofile": hotspots,
        "quality_controls": {
            "source_unchanged": True,
            "official_cli_attestation_verified": True,
            "complete_reports_equal": True,
            "schema_validation_not_skipped": True,
            "wiki_access_performed": False,
            "translation_logic_exercised": False,
            "real_source_exported": False,
        },
        "cautions": [
            "Le profilage en Python ralentit les fonctions instrumentées.",
            "Les durées cumulées des méthodes s'imbriquent et ne s'additionnent pas.",
            "Seules les cinq portées du contrôle initial sont mesurées.",
            "La traduction, la publication et les crédits Codex ne sont pas mesurés.",
        ],
    }
    result["report_sha256"] = _hash(result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    source, _ = _snapshot_source(ROOT, args.snapshot)
    output = _output_path(source.resolve(), args.output) if args.output else None
    data = profile_snapshot(args.snapshot, iterations=args.iterations, top=args.top)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.is_symlink() or output.resolve().is_relative_to(source.resolve()):
            raise ProfileError("Rapport sous extraction interdit")
        output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProfileError as exc:
        print(f"PROFILAGE DU VALIDATEUR BLOQUÉ : {exc}", file=sys.stderr)
        raise SystemExit(2)
