# Wikidéb’IA Kit 2.16.47

La commande `fr-publication-relay` transporte des demandes françaises explicitement
approuvées par Git vers un relais Debian distinct du déploiement du programme.
Elle réutilise les accès Pywikibot du serveur, contrôle les révisions avant écriture
et conserve un journal de reprise. Voir `deploy/README_PUBLICATION_FR.md` dans le
dépôt complet ; le relais n'est pas activé par une simple mise à jour du kit.

Le kit 2.16.47 conserve l’ordre final `Debate` puis `Argument` de 2.16.46 et corrige la reprise des plans distants signés après une mise à niveau : `kit_version` et `required_validator_version` sont traités comme provenance du producteur, tandis que la signature du plan, son schéma, le débat, le manifeste et la configuration exacts restent obligatoirement vérifiés. Norme active : 1.2.88. Validateur associé : 0.4.105.

Les exécutions distantes utilisent un bail local identifié plutôt qu’un simple PID. Un
processus vivant conserve toujours son verrou, y compris avec l’ancien format. Après un
arrêt brutal, un PID local mort est récupéré immédiatement ; un verrou illisible ou créé
sur un autre hôte doit expirer (six heures par défaut, configurable avec
`update_lock_stale_seconds`). Chaque récupération est consignée sans contenu de page
dans `.state/locks/IDENTIFIANT.recoveries.jsonl`, et seul le propriétaire du bail courant
peut le libérer.

Le kit 2.16.44 corrige la préparation de la publication finale anglaise : la configuration construite par `wikidebia_final_publication` transporte désormais explicitement `validator.fingerprint_path` et `max_warnings`, comme toutes les configurations `GenericPublisher` courantes. Sans ce champ, la construction du plan anglais atteignait `_package_fingerprints()` puis levait `KeyError('fingerprint_path')` après les connexions de préflight mais avant toute autorisation ou écriture distante. Le correctif ne modifie aucun corpus, plan français, convergence, contenu éditorial ni règle normative.


Le kit 2.16.43 complète la réconciliation sûre des checkpoints français historiques non liés. Un ancien `workflow.json` déjà arrivé à `final_publication` peut avoir conservé un statut local obsolète (ou aucun statut canonique) en plus de l'absence de `receipt_sha256` et `plan_sha256`. Ce statut local est désormais remplacé par le reçu courant uniquement lorsque le workflow est totalement non lié, sans revue pendante, avant toute publication finale et sans état anglais, et lorsque le reçu auto-signé et l'état français signé attestent exactement le même plan. Un workflow déjà lié à un reçu ou un plan reste bloquant en cas de statut incohérent. Aucune revue, convergence, page ou donnée éditoriale n'est modifiée.

Le kit 2.16.41 corrige la reprise de la publication finale lorsqu’une restauration transactionnelle a laissé dans `workflow.json` une ancienne empreinte du reçu du checkpoint français final. La référence n’est réparée que si le reçu courant et l’état français signé attestent exactement le même `plan_sha256` que le workflow, avant toute autorisation de publication finale et sans état anglais signé. Une divergence réelle de plan reste bloquante. Aucune revue, convergence, page ou donnée éditoriale n’est modifiée.

Le kit 2.16.40 corrige le préflight de rendu du revenu de base sans rouvrir le contenu éditorial. Avant validation finale, il réconcilie uniquement les métadonnées de preuve déjà attestées : les locutions historiques déclarées atomiques reçoivent le marqueur multi-mots correspondant, une exception anglaise copiée mécaniquement vers une forme compacte est retirée, l’introduction française est explicitement marquée comme historique depuis son verrou, et une note anglaise clairement explicative peut recevoir l’exception de ponctuation déjà couverte par la revue humaine globale.

Aucun mot-clé, titre, résumé, introduction, source ou relation n’est modifié. Les normalisations ne s’appliquent pas aux concepts nouveaux non revus. Toutes les capacités de publication finale de 2.16.39 sont conservées.


Le kit 2.16.39 prolonge automatiquement un Work bilingue déjà `release_ready` jusqu’à la publication MediaWiki finale. Il scelle une baseline liée au Work (`FR = dernier checkpoint signé`, `EN = never_published_by_this_work` uniquement sur preuve `deferred`), construit et relit tous les plans avant la première écriture, publie les nouvelles pages anglaises avec leurs métadonnées de première création puis ajoute les liens interlangues français, et installe le `release-copy` après succès. Un Work 2.16.37/2.16.38 déjà `release_ready` reprend directement cette phase sans refaire les deux convergences sémantiques.

