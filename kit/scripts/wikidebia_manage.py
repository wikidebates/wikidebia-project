from __future__ import annotations

from wikidebia_release_info import KIT_VERSION, NORM_VERSION, VALIDATOR_VERSION

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

SCOPES = ("all", "fr", "en", "fr-debate", "en-debate")
COMPONENTS = {
    "wikidebia-normes": "norms",
    "wikidebia-validator": "validator",
    "wikidebia-kit": "kit",
}
TRACKED_ROOT_FILES = (
    "wikidebia",
    ".gitignore",
    "README.md",
    "WIKIDEBIA_NORMES_ACTIVES.md",
    "WIKIDEBIA_VALIDATEUR_ACTIF.md",
    "WIKIDEBIA_RECUS_ARCHIVES.json",
    "WIKIDEBIA_SOURCE_ACTIVE.md",
    "WIKIDEBIA_SOURCE_PACKAGE_RECEIPT.json",
    "requirements-runtime.txt",
)

OBSOLETE_ROOT_SOURCE_FILES = (
    "WIKIDEBIA_NORMES_ACTIVES.md",
    "WIKIDEBIA_VALIDATEUR_ACTIF.md",
    "WIKIDEBIA_RECUS_ARCHIVES.json",
)

REQUIRED_GITIGNORE_RULES = (
    "/private/", "/corpus/", "/archives/", "/updates/", "/incoming/", "/outgoing/",
    "/logs/", "/plans/", "/.state/", "/.venv/",
    "/config/wikidebia.local.json", "/configs/", "/.gitconfig-wikidebia",
    "/user-config.py", "/user-password.cfg", "/apicache/",
    "*.lwp", "throttle.ctrl", "__pycache__/", ".pytest_cache/",
    "*.py[cod]", "*.egg-info/",
)
FORBIDDEN_GIT_PREFIXES = (
    "private/", "corpus/", "archives/", "updates/", "incoming/", "outgoing/",
    "logs/", "plans/", ".state/", ".venv/", "configs/", "apicache/",
)
FORBIDDEN_GIT_EXACT = {
    "config/wikidebia.local.json", ".gitconfig-wikidebia",
    "user-config.py", "user-password.cfg", "throttle.ctrl",
}


class ManagementError(RuntimeError):
    pass


def timestamp() -> str:
    return dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        relative = item.relative_to(path).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(bytes.fromhex(sha256_file(item)))
    return digest.hexdigest()


