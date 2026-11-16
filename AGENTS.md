# Consignes d’accès Wikidébates dans l’environnement géré

- Dans Codex Cloud, chercher d’abord les accès dans les variables d’environnement. Les noms attendus sont `WIKIDEBIA_API_TOKEN`, `WIKIDEBIA_FR_BOT_USERNAME`, `WIKIDEBIA_FR_BOT_PASSWORD`, `WIKIDEBIA_EN_BOT_USERNAME` et `WIKIDEBIA_EN_BOT_PASSWORD`. Vérifier leur présence ou leur état sans afficher leur valeur.
- `WIKIDEBIA_API_TOKEN` doit être transmis uniquement aux API `fr.wikidebates.org` et `en.wikidebates.org` sous l’en-tête `x-wikidebia-access`. Les adaptateurs du dépôt le font automatiquement.
- Les identifiants Pywikibot gérés sont lus directement depuis ces variables. Ne pas se connecter au serveur Debian pour les chercher et ne pas demander au propriétaire de les recopier lorsque les variables sont configurées.
- Le serveur Debian constitue un contexte distinct : ses services utilisent `private/pywikibot/`, qui reste local, ignoré par Git et ne doit jamais être copié dans l’environnement géré.
- Ne jamais écrire une valeur secrète dans le dépôt, un journal, une commande affichée, un rapport ou un fichier de corpus.

Pour les pages françaises préexistantes, conserver chaque `titre-affiché` contextuel. Un renommage canonique peut changer `page=`, mais ne change jamais automatiquement `titre-affiché`. Les paramètres relationnels facultatifs sans valeur doivent être omis : ne jamais produire `|justifications=` ou `|objections=`.

## Continuité entre sessions IA (issue #81)

- Avant une nouvelle enquête sur un Work, privilégier `./wikidebia resume` et les preuves signées existantes. Pour les travaux de développement, consulter en priorité la dernière passation concise de l'issue ou de la PR, si elle existe, et vérifier son commit de référence.
- Ne pas relire mécaniquement tous les fichiers déjà parcourus : vérifier seulement les conclusions susceptibles d'être périmées et les fichiers nécessaires à la tâche courante. Une note narrative n'est jamais une autorisation de publication, ni un substitut aux contrôles du kit.
- Si une investigation substantielle doit être reprise, transmettre les décisions, fichiers publics lus, hypothèses écartées, preuves, commit et prochaine étape dans un commentaire court sur l'issue ou la PR. Aucun secret, log brut, fichier privé ou contenu de corpus dans la passation.
- Voir [le protocole de passation et l'audit optionnel](docs/SESSION_HANDOFF.md). L'audit de relectures distingue répétitions intra-session et intersessions sans prétendre mesurer les tokens facturés.
