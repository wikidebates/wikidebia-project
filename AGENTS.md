# Consignes d’accès Wikidébates dans l’environnement géré

- Dans Codex Cloud, chercher d’abord les accès dans les variables d’environnement. Les noms attendus sont `WIKIDEBIA_API_TOKEN`, `WIKIDEBIA_FR_BOT_USERNAME`, `WIKIDEBIA_FR_BOT_PASSWORD`, `WIKIDEBIA_EN_BOT_USERNAME` et `WIKIDEBIA_EN_BOT_PASSWORD`. Vérifier leur présence ou leur état sans afficher leur valeur.
- `WIKIDEBIA_API_TOKEN` doit être transmis uniquement aux API `fr.wikidebates.org` et `en.wikidebates.org` sous l’en-tête `x-wikidebia-access`. Les adaptateurs du dépôt le font automatiquement.
- Les identifiants Pywikibot gérés sont lus directement depuis ces variables. Ne pas se connecter au serveur Debian pour les chercher et ne pas demander au propriétaire de les recopier lorsque les variables sont configurées.
- Le serveur Debian constitue un contexte distinct : ses services utilisent `private/pywikibot/`, qui reste local, ignoré par Git et ne doit jamais être copié dans l’environnement géré.
- Ne jamais écrire une valeur secrète dans le dépôt, un journal, une commande affichée, un rapport ou un fichier de corpus.

Pour les pages françaises préexistantes, conserver chaque `titre-affiché` contextuel. Un renommage canonique peut changer `page=`, mais ne change jamais automatiquement `titre-affiché`. Les paramètres relationnels facultatifs sans valeur doivent être omis : ne jamais produire `|justifications=` ou `|objections=`.
