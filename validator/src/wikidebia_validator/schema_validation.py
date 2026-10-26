from __future__ import annotations

import json
import hashlib
from importlib.resources import files
from pathlib import Path
from typing import Any

from jsonschema import FormatChecker
from jsonschema.validators import validator_for
from referencing import Registry, Resource

from .package import PackageContext


SCHEMA_BY_PATH = {
    "manifest.json": "debate_package.schema.json",
    "scope.json": "scope.schema.json",
    "data/registre_debat.json": "argument_registry.schema.json",
    "data/sources.json": "source_registry.schema.json",
    "data/lots_fr.json": "batch_collection.schema.json",
    "data/lots_en.json": "batch_collection.schema.json",
    "graph/graphe_argumentatif.json": "argument_graph.schema.json",
    "patches/interlanguage_fr.json": "interlanguage_patch.schema.json",
    "patches/interlanguage_fr.validated.json": "interlanguage_patch.schema.json",
    "release_manifest.json": "release_manifest.schema.json",
    "normative/requirements_catalog_wikidebia.json": "requirements_catalog.schema.json",
    "data/remote_migrations.json": "remote_migrations.schema.json",
}


class SchemaStore:
    def __init__(self) -> None:
        schema_dir = files("wikidebia_validator").joinpath("schemas")
        self.schemas: dict[str, dict[str, Any]] = {}
        for item in schema_dir.iterdir():
            if item.name.endswith(".schema.json"):
                doc = json.loads(item.read_text(encoding="utf-8"))
                self.schemas[item.name] = doc
        pairs = [(name, Resource.from_contents(doc)) for name, doc in self.schemas.items()]
        self.registry = Registry().with_resources(pairs)
        self.format_checker = FormatChecker()

    def validate(self, instance: Any, schema_name: str) -> list[Any]:
        schema = self.schemas[schema_name]
        cls = validator_for(schema)
        cls.check_schema(schema)
        validator = cls(schema, registry=self.registry, format_checker=self.format_checker)
        return sorted(validator.iter_errors(instance), key=lambda e: (list(e.absolute_path), e.message))


def pointer(path: Any) -> str:
    parts = []
    for part in path:
        s = str(part).replace("~", "~0").replace("/", "~1")
        parts.append(s)
    return "/" + "/".join(parts) if parts else "/"


def _historical_classification_ids(ctx: PackageContext, language: str) -> set[str]:
    """Find historical arguments, including the import stage before page manifests."""
    historical: set[str] = set()
    provenance_path = "data/import_provenance.json"
    provenance = ctx.load_json(provenance_path) if ctx.exists(provenance_path) else None
    if isinstance(provenance, dict) and provenance.get("schema") == "wikidebia-import-provenance-1.0":
        for row in provenance.get("pages") or []:
            if not isinstance(row, dict) or row.get("kind") != "argument":
                continue
            node_id, path = row.get("page_id"), row.get("import_path")
            revision = row.get("revision_id")
            if (isinstance(node_id, str) and isinstance(path, str)
                    and path.startswith("imports/fr/arguments/")
                    and type(revision) is int and revision > 0
                    and isinstance(row.get("sha256"), str)
                    and ctx.sha256(path) == row["sha256"]):
                historical.add(node_id)
    for row in (ctx.manifest() or {}).get("pages") or []:
        if not isinstance(row, dict) or row.get("page_type") != "argument" or row.get("language") != language:
            continue
        node_id = row.get("page_id")
        if not isinstance(node_id, str):
            continue
        if row.get("page_origin") == "preexisting" or (language == "en" and row.get("source_page_origin") == "preexisting"):
            historical.add(node_id)
        elif language == "fr" and row.get("page_origin") == "new":
            historical.discard(node_id)
    return historical


