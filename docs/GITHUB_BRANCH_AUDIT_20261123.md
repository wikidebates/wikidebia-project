# Politique de branches et audit de nettoyage (23 novembre 2026)

## Objectif

Assainir les références Git sans effacer de contenu ni provoquer de régression dans Wikidéb'IA. Une branche n'est **jamais** supprimée simplement parce qu'une PR est fermée ou que son nom date de plusieurs jours.

## Inventaire vérifié

- 151 branches GitHub, dont `main`.
- 131 branches dont le HEAD correspond à une PR **fusionnée**, à étudier comme candidates (et non comme suppressions automatiquement autorisées).
- 12 branches liées à une PR fermée **sans fusion** : **ne pas supprimer sans revue du diff**.
- 6 branches sans PR retrouvée : **conserver jusqu'à identification de leur rôle**.
- `work` a été réutilisée et ne pointe plus vers le HEAD de sa précédente PR : **ne pas supprimer**.
- Aucune PR ouverte lors du contrôle.

Les 19 branches à examen renforcé sont :

**PR fermée sans fusion :**
`audit/schema-cache-benchmark-20261119`, `audit/schema-file-cost-breakdown-20261119`, `feat/scope-publication-closure-20261116`, `fix/close-work-require-all-scope-20261116`, `fix/english-quote-date-british-20261118`, `fix/remote-execution-receipt-identity-20261116`, `fix/workflow-reconcile-unique-work-20261116`, `fix/workflow-status-reconciliation-guidance-20261116`, `fix/workspace-status-partial-scope-20261116`, `optimize/compact-repository-index-failure-reports`, `perf/inspect-reuse-json-digests-20261119`, `perf/schema-registry-traversal-20261119`.

**Sans PR identifiée :**
`codex/traduction-combat-feministe`, `feat/graph-extract-max-depth`, `feature/reuse-existing-english-pages`, `translation/cannabis-en-20261021-verifiee`, `translation/liberte-expression-en-20261027`, `wiki-fr-publication`.

**Réutilisée :** `work`.

Comparaison à `main` : `codex/traduction-combat-feministe` contient 35 commits propres; `translation/cannabis-en-20261021-verifiee` et `wiki-fr-publication` n'ont pas d'ancêtre commun avec `main`. Ces trois branches sont **à conserver impérativement** tant qu'un archivage vérifié n'existe pas. Plusieurs branches liées à des PR fermées sans fusion comportent encore de 1 à 7 commits propres (voir le diff et leur valeur fonctionnelle avant toute décision). Les trois branches `feat/graph-extract-max-depth`, `feature/reuse-existing-english-pages` et `translation/liberte-expression-en-20261027` sont ancêtres de `main`, mais les références externes doivent encore être contrôlées.

## Critères de suppression d'une branche candidate

1. Récupérer la liste complète des branches et leur SHA exact, et toutes les PR ouvertes et closes, en revalidant les résultats immédiatement avant suppression.
2. Vérifier que la branche n'est ni `main`, ni protégée, ni liée à une PR ouverte, ni à une livraison, traduction, checkpoint, script de reprise, release, déploiement ou outil externe.
3. Vérifier l'intégration réelle : pour les merge commits, utiliser le graphe Git; pour les squash/rebase, la PR fusionnée ne suffit pas à prouver la parité fonctionnelle. Comparer les fichiers ou le patch et examiner les éventuels commits supplémentaires.
4. Exclure automatiquement toutes les branches sans PR, avec PR fermée sans fusion, divergentes non comprises, sans ancêtre commun, dont le HEAD a changé depuis l'audit ou dont le nom figure dans les exceptions ci-dessus.
5. Geler un manifeste contenant `repo\tbranche\tSHA\tPR\tstatut\tpreuve` avant le nettoyage. Exécuter d'abord un dry-run; ne passer en mode suppression qu'avec une sélection explicitement validée et une nouvelle lecture du SHA.
6. Préserver les preuves et l'historique des PR. La suppression d'une **référence de branche** ne doit pas être confondue avec la suppression de fichiers du dépôt `main`. Ne pas faire de `git push --force`, `git reset --hard` ou `git clean`.

## Protections GitHub à configurer (administration)

Au 23 novembre 2026, `main` est la branche par défaut mais **aucun ruleset n'a été listé** pour ce dépôt. Dans **Settings > Rules > Rulesets**, créer une règle active ciblant la branche par défaut : interdire suppressions et force-push, exiger PR et résolution des commentaires, et rendre obligatoire le job `tests` du workflow `.github/workflows/validate.yml` (exécuté sur toutes les PR). Tester le ruleset sur une PR représentative et vérifier que la logique de réutilisation des tests après fusion fonctionne encore. Ne pas imposer d'approbation humaine automatique sans décision explicite du mainteneur.

La configuration d'administration n'est pas modifiable via le connecteur GitHub de cet audit. Aucun changement de règles, de CI ni de branche `main` n'est inclus dans ce document.

## Portée

Cet audit est non destructif. Il n'implique aucune action sur le serveur `dialectica`, les comptes de publication, les wikis FR/EN, les données de traduction ou les autres dépôts. Les évaluations ponctuelles doivent être reconduites si les branches bougent.
