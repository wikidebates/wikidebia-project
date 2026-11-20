# Arrêt anticipé du parseur MediaWiki après `maxsplit` — mesures du 20 novembre 2026

## Pourquoi optimiser ce chemin ?

Après [la PR #181](https://github.com/wikidebates/wikidebia-project/pull/181), le parseur du kit `kit/scripts/wikidebia_graph_extract.py` évite déjà les vérifications de délimiteurs impossibles dans les caractères ordinaires. Un coût indépendant subsistait : `_split_top_level(segment, "=", maxsplit=1)`, appelée sur chaque paramètre de modèle, poursuivait inutilement le balayage du **reste entier de la valeur**, souvent un long résumé MediaWiki, même après avoir séparé la clé de sa valeur.

La [PR #182](https://github.com/wikidebates/wikidebia-project/pull/182) ajoute un arrêt immédiatement après le **dernier séparateur autorisé** ; pour `maxsplit=0`, elle renvoie immédiatement le résultat équivalent à `text[:]`. Le séparateur vide reste explicitement interdit, comme depuis la PR #181.

## Correction et invariants

- Pour `maxsplit=1`, après le premier `=` **hors des modèles et liens imbriqués**, la fonction conserve la partie restante `text[start:]` **telle quelle**, sans interpréter les accolades et les liens de la suite. C'est exactement le fragment qu'aurait ajouté la boucle historique, laquelle ne peut plus modifier `start` dès que le quota de séparateurs est atteint.
- Pour `maxsplit=2`, le même raisonnement est appliqué après le deuxième séparateur ; pour `maxsplit=0`, le résultat est le texte complet, avec conservation du type historique de la tranche même sur une sous-classe de `str`. Tous les `maxsplit<0` conservent l'analyse complète.
- Aucun changement de l'ordre de priorité entre `{{{`, `{{`, `}}`, `[[`, `]]` ou les séparateurs. Les paramètres relationnels, les `titre-affiché` existants, les pages historiques, l'ordre des erreurs et les contrôles de provenance ne sont pas modifiés.
- Tous les octets historiques sont toujours lus, vérifiés par empreinte avant la construction, puis **revérifiés au moment de la copie** ; l'arrêt anticipé ne concerne que la recherche des séparateurs à l'intérieur d'une valeur déjà lue, **jamais les contrôles SHA-256, la certification des builds ou les validations d'instances**.

## Tests de correction

Les tests `kit/tests/test_graph_extract_parser_fastpath.py` conservent l'ancienne implémentation intégrale en oracle indépendant. La suite différentielle compare l'ancien et le nouveau parseur sur modèles imbriqués, triples accolades, liens, commentaires, Unicode, séparateurs à plusieurs caractères, restes syntaxiquement malformés et chaînes déterministes pseudo-aléatoires.

Sept nouveaux cas couvrent spécialement `maxsplit=0`, `1` et `2`, la non-exploration des valeurs longues après le dernier séparateur autorisé, la présence d'accolades/liens incomplets en fin de valeur et la conservation du type de tranche sur une sous-classe de `str`. **1 384 tests du kit réussis** dans le workflow de mesure ; rapports de tests, reçu et manifeste SHA-256 régénérés sur la version finale.

Lors de la comparaison [Actions #44736131227](https://github.com/wikidebates/wikidebia-project/actions/runs/44736131227), la construction complète de corpus synthétiques a produit, pour cinq passages alternés dans chaque variante, **exactement les mêmes SHA-256 de tous les fichiers** et le même contrat de build dans chaque taille : 54 fichiers (40 arguments), 314 fichiers (300 arguments), 892 fichiers (878 arguments).

## Résultat isolé sur `build_corpus`

Mesures sur le même runner Ubuntu 24.04, Python 3.12, cinq répétitions de chacune des deux variantes. La variante ancienne utilise l'oracle original de `_split_top_level` ; les autres fonctions restent identiques. Les horodatages sont figés uniquement pour la preuve de parité des fichiers.

| Arguments | Fichiers aux empreintes identiques | Avant (s) | Après (s) | Réduction |
| ---: | ---: | ---: | ---: | ---: |
| 40 | 54 | 0.066846 | 0.036524 | **45.36 %** |
| 300 | 314 | 0.486987 | 0.245024 | **49.69 %** |
| 878 | 892 | 1.416911 | 0.715087 | **49.53 %** |

Échantillons bruts en secondes :

- 40 arguments : sans arrêt borné `[0.084955, 0.072204, 0.066113, 0.066846, 0.066632]` ; avec arrêt borné `[0.050413, 0.040204, 0.036045, 0.034823, 0.036524]`.
- 300 arguments : sans arrêt borné `[0.500107, 0.485320, 0.493969, 0.484937, 0.486987]` ; avec arrêt borné `[0.245957, 0.245024, 0.243399, 0.253321, 0.240275]`.
- 878 arguments : sans arrêt borné `[1.426717, 1.414867, 1.424087, 1.401378, 1.416911]` ; avec arrêt borné `[0.716029, 0.715087, 0.699661, 0.717365, 0.708959]`.

## Impact de bout en bout sur la prétraduction

Le second benchmark [Actions #44736131227](https://github.com/wikidebates/wikidebia-project/actions/runs/44736131227) emploie les mêmes bibliothèques `jsonschema==4.26.0`, `referencing==0.37.0`, le validateur déjà optimisé en #178/#179 et le parseur #181 comme référence. Il effectue **trois répétitions alternées** sur les trois scénarios normaux, avec hachage et vérification des rapports signés, contrats égaux, validations initiales réussies et reçus vérifiés.

### Construction initiale, validation, reçu

| Arguments | Ancien parseur (s) | Parseur borné (s) | Réduction |
| ---: | ---: | ---: | ---: |
| 40 | 0.228612 | 0.203357 | 11.05 % |
| 300 | 0.959217 | 0.709591 | 26.02 % |
| 878 | 2.570727 | 1.867030 | 27.37 % |

### Reprise interrompue après construction

| Arguments | Ancien parseur (s) | Parseur borné (s) | Réduction |
| ---: | ---: | ---: | ---: |
| 40 | 0.179986 | 0.181358 | -0.76 % |
| 300 | 0.584823 | 0.578419 | 1.10 % |
| 878 | 1.505867 | 1.509556 | -0.24 % |

### Reprise exacte avec reçu déjà validé

| Arguments | Ancien parseur (s) | Parseur borné (s) | Réduction |
| ---: | ---: | ---: | ---: |
| 40 | 0.016106 | 0.016155 | -0.30 % |
| 300 | 0.105285 | 0.105456 | -0.16 % |
| 878 | 0.314509 | 0.304624 | 3.14 % |

**Interprétation :** l'arrêt borné accélère la **construction** ; les deux reprises ne reconstruisent pas le corpus et ne bénéficient pas systématiquement de cette modification. Le léger écart de leur durée relève de la variabilité, pas d'une nouvelle permission d'éviter la vérification de l'extraction, du reçu ou du validateur.

Échantillons bruts des trois scénarios, en secondes :

- **40 arguments** :
  - Construction initiale, validation et reçu : ancien `[0.228612, 0.227256, 0.261502]` ; nouveau `[0.287632, 0.197540, 0.203357]`.
  - Reprise interrompue, avant reçu : ancien `[0.178590, 0.179986, 0.180481]` ; nouveau `[0.214270, 0.180611, 0.181358]`.
  - Reprise exacte, reçu valide : ancien `[0.016106, 0.016046, 0.016118]` ; nouveau `[0.016507, 0.016155, 0.015713]`.
- **300 arguments** :
  - Construction initiale, validation et reçu : ancien `[0.944977, 0.959217, 0.973374]` ; nouveau `[0.709591, 0.799146, 0.702805]`.
  - Reprise interrompue, avant reçu : ancien `[0.584823, 0.574484, 0.603419]` ; nouveau `[0.562543, 0.578419, 0.611326]`.
  - Reprise exacte, reçu valide : ancien `[0.105285, 0.100458, 0.137921]` ; nouveau `[0.104985, 0.107621, 0.105456]`.
- **878 arguments** :
  - Construction initiale, validation et reçu : ancien `[2.570727, 2.647199, 2.539773]` ; nouveau `[1.929583, 1.867030, 1.862201]`.
  - Reprise interrompue, avant reçu : ancien `[1.541330, 1.505867, 1.462889]` ; nouveau `[1.505000, 1.509556, 1.518926]`.
  - Reprise exacte, reçu valide : ancien `[0.301645, 0.340170, 0.314509]` ; nouveau `[0.298733, 0.309790, 0.304624]`.

## Limites et sécurité

Ces résultats sont issus de pages **synthétiques** dont les longues valeurs sont principalement du texte ordinaire. Les gains ne doivent pas être extrapolés à une extraction réelle inconnue sans la benchmarker **en lecture seule et localement**. Les tests aléatoires et la comparaison octet pour octet réduisent le risque de changement du parseur mais ne remplacent pas une preuve formelle pour toutes les syntaxes MediaWiki.

Le benchmark n'a réalisé **aucun accès réseau aux wikis**, aucune traduction, aucune publication, aucune lecture du serveur Debian et aucun appel à un LLM. Il ne permet pas de conclure à une économie de tokens, de crédits Codex ou à une amélioration de la qualité linguistique. Les contrôles éditoriaux et les deux checkpoints français restent inchangés.

L'issue [#153](https://github.com/wikidebates/wikidebia-project/issues/153) conserve la passation. La prochaine étape utile est de mesurer les passages complets sur une **extraction figée disponible localement sur le serveur**, sans envoyer les textes ni leurs titres à GitHub.
