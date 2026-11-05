# Préflight mécanique des correctifs

Avant toute décision sémantique, contrôlez un correctif d’unité avec :

```text
./wikidebia corpus-workspace-translation-preflight <debate_id> \
  --work-id <work_id> --unit-id U001
```

Le préflight vérifie sans modèle de langage :

- l’absence de modification de la source française et du contexte du Work ;
- l’absence de champs `justifications` ou `objections` injectés dans une traduction ;
- les règles certaines de ponctuation et de structure des titres ;
- les espaces externes et caractères de contrôle ;
- la présence, l’unicité et la capitalisation mécanique du vocabulaire ;
- la présence des libellés relationnels traduits.

Le scellement d’un correctif exécute automatiquement ce contrôle et refuse tout
résultat bloqué. Le rapport signé est écrit sous
`audits/translation-preflight/`. Il atteste explicitement qu’aucune relecture
sémantique n’a été effectuée et ne remplace donc pas la validation linguistique.