def json_load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManagementError(f"JSON illisible : {path.name}") from exc
    if not isinstance(value, dict):
        raise ManagementError(f"Objet JSON attendu : {path.name}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def portable_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ManagementError(f"Chemin extérieur au projet interdit : {path}") from exc


def _safe_member(name: str) -> bool:
    pure = PurePosixPath(name)
    if pure.is_absolute() or ".." in pure.parts:
        return False
    if re.match(r"^[A-Za-z]:", name):
        return False
    return True


def safe_extract(archive: Path, destination: Path) -> None:
    try:
        with zipfile.ZipFile(archive) as bundle:
            seen: set[str] = set()
            for info in bundle.infolist():
                if not _safe_member(info.filename):
                    raise ManagementError(f"Chemin dangereux dans {archive.name} : {info.filename}")
                normalized = PurePosixPath(info.filename).as_posix()
                if normalized in seen:
                    raise ManagementError(f"Entrée ZIP dupliquée : {info.filename}")
                seen.add(normalized)
                mode = (info.external_attr >> 16) & 0o170000
                if mode == stat.S_IFLNK:
                    raise ManagementError(f"Lien symbolique interdit dans {archive.name}")
            bundle.extractall(destination)
            # Python's zipfile does not restore Unix permission bits.  Restore
            # ordinary file modes explicitly after the symlink/path checks so
            # direct historical entry points keep their executable contract.
            for info in bundle.infolist():
                if info.is_dir():
                    continue
                file_type = (info.external_attr >> 16) & 0o170000
                if file_type not in {0, stat.S_IFREG}:
                    continue
                permissions = (info.external_attr >> 16) & 0o777
                if permissions:
                    target = destination / PurePosixPath(info.filename)
                    target.chmod(permissions)
    except zipfile.BadZipFile as exc:
        raise ManagementError(f"Archive ZIP invalide : {archive.name}") from exc



def restore_historical_entrypoint_modes(kit_root: Path) -> None:
    """Restore the executable contract of the two direct legacy entry points.

    This also repairs staging produced by managers older than 2.15.1, whose
    ZIP extractor validated Unix modes but did not reapply them.
    """
    for relative in (
        "scripts/wikidebia_graph_extract.py",
        "scripts/wikidebia_corpus_init.py",
    ):
        target = kit_root / relative
        if target.is_file():
            target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def inspect_component_zip(archive: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(archive) as bundle:
            names = {PurePosixPath(info.filename).as_posix() for info in bundle.infolist() if not info.is_dir()}
            if "PACKAGE_MANIFEST_SHA256.json" not in names:
                raise ManagementError(f"Manifeste interne absent : {archive.name}")
            manifest = json.loads(bundle.read("PACKAGE_MANIFEST_SHA256.json").decode("utf-8"))
            artifact = str(manifest.get("artifact") or "")
            if artifact not in COMPONENTS:
                raise ManagementError(f"Type de composant inconnu dans {archive.name} : {artifact}")
            declared = {str(row["path"]): row for row in manifest.get("files", [])}
            metadata_names = {"PACKAGE_MANIFEST_SHA256.json"}
            if "PACKAGE_RECEIPT.json" in names:
                metadata_names.add("PACKAGE_RECEIPT.json")
            expected = set(declared) | metadata_names
            if names != expected:
                missing = sorted(expected - names)
                extra = sorted(names - expected)
                raise ManagementError(
                    f"Inventaire divergent dans {archive.name}; absents={missing[:3]}, supplémentaires={extra[:3]}"
                )
            if "PACKAGE_RECEIPT.json" in names:
                receipt = json.loads(bundle.read("PACKAGE_RECEIPT.json").decode("utf-8"))
                manifest_payload = bundle.read("PACKAGE_MANIFEST_SHA256.json")
                if str(receipt.get("artifact") or "") != artifact:
                    raise ManagementError(f"Reçu associé au mauvais composant : {archive.name}")
                if receipt.get("package_manifest_sha256") != hashlib.sha256(manifest_payload).hexdigest():
                    raise ManagementError(f"Reçu incohérent avec le manifeste : {archive.name}")
                if str(receipt.get("version") or "") != str(manifest.get("version") or ""):
                    raise ManagementError(f"Version du reçu incohérente : {archive.name}")
                if str(receipt.get("normative_revision") or "") != str(manifest.get("normative_revision") or ""):
                    raise ManagementError(f"Révision normative du reçu incohérente : {archive.name}")
                receipt_hash = str(receipt.get("receipt_sha256") or "")
                receipt_body = dict(receipt)
                receipt_body.pop("receipt_sha256", None)
                canonical = json.dumps(receipt_body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
                if receipt_hash and receipt_hash != hashlib.sha256(canonical).hexdigest():
                    raise ManagementError(f"Empreinte du reçu incohérente : {archive.name}")
            for relative, row in declared.items():
                payload = bundle.read(relative)
                if len(payload) != int(row.get("size_bytes", -1)):
                    raise ManagementError(f"Taille divergente : {archive.name}:{relative}")
                if hashlib.sha256(payload).hexdigest() != row.get("sha256"):
                    raise ManagementError(f"SHA-256 divergent : {archive.name}:{relative}")
            versions = json.loads(bundle.read("VERSIONS.json").decode("utf-8"))
            compatibility = {}
            capabilities = {}
            if "COMPATIBILITY.json" in names:
                compatibility = json.loads(bundle.read("COMPATIBILITY.json").decode("utf-8"))
            if "CAPABILITIES.json" in names:
                capabilities = json.loads(bundle.read("CAPABILITIES.json").decode("utf-8"))
            return {
                "artifact": artifact,
                "manifest": manifest,
                "versions": versions,
                "compatibility": compatibility,
                "capabilities": capabilities,
            }
    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManagementError(f"Composant illisible : {archive.name}") from exc


def _iter_input_zips(updates: Path, explicit: Path | None) -> list[Path]:
    if explicit is not None:
        return [explicit.resolve()]
    return sorted(path for path in updates.iterdir() if path.is_file() and path.suffix.casefold() == ".zip")


def _discover_component_archives(workspace: Path, initial_archives: list[Path], max_depth: int = 2) -> list[Path]:
    """Discover component ZIPs directly or through a small number of safe wrapper ZIPs."""
    discovered: list[Path] = []
    pending: list[tuple[Path, int]] = [(path, 0) for path in initial_archives]
    seen: set[tuple[str, str]] = set()
    extracted_index = 0
    while pending:
        archive, depth = pending.pop(0)
        try:
            metadata = inspect_component_zip(archive)
        except ManagementError:
            metadata = None
        if metadata is not None:
            marker = (metadata["artifact"], hashlib.sha256(archive.read_bytes()).hexdigest())
            if marker not in seen:
                seen.add(marker)
                discovered.append(archive)
            continue
        if depth >= max_depth:
            continue
        try:
            with zipfile.ZipFile(archive) as bundle:
                nested_names = [PurePosixPath(info.filename).as_posix() for info in bundle.infolist() if not info.is_dir() and info.filename.casefold().endswith(".zip")]
        except zipfile.BadZipFile:
            continue
        if not nested_names:
            continue
        extracted_index += 1
        destination = workspace / f"wrapper-{extracted_index}"
        safe_extract(archive, destination)
        nested = sorted(path for path in destination.rglob("*.zip") if path.is_file())
        if len(nested) > 32:
            raise ManagementError(f"Archive enveloppante trop complexe : {archive.name}")

        # Prefer the shallowest directory that already contains a complete,
        # coherent set of the three component ZIPs. A project delivery may
        # also contain corpus archives with historical technical inputs; those
        # must never compete with the active root-level components.
        groups: dict[Path, dict[str, Path]] = {}
        divergent_groups: set[Path] = set()
        for nested_archive in nested:
            try:
                nested_metadata = inspect_component_zip(nested_archive)
            except ManagementError:
                continue
            parent = nested_archive.parent
            artifact = nested_metadata["artifact"]
            current = groups.setdefault(parent, {}).get(artifact)
            if current is not None and hashlib.sha256(current.read_bytes()).hexdigest() != hashlib.sha256(nested_archive.read_bytes()).hexdigest():
                divergent_groups.add(parent)
                continue
            groups[parent][artifact] = nested_archive
        complete_groups = [
            (parent, components)
            for parent, components in groups.items()
            if parent not in divergent_groups and set(components) == set(COMPONENTS)
        ]
        if complete_groups:
            parent, components = min(
                complete_groups,
                key=lambda item: (len(item[0].relative_to(destination).parts), item[0].as_posix()),
            )
            pending.extend((components[artifact], depth + 1) for artifact in sorted(COMPONENTS))
            continue
        pending.extend((path, depth + 1) for path in nested)
    return discovered


def collect_update_payload(root: Path, explicit: Path | None = None) -> tuple[dict[str, Path], list[Path], Path]:
    updates = root / "updates"
    updates.mkdir(parents=True, exist_ok=True)
    candidates = _iter_input_zips(updates, explicit)
    if not candidates:
        raise ManagementError("Aucune archive ZIP trouvée dans updates/")

    state_dir = root / ".state"
    state_dir.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="wikidebia-update-", dir=state_dir))
    source_files = list(candidates)
    component_candidates = _discover_component_archives(workspace, candidates)

    components: dict[str, Path] = {}
    for candidate in component_candidates:
        metadata = inspect_component_zip(candidate)
        artifact = metadata["artifact"]
        if artifact in components:
            previous_hash = hashlib.sha256(components[artifact].read_bytes()).hexdigest()
            candidate_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
            if previous_hash != candidate_hash:
                raise ManagementError(f"Plusieurs archives candidates divergentes pour {artifact}")
            continue
        components[artifact] = candidate
    missing = sorted(set(COMPONENTS) - set(components))
    if missing:
        raise ManagementError("Composants de mise à jour absents : " + ", ".join(missing))
    return components, source_files, workspace


def _version_tuple(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.split("."))
    except ValueError as exc:
        raise ManagementError(f"Version invalide : {value}") from exc


def current_versions(root: Path) -> dict[str, str]:
    for component in ("norms", "validator", "kit"):
        path = root / component / "VERSIONS.json"
        if path.is_file():
            return {str(key): str(value) for key, value in json_load(path).items()}
    return {}


def verify_version_set(components: dict[str, Path], root: Path, allow_downgrade: bool) -> dict[str, str]:
    """Resolve the active release from component-owned versions.

    Historical packages repeat the whole norm/validator/kit triplet inside every
    component.  Those foreign-version fields are provenance hints, not runtime
    compatibility gates: otherwise a kit-only maintenance release would force
    bytewise repackaging of unchanged norms and validator components.

    Each component is therefore authoritative only for its own version.
    Compatibility is checked through the component manifest's implemented
    normative revision and, where available, schema/capability metadata.
    """
    metadata = {artifact: inspect_component_zip(path) for artifact, path in components.items()}
    owner_key = {
        "wikidebia-normes": "norm",
        "wikidebia-validator": "validator",
        "wikidebia-kit": "kit",
    }
    required_artifacts = set(owner_key)
    if set(metadata) != required_artifacts:
        raise ManagementError("Les trois composants norm/validator/kit sont requis")

    selected: dict[str, str] = {}
    required_version_fields = {"norm", "validator", "kit"}
    for artifact, own_key in owner_key.items():
        info = metadata[artifact]
        versions = {str(key): str(value) for key, value in info["versions"].items()}
        if set(versions) != required_version_fields:
            raise ManagementError(f"{artifact}: VERSIONS.json doit contenir norm, validator et kit")
        own_version = versions[own_key]
        manifest_version = str((info.get("manifest") or {}).get("version") or "")
        if manifest_version != own_version:
            raise ManagementError(
                f"{artifact}: version propre incohérente entre VERSIONS.json ({own_version}) "
                f"et le manifeste ({manifest_version})"
            )
        selected[own_key] = own_version

    active_norm = selected["norm"]
    # A component that explicitly declares the normative revision it implements
    # must match the active norm selected for this installation. This is a
    # functional contract, unlike foreign producer-version hints.
    for artifact in ("wikidebia-validator", "wikidebia-kit"):
        implemented = str((metadata[artifact].get("manifest") or {}).get("normative_revision") or "")
        if implemented and implemented != active_norm:
            compat = metadata[artifact].get("compatibility") or {}
            supported = {str(x) for x in compat.get("supported_normative_revisions") or []}
            compatible = {str(x) for x in compat.get("compatible_normative_revisions") or []}
            if active_norm not in supported and active_norm not in compatible:
                raise ManagementError(
                    f"{artifact}: la norme {active_norm} n'est pas déclarée compatible "
                    f"(révision implémentée : {implemented})"
                )

    previous = current_versions(root)
    if previous and not allow_downgrade:
        for key in required_version_fields:
            if _version_tuple(selected[key]) < _version_tuple(previous.get(key, "0")):
                raise ManagementError(f"Rétrogradation refusée pour {key}: {previous[key]} -> {selected[key]}")
    return selected


def run(
    command: list[str],
    *,
    cwd: Path,
    capture: bool = False,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    process_env = os.environ.copy()
    if env:
        process_env.update(env)
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=False,
        env=process_env,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise ManagementError(f"Commande échouée ({result.returncode}) : {' '.join(command)}\n{detail}")
    return result


def python_command(root: Path) -> str:
    candidate = root / ".venv" / "bin" / "python"
    return str(candidate) if candidate.is_file() else sys.executable


def runtime_requirements_sha(root: Path) -> str | None:
    path = root / "requirements-runtime.txt"
    return sha256_file(path) if path.is_file() else None


def runtime_environment_report(root: Path) -> dict[str, Any]:
    python = root / ".venv" / "bin" / "python"
    required = ("jsonschema", "referencing", "pytest", "pywikibot")
    report: dict[str, Any] = {
        "python": ".venv/bin/python",
        "python_available": False,
        "requirements_file": "requirements-runtime.txt",
        "requirements_sha256": runtime_requirements_sha(root),
        "modules": {},
        "missing_modules": list(required),
    }
    if not python.is_file():
        return report
    probe = r"""
import importlib.util
import json
import sys
from importlib.metadata import PackageNotFoundError, version
modules = ("jsonschema", "referencing", "pytest", "pywikibot")
packages = {}
missing = []
for name in modules:
    if importlib.util.find_spec(name) is None:
        missing.append(name)
        continue
    try:
        packages[name] = version(name)
    except PackageNotFoundError:
        packages[name] = "présent"
print(json.dumps({"python_version": sys.version.split()[0], "modules": packages, "missing_modules": missing}))
"""
    result = run([str(python), "-c", probe], cwd=root, capture=True, check=False)
    if result.returncode != 0:
        report["probe_error"] = (result.stderr or result.stdout or "échec inconnu").strip()
        return report
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        report["probe_error"] = "sortie de diagnostic Python illisible"
        return report
    report.update(payload)
    report["python_available"] = True
    return report


def write_runtime_marker_if_ready(root: Path) -> None:
    report = runtime_environment_report(root)
    expected = report.get("requirements_sha256")
    if not report.get("python_available") or report.get("missing_modules") or not expected:
        return
    marker = root / ".state" / "runtime-requirements.sha256"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(str(expected) + "\n", encoding="utf-8", newline="\n")


def extract_components(components: dict[str, Path], workspace: Path) -> dict[str, Path]:
    extracted: dict[str, Path] = {}
    for artifact, archive in components.items():
        destination = workspace / "staged" / COMPONENTS[artifact]
        destination.mkdir(parents=True, exist_ok=True)
        safe_extract(archive, destination)
        extracted[COMPONENTS[artifact]] = destination
    return extracted


def compare_normative_trees(norms: Path, validator: Path) -> None:
    source = norms / "normative_reference"
    embedded = validator / "normative_reference"
    if not source.is_dir() or not embedded.is_dir():
        raise ManagementError("Copie normative absente des composants")
    if sha256_tree(source) != sha256_tree(embedded):
        raise ManagementError("La copie normative du validateur diverge du paquet des normes")


def test_staged_components(root: Path, staged: dict[str, Path]) -> None:
    py = python_command(root)
    compare_normative_trees(staged["norms"], staged["validator"])
    run([py, "scripts/self_audit.py"], cwd=staged["validator"])
    run([py, "-m", "pytest", "-q"], cwd=staged["validator"], env={"PYTHONPATH": "src", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"})
    run([py, "-m", "pytest", "-q"], cwd=staged["kit"], env={"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"})


RUNTIME_ARTIFACT_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
RUNTIME_ARTIFACT_FILES = {".coverage", "coverage.xml"}
RUNTIME_ARTIFACT_SUFFIXES = {".pyc", ".pyo"}


def purge_staged_runtime_artifacts(staged: dict[str, Path]) -> None:
    """Remove files created by validation/tests before staged components are installed."""
    for base in staged.values():
        if not base.is_dir():
            continue
        for current, dirnames, filenames in os.walk(base, topdown=False):
            current_path = Path(current)
            for filename in filenames:
                path = current_path / filename
                if filename in RUNTIME_ARTIFACT_FILES or path.suffix in RUNTIME_ARTIFACT_SUFFIXES:
                    path.unlink(missing_ok=True)
            for dirname in dirnames:
                path = current_path / dirname
                if dirname in RUNTIME_ARTIFACT_DIRS and path.exists():
                    shutil.rmtree(path)


def aggregate_package(package: Path, title: str, versions: dict[str, str]) -> str:
    """Compatibilité interne : agrège les fichiers textuels d’un composant.

    La mise à niveau courante utilise `build_unified_source`; cette fonction reste
    disponible pour les consommateurs historiques du kit.
    """
    manifest = json_load(package / "PACKAGE_MANIFEST_SHA256.json")
    lines = [
        f"# {title}",
        "",
        f"**Norme active :** {versions['norm']}  ",
        f"**Validateur :** {versions['validator']}  ",
        f"**Kit :** {versions['kit']}",
        "",
    ]
    for row in manifest.get("files", []):
        relative = str(row["path"])
        path = package / relative
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        suffix = path.suffix.casefold()
        language = {".json": "json", ".py": "python", ".toml": "toml", ".sh": "bash"}.get(suffix, "")
        lines.extend(
            [
                f"# Source incorporée : `{relative}`",
                "",
                f"**SHA-256 :** `{row['sha256']}`",
                "",
                f"```{language}",
                text.rstrip("\n"),
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _append_unified_source_section(lines: list[str], title: str, source_label: str, path: Path) -> None:
    lines.extend(
        [
            f"## {title}",
            "",
            f"Source interne : `{source_label}`  ",
            f"SHA-256 : `{sha256_file(path)}`",
            "",
            path.read_text(encoding="utf-8").rstrip("\n"),
            "",
        ]
    )


def build_unified_source(
    staged: dict[str, Path],
    versions: dict[str, str],
    component_archives: dict[str, Path],
) -> str:
    stable = {
        "wikidebia-normes": "wikidebia-normes.zip",
        "wikidebia-validator": "wikidebia-validator.zip",
        "wikidebia-kit": "wikidebia-kit.zip",
    }
    lines = [
        "# Wikidéb’IA — Source active unifiée",
        "",
        "Ce fichier est la source textuelle active générée par `./wikidebia upgrade`. "
        "Il remplace les anciennes sources séparées consacrées aux normes, au validateur et au kit.",
        "",
        f"- norme active : **{versions['norm']}** ;",
        f"- validateur actif : **{versions['validator']}** ;",
        f"- kit actif : **{versions['kit']}**.",
        "",
        "## Composants associés",
        "",
    ]
    for artifact in ("wikidebia-normes", "wikidebia-validator", "wikidebia-kit"):
        path = component_archives[artifact]
        lines.append(
            f"- `{stable[artifact]}` — {path.stat().st_size} octets — SHA-256 `{sha256_file(path)}`"
        )
    lines.append("")

    norm_file = staged["norms"] / "normative_reference" / "01_normes" / f"WIKIDEBIA_NORME_CONSOLIDEE_{versions['norm']}.md"
    sections = (
        ("Norme consolidée active", f"norms/normative_reference/01_normes/{norm_file.name}", norm_file),
        ("Changelog normatif", "norms/normative_reference/01_normes/CHANGELOG_NORMATIF.md", staged["norms"] / "normative_reference" / "01_normes" / "CHANGELOG_NORMATIF.md"),
        ("État actif du validateur", "validator/README.md", staged["validator"] / "README.md"),
        ("Changelog du validateur", "validator/CHANGELOG.md", staged["validator"] / "CHANGELOG.md"),
        ("État actif du kit", "kit/README.md", staged["kit"] / "README.md"),
        ("Changelog du kit", "kit/CHANGELOG.md", staged["kit"] / "CHANGELOG.md"),
        ("Guide de publication", "kit/GUIDE_PUBLICATION.md", staged["kit"] / "GUIDE_PUBLICATION.md"),
        ("Guide de revue du contenu", "kit/GUIDE_CONTENT_REVIEW.md", staged["kit"] / "GUIDE_CONTENT_REVIEW.md"),
        ("Rapport de tests du kit", "kit/TEST_REPORT.txt", staged["kit"] / "TEST_REPORT.txt"),
    )
    for title, source_label, path in sections:
        if not path.is_file():
            raise ManagementError(f"Source active introuvable : {source_label}")
        _append_unified_source_section(lines, title, source_label, path)
    orchestration_guide = staged["kit"] / "GUIDE_EDITORIAL_ORCHESTRATION.md"
    if orchestration_guide.is_file():
        _append_unified_source_section(lines, "Guide d’orchestration éditoriale", "kit/GUIDE_EDITORIAL_ORCHESTRATION.md", orchestration_guide)
    translation_guide = staged["kit"] / "GUIDE_TRANSLATION_REVIEW.md"
    if translation_guide.is_file():
        _append_unified_source_section(lines, "Guide de traduction anglaise", "kit/GUIDE_TRANSLATION_REVIEW.md", translation_guide)
    return "\n".join(lines).rstrip() + "\n"


def generate_readable_sources(root: Path, staged: dict[str, Path], versions: dict[str, str], component_archives: dict[str, Path]) -> dict[str, Path]:
    output = root / ".state" / "generated-update"
    output.mkdir(parents=True, exist_ok=True)
    source = output / "WIKIDEBIA_SOURCE_ACTIVE.md"
    source.write_text(
        build_unified_source(staged, versions, component_archives),
        encoding="utf-8",
        newline="\n",
    )

    stable = {
        "wikidebia-normes": "wikidebia-normes.zip",
        "wikidebia-validator": "wikidebia-validator.zip",
        "wikidebia-kit": "wikidebia-kit.zip",
    }
    files = [
        {
            "path": source.name,
            "size_bytes": source.stat().st_size,
            "sha256": sha256_file(source),
        }
    ]
    for artifact in ("wikidebia-normes", "wikidebia-validator", "wikidebia-kit"):
        path = component_archives[artifact]
        files.append(
            {
                "path": stable[artifact],
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    receipt = output / "WIKIDEBIA_SOURCE_PACKAGE_RECEIPT.json"
    write_json(
        receipt,
        {
            "artifact": "WIKIDEBIA_SOURCES_COMPLETES_RATIONALISE",
            "versions": versions,
            "created_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "purpose": "Source textuelle unifiée et composants de mise à niveau",
            "files": files,
        },
    )
    return {path.name: path for path in (source, receipt)}


def migrate_private_files(root: Path, backup: Path) -> None:
    private = root / "private" / "pywikibot"
    private.mkdir(parents=True, exist_ok=True)
    for name in ("user-config.py", "user-password.cfg"):
        source = root / name
        target = private / name
        if not source.exists():
            continue
        if target.exists():
            destination = backup / "legacy-secrets" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), destination)
        else:
            shutil.move(str(source), target)
            target.chmod(0o600)


def migrate_legacy_debate_inbox(root: Path, backup: Path) -> None:
    legacy = root / "incoming" / "debates"
    if not legacy.exists():
        return
    if not legacy.is_dir():
        raise ManagementError("incoming/debates existe mais n’est pas un dossier")
    entries = sorted(legacy.iterdir())
    unsupported = [item.name for item in entries if not item.is_file() or item.suffix.casefold() != ".zip"]
    if unsupported:
        raise ManagementError(
            "Migration de incoming/debates bloquée par des entrées non ZIP : " + ", ".join(unsupported)
        )
    incoming = root / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    for source in entries:
        target = incoming / source.name
        if target.exists() and sha256_file(target) != sha256_file(source):
            collision = backup / "legacy-incoming-collisions" / source.name
            collision.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, collision)
            raise ManagementError(
                f"Collision pendant la migration de {source.name}; copie conservée dans {collision.relative_to(root)}"
            )
    for source in entries:
        target = incoming / source.name
        if target.exists():
            source.unlink()
        else:
            shutil.move(str(source), target)
    legacy.rmdir()


def backup_root_template_files(root: Path, backup: Path) -> None:
    targets = [root / name for name in ("wikidebia", ".gitignore", "README.md", "requirements-runtime.txt")]
    targets.extend([root / "config" / "wikidebia.example.json", root / ".github"])
    for target in targets:
        if not target.exists() and not target.is_symlink():
            continue
        relative = target.relative_to(root)
        destination = backup / "previous-root" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if target.is_dir():
            shutil.copytree(target, destination, dirs_exist_ok=True)
        else:
            shutil.copy2(target, destination)


def install_root_template(root: Path, kit: Path) -> None:
    template = kit / "root_template"
    if not template.is_dir():
        raise ManagementError("Le nouveau kit ne contient pas root_template/")
    for source in sorted(template.rglob("*")):
        relative = source.relative_to(template)
        target = root / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if relative.as_posix() == "config/wikidebia.local.json":
            continue
        shutil.copy2(source, target)
    launcher = root / "wikidebia"
    if launcher.is_file():
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)


def _replace_path(source: Path, target: Path, backup_root: Path) -> None:
    if target.exists() or target.is_symlink():
        destination = backup_root / "previous" / target.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target), destination)
    shutil.move(str(source), target)


def assert_portable_sources(root: Path) -> None:
    needle = str(root.resolve())
    candidates: list[Path] = []
    for dirname in ("norms", "validator", "kit"):
        base = root / dirname
        if base.is_dir():
            candidates.extend(path for path in base.rglob("*") if path.is_file())
    for name in TRACKED_ROOT_FILES:
        path = root / name
        if path.is_file():
            candidates.append(path)
    for base in (root / "config", root / ".github"):
        if base.is_dir():
            candidates.extend(path for path in base.rglob("*") if path.is_file())
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if needle in text:
            raise ManagementError(f"Chemin absolu du projet conservé dans {path.relative_to(root)}")


def _normalized_git_path(value: str) -> str:
    path = value.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return PurePosixPath(path).as_posix()


def forbidden_git_path(value: str) -> bool:
    path = _normalized_git_path(value)
    return (
        path in FORBIDDEN_GIT_EXACT
        or path.casefold().endswith(".lwp")
        or any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in FORBIDDEN_GIT_PREFIXES)
    )


def gitignore_missing_rules(root: Path) -> list[str]:
    path = root / ".gitignore"
    if not path.is_file():
        return list(REQUIRED_GITIGNORE_RULES)
    active = {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")}
    return [rule for rule in REQUIRED_GITIGNORE_RULES if rule not in active]


def git_is_repo(root: Path) -> bool:
    return (root / ".git").is_dir()


def git_tracked_forbidden_paths(root: Path) -> list[str]:
    if not git_is_repo(root):
        return []
    result = run(["git", "ls-files", "-z"], cwd=root, capture=True, check=False)
    if result.returncode != 0:
        return []
    return sorted(path for path in result.stdout.split("\0") if path and forbidden_git_path(path))


def git_unignored_forbidden_paths(root: Path) -> list[str]:
    if not git_is_repo(root):
        return []
    result = run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=root,
        capture=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return sorted(path for path in result.stdout.split("\0") if path and forbidden_git_path(path))


def git_security_issues(root: Path) -> list[str]:
    issues: list[str] = []
    missing = gitignore_missing_rules(root)
    if missing:
        issues.append("Règles .gitignore manquantes : " + ", ".join(missing))
    tracked = git_tracked_forbidden_paths(root)
    if tracked:
        issues.append("Fichiers locaux ou sensibles encore suivis par Git : " + ", ".join(tracked))
    unignored = git_unignored_forbidden_paths(root)
    if unignored:
        issues.append("Fichiers locaux ou sensibles non ignorés : " + ", ".join(unignored))
    return issues


def prepare_git_security(root: Path) -> None:
    missing = gitignore_missing_rules(root)
    if missing:
        raise ManagementError("Règles de sécurité absentes du .gitignore : " + ", ".join(missing))
    tracked = git_tracked_forbidden_paths(root)
    if tracked:
        for offset in range(0, len(tracked), 100):
            run(
                ["git", "rm", "-r", "--cached", "--ignore-unmatch", "--", *tracked[offset:offset + 100]],
                cwd=root,
            )
        print("Fichiers locaux retirés de l’index Git sans suppression locale : " + ", ".join(tracked), file=sys.stderr)
    remaining = git_security_issues(root)
    if remaining:
        raise ManagementError("Contrôle de sécurité Git échoué : " + " | ".join(remaining))


def git_has_origin(root: Path) -> bool:
    if not git_is_repo(root):
        return False
    result = run(["git", "remote", "get-url", "origin"], cwd=root, capture=True, check=False)
    return result.returncode == 0 and bool(result.stdout.strip())


def ensure_git_identity(root: Path) -> None:
    defaults = {
        "user.name": "Wikidéb’IA",
        "user.email": "wikidebia@localhost",
    }
    for key, default in defaults.items():
        result = run(["git", "config", "--get", key], cwd=root, capture=True, check=False)
        if result.returncode != 0 or not result.stdout.strip():
            run(["git", "config", "--local", key, default], cwd=root)


def git_push_current_branch(root: Path, *, strict: bool) -> bool:
    if not git_has_origin(root):
        message = (
            "Aucun remote origin n’est configuré. Utilisez ./wikidebia github-init URL_DU_DEPOT."
        )
        if strict:
            raise ManagementError(message)
        print("Dépôt Git mis à jour localement. " + message, file=sys.stderr)
        return False
    branch = run(["git", "branch", "--show-current"], cwd=root, capture=True).stdout.strip() or "main"
    result = run(
        ["git", "push", "-u", "origin", branch],
        cwd=root,
        capture=True,
        check=False,
        env={"GIT_TERMINAL_PROMPT": "0"},
    )
    if result.returncode == 0:
        return True
    detail = (result.stderr or result.stdout or "échec d’authentification inconnu").strip()
    message = (
        "Push GitHub non effectué. Le commit reste local. Authentifiez GitHub CLI avec "
        "`gh auth login -h github.com -p https`, puis exécutez `gh auth setup-git --hostname github.com` "
        "et `./wikidebia github-sync`. Détail Git : " + detail
    )
    if strict:
        raise ManagementError(message)
    print("AVERTISSEMENT : " + message, file=sys.stderr)
    return False


def git_commit_and_push(root: Path, message: str, *, push: bool) -> bool:
    if not git_is_repo(root):
        run(["git", "init", "-b", "main"], cwd=root)
    ensure_git_identity(root)
    prepare_git_security(root)
    run(["git", "add", "-A"], cwd=root)
    tracked_after_add = git_tracked_forbidden_paths(root)
    if tracked_after_add:
        raise ManagementError("git add a tenté de suivre des fichiers interdits : " + ", ".join(tracked_after_add))
    status = run(["git", "status", "--porcelain"], cwd=root, capture=True).stdout.strip()
    if status:
        run(["git", "commit", "-m", message], cwd=root)
    return git_push_current_branch(root, strict=False) if push else False


def update_sources(root: Path, archive: Path | None, *, allow_downgrade: bool, no_push: bool, no_git: bool) -> dict[str, str]:
    components, input_files, workspace = collect_update_payload(root, archive)
    try:
        versions = verify_version_set(components, root, allow_downgrade)
        staged = extract_components(components, workspace)
        test_staged_components(root, staged)
        purge_staged_runtime_artifacts(staged)
        generated = generate_readable_sources(root, staged, versions, components)

        backup = root / "archives" / "updates" / f"{timestamp()}-{versions['norm']}"
        backup.mkdir(parents=True, exist_ok=True)
        migrate_private_files(root, backup)
        migrate_legacy_debate_inbox(root, backup)
        backup_root_template_files(root, backup)

        installed: list[str] = []
        try:
            for name in ("norms", "validator", "kit"):
                _replace_path(staged[name], root / name, backup)
                installed.append(name)
        except Exception:
            for name in reversed(installed):
                current = root / name
                if current.exists():
                    shutil.rmtree(current)
                previous = backup / "previous" / name
                if previous.exists():
                    shutil.move(str(previous), current)
            raise
        restore_historical_entrypoint_modes(root / "kit")
        install_root_template(root, root / "kit")
        write_runtime_marker_if_ready(root)
        for name in OBSOLETE_ROOT_SOURCE_FILES:
            legacy = root / name
            if legacy.exists():
                destination = backup / "previous" / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(legacy), destination)
        for name, source in generated.items():
            target = root / name
            if target.exists():
                destination = backup / "previous" / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target), destination)
            shutil.copy2(source, target)

        incoming_archive = backup / "incoming"
        incoming_archive.mkdir(parents=True, exist_ok=True)
        updates_dir = root / "updates"
        for item in list(updates_dir.iterdir()):
            shutil.move(str(item), incoming_archive / item.name)
        for item in input_files:
            if item.parent != updates_dir and item.exists():
                shutil.copy2(item, incoming_archive / item.name)

        assert_portable_sources(root)
        if not no_git:
            git_commit_and_push(
                root,
                f"Mise à jour Wikidéb’IA {versions['norm']} / {versions['validator']} / {versions['kit']}",
                push=not no_push,
            )
        return versions
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def load_local_settings(root: Path) -> dict[str, Any]:
    path = root / "config" / "wikidebia.local.json"
    if not path.is_file():
        return {}
    return json_load(path)


