# Parcours des grandes frontières de graphe : déduplication sans balayage quadratique — 20 novembre 2026

## Constat dans l'extracteur

`kit/scripts/wikidebia_graph_extract.py::crawl_graph` lit les arguments français à partir d'un débat MediaWiki (en mode lecture seule). Pour conserver l'ordre des racines et des arguments d'un même niveau, il utilisait des listes. Deux tests d'appartenance étaient effectués pour chaque candidat :

- `canonical not in destination` lors de la construction des listes de racines *pour* et *contre* ;
- `title not in frontier` lors de la construction de chaque niveau de parcours en largeur.

Pour des niveaux contenant de nombreux arguments, ces tests d'appartenance aux listes ont un coût potentiellement quadratique.

La [PR #170](https://github.com/wikidebates/wikidebia-project/pull/170) conserve les listes ordonnées utilisées par le graphe, mais maintient en parallèle un ensemble distinct de titres déjà vus pour chaque orientation de racines et pour chaque niveau. Chaque nouvelle appartenance est vérifiée dans l'ensemble, sans modifier l'ordre, le nombre de pages demandées, la gestion des redirections, les relations, les avertissements ou les limites de sécurité.

## Mesures de bout en bout du parcours hors réseau

- Exécution : [GitHub Actions #44638020067](https://github.com/wikidebates/wikidebia-project/actions/runs/44638020067), Ubuntu 24.04 / Python 3.12, succès.
- Baseline : commit `5100395b819e7f7bb40df50882a52f7f54366e1e`, précédant ce changement.
- Les deux modules Python sont chargés séparément, sans modifier les mécanismes de parsing ou d'analyse. Chaque mesure appelle la fonction complète `crawl_graph` avec un **faux client de lecture** déterministe (aucune API MediaWiki ou connexion réseau).
- Deux formes synthétiques : (1) de nombreux arguments principaux listés dans le débat ; (2) une seule racine avec de nombreux arguments enfants dans les `Justification`. Les arguments enfants sont des feuilles.
- Tailles : 120, 300, 700 arguments, six essais alternés par variante ; 2 000 et 4 000 arguments, quatre essais alternés par variante.
- Pour chaque paire, **tous les champs** du résultat de crawl sont comparés après conversion des dataclasses en dictionnaires, ainsi que **tous les appels `fetch_many` et les titres de chaque lot**. Ils sont strictement identiques.
- Les temps en secondes ci-dessous sont des **médianes** et incluent le parsing du wikicode et le parcours complet, mais excluent les délais de réseau, l'analyse `analyze_graph`, la production des snapshots, la revue, la traduction et la publication.

| Arguments | Disposition | Avant (s) | Après (s) | Gain |
| --- | --- | ---: | ---: | ---: |
| 120 | Racines | 0,026567 | 0,026625 | −0,22 % |
| 120 | Enfants | 0,026598 | 0,0266915 | −0,35 % |
| 300 | Racines | 0,066761 | 0,066244 | 0,77 % |
| 300 | Enfants | 0,066022 | 0,066113 | −0,14 % |
| 700 | Racines | 0,157560 | 0,1543515 | 2,04 % |
| 700 | Enfants | 0,1549925 | 0,1535125 | 0,95 % |
| 2 000 | Racines | 0,4689875 | 0,4449215 | 5,13 % |
| 2 000 | Enfants | 0,453771 | 0,440614 | 2,90 % |
| 4 000 | Racines | 0,996045 | 0,8830595 | 11,34 % |
| 4 000 | Enfants | 0,943244 | 0,8905635 | 5,59 % |

### Échantillons bruts (secondes)

Chaque ligne contient la série de l'ancienne version suivie de celle utilisant les ensembles.

- 120 racines : `[0.027098,0.026608,0.026626,0.026526,0.026523,0.026447]` ; `[0.027166,0.026962,0.026718,0.026532,0.026462,0.026497]`.
- 120 enfants : `[0.026625,0.026502,0.026650,0.026353,0.027582,0.026571]` ; `[0.026644,0.026739,0.026741,0.026395,0.026571,0.026740]`.
- 300 racines : `[0.066382,0.067212,0.066792,0.066730,0.070243,0.066411]` ; `[0.066041,0.066257,0.066189,0.066480,0.066231,0.066493]`.
- 300 enfants : `[0.065798,0.066000,0.065884,0.066178,0.066044,0.066325]` ; `[0.065932,0.066079,0.066147,0.066155,0.066053,0.066357]`.
- 700 racines : `[0.157364,0.157299,0.157756,0.157868,0.162319,0.157295]` ; `[0.154278,0.154181,0.155013,0.154425,0.154559,0.153935]`.
- 700 enfants : `[0.155622,0.160304,0.154966,0.155019,0.154870,0.154671]` ; `[0.153244,0.153414,0.153596,0.153526,0.158440,0.153499]`.
- 2 000 racines : `[0.468447,0.469626,0.469350,0.468625]` ; `[0.450048,0.441433,0.441971,0.447872]`.
- 2 000 enfants : `[0.458711,0.451050,0.456492,0.449525]` ; `[0.441926,0.445517,0.438483,0.439302]`.
- 4 000 racines : `[0.996078,0.994198,0.996012,1.007439]` ; `[0.879467,0.879526,0.892624,0.886593]`.
- 4 000 enfants : `[0.935240,0.944489,0.941999,0.945896]` ; `[0.878238,0.889881,0.894631,0.891246]`.

## Contrôles supplémentaires

Six tests pytest couvrent notamment :
- la préservation du premier ordre des racines malgré les alias redirigés et les doublons (pour et contre sont distincts) ;
- un enfant partagé : une seule lecture/analyse, mais les deux relations restent représentées ;
- un niveau très large de racines, sans omission ni changement de lot ;
- un niveau très large d'enfants, sans omission ni changement de lot ;
- le refus du dépassement du plafond de pages ;
- la conservation des indications de provenance d'une page absente.

## Limites et décision

Les écarts à 120 et 300 arguments sont proches de la variance de mesure, et la variante utilisant les ensembles peut y être légèrement plus lente : **aucun gain significatif n'est affirmé pour ces petites tailles**. L'amélioration augmente avec la largeur des niveaux, ce qui concorde avec la suppression du coût quadratique. Les niveaux de 4 000 arguments sont un cas défavorable volontairement synthétique, proche du plafond normal de 5 000 pages ; ce scénario n'est pas une moyenne représentative des débats réels.

La modification ne crée aucun cache persistant et ne modifie pas les appels MediaWiki, la traduction, les autorisations, les contrôles d'intégrité ni les exports. Elle rend une déduplication locale plus efficace. Les chiffres ne mesurent ni le temps de réseau réel ni la consommation de tokens ou de crédits Codex. Le workflow de benchmark provisoire n'est pas intégré dans `main`.
