#!/usr/bin/env python3
"""Benchmark local pretranslation resume paths without network or LLM calls."""
from __future__ import annotations

from wikidebia_release_info import KIT_VERSION, NORM_VERSION, VALIDATOR_VERSION

import argparse
import hashlib
import json
import platform
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from wikidebia_corpus_build import (
    CorpusBuildError,
    assert_no_symlinks,
    canonical_json,
    load_json,
    relative_to_project,
    write_json,
)
from wikidebia_corpus_init import (
    build_corpus,
    canonical_json_sha256,
    compute_build_contract,
    inspect_existing_build,
    run_validator,
    write_build_receipt,
)

REPORT_SCHEMA = "wikidebia-pretranslation-benchmark-1.0"
DEBATE_ID = "benchmark_pretranslation"
SHORT_CODE = "BENCH"
SYNTHETIC_ROOTS = 20
SYNTHETIC_BRANCHING_FACTOR = 3


class PretranslationBenchmarkError(RuntimeError):
    pass


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _snapshot_row(root: Path, title: str, relative: str, revision_id: int) -> dict[str, Any]:
    payload = (root / relative).read_bytes()
    return {
        "requested_title": title,
        "canonical_title": title,
        "relative_path": relative,
        "revision_id": revision_id,
        "revision_timestamp": "2026-01-01T00:00:00+00:00",
        "url": f"https://example.invalid/wiki/{title.replace(' ', '_')}",
        "redirect_chain": [],
        "fetched_at": "2026-01-01T00:00:00+00:00",
        "size_bytes": len(payload),
        "sha256": _sha256(payload),
    }


def make_synthetic_extraction(root: Path, *, arguments: int, payload_bytes: int) -> Path:
    if arguments < 2:
        raise PretranslationBenchmarkError("Le benchmark exige au moins deux arguments")
    if payload_bytes < 64:
        raise PretranslationBenchmarkError("payload-bytes doit être supérieur ou égal à 64")
    snapshot = root / "snapshot"
    argument_root = snapshot / "pages/arguments"
    argument_root.mkdir(parents=True)
    debate_text = (
        "{{Débat|rubriques=Philosophie|mots-clés=benchmark;reprise;traduction|"
        "date-création=2026-01-01}}\n"
    )
    (snapshot / "pages/debate.wiki").write_text(debate_text, encoding="utf-8")
    padding = "x" * payload_bytes
    argument_rows: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    titles: list[str] = []
    for index in range(1, arguments + 1):
        title = f"Argument synthétique {index:04d}"
        relative = f"pages/arguments/a{index:04d}.wiki"
        text = (
            "{{Argument|résumé=Argument de benchmark local "
            f"{index:04d} {padding}|rubriques=Philosophie|"
            "mots-clés=benchmark;reprise|date-création=2026-01-01}}\n"
        )
        (snapshot / relative).write_text(text, encoding="utf-8")
        argument_rows.append(_snapshot_row(snapshot, title, relative, index + 1))
        nodes.append({
            "titre": title,
            "titres_affichés_observés": [f"L'argument synthétique {index:04d} est pertinent"],
        })
        titles.append(title)
    snapshot_manifest = {
        "schema": "wikidebia-graph-snapshot-1.0",
        "kit_version": KIT_VERSION,
        "extractor_version": "benchmark-1.0",
        "extraction_date": "2026-01-01",
        "debate": _snapshot_row(snapshot, "Débat synthétique", "pages/debate.wiki", 1),
        "arguments": argument_rows,
        "crawl_options": {"synthetic_benchmark": True},
        "counts": {
            "debate_pages": 1,
            "argument_pages": arguments,
            "total_pages": arguments + 1,
        },
    }
    write_json(snapshot / "snapshot_manifest.json", snapshot_manifest)
    root_count = min(arguments, SYNTHETIC_ROOTS)
    roots = titles[:root_count]
    pro = roots[::2]
    con = roots[1::2]
    relations = []
    for child_offset, child_title in enumerate(titles[root_count:]):
        parent_index = child_offset // SYNTHETIC_BRANCHING_FACTOR
        relations.append({
            "source": titles[parent_index],
            "relation": "justification" if child_offset % 2 == 0 else "objection",
            "cible": child_title,
            "ordre": child_offset % SYNTHETIC_BRANCHING_FACTOR + 1,
        })
    graph = {
        "metadata": {
            "débat": "Débat synthétique",
            "occurrences_argumentatives": arguments,
            "frontières_débat_détaillé": {},
            "traduction_du_débat_requise": True,
            "traduction_anglaise_débat_vérifiée": False,
        },
        "arguments_pour_niveau_1": pro,
        "arguments_contre_niveau_1": con,
        "noeuds": nodes,
        "relations": relations,
    }
    graph_path = root / "benchmark_graphe_recursif_2026-01-01.json"
    write_json(graph_path, graph)
    declared_paths = [
        graph_path,
        snapshot / "snapshot_manifest.json",
        snapshot / "pages/debate.wiki",
        *sorted(argument_root.glob("*.wiki")),
    ]
    declared = []
    for path in declared_paths:
        payload = path.read_bytes()
        declared.append({
            "path": path.relative_to(root).as_posix(),
            "sha256": _sha256(payload),
            "size_bytes": len(payload),
        })
    write_json(root / "benchmark_manifest_sha256_2026-01-01.json", {
        "schema": "wikidebia-graph-extraction-package-1.0",
        "kit_version": KIT_VERSION,
        "extractor_version": "benchmark-1.0",
        "debate": "Débat synthétique",
        "extraction_date": "2026-01-01",
        "audit_status": "passed",
        "declared_file_count": len(declared),
        "files": declared,
    })
    return root