Le correctif 2.16.38 reste intégralement conservé : `update --archive` résout le dernier état publié langue par langue et garde le fallback historique explicitement attesté `translation_status.en=deferred`.

## Notes héritées du kit 2.16.37

Le kit 2.16.37 accompagne le validateur 0.4.103, qui corrige la cause racine du blocage répété du vote électronique : la provenance historique des résumés était calculée deux fois, différemment, par `wikicode` et `editorial`, avec un cache partagé. Le rendu n’a pas besoin de réécrire les résumés ni leurs attestations ; le préflight utilise désormais une seule source de vérité interne.

L’attestation `metrics.runtime_attestation` est étendue aux SHA-256 de `wikicode.py` et `historical_summary.py` en plus de `cli.py` et `editorial.py`. `_run_validator` recalcule les quatre empreintes avant d’accepter un rapport. Les diagnostics complets et leur persistance transactionnelle restent inchangés.

Norme active : 1.2.87. Validateur associé : 0.4.104.

## Notes héritées du kit 2.16.35

Le kit 2.16.35 isole l’exécution du validateur orchestré de toute copie Python parasite. `_run_validator` utilise désormais exclusivement `project_root/validator/src`, désactive le user-site, neutralise un `PYTHONHOME` hérité et exécute le sous-processus depuis le composant `validator/`. Une vieille copie de `wikidebia_validator` présente à la racine du projet ou dans un `PYTHONPATH` hérité ne peut donc plus masquer le validateur installé par `upgrade`.

Ce correctif répond au diagnostic réel du vote électronique : les fichiers exacts de `render_preflight` produisent zéro anomalie `WDV-EDT-013/014/015/020` lorsqu’ils sont validés avec le code 0.4.101 de la release, alors que le préflight utilisateur exécutait manifestement une autre copie logique du validateur. Aucun contrôle éditorial n’est assoupli. Norme active : 1.2.87. Validateur associé : 0.4.101.

## État hérité de 2.16.34
Le kit 2.16.34 conserve désormais les paquets de diagnostic complets à travers le rollback transactionnel de `review-import`. Le kit 2.16.33 les créait correctement, mais le nettoyage transactionnel de `outgoing/` pouvait ensuite les supprimer avant que l’utilisateur puisse les récupérer. Seuls les ZIP auto-identifiés par `DIAGNOSTIC_PACKAGE.json` et le schéma `wikidebia-workflow-diagnostic-package-1.0` sont exemptés du nettoyage ; les sorties partielles ordinaires restent supprimées.

Le mécanisme 2.16.33 exporte automatiquement un paquet de diagnostic complet à chaque échec du validateur orchestré. Le terminal continue d'afficher un résumé compact, mais `outgoing/<debate_id>_<rapport>_diagnostic.zip` contient désormais **toutes** les erreurs bloquantes dans `ERRORS.json` / `ERRORS.txt`, le rapport complet et le contexte minimal directement utile. Le ZIP est conçu pour être transmis tel quel à ChatGPT afin d'analyser un blocage en une seule fois.

La génération est en lecture seule, n'inclut aucun secret ni état d'authentification, borne la taille du contexte et reste best-effort : une panne de diagnostic ne masque jamais l'échec original du validateur. Norme active : 1.2.87. Validateur associé : 0.4.101.

## État hérité de 2.16.32
Le kit 2.16.32 corrige le préflight final des reprises historiques bilingues sans rouvrir les décisions éditoriales déjà scellées. Au rendu, `individual_review.json` propage désormais les preuves de changement de forme idiomatique des titres affichés et les attestations attendues par le validateur courant. `summary_style_review.json` est réconcilié depuis les verrous FR/EN autoritatifs pour les résumés `historical_existing`, `historical_absent` ou explicitement autorisés : aucune attestation de création, notamment `forceful_expression`, n’est inventée rétroactivement.

Le renderer localise aussi les dates documentaires au format ISO qui subsistent dans la prose des notes `<ref>` anglaises (`2024-07-09` → `9 July 2024`) tout en préservant exactement les URL contenant un segment de date. Les contenus hors notes et les dates de création restent inchangés. Norme active : 1.2.87. Validateur associé : 0.4.101.