def _historical_classification_count(ctx: PackageContext, schema_name: str, instance: Any, err: Any) -> bool:
    # Only cardinality is contextual. Enum, uniqueness, types and all other
    # schema constraints remain mandatory, including for historical pages.
    if err.validator != "maxItems" or err.validator_value != 4:
        return False
    path = list(err.absolute_path)
    if schema_name == "argument_registry.schema.json" and path[:2] == ["graph", "nodes"]:
        path = path[1:]
        graph = instance.get("graph") or {}
    elif schema_name == "argument_graph.schema.json":
        graph = instance
    else:
        return False
    if len(path) != 4 or path[0] != "nodes" or not isinstance(path[1], int):
        return False
    language, field = path[2:]
    if (language, field) not in {("fr", "rubriques"), ("en", "sections")}:
        return False
    node = graph["nodes"][path[1]]
    return node.get("id") in _historical_classification_ids(ctx, language)


def _valid_translation_source_preservation(ctx: PackageContext) -> bool:
    rel = "data/source_preservation_receipt.json"
    if not ctx.exists(rel):
        return False
    receipt = ctx.load_json(rel)
    if not isinstance(receipt, dict) or receipt.get("schema") != "wikidebia-translation-source-preservation-1.0":
        return False
    body = dict(receipt)
    digest = body.pop("receipt_sha256", None)
    actual = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if digest != actual or receipt.get("policy") != "published-french-import-preserved-for-translation-1.0":
        return False
    pages = receipt.get("pages")
    if not isinstance(pages, list) or not pages:
        return False
    for page in pages:
        path = page.get("import_path")
        if type(page.get("revision_id")) is not int or page["revision_id"] <= 0 or not isinstance(path, str) or not path.startswith("imports/fr/") or ".." in Path(path).parts or ctx.sha256(path) != page.get("sha256"):
            return False
    for rel in ("data/fr_content_lock.json", "data/fr_page_metadata_lock.json"):
        if not ctx.exists(rel) or (ctx.load_json(rel) or {}).get("source_preservation_receipt_sha256") != digest:
            return False
    return True


