# Guide de traduction anglaise contrôlée — Kit 2.16.32

Pour les noms de pages français et anglais, appliquer aussi la
[revue des titres canoniques](GUIDE_CANONICAL_TITLE_REVIEW.md) : une phrase par
nom, avec contrôle avant finalisation et publication. La fidélité à la source
ne dispense pas de cette revue ; les citations et résumés restent inchangés.

> Les règles ci-dessous sont cumulatives et ne dépendent pas d’un numéro `*_revision`. Cette architecture cumulative a été formalisée par la révision 1.2.54.

La traduction anglaise commence uniquement après le verrouillage complet des métadonnées et du contenu français. Elle travaille dans le même workspace éditorial et ne modifie ni le corpus promu, ni `working-copy/`, ni `reviewed-copy/`, ni `content-reviewed-copy/`.

Pour la reprise d'un import français publié à conserver intégralement, voir
[le gel de source pour traduction](GUIDE_TRANSLATION_SOURCE_PRESERVATION.md).
Ce gel n'est pas une nouvelle validation documentaire du contenu français.

## 0. Protocole de lots pour la traduction

La traduction est une adaptation idiomatique et documentaire, pas une substitution mot à mot. Elle est effectuée dans l'ordre suivant :

1. **Lot Debate** : la page `Debate` complète constitue un lot autonome, avec son introduction, ses titres, ses sections, ses keywords, ses liens Wikipédia anglais et toute sa documentation anglaise.
2. **Unités de revue Argument** : le kit calcule avant traduction un profil de densité depuis la source française immuable et recommande 10, 8, 6 ou 5 pages. Les facteurs observables sont consignés ; le score alloue l’effort de revue et n’évalue pas la qualité de l’argument. Une livraison Work peut agréger plusieurs unités closes ; ne pas fusionner leur revue.
3. Une page Argument est entièrement achevée dans le même lot : canonical title, displayed title, summary, sections, keywords, `established-name=` éventuel, citations et références.
4. Chaque lot est relu et clos avant le suivant. Il faut notamment vérifier le sens et l'orientation de chaque argument à partir du summary français, des citations, justifications et objections disponibles, afin d'éviter une inversion pour/contre.
5. Après le dernier lot, effectuer une passe globale inter-lots sur la terminologie, les titres, le vocabulaire bilingue, les `established-name=`, les références, les citations et la parité du graphe avant `--finalize`.

Ces tailles sont des bornes de qualité de travail, non des quotas de contenu. Un lot peut être réduit davantage si cela améliore la fiabilité de la recherche documentaire.

## 0.1 Règle source-authoritative et métadonnées FR→EN

Avant de constituer le corpus à traduire, `graph-extract` contrôle d'abord le
paramètre `interlangue` de la page Débat française. Si la page anglaise existe,
le workflow s'arrête avant la création du corpus. Il contrôle ensuite chaque
page Argument française. Une cible déclarée avec
`{{Lien interlangue|langue=en|page=…}}` devient une frontière : le lien est
conservé et le travail s'arrête à ce nœud, sans retraduire la page ni parcourir
ses relations locales. Le rapport d'extraction inventorie ces frontières et
leurs titres anglais.

Ces décisions sont consommées automatiquement par toute la chaîne : les
arguments marqués `reuse_existing` sont absents de la revue de traduction, du
verrou de contenu anglais, du rendu anglais et des lots de publication. Leur
page française conserve cependant son lien interlangue vers le titre anglais
canonique vérifié.

Pour les pages qui restent réellement à traduire, le corpus français validé est
la source éditoriale. Une autre page anglaise éventuellement trouvée pendant la
recherche ne sert pas de source pour le texte, les titres, le plan, `progress`,
les avertissements, les références ou les relations. Les contrôles techniques
distants nécessaires à une future publication restent séparés de cette règle.

