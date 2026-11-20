# Mesure avant/après des trois chemins de préparation et reprise — 20 novembre 2026

## Objet de l'expérience

Après la fusion des [PR #178](https://github.com/wikidebates/wikidebia-project/pull/178) et [#179](https://github.com/wikidebates/wikidebia-project/pull/179), vérifier leur effet **sur le workflow complet de préparation prétraduction**, et non uniquement sur `validate_package(scopes=["schema"])`. Le protocole compare :
- **Avant #178** : `065bb4af6c895a456d7a92e1c9615115f134d5d7`.
- **Après #178** : `2d8e9b540016e2335d1613b9cbe9df13644fa9e4` (métavalidation statique attestée).
- **Après #179** : `ba366eb79b7dc2dc7c1cfe32a54508ed0feac20a` (développement borné des `$ref` du registre d'arguments).

Source : [GitHub Actions #44732532308](https://github.com/wikidebates/wikidebia-project/actions/runs/44732532308), `ubuntu-24.04`, Python 3.12, dépendances **`jsonschema==4.26.0`** et **`referencing==0.37.0`**. Le travail expérimental est enregistré dans la [PR #180](https://github.com/wikidebates/wikidebia-project/pull/180). Le workflow temporaire a été retiré de la version livrée.

## Protocole et garde-fous

1. Utilisation du **même benchmark de production non modifié** : `kit/scripts/wikidebia_pretranslation_benchmark.py`. Son SHA-256 exact est `656f198cdb756ac160fc569dfc88d1324858ee7dac8af348c2e364cd5b11a432` dans chacune des trois révisions, vérifié avant toute mesure.
2. Trois tailles de **corpus exclusivement synthétiques** : 40, 120, 300 arguments ; 1 024 octets de remplissage par argument, 20 racines au plus, relations récursives ; pas de données réelles Wikidébates. Chaque exécution régénère indépendamment la même fixture déterministe. Les empreintes du contrat de build sont strictement identiques **entre les trois révisions et les cinq passages** pour une même taille :
   - 40 arguments : `f7796600da27c1254d815f62bfabd25d9f5d0b1cbedf50a5e5c0bce7f113a060`
   - 120 arguments : `7b4b8e3cc46d85d88bae164b7043630a26708cd020e3e5eb9e0b5aec81dd4fc8`
   - 300 arguments : `33fdda65c18d4e98a37139d453e6410348616d25454c8f9840194b19289afdfb`
3. **Cinq répétitions**, une itération complète du benchmark par passage et par révision, en alternant l'ordre des versions dans un **seul job sur un même runner**. Les temps de démarrage, les écritures temporaires, la validation en sous-processus, les reçus et les relectures de reprise sont mesurés effectivement. Aucune instrumentation `--profile-file-io` n'altère ces durées.
4. Vérification du **SHA-256 signé de chaque rapport** et des `quality_controls` : même contrat, construction initiale validée, reprise interrompue validée, reçu de reprise exacte vérifié ; `real_snapshot_used=false`, `wiki_access_performed=false`, `translation_logic_exercised=false`. Les résultats seraient rejetés si un seul de ces contrôles échouait.

Les scénarios mesurés sont ceux du guide de benchmark existant : construction + validateur + reçu ; reprise après construction mais avant reçu (source et validateur revérifiés) ; reprise exacte d'un reçu préexistant (source et reçu revérifiés, **sans relancer le validateur**).

## Résultats complets

Durées médianes en secondes (plus bas = plus rapide). Le pourcentage compare le dernier commit au commit antérieur aux deux PR.

### Construction initiale et validation

| Arguments | Avant #178 (s) | Après #178 (s) | Après #179 (s) | Réduction totale |
| ---: | ---: | ---: | ---: | ---: |
| 40 | 0.564119 | 0.391359 | **0.351426** | **37.70 %** |
| 120 | 1.004048 | 0.847344 | **0.707694** | **29.52 %** |
| 300 | 1.997155 | 1.816102 | **1.489494** | **25.42 %** |

### Reprise interrompue, avant reçu final

| Arguments | Avant #178 (s) | Après #178 (s) | Après #179 (s) | Réduction totale |
| ---: | ---: | ---: | ---: | ---: |
| 40 | 0.472662 | 0.299578 | **0.259614** | **45.07 %** |
| 120 | 0.732794 | 0.565008 | **0.436816** | **40.39 %** |
| 300 | 1.323412 | 1.147374 | **0.835010** | **36.90 %** |

### Reprise exacte, avec reçu déjà validé

| Arguments | Avant #178 (s) | Après #178 (s) | Après #179 (s) | Réduction totale |
| ---: | ---: | ---: | ---: | ---: |
| 40 | 0.020310 | 0.020324 | **0.020188** | **0.60 %** |
| 120 | 0.053399 | 0.053298 | **0.053329** | **0.13 %** |
| 300 | 0.128163 | 0.127658 | **0.126826** | **1.04 %** |

**Interprétation :** les gains sont principalement concentrés sur les chemins qui **relancent le validateur**. La reprise exacte reste très rapide et essentiellement inchangée ; ses faibles variations ne prouvent pas une amélioration significative. Les opérations d'intégrité de la source et du reçu sont conservées. Il ne faut pas additionner les pourcentages obtenus séparément sur les deux PR : les mesures ci-dessus concernent directement trois versions complètes.

### Détail des étapes techniques

| Arguments | Variante | Validateur initial (construction, s) | Construction du corpus (s) | Vérification source, reprise exacte (s) | Vérification reçu, reprise exacte (s) |
| ---: | --- | ---: | ---: | ---: | ---: |
| 40 | pre 178 | 0.443874 | 0.111668 | 0.012518 | 0.007698 |
| 40 | post 178 | 0.269811 | 0.112233 | 0.012615 | 0.007561 |
| 40 | post 179 | 0.231481 | 0.112253 | 0.012505 | 0.007577 |
| 120 | pre 178 | 0.658928 | 0.326776 | 0.034736 | 0.018075 |
| 120 | post 178 | 0.500320 | 0.321336 | 0.035057 | 0.018048 |
| 120 | post 179 | 0.367203 | 0.322725 | 0.035130 | 0.018077 |
| 300 | pre 178 | 1.152727 | 0.794313 | 0.086393 | 0.041232 |
| 300 | post 178 | 0.980086 | 0.801162 | 0.085920 | 0.041210 |
| 300 | post 179 | 0.659407 | 0.792605 | 0.085520 | 0.040733 |

Le gain du validateur est moins visible à mesure que la taille augmente dans le workflow total, car la construction du corpus et les vérifications des sources prennent une proportion croissante du temps. Ces dernières ne doivent pas être supprimées seulement pour accélérer le benchmark.

### Échantillons bruts

| Arguments | Variante | Construction initiale (5 échantillons, s) | Reprise interrompue (5 échantillons, s) | Reprise exacte (5 échantillons, s) |
| ---: | --- | --- | --- | --- |
| 40 | pre_178 | `0.698196, 0.563903, 0.564119, 0.563335, 0.564365` | `0.474219, 0.468142, 0.471290, 0.472662, 0.475197` | `0.020567, 0.020610, 0.020310, 0.019982, 0.020161` |
| 40 | post_178 | `0.486902, 0.391359, 0.389391, 0.391104, 0.394562` | `0.297718, 0.322176, 0.299978, 0.297633, 0.299578` | `0.020281, 0.020717, 0.020212, 0.020404, 0.020324` |
| 40 | post_179 | `0.448333, 0.350954, 0.351168, 0.355596, 0.351426` | `0.260528, 0.259506, 0.258475, 0.262225, 0.259614` | `0.020354, 0.020202, 0.020157, 0.020174, 0.020188` |
| 120 | pre_178 | `1.019338, 1.004328, 0.996159, 0.996472, 1.004048` | `0.731355, 0.730096, 0.732794, 0.736856, 0.734196` | `0.053673, 0.052751, 0.052821, 0.053399, 0.054185` |
| 120 | post_178 | `0.830787, 0.901245, 0.868658, 0.845631, 0.847344` | `0.565008, 0.566834, 0.565592, 0.563286, 0.557225` | `0.053340, 0.076209, 0.053298, 0.053226, 0.053079` |
| 120 | post_179 | `0.715890, 0.724041, 0.707694, 0.703214, 0.703992` | `0.439882, 0.435413, 0.437878, 0.435617, 0.436816` | `0.053213, 0.053329, 0.052894, 0.053440, 0.053667` |
| 300 | pre_178 | `1.998896, 1.981238, 1.997155, 1.996949, 2.015800` | `1.314415, 1.330102, 1.323412, 1.326498, 1.317410` | `0.127595, 0.128163, 0.128845, 0.136239, 0.127059` |
| 300 | post_178 | `1.816102, 1.820762, 1.822127, 1.812201, 1.804688` | `1.156941, 1.142604, 1.147374, 1.141766, 1.155565` | `0.127658, 0.127574, 0.128711, 0.127252, 0.128671` |
| 300 | post_179 | `1.488182, 1.480858, 1.489494, 1.514427, 1.493965` | `0.825612, 0.834545, 0.835010, 0.845055, 0.835508` | `0.126178, 0.126826, 0.127555, 0.126214, 0.127323` |

Cinq répétitions par cellule ; les rapports originaux contiennent aussi les écarts-types par scénario. Les premières mesures de certains chemins peuvent être plus lentes, ce qui justifie une lecture des **médianes** et une alternance des ordres de passage.

## Ce que cette expérience démontre — et ne démontre pas

- Elle démontre un gain mesurable **de bout en bout sur la préparation hors ligne** pour une construction initiale et une reprise interrompue, sur les fixtures synthétiques décrites et les bibliothèques attestées. Les précautions de reprise (empreintes des sources, validation non encore attestée, reçu) ont toutes réussi.
- Elle ne mesure **aucune extraction réelle**. Pour cela, la commande documentée `./wikidebia pretranslation-benchmark --snapshot ...` doit être exécutée **localement**, sur une extraction figée autorisée, sans publier ni exporter le corpus ni ses titres.
- Elle ne mesure ni traduction effective, ni revue sémantique bilingue, ni publication MediaWiki, ni temps réseau, ni facturation Codex. **Aucune économie de tokens ou de crédits n'est attestée.**
- La variante optimisée est volontairement limitée aux versions de bibliothèques connues ; sur un environnement utilisant d'autres versions, le chemin original de validation restera actif, donc ces gains ne doivent pas être supposés acquis.
- La mesure de la **reprise exacte** confirme qu'elle évite les opérations coûteuses tout en gardant les contrôles indépendants. Ne pas dédupliquer ou mettre en cache durablement ses hachages de sécurité.

## Suite proposée

Avec 300 arguments, le validateur a fortement diminué mais `build_corpus` représente à lui seul environ 0,79 s sur 1,49 s au dernier commit, tandis que la reprise exacte vérifie toujours la source et le reçu. **La priorité suivante est donc de profiler la construction du corpus** (sans désactiver les vérifications répétées nécessaires entre contrôle et copie), avant toute nouvelle optimisation de code. Un éventuel gain doit être mesuré en face d'une version antérieure avec une équivalence complète des fichiers construits, du contrat, des reçus et des diagnostics.
