# Mesures hors ligne des reprises de prétraduction — 19 novembre 2026

## Provenance et périmètre

- Dépôt : `wikidebates/wikidebia-project`.
- Révision de départ : `59962a676e8e6a8b47d0805c0e5b8a572edff584` (après #152 et #154).
- Exécution : [GitHub Actions #44575044486](https://github.com/wikidebates/wikidebia-project/actions/runs/44575044486), Ubuntu 24.04, Python 3.12, succès.
- Programme : `kit/scripts/wikidebia_pretranslation_benchmark.py`, trois itérations pour chaque scénario et chacune des deux tailles.
- Corpus **synthétiques** : 40 arguments de 256 octets de remplissage par argument ; 120 arguments de 1 024 octets. Les graphes comprennent les relations argumentatives générées par le benchmark.
- Réseau MediaWiki, écriture wiki, modèle linguistique et traduction : **aucun**.
- Les nombres ci-dessous sont des secondes, sauf mention contraire, et correspondent à des **médianes**, pas à des garanties de performance.

## Résultats

| Scénario | 40 arguments (s) | 120 arguments (s) |
| --- | ---: | ---: |
| Build initial + validateur + reçu | 0,480186 | 0,841646 |
| Reprise du build sans reçu final | 0,374194 | 0,670094 |
| Reprise avec reçu validé | 0,013097 | 0,033693 |

Variabilité des durées totales (écart-type population) :

| Scénario | 40 arguments (s) | 120 arguments (s) |
| --- | ---: | ---: |
| Build initial | 0,052466 | 0,012371 |
| Reprise sans reçu | 0,032823 | 0,008170 |
| Reprise avec reçu | 0,000050 | 0,000036 |

Détails des étapes (médianes, secondes) :

| Étape | 40 arguments | 120 arguments |
| --- | ---: | ---: |
| Construction du corpus, build initial | 0,039782 | 0,204259 |
| Validateur, build initial | 0,352413 | 0,624799 |
| Création du reçu, build initial | 0,006123 | 0,012769 |
| Vérification du contrat source, reprise sans reçu | 0,007836 | 0,021199 |
| Validateur, reprise sans reçu | 0,352694 | 0,621233 |
| Reçu final, reprise sans reçu | 0,006019 | 0,012665 |
| Vérification du reçu écrit, reprise sans reçu | 0,005731 | 0,013081 |
| Vérification du contrat source, reprise exacte | 0,007536 | 0,020971 |
| Vérification du reçu, reprise exacte | 0,005465 | 0,012562 |

Dans le scénario synthétique à 120 arguments, la reprise exacte est environ **24,98 fois** plus rapide que le build initial complet (réduction de temps de 96,00 %). Ce ratio oppose deux **chemins d'exécution différents** ; il ne mesure pas l'effet d'une modification récente du code.

Le validateur représente environ **74,2 %** du temps total médian du build initial de 120 arguments (0,624799 / 0,841646). La validation occupe aussi la majeure partie du temps de reprise lorsque le reçu final est absent. En revanche, la réinspection d'un build validé et la vérification de son contrat coûtent quelques dizaines de millisecondes dans cette expérience.

## Décisions techniques

1. **Préserver impérativement** la validation obligatoire, l'intégrité des manifestes et reçus, les empreintes du contenu et les verrous éditoriaux. Aucun contournement de vérification ne se justifie par ces mesures.
2. **Priorité de profilage :** détailler les coûts internes du validateur sur plusieurs corpus synthétiques et un snapshot réel figé (avec autorisation et sans l'exporter), puis examiner uniquement des gains ne réduisant pas la portée des validations.
3. **Faible priorité immédiate :** micro-optimiser `compute_build_contract` ou `inspect_existing_build` : leurs coûts mesurés ici ne constituent pas le principal goulot d'étranglement.
4. **Ne pas interpréter** la différence entre build complet et reprise déjà vérifiée comme un gain attribuable aux PR #152 ou #154. Il faut une comparaison avant/après sur charges identiques pour les mesurer.
5. Pour toute optimisation du validateur, conserver les tests complets du dépôt et ajouter des tests de corruption, de sources modifiées entre lectures, de reprise interrompue et de validation bloquante.

## Reproduction

Depuis le commit ci-dessus avec les dépendances du validateur installées :

```sh
PYTHONPATH=kit/scripts python kit/scripts/wikidebia_pretranslation_benchmark.py \
  --arguments 40 --payload-bytes 256 --iterations 3 --machine-readable
PYTHONPATH=kit/scripts python kit/scripts/wikidebia_pretranslation_benchmark.py \
  --arguments 120 --payload-bytes 1024 --iterations 3 --machine-readable
```

Les fichiers de mesures complets ont été produits lors du workflow temporaire et les valeurs récapitulatives ont été conservées dans ses journaux. Aucune donnée de corpus privé n'a été publiée.

## Limites

Les deux corpus ont été exécutés sur le même runner, mais ils n'ont pas la même charge et ne constituent pas un comparatif avant/après d'implémentations. Trois répétitions sont un minimum exploratoire ; les variations de disque, cache et ordonnanceur influencent les résultats, surtout pour des opérations courtes. Les durées ne comprennent pas toutes les étapes d'extraction distante, de revue sémantique, de traduction ou de publication. Aucun gain en tokens ni en crédits Codex n'a été mesuré.
