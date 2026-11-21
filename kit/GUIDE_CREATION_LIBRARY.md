# Réutiliser les recherches d'autres débats sans transférer leur validation

Cette fonction **facultative** aide à limiter les recherches documentaires répétées
lorsque plusieurs débats nouveaux sont créés sur des sujets proches. Elle indexe
localement les notices **francophones** déjà conservées dans des corpus explicitement
choisis. Elle ne fait ni recherche sur Internet, ni consultation de sources,
ni appel à un modèle, ni écriture wiki. Elle n'est pas une mémoire éditoriale
publique et ne transfère aucune approbation.

## 1. Construire une bibliothèque privée

```sh
./wikidebia creation-library-build \
  --corpus corpus/debat_anterieur_1 \
  --corpus corpus/debat_anterieur_2
```

Le fichier `private/creation_library.json`, ignoré par Git, est déterministe
pour les mêmes sources. Le dossier `private/` doit être inaccessible aux autres
utilisateurs (mode POSIX `0700`) ; le fichier est écrit en mode `0600`.
Les sources doivent être des corpus locaux possédant un manifeste, un registre,
un cadrage et un registre documentaire cohérents. Leurs imports interrompus
sont refusés. Rien n'est récupéré automatiquement depuis le wiki.

Le kit extrait uniquement des **notices documentaires**, leur identité DOI/URL
canonique ou bibliographique, les titres des pages précédemment concernées et
une courte justification antérieure lorsqu'elle est disponible. Il peut exploiter
les `sources.json` canoniques et les ressources du carnet `creation_research.json`.
Il **ne copie pas** les extraits consultés, les requêtes négatives, les textes
intégraux ni les attestations de validation. Une même notice rencontrée dans
plusieurs corpus est rapprochée ; deux variantes de métadonnées conservent
leur identité distincte et sont signalées, sans résolution automatique.

Les empreintes des fichiers documentaires et de cadrage utilisés sont conservées.
Si l'un change, une bibliothèque ancienne est refusée et doit être reconstruite.
Cela ne détecte **pas** les modifications d'un site Internet depuis la recherche.
La bibliothèque n'est pas signée par une autorité extérieure : son empreinte
permet de détecter les modifications accidentelles, pas d'authentifier un auteur.

## 2. Recevoir un contexte ciblé pour un nouveau débat

```sh
./wikidebia creation-package --corpus corpus/nouveau_debat \
  --research-only --page-id A0003 --reuse-library
```

Pour chercher une notion spécifique même si elle n'apparaît pas dans le titre :

```sh
./wikidebia creation-package --corpus corpus/nouveau_debat \
  --research-only --page-id A0003 --reuse-library \
  --reuse-query 'souveraineté alimentaire'
```

L'option `--reuse-library` marche également lors de la rédaction habituelle :

```sh
./wikidebia creation-package --corpus corpus/nouveau_debat --reuse-library
```

Le ZIP habituel contient deux fichiers de contexte **en lecture seule** :
`context/REUSE_CANDIDATES.json` et `context/REUSE_HELP.md`. Il ne contient pas
la bibliothèque entière. Chaque sélection porte sur les pages demandées,
avec un appariement lexical déterministe, un classement des pistes et des
limites de taille. La méthode ne trouve **pas** toutes les sources pertinentes :
les synonymes, les langues et les relations conceptuelles doivent encore être
recherchés. Les suggestions peuvent être vides et certaines peuvent être
inadaptées. Le rapport donne `reuse_candidate_count` et `reuse_preview_bytes`,
qui **ne sont pas** des tokens facturés ni une preuve d'économie de quota.

Les anciens `creation-package` sans cette option restent identiques dans leur
fonctionnement. Le kit relie les propositions à l'empreinte exacte de la
bibliothèque et des fichiers sources lus. Une évolution postérieure oblige à
repréparer le paquet ; elle ne peut pas remplacer silencieusement son contexte.

## 3. Réexaminer et enregistrer pour la nouvelle page

Une proposition réutilisable est un **indice de découverte** et **jamais** une
observation valable pour la page cible. Même si elle provient d'une référence
vérifiée dans un autre corpus, il faut vérifier de nouveau l'édition française,
le document, sa disponibilité, sa date, son attribution et surtout sa capacité
à développer le **nouvel argument**. Le rapprochement lexical n'atteste rien.

Le relecteur enregistre sa **nouvelle recherche ou consultation réelle** dans
`editable/RESEARCH.json`, comme indiqué dans `GUIDE_CREATION_RESEARCH.md`.
Il ne copie ni `hint_id` comme identifiant `R…`, ni `observation_id` d'un autre
corpus. Après import des notes, un **second retour distinct** avec
`editable/SOURCES.json` permet, si la vérification a bien été effectuée,
de retenir la référence selon `GUIDE_CREATION_SOURCES.md`.

Cette chaîne ne fabrique jamais une source vérifiée, une recherche négative,
un relecteur, une citation ou une validation de page. Le registre canonique,
les statuts, le graphe et le wikicode du débat cible restent intacts lors de
la construction et de la consultation de la bibliothèque. La publication
reste entièrement séparée et soumise à ses propres contrôles.

La bibliothèque vise à **éviter de redécouvrir les notices**, pas à réduire la
recherche ou l'examen éditorial nécessaire. Aucune baisse de quota ChatGPT ou
Codex n'est avancée sans une mesure sur de vrais travaux comparables.

Tests ciblés :

```sh
python -m pytest -q kit/tests/test_wikidebia_creation_library.py
```
