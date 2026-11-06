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

L’export alimente aussi `translation-memory/fields/index.json`. Cet index
sépare le titre canonique, le titre affiché, le résumé et chaque citation. Sa
clé contient l’identité canonique de la page, le type de champ et l’empreinte
de la valeur française exacte.
Une modification ailleurs dans la page n’empêche donc plus de retrouver les
champs restés identiques.

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

Pour une page modifiée, les champs dont la source française est encore
strictement identique sont préremplis sans approuver la page ni la citation.
Le reçu séparé `audits/translation-memory/field-reuse.json` lie chaque valeur
source et cible à son empreinte. Les champs français, les paramètres propres au
Work et les attestations de relecture ne sont jamais copiés. Une traduction
différente déjà approuvée pour la même valeur source bloque la commande.
