# Déduplication locale des checkpoints (issue #65)

Commande autonome, hors ligne, sans écriture wiki :

```sh
python3 kit/scripts/wikidebia_checkpoint_store.py --project-root .
python3 kit/scripts/wikidebia_checkpoint_store.py --project-root . --apply
python3 kit/scripts/wikidebia_checkpoint_store.py --project-root . --apply --prune
```

Par défaut, l'inventaire est **en lecture seule**. `--apply` crée un magasin
d'objets SHA-256 sous `.state/checkpoint-objects/` et remplace uniquement les
ZIP **strictement identiques** par des liens physiques sur le même volume.
Les noms de checkpoints et leur format ZIP historique ne changent pas ; les
restaurations existantes continuent de fonctionner. Les écritures utilisent un
fichier temporaire et un remplacement atomique. Aucun secret n'est exporté.

`--prune` ne supprime que les objets du magasin sans autre lien physique
(`st_nlink == 1`), après vérification de leur empreinte. Il ne supprime
jamais un checkpoint utilisateur. La déduplication n'est pas automatique,
notamment parce qu'un système de fichiers peut interdire les liens physiques.
Le champ `potential_duplicate_bytes` est une estimation logique, pas une
mesure de blocs effectivement récupérés.
