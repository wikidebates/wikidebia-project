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
corpus, archives, états et mémoires de traduction sont exclus. Les comptes
rendus ne retiennent que les lignes signalant les échecs, avec une occultation
élémentaire des secrets ; **ne pas considérer cette occultation comme une
garantie de confidentialité** pour des journaux arbitraires. Ne jamais publier
un rapport non relu. Aucun fichier n'est généré automatiquement : le
comportement historique reste inchangé.

Le mode JUnit est celui à privilégier pour la CI et les reprises avec ChatGPT.
Il ne copie ni traceback ni ligne arbitraire du journal. Il conserve uniquement
le nom expurgé du test, la catégorie `failure`/`error`, le type d’exception et
au plus 300 caractères du message XML après occultation. Il accepte plusieurs
fichiers, signale ceux qui manquent ou sont partiels, et limite la liste à 100
échecs.

Le workflow GitHub produit automatiquement l’artefact
`ci-failure-report-<run_id>` pendant sept jours lorsqu’un test échoue. Consulter
ce petit JSON avant les logs complets réduit fortement le contexte à charger ;
les logs ne sont nécessaires que si le résumé structuré ne suffit pas. Aucun
rapport n’est produit lorsque la CI réussit.
