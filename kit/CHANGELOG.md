## Correctif du 14 novembre 2026 — adoption contrôlée d’un Work restauré

- permet à un workflow initial sans `work_id` d’adopter explicitement un Work
  `release_ready` dont le workspace et le reçu de release sont intacts ;
- refuse l’adoption après toute publication anglaise ou autorisation finale ;
- exige ensuite les deux checkpoints français ordinaires et leurs reçus signés ;
- arrête la reprise à la frontière `release_ready` avant la publication finale.

## 2.15.54 — 10 août 2026 — alignement des métadonnées de première publication anglaise

- aligne le validateur courant sur le contrat déjà actif : aucune projection `initialisation` → `initialization` pour une nouvelle traduction anglaise ;
- conserve `creation-date` anglaise indépendante de `date-création` française et sous responsabilité du jour réel de première publication distante ;
- préserve les métadonnées historiques des pages anglaises préexistantes ;
- ajoute des tests d’exécution croisés et restaure l’attribution historique exacte des versions 2.15.52 et 2.15.53.

## 2.15.53 — 10 août 2026 — renommage des paramètres MediaWiki

- émet `sujet-développé` / `expanded-topic` et `débat-dédié` / `dedicated-debate` dans les sorties courantes ;
- conserve la lecture des anciens noms pour les corpus historiques et normalise les reprises sans modifier les valeurs ;
- ajoute les tests de migration, de reprise et de non-coexistence des anciens/nouveaux noms.

## 2.15.52 — 10 août 2026 — durcissement final des preuves

- normalise les familles de méthodes des passes de convergence ;
- ajoute la régression explicite `established-name=` → keyword ;
- teste le parsing multiligne jusque dans `wikidebia_publish.py` ;
- conserve tous les comportements éditoriaux de 2.15.51.

## 2.15.51 — 10 août 2026 — régressions réelles et changements idiomatiques revus

- changement de forme du displayed-title autorisé seulement avec revue de l’acte de langage ;
- corpus versionné de régressions FR→EN réelles, mauvaises/corrigées ;
- catalogue sémantique aligné avec le validateur ;
- preuves source/cible obligatoires pour les risques ;
- preuves par champ Debate propagées dans les verrous.

## 2.15.50 — 10 août 2026 — preuve sémantique et convergence finale

- enrichit translation_review avec empreintes, preuves et risques ;
- ajoute la commande de convergence à deux passes distinctes ;
- bloque l'application sans reçu convergé et propage sa preuve jusqu'à la release ;
- ajoute les concept_id déterministes et les régressions de parsing multiligne.

## 2.15.49 — 10 août 2026 — cohérence documentaire croisée

- aligne les métadonnées sur la norme 1.2.65 et le validateur 0.4.68 ;
- ajoute un test croisé vérifiant que le guide actif des Normes emploie `nom-consacré=` / `established-name=` ;
- ajoute le regression gate `active_document_contract_consistency`.

## 2.15.48 — 10 août 2026 — tests critiques autonomes

- rend `test_wikidebia_remote_update.py` autonome en ajoutant explicitement `scripts/` à son chemin d’import ;
- applique la même correction à `test_reference_note_punctuation_1244.py` ;
- ajoute deux tests de régression qui relancent ces modules dans des processus pytest réellement isolés ;
- aligne les métadonnées sur la norme 1.2.64 et le validateur 0.4.67.

## 2.15.47 — 10 août 2026 — correctif de réconciliation

- restaure dans `KIT_MANIFEST.json` les scopes, règles de sécurité, features, quality gates et regression gates de la branche publication ;
- aligne les guides actifs sur `nom-consacré` / `established-name` et `AI-translated quote` ;
- ajoute des tests ciblés empêchant la perte déclarative d’une capacité de branche lors d’une future fusion.

## 2.15.46 — 10 août 2026 — réconciliation traduction + publication

- fusionne la lignée traduction/validation 2.15.38 avec la lignée de publication GitHub 2.15.45 (`8b46816`) ;
- conserve la validation différentielle, le moteur de marqueurs sémantiques, la revue de portée des appellations consacrées, le registre documentaire, la complétude des `Quote`, la validation multicouche et le scellement d’archive de la lignée traduction ;
- conserve les résumés de publication FR→EN, les balises `translated-fr`, le rattrapage de balises, la reprise interlangue, la relecture distante bornée, `nom-consacré` / `established-name`, la politique `initialization` et la date réelle de création anglaise de la lignée GitHub ;
- archive les historiques de branches lorsque les mêmes numéros de version avaient été réutilisés avec des changements différents ;
- aligne le kit sur la norme 1.2.62 et le validateur 0.4.65.

L’historique exact des deux branches antérieures est conservé sous `branch_history/`.

## 2.15.55 — 10 août 2026 — workflows version-agnostiques et release canonique

- centralise les versions courantes dans `VERSIONS.json` via `wikidebia_release_info.py` ;
- remplace les égalités exactes kit/validateur des workflows par des contrats de schéma/capacité ;
- normalise à l’entrée les labels historiques des plans et paramètres MediaWiki ;
- fait de la release complète unique le format standard pour upgrade, audit, conservation et handoff.

## 2.15.56 — 11 août 2026 — correction graph-extract dedicated-debate

- corrige le `Namespace` de `graph-extract` : `args.follow_local_relations_at_dedicated_debate` est désormais utilisé de bout en bout ;
- conserve `--follow-local-relations-at-detailed-debate` comme alias d’entrée historique ;
- ne renomme pas les clés internes `complete_topic` et `detailed_debate`, conformément au contrat 1.2.69 ;
- ajoute des tests de régression sur `main()` et sur les deux noms d’option ;
- aucune modification des formats de corpus, des règles éditoriales ou des contrats de publication.


## 2.16.0 — 11 août 2026 — orchestration ergonomique des revues ChatGPT

