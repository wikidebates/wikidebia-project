## 24 novembre 2026 — retrait des paramètres de date de création de page

- `date-création` et `creation-date` ne font plus partie des quatre modèles ni des nouveaux artefacts de production ; les archives signées restent intactes.
- Les dates documentaires et les horodatages techniques sont conservés ; les plans de publication ne dépendent plus du passage à minuit.
- Une suppression distante exacte de ce paramètre est reconnue à partir d'une révision attestée, sans autoriser d'autres modifications concurrentes.

## 1.2.70 — alignement du validateur sur la première publication anglaise

- le chemin de validation source-authoritative n’exige plus `initialization` à partir de `initialisation` française ;
- une nouvelle traduction anglaise reste interdite si elle contient `initialization` ;
- `creation-date` anglaise n’est plus comparée à `date-création` française ; la date effective est imposée par le moteur de publication au jour civil de la création distante ;
- ajout de tests d’exécution dédiés à ces deux contrats, sans modification des règles éditoriales déjà actives.

## 1.2.69 — renommage des paramètres MediaWiki de cadrage et de frontière

- `sujet-complet` devient `sujet-développé` dans `{{Débat}}`.
- `complete-topic` devient `expanded-topic` dans `{{Debate}}`.
- `débat-détaillé` devient `débat-dédié` dans `{{Argument}}`.
- `detailed-debate` devient `dedicated-debate` dans `{{Argument}}` anglais.
- Les anciens noms restent des alias de lecture des formats antérieurs ; toute sortie courante est normalisée vers les nouveaux noms sans modifier les valeurs.
- Les structures, profils, workflows, validateur, rendu, publication, reprise distante, tests et exemples sont alignés sur ce contrat.

## 1.2.68 — 10 août 2026 — durcissement des preuves de convergence et de parsing

- ajoute `method_family` au reçu de convergence courant 1.1 et exige deux familles distinctes pour les deux dernières passes propres ;
- conserve la lecture des reçus historiques 1.0 ;
- ajoute un test négatif explicite `established-name=` → keyword ;
- étend le test de parsing multiligne au parseur de publication/prépublication ;
- ne modifie aucune règle éditoriale de 1.2.67.

## 1.2.67 — 10 août 2026 — corpus réel de régressions et changements idiomatiques revus

- autorise un changement de forme du `displayed-title` uniquement sous revue explicite de l’acte de langage, de la thèse et de la portée ;
- interdit toujours la dégradation d’une proposition source en fragment/non-proposition ;
- aligne le catalogue conceptuel des marqueurs sémantiques entre kit et validateur ;
- versionne un corpus de régressions dérivé des erreurs réelles documentées, avec couples mauvaise/correcte traduction ;
- exige des extraits de preuve source/cible pour chaque risque sémantique détecté ;
- étend les empreintes et preuves de risques aux champs de la page `Debate`.

## 1.2.66 — 10 août 2026 — équivalence propositionnelle et convergence sémantique

- impose la filiation directe `titre-affiché` → `displayed-title` ;
- exige un prédicat principal pour les titres affichés propositionnels ;
- renforce la revue différentielle des résumés et du métadiscours ;
- étend les signaux sémantiques à des erreurs réellement observées ;
- lie la revue à des empreintes et preuves de champ ;
- exige deux passes sémantiques indépendantes propres avant application ;
- propage le reçu de convergence jusqu'à la release et l'extraction fraîche ;
- ajoute des `concept_id` stables pour les nouveaux vocabulaires et des régressions multiligne.

## 1.2.65 — 10 août 2026 — cohérence des documents actifs

- corrige le guide actif de traduction pour employer `nom-consacré=` / `established-name=` dans les nouvelles recherches et sous-titres ;
- aligne les sections principales du workflow, du profil de rendu et du schéma sur `translation_status.en=deferred` et la reprise interlangue explicite ;
- remplace dans la checklist active l’ancienne interdiction de `citations` / `quotes` par le contrat courant de rendu des citations importées, revues et verrouillées ;
- ne modifie aucune exigence atomique ni aucun identifiant normatif.

# Changelog normatif Wikidéb’IA

## 1.2.64 — 10 août 2026 — correctif de preuve de release

- restaure `1.2.62` dans les listes de compatibilité du validateur et supprime la duplication accidentelle de `1.2.63` ;
- impose que les modules de tests critiques du kit soient exécutables isolément sans dépendre d’un `sys.path` modifié par un autre module ;
- ne modifie aucune règle éditoriale, aucun contrat de publication ni aucun historique antérieur.

## 1.2.63 — 10 août 2026 — correctif de réconciliation

- aligne toutes les règles actives sur `nom-consacré` / `established-name` ;
- aligne le contrat courant des citations sur `AI-translated quote` ;
- restaure dans les métadonnées de compatibilité et le manifeste du kit toutes les capacités de publication de la branche GitHub ;
- ajoute des tests de non-régression spécifiques à la fusion.

## 1.2.62 — 10 août 2026

- réconciliation des branches traduction/validation et publication GitHub ;
- conservation sans réécriture des deux historiques parallèles ;
- intégration des conventions de publication FR→EN, `translated-fr`, `nom-consacré` / `established-name`, `AI-translated quote`, `initialization` et `creation-date` ;
- maintien intégral des contrôles différentiels et sémantiques 1.2.61 ;
- renumérotation des deux exigences en collision : branche publication `TRN-009` → `TRN-019`, `RND-007` → `RND-009`.

## 1.2.61

- Cohérence obligatoire des schémas kit↔validateur et test croisé isolé.
- Archivage exact des normes consolidées remplacées.
- Correction des métadonnées de compatibilité.

# Changelog normatif

## 1.2.60
- tests de régression sémantique FR→EN issus des erreurs réelles ;
- format `name=` 1.2 avec identité exacte de portée ;
- attestation structurée sujet/prédicat/portée/modalité ;
- score de densité source-only et unités de revue 10/8/6/5.

## 1.2.59 — 9 août 2026

- formalise la provenance des recherches de noms consacrés avec le format de revue 1.1 ;
- exige une attestation humaine de complétude de chaque `Quote` et une seconde revue documentée en cas de ratio lexical faible ;
- ajoute un inventaire transactionnel de contenu de release recalculé après extraction fraîche pour empêcher les reçus et compteurs périmés.

## 1.2.58 — 9 août 2026

- ajout du registre global déterministe des identités documentaires DOI/URL/empreinte bibliographique, séparé des usages de `sources.json` ;
- détection des métadonnées incompatibles pour une même identité documentaire dans une même langue ;
- rapports de validation à quatre couches : `structural`, `documentary`, `semantic_review`, `fresh_archive` ;
- `fresh_archive` scellé uniquement dans la preuve externe post-ZIP ;
- moteur bilingue systématique de marqueurs sémantiques sur titres canoniques, titres affichés et résumés, en mode signal de revue non destructif.

## 1.2.57 — 9 août 2026

