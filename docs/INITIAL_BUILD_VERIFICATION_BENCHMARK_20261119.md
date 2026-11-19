# Première construction du corpus : élimination de la double vérification — 19 novembre 2026

## Constat dans les sources

Avant la [PR #163](https://github.com/wikidebates/wikidebia-project/pull/163), `_initialize_graph_stage` dans `kit/scripts/wikidebia_review_workflow.py` appelait systématiquement `compute_build_contract` dès la disponibilité du snapshot. Lors de la **première construction**, `build_corpus` réexécutait immédiatement `verify_extraction` et calculait le même contrat, après avoir décompressé l'archive une deuxième fois si l'entrée était un ZIP. L'empreinte du premier contrat n'était utilisée qu'en cas de build préexistant pour contrôler une éventuelle reprise.

Le correctif appelle `compute_build_contract` **uniquement** lorsqu'un dossier de build existe déjà. Sur un nouveau build, `build_corpus` reste l'unique autorité pour la vérification intégrale de l'extraction, la construction et l'écriture du contrat signé. Les vérifications SHA-256, les manifestes de pages, le reçu du build et le refus d'écraser automatiquement un ancien build restent en place.

## Protocole de mesure

- Exécution : [GitHub Actions #44630659561](https://github.com/wikidebates/wikidebia-project/actions/runs/44630659561), Ubuntu 24.04 et Python 3.12, succès.
- Trois sources synthétiques identiques à l'intérieur de chaque comparaison : 120 arguments en dossier, 300 en dossier, 120 en ZIP. Chaque page synthétique comprend 1 024 octets de remplissage.
- Six répétitions **alternées** pour chaque variante. Les sources sont préparées avant la mesure, et chaque essai construit dans un nouveau dossier temporaire.
- `avant` : construction du workflow avec l'ancien calcul préalable du contrat, simulé par un appel réel à `compute_build_contract`, puis `build_corpus`. `après` : nouveau workflow, `build_corpus` seul.
- Les deux variantes exécutent les vérifications complètes de l'extraction pendant `build_corpus`. Le contrat SHA-256 attendu doit être identique entre variantes. Le reçu signé est écrit et contrôlé par `inspect_existing_build` à chaque essai.
- Préflight anglais et validation initiale du corpus **simulés** afin de mesurer seulement le coût des opérations mécaniques de création. **Aucune** mesure de traduction, revue sémantique, publication, ou économie de tokens n'est effectuée.

| Scénario | Médiane avant | Médiane après | Réduction du temps |
| --- | ---: | ---: | ---: |
| 120 arguments — dossier | 0,449346 s | 0,407656 s | 9,28 % |
| 300 arguments — dossier | 1,101071 s | 1,006459 s | 8,59 % |
| 120 arguments — ZIP | 0,475671 s | 0,423294 s | 11,01 % |

Échantillons bruts, en secondes :

- Dossier 120 avant : `[0.458261, 0.447273, 0.444654, 0.452664, 0.451419, 0.444290]`.
- Dossier 120 après : `[0.416794, 0.407876, 0.407435, 0.406869, 0.408877, 0.406333]`.
- Dossier 300 avant : `[1.101504, 1.098974, 1.105123, 1.100637, 1.101598, 1.097085]`.
- Dossier 300 après : `[1.007739, 1.022661, 1.006083, 1.005333, 1.006834, 1.001980]`.
- ZIP 120 avant : `[0.473464, 0.472449, 0.477877, 0.480848, 0.485279, 0.473215]`.
- ZIP 120 après : `[0.423070, 0.425939, 0.420530, 0.429422, 0.421892, 0.423517]`.

## Sécurité, régressions et limites

Les tests ajoutés au kit vérifient :
- première construction depuis un dossier ou un ZIP : un seul appel réel à `verify_extraction`, puis reçu de build vérifiable ;
- extraction altérée : refus du build sans création du dossier ;
- build existant et incomplet : calcul du contrat source toujours requis et aucune suppression du dossier ;
- build existant avec reçu valide : réutilisation du build sans reconstruction ni revalidation redondante.

Les trois mesures sont sur des données synthétiques et un runner partagé. Le gain de 8,6 à 11,0 % concerne seulement le chemin mécanique initial avec préflight et validateur initial simulés. Un corpus réel, des temps d'API et le reste du workflow peuvent avoir des performances différentes. Le chemin de reprise d'un **build existant** n'est pas accéléré par ce correctif ; les contrôles de contrat et de reçu y sont volontairement conservés.

Le workflow GitHub Actions temporaire utilisé pour la mesure a été supprimé avant fusion. Aucun contenu éditorial, traduction française/anglaise, attestation de revue humaine ni publication MediaWiki n'est modifié.
