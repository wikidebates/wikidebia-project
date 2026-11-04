# Guide de comparaison distante en lecture seule — Kit 2.15.21

## Commande

```bash
./wikidebia corpus-workspace-remote-compare <debate_id> \
  --work-id <work_id> \
  --confirm-release-sha256 <empreinte_de_release-copy> \
  --scope all
```

La commande ouvre les wikis uniquement en lecture. Elle ne vérifie pas les droits d’écriture, ne demande aucune confirmation d’exécution et n’appelle aucune méthode de création, modification, déplacement ou suppression.

## Base historique

Pour chaque langue, l’état publié signé est prioritaire. À défaut, le français est reconstruit depuis `data/import_provenance.json` et les fichiers `imports/fr/`; l’anglais reçoit une base vide explicite lorsqu’il s’agit d’une traduction nouvelle.

## Sorties

Les fichiers sont écrits sous `.state/remote-comparisons/<debate_id>/<work_id>/<comparison_id>/` :

- `baseline/fr.json` et `baseline/en.json` ;
- `read-checkpoint.json`, checkpoint signé après chaque lot de 50 lectures ;
- `remote-inventory.json` ;
- `read-only-events.jsonl` ;
- `update-plan.json` ;
- `plan-validation.json` et `plan-validation.txt` ;
- `comparison-receipt.json`.

Un plan contenant `manual_review` ou `blocked` reste un résultat de comparaison valable mais n’est pas exécutable.

## Reprise après une coupure

Chaque lot MediaWiki terminé est enregistré atomiquement avec les contenus,
révisions, titres, langue, portée et empreinte exacte de `release-copy`. En cas
de coupure, le message d’erreur donne une commande `corpus-workspace-finalize`
exacte contenant le même `comparison_id`. Cette commande vérifie le checkpoint,
réutilise les pages déjà scellées et ne relit que les lots manquants.

Un checkpoint modifié, associé à une autre release, à une autre portée ou à un
autre jeu de titres est refusé. Le reçu final lie l’empreinte du checkpoint et
indique séparément `checkpoint_pages_reused` et `network_pages_read`.

## Cache de validation locale

La validation complète de `release-copy` est mise en cache sous
`.state/validation-cache/remote-update/`. La clé couvre l’arbre exact du corpus,
l’empreinte des sources du validateur, sa commande, sa version, ses portées et
le code du planificateur. Une comparaison suivante sur les mêmes entrées
réutilise le rapport signé ; toute modification invalide naturellement la clé.

Le reçu de comparaison indique `validation_cache_status` (`miss` ou `hit`) et
`validation_cache_key`. Un fichier de cache altéré bloque la comparaison au lieu
d’être accepté ou remplacé silencieusement.

## Portée française différée

La comparaison distante ignore les pages anglaises absentes lorsqu’un manifeste 1.2.x pris en charge déclare explicitement `translation_status.en=deferred`. Elle ne doit ni créer d'opération anglaise ni interpréter l'absence de lien français comme un retrait.