- étend l’inventaire sémantique différentiel aux titres canoniques des pages Argument ;
- impose une revue sémantique FR→EN explicite de la page Debate : titre, topic, complete-topic, affirmations de l’introduction et structure des sous-parties ;
- précise qu’un `passed` du validateur signifie réussite des contrôles automatisés et des attestations encodées, sans se substituer à la revue bilingue humaine ;
- conserve intégralement le principe 1.2.56 : aucune règle de création ne sert à rééditer rétroactivement le contenu français autoritatif.

## 1.2.56 — 9 août 2026

- validation FR→EN explicitement différentielle : conservation fidèle des formes source déjà validées et blocage des dégradations introduites par la traduction ;
- inventaire sémantique obligatoire des titres : sujet, prédicat, polarité, modalité, attribution, quantificateurs, degré, temporalité, conditions, connecteurs logiques et portée ;
- ratio de résumé confirmé comme signal de risque et non objectif de rédaction ; détection du métadiscours ajouté uniquement en anglais ;
- distinction explicite entre la majuscule de sous-titre de `name=` et la casse lexicale des keywords ;
- interdiction de fabriquer rétroactivement des requêtes de recherche historiques ;
- cohérence documentaire transversale par identité URL/DOI ;
- contrôle de complétude source→cible des `Quote` comme signal de revue ;
- validation finale obligatoire sur extraction neuve de l’archive exacte, avec SHA-256 enregistré ;
- distinction entre validation automatique et revue sémantique humaine.

## 1.2.55 — 2026-08-07

- unités internes de revue anglaise ramenées à 10 arguments par défaut, 5–8 pour les groupes denses, avec agrégation possible de plusieurs unités dans une livraison longue ;
- `name=` anglais : comparaison obligatoire des formes concurrentes, interdiction d'uniformiser `X argument` / `Argument from X` / possessifs, et exigence d'identité de portée ;
- principe explicite « contraintes, pas patron mécanique » pour Work et les agents ;
- conservation de l'absence historique de résumé dans la traduction et interdiction de créer un `summary=` de remplissage.

## 1.2.54 — 7 août 2026 — architecture cumulative des normes éditoriales

- supprime l’activation des règles éditoriales par listes ou comparaisons de versions ;
- conserve `consolidated_norm` pour le format, les migrations, la provenance et la traçabilité uniquement ;
- transforme les anciens `*_policy_revision` / `*_revision` en métadonnées de trace sans effet de sélection ;
- fait dépendre les contrôles de l’état fonctionnel réellement pertinent ;
- conserve des versions propres aux formats d’artefacts ;
- exige des tests d’invariance pour empêcher le retour de gardes éditoriales par version ;
- aligne également le cahier des charges, le workflow, les structures MediaWiki et le schéma de graphe afin qu’aucune formulation active ne réintroduise un seuil éditorial par version ;
- préserve sans modification toutes les règles de contenu 1.2.53.
- correctif de traduction FR→EN : la page anglaise cible existante est ignorée comme source éditoriale ;
- ajout d'une table exhaustive des valeurs `avancement`/`progress`, `avertissements-titre`/`title-warnings`, `avertissements-débat`/`debate-warnings` et `avertissements-argument`/`argument-warnings` ;
- les valeurs françaises présentes sont traduites exactement et l'absence d'un paramètre reste une absence, sans injection d'un défaut de création ;
- `related-debates` ne projette que les débats connexes français dont la page anglaise existe réellement ;
- ajout d'une seconde passe FR→EN obligatoire avant clôture de chaque lot.

## 1.2.53 — 7 août 2026

- traduction anglaise organisée en lots fermés : page Debate seule, puis 20 Arguments par défaut, maximum 25 et réduction à 10–15 pour les lots documentaires denses ;
- passe globale inter-lots obligatoire avant finalisation ;
- recherche de `name=` indépendante dans la littérature anglophone, sans traduction mécanique de `nom=` ;
- interdiction de traduire artificiellement les références françaises ; projection uniquement d'une version anglaise réelle et vérifiée avec ses métadonnées propres ;
- recherche indépendante de nouvelles références anglophones ;
- confirmation du contrat `Citation`→`Quote` : seules les valeurs `quote` et `date` sont traduites et `Quote translated by AI` est ajouté ;
- alignement recommandé : validateur 0.4.56 et kit 2.15.30.

## 1.2.52 — 7 août 2026

- recherche documentaire obligatoire d’une appellation consacrée pour chaque page Argument nouvelle ;
- présomption explicite d’absence : aucun quota et aucun objectif de remplissage de `nom` / `name` ;
- nom retenu uniquement lorsqu’il est attesté dans la littérature pour le même raisonnement et dans une forme adaptée à la langue de la page ;
- registre de revue avec requêtes, résultat `none` / `known_name` et preuves documentaires ;
- nouveau contrôle `WDV-EDT-032` ;
- alignement recommandé : validateur 0.4.55 et kit 2.15.29.

## 1.2.51 — 7 août 2026

- maintien de la préservation stricte des `nom` / `name` historiques existants ;
- ajout d’un registre d’attribution éditoriale explicite pour les appellations consacrées ajoutées à des pages auparavant dépourvues de `nom` / `name` ;
- séparation obligatoire entre la provenance historique et la nouvelle décision éditoriale ;
- dérogation limitée au seul paramètre `nom` / `name` et aux seules pages listées ;
- alignement recommandé : validateur 0.4.54 et kit 2.15.28.

## 1.2.50 — 7 août 2026

- séparation normative entre création d’une page nouvelle et modification d’une page existante ;
- préservation de présence de tout paramètre top-level autorisé attesté sur une page existante ;
- préservation exacte par défaut des métadonnées historiques et avertissements ;
- interdiction d’appliquer rétroactivement les marqueurs IA aux pages préexistantes ;
- suppression uniquement sur décision explicite page/paramètre ou exception spécialisée ;
- même contrat pour les pages Débat et Argument, françaises et anglaises ;
- alignement recommandé : validateur 0.4.53 et kit 2.15.27.

## 1.2.49 — 7 août 2026

- préservation stricte de `nom` / `name` lorsqu’il existe sur une page Argument historique ;
- interdiction de le supprimer, modifier, normaliser ou remplacer lors d’un renommage ;
- interdiction symétrique d’inventer ce paramètre lorsqu’il était absent ;
- état de présence et valeur consignés dans les paramètres préservés et dans le verrou historique ;
- alignement recommandé : validateur 0.4.52 et kit 2.15.26.

## 1.2.48 — 7 août 2026
- prise en charge nominative des relations externes préservées dans une adoption distante, sans création de nœud local ;

- adoption contrôlée des pages créées ou modifiées manuellement après le dernier état publié signé ;
- attestation par identifiant de révision et/ou empreinte SHA-256 ;
- autorisation explicite et nominative des changements de paramètres de cycle de vie ;
- maintien du blocage si la page distante a changé depuis l’attestation ;
- interdiction maintenue de modifier directement l’état publié signé ;
- nouveau contrôle `WDV-RMT-007`.

## 1.2.47 — 6 août 2026

