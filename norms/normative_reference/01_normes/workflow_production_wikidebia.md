## Workflow 1.2.76 — convergence après revue des changements de forme

Avant la première passe de convergence, tout changement de forme d’un `displayed-title` est classé et justifié. Une proposition source devenue non-proposition bloque la revue ; une transformation idiomatique recevable ne passe qu’après attestation du même acte de langage, de la même thèse et de la même portée. Les risques sémantiques des Arguments et de Debate doivent tous posséder leurs preuves source/cible avant scellement. Les deux passes de convergence portent ensuite sur cet état exact.

# Workflow de production Wikidéb’IA — norme 1.2.76

**Statut :** workflow actif générique  
**Portée :** production bilingue français–anglais, validation et publication MediaWiki


### Validation pré-revue et blocage technique

Une validation précédant une revue ChatGPT ne bloque pas sur les défauts éditoriaux que la revue suivante est destinée à corriger. Avant présence du verrou `data/fr_page_metadata_lock.json` (ou de son équivalent anglais), les défauts de forme/autonomie des titres importés restent des avertissements de travail. Les incohérences structurelles du graphe restent en revanche bloquantes.

Si un blocage technique subsiste, `workflow` affiche ses diagnostics et construit automatiquement `outgoing/<debate_id>_initial_validation_diagnostic.zip`. Ce ZIP est un paquet de diagnostic en lecture seule, sans secret, destiné à être envoyé à ChatGPT ; l’utilisateur n’a pas à ouvrir les rapports internes. Après correction, relancer la même commande `workflow` réessaie la phase bloquée et reprend automatiquement.

## 0. Orchestration utilisateur des points éditoriaux

Le mode normal utilise `./wikidebia workflow "Titre du débat"`. Le kit exécute les étapes mécaniques jusqu’à une revue externe, crée automatiquement `outgoing/<debate_id>_<type>.zip`, puis s’arrête. Le ZIP corrigé est placé dans `incoming/`, puis réimporté par `./wikidebia review-import`. Lorsqu’un seul paquet de revue valide est présent il est choisi automatiquement d’après son `debate_id` interne ; s’il y en a plusieurs, `./wikidebia review-import <debate_id>` sélectionne le débat sans jamais dépendre du nom du ZIP. Les empreintes nécessaires aux primitives internes sont résolues automatiquement. Les commandes détaillées restent disponibles pour audit et debug.

La chaîne de production devient :

```text
commande utilisateur
→ mécanique locale
→ paquet ChatGPT
→ review-import
→ validation/finalisation/application automatiques
→ prochain paquet ChatGPT
→ …
→ convergence sémantique
→ rendu + release_ready
```

L’orchestration française comporte deux checkpoints distants avant traduction : **graphe + titres** après validation de la structure et des titres canoniques/affichés, puis **contenu + classification** après validation des rubriques, mots-clés et documentation. Pour les pages préexistantes, les résumés et l’introduction historiques sont préservés par défaut ; un delta explicitement autorisé par le propriétaire pendant `fr_content_review` devient la valeur éditoriale sélectionnée et peut être publié au second checkpoint. Les décisions structurelles de correction restent locales jusqu’au premier checkpoint. Chaque checkpoint utilise un plan signé et des résumés individualisés.

### Rejet et correction du graphe

Une revue du graphe rejetée ne déclenche jamais `corpus-promote`. `review-import` conserve le build en `graph_draft`, enregistre les motifs de rejet et produit automatiquement un paquet `graph_correction`. Après réimport d’une correction, le kit reconstruit et revalide la structure puis produit un **nouveau paquet `graph_review`**. La correction et l’approbation sont deux décisions distinctes : même une correction structurellement valide doit repasser par une revue complète avant toute promotion. Un rejet répété recommence le même cycle, sans création de Work. Il reste sans écriture distante sauf si l’utilisateur choisit explicitement la voie `--execute-graph-actions` sur un ZIP comportant des décisions exécutables.

Si le ZIP de revue rejetée contient déjà des décisions structurelles explicites, l’utilisateur peut les appliquer et les publier en une commande avec `./wikidebia review-import <debate_id> --execute-graph-actions`. Cette voie prend en charge retrait/suppression, fusion avec redirection, déplacement et changement de relation. Elle valide d’abord la projection locale complète, préflight toutes les pages distantes avant la première écriture, retire le modèle de relation de la page mère, crée `#REDIRECTION [[Destination]]` pour les doublons ou supprime la page lorsque le retrait n’est pas un doublon, puis reconstruit le graphe et prépare une nouvelle revue complète. Chaque écriture reçoit un résumé individualisé ; pour un doublon, le résumé de la page mère mentionne obligatoirement `[[Destination]]`. Cette voie reste explicitement destructive et n’est jamais déclenchée par un simple `review-import` sans drapeau.

## 1. Principes