def ensure_credentials(root: Path) -> Path:
    private = root / "private" / "pywikibot"
    private.mkdir(parents=True, exist_ok=True)
    for name in ("user-config.py", "user-password.cfg"):
        legacy = root / name
        target = private / name
        if legacy.is_file() and not target.exists():
            shutil.move(str(legacy), target)
            target.chmod(0o600)
    if not (private / "user-config.py").is_file():
        raise ManagementError("private/pywikibot/user-config.py est absent")
    return private


def find_debate_archive(root: Path, debate_identifier: str | None) -> Path:
    incoming = root / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    candidates = sorted(path for path in incoming.iterdir() if path.is_file() and path.suffix.casefold() == ".zip")

    if debate_identifier is not None:
        identifier = debate_identifier.strip()
        if identifier.casefold().endswith(".zip"):
            raise ManagementError("Indiquez l’identifiant du débat sans l’extension .zip")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", identifier):
            raise ManagementError("Identifiant de débat invalide; caractères admis : lettres, chiffres, _, - et .")
        archive = incoming / f"{identifier}.zip"
        if not archive.is_file():
            available = ", ".join(path.stem for path in candidates) or "aucun"
            raise ManagementError(f"Archive introuvable : incoming/{identifier}.zip; identifiants disponibles : {available}")
        return archive

    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ManagementError("Aucune archive ZIP trouvée dans incoming/")
    available = ", ".join(path.stem for path in candidates)
    raise ManagementError(
        "Plusieurs archives ZIP sont présentes dans incoming/. "
        f"Relancez avec ./wikidebia publish IDENTIFIANT. Identifiants disponibles : {available}"
    )


def locate_package_root(extracted: Path) -> Path:
    manifests = sorted(extracted.rglob("manifest.json"))
    if len(manifests) != 1:
        raise ManagementError(f"Le ZIP de débat doit contenir exactement un manifest.json; trouvé : {len(manifests)}")
    return manifests[0].parent


def stage_debate_corpus(root: Path, archive: Path, *, purpose: str = "debates") -> tuple[str, Path, Path]:
    staging_parent = root / ".state" / purpose
    staging_parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f"{timestamp()}-{sha256_file(archive)[:12]}-", dir=staging_parent))
    safe_extract(archive, stage)
    package_root = locate_package_root(stage)
    manifest = json_load(package_root / "manifest.json")
    debate_id = str(manifest.get("debate_id") or "").strip()
    if not debate_id or not re.fullmatch(r"[A-Za-z0-9_.-]+", debate_id):
        shutil.rmtree(stage, ignore_errors=True)
        raise ManagementError("debate_id absent ou impropre à un nom de dossier")
    return debate_id, package_root, stage


def promote_debate_corpus(root: Path, debate_id: str, package_root: Path) -> Path:
    target = root / "corpus" / debate_id
    if target.is_dir() and sha256_tree(target) == sha256_tree(package_root):
        return target
    if target.exists():
        backup = root / "archives" / "debates" / f"{timestamp()}-{debate_id}" / "previous-corpus"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target), backup)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(package_root, target)
    return target


def install_debate_corpus(root: Path, archive: Path) -> tuple[str, Path]:
    debate_id, package_root, stage = stage_debate_corpus(root, archive)
    try:
        target = promote_debate_corpus(root, debate_id, package_root)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return debate_id, target


def scope_values(scope: str) -> tuple[list[str], list[str]]:
    mapping = {
        "all": (["fr", "en"], []),
        "fr": (["fr"], []),
        "en": (["en"], []),
        "fr-debate": (["fr"], ["debate"]),
        "en-debate": (["en"], ["debate"]),
    }
    return mapping[scope]


def publication_config(root: Path, debate_id: str, scope: str, run_dir: Path) -> Path:
    settings = load_local_settings(root)
    languages, page_types = scope_values(scope)
    users = settings.get("expected_users") or {"fr": "ChatGPT", "en": "ChatGPT"}
    summaries = settings.get("edit_summaries") or {
        "fr": "Contenu généré par ChatGPT 5.6",
        "en": "Content generated by ChatGPT 5.6",
    }
    sites = {language: {"code": language, "expected_user": str(users.get(language) or "ChatGPT")} for language in languages}
    corpus_manifest_path = root / "corpus" / debate_id / "manifest.json"
    translation_status = "pending"
    if corpus_manifest_path.is_file():
        corpus_manifest = json_load(corpus_manifest_path)
        translation_status = str((((corpus_manifest.get("translation_status") or {}).get("en")) or "pending"))
    publication_profile = (
        "norm_1_2_deferred_translation" if translation_status == "deferred" else "norm_1_2_direct_interlanguage"
    )
    config = {
        "kit_version": KIT_VERSION,
        "project_root": ".",
        "family": str(settings.get("family") or "wikidebates"),
        "family_file": "kit/families/wikidebates_family.py",
        "pywikibot_dir": "private/pywikibot",
        "sites": sites,
        "change_tags": ["chatgpt"],
        "translation_change_tag": "translated-fr",
        "publication_timezone": str(settings.get("publication_timezone") or "Europe/Paris"),
        "verification_attempts": int(settings.get("verification_attempts", 8)),
        "verification_delay_seconds": float(settings.get("verification_delay_seconds", 2)),
        "write_delay_seconds": float(settings.get("write_delay_seconds", 0.5)),
        "debate_id": debate_id,
        "corpus_root": f"corpus/{debate_id}",
        "logs_dir": f"logs/{debate_id}/{run_dir.name}",
        "validator": {
            "command": [".venv/bin/python", "validator/scripts/wikidebia_validate.py", "validate"],
            "required_version": VALIDATOR_VERSION,
            "scopes": ["schema", "coherence", "graph", "files", "batches", "sources", "wikicode", "bilingual", "editorial", "workflow"],
            "max_warnings": 0,
            "fingerprint_path": "validator",
        },
        # Les versions déclarées par le corpus sont une provenance historique.
        # La sécurité repose sur le validateur installé, sa version réelle et son
        # rapport positif, non sur une réécriture du manifeste au fil des mises à jour.
        "manifest_requirements": {},
        "operation": {
            "id": f"publish_{scope.replace('-', '_')}",
            "kind": "full_page",
            "languages": languages,
            "page_types": page_types,
            "language_order": languages,
            "page_type_order": ["debate", "argument"],
            "source_path_field": "file_path",
            "create_missing": True,
            "update_existing": False,
            "edit_summaries": {language: str(summaries[language]) for language in languages},
            "remote_title_overrides": {language: {} for language in languages},
        },
        "publication_profile": publication_profile,
    }
    path = run_dir / "config.json"
    write_json(path, config)
    return path


