# Démarrer un corpus français nouveau

Ce parcours transforme un plan compact de cadrage et de graphe en fichiers
canoniques de création. Il ne conçoit pas le débat à partir d'un simple sujet :
les raisonnements, titres, placements et lots sont des décisions éditoriales.
Le kit calcule les relations, profondeurs, compteurs, chemins, manifestes et
empreintes. Il n'invente ni recherche, ni source, ni approbation, ni page wiki.

## Préparer le plan et sa revue

Copier `kit/examples/creation_plan.example.json` dans `incoming/plan.json`,
puis remplacer **tout le contenu illustratif** par les décisions réelles.
L'exemple est fictif, non approuvé et non publiable.

```sh
./wikidebia creation-prepare --plan incoming/plan.json
```

Le plan utilise `wikidebia-creation-plan-1.0` : `debate_id`, `scope`, `nodes`,
`placements` et `batches`. `scope` distingue question, proposition, périmètre,
interprétations et exclusions. Chaque nœud possède son identifiant A..., son
titre canonique et son titre affiché. Ses rubriques et mots-clés sont des
propositions initiales : ils ne constituent pas une classification validée.
Ne pas renseigner de titres anglais, de dates de page, de chemins techniques ou
de statuts de production dans le plan.

Chaque occurrence O... indique son nœud, son parent immédiat, sa relation, son
ordre et son rôle primaire ou secondaire. Une racine porte `branch=pro|con` et
`relation=null`. Un enfant porte `branch=null` et une relation `justification`
ou `objection`. Un raisonnement réutilisé conserve une seule page et plusieurs
occurrences. Les lots déclarent explicitement leurs nœuds ; chaque nœud est
propriété d'un seul lot. Les dépendances explicites appartiennent aux lots
antérieurs, sans quoi la reprise ordonnée pourrait rester bloquée.
Aucun nombre maximal d'arguments ou plafond éditorial de profondeur n'est imposé.
Les limites techniques de taille des fichiers/ZIP restent des protections locales.

La commande produit `package_path` dans `outgoing/`, mais **aucun corpus installé**.
Les contrôles structurels existants sont exécutés sur une copie préparatoire.
En cas d'erreur de validation, un ZIP de diagnostic avec les codes concrets est
conservé dans `outgoing/` ; ce ZIP n'est pas un paquet de revue approuvable.

Le paquet de revue réutilise `wikidebia-chatgpt-review-package-1.0`, avec le type
`fr_creation_graph`. Lire les instructions et le contexte : plan exact, graphe
lisible, lots, extraits normatifs et rapport structurel. Seul
`editable/REVIEW.json` est modifiable. Tous les marqueurs d'approbation sont
initialement faux ou en attente.

## Réaliser la revue, puis initialiser

La revue nomme le relecteur, date son intervention (ISO 8601 avec fuseau), motive
le cadrage, examine les omissions et réutilisations, couvre chaque titre et chaque
occurrence. Elle doit distinguer arguments principaux autonomes et arguments
subordonnés visant leur meilleure cible immédiate. Ne jamais remplir ces
attestations automatiquement pour faire passer le contrôle.

Le kit contrôle les déclarations, leur couverture et leur rattachement au contenu
exact. **Il ne vérifie pas indépendamment l'identité du relecteur ni la vérité
de son jugement sémantique.** Une empreinte n'est pas une signature d'identité.
La réalité de la revue reste une responsabilité éditoriale.

Rendre le ZIP complet dans `incoming/`, puis :

```sh
./wikidebia creation-init --archive incoming/plan_revu.zip
```

Sans `--archive`, la commande exige un seul ZIP de type `fr_creation_graph`.
Elle ne passe pas par `review-import` et ne déclenche aucun checkpoint distant.
Une revue `pending`, incomplète, datée avant sa préparation ou contenant des
blocages ne permet pas l'installation. Un rejet est conservé et ne crée aucun
corpus. Un paquet rejeté ne peut ensuite être transformé en approbation : corriger
le plan source et refaire `creation-prepare` puis une revue complète du nouveau
plan. Les titres et placements ne se corrigent pas en modifiant le contexte du ZIP.

