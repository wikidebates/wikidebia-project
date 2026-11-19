# Index des titres normalisés à l'import — mesure du 19 novembre 2026

## Origine de l'optimisation

L'importation des pages du snapshot (`kit/scripts/wikidebia_corpus_init.py::copy_import_pages`) associait chaque titre du graphe à la page française archivée. Une correspondance exacte par titre était obtenue immédiatement. À défaut, le code normalisait le titre du graphe, puis **reparcourait et renormalisait tous les titres du snapshot**, pour chaque argument concerné. Lorsque beaucoup de titres présentent des différences de typographie ou d'espacement (`Argument_synthétique` contre `Argument synthétique`, apostrophes, espaces multiples, points terminaux), la recherche peut avoir un coût quadratique dans le nombre d'arguments.

La [PR #167](https://github.com/wikidebates/wikidebia-project/pull/167) construit un index normalisé **une seule fois et uniquement après le premier échec d'une recherche exacte**. Les recherches suivantes prennent un temps amorti constant. La construction conserve l'ordre des entrées du dictionnaire des titres historiques ; `setdefault` conserve le premier candidat sur collision ; une recherche exacte garde toujours la priorité. Le code préserve également le comportement d'erreur si un titre vide précède le premier candidat valide.

Le correctif n'altère pas le wikicode, les titres canoniques finaux, les métadonnées de provenance, les empreintes sources, la traduction ni la publication.

## Benchmark hors ligne

- Exécution : [GitHub Actions #44633959429](https://github.com/wikidebates/wikidebia-project/actions/runs/44633959429) (succès), Ubuntu 24.04 / Python 3.12.
- Baseline : commit `afff1dc1732bae883ba048a811f2ede8cff64743`, avant ce correctif.
- Corpus synthétiques de **120, 300 et 700 arguments**, avec 512 octets de texte de remplissage par argument.
- Les noms canoniques dans le manifeste de snapshot portent des underscores, tandis que le graphe contient les mêmes titres avec des espaces. Le manifeste SHA-256 de l'extraction a été recalculé, puis `verify_extraction` a contrôlé chaque source avant la mesure.
- **Import isolé :** six essais alternés pour l'ancien et le nouveau code, avec comparaison exhaustive des métadonnées des pages, de la provenance et des empreintes SHA-256 des fichiers copiés.
- **Construction intégrale du corpus `build_corpus` :** quatre essais alternés sur 300 et 700 arguments, exigeant le même contrat source et les mêmes octets des pages importées. Le validateur initial externe, les revues, la traduction et les actions MediaWiki sont exclus de cette mesure.
- Les secondes ci-dessous sont des **médianes**, non des promesses de performance sur les corpus réels.

| Arguments | Import avant | Import après | Réduction à l'import | Build avant | Build après | Réduction du build |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 120 | 0,126617 s | 0,120442 s | 4,88 % | — | — | — |
| 300 | 0,337681 s | 0,300048 s | 11,14 % | 0,465645 s | 0,424113 s | 8,92 % |
| 700 | 0,904561 s | 0,697331 s | 22,91 % | 1,202888 s | 0,986868 s | 17,96 % |

### Échantillons bruts (secondes)

- Import 120 ancien : `[0.127203,0.126602,0.129174,0.126631,0.126178,0.126398]`.
- Import 120 indexé : `[0.119579,0.120426,0.126473,0.120618,0.119594,0.120457]`.
- Import 300 ancien : `[0.337286,0.337699,0.338568,0.337621,0.339022,0.337662]`.
- Import 300 indexé : `[0.299453,0.300098,0.300264,0.300951,0.299826,0.299998]`.
- Import 700 ancien : `[0.903726,0.904557,0.904824,0.903379,0.904564,0.905789]`.
- Import 700 indexé : `[0.697350,0.697312,0.703671,0.696932,0.698793,0.695824]`.
- Build 300 ancien : `[0.475542,0.467255,0.464034,0.462469]`.
- Build 300 indexé : `[0.422864,0.424862,0.423506,0.424720]`.
- Build 700 ancien : `[1.207065,1.198710,1.196468,1.208593]`.
- Build 700 indexé : `[0.983500,0.992496,0.989220,0.984516]`.

## Vérification fonctionnelle et limites

Six nouveaux cas pytest couvrent la conservation exacte du contenu des pages, le choix des titres normalisés, la priorité d'une correspondance exacte, le premier candidat lors d'une collision, l'ordre des exceptions en présence de titres invalides et le nombre linéaire de normalisations sur 100 arguments.

**Conditions du gain :** tous les titres synthétiques du benchmark nécessitaient la recherche de repli. Lorsque tous les titres correspondent exactement, le nouveau code n'active pas l'index ; le gain attendu est donc proche de zéro, conformément au choix d'un index paresseux. Une extraction réelle peut comporter un taux d'alias beaucoup plus faible.

Les tests ne mesurent pas la consommation de tokens d'un modèle, ni le coût du traitement complet d'un Work (validateur, revues bilingues et publications). Aucun wiki n'a été contacté. Le code conserve les contrôles SHA-256 et les conditions d'acceptation du corpus en vigueur.

Le workflow de profilage temporaire a été supprimé avant fusion pour ne pas alourdir les workflows permanents du dépôt.
