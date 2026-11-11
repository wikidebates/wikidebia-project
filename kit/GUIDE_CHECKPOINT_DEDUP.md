# Déduplication sécurisée des checkpoints (#79)

La commande est en lecture seule par défaut :

```sh
python3 kit/scripts/wikidebia_checkpoint_store.py --project-root .
```

L’inventaire signale aussi `hardlinked_files`. Une valeur non nulle indique des
checkpoints créés par l’ancienne implémentation à liens physiques. Ils peuvent
être séparés, sans déduplication simultanée, avec :

```sh
python3 kit/scripts/wikidebia_checkpoint_store.py --project-root . \
  --repair-hardlinks
```

Chaque checkpoint concerné est recopié et remplacé atomiquement après contrôle
SHA-256. L’objet historique éventuel reste intact et chaque chemin obtient un
inode indépendant.

L'option `--apply` nécessite un système de fichiers Linux prenant en charge
les reflinks (copy-on-write, FICLONE). Elle échoue sans modification si le
système de fichiers ne les prend pas en charge. Aucun lien physique n'est créé.
Les fichiers historiques peuvent toujours être restaurés individuellement.
L'option `--prune` est temporairement désactivée par sécurité.

Ne pas exécuter `--apply` sur les sauvegardes de production avant d'avoir
vérifié la restauration dans un environnement isolé. Les valeurs `linked_bytes`
et `potential_duplicate_bytes` sont logiques et ne constituent pas une
mesure des blocs effectivement économisés.