Lorsqu’un résumé français est marqué `historical_existing` avec décision `preserved`, sa forme historique préservée reste autoritative même si elle ne satisfait pas les règles de rédaction d’un nouveau résumé. Avec `authorized_change`, la valeur française finale autorisée dans `fr_content_lock.json` devient au contraire la source autoritative de la traduction, sans que cette autorisation ne requalifie les autres textes historiques. La traduction anglaise doit rester fidèle à ce texte et les exigences de création ne doivent pas être utilisées pour l’allonger ou le réécrire silencieusement. Lorsqu’il est `historical_absent`, `summary=` reste absent en anglais.

Traduire les métadonnées réellement présentes, sans appliquer les valeurs de création par défaut :

- `avancement` : `Ébauche`→`Draft` ; `Débat en construction`→`Debate under construction` ; `Débat construit`→`Constructed debate` ;
- `avertissements-titre` du Débat : `Titre non standard`→`Non-standard title` ; `Titre à simplifier`→`Title to simplify` ; `Titre à expliciter`→`Title to be explained` ;
- `avertissements-débat` : `Débat sensible`→`Sensitive debate` ; `Débat saugrenu`→`Fanciful debate` ; `Débat redondant`→`Redundant debate` ; `Débat déséquilibré`→`Unbalanced debate` ; `Plan à améliorer`→`Plan to improve` ; `Débat généré par IA`→`Debate generated by AI` ;
- `avertissements-titre` de l'Argument : `Titre désavantageux`→`Disadvantageous title` ; `Titre peu clair`→`Unclear title` ; `Titre incomplet`→`Incomplete title` ; `Titre trop long`→`Too long title` ;
- `avertissements-argument` : `Argument sensible`→`Sensitive argument` ; `Argument saugrenu`→`Fanciful argument` ; `Argument potentiellement illégal`→`Potentially illegal argument` ; `Argument généré par IA`→`Argument generated by AI`.

Un paramètre absent en français reste absent en anglais. Une valeur non reconnue déclenche une revue ; elle n'est pas traduite par approximation. Pour un champ multiple, traduire chaque valeur présente dans le même ordre.

Pour `related-debates`, partir uniquement des débats connexes français et vérifier l'existence de chaque page anglaise correspondante. Ajouter seulement les cibles anglaises vérifiées comme existantes ; ne rien inventer et omettre le paramètre si aucune cible anglaise n'existe.

Avant de clore le lot, refaire une passe distincte de vérification FR→EN : métadonnées exactes, absence de défauts ajoutés, débats connexes vérifiés, sens et polarité conservés, anglais idiomatique, aucun wikicode français résiduel, références anglaises réelles et contrat `Citation`→`Quote` respecté.

## 1. Préparation

```bash
./wikidebia corpus-workspace-translation <debate_id> --work-id <work_id> --prepare
```

La commande exige un workspace au statut `fr_content_applied` et une préparation anglaise `ready_for_translation`. Elle produit :

- `reviews/en/translation_review.json` ;
- `data/sources_en_working.json` ;
- `audits/en_translation_inventory.json` ;
- `audits/en_translation_inventory.md`.

Le registre couvre la page Debate, chaque argument actif, le vocabulaire contrôlé français–anglais et les sources anglaises. Aucune traduction automatique n’est appliquée.

### Contraintes, pas patron mécanique

Les exemples, lots déjà validés et champs de revue sont des garde-fous. Ils ne doivent jamais servir de modèle lexical ou rhétorique à reproduire automatiquement. Chaque argument est interprété à partir de sa page française et des sources pertinentes.

### Résumé historiquement absent

Si le résumé français est absent et cette absence est attestée par la source verrouillée, laisser `summary` vide dans la fiche de travail. La finalisation conserve `summary=None`, omet le paramètre dans le rendu et n’exige ni ratio, ni expression de force, ni attestations stylistiques de résumé.

## 2. Revue à compléter

La page Debate reçoit un titre canonique, `topic`, `expanded-topic`, des sections, des keywords, une introduction structurée, des articles Wikipédia anglais vérifiés et une documentation classée selon sa contribution réelle, sans quota par paramètre. Une source couvrant les deux positions est placée dans la rubrique neutre.

