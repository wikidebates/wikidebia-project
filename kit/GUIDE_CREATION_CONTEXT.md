# Contexte ciblé pour la création de débats

`creation-context` prépare une aide de lecture locale pour un débat français
réellement nouveau. Il ne traduit rien, ne contacte aucun wiki, ne consomme
aucune API de modèle et ne change ni corpus, ni registre, ni statut de validation.

## Avant de commencer une étape

```sh
./wikidebia creation-context --stage cadrage
./wikidebia creation-context --stage graphe
./wikidebia creation-context --stage debat-fr
./wikidebia creation-context --stage arguments-fr
./wikidebia creation-context --stage validation-fr
```

La sortie compacte donne `context_path`. Lire `INSTRUCTIONS.md`, puis
`NORMATIVE_CONTEXT.md` dans ce dossier. Ne pas relire automatiquement la source
unifiée, ses changelogs et les guides de traduction. Les extraits sont repris
**octet pour octet**, sans résumé IA ni normalisation, depuis la norme consolidée
active désignée par `norms/VERSIONS.json`. Ce numéro localise la source ; il
n'active ni ne désactive aucune règle éditoriale.

`kit/configs/creation_context_sections.json` classe chaque section et explique sa
portée. Toute section ajoutée, renommée, retirée ou réordonnée bloque la
préparation jusqu'à une mise à jour explicite de ce classement. Une modification
du corps d'une section est copiée exactement et change l'empreinte du contexte.
Le manifeste conserve les chemins, lignes et empreintes de toutes les sections,
y compris celles non lues pour cette étape. Les sources complètes restent
accessibles pour une question transversale ; aucune règle n'est abrogée.

## Pour un lot ou un argument déjà inscrit au registre

```sh
./wikidebia creation-context --stage arguments-fr \
  --corpus corpus/mon_debat --batch-id FR-A-001

./wikidebia creation-context --stage arguments-fr \
  --corpus corpus/mon_debat --node-id A0001
```

`--corpus` est un chemin relatif au projet. Le manifeste doit déclarer
`page_origin=new` pour le débat et les pages sélectionnées. Un corpus importé
ou une provenance absente ne sont jamais assimilés silencieusement à une création.
Le registre canonique 1.0 et les fichiers déclarés dans `core_files` restent
les sources de vérité. L'outil n'initialise pas un corpus inexistant.

`CORPUS_CONTEXT.json` contient le cadrage, la vue globale des titres, toutes les
relations et occurrences, puis les textes du lot choisi, de ses dépendances
explicitement déclarées et de ses parents/enfants directs. Une réutilisation
conserve ses occurrences et ses libellés contextuels : elle n'est pas dupliquée.
Les autres textes ne sont pas copiés. Les dépendances sont en lecture seule ;
leur inclusion ne demande pas de les réécrire. Une revue globale du graphe et
une passe inter-lots restent nécessaires, et des recherches doivent compléter les
sources du dossier si elles ne couvrent pas tous les raisonnements pertinents.

Les notices documentaires sont sélectionnées par identifiant ou usage réciproque.
Les éditions du même `equivalence_group` sont incluses pour ne pas masquer un
équivalent français. Chaque notice n'apparaît qu'une fois, mais ses usages
page par page, leurs preuves et leurs réserves sont conservés. Cette sélection
n'est pas une recherche nouvelle, une validation des sources ni une mémoire
documentaire inter-débats.

## Relecture ciblée et limites de reprise

Relancer la même commande avec les mêmes entrées réutilise le dossier exact
(`status=reused`). Les empreintes des entrées et des sorties sont revérifiées.
Une modification du registre, du cadrage, du registre documentaire, d'une page
lue ou de la norme produit un autre contexte. Une sortie altérée est refusée
sans écrasement. Les chemins privés, traversées et liens symboliques sont refusés.
Les dossiers dérivés restent sous `.state/creation-context/`, hors Git.

`creation-context` reste une aide de lecture : il n'initialise pas les Works,
ne déclare aucune page terminée et n'importe pas de réponse éditoriale.
La commande complémentaire `creation-next` choisit désormais le prochain travail
à partir des états canoniques ; voir `GUIDE_CREATION_RESUME.md`. Les états déclarés restent informatifs.
Il ne remplace ni les handoffs, ni `resume`, ni `review-import`, ni les contrôles
de cohérence, de recherche d'omissions, de qualité et de publication existants.
La file dérivée de `creation-next` ne remplace aucun état du corpus. L'import
transactionnel des réponses et la validation incrémentale restent à développer.

## Mesures honnêtes

`measurement` distingue les octets de la norme source, ceux des extraits et le
volume total des fichiers recommandés à la lecture. Le manifeste d'audit n'est
pas inclus dans ce dernier volume. Ces nombres mesurent la taille de fichiers
produits, pas les lectures effectives du modèle. `actual_billed_tokens` et
`actual_codex_cloud_credits` restent `null`. Aucun pourcentage d'économie de quota
n'est déduit du poids du dossier, de sa réutilisation ou de son temps de calcul.

## Non-régression

```sh
python -m pytest -q kit/tests/test_wikidebia_creation_context.py \
  kit/tests/test_creation_documentation_consistency.py
```

Le second module vérifie l'alignement des six documents actifs dans les deux
composants normatif et validateur. La règle `DFR-045` n'impose plus le minimum
périmé de deux sources par paramètre. Les sources sont choisies pour leur apport
réel, sans réduire artificiellement la documentation ; les catégories vides
sont omises et les doublons entre orientations restent interdits. Les snapshots
historiques et les changelogs restent intacts.

## Notes documentaires conservées

Lorsque `data/creation_research.json` existe, le contexte ajoute les recherches
et observations de la sélection et de ses dépendances, pas le carnet entier.
Les drapeaux `page_basis_changed`, `resource_basis_changed` et `recheck_due`
signalent les réexamens nécessaires. Aucune note n'est une validation de source.
Voir `GUIDE_CREATION_RESEARCH.md` pour l'enregistrement dans le ZIP de brouillons.

## Démarrage sans corpus

Pour initialiser les fichiers techniques depuis un plan de création réellement
revu, utiliser le parcours distinct `creation-prepare` puis `creation-init` de
`GUIDE_CREATION_INIT.md`. `creation-context` reste une aide de lecture sans mutation.