def publisher_command(root: Path, config: Path, *args: str) -> list[str]:
    return [python_command(root), "kit/scripts/wikidebia_publish.py", "--config", str(config.relative_to(root)), *args]


def publish_debate(root: Path, debate_identifier: str | None, scope: str, assume_yes: bool, keep_zip: bool) -> dict[str, int]:
    ensure_credentials(root)
    archive = find_debate_archive(root, debate_identifier)
    debate_id, _ = install_debate_corpus(root, archive)
    try:
        archive_display = archive.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        archive_display = archive.name
    print(f"Archive sélectionnée : {archive_display}")
    print(f"Identifiant interne du débat : {debate_id}")
    run_dir = root / "plans" / debate_id / timestamp()
    run_dir.mkdir(parents=True, exist_ok=True)
    config = publication_config(root, debate_id, scope, run_dir)
    plan_path = run_dir / "plan.json"
    run(publisher_command(root, config, "--mode", "plan", "--plan-output", str(plan_path.relative_to(root))), cwd=root)
    plan = json_load(plan_path)
    if plan.get("blockers"):
        raise ManagementError(f"Le plan contient {len(plan['blockers'])} bloqueur(s); voir {plan_path.relative_to(root)}")
    counts = plan.get("counts") or {}
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    # Le plan signé est transmis automatiquement au moteur ; aucune invite interactive n’est utilisée.

    receipt_path = run_dir / "debate-test-receipt.json"
    french_create = any(
        row.get("language") == "fr" and row.get("page_type") == "debate" and row.get("operation") == "create"
        for row in plan.get("actions", [])
    )
    if french_create:
        run(
            publisher_command(
                root,
                config,
                "--mode", "debate-test",
                "--execute",
                "--plan-input", str(plan_path.relative_to(root)),
                "--confirm-plan-sha256", str(plan["plan_sha256"]),
                "--debate-test-receipt-output", str(receipt_path.relative_to(root)),
            ),
            cwd=root,
        )

    publish_args = [
        "--mode", "publish",
        "--execute",
        "--plan-input", str(plan_path.relative_to(root)),
        "--confirm-plan-sha256", str(plan["plan_sha256"]),
    ]
    if french_create:
        publish_args.extend(["--debate-test-receipt", str(receipt_path.relative_to(root))])
    result = run(publisher_command(root, config, *publish_args), cwd=root, capture=True)
    output = (result.stdout or "").strip().splitlines()
    published = json.loads(output[-1]) if output else {}
    if french_create:
        published["created"] = int(published.get("created", 0)) + 1
        published["skipped"] = max(0, int(published.get("skipped", 0)) - 1)
    if not keep_zip:
        destination = root / "archives" / "debates" / f"{timestamp()}-{debate_id}" / archive.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if archive.resolve().is_relative_to(root.resolve()):
            shutil.move(str(archive), destination)
        else:
            shutil.copy2(archive, destination)
    return {str(key): int(value) for key, value in published.items()}



def resolve_update_scope(corpus_root: Path, requested_scope: str | None) -> str:
    """Choose all publishable languages when --scope is omitted.

    Explicit scopes are preserved. In automatic mode, only languages represented by
    validated page entries and not marked deferred are selected.
    """
    if requested_scope is not None:
        return requested_scope
    manifest = json_load(corpus_root / "manifest.json")
    page_languages = {
        str(row.get("language"))
        for row in (manifest.get("pages") or [])
        if isinstance(row, dict)
        and row.get("language") in {"fr", "en"}
        and row.get("status") in {"validated", "release_ready", "published"}
        and row.get("file_path")
    }
    translation_status = manifest.get("translation_status") or {}
    publishable = [
        language for language in ("fr", "en")
        if language in page_languages and str(translation_status.get(language) or "ready") != "deferred"
    ]
    if publishable == ["fr", "en"]:
        return "all"
    if len(publishable) == 1:
        return publishable[0]
    if page_languages == {"fr"}:
        return "fr"
    if page_languages == {"en"}:
        return "en"
    raise ManagementError(
        "Impossible de déterminer automatiquement la portée de mise à jour; "
        "utilisez --scope fr, --scope en ou --scope all."
    )


def remote_update_config(root: Path, debate_id: str, scope: str, run_dir: Path, corpus_root: Path | None = None, interlanguage_only: bool = False) -> Path:
    settings = load_local_settings(root)
    languages = ["fr", "en"] if scope == "all" else [scope]
    users = settings.get("expected_users") or {"fr": "ChatGPT", "en": "ChatGPT"}
    sites = {language: {"code": language, "expected_user": str(users.get(language) or "ChatGPT")} for language in languages}
    config = {
        "kit_version": KIT_VERSION,
        "project_root": ".",
        "family": str(settings.get("family") or "wikidebates"),
        "family_file": "kit/families/wikidebates_family.py",
        "pywikibot_dir": "private/pywikibot",
        "sites": sites,
        "languages": languages,
        "debate_id": debate_id,
        "corpus_root": portable_path(corpus_root or (root / "corpus" / debate_id), root),
        "interlanguage_only": bool(interlanguage_only),
        "logs_dir": f"logs/{debate_id}/{run_dir.name}",
        "published_state_dir": ".state/published",
        "receipts_dir": ".state/receipts",
        "validator": {
            "command": [".venv/bin/python", "validator/scripts/wikidebia_validate.py", "validate"],
            "required_version": VALIDATOR_VERSION,
            "scopes": ["schema", "coherence", "graph", "files", "batches", "sources", "wikicode", "bilingual", "editorial", "workflow"],
        },
    }
    path = run_dir / "config.json"
    write_json(path, config)
    return path


def remote_update_command(root: Path, config: Path, *args: str) -> list[str]:
    return [python_command(root), "kit/scripts/wikidebia_update.py", "--config", str(config.relative_to(root)), *args]


def _prepare_update_corpus(
    root: Path,
    debate_identifier: str | None,
    archive_selector: str | None = None,
) -> tuple[str, Path | None, Path, Path | None]:
    if archive_selector and debate_identifier:
        raise ManagementError("Utilisez soit l’identifiant positionnel, soit --archive, pas les deux")

    incoming = root / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    candidates = sorted(path for path in incoming.iterdir() if path.is_file() and path.suffix.casefold() == ".zip")

    # Compatibility path: --archive remains valid, but is no longer required.
    if archive_selector:
        archive = find_debate_archive(root, archive_selector)
        debate_id, package_root, stage = stage_debate_corpus(root, archive, purpose="update-staging")
        return debate_id, archive, package_root, stage

    if debate_identifier:
        identifier = debate_identifier.strip()
        if identifier.casefold().endswith(".zip"):
            raise ManagementError("Indiquez l’identifiant sans l’extension .zip")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", identifier):
            raise ManagementError("Identifiant invalide; caractères admis : lettres, chiffres, _, - et .")
        incoming_match = incoming / f"{identifier}.zip"
        if incoming_match.is_file():
            debate_id, package_root, stage = stage_debate_corpus(root, incoming_match, purpose="update-staging")
            return debate_id, incoming_match, package_root, stage
        installed = root / "corpus" / identifier
        if (installed / "manifest.json").is_file():
            return identifier, None, installed, None
        incoming_ids = ", ".join(path.stem for path in candidates) or "aucun"
        installed_ids = ", ".join(sorted(path.name for path in (root / "corpus").glob("*") if (path / "manifest.json").is_file())) if (root / "corpus").is_dir() else "aucun"
        raise ManagementError(
            f"Aucune archive ni aucun corpus installé ne correspond à {identifier}. "
            f"ZIP disponibles : {incoming_ids}; corpus installés : {installed_ids or 'aucun'}"
        )

    # A unique incoming archive is the unambiguous new version and takes priority.
    if len(candidates) == 1:
        archive = candidates[0]
        debate_id, package_root, stage = stage_debate_corpus(root, archive, purpose="update-staging")
        return debate_id, archive, package_root, stage
    if len(candidates) > 1:
        available = ", ".join(path.stem for path in candidates)
        raise ManagementError(
            "Plusieurs archives ZIP sont présentes dans incoming/. "
            f"Relancez avec ./wikidebia update IDENTIFIANT. Identifiants disponibles : {available}"
        )

    installed = sorted(
        path for path in (root / "corpus").glob("*")
        if path.is_dir() and (path / "manifest.json").is_file()
    ) if (root / "corpus").is_dir() else []
    if len(installed) == 1:
        return installed[0].name, None, installed[0], None
    if not installed:
        raise ManagementError("Aucune archive ZIP dans incoming/ et aucun corpus installé.")
    available = ", ".join(path.name for path in installed)
    raise ManagementError(
        "Plusieurs corpus sont installés et aucune archive n’est présente. Indiquez leur identifiant. "
        f"Identifiants disponibles : {available}"
    )


def _archive_after_update(root: Path, archive: Path, debate_id: str, keep_zip: bool) -> None:
    if keep_zip:
        return
    destination = root / "archives" / "debates" / f"{timestamp()}-{debate_id}" / archive.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(archive), destination)


def update_debate(
    root: Path,
    debate_identifier: str | None,
    scope: str | None,
    assume_yes: bool,
    no_delete: bool,
    only_delete: bool,
    dry_run: bool,
    keep_zip: bool,
    archive_selector: str | None = None,
    interlanguage_only: bool = False,
) -> dict[str, Any]:
    ensure_credentials(root)
    if no_delete and only_delete:
        raise ManagementError("--no-delete et --only-delete sont incompatibles")
    staging_root: Path | None = None
    archive: Path | None = None
    try:
        debate_id, archive, corpus_root, staging_root = _prepare_update_corpus(root, debate_identifier, archive_selector)
        effective_scope = resolve_update_scope(corpus_root, scope)
        if interlanguage_only and effective_scope != "fr":
            raise ManagementError("--interlanguage-only exige --scope fr")
        if interlanguage_only and (no_delete or only_delete):
            raise ManagementError("--interlanguage-only est incompatible avec --no-delete et --only-delete")
        if scope is None:
            print(f"Portée sélectionnée automatiquement : {effective_scope}")
        if archive is None:
            print(f"Corpus installé sélectionné : {portable_path(corpus_root, root)}")
        else:
            print(f"Archive sélectionnée pour staging : {portable_path(archive, root)}")
        print(f"Identifiant interne du débat : {debate_id}")
        run_dir = root / "plans" / debate_id / timestamp()
        run_dir.mkdir(parents=True, exist_ok=True)
        config = (
            remote_update_config(root, debate_id, effective_scope, run_dir, corpus_root, True)
            if interlanguage_only
            else remote_update_config(root, debate_id, effective_scope, run_dir, corpus_root)
        )
        plan_path = run_dir / "update-plan.json"
        flags: list[str] = []
        if no_delete:
            flags.append("--no-delete")
        if only_delete:
            flags.append("--only-delete")
        result = run(remote_update_command(root, config, "--mode", "plan", "--plan-output", str(plan_path.relative_to(root)), *flags), cwd=root, capture=True, check=False)
        if result.returncode not in {0, 3}:
            raise ManagementError((result.stderr or result.stdout or "Plan de reprise impossible").strip())
        plan = json_load(plan_path)
        counts = plan.get("counts") or {}
        print(json.dumps(counts, ensure_ascii=False, indent=2))
        operations = plan.get("operations") or {}
        blocked = operations.get("blocked") or []
        manual_review = operations.get("manual_review") or []
        if dry_run:
            status = "blocked" if blocked else ("manual_review_required" if manual_review else "dry_run")
            return {"status": status, "plan": str(plan_path.relative_to(root)), "plan_sha256": plan["plan_sha256"], "counts": counts}
        if blocked:
            raise ManagementError(f"Le plan contient {len(blocked)} opération(s) bloquée(s); voir {plan_path.relative_to(root)}")
        if manual_review:
            raise ManagementError(
                f"Le plan contient {len(manual_review)} opération(s) nécessitant une révision manuelle; "
                f"aucune écriture ni mise à jour de l’état n’a été effectuée. Voir {plan_path.relative_to(root)}"
            )

        mutable_names = ("create", "update", "move", "redirect", "delete")
        if only_delete:
            selected_names = ("redirect", "delete")
        elif no_delete:
            selected_names = ("create", "update", "move", "redirect")
        else:
            selected_names = mutable_names
        mutable_count = sum(len(operations.get(name) or []) for name in mutable_names)
        selected_count = sum(len(operations.get(name) or []) for name in selected_names)

        if mutable_count == 0:
            attest = run(
                remote_update_command(
                    root,
                    config,
                    "--mode", "attest",
                    "--plan-input", str(plan_path.relative_to(root)),
                    "--confirm-plan-sha256", str(plan["plan_sha256"]),
                ),
                cwd=root,
                capture=True,
            )
            lines = (attest.stdout or "").strip().splitlines()
            attestation_counts = json.loads(lines[-1]) if lines else {}
            if staging_root is not None:
                promote_debate_corpus(root, debate_id, corpus_root)
            if archive is not None:
                _archive_after_update(root, archive, debate_id, keep_zip)
            return {
                "status": "no_changes",
                "plan": str(plan_path.relative_to(root)),
                "plan_sha256": plan["plan_sha256"],
                "counts": attestation_counts or counts,
            }

        if selected_count == 0:
            return {
                "status": "no_changes_in_scope",
                "plan": str(plan_path.relative_to(root)),
                "plan_sha256": plan["plan_sha256"],
                "counts": counts,
            }

        _ = assume_yes
        execute = run(
            remote_update_command(
                root,
                config,
                "--mode", "execute",
                "--plan-input", str(plan_path.relative_to(root)),
                "--confirm-plan-sha256", str(plan["plan_sha256"]),
                *flags,
            ),
            cwd=root,
            capture=True,
        )
        lines = (execute.stdout or "").strip().splitlines()
        execution_counts = json.loads(lines[-1]) if lines else {}
        if staging_root is not None:
            promote_debate_corpus(root, debate_id, corpus_root)
        if archive is not None:
            _archive_after_update(root, archive, debate_id, keep_zip)
        return {"status": "executed", "plan": str(plan_path.relative_to(root)), "plan_sha256": plan["plan_sha256"], "counts": execution_counts}
    finally:
        if staging_root is not None:
            shutil.rmtree(staging_root, ignore_errors=True)