- ajoute `workflow`, `review-import` et `workflow-status` au lanceur principal ;
- enchaîne automatiquement extraction, initialisation, validations, promotions, applications, rendu et release jusqu’au prochain point éditorial ;
- produit des ZIP minimaux `wikidebia-chatgpt-review-package-1.0` avec séparation `editable/` / `context/` ;
- vérifie provenance locale, manifeste, contexte, baseline locale, structure ZIP et absence de fichiers supplémentaires ;
- restaure transactionnellement le répertoire de contrôle si la finalisation d’un retour échoue ;
- orchestre graphe, métadonnées françaises, contenu/documentation française, traduction/documentation anglaise et convergence sémantique ;
- rouvre la traduction et recommence les deux passes sémantiques lorsqu’une erreur certaine est trouvée ;
- ajoute `outgoing/` aux zones privées exclues de Git ;
- conserve toutes les primitives détaillées et tous les garde-fous de publication existants.

## 2.16.1 — 11 août 2026 — reprise ergonomique après validation initiale

- n’interrompt plus l’orchestration avant la revue des métadonnées pour les seuls défauts de forme/autonomie de titres importés que cette revue peut corriger ;
- conserve le blocage immédiat des incohérences réellement structurelles du graphe ;
- remplace le message opaque de validation initiale par un état `blocked_technical` avec codes/messages concrets ;
- produit automatiquement `outgoing/<debate_id>_initial_validation_diagnostic.zip`, limité aux rapports, graphe, registre, imports et contexte nécessaires, sans secret ;
- une simple relance de `workflow` réessaie la validation bloquée après mise à jour/correction et poursuit ensuite normalement ;
- ajoute des tests d’intégration sur le paquet de diagnostic et la reprise.

## 2.16.2 — 11 août 2026 — short_code ASCII et reprise sans reset

- dérive le `short_code` automatique depuis le `debate_id` canonique ASCII plutôt que depuis les initiales Unicode du titre ;
- `revenu_de_base` produit déterministement `RDB` ;
- répare automatiquement un workflow existant dont `short_code` est absent ou invalide avant l’initialisation du corpus ;
- accepte `--short-code` lors de cette reprise sans exiger la suppression de `.state/workflows/...` ;
- conserve et protège un code déjà valide en refusant une valeur explicite contradictoire ;
- ajoute des régressions sur le titre « Un revenu de base doit-il être instauré ? », le corpus-init direct et la reprise du workflow.
## 2.16.3 — 11 août 2026 — correction de la boucle de rejet du graphe

- corrige `review-import`, qui ne passe plus inconditionnellement à `promote_and_workspace` après `finalize_graph_review` ;
- un résultat `rejected` ouvre désormais `graph_correction` et produit automatiquement un paquet ChatGPT ;
- ajoute le contrat `wikidebia-graph-correction-1.0` et un moteur déterministe de reconstruction des placements, relations, profondeurs, branches, rôles et compteurs ;
- valide la correction avant reprise et restaure transactionnellement le build en cas d’échec ;
- prépare obligatoirement une nouvelle revue complète du graphe après correction, sans promotion implicite ;
- ajoute des tests de rejet, correction valide, correction invalide/rollback et absence de promotion.
## 2.16.4 — 11 août 2026 — exécution des décisions structurelles de revue

- ajoute `--execute-graph-actions` à `review-import` pour appliquer en une commande les décisions explicites `remove`, `merge_redirect`, `move` et `relation_change` ;
- retire les modèles de relation des pages mères et transforme les doublons en `#REDIRECTION [[page conservée]]` ;
- produit un résumé MediaWiki individualisé par page, avec `[[destination]]` obligatoire dans le résumé de retrait d’un doublon ;
- valide la projection locale complète avant la première écriture distante, puis préflight toutes les pages et revérifie chaque révision avant mutation ;
- relit contenu, résumé et balise `chatgpt` après chaque édition ;
- accepte de façon étroite les décisions propriétaires déjà inscrites dans certains ZIP 2.16.2/2.16.3 ;
- reconstruit le graphe et prépare une nouvelle revue complète sans promotion implicite.
## 2.16.5 — 11 août 2026 — relecture post-écriture bornée et reprise idempotente

- applique aux actions structurelles la même politique de relecture bornée déjà utilisée par la publication et les mises à jour ordinaires ;
- tolère le retard temporaire de visibilité d’une nouvelle révision et de la balise `chatgpt` après `action=edit` ;
- distingue les échecs de contenu, résumé, identifiant et balise au lieu d’un diagnostic générique ;
- lors d’une relance après exécution partielle, accepte un état final déjà présent uniquement si la révision courante porte exactement le contenu, le résumé et la balise attendus ;
- ajoute des tests de retard de réplica/balise et de reprise sans réécriture d’une page déjà correctement modifiée.

## 2.16.6 — 11 août 2026 — cohérence de la provenance après actions structurelles

- met à jour `sha256` et `size_bytes` de `data/import_provenance.json` après toute action de graphe qui réécrit un snapshot local (`update` ou `redirect`) ;
- répare automatiquement les états 2.16.4/2.16.5 déjà exécutés uniquement lorsque `graph_action_decisions.json` atteste le chemin, l’empreinte post-action exacte et une révision distante avancée ;
- laisse toute autre divergence de provenance bloquante, sans normalisation ni adoption silencieuse ;
- exécute cette réparation étroite avant la création/reprise du workspace éditorial afin d’éviter le blocage `Empreinte de provenance divergente` sur une modification effectuée par le kit lui-même ;
- ajoute des régressions couvrant la mise à jour immédiate de provenance, la reprise du défaut 2.16.5 et le maintien du blocage d’une dérive non attestée.


## 2.16.7 — 11 août 2026 — reprise de provenance après plusieurs vagues de corrections du graphe