- préservation obligatoire de `débat-détaillé` / `detailed-debate` sur les pages historiques ;
- distinction entre arrêt du parcours du graphe et suppression du paramètre MediaWiki ;
- omission autorisée de `justifications` et `objections` aux frontières uniquement après attestation page par page ;
- verrouillage de la cible par comparaison avec l’inventaire source ;
- attestation obligatoire que le propriétaire a été informé de l’omission des relations locales ;
- alignement recommandé : validateur 0.4.50 et kit 2.15.24.

## 1.2.46 — 6 août 2026

- remplacement du contrôle limité aux groupes de notions voisines par une revue exhaustive de toutes les notions spécialisées de chaque sous-partie ;
- ajout de `specialized_term_inventory_reviewed` et `specialized_term_inventory` ;
- quatre traitements vérifiables : lien Wikipédia, explication intégrée, traitement antérieur et contexte suffisant ;
- correspondance obligatoire entre l’inventaire, les textes visibles et tous les liens Wikipédia réellement rendus ;
- inventaire non vide pour toute sous-partie déclarée technique ou spécialisée ;
- nouveau contrôle `WDV-EDT-029`.

## 1.2.45 — 6 août 2026

- cohérence locale obligatoire des liens Wikipédia explicatifs ;
- examen conjoint des notions spécialisées de même rang dans une énumération ou une comparaison ;
- traitement uniforme lorsque les articles existent et que le besoin explicatif est comparable ;
- justification notion par notion de toute asymétrie ;
- nouveau registre `wikipedia_link_groups` et contrôle `WDV-EDT-028`.

## 1.2.44 — 6 août 2026

- suppression du point final dans les simples notices placées à l’intérieur de `<ref>…</ref>` ;
- maintien du point uniquement lorsque le corps de la note constitue une phrase explicative complète ;
- ponctuation de la phrase principale placée après l’appel de note ;
- exceptions liées par SHA-256 et attestées dans la revue de l’introduction ;
- activation rétrocompatible par `inline_reference_punctuation_policy_revision=1.2.44`.

## 1.2.43 — 6 août 2026

- sous-partie `Enjeux du débat` obligatoire dans toute introduction française ;
- sous-partie `Stakes of the debate` obligatoire dans toute introduction anglaise ;
- au moins deux conséquences concrètes consignées dans la revue ;
- interdiction des listes génériques de domaines et de la reproduction du graphe argumentatif ;
- activation rétrocompatible par `introduction_policy_revision=1.2.43`.

## 1.2.42 — 6 août 2026

- classement neutre obligatoire des sources présentant plusieurs positions et interdiction des doublons entre orientations ;
- suppression des quotas documentaires par paramètre de débat ;
- auteur ou chaîne obligatoire pour toute référence YouTube lorsque l'attribution est visible ;
- introduction fondée sur la densité informative, sans rubrique générique de remplissage ;
- identité titre canonique / titre affiché admise sans plafond ;
- reformulation d'un titre affiché autorisée seulement avec amélioration réelle et équivalence sémantique attestée.

## 1.2.41 — 6 août 2026

- simplification des mots-clés contextuels des pages nouvelles ;
- conservation explicite des locutions conceptuelles autonomes, dont `croyance fondamentale` ;
- sélection automatique de l’unique ZIP de `incoming/` par `./wikidebia update` ;
- portée `all` utilisée par défaut ;
- identifiant exigé uniquement en cas d’ambiguïté.

## 1.2.40 — 6 août 2026

- conservation de l’absence historique d’un résumé lorsqu’elle est attestée par l’inventaire source ;
- ajout de `summary_provenance=historical_absent` ;
- interdiction maintenue des résumés absents sur les pages nouvelles ;
- revue spécifique `historical_absence_verified` et exclusion des contrôles stylistiques inapplicables.

## 1.2.39 — 6 août 2026

- interdiction de réécrire un champ historique lors d'une correction ciblée non autorisée ;
- restauration et préservation exacte de `initialisation` / `initialization` sur les pages importées ;
- ajout d'un verrou machine des résumés et paramètres historiques ;
- séparation des politiques d'atomicité des mots-clés, d'originalité des résumés et de capitalisation ;
- compatibilité conservée avec le profil combiné 1.2.38.

## 1.2.38 — 6 août 2026

- distinction explicite entre locution atomique et intersection compositionnelle de domaines ;
- obligation de décomposer `psychologie de la religion` ou `psychologie religieuse` en `psychologie` et `religion` ;
- maintien des catégories irréductibles telles que `argument d'autorité` ;
- ajout de l’attestation `compositional_intersection=false` dans le vocabulaire contrôlé ;
- contrôle symétrique des constructions françaises et anglaises ;
- schémas dédiés au vocabulaire de mots-clés et à la revue des résumés ;
- activation complète des barrières éditoriales sur les corpus migrant vers 1.2.38.

## 1.2.37 — 5 août 2026

- remplacement du critère purement quantitatif des mots-clés par une exigence de concept atomique ;
- blocage des mini-rubriques productives telles que `limites de la science`, `histoire des religions` et `construction des lois scientifiques` ;
- maintien des locutions lexicalisées telles que `lois de la nature`, avec exception multi-mots motivée ;
- blocage des résumés construits par charpente générique, métadiscours, copie de titres enfants ou répétition d’une même phrase dans quatre pages ou davantage ;
- attestation obligatoire d’originalité et d’un extrait formulant le mécanisme propre au nœud ;
- contrôle de la majuscule de `Dieu` lorsqu’il s’agit du nom propre.

## 1.2.36 — 5 août 2026

- politique `per_page_preserved` appliquée par défaut : les pages existantes conservent leur date historique sans exigence de date du corpus ou du jour ;
- réconciliation automatique et traçable des paramètres de cycle de vie protégés pour les pages distantes exactement attestées ;
- absence d’ajout rétroactif des avertissements IA aux pages historiques ;
- suppression d’une page historique non marquée autorisée seulement par migration explicite, état distant exact et absence d’autre propriétaire connu ;
- maintien de la traduction anglaise différée et de toutes les protections contre les modifications humaines.

## 1.2.35 — 5 août 2026

- le statut anglais `deferred` devient une déclaration opérationnelle rétrocompatible avec tous les corpus historiques 1.2.x pris en charge, sans migration de leur norme éditoriale ;
- ajout de `creation_date_policy=per_page_preserved` pour conserver les dates immuables page par page ;
- encadrement d'une exception propriétaire, exhaustive et file-backed pour des titres affichés hérités déjà verrouillés ;
- maintien du contrôle strict des corpus non différés, des liens existants et des portées anglaises.

## 1.2.34 — 5 août 2026

- ajout de `translation_status.en=deferred` pour une publication française autonome ;
- titres anglais, pages anglaises et liens interlangues non requis dans cet état ;
- blocage des portées anglaises tant que la traduction est différée ;
- maintien des contrôles stricts pour les titres verrouillés, liens existants et états `ready`/`published` ;
- ajout ultérieur des liens interlangues par reprise française sans modification de la date de création ;
- remplacement explicite des anciennes obligations de verrouillage et de lien immédiats.

