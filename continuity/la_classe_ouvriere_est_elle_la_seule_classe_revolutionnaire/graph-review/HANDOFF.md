# La classe ouvrière est-elle la seule classe révolutionnaire ?

Le Work `EDIT-20261125-001` est à l’étape `graph_review`, statut `awaiting_review`. La révision française du débat est [267940](https://fr.wikidebates.org/wiki/Special:PermanentLink/267940). Le kit a validé la structure de l’import sur les portées `schema`, `coherence`, `graph`, `files` et `workflow`. Base du kit `4096972a577dddd630f9bc5cf0d45f67fd3145df`.

L’import comprend 227 pages Argument, 241 relations et 256 placements. Une page possède déjà une [traduction anglaise](https://en.wikidebates.org/wiki/The_left_has_contributed_to_xenophobic_rhetoric_and_policies). Les deux frontières vers des débats détaillés restent dans le périmètre du graphe extrait, avec leur débat cible hors périmètre.

## Revue du graphe

La [première lecture](PLACEMENTS.tsv) couvre les 256 placements. La [seconde lecture](ARBITRAGES.tsv) recommande, sur les 16 liens examinés, 2 maintiens, 8 déplacements, 4 reclassements et 2 retraits de lien vers des arguments qui figurent déjà ailleurs dans le graphe.

- E00106 passe d’objection à justification. Les citations décrivent la fragmentation de la production comme moyen de réduire le pouvoir des travailleurs.
- E00144 et E00145 passent de justifications à objections. Les textes cités contestent l’inférence selon laquelle la fragmentation empêche une nouvelle unification.
- E00079 passe sous l’argument consacré aux autres acteurs révolutionnaires. Plusieurs enfants documentent un rôle des étudiants en appui aux travailleurs.
- E00113 et E00135 sont proposés au retrait comme liens seulement. Les pages cibles restent accessibles respectivement par E00123 et E00062. Les identifiants sont ceux de l’import et seront recalculés après projection.

Le kit a généré en lecture locale un plan pour les déplacements et reclassements. Son action de retrait refuse une page réutilisée. Les deux retraits de lien ont donc été vérifiés dans une projection locale distincte. La projection à 239 relations et 254 placements conserve les 227 pages et passe le validateur structurel. Sur les 21 pages dont les liens changent dans cette prévisualisation, les paramètres hors relations et les libellés des liens conservés ont été comparés à l’import.

## Revue des titres

Les 228 titres canoniques ont été contrôlés pour leur forme et leur unicité. Six [corrections de titres canoniques](TITRES.tsv) sont proposées. Deux répondent à un blocage du validateur, le point final d’A0048 et la forme des guillemets d’A0114. Les six destinations proposées étaient libres lors du contrôle en lecture du wiki français.

La page principale distingue, pour A0002, le titre canonique sur la capacité à réorganiser la société et le libellé contextualisé sur une organisation économique sans exploitation. Le lien vers A0004 passe par une redirection vers le titre canonique extrait. Les libellés affichés de ces occurrences sont attestés à la révision 267940.

## Reprise

Le ZIP émis par le kit se trouve dans `outgoing/`. SHA-256 `b204970f3fc531c1fe69f40eb14fd77d1fb3a3966c6acbe8c0603e1ce308a767`. La prévisualisation complète est conservée localement dans `work/graph-review-preview/`. Vérifier l’état du Work avec `./wikidebia resume --debate-id la_classe_ouvriere_est_elle_la_seule_classe_revolutionnaire --work-id EDIT-20261125-001`.

Les changements proposés restent soumis à l’autorisation de modifier les pages du wiki français avant le premier checkpoint. Les sources et citations historiques demeurent dans le snapshot. Le verrouillage français est préalable à la traduction selon le kit.

[Premières recherches pour la page Debate](DOCUMENTATION.md).
