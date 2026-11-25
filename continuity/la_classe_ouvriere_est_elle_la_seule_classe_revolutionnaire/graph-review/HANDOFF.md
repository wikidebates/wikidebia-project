# La classe ouvrière est-elle la seule classe révolutionnaire ?

Le propriétaire a retenu les six renommages et demandé de poursuivre à partir du graphe publié. Les six renommages sont vérifiés sur le wiki. La traduction utilise la réextraction qui suit ces renommages. [État de la traduction et révisions](../traduction-anglaise/README.md).

Le Work `EDIT-20261125-001` est à l’étape `graph_review`, statut `awaiting_review`. La révision française du débat est [267940](https://fr.wikidebates.org/wiki/Special:PermanentLink/267940). Le kit a validé la structure de l’import sur les portées `schema`, `coherence`, `graph`, `files` et `workflow`. Base du kit `4096972a577dddd630f9bc5cf0d45f67fd3145df`.

L’import comprend 227 pages Argument, 241 relations et 256 placements. Une page possède déjà une [traduction anglaise](https://en.wikidebates.org/wiki/The_left_has_contributed_to_xenophobic_rhetoric_and_policies). Les deux frontières vers des débats détaillés restent dans le périmètre du graphe extrait, avec leur débat cible hors périmètre.

## Revue du graphe

La première lecture couvre les 256 placements, avec le titre complet de chaque argument et celui de son parent. [Tableau des placements](PLACEMENTS.tsv).

La seconde lecture recommande, sur les 16 liens examinés, 2 maintiens, 8 déplacements, 4 reclassements et 2 retraits de liens vers des arguments qui figurent déjà ailleurs dans le graphe. [Revue détaillée par titre](REVUE.md).

Le kit a généré en lecture locale un plan pour les déplacements et reclassements. Son action de retrait refuse une page réutilisée. Les deux retraits de lien ont donc été vérifiés dans une projection locale distincte. La projection à 239 relations et 254 placements conserve les 227 pages et passe le validateur structurel. Sur les 21 pages dont les liens changent dans cette prévisualisation, les paramètres hors relations et les libellés des liens conservés ont été comparés à l’import.

## Revue des titres

Les 228 titres canoniques ont été contrôlés pour leur forme et leur unicité. Six corrections sont proposées. Deux répondent à un blocage du validateur, le point final de **La classe ouvrière inclut les travailleurs intellectuels, les étudiants, les retraités, les chômeurs, etc.** et les guillemets de **La production reste structurée autour de sites ou « écosystèmes » industriels à forte concentration ouvrière**. Les six destinations proposées étaient libres lors du contrôle en lecture du wiki français. [Titres actuels et proposés](REVUE.md#corriger-six-titres-canoniques).

La page du débat présente « La classe ouvrière est la seule classe capable de réorganiser la société sur une autre base » sous le libellé « La classe ouvrière est la seule classe porteuse d'une nouvelle organisation économique débarrassée de l'exploitation ». Le lien vers « La classe ouvrière est la seule classe capable d'aller jusqu'au bout de la lutte révolutionnaire » passe par une redirection. Les libellés affichés de ces occurrences sont attestés à la révision 267940.

## Reprise

Le ZIP émis par le kit se trouve dans `outgoing/`. SHA-256 `b204970f3fc531c1fe69f40eb14fd77d1fb3a3966c6acbe8c0603e1ce308a767`. La prévisualisation complète est conservée localement dans `work/graph-review-preview/`. Vérifier l’état du Work avec `./wikidebia resume --debate-id la_classe_ouvriere_est_elle_la_seule_classe_revolutionnaire --work-id EDIT-20261125-001`.

Les propositions de correction du graphe sont conservées comme notes de revue. Le premier checkpoint du Work standard reste en attente. Le brouillon anglais prend pour référence la réextraction, qui conserve les sources et les citations historiques.

[Premières recherches pour la page Debate](DOCUMENTATION.md).