## 1.2.33 — 5 août 2026

- sélection des références d’Argument fondée sur le développement de l’argument ; la couverture simultanée d’objections reste admise ;
- distinction explicite entre page nouvelle et page préexistante ;
- préservation exacte de l’avancement, des avertissements et des débats connexes sur les pages existantes ;
- ajout des valeurs IA et de `Débat construit` uniquement lors de la création ;
- instantané de paramètres protégés dans les manifestes de page et garde-fou du plan de mise à jour.

## 1.2.32 — 4 août 2026

- minuscule initiale obligatoire pour les mots-clés communs ;
- conservation justifiée de la graphie canonique des noms propres, dénominations officielles, marques, sigles et acronymes ;
- interdiction des doublons ne différant que par la casse ;
- contrôle symétrique des keywords anglais ;
- compatibilité des normes 1.2.31 et antérieures conservée.

## 1.2.31 — 4 août 2026

- classement des mots-clés par pertinence décroissante, du plus direct au moins direct ;
- interdiction de l’ordre chronologique ou alphabétique comme principe de classement ;
- conservation exacte du classement conceptuel dans les keywords anglais ;
- suppression de toute cible, limite et alerte numérique de profondeur ;
- `maximum_observed` maintenu comme métrique descriptive.

## 1.2.30 — 4 août 2026

- localisation complète du modèle anglais `{{Quote}}` et de tous ses paramètres ;
- correspondances canoniques `citation→quote`, `auteurs→authors`, `ouvrage→work`, `numéro→issue`, `localisation→location`, `édition→publisher`, `lieu→place`, `lien→link` et `avertissements-citation→warnings` ;
- traduction limitée aux valeurs de `quote` et de `date` ;
- blocage de tout paramètre français ou sans équivalent déclaré dans une page anglaise ;
- alignement recommandé : validateur 0.4.32 et kit 2.15.3.

## 1.2.29 — 4 août 2026

- restauration du nom anglais `{{Quote}}` dans `quotes=` ;
- conservation des noms français de paramètres verrouillés à l’intérieur du modèle anglais ;
- traduction limitée aux valeurs de `citation` et de `date` ;
- aucune suppression ni modification des fonctions introduites avant cette correction.

## 1.2.28 — 3 août 2026

- correction documentaire de 1.2.27 sans modification du graphe ni du protocole distant ;
- suppression de l’ancienne interdiction contradictoire des citations dans les documents spécialisés ;
- maintien de `{{Citation}}` dans `quotes=` avec les mêmes paramètres documentaires français ;
- revérification du rendu des citations lors de la migration.

## 1.2.27 — 3 août 2026

- rendu déterministe bilingue depuis les verrous ;
- lien interlangue direct obligatoire dans chaque page française ;
- traduction sélective des citations et avertissement canonique ;
- alignement recommandé : validateur 0.4.29 et kit 2.10.0.

## 1.2.26 — 2 août 2026

- remplacement de l’absence d’état pour un plan entièrement `skip` par une attestation signée `no_changes` après relecture distante complète, sans écriture MediaWiki ;
- sélection d’une archive uniquement avec `--archive`, sans repli implicite depuis un identifiant ou un ZIP unique ;
- nettoyage systématique des zones de staging sur toutes les sorties ;
- statut `no_changes_in_scope` lorsqu’aucune opération mutante n’appartient à la portée demandée ;
- conservation signée des pages `pending_delete` après `--no-delete`, afin de permettre une reprise sûre avec `--only-delete` ;
- ajout des exigences `GOV-009`, `PUB-041` à `PUB-044` et `VAL-034` ;
- alignement recommandé : validateur 0.4.28 et kit 2.2.13.

## 1.2.25 — 2 août 2026

- `manual_review` devient un blocage effectif de l’exécution, au même titre que `blocked` ;
- interdiction d’écrire un reçu de succès ou un état publié lorsqu’un plan reste non résolu ;
- statut `no_changes` et absence de faux reçu pour un plan composé uniquement de `skip` ;
- staging obligatoire des archives de reprise et garantie qu’un dry-run ne modifie jamais `corpus/` ;
- priorité au corpus installé pour `update IDENTIFIANT` et sélection explicite des archives par `--archive` ;
- exclusion des corpus de débat des archives génériques et du bundle de composants ;
- ajout des exigences `GOV-008`, `FIL-019`, `PUB-037` à `PUB-040` et `VAL-033` ;
- alignement recommandé : validateur 0.4.27 et kit 2.2.12.

## 1.2.24 — 2 août 2026

- autorisation encadrée de `{{Lien Wikipédia}}` dans les introductions et résumés français ;
- équivalent anglais `{{Wikipedia link}}` ;
- paramètres localisés `texte-affiché` et `displayed-text`, omis pour une simple adaptation de casse initiale ;
- vérification de la page dans la langue correspondante, usage à la première occurrence utile et interdiction dans les notes de référence ;
- distinction explicite entre aide au survol et source documentaire ;
- ajout des exigences `ARG-035`, `DFR-047`, `DEN-008`, `MW-027`, `PRM-018` et `VAL-032` ;
- alignement recommandé : validateur 0.4.26 et kit 2.2.11.


## 1.2.23 — 2 août 2026

- minuscule initiale harmonisée pour `sujet-complet` et `complete-topic` ;
- préférence explicite pour un sujet nominal conventionnel ;
- règles auteur/site/page étendues aux pages Argument et à la vidéographie, avec seconde recherche obligatoire en cas d’égalité auteur-site ;
- résumé de modification distant simplifié en « Corrections » ;
- compatibilité du fichier unique de mise à niveau renforcée.

## 1.2.22 — 1er août 2026

- le titre affiché doit désormais remplir une fonction de lecture réellement distincte du titre canonique ;
- toute identité exacte devient exceptionnelle et doit être justifiée individuellement dans chaque langue ;
- le taux d'identité est plafonné à 10 % des arguments actifs par langue ;
- ajout des exigences `TTL-014` et `VAL-030` ;
- réactivation bloquante de `WDV-EDT-001` pour les corpus 1.2.22 ;
- conservation de `WDV-EDT-021` et `WDV-EDT-022` ;
- alignement recommandé : validateur 0.4.24 et kit 2.2.8.

## 1.2.21 — 1er août 2026

- correction de la collision de traçabilité qui réutilisait à tort `GR-045`, `GR-046` et `GR-047` ;
- attribution des identifiants non ambigus `GR-048`, `GR-049` et `GR-050` aux exigences de placement ;
- conservation intégrale des critères de niveau 1 et de subordination introduits en 1.2.20 ;
- aucun changement de graphe ni de contenu imposé aux corpus 1.2.20 ;
- alignement recommandé : validateur 0.4.23 et kit 2.2.7.


## 1.2.20 — 1er août 2026

