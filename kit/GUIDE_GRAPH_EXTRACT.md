# Guide d'extraction récursive des graphes

## Objet

`./wikidebia graph-extract` lit un débat déjà présent sur un wiki MediaWiki et produit une photographie locale de son graphe argumentatif. La commande ne crée, ne modifie, ne déplace et ne supprime aucune page.

Elle suit uniquement :

1. les `arguments-pour` et `arguments-contre` de la page `Débat` ;
2. les `justifications` et `objections` de chaque page `Argument` ;
3. les redirections nécessaires pour retrouver les titres canoniques.

Une page portant un paramètre `débat détaillé` reste dans le graphe, mais constitue par défaut une frontière. Le débat sous-jacent n'est jamais ouvert automatiquement.

Avant le parcours, la page Débat elle-même est contrôlée. Si sa cible anglaise
déclarée existe, l'extraction s'arrête immédiatement et produit la preuve
`traduction_du_débat_requise=false` ; le workflow éditorial termine alors sans
créer de corpus ni retraduire le débat.

De même, toute page Argument française qui déclare une cible anglaise au moyen de
`interlangue={{Lien interlangue|langue=en|page=…}}` est considérée comme déjà
traduite. L'arête entrante et le titre anglais sont conservés, mais les
justifications et objections de ce nœud ne sont plus parcourues : cette branche
est déjà prise en charge par la page anglaise existante.

## Commande minimale

```bash
./wikidebia graph-extract "Dieu existe-t-il ?"
```

Le dossier par défaut est :

```text
.state/graph-extract/dieu_existe_t_il/
```

## Reprise après interruption

Chaque page lue est enregistrée immédiatement dans `.cache_pages/`. Une nouvelle exécution avec le même titre et le même dossier réutilise ce cache. Le parcours logique est recalculé, mais les pages déjà acquises ne sont pas relues à distance.

```bash
./wikidebia graph-extract "Dieu existe-t-il ?"
```

Pour invalider le cache :

```bash
./wikidebia graph-extract "Dieu existe-t-il ?" --force-refresh
```

## Sorties

La commande produit :

- un registre JSON du graphe ;
- un CSV des pages uniques ;
- un CSV des relations ;
- un rapport Markdown ;
- un audit Markdown ;
- un manifeste SHA-256 ;
- un ZIP audité ;
- un snapshot du wikicode de la page Débat et de toutes les pages Argument ;
- un `snapshot_manifest.json` associant les fichiers locaux aux titres, URL, révisions, horodatages et chaînes de redirection.

Le snapshot est l'entrée de `./wikidebia corpus-init-from-snapshot`. L'extracteur lui-même reste strictement en lecture seule et ne crée aucun corpus.

## Options principales

```text
--output-dir CHEMIN       choisir un dossier de sortie situé dans l'installation
--cache-dir CHEMIN        séparer le cache des résultats
--slug TEXTE              imposer le préfixe stable des fichiers
--date AAAA-MM-JJ         fixer la date portée par les noms et manifestes
--max-pages N             arrêter avant une expansion accidentelle
--progress-every N        afficher un état toutes les N pages
--retries N               régler les nouvelles tentatives réseau
--retry-delay SECONDES    régler le délai initial de reprise
--allow-missing           exporter malgré des pages liées inexistantes
--login                   utiliser le compte Pywikibot configuré
--force-refresh           ignorer les pages déjà mises en cache
--max-depth N             limiter la profondeur en arêtes (niveau 1 = profondeur 0)
```

Sans `--max-depth`, le parcours récursif reste illimité. Avec
`--max-depth 4`, les arguments principaux et les quatre générations de relations
suivantes sont conservés ; les relations qui partiraient vers la profondeur 5
sont comptées mais ne sont ni suivies ni ajoutées au graphe extrait.

L'option suivante suit les relations locales d'une page frontière, sans ouvrir le débat sous-jacent :

```text
--follow-local-relations-at-dedicated-debate
```

Le contrôle des traductions existantes est actif par défaut. L'option suivante
est réservée au diagnostic et force le parcours sous ces frontières :

