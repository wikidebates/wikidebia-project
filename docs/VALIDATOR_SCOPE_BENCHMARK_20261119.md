# Profilage des portées du validateur — 19 novembre 2026

## Provenance et précautions

- Workflow temporaire [GitHub Actions #44576168275](https://github.com/wikidebates/wikidebia-project/actions/runs/44576168275) : quatre répétitions par portée, corpus synthétiques de 40 et 120 arguments, Python 3.12 sur Ubuntu 24.04.
- Workflow temporaire [GitHub Actions #44576456246](https://github.com/wikidebates/wikidebia-project/actions/runs/44576456246) : même profilage et expérience complémentaire sur le coût de la vérification des *schémas* JSON, avec cinq répétitions par variante.
- Source de départ : `main` au commit `b264607c71831caa9b5b6730cdc2e88b974a221e`.
- La validation complète de tous les scopes sur un corpus au stade `graph_draft` produit **10 erreurs éditoriales attendues**. Il ne faut pas interpréter ce résultat comme un échec du validateur : l'étape initiale de corpus utilise précisément `schema`, `coherence`, `graph`, `files` et `workflow`. Ces cinq portées ont chacune produit zéro erreur dans l'expérience.
- Aucune publication wiki, revue linguistique ou modification de code productif.

## Médianes des durées par portée

| Portée | 40 arguments (s) | 120 arguments (s) |
| --- | ---: | ---: |
| Toutes les portées (10 erreurs éditoriales attendues) | 0,306481 | 0,628769 |
| `schema` | 0,297942 | 0,610570 |
| `coherence` | 0,001886 | 0,004295 |
| `graph` | 0,004762 | 0,013078 |
| `files` | 0,001232 | 0,002514 |
| `workflow` | 0,000811 | 0,002083 |
| `batches` | 0,001191 | 0,002948 |
| `sources` | 0,000916 | 0,002259 |
| `wikicode` | 0,000932 | 0,002158 |
| `bilingual` | 0,000847 | 0,002106 |
| `editorial` (10 erreurs attendues) | 0,002834 | 0,005981 |

Sur 120 arguments, `schema` représente environ **97,1 %** du temps de toutes les portées (0,610570 / 0,628769). Les médianes ont été mesurées séparément ; leur somme n'est pas rigoureusement comparable à celle du total.

## Expérience isolant la métavalidation des schémas

Dans **un processus expérimental uniquement**, le contrôle `Draft202012Validator.check_schema` a été neutralisé après la phase normale afin de mesurer sa contribution ; cette neutralisation **n'a pas été committée dans le validateur** et ne constitue **pas** un correctif recommandé. Les deux variantes ont produit des rapports identiques sur le corpus synthétique de 120 arguments utilisé.

| Variante (portée `schema`, 120 arguments, cinq essais) | Médiane (s) |
| --- | ---: |
| Contrôle complet, production | 0,623489 |
| Contrôle métaschéma neutralisé expérimentalement | 0,480074 |

La différence expérimentale est **0,143415 s**, soit une baisse d'environ **23,0 % de la durée de la portée `schema`** dans ce contexte seulement. Le chemin restant (environ 0,48 s) est dominé par d'autres coûts non encore isolés.

## Décisions et suites

1. **Ne jamais supprimer `check_schema` en production** sur la seule base de cet essai. La cohérence des schémas est un contrôle de sûreté et doit rester attestée.
2. Examiner un dispositif de précompilation/vérification de schémas où toutes les ressources internes seraient validées une fois par processus ou par version **sans** accepter de schémas mutables non revalidés, après mesure et tests d'équivalence complets. Ce n'est pas encore une modification validée.
3. Profilage plus détaillé du chemin restant : résolution des références `$ref`, itération sur les erreurs et vérification des contraintes sur les grands graphes.
4. Tester toutes les variantes avec des schémas intentionnellement corrompus, des données invalides, des corpus réels figés, et vérifier les rapports **identiques** (codes, chemins, pointeurs, sévérités et métadonnées). La validation complète et la revue éditoriale demeurent obligatoires.
5. Les résultats sont des mesures synthétiques sur GitHub Actions, non des gains démontrés sur Debian ni des économies de tokens ou crédits.

La campagne initiale sur la construction et la reprise est documentée dans [PRETRANSLATION_BENCHMARK_20261119.md](PRETRANSLATION_BENCHMARK_20261119.md).