- corrige la reprise 2.16.6 lorsque plusieurs séries d’actions structurelles ont été exécutées : `reviews/graph_action_decisions.json` ne conserve que la dernière série, tandis que les séries antérieures restent attestées dans `.state/graph-actions/<débat>/` ;
- agrège, pour la réparation de compatibilité uniquement, les plans et reçus historiques dont les schémas, identifiants de débat et empreintes internes sont valides ;
- exige que le contenu local corresponde exactement à `desired_sha256` et que la révision de provenance corresponde à la révision réellement écrite par le reçu avant de rafraîchir `sha256` et `size_bytes` ;
- ne réexécute aucune écriture distante et laisse toute dérive non attestée bloquante ;
- ajoute une régression reproduisant deux vagues de corrections où l’audit courant a écrasé l’attestation de la première vague.
## 2.16.8 — 11 août 2026 — import de revue transactionnel et cohérence de release

- `review-import` conserve désormais une sauvegarde transactionnelle jusqu’à la réussite de l’avancement mécanique suivant.
- En cas d’échec local après acceptation d’une revue, la base, le workflow et les artefacts mécaniques nouvellement créés sont restaurés ; le même paquet de revue reste réimportable.
- Les actions de graphe déjà écrites à distance sont traitées comme une frontière irréversible explicite et restent enregistrées pour reprise, sans faux rollback local.
- La réparation de provenance est documentée et testée comme mécanisme fondé sur preuves/schémas plutôt que sur le numéro du kit producteur.
- Pour les versions installées à partir de 2.16.8, `upgrade` ne requiert plus l’égalité du triplet répété dans les trois composants : chaque composant fait autorité pour sa propre version, les versions étrangères restant de la provenance.
- La fabrication de release est assortie d’un contrôle explicite garantissant que les trois `VERSIONS.json` embarqués sont identiques.

## 2.16.9 — 12 août 2026 — revue différentielle des métadonnées préexistantes

- propage `page_origin=preexisting` dans les paquets de revue issus d’un corpus extrait du wiki ;
- ne requiert plus `displayed_title_complete_proposition=true` pour un `titre-affiché` historique préexistant et ne le réécrit pas pour la seule raison qu’il est nominal ;
- conserve les exigences complètes de création pour les pages/titres nouveaux ;
- ne bloque plus une page préexistante parce qu’elle dépasse la cible de mots-clés de création ;
- vérifie qu’aucun mot-clé historique n’a été retiré, sauf correction explicitement décrite ou suppression `clearly_irrelevant` accompagnée d’une justification ;
- autorise corrections de casse/graphie, réordonnancement et ajouts de mots-clés ;
- ajoute les consignes correspondantes directement dans les ZIP `fr_metadata_review` et des tests de non-régression.

## 2.16.10 — 12 août 2026 — faux positif « Il ne faut »

- corrige `WDV-EDT-016` via le validateur aligné : `Il ne faut…` est reconnu comme tournure impersonnelle, au même titre que `Il faut…` ;
- maintient le blocage des pronoms réellement anaphoriques comme `Il réduit…` lorsque leur référent est extérieur au titre ;
- ajoute une régression explicite sur le titre réel `Il ne faut pas instaurer plus de temps libre` ;
- aucune règle éditoriale n’est assouplie et la norme reste 1.2.78.

## 2.16.11 — 12 août 2026 — provenance retirée et revue de contenu

- conserve dans `import_provenance.json` les pages retirées du graphe afin de préserver leur traçabilité ;
- exclut de la couverture active de la revue de contenu uniquement les lignes explicitement marquées `retired_redirect` ou `retired_deleted` ;
- continue de bloquer toute ligne de provenance supplémentaire non explicitement retirée et toute absence de provenance pour un nœud actif ;
- ajoute des tests positif et négatif de non-régression.

## 2.16.12 — 12 août 2026 — résumés individualisés des reprises de corpus

- chaque nouveau plan `update --archive` déclare `edit_summary_contract=page_specific_v1` ;
- les opérations `create`, `update`, `move`, `redirect` et `delete` portent toutes une politique et un résumé MediaWiki propres ;
- une mise à jour ordinaire calcule son résumé à partir des paramètres réellement modifiés (`résumé`, références, rubriques, mots-clés, introduction, plan argumentatif, etc.) ;
- l’ajout interlangue français conserve son résumé spécialisé avec wikilien anglais ;
- les renommages, redirections et suppressions reçoivent des résumés spécifiques à leur opération ;
- l’exécuteur recalcule le résumé attendu avant chaque écriture, refuse une divergence ou `Corrections`, puis vérifie le résumé dans la révision relue ;
- les plans historiques sans contrat individualisé conservent leur voie de compatibilité ;
- les tests couvrent les cinq familles de mutations et le refus du résumé générique.

## 2.16.13 — 12 août 2026 — publication française automatique avant traduction

- fait de la réussite de `fr_content_review` une frontière distante : rendu FR sans interlangue, plan signé, publication/attestation, puis seulement préparation anglaise ;
- réutilise le moteur de reprise 2.16.12 et ses résumés MediaWiki individualisés, gardes de révision et vérifications post-écriture ;
- conserve le plan/reçu et reprend idempotemment après interruption, y compris si la publication a réussi mais que la préparation anglaise échoue ensuite ;
- répare les workflows déjà arrêtés sur un paquet anglais produit avant cette règle en publiant d’abord le checkpoint français manquant ;
- déplace l’UX de retour vers `incoming/` : `./wikidebia review-import` pour un seul paquet, `./wikidebia review-import <debate_id>` en cas de pluralité ;
- sélectionne par `REVIEW_PACKAGE.json.debate_id`, archive le ZIP après succès et le conserve dans `incoming/` après échec ;
- valide `document_kind` directement dans `sources_working.json` avant la projection finale.

## 2.16.14 — 12 août 2026 — deux publications françaises avant traduction

- transforme le checkpoint français unique en deux checkpoints ordonnés : `graph` puis `content` ;
- le paquet `graph_review` combine désormais dans un même ZIP placements/relations, décisions structurelles et revue des titres canoniques/affichés ; il n’existe plus de handoff de titres séparé dans un nouveau workflow ;
- son réimport approuvé déclenche immédiatement le checkpoint `graph`, qui reconstruit les relations à partir du graphe validé mais conserve à l’identique résumés, introduction, références, rubriques et mots-clés du wikicode importé ;
- les suppressions, fusions/redirections et déplacements décidés pendant la revue sont différés et publiés avec les titres au premier checkpoint ;
- le checkpoint `content` utilise `.state/published` issu du premier comme baseline, ne republie que le delta de contenu/classification et refuse `move`, `redirect` et `delete` ;
- la traduction anglaise n’est préparée qu’après les deux reçus français ;
- conserve `incoming/`, la sélection par `debate_id`, les résumés personnalisés et la validation précoce de `sources_working.json.document_kind`.