```text
--follow-local-relations-at-existing-english-translation
```

## Authentification

La lecture d'un wiki public peut fonctionner sans fichier d'identification. `--login` exige en revanche `private/pywikibot/user-config.py` et la configuration privée habituelle.

## Statut des données produites

Les fichiers sont des données d'extraction et de provenance, non un corpus `release_ready`. Ils ne remplacent ni la revue sémantique du graphe, ni la génération bilingue, ni le validateur, ni le kit de publication.

## Niveaux, profondeurs et occurrences

L’extracteur 1.2.0 distingue explicitement :

- le **niveau**, numéroté à partir de 1 pour un argument principal ;
- la **profondeur en nombre d’arêtes**, égale au niveau moins un ;
- le niveau minimal d’une page unique ;
- le niveau maximal atteint par une occurrence réutilisée ;
- les occurrences dépliées par chemins, qui peuvent être plus nombreuses que les pages et les relations.

Les champs principaux sont :

```text
niveau_minimal_maximal_pages_uniques
niveau_maximal_occurrences
profondeur_maximale_en_aretes
occurrences_argumentatives_depliees_par_chemins
occurrences_depliees_par_niveau
arguments_par_niveau
```

Le rapport Markdown contient une table « Nombre d’arguments par niveau ».
`arguments_par_niveau` compte les pages Argument uniques selon leur niveau minimal ;
les occurrences réutilisées par plusieurs chemins restent présentées séparément.

Chaque nœud expose aussi `traduction_anglaise_requise`. Le compteur
`pages_arguments_a_traduire` exclut les frontières dont la cible anglaise a été
vérifiée ; ces nœuds sont conservés uniquement pour maintenir le lien entrant.

Une ligne de niveau contenant des occurrences mais aucune page unique est normale lorsque toutes ces occurrences réutilisent des pages déjà rencontrées à un niveau inférieur.

## Feuilles et frontières

Le rapport distingue :

- `pages_sans_sortie_dans_graphe_extrait` : toutes les pages sans relation conservée ;
- `pages_terminales_reelles` : les feuilles ordinaires ;
- les frontières `débat détaillé`, dont les relations locales sont volontairement non suivies.
- les frontières `traduction anglaise existante`, dont la cible anglaise est
  conservée et dont les relations locales sont volontairement non suivies.

Les relations ignorées aux frontières sont des informations de périmètre, non des avertissements. Les vrais avertissements restent réservés aux fallbacks, pages manquantes autorisées ou structures inhabituelles.

## Régénérer les rapports sans relire le wiki

Après une mise à niveau du kit, relancer la commande initiale sans `--force-refresh`. Le cache `.cache_pages/` est réutilisé et seuls le graphe analytique, les rapports, l’audit et le paquet local sont reconstruits.

## Compatibilité des champs historiques

L’extracteur 1.2.0 conserve les champs historiques avec leur valeur 1.0.0 afin de ne pas casser les scripts existants. Ces champs sont dépréciés parce que leur nom employait « profondeur » pour un niveau commençant à 1. Les nouveaux développements doivent utiliser uniquement les champs explicites `niveau_*` et `*_en_aretes`.


## Orchestration éditoriale de haut niveau

La commande `workflow` exige un graphe portant la preuve de ce contrôle. Un
cache plus ancien est réextrait automatiquement ; un snapshot fourni
explicitement mais antérieur à l'extracteur 1.2.0 est refusé, afin qu'une
traduction ne puisse pas démarrer sans ce préflight.

Pour l'usage normal d'un débat qui doit être préparé puis traduit, préférer :

```bash
./wikidebia workflow "Titre exact du débat"
```

La commande enchaîne les opérations mécaniques et produit automatiquement les paquets de revue sous `outgoing/`. Après chaque retour de ChatGPT :

```bash
./wikidebia review-import <debate_id>
```

Voir `GUIDE_EDITORIAL_ORCHESTRATION.md`. Les commandes détaillées restent disponibles pour audit/debug.
