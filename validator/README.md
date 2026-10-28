# Wikidéb’IA Validator 0.4.105

Correctif de validation des rubriques historiques : la limite de quatre ne bloque
plus les pages préexistantes ni leurs traductions. Avant la création des manifestes
de pages, la provenance d'import et les empreintes des fichiers sources sont
vérifiées. Les catégories autorisées, l'unicité et les limites des pages nouvelles
restent contrôlées.

Le validateur 0.4.105 s’aligne sur la norme 1.2.88 et le kit 2.16.47. Il conserve tous les contrôles 0.4.104 ; la modification porte sur le contrat de publication finale, où la page anglaise `Debate` doit précéder les créations `Argument`.

Norme active : 1.2.88. Kit associé : 2.16.47.

## Régénération des métadonnées du paquet

Après une modification du validateur et une exécution réussie de sa suite de
tests, régénérer les rapports, le manifeste et le reçu avec le nombre exact de
tests :

```bash
python validator/scripts/refresh_package_metadata.py --test-count N
python validator/scripts/self_audit.py
```

Le générateur exclut ses propres manifeste et reçu du calcul, met à jour les
deux rapports avant de calculer les empreintes et produit un résultat identique
pour des sources, une date et un nombre de tests identiques.

Il accepte en outre les deux formes légitimes de `documentation_family_notes` (trois familles agrégées ou neuf familles orientées), et la limite formelle de longueur d’un mot-clé ne s’applique plus lorsqu’une exception multi-mots valide du vocabulaire contrôlé atteste déjà le concept lexicalisé. Les contrôles restent stricts sur les contenus nouveaux, les introductions autorisées modifiées et les mots-clés sans attestation atomique.


Le validateur 0.4.103 supprime une divergence interne de provenance historique qui se manifestait uniquement lorsque plusieurs portées étaient exécutées dans le même processus. `wikicode.py` et `editorial.py` possédaient chacun leur propre fonction `_protected_historical_summary_keys` tout en partageant le même nom de cache sur `PackageContext`. Comme `wikicode` s’exécute avant `editorial`, sa version plus ancienne du calcul pouvait mettre en cache une liste incomplète qui reconnaissait `historical_existing` mais pas `historical_authorized_change`; la portée éditoriale réutilisait ensuite ce cache et requalifiait à tort les résumés autorisés comme créations nouvelles.

La provenance des résumés est désormais calculée dans un module unique `historical_summary.py`, utilisé par les deux portées. Le calcul reconnaît de façon identique `historical_existing`, `historical_authorized_change`, `historical_authorized_creation`, `historical_absent` et `owner_removed`, avec compatibilité pour les verrous historiques plus anciens. L’attestation runtime couvre aussi `wikicode.py` et `historical_summary.py`, en plus de `cli.py` et `editorial.py`.

La régression reproduit l’ordre réel `wikicode → editorial` et vérifie qu’un `historical_authorized_change` français et sa traduction anglaise restent hors du profil de création. Aucun contrôle n’est assoupli pour un résumé réellement nouveau.

Norme active : 1.2.87. Kit associé : 2.16.45.

## Notes héritées du validateur 0.4.101

Le validateur 0.4.101 rend le registre `summary_style_review.json` explicitement **non autoritatif pour les résumés historiques**. Dès qu’un résumé est identifié par les verrous FR/EN comme `historical_existing`, `historical_authorized_change`, `historical_authorized_creation`, `historical_absent` ou retiré par décision propriétaire, les attestations de création (style grand public, ouverture, force expressive, exemple/chiffre) ne sont ni exigées ni reconstruites à partir de ce registre. La fidélité, l’absence et les autorisations restent contrôlées par les verrous historiques et les contrôles dédiés, notamment `WDV-EDT-034`.

Un ancien registre peut donc conserver des lignes de provenance incomplètes, voire omettre les nœuds dont tous les résumés sont historiques, sans déclencher `WDV-EDT-013/014/015/020`. Les mêmes contrôles restent strictement applicables à chaque résumé réellement nouveau ou substantiellement réécrit hors profil historique. Norme active : 1.2.87. Kit associé : 2.16.35.

## Notes héritées du validateur 0.4.100