## 2.16.16 — 12 août 2026 — préservation des résumés et de l’introduction historiques

- corrige la régression réelle où `fr_content_review` pouvait réécrire et publier l’introduction et les résumés de pages déjà existantes ;
- initialise les décisions de ces champs à `keep` et refuse toute modification dans une reprise ordinaire ;
- conserve l’absence historique de résumé au lieu de générer un texte de remplissage ;
- exclut les règles de style de création pour les textes historiques simplement préservés ;
- scelle les empreintes des textes historiques dans `fr_content_lock.json` et empêche leur apparition dans le changeset de contenu ;
- précise dans le paquet ChatGPT que ces champs sont en lecture seule et qu’une réécriture nécessite une opération corrective propriétaire distincte ;
- ajoute des tests de non-régression couvrant introduction, résumé existant et résumé historiquement absent.
- aligne la traduction sur cette préservation : un résumé français historique reste une source différentielle et n’est pas allongé pour satisfaire les règles de création ; le registre de style anglais utilise `translated_historical_source`.

## 2.16.17 — 12 août 2026 — consentement propriétaire scoped sur les textes historiques

- remplace l’immutabilité absolue de 2.16.16 par « préservation par défaut → suggestion → décision explicite du propriétaire → modification autorisée et traçable » ;
- ajoute `historical_change_request` et la distinction `preserved` / `authorized_change` ;
- ajoute `review-import --authorize-historical-changes`, qui produit hors ZIP un reçu local lié à l’archive exacte, au paquet/manifeste et aux SHA avant/après ;
- permet les corrections autorisées pendant la même `fr_content_review`, publiées au checkpoint n°2 sans troisième frontière ;
- conserve l’absence historique d’un résumé sauf création nominativement autorisée et n’applique pas rétroactivement les règles stylistiques de création à une correction locale ;
- normalise les anciennes revues supportées par schéma/données, conserve leurs autres décisions et transforme les deltas automatiques non autorisés en suggestions ;
- traduit ensuite la version française finale effectivement autorisée.

## 2.16.18 — 12 août 2026 — valeur finale sélectionnée et portée différentielle des textes historiques

- utilise la valeur finale autorisée comme valeur éditoriale effective après `authorized_change`, l’historique restant uniquement la provenance ;
- fait travailler `review.subsections`, les contrôles structurels, le verrou, le changeset, le rendu, le checkpoint français n°2 et la traduction sur cette valeur sélectionnée ;
- ajoute une portée structurée des introductions historiques (`added`, `modified`, `removed`, `reordered`) et bloque tout delta parasite hors portée ;
- applique les contrôles de création/réécriture uniquement aux sous-parties ajoutées ou substantiellement modifiées, sans requalifier les sous-parties historiques inchangées ;
- conserve la compatibilité des reçus de consentement 2.16.17 à portée de champ entier ;
- ajoute une régression d’intégration reproduisant le vote électronique : 4 sous-parties historiques + ajout autorisé de `Enjeux du débat` → verrou historique/final, changeset et checkpoint 2 à 5 sous-parties ; le même delta sans autorisation est bloqué.

## 2.16.19 — 12 août 2026 — provenance éditoriale et reprise différentielle des métadonnées historiques

- ajoute `source_page_origin` dérivé des verrous français et non modifiable par la revue anglaise ;
- réserve aux sources nouvelles les quotas keywords et les préférences de titres affichés propositionnels/lisibilité ;
- maintient atomicité, forme canonique, longueur et vocabulaire contrôlé pour les keywords historiques ;
- transforme le ratio EN/FR historique hors plage en signal exigeant une justification bilingue ;
- conserve l’adaptation autonome des introductions historiques et leurs contrôles documentaires intrinsèques sans imposer `Stakes of the debate` ;
- autorise les corrections de rubriques historiques avec justification sans blocage par cardinalité ;
- supprime la troncature `[:4]` des rubriques importées et corrige le tri alphabétique français accentué ;
- normalise les anciens paquets de revue supportés dépourvus des nouvelles attestations de provenance.

## 2.16.20 — 12 août 2026 — sous-paramètres facultatifs vides des Citation/Quote historiques

- corrige `_citation_template()` : un nom de paramètre vide reste bloquant, mais une valeur facultative vide est conservée dans l’inventaire puis omise par le rendu canonique ;
- n’invente aucune valeur pour `ouvrage`, `numéro`, `localisation`, `page`, `édition`, `lieu` ni leurs équivalents anglais ;
- conserve la provenance historique exacte dans `source_parameters` et la projection anglaise dans `parameters` ;
- applique la même omission canonique à `work`, `issue`, `location`, `page`, `publisher` et `place` dans `{{Quote}}` ;
- ajoute les régressions A0055-C001/A0056-C001 et un trajet d’intégration vote électronique allant de l’autorisation historique au checkpoint français n°2 puis à la préparation de la revue anglaise ;
- conserve le contrôle amont qui bloque une valeur obligatoire `citation` vide.

## 2.16.21 — 13 août 2026 — rollback transactionnel des checkpoints français pré-écriture

