# Finalisation idempotente d’un workspace

La commande suivante reprend automatiquement au premier jalon manquant :

```text
./wikidebia corpus-workspace-finalize <debate_id> --work-id <work_id>
```

Elle vérifie les preuves signées, crée si nécessaire `rendered-copy/` puis
`release-copy/`, et termine par une comparaison distante strictement en lecture
seule. Les empreintes de confirmation sont dérivées des verrous validés du
workspace : il n’est plus nécessaire de les recopier entre trois commandes.

Une seconde exécution réutilise le rendu, la release et la comparaison si leurs
empreintes et leurs reçus sont encore valides. Pour relire volontairement le
wiki, utiliser :

```text
./wikidebia corpus-workspace-finalize <debate_id> --work-id <work_id> --refresh-remote
```

`--scope fr` et `--scope en` limitent la comparaison. `--comparison-id` est
accepté uniquement avec `--refresh-remote`. Cette commande ne publie aucune
page et son résultat porte toujours `remote_write_performed: false`.
