# Optimisation des clauses `allOf` à condition fausse attestée — 20 novembre 2026

## Diagnostic et périmètre

Dans le profilage **réel** Debian de 680 arguments communiqué avant la PR #187, le registre `argument_registry.schema.json` était toujours le coût majeur de la validation. Son profil montrait environ **6 194 appels** à la routine `allOf` sur trois contrôles instrumentés ; ces mesures constituent un diagnostic historique, **pas** une estimation de l'accélération de cette PR.

Dans le schéma du registre, une fois les définitions communes développées par la procédure sûre déjà attestée, il existe **50 clauses** `allOf` : **49** sont exactement des règles `{"if": {"properties": {"<champ>": {"const": "<valeur>"}}}, "then": {...}}` ou de même forme avec une liste `enum` **de chaînes** ; elles ne contiennent **aucun** `else`. La cinquantième teste la profondeur numérique d'une occurrence et possède un `else` ; elle ne peut pas bénéficier de cette optimisation.

## Propriété logique exploitée

Si l'instance est un véritable `dict` Python et contient une **chaîne Python de type exact `str`** pour le champ du statut, cette chaîne permet de conclure que le `if` est **faux** lorsqu'elle n'égale pas le `const` ou ne figure pas dans l'`enum`. Sans `else`, un `if` faux laisse la totalité du sous-schéma `if`/`then` **valide**, sans diagnostic. Dans ce seul cas, l'itération de `allOf` n'appelle pas `validator.descend` pour cette clause. Tous les autres membres de `allOf`, et **tous les `then` déclenchés**, continuent de passer par la bibliothèque JSON Schema avec la même position `schema_path`.

Cela **ne valide pas moins de données** : c'est uniquement l'élimination d'une invocation dont on sait mathématiquement qu'elle ne peut produire aucune erreur. Aucun graphe, état, source, format, reçu ou contenu éditorial n'est préjugé valide.

## Conditions de confiance et stratégie de repli

La fonction `_guarded_registry_false_status_allof` est appelée **uniquement après** le succès des preuves existantes : versions exactes `jsonschema==4.26.0`/`referencing==0.37.0`, empreintes SHA-256 canoniques de `argument_registry.schema.json` et `common.schema.json`, expansion sûre des références, puis accélérations successives `oneOf`, `if` et `type` attestées.

La nouvelle preuve exige **exactement 49 clauses admissibles**. Au moment de chaque validation, le code impose l'identité du validateur compilé, l'identité de la liste `allOf`, les types Python exacts `dict`/`list`/`str`, l'identité des gestionnaires conditionnels `if`, `properties`, `const` et `enum`, ainsi que l'intégrité structurelle et la valeur du `if` concerné. Les sous-classes et gestionnaires modifiés ne passent pas la voie rapide.

Toute valeur absente, mal typée ou inattendue, tout changement du schéma compilé ou du moteur conditionnel déclenche le comportement **natif**, sans altération des messages, contextes ou chemins d'erreur. Les clauses possédant un `else` ou une condition numérique sont toujours validées normalement. Les schémas source restent intacts.

## Non-régressions et vérification

Les tests `validator/tests/test_registry_status_allof_fastpath.py` comparent les **rapports complets de validation** (les cinq portées initiales, pas seulement les booléens), avec et sans la voie rapide : valeurs valides, absentes, fausses, inattendues et mal typées, erreurs dans les branches `then`, mutation des schémas compilés, gestionnaires de mots-clés remplacés, invalidation des preuves et erreurs de métaschéma.

Un workflow de **profilage temporaire** mesure en CI des corpus entièrement **synthétiques** de 40 et 680 arguments, en alternant les deux implémentations et en vérifiant l'égalité intégrale des rapports ainsi que l'immuabilité SHA-256 des sources et du corpus. Ce workflow doit être **retiré avant fusion**. Les résultats de CI synthétiques ne doivent pas être présentés comme des mesures réelles sur Debian.

L'optimisation n'effectue ni appels LLM, ni traductions, ni accès aux wikis. Elle ne porte que sur la préparation technique et n'implique aucune économie mesurée de crédits ou de tokens.

## Résultats du premier benchmark synthétique

[GitHub Actions #44777690902](https://github.com/wikidebates/wikidebia-project/actions/runs/44777690902), Python 3.12, `jsonschema 4.26.0`, `referencing 0.37.0`, itérations alternées **dans un même programme** avec tous les autres optimiseurs identiques. Le corpus et l'extraction sont demeurés bit à bit identiques ; pour chaque paire, les rapports complets du validateur sont égaux.

| Taille du corpus | Répétitions par variante | Médiane native (s) | Médiane optimisée (s) | Différence |
| --- | ---: | ---: | ---: | ---: |
| 40 arguments | 3 | 0,049253 | 0,049226 | −0,05 % (négligeable) |
| 680 arguments | 5 | 0,615375 | 0,605276 | **−1,64 %** |

Ces mesures sont **synthétiques**, non des résultats Debian. Le gain est réel mais modeste à l'échelle de l'ensemble du validateur, et la dispersion limite la généralisation. Ne pas interpréter ces chiffres comme un gain sur la génération éditoriale, les traductions ou les reprises déjà vérifiées sans un benchmark spécifique sur le serveur.
