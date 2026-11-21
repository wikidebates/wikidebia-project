# Enregistrer les brouillons de création française

Ce parcours complète `creation-next` pour un corpus nouveau déjà constitué,
avec graphe et titres verrouillés et anglais `deferred`. Il ne crée pas le graphe,
ne recherche aucune source, ne traduit rien et ne contacte aucun wiki ou modèle.
Son objectif est de conserver les réponses utiles sans refaire la rédaction ni
reconstituer manuellement les empreintes et l'avancement après interruption.

## Parcours

```sh
./wikidebia creation-package --corpus corpus/mon_debat
```

La commande choisit la prochaine tâche avec le planificateur existant et fournit
`package_path`, un ZIP dans `outgoing/`. Huit pages au maximum sont ciblées par
défaut ; `--max-pages 1` limite une demande à une page, sans changer les lots.
Si la prochaine tâche est une revue, elle renvoie `review_required` sans fabriquer
un nouveau paquet de rédaction. Elle ne rouvre jamais une page validée.

Dans le ZIP, lire `INSTRUCTIONS.md` et les deux fichiers sous `context/`.
Seuls les fichiers sous `editable/` sont modifiables : les pages `.wiki` et
`RESPONSE.json`, ainsi que les notes facultatives `RESEARCH.json` (voir
`GUIDE_CREATION_RESEARCH.md`). En mode `--research-only`, le ZIP propose aussi
`SOURCES.json` pour une sélection documentaire explicite depuis des notes
**déjà** enregistrées (voir `GUIDE_CREATION_SOURCES.md`). Conserver tous les identifiants et choisir pour chaque page :

- `unchanged` : ne pas remplacer le texte, qui doit rester identique ;
- `partial` : enregistrer un brouillon inachevé, sans exiger une syntaxe finale ;
- `generated` : enregistrer une rédaction terminée, **encore à relire**.

Une page `generated` doit posséder son modèle français et une `date-création`
explicite au format `AAAA-MM-JJ`. Une date déjà enregistrée est conservée.
Ce contrôle minimal d'enveloppe n'est ni une validation du wikicode complet,
ni une vérification documentaire, ni une approbation éditoriale.

Placer le ZIP retourné dans `incoming/`, puis lancer :

```sh
./wikidebia creation-import --corpus corpus/mon_debat
./wikidebia creation-next --corpus corpus/mon_debat
```

La sélection automatique exige un seul ZIP de création pour ce débat.
En cas de pluralité, sélectionner explicitement le fichier :

```sh
./wikidebia creation-import --corpus corpus/mon_debat --archive incoming/retour.zip
```

Le format externe reprend `wikidebia-chatgpt-review-package-1.0` et sa séparation
`editable/` / `context/`. Le type `fr_creation_draft` utilise **creation-import**,
pas `review-import` : enregistrer un texte ne doit pas déclencher un checkpoint.
Les paquets, réponses et sauvegardes restent locaux et exclus de Git.

## Ce qui est mis à jour

L'import modifie uniquement les textes explicitement retournés et leurs états
canoniques dans le registre, le manifeste et les miroirs existants. Un brouillon
partiel reste `in_progress`. Une rédaction terminée devient `generated` avec
validation `pending`. Les lots concernés restent ouverts ; leurs anciennes
empreintes d'agrégats ne sont plus présentées comme courantes. Les rapports
antérieurs restent conservés, sans être réutilisés pour valider le nouveau texte.
Les autres pages, le graphe et les données anglaises restent intacts.
Le registre documentaire demeure inchangé pour un import de brouillon ordinaire.
Une revue `SOURCES.json` explicite peut le mettre à jour en mode recherche seule,
sans modifier le texte ni le statut des pages.

Les recherches peuvent être conservées avec les brouillons, dans le carnet de
travail ciblé `data/creation_research.json`, sans promotion automatique de source.
Les références sélectionnées après examen explicite peuvent être enregistrées
localement par `SOURCES.json`, mais les contrôles documentaires complets et
les attestations éditoriales finales restent obligatoires. L'import ne les invente
pas à partir de la prose et n'accepte pas de fichiers supplémentaires pour les
modifier indirectement. Il ne ferme aucun Work ou lot, ne produit aucun
`release_ready` et n'autorise aucune publication. Les validations globales restent
obligatoires, même quand toutes les pages sont enregistrées.

## Transaction, reprise et limites

Le retour est comparé au paquet préparé localement, au corpus complet et aux
entrées normatives. Une modification locale intervenante, une date incohérente,
un contexte modifié, un chemin dangereux, un lien symbolique, un fichier lié en
dur ou une archive trop volumineuse bloque l'import sans écraser le corpus.
Les copies de travail et les octets retournés ne sont pas envoyés au modèle.

Le corpus entier est préparé dans un répertoire temporaire du même système de
fichiers. Deux renommages remplacent ensuite le corpus, avec un journal de
reprise et une sauvegarde de l'original. **Il ne s'agit pas d'un échange atomique
unique de répertoires** : une interruption entre les renommages peut laisser le
chemin du corpus temporairement absent. Elle ne laisse pas un mélange de pages
et de métadonnées anciennes/nouvelles. Les commandes de contexte et de reprise
bloquent tant que le journal n'est pas résolu.

```sh
./wikidebia creation-import --corpus corpus/mon_debat --recover
```

La récupération restaure l'ancien corpus si le remplacement n'est pas terminé,
ou finalise le reçu lorsque le nouvel état exact est déjà installé. Une relance
normale de `creation-import` commence aussi par cette récupération.
En cas d'état inattendu, elle s'arrête en conservant corpus, sauvegarde et journal :
ne pas les supprimer ni modifier leurs empreintes pour forcer la reprise.
Les tests incluent un arrêt brutal de processus, pas une certification de
résistance à toute panne de stockage ou coupure électrique.

Un verrou POSIX sérialise les commandes de création coopérantes. Ne pas lancer
simultanément d'autres outils qui modifient ce corpus. Un éditeur externe ne
respecte pas ce verrou ; une divergence détectée est conservée pour examen, jamais
réconciliée ou effacée automatiquement. Le stockage temporaire doit être sur le
même système de fichiers. Ce parcours est destiné aux installations POSIX.

La réponse exacte et la sauvegarde restent sous `.state/creation-import/`.
Le ZIP entrant reste aussi dans `incoming/` pour permettre le rejeu explicite ;
le retirer de cette zone après succès ou utiliser `--archive` au retour suivant.
Un même retour déjà importé renvoie `already_imported` sans réécrire. Ce reçu
est historique : `current_state_matches_receipt=false` signale une progression
ultérieure sans l'annuler. Un retour différent pour un paquet consommé est refusé.

## Mesure et tests

Aucun gain chiffré de quota n'est déduit de ces mécanismes. Les copies et
empreintes complètes consomment des ressources locales ; l'économie visée est
d'éviter de redemander au modèle des brouillons perdus ou de lui faire reconstruire
l'avancement. Les tests ne mesurent ni tokens facturés ni crédits réels.

```sh
python -m pytest -q kit/tests/test_wikidebia_creation_import.py
```
