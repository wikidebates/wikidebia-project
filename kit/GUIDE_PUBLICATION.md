# Guide de publication et de reprise Wikidéb’IA 2.15.9

## Extraire le graphe d'un débat existant

```bash
./wikidebia graph-extract "Dieu existe-t-il ?"
```

L'extraction est en lecture seule et écrit par défaut dans `.state/graph-extract/dieu_existe_t_il/`. Relancer la même commande réutilise le cache par page. `--force-refresh` force une nouvelle lecture distante. Le ZIP audité contient le graphe, les inventaires CSV, les rapports et le snapshot du wikicode.


## Comparer un corpus final sans l’exécuter

```bash
./wikidebia corpus-workspace-remote-compare <debate_id> \
  --work-id <work_id> \
  --confirm-release-sha256 <empreinte_de_release-copy> \
  --scope all
```

Cette commande est distincte de `update --dry-run` : elle part du workspace et de sa `release-copy/`, conserve un dossier de comparaison immuable et n’offre aucune voie d’exécution. Le plan produit doit être repris explicitement par une phase ultérieure.


## Revoir puis exécuter un plan du workspace

Après la comparaison et la revue formelle, préparer le préflight :

```bash
./wikidebia corpus-workspace-plan-execute <debate_id> \
  --work-id <work_id> \
  --comparison-id <comparison_id> \
  --prepare \
  --confirm-acceptance-sha256 <empreinte>
```

Puis exécuter uniquement après examen de ce préflight :

```bash
./wikidebia corpus-workspace-plan-execute <debate_id> \
  --work-id <work_id> \
  --comparison-id <comparison_id> \
  --execute \
  --confirm-preflight-sha256 <empreinte>
```

La deuxième commande effectue réellement les écritures distantes. Toute divergence observée juste avant l’exécution bloque le plan.

## Nouveau débat

Déposer le ZIP du corpus dans `incoming/`, puis lancer `./wikidebia publish [SÉLECTEUR] --scope all`.

### Reprise de publication après minuit

La date civile ne modifie plus le contenu à publier : le changement de jour ne nécessite aucun recalcul du plan. Les vérifications de révision, de contenu, de configuration, de résumé et de balises demeurent obligatoires. Un ancien plan signé qui imposait une date de création de page ne doit pas être exécuté ; reconstruire et autoriser son remplacement.

### Noms français normalisés à l’import

Pour `update --archive <SÉLECTEUR> --scope fr --interlanguage-only`, une page
introuvable sous le nom du manifeste peut être retrouvée sous le nom exact
consigné dans `data/import_provenance.json`, lorsque la seule différence est
la normalisation d’une apostrophe typographique en apostrophe droite.
Le fichier importé doit correspondre à son empreinte et la page distante à la
révision et au contenu importés, ou à ce contenu déjà augmenté du seul lien
interlangue attendu. Toute autre divergence reste bloquante.

Le nom réellement retrouvé est signé dans le plan, utilisé pour l’écriture
et conservé dans l’état publié. Cette reprise ne crée ni ne renomme de page
française, ne réécrit aucun autre paramètre et ne change pas l’archive.

## Débat déjà publié — corpus installé

Lancer `./wikidebia update <debate_id> --dry-run`, examiner le plan, puis relancer sans `--dry-run`. Sans `--archive`, la commande ne consulte que `corpus/<debate_id>/` et ne sélectionne jamais implicitement un ZIP de `incoming/`.

## Débat déjà publié — nouvelle archive

Utiliser explicitement :

```bash
./wikidebia update --archive <SÉLECTEUR> --dry-run
./wikidebia update --archive <SÉLECTEUR>
```

À partir du kit 2.16.12, toute opération mutante issue de cette archive (`create`, `update`, `move`, `redirect` ou `delete`) reçoit dans le plan signé un **résumé MediaWiki individualisé**. Pour une mise à jour de contenu, ce résumé est calculé à partir du diff réel des paramètres de la page et regroupe les changements par fonction éditoriale (par exemple résumé, références, mots-clés, rubriques ou introduction). Un nouveau plan de cette génération ne publie jamais une mutation avec le résumé générique `Corrections`. L’exécuteur recalcule le résumé attendu immédiatement avant l’écriture à partir du contenu distant relu et du contenu désiré signé ; toute divergence bloque l’opération.

Les conventions spécialisées restent prioritaires lorsqu’elles sont plus précises, notamment l’ajout d’un lien interlangue français, les renommages canoniques, les fusions en redirection et les retraits. Le résumé réellement enregistré par MediaWiki est relu avec le contenu, la balise `chatgpt` et la révision.

L’archive est extraite dans une zone temporaire de staging. La simulation ne modifie pas `corpus/`, puis le staging est supprimé. Le corpus actif n’est remplacé qu’après une exécution réussie ou une attestation `no_changes` réussie.

Un plan contenant `blocked` ou `manual_review` est bloquant et ne produit ni écriture MediaWiki, ni reçu de succès, ni nouvel état publié. Un plan entièrement `skip` déclenche une relecture distante complète, produit une attestation signée `no_changes` et actualise l’état publié sans éditer le wiki.