Le registre maître et les fichiers individuels sont les sources de vérité. Les titres canoniques français sont verrouillés avant la première génération française. Les titres canoniques anglais et les liens `{{Lien interlangue}}` français dépendent de `translation_status.en` : avec `deferred`, aucun titre anglais ni lien interlangue n’est requis ; avec `ready` ou `published`, les titres anglais sont verrouillés et chaque page française contient exactement le lien vers son titre canonique anglais.

Aucune copie `staging/interlanguage/` ni ancien mécanisme de patch de corpus n’est utilisé. Lorsque l’anglais passe de `deferred` à `ready` ou `published`, l’ajout des liens français se fait par la reprise interlangue explicite et sûre prévue par le kit.

Chaque Work reçoit un handoff vérifié, modifie uniquement les champs autorisés et livre des rapports reproductibles. Dans une reprise issue de pages existantes, les résumés et l’introduction historiques sont protégés par défaut : `fr_content_review` peut enregistrer des suggestions, mais aucun delta n’est appliqué sans décision propriétaire explicite et traçable. Une autorisation valide sélectionne la valeur finale autorisée dans cette même phase et reste strictement limitée à son champ et à sa portée ; l’absence historique d’un résumé reste une absence sauf création nominative. Hors les deux checkpoints français déclarés (graphe/titres puis contenu/classification), aucune écriture distante n’est autorisée avant W11. Ces exceptions conservent un plan et un reçu signés et ne dispensent pas de la publication finale.

## 2. États actifs

```text
initialized
→ graph_draft
→ graph_validated
→ graph_locked
→ fr_debate_validated
→ fr_arguments_in_progress
→ fr_content_complete
→ fr_validated
→ en_debate_validated
→ en_arguments_in_progress
→ en_content_complete
→ en_validated
→ bilingual_validated
→ interlanguage_validated
→ release_ready
→ published
→ archived
```

Les états `interlanguage_prepared` et `interlanguage_applied` sont historiques. Le validateur peut les accepter pour les paquets antérieurs à 1.2.0, mais une nouvelle production ne les émet pas.

## 3. Work 00 — Cadrage

Définir la proposition, le périmètre, les acteurs, juridictions, ambiguïtés, exclusions, versions normatives et chemins du paquet. Créer `manifest.json`, `scope.json` et le registre initial sans inventer de contenu documentaire.

## 4. Work 01 — Recherche, graphe et titres bilingues

Effectuer les recherches et passes d’omission, construire puis consolider le DAG, fixer les occurrences et lots, et verrouiller les titres canoniques et affichés français. Les titres anglais ne sont verrouillés à ce stade que si la traduction n’est pas `deferred`; en mode `deferred`, aucune valeur anglaise n’est inventée.

Contrôles obligatoires : DAG, absence de doublons, autonomie référentielle, titres idiomatiques, équilibre, saturation documentée, empreinte structurelle et revue humaine.

## 5. Work 02 — Page Débat française

Créer la page française. Si `translation_status.en=deferred`, omettre `interlangue`; si l’anglais est `ready` ou `published`, inclure exactement `{{Lien interlangue}}` vers le titre canonique anglais verrouillé. Concevoir l’introduction à partir des connaissances nécessaires au lecteur : définition et périmètre, sens de la question, histoire, actualité lorsqu’elle est pertinente, connaissances préalables et enjeux. Lors de la rédaction, repérer les notions spécialisées dont une définition secondaire aiderait le lecteur : utiliser à leur première occurrence `{{Lien Wikipédia|article=…}}` en français ou `{{Wikipedia link|article=…}}` en anglais lorsque le premier paragraphe de Wikipédia suffit ; sinon conserver une explication intégrée. Vérifier la page dans la langue correspondante, réserver le paramètre d’affichage aux différences réelles de libellé et ne jamais considérer ce lien comme une référence. Chaque sous-partie répond à une question identifiable ; une section technique explique pourquoi elle compte pour le débat. L’introduction ne reproduit ni le graphe ni une checklist issue d’un corpus pilote. Produire le registre bilingue de revue des introductions. Les appels `<ref>…</ref>` sont ajoutés lorsque nécessaire ; leur contenu bibliographique ou web est rédigé directement en wikicode, sans aucun modèle MediaWiki et sans balise `<references />`. Les dates documentaires complètes sont écrites en langage naturel. Aucun minimum global ou par sous-partie n’est recherché. Toutes les références de la page Débat sont disponibles en français. La bibliographie privilégie les ouvrages fondamentaux et synthèses larges. Les paramètres documentaires de la page Débat ou Debate sont remplis selon la pertinence réelle des sources, sans quota par paramètre. Une catégorie peut contenir une seule référence ; si aucune source pertinente n’est retenue, le paramètre est entièrement omis. Une même référence ne figure jamais dans plusieurs orientations ; une source développant substantiellement les deux positions est classée uniquement dans la documentation neutre.

## 6. Work 03 — Arguments français

