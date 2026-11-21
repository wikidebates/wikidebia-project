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
- Pour une **expérience de mesure explicitement demandée seulement**, utiliser le lecteur instrumenté `tools/session_read_capture.py` sur les fichiers publics suivis par Git. Ne pas l'imposer aux usages ordinaires, à la traduction ou à la publication.

## Création française : contexte ciblé

- Pour créer un débat nouveau, commencer l'étape par `./wikidebia creation-context --stage cadrage|graphe|debat-fr|arguments-fr|validation-fr` (choisir une seule valeur). Lire les fichiers indiqués, plutôt que la source unifiée et ses historiques en entier.
- Un corpus nouveau explicitement identifié peut fournir le contexte d'un lot avec `--corpus corpus/<id> --batch-id FR-A-001`, ou d'un argument avec `--node-id A0001`, au stade `arguments-fr`. Ne pas appliquer ce profil à un corpus historique importé.
- Ce contexte ne vaut ni recherche exhaustive, ni validation, ni autorisation de publication. Garder les recherches, les revues globales et les garde-fous existants. Aucun gain de quota ne se déduit des seuls octets. Voir `kit/GUIDE_CREATION_CONTEXT.md`.

## Reprise d'une création en cours

- Pour un corpus français nouveau déjà constitué (graphe/titres verrouillés, anglais différé), commencer par `./wikidebia creation-next --corpus corpus/<id>`. La commande retrouve les pages restantes dans les états canoniques ; `creation-status` inspecte sans écrire.
- Lire `read_first` et le contexte indiqué, pas l'inventaire exhaustif `QUEUE.json` ni les textes déjà produits sans rapport avec la tâche. Ne jamais éditer la file dérivée pour déclarer une page terminée. Un fichier non enregistré ou divergent doit être préservé et réconcilié, pas régénéré.
- `generated` attend encore sa revue. `recorded_validated` est un état relu, pas une nouvelle preuve de validation. Ces commandes ne publient rien ; voir `kit/GUIDE_CREATION_RESUME.md`. Pour enregistrer des brouillons, utiliser `creation-package` puis `creation-import` selon `kit/GUIDE_CREATION_IMPORT.md`, sans modifier manuellement les empreintes. Un journal d'import interrompu se reprend par `creation-import --corpus corpus/<id> --recover`, jamais en supprimant l'état.

## Recherches documentaires de création

- Conserver les recherches effectivement réalisées dans `editable/RESEARCH.json` du paquet `creation-package`, puis importer avec `creation-import`. Lire `context/RESEARCH_HELP.md` pour le format ; un fichier vide reste sans effet.
- Réutiliser les notes ciblées de `CORPUS_CONTEXT.json` sans relire le carnet entier. Vérifier leur date, les variantes et les drapeaux de changement ; une recherche négative ne prouve jamais l'absence de source. Ne jamais fabriquer des recherches, consultations ou preuves historiques.
- `--research-only [--page-id IDENTIFIANT]` conserve tous les textes et statuts `unchanged`. Les notes ne valident ni source ni page et ne modifient pas `sources.json`. Les références retenues doivent encore suivre le workflow documentaire ordinaire. Voir `kit/GUIDE_CREATION_RESEARCH.md`.
