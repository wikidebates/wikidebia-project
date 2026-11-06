# Checkpoint portable de traduction

Chaque commande de fragment exporte automatiquement un checkpoint ZIP sous
`.state/resume-checkpoints/<debate_id>/<work_id>/`. L’archive est déterministe,
compressée et décrite par un manifeste signé. Elle contient uniquement :

- le reçu du workspace ;
- la source française verrouillée nécessaire à la reconstruction ;
- la revue anglaise courante ;
- toutes les preuves d’application de fragments correspondant encore exactement
  à la revue anglaise courante ;
- la capsule, la sélection, le paquet et le fragment actifs disponibles.

Les preuves obsolètes ou altérées ne sont pas exportées. Après restauration, les
arguments couverts par les preuves conservées restent donc exclus des paquets
d’unité, sans devoir recharger leur contexte.

Les configurations, identifiants, variables d’environnement, caches, copies de
rendu, releases et sauvegardes générales ne font pas partie de la liste blanche.

Un export manuel reste possible :

```text
./wikidebia corpus-workspace-translation-checkpoint <debate_id> \
  --work-id <work_id> --export
```

Pour restaurer l’archive dans un environnement où le Work n’existe plus :

```text
./wikidebia corpus-workspace-translation-checkpoint \
  --restore .state/resume-checkpoints/<debate_id>/<work_id>/<empreinte>.zip
```

La restauration contrôle les chemins, la taille décompressée, l’inventaire et
chaque SHA-256 avant d’écrire. Un Work absent est installé par échange atomique.
Sur un Work existant, seuls les fichiers manquants sont ajoutés et tout contenu
divergent bloque l’opération ; aucun état plus récent n’est écrasé. L’opération
n’accède pas aux wikis et n’effectue aucune publication.