def _tree_metrics(root: Path) -> dict[str, int]:
    files = [path for path in root.rglob("*") if path.is_file() and not path.is_symlink()]
    return {
        "file_count": len(files),
        "size_bytes": sum(path.stat().st_size for path in files),
    }


def _snapshot_source(project_root: Path, requested: Path) -> tuple[Path, dict[str, Any]]:
    requested = requested.expanduser()
    if not requested.is_absolute():
        requested = project_root / requested
    if requested.is_symlink():
        raise PretranslationBenchmarkError("Le snapshot demandé est absent ou non sûr")
    requested = requested.resolve()
    if not requested.is_dir() or requested.is_symlink():
        raise PretranslationBenchmarkError("Le snapshot demandé est absent ou non sûr")
    if (requested / "snapshot/snapshot_manifest.json").is_file():
        source = requested
    elif (requested / "snapshot_manifest.json").is_file():
        source = requested.parent
    else:
        raise PretranslationBenchmarkError(
            "--snapshot doit viser une extraction ou son sous-répertoire snapshot"
        )
    assert_no_symlinks(source)
    manifest = load_json(source / "snapshot/snapshot_manifest.json", "manifeste du snapshot")
    if manifest.get("schema") != "wikidebia-graph-snapshot-1.0":
        raise PretranslationBenchmarkError("Schéma de snapshot non pris en charge")
    arguments = manifest.get("arguments") or []
    declared_count = int((manifest.get("counts") or {}).get("argument_pages") or 0)
    if not isinstance(arguments, list) or declared_count != len(arguments) or declared_count < 2:
        raise PretranslationBenchmarkError("Le snapshot ne contient pas un graphe représentatif")
    graph_paths = sorted(source.glob("*graphe_recursif*.json"))
    if len(graph_paths) != 1:
        raise PretranslationBenchmarkError("Le graphe récursif du snapshot est absent ou ambigu")
    graph = load_json(graph_paths[0], "graphe récursif du snapshot")
    roots = len(graph.get("arguments_pour_niveau_1") or []) + len(
        graph.get("arguments_contre_niveau_1") or []
    )
    try:
        source_path = relative_to_project(source, project_root)
    except CorpusBuildError:
        source_path = f"external:{source.name}"
    return source, {
        "kind": "snapshot",
        "source_path": source_path,
        "arguments": declared_count,
        "root_arguments": roots,
        "relations": len(graph.get("relations") or []),
        "snapshot_manifest_sha256": _sha256(
            (source / "snapshot/snapshot_manifest.json").read_bytes()
        ),
    }


def _output_path(
    project_root: Path, output: Path, snapshot: Path | None,
) -> Path:
    candidate = output if output.is_absolute() else project_root / output
    if candidate.is_symlink():
        raise PretranslationBenchmarkError("La sortie du benchmark est un lien symbolique")
    resolved = candidate.resolve()
    if snapshot is not None:
        source, _ = _snapshot_source(project_root, snapshot)
        if resolved == source or resolved.is_relative_to(source):
            raise PretranslationBenchmarkError(
                "La sortie du benchmark ne peut pas modifier l’extraction mesurée"
            )
    return resolved