Produire les pages par lots séquentiels. Chaque page omet `interlangue` tant que `translation_status.en=deferred`; dès que l’anglais est `ready` ou `published`, le lien interlangue exact est présent. Chaque page reproduit exactement les relations du registre, emploie des références françaises lorsqu’un équivalent officiel existe et justifie toute source étrangère sans équivalent. Les incises françaises utilisent des parenthèses, non des tirets cadratins appariés.

## 7. Work 04 — Validation française

Exécuter au minimum les portées `schema`, `coherence`, `graph`, `files`, `batches`, `sources`, `wikicode`, `editorial` et `workflow`. Vérifier notamment le registre de revue de l’introduction, la fonction de chaque sous-partie, la progression et l’absence de minimum mécanique ou de checklist de corpus. Corriger les pages sources puis régénérer agrégats et empreintes. Zéro erreur et zéro avertissement non résolu sont exigés.

## 8. Work 05 — Audit des titres bilingues

Au démarrage de la phase anglaise, vérifier puis verrouiller les titres anglais idiomatiques, autonomes et équivalents aux titres français. Toute modification ultérieure est une migration explicite ; les liens interlangues français sont ajoutés ou mis à jour uniquement par le workflow interlangue prévu, après passage à `ready` ou `published`.

## 9. Work 06 — Page Debate anglaise

Créer la page anglaise autonome avec `topic` et `expanded-topic`, sans `type` ni interlangue. Adapter le contexte et utiliser des sources anglaises vérifiées.

## 10. Work 07 — Arguments anglais

Produire les pages anglaises par lots avec la même structure logique, une profondeur documentaire comparable et une rédaction idiomatique. Les pages anglaises ne contiennent jamais d’interlangue.

## 11. Work 08 — Validation anglaise

Exécuter les mêmes portées applicables que pour le français, notamment `wikicode` et `editorial`. Vérifier références, titres, relations, agrégats et empreintes.

## 12. Work 09 — Validation bilingue

Contrôler l’identité des nœuds, relations, occurrences, réutilisations et propriétaires de lots, ainsi que l’équivalence substantielle des résumés, rubriques/sections et mots-clés.

## 13. Work 10 — Audit interlangue et prépublication

Vérifier l’état interlangue selon `translation_status.en` : en `deferred`, aucun lien interlangue français n’est requis ; en `ready` ou `published`, chaque page française contient exactement un `{{Lien interlangue}}` vers sa cible canonique anglaise. Vérifier aussi l’absence de lien en anglais et l’absence de staging interlangue historique actif. Produire `reports/validation_interlanguage.txt`, la revue finale, le manifeste de libération et le handoff W11. W10 n’écrit jamais sur le wiki.

## 14. Work 11 — Simulation, test de la page Débat et publication

1. Exécuter toutes les portées applicables du validateur, y compris `wikicode` et `editorial`.
2. Construire un plan déterministe signé par SHA-256.
3. Vérifier les modèles publics, l’identité, la balise `chatgpt`, les collisions et les empreintes.
4. Créer en premier l’unique page Débat française canonique, obligatoirement absente dans le plan, avec `createonly` ; relire la révision exacte et produire un reçu machine signé.
5. Avant toute autre écriture, recharger le même plan et le reçu, vérifier leurs empreintes et confirmer que la page Débat est toujours à la révision attestée avec le même contenu, le même résumé et la même balise.
6. Créer ensuite les autres pages françaises. Pour l’anglais, créer d’abord la page Debate puis les pages Argument anglaises. Dans chaque langue, la page principale précède donc toujours ses arguments.
7. Ne créer aucune sous-page utilisateur de test. Une page Débat française préexistante bloque le test au lieu d’être écrasée ou réutilisée comme preuve.

8. Le flux ordinaire est exposé par une commande intégrée unique : déposer le ZIP dans `incoming/`. Si un seul ZIP est présent, lancer `./wikidebia publish --scope PORTÉE`; s’il y en a plusieurs, lancer `./wikidebia publish IDENTIFIANT --scope PORTÉE`. Le fichier sélectionné est `incoming/IDENTIFIANT.zip`; son nom sert seulement à sélectionner l’archive et le `debate_id` interne détermine l’identité du corpus. Les portées `fr-debate`, `en-debate`, `fr`, `en` et `all` sont canoniques.
9. Après succès, le ZIP du débat est déplacé dans `archives/debates/`; le corpus extrait reste dans `corpus/`, hors Git.
8. Utiliser `createonly` pour toute création. Une modification explicitement autorisée exige `baserevid`.
9. Relire chaque révision exacte, vérifier contenu, résumé et balise, puis journaliser.
10. S’arrêter sur toute divergence, collision, perte d’identité, changement de plan ou révision concurrente.

Une mise à jour interlangue distincte n’est admise que lorsque la langue cible est préparée (`ready` ou `published`) et que le workflow la prévoit explicitement. Elle reste interdite tant que `translation_status.en=deferred`; aucun lien provisoire n’est créé.

## 15. Reprises correctives

