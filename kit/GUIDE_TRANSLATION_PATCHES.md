# Correctifs signés par unité de traduction

Préparez une copie éditable limitée à une unité :

```text
./wikidebia corpus-workspace-translation-patch <debate_id> \
  --work-id <work_id> --unit-id U001 --prepare
```

Éditez le JSON sous `reviews/en/unit-patches/`. Il ne contient aucun bloc
français éditable. Scellez ensuite le résultat :

```text
./wikidebia corpus-workspace-translation-patch <debate_id> \
  --work-id <work_id> --unit-id U001 --seal \
  --reviewer <identité> --unit-status approved --note "Relecture effectuée…"
```

Appliquez enfin l’empreinte retournée avec `--apply
--confirm-patch-sha256 <empreinte>`. La commande refuse toute dérive du paquet,
de la revue ou des sources, conserve les champs français et les identifiants
structurels, puis produit un reçu signé avant/après. Une revue déjà finalisée
doit passer par sa commande de réouverture contrôlée.
