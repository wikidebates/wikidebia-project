# Paquets compacts de traduction

Après avoir produit la liste différentielle, extrayez uniquement l’unité à
travailler :

```text
./wikidebia corpus-workspace-translation-packet <debate_id> \
  --work-id <work_id> --unit-id <U001>
```

La commande vérifie le workspace, la revue et les sources françaises, puis
écrit un JSON signé et un résumé Markdown sous
`audits/translation-packets/`. Le paquet contient uniquement les arguments de
l’unité, leurs sources françaises courantes, le vocabulaire utilisé et les
libellés relationnels entrants ou sortants.

La source française intégrée à la grande revue n’est pas dupliquée dans le
paquet. Ses empreintes préparée et courante permettent de signaler une source
modifiée. La commande n’accède pas au wiki et ne publie rien.
