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
## Release française préservée

Pour un Work portant un reçu de préservation, `release_ready` signifie **prêt
localement**, et non « publié ». Le statut compact indique alors :

```bash
./wikidebia publish-preserved <debate_id> --work-id <work_id>
```

La même commande reprend une publication interrompue (y compris après des
créations anglaises). Elle refait les contrôles distants nécessaires ; ne pas
substituer `corpus-workspace-finalize` ou une publication française classique.
Un reçu final signé et cohérent distingue une publication terminée ; si le Work
local n'est pas encore réconcilié, la commande proposée est
`corpus-workspace-reconcile-publication`. Le contrôle de statut reste local,
sans accès ni écriture sur les wikis. Une révision française divergente ou un
titre anglais occupé doivent bloquer la publication, pas être corrigés
silencieusement.
