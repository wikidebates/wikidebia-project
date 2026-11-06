# Budget de tokens des fragments de traduction

La préparation d’un argument mesure localement le JSON qui serait fourni au
modèle avec l’estimateur versionné `unicode_conservative_v1`. Il combine volume
UTF-8 et segmentation lexicale, puis applique une marge de sécurité de 15 %.
Il ne télécharge aucune table et fonctionne donc sans réseau. Le budget par
défaut est :

- 32 000 tokens de fenêtre totale ;
- 8 000 tokens réservés à la réponse ;
- 256 tokens réservés à l’enveloppe et aux instructions ;
- 23 744 tokens disponibles pour le contenu mesuré.

Ces valeurs peuvent être ajustées explicitement :

```text
./wikidebia corpus-workspace-translation-fragment <debate_id> \
  --work-id <work_id> --prepare-next \
  --max-context-tokens 64000 --response-reserve-tokens 12000
```

La sélection signée consigne l’estimateur et sa version, le décompte brut, la
marge de sécurité, les deux réserves et la capacité restante. Le résultat est
explicitement marqué comme estimation conservatrice ; il ne prétend pas
reproduire à l’unité près le tokenizer privé d’un modèle donné.

Si le contenu dépasse la capacité d’entrée, le contexte transmissible n’est pas
écrit et la commande se termine en blocage. Le fragment local, sa capsule et son
checkpoint restent sauvegardés. Aucun texte n’est tronqué et aucun argument
suivant n’est choisi pour masquer le dépassement.
