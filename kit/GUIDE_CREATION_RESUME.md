# Reprise de la création française par argument

Cette entrée complète `creation-context` : elle retrouve le travail restant dans
un corpus français nouveau **déjà constitué**, dont le graphe et les titres
français sont verrouillés et dont l'anglais est explicitement `deferred`.
Elle n'initialise pas le corpus et ne modifie aucune donnée canonique.

## Commandes

```sh
./wikidebia creation-status --corpus corpus/mon_debat
./wikidebia creation-next --corpus corpus/mon_debat
./wikidebia creation-next --corpus corpus/mon_debat --max-pages 1
```

`creation-status` inspecte sans écrire, même dans `.state/`. Sa sortie compacte
indique les comptes, la prochaine action et les identifiants concernés.
`creation-next` ajoute le contexte de lecture ciblé et une file dérivée scellée
sous `.state/creation-resume/`, hors Git. Le nombre maximal de pages par demande
est 8 par défaut (1 à 20 autorisées), **sans changer les lots du registre**.
Ce plafond est une taille de contexte, jamais une limite au nombre d'arguments.

Lire d'abord le fichier `read_first`, puis le contexte indiqué. Ne pas charger
systématiquement `QUEUE.json` : l'inventaire exhaustif reste local pour l'audit.
Le corpus et ses textes sont privés ; ni les contextes ni les files dérivées
ne doivent être committés dans le dépôt générique.

## Une seule source de progression

Le registre maître, le manifeste de pages et les lots canoniques font autorité.
Aucun fichier `done.json`, booléen de complétion ou compteur concurrent n'est
introduit. La file sous `.state/` est une projection reproductible, pas un nouvel
état de production. Elle lie les entrées présentes et **absentes** à leurs
empreintes : un brouillon apparaissant pendant la préparation bloque le résultat.
Un nouveau processus peut reprendre avec la même commande et les mêmes fichiers.

La commande distingue :

- `to_generate` : fichier absent, absence cohérente dans les deux manifestes ;
- `draft_in_progress` : brouillon partiel déjà enregistré avec ses empreintes ;
- `needs_correction` : état d'échec explicite, sans effacer le texte existant ;
- `awaiting_review` : page générée qui ne doit pas être automatiquement régénérée ;
- `recorded_validated` : concordance des états, empreintes et présence du rapport
  de validation déclaré. Ce terme ne signifie pas qu'une nouvelle revue a eu lieu.

La présence et l'empreinte d'un rapport ne prouvent pas à elles seules sa validité
éditoriale. L'outil ne réévalue pas ces attestations et ne les transforme jamais
en preuve de release ou autorisation de publication. Il conserve explicitement
`editorial_validation_performed=false` et `publication_authorized=false`.

## Ordre et garde-fous

La page Débat précède ses arguments. Une page Débat déjà générée mais non
validée ouvre `review_debate`, pas une nouvelle rédaction. Ensuite, le premier lot
non clos dans **l'ordre du registre** est choisi. Ses brouillons partiels et ses
corrections passent avant les pages encore absentes ; les pages déjà générées
sont conservées. Les textes détaillés hors de la sélection et de ses dépendances
ne sont pas recopiés dans le contexte destiné à l'IA. Le graphe global, ses
réutilisations et les sources utiles restent disponibles.

Un lot dont tous les brouillons sont produits ouvre la revue des pages, puis
`batch_review_required` si la clôture du lot manque. Le lot suivant n'est pas
ouvert sur la seule présence des fichiers. Les lots `validated` ou `released`
locaux sont reconnus uniquement avec toutes leurs pages dans l'état cohérent
`recorded_validated`, l'agrégat attendu et le rapport de lot. Une dépendance
externe au lot non validée est signalée, jamais contournée ni réordonnée
silencieusement. Une page réutilisée n'est planifiée qu'une fois par identifiant.

Quand tous les lots sont clos, la sortie est `global_review_required`, jamais
`release_ready` ou `published`. La revue globale, les recherches d'omissions,
la documentation et les validations ordinaires restent obligatoires.

Les divergences de titre, chemin, propriété de lot, empreinte ou état bloquent.
Une page perdue n'est pas assimilée à du travail terminé. Un fichier non enregistré
n'est jamais adopté, supprimé ou écrasé automatiquement : le conserver et
réconcilier les données par le workflow ordinaire avant de relancer. Le graphe
verrouillé est revérifié avec l'algorithme d'empreinte structurelle du validateur.
Les corpus importés, les pages historiques ou déjà publiées, les chemins privés,
les traversées et les liens symboliques sont refusés.

## Reprise et limites

Après enregistrement cohérent d'une page ou d'une validation par le workflow
ordinaire, relancer `creation-next`. Ne pas modifier la file pour faire avancer
l'outil. Une file inchangée et intacte est réutilisée ; une entrée modifiée
produit une nouvelle file et une sortie altérée bloque sans écrasement.
Toujours relancer la commande au début d'une session, plutôt que de considérer
un ancien `QUEUE.json` comme l'état courant.

Ces commandes automatisent **la sélection et la préparation**. L'enregistrement
local des brouillons est maintenant disponible par `creation-package` puis
`creation-import` ; voir [le guide d'import](GUIDE_CREATION_IMPORT.md).
L'initialisation depuis un sujet, la validation incrémentale des contenus et la
mémoire documentaire inter-débats restent distinctes. Cette reprise n'utilise pas `review-import` et
ne touche pas au parcours de traduction ni aux commandes de publication.
Les lots, Works et validations existants ne sont ni inventés ni automatiquement
marqués terminés. Aucun modèle ni wiki n'est appelé.

## Mesure et tests

Le test synthétique de 200 arguments conserve les 198 brouillons déjà produits
hors des textes détaillés du prochain contexte, et cible les 2 arguments restants,
tout en maintenant la vue globale du graphe. Il ne mesure pas de tokens facturés
ni de crédits : ces deux compteurs restent `null`. Les empreintes peuvent relire
les fichiers localement sans en présenter le texte au modèle.

```sh
python -m pytest -q kit/tests/test_wikidebia_creation_resume.py \
  kit/tests/test_wikidebia_creation_context.py
```

Les régressions couvrent notamment une reprise dans un processus neuf, un fichier
manquant malgré un statut généré, un brouillon non enregistré, une modification
concurrente, un lot faussement clos, les dépendances, les miroirs divergents,
les chemins dangereux et l'absence de mutation du corpus ou d'accès réseau.