def _measure(operation: Callable[[], Any]) -> tuple[float, Any]:
    started = time.perf_counter()
    result = operation()
    return time.perf_counter() - started, result


def _validated_build(project_root: Path, source: Path, output: Path) -> dict[str, Any]:
    result = build_corpus(
        source,
        output,
        debate_id=DEBATE_ID,
        short_code=SHORT_CODE,
        scope_summary=None,
        overwrite=False,
    )
    validation = run_validator(project_root, output)
    if validation.get("status") != "passed":
        raise PretranslationBenchmarkError("La validation du build synthétique a échoué")
    receipt = write_build_receipt(
        output,
        build_contract=result["build_contract"],
        validation=validation,
    )
    return {"build": result, "validation": validation, "receipt": receipt}


def _summary(samples: Sequence[float]) -> dict[str, Any]:
    median = statistics.median(samples)
    return {
        "samples_seconds": [round(value, 6) for value in samples],
        "median_seconds": round(median, 6),
        "minimum_seconds": round(min(samples), 6),
        "maximum_seconds": round(max(samples), 6),
    }


def _gain(reference: float, candidate: float) -> dict[str, Any]:
    return {
        "seconds_avoided": round(reference - candidate, 6),
        "elapsed_reduction_percent": round((1 - candidate / reference) * 100, 2) if reference else None,
        "speedup_factor": round(reference / candidate, 2) if candidate else None,
    }