Le cycle est `release_ready → corrective_in_progress → corrective_blocked` si nécessaire, puis retour à `release_ready` après validation complète. Les handoffs historiques sont immuables. Les constantes propres à un débat restent dans son profil local.

## 16. Livrables

Le paquet final contient le registre, le graphe, les pages individuelles, agrégats, sources, lots, rapports, revues humaines, manifestes, handoffs, journaux locaux et reçus SHA-256. Les archives de normes, validateur et kit possèdent des manifestes exhaustifs.

## Addendum 1.2.6 — contrôles éditoriaux avant libération

Avant `release_ready`, la reprise trie toutes les rubriques et sections dans leur langue, vérifie la majuscule initiale de `sujet`/`topic`, reformule les sujets complets comme compléments d’en-tête et réévalue la sélection documentaire de chaque page Débat/Debate. La revue des résumés enregistre pour chaque langue un extrait exact attestant la force expressive ; une attestation générique répétée sur toutes les pages est insuffisante.

## Addendum 1.2.7 — cohérence de livraison

Le workflow de production et de publication reste identique à celui de 1.2.6. Les composants génériques doivent toutefois refuser toute archive dont le catalogue renvoie à un fichier absent ou dont le compteur `declared_file_count` diverge.


## Publication française avant production anglaise — norme 1.2.9

Une opération W11 peut sélectionner uniquement `fr`. En mode `deferred`, elle n’exige ni titre anglais, ni page anglaise, ni lien interlangue. En mode `ready` ou `published`, le kit vérifie chaque cible `{{Lien interlangue}}` contre le titre anglais verrouillé dans `data/registre_debat.json`; toute cible incohérente est bloquante.


## Addendum 1.2.11 — passe de compaction avant validation

Après chaque génération ou correction de pages, rechercher récursivement la séquence `}}` suivie d’un ou plusieurs retours à la ligne puis de `{{`, avec d’éventuels espaces ou tabulations. Remplacer chaque occurrence par `}}{{` avant de régénérer les agrégats et les empreintes. Les portées `wikicode` et le préflight du kit bloquent toute occurrence résiduelle.
## 18. Installation, mises à jour et sauvegarde Git

L’installation est portable et pilotée par le lanceur racine `wikidebia`. Les composants entrants sont déposés dans `updates/`; `./wikidebia update` les vérifie, les teste, archive les versions précédentes dans `archives/updates/`, remplace les composants, vide `updates/` et synchronise le dépôt Git lorsque `origin` est configuré.

Le dépôt suit les sources génériques et la documentation, mais ignore `private/`, `corpus/`, `archives/`, `updates/`, `incoming/`, `logs/`, `plans/`, `.state/` et `.venv/`. Les secrets Pywikibot résident dans `private/pywikibot/`. Aucun rapport ou fichier persistant ne contient le chemin absolu de l’installation.


Les ZIP encore présents dans l’ancien dossier `incoming/debates/` sont migrés automatiquement vers `incoming/` pendant la mise à jour. Toute collision de noms avec un contenu différent bloque l’opération sans écrasement.


## Compatibilité de publication — norme 1.2.15

Avant de construire le plan, le kit exécute le validateur installé sur le corpus. La version réelle du validateur doit correspondre à celle exigée par le kit et le rapport doit être positif. Les versions historiques inscrites dans `manifest.json` ne sont ni comparées pour égalité aux versions installées, ni réécrites. La norme déclarée reste soumise à la liste de compatibilité et aux schémas du validateur courant.


## Reprise distante d’un corpus publié — révision 1.2.16

Une reprise compare obligatoirement le dernier état publié signé, l’état distant courant et le nouveau corpus validé. Le kit produit un plan signé comprenant `create`, `skip`, `update`, `move`, `redirect`, `delete`, `manual_review` et `blocked`. Une page absente du nouveau manifeste n’est jamais supprimée sans preuve d’appartenance à la version antérieure du même débat.

Les mises à jour et suppressions vérifient la révision ou l’empreinte attendue et utilisent le contrôle de concurrence MediaWiki. Toute modification humaine ou provenance indéterminée est classée `manual_review`. Les déplacements et fusions sont déclarés explicitement. Les suppressions sont exécutées seulement après vérification du nouveau graphe publié. Les opérations sont idempotentes et donnent lieu à un reçu final et à un nouvel état publié signé.

Le validateur contrôle localement les structures et la cohérence des plans, mais toutes les lectures et écritures MediaWiki restent dans le kit.

## Correctif 1.2.17 — contrôles avant publication

Avant la signature du plan, le validateur et le kit vérifient que chaque page Débat/Debate contient au moins un article Wikipédia vérifié, que les pages nouvelles n’ajoutent aucun `débats-connexes` ou `related-debates` et que les pages préexistantes en préservent exactement l’état et qu’aucun champ `auteurs`/`authors` ne contient un tableau JSON littéral.