- étend la sauvegarde transactionnelle de `review-import` au stage français concerné sous `.state/fr-publication/<debate>/<work>/` ;
- supprime ou restaure `checkpoint-corpus/`, `checkpoint.json`, `remote-update-config.json`, `update-plan.json`, `inventory/` et les autres artefacts dérivés lorsque la tentative échoue avant toute exécution distante ;
- préserve intégralement le checkpoint `graph` déjà publié lors d’un rollback du stage `content` ;
- conserve sans rollback le checkpoint, le plan et les preuves dès qu’une exécution distante a commencé, afin de maintenir la reprise idempotente ;
- autorise `build_checkpoint()` à reconstruire un checkpoint de source divergente laissé par 2.16.20 uniquement lorsque l’état est prouvablement pré-exécution (aucun plan, ou plan bloqué/non exécutable) ; un reçu de publication ou un plan exécutable bloque tout auto-nettoyage ;
- ajoute les régressions sur deux échecs locaux successifs, conservation après début d’écriture et le scénario vote électronique v6 → v7 jusqu’au prochain handoff anglais.
## 2.16.22 — 13 août 2026 — préservation de présence des paramètres éditoriaux historiques

- capture séparément la présence historique des paramètres top-level éditoriaux des pages Débat et Argument dans `source_parameter_presence` ;
- propage cette présence de l’import vers la revue, `fr_content_lock.json` et le rendu du checkpoint `content` ;
- introduit un état interne `present-empty` : `None` continue de signifier « absent », tandis qu’un paramètre historiquement présent dont la valeur finale est vide est émis sous la forme `|paramètre=` ;
- n’ajoute jamais mécaniquement un paramètre vide historiquement absent et ne remplace aucune valeur par un espace ou une valeur factice ;
- conserve l’omission spéciale des `justifications`/`objections` sur une page frontière `débat-dédié` et ne modifie pas le mécanisme explicite `allowed_parameter_deletions` ;
- ajoute les régressions A0021 `|objections=`, Débat `bibliographie-pour=` / `vidéographie-contre=`, présence absente, suppression explicitement autorisée, non-vidage d’une valeur historique non vide et préflight synthétique de 100 mises à jour sans blocage.

## 2.16.23 — 13 août 2026 — migration des revues appliquées avant la présence top-level

- redérive `source_parameter_presence` depuis le `reviewed-copy` immuable lors de la reconstruction du contenu, même si une revue approuvée ancienne ne portait pas encore ce champ dans `final_values` ;
- détecte un `content-reviewed-copy` appliqué ancien dont le verrou ne contient pas l’inventaire complet de présence et le reconstruit localement avant tout checkpoint `content` ;
- refuse cette migration dès qu’un état `.state/fr-publication/<débat>/<work>/content` existe, afin de ne jamais effacer ou remplacer un plan/reçu potentiellement lié à une exécution distante ;
- conserve l’idempotence des revues déjà migrées ;
- ajoute une régression reproduisant une revue finalisée/appliquée pré-2.16.22 puis reprise sous le kit courant ;
- s’aligne sur le validateur 0.4.92, qui accepte les paramètres top-level historiquement présents et scellés lorsqu’ils sont rendus vides.

## 2.16.24 — 13 août 2026 — omission canonique des paramètres optionnels vides

- retire le rendu `present-empty` introduit en 2.16.22 : un paramètre optionnel vide est toujours omis ;
- conserve `source_parameter_presence` comme provenance d’audit sans effet sur le wikicode ;
- autorise au préflight la disparition des paramètres éditoriaux optionnels gérés, après validation du corpus, sans affaiblir la protection des paramètres de cycle de vie, inconnus ou hors contrat ;
- corrige les régressions réelles `A0021 |objections=` et Débat `|bibliographie-pour=` / `|vidéographie-contre=` ;
- s’aligne sur la norme 1.2.87 et le validateur 0.4.93.

## 2.16.25 — 13 août 2026 — normalisation des vérifications documentaires anglaises

- corrige le blocage tardif `WDV-SCH-003` où `sources_en_working.json` acceptait `checked_at` / `method` / `note` puis les recopiait tels quels dans `data/sources.json` ;
- normalise ces clés historiques vers `verified_at` et `notes` au moment de la projection finale ;
- conserve explicitement `primary_source=null` lorsqu'une revue déjà préparée n'avait jamais enregistré cette classification, sans fabriquer `true` ou `false` ;
- exige `verification.primary_source` booléen dans toute nouvelle vérification au format canonique ;
- préserve le `review_sha256`, le `semantic_content_sha256` et les deux passes de convergence, la migration ne touchant qu'aux métadonnées documentaires non sémantiques de sortie ;
- s'aligne sur le validateur 0.4.94 ; la norme active reste 1.2.87.


## 2.16.26 — 18 août 2026 — garde pré-convergence des titres anglais

- refuse les apostrophes typographiques non ASCII dès la finalisation de `en_translation_review` / `en_translation_correction` ;
- ne normalise jamais silencieusement un titre scellé ;
- pour un Work déjà convergé sous une version antérieure, détecte avant application tous les champs de titre non conformes et rouvre automatiquement `en_translation_correction` ;
- invalide alors le reçu de convergence afin que les deux passes indépendantes recommencent sur la nouvelle empreinte ;
- ajoute les apostrophes ASCII aux instructions des paquets de traduction/correction et une régression d’orchestration sur la reprise post-convergence ;
- s’aligne sur le validateur 0.4.95 ; la norme active reste 1.2.87.
## 2.16.27 — 18 août 2026 — garde documentaire anglaise avant convergence

- valide `sources_en_working.json` avant la première convergence avec le contrat documentaire réellement exigé par `data/sources.json` ;
- exige `document_kind` et `documentary_scope=foundational_work|broad_synthesis` pour toute bibliographie de la page Debate ;
- exige `authorship_verified=true` pour tout auteur Web/vidéo conservé et bloque la copie mécanique auteur=site ;
- pour un Work ancien déjà convergé, inventorie toutes les lacunes en une seule fois et ouvre `en_documentation_correction`, avec seul `sources_en_working.json` éditable ;
- laisse les valeurs sémantiques en lecture seule pendant cette correction et invalide proprement l’ancien reçu de convergence lors de la réouverture ;
- ajoute des régressions sur le blocage précoce, l’inventaire documentaire exhaustif et l’orchestration post-convergence ;
- conserve la norme 1.2.87 et le validateur 0.4.95.