def _title_checkpoint_preserves_empty_classification(
    ctx: PackageContext, node_id: str, field: str, value: Any
) -> bool:
    """Accept a proven historical empty field during the title-only checkpoint.

    The first French checkpoint deliberately locks graph structure and titles
    before rubrics and keywords are reviewed.  An imported page whose source
    truly omitted one of those fields must therefore remain representable until
    the content/classification review fills it.  The exception is tied to the
    signed local review/lock pair and to the exact imported wikicode.
    """
    if field not in {"rubriques", "keywords"} or value != []:
        return False
    lock_rel = "data/fr_page_metadata_lock.json"
    review_rel = "reviews/fr/page_metadata_review.json"
    provenance_rel = "data/import_provenance.json"
    if not all(ctx.exists(rel) for rel in (lock_rel, review_rel, provenance_rel)):
        return False
    lock = ctx.load_json(lock_rel)
    review = ctx.load_json(review_rel)
    provenance = ctx.load_json(provenance_rel)
    if not isinstance(lock, dict) or lock.get("schema") != "wikidebia-fr-page-metadata-lock-1.0":
        return False
    if not isinstance(review, dict) or review.get("review_scope") != "graph_and_titles" or review.get("status") != "approved":
        return False
    if not isinstance(provenance, dict) or provenance.get("schema") != "wikidebia-import-provenance-1.0":
        return False
    review_sha = review.get("review_sha256")
    review_body = dict(review)
    review_body.pop("review_sha256", None)
    computed_review_sha = hashlib.sha256(
        json.dumps(
            review_body,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    if (
        not isinstance(review_sha, str)
        or review_sha != computed_review_sha
        or lock.get("review_sha256") != review_sha
    ):
        return False
    locked = next(
        (row for row in lock.get("arguments") or [] if isinstance(row, dict) and row.get("entity_id") == node_id),
        None,
    )
    if not locked or locked.get("page_origin") != "preexisting" or locked.get(field) != []:
        return False
    if (locked.get("decisions") or {}).get(field) != "deferred_to_content_review":
        return False
    if (locked.get("attestations") or {}).get("classification_review_deferred") is not True:
        return False
    page = next(
        (
            row for row in provenance.get("pages") or []
            if isinstance(row, dict) and row.get("kind") == "argument" and row.get("page_id") == node_id
        ),
        None,
    )
    if not page:
        return False
    path = page.get("import_path")
    if (
        not isinstance(path, str)
        or not path.startswith("imports/fr/arguments/")
        or ".." in Path(path).parts
        or type(page.get("revision_id")) is not int
        or page["revision_id"] <= 0
        or ctx.sha256(path) != page.get("sha256")
    ):
        return False
    from .wikicode import parse_template
    try:
        # The import hash was verified immediately above.  Read it without the
        # generated-file newline policy: historical wiki revisions are immutable
        # evidence and may legitimately lack a trailing newline.
        template = parse_template((ctx.root / path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return False
    parameter = "rubriques" if field == "rubriques" else "mots-clés"
    return not (template.one(parameter) or "").strip()


def _preserved_keyword_duplicates(ctx: PackageContext, schema_name: str, instance: Any, err: Any) -> bool:
    if err.validator not in {"uniqueItems", "minItems"}:
        return False
    path = list(err.absolute_path)
    if schema_name == "argument_registry.schema.json" and path[:2] == ["graph", "nodes"]:
        path = path[1:]; graph = instance.get("graph") or {}
    elif schema_name == "argument_graph.schema.json":
        graph = instance
    else:
        return False
    if len(path) != 4 or path[0] != "nodes" or tuple(path[2:]) not in {("fr", "keywords"), ("en", "keywords")}:
        return False
    node = graph["nodes"][path[1]]; node_id = node.get("id")
    if (
        err.validator == "minItems"
        and path[2] == "fr"
        and _title_checkpoint_preserves_empty_classification(
            ctx, str(node_id), "keywords", node.get("fr", {}).get("keywords")
        )
    ):
        return True
    if not _valid_translation_source_preservation(ctx):
        return False
    if node_id not in _historical_classification_ids(ctx, "fr"):
        return False
    provenance = ctx.load_json("data/import_provenance.json") or {}
    source = next((r for r in provenance.get("pages") or [] if r.get("page_id") == node_id), None)
    if not source or not ctx.exists("data/keyword_vocabulary_bilingual.json"):
        return False
    from .wikicode import parse_template
    try:
        original = parse_template(ctx.read_text(source["import_path"]) or "").one("mots-clés") or ""
    except ValueError:
        return False
    french = [v.strip() for v in original.split(",") if v.strip()]
    entries = (ctx.load_json("data/keyword_vocabulary_bilingual.json") or {}).get("entries") or []
    mapping = {r.get("fr"): r.get("en") for r in entries}
    if any(v not in mapping for v in french):
        return False
    if err.validator == "minItems":
        return not french and node.get(path[2], {}).get("keywords") == []
    if len(french) == len(set(french)):
        return False
    expected = [mapping[v] for v in french]
    # Duplicates must have exactly the same positions; distinct FR concepts
    # must not have been accidentally collapsed onto one English keyword.
    return len(set(expected)) == len(set(french)) and node.get(path[2], {}).get("keywords") == (expected if path[2] == "en" else french)


def validate_instance(ctx: PackageContext, store: SchemaStore, rel: str, schema_name: str, instance: Any | None = None) -> None:
    if instance is None:
        instance = ctx.load_json(rel)
    if instance is None:
        return
    try:
        errors = store.validate(instance, schema_name)
    except Exception as exc:
        ctx.report.error("WDV-SCH-002", f"Impossible d'appliquer {schema_name} : {exc}", path=rel)
        return
    for err in errors:
        if _historical_classification_count(ctx, schema_name, instance, err) or _preserved_keyword_duplicates(ctx, schema_name, instance, err) or _preserved_empty_rubrics(ctx, schema_name, instance, err):
            continue
        ctx.report.error("WDV-SCH-003", err.message, path=rel, pointer=pointer(err.absolute_path), details={"schema": schema_name})


def _preserved_empty_rubrics(ctx: PackageContext, schema_name: str, instance: Any, err: Any) -> bool:
    if err.validator != 'minItems':
        return False
    path = list(err.absolute_path)
    if schema_name == 'argument_registry.schema.json' and path[:2] == ['graph', 'nodes']:
        path = path[1:]; graph = instance.get('graph') or {}
    elif schema_name == 'argument_graph.schema.json':
        graph = instance
    else:
        return False
    if len(path) != 4 or path[0] != 'nodes' or path[2:] != ['fr', 'rubriques']:
        return False
    node = graph['nodes'][path[1]]
    if _title_checkpoint_preserves_empty_classification(
        ctx, str(node.get('id')), 'rubriques', node.get('fr', {}).get('rubriques')
    ):
        return True
    if not _valid_translation_source_preservation(ctx):
        return False
    receipt = ctx.load_json('data/source_preservation_receipt.json') or {}
    row = next((r for r in receipt['pages'] if r.get('page_id') == node.get('id')), None)
    if not row:
        return False
    from .wikicode import parse_template
    try:
        template = parse_template(ctx.read_text(row['import_path']) or '')
        return not (template.one('rubriques') or '').strip() and node.get('fr', {}).get('rubriques') == []
    except ValueError:
        return False


def validate_all_schemas(ctx: PackageContext, store: SchemaStore) -> None:
    manifest = ctx.manifest()
    core = ctx.core_paths()
    mapping = dict(SCHEMA_BY_PATH)
    mapping[core["scope"]] = "scope.schema.json"
    mapping[core["registry"]] = "argument_registry.schema.json"
    mapping[core["graph_json"]] = "argument_graph.schema.json"
    mapping[core["sources"]] = "source_registry.schema.json"
    for rel, schema in mapping.items():
        if ctx.exists(rel):
            validate_instance(ctx, store, rel, schema)
    controls = (manifest or {}).get("editorial_controls") or {}
    for path_key, schema_name in (
        ("keyword_vocabulary_path", "keyword_vocabulary.schema.json"),
        ("summary_style_review_path", "summary_style_review.schema.json"),
        ("manual_remote_adoption_path", "manual_remote_adoptions.schema.json"),
        ("argument_name_assignment_path", "argument_name_assignments.schema.json"),
        ("argument_name_discovery_path", "argument_name_discovery_review.schema.json"),
        ("documentary_resource_registry_path", "documentary_resource_registry.schema.json"),
        ("semantic_convergence_review_path", "semantic_convergence_review.schema.json"),
    ):
        rel = controls.get(path_key)
        if rel and ctx.exists(rel):
            validate_instance(ctx, store, rel, schema_name)
    preservation = controls.get("legacy_content_preservation") or {}
    if preservation.get("enabled") is True:
        rel = preservation.get("lock_path")
        if rel and ctx.exists(rel):
            validate_instance(ctx, store, rel, "historical_content_lock.schema.json")
    if manifest:
        for i, page in enumerate(manifest.get("pages", [])):
            validate_instance(ctx, store, "manifest.json", "page_manifest.schema.json", page)
        for batch in manifest.get("batches", []):
            validate_instance(ctx, store, "manifest.json", "batch_manifest.schema.json", batch)
    for path in sorted(ctx.iter_files("manifests/pages/**/*.json")):
        validate_instance(ctx, store, ctx.relative(path), "page_manifest.schema.json")
    for path in sorted(ctx.iter_files("manifests/batches/**/*.json")):
        validate_instance(ctx, store, ctx.relative(path), "batch_manifest.schema.json")
    for path in sorted(ctx.iter_files("handoff/*.json")):
        validate_instance(ctx, store, ctx.relative(path), "handoff.schema.json")
    for path in sorted(ctx.iter_files("**/*receipt*.json")):
        rel = ctx.relative(path)
        if rel == "data/source_preservation_receipt.json":
            validate_instance(ctx, store, rel, "translation_source_preservation.schema.json")
            if not _valid_translation_source_preservation(ctx):
                ctx.report.error("WDV-SCH-003", "Reçu de préservation de source divergent des imports ou verrous français", path=rel)
        else:
            validate_instance(ctx, store, rel, "archive_receipt.schema.json")
    for path in sorted(ctx.iter_files("logs/*.jsonl")):
        rel = ctx.relative(path)
        for line_no, obj in ctx.load_jsonl(rel):
            before = len(ctx.report.findings)
            validate_instance(ctx, store, rel, "operation_log_entry.schema.json", obj)
            for finding in ctx.report.findings[before:]:
                if finding.pointer:
                    object.__setattr__(finding, "pointer", f"ligne {line_no}{finding.pointer}")