Chaque argument reçoit un titre canonique et un displayed title idiomatiques, des sections exactement équivalentes aux rubriques françaises, des keywords issus du vocabulaire bilingue et une documentation anglaise adaptée. Lorsqu’un summary français existe, son équivalent anglais doit être substantiellement équivalent et son ratio de longueur anglais/français doit rester compris entre 0,60 et 1,45. Lorsqu’il est historiquement absent et attesté comme tel, aucun summary anglais n’est créé et aucun ratio n’est calculé. La traduction vérifie explicitement la polarité du raisonnement : le titre seul ne suffit pas lorsqu'il peut être ambigu ; le summary français lorsqu’il existe, les citations, justifications et objections disponibles servent à confirmer si l'argument soutient ou combat la thèse parente.

Les relations, occurrences, orientations et profondeurs sont linguistiquement neutres : elles ne peuvent pas être modifiées pendant cette phase.

### Références anglaises

Une référence française n'est **jamais traduite comme notice anglaise**. Pour chaque référence française pertinente, rechercher si une version anglaise réelle existe : édition ou traduction anglaise publiée, publication originale anglaise, version anglaise officielle d'une page ou d'un rapport, version audiovisuelle anglaise officielle, ou autre équivalent documentaire vérifiable.

Si cet équivalent existe, enregistrer et citer **la version anglaise elle-même**, avec son titre publié, son éditeur/diffuseur, sa date, son lien et ses autres métadonnées vérifiées. Ne jamais traduire librement le titre ou recopier les métadonnées françaises comme si elles appartenaient à une édition anglaise. Si aucune version anglaise n'existe, ne pas transférer cette référence au seul motif qu'elle existe en français.

Chaque page anglaise fait en outre l'objet d'une **recherche indépendante de nouvelles références anglophones**. La documentation anglaise doit refléter la littérature réellement disponible en anglais et peut donc différer de la sélection française tout en conservant une profondeur et une qualité comparables. Pour la page Debate, toutes les références doivent être réellement disponibles en anglais. Pour les pages Argument, la politique linguistique générale demeure symétrique à celle du français ; une éventuelle source non anglaise est sélectionnée indépendamment selon cette politique, jamais produite par traduction artificielle d'une notice française.

Pour toute source nouvellement enregistrée, `verification` utilise directement le format canonique du registre documentaire : `status`, `verified_at`, `primary_source`, `notes`, puis les attestations applicables (`language_verified`, `authorship_checked`, etc.). `primary_source` est une décision documentaire explicite et ne doit pas être inventé. Les anciens paquets déjà préparés qui utilisent `checked_at`, `method` et `note` restent lisibles ; au moment de la projection finale ces clés sont normalisées vers `verified_at` et `notes`, et l'absence historique de classification `primary_source` devient explicitement `null` au lieu d'être transformée arbitrairement en `true` ou `false`. Un nouveau paquet ne doit plus émettre ce format historique.

La finalisation anglaise contrôle désormais directement les métadonnées qui seront exigées dans le registre final, avant toute convergence sémantique. Toute bibliographie utilisée sur la page Debate renseigne `document_kind` et classe son usage comme `foundational_work` ou `broad_synthesis`; une source trop étroite est retirée de la bibliographie générale au lieu d'être requalifiée artificiellement. Pour les sources Web et vidéo, tout auteur conservé doit avoir `authorship_verified=true`. Une égalité auteur/site est revue explicitement : le nom du site n'est pas recopié comme auteur en l'absence d'une responsabilité distinctement créditée.

Pour compatibilité avec un Work déjà convergé sous une version plus ancienne, la garde pré-application inventorie toutes les lacunes documentaires en une seule fois et ouvre `en_documentation_correction`. Ce paquet rend uniquement `data/sources_en_working.json` éditable ; les textes et preuves sémantiques restent en lecture seule. Après correction, la revue est refinalisée et les deux passes sémantiques recommencent, car le reçu historique reste lié à l'ancienne empreinte complète de revue même si le `semantic_content_sha256` textuel n'a pas changé.

### Citations importées