La commande `./wikidebia publish` est entièrement non interactive : après validation positive et génération du plan, l’orchestrateur transmet lui-même l’empreinte SHA-256 du plan au moteur. L’option historique `--yes` reste tolérée pour compatibilité mais n’est plus nécessaire et aucune question `[o/N]` n’est affichée. La commande `update`, qui peut inclure des suppressions, conserve sa confirmation d’empreinte ou son équivalent automatisé explicite.

## Contrôle 1.2.19 des titres affichés

Avant toute génération d’un nouveau titre affiché, celui-ci est lu comme une phrase indépendante : la revue vérifie la présence d’un sujet, d’un prédicat et de la conclusion argumentative utile. Cette exigence ne sert pas à normaliser rétroactivement les `titre-affiché` déjà publiés dans un corpus importé du wiki. Pour ces pages préexistantes, le titre affiché est conservé par défaut, y compris lorsqu’il est nominal, et n’est corrigé que pour une faute ou un problème flagrant, ou sur décision explicite du propriétaire. Le titre canonique / nom de page reste, lui, soumis aux exigences d’autonomie et peut être corrigé.


En traduction, `displayed-title` traduit le `titre-affiché` français validé, quelle que soit la provenance de la source et même si la page cible anglaise est nouvelle. Une forme courte, nominale ou contextuelle ne doit pas être allongée ni transformée en proposition pour satisfaire une règle de génération. La fidélité du sens, de la portée et de l'acte de langage reste obligatoire : seule une dégradation introduite par la traduction est bloquante. Un renommage canonique change la cible `page=`, sans remplacer automatiquement le libellé `titre-affiché`.

## Contrôle 1.2.20 du placement des arguments

Avant `graph_validated`, effectuer une passe indépendante qui ne juge ni le style des titres ni le nombre de nœuds, mais uniquement la fonction logique des occurrences.

1. Pour chaque occurrence de niveau 1, formuler en une phrase sa réponse directe à la proposition du débat.
2. Rechercher un parent plus général non redondant. S’il existe, déplacer l’occurrence sous ce parent.
3. Vérifier si l’argument vise spécialement une preuve, une prémisse ou un mécanisme déjà présent. Dans ce cas, le rattacher comme objection ou justification à cette cible.
4. Regrouper sous une thèse générale les exemples historiques, résultats scientifiques, doctrines particulières, applications sectorielles et précisions techniques qui n’ouvrent pas une famille autonome.
5. Refaire le test après chaque déplacement, puis régénérer profondeurs, branches, lots, projections et empreinte structurelle.
6. Produire `reports/graph_placement_review.json` et le déclarer dans `editorial_controls.graph_placement_review_path`.

Le cas « les bouleversements de l’histoire des sciences » sert de test de régression générique : lorsqu’il conteste l’inférence du succès scientifique à la vérité ou au réalisme, il doit être une objection sous l’argument du succès scientifique, non un argument principal parallèle.

### Renforcement 1.2.22 — concision des titres affichés

Pour chaque langue, la concision et l’équivalence sémantique d’un titre affiché nouvellement généré sont revues explicitement. La proposition complète, le prédicat explicite et l’intelligibilité autonome sont des exigences de création. Pour un `titre-affiché` préexistant importé du wiki, la revue atteste au contraire sa préservation par défaut et ne le réécrit pas pour satisfaire ces seules exigences formelles ; seules une faute, une corruption, une ambiguïté flagrante ou une autre anomalie manifeste, ou une décision explicite du propriétaire, justifient normalement sa modification.


## Workflow 1.2.23

Avant validation, la revue choisit un sujet nominal conventionnel, contrôle la minuscule du complément, puis effectue une seconde recherche d’auteur chaque fois qu’une attribution provisoire reproduit le nom du site. Les nouveaux plans de reprise distante utilisent un résumé MediaWiki individualisé, calculé page par page à partir de la mutation réelle ; le résumé générique « Corrections » n’est plus émis. Le ZIP de livraison unique expose les trois composants à sa racine ; le gestionnaire courant sait également les découvrir dans un bundle imbriqué.

## Reprise sûre depuis la révision 1.2.25

Le planificateur peut produire `manual_review`, mais le gestionnaire et l’exécuteur refusent tous deux de l’exécuter. Aucun reçu final ni état publié n’est écrit dans ce cas. Un plan sans opération mutante renvoie `no_changes`. Une archive demandée par `--archive` est validée depuis une zone de staging ; `--dry-run` ne modifie pas le corpus installé. La promotion vers `corpus/<debate_id>/` intervient seulement après une exécution réelle sans opération non résolue.

## Attestation et portées différées depuis la révision 1.2.26

Un plan entièrement `skip` est attesté par une commande dédiée qui recharge le plan signé, relit toutes les pages et renouvelle l’état publié sans écrire sur MediaWiki. Toute archive de reprise requiert `--archive`; le staging est supprimé à chaque sortie. Si la portée demandée ne contient aucune opération mutante, la commande renvoie `no_changes_in_scope`. Avec `--no-delete`, les pages retirées mais non supprimées restent dans l’état signé sous le statut `pending_delete` jusqu’à une reprise `--only-delete`.