## État hérité de 2.16.31
Le kit 2.16.31 localise les attestations de qualité du vocabulaire bilingue au niveau de chaque langue. Une traduction anglaise ne réutilise plus mécaniquement `multiword_exception`, `kind`, `atomic_concept` et `compositional_intersection` de la forme française : le fichier `keyword_vocabulary_bilingual.json` reçoit des champs `en_*` calculés pour la forme anglaise réellement validée. Ainsi une locution française comme `bourrage d'urnes` peut devenir le composé anglais `ballot stuffing` sans faux `WDV-EDT-025`, tandis qu’une forme anglaise réellement longue conserve une exception multi-mots et une justification propre.

Le contrôle `WDV-EDT-025` reste strict et inchangé. Ce correctif ne modifie aucun mot-clé, aucun ordre de pertinence et aucune règle normative ; il corrige uniquement la projection bilingue des attestations déjà prévues par le validateur. Norme active : 1.2.87. Validateur associé : 0.4.98.

# Wikidéb’IA Kit 2.16.30

Le kit 2.16.30 corrige le rendu des métadonnées protégées lors d’une traduction FR→EN. Une page anglaise cible est normalement techniquement `new`, mais ce statut ne doit jamais déclencher les valeurs de création lorsqu’elle traduit une page française autoritative. Le renderer projette désormais `avancement`, `avertissements-titre`, `avertissements-débat`, `avertissements-argument` et `avertissements-résumé` depuis la présence et la valeur françaises effectives. Une absence française reste donc une absence anglaise ; les valeurs présentes sont traduites par la table normative contrôlée.

Le correctif conserve intégralement la réconciliation 2.16.29 : `en_documentation_correction`, identité documentaire FR→EN, sélection Debate fondée sur la portée, et `historical_text_render_validation_mode=differential_preservation_v1`. Le validateur 0.4.98 conserve cette garde et corrige le préflight de schéma/Quote et `WDV-MWK-023` demeure la garde qui bloque toute métadonnée anglaise ajoutée ou mal traduite. Norme active : 1.2.87.

# Wikidéb’IA Kit 2.16.27

Le kit 2.16.27 ferme la dernière validation documentaire tardive observée dans la traduction anglaise. `sources_en_working.json` est désormais contrôlé avant `semantic_convergence_1` avec le même contrat que le registre final pour les bibliographies de Debate (`document_kind`, portée `foundational_work`/`broad_synthesis`, justification) et pour l’attribution des sources Web/vidéo (`authorship_verified`, absence de copie mécanique auteur=site).

Pour les Work déjà convergés sous une version antérieure, la garde pré-application inventorie toutes les lacunes documentaires en une seule fois et ouvre automatiquement `en_documentation_correction`. Dans ce paquet, seul `data/sources_en_working.json` est modifiable : les titres, résumés, champs Debate et preuves sémantiques restent en lecture seule. La correction ne fabrique aucune classification documentaire ni preuve d’auteur ; elle requiert une décision éditoriale explicite. Après refinalisation, la convergence recommence conformément au lien du reçu précédent avec l’ancienne revue scellée. La norme reste 1.2.87 et le validateur reste 0.4.95.

# Wikidéb’IA Kit 2.16.26

Le kit 2.16.26 fait échouer la finalisation anglaise immédiatement lorsqu’un titre contient une apostrophe typographique non ASCII, au lieu de laisser cette non-conformité apparaître seulement après les deux passes de convergence. Aucune normalisation silencieuse n’est effectuée : la valeur éditoriale doit être corrigée explicitement.

Pour les Work déjà convergés sous une version antérieure, `review-import` détecte avant l’application les titres ainsi scellés, invalide le reçu de convergence, rouvre automatiquement `en_translation_correction` avec la liste exhaustive des champs concernés, puis exige à nouveau deux passes indépendantes sur la nouvelle empreinte. Le validateur 0.4.95 corrige parallèlement le faux positif anglais `It is unfair for X to…`. La norme active reste 1.2.87.

## Wikidéb’IA Kit 2.16.25

Le kit 2.16.25 corrige la projection des vérifications documentaires anglaises vers `data/sources.json`. Les paquets déjà préparés avec le format historique `checked_at` / `method` / `note` sont normalisés à la frontière de sortie vers `verified_at` / `notes`; lorsqu'aucune classification `primary_source` n'avait été enregistrée, la valeur canonique devient explicitement `null` au lieu d'inventer un booléen. Les nouvelles revues doivent renseigner `primary_source` explicitement.