Chaque modèle `{{Citation}}` français importé est inventorié avec un identifiant stable. La projection anglaise utilise `{{Quote}}` et traduit obligatoirement tous les noms de paramètres selon le contrat du wiki anglais : `citation→quote`, `auteurs→authors`, `ouvrage→work`, `numéro→issue`, `localisation→location`, `édition→publisher`, `lieu→place`, `lien→link` et `avertissements-citation→warnings`; les noms `article`, `volume`, `page` et `date` sont identiques dans les deux langues.

Seules les valeurs de `quote` et de `date` peuvent être traduites. Les valeurs de `authors`, `article`, `work`, `volume`, `issue`, `page`, `location`, `publisher`, `place` et `link` sont reprises exactement. `warnings` reçoit toujours `AI-translated quote`, après un avertissement préexistant avec le séparateur exact `, `. La date traduite doit désigner la même date ; une année seule reste inchangée. Un paramètre français sans équivalent anglais déclaré bloque la finalisation.

Les dates historiques françaises numériques (`15/06/2011`, `24.08.2018`, `11/2020`) et les mois abrégés (`17 nov. 2021`) sont comparés à la date anglaise à précision égale : une date au mois ne devient pas une date au jour. Une date source non reconnue ou impossible bloque la finalisation et demande une revue, au lieu de contourner silencieusement le contrôle. Une valeur numérique historique conservée strictement à l’identique reste admise.

## 3. Finalisation

Avant d’exécuter `--finalize`, la revue éditoriale du travail doit avoir contrôlé et consigné : la clôture de chaque lot ; l’existence d’un équivalent anglais réel pour toute référence française projetée ; la recherche indépendante de nouvelles références anglophones ; la recherche autonome de `established-name=` dans la littérature anglophone ; et la passe globale inter-lots. Ces opérations de recherche ne sont pas toutes déductibles automatiquement du wikicode final : elles restent des obligations éditoriales même lorsque le validateur ne peut en vérifier que les traces structurées disponibles.

```bash
./wikidebia corpus-workspace-translation <debate_id> --work-id <work_id> --finalize
```

La finalisation vérifie notamment :

- la couverture exacte de tous les arguments actifs ;
- l’unicité et l’autonomie des titres canoniques anglais ;
- le caractère propositionnel des displayed titles ;
- la possibilité de conserver le titre canonique comme displayed title lorsqu’il est déjà le plus clair ;
- pour tout displayed title distinct, l’équivalence sémantique et le gain réel de lisibilité ;
- la correspondance des sections avec les rubriques françaises ;
- la correspondance des keywords avec le vocabulaire contrôlé ;
- la limite de 25 % pour un même jeu exact de keywords ;
- l’équivalence substantielle des introductions et des summaries lorsqu’ils existent, ou la préservation attestée de leur absence historique ;
- la couverture exacte des citations françaises, la préservation de leurs paramètres, l’équivalence des dates et l’avertissement de traduction ;
- la langue et la vérification des sources anglaises ;
- l’absence de doublon documentaire entre orientations et l’attribution des vidéos YouTube ;
- la présence des attestations éditoriales requises ;
- l’absence de page finale et d’accès distant.

La revue et le registre documentaire anglais sont scellés par SHA-256.

### 3.1 Convergence sémantique obligatoire

Après la dernière correction et avant l’application, exécuter **deux passes sémantiques indépendantes** sur la revue finalisée. Elles doivent employer des méthodes distinctes, porter sur le même `semantic_content_sha256` et déclarer chacune `new_certain_errors=0`. Une passe qui trouve une erreur certaine invalide la chaîne précédente ; toute mutation ultérieure de la revue ou du contenu invalide le reçu.

Exemple :

```bash
./wikidebia corpus-workspace-semantic-convergence <debate_id> --work-id <work_id> \
  --method-family proposition_by_proposition \
  --method "comparaison proposition par proposition" --reviewer "Relecteur A" \
  --note "Comparaison indépendante du sujet, du prédicat, de la force, de la portée et des relations logiques."

./wikidebia corpus-workspace-semantic-convergence <debate_id> --work-id <work_id> \
  --method-family risk_marker_review \
  --method "relecture des marqueurs de risque et des propositions limites" --reviewer "Relecteur B" \
  --note "Relecture indépendante des risques, de l'ouverture, de la conclusion, des conditions et des ancrages concrets."
```