- le niveau 1 est réservé aux réponses directes, autonomes et structurantes à la proposition du débat ;
- les objections ciblées, preuves secondaires, exemples, interprétations particulières, doctrines instanciées et précisions techniques sont subordonnés à leur meilleure cible immédiate ;
- ajout d’un registre de placement couvrant toutes les occurrences actives ;
- ajout des règles de placement et du contrôle `VAL-029` ; une collision d’identifiants de catalogue, corrigée en 1.2.21, subsistait dans cette livraison ;
- ajout du contrôle `WDV-EDT-022` dans le validateur 0.4.22 ;
- alignement recommandé : validateur 0.4.22 et kit 2.2.6.

## 1.2.19 — 1er août 2026

- le titre affiché devient obligatoirement une proposition argumentative complète et intelligible ;
- les simples groupes nominaux, thèmes et étiquettes doctrinales sont interdits ;
- le contexte d’affichage peut raccourcir le cadrage mais ne peut fournir un prédicat ou une conclusion absents ;
- la revue individuelle bilingue atteste la complétude de la proposition et l’intelligibilité de l’argument ;
- ajout des exigences `TTL-013` et `VAL-028` et du contrôle `WDV-EDT-021` ;
- alignement recommandé : validateur 0.4.21 et kit 2.2.5.

## Maintenance 1.2.18 — 1er août 2026

- correction du squelette anglais afin que `wikipedia-articles` ne soit jamais montré vide ;
- ajout d’un contrôle permanent de cohérence des exemples actifs ;
- alignement recommandé : validateur 0.4.20, kit 2.2.4.

## 1.2.18 — 1er août 2026

- séparateur canonique des auteurs : virgule suivie d’une espace ;
- refus du point-virgule, des virgules mal espacées et de la virgule pleine chasse dans les sorties générées ;
- compatibilité historique conservée pour les paquets déclarés sous 1.2.17 ;
- alignement avec le validateur 0.4.19 et le kit 2.2.3.


## 1.2.17 — 1er août 2026

- `articles-Wikipédia` et `wikipedia-articles` deviennent obligatoires et non vides, avec au moins un titre exact vérifié ;
- `débats-connexes` et `related-debates` sont interdits dans les sorties générées ;
- les tableaux JSON d’auteurs sont convertis en texte MediaWiki et leur sérialisation littérale est bloquée ;
- la publication ordinaire devient non interactive tout en conservant la vérification automatique de l’empreinte du plan ;
- alignement recommandé : validateur 0.4.18, kit 2.2.1.

## 1.2.16 — 31 juillet 2026

- distinction normative entre publication initiale et reprise ;
- état publié signé par débat et langue ;
- plan complet `create`, `skip`, `update`, `move`, `redirect`, `delete`, `manual_review`, `blocked` ;
- mises à jour protégées par révision/empreinte et contrôle de concurrence ;
- protection absolue des modifications humaines ;
- suppressions attestées, idempotentes et exécutées après vérification du nouveau graphe ;
- droits MediaWiki vérifiés avant écriture, sessions linguistiques séquentielles ;
- schémas, validation locale, reçus et commandes de reprise alignés sur le kit 2.2.0.

## 1.2.15 — 31 juillet 2026

- correction de la contrainte 1.2.13 qui imposait à tort l’égalité entre le nom du ZIP et `manifest.debate_id` ;
- sélection automatique d’un ZIP unique quel que soit son nom ;
- sélection exacte par nom de fichier lorsqu’il y a plusieurs ZIP ;
- `manifest.debate_id` déclaré comme identité autoritative du corpus ;
- compatibilité directe avec les anciennes archives portant des suffixes descriptifs ou une date.

## 1.2.14 — 31 juillet 2026

- correction de la contrainte 1.2.13 qui imposait l’égalité entre le nom du ZIP et `manifest.debate_id` ;
- nom du ZIP réduit au rôle de sélecteur de fichier ;
- `manifest.debate_id` maintenu comme identité autoritative du corpus ;
- compatibilité directe avec les archives historiques dont le nom comporte un suffixe descriptif.

## 1.2.13 — 30 juillet 2026

- dossier unique `incoming/` pour les archives de débats ;
- sélection automatique lorsqu’un seul ZIP est présent ;
- sélection obligatoire par identifiant lorsqu’il y en a plusieurs ;
- suppression de toute obligation de suffixe `release_ready` dans le nom du ZIP ;
- correspondance bloquante entre `<identifiant>.zip` et `manifest.debate_id`.

## 1.2.12 — 30 juillet 2026

- publication d’un paquet `release_ready` en une commande, avec cinq portées canoniques ;
- ordre Débat/Debate puis Argument imposé dans chaque langue ;
- mise à jour atomique en une commande, sauvegarde des versions précédentes et vidage de `updates/` ;
- dépôt Git/GitHub des seules sources nécessaires ;
- exclusion des secrets, corpus, archives, entrées, plans et journaux ;
- déplacement des fichiers Pywikibot dans `private/pywikibot/` ;
- interdiction de conserver le chemin absolu de l’installation dans les fichiers persistants ;
- alignement recommandé : validateur 0.4.12 et kit 2.1.12.

## 1.2.11 — 30 juillet 2026

- interdiction de tout saut de ligne ou espace entre deux modèles MediaWiki adjacents ;
- forme canonique obligatoire `}}{{` ;
- ajout de l’exigence automatique `MW-025` et du contrôle `WDV-MWK-018` ;
- préflight identique dans le kit 2.1.11 ;
- maintien intégral des règles 1.2.10.

## 1.2.10 — 30 juillet 2026

- suppression du modèle générique `Référence`/`Reference` dans les notes d’introduction ;
- rédaction directe du contenu documentaire dans `<ref>…</ref>` ;
- refus de tout modèle MediaWiki dans le corps d’une note développée d’introduction ;
- maintien des références nommées et de leur réutilisation autofermante ;
- maintien de toutes les autres règles 1.2.9.

## 1.2.9 — 30 juillet 2026

- dates documentaires complètes en langage naturel, dates de création inchangées au format machine ;
- modèle générique `Référence`/`Reference` obligatoire dans les appels inline des introductions ;
- au moins deux références dans chacun des neuf paramètres documentaires des pages Débat/Debate ;
- usage des acronymes courants dans `sujet-complet`/`complete-topic` ;
- publication des pages françaises autorisée avant la création des pages anglaises lorsque les titres anglais sont verrouillés dans le registre.

## 1.2.8 — 29 juillet 2026

- déclaration de toutes les étiquettes de provenance utilisées par les 320 exigences ;
- alignement des exemples actifs sur la révision 1.2.8 et correction de la langue de l’exemple anglais ;
- correction de la condition de schéma applicable aux paquets 1.2.7 et ultérieurs ;
- renforcement de l’auto-audit pour empêcher ces régressions ;
- aucune modification des exigences éditoriales 1.2.6.

## 1.2.7 — 29 juillet 2026

- correction de tous les alias et chemins de provenance absents ;
- signalement explicite des sources d’origine non distribuées séparément ;
- correction des chemins historiques vers la norme 1.1.9 ;
- nettoyage de la matrice de traçabilité ;
- alignement recommandé : validateur 0.4.7 et kit 2.1.7 ;
- aucune modification des règles éditoriales 1.2.6.

