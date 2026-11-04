# État compact et reprise d’un workspace

Pour obtenir l’état autoritatif du workspace sans charger son historique complet :

```text
./wikidebia corpus-workspace-status <debate_id> --work-id <work_id>
```

La sortie JSON tient dans un petit objet stable. Elle vérifie l’empreinte de
`workspace.json` et, pendant les phases distantes, la comparaison signée, son
plan et son inventaire. Elle contient `next_action` et `next_command`, cette
dernière étant directement exécutable lorsque l’étape ne demande pas d’abord
une décision éditoriale humaine.

Les champs `next_remote_read_possible` et `next_remote_write_possible`
annoncent les effets possibles de la prochaine commande. Le contrôle d’état
lui-même reste local et porte toujours :

```json
{
  "status_check_remote_access": false,
  "status_check_remote_write": false
}
```

Ce résumé se fonde sur le workspace signé. Il reste donc exact même si un ancien
fichier d’orchestration générale n’a pas été actualisé après l’usage des
commandes avancées.