## Contrôle création/modification — révision 1.2.33

Avant rendu, chaque page est classée `new` ou `preexisting`. Toute page préexistante possède un instantané des paramètres protégés importés. Cette origine gouverne aussi la revue des métadonnées : la propositionnalité du titre affiché et la cible quantitative de mots-clés sont des règles de création pour `new`, tandis que `preexisting` suit une politique différentielle de conservation. Un `titre-affiché` historique est conservé sauf faute/problème flagrant ; les mots-clés historiques sont conservés sauf non-pertinence réelle explicitement justifiée, avec correction de casse/graphie et ajouts autorisés. Le rendu et le plan de mise à jour comparent cet instantané au wikicode proposé et bloquent toute mutation de `avancement`, `progress`, des avertissements IA et des débats connexes.

## Traduction anglaise différée — révision 1.2.34

Le manifeste peut déclarer `translation_status.en=deferred`. Dans ce cas, les Works français, la validation et `./wikidebia update --archive <archive> --scope fr` n'exigent ni titre anglais, ni page anglaise, ni lien interlangue. Les étapes anglaises et les contrôles bilingues sont suspendus. `--scope en` est bloqué. Après traduction, le statut passe à `ready` ou `published`; les titres anglais sont verrouillés, les pages anglaises sont ajoutées, puis une reprise française distincte ajoute les liens interlangues sans changer les dates de création. Cette section remplace toute instruction antérieure imposant le verrouillage anglais avant la génération française.

## Correctif 1.2.35 — traduction différée sur corpus historique

`translation_status.en=deferred` est lu comme un état opérationnel explicite, indépendamment de la révision éditoriale 1.2.x déclarée. `--scope fr` reste autonome ; `--scope en` est bloqué jusqu'au passage à `ready` ou `published`.

## Ponctuation des notes de référence (1.2.44)

Une simple notice documentaire placée dans `<ref>…</ref>` ne se termine pas par un point avant `</ref>`. Le point de la phrase principale vient après l’appel de note. Un point terminal interne est réservé à une phrase explicative complète et doit être attesté dans la revue par l’empreinte du corps exact de la note.

## Cohérence locale des liens Wikipédia explicatifs (1.2.45)

Les notions spécialisées de même rang énumérées ou comparées dans un même passage sont revues comme un groupe. Lier une seule notion alors que les notions voisines disposent d’articles pertinents et présentent le même besoin explicatif est interdit sans justification explicite. Le registre `wikipedia_link_groups` consigne la sous-partie, les termes, les articles, la décision et toute exception.



## Inventaire général des notions spécialisées (1.2.46)

La revue ne se limite pas aux séries de notions comparables. Chaque sous-partie est examinée intégralement et reçoit une entrée dans `specialized_term_inventory`. Toute notion susceptible d’arrêter un lecteur est liée, expliquée, rattachée à un traitement antérieur ou déclarée intelligible en contexte avec une justification spécifique. Tous les liens Wikipédia réellement présents sont recensés. Le registre `wikipedia_link_groups` de 1.2.45 est remplacé comme mécanisme actif par cet inventaire général.

## Traduction anglaise adaptative — révisions 1.2.53 et 1.2.55

Après verrouillage du français, la page Debate anglaise est traduite et documentée comme un lot autonome. Les pages Argument sont ensuite relues en unités internes de 10 pages par défaut, réduites à 5–8 pour les groupes riches en citations, recherches documentaires, ambiguïtés terminologiques ou anomalies de préservation. Une livraison longue peut agréger plusieurs unités déjà closes ; une page Argument est entièrement traitée dans une seule unité.

Chaque unité inclut : traduction idiomatique ; contrôle de l'orientation argumentative ; recherche autonome d'un éventuel `established-name=` anglais ; comparaison des formes anglaises concurrentes sans normaliser artificiellement `X argument`, `Argument from X`, les possessifs ou d'autres constructions attestées ; vérification que le nom couvre exactement la portée de la page ; recherche d'une version anglaise réelle pour les références françaises pertinentes sans traduction artificielle de leurs notices ; recherche de nouvelles références anglophones ; traitement des `Citation`→`Quote` selon les deux provenances du § 7.4 : traduction IA avec l'avertissement `AI-translated quote`, ou passage anglais publié exact avec notice d'édition, preuve et revue distinctes. Les checklists et exemples sont des garde-fous et non des patrons de rédaction.

