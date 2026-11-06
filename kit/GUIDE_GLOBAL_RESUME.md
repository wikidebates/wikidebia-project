# Reprise globale après interruption

Pour retrouver le seul Work actif sans mémoriser son débat, son identifiant ou
la dernière commande exécutée :

```text
./wikidebia resume
```

La commande examine uniquement les workspaces locaux, vérifie leurs preuves et
retourne l’action et la commande suivantes. Pendant une traduction en cours,
une capsule de traduction valide et rattachée à la revue courante est plus
précise que le statut général : elle peut ainsi pointer directement vers le
correctif à éditer ou la commande d’application exacte.

Si plusieurs Works sont actifs, aucune sélection implicite n’est faite. La
sortie fournit pour chacun une commande de reprise explicite :

```text
./wikidebia resume --debate-id <debate_id> --work-id <work_id>
```

Le registre signé `.state/resume/registry.json` est reconstruit à chaque appel.
Les états distincts sont conservés sous forme d’événements signés et immuables
dans `.state/resume/events/`. Un registre absent ou altéré n’empêche donc pas
la reprise ; les événements valides et les workspaces sont relus. Un même état
n’est enregistré qu’une fois.

Cette commande n’accède pas aux wikis, ne publie rien et ne copie aucun secret.
