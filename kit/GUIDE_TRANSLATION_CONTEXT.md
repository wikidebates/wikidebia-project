# Contexte compact et télémétrie

La commande suivante prépare par défaut un contexte de reprise sans recopier
les contenus du paquet ni du correctif :

```text
./wikidebia corpus-workspace-translation-context <debate_id> \
  --work-id <work_id> --unit-id U001
```

Le JSON compact contient leurs chemins et empreintes, ainsi que la capsule
signée. Pour un diagnostic local nécessitant les contenus, utilisez
`--output-mode full` : le contenu est écrit dans un fichier, tandis que la
sortie de commande reste un résumé court.

Chaque état inédit alimente un registre signé sous
`.state/context-telemetry/`. La mesure compare la taille de la revue complète à
la somme du paquet, du correctif et de la capsule sélectionnés. Un même triplet
d’empreintes n’est jamais compté deux fois. Aucun contenu ni aucune mesure n’est
envoyé à distance.

`corpus-workspace-translation-next` utilise automatiquement le mode compact et
retourne le nombre d’octets évités.
