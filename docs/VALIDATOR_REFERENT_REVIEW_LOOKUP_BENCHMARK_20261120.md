# Index local des attestations de référents de titres — 20 novembre 2026

## Coût répété identifié

La fonction `validator/src/wikidebia_validator/graph.py::_canonical_referent_manually_verified`
cherche, pour chaque titre d'argument français ou anglais, son éventuelle
attestation de référent explicite dans les `entries` d'un document
de revue individuelle déclaré par
`manifest.editorial_controls.individual_review_path`.

Sur les grands graphes importés, le document de revue peut décrire de
nombreux arguments. L'ancienne implémentation exécutait alors
`next(entry for entry in entries if entry.id == node_id)` à chaque titre.
Bien que `PackageContext` mette déjà le JSON en cache, la **liste complète**
restait reparcourue, avec un coût potentiellement quadratique.

La [PR #175](https://github.com/wikidebates/wikidebia-project/pull/175)
indexe les premières entrées par identifiant **une fois par appel à
`validate_graph`**, uniquement lorsque le tableau de revue compte
au moins **32 entrées**. Les petits tableaux et les structures non standard
conservent le parcours initial. La liste est indexée dans l'ordre original
avec `setdefault`, de sorte que la **première** entrée reste
prioritaire si l'identifiant est dupliqué.

### Garantie : aucun contrôle de chemin sauté

À chaque appel, les opérations d'origine restent exécutées :
`ctx.manifest()`, contrôle de type de
`individual_review_path`, `ctx.exists(rel)` et `ctx.load_json(rel)`.
Elles continuent donc à générer **exactement** les erreurs d'accès hors
paquet, d'absence, de chargement JSON et d'encodage qui existaient
avant l'optimisation. Aucun document de revue non autorisé n'est accepté.

L'index temporaire est invalidé si le document ou sa liste d'entrées
est remplacé ou si la longueur de celle-ci change. Les lignes
restent des références aux dictionnaires originaux, afin que les
mises à jour des champs de vérification soient observées. Rien n'est
conservé sur disque ou entre validations.

## Mesure avant/après, avec parité complète des rapports

- GitHub Actions [run #44644996230](https://github.com/wikidebates/wikidebia-project/actions/runs/44644996230), succès, Ubuntu 24.04 / Python 3.12.
- Ancienne version : commit `ba9a0d50fa5f9b87197c137ad17b5d58b49baadf`, chargée dans un module distinct.
- Chaque scénario prépare un paquet synthétique valide pour la portée `graph`, avec chaîne argumentaire, titre en français et tableau de revue de 200 à 950 lignes.
- Deux familles : titres ordinaires, ou titres contenant un référent contextuel nécessitant une décision documentaire (avec doublons de revue dans la famille contextuelle).
- Six essais **alternés** par scénario, sur les mêmes fichiers sources. Le validateur complet `validate_package(scopes=['graph'])` est exécuté à chaque essai.
- Les rapports `Report.to_dict()` complets — codes, niveaux, messages, chemins, ordre, détails et métriques — sont comparés **strictement** et identiques pour chaque paire. Aucun appel aux wikis ni à un modèle de traduction.

| Scénario | Arguments / entrées de revue | Ancien (s) | Indexé (s) | Gain |
| --- | ---: | ---: | ---: | ---: |
| Titres ordinaires | 152 / 200 | 0,0168675 | 0,0161190 | 4,44 % |
| Titres ordinaires | 402 / 650 | 0,0465645 | 0,0422330 | 9,30 % |
| Titres ordinaires | 702 / 950 | 0,0895245 | 0,0756775 | **15,47 %** |
| Titres contextuels avec doublons | 402 / 650 | 0,0465570 | 0,0415350 | 10,79 % |
| Titres contextuels avec doublons | 702 / 950 | 0,0891780 | 0,0757020 | **15,11 %** |

### Échantillons bruts (secondes)

Chaque ligne indique d'abord l'ancien code, puis la variante indexée.

- 152 / 200 : `[0.017569,0.016909,0.016826,0.016767,0.016703,0.017068]` ; `[0.016188,0.016374,0.015977,0.016050,0.015917,0.023334]`.
- 402 / 650 : `[0.047457,0.046661,0.046391,0.046732,0.046468,0.046463]` ; `[0.041618,0.042313,0.042370,0.041690,0.042153,0.042706]`.
- 702 / 950 : `[0.089414,0.089850,0.090108,0.089165,0.089629,0.089420]` ; `[0.075663,0.076064,0.086587,0.075692,0.075338,0.075616]`.
- Contextuels 402 / 650 : `[0.054950,0.046457,0.046128,0.046657,0.046902,0.046261]` ; `[0.041523,0.041547,0.041981,0.041448,0.041330,0.042111]`.
- Contextuels 702 / 950 : `[0.088500,0.089043,0.089568,0.089091,0.089364,0.089265]` ; `[0.075665,0.075558,0.075568,0.086651,0.075739,0.076331]`.

## Tests de non-régression

**11 cas pytest** couvrent :

- les identifiants dupliqués : la première entrée reste autoritaire ;
- la modification du champ d'une entrée déjà chargée ;
- le remplacement du document JSON et l'allongement de la liste ;
- le repli sur l'ancien parcours pour une petite revue ;
- le document absent ;
- trois chemins non portables/hors paquet, toujours refusés avec les
  diagnostics `WDV-FS-002` historiques ;
- un document JSON mal formé, toujours signalé ;
- des titres contextuels avec une attestation favorable et une autre
  absente, entraînant une décision `WDV-EDT-016` au bon identifiant.

## Limites

Ces chiffres concernent la **seule portée `graph`** du validateur,
avec des données synthétiques. La validation JSON Schema complète, les
autres portées, les vérifications de reçus, l'extraction MediaWiki,
la traduction et la publication n'ont pas été chronométrées ici.
L'amélioration dépend notamment de la présence d'un long tableau de
revue individuelle. Un petit débat sans cette revue ne bénéficie pas
de l'index.

La modification ne réduit aucun contrôle de chemin, ne change aucune
décision éditoriale, n'affecte aucune source ni aucun texte traduit.
Aucune économie de tokens ou de crédits Codex n'est mesurée.
Le workflow temporaire de benchmark est supprimé avant fusion.