## 2.16.28 — 19 août 2026 — réconciliation documentaire des branches 2.16.27

- conserve la garde `en_documentation_correction` introduite dans la branche préflight 2.16.27 ;
- réutilise l’identifiant canonique d’une ressource anglophone déjà présente dans le registre au lieu de recréer un doublon FR→EN ;
- préserve les métadonnées historiques de la ressource réutilisée et ajoute uniquement les usages anglais revus ;
- bloque toute fusion silencieuse si la famille documentaire ou `document_kind` diverge ;
- aligne la garde Debate sur le vocabulaire documentaire complet : `legal_text` est valide lorsque la portée est `foundational_work`/`broad_synthesis` et la sélection suffisamment justifiée ;
- ajoute des régressions reproduisant le doublon DEF CON `S10003 → S00013` et l’acceptation d’un texte juridique large ;
- s’aligne sur la norme 1.2.87 et le validateur 0.4.96.

## 2.16.29 — 19 août 2026 — réconciliation documentaire + rendu historique

- réconcilie les deux variantes 2.16.28 sans supprimer aucune capacité de branche ;
- conserve `en_documentation_correction`, la réutilisation d’identité documentaire et le contrôle Debate fondé sur la portée documentaire ;
- conserve `historical_text_render_validation_mode=differential_preservation_v1` au rendu final ;
- conserve les audits et régressions des deux branches ;
- s’aligne sur le validateur 0.4.97 et la norme inchangée 1.2.87.

## 2.16.30 — 19 août 2026 — rendu FR→EN source-authoritative des métadonnées protégées

- corrige le renderer bilingue qui appliquait encore les valeurs de création anglaises à une page cible `new` alors qu’elle traduisait une page française autoritative ;
- projette `avancement→progress`, `avertissements-titre→title-warnings`, `avertissements-débat→debate-warnings`, `avertissements-argument→argument-warnings` et `avertissements-résumé→summary-warnings` depuis la présence et la valeur françaises effectives ;
- une absence française reste une absence anglaise et aucune valeur `generated by AI` n’est ajoutée du seul fait que la page anglaise est techniquement nouvelle ;
- une page française réellement nouvelle conserve ses valeurs de création, traduites par la table normative ;
- conserve `WDV-MWK-023` inchangé comme garde de non-régression et ajoute des tests couvrant absence, traduction de valeurs présentes et source française nouvelle ;
- conserve intégralement les réconciliations documentaire et historique de 2.16.29 ; norme 1.2.87 et validateur 0.4.97 inchangés.

## 2.16.31 — 19 août 2026 — atomicité des mots-clés localisée par langue

- renseigne dans `keyword_vocabulary_bilingual.json` les métadonnées anglaises `en_kind`, `en_capitalization_policy`, `en_atomic_concept`, `en_compositional_intersection`, `en_multiword_exception` et `en_multiword_exception_rationale` ;
- empêche qu’une exception multi-mots requise par la forme française soit appliquée mécaniquement à une forme anglaise plus compacte ;
- conserve une exception propre lorsque la forme anglaise comporte plus de deux mots ou un connecteur pertinent ;
- ne modifie ni les mots-clés validés, ni leur ordre, ni `WDV-EDT-025` ;
- ajoute des régressions sur `ballot stuffing`, une forme anglaise longue et l’émission effective des champs `en_*` ;
- s’aligne sur la norme 1.2.87 et le validateur 0.4.98.

## 2.16.32 — 19 août 2026 — preuves historiques finales et dates documentaires inline

- réconcilie `summary_style_review.json` au rendu depuis les verrous FR/EN pour les résumés historiques, absents ou explicitement autorisés, sans fabriquer d’attestations de création ;
- propage dans `individual_review.json` les preuves de changement de forme idiomatique et les attestations de revue attendues par le validateur courant ;
- localise les dates documentaires ISO présentes dans la prose des notes `<ref>` anglaises sans modifier les URL ;
- conserve les deux passes de convergence et toutes les décisions sémantiques déjà scellées ;
- s’aligne sur la norme 1.2.87 et le validateur 0.4.99.

## 2.16.33 — 19 août 2026 — diagnostic complet automatique des validations bloquées

- généralise le paquet de diagnostic de validation à tous les appels orchestrés du validateur via `_run_validator` ;
- crée automatiquement `outgoing/<debate_id>_<rapport>_diagnostic.zip` lors d'un échec ;
- inclut `ERRORS.json` et `ERRORS.txt` avec la liste exhaustive des erreurs, au-delà des quatre diagnostics affichés dans le terminal ;
- joint le rapport JSON/TXT complet, les fichiers directement pointés par les erreurs et un contexte borné de manifestes, verrous et registres utiles ;
- exclut les secrets et états d'authentification et limite la taille totale du contexte ;
- garantit qu'une panne de génération du diagnostic ne masque jamais le blocage original ;
- ajoute des régressions sur un rapport de sept erreurs et sur l'échec best-effort du diagnostic ;
- conserve la norme 1.2.87 et le validateur 0.4.101.

## 2.16.34 — 19 août 2026 — persistance des diagnostics à travers le rollback de review-import

- corrige le cas où `_run_validator` créait bien `outgoing/<debate>_<rapport>_diagnostic.zip`, puis où le rollback transactionnel de `review-import` supprimait ce nouveau fichier avec les autres sorties mécaniques ;
- préserve uniquement les ZIP de diagnostic complets qui contiennent `DIAGNOSTIC_PACKAGE.json`, portent le schéma `wikidebia-workflow-diagnostic-package-1.0` et déclarent au moins une erreur ;
- continue de supprimer les paquets de revue partiels, fichiers ordinaires et faux ZIP de diagnostic créés pendant une transaction échouée ;
- ajoute des régressions couvrant la survie d’un diagnostic réel et la suppression d’un faux diagnostic ;
- conserve la norme 1.2.87 et le validateur 0.4.101.

## 2.16.35 — 19 août 2026 — isolation de la copie runtime du validateur

