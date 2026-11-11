# Mesure et maintenance prudente de `.state`

La commande suivante inspecte uniquement les fichiers locaux, mesure leur taille
logique et les blocs alloués visibles via `st_blocks`, puis produit un plan signé :

```sh
./wikidebia state-maintenance --output .state/maintenance-plan.json
```

Seules les sauvegardes nommées
`<WORK>.review-import-backup-<8 hex>` peuvent devenir candidates. Le workspace
canonique doit être terminal `published` et lié à un reçu de réconciliation
post-publication signé. Les liens symboliques, arbres divergents et Works non
terminaux sont exclus.

La lecture du plan ne supprime rien. Une suppression exige simultanément le fichier
exact et son empreinte :

```sh
./wikidebia state-maintenance \
  --apply-plan .state/maintenance-plan.json \
  --confirm-plan-sha256 <empreinte exacte>
```

Chaque arbre est contrôlé une seconde fois, déplacé atomiquement dans une quarantaine
propre au plan, attesté par un checkpoint signé, puis supprimé. Une coupure reprend
depuis le checkpoint. Le reçu final énumère exactement les chemins supprimés. Cette
action est irréversible ; conserver le plan et le reçu avec les preuves du Work.

`allocated_bytes_unique_inodes` mesure les blocs attribués par le système de fichiers
sans recompter les hardlinks. Cette valeur ne sait pas reconnaître les extents partagés
par reflink. `filesystem.available_bytes` porte sur tout le volume et peut varier sous
la charge : aucune de ces valeurs ne doit être présentée comme une mesure de crédits ou
de tokens. La commande ne contacte jamais les wikis.
