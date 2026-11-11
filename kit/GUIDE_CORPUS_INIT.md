# Initialisation d’un corpus depuis un snapshot

Le kit 2.15.21 transforme un paquet produit par `graph-extract` en corpus local au statut `graph_draft`.

```bash
./wikidebia corpus-init-from-snapshot \
  .state/graph-extract/dieu_existe \
  --debate-id dieu_existe \
  --short-code DIEU
```

Le résultat est écrit par défaut dans :

```text
.state/corpus-builds/<debate_id>/
```

## Séparation entre import et sortie normative

Les wikicodes récupérés sont conservés sous :

```text
imports/fr/debate/debate.wiki
imports/fr/arguments/A0001.wiki
```

Ils constituent une provenance historique. Ils ne sont pas copiés dans `output/fr/` et ne sont pas déclarés comme pages générées ou validées. Les fichiers de sortie restent `pending` jusqu’au Work éditorial.

## Fichiers construits

- `manifest.json` au statut `graph_draft` ;
- `scope.json` provisoire ;
- `data/registre_debat.json` ;
- `data/import_provenance.json` ;
- `data/sources.json` ;
- `graph/graphe_argumentatif.json` ;
- `graph/graphe_argumentatif.md` ;
- registres de revue initialisés à `pending` ;
- rapport d’import ;
- rapports de validation structurelle initiale.
- contrat de construction `reports/corpus_build_contract.json` ;
- reçu cryptographique `reports/corpus_build_receipt.json` après validation réussie.

## Identifiants et occurrences

Les identifiants sont déterministes pour un même snapshot :

- nœuds : `A0001`, `A0002`, etc. ;
- relations : `E00001`, `E00002`, etc. ;
- occurrences : `O00001`, `O00002`, etc.

Une occurrence principale est créée pour chaque nœud. Une réutilisation crée une occurrence secondaire sans redéploiement de ses enfants, conformément au modèle normatif du registre. Le nombre d’occurrences normatives peut donc être inférieur au nombre de chemins du graphe entièrement déplié indiqué par l’extracteur. La sortie machine distingue désormais `source_unfolded_occurrences` et `normative_occurrences`; l’ancien champ `occurrences` reste un alias des occurrences normatives.

## Validation initiale

La commande lance automatiquement les portées suivantes du validateur local :

- `schema` ;
- `coherence` ;
- `graph` ;
- `files` ;
- `workflow`.

Elle n’exécute pas encore les contrôles `wikicode` ou `editorial`, car les pages importées ne sont pas des sorties normatives.

Une validation réussie produit ensuite un reçu qui lie l’empreinte du snapshot et
du graphe, les paramètres et versions de construction, puis l’empreinte de tous
les fichiers du build. Une reprise ne peut considérer un build comme
`valid_and_matching` que si le reçu, le contenu actuel et le contrat attendu
correspondent exactement. Un build ancien sans reçu reste `unverified`; un reçu
dont la source ou les options diffèrent est `stale`; toute modification après
validation rend le reçu `invalid`. Aucun de ces états ne déclenche un
écrasement automatique.

Le contrat est écrit avant la validation. Si une interruption survient entre la
fin de la construction et le reçu, l’orchestrateur compare ce contrat au
snapshot courant, relance uniquement la validation locale, puis écrit le reçu.
Si un reçu valide et exactement correspondant existe déjà, la construction et
la validation sont toutes deux réutilisées et le workflow passe directement à
la revue du graphe.

## Options utiles

```bash
--output-dir CHEMIN
--scope-summary TEXTE
--overwrite
--skip-validation
```

`--skip-validation` ne produit volontairement aucun reçu réutilisable.

`--output-dir`, lorsqu’il est utilisé, doit rester sous `.state/corpus-builds/`. `--overwrite` ne concerne que le build local sélectionné dans cette zone. L’argument positionnel doit désigner la racine complète du paquet `graph-extract` ou son ZIP audité, et non le seul sous-dossier `snapshot/`, car le graphe JSON et le manifeste SHA-256 sont également requis. Le manifeste complet du paquet d’extraction, le graphe, le snapshot et chaque page importée sont revérifiés avant toute écriture locale. Aucune écriture MediaWiki et aucune promotion vers `corpus/` ne sont effectuées.
## Étape suivante

Le build reste volontairement sous `.state/corpus-builds/`. Sa revue et sa promotion utilisent ensuite :

```bash
./wikidebia corpus-review-graph <debate_id> --prepare
./wikidebia corpus-review-graph <debate_id> --finalize
./wikidebia corpus-promote <debate_id> --confirm-review-sha256 <empreinte>
```

Ces commandes ne génèrent pas encore de pages. Voir `GUIDE_CORPUS_REVIEW.md`.


## Profondeur

Sans limite dans le snapshot, le build utilise `depth_policy.limit_policy=unbounded`.
Lorsqu’une extraction a été produite avec `--max-depth`, le build conserve au
contraire `limit_policy=bounded`, la profondeur demandée, la liste des nœuds de
frontière et le nombre de relations non suivies. Le checkpoint français ne
réécrit jamais les paramètres relationnels de ces pages de frontière : leurs
relations historiques hors périmètre restent intactes.
