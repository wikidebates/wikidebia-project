# Export des composants et de la source unifiée

La source unifiée à la racine et son reçu sont des instantanés de livraison.
Ils ne constituent pas la norme de travail courante : consulter en priorité
les composants du commit Git en cours. Ne jamais remplacer les empreintes
d'archives par celles de répertoires ou de fichiers individuels.

Après réussite de la validation complète du commit, produire les ZIP depuis
un checkout propre des composants :

```sh
python tools/build_component_bundle.py --output /tmp/wikidebia-components
```

La destination doit être nouvelle. Les trois archives contiennent seulement
les fichiers versionnés, déclarés par les manifestes, avec leurs reçus. Le
gestionnaire vérifie leurs inventaires, empreintes et versions, ainsi que
l'égalité des deux copies de la référence normative. Les fichiers
`WIKIDEBIA_SOURCE_ACTIVE.md` et `WIKIDEBIA_SOURCE_PACKAGE_RECEIPT.json`
sont générés à partir de ces ZIP réels, sans installer de composant ni écrire
sur les wikis. Le script ne crée aucune preuve de réussite des tests :
la CI complète reste un préalable à toute livraison.

On peut aussi lancer manuellement le workflow GitHub Actions « Export des
composants » et récupérer son artefact. Il s'exécute également sur les PR
qui modifient l'outil d'export ou un manifeste de composant. Un artefact
issu d'une PR en brouillon est un candidat de vérification, pas une release
autorisée. Le succès de l'export ne dispense
pas de la validation complète du même commit. L'artefact contient les trois
ZIP, la source et le reçu. Conserver ensemble ces cinq fichiers.
