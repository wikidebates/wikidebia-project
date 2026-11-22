# Préparer uniquement la prochaine unité

La commande suivante remplace la construction manuelle de la liste, le choix
d’une unité, l’application de la mémoire, la création du paquet et la
préparation du correctif :

```text
./wikidebia corpus-workspace-translation-next <debate_id> \
  --work-id <work_id>
```

Elle choisit la première unité encore nécessaire dans l’ordre signé de la
revue. La mémoire `translation-memory/` est appliquée par défaut ; utilisez
`--no-memory` pour une exécution explicitement isolée. La sortie machine ne
contient que l’unité, les chemins du paquet et du correctif, leurs empreintes,
les compteurs de réutilisation et le modèle de commande de scellement.

La sélection est signée dans `audits/translation-next.json`. Si aucune unité ne
reste, la commande indique soit la finalisation possible, soit les contrôles
globaux encore nécessaires. Elle n’accède jamais au wiki.

## Sortie concise pour Codex Cloud

`corpus-workspace-translation-next` affiche l’unité, le paquet, le correctif,
le contexte à lire et le modèle de scellement après revue. Les artefacts
signés et les contrôles restent identiques. Le JSON intégral est disponible
sur demande :

```sh
./wikidebia corpus-workspace-translation-next <debate_id> --work-id <work_id> --machine-readable
```

Aucune revue humaine n’est automatisée ni dispensée.
