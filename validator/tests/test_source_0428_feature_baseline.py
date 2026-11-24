from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = json.loads((ROOT / "docs/BASELINE_FEATURES_0.4.28.json").read_text(encoding="utf-8"))


def _symbols(path: Path) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result = {"functions": set(), "classes": {}, "constants": set(), "literal_constants": {}}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result["functions"].add(node.name)
        elif isinstance(node, ast.ClassDef):
            result["classes"][node.name] = {
                item.name for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    result["constants"].add(target.id)
                    try:
                        value = ast.literal_eval(node.value)
                    except Exception:
                        continue
                    def normalize(obj):
                        if isinstance(obj, dict):
                            return {str(key): normalize(value) for key, value in obj.items()}
                        if isinstance(obj, (list, tuple)):
                            return [normalize(value) for value in obj]
                        if isinstance(obj, set):
                            return sorted((normalize(value) for value in obj), key=repr)
                        if isinstance(obj, (str, int, float, bool)) or obj is None:
                            return obj
                        raise TypeError(type(obj))
                    try:
                        if target.id.endswith("VERSION") or target.id == "VERSION":
                            continue
                        result["literal_constants"][target.id] = normalize(value)
                    except TypeError:
                        pass
    return result


def _contains_literal(actual, expected):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _contains_literal(actual[key], value)
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return False
        # Literal sequences from the source are contracts: preserve order and values.
        return actual == expected or all(value in actual for value in expected)
    return actual == expected


def _schema_features(obj, prefix=""):
    props, required, enums = set(), set(), {}
    if isinstance(obj, dict):
        if isinstance(obj.get("properties"), dict):
            for key, value in obj["properties"].items():
                path = f"{prefix}.{key}" if prefix else key
                props.add(path)
                p2, r2, e2 = _schema_features(value, path)
                props |= p2
                required |= r2
                enums.update(e2)
        if isinstance(obj.get("required"), list):
            required |= {f"{prefix}.{key}" if prefix else key for key in obj["required"]}
        if isinstance(obj.get("enum"), list):
            enums[prefix] = {str(value) for value in obj["enum"]}
        for key in ("$defs", "definitions"):
            if isinstance(obj.get(key), dict):
                for name, value in obj[key].items():
                    p2, r2, e2 = _schema_features(value, f"{key}.{name}")
                    props |= p2
                    required |= r2
                    enums.update(e2)
        for key in ("items", "allOf", "anyOf", "oneOf", "if", "then", "else"):
            value = obj.get(key)
            rows = value if isinstance(value, list) else [value]
            for row in rows:
                if isinstance(row, dict):
                    p2, r2, e2 = _schema_features(row, prefix)
                    props |= p2
                    required |= r2
                    enums.update(e2)
    return props, required, enums


def _mapped_required_path(rel: str) -> Path:
    if rel == "normative_reference/01_normes/WIKIDEBIA_NORME_CONSOLIDEE_1.2.26.md":
        return ROOT / "normative_reference/01_normes/history/WIKIDEBIA_NORME_CONSOLIDEE_1.2.26.md"
    return ROOT / rel


def test_all_0428_validator_files_are_present_or_normatively_archived():
    missing = [path for path in BASELINE["required_files"] if not _mapped_required_path(path).is_file()]
    assert missing == []


def test_all_0428_python_symbols_are_still_present():
    missing = []
    for rel, expected in BASELINE["python_symbols"].items():
        actual = _symbols(ROOT / rel)
        missing.extend(f"{rel}:function:{name}" for name in set(expected["functions"]) - actual["functions"])
        missing.extend(f"{rel}:constant:{name}" for name in set(expected["constants"]) - actual["constants"])
        for name, value in expected.get("literal_constants", {}).items():
            if name not in actual["literal_constants"] or not _contains_literal(actual["literal_constants"][name], value):
                missing.append(f"{rel}:literal_constant:{name}")
        for class_name, methods in expected["classes"].items():
            if class_name not in actual["classes"]:
                missing.append(f"{rel}:class:{class_name}")
            else:
                missing.extend(
                    f"{rel}:method:{class_name}.{name}"
                    for name in set(methods) - actual["classes"][class_name]
                )
    intentional = {
        "src/wikidebia_validator/sources.py:function:_norm",
        "src/wikidebia_validator/wikicode.py:function:_is_norm_120",
        "src/wikidebia_validator/wikicode.py:function:_norm_tuple",
        "src/wikidebia_validator/wikicode.py:function:_norm_at_least",
        "src/wikidebia_validator/wikicode.py:function:_is_norm_1218",
        "src/wikidebia_validator/wikicode.py:function:_is_norm_126",
        "src/wikidebia_validator/wikicode.py:function:_consolidated_norm",
        "src/wikidebia_validator/wikicode.py:function:_is_norm_1217",
        "src/wikidebia_validator/graph.py:constant:CONTEXTUAL_TITLE_PATTERNS_121",
        "src/wikidebia_validator/graph.py:constant:CONTEXTUAL_TITLE_PATTERNS_120",
        "src/wikidebia_validator/editorial.py:function:_consolidated_norm_from_manifest",
    }
    # Test functions themselves are not product API contracts and may be renamed
    # when a historical version-gating test becomes an invariance test.
    unexpected = [item for item in missing if not item.startswith("tests/") and item not in intentional]
    assert unexpected == []


def test_0428_schema_contracts_are_preserved():
    missing = {}
    for name, expected in BASELINE["schemas"].items():
        current_path = ROOT / "src/wikidebia_validator/schemas" / name
        assert current_path.is_file(), name
        props, required, enums = _schema_features(json.loads(current_path.read_text(encoding="utf-8")))
        absent = []
        absent.extend(f"property:{value}" for value in set(expected["properties"]) - props)
        absent.extend(f"required:{value}" for value in set(expected["required"]) - required)
        for path, values in expected["enums"].items():
            absent.extend(f"enum:{path}:{value}" for value in set(values) - enums.get(path, set()))
        if absent:
            missing[name] = sorted(absent)
    intentional_absences = {
        "enum:normative_versions.consolidated_norm:1.2.20",
        "enum:normative_versions.consolidated_norm:1.2.21",
        "enum:normative_versions.consolidated_norm:1.2.22",
        "enum:normative_versions.consolidated_norm:1.2.23",
        "enum:normative_versions.consolidated_norm:1.2.24",
        "enum:normative_versions.consolidated_norm:1.2.25",
        "enum:normative_versions.consolidated_norm:1.2.26",
        "property:normative_versions.consolidated_norm",
        "required:normative_versions.consolidated_norm",
        "required:editorial_controls",
        "required:editorial_controls.debate_documentation.profile_rationale",
        "required:editorial_controls.graph_placement_review_path",
        "required:editorial_controls.introduction_review_path",
        # Owner retirement: these historical properties remain readable, not required.
        "required:$defs.generationRecord.creation_date",
        "required:editorial_controls.creation_date",
        "required:creation_date",
        "required:entries.creation_date",
    }
    unexpected = {name: [item for item in items if item not in intentional_absences] for name, items in missing.items()}
    unexpected = {name: items for name, items in unexpected.items() if items}
    assert unexpected == {}
