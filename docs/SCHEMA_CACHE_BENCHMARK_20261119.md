# Mesure avant/après du cache de validation des schémas — 19 novembre 2026

## Contexte vérifié

- Correctif : [PR #157](https://github.com/wikidebates/wikidebia-project/pull/157), fusionnée au commit `50bde613f07b22c60c35d1a38141b1d591631928`.
- Baseline : `1f80a522d5ac0fdecd4b7f20bd8bff939dc62b22`, avant ce correctif.
- Exécution : [GitHub Actions #44578582922](https://github.com/wikidebates/wikidebia-project/actions/runs/44578582922), Ubuntu 24.04, Python 3.12, statut `success`.
- Instrumentation temporaire : [PR #158](https://github.com/wikidebates/wikidebia-project/pull/158), fermée **sans fusion** afin de ne pas conserver un workflow de profilage temporaire dans les sources actives.
- Corpus : un même build synthétique de 120 arguments et 1 024 octets de remplissage par argument, construit une seule fois depuis la baseline ; le répertoire a été réutilisé à l'identique dans les deux variantes.
- Portée : `validate_package(..., scopes=['schema'])` exécuté sept fois par variante. Aucune traduction, aucun wiki ni LLM sollicité.
- Chaque passage exigeait zéro erreur et l'égalité exacte des constatations structurées avec les résultats de référence.

## Résultats

| Variante | Médiane (secondes) |
| --- | ---: |
| Avant la PR #157 | 0,523481 |
| Après la PR #157 | 0,522071 |
| Écart médian (avant moins après) | 0,001410 |
| Réduction apparente relative | 0,27 % |

Échantillons bruts avant, secondes : `0.523480603, 0.532373784, 0.576229093, 0.523226335, 0.525953679, 0.517031396, 0.517855080`.

Échantillons bruts après, secondes : `0.531478873, 0.518369455, 0.516199419, 0.575424973, 0.522070537, 0.520931223, 0.525312987`.

**Interprétation :** la différence de 0,27 % est très inférieure à la variabilité observée. Cette expérience ne démontre donc **aucun gain de performance significatif** du correctif #157 sur cette charge. Elle établit en revanche que les constatations de validation restent identiques dans ce test de corpus synthétique. Le cache à empreinte exact peut économiser certaines métavalidations, mais son calcul d'empreinte a lui-même un coût ; aucun bilan de rentabilité plus large n'est établi.

## Décisions et limites

1. Ne pas annoncer de gain en temps, en tokens ou en crédits sur cette base ; le gain mesuré n'est pas significatif et ne concerne que le scope `schema`.
2. Conserver les contrôles d'intégrité et les validations de schémas : le correctif #157 ne les désactive pas. Les tests ajoutés contrôlent l'invalidation du cache sur modification du schéma et l'absence de cache entre deux `SchemaStore`.
3. Donner la priorité au profilage du **chemin de validation des instances** : coût des `$ref`, duplication éventuelle des validations entre graphe et registre, itération sur les erreurs et chargement de fichiers. Aucune suppression de contrôle ou déduplication supposée sûre ne doit précéder une preuve d'équivalence.
4. Pour toute variante suivante, recueillir les rapports exacts (codes, niveaux, chemins, pointeurs et détails) et tester aussi les schémas corrompus, les références externes, les builds interrompus et une extraction réelle figée non exportée.
5. Les observations proviennent d'un runner GitHub partagé et de sept répétitions consécutives, baseline exécutée avant correctif. L'ordre de passage, le cache disque et la charge de la machine peuvent biaiser la comparaison ; un protocole alterné serait préférable pour détecter de faibles gains.

Voir également [les mesures par portée](VALIDATOR_SCOPE_BENCHMARK_20261119.md) et [les mesures des reprises](PRETRANSLATION_BENCHMARK_20261119.md).
