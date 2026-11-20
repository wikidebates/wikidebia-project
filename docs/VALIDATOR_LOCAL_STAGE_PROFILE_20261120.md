# Profilage local et confidentiel du validateur Wikidéb'IA — 20 novembre 2026

## Pourquoi ce diagnostic ?

Après les PR [#178](https://github.com/wikidebates/wikidebia-project/pull/178) et [#179](https://github.com/wikidebates/wikidebia-project/pull/179) (schémas JSON), [#181](https://github.com/wikidebates/wikidebia-project/pull/181) et [#182](https://github.com/wikidebates/wikidebia-project/pull/182) (parseur MediaWiki), la [comparaison sur extraction réelle](https://github.com/wikidebates/wikidebia-project/issues/153) de **680 arguments** (cinq répétitions) a montré une accélération totale de **38,97 %** sur la préparation initiale et **36,56 %** sur la reprise interrompue. Le validateur dure cependant encore environ **1,038 seconde** sur le serveur de mesure, soit la part technique la plus coûteuse du parcours optimisé.

Il serait dangereux de supprimer des contrôles de provenance ou d'intégrité sur cette seule observation. La [PR #184](https://github.com/wikidebates/wikidebia-project/pull/184) sépare les coûts de validation et fournit une méthode facultative, **entièrement locale**, pour mesurer une extraction réelle sans recopier les pages sur GitHub.

## Premier profilage sans extraction réelle

[GitHub Actions #44744000836](https://github.com/wikidebates/wikidebia-project/actions/runs/44744000836), Ubuntu 24.04, Python 3.12, `jsonschema==4.26.0`, `referencing==0.37.0`. Validateur complet sur les cinq portées exactes de la préparation (`schema`, `coherence`, `graph`, `files`, `workflow`) ; trois répétitions par taille ; rapports `Report.to_dict()` égaux entre l'appel direct instrumenté et le lanceur officiel, après isolation de son champ supplémentaire `runtime_attestation` (attestation qui reste obligatoire dans le lanceur). Le corpus est intégralement synthétique.

| Arguments | Validateur sous-processus (médiane, s) | Processus déjà chargé, instrumenté (s) | Portée schémas (s) | Graphe (s) |
| ---: | ---: | ---: | ---: | ---: |
| 40 | 0,260405 | 0,103302 | 0,091059 | 0,006461 |
| 300 | 0,826909 | 0,665459 | 0,612038 | 0,045332 |
| 680 | 1,627682 | 1,484684 | 1,371707 | 0,103026 |

La **portée schémas représente environ 92 % du temps instrumenté en processus** sur 680 arguments. Dans le profil `cProfile`, les méthodes dominantes appartiennent au moteur `jsonschema` : `iter_errors`, `properties`, `items`, `descend`, `allOf`, `if_`, `oneOf`, `evolve`. Le module `PackageContext.safe_path` et le chargement des schémas coûtent beaucoup moins.

**Attention aux unités :** les durées de sous-processus et d'appel Python direct n'ont pas les mêmes surcoûts d'instrumentation. Leur différence ne mesure **pas** exactement le démarrage de Python. Les temps cumulés des méthodes imbriquées **ne s'additionnent pas**, et les `cumulative_seconds` de `cProfile` ralentissent elles-mêmes le code. Ces résultats ne doivent pas être confondus avec les durées mesurées sous Python 3.13.5 sur le serveur réel.

## Profilage local facultatif sur extraction réelle

Une fois la version du dépôt contenant la PR #184 installée localement :

```bash
.venv/bin/python tools/profile_validator_offline.py \
  --snapshot .state/graph-extract/NOM_DU_DOSSIER \
  --iterations 3 \
  --top 20 \
  --output .state/benchmarks/profil-validateur-local.json
```

La commande ne lance **aucune connexion MediaWiki**, aucun LLM, aucune traduction et aucune publication. Elle vérifie l'extraction et copie les pages dans un dossier temporaire via `build_corpus`, en préservant les contrôles de source, puis exécute le validateur officiel et son appel Python instrumenté sur **le même corpus temporaire**. Les deux rapports complets doivent être identiques, hormis l'attestation du lanceur officiel, avant qu'une mesure soit acceptée.

Pour éviter toute divulgation, le fichier JSON généré **ne contient pas** les titres, textes de pages, erreurs détaillées, chemins privés, noms de fichiers de l'extraction ni jetons. Il contient uniquement : versions de Python, nombre d'arguments et fichiers source, durées (brutes, médianes), durée par portée, temps cumulés par catégorie de méthode, noms de schémas prédéfinis, symboles de fonctions sans chemin et un SHA-256 du rapport. Si une donnée source change pendant l'expérience, aucun rapport n'est accepté. Ne pas exporter l'extraction.

La commande accepte `--iterations` de **2 à 12** et `--top` de **0 à 50** ; `--top 0` désactive `cProfile` (plus léger). Le fichier de sortie est optionnel et ne peut pas être écrit dans l'extraction.

### Interpréter les résultats

La section `breakdown` fournit des durées de portée `scope:schema` ou `scope:graph` et des mesures par schéma sous `schema:argument_registry.schema.json` ou `schema:argument_graph.schema.json`. Les durées de `SchemaStore.validate`, `PackageContext.safe_path` et des fonctions enfants se recouvrent **par construction** : seules les mesures des portées complètes permettent une répartition globale.

La section `validator_subprocess` mesure le coût réel d'un lancement du validateur officiel en Python isolé et la section `validator_inprocess_instrumented` celui d'un appel direct **avec instrumentation**. Ne pas soustraire ces deux chiffres comme si le second était non instrumenté. Le rapport du validateur et les résultats des contrôles normatifs sont **comparés en mémoire puis abandonnés**, sans les inscrire dans le fichier de mesures.

Les résultats servent à déterminer où mesurer ensuite ; ils ne justifient pas, à eux seuls, un contournement de `iter_errors`, `check_schema`, des empreintes, des reçus, des contrôles du graphe, des deux checkpoints français ni des revues sémantiques bilingues.

## Contrôles de non-régression

`tools/test_profile_validator_offline.py` couvre la signature du rapport, la suppression **seulement** de `runtime_attestation` lors de la comparaison, l'isolation des variables secrètes dans le sous-processus, la protection contre les chemins de sortie dans le snapshot, le refus des liens symboliques et des mutations de source, les limites des répétitions, et un **vrai test de bout en bout** sur une petite extraction synthétique (même validateur officiel, mêmes rapports et mêmes empreintes source). Cette suite est appelée dans la CI permanente depuis `.github/workflows/validate.yml`.

La méthode ne prétend pas mesurer la qualité des traductions ni les crédits Codex. Le serveur Debian et les wikis ne sont pas modifiés lors de l'audit GitHub ; l'éventuelle commande locale reste une action distincte de l'exploitant.
