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
les paquets d’un autre débat est une opération séparée afin que chaque étape
reste auditée indépendamment.