def tag_translated_fr(root: Path, debate_id: str, *, dry_run: bool) -> dict[str, Any]:
    ensure_credentials(root)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", debate_id or ""):
        raise ManagementError("Identifiant de débat invalide")
    script = root / "kit" / "scripts" / "wikidebia_retro_tag.py"
    if not script.is_file():
        raise ManagementError("Outil de rattrapage translated-fr absent du kit")
    settings = load_local_settings(root)
    users = settings.get("expected_users") or {"fr": "ChatGPT", "en": "ChatGPT"}
    expected_user = str(users.get("en") or "ChatGPT")
    family = str(settings.get("family") or "wikidebates")
    run_dir = root / "plans" / debate_id / timestamp()
    run_dir.mkdir(parents=True, exist_ok=True)
    plan_path = run_dir / "translated-fr-tag-plan.json"
    command = [
        python_command(root), str(script), debate_id,
        "--project-root", str(root),
        "--family", family,
        "--code", "en",
        "--pywikibot-dir", str(root / "private" / "pywikibot"),
        "--family-file", str(root / "kit" / "families" / "wikidebates_family.py"),
        "--expected-user", expected_user,
        "--plan-output", str(plan_path),
        "--machine-readable",
    ]
    if dry_run:
        command.append("--dry-run")
    result = run(command, cwd=root, capture=True, check=False)
    if result.returncode != 0:
        raise ManagementError((result.stderr or result.stdout or "Rattrapage translated-fr impossible").strip())
    lines = (result.stdout or "").strip().splitlines()
    if not lines:
        raise ManagementError("Sortie du rattrapage translated-fr absente")
    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise ManagementError("Sortie du rattrapage translated-fr illisible") from exc
    return payload


