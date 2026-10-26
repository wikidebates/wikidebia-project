from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load_module(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


resources = load_module("wikidebia_documentary_resources")


def test_build_file_is_deterministic_and_groups_tracking_url_variants(tmp_path: Path):
    sources = {
        "source_registry_version": "1.0", "debate_id": "d",
        "sources": [
            {"id":"S00001","type":"webliography","language":"en","metadata":{"authors":[],"article":None,"work":None,"volume":None,"issue":None,"location":None,"publisher":None,"place":None,"date":"2024","link":"https://example.org/x?utm_source=a&q=1","page":"Page","site":"Example","title":None},"verification":{"status":"verified","verified_at":None,"primary_source":False,"notes":[]},"usage":[],"deduplication_key":"a"},
            {"id":"S00002","type":"webliography","language":"fr","metadata":{"authors":[],"article":None,"work":None,"volume":None,"issue":None,"location":None,"publisher":None,"place":None,"date":"2024","link":"https://EXAMPLE.org/x?q=1#frag","page":"Page FR","site":"Example","title":None},"verification":{"status":"verified","verified_at":None,"primary_source":False,"notes":[]},"usage":[],"deduplication_key":"b"},
        ]
    }
    source = tmp_path / "sources.json"; out = tmp_path / "resources.json"
    source.write_text(json.dumps(sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    first = resources.build_file(source, out)
    raw1 = out.read_bytes()
    second = resources.build_file(source, out)
    assert raw1 == out.read_bytes()
    assert first == second
    assert len(first["resources"]) == 1
    assert first["resources"][0]["canonical_url"] == "https://example.org/x?q=1"


def test_embedded_short_headline_is_a_compatible_label_variant():
    common = {
        "language": "fr", "verification": {}, "usage": [],
        "deduplication_key": "unused",
    }
    sources = {
        "debate_id": "d",
        "sources": [
            {
                **common, "id": "S00001", "type": "bibliography",
                "metadata": {
                    "authors": ["Amandine Hancewicz"],
                    "article": "Nos vies confinées : « Les femmes accomplissent 70 %, en moyenne, du travail familial et domestique »",
                    "work": "Le Monde", "date": "20/04/2020",
                    "link": "https://example.org/article",
                },
            },
            {
                **common, "id": "S00002", "type": "webliography",
                "metadata": {
                    "authors": ["Amandine Hancewicz"],
                    "page": "Les femmes accomplissent 70 % en moyenne du travail familial et domestique",
                    "site": "Le Monde", "date": "20 avril 2020",
                    "link": "https://example.org/article#fragment",
                },
            },
        ],
    }

    resource = resources.build_resource_registry(sources, "0" * 64)["resources"][0]

    assert resource["conflicts"] == []
    assert resource["labels"] == [{
        "language": "fr",
        "label": "Nos vies confinées : « Les femmes accomplissent 70 %, en moyenne, du travail familial et domestique »",
    }]
    assert len(resource["metadata_variants"]) == 2