La normalisation intervient après la revue scellée et ne modifie ni le contenu sémantique FR→EN ni le reçu de convergence. Tous les contrôles 2.16.24 restent actifs.

## Wikidéb’IA Kit 2.16.24

Le kit 2.16.24 corrige la régression `present-empty` introduite en 2.16.22. `source_parameter_presence` reste conservé comme provenance d’audit, mais le renderer omet désormais tout paramètre éditorial optionnel dont la valeur logique finale est vide, même si ce paramètre existait historiquement.

Le préflight distant traite la disparition des paramètres éditoriaux optionnels gérés comme une **omission canonique** après validation du corpus. Cette exception ne couvre ni les paramètres de cycle de vie, ni les paramètres inconnus, ni les paramètres hors contrat.

La migration 2.16.23 de `source_parameter_presence` est conservée pour l’audit et la compatibilité des artefacts historiques ; elle ne force plus aucune ligne `|paramètre=` dans le wikicode.

# Wikidéb’IA Kit 2.16.22

Le kit 2.16.22 préserve explicitement la **présence top-level** des paramètres éditoriaux historiques, indépendamment de leur valeur. Sur une page française `preexisting`, un paramètre attesté dans l’import qui devient vide après revue est rendu sous la forme `|paramètre=` ; un paramètre historiquement absent n’est jamais créé seulement parce que sa valeur logique est vide.

Le renderer utilise un état interne `present-empty` distinct de `None` : `None` signifie toujours « omettre », tandis que l’état `present-empty` n’est produit que lorsque `source_parameter_presence` atteste la présence historique. Cette provenance est capturée pour les paramètres éditoriaux des pages Débat et Argument, propagée dans `fr_content_lock.json`, puis utilisée par le checkpoint français `content`. Les suppressions réellement autorisées restent gérées séparément par `allowed_parameter_deletions`.

Une régression reproduit A0021 avec `|objections=`, les buckets historiques `bibliographie-pour` et `vidéographie-contre` devenant vides, les cas négatifs d’absence historique et de suppression autorisée, ainsi qu’un préflight synthétique de vote électronique à 100 mises à jour résolues sans `blocked` ni `manual_review`.

# Wikidéb’IA Kit 2.16.21

Le kit 2.16.21 étend la transaction de `review-import` aux artefacts de checkpoint français sous `.state/fr-publication/<debate>/<work>/<stage>`. Tant qu’aucune exécution distante n’a commencé, un échec de validation, préflight ou planification restaure exactement le stage qui existait avant la tentative, ou supprime le stage provisoire créé par cette tentative. Le checkpoint `graph` déjà publié reste intact lorsqu’un checkpoint `content` échoue localement.

Dès qu’une exécution distante est signalée, le rollback local reste interdit : checkpoint, plan et preuves de reprise sont conservés pour la reprise idempotente. `build_checkpoint()` sait en outre remplacer un artefact 2.16.20 périmé de source différente uniquement lorsqu’il est **prouvablement pré-exécution** : absence de plan, ou plan explicitement bloqué/non exécutable. Un `publication-receipt.json` ou un plan exécutable interdit tout auto-nettoyage.

Une régression d’intégration reproduit le vote électronique : tentative v6 rejetée par la validation documentaire avant écriture → rollback du checkpoint content → revue v7 différente → reconstruction du checkpoint 2 → préparation de la revue anglaise, sans manipulation manuelle de `.state/`.

# Wikidéb’IA Kit 2.16.20

Le kit 2.16.20 corrige le rendu des `Citation`/`Quote` importées lorsque leur inventaire historique contient des sous-paramètres facultatifs présents mais vides. Le registre et les verrous conservent ces lignes de provenance à l’identique, tandis que le wikicode canonique les omet conformément au profil de rendu ; aucune valeur documentaire n’est inventée.

Un nom de paramètre vide reste une erreur et la valeur obligatoire `citation` reste contrôlée en amont. Le même contrat est appliqué au trajet FR→EN : les paramètres vides peuvent rester dans `source_parameters` et dans l’inventaire mappé `parameters`, puis `work`, `issue`, `location`, `page`, `publisher` ou `place` vides sont omis de `{{Quote}}`. Une régression d’intégration reproduit le vote électronique jusqu’au checkpoint français n°2 puis jusqu’à la préparation de la revue anglaise.

# Wikidéb’IA Kit 2.16.19

