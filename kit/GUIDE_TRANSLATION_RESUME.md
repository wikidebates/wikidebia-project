# Capsule compacte de reprise

Les commandes `corpus-workspace-translation-next` et
`corpus-workspace-translation-patch` régénèrent automatiquement
`audits/translation-resume.json`. Ce fichier signé contient uniquement :

- l’identité du Work et de l’unité active ;
- les chemins et empreintes des artefacts vérifiés ;
- les compteurs de réutilisation ;
- l’action et, lorsqu’elle est déterministe, la commande suivante exacte.

Il ne recopie aucun texte français ou anglais. Une nouvelle conversation peut
donc reprendre avec la seule commande :

```text
./wikidebia corpus-workspace-translation-resume <debate_id> \
  --work-id <work_id>
```

La commande refuse une sélection, un paquet, un reçu de mémoire, un correctif
scellé ou un reçu d’application dont la signature ne correspond plus. La
capsule est locale et n’effectue aucun accès wiki.
