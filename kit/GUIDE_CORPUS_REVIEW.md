# Revue et promotion d’un build de graphe

Le kit 2.15.2 transforme un build local `graph_draft` en corpus actif `graph_validated`, sans produire ni publier les pages finales.

## 1. Préparer la revue

```bash
./wikidebia corpus-review-graph dieu_existe --prepare
```

La commande contrôle que le build se trouve exactement sous `.state/corpus-builds/dieu_existe/`, qu’il ne contient aucun lien symbolique, aucune page déclarée et aucun fichier sous `output/`. Elle crée :

- `reviews/graph_build_review.json` : décision globale, attestations, relecteur et notes ;
- `reviews/graph_placement_review.json` : revue de chaque occurrence du graphe.

Le SHA-256 du build source est enregistré. Les deux fichiers de revue sont exclus de cette empreinte afin de pouvoir être complétés, mais toute modification du graphe, du cadrage, du manifeste, du registre ou des imports impose une nouvelle préparation avec `--overwrite-review`.

Dans le workflow orchestré, une interruption peut survenir après la création de
ces registres mais avant l’enregistrement du paquet ZIP. La reprise réutilise
alors uniquement des registres encore entièrement vierges, dont l’empreinte
source et le contenu déterministe correspondent exactement. Dès qu’un champ de
revue a été modifié, la réadoption automatique est refusée. La commande bas
niveau conserve son refus par défaut ; cette tolérance est réservée à la reprise
orchestrée vérifiée.

## 2. Compléter les deux registres

Dans `graph_build_review.json`, renseigner :

- `decision` avec `approved` ou `rejected` ;
- `reviewer` et `reviewed_at` ;
- toutes les attestations ;
- `blocking_issues` ;
- des notes non vides.

Pour une approbation, toutes les attestations valent `true` et `blocking_issues` reste vide.

Dans `graph_placement_review.json`, chaque occurrence doit être couverte. Les arguments de niveau 1 attestent leur réponse directe au débat, leur autonomie et leur capacité à organiser une famille. Les occurrences subordonnées attestent que leur parent est la meilleure cible immédiate et que la relation déclarée est explicite. Chaque décision comporte une justification substantielle.

## 3. Finaliser la revue

```bash
./wikidebia corpus-review-graph dieu_existe --finalize
```

La finalisation :

1. revérifie l’empreinte du build préparé ;
2. contrôle la couverture occurrence par occurrence ;
3. exécute les portées `schema`, `coherence`, `graph`, `files` et `workflow` ;
4. scelle la revue par SHA-256 ;
5. inscrit l’empreinte structurelle du graphe ;
6. fait passer le manifeste à `graph_validated` et le cycle du graphe à `validated`.

Elle ne passe pas à `graph_locked`, ne crée aucun lot, ne crée aucune entrée de page et n’écrit rien sur MediaWiki. Une revue rejetée reste au statut `graph_draft`.

## 4. Promouvoir atomiquement

La sortie de finalisation fournit `review_sha256`. La promotion exige sa confirmation exacte :

```bash
./wikidebia corpus-promote dieu_existe \
  --confirm-review-sha256 0123456789abcdef...
```

Avant le renommage, le kit relance le validateur et vérifie que le build n’a pas changé depuis l’approbation. La cible `corpus/dieu_existe/` doit être absente. La source et la cible doivent appartenir au même système de fichiers ; aucune copie de secours non atomique n’est autorisée.

Le déplacement est effectué par renommage atomique de `.state/corpus-builds/dieu_existe/` vers `corpus/dieu_existe/`. Un reçu signé est conservé sous `.state/corpus-promotions/dieu_existe/`. Le reçu atteste notamment l’empreinte avant et après bascule et l’absence de pages finales.