## 1.2.6 — 29 juillet 2026

- tri alphabétique obligatoire des rubriques françaises et sections anglaises, indépendamment dans chaque langue ;
- majuscule initiale obligatoire pour `sujet` et `topic` ;
- `sujet-complet` et `complete-topic` reformulés comme compléments non interrogatifs des en-têtes de page ;
- principe explicite « préférer la précision à l’exhaustivité » pour les rubriques des pages de débat ;
- richesse documentaire proportionnée à l’abondance de la littérature, avec revue séparée des trois familles documentaires sans quota universel ;
- force expressive des résumés rendue obligatoire et attestée par un extrait réel de chaque résumé ;
- alignement recommandé : validateur 0.4.6 et kit 2.1.6.

## 1.2.5 — 28 juillet 2026

- suppression de tout minimum global ou par sous-partie pour les appels `<ref>` des introductions ;
- clarification : les références inline sont exigées uniquement pour les affirmations factuelles qui nécessitent une attribution ;
- correction du validateur afin qu’une introduction conceptuelle sans affirmation factuelle externe puisse être conforme sans appel inline ;
- droit d’exécution restauré pour le lanceur de tests du validateur ;
- maintien de toutes les règles génériques et de l’interdiction des balises `<references />`.

## 1.2.4 — 28 juillet 2026

- remplacement de la checklist d’introduction issue d’un corpus pilote par une architecture fonctionnelle applicable à tous les débats ;
- définition obligatoire du sujet, du sens de la question, des repères historiques et actuels pertinents, des connaissances préalables et des enjeux ;
- suppression des minima universels de cinq sous-parties et vingt références ; les minima éventuels sont locaux et justifiés ;
- registre bilingue obligatoire de revue des introductions ;
- contextualisation obligatoire de toute sous-partie technique ;
- retrait des exemples, identifiants et configurations propres aux corpus pilotes dans les composants génériques actifs ;
- alignement recommandé : validateur 0.4.4 et kit 2.1.4.

## 1.2.3 — 28 juillet 2026

- remplacement du test sur sous-page utilisateur par un test direct de la page Débat française canonique ;
- création `createonly` de cette page comme première écriture distante ;
- blocage si la page Débat existe déjà au moment du plan ou de l’écriture ;
- reçu signé lié au titre canonique, au fichier local, au contenu et à la révision créée ;
- revérification de la révision courante avant toute autre page ;
- alignement recommandé : validateur 0.4.3 et kit 2.1.3.

## 1.2.2 — 28 juillet 2026

- intégration complète du workflow interlangue direct dans les documents actifs ;
- correction des squelettes et listes de contrôle qui conservaient encore l’ancien ajout tardif ;
- retrait des constantes propres à un corpus pilote de la norme générique ;
- manifestes SHA-256 exhaustifs et compteurs documentaires reproductibles ;
- portées `wikicode` et `editorial` obligatoires avant publication ;
- reçu de test utilisateur signé et revérifié à distance avant toute écriture canonique ;
- alignement recommandé : validateur 0.4.2 et kit 2.1.2.

## 1.2.1 — 28 juillet 2026

- reformulation de la règle des titres canoniques autour de l’autonomie référentielle, indépendamment de la nature du référent ;
- distinction explicite entre le nom de page autonome et le titre affiché pouvant exploiter son contexte immédiat ;
- emploi obligatoire des parenthèses pour les incises explicatives de la prose française, à la place des tirets cadratins appariés ;
- ajout des contrôles `WDV-EDT-016` révisé et `WDV-MWK-015`.

## 1.2.0 — 28 juillet 2026

- `{{Lien interlangue}}` devient le sous-modèle unique de toutes les pages françaises, débat compris ;
- les liens français sont intégrés dès la première génération, avant la création ultérieure des pages anglaises ;
- les titres anglais sont verrouillés avant la production française ;
- suppression de toute génération de `<references />` ;
- la page Debate anglaise utilise `topic` et `complete-topic` et interdit `type` ;
- les pages de débat utilisent exclusivement des sources dans leur langue ;
- les pages Argument préfèrent l’équivalent officiel dans leur langue ;
- la bibliographie de débat privilégie les ouvrages fondamentaux et synthèses larges ;
- les métadonnées sitographiques redondantes sont interdites et l’auteur peut être omis ;
- les titres canoniques doivent nommer explicitement leurs référents.

# Changelog normatif 1.1.9

- la première phrase doit développer le titre au lieu de le répéter ou de le paraphraser étroitement ;
- les exemples, ordres de grandeur et chiffres sont facultatifs et ne sont ajoutés que lorsqu’ils éclairent réellement le raisonnement ;
- toute donnée chiffrée fait l’objet d’une vérification documentaire humaine explicite ;
- un style ferme, imagé et légèrement mordant est admis, sans sarcasme, caricature, militantisme ni slogan mécanique ;
- le registre de revue bilingue atteste ces décisions page par page ;
- le validateur 0.3.1 ajoute `WDV-EDT-014` et `WDV-EDT-015`.

Toutes les exigences 1.1.8 restent actives sauf contradiction explicite ci-dessus.

## Historique 1.1.8

- style encyclopédique grand public obligatoire pour les résumés ;
- idée principale annoncée dès l'ouverture ;
- phrases de longueur variée et refus des enchaînements universitaires soporifiques ;
- définition immédiate des termes scientifiques ou techniques nécessaires ;
- revue page par page déclarée dans le manifeste ;
- heuristique non bloquante sur la longueur des phrases.

Toutes les exigences 1.1.7 restent actives sauf contradiction explicite ci-dessus.

## Historique 1.1.7

- remplacement des avertissements « généré avec IA / generated with AI » par « généré par IA / generated by AI » ;
- résumés de modification localisés ChatGPT 5.6 ;
- balise de modification obligatoire `chatgpt` ;
- vérification de la révision exacte après écriture, avec normalisation limitée des fins de ligne ;
- migration sûre des pages déjà créées depuis l’état W10.R7.

Toutes les exigences 1.1.6 restent actives sauf contradiction explicite ci-dessus.

## 1.2.71 — 10 août 2026 — architecture réellement version-agnostique

- sépare la norme opérationnelle active des snapshots historiques et du changelog ;
- rend les versions de release non normatives pour les règles éditoriales ;
- pilote la compatibilité par schémas/capacités et normalise les alias historiques à l’entrée ;
- centralise les versions courantes et rend les listes historiques compatibles dérivables ;
- consacre une archive canonique unique pour upgrade, audit, conservation et handoff, avec `WIKIDEBIA_SOURCE_ACTIVE.md` à la racine.

## 1.2.72 — 11 août 2026 — correctif d’exécution graph-extract

- aucune modification des règles éditoriales actives ;
- corrige l’alignement du chemin CLI `dedicated-debate` dans le kit ;
- confirme que `complete_topic` et `detailed_debate` restent des clés techniques internes stables et ne doivent pas être renommées globalement ;
- ajoute une régression d’intégration couvrant le trajet réel `argparse → main() → graph-extract`.

