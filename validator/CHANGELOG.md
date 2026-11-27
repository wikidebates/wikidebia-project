## 0.4.106 — 27 novembre 2026 — provenance et unicité des citations

- valide les preuves de passage publié indépendamment du kit ;
- contrôle les valeurs rendues et le reçu d'unicité lié aux verrous et à l'index ;
- conserve les contrats historiques et les revues de complétude.

## 0.4.73 — 10 août 2026 — alignement des métadonnées de première publication anglaise

- ne projette plus `initialisation` vers `initialization` dans le chemin `translated_english` d’une nouvelle page ;
- ne compare plus `creation-date` anglaise à `date-création` française ;
- conserve la préservation historique d’`initialization` et de `creation-date` sur les pages anglaises préexistantes ;
- ajoute des régressions d’exécution et restaure l’attribution historique exacte de 0.4.71/0.4.72.

## 0.4.72 — 10 août 2026 — renommage des paramètres MediaWiki

- valide `sujet-développé` / `expanded-topic` et `débat-dédié` / `dedicated-debate` comme paramètres courants ;
- conserve la lecture des anciens noms pour les paquets antérieurs à 1.2.69 ;
- refuse la coexistence des anciennes et nouvelles formes dans une sortie courante.

## 0.4.71 — 10 août 2026 — familles de convergence normalisées

- accepte les reçus de convergence 1.0 et 1.1 ;
- exige pour 1.1 deux `method_family` finales distinctes ;
- conserve tous les contrôles de 0.4.70.

## 0.4.70 — 10 août 2026 — revue idiomatique et corpus réel de régressions

- accepte la revue sémantique 1.4 et le moteur de marqueurs 1.3 ;
- distingue changement idiomatique revu et dégradation formelle ;
- étend les risques lexicaux et le corpus de fixtures réelles ;
- maintient la convergence obligatoire pour les revues 1.3 et 1.4.

## 0.4.69 — 10 août 2026 — équivalence propositionnelle et convergence sémantique

- contrôle le prédicat principal des displayed-title anglais ;
- étend les signaux différentiels et le métadiscours anglais ;
- valide les preuves de champ, les concept_id et le reçu de convergence ;
- ajoute les régressions multiligne et les codes WDV-BIL-008/009, WDV-EDT-033.

## 0.4.68 — 10 août 2026 — cohérence des documents actifs

- aligne la copie normative sur 1.2.65 ;
- corrige le diagnostic utilisateur qui appelait encore `name=` le champ MediaWiki anglais alors que `name` n’est plus qu’un champ interne de registre ;
- ajoute des tests empêchant le retour des contradictions actives sur l’interlangue différée et les Citation/Quote.

## 0.4.67 — 10 août 2026 — continuité de compatibilité

- restaure `1.2.62` dans `compatible_normative_revisions` et `supported_normative_revisions` ;
- supprime la duplication accidentelle de `1.2.63` ;
- aligne le validateur sur la norme 1.2.64 et le kit 2.15.48, sans changement de logique de validation éditoriale.

## 0.4.66 — 10 août 2026 — correctif de réconciliation

- aligne la copie normative sur 1.2.63 ;
- ajoute des tests garantissant la terminologie active `established-name` / `AI-translated quote` et la cohérence des contrats fusionnés.

## 0.4.65 — 10 août 2026 — réconciliation traduction + publication

- fusionne les deux variantes 0.4.64 développées en parallèle ;
- conserve la validation différentielle FR→EN, les signaux sémantiques structurés, les registres documentaires et les contrôles de scellement ;
- intègre `nom-consacré` / `established-name`, `AI-translated quote`, l'interdiction d'`initialization` sur les nouveaux Arguments EN et les contrôles de cohérence normative de la branche GitHub ;
- combine l'attestation humaine de proposition/intelligibilité avec le contrôle différentiel sans permettre à une attestation générique d'annuler une régression FR→EN ;
- aligne les schémas et la copie normative sur 1.2.62.

Les changelogs complets des deux branches 0.4.64 sont conservés sous `branch_history/`.

## 0.4.74 — 10 août 2026 — compatibilité pilotée par schémas et capacités

- ajoute un schéma explicite `wikidebia-validator-report-1.0` aux rapports ;
- centralise les versions courantes dans `VERSIONS.json` ;
- remplace les listes manuelles de révisions compatibles par une dérivation historique informative ;
- conserve les numéros de producteur comme provenance sans les utiliser comme feature flags.

## 0.4.75 — 11 août 2026 — maintenance d’alignement graph-extract

