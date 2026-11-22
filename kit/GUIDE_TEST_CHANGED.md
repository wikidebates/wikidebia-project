# Tests locaux ciblés

Pour construire un plan depuis les changements de la branche courante :

```text
./wikidebia test-changed --base origin/main
```

Ajoutez `--execute` pour lancer le plan. Les scripts spécialisés sélectionnent
leur fichier de tests et les tests du gestionnaire ; les changements du
validateur, du déploiement et de la mémoire choisissent leurs contrôles dédiés.
Les scripts partagés ou les chemins inconnus déclenchent automatiquement toutes
les suites locales.

Les guides et les métadonnées de paquet régénérées n’entraînent pas seuls une
suite pytest. `git diff --check` reste toujours exécuté. Cette sélection concerne
uniquement les itérations locales : la CI de chaque PR conserve les tests kit,
validateur, auto-audit et déploiement complets.

Pour une itération Codex Cloud, les changements limités à `docs/*.md`
restent soumis à `git diff --check` mais n’entraînent pas à eux seuls les
suites pytest locales. Certains modules ont des tests nommés différemment ;
leurs correspondances explicites sont vérifiées avant la sélection. Lorsqu’un
test attendu manque ou que le périmètre n’est pas connu, le repli exécute
toutes les suites locales, sans ignorer les modules sensibles. Aucune de ces
optimisations locales ne modifie la validation complète de chaque PR sur GitHub.

## Sortie de diagnostic adaptée à Codex Cloud

La commande affiche par défaut une synthèse courte : nombre de fichiers
modifiés, suites de tests choisies, repli conservateur éventuel, état
d'exécution et chemin du rapport complet. Elle ne copie pas systématiquement
les listes détaillées et JSON en contexte de l'agent. Le plan complet et les
résultats restent enregistrés sous `.state/changed-test-plan.json`.

Pour une intégration nécessitant le JSON exact, utiliser :

```sh
./wikidebia test-changed --machine-readable
```

Un échec reste visible dans la synthèse, et son code de sortie reste non nul.
Ce changement n'altère ni la sélection, ni la commande exécutée, ni la CI
complète de chaque PR.