Le kit 2.16.19 propage la provenance éditoriale française jusqu’à la traduction anglaise au moyen de `source_page_origin`, distinct du `page_origin` de la page cible. Une page EN nouvelle qui traduit un corpus français préexistant conserve donc le profil historique pour les quotas et préférences de génération sans affaiblir les contrôles de qualité intrinsèque, de documentation ni de fidélité.

Les listes historiques de keywords ne sont plus ramenées à 2–4/5–8 et les titres affichés historiques ne sont plus forcés en propositions ; un mauvais mot-clé historique reste corrigeable, y compris par décomposition tracée. Les rubriques historiques sont conservées intégralement lors de `corpus-init` (suppression de la troncature silencieuse à quatre), puis peuvent être corrigées avec justification. L’ordre alphabétique français est désormais accent-insensible. L’introduction historique anglaise demeure une adaptation autonome du contexte franco-français, avec maintien des contrôles documentaires intrinsèques.

# Wikidéb’IA Kit 2.16.18

Le kit 2.16.18 corrige la sélection et la validation d’un texte historique après consentement propriétaire. L’historique reste la provenance, mais il n’est plus utilisé comme valeur effective lorsqu’un `authorized_change` valide existe : l’introduction ou le résumé final autorisé devient la valeur éditoriale sélectionnée utilisée par les contrôles structurels, `fr_content_lock.json`, le changeset, le rendu, le checkpoint français n°2 et la traduction.

Pour l’introduction, le consentement v3 peut sceller un delta structuré de sous-parties (`added`, `modified`, `removed`, `reordered`). Une autorisation limitée à l’ajout de `Enjeux du débat` ne couvre donc aucune modification parasite d’une sous-partie historique. Les règles éditoriales de création sont appliquées différentiellement aux seules sous-parties ajoutées ou substantiellement réécrites ; les sous-parties historiques inchangées ne sont pas requalifiées comme nouvelles. Les reçus 2.16.17 à portée de champ entier restent lisibles et liés à leur valeur finale exacte.

# Wikidéb’IA Kit 2.16.17

Le kit 2.16.17 remplace la protection absolue des textes historiques introduite en 2.16.16 par un contrat de **consentement explicite et scoped**. Sur une page `preexisting`, l’introduction et les résumés restent identiques par défaut et une absence historique de résumé reste une absence. ChatGPT peut toutefois enregistrer des suggestions. Si le propriétaire approuve précisément un ou plusieurs deltas pendant `fr_content_review`, le même paquet peut demander leur ouverture et `review-import --authorize-historical-changes` crée localement, hors du ZIP éditable, une preuve liée au paquet exact, aux champs et aux SHA avant/après.

Le finaliseur accepte alors uniquement les valeurs couvertes par ce reçu, `fr_content_lock.json` distingue `preserved` et `authorized_change`, le checkpoint français n°2 publie les deltas autorisés avec les résumés MediaWiki individualisés normaux et aucune troisième publication française n’est créée. Les anciennes revues au schéma supporté sont normalisées par leurs données : les anciens deltas automatiques deviennent des suggestions, tandis qu’un delta explicitement demandé peut être autorisé sans refaire rubriques, mots-clés ni documentation. La traduction anglaise utilise ensuite la version française finale autorisée.

# Wikidéb’IA Kit 2.16.16

Le kit 2.16.16 corrige une régression critique de `fr_content_review` observée sur un corpus historique : une reprise ordinaire ne peut plus proposer, accepter ni publier une nouvelle introduction ou de nouveaux résumés pour des pages françaises `preexisting`. L’introduction et chaque résumé historiques sont repris exactement ; l’absence historique de résumé reste une absence.

Le paquet de revue marque ces champs comme protégés, la finalisation refuse leur modification, `fr_content_lock.json` scelle leurs empreintes et le checkpoint de contenu ordinaire doit présenter un delta nul sur ces champs. Une réécriture volontaire reste possible uniquement dans une opération corrective distincte explicitement autorisée par le propriétaire.

Les deux checkpoints français, la classification/documentation, les résumés MediaWiki individualisés et toutes les protections de 2.16.14 sont conservés.

# Wikidéb’IA Kit 2.16.14

