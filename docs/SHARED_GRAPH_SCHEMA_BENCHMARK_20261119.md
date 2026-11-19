# Réutilisation contrôlée de la validation du graphe — 19 novembre 2026

## Objectif et méthode

Le profilage par fichier [PR #161](https://github.com/wikidebates/wikidebia-project/pull/161) a montré que les validations JSON du registre maître (`argument_registry.schema.json`) et de la projection du graphe (`argument_graph.schema.json`) représentaient ensemble environ 93,5 % du temps de la portée `schema` sur le corpus synthétique de 300 arguments.

Ces deux schémas ont six sous-structures textuellement identiques : `lifecycle`, `depth_policy`, `nodes`, `edges`, `occurrences` et `derived_counts`. Le correctif [PR #162](https://github.com/wikidebates/wikidebia-project/pull/162) réutilise une validation *seulement* si le registre complet a été validé sans **aucune erreur brute de schéma**, même lorsqu'une exception historique filtrerait les diagnostics, et si les schémas ainsi que les valeurs JSON de ces six structures sont identiques, types compris. Il valide toujours la structure propre à la projection (dont `graph_schema_version`, `debate`, les propriétés requises et l'interdiction des propriétés supplémentaires). Il revalide toujours le schéma JSON complet original avant de valider sa version limitée au cas présent.

En cas de divergence, d'erreur brute de schéma, de chemins de fichiers non canoniques, de références dont la résolution dépend du schéma racine ou d'évolution non prévue du schéma, les deux validations complètes sont maintenues. Aucun cache persistant, reçu, hachage signé, règle éditoriale ou accès MediaWiki n'est modifié.

## Mesures comparatives

- [GitHub Actions #44628885732](https://github.com/wikidebates/wikidebia-project/actions/runs/44628885732), Ubuntu 24.04, Python 3.12, même code et même corpus pour les deux variantes.
- Six répétitions alternées par variante et par taille de corpus (120 et 300 arguments, 1 024 octets de texte synthétique par argument).
- Baseline : même validateur et mêmes schémas avec réutilisation conditionnelle désactivée. Variante : réutilisation activée. Tous les rapports JSON complets ont été comparés strictement et étaient identiques.
- La suite ciblée de non-régression a réussi, notamment sur des graphes invalides, discordants et des schémas modifiés. Les tests ne mesurent pas la fidélité des traductions, qui ne sont pas touchées.

| Nombre d'arguments | Médiane deux validations complètes | Médiane réutilisation prouvée | Réduction mesurée |
| --- | ---: | ---: | ---: |
| 120 | 0,6522925 s | 0,4154400 s | 36,3 % |
| 300 | 1,3952820 s | 0,8006365 s | 42,6 % |

Échantillons bruts (secondes) :

- 120, complet : `[0.670965, 0.653360, 0.651934, 0.649572, 0.652651, 0.647062]`.
- 120, réutilisation : `[0.409493, 0.414015, 0.418286, 0.416865, 0.418478, 0.413921]`.
- 300, complet : `[1.393362, 1.390564, 1.373176, 1.397202, 1.402436, 1.410926]`.
- 300, réutilisation : `[0.794043, 0.801266, 0.804239, 0.804404, 0.798672, 0.800007]`.

## Précautions et interprétation

Les gains sont sensibles et dépassent la dispersion des six mesures sur ces corpus synthétiques. Ils concernent **uniquement** la portée `schema` du validateur. Le gain de temps du workflow complet (qui inclut vérification de fichiers, revues, traduction et publication) n'est pas mesuré ici ; aucune réduction de coût/tokens de modèle n'est démontrée.

Les deux schémas restent distincts et portent des contraintes de racine propres. Le correctif ne se fonde pas sur une équivalence supposée entre fichiers : chaque invocation compare directement les valeurs JSON analysées et les sous-schémas actuels, puis réutilise uniquement la partie démontrée équivalente. La comparaison refuse `true` versus `1`, même si Python les comparerait égaux.

L'évaluation est réalisée sur runner GitHub partagé, avec cache machine et ordre alterné. Des mesures sur un corpus réel figé et une validation complète multi-portées restent utiles pour estimer le gain opérationnel.

Ne jamais retirer une validation ou un contrôle d'intégrité pour améliorer ce résultat. La compatibilité doit continuer à couvrir les graphes divergent du registre, les métadonnées de projection invalides et les schémas évolutifs.