Après approbation, le kit revalide la structure, enregistre la revue, verrouille
le graphe et les titres français, puis installe `corpus/<debate_id>`. Il prépare
ensuite automatiquement le premier paquet de rédaction de la page Débat avec
`creation-package`. Le champ `draft_package.package_path` indique ce ZIP.
Si cette dernière préparation échoue, `initialized_next_blocked` indique que le
corpus est bien installé ; le diagnostic et la commande de reprise sont fournis.
Il ne faut pas supprimer le corpus pour recommencer.

Toutes les pages restent `planned`, sans fichier `.wiki`
et sans validation de contenu. L'anglais reste `deferred`. Le registre documentaire
est vide ; aucune attestation de recherche ou de contenu n'est fabriquée. Une page
Argument française explicitement nouvelle et encore physiquement absente peut
attendre sa recherche d'appellation consacrée pendant les seuls stades de graphe.
Dès qu'elle est produite, ou qu'une revue est déclarée, le contrôle ordinaire
reste obligatoire. Cela ne dispense jamais une page produite de sa recherche.

Les revues de classification, de contenu, de documentation, les recherches
d'omissions et les validations finales restent distinctes et obligatoires.
`graph_locked` n'est ni `release_ready`, ni une autorisation de publication.

## Intégrité et reprise

Le paquet est lié aux octets du plan, aux entrées normatives, au producteur et à
la copie préparatoire. Toute modification de ces entrées avant l'installation
impose une nouvelle préparation/revue. Les fichiers supplémentaires, les chemins
non canoniques, liens symboliques, fichiers liés en dur et retours étrangers sont
refusés. La même préparation inchangée réutilise son paquet exact.

L'installation initiale utilise **Linux `renameat2(RENAME_NOREPLACE)`**, un verrou
POSIX coopératif et un seul renommage de répertoire, sur le même système de
fichiers. Un corpus existant n'est jamais remplacé, même vide ou apparu entre
le contrôle et le renommage. Sans cette capacité, l'opération bloque plutôt que
de se rabattre sur un remplacement dangereux. Ne pas modifier simultanément le
corpus ou l'état de préparation avec un outil non coopérant.

Un arrêt de processus avant le renommage ne laisse aucun corpus installé ; après
le renommage, le corpus et son reçu sont présents ensemble. Relancer la même
commande avec le même ZIP reprend sans réécriture. Un reçu historique ne remplace
jamais les brouillons produits depuis : `current_state_matches_receipt=false`
signale une progression ou divergence ultérieure, sans la réparer automatiquement.
Ces tests de processus ne certifient pas la résistance à toute panne de stockage.
La transaction d'import des brouillons conserve ses limites propres, distinctes,
décrites dans `GUIDE_CREATION_IMPORT.md`.

Les paquets, réponses et copies préparatoires restent locaux dans `incoming/`,
`outgoing/`, `.state/creation-init/` et `corpus/`, tous exclus de Git. Le ZIP entrant
est conservé ; l'archiver après succès ou utiliser `--archive` pour le retour suivant.
Aucun appel réseau, modèle ou wiki n'est effectué par ce parcours.

## Quota et tests

L'économie recherchée est d'éviter de faire produire puis corriger par l'IA les
fichiers techniques redondants. Elle ne repose pas sur une réduction du nombre
d'arguments ou de la recherche. Aucun gain réel de tokens ou de crédits n'a été
mesuré ; les compteurs réels restent inconnus.

```sh
python -m pytest -q kit/tests/test_wikidebia_creation_init.py
PYTHONPATH=validator/src python -m pytest -q validator/tests/test_creation_planned_name_discovery.py
```
