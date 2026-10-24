from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict, deque
from typing import Any

from .package import PackageContext



CONTEXTUAL_TITLE_PATTERNS = {
    "fr": {
        "initial": re.compile(r"^(?:(?:Il|Elle|Ils|Elles|Cela|Ceci|Ça|Celui(?:-ci|-là)?|Celle(?:-ci|-là)?)\b|(?:Ce|Cet|Cette|Ces)\s+(?!(?:que|qui|dont)\b)[a-zà-öø-ÿ][\w'’-]*)", re.I),
        "internal": re.compile(r"\b(?:ce|cet|cette|ces)\s+(?:protocole|projet|programme|étude|expérience|méthode|résultats?|dispositif|institution|théorie|modèle|analyse|essai|article|ouvrage|rapport)\b", re.I),
    },
    "en": {
        "initial": re.compile(r"^(?:(?:It|They)\b|(?:This|That|These|Those)\s+(?!(?:which|that)\b)[a-z][\w'-]*)", re.I),
        "internal": re.compile(r"\b(?:this|that|these|those)\s+(?:protocol|project|program|study|experiment|method|results?|findings?|device|institution|theory|model|analysis|trial|article|book|report)\b", re.I),
    },
}


def contextual_title_issues(title: str, language: str, revision: str | None = None) -> list[str]:
    """Return issues under the current cumulative title policy.

    ``revision`` is accepted for backward API compatibility but is deliberately
    ignored: editorial rules no longer switch on normative revision.
    """
    value = title or ""
    patterns = CONTEXTUAL_TITLE_PATTERNS.get(language) or {}
    issues: list[str] = []
    initial_match = patterns.get("initial") and patterns["initial"].search(value)
    if initial_match:
        # Impersonal / extraposition constructions do not contain an anaphoric
        # referent.  Keep this narrow: an English "It ..." is exempt only when
        # the grammatical subject is supplied by a following infinitival or
        # finite clause (for X to..., to..., that...).
        impersonal_fr = language == "fr" and re.match(
            r"^(?:Il\s+(?:existe|n['’]existe|(?:ne\s+)?faut|y\s+a|n['’]y\s+a|est|n['’]est|ne\s+devrait|reste)|Ce\s+(?:qu['’]|n['’]est))",
            value, re.I,
        )
        impersonal_en = language == "en" and (
            re.match(
                r"^It\s+(?:(?:is|was|will\s+be|would\s+be|can\s+be|could\s+be|should\s+be|must\s+be)\s+[^,;:!?]{0,100}?\s+for\s+[^,;:!?]{1,80}?\s+to\b)",
                value, re.I,
            )
            or re.match(
                r"^It\s+(?:(?:is|was|will\s+be|would\s+be|can\s+be|could\s+be|should\s+be|must\s+be)\s+(?:(?:entirely|perfectly|quite|fully)\s+)?(?:necessary|important|essential|possible|impossible|fair|unfair|right|wrong|reasonable|unreasonable|better|worse)\s+(?:to|that)\b)",
                value, re.I,
            )
        )
        if not (impersonal_fr or impersonal_en):
            issues.append("initial_contextual_referent")
    # Internal demonstratives remain a review signal. They are not automatically
    # blocking, but the title must explicitly name the referent or document the
    # contextual shortening in its page-level review.
    internal_match = patterns.get("internal") and patterns["internal"].search(value)
    if internal_match and not initial_match:
        issues.append("possible_contextual_referent")
    return issues


STATE_ORDER = [
    "initialized", "graph_draft", "graph_validated", "graph_locked", "fr_debate_validated",
    "fr_arguments_in_progress", "fr_content_complete", "fr_validated", "en_titles_locked",
    "en_debate_validated", "en_arguments_in_progress", "en_content_complete", "en_validated",
    "bilingual_validated", "interlanguage_prepared", "release_ready", "published",
    "interlanguage_applied", "released", "archived",
]


def state_at_least(status: str | None, target: str) -> bool:
    if status in {"migration_required", "blocked"}:
        return False
    try:
        return STATE_ORDER.index(status or "") >= STATE_ORDER.index(target)
    except ValueError:
        return False


def normalized_title(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split()).casefold()


def _duplicates(values: list[str]) -> set[str]:
    c = Counter(values)
    return {v for v, n in c.items() if n > 1}


