# Optimisation des statistiques par racine dans `analyze_graph` — 20 novembre 2026

## Constat

L'extracteur `kit/scripts/wikidebia_graph_extract.py` prépare un graphe d'arguments depuis des pages MediaWiki, puis calcule des statistiques de graphe avec `analyze_graph`. Le nombre d'occurrences dépliées, la profondeur maximale et le nombre de pages distinctes sont calculés **pour chaque argument principal**.

Dans l'implémentation antérieure, chaque racine entraînait (1) une recherche des descendants, (2) l'allocation d'un `Counter` de profondeurs pour **tous** les nœuds du graphe, (3) une propagation des compteurs sur l'intégralité de l'ordre topologique. Cette répétition a un coût élevé quand le débat comporte de nombreux arguments principaux ou que plusieurs racines partagent des descendants.

## Correction

La [PR #171](https://github.com/wikidebates/wikidebia-project/pull/171) utilise les propriétés mathématiques d'un graphe orienté **sans cycle** :

- Le nombre d'occurrences dépliées à partir d'un nœud vaut `1 + somme(occurrences de chaque enfant)`. Les relations multiples entre deux mêmes nœuds comptent séparément, comme auparavant.
- La profondeur maximale de ce nœud vaut `1 + maximum(profondeur de chaque enfant)`. Ces deux informations sont calculées **une fois**, en ordre topologique inverse, puis lues pour chaque racine.
- Les **pages distinctes** doivent être comptées autrement que les chemins. Pour un graphe comprenant au moins huit racines et au plus 8 000 nœuds, un ensemble compact de bits par nœud mémorise exactement ses descendants ; la cardinalité est obtenue par `bit_count()`. La limite de taille borne la mémoire des masques à quelques mégaoctets. En dessous de huit racines ou au-delà de 8 000 nœuds, une recherche DFS classique est conservée pour cette seule statistique.
- Lorsqu'un cycle est présent, la construction des lignes statistiques par racine reste ignorée, conformément au comportement antérieur. Les compteurs **par nœud et par niveau**, utiles pour les autres contrôles, ne sont pas modifiés.

Les sorties concernant les arguments, les racines pour/contre, les relations, les occurrences, les titres, les références existantes, les avertissements, les contrôles d'intégrité et la publication demeurent inchangées.

## Benchmark hors ligne

- [GitHub Actions #44639262168](https://github.com/wikidebates/wikidebia-project/actions/runs/44639262168), succès, runner Ubuntu 24.04, Python 3.12.
- Ancien code fixé au commit `0b1181720a79eedfc32ad579c797dc63749437e8`, dernière version de `main` avant cette correction.
- Anciens et nouveaux modules chargés séparément, avec le **même** objet `CrawlResult` synthétique ; aucun accès au réseau ni aux wikis.
- Des graphes de types variés : branches indépendantes, longues chaînes partagées, nombreuses connexions en losange et une seule branche profonde.
- Cinq essais alternés par version pour les petits cas et trois pour les plus grands. Les valeurs indiquées sont des **médianes** de `analyze_graph` complet.
- À chaque essai, **toutes les clés et valeurs** du graphe produit sont comparées par égalité stricte, pas seulement `branches_niveau_1`. Les résultats sont identiques pour chaque paire.

| Structure | Racines | Nœuds | Avant (s) | Après (s) | Réduction |
| --- | ---: | ---: | ---: | ---: | ---: |
| Branches indépendantes | 120 | 240 | 0,019724 | 0,002246 | 88,61 % |
| Branches indépendantes | 300 | 600 | 0,116196 | 0,005511 | 95,26 % |
| Branches indépendantes | 700 | 1 400 | 0,710978 | 0,012986 | 98,17 % |
| Chaîne partagée | 20 | 240 | 0,010721 | 0,005302 | 50,55 % |
| Chaîne partagée | 80 | 520 | 0,067262 | 0,019908 | 70,40 % |
| Losanges partagés | 12 | 92 | 0,011676 | 0,002961 | 74,64 % |
| Losanges partagés | 25 | 155 | 0,053130 | 0,006857 | 87,09 % |
| Une seule longue chaîne | 1 | 1 201 | 0,013299 | 0,012501 | 6,00 % |

### Échantillons complets (secondes)

Ancien code, puis nouveau code :

- Branches indépendantes, 120 racines : `[0.019807,0.019619,0.019724,0.019653,0.019930]` ; `[0.002307,0.002223,0.002017,0.002246,0.002260]`.
- Branches indépendantes, 300 racines : `[0.117502,0.116988,0.116148,0.116017,0.116196]` ; `[0.012742,0.005811,0.005275,0.005511,0.005367]`.
- Branches indépendantes, 700 racines : `[0.696230,0.710978,0.720423]` ; `[0.012986,0.020477,0.012663]`.
- Chaîne partagée, 20 racines : `[0.011435,0.015358,0.010643,0.010721,0.010614]` ; `[0.005231,0.005216,0.005335,0.005302,0.005331]`.
- Chaîne partagée, 80 racines : `[0.066673,0.067262,0.067333]` ; `[0.019452,0.019908,0.019925]`.
- Losanges, 12 racines : `[0.011955,0.011728,0.011676,0.011571,0.011666]` ; `[0.002927,0.003047,0.002893,0.002961,0.007449]`.
- Losanges, 25 racines : `[0.053292,0.052997,0.053130]` ; `[0.006736,0.007459,0.006857]`.
- Une seule chaîne, une racine : `[0.012973,0.019609,0.013299,0.013114,0.019831]` ; `[0.012359,0.013060,0.012440,0.012855,0.012501]`.

## Tests de non-régression

**17 cas ciblés** vérifient les occurrences et pages distinctes d'un losange, une racine elle-même réutilisée sous une autre racine, des relations parallèles vers le même enfant, les racines présentes à la fois en *pour* et *contre*, plusieurs racines partageant une chaîne avec chemins multiples, un graphe cyclique, une page manquante, une chaîne profonde, six graphes acycliques aléatoires à partage de nœuds, un débat anglais déjà existant sans racine, le repli en mode DFS au-dessus de 8 000 nœuds et la présence de nœuds isolés/inaccessibles.

La comparaison avec l'ancien `analyze_graph` s'ajoute à ces tests et couvre l'égalité de toute la structure résultante, y compris les propriétés historiques, les occurrences par niveau, les compteurs de réutilisation et les orientations.

## Limites

Les essais sont synthétiques et isolent **l'analyse du graphe**. Ils ne mesurent pas la récupération des pages MediaWiki, le parsing du wikicode en amont, l'initialisation du corpus, le validateur, la traduction, la revue ou la publication. Les gains sont nettement plus faibles pour un débat avec une unique racine ; ils ne doivent pas être interprétés comme une réduction équivalente de la durée totale d'une création/traduction ou de la consommation de tokens.

Les calculs combinatoires restent exacts sur les graphes sans cycle, même lorsqu'un descendant est emprunté par plusieurs chemins. Les graphes cycliques conservent l'état de non-validation antérieur. Aucun wiki ni serveur n'a été modifié ; le workflow de benchmark temporaire est supprimé avant fusion de la PR.
