import importlib.util
import json
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "wikidebia_graph_extract.py"
spec = importlib.util.spec_from_file_location("graphmod", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class FakeClient:
    def __init__(self, pages, aliases=None):
        self.pages = pages
        self.aliases = aliases or {}

    def fetch(self, title):
        canonical = self.aliases.get(title, title)
        if canonical not in self.pages:
            raise mod.PageMissingError(title)
        return mod.PageRecord(
            requested_title=title,
            canonical_title=canonical,
            text=self.pages[canonical],
            url=f"https://example.test/wiki/{canonical}",
            revision_id=1,
        )


class ParserTests(unittest.TestCase):
    def test_nested_debate_templates(self):
        text = """{{Débat
|arguments-pour={{Argument pour|page=A|titre-affiché=A prouve P}}{{Argument pour|page=B}}
|arguments-contre={{Argument contre|page=C}}
}}"""
        parsed = mod.parse_debate_wikitext(text)
        self.assertEqual([x.page for x in parsed.pro], ["A", "B"])
        self.assertEqual([x.page for x in parsed.con], ["C"])
        self.assertEqual(parsed.pro[0].displayed_title, "A prouve P")

    def test_frontier_discards_relations(self):
        text = """{{Argument
|débat-dédié=[[Débat sous-jacent]]
|justifications={{Justification|page=X}}
|objections={{Objection|page=Y}}
}}"""
        parsed = mod.parse_argument_wikitext(text)
        self.assertEqual(parsed.detailed_debate, "Débat sous-jacent")
        self.assertEqual(parsed.justifications, [])
        self.assertEqual(parsed.objections, [])
        self.assertEqual(parsed.ignored_relations_at_frontier, 2)
        self.assertFalse(parsed.warnings)


class CrawlTests(unittest.TestCase):
    def test_max_depth_limits_traversal_and_counts_arguments_by_level(self):
        pages = {
            "Débat test": "{{Débat|arguments-pour={{Argument pour|page=A}}|arguments-contre=}}",
            "A": "{{Argument|justifications={{Justification|page=B}}|objections=}}",
            "B": "{{Argument|justifications={{Justification|page=C}}|objections=}}",
            "C": "{{Argument|justifications={{Justification|page=D}}|objections=}}",
        }
        result = mod.crawl_graph(
            FakeClient(pages),
            debate_title="Débat test",
            max_depth=1,
            progress_every=0,
        )
        graph = mod.analyze_graph(result)
        self.assertEqual(set(result.parsed_arguments), {"A", "B"})
        self.assertEqual([(edge.source, edge.target) for edge in result.relations], [("A", "B")])
        self.assertEqual(result.depth_frontiers, {"B": 1})
        self.assertEqual(graph["metadata"]["arguments_par_niveau"], {1: 1, 2: 1})
        self.assertEqual(graph["metadata"]["limite_profondeur"], 1)
        self.assertEqual(graph["metadata"]["relations_ignorees_limite_profondeur"], 1)
        b = next(row for row in graph["noeuds"] if row["titre"] == "B")
        self.assertEqual(b["statut"], "frontière_profondeur")

    def test_default_depth_remains_unbounded(self):
        pages = {
            "Débat test": "{{Débat|arguments-pour={{Argument pour|page=A}}|arguments-contre=}}",
            "A": "{{Argument|justifications={{Justification|page=B}}|objections=}}",
            "B": "{{Argument|justifications={{Justification|page=C}}|objections=}}",
            "C": "{{Argument|justifications=|objections=}}",
        }
        result = mod.crawl_graph(FakeClient(pages), debate_title="Débat test", progress_every=0)
        graph = mod.analyze_graph(result)
        self.assertEqual(set(result.parsed_arguments), {"A", "B", "C"})
        self.assertIsNone(graph["metadata"]["limite_profondeur"])
        self.assertEqual(graph["metadata"]["arguments_par_niveau"], {1: 1, 2: 1, 3: 1})

    def test_recursive_graph_reuse_and_redirect(self):
        pages = {
            "Débat test": """{{Débat
|arguments-pour={{Argument pour|page=A}}
|arguments-contre={{Argument contre|page=B}}
}}""",
            "A": """{{Argument
|justifications={{Justification|page=Alias C}}
|objections={{Objection|page=B}}
}}""",
            "B": "{{Argument|justifications=|objections=}}",
            "C": """{{Argument
|débat détaillé=Débat C
|justifications={{Justification|page=X}}
|objections=
}}""",
        }
        client = FakeClient(pages, aliases={"Alias C": "C"})
        result = mod.crawl_graph(client, debate_title="Débat test", progress_every=0)
        graph = mod.analyze_graph(result)
        meta = graph["metadata"]
        self.assertEqual(meta["pages_arguments_uniques"], 3)
        self.assertEqual(meta["relations_uniques"], 2)
        self.assertEqual(meta["pages_uniques_par_niveau_minimal"], {1: 2, 2: 1})
        self.assertEqual(meta["occurrences_par_niveau"], {1: 2, 2: 2})
        self.assertEqual(meta["frontières_débat_détaillé"], {"C": "Débat C"})
        self.assertEqual(meta["niveau_minimal_maximal_pages_uniques"], 2)
        self.assertEqual(meta["niveau_maximal_occurrences"], 2)
        self.assertEqual(meta["profondeur_maximale_en_aretes"], 1)
        self.assertEqual(meta["occurrences_reutilisees_par_niveau"], {2: 1})
        self.assertEqual(meta["pages_sans_sortie_dans_graphe_extrait"], 2)
        self.assertEqual(meta["pages_terminales_reelles"], 1)
        self.assertEqual(meta["relations_locales_ignorees_aux_frontières"], 1)
        self.assertEqual(meta["avertissements"], 0)
        self.assertEqual(meta["informations_frontières"], 1)
        b = next(row for row in graph["noeuds"] if row["titre"] == "B")
        self.assertEqual(b["occurrences_totales"], 2)
        self.assertEqual(b["niveau_minimal"], 1)
        self.assertEqual(b["profondeur_minimale_en_aretes"], 0)


    def test_levels_and_edge_depth_are_not_confused(self):
        pages = {
            "Débat test": "{{Débat|arguments-pour={{Argument pour|page=A}}|arguments-contre=}}",
            "A": "{{Argument|justifications={{Justification|page=B}}|objections=}}",
            "B": "{{Argument|justifications={{Justification|page=C}}|objections=}}",
            "C": "{{Argument|justifications=|objections=}}",
        }
        graph = mod.analyze_graph(
            mod.crawl_graph(FakeClient(pages), debate_title="Débat test", progress_every=0)
        )
        meta = graph["metadata"]
        self.assertEqual(meta["niveau_minimal_maximal_pages_uniques"], 3)
        self.assertEqual(meta["niveau_maximal_occurrences"], 3)
        self.assertEqual(meta["profondeur_maximale_en_aretes"], 2)
        c = next(row for row in graph["noeuds"] if row["titre"] == "C")
        self.assertEqual(c["niveau_minimal"], 3)
        self.assertEqual(c["profondeur_minimale_en_aretes"], 2)
        self.assertTrue(all(check["ok"] for check in mod.audit_graph(graph)))

    def test_legacy_metric_aliases_keep_100_semantics(self):
        pages = {
            "Débat test": "{{Débat|arguments-pour={{Argument pour|page=A}}|arguments-contre=}}",
            "A": "{{Argument|justifications={{Justification|page=B}}|objections=}}",
            "B": "{{Argument|débat détaillé=Débat spécialisé|justifications={{Justification|page=C}}|objections=}}",
        }
        graph = mod.analyze_graph(
            mod.crawl_graph(FakeClient(pages), debate_title="Débat test", progress_every=0)
        )
        meta = graph["metadata"]
        # Nouveaux champs : profondeur réelle en arêtes.
        self.assertEqual(meta["niveau_minimal_maximal_pages_uniques"], 2)
        self.assertEqual(meta["niveau_maximal_occurrences"], 2)
        self.assertEqual(meta["profondeur_maximale_en_aretes"], 1)
        self.assertEqual(meta["pages_terminales_reelles"], 0)
        self.assertEqual(meta["pages_sans_sortie_dans_graphe_extrait"], 1)
        # Alias historiques 1.0.0 : anciens niveaux et pages sans sortie.
        self.assertEqual(meta["profondeur_maximale"], 2)
        self.assertEqual(meta["pages_terminales"], 1)
        a = next(row for row in graph["noeuds"] if row["titre"] == "A")
        b = next(row for row in graph["noeuds"] if row["titre"] == "B")
        self.assertEqual(a["profondeur_minimale"], 1)
        self.assertEqual(a["profondeur_minimale_en_aretes"], 0)
        self.assertEqual(b["profondeur_minimale"], 2)
        self.assertEqual(b["profondeur_minimale_en_aretes"], 1)
        self.assertEqual(b["occurrences_par_profondeur"], {2: 1})
        self.assertEqual(b["occurrences_par_profondeur_en_aretes"], {1: 1})
        relation = graph["relations"][0]
        self.assertEqual(relation["profondeur_source_minimale"], 1)
        self.assertEqual(relation["profondeur_source_minimale_en_aretes"], 0)
        branch = graph["branches_niveau_1"][0]
        self.assertEqual(branch["profondeur_maximale"], 2)
        self.assertEqual(branch["profondeur_maximale_en_aretes"], 1)

    def test_snapshot_and_package_are_complete(self):
        pages = {
            "Débat test": "{{Débat|arguments-pour={{Argument pour|page=A}}|arguments-contre=}}",
            "A": "{{Argument|justifications={{Justification|page=B}}|objections=}}",
            "B": "{{Argument|justifications=|objections=}}",
        }
        result = mod.crawl_graph(FakeClient(pages), debate_title="Débat test", progress_every=0)
        graph = mod.analyze_graph(result)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            paths = mod.write_outputs(
                graph, result, output_dir=output, slug="debat_test", extraction_date="2026-08-03"
            )
            snapshot = json.loads(paths["snapshot_manifest"].read_text(encoding="utf-8"))
            self.assertEqual(snapshot["counts"], {"debate_pages": 1, "argument_pages": 2, "total_pages": 3})
            self.assertEqual(len(snapshot["arguments"]), 2)
            package = json.loads(paths["manifest"].read_text(encoding="utf-8"))
            self.assertEqual(package["audit_status"], "passed")
            self.assertGreater(package["declared_file_count"], 6)
            with zipfile.ZipFile(paths["zip"]) as archive:
                names = set(archive.namelist())
            self.assertIn("snapshot/snapshot_manifest.json", names)
            self.assertIn("snapshot/pages/debate.wiki", names)

    def test_report_separates_depth_levels_and_frontier_information(self):
        pages = {
            "Débat test": "{{Débat|arguments-pour={{Argument pour|page=A}}|arguments-contre=}}",
            "A": "{{Argument|débat détaillé=Débat spécialisé|justifications={{Justification|page=B}}|objections=}}",
        }
        result = mod.crawl_graph(FakeClient(pages), debate_title="Débat test", progress_every=0)
        graph = mod.analyze_graph(result)
        with tempfile.TemporaryDirectory() as directory:
            paths = mod.write_outputs(
                graph,
                result,
                output_dir=Path(directory),
                slug="debat_test",
                extraction_date="2026-08-04",
            )
            report = paths["report"].read_text(encoding="utf-8")
        self.assertIn("Niveau maximal d’une occurrence", report)
        self.assertIn("Profondeur maximale en nombre d’arêtes", report)
        self.assertIn("## Informations sur les frontières", report)
        self.assertIn("1 relation(s) locale(s) non suivie(s)", report)
        self.assertIn("## Avertissements réels", report)
        self.assertNotIn("Frontière débat détaillé", report)

    def test_report_exposes_depth_frontiers_and_argument_counts(self):
        pages = {
            "Débat test": "{{Débat|arguments-pour={{Argument pour|page=A}}|arguments-contre=}}",
            "A": "{{Argument|justifications={{Justification|page=B}}|objections=}}",
            "B": "{{Argument|justifications={{Justification|page=C}}|objections=}}",
            "C": "{{Argument|justifications=|objections=}}",
        }
        result = mod.crawl_graph(
            FakeClient(pages), debate_title="Débat test", max_depth=1, progress_every=0
        )
        graph = mod.analyze_graph(result)
        with tempfile.TemporaryDirectory() as directory:
            paths = mod.write_outputs(
                graph,
                result,
                output_dir=Path(directory),
                slug="debat_test",
                extraction_date="2026-10-24",
            )
            report = paths["report"].read_text(encoding="utf-8")
        self.assertIn("### Nombre d’arguments par niveau", report)
        self.assertIn("## Frontières de profondeur", report)
        self.assertIn("Limite demandée : **1 arête(s)**", report)
        self.assertIn("Relations vers le niveau suivant non suivies : **1**", report)

    def test_cache_is_reusable(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = mod.JsonPageCache(Path(directory))
            record = mod.PageRecord(
                requested_title="Alias", canonical_title="A", text="texte", revision_id=7
            )
            cache.put(record)
            self.assertEqual(cache.get("Alias").canonical_title, "A")
            self.assertEqual(cache.get("A").revision_id, 7)

    def test_cycle_is_reported(self):
        pages = {
            "Débat test": "{{Débat|arguments-pour={{Argument pour|page=A}}|arguments-contre=}}",
            "A": "{{Argument|justifications={{Justification|page=B}}|objections=}}",
            "B": "{{Argument|justifications={{Justification|page=A}}|objections=}}",
        }
        graph = mod.analyze_graph(
            mod.crawl_graph(FakeClient(pages), debate_title="Débat test", progress_every=0)
        )
        self.assertFalse(graph["metadata"]["graphe_sans_cycle"])
        self.assertTrue(graph["metadata"]["nœuds_dans_cycles"])



class DedicatedDebateCliRegressionTests(unittest.TestCase):
    def test_parser_uses_dedicated_destination_for_new_and_legacy_option_names(self):
        for option in (
            "--follow-local-relations-at-dedicated-debate",
            "--follow-local-relations-at-detailed-debate",
        ):
            args = mod.build_parser().parse_args(["--debate", "Débat test", option])
            self.assertTrue(args.follow_local_relations_at_dedicated_debate)
            self.assertFalse(hasattr(args, "follow_local_relations_at_detailed_debate"))

    def test_parser_accepts_max_depth(self):
        args = mod.build_parser().parse_args(["--debate", "Débat test", "--max-depth", "4"])
        self.assertEqual(args.max_depth, 4)

if __name__ == "__main__":
    unittest.main()


class SafetyTests(unittest.TestCase):
    def test_extractor_contains_no_pywikibot_write_call(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        forbidden = ("page.save(", "page.put(", "page.delete(", "page.move(", "editpage(", "submit(")
        self.assertFalse([token for token in forbidden if token in source])

    def test_anonymous_read_does_not_require_user_config(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = mod.JsonPageCache(Path(directory) / "cache")
            client = mod.PywikibotPageClient(
                family="wikidebates",
                lang="fr",
                family_file=None,
                pywikibot_dir=Path(directory) / "private",
                cache=cache,
                login=False,
            )
            self.assertFalse(client.login)

    def test_cloudflare_access_header_is_configured_before_site_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            config = types.SimpleNamespace(extra_headers={}, family_files={})
            fake = types.SimpleNamespace(
                config=config,
                Site=lambda **_kwargs: types.SimpleNamespace(),
            )
            cache = mod.JsonPageCache(Path(directory) / "cache")
            client = mod.PywikibotPageClient(
                family="wikidebates",
                lang="fr",
                family_file=None,
                pywikibot_dir=None,
                cache=cache,
                login=False,
            )
            with mock.patch.dict(sys.modules, {"pywikibot": fake}), mock.patch.dict(
                "os.environ", {"WIKIDEBIA_API_TOKEN": "test-access-token"}, clear=False,
            ):
                client._open()
            self.assertEqual(
                config.extra_headers["x-wikidebia-access"], "test-access-token",
            )