Le reçu courant 1.1 `reviews/en/semantic_convergence_review.json` doit atteindre `status=converged`. Il est ensuite lié au verrou de traduction, à l’inventaire transactionnel et au reçu de release. Les deux dernières passes propres déclarent également des `method_family` différentes parmi `proposition_by_proposition`, `risk_marker_review`, `reverse_source_target`, `field_boundary_review` et `independent_bilingual_reread`; changer seulement le libellé libre de `method` ne suffit pas à établir l’indépendance.

## 4. Application

```bash
./wikidebia corpus-workspace-translation <debate_id> --work-id <work_id> --apply --confirm-review-sha256 <empreinte>
```

L’application crée atomiquement `translated-copy/`. Cette copie contient notamment :

- `data/en_page_metadata_lock.json` ;
- `data/en_content_lock.json` ;
- `data/en_translation_lock.json` ;
- `data/keyword_vocabulary_bilingual.json` ;
- `changes/en_translation_changeset.json` ;
- les projections anglaises du registre maître ;
- les rapports de validation de la traduction.

Les verrous français et les imports de provenance doivent rester identiques octet par octet. Aucune page sous `output/` n’est créée.

## Ordre des keywords

La traduction conserve terme à terme l’ordre français de pertinence décroissante. Chaque entrée Debate et Argument atteste `keywords_order_preserved_by_relevance=true`.

## Sortie du mode différé

Une revue de traduction validée remplace `translation_status.en=deferred` par `ready`. Elle verrouille les titres anglais, prépare les pages anglaises et réactive les contrôles bilingues. Les liens français sont ajoutés ensuite par une reprise explicite ; ils ne sont jamais anticipés.



## Noms consacrés des arguments anglais

Un `established-name=` anglais n’est jamais obtenu par simple traduction d’un `nom-consacré=` français. Pour chaque page Argument anglaise nouvelle, la revue recherche séparément l’appellation réellement employée dans la littérature anglophone. Elle compare les variantes attestées et ne normalise pas leur construction (`X argument`, `Argument from X`, possessif, etc.). `same_reasoning_confirmed` signifie aussi **même portée** : un nom propre à une sous-variante, à un auteur ou à une étape du raisonnement ne convient pas à une page plus large. Le résultat par défaut reste l’absence de nom ; une valeur n’est verrouillée que si la littérature désigne exactement le raisonnement de la page sous cette appellation. L'existence d'un `nom-consacré=` français sert uniquement de piste pour les requêtes. Une traduction anglaise plausible mais non attestée ne doit jamais être inscrite dans `established-name=`.

## Révision 1.2.57 — validation différentielle FR→EN

En traduction, le français validé est la **source autoritative**. Les règles de forme de création ne sont pas réappliquées rétroactivement au contenu source. Une question, un impératif, un intitulé thématique, un groupe nominal ou une étiquette doctrinale déjà validés en français sont conservés sous une forme anglaise équivalente ; ils ne doivent pas être « réparés » silencieusement. En revanche, une proposition française ne peut devenir un fragment, une question, un impératif ou une simple étiquette en anglais.

Pour chaque `displayed-title`, la revue consigne la forme source et cible et vérifie explicitement : sujet, prédicat, polarité/négation, modalité, attribution, quantificateurs, degré/intensité, temporalité/fréquence, condition/restriction, causalité/concession/comparaison et portée du référent (notamment `a god`/`God`). Si un raccourcissement perd l'un de ces éléments, reprendre le titre canonique plutôt que forcer la concision.

Le **titre canonique** reçoit désormais son propre inventaire sémantique : sa fidélité ne peut pas être déduite de celle du `displayed-title`. Toute perte de conclusion, changement de sujet du prédicat, généralisation, restriction ou modification de modalité dans le canonique bloque la finalisation.

La page `Debate` est contrôlée de la même manière : titre canonique, `topic`, `expanded-topic`, affirmations et distinctions de l’introduction, faits historiques ou actuels, enjeux et fonction des sous-parties sont comparés à la source française. Remplacer une référence par une source anglophone réelle ne permet jamais de supprimer l’information qu’elle étayait.

