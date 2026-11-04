# Liste différentielle de traduction

Pour une reprise de traduction, ne chargez pas d’emblée la revue anglaise
complète. Produisez d’abord la liste des seules unités à reprendre :

```text
./wikidebia corpus-workspace-translation-worklist <debate_id> --work-id <work_id>
```

La commande compare chaque source française intégrée à la revue avec les
verrous français actuels. Elle retient uniquement :

- `Debate` si sa traduction ou sa source a changé ;
- les unités contenant un argument incomplet, rouvert ou lié à une source
  française modifiée ;
- les entrées de vocabulaire et les libellés relationnels encore incomplets ;
- les attestations globales restantes.

Les arguments déjà approuvés dans une unité close restent hors de la liste. Les
sorties signées sont écrites dans :

```text
audits/en_translation_worklist.json
audits/en_translation_worklist.md
```

La sortie terminal reste compacte et indique les compteurs ainsi que les deux
chemins. Si plus rien ne manque dans une revue encore en brouillon,
`next_command` fournit directement la commande de finalisation. La commande ne
contacte pas MediaWiki et ne publie rien.