- exécute `_run_validator` depuis le composant `validator/` avec un `PYTHONPATH` limité à `validator/src` ;
- désactive le user-site Python, neutralise `PYTHONHOME` et empêche une copie ancienne de `wikidebia_validator` située à la racine du projet ou dans l’environnement hérité de masquer la release installée ;
- ajoute une régression hostile où une fausse copie top-level du validateur retourne volontairement une erreur mais ne doit jamais être importée ;
- vérifie sur les fichiers exacts du diagnostic du vote électronique que le validateur 0.4.101 courant produit zéro `WDV-EDT-013/014/015/020` pour les résumés historiques scellés ;
- conserve les diagnostics complets et leur persistance transactionnelle de 2.16.33/2.16.34 ; aucune règle éditoriale ni aucun contenu de corpus n’est modifié.

## 2.16.36 — 19 août 2026 — entrypoint physique et attestation runtime du validateur

- remplace les invocations orchestrées `python -m wikidebia_validator.cli` par le lanceur physique `validator/scripts/wikidebia_validate.py` exécuté avec `python -I` ;
- le lanceur insère explicitement `validator/src` après l’initialisation Python et refuse `cli.py` ou `editorial.py` chargés hors de ce composant ;
- les rapports portent `metrics.runtime_attestation` avec les SHA-256 de `cli.py` et `editorial.py`, et le kit recalcule ces empreintes avant d’accepter le rapport ;
- étend le même mode isolé aux validations d’initialisation, de revue de graphe et de promotion ;
- ajoute une régression avec copie hostile et `sitecustomize` injecteur ;
- vérifie sur le diagnostic exact du vote électronique que les quatre codes `WDV-EDT-013/014/015/020` disparaissent avec le runtime attesté ;
- conserve la norme 1.2.87 et le validateur 0.4.102.

## 2.16.37 — 19 août 2026 — provenance historique unifiée et attestation runtime étendue

- s’aligne sur le validateur 0.4.103, qui centralise la provenance des résumés historiques entre `wikicode` et `editorial` ;
- étend l’attestation runtime aux SHA-256 de `wikicode.py` et `historical_summary.py` ;
- refuse tout rapport dont l’une des quatre empreintes critiques diverge de la copie installée ;
- conserve le diagnostic complet automatique et sa persistance à travers le rollback ;
- ne modifie aucun contenu, aucune traduction, aucun verrou ni aucune règle éditoriale du corpus ;
- conserve la norme 1.2.87.

## 2.16.38 — 20 août 2026 — résolution du dernier état publié par langue

- corrige `./wikidebia update` lors de la première publication bilingue après les checkpoints français : l’absence normale de `.state/published/<débat>/en/latest.json` ne fait plus ignorer le reçu français valide ;
- résout la provenance du dernier état langue par langue, selon la priorité reçu publié → ancien manifeste installé → inventaire distant explicitement rattaché ;
- reconnaît `corpus/<debate_id>/manifest.json` comme ancien manifeste installé lorsque le nouveau corpus provient d’un ZIP stagé sous `.state/update-staging` ;
- accepte une baseline anglaise vide depuis cet ancien manifeste uniquement lorsque `translation_status.en=deferred` l’atteste explicitement ; sans cette preuve, le blocage « Dernier état publié introuvable » est conservé ;
- conserve le schéma de plan 1.0 et expose la composition exacte sous `state_source.resolution=per_language_attested_v1` / `per_language` ;
- n’écrit aucun faux `en/latest.json`, n’adopte aucune page distante inconnue et conserve les collisions, gardes de révision et protections contre les modifications humaines ;
- ajoute deux régressions reproduisant le cas FR publié + EN différé et le cas négatif sans preuve ;
- conserve la norme 1.2.87 et le validateur 0.4.103.

## 2.16.39 — 20 août 2026 — publication finale automatique du workflow

- fait suivre `release_ready` par une phase `final_publication` au lieu de terminer le workflow localement ;
- reprend directement les Work 2.16.37/2.16.38 déjà `release_ready`, sans refaire rendu, release ni convergence ;
- introduit une baseline finale scellée et liée au Work : dernier checkpoint FR signé + attestation EN `never_published_by_this_work`, sans déduction d’absence distante ;
- construit avant toute écriture un plan de sûreté bilingue, le plan exact de première publication EN et le plan FR d’ajout interlangue ;
- bloque avant la première écriture toute collision, modification humaine, création FR, mise à jour EN, move/redirect/delete ou delta FR autre que l’interlangue ;
- publie les pages EN avec la date réelle de création, le résumé source FR et `translated-fr`, puis les liens interlangues FR avec garde de révision ;
- conserve les plans et reçus pour une reprise idempotente après interruption et installe le `release-copy` seulement après succès ;
- permet à `update --archive` de réutiliser la même preuve Work-scoped lorsqu’elle est disponible, tout en conservant le fallback sûr 2.16.38 pour les anciens corpus.

## 2.16.40 — 20 août 2026 — réconciliation des preuves du render preflight

- normalise, au rendu final, les seuls champs `multiword_exception*` contradictoires avec une attestation historique déjà `atomic_concept=true` / `compositional_intersection=false`, sans changer les mots-clés ;
- localise la même normalisation en anglais et retire l’exception devenue inutile pour une forme compacte telle que `working-time reduction` ;
- propage dans `introduction_review.json` la provenance historique autoritative de l’introduction française sans sélectionner une ancienne proposition de réécriture ;
- transforme l’attestation globale de ponctuation d’une traduction historique en exception précise uniquement pour une note longue, sans URL et composée de plusieurs phrases explicatives ;
- conserve le corpus sémantique, les deux convergences, les verrous et les capacités de publication finale 2.16.39 ;
- ajoute des régressions empêchant toute normalisation automatique d’un concept nouveau non revu ;
- s’aligne sur le validateur 0.4.104 et conserve la norme 1.2.87.

## 2.16.41 — 20 août 2026 — réconciliation de la référence du checkpoint français final