Avant la rédaction des citations anglaises, choisir le mode documentaire anticipé ou intégré pour les liens MIA du verrou français, puis examiner les résultats et sélectionner les propositions éligibles avant d'appliquer la mémoire de traduction. Le mode anticipé ne relance pas de recherche ; une absence de preuve reste une abstention. Les contrôles des droits, de l'édition, de complétude et de convergence restent distincts. Une passe globale inter-unités est obligatoire avant finalisation afin d'harmoniser terminologie, titres, vocabulaire, documentation et noms consacrés, de vérifier la parité complète du graphe et d'empêcher les doublons des citations finales sur des pages distinctes, y compris pour la provenance IA. L'index public complet et frais exigé par le nouveau parcours doit être revalidé avant publication ou reprise des écritures. Lorsqu'un résumé français est historiquement absent et verrouillé comme tel, l'anglais conserve cette absence et aucun résumé de remplacement n'est généré.

## Architecture cumulative depuis 1.2.54

Les numéros de norme et les anciens champs `*_policy_revision` / `*_revision` ne sélectionnent plus les règles éditoriales. Le workflow applique la norme consolidée courante à partir de l’état fonctionnel du corpus. Les versions globales restent disponibles pour la lecture d’anciens formats, les migrations, la provenance et l’identification d’une livraison. Un registre ou un artefact dont le format évolue utilise sa propre version de schéma.


## Traduction différentielle — révision 1.2.56

Lorsqu'un contenu français déjà validé est traduit, il devient la source autoritative du contrôle de forme. Les normes de création ne doivent pas être utilisées pour « corriger » rétroactivement en anglais une question, un impératif, un intitulé thématique, un groupe nominal ou une autre forme déjà acceptée en français. Le contrôle porte sur la **non-régression** : une propriété formelle ou sémantique absente du défaut source ne peut être perdue ou dégradée par la traduction. Une proposition française ne peut notamment devenir un fragment, une simple étiquette ou une injonction anglaise.

Chaque titre traduit est relu selon un inventaire sémantique explicite : sujet, prédicat, polarité, modalité, attribution, quantificateurs, intensité, temporalité, condition, causalité/concession et portée du référent. Les contrôles lexicaux automatisés sont des signaux de revue, non des preuves autonomes d'erreur.


## Couverture différentielle complète — révision 1.2.57

La revue différentielle porte sur **chaque titre canonique traduit** en plus du `displayed-title`. Une attestation distincte consigne l’inventaire sémantique du titre canonique et confirme son équivalence avec le titre français autoritatif ; la validation d’un `displayed-title` ne peut servir de preuve par substitution.

La page `Debate` est relue comme un objet bilingue complet : titre canonique, `topic`, `expanded-topic`, affirmations et distinctions de l’introduction, faits historiques ou actuels, enjeux, et structure fonctionnelle des sous-parties. Le remplacement légitime d’une référence française par une source anglophone ne permet jamais de supprimer l’information que cette référence étayait.

Le verdict technique `passed` signifie seulement que les contrôles automatisés et les attestations requises sont cohérents. Le statut `release_ready` exige toujours les revues humaines prévues ; aucun rapport automatique ne doit se présenter comme une certification autonome de fidélité sémantique.

## Scellement documentaire et validation multicouche — révision 1.2.58

Avant une validation finale bilingue, `data/documentary_resources.json` est généré à partir de `data/sources.json`. Il regroupe les identités documentaires par DOI normalisé, URL canonique (sans fragment ni paramètres de suivi) ou empreinte bibliographique. Toute collision incompatible dans une même langue bloque la clôture documentaire.

Le rapport de validation conserve quatre statuts indépendants : structure, documentation, revue sémantique encodée et archive fraîche. Les trois premiers peuvent être calculés sur un dossier de paquet. Le quatrième est nécessairement établi après création du ZIP exact et figure dans le reçu externe.

Le moteur de marqueurs sémantiques est exécuté en mode traduction différentielle sur les titres canoniques, `displayed-title` et résumés. Il produit une liste de familles possiblement perdues à relire; aucune correction n’est appliquée automatiquement à partir de ce signal.



### Correctif 1.2.59 — preuve de recherche et complétude de citation

La traduction porte séparément `page_origin` (page cible) et `source_page_origin` (provenance française autoritative). Les règles de création se fondent sur la seconde : une page EN nouvelle issue d’un corpus FR préexistant conserve les titres affichés historiques, les nombres historiques de mots-clés et de rubriques sous le régime différentiel, tandis que les règles intrinsèques de qualité et la fidélité restent actives. L’introduction historique est adaptée de manière autonome au contexte anglophone, avec revue explicite du contenu franco-français. Pour toute nouvelle recherche de `nom-consacré=` / `established-name=`, conserver la provenance réelle (`actual_log` ou `fresh_recheck`) ; une décision historique reconstruite est marquée `historical_reconstruction` et ne remplace jamais une recherche obligatoire d'une nouvelle page anglaise. Chaque `Quote` est comparée intégralement à la `Citation` source ; un ratio lexical inférieur à 0,60 impose une seconde revue explicite, sans réécriture automatique. La release finale génère et revalide `release/content_inventory.json` sur l'archive exacte.


## Allocation adaptative des unités de traduction — 1.2.60

