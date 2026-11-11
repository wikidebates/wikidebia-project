# Reprise globale après interruption

Pour retrouver le seul Work actif sans mémoriser son débat, son identifiant ou
la dernière commande exécutée :

```text
./wikidebia resume
```

La commande examine les workflows d’orchestration encore antérieurs au
workspace, puis les workspaces locaux dès qu’ils existent, vérifie leurs preuves
et retourne l’action et la commande suivantes. Un workflow interrompu pendant
l’extraction, l’initialisation du corpus ou la préparation de la revue du graphe
est donc retrouvé avec le seul `debate_id`; il n’est plus nécessaire de recréer
un Work pour le rendre visible. Lorsqu’un `workspace.json` canonique existe, son
état plus précis devient automatiquement la source autoritative et le workflow
pré-workspace n’est pas compté une seconde fois. Pendant une traduction en cours,
une capsule de traduction valide et rattachée à la revue courante est plus
précise que le statut général : elle peut ainsi pointer directement vers le
correctif à éditer ou la commande d’application exacte.

Si plusieurs Works sont actifs, aucune sélection implicite n’est faite. La
sortie fournit pour chacun une commande de reprise explicite :

```text
./wikidebia resume --debate-id <debate_id> --work-id <work_id>
```

Le registre signé `.state/resume/registry.json` est reconstruit à chaque appel à
partir des workflows pré-workspace et des workspaces.
Les états distincts sont conservés sous forme d’événements signés et immuables
dans `.state/resume/events/`. Un registre absent ou altéré n’empêche donc pas
la reprise ; les événements valides et les workspaces sont relus. Un même état
n’est enregistré qu’une fois.

Cette commande n’accède pas aux wikis, ne publie rien et ne copie aucun secret.