def graph_output_slug(value: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", normalized).strip("_").lower()
    return normalized or "debat"


def graph_extract_debate(
    root: Path,
    debate_title: str,
    *,
    lang: str,
    family: str,
    output_dir: Path | None,
    cache_dir: Path | None,
    slug: str | None,
    extraction_date: str | None,
    login: bool,
    force_refresh: bool,
    allow_missing: bool,
    max_depth: int | None,
    max_pages: int,
    retries: int,
    retry_delay: float,
    progress_every: int,
    follow_local_relations_at_dedicated_debate: bool,
    follow_local_relations_at_existing_english_translation: bool = False,
) -> int:
    script = root / "kit" / "scripts" / "wikidebia_graph_extract.py"
    family_file = root / "kit" / "families" / "wikidebates_family.py"
    pywikibot_dir = root / "private" / "pywikibot"
    if not script.is_file():
        raise ManagementError("Extracteur de graphe absent du kit")
    if family == "wikidebates" and not family_file.is_file():
        raise ManagementError("Fichier de famille Pywikibot Wikidébates absent")
    if max_pages < 1:
        raise ManagementError("--max-pages doit être supérieur à zéro")
    if max_depth is not None and max_depth < 0:
        raise ManagementError("--max-depth doit être positif ou nul")
    if retries < 0 or retry_delay < 0 or progress_every < 0:
        raise ManagementError("Les options de reprise et de progression ne peuvent pas être négatives")

    selected_slug = slug or graph_output_slug(debate_title)
    selected_output = output_dir or (root / ".state" / "graph-extract" / selected_slug)
    if not selected_output.is_absolute():
        selected_output = root / selected_output
    selected_output = selected_output.resolve()
    portable_path(selected_output, root)
    selected_output.mkdir(parents=True, exist_ok=True)

    selected_cache = cache_dir
    if selected_cache is not None:
        if not selected_cache.is_absolute():
            selected_cache = root / selected_cache
        selected_cache = selected_cache.resolve()
        portable_path(selected_cache, root)

    command = [
        python_command(root),
        str(script),
        "--debate", debate_title,
        "--family", family,
        "--lang", lang,
        "--pywikibot-dir", str(pywikibot_dir),
        "--output-dir", str(selected_output),
        "--slug", selected_slug,
        "--max-pages", str(max_pages),
        "--retries", str(retries),
        "--retry-delay", str(retry_delay),
        "--progress-every", str(progress_every),
        "--machine-readable",
    ]
    if max_depth is not None:
        command.extend(["--max-depth", str(max_depth)])
    if family == "wikidebates":
        command.extend(["--family-file", str(family_file)])
    if selected_cache is not None:
        command.extend(["--cache-dir", str(selected_cache)])
    if extraction_date:
        command.extend(["--date", extraction_date])
    if login:
        command.append("--login")
    if force_refresh:
        command.append("--force-refresh")
    if allow_missing:
        command.append("--allow-missing")
    if follow_local_relations_at_dedicated_debate:
        command.append("--follow-local-relations-at-dedicated-debate")
    if follow_local_relations_at_existing_english_translation:
        command.append("--follow-local-relations-at-existing-english-translation")

    result = run(command, cwd=root, check=False)
    return result.returncode


def corpus_init_from_snapshot(
    root: Path,
    snapshot: Path,
    *,
    debate_id: str,
    short_code: str | None,
    output_dir: Path | None,
    scope_summary: str | None,
    overwrite: bool,
    skip_validation: bool,
) -> int:
    script = root / "kit" / "scripts" / "wikidebia_corpus_init.py"
    if not script.is_file():
        raise ManagementError("Constructeur de corpus depuis snapshot absent du kit")
    selected_snapshot = snapshot if snapshot.is_absolute() else (root / snapshot)
    selected_snapshot = selected_snapshot.resolve()
    if not selected_snapshot.exists():
        raise ManagementError(f"Snapshot introuvable : {snapshot}")
    selected_output = output_dir or (root / ".state" / "corpus-builds" / debate_id)
    if not selected_output.is_absolute():
        selected_output = root / selected_output
    selected_output = selected_output.resolve()
    portable_path(selected_output, root)
    allowed_output_root = (root / ".state" / "corpus-builds").resolve()
    try:
        selected_output.relative_to(allowed_output_root)
    except ValueError as exc:
        raise ManagementError(
            f"La sortie corpus-init doit rester sous {allowed_output_root}: {selected_output}"
        ) from exc
    if selected_output == allowed_output_root:
        raise ManagementError("Le dossier .state/corpus-builds ne peut pas être utilisé directement comme build")
    command = [
        python_command(root), str(script), str(selected_snapshot),
        "--output-dir", str(selected_output),
        "--debate-id", debate_id,
        "--project-root", str(root),
        "--machine-readable",
    ]
    if short_code:
        command.extend(["--short-code", short_code])
    if scope_summary:
        command.extend(["--scope-summary", scope_summary])
    if overwrite:
        command.append("--overwrite")
    if skip_validation:
        command.append("--skip-validation")
    result = run(command, cwd=root, check=False)
    return result.returncode

def corpus_review_graph(
    root: Path,
    debate_id: str,
    *,
    prepare: bool,
    finalize: bool,
    overwrite_review: bool,
) -> int:
    script = root / "kit" / "scripts" / "wikidebia_corpus_review.py"
    if not script.is_file():
        raise ManagementError("Outil de revue formelle du graphe absent du kit")
    command = [
        python_command(root), str(script), debate_id,
        "--project-root", str(root), "--machine-readable",
    ]
    if prepare:
        command.append("--prepare")
    if finalize:
        command.append("--finalize")
    if overwrite_review:
        command.append("--overwrite-review")
    result = run(command, cwd=root, check=False)
    return result.returncode


def corpus_workspace_init(root: Path, debate_id: str, *, work_id: str | None) -> int:
    script = root / "kit" / "scripts" / "wikidebia_editorial_workspace.py"
    if not script.is_file():
        raise ManagementError("Outil d'initialisation du workspace éditorial absent du kit")
    command = [
        python_command(root), str(script), debate_id,
        "--project-root", str(root), "--machine-readable",
    ]
    if work_id:
        command.extend(["--work-id", work_id])
    result = run(command, cwd=root, check=False)
    return result.returncode


def corpus_workspace_review(
    root: Path, debate_id: str, *, work_id: str, finalize: bool, apply: bool,
    confirm_review_sha256: str | None,
) -> int:
    script = root / "kit" / "scripts" / "wikidebia_editorial_review.py"
    if not script.is_file():
        raise ManagementError("Outil de revue éditoriale française absent du kit")
    command = [
        python_command(root), str(script), debate_id,
        "--work-id", work_id,
        "--project-root", str(root), "--machine-readable",
        "--finalize" if finalize else "--apply",
    ]
    if apply:
        if not confirm_review_sha256:
            raise ManagementError("--confirm-review-sha256 est obligatoire avec --apply")
        command.extend(["--confirm-review-sha256", confirm_review_sha256])
    result = run(command, cwd=root, check=False)
    return result.returncode



def corpus_workspace_content_review(
    root: Path, debate_id: str, *, work_id: str, prepare: bool, finalize: bool, apply: bool,
    overwrite_review: bool, confirm_review_sha256: str | None,
) -> int:
    script = root / "kit" / "scripts" / "wikidebia_content_review.py"
    if not script.is_file():
        raise ManagementError("Outil de revue du contenu français absent du kit")
    command = [
        python_command(root), str(script), debate_id,
        "--work-id", work_id,
        "--project-root", str(root), "--machine-readable",
    ]
    if prepare:
        command.append("--prepare")
    elif finalize:
        command.append("--finalize")
    else:
        command.append("--apply")
    if overwrite_review:
        command.append("--overwrite-review")
    if apply:
        if not confirm_review_sha256:
            raise ManagementError("--confirm-review-sha256 est obligatoire avec --apply")
        command.extend(["--confirm-review-sha256", confirm_review_sha256])
    result = run(command, cwd=root, check=False)
    return result.returncode

def corpus_workspace_translation_review(
    root: Path, debate_id: str, *, work_id: str, prepare: bool, finalize: bool, apply: bool,
    overwrite_review: bool, confirm_review_sha256: str | None,
) -> int:
    script = root / "kit" / "scripts" / "wikidebia_translation_review.py"
    if not script.is_file():
        raise ManagementError("Outil de traduction anglaise contrôlée absent du kit")
    command = [
        python_command(root), str(script), debate_id,
        "--work-id", work_id,
        "--project-root", str(root), "--machine-readable",
    ]
    if prepare:
        command.append("--prepare")
    elif finalize:
        command.append("--finalize")
    else:
        command.append("--apply")
    if overwrite_review:
        command.append("--overwrite-review")
    if apply:
        if not confirm_review_sha256:
            raise ManagementError("--confirm-review-sha256 est obligatoire avec --apply")
        command.extend(["--confirm-review-sha256", confirm_review_sha256])
    result = run(command, cwd=root, check=False)
    return result.returncode


def corpus_workspace_semantic_convergence(
    root: Path, debate_id: str, *, work_id: str, method_family: str, method: str, reviewer: str,
    note: str, new_certain_errors: int,
) -> int:
    script = root / "kit" / "scripts" / "wikidebia_semantic_convergence.py"
    if not script.is_file():
        raise ManagementError("Outil de convergence sémantique absent du kit")
    command = [
        python_command(root), str(script), debate_id,
        "--work-id", work_id, "--project-root", str(root),
        "--method-family", method_family, "--method", method, "--reviewer", reviewer, "--note", note,
        "--new-certain-errors", str(new_certain_errors), "--machine-readable",
    ]
    result = run(command, cwd=root, check=False)
    return result.returncode




def editorial_workflow(
    root: Path, debate_title: str, *, debate_id: str | None, short_code: str | None,
    snapshot: Path | None, force_refresh: bool,
) -> int:
    script = root / "kit" / "scripts" / "wikidebia_review_workflow.py"
    if not script.is_file():
        raise ManagementError("Orchestrateur éditorial absent du kit")
    command = [
        python_command(root), str(script), "--project-root", str(root), "workflow", debate_title,
    ]
    if debate_id:
        command.extend(["--debate-id", debate_id])
    if short_code:
        command.extend(["--short-code", short_code])
    if snapshot:
        selected = snapshot if snapshot.is_absolute() else (root / snapshot)
        command.extend(["--snapshot", str(selected.resolve())])
    if force_refresh:
        command.append("--force-refresh")
    return run(command, cwd=root, check=False).returncode


def _review_package_identity(archive: Path) -> str | None:
    try:
        with zipfile.ZipFile(archive) as zf:
            names = zf.namelist()
            if names.count("REVIEW_PACKAGE.json") != 1:
                return None
            raw = zf.read("REVIEW_PACKAGE.json")
            manifest = json.loads(raw.decode("utf-8"))
    except (OSError, zipfile.BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if manifest.get("schema") != "wikidebia-chatgpt-review-package-1.0":
        return None
    debate_id = str(manifest.get("debate_id") or "").strip()
    return debate_id if re.fullmatch(r"[A-Za-z0-9_.-]+", debate_id) else None


def find_review_archive(root: Path, debate_identifier: str | None = None) -> tuple[str, Path]:
    incoming = root / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    candidates: list[tuple[str, Path]] = []
    for path in sorted(incoming.iterdir()):
        if not path.is_file() or path.suffix.casefold() != ".zip":
            continue
        debate_id = _review_package_identity(path)
        if debate_id is not None:
            candidates.append((debate_id, path))

    if debate_identifier is not None:
        identifier = debate_identifier.strip()
        if identifier.casefold().endswith(".zip"):
            raise ManagementError("Indiquez l’identifiant du débat, pas le nom du fichier ZIP")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", identifier):
            raise ManagementError("Identifiant de débat invalide; caractères admis : lettres, chiffres, _, - et .")
        matches = [(debate_id, path) for debate_id, path in candidates if debate_id == identifier]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            available = ", ".join(sorted({debate_id for debate_id, _ in candidates})) or "aucun"
            raise ManagementError(
                f"Aucun ZIP de revue pour {identifier} dans incoming/. Débats disponibles : {available}"
            )
        names = ", ".join(path.name for _, path in matches)
        raise ManagementError(
            f"Plusieurs ZIP de revue concernent {identifier} dans incoming/ : {names}. "
            "Retirez ou archivez les doublons avant de relancer la commande."
        )

    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ManagementError(
            "Aucun ZIP de revue ChatGPT valide trouvé dans incoming/. "
            "Placez-y le ZIP corrigé puis relancez ./wikidebia review-import"
        )
    available = sorted({debate_id for debate_id, _ in candidates})
    commands = "; ".join(f"./wikidebia review-import {debate_id}" for debate_id in available)
    raise ManagementError(
        "Plusieurs ZIP de revue sont présents dans incoming/. Précisez l’identifiant du débat. "
        f"Commandes possibles : {commands}"
    )


def review_import(
    root: Path, debate_id: str | None, *, execute_graph_actions: bool = False,
    authorize_historical_changes: bool = False,
) -> int:
    script = root / "kit" / "scripts" / "wikidebia_review_workflow.py"
    if not script.is_file():
        raise ManagementError("Orchestrateur éditorial absent du kit")
    selected_debate_id, selected = find_review_archive(root, debate_id)
    command = [
        python_command(root), str(script), "--project-root", str(root),
        "review-import", selected_debate_id, str(selected.resolve()),
    ]
    if execute_graph_actions:
        command.append("--execute-graph-actions")
    if authorize_historical_changes:
        command.append("--authorize-historical-changes")
    result = run(command, cwd=root, check=False)
    if result.returncode == 0 and selected.exists():
        destination = root / "archives" / "reviews" / f"{timestamp()}-{selected_debate_id}" / selected.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(selected), destination)
        print(f"ZIP de revue archivé : {portable_path(destination, root)}")
    return result.returncode


def workflow_status(root: Path, debate_id: str) -> int:
    script = root / "kit" / "scripts" / "wikidebia_review_workflow.py"
    if not script.is_file():
        raise ManagementError("Orchestrateur éditorial absent du kit")
    command = [
        python_command(root), str(script), "--project-root", str(root),
        "workflow-status", debate_id,
    ]
    return run(command, cwd=root, check=False).returncode


def workflow_reconcile(root: Path, debate_id: str) -> int:
    script = root / "kit" / "scripts" / "wikidebia_review_workflow.py"
    if not script.is_file():
        raise ManagementError("Orchestrateur éditorial absent du kit")
    command = [
        python_command(root), str(script), "--project-root", str(root),
        "--machine-readable", "workflow-reconcile", debate_id,
    ]
    return run(command, cwd=root, check=False).returncode

def corpus_workspace_render(
    root: Path, debate_id: str, *, work_id: str, confirm_translation_sha256: str,
) -> int:
    script = root / "kit" / "scripts" / "wikidebia_render.py"
    if not script.is_file():
        raise ManagementError("Outil de rendu bilingue déterministe absent du kit")
    command = [
        python_command(root), str(script), debate_id,
        "--work-id", work_id,
        "--confirm-translation-sha256", confirm_translation_sha256,
        "--project-root", str(root), "--machine-readable",
    ]
    result = run(command, cwd=root, check=False)
    return result.returncode


def corpus_workspace_release(
    root: Path, debate_id: str, *, work_id: str, confirm_render_sha256: str,
) -> int:
    script = root / "kit" / "scripts" / "wikidebia_release.py"
    if not script.is_file():
        raise ManagementError("Outil de scellement local du corpus absent du kit")
    command = [
        python_command(root), str(script), debate_id,
        "--work-id", work_id,
        "--confirm-render-sha256", confirm_render_sha256,
        "--project-root", str(root), "--machine-readable",
    ]
    result = run(command, cwd=root, check=False)
    return result.returncode



def corpus_workspace_remote_compare(
    root: Path, debate_id: str, *, work_id: str, confirm_release_sha256: str,
    scope: str, comparison_id: str | None,
) -> int:
    script = root / "kit" / "scripts" / "wikidebia_remote_compare.py"
    if not script.is_file():
        raise ManagementError("Outil de comparaison distante en lecture seule absent du kit")
    command = [
        python_command(root), str(script), debate_id,
        "--work-id", work_id,
        "--confirm-release-sha256", confirm_release_sha256,
        "--scope", scope,
        "--project-root", str(root), "--machine-readable",
    ]
    if comparison_id:
        command.extend(["--comparison-id", comparison_id])
    result = run(command, cwd=root, check=False)
    return result.returncode

def corpus_workspace_remote_plan_review(
    root: Path, debate_id: str, *, work_id: str, comparison_id: str,
    prepare: bool, finalize: bool, overwrite_review: bool,
) -> int:
    script = root / "kit" / "scripts" / "wikidebia_remote_plan_review.py"
    if not script.is_file():
        raise ManagementError("Outil de revue formelle du plan distant absent du kit")
    command = [
        python_command(root), str(script), debate_id,
        "--work-id", work_id, "--comparison-id", comparison_id,
        "--project-root", str(root), "--machine-readable",
    ]
    command.append("--prepare" if prepare else "--finalize")
    if overwrite_review:
        command.append("--overwrite-review")
    result = run(command, cwd=root, check=False)
    return result.returncode



def corpus_workspace_remote_execute(
    root: Path, debate_id: str, *, work_id: str, comparison_id: str,
    prepare: bool, execute: bool, mode: str,
    confirm_acceptance_sha256: str | None, confirm_preflight_sha256: str | None,
) -> int:
    script = root / "kit" / "scripts" / "wikidebia_remote_execute.py"
    if not script.is_file():
        raise ManagementError("Outil d’exécution distante contrôlée absent du kit")
    command = [
        python_command(root), str(script), debate_id,
        "--work-id", work_id, "--comparison-id", comparison_id,
        "--project-root", str(root), "--machine-readable",
    ]
    if prepare:
        if not confirm_acceptance_sha256:
            raise ManagementError("--confirm-acceptance-sha256 est obligatoire avec --prepare")
        command.extend(["--prepare", "--mode", mode, "--confirm-acceptance-sha256", confirm_acceptance_sha256])
    else:
        if not confirm_preflight_sha256:
            raise ManagementError("--confirm-preflight-sha256 est obligatoire avec --execute")
        command.extend(["--execute", "--confirm-preflight-sha256", confirm_preflight_sha256])
    result = run(command, cwd=root, check=False)
    return result.returncode


def corpus_workspace_close(
    root: Path, debate_id: str, *, work_id: str, comparison_id: str,
    confirm_execution_sha256: str,
) -> int:
    script = root / "kit" / "scripts" / "wikidebia_work_close.py"
    if not script.is_file():
        raise ManagementError("Outil de clôture formelle du Work absent du kit")
    command = [
        python_command(root), str(script), debate_id,
        "--work-id", work_id, "--comparison-id", comparison_id,
        "--confirm-execution-sha256", confirm_execution_sha256,
        "--project-root", str(root), "--machine-readable",
    ]
    result = run(command, cwd=root, check=False)
    return result.returncode

def corpus_promote_graph(root: Path, debate_id: str, *, confirm_review_sha256: str) -> int:
    script = root / "kit" / "scripts" / "wikidebia_corpus_promote.py"
    if not script.is_file():
        raise ManagementError("Outil de promotion atomique du corpus absent du kit")
    command = [
        python_command(root), str(script), debate_id,
        "--confirm-review-sha256", confirm_review_sha256,
        "--project-root", str(root), "--machine-readable",
    ]
    result = run(command, cwd=root, check=False)
    return result.returncode


def github_init(root: Path, remote: str, private: bool) -> None:
    if not git_is_repo(root):
        run(["git", "init", "-b", "main"], cwd=root)
    if git_has_origin(root):
        current = run(["git", "remote", "get-url", "origin"], cwd=root, capture=True).stdout.strip()
        if current != remote:
            raise ManagementError(f"origin existe déjà et pointe vers {current}")
    else:
        run(["git", "remote", "add", "origin", remote], cwd=root)
    # Le caractère privé/public est défini lors de la création du dépôt distant.
    _ = private
    assert_portable_sources(root)
    git_commit_and_push(root, "Initialisation du dépôt Wikidéb’IA", push=False)
    git_push_current_branch(root, strict=True)


def github_sync(root: Path) -> None:
    if not git_is_repo(root):
        raise ManagementError("Le dossier n’est pas un dépôt Git")
    assert_portable_sources(root)
    # Cette commande sert aussi à terminer une mise à jour installée avec --no-git :
    # elle nettoie l’index, ajoute les sources sûres et crée le commit avant le push.
    git_commit_and_push(root, "Synchronisation sécurisée Wikidéb’IA", push=False)
    git_push_current_branch(root, strict=True)


def check_wikidebates_apis(access_token: str, *, timeout: float = 15.0) -> dict[str, Any]:
    """Probe both Wikidebates APIs without exposing the access token."""
    results: dict[str, Any] = {}
    query = urllib.parse.urlencode({"action": "query", "meta": "siteinfo", "format": "json"})
    for language in ("fr", "en"):
        url = f"https://{language}.wikidebates.org/w/api.php?{query}"
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": f"Wikidebia/{KIT_VERSION} doctor",
                "x-wikidebia-access": access_token,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = int(response.status)
            results[language] = {
                "status": "passed" if status == 200 else "failed",
                "http_status": status,
            }
        except urllib.error.HTTPError as exc:
            results[language] = {"status": "failed", "http_status": int(exc.code)}
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            results[language] = {
                "status": "failed", "error_type": type(exc).__name__,
            }
    return results


def doctor(root: Path, *, check_api: bool = False) -> dict[str, Any]:
    issues: list[str] = []
    versions = current_versions(root)
    if not versions:
        issues.append("VERSIONS.json introuvable")
    if (root / "user-config.py").exists() or (root / "user-password.cfg").exists():
        issues.append("Secrets Pywikibot encore présents à la racine")
    local_pywikibot_config = (root / "private" / "pywikibot" / "user-config.py").is_file()
    managed_credentials: dict[str, str] = {}
    for language in ("fr", "en"):
        prefix = f"WIKIDEBIA_{language.upper()}_BOT_"
        username_present = bool(os.environ.get(prefix + "USERNAME"))
        password_present = bool(os.environ.get(prefix + "PASSWORD"))
        if username_present and password_present:
            managed_credentials[language] = "complete"
        elif username_present or password_present:
            managed_credentials[language] = "partial"
            missing = prefix + ("PASSWORD" if username_present else "USERNAME")
            issues.append(f"Identifiants Pywikibot gérés incomplets : {missing} absent")
        else:
            managed_credentials[language] = "absent"
    if not local_pywikibot_config and "complete" not in managed_credentials.values():
        issues.append(
            "Accès Pywikibot absent : configurez private/pywikibot/user-config.py "
            "ou les variables WIKIDEBIA_<LANG>_BOT_USERNAME/PASSWORD"
        )
    api_access_token = os.environ.get("WIKIDEBIA_API_TOKEN")
    api_connectivity: dict[str, Any] = {"requested": check_api}
    if check_api:
        if not api_access_token:
            issues.append("Test API impossible : WIKIDEBIA_API_TOKEN absent")
            api_connectivity["status"] = "not_configured"
        else:
            api_results = check_wikidebates_apis(api_access_token)
            api_connectivity.update({"status": "completed", "languages": api_results})
            for language, result in api_results.items():
                if result.get("status") != "passed":
                    detail = result.get("http_status") or result.get("error_type") or "erreur inconnue"
                    issues.append(f"API Wikidebates {language} inaccessible : {detail}")
    required_scripts = (
        "wikidebia_publish.py", "wikidebia_update.py",
        "wikidebia_graph_extract.py", "wikidebia_corpus_init.py",
        "wikidebia_corpus_review.py", "wikidebia_corpus_promote.py",
        "wikidebia_editorial_workspace.py", "wikidebia_editorial_review.py",
        "wikidebia_content_review.py", "wikidebia_translation_review.py",
        "wikidebia_render.py", "wikidebia_release.py",
        "wikidebia_remote_compare.py", "wikidebia_remote_plan_review.py",
        "wikidebia_remote_execute.py", "wikidebia_work_close.py",
        "wikidebia_workflow_baseline.py", "wikidebia_final_publication.py",
        "wikidebia_retro_tag.py",
    )
    for script_name in required_scripts:
        if not (root / "kit" / "scripts" / script_name).is_file():
            issues.append(f"kit/scripts/{script_name} absent")
    runtime = runtime_environment_report(root)
    if not runtime.get("requirements_sha256"):
        issues.append("requirements-runtime.txt absent")
    if not runtime.get("python_available"):
        issues.append(".venv/bin/python absent ou inutilisable")
    missing = runtime.get("missing_modules") or []
    if missing:
        issues.append("Modules Python manquants dans .venv : " + ", ".join(str(item) for item in missing))
    if runtime.get("probe_error"):
        issues.append("Diagnostic de .venv impossible : " + str(runtime["probe_error"]))
    try:
        assert_portable_sources(root)
    except ManagementError as exc:
        issues.append(str(exc))
    issues.extend(git_security_issues(root))
    updates = root / "updates"
    update_count = len(list(updates.iterdir())) if updates.is_dir() else 0
    return {
        "versions": versions,
        "access_configuration": {
            "local_pywikibot_config": local_pywikibot_config,
            "managed_credentials": managed_credentials,
            "api_access_header_configured": bool(api_access_token),
            "api_connectivity": api_connectivity,
        },
        "runtime_environment": runtime,
        "git_repository": git_is_repo(root),
        "git_origin": git_has_origin(root),
        "updates_entries": update_count,
        "issues": issues,
        "status": "passed" if not issues else "failed",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wikidebia", description="Gestion portable de Wikidéb’IA")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)

    publish = sub.add_parser("publish", help="Valider, planifier et publier un ZIP de débat")
    publish.add_argument("debate_identifier", nargs="?", help="Nom du ZIP sans .zip; facultatif si incoming/ contient un seul ZIP. Le debate_id interne peut être différent.")
    publish.add_argument("--scope", choices=SCOPES, default="all")
    publish.add_argument("--yes", action="store_true", help=argparse.SUPPRESS)
    publish.add_argument("--keep-zip", action="store_true", help="Ne pas archiver le ZIP après succès")

    update = sub.add_parser("update", help="Reprendre un débat déjà publié avec créations, mises à jour et retraits contrôlés")
    update.add_argument("debate_identifier", nargs="?", help="Nom du ZIP entrant sans .zip, ou identifiant du corpus installé si incoming/ est vide")
    update.add_argument("--archive", metavar="SÉLECTEUR", help="Option de compatibilité pour sélectionner explicitement incoming/SÉLECTEUR.zip")
    update.add_argument("--scope", choices=("all", "fr", "en"), default=None, help="Portée explicite; par défaut, détection automatique des langues publiables")
    update.add_argument("--yes", action="store_true", help=argparse.SUPPRESS)
    update.add_argument("--no-delete", action="store_true", help="Exécuter la reprise sans suppressions finales")
    update.add_argument("--only-delete", action="store_true", help="N’exécuter que les retraits sûrs et redirections de fusion")
    update.add_argument("--dry-run", action="store_true", help="Produire seulement le plan signé")
    update.add_argument("--keep-zip", action="store_true", help="Ne pas archiver le ZIP après succès")
    update.add_argument("--interlanguage-only", action="store_true", help="Préserver chaque page française distante et n'ajouter que son lien vers la page anglaise correspondante")

    retro_tag = sub.add_parser("tag-translated-fr", help="Ajouter rétroactivement translated-fr aux révisions anglaises de traduction")
    retro_tag.add_argument("debate_id", help="Identifiant interne du débat")
    retro_tag.add_argument("--dry-run", action="store_true", help="Vérifier les révisions ciblées sans modifier leurs balises")

    upgrade = sub.add_parser("upgrade", help="Installer les composants déposés dans updates/")
    upgrade.add_argument("archive", nargs="?", type=Path, help="Archive complète facultative")
    upgrade.add_argument("--allow-downgrade", action="store_true")
    upgrade.add_argument("--no-push", action="store_true", help="Créer le commit sans pousser vers origin")
    upgrade.add_argument("--no-git", action="store_true", help="Ne pas créer de commit Git")

    relay = sub.add_parser("fr-publication-relay", help="Relayer des demandes explicites vers le wiki français")
    relay.add_argument("--execute", action="store_true", help="Exécuter les demandes de la branche dédiée")
    relay.add_argument("--retry", help="Identifiant d'une demande bloquée à retenter")
    relay.add_argument("--enqueue", type=Path, help="Dossier d'une demande approuvée à envoyer")
    relay.add_argument("--confirm-request-sha256")

    workflow = sub.add_parser(
        "workflow",
        help="Piloter automatiquement le workflow éditorial jusqu'au prochain paquet ChatGPT",
    )
    workflow.add_argument("debate_title", help="Titre exact de la page Débat")
    workflow.add_argument("--debate-id", help="Identifiant stable; par défaut dérivé du titre")
    workflow.add_argument("--short-code", help="Code court du débat; par défaut dérivé automatiquement")
    workflow.add_argument("--snapshot", type=Path, help="Snapshot graph-extract existant; sinon extraction automatique")
    workflow.add_argument("--force-refresh", action="store_true", help="Forcer la relecture distante lors de l'extraction initiale")

    review_import_parser = sub.add_parser(
        "review-import",
        help="Réimporter un ZIP corrigé par ChatGPT et reprendre automatiquement le workflow",
    )
    review_import_parser.add_argument("debate_id", nargs="?", help="Identifiant du débat uniquement si plusieurs ZIP de revue sont présents dans incoming/")
    review_import_parser.add_argument("--execute-graph-actions", action="store_true", help="Après une revue de graphe rejetée, exécuter en une commande les suppressions, redirections, déplacements et requalifications explicitement décidés")
    review_import_parser.add_argument("--authorize-historical-changes", action="store_true", help="Autoriser uniquement les deltas d’introduction/résumés historiques explicitement déclarés dans le ZIP de revue sélectionné")

    workflow_status_parser = sub.add_parser(
        "workflow-status", help="Afficher l'état de l'orchestration éditoriale"
    )
    workflow_status_parser.add_argument("debate_id")
    workflow_reconcile_parser = sub.add_parser(
        "workflow-reconcile", help="Réconcilier un workflow en retard depuis ses preuves signées"
    )
    workflow_reconcile_parser.add_argument("debate_id")

    graph = sub.add_parser(
        "graph-extract",
        help="Extraire récursivement un graphe argumentatif depuis le wiki, en lecture seule",
    )
    graph.add_argument("debate_title", help="Titre exact de la page Débat")
    graph.add_argument("--lang", default="fr", help="Code linguistique Pywikibot (défaut : fr)")
    graph.add_argument("--family", default="wikidebates", help="Famille Pywikibot (défaut : wikidebates)")
    graph.add_argument("--output-dir", type=Path, help="Dossier de sortie, par défaut .state/graph-extract/<slug>")
    graph.add_argument("--cache-dir", type=Path, help="Dossier de cache distinct du dossier de sortie")
    graph.add_argument("--slug", help="Préfixe stable des fichiers de sortie")
    graph.add_argument("--date", dest="extraction_date", help="Date d’extraction AAAA-MM-JJ")
    graph.add_argument("--login", action="store_true", help="Ouvrir une session Pywikibot avant les lectures")
    graph.add_argument("--force-refresh", action="store_true", help="Ignorer le cache et relire toutes les pages")
    graph.add_argument("--allow-missing", action="store_true", help="Exporter même si certaines pages liées sont absentes")
    graph.add_argument(
        "--max-depth",
        type=int,
        help="Profondeur maximale en arêtes; 0 conserve uniquement les arguments de niveau 1",
    )
    graph.add_argument("--max-pages", type=int, default=5000, help="Limite de sécurité du nombre de pages Argument")
    graph.add_argument("--retries", type=int, default=4, help="Nombre de nouvelles tentatives après erreur réseau")
    graph.add_argument("--retry-delay", type=float, default=2.0, help="Délai initial entre les tentatives")
    graph.add_argument("--progress-every", type=int, default=25, help="Fréquence des messages de progression")
    graph.add_argument(
        "--follow-local-relations-at-dedicated-debate",
        "--follow-local-relations-at-detailed-debate",
        action="store_true",
        help="Suivre les relations locales d’une page frontière sans ouvrir le débat sous-jacent",
    )
    graph.add_argument(
        "--follow-local-relations-at-existing-english-translation",
        action="store_true",
        help="Mode de diagnostic : poursuivre sous les arguments déjà traduits en anglais",
    )

    corpus_init = sub.add_parser(
        "corpus-init-from-snapshot",
        help="Construire un corpus graph_draft local depuis un snapshot graph-extract",
    )
    corpus_init.add_argument("snapshot", type=Path, help="Dossier ou ZIP produit par graph-extract")
    corpus_init.add_argument("--debate-id", required=True, help="Identifiant stable du corpus")
    corpus_init.add_argument("--short-code", help="Code court du débat (2 à 12 caractères)")
    corpus_init.add_argument("--output-dir", type=Path, help="Défaut : .state/corpus-builds/<debate_id>")
    corpus_init.add_argument("--scope-summary", help="Résumé provisoire du périmètre")
    corpus_init.add_argument("--overwrite", action="store_true", help="Remplacer un build local existant")
    corpus_init.add_argument("--skip-validation", action="store_true", help="Ne pas lancer la validation structurelle initiale")

    corpus_review = sub.add_parser(
        "corpus-review-graph",
        help="Préparer ou finaliser la revue formelle d'un build graph_draft",
    )
    corpus_review.add_argument("debate_id", help="Identifiant du build sous .state/corpus-builds/")
    review_action = corpus_review.add_mutually_exclusive_group(required=True)
    review_action.add_argument("--prepare", action="store_true", help="Créer les registres de revue à compléter")
    review_action.add_argument("--finalize", action="store_true", help="Sceller une revue complétée et valider le graphe")
    corpus_review.add_argument("--overwrite-review", action="store_true", help="Régénérer les registres préparatoires")

    corpus_promote = sub.add_parser(
        "corpus-promote",
        help="Promouvoir atomiquement un build graph_validated vers corpus/",
    )
    corpus_promote.add_argument("debate_id", help="Identifiant du build approuvé")
    corpus_promote.add_argument("--confirm-review-sha256", required=True, help="Empreinte exacte de la revue approuvée")

    corpus_workspace = sub.add_parser(
        "corpus-workspace-init",
        help="Créer un workspace éditorial audité depuis un corpus graph_validated promu",
    )
    corpus_workspace.add_argument("debate_id", help="Identifiant du corpus sous corpus/")
    corpus_workspace.add_argument("--work-id", help="Identifiant explicite du Work; défaut : EDIT-AAAAMMJJ-NNN")

    corpus_workspace_review_parser = sub.add_parser(
        "corpus-workspace-review",
        help="Finaliser puis appliquer la revue française des titres, rubriques et mots-clés",
    )
    corpus_workspace_review_parser.add_argument("debate_id", help="Identifiant du corpus sous corpus/")
    corpus_workspace_review_parser.add_argument("--work-id", required=True, help="Identifiant du workspace éditorial")
    workspace_review_action = corpus_workspace_review_parser.add_mutually_exclusive_group(required=True)
    workspace_review_action.add_argument("--finalize", action="store_true", help="Sceller la revue complétée sans modifier working-copy")
    workspace_review_action.add_argument("--apply", action="store_true", help="Créer reviewed-copy à partir de la revue scellée")
    corpus_workspace_review_parser.add_argument("--confirm-review-sha256", help="Empreinte obligatoire avec --apply")

    corpus_content_review_parser = sub.add_parser(
        "corpus-workspace-content-review",
        help="Préparer, finaliser puis appliquer la revue du contenu français",
    )
    corpus_content_review_parser.add_argument("debate_id", help="Identifiant du corpus sous corpus/")
    corpus_content_review_parser.add_argument("--work-id", required=True, help="Identifiant du workspace éditorial")
    content_review_action = corpus_content_review_parser.add_mutually_exclusive_group(required=True)
    content_review_action.add_argument("--prepare", action="store_true", help="Préparer les registres depuis le wikicode importé")
    content_review_action.add_argument("--finalize", action="store_true", help="Sceller la revue du contenu sans modifier reviewed-copy")
    content_review_action.add_argument("--apply", action="store_true", help="Créer content-reviewed-copy depuis la revue scellée")
    corpus_content_review_parser.add_argument("--overwrite-review", action="store_true", help="Régénérer les registres préparatoires non appliqués")
    corpus_content_review_parser.add_argument("--confirm-review-sha256", help="Empreinte obligatoire avec --apply")

    corpus_translation_review_parser = sub.add_parser(
        "corpus-workspace-translation",
        help="Préparer, finaliser puis appliquer la traduction anglaise contrôlée",
    )
    corpus_translation_review_parser.add_argument("debate_id", help="Identifiant du corpus sous corpus/")
    corpus_translation_review_parser.add_argument("--work-id", required=True, help="Identifiant du workspace éditorial")
    translation_review_action = corpus_translation_review_parser.add_mutually_exclusive_group(required=True)
    translation_review_action.add_argument("--prepare", action="store_true", help="Préparer le registre bilingue depuis les verrous français")
    translation_review_action.add_argument("--finalize", action="store_true", help="Sceller la traduction anglaise sans modifier content-reviewed-copy")
    translation_review_action.add_argument("--apply", action="store_true", help="Créer translated-copy depuis la revue scellée")
    corpus_translation_review_parser.add_argument("--overwrite-review", action="store_true", help="Régénérer les registres préparatoires non appliqués")
    corpus_translation_review_parser.add_argument("--confirm-review-sha256", help="Empreinte obligatoire avec --apply")

    semantic_convergence_parser = sub.add_parser(
        "corpus-workspace-semantic-convergence",
        help="Enregistrer une passe indépendante de convergence sémantique sur la traduction scellée",
    )
    semantic_convergence_parser.add_argument("debate_id", help="Identifiant du corpus sous corpus/")
    semantic_convergence_parser.add_argument("--work-id", required=True, help="Identifiant du workspace éditorial")
    semantic_convergence_parser.add_argument("--method-family", required=True, choices=["proposition_by_proposition", "risk_marker_review", "reverse_source_target", "field_boundary_review", "independent_bilingual_reread"], help="Famille normalisée de la passe sémantique")
    semantic_convergence_parser.add_argument("--method", required=True, help="Méthode concrète ou angle de la passe sémantique")
    semantic_convergence_parser.add_argument("--reviewer", required=True, help="Relecteur de la passe")
    semantic_convergence_parser.add_argument("--note", required=True, help="Note concrète sur la passe effectuée")
    semantic_convergence_parser.add_argument("--new-certain-errors", type=int, default=0, help="Nombre de nouvelles erreurs certaines trouvées")

    corpus_render_parser = sub.add_parser(
        "corpus-workspace-render",
        help="Rendre et valider les pages MediaWiki bilingues depuis la traduction verrouillée",
    )
    corpus_render_parser.add_argument("debate_id", help="Identifiant du corpus sous corpus/")
    corpus_render_parser.add_argument("--work-id", required=True, help="Identifiant du workspace éditorial")
    corpus_render_parser.add_argument(
        "--confirm-translation-sha256", required=True,
        help="Empreinte exacte de la revue de traduction verrouillée",
    )

    corpus_release_parser = sub.add_parser(
        "corpus-workspace-release",
        help="Sceller le rendu bilingue en corpus local installable sans accès distant",
    )
    corpus_release_parser.add_argument("debate_id", help="Identifiant du corpus sous corpus/")
    corpus_release_parser.add_argument("--work-id", required=True, help="Identifiant du workspace éditorial")
    corpus_release_parser.add_argument(
        "--confirm-render-sha256", required=True,
        help="Empreinte exacte de rendered-copy",
    )

    corpus_remote_compare_parser = sub.add_parser(
        "corpus-workspace-remote-compare",
        help="Comparer release-copy au wiki en lecture seule et produire un plan signé",
    )
    corpus_remote_compare_parser.add_argument("debate_id", help="Identifiant du corpus sous corpus/")
    corpus_remote_compare_parser.add_argument("--work-id", required=True, help="Identifiant du workspace éditorial")
    corpus_remote_compare_parser.add_argument(
        "--confirm-release-sha256", required=True,
        help="Empreinte exacte de release-copy",
    )
    corpus_remote_compare_parser.add_argument("--scope", choices=("all", "fr", "en"), default="all")
    corpus_remote_compare_parser.add_argument("--comparison-id", help="Identifiant REMOTE-AAAAMMJJ-NNN facultatif")

    corpus_remote_plan_review_parser = sub.add_parser(
        "corpus-workspace-plan-review",
        help="Préparer ou finaliser la revue formelle d’un plan distant signé",
    )
    corpus_remote_plan_review_parser.add_argument("debate_id", help="Identifiant du corpus sous corpus/")
    corpus_remote_plan_review_parser.add_argument("--work-id", required=True, help="Identifiant du workspace éditorial")
    corpus_remote_plan_review_parser.add_argument("--comparison-id", required=True, help="Identifiant REMOTE-AAAAMMJJ-NNN")
    remote_plan_review_action = corpus_remote_plan_review_parser.add_mutually_exclusive_group(required=True)
    remote_plan_review_action.add_argument("--prepare", action="store_true", help="Créer le registre de revue à compléter")
    remote_plan_review_action.add_argument("--finalize", action="store_true", help="Sceller la décision et produire le handoff d’acceptation")
    corpus_remote_plan_review_parser.add_argument("--overwrite-review", action="store_true", help="Régénérer une revue préparatoire non finalisée")

    corpus_remote_execute_parser = sub.add_parser(
        "corpus-workspace-plan-execute",
        help="Préparer puis exécuter de façon contrôlée un plan distant accepté",
    )
    corpus_remote_execute_parser.add_argument("debate_id", help="Identifiant du corpus sous corpus/")
    corpus_remote_execute_parser.add_argument("--work-id", required=True, help="Identifiant du workspace éditorial")
    corpus_remote_execute_parser.add_argument("--comparison-id", required=True, help="Identifiant REMOTE-AAAAMMJJ-NNN")
    remote_execute_action = corpus_remote_execute_parser.add_mutually_exclusive_group(required=True)
    remote_execute_action.add_argument("--prepare", action="store_true", help="Relire le wiki, vérifier les droits et sceller le préflight")
    remote_execute_action.add_argument("--execute", action="store_true", help="Exécuter le plan après confirmation du préflight")
    corpus_remote_execute_parser.add_argument("--mode", choices=("all", "no-delete", "only-delete"), default="all")
    corpus_remote_execute_parser.add_argument("--confirm-acceptance-sha256")
    corpus_remote_execute_parser.add_argument("--confirm-preflight-sha256")

    corpus_close_parser = sub.add_parser(
        "corpus-workspace-close",
        help="Clôturer un Work après exécution distante vérifiée et promouvoir le corpus publié",
    )
    corpus_close_parser.add_argument("debate_id", help="Identifiant du corpus sous corpus/")
    corpus_close_parser.add_argument("--work-id", required=True, help="Identifiant du workspace éditorial")
    corpus_close_parser.add_argument("--comparison-id", required=True, help="Identifiant REMOTE-AAAAMMJJ-NNN")
    corpus_close_parser.add_argument(
        "--confirm-execution-sha256", required=True,
        help="Empreinte exacte du reçu d’exécution distante",
    )

    continuity_parser = sub.add_parser(
        "continuity-sync",
        help="Projeter et vérifier la succession française signée dans la sauvegarde de continuité",
    )
    continuity_parser.add_argument("debate_id", help="Identifiant interne du débat")
    continuity_parser.add_argument("--work-id", help="Work attendu; par défaut, celui du workflow courant")
    continuity_parser.add_argument(
        "--snapshot-root", type=Path,
        help="Racine de la projection; défaut : continuity/<debate_id>/latest",
    )
    continuity_parser.add_argument(
        "--check", action="store_true",
        help="Vérifier la projection existante sans la modifier",
    )

    github = sub.add_parser("github-init", help="Initialiser le dépôt et pousser vers GitHub")
    github.add_argument("remote", help="URL Git du dépôt, par exemple git@github.com:COMPTE/wikidebia.git")
    github.add_argument("--private", action="store_true", help="Documentation uniquement; la visibilité se règle sur GitHub")
    sub.add_parser("github-sync", help="Pousser les commits locaux vers origin après authentification")

    doctor_parser = sub.add_parser("doctor", help="Contrôler l'installation portable")
    doctor_parser.add_argument(
        "--check-api", action="store_true",
        help="Tester les API fr/en avec x-wikidebia-access sans afficher le jeton",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.expanduser().resolve()
    if args.command == "publish":
        result = publish_debate(root, args.debate_identifier, args.scope, args.yes, args.keep_zip)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "update":
        result = update_debate(root, args.debate_identifier, args.scope, args.yes, args.no_delete, args.only_delete, args.dry_run, args.keep_zip, args.archive, args.interlanguage_only)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "tag-translated-fr":
        result = tag_translated_fr(root, args.debate_id, dry_run=args.dry_run)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "upgrade":
        versions = update_sources(
            root,
            args.archive,
            allow_downgrade=args.allow_downgrade,
            no_push=args.no_push,
            no_git=args.no_git,
        )
        print(json.dumps(versions, ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "fr-publication-relay":
        from wikidebia_fr_publication_relay import main as relay_main
        command = ["--root", str(root)]
        if args.execute:
            command.append("--execute")
        if args.retry:
            command.extend(["--retry", args.retry])
        if args.enqueue:
            command.extend(["--enqueue", str(args.enqueue)])
        if args.confirm_request_sha256:
            command.extend(["--confirm-request-sha256", args.confirm_request_sha256])
        try:
            return relay_main(command)
        except Exception as exc:
            raise ManagementError(f"Relais de publication arrêté : {exc}") from exc
    if args.command == "workflow":
        return editorial_workflow(
            root, args.debate_title, debate_id=args.debate_id, short_code=args.short_code,
            snapshot=args.snapshot, force_refresh=args.force_refresh,
        )
    if args.command == "review-import":
        return review_import(
            root, args.debate_id, execute_graph_actions=args.execute_graph_actions,
            authorize_historical_changes=args.authorize_historical_changes,
        )
    if args.command == "workflow-status":
        return workflow_status(root, args.debate_id)
    if args.command == "workflow-reconcile":
        return workflow_reconcile(root, args.debate_id)
    if args.command == "graph-extract":
        return graph_extract_debate(
            root,
            args.debate_title,
            lang=args.lang,
            family=args.family,
            output_dir=args.output_dir,
            cache_dir=args.cache_dir,
            slug=args.slug,
            extraction_date=args.extraction_date,
            login=args.login,
            force_refresh=args.force_refresh,
            allow_missing=args.allow_missing,
            max_depth=args.max_depth,
            max_pages=args.max_pages,
            retries=args.retries,
            retry_delay=args.retry_delay,
            progress_every=args.progress_every,
            follow_local_relations_at_dedicated_debate=args.follow_local_relations_at_dedicated_debate,
            follow_local_relations_at_existing_english_translation=(
                args.follow_local_relations_at_existing_english_translation
            ),
        )
    if args.command == "corpus-init-from-snapshot":
        return corpus_init_from_snapshot(
            root,
            args.snapshot,
            debate_id=args.debate_id,
            short_code=args.short_code,
            output_dir=args.output_dir,
            scope_summary=args.scope_summary,
            overwrite=args.overwrite,
            skip_validation=args.skip_validation,
        )
    if args.command == "corpus-review-graph":
        return corpus_review_graph(
            root,
            args.debate_id,
            prepare=args.prepare,
            finalize=args.finalize,
            overwrite_review=args.overwrite_review,
        )
    if args.command == "corpus-promote":
        return corpus_promote_graph(
            root,
            args.debate_id,
            confirm_review_sha256=args.confirm_review_sha256,
        )
    if args.command == "corpus-workspace-init":
        return corpus_workspace_init(root, args.debate_id, work_id=args.work_id)
    if args.command == "corpus-workspace-review":
        return corpus_workspace_review(
            root, args.debate_id, work_id=args.work_id, finalize=args.finalize, apply=args.apply,
            confirm_review_sha256=args.confirm_review_sha256,
        )
    if args.command == "corpus-workspace-content-review":
        return corpus_workspace_content_review(
            root, args.debate_id, work_id=args.work_id, prepare=args.prepare, finalize=args.finalize,
            apply=args.apply, overwrite_review=args.overwrite_review,
            confirm_review_sha256=args.confirm_review_sha256,
        )

    if args.command == "corpus-workspace-translation":
        return corpus_workspace_translation_review(
            root, args.debate_id, work_id=args.work_id, prepare=args.prepare, finalize=args.finalize,
            apply=args.apply, overwrite_review=args.overwrite_review,
            confirm_review_sha256=args.confirm_review_sha256,
        )

    if args.command == "corpus-workspace-semantic-convergence":
        return corpus_workspace_semantic_convergence(
            root, args.debate_id, work_id=args.work_id, method_family=args.method_family, method=args.method,
            reviewer=args.reviewer, note=args.note, new_certain_errors=args.new_certain_errors,
        )

    if args.command == "corpus-workspace-render":
        return corpus_workspace_render(
            root, args.debate_id, work_id=args.work_id,
            confirm_translation_sha256=args.confirm_translation_sha256,
        )

    if args.command == "corpus-workspace-release":
        return corpus_workspace_release(
            root, args.debate_id, work_id=args.work_id,
            confirm_render_sha256=args.confirm_render_sha256,
        )

    if args.command == "corpus-workspace-remote-compare":
        return corpus_workspace_remote_compare(
            root, args.debate_id, work_id=args.work_id,
            confirm_release_sha256=args.confirm_release_sha256,
            scope=args.scope, comparison_id=args.comparison_id,
        )

    if args.command == "corpus-workspace-plan-review":
        return corpus_workspace_remote_plan_review(
            root, args.debate_id, work_id=args.work_id, comparison_id=args.comparison_id,
            prepare=args.prepare, finalize=args.finalize, overwrite_review=args.overwrite_review,
        )

    if args.command == "corpus-workspace-plan-execute":
        return corpus_workspace_remote_execute(
            root, args.debate_id, work_id=args.work_id, comparison_id=args.comparison_id,
            prepare=args.prepare, execute=args.execute, mode=args.mode,
            confirm_acceptance_sha256=args.confirm_acceptance_sha256,
            confirm_preflight_sha256=args.confirm_preflight_sha256,
        )

    if args.command == "corpus-workspace-close":
        return corpus_workspace_close(
            root, args.debate_id, work_id=args.work_id, comparison_id=args.comparison_id,
            confirm_execution_sha256=args.confirm_execution_sha256,
        )

    if args.command == "continuity-sync":
        from wikidebia_continuity import ContinuityError, sync_signed_french_history
        try:
            result = sync_signed_french_history(
                root,
                args.debate_id,
                work_id=args.work_id,
                snapshot_root=args.snapshot_root,
                check_only=args.check,
            )
        except ContinuityError as exc:
            raise ManagementError(f"Continuité bloquée : {exc}") from exc
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0

    if args.command == "github-init":
        github_init(root, args.remote, args.private)
        print("Dépôt GitHub initialisé et synchronisé.")
        return 0
    if args.command == "github-sync":
        github_sync(root)
        print("Dépôt GitHub synchronisé.")
        return 0
    report = doctor(root, check_api=args.check_api)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ManagementError as exc:
        print(f"WIKIDEBIA BLOQUÉ : {exc}", file=sys.stderr)
        raise SystemExit(2)
