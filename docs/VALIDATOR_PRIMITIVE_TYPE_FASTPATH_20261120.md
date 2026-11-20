# Optimisation attestée des types primitifs du registre — 20 novembre 2026

## Origine du diagnostic

Sur le serveur Debian, le profilage réel après la [PR #186](https://github.com/wikidebates/wikidebia-project/pull/186) de **680 arguments** sous Python 3.13.5 a mesuré : validateur CLI **0,835953 s**, validation Python instrumentée **0,729249 s**, portée `schema` **0,659004 s**, et évaluation de `argument_registry.schema.json` **0,604022 s** (médianes de 3 passages). Le registre représente encore **~83 %** du temps instrumenté. Les métriques anonymisées ont été consignées dans l'[issue #153](https://github.com/wikidebates/wikidebia-project/issues/153#issuecomment-7042797900), sans transmettre les données historiques du corpus.

Le profil `cProfile` indique environ 81 116 passages dans le mot-clé `type` de `jsonschema` et 196 887 contrôles `is_type`. Les anciennes optimisations de `oneOf` et `if` ont déjà diminué sensiblement le coût global, mais les contrôles de types ordinaires restent très fréquents.

## Principe de l'optimisation

Le registre, après **développement sûr et attesté** des références de `common.schema.json`, contient exactement **334 schémas** possédant un type primitif simple : `string`, `object`, `array`, `boolean`, `null` ou `integer`. Le code ajouté dans `_guarded_registry_primitive_type` reconnaît uniquement ces six cas sur les **objets de schéma précis** qui ont été inventoriés à la compilation et recontrôle à chaque appel leur identité et le type déclaré.

Pour un objet JSON Python dont le type exact est l'un des suivants, la condition `type` est automatiquement vraie, et seul le mot-clé `type` est raccourci :

| Type JSON Schema | Type Python exact |
| --- | --- |
| `string` | `str` |
| `object` | `dict` |
| `array` | `list` |
| `boolean` | `bool` |
| `null` | `NoneType` |
| `integer` | `int` |

**Aucun autre mot-clé n'est ignoré.** Les validations de format, longueur, regex, enum, propriété requise, `oneOf`, `if`, `allOf`, etc. s'exécutent comme auparavant. Les valeurs invalides, types personnalisés, sous-classes Python, types non listés, schémas modifiés, listes de types et vérificateurs de types personnalisés déclenchent toujours le **gestionnaire `type` d'origine de `jsonschema`**, avec les mêmes erreurs, messages, pointeurs, contextes et ordre.

Le cas des booléens est distinct de celui des entiers : `type(True) is bool`, et la règle `integer` n'est pas raccourcie pour `True`. Les flottants tels que `1.0` ne sont pas traités par la voie rapide de `integer`, même lorsqu'ils seraient acceptés par le moteur natif.

### Attestations obligatoires et repli

L'optimisation n'est permise que si toutes les preuves existantes réussissent d'abord :

1. `jsonschema==4.26.0` et `referencing==0.37.0` (exactement) ;
2. empreintes SHA-256 canoniques inchangées du registre et de `common.schema.json` ;
3. développement `$ref` sûr, sans référence cyclique ou changement de portée ;
4. construction réussie du gestionnaire `oneOf` attesté de la PR #185 ;
5. construction réussie du gestionnaire `if` attesté de la PR #186 ;
6. exactement **334** objets de schéma primitif admissibles, et présence du gestionnaire natif `type` ;
7. vérificateur de types standard de la classe compilée : le type checker de la validation courante doit être celui de la classe attestée, sans surcharge.

Si l'un de ces points échoue, la validation native reste active pour la nouvelle optimisation. L'échec du premier garde-fou `oneOf` conserve **le validateur entièrement natif**, comme le demandaient les tests historiques. Les modifications en mémoire de schéma invalident les compilations existantes par empreinte et ne peuvent pas conserver un type ancien via l'identité seule.

**Le document JSON Schema normatif lui-même reste inchangé** ; les contrôles de fichiers, d'empreintes, des verrous, des reçus, de la provenance et des règles bilingues ne sont pas modifiés. Aucune fonction de traduction ou de publication n'est touchée.

## Mesures appariées sur corpus synthétiques

Une première expérience de faisabilité [GitHub Actions #44759371270](https://github.com/wikidebates/wikidebia-project/actions/runs/44759371270) avait donné environ **6,94 %** d'amélioration à 680 arguments.

La mesure déterminante utilise ensuite **le code de production exact de la PR #187**, comparé à lui-même en désactivant **uniquement** `_guarded_registry_primitive_type` pour la référence, sur les cinq portées initiales `schema`, `coherence`, `graph`, `files`, `workflow`. Sept répétitions alternées par variante, mêmes versions de dépendances, mêmes fichiers, **rapports `Report.to_dict()` complets identiques** : [GitHub Actions #44760169810](https://github.com/wikidebates/wikidebia-project/actions/runs/44760169810).

| Arguments synthétiques | Référence (médiane) | Optimisation (médiane) | Gain |
| ---: | ---: | ---: | ---: |
| 40 | 0,050640 s | 0,048712 s | **3,81 %** |
| 300 | 0,300911 s | 0,280271 s | **6,86 %** |
| 680 | 0,667449 s | 0,622818 s | **6,69 %** |

Les mesures sont obtenues sous Ubuntu 24.04, Python 3.12 et dépendent du matériel ainsi que des caches. Elles ne prouvent **pas** encore un gain de 6,69 % sur Debian ou sur les 680 arguments du corpus réel, qu'il faudra mesurer en comparant le commit précédent `1919d5f00d8b7cf6f532387581a88a5bea844412` au commit de fusion de cette PR.

## Tests et contrôle de distribution

Le fichier `validator/tests/test_registry_primitive_type_fastpath.py` ajoute **142 cas de test** : 13 champs × 9 mutations de type, 12 comparaisons directes de type avec erreurs, 6 combinaisons de repli des attestations et mutations, et plusieurs tests isolés sur la bibliothèque de types personnalisés, les sous-classes, les modifications du schéma compilé et l'intégrité des schémas normatifs.

Le total des tests du validateur passe de **802 à 944**, sous réserve de confirmation par la CI. Le manifeste `validator/PACKAGE_MANIFEST_SHA256.json`, le `validator/PACKAGE_RECEIPT.json` signé, `validator/docs/TEST_REPORT.txt` et `validator/docs/SELF_AUDIT_REPORT.txt` doivent être recalculés ensemble, puis validés par `validator/scripts/self_audit.py`. Le workflow GitHub Actions exploratoire doit être supprimé avant fusion, comme pour les PR précédentes.

## Prochaine vérification utile

Après fusion et déploiement du nouveau commit sur le serveur Debian, relancer `tools/pretranslation_compare_revisions.py` sur **l'extraction figée inchangée**, avec la référence **`1919d5f00d8b7cf6f532387581a88a5bea844412`**. Exiger l'égalité des empreintes SHA-256 de tous les fichiers produits, les attestations, les rapports et les reçus avant d'accepter un gain de performance réel. Ne rien déduire de cette expérience concernant les crédits Codex, les tokens ou la qualité de traduction : ce sont des domaines volontairement non exercés.
