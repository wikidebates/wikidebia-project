# Réutilisation d'une extraction ZIP pendant une étape de workflow — 19 novembre 2026

## Constat technique

Lorsqu'une extraction était fournie sous forme de ZIP, `_initialize_graph_stage` dans `kit/scripts/wikidebia_review_workflow.py` faisait :
1. `_graph_translation_preflight(source_zip)` : création et extraction temporaire du ZIP, lecture des métadonnées du graphe puis suppression de l'extraction.
2. Ensuite, soit `compute_build_contract(source_zip)` pour vérifier un build existant, soit `build_corpus(source_zip)` pour un premier build. Cette opération redécompressait l'archive, vérifiait les empreintes source et nettoyait son second répertoire temporaire.

La [PR #168](https://github.com/wikidebates/wikidebia-project/pull/168) conserve l'original du ZIP dans le workflow mais, au cours **d'une seule initialisation du graphe**, résout et extrait l'archive une fois et utilise le répertoire temporaire pour ces opérations successives. La validation intégrale des fichiers du snapshot, les manifestes SHA-256 et les reçus signés sont préservés. Le répertoire temporaire est toujours supprimé lorsque la fonction termine, y compris en cas de blocage. Si le ZIP source change au cours de l'étape (identité, taille, horodatages de modification/changement), la tentative est bloquée et l'état initial du workflow est restauré.

Une correction complémentaire dans `resolve_extraction_input` supprime maintenant un répertoire d'extraction temporaire **même si l'ouverture du ZIP échoue avant de retourner un objet aux appelants**. Les tests vérifient notamment les archives illisibles et les graphes absents.

## Mesure avant/après

- Source : [GitHub Actions #44635015844](https://github.com/wikidebates/wikidebia-project/actions/runs/44635015844), Ubuntu 24.04, Python 3.12, succès.
- Baseline : commit `9ec9e57dfe42c54a731f03f416bde2ff72752fd0`, avant la PR #168.
- Archives synthétiques contenant 120, 300 et 700 arguments et 512 octets de remplissage par argument. Une archive est générée en amont, et les deux variantes utilisent les mêmes octets sources.
- Trois scénarios : première construction du corpus, reprise d'un build **sans** reçu final, reprise d'un build avec reçu **déjà vérifiable**.
- Six répétitions **alternées** par variante/scénario/taille. Le préflight des métadonnées anglaises est réellement exécuté et chaque scénario vérifie le même contrat source ainsi que la validité du reçu final. La validation initiale indépendante est simulée comme réussie dans les scénarios qui la requièrent pour isoler les opérations mécaniques.
- Une reprise ou un build initialisé avec l'ancien code a exécuté exactement **deux extractions ZIP** ; la variante optimisée en a exécuté **une seule**, pour chaque scénario et taille.
- Les secondes indiquées sont des **médianes**.

| Arguments | Scénario | Avant (s) | Après (s) | Réduction |
| --- | --- | ---: | ---: | ---: |
| 120 | Premier build | 0,187321 | 0,182018 | 2,83 % |
| 120 | Reprise sans reçu | 0,065849 | 0,060989 | 7,38 % |
| 120 | Reprise exacte | 0,049757 | 0,044664 | 10,24 % |
| 300 | Premier build | 0,463182 | 0,449912 | 2,86 % |
| 300 | Reprise sans reçu | 0,156374 | 0,144383 | 7,67 % |
| 300 | Reprise exacte | 0,120485 | 0,107695 | 10,62 % |
| 700 | Premier build | 1,074565 | 1,047611 | 2,51 % |
| 700 | Reprise sans reçu | 0,359405 | 0,330702 | 7,99 % |
| 700 | Reprise exacte | 0,280406 | 0,251529 | 10,30 % |

### Séries brutes (secondes)

Chaque paire montre les six temps de l'ancienne version puis les six temps de la version à extraction unique.

- 120 / premier build : `[0.189656,0.186363,0.186216,0.193233,0.187234,0.187407]` ; `[0.182604,0.181742,0.181462,0.182103,0.181933,0.182706]`.
- 120 / sans reçu : `[0.065980,0.065916,0.065716,0.065782,0.066183,0.065641]` ; `[0.062741,0.061072,0.060774,0.061202,0.060704,0.060906]`.
- 120 / exact : `[0.050434,0.049845,0.049562,0.049680,0.049677,0.049835]` ; `[0.044686,0.044631,0.044619,0.044671,0.044656,0.044786]`.
- 300 / premier build : `[0.461179,0.462044,0.463842,0.462522,0.464115,0.466992]` ; `[0.450023,0.448275,0.451254,0.451763,0.449738,0.449801]`.
- 300 / sans reçu : `[0.157052,0.156339,0.156408,0.157201,0.156236,0.155602]` ; `[0.143578,0.144185,0.143803,0.150285,0.144581,0.147850]`.
- 300 / exact : `[0.119943,0.121180,0.120319,0.120651,0.121963,0.119927]` ; `[0.107027,0.107637,0.108133,0.107753,0.108362,0.107186]`.
- 700 / premier build : `[1.075115,1.074015,1.073646,1.082160,1.073282,1.086624]` ; `[1.045015,1.048149,1.049856,1.047853,1.047368,1.041859]`.
- 700 / sans reçu : `[0.358165,0.359600,0.359209,0.366076,0.357493,0.360254]` ; `[0.330725,0.337543,0.328444,0.334968,0.330679,0.330506]`.
- 700 / exact : `[0.284518,0.280620,0.281691,0.280192,0.277479,0.277611]` ; `[0.249387,0.250918,0.257331,0.252139,0.248786,0.252835]`.

## Fiabilité et limites

Huit cas pytest ciblés : extraction unique du ZIP sur création/reprise exacte/reprise inachevée, vérification des reçus source/build, nettoyage en cas d'erreur, refus et retour à l'état précédent si le ZIP est modifié en cours d'étape, absence de décompression artificielle pour une source dossier, et nettoyage des extractions échouées avant leur retour à l'appelant (ZIP illisible et graphe introuvable).

**Portée du gain :** seules les étapes d'initialisation à partir d'un **ZIP** sont concernées. Les sources déjà sous forme de dossier utilisent le chemin historique inchangé. Un validateur séparé, la traduction anglaise, les revues et la publication finale ne sont pas inclus dans les chiffres. Ces mesures ne démontrent aucune économie de tokens de modèle ou de crédits Codex ; des corpus réels et des disques différents peuvent produire d'autres résultats.

La comparaison de performance a été réalisée avant l'ajout des deux tests et du nettoyage supplémentaire en cas de ZIP invalide ; la voie des ZIP valides, seule mesurée, n'a pas changé. Le workflow de benchmark temporaire n'est pas conservé dans `main`.
