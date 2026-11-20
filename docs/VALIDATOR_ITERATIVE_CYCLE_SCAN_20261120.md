# Détection des cycles sans limite de récursion — 20 novembre 2026

## Constat : une validation interrompue par la récursion Python

Dans `validator/src/wikidebia_validator/graph.py::validate_graph`, le parcours
des cycles du graphe argumentatif actif utilisait une fonction DFS récursive
`visit(node_id)`. Sur une chaîne de profondeur supérieure à la limite de
récursion du processus Python, le contrôle déclenchait `RecursionError`
avant la fin de la validation. La frontière défensive de `validate_package`
convertissait cette exception en diagnostic général `WDV-INT-001`.

Ce n'était pas une anomalie du graphe. Les graphes sans cycle et sans
limite de profondeur doivent pouvoir être validés, y compris quand leur
chaîne d'arguments est longue.

La [PR #174](https://github.com/wikidebates/wikidebia-project/pull/174)
remplace la récursion par une pile explicite d'itérateurs des enfants :
- parcours initial des nœuds dans le même ordre lexicographique trié ;
- exploration des relations enfants dans l'ordre du graphe d'origine ;
- conservation des couleurs DFS (blanc, gris, noir), des parcours
  disjoints et des relations parallèles ;
- même chemin pour les cycles détectés et même diagnostic `WDV-GRA-005` ;
- nœuds manquants toujours signalés par les contrôles existants ;
- indice des nœuds gris sur la pile, évitant `stack.index()` pour
  retrouver le début d'un cycle ;
- mémoire `O(profondeur)`, sans modifier la limite globale de récursion
  ni conserver d'état entre validations.

## Preuves reproduites avec l'ancien et le nouveau code

Exécution ciblée GitHub Actions :
[run #44643965873](https://github.com/wikidebates/wikidebia-project/actions/runs/44643965873)
(terminé avec succès, Python 3.12, Ubuntu 24.04).

La version d'origine a été extraite du commit
`5e1cdb85b10d19f8bb83587cc2c0218a0604c165`, chargée dans un
module séparé, puis injectée temporairement comme `validate_graph`
pour mesurer les sorties de l'ancienne implémentation. Le code corrigé
a ensuite été exécuté sur les **mêmes paquets**, sans aucune opération wiki.

**Preuve fonctionnelle :** sur le même paquet de 1 152 nœuds,
contenant une chaîne de 1 150 arguments sous une racine et aucun cycle :

| Variante | Résultat de `validate_package(scopes=['graph'])` |
| --- | --- |
| Version historique | Erreur interne `WDV-INT-001` |
| Version corrigée | 0 erreur, validation terminée ; information documentaire `WDV-DOC-001` attendue |

**Parité complète des rapports sur des graphes courants :**

| Scénario | Diagnostics historiques | Résultats identiques |
| --- | --- | --- |
| Graphe valide | `WDV-DOC-001` | Oui |
| Cycle à deux nœuds | `WDV-GRA-005`, ainsi que les erreurs indépendantes de cohérence | Oui |
| Auto-relation | `WDV-GRA-006`, `WDV-GRA-005`, puis les erreurs indépendantes | Oui |
| Plusieurs cycles et relations dupliquées | Deux `WDV-GRA-005`, doublons et erreurs indépendantes | Oui |
| Relation vers une page inexistante | `WDV-GRA-003` et erreurs indépendantes | Oui |

L'égalité porte sur **`Report.to_dict()` en entier**, notamment l'ordre des
diagnostics, le code, la gravité, les détails, les chemins/pointeurs et les
métriques du validateur. Les cinq cas ont passé l'égalité stricte.

## Régressions automatisées

Quinze cas pytest ciblés contrôlent :
- sept jeux de relations avec un oracle DFS récursif indépendant
  (l'oracle n'est exécuté que sur des graphes de petite profondeur) ;
- cinq graphes pseudoaléatoires déterministes pouvant contenir plusieurs
  cycles ;
- un paquet complet avec une chaîne dépassant la limite de récursion ;
- un paquet complet avec cycle profond, qui doit signaler
  `WDV-GRA-005` **sans** erreur `WDV-INT-001` ;
- un graphe comportant plusieurs composantes et des arêtes parallèles,
  avec contrôle de l'ordre exact des chemins signalés.

Le programme temporaire de comparaison avant/après est retiré de la
branche avant fusion. La suite complète des tests du validateur et du kit
est exécutée par la CI permanente. Les attestations signées du validateur
sont recalculées pour inclure ces nouveaux tests.

## Portée et limites

Il s'agit d'une correction de **robustesse**. Les mesures ne démontrent
pas de gain sensible de durée sur les petits graphes et ne donnent aucune
réduction des tokens, des crédits Codex ou du temps de traduction.
Le correctif ne modifie pas les fichiers éditoriaux, les schémas JSON,
les règles de publication ni les exigences de fidélité documentaire.
Les tests n'accèdent à aucun wiki et ne modifient pas le serveur Debian.