- aucune modification des règles de validation éditoriale ;
- aligne la release sur la norme 1.2.72 et le kit 2.15.56 ;
- conserve `complete_topic` et `detailed_debate` comme clés internes historiques ;
- la régression CLI est corrigée et testée dans le kit.


## 0.4.76 — 11 août 2026 — contrats d’orchestration éditoriale

- s’aligne sur la norme 1.2.73 et le kit 2.16.0 ;
- ajoute les schémas JSON des paquets ChatGPT, de l’état d’orchestration et des réponses de convergence ;
- déclare ces schémas dans `CAPABILITIES.json` ;
- conserve l’intégralité des contrôles éditoriaux, différentiels, documentaires et de publication précédents.

## 0.4.77 — 11 août 2026 — sévérité fonctionnelle des titres avant revue

- `WDV-GRA-016` et `WDV-EDT-016` relatifs aux titres importés sont des avertissements tant que le verrou de métadonnées de la langue concernée n’existe pas ;
- ces contrôles redeviennent bloquants dès présence de `data/fr_page_metadata_lock.json` ou `data/en_page_metadata_lock.json` ;
- les collisions, cycles, auto-relations, relations/occurrences invalides et autres incohérences structurelles restent bloquantes sans assouplissement ;
- ajoute des tests positif/négatif empêchant une nouvelle confusion entre signal éditorial pré-revue et erreur structurelle.

## 0.4.78 — 11 août 2026 — maintenance d’alignement short_code

- aucune modification des contrôles de validation ;
- aligne les métadonnées de release sur la norme 1.2.75 et le kit 2.16.2 ;
- conserve intégralement la sévérité fonctionnelle pré-revue introduite en 0.4.77.
## 0.4.79 — 11 août 2026 — schéma de correction du graphe

- ajoute et catalogue `graph_correction.schema.json` pour `wikidebia-graph-correction-1.0` ;
- déclare la capacité de lecture du document de correction utilisé après rejet d’une revue de graphe ;
- ne modifie aucun contrôle éditorial ou structurel existant du corpus.

## 0.4.80 — 11 août 2026 — alignement sur les actions structurelles de revue

- aligne la copie normative sur 1.2.77 et le kit recommandé sur 2.16.4 ;
- conserve tous les contrôles structurels et éditoriaux existants ;
- permet au kit de valider prospectivement le corpus reconstruit avant l’exécution distante des actions de graphe.

## 0.4.81 — 12 août 2026 — validation différentielle des métadonnées historiques

- aligne le validateur sur la norme 1.2.78 ;
- n’émet plus `WDV-EDT-021` pour le seul caractère non propositionnel d’un `displayed-title` appartenant à une page `preexisting` ;
- n’applique plus le contrôle de quantité 2–4 aux keywords d’une page Argument `preexisting` ;
- maintient les contrôles de forme flagrante, de vocabulaire, de capitalisation, de cohérence et tous les contrôles stricts pour les pages `new` ;
- ajoute des régressions positives/négatives sur `new` vs `preexisting`.

## 0.4.82 — 12 août 2026 — tournures impersonnelles françaises

- corrige `contextual_title_issues` afin que `Il ne faut…` ne soit plus interprété comme un pronom anaphorique ;
- conserve la détection des vrais référents contextuels initiaux ;
- ajoute un test positif pour `Il faut…` / `Il ne faut…` et un test négatif pour `Il réduit…` ;
- aucune modification de la norme éditoriale 1.2.78.

## 0.4.83 — 12 août 2026 — contrôle des résumés individualisés de reprise

- aligne le validateur sur la norme 1.2.79 et le kit 2.16.12 ;
- accepte le contrat additif `edit_summary_contract=page_specific_v1` dans les plans `wikidebia-remote-update-plan-1.0` ;
- ajoute `WDV-RMT-008` pour bloquer une mutation sans politique/résumé individualisés ou portant encore le résumé générique `Corrections` ;
- conserve la lecture des plans historiques dépourvus de ce contrat ;
- ne modifie aucun contrôle éditorial de contenu.

## 0.4.84 — 12 août 2026 — alignement checkpoint français 1.2.80

- aligne la copie normative sur la publication française automatique après `fr_content_review` ;
- conserve `WDV-RMT-008` et tous les contrôles de résumés individualisés ;
- reconnaît le checkpoint français comme corpus `translation_status.en=deferred` contrôlé avant reprise distante ;
- ne modifie aucun contrôle sémantique FR→EN ni aucune règle de traduction.

