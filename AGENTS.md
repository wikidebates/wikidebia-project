# Wikidéb’IA — instructions essentielles pour les agents

Ces règles s’appliquent à toutes les sessions. Les procédures spécifiques restent disponibles dans [le guide détaillé](docs/AGENT_PROCEDURES.md) : **lire uniquement la section correspondant à la tâche**, en plus du guide fonctionnel concerné. Ne pas charger par défaut les longues sources unifiées, historiques, corpus ou journaux.

## Secrets et accès

- Dans Codex Cloud, utiliser les variables gérées `WIKIDEBIA_API_TOKEN`, `WIKIDEBIA_FR_BOT_USERNAME`, `WIKIDEBIA_FR_BOT_PASSWORD`, `WIKIDEBIA_EN_BOT_USERNAME` et `WIKIDEBIA_EN_BOT_PASSWORD`. Vérifier leur présence, jamais afficher leurs valeurs.
- Le jeton `WIKIDEBIA_API_TOKEN` ne doit être envoyé **qu’aux API** `fr.wikidebates.org` et `en.wikidebates.org`, dans l’en-tête `x-wikidebia-access`, via les adaptateurs du projet.
- Ne pas chercher les secrets sur le serveur Debian : `private/pywikibot/` y est local, ignoré par Git et ne doit pas être copié dans l’environnement géré.
- Aucun secret, jeton, identifiant sensible, fichier privé, journal brut ou contenu de corpus privé dans Git, les issues/PR, les commandes affichées et les rapports.

## Branches de travail sur GitHub

Quand une tâche demande de modifier ce dépôt, les agents sont autorisés à créer une branche de travail dédiée et à y pousser les commits vérifiés de la tâche sur `https://github.com/wikidebates/wikidebia-project.git`. Cette autorisation couvre les pushes ordinaires sur cette branche pendant toute la tâche, sans confirmation à chaque envoi.

## Frontières éditoriales et de publication

- Aucune publication, modification ou suppression wiki sans demande explicite et **contrôles prévus par le kit** (provenance, identité, droits, plan accepté, empreintes, revue humaine et préflight applicables). Un reçu narratif ou un test local ne remplace jamais une preuve scellée. Ne jamais fabriquer recherches, consultations ou attestations.
- Conserver les citations, sources, attributions et résumés existants, sauf demande spécifique de leur modification. Une source introuvable ou non vérifiée ne justifie pas une suppression.
- Pour les pages françaises existantes, préserver le `titre-affiché` de chaque occurrence même si `page=` change. Omettre les paramètres relationnels facultatifs vides, notamment `|justifications=` et `|objections=`.
- Séparer strictement brouillon, validation, traduction et publication ; ne jamais déclarer une étape terminée à partir d’un simple paquet, contexte ou candidat documentaire.

## Vérifications proportionnées pour économiser les crédits

- **Développement local :** commencer par le diff Git et les seuls fichiers concernés ; utiliser `./wikidebia test-changed --base origin/main` pour proposer les tests, puis `--execute` lorsque les chemins proposés existent. Si un chemin de test est absent, corriger la sélection ou exécuter la suite concernée : ne pas relancer en boucle une commande vouée à échouer.
- `git diff --check` reste systématique. Exécuter les tests locaux ciblés après stabilisation des changements, pas après chaque lecture. Les changements transversaux ou sensibles (authentification, secrets, publication, schémas, vérification des signatures) exigent une couverture élargie. **La CI complète des PR et les contrôles de livraison restent obligatoires.**
- Ne pas lancer `doctor --check-api` ou `--check-auth` pour une modification purement hors ligne : ces diagnostics distants se justifient par une opération ou un problème d’accès. Ils ne remplacent jamais les vérifications au moment d’une écriture wiki.
- Réutiliser une preuve de test **uniquement** lorsque le commit, l’arbre Git, les entrées et les conditions de validité correspondent. Ne pas régénérer les reçus de paquet à chaque modification intermédiaire ; les actualiser et les vérifier après les changements définitifs, selon la procédure de livraison.
- Préférer résumés d’échecs, chemins et empreintes aux logs complets. Ne jamais annoncer des crédits/tokens économisés sans mesure réelle du fournisseur.

## Entrée par type de tâche

- **Reprise d’un Work :** `./wikidebia resume` puis passation concise de l’issue/PR, avec commit vérifié. Voir [SESSION_HANDOFF](docs/SESSION_HANDOFF.md).
- **Création française :** `creation-context --stage …` ; pour la suite, `creation-next --corpus …`, puis les guides `kit/GUIDE_CREATION_*.md`. Les recherches, sources, revues et imports restent séparés et vérifiés.
- **Traduction / édition :** sélectionner uniquement les unités et guides pertinents ; appliquer les validations linguistiques et éditoriales prévues.
- **Publication ou mise à jour distante :** lire les guides `kit/GUIDE_PUBLICATION.md`, `kit/GUIDE_REMOTE_EXECUTION.md` et les consignes détaillées applicables **avant** toute action.
- **Mesure expérimentale :** utiliser les protocoles ponctuels dédiés, sans imposer l’instrumentation aux travaux ordinaires ni inférer des économies de crédits à partir des octets.

Pour toute règle spécialisée non détaillée ici, consulter **avant l’action** la section correspondante de [docs/AGENT_PROCEDURES.md](docs/AGENT_PROCEDURES.md). Le présent fichier conserve les interdits et frontières permanents ; le guide détaille les procédures par métier.
