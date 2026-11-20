# Accélération attestée des conditions JSON Schema du registre — 20 novembre 2026

## Origine : le coût restant après la PR #185

Le [profilage du validateur sur une extraction réelle figée de 680 arguments](https://github.com/wikidebates/wikidebia-project/issues/153#issuecomment-7041334536), réalisé sous Python 3.13.5 sur Debian, situait la validation de `argument_registry.schema.json` autour de **0,819 seconde** par appel instrumenté, avant la PR #185. La [PR #185](https://github.com/wikidebates/wikidebia-project/pull/185) a ensuite réduit de **4,86 %** la durée de préparation initiale complète sur cette extraction réelle, sans modifier les pages construites.

Le profil `cProfile` a aussi révélé des milliers de passages dans le mot-clé JSON Schema `if` et ses sous-validations `properties` / `const` / `enum`. De nombreuses clauses répétées à chaque argument sont simplement des conditions de statut : `generation.status`, `file.status`, `wiki.check_status`, `interlanguage.status`, `title_status` ou `occurrence_role`.

## Implémentation : seuls les cas prouvés sont raccourcis

La [PR #186](https://github.com/wikidebates/wikidebia-project/pull/186) ajoute `_guarded_registry_status_if` dans `validator/src/wikidebia_validator/schema_validation.py`. L'optimisation concerne **49 clauses** du registre **développé en mémoire**, identifiées sur le schéma exact déjà attesté. Elles ont exclusivement la forme suivante, où la propriété de statut contient soit une constante textuelle, soit une énumération de chaînes :

```json
{
  "if": {
    "properties": {
      "status": {"enum": ["generated", "validated"]}
    }
  },
  "then": {"properties": {"generated_at": {"type": "string"}}}
}
```

Quand le document est un objet et que la propriété considérée existe avec une **valeur textuelle**, l'évaluation de `if` revient exactement à vérifier la constante ou l'appartenance à l'énumération. La branche `then` ou `else`, si elle existe, reste exécutée avec `validator.descend(..., schema_path="then"/"else")`, **sans aucune simplification de ses contraintes**. Les erreurs produites, leur contexte, pointeur, gravité et ordre restent donc les mêmes.

Les conditions absentes, valeurs nulles, booléennes, numériques, objets ou tableaux, clauses altérées, structures inconnues et toutes les conditions non attestées utilisent **intégralement le gestionnaire `if` d'origine de `jsonschema`**. En particulier, le contrôle numérique `depth` n'est **pas** accéléré et conserve la sémantique native des entiers/booléens. Les cas où la propriété est absente sont toujours évalués par le moteur original, car `properties` sans `required` accepte une propriété absente.

### Bornes de sécurité

Le gestionnaire n'est construit **que si tous les critères suivants sont satisfaits** :

1. Les versions exécutées sont exactement `jsonschema==4.26.0` et `referencing==0.37.0`.
2. Le registre normatif et le schéma commun présentent les **empreintes canoniques SHA-256 exactes** déjà attestées par les PR #178/#179.
3. L'expansion contrôlée des références du schéma commun (PR #179) a réussi : ni cycle, ni résolution ambiguë, ni changement de portée.
4. Le premier gestionnaire accéléré `oneOf` de la PR #185 a été construit avec succès ; s'il renonce à ses preuves, **toutes** les nouvelles optimisations sont refusées, selon le garde-fou préexistant.
5. Le schéma développé contient exactement **49 clauses admissibles**, et le moteur d'origine fournit un gestionnaire `if`.
6. Lors de **chaque** application du chemin court, l'identité, la forme complète et la valeur de la condition sont revérifiées, évitant qu'une modification en mémoire d'un objet compilé conserve un raccourci périmé.

Toute modification du registre, de `common.schema.json` ou de l'attestation invalide déjà le validateur compilé dans `SchemaStore` et rétablit les contrôles normatifs. **Aucun fichier JSON Schema n'est modifié**, aucun cache inter-session n'est ajouté et aucune validation d'instance n'est supprimée du parcours global.

Les contrôles de provenance, des empreintes de fichiers, des reçus, des sauvegardes, du graphe, des verrous français et de la revue éditoriale/bilingue ne changent pas. Aucune logique de traduction ni de publication n'est touchée.

## Mesures sous Python 3.12 sur corpus synthétiques

Le [prototype initial — GitHub Actions #44754385859](https://github.com/wikidebates/wikidebia-project/actions/runs/44754385859) utilisait 7 répétitions alternées et a mesuré un gain d'environ **16,87 %** à 680 arguments ; les rapports complets du corpus valide et de **14 variantes invalides** étaient identiques.

Plus important, le **code de production proposé**, comparé à **lui-même avec le seul nouveau gestionnaire désactivé** (la PR #185 reste active dans les deux variantes), a été évalué dans [GitHub Actions #44755650630](https://github.com/wikidebates/wikidebia-project/actions/runs/44755650630) : **sept répétitions alternées par variante, même version de schémas et de bibliothèques, cinq portées de validation `schema`, `coherence`, `graph`, `files`, `workflow`**.

| Arguments synthétiques | Avant (médiane) | Avec raccourci (médiane) | Gain |
| ---: | ---: | ---: | ---: |
| 40 | 0,058866 s | 0,051486 s | 12,54 % |
| 300 | 0,365231 s | 0,303007 s | 17,04 % |
| 680 | 0,818513 s | 0,682793 s | **16,58 %** |

Tous les rapports `Report.to_dict()` des corpus valides sont **strictement identiques** entre les variantes. L'exécution n'a pas accédé aux wikis ; elle n'a pas exploité de source historique réelle ou de traduction. Le gain de cette nouvelle PR sur Debian Python 3.13.5 et sur un corpus réel **reste à mesurer séparément**, sans extrapolation à partir d'Ubuntu.

## Régressions et reprise

`validator/tests/test_registry_status_if_fastpath.py` ajoute **131 cas de test** : dix propriétés de statut × dix valeurs (branches textuelles admissibles, inconnues, vides, absentes, nulles et de types erronés), sept champs de branche × trois charges utiles, plus les vérifications de l'attestation, des modifications en mémoire, de l'échec du garde-fou `oneOf`, de la métavalidation des schémas modifiés et des contextes d'erreur `then`/`else`. Chaque cas exécuté sur un corpus synthétique compare les **rapports complets** avec et sans ce gestionnaire, tandis que toutes les optimisations précédentes sont conservées.

Le total des tests du validateur passe de **671 à 802** (à confirmer systématiquement par la CI), et le manifeste de distribution, le reçu et les comptes dans les rapports d'auto-audit doivent être réactualisés ensemble. L'expérience GitHub Actions temporaire ne doit pas rester dans `main`.

Une fois cette PR fusionnée, la comparaison sur le serveur Debian devra isoler la nouvelle optimisation en partant du commit `6732420dc4f5ee589e95af6581336f3b1e87aa52`, sur **la même extraction figée** et avec **des contrôles d'empreinte et de reçus intégralement conservés**. Les gains ne s'appliquent qu'à la préparation technique et ne mesurent ni le temps de traduction ni la consommation de tokens ou crédits Codex.
