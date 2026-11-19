# Isolation des chemins de pages des snapshots — 19 novembre 2026

## Constat

Le validateur initial d'extraction (`kit/scripts/wikidebia_corpus_init.py::verify_extraction`) vérifiait le SHA-256 des pages listées dans `snapshot_manifest.json`, mais résolvait leurs `relative_path` directement à partir du dossier du snapshot. Un manifeste portant des empreintes correctes pouvait ainsi déclarer un chemin avec `..`, un chemin absolu ou un lien symbolique pointant à l'extérieur de son arborescence. Le contrôle de hachage ne prouvait pas, à lui seul, que le fichier provenait du snapshot autorisé.

De même, la découverte de fichiers JSON du graphe et du manifeste d'audit pouvait accepter des liens symboliques vers un fichier extérieur à la racine de l'extraction.

## Correction

- Les chemins des pages doivent être des chemins POSIX relatifs, non vides, sans remontée `..`, sans chemin absolu et sans séparateur Windows `\\`.
- Après résolution des liens symboliques, chaque page doit rester à l'intérieur du dossier de snapshot. Un lien symbolique **interne** qui conserve des octets attestés reste accepté, afin de ne pas ajouter de restrictions inutiles aux copies locales.
- Le graphe, le manifeste de snapshot et les manifestes d'audit doivent également rester dans la racine de l'extraction après résolution des liens.
- `copy_import_pages` refait le contrôle du chemin avant lecture, même lorsqu'il est appelé indépendamment. La PR #164 vérifie en outre que les octets effectivement écrits correspondent à l'empreinte du snapshot.

Ces contrôles s'exécutent avant toute copie d'un fichier incriminé. Ils n'autorisent aucune publication sur un wiki.

## Régressions

Les tests du kit couvrent les chemins `../..`, absolus, avec antislashs, les pages liées symboliquement vers l'extérieur, les graphes ou manifestes d'audit externes, et une page liée à un autre fichier **à l'intérieur** de la racine (cas autorisé). Ils vérifient aussi le refus d'un chemin dangereux lorsque la fonction de copie est appelée directement sans prévalidation.

## Limites

La protection porte sur la résolution de chemins au moment de la vérification ou de la copie ; elle ne constitue pas une garantie de verrouillage atomique du système de fichiers contre un adversaire capable de remplacer des liens entre ces opérations. Le contrôle SHA-256 des octets importés (PR #164) et les reçus de build demeurent nécessaires. Aucun changement de contenu éditorial, de traduction ou de schéma MediaWiki.