def run_benchmark(
    project_root: Path,
    *,
    arguments: int,
    payload_bytes: int,
    iterations: int,
    snapshot: Path | None = None,
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    if iterations < 1:
        raise PretranslationBenchmarkError("iterations doit être supérieur ou égal à 1")
    cold_samples: list[float] = []
    interrupted_samples: list[float] = []
    exact_samples: list[float] = []
    contract_hashes: set[str] = set()
    with tempfile.TemporaryDirectory(prefix="wikidebia-pretranslation-benchmark-") as temp_name:
        temp_root = Path(temp_name)
        if snapshot is None:
            source = make_synthetic_extraction(
                temp_root / "source",
                arguments=arguments,
                payload_bytes=payload_bytes,
            )
            fixture = {
                "kind": "synthetic",
                "arguments": arguments,
                "root_arguments": min(arguments, SYNTHETIC_ROOTS),
                "relations": max(0, arguments - SYNTHETIC_ROOTS),
                "branching_factor": SYNTHETIC_BRANCHING_FACTOR,
                "payload_bytes_per_argument": payload_bytes,
            }
        else:
            source, fixture = _snapshot_source(project_root, snapshot)
        source_metrics = _tree_metrics(source)
        output_metrics: dict[str, int] | None = None
        for index in range(iterations):
            cold_output = temp_root / f"cold-{index}"
            cold_elapsed, cold = _measure(
                lambda output=cold_output: _validated_build(project_root, source, output)
            )
            cold_samples.append(cold_elapsed)
            contract_sha = str(cold["build"]["build_contract_sha256"])
            contract_hashes.add(contract_sha)
            output_metrics = _tree_metrics(cold_output)

            partial_output = temp_root / f"partial-{index}"
            partial_build = build_corpus(
                source,
                partial_output,
                debate_id=DEBATE_ID,
                short_code=SHORT_CODE,
                scope_summary=None,
                overwrite=False,
            )
            contract_hashes.add(str(partial_build["build_contract_sha256"]))

            def resume_interrupted() -> str:
                expected = compute_build_contract(
                    source,
                    debate_id=DEBATE_ID,
                    short_code=SHORT_CODE,
                    scope_summary=None,
                )
                expected_sha = canonical_json_sha256(expected)
                before = inspect_existing_build(
                    partial_output,
                    expected_debate_id=DEBATE_ID,
                    expected_contract_sha256=expected_sha,
                )
                if before.get("status") != "unverified":
                    raise PretranslationBenchmarkError("État interrompu synthétique inattendu")
                validation = run_validator(project_root, partial_output)
                if validation.get("status") != "passed":
                    raise PretranslationBenchmarkError("Validation de reprise échouée")
                write_build_receipt(
                    partial_output,
                    build_contract=expected,
                    validation=validation,
                )
                after = inspect_existing_build(
                    partial_output,
                    expected_debate_id=DEBATE_ID,
                    expected_contract_sha256=expected_sha,
                )
                if not after.get("safe_to_reuse"):
                    raise PretranslationBenchmarkError("Le reçu de reprise n'est pas réutilisable")
                return expected_sha

            interrupted_elapsed, interrupted_sha = _measure(resume_interrupted)
            interrupted_samples.append(interrupted_elapsed)
            contract_hashes.add(interrupted_sha)

            def resume_exact() -> str:
                expected = compute_build_contract(
                    source,
                    debate_id=DEBATE_ID,
                    short_code=SHORT_CODE,
                    scope_summary=None,
                )
                expected_sha = canonical_json_sha256(expected)
                inspection = inspect_existing_build(
                    cold_output,
                    expected_debate_id=DEBATE_ID,
                    expected_contract_sha256=expected_sha,
                )
                if not inspection.get("safe_to_reuse"):
                    raise PretranslationBenchmarkError("Le build exact n'a pas été réutilisé")
                return expected_sha

            exact_elapsed, exact_sha = _measure(resume_exact)
            exact_samples.append(exact_elapsed)
            contract_hashes.add(exact_sha)

        if len(contract_hashes) != 1:
            raise PretranslationBenchmarkError("Les scénarios ne partagent pas le même contrat")
        cold = _summary(cold_samples)
        interrupted = _summary(interrupted_samples)
        exact = _summary(exact_samples)
        report: dict[str, Any] = {
            "schema": REPORT_SCHEMA,
            "kit_version": KIT_VERSION,
            "norm_version": NORM_VERSION,
            "validator_version": VALIDATOR_VERSION,
            "environment": {
                "python": platform.python_version(),
                "platform": platform.platform(),
            },
            "fixture": {
                **fixture,
                "iterations": iterations,
                "source": source_metrics,
                "validated_build": output_metrics,
                "build_contract_sha256": next(iter(contract_hashes)),
            },
            "scenarios": {
                "cold_build_validate_receipt": {
                    **cold,
                    "operations": ["build_corpus", "initial_validator", "write_receipt"],
                },
                "resume_after_build_before_receipt": {
                    **interrupted,
                    "operations": ["verify_source_contract", "initial_validator", "write_receipt"],
                    "avoided_operations": ["build_corpus"],
                    "gain_vs_cold": _gain(cold["median_seconds"], interrupted["median_seconds"]),
                },
                "resume_exact_verified_receipt": {
                    **exact,
                    "operations": ["verify_source_contract", "verify_build_receipt"],
                    "avoided_operations": ["build_corpus", "initial_validator"],
                    "gain_vs_cold": _gain(cold["median_seconds"], exact["median_seconds"]),
                },
            },
            "quality_controls": {
                "same_build_contract": True,
                "cold_validation_passed": True,
                "interrupted_validation_passed": True,
                "exact_receipt_verified": True,
                "translation_logic_exercised": False,
                "wiki_access_performed": False,
                "real_snapshot_used": snapshot is not None,
            },
            "billing": {
                "llm_calls_performed": 0,
                "estimated_tokens": None,
                "actual_billed_tokens": None,
                "actual_codex_cloud_credits": None,
                "note": "Ce benchmark local ne mesure ni tokens facturés ni crédits Codex Cloud.",
            },
            "limitations": [
                "Les temps dépendent de la machine, du cache disque et de la charge système.",
                (
                    "Le snapshot réel est figé localement; aucune traduction ni équivalence linguistique n'est évaluée."
                    if snapshot is not None else
                    "Le corpus est synthétique; aucune équivalence linguistique n'est évaluée."
                ),
                "Les gains en crédits doivent être mesurés séparément dans la télémétrie du produit.",
            ],
        }
        report["report_sha256"] = _sha256(canonical_json(report))
        return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--arguments", type=int, default=250)
    parser.add_argument("--payload-bytes", type=int, default=1024)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument(
        "--snapshot", type=Path,
        help="Extraction locale réelle, ou son répertoire snapshot, à mesurer sans accès wiki",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--machine-readable", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_benchmark(
        args.project_root,
        arguments=args.arguments,
        payload_bytes=args.payload_bytes,
        iterations=args.iterations,
        snapshot=args.snapshot,
    )
    if args.output:
        output = _output_path(
            args.project_root.expanduser().resolve(), args.output, args.snapshot,
        )
        write_json(output, report)
    print(
        json.dumps(report, ensure_ascii=False, sort_keys=True)
        if args.machine_readable
        else json.dumps(report, ensure_ascii=False, indent=2)
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PretranslationBenchmarkError as exc:
        print(f"BENCHMARK PRÉTRADUCTION BLOQUÉ : {exc}", file=__import__("sys").stderr)
        raise SystemExit(2)
