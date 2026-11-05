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
