# Intégrité des pages importées après vérification de l'extraction — 19 novembre 2026

## Constat

Dans `kit/scripts/wikidebia_corpus_init.py`, `verify_extraction` contrôle les empreintes SHA-256 de chaque page du snapshot et le manifeste d'audit. La phase suivante `copy_import_pages` recopiait néanmoins les fichiers avec `shutil.copyfile`, puis relisait les cibles pour en extraire les métadonnées.

Entre le contrôle d'une page et sa copie, les octets de la source peuvent changer (processus externe, réextraction, modification accidentelle). L'ancien code pouvait alors enregistrer un texte différent sous une ligne de provenance portant toujours l'empreinte de la version antérieure. Cette course entre vérification et utilisation constitue une lacune de cohérence des preuves, même lorsque les vérifications initiales ont réussi.

## Correctif

La copie utilise maintenant **un seul tampon de lecture** pour chaque page. Le SHA-256 de ce tampon est contrôlé contre l'empreinte portée par le manifeste de snapshot immédiatement avant l'écriture du fichier importé. Les octets vérifiés sont ceux écrits dans le corpus ; les métadonnées sont analysées à partir des mêmes octets (UTF-8), sans relecture de la cible.

Cela maintient la préservation exacte du wikicode français préexistant et évite de mettre un contenu différent derrière une empreinte de provenance antérieure. La vérification complète de l'extraction reste inchangée. Aucune preuve cryptographique n'est remplacée par un cache fondé sur l'heure ou la taille.

## Scénarios de non-régression

1. Une page modifiée **après** `verify_extraction` mais **avant** sa copie doit faire échouer l'import sans écrire la cible affectée.
2. Une page modifiée **après la lecture de son tampon** doit être importée sous sa version vérifiée, indépendamment de la modification ultérieure du fichier source.
3. La copie ne doit pas relire le fichier de destination pour extraire les métadonnées.

La suite habituelle de tests des corpus et du kit continue à vérifier les structures, les preuves et les contrôles d'historique.

## Limites

Cette correction prévient la substitution d'octets **dans la fenêtre entre contrôle et copie**. Elle ne prétend pas verrouiller une source modifiée par un autre processus, ni résoudre à elle seule les problèmes éventuels de chemins malveillants ou de mutation ultérieure du corpus. Les reçus signés de build et les autres vérifications restent requis pour le reste du workflow.

La suppression de la relecture de chaque cible peut réduire les opérations disque, mais aucun gain de temps n'est annoncé sans benchmark comparatif. Aucun wiki n'est contacté et aucune traduction n'est générée.