def active_graph(registry: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    graph = registry.get("graph", {})
    nodes = [n for n in graph.get("nodes", []) if n.get("status") == "active"]
    node_ids = {n.get("id") for n in nodes}
    edges = [e for e in graph.get("edges", []) if e.get("status") == "active"]
    edge_ids = {e.get("id") for e in edges}
    occurrences = [o for o in graph.get("occurrences", []) if o.get("node_id") in node_ids and (o.get("edge_id") is None or o.get("edge_id") in edge_ids)]
    return nodes, edges, occurrences


def compute_derived(registry: dict[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    nodes, edges, occurrences = active_graph(registry)
    node_ids = {n["id"] for n in nodes}
    edge_by_id = {e["id"]: e for e in edges}
    by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for occ in occurrences:
        by_node[occ["node_id"]].append(occ)
    outgoing = Counter(e["parent_node_id"] for e in edges if e["parent_node_id"] in node_ids)
    just = Counter()
    obj = Counter()
    for occ in occurrences:
        edge = edge_by_id.get(occ.get("edge_id"))
        if edge:
            (just if edge.get("relation") == "justification" else obj)[str(occ.get("depth"))] += 1
    per_node: dict[str, dict[str, Any]] = {}
    for node in nodes:
        occs = by_node.get(node["id"], [])
        if not occs:
            continue
        primaries = [o for o in occs if o.get("occurrence_role") == "primary"]
        per_node[node["id"]] = {
            "occurrence_count": len(occs),
            "minimum_depth": min(o["depth"] for o in occs),
            "maximum_depth": max(o["depth"] for o in occs),
            "is_main_argument_anywhere": any(o["depth"] == 1 for o in occs),
            "is_reused": len(occs) >= 2,
            "primary_occurrence_id": primaries[0]["id"] if len(primaries) == 1 else None,
        }
    counts = {
        "main_pro": sum(o.get("depth") == 1 and o.get("branch") == "pro" for o in occurrences),
        "main_con": sum(o.get("depth") == 1 and o.get("branch") == "con" for o in occurrences),
        "justifications_by_depth": dict(sorted(just.items(), key=lambda x: int(x[0]))),
        "objections_by_depth": dict(sorted(obj.items(), key=lambda x: int(x[0]))),
        "distinct_nodes": len(nodes),
        "total_occurrences": len(occurrences),
        "reused_nodes": sum(len(v) >= 2 for v in by_node.values()),
        "additional_reuses": len(occurrences) - len(nodes),
        "developed_nodes": sum(outgoing.get(n["id"], 0) > 0 for n in nodes),
        "leaf_nodes": sum(outgoing.get(n["id"], 0) == 0 for n in nodes),
        "maximum_depth": max((o.get("depth", 0) for o in occurrences), default=0),
    }
    return counts, per_node


def structural_payload(registry: dict[str, Any]) -> dict[str, Any]:
    nodes, edges, occurrences = active_graph(registry)
    payload_nodes = []
    for n in sorted(nodes, key=lambda x: x["id"]):
        fr = n.get("fr", {})
        payload_nodes.append({
            "id": n["id"],
            "canonical_title_fr": unicodedata.normalize("NFC", fr.get("canonical_title", "")),
            "displayed_title_fr": unicodedata.normalize("NFC", fr.get("displayed_title", "")),
        })
    payload_edges = [
        {k: e.get(k) for k in ("id", "parent_node_id", "child_node_id", "relation", "order")}
        for e in sorted(edges, key=lambda x: x["id"])
    ]
    payload_occ = [
        {k: o.get(k) for k in ("id", "node_id", "parent_occurrence_id", "edge_id", "branch", "depth", "order", "occurrence_role", "render_children")}
        for o in sorted(occurrences, key=lambda x: x["id"])
    ]
    return {"nodes": payload_nodes, "edges": payload_edges, "occurrences": payload_occ}


def structural_sha256(registry: dict[str, Any]) -> str:
    payload = structural_payload(registry)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _canonical_referent_manually_verified(ctx: PackageContext, node_id: str, language: str) -> bool:
    controls=((ctx.manifest() or {}).get('editorial_controls') or {})
    rel=controls.get('individual_review_path')
    if not isinstance(rel,str) or not ctx.exists(rel): return False
    data=ctx.load_json(rel)
    if not isinstance(data,dict): return False
    row=next((e for e in data.get('entries') or [] if isinstance(e,dict) and str(e.get('id'))==str(node_id)),None)
    return isinstance(row,dict) and row.get(f'canonical_referents_explicit_{language}') is True


def _locked_preexisting_displayed_title(
    ctx: PackageContext, node_id: str, language: str, value: Any
) -> bool:
    """Return whether the French metadata lock proves exact historical preservation."""
    if language != "fr" or not ctx.exists("data/fr_page_metadata_lock.json"):
        return False
    lock = ctx.load_json("data/fr_page_metadata_lock.json")
    if not isinstance(lock, dict) or lock.get("schema") != "wikidebia-fr-page-metadata-lock-1.0":
        return False
    row = next(
        (
            entry for entry in lock.get("arguments") or []
            if isinstance(entry, dict) and str(entry.get("entity_id")) == str(node_id)
        ),
        None,
    )
    return bool(
        row
        and row.get("page_origin") == "preexisting"
        and (row.get("decisions") or {}).get("displayed_title") == "keep"
        and row.get("displayed_title") == value
    )

def validate_graph(ctx: PackageContext) -> None:
    registry = ctx.registry()
    if not registry:
        return
    manifest = ctx.manifest() or {}
    status = manifest.get("global_status")
    strict = state_at_least(status, "graph_validated") or registry.get("graph", {}).get("lifecycle", {}).get("status") in {"validated", "locked"}
    graph = registry.get("graph") or {}
    nodes_all = graph.get("nodes", [])
    edges_all = graph.get("edges", [])
    occ_all = graph.get("occurrences", [])

    for label, items in (("nœud", nodes_all), ("relation", edges_all), ("occurrence", occ_all)):
        ids = [x.get("id") for x in items if isinstance(x, dict)]
        for dup in sorted(_duplicates(ids)):
            ctx.report.error("WDV-GRA-001", f"Identifiant de {label} dupliqué : {dup}", path=ctx.core_paths()["registry"])

    nodes, edges, occurrences = active_graph(registry)
    node_by_id = {n.get("id"): n for n in nodes}
    edge_by_id = {e.get("id"): e for e in edges}
    occ_by_id = {o.get("id"): o for o in occurrences}

    title_policy_locked = {
        "fr": ctx.exists("data/fr_page_metadata_lock.json"),
        "en": ctx.exists("data/en_page_metadata_lock.json"),
    }
    for lang in ("fr", "en"):
        seen: dict[str, str] = {}
        title_reporter = ctx.report.error if title_policy_locked[lang] else ctx.report.warning
        debate_title = (((registry.get("debate") or {}).get("pages") or {}).get(lang) or {}).get("canonical_title")
        if debate_title and (debate_title.endswith(".") or any(ch in debate_title for ch in "’‘ʼ＇")):
            title_reporter(
                "WDV-GRA-016",
                f"Titre de débat {lang} non conforme : {debate_title}",
                path=ctx.core_paths()["registry"],
                pointer=f"/debate/pages/{lang}/canonical_title",
                details={"deferred_until_metadata_lock": not title_policy_locked[lang]},
            )
        for node in nodes:
            language_data = node.get(lang) or {}
            title = language_data.get("canonical_title")
            displayed_title = language_data.get("displayed_title")
            for field_name, field_value in (("canonical_title", title), ("displayed_title", displayed_title)):
                if field_value and (field_value.endswith(".") or any(ch in field_value for ch in "’‘ʼ＇")):
                    if field_name == "displayed_title" and _locked_preexisting_displayed_title(
                        ctx, str(node.get("id")), lang, field_value
                    ):
                        continue
                    title_reporter(
                        "WDV-GRA-016",
                        f"Titre {lang} non conforme : {field_value}",
                        path=ctx.core_paths()["registry"],
                        pointer=f"/graph/nodes/{node.get('id')}/{lang}/{field_name}",
                        details={"deferred_until_metadata_lock": not title_policy_locked[lang], "title_field": field_name},
                    )
            if not title:
                continue
            contextual = contextual_title_issues(title, lang)
            details = {
                "node_id": node.get("id"),
                "language": lang,
                "issues": contextual,
                "deferred_until_metadata_lock": not title_policy_locked[lang],
            }
            manual_referent_ok = _canonical_referent_manually_verified(ctx, str(node.get('id')), lang)
            if ("implicit_referent" in contextual or "initial_contextual_referent" in contextual) and not manual_referent_ok:
                title_reporter(
                    "WDV-EDT-016",
                    f"Titre {lang} non autonome : le référent initial dépend du contexte extérieur : {title}",
                    path=ctx.core_paths()["registry"],
                    pointer=f"/graph/nodes/{node.get('id')}/{lang}/canonical_title",
                    details=details,
                )
            elif "possible_contextual_referent" in contextual and not manual_referent_ok:
                ctx.report.warning("WDV-EDT-016", f"Titre {lang} à vérifier : un démonstratif interne peut dépendre du contexte extérieur : {title}", path=ctx.core_paths()["registry"], pointer=f"/graph/nodes/{node.get('id')}/{lang}/canonical_title", details=details)
            key = normalized_title(title)
            if key in seen and seen[key] != node.get("id"):
                ctx.report.error("WDV-GRA-002", f"Collision de titre canonique {lang} entre {seen[key]} et {node.get('id')} : {title}", path=ctx.core_paths()["registry"])
            seen[key] = node.get("id")

    relation_keys: set[tuple[Any, ...]] = set()
    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        p, c = edge.get("parent_node_id"), edge.get("child_node_id")
        if p not in node_by_id or c not in node_by_id:
            ctx.report.error("WDV-GRA-003", f"Relation {edge.get('id')} vers un nœud inexistant", path=ctx.core_paths()["registry"])
            continue
        if p == c:
            ctx.report.error("WDV-GRA-006", f"Auto-relation {edge.get('id')} sur {p}", path=ctx.core_paths()["registry"])
        key = (p, c, edge.get("relation"))
        if key in relation_keys:
            ctx.report.error("WDV-GRA-007", f"Relation directe dupliquée : {p} -> {c} ({edge.get('relation')})", path=ctx.core_paths()["registry"])
        relation_keys.add(key)
        outgoing[p].append(c)

    # Cycle detection on the active node graph.
    colors: dict[str, int] = {node_id: 0 for node_id in node_by_id}
    stack: list[str] = []
    def visit(node_id: str) -> None:
        colors[node_id] = 1
        stack.append(node_id)
        for child in outgoing.get(node_id, []):
            if colors.get(child) == 0:
                visit(child)
            elif colors.get(child) == 1:
                start = stack.index(child) if child in stack else 0
                cycle = stack[start:] + [child]
                ctx.report.error("WDV-GRA-005", "Cycle détecté : " + " -> ".join(cycle), path=ctx.core_paths()["registry"])
        stack.pop()
        colors[node_id] = 2
    for node_id in sorted(node_by_id):
        if colors[node_id] == 0:
            visit(node_id)

    children_by_occ: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for occ in occurrences:
        parent_id = occ.get("parent_occurrence_id")
        if parent_id is not None:
            children_by_occ[parent_id].append(occ)

    for occ in occurrences:
        oid = occ.get("id")
        node_id = occ.get("node_id")
        if node_id not in node_by_id:
            ctx.report.error("WDV-GRA-003", f"Occurrence {oid} vers un nœud inexistant : {node_id}", path=ctx.core_paths()["registry"])
            continue
        parent_id = occ.get("parent_occurrence_id")
        edge_id = occ.get("edge_id")
        depth = occ.get("depth")
        if depth == 1:
            if parent_id is not None or edge_id is not None or occ.get("occurrence_role") != "primary":
                ctx.report.error("WDV-GRA-009", f"Occurrence principale de niveau 1 incohérente : {oid}", path=ctx.core_paths()["registry"])
        else:
            parent = occ_by_id.get(parent_id)
            edge = edge_by_id.get(edge_id)
            if parent is None or edge is None:
                ctx.report.error("WDV-GRA-004", f"Occurrence {oid} référence un parent ou une relation inexistant", path=ctx.core_paths()["registry"])
                continue
            if depth != parent.get("depth", 0) + 1 or occ.get("branch") != parent.get("branch"):
                ctx.report.error("WDV-GRA-009", f"Profondeur ou branche incohérente pour {oid}", path=ctx.core_paths()["registry"], details={"declared_depth": depth, "parent_depth": parent.get("depth")})
            if edge.get("parent_node_id") != parent.get("node_id") or edge.get("child_node_id") != node_id:
                ctx.report.error("WDV-GRA-008", f"Occurrence {oid} incohérente avec la relation {edge_id}", path=ctx.core_paths()["registry"])
        if occ.get("occurrence_role") == "secondary" and (occ.get("render_children") or children_by_occ.get(oid)):
            ctx.report.error("WDV-GRA-011", f"Occurrence secondaire développée : {oid}", path=ctx.core_paths()["registry"])
        if occ.get("render_children") is False and children_by_occ.get(oid):
            ctx.report.error("WDV-GRA-011", f"Occurrence marquée sans enfants mais possédant des enfants : {oid}", path=ctx.core_paths()["registry"])

    roots = [o for o in occurrences if o.get("depth") == 1]
    if strict and (not any(o.get("branch") == "pro" for o in roots) or not any(o.get("branch") == "con" for o in roots)):
        ctx.report.error("WDV-GRA-017", "Le graphe validé doit contenir au moins un argument principal dans chaque branche", path=ctx.core_paths()["registry"])

    by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for occ in occurrences:
        by_node[occ.get("node_id")].append(occ)
    for node_id in node_by_id:
        occs = by_node.get(node_id, [])
        if not occs:
            (ctx.report.error if strict else ctx.report.warning)("WDV-GRA-012", f"Nœud actif sans occurrence : {node_id}", path=ctx.core_paths()["registry"])
            continue
        primaries = [o for o in occs if o.get("occurrence_role") == "primary"]
        if len(primaries) != 1:
            (ctx.report.error if strict else ctx.report.warning)("WDV-GRA-010", f"{node_id} possède {len(primaries)} occurrence(s) primaire(s), une seule requise", path=ctx.core_paths()["registry"])

    # Each active edge must be represented by at least one occurrence.
    used_edges = Counter(o.get("edge_id") for o in occurrences if o.get("edge_id"))
    for edge_id in edge_by_id:
        if used_edges[edge_id] == 0:
            (ctx.report.error if strict else ctx.report.warning)("WDV-GRA-008", f"Relation active sans occurrence : {edge_id}", path=ctx.core_paths()["registry"])

    counts, per_node = compute_derived(registry)
    declared = graph.get("derived_counts") or {}
    if declared != counts:
        (ctx.report.error if strict else ctx.report.warning)("WDV-GRA-013", "Les compteurs dérivés ne correspondent pas au recalcul", path=ctx.core_paths()["registry"], details={"declared": declared, "computed": counts})
    for node in nodes:
        expected = per_node.get(node["id"])
        declared_node = node.get("derived")
        if strict and declared_node is None:
            ctx.report.error("WDV-GRA-013", f"Bloc derived absent pour le nœud validé {node['id']}", path=ctx.core_paths()["registry"])
        elif declared_node is not None and expected != declared_node:
            (ctx.report.error if strict else ctx.report.warning)("WDV-GRA-013", f"Données dérivées incorrectes pour {node['id']}", path=ctx.core_paths()["registry"], details={"declared": declared_node, "computed": expected})

    policy = graph.get("depth_policy") or {}
    observed = counts["maximum_depth"]
    if policy.get("maximum_observed") != observed:
        (ctx.report.error if strict else ctx.report.warning)("WDV-GRA-013", "maximum_observed incorrect", path=ctx.core_paths()["registry"], details={"declared": policy.get("maximum_observed"), "computed": observed})
    limit_policy = policy.get("limit_policy")
    if limit_policy == "bounded":
        maximum_edge_depth = policy.get("maximum_edge_depth")
        frontier_node_ids = policy.get("frontier_node_ids")
        omitted = policy.get("relations_omitted_at_frontier")
        if not isinstance(maximum_edge_depth, int) or isinstance(maximum_edge_depth, bool):
            ctx.report.error("WDV-GRA-009", "La profondeur maximale en arêtes est absente ou invalide", path=ctx.core_paths()["registry"])
        elif observed > maximum_edge_depth + 1:
            ctx.report.error(
                "WDV-GRA-009",
                "Une occurrence dépasse la limite de profondeur déclarée",
                path=ctx.core_paths()["registry"],
                details={"maximum_observed": observed, "maximum_edge_depth": maximum_edge_depth},
            )
        if not isinstance(frontier_node_ids, list) or not frontier_node_ids:
            ctx.report.error("WDV-GRA-009", "Une politique bornée doit déclarer ses nœuds de frontière", path=ctx.core_paths()["registry"])
        else:
            unknown_frontiers = sorted(set(frontier_node_ids) - set(node_by_id))
            if unknown_frontiers:
                ctx.report.error(
                    "WDV-GRA-009",
                    "La frontière de profondeur référence des nœuds inexistants",
                    path=ctx.core_paths()["registry"],
                    details={"unknown_frontier_node_ids": unknown_frontiers},
                )
            if isinstance(maximum_edge_depth, int) and not isinstance(maximum_edge_depth, bool):
                expected_depth = maximum_edge_depth + 1
                wrong_depth = sorted(
                    node_id
                    for node_id in set(frontier_node_ids) & set(node_by_id)
                    if not any(occ.get("depth") == expected_depth for occ in by_node.get(node_id, []))
                )
                if wrong_depth:
                    ctx.report.error(
                        "WDV-GRA-009",
                        "Des nœuds de frontière ne se trouvent pas au niveau correspondant à la limite",
                        path=ctx.core_paths()["registry"],
                        details={"expected_depth": expected_depth, "frontier_node_ids": wrong_depth},
                    )
        if not isinstance(omitted, int) or isinstance(omitted, bool) or omitted < 1:
            ctx.report.error(
                "WDV-GRA-009",
                "Une politique bornée doit comptabiliser les relations omises à la frontière",
                path=ctx.core_paths()["registry"],
                details={"relations_omitted_at_frontier": omitted},
            )
    elif limit_policy == "unbounded":
        bounded_fields = [
            key
            for key in ("maximum_edge_depth", "frontier_node_ids", "relations_omitted_at_frontier")
            if key in policy
        ]
        if bounded_fields:
            ctx.report.error(
                "WDV-GRA-009",
                "Une politique non limitée ne peut pas déclarer de frontière de profondeur",
                path=ctx.core_paths()["registry"],
                details={"bounded_fields": bounded_fields},
            )
    else:
        ctx.report.error("WDV-GRA-009", "Politique de profondeur inconnue", path=ctx.core_paths()["registry"], details={"limit_policy": limit_policy})
    legacy_fields = [key for key in ("normal_target", "declared_maximum", "exception_reason") if key in policy]
    if legacy_fields:
        ctx.report.error("WDV-GRA-009", "Les champs historiques de limitation de profondeur sont interdits par la politique courante", path=ctx.core_paths()["registry"], details={"legacy_fields": legacy_fields})

    lifecycle = graph.get("lifecycle") or {}
    declared_hash = lifecycle.get("structural_sha256")
    computed_hash = structural_sha256(registry)
    if declared_hash and declared_hash != computed_hash:
        ctx.report.error("WDV-GRA-015", "Empreinte structurelle incorrecte", path=ctx.core_paths()["registry"], details={"declared": declared_hash, "computed": computed_hash})
    if lifecycle.get("status") == "locked" and not declared_hash:
        ctx.report.error("WDV-GRA-015", "Un graphe verrouillé doit posséder une empreinte structurelle", path=ctx.core_paths()["registry"])

    projection = ctx.graph_projection()
    if projection:
        projection_graph = {k: projection.get(k) for k in ("lifecycle", "depth_policy", "nodes", "edges", "occurrences", "derived_counts")}
        registry_graph = {k: graph.get(k) for k in ("lifecycle", "depth_policy", "nodes", "edges", "occurrences", "derived_counts")}
        if projection_graph != registry_graph:
            ctx.report.error("WDV-GRA-014", "La projection du graphe diverge du registre maître", path=ctx.core_paths()["graph_json"])
        debate_id = (registry.get("debate") or {}).get("id")
        if (projection.get("debate") or {}).get("id") != debate_id:
            ctx.report.error("WDV-GRA-014", "L'identifiant du débat diffère dans la projection", path=ctx.core_paths()["graph_json"])

    ctx.report.metrics["graph"] = counts
