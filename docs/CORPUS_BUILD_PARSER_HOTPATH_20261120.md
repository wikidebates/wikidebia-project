# Accélération de la construction des corpus par analyse syntaxique MediaWiki — 20 novembre 2026

## Constat et portée

Suite du chantier de performance [#153](https://github.com/wikidebates/wikidebia-project/issues/153), après les améliorations du validateur [#178](https://github.com/wikidebates/wikidebia-project/pull/178) et [#179](https://github.com/wikidebates/wikidebia-project/pull/179), puis la [mesure du parcours complet #180](PRETRANSLATION_END_TO_END_COMPARISON_20261120.md). Le parcours de construction `build_corpus` représente encore une part importante du temps avant traduction : environ 0,79 seconde sur 1,49 seconde en construction initiale de 300 arguments lors de la mesure précédente.

Le [profilage #44733455116](https://github.com/wikidebates/wikidebia-project/actions/runs/44733455116) (Ubuntu 24.04, Python 3.12, corpus exclusivement synthétiques de 40/300/878 arguments) a identifié une source dominante **dans l'analyse des textes des pages importées**, et non dans les contrôles d'intégrité : `copy_import_pages` et `extract_page_metadata` appellent `iter_templates` et `parse_template` du module `kit/scripts/wikidebia_graph_extract.py`. La fonction `_split_top_level` réexaminait jusqu'à sept délimiteurs avec `str.startswith` à chaque position de la chaîne, même pour les caractères ordinaires.

Le profilage observait, sur 878 arguments, 1,726 seconde de `build_corpus` dont **1,367 seconde** pour `copy_import_pages`. Sous `cProfile`, plus de 18 millions d'appels cumulés à `startswith` ont été comptabilisés ; les durées de `cProfile` lui-même ne sont **pas** les durées non instrumentées du workflow.

## Optimisation livrée

La [PR #181](https://github.com/wikidebates/wikidebia-project/pull/181) améliore uniquement **deux fonctions** du parseur : `_template_spans` et `_split_top_level`.

- Le caractère courant est examiné en premier. Le code cherche `{{{` ou `{{` uniquement si c'est une accolade ouvrante, `}}}` ou `}}` uniquement en présence d'une accolade fermante et d'une pile de modèles non vide, `[[` uniquement après `[`, et `]]` uniquement après `]` quand un lien est ouvert.
- La présence du premier caractère du séparateur est vérifiée avant `startswith(delimiter, i)`. Les contenus textuels ordinaires ne déclenchent donc plus les vérifications de préfixes coûteuses.
- **Même ordre de priorité** que précédemment : triples accolades avant doubles, traitement des modèles et des liens avant les séparateurs ; mêmes piles, mêmes indices et mêmes tranches de chaîne. Aucun parseur externe n'est introduit, aucun modèle MediaWiki ni métadonnée n'est supprimé.
- Un séparateur vide, qui ne permettait pas à l'ancienne boucle de progresser, est désormais rejeté explicitement par `ValueError`. Les séparateurs non vides utilisés par le projet (notamment `|` et `=`) conservent leurs résultats.

Le comportement de contrôle des sources n'a pas été modifié : empreintes du snapshot, vérification à la copie des octets exacts (contre une modification entre vérification et import), provenance, contrats, signatures du build et reçus indépendants sont tous inchangés.

## Tests différentiels et comparaison octet par octet

La suite `kit/tests/test_graph_extract_parser_fastpath.py` inclut **35 nouveaux tests**. Elle conserve un oracle indépendant issu des deux anciennes fonctions et confronte la nouvelle implémentation à l'ancienne, y compris sur des textes avec accolades triples et doubles imbriquées, liens, commentaires, séparateurs multi-caractères, fins de modèle manquantes, syntaxe malformée, contenus Unicode et 24 graines pseudo-aléatoires déterministes de 48 exemples chacune. `iter_templates` et les métadonnées extraites sont également comparées.

Un test de construction complet supplémentaire, passé sur [GitHub Actions #44733979600](https://github.com/wikidebates/wikidebia-project/actions/runs/44733979600), a construit cinq fois la même extraction synthétique avec chaque parseur, dans un ordre alterné, en figeant les horodatages pour comparer les **octets** plutôt que des textes modifiés uniquement par la date. À chaque variante, le SHA-256 de **tous les fichiers produits**, ainsi que le contrat de build, était identique.

| Arguments | Fichiers produits comparés | Ancien `build_corpus` (s) | Nouveau `build_corpus` (s) | Réduction |
| ---: | ---: | ---: | ---: | ---: |
| 40 | 54 | 0.137783 | 0.069060 | **49.88 %** |
| 300 | 314 | 0.999118 | 0.490136 | **50.94 %** |
| 878 | 892 | 2.925123 | 1.433798 | **50.98 %** |

Cinq répétitions par taille et par variante, sans validation distante.

Échantillons bruts `build_corpus` (secondes) :

- **40 arguments**, ancien : `[0.137178, 0.138724, 0.137783, 0.136744, 0.137895]` ; nouveau : `[0.077939, 0.069060, 0.068999, 0.068880, 0.069629]`.
- **300 arguments**, ancien : `[1.000401, 0.999118, 0.998697, 1.002519, 0.999103]` ; nouveau : `[0.490136, 0.490873, 0.489576, 0.497772, 0.487611]`.
- **878 arguments**, ancien : `[2.929184, 2.913410, 2.925123, 2.933269, 2.916794]` ; nouveau : `[1.451571, 1.441925, 1.427826, 1.433798, 1.423141]`.

**1 377 tests du kit réussis** (contre 1 342 auparavant), rapport de tests et manifeste/reçu SHA-256 régénérés. Un contrôle intégral de la CI reste nécessaire avant fusion.

## Effet mesuré sur les chemins complets de prétraduction

[GitHub Actions #44734412765](https://github.com/wikidebates/wikidebia-project/actions/runs/44734412765), même révision, même runner Ubuntu, Python 3.12, `jsonschema==4.26.0`, `referencing==0.37.0` ; trois répétitions par taille et variante alternées. Seul le parseur utilisé dans le processus principal change : le validateur en sous-processus, les contrôles de reçus, les versions du kit et les paramètres de build sont identiques. Les rapports signés et les `quality_controls` ont tous été vérifiés, et chaque taille conserve une seule empreinte de contrat pour les deux variantes.

### Construction initiale, validateur et reçu

| Arguments | Parseur ancien (médiane s) | Parseur optimisé (médiane s) | Variation relative |
| ---: | ---: | ---: | ---: |
| 40 | 0.416859 | 0.349957 | 16.05 % |
| 300 | 1.902099 | 1.373012 | 27.82 % |
| 878 | 5.170697 | 3.646277 | 29.48 % |

### Reprise après une interruption avant le reçu

| Arguments | Parseur ancien (médiane s) | Parseur optimisé (médiane s) | Variation relative |
| ---: | ---: | ---: | ---: |
| 40 | 0.309431 | 0.308682 | 0.24 % |
| 300 | 1.079209 | 1.072335 | 0.64 % |
| 878 | 2.783162 | 2.786928 | -0.14 % |

### Reprise exacte d'un reçu déjà vérifié

| Arguments | Parseur ancien (médiane s) | Parseur optimisé (médiane s) | Variation relative |
| ---: | ---: | ---: | ---: |
| 40 | 0.030062 | 0.029649 | 1.37 % |
| 300 | 0.190502 | 0.189140 | 0.71 % |
| 878 | 0.546575 | 0.543626 | 0.54 % |

**Interprétation :** le gain de performance intervient lorsque le corpus **est réellement construit**. Les reprises après construction (avec ou sans reçu) restent stables dans la variabilité des mesures, car elles ne relancent pas le parseur des pages importées. Une légère baisse ponctuelle n'est pas une accélération démontrée. La vitesse du validateur reste celle des PR #178/#179.

Échantillons bruts du benchmark complet (secondes) :

- **40 arguments** :
  - Construction initiale, validateur et reçu : ancien `[0.416859, 0.418215, 0.416212]` ; nouveau `[0.482781, 0.346185, 0.349957]`.
  - Reprise interrompue : ancien `[0.312738, 0.307966, 0.309431]` ; nouveau `[0.305808, 0.308682, 0.310897]`.
  - Reprise exacte : ancien `[0.030062, 0.029847, 0.030998]` ; nouveau `[0.029957, 0.029493, 0.029649]`.
- **300 arguments** :
  - Construction initiale, validateur et reçu : ancien `[1.893132, 1.902099, 1.907339]` ; nouveau `[1.373012, 1.369209, 1.395163]`.
  - Reprise interrompue : ancien `[1.067545, 1.091729, 1.079209]` ; nouveau `[1.065419, 1.072335, 1.093501]`.
  - Reprise exacte : ancien `[0.189150, 0.191723, 0.190502]` ; nouveau `[0.188484, 0.189140, 0.193135]`.
- **878 arguments** :
  - Construction initiale, validateur et reçu : ancien `[5.170697, 5.142924, 5.197433]` ; nouveau `[3.646277, 3.628664, 3.655055]`.
  - Reprise interrompue : ancien `[2.783162, 2.795409, 2.773492]` ; nouveau `[2.776695, 2.787644, 2.786928]`.
  - Reprise exacte : ancien `[0.544104, 0.546575, 0.552789]` ; nouveau `[0.543626, 0.543328, 0.544498]`.

## Limites et prochaines mesures

- **Uniquement des corpus synthétiques déterministes** ; aucune extraction privée, réelle ou historique n'a été importée depuis le serveur Debian ou exportée vers GitHub. Les pages générées pour le benchmark contiennent beaucoup de texte ordinaire : le gain peut être différent avec des pages fortement imbriquées en modèles.
- L'égalité des fichiers construits et des rapports vérifiés s'applique aux cas testés ; elle ne constitue pas une preuve formelle d'équivalence de toutes les syntaxes MediaWiki possibles. Les tests différentiels ciblent explicitement les formes ambiguës et malformées pour réduire ce risque.
- Aucune mesure de traduction effective, d'évaluation de la fidélité sémantique, de publication, de réseau wiki ou de tokens/crédits Codex.
- La suite logique est de mesurer le nouveau parcours `./wikidebia pretranslation-benchmark --snapshot ...` sur une **extraction réelle figée et autorisée**, localement et sans publier, puis de comparer les étapes non linguistiques. Les hachages de sécurité et les contrôles de qualité de traduction ne doivent pas être sacrifiés à une optimisation.
