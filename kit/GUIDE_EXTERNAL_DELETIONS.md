# Suppressions externes acceptées

Lorsqu’une page publiée est supprimée directement sur le wiki pour une raison
éditoriale reconnue, une comparaison distante la propose normalement à la
recréation. Enregistrez la décision à partir de cette comparaison signée :

```text
./wikidebia corpus-external-deletion-accept <debate_id> \
  --work-id <work_id> \
  --comparison-id <REMOTE-AAAAMMJJ-NNN> \
  --language fr \
  --page-id <page_id> \
  --reason "raison éditoriale explicite" \
  --accepted-by <identité> \
  --confirm-plan-sha256 <empreinte_du_plan>
```

La commande exige trois preuves concordantes et signées : le reçu de
comparaison, le plan qui propose la recréation et l’inventaire qui constate
l’absence distante. Elle écrit le registre dans
`.state/external-deletions/<debate_id>.json` sans contacter le wiki.

Les comparaisons suivantes transforment la recréation correspondante en
`skip` audité uniquement si le titre, le contenu rendu et le fichier source
correspondent encore exactement à la décision. Si la source a changé, la
création reste visible et demande une nouvelle décision. Le chemin et
l’empreinte du registre sont inscrits dans le plan et le reçu de comparaison.

Le registre peut être transporté entre installations sans accès au wiki :

```text
./wikidebia corpus-external-deletion-export <debate_id> --output <registre.json>
./wikidebia corpus-external-deletion-import <debate_id> --source <registre.json>
```

Un import ne peut ni retirer une décision existante ni remplacer son contenu.
Il peut seulement ajouter une identité ou transporter sa révocation signée.
Pour réactiver la création d’une page :

```text
./wikidebia corpus-external-deletion-revoke <debate_id> \
  --language fr --page-id <page_id> --revoked-by <identité> \
  --reason "raison explicite de la révocation"
```

`continuity-sync` copie automatiquement le registre local signé dans la
projection et `--check` vérifie sa présence et son empreinte.