## 0.4.85 — 12 août 2026 — alignement sur les deux checkpoints français

- aligne la copie normative sur 1.2.81 et le kit recommandé sur 2.16.14 ;
- conserve `WDV-RMT-008` et tous les contrôles existants de plans/résumés individualisés ;
- reconnaît les checkpoints français graphe/titres et contenu/classification comme deux usages successifs du même contrat de corpus/plan ;
- aucune règle sémantique ou bilingue n’est assouplie.

## 0.4.87 — 12 août 2026 — verrouillage des textes historiques français

- s’aligne sur la norme 1.2.83 et le kit 2.16.16 ;
- ajoute `WDV-EDT-034` pour détecter toute divergence entre les empreintes historiques scellées et l’introduction/résumé rendu ;
- traite `historical_existing` et `historical_absent` comme états de préservation, sans imposer rétroactivement les règles de création ;
- couvre par tests la conservation exacte, la réécriture interdite du résumé, la réécriture interdite de l’introduction et l’acceptation d’une introduction historique ne satisfaisant pas les contraintes de nouvelle création.
- accepte `translated_historical_source` pour la traduction d’un résumé français historique protégé, sans appliquer les exigences de création à la source préexistante.

## 0.4.88 — 12 août 2026 — validation du consentement propriétaire historique

- aligne `WDV-EDT-034` sur `preserved` / `authorized_change` ;
- vérifie le reçu local de workflow, son scellement et sa portée exacte ;
- compare le rendu à l’empreinte historique pour `preserved` et à l’empreinte finale autorisée pour `authorized_change` ;
- refuse une fausse autorisation, un delta hors portée et une création historique absente non autorisée ;
- conserve la validation différentielle de la traduction à partir de la version française finale autorisée.

## 0.4.89 — 12 août 2026 — validation de la valeur sélectionnée et de la portée structurée

- aligne `WDV-EDT-034` sur le contrat de consentement v3 ;
- exige, pour un nouveau `authorized_change`, la concordance exacte de `change_type` et `change_scope` entre verrou, autorisation et reçu local ;
- vérifie que le rendu correspond à la valeur finale autorisée, l’historique restant la provenance ;
- conserve la lecture tolérante des reçus 2.16.17/v2 dépourvus de portée structurée ;
- ajoute une régression positive de portée structurée et une régression négative de divergence de portée ;
- conserve tous les contrôles de non-régression, de traduction différentielle et des deux checkpoints français.

## 0.4.90 — 12 août 2026 — provenance éditoriale de la source et validation historique différentielle

- distingue `page_origin` cible et provenance française autoritative pour les contrôles EN ;
- réserve quotas et préférences de création aux contenus effectivement générés ;
- conserve les contrôles intrinsèques de mots-clés historiques et la fidélité FR→EN ;
- rend non bloquants par provenance les jeux historiques de keywords >25 % et les ratios historiques explicitement revus ;
- accepte les titres affichés historiques nominaux/contextuels sans fausse attestation de référent explicite ;
- conserve les contrôles documentaires intrinsèques de l’introduction historique adaptée ;
- ajoute les régressions de provenance correspondantes.

## 0.4.91 — 12 août 2026 — validation des Citation/Quote à paramètres facultatifs vides

- aligne la comparaison des verrous de citations sur le profil canonique d’omission des sous-paramètres facultatifs vides ;
- conserve dans les verrous la provenance historique vide sans exiger son émission dans le wikicode final ;
- maintient la comparaison exacte des paramètres documentaires non vides et le mapping FR→EN des noms de paramètres ;
- ajoute une régression `Quote` où `work`, `issue`, `location`, `page`, `publisher` et `place` restent vides dans le verrou mais sont absents du wikicode rendu ;
- ne modifie aucune règle normative : la norme active reste 1.2.86.

## 0.4.92 — 13 août 2026 — paramètres top-level historiquement présents et vides

- corrige `WDV-MWK-005`, qui rejetait encore les paramètres top-level français que le kit 2.16.22+ préserve volontairement sous la forme `|paramètre=` ;
- exige simultanément `page_origin=preexisting`, la présence de `data/fr_content_lock.json` et `source_parameter_presence[paramètre].present=true` pour la page exacte ;
- conserve le blocage des paramètres vides historiquement absents, des pages nouvelles et des sous-paramètres non couverts ;
- ajoute des régressions positive/négative sur `|objections=` ;
- s’aligne sur le kit 2.16.23 ; la norme 1.2.86 reste inchangée.

