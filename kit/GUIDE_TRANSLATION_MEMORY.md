# Mémoire de traduction inter-débats

Une revue anglaise entièrement approuvée peut alimenter une mémoire locale et
portable :

```text
./wikidebia corpus-translation-memory export <debate_id> \
  --work-id <work_id>
```

La commande ne contacte aucun wiki. Elle écrit un index signé sous
`translation-memory/index.json` et un objet signé par traduction sous
`translation-memory/objects/`. La clé associe le titre canonique français
normalisé à l’empreinte exacte de son import source. Une source modifiée reçoit
donc une autre clé.

Les blocs français et les autorisations de mise à jour anglaise propres au Work
ne sont jamais exportés. Si deux revues proposent des traductions différentes
pour la même identité et la même révision françaises, l’export est bloqué au
lieu de choisir silencieusement l’une des versions.

Vérifiez toute la mémoire avec :

```text
./wikidebia corpus-translation-memory verify
```

Cette première commande construit et contrôle la mémoire. Sa réutilisation dans
les paquets d’un autre débat reste explicitement auditée :

```text
./wikidebia corpus-workspace-translation-packet <debate_id> \
  --work-id <work_id> --unit-id U001 --reuse-memory
```

L’option applique d’abord les seules correspondances exactes à la revue
brouillon, conserve les blocs français et les champs propres au nouveau Work,
remappe les identifiants internes de la page, puis écrit un reçu signé sous
`audits/translation-memory/reuse.json`. Les pages appliquées sont retirées du
paquet compact, y compris lors de la préparation ultérieure d’un correctif
d’unité. Une entrée portant le même titre mais une autre empreinte source est
signalée comme obsolète et reste intégralement dans le paquet à traduire.
