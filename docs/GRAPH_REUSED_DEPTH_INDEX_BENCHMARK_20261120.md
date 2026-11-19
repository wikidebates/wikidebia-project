# Index des arguments réutilisés par niveau — 20 novembre 2026

## Problème mesuré et correction

Dans `kit/scripts/wikidebia_graph_extract.py::analyze_graph`, les champs
`occurrences_reutilisees_par_niveau` et
`pages_concernees_par_reutilisation_au_niveau` signalent les arguments réutilisés
à différentes profondeurs. L'algorithme historique parcourait l'ensemble des
nœuds **pour chaque niveau possédant un surplus d'occurrences** afin d'identifier
les titres concernés.

Le coût est `O(N × Lr)`, où `N` est le nombre de nœuds et `Lr` le nombre de
niveaux présentant une réutilisation. Un graphe très profond sans réutilisation
n'effectuait pas ces balayages répétés : il serait trompeur d'y annoncer un
gain quadratique. En revanche, lorsqu'une longue chaîne est partagée entre
plusieurs arguments principaux, presque tous les niveaux présentent un surplus.

La [PR #172](https://github.com/wikidebates/wikidebia-project/pull/172)
construit un index **en un seul parcours des occurrences réellement présentes** :
pour chaque titre et chaque niveau renseigné dans son compteur, le titre est
ajouté uniquement s'il apparaît à un niveau postérieur au minimum ou si le
compteur au niveau courant dépasse une occurrence. Les mêmes niveaux sont
ensuite émis en ordre croissant, avec le même tri `str.casefold` des titres.
Le décompte des surplus reste inchangé et indépendant de l'index. Les graphes
cycliques conservent leurs rapports de réutilisation vides.

Cette optimisation ne modifie pas les pages, les graphes, les occurrences,
la traduction, les preuves cryptographiques ni les conditions de publication.

## Protocole

Deux mesures successives sur des runners Ubuntu 24.04 / Python 3.12 de
GitHub Actions :
- [run initial #44640741634](https://github.com/wikidebates/wikidebia-project/actions/runs/44640741634) ;
- [run répété #44640845487](https://github.com/wikidebates/wikidebia-project/actions/runs/44640845487).

Le code antérieur est **fixé** au commit `1847bd8e31bfe40d1e340293764d2929814f64a8`.
Les deux modules sont chargés dans le même processus, avec exactement le
même objet `CrawlResult`. Trois à treize essais alternent ancien et nouveau
code suivant le scénario. Après chaque paire, **toutes les clés et valeurs de
`analyze_graph` sont comparées strictement**, pas seulement le rapport des
réutilisations.

Les graphes synthétiques testés incluent une chaîne simple (sans réutilisation),
une chaîne avec raccourci (réutilisation ponctuelle), une chaîne profonde
partagée par huit racines (réutilisation à chaque niveau), des racines larges
avec un seul enfant chacune, et un DAG en couches.

Toutes les mesures sont **hors réseau**, sans lecture/écriture wiki et sans
traduction. Les temps ci-dessous ne mesurent que l'analyse du graphe,
pas le temps d'extraction MediaWiki, de validation, de revue ou de publication.

## Résultats — deuxième campagne (reprise pour éliminer le bruit)

| Scénario | Taille | Avant (s) | Après (s) | Réduction |
| --- | ---: | ---: | ---: | ---: |
| Chaîne partagée, 8 racines | 240 | 0,005444 | 0,002870 | 47,28 % |
| Chaîne partagée, 8 racines | 800 | 0,038081 | 0,009990 | 73,77 % |
| Chaîne partagée, 8 racines | 2 000 | 0,208829 | 0,025436 | 87,82 % |
| Chaîne partagée, 8 racines | 4 000 | 0,768644 | 0,065773 | 91,44 % |
| Chaîne sans partage | 240 | 0,002337 | 0,002424 | −3,72 % |
| Chaîne sans partage | 800 | 0,008509 | 0,008592 | −0,98 % |
| Chaîne sans partage | 2 000 | 0,021729 | 0,021815 | −0,40 % |
| Chaîne sans partage | 4 000 | 0,054955 | 0,047072 | 14,34 % |
| Chaîne à raccourci | 240 | 0,002409 | 0,002476 | −2,78 % |
| Chaîne à raccourci | 800 | 0,008564 | 0,008713 | −1,74 % |
| Chaîne à raccourci | 2 000 | 0,021991 | 0,022101 | −0,50 % |
| Racines larges | 300 racines, 600 nœuds | 0,006130 | 0,006011 | 1,94 % |
| DAG en couches | 22 × 24 nœuds | 0,007926 | 0,007475 | 5,69 % |

Les résultats de la **première campagne** sur les chaînes partagées étaient
également positifs : 240 (48,95 %), 800 (75,47 %), 2 000 (89,53 %)
et 4 000 nœuds (93,37 %). Les temps absolus différaient entre runners :
le gain robuste porte sur les comparaisons *appariées* d'une même exécution,
et non sur des valeurs absolues à transférer d'un runner à un autre.

### Échantillons bruts de la deuxième campagne (secondes)

Dans chaque paire : ancien code ; nouveau code.

- Partagée 240 : `[0.006132,0.005444,0.005403,0.005336,0.005703]` ; `[0.002990,0.002870,0.002662,0.008444,0.002709]`.
- Partagée 800 : `[0.038081,0.037621,0.038429,0.037778,0.038391]` ; `[0.009471,0.009990,0.017016,0.010078,0.009432]`.
- Partagée 2 000 : `[0.210779,0.209658,0.203543,0.200924,0.211849,0.208829,0.203696]` ; `[0.026208,0.025436,0.036429,0.024784,0.025265,0.025005,0.036177]`.
- Partagée 4 000 : `[0.770417,0.768644,0.776034,0.754843,0.774968,0.756182,0.768218]` ; `[0.070852,0.053232,0.068342,0.065626,0.067354,0.064399,0.065773]`.
- Sans partage 240 : `[0.002378,0.002274,0.002415,0.002310,0.002337]` ; `[0.002773,0.002424,0.002349,0.002425,0.002335]`.
- Sans partage 800 : `[0.015143,0.008412,0.008509,0.008374,0.014053]` ; `[0.008817,0.008650,0.008537,0.008592,0.008260]`.
- Sans partage 2 000 : `[0.022921,0.027979,0.029235,0.028072,0.021729,0.020737,0.021576,0.020796,0.028381,0.027766,0.021489,0.020887,0.021721]` ; `[0.030154,0.025957,0.021062,0.021815,0.020930,0.028955,0.028081,0.021595,0.021358,0.021772,0.021022,0.028690,0.027741]`.
- Sans partage 4 000 : `[0.055778,0.053049,0.054955,0.053459,0.056913,0.053991,0.057969,0.053958,0.058371]` ; `[0.057772,0.046650,0.055676,0.045844,0.059004,0.047072,0.045313,0.056106,0.044918]`.
- Raccourci 240 : `[0.004268,0.008381,0.002409,0.002310,0.002405]` ; `[0.002403,0.002476,0.002343,0.002528,0.002479]`.
- Raccourci 800 : `[0.008320,0.008404,0.008836,0.008564,0.008686]` ; `[0.008288,0.008902,0.015759,0.008713,0.008613]`.
- Raccourci 2 000 : `[0.029474,0.028815,0.021928,0.020849,0.021438,0.020848,0.028590,0.028187,0.021529,0.021037,0.029353,0.028849,0.021991]` ; `[0.021362,0.022198,0.021297,0.028673,0.028103,0.022101,0.021362,0.022201,0.021287,0.028737,0.021099,0.022147,0.021289]`.
- Racines larges : `[0.007679,0.005848,0.011926,0.005955,0.006130]` ; `[0.005976,0.006117,0.006011,0.006394,0.006007]`.
- DAG en couches : `[0.007926,0.007778,0.013841,0.007792,0.008006]` ; `[0.007475,0.007651,0.007302,0.007587,0.007316]`.

## Contrôles de non-régression et limites

**18 cas pytest ciblés**, dont sept DAG aléatoires déterministes,
comparent le rapport des réutilisations à un **oracle indépendant**
implémentant l'ancien balayage. Ils couvrent les losanges, les niveaux
multiples d'un même argument racine, les relations parallèles, les
cycles, les pages manquantes, les nœuds inaccessibles, les collisions de
casse dans le tri, les chaînes avec raccourci, les grandes chaînes
partagées par deux ou huit racines, les débats sans racines et les
longues chaînes sans réutilisation.

Les écarts sous quelques millisecondes montrent des fluctuations de
runner ; aucune accélération systématique n'est revendiquée pour les
graphes sans réutilisation. Le gain fort concerne les graphes
profonds où **des nœuds sont effectivement réutilisés à beaucoup de
niveaux**. Les mesures n'impliquent aucun changement de qualité de
traduction ni d'économie démontrée de tokens, de crédits Codex ou
de temps de publication.

Le workflow de benchmark temporaire a été retiré de la branche avant
fusion, afin de ne pas alourdir les CI permanentes.
