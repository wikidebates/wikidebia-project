# Parcours des titres des frontières de profondeur — 20 novembre 2026

## Constat et correction

Dans `kit/scripts/wikidebia_corpus_init.py::_depth_policy`, un débat avec `metadata.limite_profondeur` utilise `frontières_profondeur` pour identifier les nœuds situés à la limite d'extraction. Quand le titre d'une frontière diffère du titre du nœud par une normalisation (espaces, underscores, typographie), la fonction cherchait la première correspondance en **parcourant et normalisant tous les titres du graphe**, à nouveau pour chaque frontière non exacte. Le coût est potentiellement quadratique.

La [PR #169](https://github.com/wikidebates/wikidebia-project/pull/169) remplace ce parcours par un **index progressif** : lors d'un échec de correspondance exacte, la fonction consomme successivement les titres non encore vus, conserve les formes normalisées et s'arrête dès le premier match. Les prochains titres cherchent d'abord dans ce préfixe indexé. Chaque titre source est donc normalisé au plus une fois, même si de nombreuses frontières sont concernées. Si une seule frontière correspond presque immédiatement, le reste de la liste n'est **pas** analysé.

Le correctif préserve la priorité d'une correspondance exacte, le premier candidat sur collision de titres normalisés, les erreurs de titres vides dans le même ordre que l'algorithme historique, ainsi que le tri/dédoublonnage final des identifiants de nœuds. Les débats sans limite de profondeur ne créent aucun index et conservent le retour immédiat.

## Protocole reproductible

- [GitHub Actions #44636665258](https://github.com/wikidebates/wikidebia-project/actions/runs/44636665258), Ubuntu 24.04 et Python 3.12, succès.
- Baseline : code du commit `823c9aa9f49ab516591df6a60b6bebf48fd0bcc1` sur `main`, chargé dans un module séparé du nouveau code.
- Corpus **synthétiques** : 300, 700 ou 1 500 arguments, avec toutes les frontières indiquées en underscore et les titres des nœuds en espaces. Chaque extraction est vérifiée contre son manifeste de paquet recalculé.
- Six essais alternés de la fonction `_depth_policy` pour chaque taille : ancienne et nouvelle implémentation sur **le même** objet graphe, avec exigence d'identité exacte du résultat.
- Quatre essais alternés de `build_corpus` pour les corpus de 300 et 700 arguments : identité exacte des contrats source, des nœuds, des relations, des occurrences, des compteurs, des limites et des octets SHA-256 de toutes les pages françaises importées.
- Ce benchmark mesure la **construction mécanique du corpus**, pas le validateur initial lancé séparément, la revue bilingue, la traduction ni la publication. Aucune opération MediaWiki n'est effectuée.

| Arguments | Fonction ancienne | Fonction indexée | Réduction fonction | Build ancien | Build indexé | Réduction build |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 300 | 0,040698 s | 0,000695 s | 98,29 % | 0,427955 s | 0,3810505 s | 10,96 % |
| 700 | 0,2227105 s | 0,001649 s | 99,26 % | 1,116223 s | 0,8993355 s | 19,43 % |
| 1 500 | 1,0096615 s | 0,0035545 s | 99,65 % | — | — | — |

### Mesures brutes (secondes)

Chaque ligne donne les temps de l'algorithme antérieur, puis les temps de l'algorithme optimisé.

- Frontières 300 : `[0.045752,0.040734,0.041711,0.040543,0.040662,0.040518]` ; `[0.000735,0.000678,0.000706,0.000688,0.000702,0.000677]`.
- Build 300 : `[0.444584,0.424326,0.430972,0.424938]` ; `[0.380641,0.380899,0.383677,0.381202]`.
- Frontières 700 : `[0.222510,0.224806,0.222911,0.223043,0.222060,0.221729]` ; `[0.001682,0.001620,0.001670,0.001628,0.001680,0.001601]`.
- Build 700 : `[1.123249,1.126070,1.106135,1.109197]` ; `[0.900307,0.896619,0.902284,0.898364]`.
- Frontières 1 500 : `[1.005334,1.008977,1.010346,1.022679,1.055421,1.001584]` ; `[0.003563,0.003488,0.003565,0.003559,0.003550,0.003535]`.

## Contrôles de non-régression

Onze tests ciblés vérifient les correspondances exactes, la priorité du premier titre normalisé, le comportement historique quand un titre source invalide précède ou suit une correspondance, l'absence de suppression de contrôle sur titre inconnu ou structure invalide, la déduplication et le tri des identifiants, la sortie immédiate sans limite de profondeur, le nombre linéaire de normalisations pour 600 frontières, la recherche rapide d'un seul alias placé en tête et la réutilisation d'un préfixe déjà parcouru pour des frontières fournies en ordre inverse.

## Portée et limites

Ces mesures mettent **volontairement en évidence le cas défavorable de l'ancien code** : tous les titres des frontières nécessitent une normalisation. L'amélioration opérationnelle est moindre, voire nulle, sur un débat sans borne de profondeur, sans frontières ou dont tous les titres correspondent exactement. Les performances dépendent aussi de la taille du graphe, du disque et du cache du runner.

L'intégrité des extractions, les contrats/reçus signés, les imports historiques, la revue éditoriale française et anglaise et les règles de publication demeurent inchangés. Aucun gain en tokens de modèle ou crédits Codex n'est mesuré. Le workflow de benchmark temporaire n'est pas conservé dans `main`.
