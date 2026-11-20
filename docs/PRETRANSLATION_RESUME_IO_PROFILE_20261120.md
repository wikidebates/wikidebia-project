# Profilage des lectures et hachages des reprises prétraduction — 20 novembre 2026

## Objectif

Le [suivi de performance #153](https://github.com/wikidebates/wikidebia-project/issues/153)
distingue les étapes réellement coûteuses de celles qui sont nécessaires pour
prévenir la réutilisation d'un corpus ou d'une source modifiés.

La [PR #177](https://github.com/wikidebates/wikidebia-project/pull/177)
étend uniquement l'**outil de benchmark local** :
`kit/scripts/wikidebia_pretranslation_benchmark.py`.
L'option explicite `--profile-file-io` ajoute des comptages par étape des
lectures `Path.read_bytes`, des appels `Path.read_text`, des lectures
répétées du même chemin **dans la même étape**, et des appels/volumes de
hachage `wikidebia_corpus_init.sha256_bytes`. Les compteurs sont restitués
avec leurs échantillons, médianes, minimums et maximums dans le rapport
existant, dont le SHA-256 final couvre également ce champ optionnel.

Sans cette option, le benchmark garde son rapport historique intact.
Les patches instrumentés sont actifs uniquement pendant les étapes
mesurées, dans le processus Python principal, et sont rétablis en sortie,
**y compris en cas d'exception**. Aucun contenu source n'est journalisé.

## Exécution et résultats reproductibles

Benchmark temporaire passé sur [GitHub Actions #44724687331](https://github.com/wikidebates/wikidebia-project/actions/runs/44724687331),
Ubuntu 24.04 / Python 3.12, source entièrement synthétique (40 arguments,
1 024 octets de remplissage par argument), trois répétitions de chaque
scénario.

Deux commandes distinctes ont été exécutées sur le **même commit** :
l'une avec `--profile-file-io` pour les compteurs et l'autre **sans**
instrumentation pour la meilleure estimation des durées, afin de ne pas
attribuer au produit un coût de mesure introduit par le benchmark.

### Durées non instrumentées

| Scénario | Médiane du chemin total | Durées par étape (médianes) |
| --- | ---: | --- |
| Construction initiale, validation et reçu | **0,431708 s** | `build_corpus` : 0,082400 s ; validateur isolé : **0,343319 s** ; reçu : 0,006016 s |
| Reprise après build, avant reçu | **0,365882 s** | vérification de source : 0,009418 s ; inspection partielle : 0,000897 s ; validateur isolé : **0,343572 s** ; reçu : 0,005975 s ; vérification finale du reçu : 0,005924 s |
| Reprise exacte, avec reçu valide | **0,015249 s** | vérification de source : 0,009266 s ; vérification du reçu : 0,005915 s |

Échantillons complets des scénarios (secondes) :

- Construction initiale : `[0.430592,0.434578,0.431708]`.
- Reprise interrompue : `[0.362149,0.366664,0.365882]`.
- Reprise exacte : `[0.015318,0.014936,0.015249]`.

Sur ce corpus, le temps du validateur isolé représente **environ 79,5 %**
du temps d'une construction initiale et **93,9 %** du temps de reprise
interrompue. Cette observation ne doit pas être extrapolée sans mesure
aux graphes plus grands ou aux snapshots réels.

### Lectures/hachages du processus principal, avec instrumentation

Les nombres ci-dessous étaient identiques sur les trois répétitions des
mêmes étapes (tous les octets sont les volumes **observés**, pas un
total de lecture disque incluant le sous-processus du validateur).

| Scénario et étape | `Path.read_bytes` : appels | Octets lus | Relectures du même chemin | Appels au SHA-256 du kit | Octets transmis au SHA-256 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Initial — `build_corpus` | 87 | 184 842 | 43 | 91 | 217 846 |
| Initial — `write_receipt` | 57 | 357 760 | 0 | 62 | 399 279 |
| Interrompue — `verify_source_contract` | 45 | 109 987 | 2 | 46 | 117 867 |
| Interrompue — `write_receipt` | 57 | 357 772 | 0 | 62 | 399 291 |
| Interrompue — `verify_written_receipt` | 57 | 357 772 | 0 | 62 | 399 291 |
| Exacte — `verify_source_contract` | 45 | 109 987 | 2 | 46 | 117 867 |
| Exacte — `verify_build_receipt` | 57 | 357 760 | 0 | 62 | 399 279 |

`inspect_unverified_build` et `initial_validator` comptent zéro
`Path.read_bytes` observé par cette instrumentation : **ce zéro ne
signifie pas qu'ils ne lisent pas de fichier**. L'inspection utilise
notamment `Path.read_text` ; le validateur est lancé dans un
sous-processus distinct, que cet instrument ne suit pas.

## Conséquences pour les prochaines optimisations

1. **Ne pas supprimer les relectures de sécurité.** `verify_extraction`
   compare les pages au manifeste du snapshot et au manifeste audité ;
   `copy_import_pages` vérifie de nouveau les octets réellement copiés,
   afin de résister à la modification des sources entre vérification et
   importation. `write_build_receipt` puis `verify_build_receipt`
   doivent hacher le build dans des opérations distinctes pour détecter
   les modifications ultérieures.
2. **Le chemin de reprise exacte est déjà rapide.** Il évite la
   reconstruction et le validateur tout en conservant les vérifications
   indépendantes de la source et du reçu.
3. **Le validateur constitue le principal coût observé sur ce fixture.**
   Les futures optimisations doivent analyser le démarrage du
   sous-processus et les portées réellement coûteuses (`schema`,
   `graph`, `files`, etc.), sans le supprimer lors d'une reprise
   interrompue non encore validée.

## Limites

Ce profil ne mesure **ni** les lectures du sous-processus du validateur,
**ni** les accès effectués via `open()` brut ou via une projection
mémoire, ni tous les appels de hachage des autres modules. Le compteur
`read_text_total_characters` est en caractères Unicode, pas en octets
disque. Une opération absente des compteurs peut lire des données par
d'autres interfaces.

Le profilage ajoute un coût Python : les durées instrumentées ne doivent
pas remplacer les durées obtenues dans un lancement distinct non
instrumenté. Les données sont synthétiques, non un snapshot réel,
et n'évaluent ni traduction, ni publication, ni tokens ou crédits
Codex. Le benchmark n'a contacté aucun wiki, ni modifié le serveur
Debian. Le workflow provisoire de mesure a été supprimé avant
fusion, sans devenir une vérification coûteuse permanente.