## 1.2.73 — 11 août 2026 — orchestration ergonomique des revues ChatGPT

- impose l’enchaînement automatique de toutes les étapes mécaniques jusqu’au prochain point éditorial ;
- introduit le paquet de revue `wikidebia-chatgpt-review-package-1.0`, séparant `editable/` et `context/` ;
- impose une provenance locale liée, l’intégrité SHA-256 du contexte, le refus des ZIP étrangers ou altérés et une restauration transactionnelle en cas d’échec ;
- ajoute les commandes utilisateur de haut niveau `workflow`, `review-import` et `workflow-status` tout en conservant toutes les primitives avancées ;
- généralise le mécanisme au graphe, aux métadonnées françaises, au contenu français, à la traduction anglaise et aux deux passes de convergence ;
- rouvre automatiquement la traduction lorsqu’une passe sémantique trouve une erreur certaine ;
- classe `outgoing/` parmi les zones locales privées exclues de Git ;
- conserve intégralement les garde-fous de validation, les verrous français, les empreintes, l’absence d’écriture distante et le contrat de publication W11.

## 1.2.74 — 11 août 2026 — validation pré-revue et diagnostic ergonomique

- différencie les anomalies éditoriales de titre, corrigeables lors de la revue des métadonnées, des incohérences structurelles réellement bloquantes ;
- avant le verrou de métadonnées de la langue concernée, `WDV-GRA-016` et `WDV-EDT-016` liés aux titres importés sont des avertissements, puis redeviennent bloquants après verrouillage ;
- impose à l’orchestrateur de produire un paquet de diagnostic minimal et d’afficher les erreurs concrètes lorsqu’une validation structurelle bloque réellement ;
- rend la reprise idempotente par simple relance de `workflow` après correction, sans manipulation des rapports sous `.state/`.

## 1.2.75 — 11 août 2026 — maintenance du code court d’orchestration

- aucune modification des règles éditoriales de fond ni des protections de publication ;
- impose que le `short_code` automatique du workflow soit dérivé de l’identifiant canonique ASCII du débat, et non du titre Unicode ;
- permet à un workflow initialisé mais incomplet de réparer automatiquement un `short_code` absent, ou d’accepter un `--short-code` explicite compatible sans reset manuel ;
- conserve un `short_code` déjà valide et refuse une tentative explicite contradictoire après initialisation.
## 1.2.76 — 11 août 2026 — boucle de correction après rejet du graphe

- rend explicitement non promouvable toute revue du graphe `rejected` ;
- impose une phase `graph_correction` avec paquet ChatGPT dédié et schéma stable `wikidebia-graph-correction-1.0` ;
- reconstruit mécaniquement relations, profondeurs, branches, rôles et compteurs après correction, avec validation et rollback transactionnel ;
- impose une nouvelle revue complète du graphe après chaque correction valide ;
- répète correction → revue autant de fois que nécessaire, sans création de Work, promotion ni écriture distante avant une approbation explicite.
## 1.2.77 — 11 août 2026 — décisions structurelles exécutables depuis une revue du graphe

- permet à une revue rejetée de porter des actions explicites `remove`, `merge_redirect`, `move` et `relation_change` ;
- retire le modèle de relation de la page mère avant tout retrait de l’enfant ;
- transforme par défaut les doublons supprimés du graphe en `#REDIRECTION [[page conservée]]` plutôt qu’en suppression distante ;
- exige des résumés MediaWiki individualisés, avec `[[page conservée]]` dans le résumé de la page mère lors d’un doublon ;
- impose validation locale prospective, préflight distant global, garde de révision avant chaque écriture et relecture du contenu/résumé/balise ;
- impose une nouvelle revue complète du graphe après application et interdit toute promotion implicite ;
- conserve une compatibilité étroite avec les ZIP 2.16.2/2.16.3 déjà revus lorsqu’ils contiennent la formulation propriétaire explicite attendue.

## 1.2.78 — 12 août 2026 — préservation différentielle des métadonnées préexistantes

- limite l’exigence de `titre-affiché` propositionnel aux titres nouvellement générés par Wikidéb’IA ;
- impose, pour une page préexistante importée du wiki, la conservation du `titre-affiché` historique même nominal ou contextuel, sauf faute, anomalie flagrante ou décision explicite du propriétaire ;
- maintient intégralement les exigences d’autonomie et de correction des titres canoniques / noms de pages ;
- réserve la cible de deux à quatre mots-clés aux pages nouvelles et interdit de supprimer un mot-clé historique pour satisfaire ce quota ;
- autorise la correction de casse/graphie, le réordonnancement et l’ajout de mots-clés sur les pages préexistantes ; une suppression exige une non-pertinence réelle explicitement justifiée ;
- exige que le kit et le validateur distinguent fonctionnellement `new` de `preexisting` au lieu d’appliquer rétroactivement le profil de création.

## 1.2.79 — 12 août 2026 — résumés individualisés des reprises de corpus

- remplace le résumé générique `Corrections` des nouveaux plans `update --archive` par un résumé MediaWiki calculé page par page à partir de la mutation réelle ;
- couvre les créations, mises à jour de contenu, renommages, redirections et suppressions ;
- conserve les conventions plus précises déjà existantes, notamment pour les ajouts interlangues ;
- impose que la politique et le résumé soient incorporés au plan signé, recalculés avant écriture et vérifiés après écriture ;
- conserve la lecture des anciens plans dépourvus du nouveau contrat, sans réémettre ce comportement dans les nouveaux plans ;
- précise que `review-import` reste local tant qu’aucune page MediaWiki finale n’est rendue ; les actions structurelles explicitement exécutées gardent leur voie distante séparée.


## 1.2.80 — 12 août 2026 — publication française au point de validation et réimport depuis incoming

- fait de la réussite de `fr_content_review` une frontière de publication : les pages françaises scellées sont rendues sans interlangue, préflightées et publiées avant toute préparation de la traduction anglaise ;
- réutilise le moteur de reprise signé et les résumés MediaWiki individualisés page par page, avec garde de révision, balise `chatgpt` et relecture post-écriture ;
- interdit la préparation du paquet anglais tant que le checkpoint français n’est pas publié ou attesté `no_changes` ;
- rend la reprise idempotente après interruption partielle et conserve le plan/reçu dès qu’une exécution distante a commencé ;
- simplifie l’UX : les ZIP de revue corrigés sont déposés dans `incoming/`, `./wikidebia review-import` sélectionne l’unique paquet valide et `./wikidebia review-import <debate_id>` ne devient nécessaire qu’en cas de pluralité ;
- sélectionne les paquets par le `debate_id` interne de `REVIEW_PACKAGE.json`, jamais par leur nom de fichier, et archive le ZIP seulement après succès ;
- impose la validation de `document_kind` directement dans `sources_working.json` avant application de la revue française.

## 1.2.81 — 12 août 2026 — deux checkpoints français avant traduction

