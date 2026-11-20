# Index local des titres affichés français historiques — 20 novembre 2026

## Constat

Le validateur `validator/src/wikidebia_validator/graph.py` vérifie que les
**titres affichés historiques** (notamment ceux contenant une apostrophe
typographique) restent inchangés lorsqu'une page française préexistante est
conservée. La fonction `_locked_preexisting_displayed_title` lit le verrou
`data/fr_page_metadata_lock.json` et cherche la première ligne `arguments`
correspondant à l'identifiant du nœud.

Avant la [PR #176](https://github.com/wikidebates/wikidebia-project/pull/176),
pour chaque titre candidat, cette recherche recommençait au début du tableau,
même si `PackageContext` avait déjà chargé le JSON. Un import historique
de nombreux arguments avec titres affichés contenant des apostrophes pouvait
ainsi déclencher des parcours répétés de taille quadratique.

## Correction — sans modification du contrat éditorial

Pour les tableaux `arguments` comprenant au moins 32 éléments, la
vérification dispose d'un index **strictement local à un appel de
`validate_graph`**. Cet index associe chaque `entity_id` à la **première**
ligne rencontrée (`dict.setdefault`). Pour les tableaux courts ou d'un
type inattendu, l'ancien parcours linéaire reste en place.

À chaque titre candidat, le code conserve toutes les vérifications
préexistantes :

- langue française uniquement ;
- existence du verrou par `ctx.exists`, puis lecture par `ctx.load_json` ;
- correspondance exacte du schéma
  `wikidebia-fr-page-metadata-lock-1.0` ;
- `page_origin == preexisting` ;
- `decisions.displayed_title == keep` ;
- correspondance **exacte** du titre affiché dans le verrou et le graphe.

Les identifiants dupliqués continuent à respecter la **première** ligne,
même si une entrée ultérieure accorderait à tort une conservation.
L'index est recalculé quand l'objet JSON, sa liste `arguments` ou sa taille
change pendant la validation ; les références aux lignes existantes restent
vivantes pour les modifications des décisions. Aucun cache n'est persistant,
aucun contrôle de hachage, de source ou de publication n'est supprimé.

## Mesure reproductible

GitHub Actions
[run #44703387071](https://github.com/wikidebates/wikidebia-project/actions/runs/44703387071),
succès, runner Ubuntu 24.04 et Python 3.12.

L'ancienne implémentation, fixée au commit
`f3648d179db1aa7fd97cbe1d9c9752a51da79def`, et l'implémentation
indexée ont été chargées simultanément dans le même processus. Les deux
ont validé **exactement les mêmes paquets synthétiques** sous
`validate_package(scopes=['graph'])`.

Chaque scénario a été chronométré avec quatre ou six répétitions
**alternées** ancien/nouveau. Après chaque paire, l'intégralité de
`Report.to_dict()` est comparée et reste **strictement identique** :
résultat, diagnostics, gravités, messages, détails, pointeurs, ordre des
signalements et métriques. Les scénarios de refus et de doublon ont
également été comparés sans aucune différence.

| Scénario | Nœuds / lignes de verrou | Avant (s) | Après (s) | Réduction |
| --- | ---: | ---: | ---: | ---: |
| Titres historiques conservés, petit graphe | 122 / 122 | 0,0141870 | 0,0137460 | 3,11 % |
| Titres historiques conservés, graphe moyen | 352 / 352 | 0,0441340 | 0,0403015 | 8,68 % |
| Titres historiques conservés, grand graphe | 702 / 702 | 0,0980785 | 0,0836995 | **14,66 %** |
| Titres historiques conservés, graphe profond | 1102 / 1102 | 0,1676130 | 0,1356025 | **19,10 %** |
| Certaines conservations refusées | 452 / 452 | 0,0561790 | 0,0503635 | 10,35 % |
| Première ligne dupliquée non admissible | 452 / 453 | 0,0557475 | 0,0503980 | 9,60 % |

Le scénario de refus émet 66 constatations, conservées à l'identique.
Le scénario de doublon conserve deux constatations (dont le refus de
l'exception pour la première entrée dupliquée).

### Échantillons bruts (secondes)

D'abord la version historique, ensuite la version indexée :

- Petit, 122 nœuds : `[0.015153,0.014077,0.014403,0.014100,0.014247,0.014127]` ; `[0.013739,0.013844,0.013753,0.013730,0.022571,0.013713]`.
- Moyen, 352 nœuds : `[0.043934,0.044334,0.043797,0.044365,0.044644,0.043852]` ; `[0.040213,0.040249,0.040816,0.040212,0.040354,0.050474]`.
- Grand, 702 nœuds : `[0.096067,0.098173,0.098386,0.098417,0.097984,0.097711]` ; `[0.082876,0.094620,0.083422,0.083416,0.084568,0.083977]`.
- Profond, 1102 nœuds : `[0.165095,0.168365,0.166861,0.179882]` ; `[0.135496,0.135709,0.133445,0.136238]`.
- Refus, 452 nœuds : `[0.055670,0.056003,0.057081,0.055583,0.067247,0.056355]` ; `[0.051217,0.050126,0.049948,0.050575,0.050152,0.051015]`.
- Doublon, 452 nœuds : `[0.056006,0.054952,0.055512,0.056886,0.055224,0.055983]` ; `[0.050395,0.050107,0.050401,0.060985,0.050769,0.049449]`.

## Vérifications de sécurité et de non-régression

**20 cas pytest ciblés** vérifient :
- l'acceptation de nombreux titres affichés *réellement* conservés ;
- les doublons d'identifiants, où la première ligne est autoritaire ;
- le refus des pages nouvellement créées et des décisions
  `modify`/`review` ;
- le rejet des langues autres que le français ;
- le rejet des verrous absents ou non conformes au schéma ;
- le maintien du chemin historique pour les petits tableaux ;
- la prise en compte des modifications de champs, du remplacement
  du document et de l'ajout de lignes ;
- cinq jeux de décisions aléatoires déterministes comparés à
  l'ancienne recherche linéaire ;
- deux validations `graph` complètes : conservation conforme acceptée,
  titre divergent refusé avec le code `WDV-GRA-016` et le pointeur exact.

## Limites

Le benchmark se limite à la **portée `graph`** du validateur, sur des
données synthétiques. Il ne représente pas la durée d'une création ou
traduction complète, les autres portées JSON Schema, la collecte
MediaWiki, la fidélité des traductions ni la publication. Les gains ne
s'ajoutent pas mécaniquement aux précédentes optimisations du validateur
et ne démontrent aucune réduction de tokens ou de crédits Codex.

Le workflow de mesure temporaire est supprimé avant la fusion ;
les attestations et le manifeste signés du validateur sont régénérés et
vérifiés par la CI complète. Aucun wiki ni serveur Debian n'est modifié.