## Notes héritées du validateur 0.4.99

# Wikidéb’IA Validator 0.4.99

Le validateur 0.4.99 aligne le préflight final sur la provenance historique déjà prévue par la norme. En validation différentielle, un `titre-affiché` français préexistant n’est plus requalifié par une heuristique de proposition complète : sa forme source revue et l’absence de régression FR→EN font foi. Une forme source réellement propositionnelle reste protégée contre toute dégradation.

`WDV-DOC-005` ignore désormais les segments ISO qui appartiennent à une URL dans une note `<ref>`, tout en continuant de bloquer une date documentaire machine présente dans la prose de la note. Les contrôles de style des résumés restent stricts pour les contenus nouveaux ; les résumés historiques continuent d’être validés selon leur provenance et leur verrou. Norme active : 1.2.87. Kit associé : 2.16.32.

## État hérité de 0.4.98
Le validateur 0.4.98 corrige deux incompatibilités de préflight sans relâcher les contrôles. Le schéma du manifeste accepte désormais le mode déjà émis par le kit `historical_text_render_validation_mode=differential_preservation_v1`, avec cet unique enum. `WDV-MWK-024` recalcule désormais le ratio lexical des `Quote` avec exactement la même tokenisation que la revue de traduction : apostrophes françaises typographiques incluses dans les mots, mêmes suppressions de notes et de balisage simple. Une modification réelle du texte rendu reste bloquante.

Il conserve intégralement `WDV-MWK-023`, la réconciliation documentaire de 0.4.97 et tous les contrôles antérieurs. Norme active : 1.2.87. Kit associé : 2.16.31.

Le validateur 0.4.97 réconcilie les deux variantes 0.4.96 développées en parallèle. Il conserve la correction documentaire de `WDV-SRC-005` : pour une référence bibliographique de Debate, l’admissibilité repose sur `documentary_scope=foundational_work` ou `broad_synthesis` et une justification substantielle ; un `legal_text` large et justifié n’est pas rejeté pour son seul type.

Il conserve simultanément la validation différentielle du rendu historique. Lorsque le kit 2.16.29 déclare `historical_text_render_validation_mode=differential_preservation_v1`, les valeurs historiques attestées par les verrous (y compris une absence historique de résumé ou une syntaxe historique déjà scellée) ne sont pas requalifiées rétroactivement comme nouvelle génération. Cette compatibilité reste bornée au mode déclaré et ne relâche pas les contrôles sur les pages nouvelles ou les contenus non attestés. Norme active : 1.2.87.

# Wikidéb’IA Validator 0.4.95

Le validateur 0.4.95 corrige un faux positif d’autonomie référentielle dans les titres anglais : les extraposition impersonnelles comme `It is unfair for basic income to…` ne sont plus interprétées comme un pronom anaphorique. Un véritable `It` sans sujet explicite, par exemple `It reduces individual freedom` ou `It is harmful to democracy`, reste signalé.

Le contrôle `WDV-GRA-016` reconnaît aussi les principales apostrophes typographiques non ASCII (`’`, `‘`, `ʼ`, `＇`) comme non conformes dans les titres. La norme active reste 1.2.87 et exige l’apostrophe droite ASCII. Tous les contrôles 0.4.94 restent actifs.

## Wikidéb’IA Validator 0.4.94

Le validateur 0.4.94 corrige le contrat de compatibilité du registre documentaire pour les revues anglaises déjà préparées. `verification.primary_source` reste obligatoire comme clé canonique, mais peut valoir `null` lorsqu'un artefact historique ne contenait aucune décision sur ce point. Une nouvelle revue doit toujours fournir un booléen explicite.

Les clés historiques `checked_at`, `method` et `note` restent interdites dans `data/sources.json` : elles doivent être normalisées par le kit avant validation. Tous les contrôles 0.4.93 restent actifs et la norme demeure 1.2.87.

## Wikidéb’IA Validator 0.4.93

Le validateur 0.4.93 retire l’exception `present-empty` de 0.4.92. Conformément à la norme 1.2.87, `WDV-MWK-005` interdit toute valeur top-level vide dans une sortie canonique, y compris lorsqu’un paramètre était historiquement présent.

