# Métavalidation JSON Schema attestée, bornée par contenu et dépendances — 20 novembre 2026

## Point de départ et périmètre

Suite de l'[issue #153](https://github.com/wikidebates/wikidebia-project/issues/153) et de la [PR #177](https://github.com/wikidebates/wikidebia-project/pull/177). La préparation d'un corpus local synthétique déclenche une validation JSON Schema du registre des arguments et des autres fichiers structurels. Les expériences ont été réalisées **sans wiki, sans publication, sans traduction et sans LLM**.

Les mesures préalables de la [PR #157](SCHEMA_CACHE_BENCHMARK_20261119.md) montraient que le simple cache en mémoire de validateurs déjà vérifiés ne produisait aucun gain statistiquement convaincant (0,27 %). L'expérience actuelle mesure séparément les chemins par schéma, puis le coût du contrôle des **métaschémas** (`check_schema`) au démarrage d'un nouveau `SchemaStore`.

### Profilage du code inchangé

GitHub Actions [#44727155503](https://github.com/wikidebates/wikidebia-project/actions/runs/44727155503) : Ubuntu 24.04, Python 3.12, `jsonschema==4.26.0`, `referencing==0.37.0`, même fixture et trois répétitions de chaque validation instrumentée.

| Schéma validé, 300 arguments synthétiques | Médiane d'un appel |
| --- | ---: |
| `argument_registry.schema.json` | 0,619353 s |
| `argument_graph.schema.json` | 0,031996 s |
| `debate_package.schema.json` | 0,031418 s |
| `source_registry.schema.json` | 0,021990 s |

L'optimisation existante de réutilisation des champs de graphe validés donne le **même rapport complet** que la validation indépendante, y compris sur les fixtures mesurées. Ces durées instrumentées ne mesurent pas le coût isolé de `check_schema`.

Une expérience **temporaire et interdite en production** a ensuite désactivé `check_schema` pour identifier une borne supérieure de gain. Elle confirmait un coût fixe notable, mais ne constituait pas un correctif sûr et n'a jamais été livrée.

## Correction

La [PR #178](https://github.com/wikidebates/wikidebia-project/pull/178) utilise une **attestation statique restreinte**, vérifiée lors de la CI :

1. Pour six schémas canoniques sollicités lors du premier build, les tests enregistrent leur SHA-256 calculé sur la représentation JSON canonique et **exécutent réellement `validator_for(schema).check_schema(schema)`**. Le schéma commun est contrôlé séparément.
2. À l'exécution, la métavalidation est déjà attestée uniquement lorsque `jsonschema==4.26.0`, `referencing==0.37.0`, le SHA-256 du schéma courant et celui du schéma commun correspondent tous **exactement** aux empreintes attestées.
3. Pour tout **schéma nouveau, modifié, inconnu, bibliothèque différente ou attestation non correspondante**, le validateur exécute le même `check_schema` qu'avant la modification. Le cache existant invalide encore son validateur compilé si le schéma est modifié entre deux appels.
4. `iter_errors` reste exécuté sur **toutes les instances**, les erreurs restent triées de la même manière, et les contrôles de graphes, provenance, sources, schémas, métadonnées, traduction et publication sont inchangés.

Cette optimisation concerne uniquement le coût de la métavalidation de schémas de programme **déjà vérifiés**. Elle ne constitue ni une acceptation automatique d'une instance JSON, ni un cache de résultats de validation, ni une suppression de vérifications d'empreintes du corpus. Sur une installation ayant d'autres versions de bibliothèques, le chemin historique est conservé et le gain n'est **pas** garanti.

## Mesure avant/après réellement comparée

GitHub Actions [#44728202047](https://github.com/wikidebates/wikidebia-project/actions/runs/44728202047), même commit et même runner Ubuntu, six répétitions par variante et par corpus, ordre **alterné**. `validate_package(scopes=['schema'])` est exécuté dans les deux variantes : la seule différence est l'activation de l'attestation pour la comparaison. Tous les rapports `to_dict()` sont identiques. L'attestation ne change pas le nombre ou la nature des validations d'instances.

| Arguments | Métavalidation complète (médiane) | Attestation exacte (médiane) | Réduction mesurée |
| --- | ---: | ---: | ---: |
| 40 | 0,403029 s | 0,150309 s | **62,71 %** |
| 120 | 0,675876 s | 0,428511 s | **36,60 %** |
| 300 | 1,296068 s | 1,045719 s | **19,32 %** |

Échantillons bruts (secondes), toujours métavalidation complète puis attestation :

- 40 : `[0.400064,0.404268,0.405075,0.402185,0.401971,0.403872]` et `[0.157006,0.149280,0.150244,0.150374,0.149474,0.152816]`.
- 120 : `[0.676254,0.673118,0.683838,0.675273,0.675497,0.676984]` et `[0.425666,0.429381,0.427641,0.430327,0.430204,0.426862]`.
- 300 : `[1.294772,1.288538,1.297363,1.291755,1.306522,1.309954]` et `[1.042825,1.046087,1.045351,1.042952,1.057746,1.046366]`.

Le gain absolu porte principalement sur un coût de démarrage relativement fixe, environ 0,25 seconde dans ces expériences ; la réduction relative décroît lorsque le nombre d'arguments augmente.

## Tests et risques

Huit nouveaux tests couvrent l'attestation indépendante des schémas empaquetés, la réutilisation d'un métaschéma connu sans sauter le diagnostic d'une instance invalide, les mutations en mémoire d'un schéma et du schéma commun, les versions de bibliothèques non attestées, les schémas inconnus et les rapports strictement identiques pour trois corpus dont deux invalides. Le cache antérieur et ses tests de mutation restent actifs.

Le manifeste et le reçu du validateur sont régénérés à partir de **614 tests réussis**, dont les huit nouveaux, avec les empreintes du code et du test.

### Limites et prochaine étape

Mesures synthétiques : **aucune preuve de gain pour une extraction réelle non fournie**, pour des versions de dépendances différentes, pour la traduction, la publication ou les quotas de tokens/credits Codex. Aucun accès distant MediaWiki ni serveur Debian. La CI complète du dépôt reste obligatoire pour l'intégration.

Une fois ce correctif stabilisé, les améliorations de `iter_errors` ou de résolution de `$ref` doivent faire l'objet d'une revue spécifique avec preuves d'équivalence sur des données invalides ; elles ne sont pas présumées sûres sur la seule base de ce profilage.