Le ratio de longueur du résumé reste un **détecteur de risque**, jamais une cible rédactionnelle. Le summary anglais doit traduire tout le raisonnement français et rien de plus ; il ne doit pas ajouter de métadiscours (`the argument`, `this reasoning`, etc.) absent de la source.

`established-name=` est un sous-titre et commence donc par une majuscule ; les keywords ordinaires suivent la capitalisation lexicale contrôlée et ne reçoivent jamais automatiquement le `established-name=` comme mot-clé supplémentaire. Pour une nouvelle page anglaise, les recherches de `established-name=` doivent provenir d'un journal réel ou d'une nouvelle vérification : ne jamais reconstruire artificiellement des requêtes historiques.

## 2.15.35 — marqueurs sémantiques systématiques

Le moteur automatique compare les familles de marqueurs dans les titres canoniques, titres affichés et résumés. Toute perte signalée doit être relue contre le français; une paraphrase idiomatique équivalente peut être justifiée. Le moteur ne corrige jamais le texte.

La validation reste différentielle : une forme historique acceptée dans le français n’est pas normalisée au passage en anglais.



## Correctif 2.15.36 — provenance, Quote et inventaire final

La recherche d’`established-name=` enregistre sa provenance réelle. Une nouvelle page anglaise utilise `actual_log` ou `fresh_recheck`; `historical_reconstruction` ne sert qu'à décrire honnêtement une décision ancienne. Chaque `Quote` est relue de début à fin contre la `Citation` source ; sous un ratio lexical de 0,60, une seconde revue explicite est requise. La release calcule `release/content_inventory.json`, en lie l'empreinte au reçu, puis le recalcule sur l'extraction fraîche.


## Revue structurée et `established-name=`

Pour chaque titre traduit, confirmer explicitement le sujet, le prédicat, la portée et la modalité en plus de l’inventaire général. Pour chaque `established-name=` retenu, résumer séparément la portée du raisonnement de la page et celle de l’appellation attestée ; seule une correspondance exacte est admise. Les signaux automatiques issus des régressions connues servent à orienter la relecture et ne réécrivent jamais le texte.

## Conventions de publication réconciliées 1.2.64

La revue éditoriale reste indépendante de la publication distante. Pour une création anglaise réellement publiée :

- le résumé MediaWiki est `Translation of the French page: [[:fr:X|X]]` ;
- la révision reçoit `chatgpt` et `translated-fr` ;
- `creation-date=` est remplacé au plan par le jour civil réel de publication ;
- un nouvel `Argument` anglais ne transporte jamais `initialization=` depuis le wiki français ;
- le paramètre MediaWiki actuel d'appellation consacrée est `established-name=` ; `name=` n'est qu'un alias historique de préservation ;
- une `Quote` nouvellement traduite utilise `AI-translated quote`.

Ces conventions ne changent pas la règle de traduction différentielle : une propriété formelle déjà validée dans la source française n'est pas « réparée » silencieusement en anglais.

### Texte éditorial autour des citations

Le champ français `citations` peut contenir du texte avant, entre ou après les
modèles `Citation`. Cet inventaire est conservé séparément sous `citation_passages`
dans le verrou français, avec un identifiant et un ancrage `before_citation_id`
(`null` pour la fin du champ). Il ne s'agit pas de résumés ni de nouvelles citations.

La revue anglaise fournit pour chaque passage la `source_text` immuable, la
traduction `text`, `equivalent_to_french=true` après relecture effective et une
`review_note` précise. Aucun passage ne peut être omis, déplacé, supprimé ou
transformé en modèle `Quote`. Ces textes entrent dans l'empreinte sémantique et
sont réinsérés à leur position dans les rendus français et anglais.

Un ancien verrou qui omettait ces textes est refusé à la préparation anglaise
ou au rendu. Reprendre les revues et les verrous concernés ; ne pas compléter
leurs empreintes ou attestations à la main. Une source historique incertaine
reste signalée séparément et n'autorise pas une correction silencieuse du passage.