- remplace le checkpoint unique de 1.2.80 par deux publications françaises successives ;
- la revue du graphe inclut dans un même paquet les positions/relations, décisions structurelles, titres canoniques et titres affichés ; son réimport approuvé déclenche immédiatement le premier checkpoint ;
- le premier checkpoint est construit depuis le wikicode importé et préserve strictement rubriques, mots-clés, résumés, introduction et documentation ;
- second checkpoint après la revue de contenu : rubriques, mots-clés, introduction, résumés, références et autres contenus ;
- le second plan se calcule contre l’état publié attesté par le premier et interdit move/redirect/delete ;
- les décisions structurelles de correction sont appliquées localement pendant la boucle de revue et ne sont publiées qu’au premier checkpoint ;
- la traduction anglaise reste interdite tant que les deux reçus français ne sont pas acquis.

## 1.2.83 — 12 août 2026 — préservation stricte des résumés et de l’introduction historiques

- corrige la régression observée lors d’une reprise de corpus existant où `fr_content_review` pouvait réécrire puis publier des résumés historiques et l’introduction historique ;
- rend ces champs en lecture seule dans la revue de contenu ordinaire pour toute page `preexisting` ;
- conserve exactement l’absence historique d’un résumé et interdit toute génération de remplissage ;
- réserve les règles de création/réécriture des résumés et introductions aux contenus nouveaux ou à une opération corrective distincte explicitement autorisée par le propriétaire ;
- exige un verrou d’empreintes des textes historiques et un contrôle du rendu avant publication ;
- précise que le second checkpoint français publie les autres deltas de contenu/classification mais possède un delta nul sur les résumés et l’introduction historiques dans une reprise ordinaire.

## 1.2.84 — 12 août 2026 — consentement explicite pour les textes historiques

- remplace l’immutabilité absolue de 1.2.83 par la séquence « préservation par défaut → suggestion → décision explicite du propriétaire → modification autorisée et traçable » ;
- permet d’autoriser pendant `fr_content_review` une correction ciblée ou une réécriture explicitement demandée de l’introduction ou d’un résumé historique, sans troisième checkpoint français ;
- conserve l’absence historique de résumé sauf création nominativement autorisée ;
- impose une preuve locale de consentement hors du ZIP éditable, liée au paquet exact, au champ et aux empreintes avant/après ;
- fait évoluer `fr_content_lock.json` vers `preserved` / `authorized_change` avec historique, final et preuve ;
- exige que la traduction anglaise parte de la version française finale effectivement autorisée ;
- normalise les anciennes revues supportées par schéma et récupère leurs deltas comme suggestions tant qu’ils ne sont pas explicitement autorisés.

## 1.2.85 — 12 août 2026 — valeur éditoriale sélectionnée et validation différentielle des textes historiques

- distingue explicitement la provenance historique de la valeur éditoriale effective : `preserved` sélectionne l’historique, `authorized_change` sélectionne la valeur finale autorisée ;
- impose que tous les contrôles structurels, le registre des sous-parties, le verrou, le changeset, le rendu, le checkpoint français n°2 et la traduction utilisent la valeur finale sélectionnée ;
- introduit une portée structurée des changements d’introduction (`added`, `modified`, `removed`, `reordered`) afin qu’une autorisation ciblée ne couvre aucune modification parasite ;
- applique les règles de création/réécriture différentiellement aux seules sous-parties ajoutées ou substantiellement modifiées, sans requalifier les sous-parties historiques inchangées ;
- conserve la compatibilité des autorisations 1.2.84/2.16.17 à portée de champ entier, liées à la valeur finale exacte ;
- confirme qu’un ajout explicitement autorisé de `Enjeux du débat` pendant `fr_content_review` est publié au checkpoint français n°2, sans troisième publication.

## 1.2.86 — 12 août 2026 — provenance éditoriale de la source et métadonnées historiques différentielles

- distingue `page_origin` de la page cible, `source_page_origin` de la source française autoritative et la provenance éventuelle du champ ;
- réserve quotas et préférences de génération aux contenus réellement créés par Wikidéb’IA ;
- conserve les contrôles intrinsèques de qualité sur les mots-clés historiques et autorise leur correction/décomposition tracée ;
- préserve par défaut l’ensemble des rubriques historiques sans plafond rétroactif, avec corrections explicitement justifiées ;
- transforme la domination historique d’un même jeu de keywords >25 % et le ratio de résumé historique hors 0,60–1,45 en signaux de revue plutôt qu’en objectifs de réécriture ;
- maintient l’adaptation autonome des introductions historiques au lectorat anglophone, y compris la localisation du contexte franco-français, sans relâcher les contrôles documentaires intrinsèques ;
- précise que les titres affichés historiques nominaux ou contextuels n’exigent ni proposition complète ni justification rétroactive de gain de lisibilité ;
- aligne le tri des rubriques sur l’ordre alphabétique français accent-insensible.

## 1.2.87 — 13 août 2026 — omission canonique des paramètres optionnels vides

- aligne le texte consolidé sur l’exigence atomique active : tout paramètre optionnel sans contenu pertinent est omis ;
- retire l’ancienne exception contradictoire imposant des buckets documentaires Débat présents mais vides ;
- la présence historique reste une provenance d’audit et ne commande plus le rendu ;
- le préflight doit autoriser l’omission canonique des paramètres éditoriaux optionnels validés sans autoriser les suppressions de paramètres protégés ou inconnus.

## 1.2.88 — 21 août 2026 — page Debate anglaise publiée avant les Arguments

- consacre la décision explicite du propriétaire : lors de la première publication anglaise finale, la page `Debate` est créée avant toute page `Argument` encore absente ;
- remplace la règle active contradictoire qui imposait `Argument` avant `Debate` dans cette phase ;
- conserve l’ordre des autres phases, les garde-fous de publication, les dates réelles de création et la reprise idempotente ;
- pour une publication déjà partiellement exécutée sous l’ancien ordre, les pages déjà créées ne sont jamais supprimées ni recréées ; un plan successeur audité place `Debate` avant toutes les créations `Argument` restantes.

## 1.2.89 — 27 novembre 2026 — citations publiées et unicité des citations

- Distingue traduction IA et passage anglais publié vérifié dans le contrat Citation→Quote, avec préférence pour l'édition publiée réutilisable.
- Lie la preuve au verrou et à l'occurrence ; maintient séparément les revues d'édition, de droits et de complétude, la convergence et l'autorisation de publication.
- Prépare les deux modalités documentaires à reçus communs ; interdit l'introduction de citations identiques entre pages distinctes et protège les preuves contre la mémoire générique.
- Migration coordonnée avec le kit 2.16.48 et le validateur 0.4.106 ; les archives antérieures restent immuables.

## 1.2.90 — 27 novembre 2026 — accessibilité des titres français au clavier

- Dissociation obligatoire des ligatures dans les noms de pages et titres affichés, y compris chaque libellé historique ; aucune translittération générale.
- Contrôle WDV-GRA-016 avant/après verrou et sur les relations rendues ; correction au premier checkpoint, sans modification des citations ni des textes hors titres.
- Validateur 0.4.107 et kit 2.16.49.
