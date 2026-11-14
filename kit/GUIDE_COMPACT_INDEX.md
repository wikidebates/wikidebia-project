# Index compact et comptes rendus d'échecs — issue #65

Outil local en lecture seule, sans accès wiki :

```sh
python3 kit/scripts/wikidebia_compact_index.py --project-root . --output .state/repository-index.json
python3 kit/scripts/wikidebia_compact_index.py --test-log .state/pytest.log --output .state/test-failures.json
python3 kit/scripts/wikidebia_compact_index.py \
  --junit-xml /tmp/validator-tests.xml \
  --junit-xml /tmp/kit-tests.xml \
  --output .state/ci-failures.json
```

L'index contient uniquement les chemins, tailles et empreintes SHA-256 tronquées
des fichiers source et documentation de moins de 512 Ko. Les espaces privés,
corpus, archives, états et mémoires de traduction sont exclus. Le mode journal
historique ne recopie désormais aucune ligne : il conserve seulement le numéro,
la catégorie, un identifiant de test respectant une grammaire stricte et un type
d'exception strict. Les paramètres de tests et toutes les valeurs de diagnostic
sont supprimés, même lorsqu'ils ne ressemblent pas à un secret connu.

Le mode JUnit est celui à privilégier pour la CI et les reprises avec ChatGPT.
Il ne copie ni traceback, ni message XML, ni ligne arbitraire du journal. Il
conserve uniquement le nom structurel du test, la catégorie `failure`/`error`
et le type d’exception, tous soumis à une grammaire fermée. Il accepte plusieurs
fichiers, signale ceux qui manquent ou sont partiels, et limite la liste à 100
échecs.

Le workflow GitHub produit automatiquement l’artefact
`ci-failure-report-<run_id>` pendant sept jours lorsqu’un test échoue. Consulter
ce petit JSON avant les logs complets réduit fortement le contexte à charger ;
les logs ne sont nécessaires que si le résumé structuré ne suffit pas. Aucun
rapport n’est produit lorsque la CI réussit.
