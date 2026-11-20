# Accélération du registre : alternatives null/string strictement exclusives — 20 novembre 2026

## Motivation : profilage du serveur réel

À la suite de [l'issue #153](https://github.com/wikidebates/wikidebia-project/issues/153#issuecomment-7041334536) et de la [PR #184](https://github.com/wikidebates/wikidebia-project/pull/184), un profilage effectué par l'exploitant sur une extraction réelle figée de **680 arguments**, sous **Python 3.13.5**, a identifié les coûts suivants (médianes de trois passages, sans contenu de corpus transféré) :

- lancement complet du validateur en sous-processus : **1,057765 s** ;
- appel Python direct instrumenté : **0,938754 s** ;
- portée `schema` : **0,873177 s** ;
- seul schéma `argument_registry.schema.json` : **0,818801 s** (environ **87 %** du temps Python instrumenté) ;
- portée `graph` : **0,058230 s**.

Le reste du validateur est beaucoup plus léger ; accélérer les empreintes ou la provenance ne répondrait pas au principal goulot d'étranglement. Le profil `cProfile` a mis en évidence de nombreux appels `oneOf` au sein de l'évaluation du registre.

## Correction proposée : conserver le schéma et les diagnostics d'origine

Une expérimentation de la [PR #185](https://github.com/wikidebates/wikidebia-project/pull/185) a d'abord envisagé de réécrire temporairement des `oneOf` en `anyOf` lorsque les branches sont exclusives. Elle apportait un gain mesurable, mais risquait de changer les **messages et contextes d'erreur** des entrées invalides si le validateur de référence n'était pas relancé.

La variante retenue est plus conservatrice : **aucun fichier JSON Schema n'est modifié, aucun schéma n'est réécrit en mémoire, et aucune validation d'instance n'est supprimée à l'échelle du registre**.

Le validateur JSON Schema peut être muni, uniquement dans le contexte attesté ci-dessous, d'un gestionnaire `oneOf` à chemin positif court pour **23 clauses** dont la forme exacte est :

```json
{"oneOf": [{"type": "null"}, {"type": "string", "...": "..."}]}
```

L'ordre des deux branches peut être inversé. Pour une valeur `null`, la branche `null` réussit et la branche `string` ne peut pas réussir ; le `oneOf` est donc vrai sans vérification supplémentaire. Pour une chaîne, la branche `null` ne peut pas réussir : une évaluation complète de la branche `string`, via le moteur officiel `validator.descend`, suffit **uniquement lorsqu'elle ne signale aucune erreur**. Pour une valeur invalide, un type différent, une branche modifiée ou tout autre cas non prouvé, le gestionnaire appelle le **`oneOf` original de `jsonschema`**, avec ses mêmes messages, détails, pointeurs et contextes de sous-erreurs.

Cette optimisation requiert **simultanément** :

1. `jsonschema==4.26.0` et `referencing==0.37.0` ;
2. les empreintes SHA-256 exactes déjà attestées du registre et de `common.schema.json` (PR #178) ;
3. l'expansion sûre et complète des références communes du registre (PR #179), dont les protections contre les cycles, changements de portée, définitions étrangères et frères de `$ref` restent actives ;
4. exactement **23** clauses reconnaissables, contrôlées au moment de la compilation ; le gestionnaire recontrôle aussi leur forme au moment de l'exécution ;
5. un gestionnaire `oneOf` disponible dans la classe du validateur original.

Si une condition manque, **le chemin natif original est conservé**. La compilation accélérée reste locale à un `SchemaStore`, déjà invalidée par une modification en mémoire du registre, de `common.schema.json` ou du statut d'attestation. Les contrôles de `check_schema`, `iter_errors` sur le registre, les empreintes de source, les reçus, les verrouillages, les contrôles bilingues et les règles de publication demeurent inchangés.

## Mesures expérimentales avant intégration

Expérience temporaire [GitHub Actions #44749549202](https://github.com/wikidebates/wikidebia-project/actions/runs/44749549202), Python 3.12, versions de bibliothèques attestées, corpus entièrement synthétiques, **5 répétitions alternées** par variante sur la portée `schema`.

| Arguments | Gestionnaire `oneOf` original | Gestionnaire à chemin positif court | Réduction |
| ---: | ---: | ---: | ---: |
| 40 | 0,058564 s | 0,055029 s | 6,04 % |
| 300 | 0,373470 s | 0,344530 s | 7,75 % |
| 680 | 0,825228 s | 0,755502 s | **8,45 %** |

Les rapports complets des corpus valides sont identiques. **12 variantes invalides** ont produit exactement le même rapport, avec le **même gestionnaire natif** dès que les branches accélérées étaient invalides. Ces mesures portent sur un prototype de même principe, et **ne doivent pas être présentées comme des gains réels du serveur**. Les résultats du code de production final sont vérifiés séparément avant fusion.

## Contrôles de non-régression

`validator/tests/test_registry_nullable_oneof_fastpath.py` ajoute **32 cas de test** : activation uniquement sur les schémas et versions attestés, refus d'un nombre inattendu d'alternatives, invalidation après modification du registre et du schéma commun, métavalidation des schémas modifiés, vérification d'une modification en mémoire de la branche, et comparaison de **rapports complets** sur une extraction synthétique valide et **25 variantes** (statuts, titres français et anglais, nombres, booléens, champs absents, classifications, contexte de `oneOf`, reçus et métadonnées de pages).

La suite CI complète du validateur et l'auto-audit de son **manifeste SHA-256 et de son reçu** restent impératifs. Une fois la PR fusionnée, la comparaison réelle de l'issue #153 pourra être répétée sur Debian en conservant la même extraction et les mêmes scénarios. Le test d'égalité des fichiers construits démontre l'absence de modification du corpus, mais ne mesure ni les traductions ni les crédits Codex.

**Sécurité :** aucun corpus historique privé, aucune page MediaWiki et aucun secret du serveur ne sont utilisés par les expériences GitHub.