- corrige la reprise de `final_publication` lorsque `workflow.json` conserve une ancienne empreinte de reçu du checkpoint français de contenu après une restauration transactionnelle locale ;
- autorise la réparation uniquement avant toute autorisation/écriture de publication finale, sans état anglais signé, lorsque l'ancien workflow et le reçu courant appartiennent au même débat/Work/stage, sont tous deux publiés et portent exactement le même `plan_sha256` ;
- exige en plus que `.state/published/<débat>/fr/latest.json` atteste ce même plan signé avant de remplacer la référence périmée ;
- toute divergence de plan, tout état anglais existant ou tout début de publication finale reste bloquant ;
- enregistre la migration dans `workflow.compatibility_migrations` avec anciennes/nouvelles empreintes et preuve utilisée ;
- conserve intégralement le corpus, les deux convergences sémantiques, la release et le correctif de render preflight 2.16.40 ; norme 1.2.87 et validateur 0.4.104 inchangés.


## 2.16.42 — 20 août 2026 — adoption sûre des checkpoints historiques non liés

- étend la réconciliation 2.16.41 aux anciens `workflow.json` qui attestent le checkpoint français final mais ne portent encore ni `receipt_sha256` ni `plan_sha256` ;
- adopte le reçu courant uniquement s’il est auto-signé, appartient au même débat/Work/stage, est publié, et si l’état français signé courant atteste exactement son `plan_sha256` ;
- accepte le statut historique `no_changes` comme provenance d’un checkpoint achevé avant de le normaliser vers le reçu courant ;
- refuse toujours un ancien hash de reçu déjà lié mais dépourvu de plan vérifiable, toute divergence du plan signé, tout état anglais existant et tout début de publication finale ;
- trace l’adoption sous `legacy_unbound_fr_content_receipt_reference_adopted` sans modifier le corpus, les convergences ni les reçus ;
- conserve la norme 1.2.87 et le validateur 0.4.104.

## 2.16.43 — 20 août 2026 — statut historique non canonique du checkpoint final

- complète 2.16.42 pour les Work historiques dont `french_content_publication` n'est lié à aucun `receipt_sha256` ni `plan_sha256`, mais conserve un ancien statut d'orchestration non canonique ;
- autorise la normalisation de ce statut uniquement lorsque le workflow est déjà en `final_publication`, sans revue pendante, sans publication finale commencée et sans état anglais signé ;
- exige toujours que le reçu courant soit auto-signé, appartienne au même débat/Work/stage et que son `plan_sha256` soit exactement attesté par l'état français signé ;
- refuse toute normalisation si le workflow est déjà lié à un ancien reçu ou plan, afin qu'un statut contradictoire reste bloquant dans ce cas ;
- trace l'ancien statut et la réconciliation dans `compatibility_migrations` ;
- conserve la norme 1.2.87 et le validateur 0.4.104.

## 2.16.44 — 20 août 2026 — empreinte du validateur dans la publication finale

- ajoute `validator.fingerprint_path` à la configuration commune de publication finale utilisée par le plan anglais `GenericPublisher` ;
- aligne également `max_warnings=0` sur les autres chemins de publication ;
- corrige le `KeyError('fingerprint_path')` observé après les connexions de préflight et avant toute autorisation/écriture distante ;
- ajoute une régression qui construit la configuration anglaise finale puis calcule réellement les empreintes du paquet avec `GenericPublisher._package_fingerprints()` ;
- ne modifie ni le corpus, ni les deux convergences, ni le checkpoint français, ni la norme 1.2.87, ni le validateur 0.4.104.
## 2.16.45 — 21 août 2026 — changement de jour pendant la publication finale anglaise

- conserve la date réelle des pages anglaises déjà créées avant minuit et ne les redatte jamais ;
- lorsqu'une publication partielle traverse minuit, reconstruit un plan anglais successeur où les créations déjà prouvées deviennent des `skip` et où les seules pages encore absentes reçoivent le nouveau jour civil ;
- vérifie que le delta du contenu planifié des pages restantes porte exclusivement sur `creation-date`, sans changement de titre, résumé, balise, source ou contenu éditorial ;
- rescellle le préflight et l'autorisation avant reprise, tout en archivant l'ancien plan, l'ancien préflight et l'ancienne autorisation dans un audit de rollover auto-signé ;
- restaure l'état local précédent si la reconstruction ou le nouveau préflight échoue, sans écriture distante supplémentaire ;
- reprend automatiquement le même mécanisme si le changement de jour est détecté pendant l'exécution elle-même ;
- conserve la norme 1.2.87 et le validateur 0.4.104.

## 2.16.46 — 21 août 2026 — Debate avant Arguments à la publication finale

- applique la décision propriétaire et la norme 1.2.88 : la page anglaise `Debate` est ordonnée avant toute création `Argument` ;
- supprime le réordonnancement final contradictoire introduit en 2.16.39 ;
- pour un plan déjà autorisé et partiellement exécuté sous l’ancien ordre, reconstruit un plan successeur depuis l’état distant, conserve les créations déjà prouvées comme `skip` et place `Debate` avant les créations restantes ;
- rescellle préflight et autorisation et archive l’ancien état de planification, sans supprimer ni recréer une page déjà publiée ;
- conserve intégralement le rollover de date 2.16.45.

## 2.16.47 — 21 août 2026 — reprise des plans signés après mise à niveau

- corrige `Plan divergent : kit_version` lors de la reprise d’une publication distante déjà commencée avec un plan signé par une version antérieure du kit ;
- traite `kit_version` et `required_validator_version` du plan comme provenance du producteur, conformément au contrat version-agnostique déjà déclaré par `RemoteUpdatePlanner` et la norme active ;
- conserve intégralement les contrôles bloquants sur `plan_version`, l’empreinte SHA-256 du plan, le `debate_id`, l’empreinte du manifeste et l’empreinte exacte de la configuration ;
- conserve les gardes de révision/contenu immédiatement avant chaque mutation distante ;
- ajoute des régressions positives de reprise inter-version et négatives sur divergence de manifeste/configuration ;
- conserve la norme 1.2.88 et le validateur 0.4.105.