Le kit 2.16.14 scinde la publication française automatique en **deux checkpoints avant toute traduction**. La première revue externe combine le graphe et les titres canoniques/affichés dans un même ZIP ; son réimport déclenche le premier checkpoint : il publie uniquement les positions/relations, renommages, titres affichés et décisions structurelles validées (fusion/redirection, suppression), en conservant strictement le contenu, les rubriques et les mots-clés importés. Le second suit la revue de contenu : il publie rubriques, mots-clés, introduction, résumés et documentation contre l’état distant attesté par le premier checkpoint ; il refuse tout `move`, `redirect` ou `delete`.

Les décisions structurelles prises pendant une boucle de correction du graphe sont désormais appliquées localement et restent en attente jusqu’au premier checkpoint, au lieu d’être écrites au milieu de la revue. Les deux checkpoints conservent le contrat `page_specific_v1`, la garde de révision, la balise `chatgpt` et la relecture post-écriture. `review-import` reste alimenté par `incoming/` et `sources_working.json` conserve la validation précoce de `document_kind`.

# Wikidéb’IA Kit 2.16.13

Le kit 2.16.13 publie automatiquement le **checkpoint français** dès que `fr_content_review` est validée et appliquée, avant de préparer le ZIP de traduction anglaise. Le checkpoint rend les pages françaises sans lien interlangue prématuré, réutilise le moteur de reprise signé et applique à chaque mutation le résumé MediaWiki personnalisé `page_specific_v1`, la garde de révision et la balise `chatgpt`. La reprise est idempotente et un workflow déjà arrivé à la revue anglaise sous 2.16.12 publie d’abord le checkpoint manquant.

Les ZIP de revue corrigés sont désormais placés dans `incoming/`. `./wikidebia review-import` sélectionne automatiquement l’unique paquet de revue valide ; en cas de pluralité, `./wikidebia review-import <debate_id>` suffit. Le nom du ZIP n’est jamais un sélecteur. `sources_working.json` valide aussi `document_kind` immédiatement afin d’éviter un échec tardif de `data/sources.json`.

Le kit 2.16.12 remplace le résumé générique `Corrections` des nouveaux plans de reprise par des résumés MediaWiki individualisés. Chaque création, mise à jour, renommage, redirection ou suppression issue d’un corpus validé porte une politique et un résumé signés ; les mises à jour de contenu décrivent les familles de paramètres réellement modifiées. L’exécuteur recalcule le résumé avant l’écriture et la relecture post-écriture le vérifie comme auparavant.

Le kit 2.16.11 corrige la transition vers la revue de contenu après des actions structurelles : les lignes de provenance explicitement retirées (`retired_redirect` ou `retired_deleted`) restent conservées pour l’audit mais ne sont plus comptées comme arguments actifs. Une ligne supplémentaire non retirée reste bloquante.

Le kit 2.16.10 corrige un faux positif de l’autonomie des titres canoniques français : les constructions impersonnelles « Il faut… » et « Il ne faut… » ne sont plus prises pour des pronoms anaphoriques. Il conserve intégralement la politique différentielle de 2.16.9.

Le kit 2.16.9 applique la politique différentielle de reprise des métadonnées : les pages déjà présentes sur le wiki conservent par défaut leurs `titre-affiché` et mots-clés historiques. La propositionnalité complète et les cibles quantitatives restent des règles de création pour les nouvelles pages/titres générés par IA. Les titres canoniques restent corrigibles ; les mots-clés historiques peuvent être corrigés et complétés, et ne sont retirés qu’en cas de non-pertinence réelle explicitement justifiée.

# Wikidéb’IA Kit 2.16.8
Le kit 2.16.8 rend `review-import` transactionnel pour toutes les transitions locales jusqu’au prochain arrêt éditorial : si l’avancement mécanique échoue, la revue reste réimportable et le workflow, la base et les artefacts créés pendant la tentative sont restaurés. Les écritures distantes de corrections du graphe restent une frontière irréversible explicite et sont conservées avec leurs plans/reçus pour une reprise déterministe. La réparation de provenance repose sur les preuves de contenu et les schémas/capacités, pas sur l’égalité du numéro de kit. `upgrade` donne aussi désormais le détail des jeux de versions divergents entre composants.

Le kit 2.16.7 part du commit GitHub `5eca765` (1.2.77 / 0.4.80 / 2.16.5) et corrige la provenance locale après exécution des décisions structurelles du graphe. Les fichiers `imports/fr/**/*.wiki` modifiés par une action `update` ou `redirect` mettent désormais immédiatement à jour leur `sha256` et leur taille dans `data/import_provenance.json`. Pour les états déjà produits par 2.16.4/2.16.5, la reprise répare automatiquement uniquement les fichiers attestés par `reviews/graph_action_decisions.json`, dont le contenu courant correspond exactement à l’empreinte post-action prévue et dont la révision distante a avancé. Toute dérive non attestée reste bloquante.

