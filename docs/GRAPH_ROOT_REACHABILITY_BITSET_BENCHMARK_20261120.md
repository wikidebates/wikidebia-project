# Propagation des racines dans les graphes convergents — 20 novembre 2026

## Constat

La fonction `kit/scripts/wikidebia_graph_extract.py::analyze_graph` doit déterminer, pour chaque argument, l'ensemble **des arguments principaux** qui permettent de l'atteindre, ainsi que leurs orientations (« pour » ou « contre »).

L'algorithme historique propage des `set[str]` sur chaque arête du DAG. Lorsque plusieurs centaines de racines convergent vers les mêmes descendants, chaque ensemble peut contenir des centaines de titres, et `roots_reaching[target].update(roots_reaching[source])` répète de grandes copies. Les listes de titres triés et d'orientations restent indispensables à la structure exportée.

## Correctif conditionnel

La [PR #173](https://github.com/wikidebates/wikidebia-project/pull/173) utilise une représentation temporaire en entier Python (`bitmask`) **seulement** si toutes les conditions suivantes sont réunies :

- au moins **16 arguments principaux distincts** ;
- au maximum **8 000 nœuds** (limite de mémoire explicite) ;
- au moins un nœud avec **huit relations entrantes ou plus** ;
- aucun couple de titres principaux distincts produisant la même clé `casefold()`.

La dernière condition préserve à l'identique l'ordre historique des titres de casse différente : l'ancien `sorted(set, key=str.casefold)` n'impose pas de départage déterministe des ex æquo, donc ces graphes conservent **exactement** l'ancienne propagation par ensembles. Les graphes sans forte convergence, les graphes cycliques et les graphes trop volumineux conservent également ce chemin.

Pour les graphes admissibles, chaque racine est représentée par un bit. Les masques sont propagés suivant l'ordre topologique déjà calculé. Un cache **limité à 256 entrées et à l'invocation courante** évite de retrier les mêmes ensembles de titres lorsque de nombreux descendants ont les mêmes racines ; les lignes de sortie reçoivent néanmoins **des listes distinctes**, comme avant. Le cache n'est pas conservé sur disque ni entre sessions.

Les compteurs de chemins/occurrences, les profondeurs, les statuts, les titres, les pages sources et les règles de traduction et publication ne sont pas modifiés.

## Benchmarks appariés

Trois exécutions GitHub Actions, Ubuntu 24.04 / Python 3.12 :
- [première campagne #44641807757](https://github.com/wikidebates/wikidebia-project/actions/runs/44641807757) ;
- [répétition #44642200282](https://github.com/wikidebates/wikidebia-project/actions/runs/44642200282) ;
- [variante finale avec détection économe #44642353602](https://github.com/wikidebates/wikidebia-project/actions/runs/44642353602).

Le module de référence est fixé au commit `54b4005135cc89cf17b3d2a3ffc41a7cbd000493` et chargé séparément, aux côtés du candidat. Les deux reçoivent **le même `CrawlResult` synthétique**. Trois à neuf essais sont alternés avant/après, selon la taille. **Chaque comparaison exige l'égalité de l'intégralité du dictionnaire retourné par `analyze_graph`**, pas uniquement les listes des racines.

Les graphes comprennent des chaînes communes à beaucoup de racines, deux groupes de racines qui fusionnent plus loin, des branches indépendantes et des titres distincts identiques en `casefold` (chemin de repli historique). Aucune opération MediaWiki ni appel de traduction n'est effectué.

### Résultats de la version finale (médianes)

| Forme synthétique | Racines | Nœuds | Avant (s) | Après (s) | Réduction |
| --- | ---: | ---: | ---: | ---: | ---: |
| Chaîne commune | 24 | 144 | 0,0018135 | 0,0015195 | 16,21 % |
| Chaîne commune | 80 | 520 | 0,009493 | 0,006028 | 36,50 % |
| Chaîne commune | 300 | 1 100 | 0,041274 | 0,014897 | 63,91 % |
| Chaîne commune | 400 | 2 400 | 0,138063 | 0,035774 | **74,09 %** |
| Deux groupes convergents | 80 | 520 | 0,009632 | 0,005992 | 37,79 % |
| Deux groupes convergents | 300 | 1 100 | 0,041603 | 0,015077 | 63,76 % |
| Branches indépendantes | 120 | 240 | 0,002182 | 0,0021755 | 0,30 % |
| Branches indépendantes | 700 | 1 400 | 0,013690 | 0,013826 | −0,99 % |
| Collision de casse (ancien code) | 50 | 190 | 0,002636 | 0,002645 | −0,34 % |

Les deux campagnes précédentes avaient confirmé le même type d'amélioration, avec des gains d'environ 63–73 % pour les plus grands graphes convergents. Les écarts très faibles sur les cas non ciblés sont proches du bruit de mesure : **aucune accélération significative n'est annoncée sur les branches indépendantes**.

### Échantillons bruts de la dernière campagne (secondes)

Chaque ligne donne d'abord l'ancien code, puis le nouveau code :

- Commune 24/144 : `[0.001842,0.001917,0.001778,0.001851,0.001785,0.001749]` ; `[0.001525,0.001547,0.001501,0.001560,0.001473,0.001514]`.
- Commune 80/520 : `[0.009869,0.009419,0.009567,0.009394,0.009616,0.009010]` ; `[0.006022,0.012159,0.005837,0.006134,0.005447,0.006034]`.
- Commune 300/1100 : `[0.055349,0.039248,0.040567,0.041665,0.040612,0.041274,0.039524,0.041367,0.051959]` ; `[0.014735,0.014962,0.024665,0.014845,0.014251,0.024474,0.014257,0.014997,0.014897]`.
- Commune 400/2400 : `[0.164913,0.138063,0.125272,0.147747,0.124119,0.159443,0.132983,0.129025,0.149642]` ; `[0.035771,0.036558,0.046604,0.035729,0.049562,0.035774,0.035451,0.049995,0.034719]`.
- Groupes 80/520 : `[0.011343,0.009361,0.009632,0.009429,0.009693]` ; `[0.005992,0.013674,0.005920,0.006309,0.005603]`.
- Groupes 300/1100 : `[0.042002,0.040374,0.040824,0.041603,0.041382,0.052848,0.041170,0.043152,0.053281]` ; `[0.021911,0.015077,0.014224,0.023989,0.015046,0.015162,0.014318,0.015193,0.014402]`.
- Indépendantes 120/240 : `[0.002855,0.002067,0.002286,0.002177,0.002187,0.002078]` ; `[0.002420,0.002189,0.002075,0.002162,0.002081,0.002255]`.
- Indépendantes 700/1400 : `[0.013735,0.013064,0.013690,0.013311,0.013729,0.013105,0.013531,0.019890,0.013933]` ; `[0.021686,0.013826,0.013201,0.019714,0.013178,0.020365,0.013381,0.013841,0.013458]`.
- Cas `casefold` 50/190 : `[0.003060,0.002543,0.002710,0.002636,0.002616]` ; `[0.002811,0.002673,0.002569,0.002645,0.002588]`.

## Preuve de non-régression

**17 tests ciblés** reposent sur un oracle indépendant : un parcours DFS par racine calcule l'ensemble des arguments atteignant chaque nœud. Ils couvrent :
- les listes complètes de racines et d'orientations avec branche commune profonde ;
- l'absence d'aliasing entre les listes de plusieurs nœuds ;
- la fusion de deux groupes aux orientations différentes ;
- une même racine en « pour » et en « contre » (priorité historique à « contre ») ;
- les titres distincts égaux sous `casefold` ;
- les graphes sans grande convergence, sans racines, cycliques, avec pages manquantes ou inaccessibles ;
- sept DAG pseudoaléatoires déterministes ;
- le repli exact au-delà de **8 000 nœuds**.

Pour les deux titres ex æquo sous `casefold`, l'oracle vérifie les membres plutôt que leur ordre arbitraire dans des ensembles Python construits indépendamment. Le benchmark séparé compare l'**ordre complet** entre ancien et nouveau code *dans le même processus*, et l'algorithme original est effectivement conservé sur ce cas.

## Limites

Les cas sont **synthétiques et purement locaux**, non représentatifs de la distribution réelle des débats. Les réductions indiquées concernent `analyze_graph`, sans collecte des pages depuis MediaWiki, sans validation complète du corpus, sans traduction, sans revue humaine et sans publication. Elles ne démontrent **aucune économie de crédits Codex, de tokens ou de durée totale du workflow**.

La modification ne persiste aucun cache, ne supprime aucun contrôle et n'altère aucun champ éditorial. Le workflow de mesure GitHub temporaire est supprimé avant la fusion.
