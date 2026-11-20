# Réduction des résolutions répétées de références JSON Schema du registre d'arguments — 20 novembre 2026

## Périmètre, origine et objectif

Continuation de [l'issue de performance #153](https://github.com/wikidebates/wikidebia-project/issues/153), après la [PR #178](https://github.com/wikidebates/wikidebia-project/pull/178) de métavalidation attestée. Cette dernière réduit le coût initial de `check_schema` sans retirer la validation des instances. Les mesures restantes montrent que la résolution répétée des `$ref` vers `common.schema.json#/$defs/...` constitue une partie significative du temps de validation du **registre des arguments**, qui croît avec le nombre de nœuds.

La [PR #179](https://github.com/wikidebates/wikidebia-project/pull/179) évalue une **mise en ligne des définitions communes** à l'intérieur d'un schéma de validation temporaire, sans toucher aux schémas normatifs de référence ni aux documents à valider.

## Périmètre strict de l'optimisation

La transformation est appliquée exclusivement au validateur en mémoire de `argument_registry.schema.json`, et uniquement si **toutes** les conditions sont prouvées :

1. Versions des bibliothèques identiques à celles attestées précédemment : `jsonschema==4.26.0` et `referencing==0.37.0`.
2. Empreintes SHA-256 du schéma du registre **et du schéma commun** exactement égales aux empreintes vérifiées de la PR #178. Ces contrôles portent sur le contenu JSON réel chargé, et non sur `mtime`, le nom du fichier ou une déclaration seule.
3. Références remplacées limitées à `common.schema.json#/$defs/<définition>`, puis références internes `#/$defs/<définition>` dans le schéma commun. La transformation refuse les boucles, définitions inconnues, `$ref` avec frères dans le schéma commun, références externes non reconnues et mots-clés qui changent la portée de résolution (`$id`, `$anchor`, `$dynamicRef`, `$dynamicAnchor`, etc.).
4. Le schéma développé est un **nouvel objet**, utilisé uniquement par `iter_errors`. Le schéma original, le registre original et la preuve de réutilisation du graphe restent inchangés.
5. Si la preuve ou l'expansion échoue, le validateur conserve la résolution `$ref` originale. Si le registre ou le schéma commun est modifié **en mémoire** après compilation, l'ancienne compilation optimisée est invalidée ; elle est aussi supprimée *avant* un éventuel échec de métavalidation d'un schéma changé.

Le validateur continue de produire toutes les erreurs JSON Schema via `iter_errors` et de les trier de la même manière. Les contrôles de provenance, les empreintes de fichiers, les verrous français, le graphe, la traduction, les revues sémantiques bilingues et la publication ne sont pas modifiés. Aucun cache inter-session ou basé sur les dates de modification n'est ajouté.

## Expérience initiale avant changement de production

[Actions #44730629841](https://github.com/wikidebates/wikidebia-project/actions/runs/44730629841) : deux substitutions **strictement expérimentales et non livrées** dans un processus Python identique, pour des corpus synthétiques de 40/120/300 arguments, cinq répétitions par variante.

- Substitution des seules références feuilles : gain modéré.
- Substitution récursive des définitions communes non ambiguës : gain d'environ 35–39 % sur la portée `schema`.
- Comparaison stricte des rapports `Report.to_dict()` sur les mêmes corpus valides et **11 modifications invalides** par taille : aucune différence détectée.

Cette expérience a guidé la variante retenue mais ne suffit pas seule à démontrer la sécurité d'une transformation quelconque.

## Comparaison appariée de l'implémentation réelle

[Actions #44731431254](https://github.com/wikidebates/wikidebia-project/actions/runs/44731431254), Linux Ubuntu 24.04 / Python 3.12, bibliothèque JSON Schema attestée, même commit et mêmes fixtures, **six répétitions par variante**, alternées pour chaque taille. Les deux variantes emploient le validateur de la branche candidate, avec/sans la transformation des références ; **les métaschémas restent attestés dans les deux variantes**, ce qui isole la nouvelle optimisation de la PR #178. Aucun wiki, LLM ou environnement de production n'est contacté.

| Arguments synthétiques | Avant (médiane s) | Après (médiane s) | Réduction | Écart-type des échantillons avant / après (s) |
| ---: | ---: | ---: | ---: | ---: |
| 40 | 0.093670 | 0.064599 | 31.04 % | 0.003429 / 0.002094 |
| 120 | 0.259219 | 0.169467 | 34.62 % | 0.003147 / 0.001296 |
| 300 | 0.632711 | 0.401900 | 36.48 % | 0.005390 / 0.001773 |

Échantillons bruts, secondes :

- **40 arguments** : avant `[0.102522, 0.093270, 0.094070, 0.092550, 0.094096, 0.093186]` ; après `[0.067933, 0.063800, 0.064960, 0.064150, 0.064238, 0.069253]`.
- **120 arguments** : avant `[0.257351, 0.257958, 0.262793, 0.266097, 0.260480, 0.257957]` ; après `[0.167747, 0.169504, 0.170101, 0.168231, 0.171745, 0.169430]`.
- **300 arguments** : avant `[0.632095, 0.631299, 0.645795, 0.636542, 0.629449, 0.633327]` ; après `[0.401595, 0.404859, 0.402205, 0.400903, 0.399193, 0.403186]`.

Les **rapports complets** sont égaux, y compris statut, codes, gravités, messages, pointeurs, détails et ordre des constats. Les mesures ne prouvent **ni une accélération égale du workflow complet**, ni un gain sur une extraction réelle non disponible, ni une économie de tokens ou de crédits Codex. La réduction absolue reste propre à cette plateforme et ces versions de bibliothèque.

## Tests et cas de repli

**25 nouveaux tests** ajoutés dans `validator/tests/test_registry_common_ref_expansion.py` : métavalidité indépendante du schéma développé, préservation des schémas sources, activation exclusivement attestée, refus des références inconnues/cycliques/dynamiques ou des `$id` locaux, métavalidation du schéma source modifié, invalidation après changement du schéma commun ou retrait de l'attestation, non-résurrection d'une compilation périmée après une tentative invalide, comparaison des rapports complets pour un cas sain et **douze cas invalides** (titres, rubriques, mots-clés, identifiants, relations, données de pages, propriétés inconnues, contraintes conditionnelles, types incompatibles).

**639 tests du validateur réussis** sur le workflow de mesure ; les rapports de tests, le manifeste SHA-256 et le reçu attesté du validateur sont mis à jour ensemble. La CI de PR et de `main` reste obligatoire.

## Limites et prochaine action

Cette optimisation vise uniquement l'évaluation des instances JSON Schema de **l'unique registre** dans le contexte exact et explicitement attesté. Si les bibliothèques sont mises à niveau, le comportement historique reste en place jusqu'à une nouvelle analyse, un renouvellement des attestations et des tests adaptés.

La piste suivante consiste à mesurer sur **extraction réelle figée locale**, lorsque le serveur Debian en dispose, sans publier ni transférer de corpus privé. Il faudra ensuite étudier séparément le coût des autres schémas et de l'initialisation du validateur, à condition de démontrer une amélioration réelle et une équivalence stricte des diagnostics.