Historique 2.16.1 : une anomalie éditoriale de titre importé ne bloque plus avant la revue qui doit précisément la corriger. Les incohérences structurelles restent bloquantes ; lorsqu’elles surviennent, `workflow` affiche leurs codes/messages et produit automatiquement un ZIP de diagnostic minimal sous `outgoing/`. Après correction, relancer la même commande reprend la phase sans reset manuel. Le mécanisme général de paquets de revue introduit en 2.16.0 reste inchangé.

Les paquets de revue utilisent le schéma stable `wikidebia-chatgpt-review-package-1.0`, séparent `editable/` et `context/`, lient leur provenance à l’état local, refusent les fichiers supplémentaires et excluent les secrets. La convergence sémantique est elle aussi orchestrée : une erreur certaine rouvre la traduction, puis les deux passes indépendantes recommencent. Le workflow ne publie à distance qu’aux frontières déclarées : actions structurelles explicitement exécutées, puis checkpoint français automatique après la revue complète du contenu. La préparation anglaise reste interdite tant que ce checkpoint n’a pas de reçu.

## Notes héritées du paquet parent 2.15.54

Version de réconciliation entre la lignée traduction/validation 2.15.38 et la lignée de publication GitHub 2.15.45 (commit `8b46816`), issues du kit 2.15.32 commun.

Le kit conserve les renforcements de traduction : validation différentielle FR→EN, revue sémantique structurée, portée des appellations consacrées, registre documentaire global, complétude des `Quote`, score de risque des unités de revue, inventaire transactionnel de release et validation de l’archive exacte après extraction fraîche.

Il intègre également les mécanismes de publication déjà utilisés sur les wikis : résumés MediaWiki individualisés, balises `chatgpt` + `translated-fr`, rattrapage audité de `translated-fr`, reprise `--interlanguage-only`, relecture bornée des balises, résolution sûre de la révision de création, `nom-consacré` / `established-name`, absence d’`initialization` sur une nouvelle traduction anglaise et `creation-date` fixée au jour réel de publication.

Les numéros 2.15.33 à 2.15.38 ont été réutilisés différemment dans les deux branches parallèles. Leur historique exact est conservé sous `branch_history/`; la version 2.15.46 est le premier point de réconciliation.

La version 2.15.48 corrige la dépendance à l’ordre de collecte de deux modules de tests et aligne le kit sur le validateur 0.4.67 ; le premier point de réconciliation historique reste 2.15.46.

La version 2.15.50 ajoute un garde-fou croisé empêchant le retour de formulations actives obsolètes dans le paquet Normes et s’aligne sur 1.2.66 / 0.4.69.

La version 2.15.51 étend la preuve propositionnelle : changement de forme idiomatique sous revue explicite, corpus versionné de régressions réelles, catalogue de marqueurs aligné avec le validateur et preuves sémantiques de champ pour Debate/Argument. Elle s’aligne sur 1.2.67 / 0.4.70.

La version 2.15.52 durcit la preuve d’indépendance des passes et les régressions keyword/parsing, sans changer les règles éditoriales.

La version 2.15.53 émet les paramètres MediaWiki `sujet-développé` / `expanded-topic` et `débat-dédié` / `dedicated-debate`, tout en lisant les anciens noms dans les corpus historiques.

La version 2.15.54 corrige l’alignement du validateur sur les métadonnées de première publication anglaise : aucune projection cross-wiki d’`initialization`, et aucune égalité imposée entre `creation-date` anglaise et `date-création` française.

## Architecture de compatibilité 2026-08-10

Les numéros de release sont une provenance. La compatibilité opérationnelle est pilotée par `CAPABILITIES.json` et les identifiants/version de schéma ; les égalités exactes sont réservées à l’installation, l’anti-downgrade, la reproductibilité et l’audit.

La traduction des titres affichés respecte la source française validée : les critères de longueur et de forme propositionnelle appartiennent à la génération de débats. Un titre historique court ou nominal est conservé par défaut. Renommer une page modifie la cible des liens, sans recopier le nom canonique dans leurs libellés affichés.