## 0.4.93 — 13 août 2026 — omission canonique des valeurs vides

- retire l’exception 0.4.92 qui autorisait un paramètre top-level vide sur preuve de présence historique ;
- `WDV-MWK-005` interdit de nouveau toute valeur top-level vide dans le rendu canonique ;
- conserve `source_parameter_presence` comme provenance sans effet d’autorisation syntaxique ;
- s’aligne sur la norme 1.2.87 et le kit 2.16.24.

## 0.4.94 — 13 août 2026 — compatibilité des vérifications documentaires historiques

- accepte `verification.primary_source=null` dans `source_registry.schema.json` comme état explicite d'une ancienne revue qui n'avait pas enregistré cette classification ;
- conserve la clé `primary_source` requise et maintient le booléen comme forme normale des nouvelles revues ;
- n'autorise pas `checked_at`, `method` ni `note` dans le registre canonique final ;
- ajoute une régression de schéma couvrant la projection normalisée produite par le kit 2.16.25 ;
- la norme active reste 1.2.87.


## 0.4.95 — 18 août 2026 — extraposition anglaise et ponctuation des titres

- reconnaît `It is unfair for X to…` et les extraposition comparables comme tournures impersonnelles non anaphoriques ;
- maintient le blocage de `It` lorsqu’aucun sujet propositionnel explicite ne suit ;
- étend `WDV-GRA-016` aux principales apostrophes typographiques non ASCII dans les titres ;
- ajoute des régressions sur A0026/A0028 et sur l’apostrophe courbe ;
- conserve la norme active 1.2.87 et tous les contrôles 0.4.94.

## 0.4.96 — 19 août 2026 — portée documentaire des bibliographies de débat

- corrige `WDV-SRC-005`, qui transformait à tort la liste préférentielle de la section 7.6 en enum exhaustive de `document_kind` ;
- conserve les critères normatifs discriminants : `documentary_scope` doit être `foundational_work` ou `broad_synthesis` et la justification de sélection doit être substantielle ;
- accepte notamment un `legal_text` officiel de portée générale sans affaiblir les contrôles de langue, identité documentaire ou justification ;
- ajoute des régressions positive `legal_text/broad_synthesis` et négative `narrow_argument` ;
- s’aligne sur le kit 2.16.28 et conserve tous les contrôles 0.4.95.

## 0.4.97 — 19 août 2026 — réconciliation documentaire + validation différentielle historique

- réconcilie les deux variantes 0.4.96 sans supprimer aucun contrôle ;
- conserve l’alignement de `WDV-SRC-005` sur `foundational_work` / `broad_synthesis` et la justification substantielle ;
- conserve la validation différentielle des introductions/résumés historiques sous `differential_preservation_v1` ;
- maintient les contrôles stricts sur les pages nouvelles et les contenus non attestés ;
- s’aligne sur le kit 2.16.29 et la norme inchangée 1.2.87.
## 0.4.98 — 19 août 2026 — schéma du rendu historique et ratio lexical des Quote

- ajoute `editorial_controls.historical_text_render_validation_mode` au schéma courant avec l’unique valeur `differential_preservation_v1`, alignant le schéma sur le renderer et le contrôle historique déjà actifs ;
- aligne le recalcul `WDV-MWK-024` sur le tokenizer exact utilisé lors du scellement de `lexical_ratio`, notamment pour les apostrophes typographiques françaises ;
- conserve le blocage si le texte rendu diverge réellement du verrou ou si l’attestation de complétude manque ;
- ajoute des régressions sur le schéma, la tokenisation de A0005 et une modification réelle de Quote ;
- conserve la norme 1.2.87 et le kit 2.16.30.

## 0.4.99 — 19 août 2026 — validation différentielle des titres historiques et dates inline

- n’impose plus rétroactivement la proposition complète à la traduction d’un `titre-affiché` préexistant lorsque sa forme historique revue est nominale ou contextuelle ;
- conserve le blocage d’une dégradation d’une forme source propositionnelle vers une forme non propositionnelle ;
- ignore les motifs ISO appartenant à une URL lors de `WDV-DOC-005`, tout en bloquant les dates machine présentes dans la prose des notes ;
- conserve tous les contrôles de 0.4.98 et s’aligne sur le kit 2.16.32.

## 0.4.100 — 19 août 2026 — provenance historique autoritative des résumés

