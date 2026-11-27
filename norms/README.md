# Wikidéb’IA — Normes 1.2.89

Révision du 27 novembre 2026 : préférence pour les traductions publiées vérifiées, deux modalités documentaires, contrôle des doublons et provenance des preuves. Validateur 0.4.106 / kit 2.16.48. L'ancienne révision 1.2.88 est conservée à l'identique dans l'historique.

## Historique — Normes 1.2.88

**Versions associées à la révision précédente : validateur 0.4.105 / kit 2.16.47.** La révision 1.2.88 consacre la décision propriétaire selon laquelle la page anglaise `Debate` doit être créée avant les pages `Argument` lors de la publication finale. Une publication partielle déjà commencée n’est jamais réécrite : le nouveau plan place `Debate` avant les seules créations restantes.

# Wikidéb’IA — Normes 1.2.87

**Maintenance précédente 1.2.87 : validateur 0.4.104 / kit 2.16.45.** Cette maintenance ne modifie aucune règle normative : elle corrige uniquement la projection des preuves de revue historiques, la localisation technique des dates documentaires inline et l’application différentielle déjà prescrite par la norme 1.2.87.

La révision 1.2.87 corrige une contradiction interne de 1.2.86 : le catalogue atomique imposait déjà l’omission de tout paramètre optionnel sans contenu pertinent, tandis qu’un paragraphe et l’exemple de page Débat demandaient encore de conserver des buckets documentaires vides. Désormais la règle est unique : une valeur optionnelle vide est omise du wikicode.

`source_parameter_presence` peut rester conservé comme provenance historique, mais n’a aucun effet sur la présence du paramètre dans la sortie.

La mise en œuvre corrige également deux défauts de reprise : aucune troncature silencieuse des rubriques historiques à quatre et tri alphabétique français accent-insensible.

# Wikidéb’IA — Normes 1.2.85

La révision 1.2.85 précise la logique de consentement 1.2.84 : **l’historique est la provenance, la valeur finale autorisée devient la valeur éditoriale effective**. Avec `preserved`, le texte historique est sélectionné ; avec `authorized_change`, tous les contrôles structurels, le verrou, le changeset, le rendu, le checkpoint français n°2 et la traduction utilisent la valeur finale autorisée.

Pour une introduction, le consentement peut sceller une portée structurée par sous-parties (`added`, `modified`, `removed`, `reordered`). Les contrôles éditoriaux de création sont différentiels : une nouvelle sous-partie, par exemple `Enjeux du débat`, reçoit les contrôles pertinents sans transformer les sous-parties historiques inchangées en nouveau contenu. Une autorisation ciblée ne couvre aucune modification parasite.

# Wikidéb’IA — Normes 1.2.84

La révision 1.2.84 corrige la protection absolue introduite en 1.2.83. Pour une page préexistante, l’introduction et les résumés historiques sont **préservés par défaut**, mais ChatGPT peut signaler des anomalies et proposer des corrections. Une modification devient admissible seulement après une décision propriétaire explicite, précise et traçable couvrant le champ et la valeur finale.

Si cette décision intervient pendant `fr_content_review`, le changement est appliqué dans cette même phase et publié au checkpoint français n°2. Aucune troisième publication française n’est créée. L’absence historique d’un résumé reste une absence sauf création nominativement autorisée. Le consentement ne vaut jamais autorisation générale de réécrire les autres textes historiques.

La preuve d’autorisation est produite localement hors du ZIP éditable et liée à l’archive exacte, au champ et aux SHA avant/après ; `fr_content_lock.json` distingue `preserved` et `authorized_change`. La traduction anglaise utilise ensuite la version française finale effectivement autorisée.

# Wikidéb’IA — Normes 1.2.83

La révision 1.2.83 corrige une régression critique de reprise : sur une page française préexistante, `fr_content_review` ne peut plus réécrire l’introduction historique ni les résumés historiques. Une absence historique de résumé reste une absence. Toute réécriture volontaire de ces champs exige une opération corrective distincte explicitement autorisée par le propriétaire.

Le verrou français porte les empreintes des textes historiques et le validateur bloque toute divergence au rendu. Le second checkpoint français conserve donc un delta nul sur introduction/résumés lors d’une reprise ordinaire, tout en restant capable de publier classifications, documentation et autres champs effectivement ouverts.

La révision conserve les deux checkpoints français de 1.2.81 et toutes les protections de reprise déjà actives.