`source_parameter_presence` reste une provenance d’audit dans le verrou mais n’autorise plus `|paramètre=`. Un paramètre optionnel sans contenu doit être absent du wikicode.

Le validateur 0.4.91 s’aligne sur la norme 1.2.86 et le kit 2.16.20 pour les citations historiques comportant des sous-paramètres facultatifs vides. La provenance peut conserver ces lignes vides, mais la comparaison verrou↔wikicode les traite comme des paramètres omis dans le rendu canonique.

Les valeurs documentaires non vides restent comparées exactement, la traduction des noms de paramètres `Citation`→`Quote` reste obligatoire et aucune valeur manquante ne peut être inventée. Les contrôles précédents, notamment `WDV-MWK-021`, le consentement historique et la validation différentielle FR→EN, sont conservés.

# Wikidéb’IA Validator 0.4.90

Le validateur 0.4.90 s’aligne sur la norme 1.2.86 et le kit 2.16.19. Il distingue désormais explicitement le cycle de vie de la page cible anglaise de la provenance éditoriale de sa source française : une page EN techniquement nouvelle issue d’une page FR préexistante n’est pas soumise aux quotas ni aux préférences de création IA.

Les titres affichés historiques nominaux ou contextuels restent admissibles sans fausse attestation de proposition ou de référent explicite ; les mots-clés historiques échappent aux quotas mais restent soumis aux contrôles intrinsèques de qualité ; les ensembles historiques de rubriques ne sont pas rejetés pour leur seul nombre ; le ratio de résumé historique hors 0,60–1,45 devient un signal justifiable. L’introduction historique anglaise reste une adaptation autonome pouvant localiser le contexte franco-français, tout en conservant les contrôles documentaires et techniques intrinsèques.

Le contrôle des rubriques utilise en outre un véritable ordre alphabétique accent-insensible cohérent avec la norme française.

# Wikidéb’IA Validator 0.4.89

Le validateur 0.4.89 s’aligne sur la norme 1.2.85 et le kit 2.16.18. `WDV-EDT-034` conserve la distinction `preserved` / `authorized_change`, mais ajoute le contrat de consentement v3 : pour `authorized_change`, le texte français final autorisé est la valeur éditoriale effective et le verrou, le reçu local et le rendu doivent porter exactement le même `change_type` et la même `change_scope` structurée.

Une portée structurée d’introduction peut décrire les sous-parties `added`, `modified`, `removed` et un éventuel `reordered`. Une autorisation ciblée ne couvre donc aucune modification parasite. Les artefacts 2.16.17/v2 restent lisibles avec leur portée historique de champ entier. Les règles de création ne sont pas appliquées rétroactivement aux portions historiques inchangées.

# Wikidéb’IA Validator 0.4.88

Le validateur 0.4.88 s’aligne sur la norme 1.2.84 et le kit 2.16.17. `WDV-EDT-034` distingue désormais `preserved` de `authorized_change` : le premier exige l’identité avec l’empreinte historique ; le second exige un reçu de workflow propriétaire valide, l’empreinte historique, l’empreinte finale autorisée et l’identité du rendu avec cette valeur finale. Toute autorisation forgée dans le corpus, tout champ hors portée et toute création d’un résumé historiquement absent sans consentement nominatif restent bloquants.

La traduction différentielle utilise la version française finale autorisée et les contrôles de création ne sont pas appliqués rétroactivement à une correction historique locale. Tous les contrôles antérieurs sont conservés.

# Wikidéb’IA Validator 0.4.87

Le validateur 0.4.87 s’aligne sur la norme 1.2.83 et le kit 2.16.16. Il ajoute `WDV-EDT-034` pour protéger les textes français historiques pendant une reprise ordinaire : le verrou `fr_content_lock.json` porte l’empreinte de l’introduction historique et de chaque résumé historique, y compris l’état historiquement absent, et le rendu est bloqué si l’un de ces champs diverge.

Les attestations `historical_existing` / `historical_absent` ne sont plus soumises rétroactivement aux règles de création d’une nouvelle introduction ou d’un nouveau résumé. Pour la traduction anglaise d’un résumé français historique protégé, le statut `translated_historical_source` applique la validation différentielle sans prétendre que le texte source satisfaisait un profil de création. Les autres contrôles de 0.4.85 sont conservés.