- lit `summary_provenance` directement dans `fr_content_lock.json` et `en_content_lock.json` au préflight final ;
- reconnaît `historical_existing`, `historical_authorized_change`, `historical_authorized_creation` et `historical_absent` sans dépendre d’un `translation_status` transitoire ;
- empêche `WDV-EDT-013`, `WDV-EDT-014`, `WDV-EDT-015` et `WDV-EDT-020` d’appliquer rétroactivement le profil de création à un résumé historique dûment verrouillé ;
- conserve ces quatre contrôles inchangés pour les résumés réellement nouveaux ;
- ajoute des régressions sur un résumé historique autorisé comportant des données chiffrées et sur une absence historique bilingue ;
- conserve la norme 1.2.87 et le kit 2.16.32.

## 0.4.101 — 19 août 2026 — registre de style non autoritatif pour les résumés historiques

- retire du registre `summary_style_review.json` toute autorité normative sur les résumés dont la provenance historique est déjà verrouillée ;
- n’exige plus, pour ces résumés, les attestations de création `general_public_style`, `opening_develops_title`, `conviction_visible`, `forceful_expression` ou `quantitative_claims_verified` ;
- autorise un registre historique ancien à conserver des lignes incomplètes ou à omettre les nœuds dont toutes les langues sont hors profil de création ;
- conserve la couverture et toutes les attestations de style pour chaque résumé réellement nouveau ;
- conserve `WDV-EDT-034` et les verrous FR/EN comme contrôles autoritatifs de présence, fidélité et consentement historique ;
- ajoute des régressions positives sur des résumés historiques avec chiffres et des registres anciens, ainsi qu’une régression négative prouvant qu’un résumé nouveau incomplet reste bloqué ;
- conserve la norme 1.2.87 et le kit 2.16.32.

## 0.4.102 — 19 août 2026 — attestation cryptographique de l’identité runtime

- le lanceur physique vérifie que `cli` et `editorial` sont chargés depuis `validator/src` ;
- calcule les SHA-256 effectifs de ces deux modules ;
- inscrit ces preuves dans `metrics.runtime_attestation` de chaque rapport lancé par cet entrypoint ;
- ne modifie aucun contrôle éditorial, documentaire, structurel ou bilingue ;
- ajoute une régression sur l’attestation du lanceur isolé ;
- conserve la norme 1.2.87 et s’aligne sur le kit 2.16.36.

## 0.4.103 — 19 août 2026 — provenance historique partagée entre wikicode et editorial

- centralise la classification des résumés historiques dans `historical_summary.py` ;
- supprime la collision de cache entre les anciens helpers indépendants de `wikicode.py` et `editorial.py` ;
- reconnaît uniformément `historical_existing`, `historical_authorized_change`, `historical_authorized_creation`, `historical_absent` et `owner_removed` ;
- reproduit et corrige le cas réel où `wikicode` cachait d’abord une liste incomplète puis faisait échouer `WDV-EDT-013/014/015/020` sur les cinq résumés autorisés du vote électronique ;
- étend l’attestation runtime aux SHA-256 de `wikicode.py` et `historical_summary.py` ;
- conserve tous les contrôles de création pour les résumés réellement nouveaux ;
- conserve la norme 1.2.87 et s’aligne sur le kit 2.16.37.

## 0.4.104 — 20 août 2026 — préflight différentiel des preuves historiques finales

- n’applique plus `WDV-MWK-015` à un résumé français historiquement préservé et exclut les paramètres de modèles inline du contrôle des incises de prose ;
- accepte `Subsection.warnings` en anglais uniquement lorsque l’introduction cible traduit une introduction française préexistante scellée sous `differential_preservation_v1` ;
- traite le verrou français comme source autoritative de provenance pour une introduction historique, sans réactiver une ancienne proposition de réécriture restée dans `introduction_review.json` ;
- accepte `documentation_family_notes` sous forme agrégée (3 familles) ou orientée (9 familles) lorsqu’elle est complète et substantielle ;
- permet un mot-clé de plus de quatre mots lorsque son entrée de vocabulaire possède déjà une attestation atomique/multi-mots valide, sans réduire les contrôles d’atomicité ;
- ajoute des régressions positives et négatives sur chacune de ces compatibilités ;
- conserve la norme 1.2.87 et s’aligne sur le kit 2.16.40.

## 0.4.105 — 21 août 2026 — alignement Debate avant Arguments

- s’aligne sur la norme 1.2.88 et le kit 2.16.47 ;
- conserve sans modification tous les contrôles structurels, éditoriaux, documentaires et historiques de 0.4.104 ;
- met à jour la copie normative active et les métadonnées de release pour le contrat de publication finale `Debate` avant `Argument`.

