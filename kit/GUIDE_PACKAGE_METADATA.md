# Métadonnées officielles du paquet kit

Après une validation complète du kit, régénérez son rapport, son manifeste et
son reçu signé avec le nombre exact de tests réussis :

```text
python kit/scripts/refresh_package_metadata.py --test-count <nombre>
```

Pour éviter toute saisie manuelle, utilisez directement la preuve JUnit
produite par pytest :

```text
python -m pytest -q kit/tests --junitxml=/tmp/kit-tests.xml
python kit/scripts/refresh_package_metadata.py --junit-xml /tmp/kit-tests.xml
```

La commande met à jour atomiquement `TEST_REPORT.txt`,
`PACKAGE_MANIFEST_SHA256.json` et `PACKAGE_RECEIPT.json`. Elle exclut les
caches d’exécution et les deux fichiers auto-référentiels du calcul.

La CI ou une revue peut vérifier les métadonnées sans les modifier :

```text
python kit/scripts/refresh_package_metadata.py --junit-xml /tmp/kit-tests.xml --check
```

Le mode `--check` reprend la date du reçu existant lorsque
`--generated-date` est absent. Toute dérive d’un fichier du kit provoque un
échec explicite.
