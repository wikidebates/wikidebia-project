# Index compact et comptes rendus d'échecs — issue #65

Outil local en lecture seule, sans accès wiki :

```sh
python3 kit/scripts/wikidebia_compact_index.py --project-root . --output .state/repository-index.json
python3 kit/scripts/wikidebia_compact_index.py --test-log .state/pytest.log --output .state/test-failures.json
```

L'index contient uniquement les chemins, tailles et empreintes SHA-256 tronquées
des fichiers source et documentation de moins de 512 Ko. Les espaces privés,
corpus, archives, états et mémoires de traduction sont exclus. Les comptes
rendus ne retiennent que les lignes signalant les échecs, avec une occultation
élémentaire des secrets ; **ne pas considérer cette occultation comme une
garantie de confidentialité** pour des journaux arbitraires. Ne jamais publier
un rapport non relu. Aucun fichier n'est généré automatiquement : le
comportement historique reste inchangé.