Avant toute rédaction anglaise, chaque page Argument reçoit un profil de densité calculé uniquement depuis le verrou français. Les facteurs observables incluent citations, citations longues, références sélectionnées, longueur et densité logique du résumé, données chiffrées et présence d’un nom consacré dans la source. Le profil recommande une unité de 10 pages (faible), 8 (moyenne), 6 (élevée) ou 5 (très élevée). Chaque unité reste indépendante et doit être close par un relecteur ; le score n’est jamais une note de qualité ni un substitut à la revue humaine.

## Réconciliation publication — 1.2.62

## Résumé de publication des traductions anglaises

Pour une page anglaise créée comme traduction d’une page française verrouillée, le résumé MediaWiki est individualisé : `Translation of the French page: [[:fr:X|X]]`, où `X` est le titre canonique français de la même `page_id`. Le plan signé conserve cette valeur page par page ; l’exécuteur la recalcule depuis le manifeste avant écriture et la relecture de la révision créée en vérifie l’identité exacte. Le résumé générique anglais reste réservé aux créations qui ne sont pas des traductions. Ce lien d’historique ne remplace pas le lien interlangue rendu dans la page française après passage à `ready`.


## Étape de convergence sémantique 1.2.66

Après finalisation de la revue anglaise et après toute dernière correction, exécuter deux passes sémantiques indépendantes consécutives sur exactement la même empreinte. Les méthodes déclarées doivent être distinctes et chaque passe doit conclure `new_certain_errors=0`. Une passe qui trouve une erreur ou toute mutation du contenu/review invalide la chaîne précédente. L'application de la traduction est bloquée tant que le reçu n'est pas `converged`. Le reçu et ses empreintes sont ensuite vérifiés lors du rendu, de la release et de l'extraction fraîche.


## Checkpoint français avant traduction

Après validation du graphe et des titres, l’orchestrateur rend un premier corpus français temporaire à partir du wikicode importé : seules les relations et les cibles/titres validés changent. Après réussite de `fr_content_review`, il rend un second corpus français temporaire, toujours avec `translation_status.en=deferred` et sans `interlangue`, et construit un nouveau plan de reprise contre l’état publié par le premier checkpoint. Pour toute page `preexisting`, la valeur effective d’un résumé ou de l’introduction est déterminée par sa décision scellée : `preserved` reprend exactement l’historique (ou son absence) ; `authorized_change` reprend exactement la valeur finale autorisée. Pour une introduction autorisée, la structure, `review.subsections`, les inventaires applicables, le changeset et le rendu sont calculés sur cette valeur sélectionnée ; les contrôles de création sont limités au périmètre ajouté ou substantiellement réécrit. Les mutations `create`, `update` et `move` sont exécutées avec les résumés MediaWiki individualisés et la balise `chatgpt`. Les redirections, suppressions et renommages sont admis uniquement au premier checkpoint lorsqu’ils sont issus de décisions structurelles/titres validées ; ils sont interdits au second checkpoint. La préparation de `en_translation_review` n’est autorisée qu’après les deux reçus `published` ou `verified_no_changes`. Une interruption réutilise le même plan ; une écriture déjà vérifiée n’est pas rejouée.

La validation de `data/sources_working.json` contrôle directement `document_kind` contre l’enum du registre documentaire avant application. Une valeur invalide est donc signalée dans la revue de contenu plutôt que reportée au préflight structurel de `data/sources.json`.

## Addendum 1.2.90 — titres français sans ligatures

Pour les titres **français** (nom de page Débat ou Argument, titre affiché du registre et libellé de chaque occurrence relationnelle), les ligatures doivent être dissociées en lettres accessibles sur un clavier ordinaire : `œ → oe`, `Œ → OE`, `æ → ae`, `Æ → AE`, `ﬀ → ff`, `ﬁ → fi`, `ﬂ → fl`, `ﬃ → ffi`, `ﬄ → ffl`, `ﬅ → st`, `ﬆ → st`. Les accents français et les autres caractères ne sont pas translittérés ; aucune normalisation Unicode de compatibilité générale n'est appliquée. Cette règle ne s'étend ni aux citations, ni aux titres bibliographiques, ni aux textes historiques hors des champs de titre.

Cette correction orthographique est une exception obligatoire à la préservation des titres historiques. La revue explicite les changements du registre ; chaque libellé contextuel conserve sa formulation et son occurrence, avec la seule substitution des ligatures au premier checkpoint français. La provenance importée reste intacte ; les renommages et liens suivent le plan signé et les contrôles de collision habituels. Une ligature importée est signalée avant verrouillage, puis bloquante après le verrou des titres ou en validation finale (`WDV-GRA-016`). Les relations rendues sont contrôlées indépendamment. Un titre externe hors périmètre qui nécessite un renommage doit être traité explicitement avant publication ; il n'est jamais renommé par un remplacement global. Le parcours de traduction sans correction française ne peut pas sceller un corpus présentant cette anomalie.