# Wikidéb’IA Validator 0.4.85

Le validateur 0.4.85 s’aligne sur la norme 1.2.81 et le kit 2.16.14. Il conserve tous les contrôles de 0.4.84, notamment `WDV-RMT-008`. Les deux checkpoints français utilisent les mêmes schémas de corpus et de plan ; leur séparation fonctionnelle est imposée par l’orchestrateur et ses tests de non-régression.

# Wikidéb’IA Validator 0.4.84

Le validateur 0.4.84 s’aligne sur la norme 1.2.80 et le kit 2.16.13. Il conserve `WDV-RMT-008` pour les résumés MediaWiki individualisés et tous les contrôles antérieurs. Le checkpoint français intermédiaire est validé avec les portées structurelles/documentaires applicables avant la publication distante ; les attestations éditoriales françaises proviennent des verrous déjà scellés.

Le validateur 0.4.83 ajoute le contrôle `WDV-RMT-008` : lorsqu’un plan de reprise déclare le contrat `page_specific_v1`, chaque création, mise à jour, renommage, redirection ou suppression doit porter une politique et un résumé MediaWiki individualisés ; le résumé générique `Corrections` est refusé. Les plans historiques dépourvus de ce contrat restent lisibles.

Le validateur 0.4.82 corrige le contrôle `WDV-EDT-016` : les constructions impersonnelles françaises `Il faut…` et `Il ne faut…` ne constituent pas un référent contextuel. Un véritable pronom anaphorique initial reste bloquant.

Le validateur 0.4.81 distingue désormais les pages `new` des pages `preexisting` pour les règles de création relatives aux titres affichés et au nombre de mots-clés. Une page préexistante peut conserver un titre affiché nominal et un nombre historique de mots-clés ; les autres contrôles de qualité restent actifs.

# Wikidéb’IA Validator 0.4.80

Le validateur 0.4.80 s’aligne sur la norme 1.2.77 et le kit 2.16.8. Il conserve tous les contrôles existants et sert aussi à valider prospectivement le corpus reconstruit avant toute exécution distante d’une décision structurelle de revue.

## Notes héritées du paquet parent 0.4.73

Socle hérité de 0.4.73, ensuite complété par les révisions suivantes.

Elle conserve les contrôles différentiels et sémantiques de la lignée traduction 0.4.64 et intègre les contrôles de la lignée publication GitHub : `nom-consacré` / `established-name`, `AI-translated quote`, absence d'`initialization` sur une nouvelle traduction anglaise, cohérence normative et préservation historique des alias.

Les heuristiques sémantiques restent des signaux de revue humaine ; elles ne réécrivent jamais automatiquement le contenu. Les règles éditoriales actives restent cumulatives et ne sont pas conditionnées par le seul numéro de norme.

Le correctif 0.4.67 ne retire aucun contrôle de 0.4.66 ; il rétablit la continuité des révisions normatives compatibles et ajoute le test de non-régression correspondant.

Le correctif 0.4.69 aligne les diagnostics et la copie normative sur les documents actifs resynchronisés de 1.2.66.

Le correctif 0.4.70 accepte et contrôle les schémas sémantiques 1.4 / 1.3, les changements idiomatiques explicitement revus, le corpus réel de régressions et les preuves de champ scellées.

Le correctif 0.4.71 formalise les familles de méthodes de convergence 1.1 tout en conservant la lecture 1.0.

Le validateur 0.4.72 implémente le renommage des paramètres MediaWiki de la norme 1.2.69 avec compatibilité de lecture historique.

Le correctif 0.4.73 aligne l’exécution du validateur sur les règles déjà actives de première publication anglaise : pas de projection de `initialization` et aucune égalité imposée entre `creation-date` anglaise et `date-création` française.

## Architecture de compatibilité 2026-08-10

Les numéros de release sont une provenance. La compatibilité opérationnelle est pilotée par `CAPABILITIES.json` et les identifiants/version de schéma ; les égalités exactes sont réservées à l’installation, l’anti-downgrade, la reproductibilité et l’audit.