## Portées partielles

Lorsque la portée demandée ne contient aucune opération mutante, la commande renvoie `no_changes_in_scope` sans exécuter ni promouvoir un staging. Une reprise avec `--no-delete` conserve les pages à supprimer comme `pending_delete`; elles peuvent ensuite être traitées avec `--only-delete`.

## Mise à niveau des composants

Un seul fichier suffit. Vider `updates/`, y copier soit le bundle `WIKIDEBIA_SOURCES_COMPLETES_*.zip`, soit la livraison complète `WIKIDEBIA_LIVRAISON_*.zip`, puis lancer `./wikidebia upgrade`.

## Publication française avec anglais différé (1.2.35, compatible avec les corpus historiques 1.2.x)

Le corpus déclare `translation_status.en=deferred`, ne manifeste que les pages françaises et omet `interlangue`. Utiliser `./wikidebia publish --scope fr` ou `./wikidebia update --archive <archive> --scope fr`. Toute portée anglaise est refusée jusqu'au passage à `ready` ou `published`.

## Résumé individualisé des créations anglaises traduites

Lorsqu’une page anglaise est créée depuis une traduction française verrouillée et que `translation_status.en` vaut `ready` ou `published`, le plan porte un résumé propre à la page :

```text
Translation of the French page: [[:fr:X|X]]
```

`X` est le titre canonique français de la même `page_id`. Le titre est résolu depuis le manifeste, le résumé est signé avec l’action, recalculé avant l’écriture et contrôlé sur la révision relue. Le lien d’historique ne remplace pas `{{Lien interlangue}}` dans la page française.


## Ajouter rétroactivement `translated-fr`

Après une publication anglaise FR→EN déjà effectuée avec seulement `chatgpt`, lancer d’abord `./wikidebia tag-translated-fr DEBAT --dry-run`. Si le plan ne contient aucun blocage, lancer `./wikidebia tag-translated-fr DEBAT`. Le kit utilise l’état publié anglais pour identifier les révisions de création, exige leur résumé individualisé de traduction et ajoute uniquement la balise `translated-fr` via l’API MediaWiki `action=tag`. Cette opération ne crée aucune révision et ne modifie aucun contenu.

Pour les futures créations anglaises FR→EN, lorsque `translation_status.en` vaut `ready` ou `published`, le plan signé porte `change_tags: ["chatgpt", "translated-fr"]` pour chaque page anglaise et la relecture de la révision vérifie les deux balises.


## Orchestration éditoriale de haut niveau

Pour l'usage normal d'un débat qui doit être préparé puis traduit, préférer :

```bash
./wikidebia workflow "Titre exact du débat"
```

La commande enchaîne les opérations mécaniques et produit automatiquement les paquets de revue sous `outgoing/`. Après chaque retour de ChatGPT, placer le ZIP corrigé dans `incoming/`, puis :

```bash
./wikidebia review-import
```

Si plusieurs paquets de revue sont présents, utiliser uniquement l’identifiant du débat : `./wikidebia review-import <debate_id>`.

Voir `GUIDE_EDITORIAL_ORCHESTRATION.md`. Les commandes détaillées restent disponibles pour audit/debug.


### Checkpoint français automatique

Après validation de la revue française de contenu, `review-import` publie automatiquement le français scellé avant de préparer la traduction anglaise. Cette publication utilise les mêmes plans signés, résumés individualisés, gardes de révision et relectures que `update`; elle ne nécessite pas une commande `update` séparée.


## Deux checkpoints français dans le workflow éditorial

Le workflow de reprise publie le français deux fois avant traduction :

1. après graphe + titres : relations, placements, renommages, titres affichés et retraits/fusions validés ;
2. après contenu : rubriques, mots-clés, références et autres champs ouverts ; sur des pages préexistantes, l’introduction et les résumés historiques restent inchangés par défaut, mais un `authorized_change` sélectionne la valeur finale propriétaire qui est rendue et publiée dans ce même checkpoint ; une portée structurée limite le delta autorisé et l’absence historique reste une absence sauf création nominativement autorisée.

Le premier checkpoint préserve le contenu/classification importé ; le second se calcule contre l’état publié du premier et interdit les mutations structurelles. Les deux utilisent des résumés MediaWiki individualisés.

### Arrêt avant publication bilingue finale

Après le rendu et la préparation des plans, le workflow s'arrête à `publication_prepared` sans écriture finale. Les plans et le préflight signés se trouvent dans `.state/final-publication/<debate_id>/<work_id>/`. Relisez-les avant de confirmer :

```bash
./wikidebia workflow-publish <debate_id> --confirm-preflight-sha256 <sha256>
```

La commande de publication ou de reprise doit viser ce préflight signé ; une divergence de contenu ou de révision distante bloque l'opération. Ce verrou ne modifie pas les deux checkpoints français précédents, qui possèdent leurs propres contrats de publication.

