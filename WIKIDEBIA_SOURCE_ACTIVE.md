# Wikidéb’IA — Source active unifiée

Ce fichier est la source textuelle active générée par `./wikidebia upgrade`. Il remplace les anciennes sources séparées consacrées aux normes, au validateur et au kit.

- norme active : **1.2.88** ;
- validateur actif : **0.4.105** ;
- kit actif : **2.16.47**.

## Composants associés

- `wikidebia-normes.zip` — 3748362 octets — SHA-256 `e0a9bea422c69c4598dc66fdb74f379612865dcf6d7ca5d461cafee040536f77`
- `wikidebia-validator.zip` — 4008788 octets — SHA-256 `30aa9088425cffff85c2dc57fa3d6c9850164b845aa570b78ffd2301631692fe`
- `wikidebia-kit.zip` — 1439620 octets — SHA-256 `59bb85aae58d4b33df4d6e4d1603af3af01ebfd63febeba22281a801bbae0f17`

## Norme consolidée active

Source interne : `norms/normative_reference/01_normes/WIKIDEBIA_NORME_CONSOLIDEE_1.2.88.md`  
SHA-256 : `367248f8c73e8eaf901c018d6ba412515d6ef0ace8d4a0b7eb21dd8f8a998741`

# Norme opérationnelle active Wikidéb’IA 1.2.88

**Statut : source normative active unique.**  
**Date d’effet :** 21 août 2026

Cette norme contient uniquement les règles actuellement applicables. Les textes de révisions remplacées, snapshots et anciennes formulations sont conservés dans `history/` et dans les changelogs, qui sont informatifs et immuables. Les numéros de norme, validateur, kit et producteur servent à la provenance, à la reproductibilité, à l’installation et aux migrations ; ils ne sélectionnent aucune règle éditoriale.

## Architecture de compatibilité active

1. Toute règle éditoriale active s’applique d’après l’état fonctionnel du corpus et non d’après un seuil de version.
2. Les artefacts sont acceptés ou refusés d’après leur `schema`, `schema_version`, format et capacités déclarées. Le numéro du producteur est une provenance.
3. Les formats historiques sont normalisés à l’entrée vers la représentation canonique : `sujet-complet→sujet-développé`, `complete-topic→expanded-topic`, `débat-détaillé→débat-dédié`, `detailed-debate→dedicated-debate`, et, pour un ancien corpus attesté, `nom→nom-consacré`, `name→established-name`. Les anciennes étiquettes ne sont pas réémises pour une nouvelle sortie.
4. Les versions courantes ont une source de vérité unique par composant (`VERSIONS.json`) ; les listes historiques compatibles, lorsqu’elles sont exposées, sont dérivées des snapshots et restent informatives.
5. Les égalités exactes de release restent admises uniquement pour installer un paquet exact, empêcher une rétrogradation, reproduire une release ou attester sa provenance. Elles ne constituent pas un prérequis de lecture d’un artefact au schéma supporté.
6. Les historiques et changelogs ne sont jamais réécrits rétroactivement.
7. La livraison standard est une archive canonique unique, directement consommable par `./wikidebia upgrade`, contenant aussi audit, conservation, handoff et `WIKIDEBIA_SOURCE_ACTIVE.md` à sa racine.

## Contrats canoniques issus des corrections récentes

- Les paramètres MediaWiki canoniques sont `sujet-développé` / `expanded-topic`, `débat-dédié` / `dedicated-debate`, `nom-consacré` / `established-name`. Les anciens noms ne sont que des alias d’entrée historiques attestés.
- Une nouvelle traduction anglaise d’`Argument` ne reçoit jamais `initialization` depuis `initialisation` français.
- Les paramètres de premier niveau `date-création` et `creation-date` sont obsolètes dans les quatre modèles Débat/Debate et Argument. Ils ne sont ni générés, ni traduits, ni conservés dans les nouvelles pages ou les mises à jour.
- `displayed-title` traduit `titre-affiché` champ à champ. La validation FR→EN est différentielle : elle bloque les dégradations introduites par la traduction sans réécrire une anomalie formelle acceptée dans la source française historique.
- Les recherches de `established-name`, les références anglaises et les `Quote` restent contextualisées par page. Les références ne sont pas traduites artificiellement ; les citations suivent le contrat `Citation→Quote`, avec `AI-translated quote` pour les nouvelles traductions.
- La convergence sémantique finale exige deux passes indépendantes portant sur la même empreinte du contenu, selon les schémas actifs de revue et de convergence.

## 1. Autorité et priorité

En cas de contradiction, l’ordre suivant s’applique :

1. décision explicite ultérieure du propriétaire du projet ;
2. présente norme consolidée ;
3. structures et schémas portant la même version ;
4. profils de rendu et workflow portant la même version ;
5. documents historiques et prompts, uniquement comme provenance.

Un audit décrit un état constaté ; il ne crée pas une règle supérieure à une décision normative. Aucune migration vers une version nouvelle ne peut être silencieuse.

## 2. Principes de production

Chaque débat et chaque argument possède une page dédiée. Les relations sont matérialisées par les titres canoniques des pages liées. Le registre maître JSON est la source de vérité des identifiants, titres, relations, occurrences, propriétaires de lots et états de génération.

Lorsque la traduction anglaise est `ready` ou `published`, les productions française et anglaise doivent être fonctionnellement équivalentes : mêmes nœuds, mêmes relations, mêmes occurrences et même orientation argumentative. Elles peuvent employer une rédaction et une documentation adaptées à chaque langue. Lorsque `translation_status.en=deferred`, cette équivalence n'est pas encore contrôlable et les contrôles bilingues sont différés sans affaiblir les contrôles français.

Les sorties générées doivent être prêtes à être relues et importées, sans métadiscours, sans paramètres d’avertissement vides, sans texte extérieur au modèle principal et sans normalisation silencieuse par le validateur.

## 3. Invariants du graphe

Sont verrouillés après validation du graphe :

- `debate_id` ;
- identifiants des nœuds, relations et occurrences ;
- titre canonique français ;
- titre canonique anglais dès que la traduction quitte l’état `deferred` ;
- orientation, parenté, ordre et profondeur des relations ;
- occurrence primaire et réutilisations ;
- propriétaires et composition des lots.

Les titres affichés, rubriques, sections, mots-clés, résumés et métadonnées documentaires peuvent être corrigés lorsque le workflow l’autorise. Toute modification d’un champ inclus dans l’objet canonique de l’empreinte structurelle impose un recalcul explicite et la documentation de l’ancienne et de la nouvelle empreinte.

### 3.1 Fonction argumentative des niveaux

La profondeur n’est pas un indice d’importance, de prestige disciplinaire ou de richesse documentaire. Elle exprime la fonction logique de chaque occurrence dans le graphe.

Une occurrence de **niveau 1** est un argument principal. Elle doit simultanément :

1. répondre directement à la proposition du débat, en faveur ou en défaveur de celle-ci ;
2. rester intelligible et défendable sans qu’un autre argument serve de parent implicite ;
3. ouvrir une famille argumentative distincte pouvant organiser des justifications, objections et réponses ;
4. ne pas avoir de parent plus général, non redondant, qui exprimerait mieux la raison principale ;
5. ne pas avoir pour fonction première de soutenir, d’attaquer, d’illustrer, de spécialiser ou de nuancer un argument déterminé.

Un argument important n’est donc pas nécessairement principal. Une objection visant spécialement une preuve, un exemple historique, un résultat expérimental, une interprétation scientifique, une doctrine particulière, un mécanisme technique ou une application sectorielle appartient à un niveau supérieur lorsqu’un argument plus général peut l’accueillir sans perte substantielle.

Le test décisif est le suivant : si l’énoncé conserve essentiellement la même fonction après suppression de la branche qu’il vise, il peut être candidat au niveau 1 ; s’il perd sa cible, sa portée ou sa raison d’être, il doit être subordonné à cette cible. Ainsi, « Le remplacement de théories autrefois fécondes affaiblit l’inférence du succès scientifique au réalisme » est une objection à l’argument tiré du succès des sciences, et non une branche principale parallèle. De même, une interprétation quantique relative à la mesure relève normalement d’un argument plus général sur la dépendance des propriétés au contexte de mesure.

Une formulation propre à une école philosophique peut être de niveau 1 seulement si cette formulation constitue elle-même une réponse autonome au débat. Lorsqu’elle instancie une thèse plus générale, la thèse générale devient le parent et la doctrine en fournit une justification, une précision ou un développement.

Toute occurrence de profondeur supérieure à 1 doit viser directement son parent immédiat. Elle ne doit pas être placée sous un parent seulement voisin par thème. Une page réutilisée peut apparaître à plusieurs endroits, mais chaque occurrence reçoit séparément une justification de placement.

Avant le verrouillage du graphe, une revue sémantique couvre toutes les occurrences actives. Pour chaque niveau 1, elle atteste la réponse directe au débat, l’autonomie, la capacité à structurer une famille et l’absence de parent général préférable. Pour chaque niveau supérieur, elle atteste que le parent est la meilleure cible immédiate et que la relation déclarée correspond au raisonnement. Cette revue est enregistrée dans le fichier déclaré par `editorial_controls.graph_placement_review_path`.

## 4. Titres canoniques et titres affichés

Le titre canonique est le nom de page et la cible de relation. Il est complet, explicite, autonome et non ambigu. Il mentionne le sujet lorsque cela évite une collision avec d’autres débats.

Pour une page **nouvelle ou dont le titre affiché est généré par Wikidéb’IA**, le titre affiché est une formulation de lecture plus concise que le titre canonique lorsque cette concision améliore réellement le rendu. Dans ce profil de création, il reste une proposition argumentative complète et immédiatement intelligible : le lecteur doit pouvoir identifier ce qui est affirmé, et non seulement le thème auquel l’argument se rapporte. Un simple groupe nominal, une étiquette doctrinale ou l’intitulé d’un phénomène ne suffit pas. Le titre affiché comporte au minimum un sujet et un prédicat explicites, sans point final, et conserve le lien logique décisif de l’argument. Le contexte d’affichage peut permettre d’omettre un cadrage déjà évident, mais il ne peut jamais remplacer le verbe, la conclusion ou la relation argumentative qui rendent la phrase compréhensible.

Lorsqu’un corpus est **repris depuis des pages préexistantes du wiki**, cette exigence de proposition complète ne s’applique pas rétroactivement aux `titre-affiché` déjà publiés. Le titre affiché historique est conservé par défaut, y compris lorsqu’il s’agit d’un groupe nominal, d’une formule courte ou d’un intitulé dépendant de son contexte d’affichage. Son seul caractère non propositionnel ne constitue ni une erreur ni un motif de réécriture. Il n’est modifié que pour corriger une faute d’orthographe, de grammaire ou de typographie, une troncation, une corruption manifeste, une ambiguïté flagrante ou un autre problème éditorial évident, ou sur décision explicite du propriétaire. Une harmonisation stylistique, l’allongement en phrase complète ou la simple préférence de Wikidéb’IA ne suffisent jamais à modifier un titre affiché préexistant. Cette préservation du titre affiché ne réduit pas les exigences applicables au **titre canonique / nom de page**, qui reste autonome, explicite et corrigeable lorsqu’il est incomplet, contextuel, fautif ou ambigu.

En traduction, `displayed-title` traduit le `titre-affiché` français validé, quelle que soit la provenance de la source et même si la page cible anglaise est nouvelle. Une forme courte, nominale ou contextuelle ne doit pas être allongée ni transformée en proposition pour satisfaire une règle de génération. La fidélité du sens, de la portée et de l'acte de langage reste obligatoire : seule une dégradation introduite par la traduction est bloquante. Un renommage canonique change la cible `page=`, sans remplacer automatiquement le libellé `titre-affiché`.

### 4.1 Autonomie référentielle du titre canonique

Le titre canonique constitue le nom permanent de la page et la cible de ses liens. Il doit être compréhensible lorsqu’il est présenté isolément, notamment dans un résultat de recherche, une liste de pages, un historique, une catégorie ou un lien dépourvu de contexte explicatif.

Il ne doit pas dépendre d’un élément extérieur au titre pour identifier son sujet. Une formulation anaphorique ou déictique est donc non conforme lorsque son antécédent n’est pas exprimé dans le titre lui-même. Sont notamment concernés les déterminants et pronoms tels que « ce », « cet », « cette », « ces », « celui-ci », « celle-ci », « il », « elle », « ils » ou « elles » lorsqu’ils renvoient seulement au parent, à la branche ou au paragraphe environnant.

Le titre canonique remplace alors l’expression contextuelle par le nom ou la désignation explicite du référent. Cette règle porte sur l’autonomie du nom de page, non sur une catégorie particulière d’objets : elle s’applique de la même manière à une méthode, une institution, une théorie, un événement, une mesure, une personne, un résultat ou tout autre sujet.

Exemple :

- non conforme : `La répétition des défaillances de cette méthode réduit sa fiabilité` ;
- conforme : `La répétition des défaillances de la méthode de contrôle croisé réduit sa fiabilité`.

Les démonstratifs et pronoms ne sont pas interdits lorsqu’ils possèdent un antécédent explicite et non ambigu dans le titre lui-même. Ainsi, un possessif comme « sa fiabilité » peut reprendre la `méthode de contrôle croisé` déjà nommée dans la même proposition.

Pour un titre affiché nouvellement généré, une expression contextuelle plus courte est admise si son référent est immédiatement identifiable dans l’emplacement d’affichage, si aucune autre entité ne peut être visée et si le raisonnement reste strictement identique au titre canonique. Dans ce profil de création, cette souplesse ne dispense pas d’une phrase propositionnelle complète : « La convergence entre observateurs » est un thème, tandis que « La convergence entre observateurs indique l’existence d’objets publics » expose un argument. La règle ne sert pas à réécrire rétroactivement un `titre-affiché` historique déjà présent sur le wiki.

Un titre affiché nouvellement généré ne peut jamais être obtenu par une troncature aveugle ni réduit à un intitulé nominal. Sur une page préexistante, la liste ci-dessous sert à détecter les erreurs flagrantes réellement corrigeables, mais le caractère nominal historique n’est pas en lui-même un défaut. Sont notamment interdits pour une nouvelle génération :

- les ellipses `...` ou `…` ;
- la suppression d’un article, déterminant ou mot initial nécessaire à la grammaire ;
- un début de titre constitué d’une lettre résiduelle telle que `S ` ou `E ` ;
- une fin sur une préposition, une conjonction ou un connecteur incomplet ;
- les remplacements lexicaux qui créent un doublon, une construction hybride ou un énoncé non idiomatique ;
- la présence accidentelle de mots d’une autre langue, hors noms propres et dénominations officielles ;
- un groupe nominal qui nomme seulement un thème, un phénomène, une école ou une objection sans exprimer ce que cet élément établit ;
- une formulation dépourvue de prédicat explicite ou dont le lecteur ne peut comprendre la portée argumentative sans ouvrir la page.

Lorsqu’une substitution contextuelle est employée pour distinguer titre canonique et titre affiché, elle doit être relue dans la phrase entière. Le titre validé dans le registre doit être reproduit à l’identique dans toutes les relations, pages Débat/Debate, agrégats, projections et fichiers canoniques, agrégats et manifestes.

### 4.2 Guillemets dans les noms de pages et titres affichés

Le critère est l’accessibilité sur un clavier d’ordinateur ordinaire, sans saisie d’un code Unicode ou d’une combinaison spécialisée. Les deux sites utilisent donc les **guillemets droits doubles ASCII** `"..."` dans les titres canoniques et les titres affichés :

- français : `Le terme "effet de seuil" est défini...` ;
- anglais : `The term "threshold effect" is defined...`.

Les guillemets typographiques ou chevrons `« »`, `“ ”`, `„ ”`, `‹ ›` sont interdits dans les noms de pages et titres affichés. L’apostrophe droite ASCII `'` reste utilisée pour les élisions françaises et les contractions ou possessifs anglais ; elle ne remplace pas les guillemets d’une citation principale. Les guillemets droits doivent être équilibrés.

Pour un titre affiché **nouvellement généré ou substantiellement réécrit par Wikidéb’IA**, la décision reste prise page par page. Le titre canonique est conservé à l'identique lorsqu'il est déjà clair, complet et suffisamment lisible : cette identité est un choix normal, non une exception statistique, et aucun quota n'impose de reformuler les titres. Un titre affiché distinct n'est retenu que si la nouvelle formulation améliore concrètement la lecture tout en conservant exactement le sujet, le prédicat, la modalité, la relation logique, la portée et le degré de force du titre canonique.

Pour un `titre-affiché` historique préexistant et sa traduction anglaise, l'existence d'une différence avec le titre canonique n'a pas à être justifiée rétroactivement par une amélioration de lisibilité. La revue atteste en revanche la fidélité sémantique, l'intelligibilité et l'absence de nouvelle dégradation introduite par la traduction. Une anomalie historique manifeste reste corrigeable selon les règles de reprise ; le seul caractère court, nominal ou contextuel d'un titre humainement validé ne constitue pas une anomalie.

## 5. Résumés d’arguments

Le résumé expose la version la plus forte du raisonnement porté par le nœud : prémisses, mécanisme, conclusion et portée documentée. Il ne modifie ni l’identité logique, ni l’orientation, ni la force soutenue par les sources.

Le résumé ne doit pas :

- anticiper une objection ;
- se conclure par sa propre réfutation ;
- ajouter une concession destinée seulement à équilibrer le texte ;
- diminuer artificiellement la portée de la proposition ;
- parler de « l’argument », de « la page » ou du « raisonnement présenté ».

Les limites opposables sont portées par les pages d’objections reliées. Une délimitation nécessaire à l’identité de la proposition peut être conservée lorsqu’elle est formulée positivement.

Une revue humaine bilingue est obligatoire avant `release_ready`. Les heuristiques automatiques détectent notamment les concessions finales et le métadiscours, mais ne remplacent pas cette revue.

### 5.0 Préservation des résumés historiques lors d’une reprise

Lorsqu’une page `Argument` est **préexistante sur le wiki et importée comme source d’une reprise**, la présence et la valeur de son `résumé` constituent un contenu historique protégé. La revue française ordinaire de contenu ne réécrit pas ce résumé, même si une formulation nouvelle satisferait mieux les règles de style applicables aux créations. Si le résumé historique est absent, cette absence est conservée : Wikidéb’IA n’en génère pas un pour remplir un champ, satisfaire un profil de longueur, améliorer l’homogénéité du corpus ou préparer la traduction.

Les exigences des sections 5.1 et 5.2 gouvernent les résumés nouvellement créés. Pour un résumé historique, elles ne sont jamais appliquées rétroactivement afin de justifier une réécriture silencieuse. ChatGPT peut toutefois relever une faute, une corruption, une anomalie MediaWiki, un problème au regard d’une règle active ou une amélioration possible et enregistrer une suggestion sans modifier la valeur finale.

Toute modification d’un résumé historique exige une **décision explicite, précise et traçable du propriétaire**. Tant que cette décision n’existe pas, le résumé reste strictement identique à la source historique. Si l’autorisation est donnée pendant que `fr_content_review` est encore ouverte, le champ concerné devient éditable dans cette même phase et la modification autorisée peut être publiée au checkpoint français n°2 ; aucune opération corrective séparée ni troisième publication française n’est requise. Une opération corrective distincte reste disponible lorsque la demande intervient après la clôture de la revue ou du checkpoint.

L’autorisation est limitée aux champs et valeurs explicitement ouverts. Une suggestion de ChatGPT, un booléen librement éditable dans le ZIP, une préférence stylistique du validateur ou l’existence du checkpoint n°2 ne valent jamais consentement. Le workflow produit hors du ZIP éditable une preuve locale liée au paquet retourné, au champ, à l’empreinte historique et à l’empreinte finale. Un résumé historiquement absent ne peut être créé que si cette création est nominativement autorisée. Une correction locale autorisée n’active pas rétroactivement toutes les règles stylistiques destinées aux résumés nouveaux ; une réécriture substantielle explicitement demandée peut faire l’objet des contrôles supplémentaires pertinents sans autoriser d’autres modifications parasites.

Le verrou français de contenu enregistre pour chaque page préexistante l’état `historical_existing` ou `historical_absent`, la présence et l’empreinte historiques, l’état de décision `preserved` ou `authorized_change`, l’empreinte finale et, pour `authorized_change`, la preuve de consentement propriétaire. **La valeur historique reste la provenance ; elle n’est pas nécessairement la valeur éditoriale effective.** Avec `preserved`, la valeur sélectionnée est strictement la valeur historique. Avec `authorized_change`, la valeur sélectionnée est strictement la valeur finale autorisée. Tous les contrôles structurels, le verrou, le changeset, le rendu, le checkpoint français n°2 et la traduction utilisent cette valeur sélectionnée. Les règles éditoriales propres à une création ou à une réécriture ne s’appliquent qu’au périmètre réellement ajouté ou substantiellement modifié ; elles ne requalifient pas le reste du texte historique inchangé.

Lors de la traduction FR→EN, un résumé français ainsi préservé reste la source éditoriale autoritative : la traduction peut adapter la langue mais ne doit pas servir à corriger rétroactivement sa longueur, son style ou sa structure. Les contrôles sémantiques différentiels restent applicables ; une source historiquement absente produit un `summary` anglais absent.

### 5.1 Style encyclopédique grand public

Le résumé adopte un style encyclopédique destiné à un lectorat non spécialiste. Il présente l'idée centrale dès l'ouverture, puis explique le mécanisme utile à sa compréhension. Il privilégie des phrases courtes ou moyennes, de longueur variée, et évite les enchaînements de propositions longues qui donnent au texte l'allure d'un article universitaire.

Tout terme scientifique, technique, juridique ou philosophique indispensable est rendu compréhensible lors de sa première occurrence significative. Deux moyens sont admis : une brève explication intégrée au raisonnement, ou, lorsque le premier paragraphe de Wikipédia fournit une définition suffisante, un lien explicatif au survol avec `{{Lien Wikipédia}}` en français ou `{{Wikipedia link}}` en anglais. Le lien au survol évite de répéter dans la phrase une définition déjà disponible, mais il ne remplace jamais l’explication du mécanisme propre à l’argument. Un terme de langue courante n’a pas à être lié ou défini artificiellement, et le résumé ne doit devenir ni un glossaire ni une succession de liens.

Dans un résumé français, la forme canonique est `{{Lien Wikipédia|article=Titre de la page}}`. Le paramètre facultatif `|texte-affiché=…` n’est utilisé que lorsque le texte visible souhaité diffère réellement du titre de la page. Une simple adaptation de la majuscule initiale ne justifie pas ce paramètre : dans le corps d’une phrase, `L'{{Lien Wikipédia|article=effet placebo}}` est préféré à un paramètre d’affichage redondant. En anglais, les formes correspondantes sont `{{Wikipedia link|article=Page title}}` et `|displayed-text=…`.

Le titre de l’article est vérifié dans l’édition linguistique de la page produite. Le modèle est placé sur la première occurrence utile de la notion, puis normalement omis lors des répétitions. Il n’est pas employé dans les titres, les citations, les métadonnées documentaires ni le corps des notes `<ref>…</ref>`. Si le premier paragraphe de Wikipédia est trop général, ambigu ou insuffisant pour le raisonnement, une explication concise reste obligatoire dans la prose.

La rédaction suit normalement cet ordre :

1. thèse ou idée principale ;
2. explication concrète du mécanisme ;
3. exemple, donnée ou distinction réellement utile ;
4. délimitation indispensable, seulement si elle appartient à l'identité de la proposition.

Les noms d'auteurs, d'études et de méthodes ne précèdent pas l'explication qu'ils doivent éclairer. Ils sont mentionnés uniquement lorsqu'ils ajoutent une information nécessaire. Le résumé n'explique pas tout le dossier : il développe un seul nœud logique avec assez de précision pour être compris seul.

Une revue page par page atteste, pour chaque langue produite : l'annonce directe de la thèse, l'accessibilité au grand public, le rythme des phrases et l'explication des termes techniques nécessaires. Le validateur peut signaler une accumulation de phrases longues, mais ce signal est heuristique et ne mesure ni la qualité logique ni la suffisance des définitions.

Lorsqu’un résumé existe dans les deux langues, les résumés français et anglais d’un même nœud doivent être substantiellement équivalents : mêmes prémisses principales, mêmes éléments probants décisifs, même conclusion et même portée. Une différence de longueur n’est pas en soi une faute. Pour un résumé nouvellement rédigé, un ratio anglais/français inférieur à 0,60 ou supérieur à 1,45 déclenche un blocage automatique et une reprise humaine. Pour la traduction d’un résumé historique préexistant, le même seuil constitue un **signal de revue** : la sortie peut être validée hors plage lorsque la revue bilingue atteste explicitement l’équivalence et justifie l’écart, sans allonger ni raccourcir artificiellement le texte pour atteindre le ratio. Une absence historique attestée reste exclue de ce contrôle.

### 5.2 Ouverture, concrétisation et force expressive

La première phrase du résumé ne répète pas mécaniquement le titre canonique ou le titre affiché. Elle développe immédiatement l’argument en présentant un phénomène concret, une prémisse décisive, un mécanisme causal, une conséquence ou une distinction utile. La thèse doit rester identifiable dès l’ouverture, mais sa simple reformulation ne constitue pas un développement suffisant.

Un exemple concret, un ordre de grandeur ou une donnée chiffrée est ajouté lorsqu’il améliore réellement la compréhension ou renforce la démonstration. Son emploi n’est jamais obligatoire. Un chiffre doit être soutenu par une source documentaire de la page et présenté avec la portée, la population et le contexte nécessaires. Aucun exemple ou chiffre ne doit être ajouté pour donner artificiellement une impression de précision, de variété ou d’autorité.

Le résumé adopte normalement une formulation ferme, imagée et légèrement mordante qui fait apparaître la force du raisonnement et la conviction de la voix qui le défend. Une rédaction uniformément lisse, distante ou neutralisée n’est pas conforme lorsque le nœud permet une expression plus saillante. Cette fermeté ne doit pas devenir un ton militant, sarcastique ou méprisant. Le texte ne ridiculise pas l’argument adverse, ne prête pas d’intentions aux personnes ou aux institutions et ne transforme pas une proposition discutée en vérité éditoriale incontestable. La revue page par page relève une expression réellement présente dans le résumé qui rend cette force perceptible.

Les images explicatives, oppositions de formulation et phrases saillantes sont admises lorsqu’elles clarifient le mécanisme. Elles ne doivent pas devenir des slogans, être répétées mécaniquement d’une page à l’autre ou dépasser ce que permettent le titre, le graphe et les sources.

Un résumé est bloqué lorsqu’il emploie une charpente rédactionnelle générique à la place du raisonnement propre au nœud. Sont notamment non conformes les formulations telles que « Plusieurs faits ou principes sont ici interprétés… », « Cette conclusion s’appuie notamment sur les propositions suivantes… », « Les faits, principes ou expériences invoqués… », « La thèse en tire une conséquence directe… », « La critique en tire une conséquence directe… », « Le point concret est le suivant… » ou « La conséquence avancée est précise… ». Les variantes proches et les traductions fonctionnelles sont traitées de la même manière.

Le résumé ne peut pas être obtenu en recopiant ou en énumérant les titres des justifications et objections reliées. Il doit expliquer le mécanisme qui permet de passer des prémisses à la conclusion, même lorsque les pages filles fournissent le détail de ces prémisses. Une reprise de deux titres enfants ou davantage sous la forme d’une liste, d’une série de citations ou d’une phrase d’annonce constitue un signal bloquant à reprendre humainement.

À l’échelle d’un corpus, une même phrase normalisée de huit mots significatifs ou davantage ne peut apparaître dans quatre résumés ou plus, sauf citation commune explicitement balisée et documentée. La revue individuelle atteste pour chaque page que le mécanisme propre au nœud est effectivement formulé et que le résumé n’est pas une variante superficielle d’un gabarit utilisé ailleurs.

Dans la prose française, `Dieu` prend une majuscule lorsqu’il désigne le nom propre du Dieu unique des traditions monothéistes. La minuscule est conservée pour un nom commun réellement générique (`un dieu`, `les dieux`, `le dieu d’une tradition particulière`). Les occurrences telles que `dieu est`, `l’existence de dieu`, `la volonté de dieu` ou `selon laquelle dieu…` sont donc non conformes lorsqu’elles visent le nom propre.

La revue humaine page par page atteste en outre que l’ouverture développe le titre, que la pertinence d’un exemple ou d’une donnée a été examinée, que tout chiffre a fait l’objet d’une vérification documentaire explicite, et que le ton reste ferme sans devenir polémique.

## 6. Rubriques, sections et mots-clés

Les rubriques françaises autorisées sont : Aménagement, Culture, Droit, Écologie, Économie, Éducation, Éthique, Géopolitique, Histoire, Philosophie, Politique, Psychologie, Religion et spiritualité, Santé, Science, Société, Sport et loisirs, Technologie.

Chaque nœud est classé individuellement. Pour une page nouvelle ou une classification générée par Wikidéb’IA, une à trois rubriques réellement centrales sont normalement utilisées ; une quatrième est exceptionnelle et motivée. Pour une page française préexistante, les rubriques historiques constituent le point de départ autoritatif et sont conservées autant que possible : leur seul nombre, y compris au-delà de quatre, n'est pas un motif de correction. Une rubrique historique peut néanmoins être ajoutée, retirée ou remplacée lorsque la revue constate une classification réellement inadéquate ou incomplète ; ce delta est explicitement motivé et traçable. Une rubrique peut légitimement être présente sur tous les arguments d'un débat lorsque sa pertinence est démontrée page par page ; sa fréquence locale ne constitue ni une preuve de pertinence ni une anomalie automatique. Les décisions sont consignées dans un registre de revue. Dans chaque valeur MediaWiki et dans le registre correspondant, les rubriques françaises sont rangées par ordre alphabétique français et les sections anglaises par ordre alphabétique anglais. Les sections anglaises constituent le même ensemble conceptuel que les rubriques françaises **finalement validées**, mais leur ordre est recalculé indépendamment dans la langue anglaise.

Une page d’argument **nouvelle** reçoit normalement **deux à quatre mots-clés thématiques**. Leur fonction principale est la navigation à l’échelle de l’ensemble du wiki : un clic doit pouvoir rapprocher des arguments relevant de débats différents autour d’un même phénomène, d’une même méthode, d’une même question épistémologique ou d’un même contexte institutionnel.

Lorsqu’une page existe déjà sur le wiki au début de la reprise, ses mots-clés sont **préservés par défaut quant à leur présence**, sans être sanctuarisés quant à leur qualité. Aucun mot-clé historique n’est supprimé uniquement pour respecter la cible de deux à quatre, uniformiser le vocabulaire ou simplifier la page. En revanche, toutes les règles intrinsèques de qualité de la présente section restent applicables aux termes historiques : graphie canonique, forme nominale, longueur, atomicité, absence d'intersection compositionnelle artificielle et appartenance au vocabulaire contrôlé. Un mot-clé historique réellement défectueux peut donc être corrigé, remplacé ou décomposé en plusieurs concepts atomiques, avec une justification explicite propre au terme source et la liste exacte des remplacements. La suppression sans remplacement d’un mot-clé préexistant n’est admise que lorsque la revue conclut explicitement qu’il est réellement non pertinent pour la page. Le dépassement historique de la cible quantitative n’est jamais un motif de suppression.

Un mot-clé doit donc être :

- simple et immédiatement compréhensible ;
- central pour le raisonnement de la page ;
- assez général pour pouvoir être réutilisé dans d’autres débats du wiki ;
- assez précis pour former un regroupement utile ;
- formulé comme un nom, un groupe nominal court, un nom propre ou un acronyme reconnu.

Sont interdits :

- les verbes, adjectifs ou adverbes isolés ;
- les fragments de phrase ;
- les formulations qui résument presque toute la proposition de la page ;
- les détails propres à une étude, une date, un seuil ou un résultat lorsqu’un concept encyclopédique plus stable existe ;
- les synonymes artificiels créés pour rendre les jeux de mots-clés différents.

Un mot-clé thématique désigne normalement **un concept atomique de navigation**. L’atomicité est sémantique, non seulement grammaticale. Une expression n’est pas rendue atomique par le simple remplacement d’un complément par un adjectif : `psychologie de la religion` ne doit donc pas devenir `psychologie religieuse`, mais être décomposée en `psychologie` et `religion`. La même règle s’applique aux intersections transparentes de disciplines, domaines ou thèmes, telles que `histoire des religions`, `science et religion`, `sociologie religieuse` ou `religious psychology` : chaque unité de base devient un mot-clé distinct et cliquable.

Une locution multi-mots reste cependant atomique lorsqu’elle nomme une catégorie conventionnelle dont le sens ne se réduit pas à la simple intersection de ses constituants. `argument d'autorité`, `problème du mal`, `lois de la nature`, `charge de la preuve` et `pari de Pascal` sont ainsi conservés comme unités. Le test décisif est le suivant : si la combinaison des mots-clés de base permet de retrouver sans perte la même catégorie, l’expression doit être décomposée ; si la locution désigne un type d’argument, une doctrine, une méthode, un phénomène ou un objet technique reconnu qui disparaîtrait lors de la séparation, elle peut rester entière.

La forme préférée est un nom unique ou un composé lexical stable de deux mots au plus. Une expression de trois mots ou davantage, ou contenant un connecteur tel que « de », « du », « des », « et », `of` ou `and`, n’est admise que lorsqu’elle constitue une dénomination encyclopédique lexicalisée impossible à simplifier sans perte. Le vocabulaire contrôlé atteste alors `atomic_concept=true`, `compositional_intersection=false`, `multiword_exception=true` et une justification spécifique non vide. Pour toute autre entrée, `compositional_intersection=false` et `multiword_exception=false` sont explicitement enregistrés.

Les mini-rubriques productives qui décrivent un angle de traitement au lieu de nommer un concept sont interdites, notamment les formes du type `limites de la science`, `histoire des religions`, `construction des lois scientifiques`, `fiabilité des preuves`, `origine de …` ou `sens de …`, lorsqu’un nom simple ou un composé stable existe (`épistémologie`, `histoire religieuse`, `loi scientifique`, `preuve`, `cosmogonie`, `sens existentiel`). Une attestation générique ne transforme pas une telle formule en mot-clé.

Un mot-clé thématique comporte au plus quarante caractères. Le vocabulaire contrôlé bilingue consigne chaque paire français–anglais, sa définition, son caractère atomique, toute exception multi-mots et, à titre informatif, ses usages dans le corpus courant.

La **graphie canonique** est obligatoire. Un nom commun ou groupe nominal commun commence par une minuscule : `revenu`, `revenu de base`, `philosophie politique`. Une majuscule initiale ou interne n’est conservée que lorsqu’elle appartient à la graphie établie d’un nom propre, d’une dénomination officielle, d’un sigle, d’un acronyme ou d’une marque : `Dieu`, `Islam`, `Union européenne`, `ONU`, `ADN`, `eBay`. Le vocabulaire contrôlé indique pour chaque entrée sa nature grammaticale, sa politique de capitalisation et, lorsqu’une majuscule est conservée, une justification non vide. Un terme ne peut pas être déclaré artificiellement nom propre afin de conserver une majuscule décorative. Deux entrées qui ne diffèrent que par la casse, telles que `revenu` et `Revenu`, constituent un doublon interdit. Les pages reproduisent exactement la graphie canonique du vocabulaire. La même règle s’applique aux keywords anglais.

Les mots-clés d’une page sont ordonnés **du plus directement pertinent au moins directement pertinent**. Le premier mot-clé désigne le concept le plus évident, central ou immédiatement caractéristique du sujet ou du mécanisme argumentatif ; les suivants élargissent progressivement le contexte. L’ordre chronologique de création, d’importation ou d’ajout dans le vocabulaire est interdit comme principe de classement. L’ordre alphabétique est également exclu, sauf coïncidence avec l’ordre de pertinence. La revue page par page atteste explicitement ce classement.

**La fréquence dans un débat particulier n’est jamais un critère d’admissibilité.** Un mot-clé peut n’apparaître que sur un seul argument du débat courant lorsque le concept est suffisamment général pour concerner d’autres arguments du wiki ou d’autres débats. Il n’existe donc ni minimum d’occurrences locales, ni plafond de taille du vocabulaire calculé en proportion du nombre d’arguments du débat.

La réutilisation effective à l’intérieur du débat reste une information utile pour la revue, mais elle ne doit pas conduire à supprimer un thème central ou à le remplacer par un terme artificiellement plus vague. Pour des mots-clés **nouvellement attribués par Wikidéb’IA**, un même jeu exact dominant plus de 25 % des arguments concernés demeure bloquant, car il signalerait une attribution mécanique. Lorsque cette domination provient d'une classification historique préexistante, elle constitue seulement un signal de revue et ne justifie ni suppression ni réécriture mécanique.

Les keywords anglais sont des équivalents idiomatiques et conservent exactement le classement français final par pertinence décroissante. Pour les rubriques et sections des pages Débat/Debate, la précision prime sur l’exhaustivité : seules les catégories qui caractérisent le débat dans son ensemble sont retenues, sans ajouter une catégorie parce qu’un argument secondaire, une méthode particulière ou une sous-partie de l’introduction la mentionne. Une page Débat réellement nouvelle ou dont les mots-clés sont générés par Wikidéb’IA utilise normalement cinq à huit mots-clés généraux ; une page Débat préexistante conserve son nombre historique final, sous réserve des mêmes corrections qualitatives intrinsèques que les autres mots-clés.

## 7. Documentation et références

### 7.1 Principes communs

Une source possède un identifiant documentaire unique, une notice vérifiable et des usages réciproques cohérents. Les doublons par DOI, ISBN, URL canonique ou clé normalisée sont interdits.

La bibliographie est généralement prioritaire. La sitographie et la vidéographie sont complémentaires. La sélection documentaire s’adapte au domaine de l’argument : publications scientifiques et synthèses pour les questions empiriques, textes officiels et doctrine pour le droit, sources primaires et travaux historiques pour l’histoire, œuvres et commentaires académiques pour la philosophie, données et rapports institutionnels pour les politiques publiques, ou toute autre source de référence adaptée au sujet. Les pages Argument ne remplissent pas de quotas : chaque famille documentaire peut contenir zéro, une ou plusieurs références selon son apport réel. Les pages Débat et Debate répartissent les références selon leur orientation réelle, sans quota par paramètre. Une source qui développe substantiellement des arguments favorables et défavorables, présente un débat contradictoire ou offre une synthèse générale appartient à la position `ni-pour-ni-contre` / neutre. Une même référence ne figure jamais simultanément dans plusieurs orientations. Une rubrique peut rester vide ou contenir une seule référence lorsqu'aucune autre source réellement pertinente n'est disponible ; elle n'est jamais remplie artificiellement pour équilibrer le tableau.

Sur une page `Argument`, le critère déterminant est que la source développe, explique, défende, documente ou étaye réellement le raisonnement propre à l’argument. Une source seulement contextuelle ou consacrée uniquement à des objections n’est pas retenue comme référence de cet argument. En revanche, lorsqu’une source développe bien l’argument, le fait qu’elle examine aussi des objections, des limites ou des réponses adverses ne constitue jamais un motif de retrait. L’usage documentaire consigne séparément la vérification du développement de l’argument et l’éventuelle présence d’objections ; cette seconde information est descriptive et n’invalide pas la référence.

### 7.2 Pagination bibliographique

Une page ou plage de pages utilise :

```mediawiki
|page=36-37
```

La valeur ne contient ni `page`, ni `pages`, ni `p.`, ni `pp.`. `localisation=` et `location=` sont réservés aux repères non strictement paginaires : chapitre, section, annexe, numéro ou identifiant d’article.

Une incompatibilité entre la norme et un modèle public est un blocage de publication. Elle ne doit jamais être contournée silencieusement dans le corpus ou le kit.

### 7.3 Dates sitographiques

`date=` contient la date de publication ou de mise à jour substantielle. Lorsqu’une date complète est connue, elle est écrite en langage naturel dans la langue de la page (`25 juin 2012` en français, `25 June 2012` en anglais), jamais au format machine `2012-06-25`. Une année seule, par exemple `2012`, reste admise lorsqu’elle est la seule précision documentaire disponible. Une date de consultation n’est jamais placée dans `date=`. Lorsque la date documentaire n’est pas vérifiable, le paramètre est omis. Aucune date ne peut être inventée.

### 7.4 Langue des sources et éditions linguistiques

La langue enregistrée dans le registre documentaire est la langue réelle du contenu cité, et non la langue de la page qui l’utilise. Chaque usage indique séparément la langue de la page. La vérification de langue est explicite.

Les pages Débat et Debate utilisent exclusivement des ressources intégralement disponibles dans leur propre langue, y compris les appels de référence de l’introduction et les listes documentaires structurées. Une page française de débat ne cite donc aucune ressource anglaise ; une édition, traduction, page, version doublée ou sous-titrée officiellement en français constitue une notice française distincte.

Sur une page Argument française, une édition ou traduction française pertinente et vérifiable est toujours préférée lorsqu’elle existe. Une source primaire ou académique peut rester dans sa langue originale uniquement lorsqu’aucun équivalent français officiel et pertinent n’existe, ou lorsque la ressource étrangère est elle-même l’objet analysé. Cette décision est consignée dans l’usage documentaire. Les titres publiés ne sont jamais traduits artificiellement. La règle symétrique s’applique aux pages anglaises.

Les éditions ou traductions d’une même œuvre partagent un identifiant d’équivalence documentaire. Le validateur bloque l’emploi d’une source étrangère sur une page Argument lorsqu’un équivalent vérifié dans la langue de la page est disponible dans le registre.

### 7.5 Finalité et organisation des introductions Débat / Debate

Lorsqu’une page `Débat` est **préexistante sur le wiki et importée comme source d’une reprise**, son `introduction` constitue un contenu historique protégé **par défaut**. `fr_content_review` reprend exactement sa présence et sa valeur tant qu’aucune décision propriétaire ne l’ouvre. ChatGPT peut relever et enregistrer des suggestions (orthographe, grammaire, ponctuation, typographie, syntaxe MediaWiki, formulation corrompue, structure, règle active ou amélioration plus substantielle) sans les appliquer automatiquement. Les exigences de création de la présente section ne servent jamais, à elles seules, à réécrire rétroactivement une introduction historique.

Une modification de l’introduction historique devient légitime dès lors qu’une décision propriétaire explicite et traçable couvre précisément le delta. Si cette autorisation intervient avant la clôture de `fr_content_review`, la modification est appliquée dans cette même revue et publiée au checkpoint français n°2. Sont notamment autorisables de cette façon la suppression d’une balise `<references />`, une correction locale ou l’ajout explicitement demandé d’une sous-partie telle que `Enjeux du débat`. Le consentement ouvre uniquement le delta demandé et n’autorise aucune réécriture parasite. Pour une autorisation structurée, le workflow peut sceller la portée par sous-parties (`added`, `modified`, `removed`, `reordered`) afin qu’une autorisation limitée à l’ajout de `Enjeux du débat` ne couvre pas une modification silencieuse d’une sous-partie historique. Une autorisation de réécriture globale reste possible lorsqu’elle est explicitement demandée et liée à la valeur finale exacte.

Après autorisation, **l’introduction finale autorisée devient l’introduction éditoriale effective**. L’introduction historique reste sa provenance. L’extraction des sous-parties, la comparaison avec `review.subsections`, les contrôles de structure et de références, les inventaires applicables, la construction du verrou et du changeset, le rendu, le checkpoint français n°2 et la traduction travaillent donc sur cette valeur finale sélectionnée. Les contrôles de création ou de réécriture sont différentiels : les sous-parties historiques inchangées ne sont pas requalifiées comme nouvelles ; une sous-partie nouvellement ajoutée ou substantiellement réécrite reçoit les contrôles pertinents à son propre périmètre. Le verrou français de contenu conserve l’empreinte historique, l’empreinte finale autorisée, le type et la portée du changement ainsi que la preuve locale de consentement.

Lors de la traduction d'une introduction française historique, la page anglaise constitue une **adaptation éditoriale autonome** et non une transposition mécanique phrase à phrase. La revue examine explicitement les passages dont la pertinence dépend du seul contexte franco-français : ils peuvent être condensés, contextualisés, reformulés ou omis lorsqu'une reprise littérale serait trompeuse ou inutile pour un lectorat anglophone. Cette localisation ne peut ni changer la définition de la question, ni déplacer l'orientation du débat, ni supprimer un repère nécessaire à son intelligibilité, ni introduire un nouvel enjeu sans justification. Elle est documentée par une justification d'adaptation et reste soumise à la convergence sémantique. Les contraintes de structure propres à une **nouvelle introduction générée** (par exemple l'existence d'une sous-partie particulière ou un volume minimal de celle-ci) ne sont pas imposées rétroactivement aux sous-parties historiques inchangées. Les exigences intrinsèques de qualité de la version anglaise restent en revanche actives : documentation anglophone, attribution des affirmations factuelles, ponctuation des notes, revue des liens Wikipédia et des notions spécialisées, cohérence documentaire et autres contrôles techniques ne sont pas désactivés par la provenance historique.

L’introduction apporte de manière synthétique les éléments nécessaires pour comprendre le débat avant la lecture des arguments. Elle permet au lecteur d’identifier le sujet, le sens exact de la question, son contexte et ses principaux enjeux. Elle ne constitue ni une revue exhaustive de la littérature, ni un résumé successif des arguments pour et contre, ni une reproduction des branches du graphe argumentatif.

Elle traite normalement, dans un ordre adapté au sujet :

1. de la définition du ou des sujets et de la délimitation du périmètre ;
2. du sens précis de la question débattue, de ses principales interprétations et des distinctions nécessaires pour éviter les confusions ;
3. des repères historiques permettant de comprendre l’apparition et l’évolution du débat ;
4. de l’état actuel du débat lorsqu’il demeure contemporain, notamment ses principaux acteurs, institutions, évolutions ou cadres applicables ;
5. des concepts, mécanismes, méthodes, données ou contextes indispensables à la compréhension du désaccord ;
6. des conséquences ou enjeux uniquement lorsqu'ils apportent une information précise indispensable à la compréhension de la controverse.

D’autres sous-parties peuvent être ajoutées lorsqu’elles apportent un élément réellement nécessaire à la compréhension du sujet. Aucune liste thématique propre à un débat particulier ne devient une structure universelle applicable mécaniquement aux autres débats.

Les sous-parties suivent une progression compréhensible pour un lecteur qui découvre le sujet. Chacune répond à une question identifiable et son utilité pour la compréhension du débat apparaît dès ses premières phrases. Une sous-partie technique, consacrée par exemple à une méthode, un indicateur, un cadre juridique ou un mécanisme spécialisé, n’est introduite que si le texte explique pourquoi cet élément est déterminant pour la question débattue.

Les titres de sous-parties privilégient les formulations accessibles et informatives. Ils évitent les intitulés spécialisés ou abstraits dont le rapport avec le débat n’est pas immédiatement compréhensible.

Dans le contenu des sous-parties, une notion spécialisée dont la définition est utile mais secondaire peut être rendue explicite au survol avec `{{Lien Wikipédia}}` en français ou `{{Wikipedia link}}` en anglais. Le modèle est réservé aux notions qui risqueraient réellement d’arrêter un lecteur non spécialiste. Il ne sert ni à lier chaque nom propre, chaque institution ou chaque terme courant, ni à remplacer les explications nécessaires au sens de la question débattue.

La sélection des liens est précédée d’une revue sémantique complète de chaque sous-partie. La revue inventorie toute notion scientifique, philosophique, juridique, religieuse, historique ou technique qui pourrait arrêter un lecteur non spécialiste. Pour chaque notion, elle choisit et justifie un traitement :

- `wikipedia_link` lorsque le premier paragraphe d’un article vérifié fournit l’éclaircissement secondaire utile ;
- `explained_inline` lorsque le sens nécessaire au débat doit être formulé directement dans la prose ;
- `prior_treatment` lorsque la notion a déjà été liée ou expliquée dans une sous-partie antérieure et qu’un nouveau lien serait redondant ;
- `context_sufficient` seulement lorsque le passage rend déjà le sens immédiatement intelligible, avec une justification propre à la notion.

Chaque sous-partie possède une ligne d’inventaire, même lorsqu’aucune notion spécialisée n’y est retenue. L’attestation globale `specialized_terms_linked_or_explained=true` ne suffit plus. L’inventaire reproduit l’ordre des sous-parties, nomme les notions effectivement présentes et permet de vérifier tous les liens Wikipédia rendus. Les notions voisines de même rang sont naturellement traitées de manière cohérente, mais une série n’est plus nécessaire pour déclencher la revue.

Exemples français conformes :

```mediawiki
L'Alaska a mis en place l'{{Lien Wikipédia|article=Alaska Permanent Fund}}, une forme particulière de revenu de base.
{{Lien Wikipédia|article=Basic Income Earth Network}}
{{Lien Wikipédia|article=Monnaie locale|texte-affiché=monnaie locale complémentaire}}
L'{{Lien Wikipédia|article=effet placebo}} est étudié dans certains protocoles expérimentaux.
```

Le paramètre `|texte-affiché=` est réservé à une différence lexicale ou grammaticale réelle. Pour la seule minuscule initiale exigée par la phrase, le nom passé à `|article=` peut commencer par une minuscule. L’anglais suit la même règle avec `{{Wikipedia link|article=…}}` et `|displayed-text=…`. Le lien au survol est un outil d’explication et de navigation, non une référence : toute affirmation factuelle qui exige une attribution conserve son appel `<ref>…</ref>`.

Le rendu français repose sur le modèle MediaWiki suivant, fourni par le propriétaire du projet :

```mediawiki
<span class="hover-wikipedia">[https://fr.wikipedia.org/wiki/{{{article}}} {{{texte-affiché|{{{article}}}}}}]</span>
```

Cette implémentation confirme que le paramètre `article` détermine à la fois la cible Wikipédia et, par défaut, le texte visible. Le modèle anglais `Wikipedia link` suit la convention fonctionnelle correspondante avec `article` et `displayed-text`; son code interne n’est pas imposé par la norme tant que ce comportement est respecté.

Le nombre de sous-parties et le volume documentaire dépendent de la complexité, de l’étendue du sujet et de l’abondance de la littérature disponible. Il n’existe pas de minimum universel de cinq sous-parties ni de vingt références. Le profil local peut déclarer des minima adaptés, accompagnés d’une justification non vide ; ces minima ne doivent jamais conduire à fragmenter artificiellement l’introduction ou à ajouter des sources sans apport réel. Inversement, une page portant sur une controverse abondamment documentée ne doit pas s’arrêter à une sélection symbolique ou minimale. Chaque famille applicable (bibliographie, sitographie et vidéographie) fait l’objet d’un examen séparé. Pour une page Débat ou Debate, tout paramètre documentaire optionnel dont aucune source n’est finalement retenue est entièrement omis du wikicode ; une catégorie vide n’est jamais matérialisée par une ligne `|paramètre=`. Le volume total reste proportionné à l'abondance et à la qualité de la littérature. La classification suit le contenu effectif de la ressource et non un objectif de symétrie numérique.

Chaque sous-partie substantielle contient les appels de référence inline nécessaires pour soutenir les affirmations factuelles qui exigent une attribution. Dans les introductions française et anglaise, chaque appel développé est rédigé directement en wikicode lisible à l’intérieur de `<ref>…</ref>`, sans passer par un modèle MediaWiki. Les modèles `{{Référence}}`, `{{Reference}}`, les modèles bibliographiques, sitographiques ou vidéographiques spécialisés et tout autre modèle de citation sont interdits dans le corps d’une note d’introduction. La note indique directement les éléments utiles à l’identification de la source — auteur, titre, publication ou site, date en langage naturel, pagination et lien selon le cas. Une simple notice documentaire est traitée comme une notice et non comme une phrase : elle ne se termine donc pas par un point avant `</ref>`. Le signe de ponctuation de la phrase principale vient après l’appel de note (`texte<ref>Notice sans point final</ref>.`). Un point final reste admis à l’intérieur de la balise uniquement si la note contient une véritable phrase explicative complète, et cette exception est consignée dans la revue de l’introduction. Une référence nommée peut être définie sous la forme `<ref name="…">contenu rédigé directement</ref>` puis réutilisée avec `<ref name="…" />`. Les appels français sont placés avant la ponctuation finale ; les appels anglais suivent la convention anglaise. Les balises `<references />` et `<references>` ne sont jamais ajoutées : l’affichage des notes est géré par le wiki. Les mêmes sources peuvent également figurer dans les listes documentaires structurées de la page lorsque l’appel inline attribue une affirmation précise.

Aucun nombre minimal d’appels `<ref>` n’est imposé à l’introduction dans son ensemble ni à une sous-partie particulière. Une introduction principalement définitionnelle, conceptuelle ou argumentative peut donc ne contenir aucun appel inline lorsqu’elle ne formule aucune affirmation factuelle externe nécessitant une attribution. Le contrôle porte sur l’adéquation entre les affirmations présentes et leurs sources, non sur la présence mécanique d’au moins une référence.

Avant `release_ready`, une revue humaine bilingue consigne pour chaque langue que le sujet et le périmètre sont définis, que le sens de la question est expliqué, que l’histoire et l’actualité sont traitées lorsqu’elles sont pertinentes, que chaque sous-partie apporte une information distincte et nécessaire, que la progression est logique, qu’une section technique est contextualisée et que l’introduction ne reproduit ni le graphe ni une checklist propre à un corpus pilote. Une rubrique générique sur les « enjeux », la « lecture du débat » ou les « principales lignes de contestation » est supprimée lorsqu'elle se contente d'énumérer des thèmes déjà visibles dans le graphe ou d'énoncer des conséquences évidentes sans information nouvelle.

### 7.6 Sélection de la bibliographie des pages de débat

La bibliographie d’une page Débat ou Debate constitue une sélection de référence sur l’ensemble de la controverse. Elle privilégie les livres incontournables, monographies, manuels, volumes collectifs, rapports de synthèse et articles de revue réellement panoramiques. Les articles scientifiques consacrés à une expérience, un protocole ou un résultat étroit appartiennent aux pages Argument concernées et ne sont pas accumulés dans la bibliographie générale du débat.

Chaque usage bibliographique du débat indique s’il s’agit d’une œuvre fondatrice ou d’une synthèse large, ainsi qu’une justification de sélection. Une source étroite ou dépourvue de justification est bloquante.

### 7.7 Métadonnées sitographiques et conversion des auteurs

`auteurs=` ou `authors=` n’est émis que lorsqu’une personne ou une organisation est explicitement responsable du contenu. À défaut, le paramètre est omis ; le nom du site n’est jamais recopié mécaniquement comme auteur. La vérification de l’attribution est enregistrée.

Le registre JSON conserve `authors` sous forme de liste, mais cette liste ne doit jamais être sérialisée littéralement dans le wikicode. La conversion vers MediaWiki est obligatoire : une liste d’un élément devient le texte brut de cet élément (`["L'Encyclopédie philosophique"]` devient `|auteurs=L'Encyclopédie philosophique`) ; plusieurs éléments sont séparés par une virgule suivie d’une espace (`Auteur 1, Auteur 2`) ; une liste vide entraîne l’omission du paramètre. Les crochets, guillemets et virgules syntaxiques du JSON ne sont jamais publiés.

Lorsque le titre de la page et le nom du site sont identiques, seul `site=` est conservé. Les triples identiques `page`, `auteurs` et `site` sont interdits.

Pour toute référence vidéographique YouTube, `auteurs=` / `authors=` indique le créateur ou le nom de la chaîne affiché par la plateforme. Le champ n'est pas omis lorsque cette attribution est directement visible sur la page de la vidéo. Le titre de la vidéo, la plateforme et la chaîne remplissent des fonctions distinctes : le nom de YouTube n'est pas utilisé comme auteur.

### 7.8 Incises parenthétiques dans la prose française

Dans la prose française générée, une incise explicative, une apposition ou une énumération insérée à l’intérieur d’une phrase est délimitée par des parenthèses, et non par une paire de tirets cadratins.

Exemple non conforme :

`La mesure concerne plusieurs services essentiels — l’eau, l’énergie, les transports et la santé — sans s’appliquer aux activités de loisir.`

Exemple conforme :

`La mesure concerne plusieurs services essentiels (l’eau, l’énergie, les transports et la santé) sans s’appliquer aux activités de loisir.`

Cette règle vise les tirets cadratins appariés employés comme signes de parenthèse dans les introductions, résumés et autres passages rédactionnels français. Elle n’interdit pas les traits d’union, les plages numériques, les listes MediaWiki, les titres d’œuvres cités fidèlement ni les tirets présents dans une citation reproduite comme telle.

## 8. Structures MediaWiki actives

### 7.9 Articles Wikipédia obligatoires et préservation conditionnelle des débats connexes

Toute page `Débat` française contient un paramètre `articles-Wikipédia` non vide avec au moins un sous-modèle `{{Article Wikipédia|page=…}}`. Toute page `Debate` anglaise contient de même `wikipedia-articles` avec au moins un `{{Wikipedia article|page=…}}`. Les titres exacts sont recherchés et vérifiés dans l’édition linguistique correspondante ; l’absence de résultat ne peut pas être déclarée sans recherche. Un article directement centré sur le sujet est privilégié, mais des articles de cadrage étroitement liés sont admis lorsque le titre exact du débat n’a pas de page dédiée.

Lors de la création d’une page de débat réellement nouvelle hors traduction, Wikidéb’IA ne produit pas `débats-connexes` ni `related-debates`. Lors de la modification d’une page préexistante hors protocole de retraduction, le paramètre est conservé exactement s’il existe déjà, avec sa valeur antérieure ; il reste absent s’il n’existait pas. **Exception FR→EN : pendant la traduction éditoriale d’une page française, `related-debates` est reconstruit uniquement à partir des entrées françaises de `débats-connexes` dont la page anglaise correspondante est vérifiée comme existante ; les autres sont omises et aucun nouveau débat connexe n’est inventé.**

### 8.0 Création et modification des paramètres protégés

Le manifeste de chaque page déclare `page_origin` (`new` ou `preexisting`) ainsi qu’un instantané de présence et de valeur des paramètres protégés. Pour une page nouvelle, les structures ci-dessous indiquent les valeurs générées. Pour une page préexistante, ces lignes sont conditionnelles :

- `avancement` / `progress` conserve exactement sa valeur antérieure et reste absent s’il était absent ;
- `avertissements-débat` / `debate-warnings` conserve exactement sa valeur antérieure et reste absent s’il était absent ;
- `avertissements-argument` / `argument-warnings` conserve exactement sa valeur antérieure et reste absent s’il était absent ;
- `débats-connexes` / `related-debates` conserve exactement sa valeur antérieure et reste absent s’il était absent.

Le moteur de mise à jour bloque toute opération qui modifierait l’un de ces paramètres sur une page existante.

La même distinction création/reprise s’applique aux métadonnées éditoriales non protégées : un `titre-affiché` préexistant n’est pas réécrit pour satisfaire une règle de forme réservée aux créations IA, et un mot-clé préexistant n’est pas retiré pour satisfaire un quota de création. Les corrections évidentes, les ajouts utiles et les suppressions explicitement motivées par une non-pertinence réelle restent autorisés et traçables.

**Exception de production éditoriale FR→EN :** les règles de préservation distante ci-dessus ne servent pas à choisir le contenu de la traduction. Pour produire la page anglaise, la source française prévaut et les métadonnées mappées sont traduites depuis elle. La préservation distante reste une contrainte technique distincte au moment d’une éventuelle publication.

### 8.1 Page Débat française

```mediawiki
{{Débat
|sujet=
|sujet-développé=
|avancement=Débat construit
|avertissements-débat=Débat généré par IA
|introduction={{Sous-partie
|titre=
|contenu=
}}
|articles-Wikipédia={{Article Wikipédia
|page=Article vérifié directement lié au sujet
}}
|arguments-pour={{Argument pour
|page=Titre canonique complet
|titre-affiché=Titre affiché
}}
|arguments-contre={{Argument contre
|page=Titre canonique complet
|titre-affiché=Titre affiché
}}
|rubriques=
|mots-clés=
|interlangue={{Lien interlangue
|langue=en
|page=Titre canonique anglais
}}
}}
```

Les lignes `avancement=Débat construit` et `avertissements-débat=Débat généré par IA` de cet exemple valent uniquement pour une page nouvellement créée par Wikidéb’IA. Sur une page préexistante, elles sont remplacées par la conservation exacte de l’état antérieur.

Les neuf paramètres documentaires (`bibliographie-*`, `sitographie-*`, `vidéographie-*`) sont ajoutés uniquement lorsqu’ils contiennent au moins une référence retenue. Ils sont omis lorsqu’ils seraient vides, y compris sur une page préexistante après une revue autorisée qui vide une catégorie.

Le paramètre `interlangue` dépend de l'état de traduction anglaise. Avec `translation_status.en=deferred`, il est absent du wikicode français et aucun titre anglais n'est requis. Avec un état `ready` ou `published`, il contient exactement un `{{Lien interlangue}}` visant le titre canonique anglais verrouillé. Une page anglaise peut rester momentanément absente du wiki uniquement lorsque son titre est déjà verrouillé et que l'état déclaré autorise cette préparation.

Lorsque le sujet possède un acronyme courant et non ambigu, `sujet-développé` ou `expanded-topic` l’emploie de préférence à la répétition de la forme développée. Exemple : `|sujet=Gestation pour autrui` et `|sujet-développé=l’autorisation de la GPA`. Le registre de revue indique, pour chaque langue, l’acronyme retenu ou atteste qu’aucun acronyme courant n’est applicable.

Avec `translation_status.en=deferred`, les pages anglaises sont absentes du manifeste, leurs titres peuvent être absents, nuls ou `unassigned`, et les pages françaises ne contiennent aucun lien interlangue. Après traduction, le statut passe à `ready` ou `published`, les titres anglais sont verrouillés, les pages anglaises sont ajoutées au manifeste et une reprise française peut ajouter les liens interlangues exacts.

### 8.2 Page Argument française

```mediawiki
{{Argument
|avertissements-argument=Argument généré par IA
|résumé=
|citations={{Citation
|citation=
|auteurs=
|article=
|ouvrage=
|volume=
|numéro=
|page=
|localisation=
|édition=
|lieu=
|date=
|lien=
|avertissements-citation=
}}
|références-bibliographiques={{Référence bibliographique
|auteurs=
|article=
|ouvrage=
|volume=
|numéro=
|localisation=
|page=36-37
|édition=
|lieu=
|date=
|lien=
}}
|références-sitographiques=
|références-vidéographiques=
|justifications={{Justification
|page=Titre canonique complet
|titre-affiché=Titre affiché
}}
|objections={{Objection
|page=Titre canonique complet
|titre-affiché=Titre affiché
}}
|rubriques=
|mots-clés=
|interlangue={{Lien interlangue
|langue=en
|page=Titre canonique anglais
}}
}}
```

Les lignes `avertissements-argument=Argument généré par IA` de la structure française valent uniquement pour une page Argument nouvellement créée. Une page Argument préexistante conserve exactement sa valeur antérieure ou l’absence du paramètre.

Lorsqu’une page historique contient `|débat-dédié=…`, ce paramètre est conservé exactement. Il est placé après `objections` et avant `rubriques`. Les paramètres `justifications` et `objections` peuvent être omis sur cette page frontière, même si le registre conserve des relations nécessaires au graphe général, à condition que l’omission et l’information donnée au propriétaire soient attestées dans le verrou historique. L’arrêt du parcours au débat détaillé ne permet jamais de supprimer silencieusement le paramètre.

### 8.3 English Debate page

```mediawiki
{{Debate
|topic=
|expanded-topic=
|progress=Constructed debate
|debate-warnings=Debate generated by AI
|introduction={{Subsection
|title=
|content=
}}
|wikipedia-articles={{Wikipedia article
|page=Verified article directly related to the topic
}}
|pro-arguments={{Pro argument
|page=Full canonical title
|displayed-title=Displayed title
}}
|con-arguments={{Con argument
|page=Full canonical title
|displayed-title=Displayed title
}}
|pro-bibliography=
|con-bibliography=
|bibliography=
|pro-webliography=
|con-webliography=
|webliography=
|pro-videography=
|con-videography=
|videography=
|sections=
|keywords=
}}
```

The `progress=Constructed debate` and `debate-warnings=Debate generated by AI` lines apply only to a genuinely new Debate generated from scratch. **They do not apply to an English page produced as a translation of an existing French Debate:** in that workflow, `progress`, `title-warnings` and `debate-warnings` are translated from the exact French source values according to the active FR→EN mapping, and an absent source parameter remains absent. The editorial translation ignores any pre-existing English target page as a source of content.

### 8.4 English Argument page

```mediawiki
{{Argument
|argument-warnings=Argument generated by AI
|summary=
|quotes={{Quote
|quote=
|authors=
|article=
|work=
|volume=
|issue=
|page=
|location=
|publisher=
|place=
|date=
|link=
|warnings=AI-translated quote
}}
|bibliography={{Bibliographical reference
|authors=
|article=
|work=
|volume=
|issue=
|location=
|page=36-37
|publisher=
|place=
|date=
|link=
}}
|webliography=
|videography=
|justifications={{Justification
|page=Full canonical title
|displayed-title=Displayed title
}}
|objections={{Objection
|page=Full canonical title
|displayed-title=Displayed title
}}
|sections=
|keywords=
}}
```

Les pages anglaises ne contiennent pas de lien interlangue.

Dans une traduction FR→EN, `argument-warnings=Argument generated by AI` n'est pas ajouté par défaut au seul motif que le fichier anglais vient d'être généré. `title-warnings` et `argument-warnings` sont traduits uniquement à partir des valeurs françaises présentes selon la table normative active ; un paramètre absent en français reste absent en anglais.

## 9. Suppression des paramètres de date de création

Décision du propriétaire du 24 novembre 2026 : les paramètres `date-création` et `creation-date` sont supprimés des quatre modèles. Aucun nouveau corpus ne doit produire de date de création de page, ni dans le wikicode ni dans ses métadonnées de génération. Le jour civil de publication ne déclenche plus de changement de plan.

Les anciennes archives et les reçus signés restent inchangés. Leurs dates ne constituent plus que des données historiques ; elles ne doivent pas être réintroduites sur les wikis. Les plans de publication historiques qui imposent une date doivent être reconstruits et autorisés avant exécution. Les dates documentaires des sources, les horodatages techniques, les preuves de révision et les journaux de publication ne sont pas concernés.

## 9.1 Préservation automatique des pages historiques lors d’une reprise

Lorsqu’une page du nouveau corpus correspond à une page distante attestée dans l’état publié et que la révision distante courante correspond encore exactement à cet état, le kit construit un contenu effectif dérivé. Il y recopie uniquement les paramètres de cycle de vie protégés de la page distante : avertissements, avancement et paramètres historiques explicitement énumérés par le profil de rendu. Le reste du contenu provient du nouveau corpus validé. Si la révision distante diffère uniquement par le retrait exact du paramètre obsolète depuis le dernier état attesté, cette suppression peut être reconnue sans restaurer le paramètre. Toute autre modification concurrente demeure soumise aux contrôles ordinaires.

Cette réconciliation ne constitue ni une importation de modifications humaines, ni une normalisation silencieuse du corpus source. Le fichier original reste inchangé ; le plan signé référence le fichier effectif dérivé, son empreinte et le détail des valeurs préservées. Toute divergence distante non attestée reste classée `manual_review`.

Une page existante sans avertissement IA ne reçoit donc pas rétroactivement `Argument généré par IA` ou `Débat généré par IA`. Une valeur historique particulière, par exemple un avertissement éditorial ou un avancement antérieur, est conservée. Les pages réellement nouvelles reçoivent au contraire les valeurs de création prévues par le profil actif.

Pour une suppression, l’absence de marqueur Wikidéb’IA reste bloquante par défaut. Elle peut être levée uniquement pour une page historique lorsque le registre de migrations déclare explicitement son retrait, que le titre n’appartient à aucun autre débat connu et que la révision ainsi que l’empreinte distantes correspondent exactement à l’état attesté. L’exécuteur revérifie ces conditions immédiatement avant la suppression.

## 10. Workflow correctif et non-régression

Le cycle correctif autorisé est :

```text
release_ready
  → corrective_in_progress
  → corrective_blocked (si une anomalie subsiste)
  → corrective_in_progress (après reprise)
  → release_ready (validation complète uniquement)
```

Le Work porte le type `corrective_prepublication`. Il crée un instantané initial, des handoffs correctifs nouveaux et une matrice de couverture. Les handoffs historiques ne sont jamais réécrits ; leurs empreintes décrivent l’état d’entrée de leur Work original. Chaque nouvelle reprise ajoute un handoff final propre à sa révision vers W11.

Une seule norme consolidée est active à la racine du dossier `normative/`. Toute version consolidée antérieure est déplacée dans `normative/history/`. Les documents spécialisés — structures, profils, workflow, catalogue d’exigences et matrice de traçabilité — doivent pointer vers la même révision active et ne peuvent conserver une règle remplacée comme règle active.

Le retour à `release_ready` exige :

- zéro erreur bloquante ;
- zéro avertissement non résolu ;
- revue éditoriale humaine enregistrée ;
- cohérence bilingue ;
- manifeste de libération cohérent ;
- preuve que chacun des deux checkpoints français autorisés (graphe/titres puis contenu/classification) possède son plan et son reçu, et qu’aucune autre écriture distante n’a eu lieu ;
- audit de non-régression comparant la norme, le kit, les pages, les invariants, les fichiers et les exigences cumulées ;
- kit de publication produit séparément, inclus dans la livraison complète et non exécuté.

Aucune reprise corrective ne peut supprimer silencieusement une fonction, un contrôle, un test, un rapport, un fichier normatif ou une étape du kit. Une suppression intentionnelle exige une décision explicite, une justification et une trace dans le changelog.

## 11. Validateur

`validate` est strictement en lecture seule. Toute écriture locale dérivée passe par une commande distincte, explicitement demandée, telle que `recalc --write`. Le validateur n’effectue aucune connexion au wiki.

Les contrôles sont répartis entre schémas JSON, cohérence et fichiers, graphe, lots, sources, wikicode, bilinguisme, workflow, contrôles éditoriaux automatisables et revue humaine obligatoire.

Le validateur courant conserve les contrôles éditoriaux cumulés indépendamment de la révision normative historique déclarée et maintient séparément la compatibilité technique de lecture avec les formats historiques annoncés. Chaque règle binaire nouvelle possède au moins un test positif et un test négatif. Les nombres de tests, exigences et fichiers déclarés dans les reçus doivent correspondre aux éléments réellement livrés.

Les longueurs indicatives des résumés restent des guides éditoriaux et non des quotas. Une distribution systématiquement courte déclenche une information de revue humaine, sans provoquer de remplissage artificiel. La revue doit confirmer que chaque page demeure autonome, informative et fidèle à un seul nœud.

## 12. Publication W11

Pendant une reprise W10 corrective, deux frontières françaises de publication sont prévues avant toute traduction : (1) après validation complète du graphe et des titres canoniques/affichés, publication du seul delta structurel et de titres, incluant les déplacements, fusions/redirections et suppressions validés ; (2) après validation du contenu français, publication du seul delta de contenu et de classification, incluant rubriques, mots-clés, introduction, résumés et documentation. Aucune traduction anglaise ne commence avant le second reçu. Le kit W11 reste livré sans exécution et sans secret pour la publication bilingue finale.

Avant toute publication, W11 doit :

1. exécuter une simulation globale déterministe et signer le plan par SHA-256 ;
2. vérifier en lecture seule la compatibilité réelle des modèles publics ;
3. refuser de poursuivre si un paramètre normatif requis n’est pas accepté ;
4. effectuer comme première écriture distante un test sur l’unique page Débat française canonique du plan ;
5. exiger que cette page soit absente lors de la simulation, la créer avec `createonly`, relire la révision exacte et produire un reçu machine signé ;
6. avant toute autre écriture, recharger le même plan et le reçu, vérifier leurs empreintes, puis confirmer que la page Débat est toujours à la révision attestée avec le même contenu, le même résumé et la même balise ;
7. après ce test, créer les autres pages françaises, puis les pages anglaises, la page Debate précédant toutes les pages Argument dans la phase anglaise ;
8. réauthentifier et vérifier l’identité à chaque phase et avant chaque écriture ;
9. utiliser `assert=user` et `assertuser` ;
10. classifier chaque titre distant comme `absent`, `equivalent_existing`, `collision` ou `manual_review` ;
11. ne jamais écraser une page existante par défaut : une page équivalente est ignorée et une collision bloque le plan ; la page Débat française préexistante bloque spécifiquement le test ;
12. comparer les contenus local et distant par SHA-256 et enregistrer les identifiants de révision ;
13. utiliser `createonly` pour chaque création canonique ; une mise à jour interlangue distincte n’est admise que par le workflow fonctionnel prévu après préparation de la langue cible et reste interdite tant que cette traduction est `deferred` ;
14. relire chaque page après écriture, vérifier son contenu et enregistrer la nouvelle révision ;
15. s’arrêter sur perte de session, collision, divergence, droits insuffisants ou révision concurrente ;
16. ne créer aucune sous-page utilisateur pour le test de publication ;
17. écrire des journaux JSONL privés de simulation, test et import ;
18. reprendre uniquement à partir du couple titre + SHA-256 de contenu et de révisions réelles vérifiées ;
19. refuser l’exécution si le corpus, le validateur, la norme ou le plan ont changé depuis la simulation ;
20. charger pour le test et la publication le fichier de plan signé produit par la simulation, sans le reconstruire silencieusement ;
21. incorporer au plan les empreintes du manifeste, du manifeste de libération et du validateur, puis les revérifier avant toute écriture ;
22. reconnaître comme état de reprise valide la page Débat française créée par le test seulement si son reçu reste valide et sa révision courante inchangée ;
23. exiger pour la suite de la publication le reçu machine du test de la page Débat canonique, lié au plan signé et revérifié à distance immédiatement avant toute autre écriture.

Les fichiers d’authentification, cookies, secrets et identifiants privés ne sont jamais inclus dans une archive publique.

### 12.1 Résumés individualisés des reprises de corpus validés

Lorsqu’une nouvelle archive de corpus est fournie à la commande de reprise distante (`update --archive`) puis effectivement exécutée après validation du plan, **chaque opération mutante reçoit un résumé MediaWiki individualisé décrivant la modification réelle de la page**. Cette exigence vaut pour les créations, mises à jour de contenu, renommages, transformations en redirection et suppressions. Un résumé générique tel que `Corrections` n’est pas émis par un nouveau plan de reprise.

Pour une mise à jour de contenu, le résumé est calculé à partir du différentiel réel des paramètres de premier niveau de la page et regroupe les changements par fonction éditoriale (par exemple introduction, résumé, références, justifications, objections, rubriques ou mots-clés). Les cas possédant déjà une convention plus précise conservent cette convention : notamment l’ajout interlangue français et la création d’une traduction anglaise lorsque le chemin de publication correspondant s’applique.

Le plan signé porte un contrat explicite de résumés individualisés, ainsi que la politique et le texte attendus pour chaque mutation. L’exécuteur **recalcule** le résumé attendu à partir du contenu signé et de l’état distant relu immédiatement avant l’écriture ; une divergence bloque l’opération. Après écriture, la révision est relue et le contenu, le résumé, la balise et l’identifiant de révision sont vérifiés. Les anciens plans déjà signés avant l’introduction de ce contrat restent lisibles selon leur format historique, sans autoriser un nouveau plan à revenir au résumé générique.

Les deux checkpoints français réutilisent le moteur de reprise signé. Le premier est construit depuis le wikicode importé et n’autorise que les changements de structure et de titres validés : les rubriques, mots-clés, résumés, introduction et références restent identiques à la source distante. Le second part obligatoirement de l’état publié attesté par le premier et n’autorise plus de renommage, redirection ou suppression ; il applique les rubriques, mots-clés, la documentation et les autres contenus effectivement ouverts par la revue. **Dans une reprise de pages préexistantes, il conserve exactement les résumés historiques et l’introduction historique en l’absence d’autorisation propriétaire ; il publie en revanche les deltas historiques explicitement autorisés et scellés pendant `fr_content_review`.** Un résumé historiquement absent reste absent sauf création nominativement autorisée. Les deltas autorisés d’introduction/résumé appartiennent au même checkpoint n°2 et ne créent aucune troisième frontière de publication. Chaque mutation reçoit le contrat de résumé individualisé, la garde de révision, la balise `chatgpt` et la relecture post-écriture. Les décisions structurelles prises pendant une boucle de correction sont d’abord appliquées localement et ne sont écrites à distance qu’au premier checkpoint.

## 13. Profils locaux et invariants propres à un corpus

Les nombres de nœuds, relations, occurrences, lots et pages, les dates correctives, les chemins de rapports et les Work particuliers sont des données locales. Ils sont déclarés dans le manifeste, le profil de contrôle ou les rapports du corpus concerné. Ils ne deviennent jamais des constantes de la norme, du validateur ou du kit génériques.

Une reprise corrective conserve les invariants déclarés par son paquet et documente toute migration autorisée. Le statut local `release_ready` n’implique pas l’autorisation de publier : le champ de publication reste fermé jusqu’à la validation complète, au préflight et au test canonique de la page Débat W11.

## 14. Renforcement éditorial cumulatif

Avant `release_ready`, le corpus doit présenter :

1. zéro titre canonique ou affiché contenant une ellipse, une troncature grammaticale ou des guillemets non conformes ;
2. zéro lettre initiale résiduelle issue d’une suppression d’article ;
3. concordance exacte de tous les titres affichés entre registre, relations, agrégats et fichiers canoniques ;
4. pour toute page nouvelle, deux à quatre mots-clés nominaux issus du vocabulaire contrôlé bilingue ; pour une page préexistante, préservation des mots-clés historiques sauf non-pertinence claire explicitement justifiée, avec correction de graphie et ajouts pertinents autorisés ;
5. zéro mot-clé français non traduit dans la liste anglaise ;
6. vocabulaire thématique évalué à l’échelle du wiki, sans exigence de répétition dans le débat courant ;
7. revue page par page de la pertinence des mots-clés ;
8. équivalence substantielle des résumés bilingues ;
9. appels de référence inline placés sur les affirmations factuelles qui nécessitent une attribution, sans quota mécanique par sous-partie ;
10. maintien de tous les invariants verrouillés du graphe ;
11. recalcul explicite de toutes les empreintes de fichiers et, si nécessaire, de l’empreinte structurelle ;
12. absence d’écriture distante non autorisée ; seuls les deux checkpoints français graphe/titres puis contenu/classification sont admis avant traduction, avec plans et reçus signés ;
13. audit de non-régression des normes, du validateur et du kit W11 ;
14. pour toute reprise de pages préexistantes, `preserved` impose la concordance exacte avec la provenance historique, tandis que `authorized_change` impose la concordance exacte avec la valeur finale autorisée et sa portée scellée ; l’absence historique d’un résumé reste une absence sauf création nominativement autorisée.

Le paquet déclare dans son manifeste les chemins du vocabulaire contrôlé, du registre individuel, des rapports requis et du handoff correctif courant. Le validateur ne déduit jamais ces chemins d’un sujet, d’un numéro de Work ou d’une rubrique particulière. Il ne peut jamais bloquer un mot-clé au seul motif qu’il n’apparaît qu’une fois dans le débat courant.

## 15. Cohérence des livrables et garde-fous de publication

Les archives de normes, du validateur et du kit comportent un manifeste SHA-256 exhaustif. Tout fichier livré, y compris un manifeste historique placé dans un sous-dossier, est soit déclaré avec sa taille et son empreinte, soit explicitement exclu par un chemin précis. Le reçu externe indique des nombres exacts et reproductibles.

La configuration de publication finale exécute toutes les portées applicables du validateur courant, notamment `wikicode` et `editorial`. Les deux checkpoints français sont des cas spécialisés : le checkpoint graphe/titres valide le corpus français de structure sans appliquer la classification ni le contenu encore en revue ; le checkpoint contenu/classification réutilise ensuite les verrous français complets. Tous deux maintiennent `translation_status.en=deferred`, sans lien interlangue prématuré ni exigence bilingue finale.

La première écriture canonique de W11 est le test de l’unique page Débat française. La page doit être absente dans le plan et est créée avec `createonly`. Son reçu machine est lié au plan signé, au titre canonique, au fichier local, au contenu relu, à la révision distante, à l’identité vérifiée, au résumé et à la balise de modification. Avant toute autre écriture, le kit recharge ce reçu, en vérifie l’empreinte et confirme que la page courante reste exactement à la révision attestée. Aucune sous-page utilisateur n’est créée.

Les exemples, guides et listes de contrôle livrés avec la norme doivent eux-mêmes respecter la règle active : toute page française d’exemple contient son unique `{{Lien interlangue}}`, et aucun exemple actif ne décrit une phase tardive d’ajout interlangue.

## 16. Livrables minimaux d’une reprise prépublication

La livraison complète contient au minimum :

- le corpus bilingue `release_ready` et son reçu ;
- la norme consolidée active et son changelog ;
- le validateur aligné et sa suite de tests ;
- le kit W11 aligné, non exécuté, et ses tests ;
- un paquet de revue des pages ;
- l’audit de non-régression ;
- les reçus SHA-256 de chaque archive.

La présence de ces éléments est vérifiée avant livraison. Leur absence constitue une régression bloquante.

## 17. Validation différentielle et convergence sémantique

### `established-name=` : recherche propre à la langue anglaise

`established-name=` fait l’objet d’une recherche documentaire propre à la littérature anglophone. Il n’est jamais obtenu par traduction mécanique de `nom-consacré=` ; la forme syntaxique attestée et la portée exacte du raisonnement doivent correspondre. En cas de doute, le paramètre est omis.

La source française validée est autoritative pendant la traduction. La traduction distingue explicitement trois dimensions : `target_page_origin` / `page_origin`, qui décrit le cycle de vie technique de la page cible ; `source_page_origin`, qui décrit la provenance éditoriale de la page française autoritative (`new` ou `preexisting`) ; et, lorsque le champ le requiert, sa provenance propre (`historical_existing`, `historical_absent`, `authorized_change`, `ai_generated`, etc.). Le fait qu'une page anglaise soit techniquement `new` ne requalifie jamais comme création IA le contenu historique français qu'elle traduit. Les quotas et préférences de génération suivent la provenance de la source ou du champ ; les contrôles structurels, de qualité intrinsèque, de fidélité et d'intégrité restent applicables selon leur nature.

La source française validée est autoritative pendant la traduction. Les titres canoniques, titres affichés, résumés et champs Debate font l’objet d’une comparaison structurée du sujet, prédicat, polarité, modalité, attribution, quantification, temporalité, conditions, causalité, concessions et portée. Les marqueurs automatiques sont des signaux de revue et ne réécrivent jamais le texte. Les preuves de revue sont liées par SHA-256 au contenu exact. Deux passes finales indépendantes de familles méthodologiques distinctes doivent conclure à zéro nouvelle erreur certaine sur la même empreinte avant scellement.

## 18. Identité documentaire et inventaire de release

Un registre documentaire global déterministe sépare l’identité canonique d’une ressource de ses usages localisés. DOI normalisé, URL canonique puis empreinte bibliographique servent à rapprocher les ressources ; des métadonnées incompatibles pour une même identité et une même langue sont bloquantes. Toute release contient un inventaire déterministe du contenu et ses empreintes, recalculés après extraction fraîche de l’archive exacte.

## 19. Métadonnées de publication des traductions anglaises

Pour une création anglaise FR→EN, le résumé de modification est individualisé à partir du titre français verrouillé, sous la forme `Translation of the French page: [[:fr:X|X]]`, les balises `chatgpt` et `translated-fr` sont appliquées. Une nouvelle page anglaise ne transporte jamais `|initialisation=`/`|initialization=` depuis la page française : `initialization` n’est pas projeté depuis le wiki français. L’ajout interlangue français ultérieur utilise le titre anglais verrouillé et préserve les autres paramètres historiques.

## 20. Compatibilité des artefacts

Chaque format opérationnel possède un identifiant de schéma stable. Le validateur publie un rapport `wikidebia-validator-report-1.0`. Le kit publie les nouveaux plans de publication sous `wikidebia-publication-plan-1.0` et normalise les anciens labels de plans qui incorporaient le numéro du kit vers ce schéma à la frontière d’entrée. Un artefact ancien reste accepté tant que son schéma est supporté ; un schéma inconnu est refusé même si son producteur est récent.

## 21. Release canonique unique

La release standard contient à sa racine `WIKIDEBIA_SOURCE_ACTIVE.md`, `VERSIONS.json`, le manifeste SHA-256, le rapport de validation, le README de release et les trois ZIP de composants. Elle contient également les rapports d’audit et de non-régression. Le workflow standard ne requiert aucun bundle minimal séparé. La construction est déterministe et la preuve finale porte sur le ZIP exact après réextraction et revalidation.

## 22. Orchestration des interventions éditoriales externes

Le workflow utilisateur normal applique le principe de **progression mécanique jusqu’au prochain point éditorial**. Lorsqu’une succession d’étapes ne nécessite aucune décision de contenu, le kit les exécute automatiquement dans l’ordre déjà défini par les primitives auditées. L’utilisateur n’a pas à connaître les chemins de `.state/`, les fichiers JSON internes, les empreintes de confirmation ni les sous-commandes `--prepare`, `--finalize` et `--apply`. Ces primitives restent disponibles sans changement pour le debug, l’audit, les tests et les usages avancés.

La validation précédant un point de revue ne doit jamais rendre ce point inaccessible à cause d’une anomalie que cette revue est précisément destinée à corriger. En particulier, avant le verrouillage des métadonnées françaises ou anglaises, les défauts de forme ou d’autonomie référentielle des titres canoniques ou affichés déjà importés sont des **signaux éditoriaux différés** : ils sont signalés mais ne bloquent pas l’initialisation du graphe ni sa transmission à ChatGPT. Les schémas structurels d’entrée ne doivent pas réintroduire ces contraintes éditoriales comme erreurs de schéma avant ce verrou ; ils contrôlent alors seulement la structure et les contraintes syntaxiques indépendantes de la revue. Les défauts éditoriaux de titre redeviennent bloquants dès que le verrou de métadonnées de la langue concernée existe. Cette différenciation ne s’applique pas aux incohérences structurelles du graphe (cycle, auto-relation, relation ou occurrence invalide, collision d’identité, empreinte incohérente), qui restent bloquantes à tout stade applicable.

Lorsqu’une validation mécanique rencontre une erreur réellement bloquante avant le prochain point éditorial, l’orchestrateur doit conserver les diagnostics détaillés, afficher les principaux codes et messages, et produire automatiquement dans `outgoing/` un paquet de diagnostic minimal sans secret. L’utilisateur ne doit pas avoir à rechercher lui-même le rapport interne sous `.state/`. Une relance de la même commande après correction du kit ou de la donnée reprend la validation et poursuit le workflow sans recréer inutilement les étapes déjà valides.

Lorsqu’une intervention éditoriale externe devient nécessaire, le kit crée un paquet de revue au schéma stable `wikidebia-chatgpt-review-package-1.0` dans `outgoing/` et s’arrête. Ce paquet :

1. identifie le débat, le Work éventuel, le type de revue et la provenance locale exacte ;
2. sépare strictement les fichiers modifiables sous `editable/` des sources de contexte en lecture seule sous `context/` ;
3. ne contient que les fichiers explicitement autorisés pour la revue concernée ;
4. exclut les secrets, authentifications, cookies, configurations privées, états de publication et fichiers sans utilité éditoriale ;
5. lie chaque fichier de contexte à une empreinte SHA-256 et lie le manifeste à l’instance locale du workflow ;
6. fournit des instructions lisibles et une commande unique de réimport.

Le dossier `outgoing/` est une zone locale sensible au même titre que `incoming/`, `.state/`, `corpus/` et `private/` : il est exclu de Git et ne peut jamais être ajouté à un paquet générique de sources.

Le ZIP corrigé rendu par ChatGPT est placé dans `incoming/`. La commande utilisateur normale est `./wikidebia review-import` : lorsqu’un seul ZIP de revue valide est présent, il est sélectionné automatiquement d’après son `REVIEW_PACKAGE.json`, indépendamment de son nom de fichier. S’il existe plusieurs ZIP de revue, la commande bloque et indique `./wikidebia review-import <debate_id>` ; le sélecteur est l’identifiant interne du débat, jamais le nom du ZIP. Plusieurs ZIP correspondant au même `debate_id` restent ambigus et doivent être désambiguïsés par retrait/archivage du doublon. Les ZIP qui ne sont pas des paquets de revue ChatGPT ne sont pas candidats à cette commande. Après succès, le ZIP consommé est archivé ; après échec il reste dans `incoming/` pour reprise.

La commande de réimport vérifie le schéma, l’identité du débat et du Work, l’identifiant du paquet attendu, l’empreinte du manifeste, l’intégrité des fichiers de contexte, l’absence de fichiers supplémentaires, l’absence de liens ou chemins ZIP dangereux et l’immuabilité locale depuis la préparation. Un paquet provenant d’un autre corpus, d’un autre Work, d’une ancienne revue ou dont le contexte a changé est refusé.

Après installation transactionnelle des seuls fichiers `editable/`, la primitive de finalisation correspondante est exécutée. Le paquet de **revue du graphe** couvre conjointement placements/relations, décisions structurelles, titres canoniques et titres affichés. Le réimport approuvé de ce paquet unique déclenche immédiatement le premier checkpoint français. Après `fr_content_review`, qui comprend désormais aussi rubriques et mots-clés, `review-import` déclenche le second checkpoint français. Si le préflight échoue avant écriture, la transaction locale est restaurée. Dès qu’une exécution distante a commencé, l’état local scellé, le plan et les reçus sont conservés pour une reprise idempotente ; la traduction anglaise n’est jamais préparée tant que cette publication n’est pas réussie ou attestée `no_changes`. En cas de succès, les confirmations SHA-256 requises par les primitives internes sont résolues automatiquement à partir de leurs reçus, puis le workflow reprend jusqu’au prochain point éditorial.

L’orchestration couvre au minimum : revue combinée du graphe, des placements et des titres canoniques/affichés ; revue française de contenu incluant rubriques, mots-clés et documentation, **avec introduction et résumés historiques préservés par défaut, suggestions possibles et édition limitée aux deltas couverts par une décision propriétaire explicite et scellée**, l’absence historique restant une absence sauf création nominativement autorisée ; recherche d’appellations consacrées lorsqu’elle appartient au registre de la phase ; traduction et documentation anglaises ; recherche d’`established-name=` ; et deux passes indépendantes de convergence sémantique. Toute nouvelle phase nécessitant une décision éditoriale externe doit s’intégrer au même contrat de paquet plutôt que réintroduire une manipulation manuelle de fichiers internes.

Lors de la finalisation de `fr_content_review`, `data/sources_working.json` est contrôlé directement contre le vocabulaire documentaire du registre final, notamment `document_kind`. Une valeur hors enum est refusée à ce stade, avant projection vers `data/sources.json` et avant tout préflight de publication ; le workflow ne doit pas reporter cette erreur à une validation structurelle ultérieure.


Lorsqu’une revue du graphe retourne `decision=rejected`, ce résultat est **non promouvable**. L’orchestrateur ne peut ni passer à `graph_validated`, ni appeler la promotion, ni ouvrir le Work éditorial suivant. Il enregistre le rejet et ses `blocking_issues`, prépare automatiquement une phase externe `graph_correction` au schéma `wikidebia-graph-correction-1.0`, puis s’arrête sur le paquet ChatGPT correspondant. La correction ne modifie que la structure encore déverrouillée du graphe : parenté des occurrences, relation `justification`/`objection`, branche des racines, ordre et choix de l’occurrence primaire. Le kit reconstruit ensuite mécaniquement les relations, profondeurs, branches, indicateurs `render_children`, compteurs dérivés et projection du graphe, puis exécute une validation structurelle. Une correction invalide est restaurée transactionnellement et reste au point de correction. Une correction valide prépare obligatoirement **une nouvelle revue complète du graphe** ; elle ne vaut jamais approbation implicite. La promotion n’est accessible qu’après le retour `approved` de cette nouvelle revue. Les rejets successifs répètent ce cycle autant de fois que nécessaire.

Lorsqu’une revue du graphe rejetée contient déjà des **décisions structurelles explicites et exécutables**, une voie d’application directe peut remplacer le paquet intermédiaire `graph_correction`, uniquement sur demande explicite de l’utilisateur. Les actions admises sont : retrait d’une occurrence et du nœud devenu sans occurrence ; fusion d’un doublon vers un nœud conservé ; déplacement d’une occurrence ; changement de relation ou de branche. Une formulation libre ou ambiguë ne peut jamais déclencher une écriture distante. Les paquets historiques dépourvus de champ structuré ne sont exécutables que si une formulation propriétaire explicitement reconnue identifie sans ambiguïté le nœud, l’occurrence et, pour un doublon, la destination conservée.

Pour un retrait, le modèle de relation correspondant (`Argument pour`, `Argument contre`, `Justification` ou `Objection`) est retiré de la page mère avant le traitement de la page enfant. Lorsqu’il s’agit d’un doublon, la page enfant n’est normalement pas supprimée : son contenu est remplacé intégralement par `#REDIRECTION [[Titre canonique conservé]]`. Lorsqu’il ne s’agit pas d’un doublon et qu’aucune autre occurrence ni sous-branche ne dépend du nœud, la page peut être supprimée. Toute suppression d’un nœud possédant plusieurs occurrences ou des enfants est refusée tant qu’une décision plus précise n’a pas été fournie.

Chaque page distante modifiée reçoit un **résumé MediaWiki individualisé décrivant la modification réelle**. Le résumé d’une page mère dont un doublon est retiré mentionne obligatoirement la page conservée sous forme de wikilien `[[Titre canonique conservé]]`. Les résumés génériques tels que `Corrections` ne sont pas utilisés pour ces opérations. Les écritures portent la balise `chatgpt` et leur contenu, résumé, balise et révision sont relus après écriture.

Avant la première écriture distante, le kit construit et valide dans une copie temporaire le graphe exact résultant des décisions, puis effectue un préflight distant complet de toutes les pages concernées contre les révisions et empreintes du snapshot importé. L’ordre distant est : modifications des pages mères, créations de redirections, suppressions effectives. Chaque page est relue immédiatement avant sa mutation pour détecter une concurrence. Après succès, le corpus local est mis à jour, le graphe retourne à `graph_draft` et une **nouvelle revue complète** est automatiquement préparée ; l’exécution des décisions n’équivaut jamais à une approbation ni à une promotion.

Lorsqu’une passe de convergence détecte une erreur certaine, le workflow n’applique pas la traduction. Il rouvre proprement la revue anglaise sur la même base française verrouillée, conserve les constatations de convergence comme contexte, produit un nouveau paquet de correction et recommence ensuite les deux passes indépendantes sur la nouvelle empreinte sémantique. Deux passes propres de familles distinctes restent obligatoires avant le rendu et la libération.

Une commande d’orchestration de haut niveau pilote l’ensemble de ce cycle. Elle peut réutiliser un snapshot `graph-extract` déjà présent ; sinon elle effectue l’extraction en lecture seule. Le premier checkpoint publie graphe et titres ; le second publie rubriques, mots-clés et contenu. Après le second reçu seulement, la traduction peut commencer. Après la dernière revue convergée, le rendu et la construction du corpus bilingue `release_ready` restent mécaniques ; la publication bilingue finale demeure une étape distincte.

## 1.2.87 — 13 août 2026 — omission canonique des paramètres optionnels vides

- réaffirme la règle atomique déjà active selon laquelle tout paramètre optionnel sans contenu pertinent est omis du wikicode ;
- supprime la formulation contradictoire qui demandait de conserver vides les neuf paramètres documentaires d’une page Débat / Debate ;
- précise qu’une catégorie documentaire devenue vide après une revue autorisée disparaît entièrement au lieu d’être rendue sous la forme `|paramètre=` ;
- conserve séparément la provenance historique de présence pour l’audit, sans lui donner d’effet sur le rendu ;
- exige que le préflight distingue l’omission canonique d’un paramètre optionnel géré de la suppression non autorisée d’un paramètre protégé, inconnu ou hors contrat.

## 1.2.88 — 21 août 2026 — page Debate anglaise publiée avant les Arguments

- consacre la décision explicite du propriétaire : lors de la première publication anglaise finale, la page `Debate` est créée avant toute page `Argument` encore absente ;
- remplace la règle active contradictoire qui imposait `Argument` avant `Debate` dans cette phase ;
- conserve l’ordre des autres phases, les garde-fous de publication sans dépendance au jour civil ;
- lorsqu’une publication a déjà commencé sous l’ancien ordre, les pages déjà créées restent intactes et un plan successeur audité place `Debate` avant les seules créations `Argument` restantes.

## Changelog normatif

Source interne : `norms/normative_reference/01_normes/CHANGELOG_NORMATIF.md`  
SHA-256 : `86d74de19fee2600fd781f979c77de74a672bd812998e5ded1f2f713d7e339b6`

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

## État actif du validateur

Source interne : `validator/README.md`  
SHA-256 : `7496fee45a5c399a5d937ba977d589a031193b7ebb8179f45d759c83dcea3ea3`

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

## Changelog du validateur

Source interne : `validator/CHANGELOG.md`  
SHA-256 : `ca7446ed155d7c7c74172b88a144b0ec8cc4b8a2881d3f395c721c38abb9ada1`

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

## État actif du kit

Source interne : `kit/README.md`  
SHA-256 : `55f9fff29a1aaf637b0523ac23183ca6b7a426480720f6510d18c9a0125d9d45`


## Publication finale préparée, sans écriture automatique

Le workflow termine la convergence, le rendu et la release, construit en lecture seule les plans EN/FR signés et s'arrête à `publication_prepared`. L'utilisateur examine les rapports sous `.state/final-publication/<debate_id>/<work_id>/` et confirme explicitement le préflight :

```bash
./wikidebia workflow-publish <debate_id> --confirm-preflight-sha256 <sha256>
```

Cette commande recharge les plans signés, vérifie à nouveau les cibles distantes et refuse les changements concurrents. Un reçu de reprise doit rester lié au même préflight. La reprise d'une modification interlangue française dont `chatgpt` manque ne crée pas une nouvelle révision : elle ne rétablit la balise que sur une révision exacte attestée (parent, auteur, résumé, contenu et révision courante), avec droit `changetags` vérifié.

# Wikidéb’IA Kit 2.16.47

La réconciliation accepte désormais l’adoption explicite d’un Work local déjà
`release_ready` lorsque le workflow historique est resté bloqué avant toute
attribution de `work_id`. La commande `workflow-reconcile --work-id WORK`
vérifie le workspace, le release-copy et le reçu de release sans accès distant,
puis ouvre une phase dédiée. La relance ordinaire du workflow passe ensuite par
les deux checkpoints français normaux et s’arrête de nouveau à `release_ready`
avant toute publication finale. Aucun reçu n’est synthétisé.

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

Il intègre également les mécanismes de publication déjà utilisés sur les wikis : résumés MediaWiki individualisés, balises `chatgpt` + `translated-fr`, rattrapage audité de `translated-fr`, reprise `--interlanguage-only`, relecture bornée des balises, résolution sûre de la révision de création, `nom-consacré` / `established-name`, absence d’`initialization` sur une nouvelle traduction anglaise et absence des paramètres de date de création devenus obsolètes.

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

## Changelog du kit

Source interne : `kit/CHANGELOG.md`  
SHA-256 : `f8eac6ec178e5eaee37dcb98af65148f20d777a21e952b1f0b0729b792642e08`

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

## Guide de publication

Source interne : `kit/GUIDE_PUBLICATION.md`  
SHA-256 : `d940142222b9a9516b976902ff8cfc6fe7db0895bf64d53b825df152189d4b67`

# Guide de publication et de reprise Wikidéb’IA 2.15.9

## Extraire le graphe d'un débat existant

```bash
./wikidebia graph-extract "Dieu existe-t-il ?"
```

L'extraction est en lecture seule et écrit par défaut dans `.state/graph-extract/dieu_existe_t_il/`. Relancer la même commande réutilise le cache par page. `--force-refresh` force une nouvelle lecture distante. Le ZIP audité contient le graphe, les inventaires CSV, les rapports et le snapshot du wikicode.


## Comparer un corpus final sans l’exécuter

```bash
./wikidebia corpus-workspace-remote-compare <debate_id> \
  --work-id <work_id> \
  --confirm-release-sha256 <empreinte_de_release-copy> \
  --scope all
```

Cette commande est distincte de `update --dry-run` : elle part du workspace et de sa `release-copy/`, conserve un dossier de comparaison immuable et n’offre aucune voie d’exécution. Le plan produit doit être repris explicitement par une phase ultérieure.


## Revoir puis exécuter un plan du workspace

Après la comparaison et la revue formelle, préparer le préflight :

```bash
./wikidebia corpus-workspace-plan-execute <debate_id> \
  --work-id <work_id> \
  --comparison-id <comparison_id> \
  --prepare \
  --confirm-acceptance-sha256 <empreinte>
```

Puis exécuter uniquement après examen de ce préflight :

```bash
./wikidebia corpus-workspace-plan-execute <debate_id> \
  --work-id <work_id> \
  --comparison-id <comparison_id> \
  --execute \
  --confirm-preflight-sha256 <empreinte>
```

La deuxième commande effectue réellement les écritures distantes. Toute divergence observée juste avant l’exécution bloque le plan.

## Nouveau débat

Déposer le ZIP du corpus dans `incoming/`, puis lancer `./wikidebia publish [SÉLECTEUR] --scope all`.

### Reprise de publication après minuit

La date civile ne modifie plus le contenu à publier : le changement de jour ne nécessite aucun recalcul du plan. Les vérifications de révision, de contenu, de configuration, de résumé et de balises demeurent obligatoires. Un ancien plan signé qui imposait une date de création de page ne doit pas être exécuté ; reconstruire et autoriser son remplacement.

### Noms français normalisés à l’import

Pour `update --archive <SÉLECTEUR> --scope fr --interlanguage-only`, une page
introuvable sous le nom du manifeste peut être retrouvée sous le nom exact
consigné dans `data/import_provenance.json`, lorsque la seule différence est
la normalisation d’une apostrophe typographique en apostrophe droite.
Le fichier importé doit correspondre à son empreinte et la page distante à la
révision et au contenu importés, ou à ce contenu déjà augmenté du seul lien
interlangue attendu. Toute autre divergence reste bloquante.

Le nom réellement retrouvé est signé dans le plan, utilisé pour l’écriture
et conservé dans l’état publié. Cette reprise ne crée ni ne renomme de page
française, ne réécrit aucun autre paramètre et ne change pas l’archive.

## Débat déjà publié — corpus installé

Lancer `./wikidebia update <debate_id> --dry-run`, examiner le plan, puis relancer sans `--dry-run`. Sans `--archive`, la commande ne consulte que `corpus/<debate_id>/` et ne sélectionne jamais implicitement un ZIP de `incoming/`.

## Débat déjà publié — nouvelle archive

Utiliser explicitement :

```bash
./wikidebia update --archive <SÉLECTEUR> --dry-run
./wikidebia update --archive <SÉLECTEUR>
```

À partir du kit 2.16.12, toute opération mutante issue de cette archive (`create`, `update`, `move`, `redirect` ou `delete`) reçoit dans le plan signé un **résumé MediaWiki individualisé**. Pour une mise à jour de contenu, ce résumé est calculé à partir du diff réel des paramètres de la page et regroupe les changements par fonction éditoriale (par exemple résumé, références, mots-clés, rubriques ou introduction). Un nouveau plan de cette génération ne publie jamais une mutation avec le résumé générique `Corrections`. L’exécuteur recalcule le résumé attendu immédiatement avant l’écriture à partir du contenu distant relu et du contenu désiré signé ; toute divergence bloque l’opération.

Les conventions spécialisées restent prioritaires lorsqu’elles sont plus précises, notamment l’ajout d’un lien interlangue français, les renommages canoniques, les fusions en redirection et les retraits. Le résumé réellement enregistré par MediaWiki est relu avec le contenu, la balise `chatgpt` et la révision.

L’archive est extraite dans une zone temporaire de staging. La simulation ne modifie pas `corpus/`, puis le staging est supprimé. Le corpus actif n’est remplacé qu’après une exécution réussie ou une attestation `no_changes` réussie.

Un plan contenant `blocked` ou `manual_review` est bloquant et ne produit ni écriture MediaWiki, ni reçu de succès, ni nouvel état publié. Un plan entièrement `skip` déclenche une relecture distante complète, produit une attestation signée `no_changes` et actualise l’état publié sans éditer le wiki.

## Portées partielles

Lorsque la portée demandée ne contient aucune opération mutante, la commande renvoie `no_changes_in_scope` sans exécuter ni promouvoir un staging. Une reprise avec `--no-delete` conserve les pages à supprimer comme `pending_delete`; elles peuvent ensuite être traitées avec `--only-delete`.

## Mise à niveau des composants

Un seul fichier suffit. Vider `updates/`, y copier soit le bundle `WIKIDEBIA_SOURCES_COMPLETES_*.zip`, soit la livraison complète `WIKIDEBIA_LIVRAISON_*.zip`, puis lancer `./wikidebia upgrade`.

## Publication française avec anglais différé (1.2.35, compatible avec les corpus historiques 1.2.x)

Le corpus déclare `translation_status.en=deferred`, ne manifeste que les pages françaises et omet `interlangue`. Utiliser `./wikidebia publish --scope fr` ou `./wikidebia update --archive <archive> --scope fr`. Toute portée anglaise est refusée jusqu'au passage à `ready` ou `published`.

## Résumé individualisé des créations anglaises traduites

Lorsqu’une page anglaise est créée depuis une traduction française verrouillée et que `translation_status.en` vaut `ready` ou `published`, le plan porte un résumé propre à la page :

```text
Translation of the French page: [[:fr:X|X]]
```

`X` est le titre canonique français de la même `page_id`. Le titre est résolu depuis le manifeste, le résumé est signé avec l’action, recalculé avant l’écriture et contrôlé sur la révision relue. Le lien d’historique ne remplace pas `{{Lien interlangue}}` dans la page française.


## Ajouter rétroactivement `translated-fr`

Après une publication anglaise FR→EN déjà effectuée avec seulement `chatgpt`, lancer d’abord `./wikidebia tag-translated-fr DEBAT --dry-run`. Si le plan ne contient aucun blocage, lancer `./wikidebia tag-translated-fr DEBAT`. Le kit utilise l’état publié anglais pour identifier les révisions de création, exige leur résumé individualisé de traduction et ajoute uniquement la balise `translated-fr` via l’API MediaWiki `action=tag`. Cette opération ne crée aucune révision et ne modifie aucun contenu.

Pour les futures créations anglaises FR→EN, lorsque `translation_status.en` vaut `ready` ou `published`, le plan signé porte `change_tags: ["chatgpt", "translated-fr"]` pour chaque page anglaise et la relecture de la révision vérifie les deux balises.


## Orchestration éditoriale de haut niveau

Pour l'usage normal d'un débat qui doit être préparé puis traduit, préférer :

```bash
./wikidebia workflow "Titre exact du débat"
```

La commande enchaîne les opérations mécaniques et produit automatiquement les paquets de revue sous `outgoing/`. Après chaque retour de ChatGPT, placer le ZIP corrigé dans `incoming/`, puis :

```bash
./wikidebia review-import
```

Si plusieurs paquets de revue sont présents, utiliser uniquement l’identifiant du débat : `./wikidebia review-import <debate_id>`.

Voir `GUIDE_EDITORIAL_ORCHESTRATION.md`. Les commandes détaillées restent disponibles pour audit/debug.


### Checkpoint français automatique

Après validation de la revue française de contenu, `review-import` publie automatiquement le français scellé avant de préparer la traduction anglaise. Cette publication utilise les mêmes plans signés, résumés individualisés, gardes de révision et relectures que `update`; elle ne nécessite pas une commande `update` séparée.


## Deux checkpoints français dans le workflow éditorial

Le workflow de reprise publie le français deux fois avant traduction :

1. après graphe + titres : relations, placements, renommages, titres affichés et retraits/fusions validés ;
2. après contenu : rubriques, mots-clés, références et autres champs ouverts ; sur des pages préexistantes, l’introduction et les résumés historiques restent inchangés par défaut, mais un `authorized_change` sélectionne la valeur finale propriétaire qui est rendue et publiée dans ce même checkpoint ; une portée structurée limite le delta autorisé et l’absence historique reste une absence sauf création nominativement autorisée.

Le premier checkpoint préserve le contenu/classification importé ; le second se calcule contre l’état publié du premier et interdit les mutations structurelles. Les deux utilisent des résumés MediaWiki individualisés.

### Arrêt avant publication bilingue finale

Après le rendu et la préparation des plans, le workflow s'arrête à `publication_prepared` sans écriture finale. Les plans et le préflight signés se trouvent dans `.state/final-publication/<debate_id>/<work_id>/`. Relisez-les avant de confirmer :

```bash
./wikidebia workflow-publish <debate_id> --confirm-preflight-sha256 <sha256>
```

La commande de publication ou de reprise doit viser ce préflight signé ; une divergence de contenu ou de révision distante bloque l'opération. Ce verrou ne modifie pas les deux checkpoints français précédents, qui possèdent leurs propres contrats de publication.

## Guide de revue du contenu

Source interne : `kit/GUIDE_CONTENT_REVIEW.md`  
SHA-256 : `ead8e97a8a509705ebc5e6b5675bad3c078f7635fe2b4c3d89b16f88b04fa50c`

# Revue française du contenu et de la documentation

> Depuis 1.2.54, les normes éditoriales sont cumulatives : les anciennes métadonnées de révision ne servent plus à sélectionner les contrôles.

La phase de contenu intervient après le verrouillage et la publication du graphe et des titres. Elle prend désormais aussi en charge les **rubriques et mots-clés**, afin qu’ils soient publiés au second checkpoint avec l’introduction, les résumés et la documentation. Elle part de `reviewed-copy/`, conserve toutes les copies antérieures et ne génère toujours aucune page MediaWiki finale.


## Protection des textes historiques

Pour une page importée avec `page_origin=preexisting`, l’introduction du Débat et les résumés des Arguments sont **protégés par défaut**. `--prepare` recopie leur valeur historique avec `decision=keep`; une absence historique de résumé reste absente. ChatGPT peut renseigner `suggested_change` sans modifier `proposed_*`. Les règles de style de création ne sont pas appliquées rétroactivement à un texte simplement préservé.

Si le propriétaire approuve une correction pendant que la revue est ouverte, le ZIP rendu peut porter `decision=change`, la valeur finale et un `historical_change_request` précis (`field_key`, `final_value`, `change_type`, `rationale`, `owner_instruction_reference`). Ce contenu ne s’autorise jamais lui-même : `./wikidebia review-import` bloque encore le delta. Après accord explicite du propriétaire, lancer le **même ZIP** avec `./wikidebia review-import --authorize-historical-changes` (ou avec le `debate_id` en cas d’ambiguïté). Le kit crée alors localement un reçu de consentement lié au ZIP exact et à chaque SHA avant/après, finalise la même `fr_content_review` et publie le delta au checkpoint français n°2. Une autorisation ne couvre aucun autre champ. Une opération corrective séparée n’est nécessaire que si la demande arrive après la clôture du checkpoint.

Après ce consentement, la valeur finale proposée est la **valeur éditoriale sélectionnée** : l’historique reste sa provenance, mais l’extraction de `review.subsections`, les contrôles structurels, le verrou, le changeset, le rendu, le checkpoint 2 et la traduction utilisent le texte final autorisé. Pour une modification structurelle d’introduction, `historical_change_request.change_scope` peut décrire précisément les sous-parties ajoutées, modifiées, supprimées et un éventuel réordonnancement. Les contrôles de création s’appliquent alors seulement aux sous-parties ajoutées ou substantiellement réécrites. Une portée « ajouter `Enjeux du débat` » bloque toute autre modification silencieuse de l’introduction.

## 1. Préparer la revue

```bash
./wikidebia corpus-workspace-content-review <debate_id> \
  --work-id <work_id> \
  --prepare
```

La commande lit le wikicode importé et crée :

```text
reviews/fr/content_review.json
reviews/fr/classification_review.json
data/keyword_vocabulary_working.json
data/sources_working.json
audits/fr_content_inventory.json
audits/fr_content_inventory.md
```

Le registre couvre :

- `sujet` et `sujet-développé` de la page Débat ;
- l’introduction et chacune de ses sous-parties ;
- les articles Wikipédia français vérifiés ;
- les neuf paramètres documentaires de la page Débat ;
- le résumé de chaque argument comme contexte ; pour une page préexistante sa valeur et sa présence sont protégées et non réécrites ;
- les données de contenu des arguments français importés ; les arguments réellement nouveaux ne sont pas créés par cette commande et doivent, lorsqu’un corpus en contient, être accompagnés de la revue documentaire 1.2.53 décrite ci-dessous ;
- la bibliographie, la sitographie et la vidéographie de chaque argument ;
- les attestations de lisibilité, de fidélité logique, de force expressive et de vérification documentaire.

Aucune proposition produite par une heuristique n’est appliquée automatiquement.


## Recherche d’un nom consacré pour un argument nouveau

Cette exigence relève du contrat général de génération 1.2.53. La commande `corpus-workspace-content-review` ci-dessus part d’un snapshot importé et ne crée donc pas elle-même de nouvel argument français. Lorsqu’un corpus généré contient des pages `Argument` françaises nouvelles, il doit fournir `reviews/argument_name_discovery_review.json` avant validation ; le validateur 0.4.61 bloque toute page nouvelle non couverte. La phase de traduction anglaise du kit construit la partie anglaise de ce registre pour les pages anglaises nouvelles.

La recherche est **obligatoire**, mais l’ajout d’un nom ne l’est pas. Le cas normal est `outcome=none`. Il ne faut jamais chercher à augmenter artificiellement le nombre de pages possédant `nom-consacré=`.

Pour chaque argument nouveau :

1. partir du raisonnement complet (prémisses, mécanisme, conclusion), pas seulement de son titre ;
2. effectuer au moins deux recherches terminologiques distinctes ;
3. lorsque la littérature pertinente est internationale, vérifier également l’anglais ou la langue académique/originale pertinente ;
4. privilégier les encyclopédies spécialisées, ouvrages et articles académiques ;
5. ne retenir un nom que si ces sources emploient réellement cette étiquette pour le **même raisonnement** ;
6. ne pas transformer en nom d’argument un thème, une doctrine, un auteur, un principe seulement mobilisé ou un raccourci inventé ;
7. en français, ne pas fabriquer une traduction d’un nom anglais : employer une forme française attestée ou, si c’est l’usage établi, la forme étrangère elle-même ;
8. au moindre doute sérieux, conclure `none`.

La fiche `reviews/argument_name_discovery_review.json` conserve les requêtes, le périmètre de recherche, le résultat et la justification. Si le résultat est `known_name`, elle conserve aussi au moins une attestation documentaire avec l’appellation telle qu’elle est utilisée et sa localisation.

La rareté des arguments nommés est donc attendue, mais elle n’est pas contrôlée par un quota : certains corpus spécialisés peuvent naturellement en contenir davantage que d’autres.

## 2. Finaliser la revue

Après avoir complété le registre de contenu et le registre documentaire :

```bash
./wikidebia corpus-workspace-content-review <debate_id> \
  --work-id <work_id> \
  --finalize
```

La finalisation vérifie notamment :

- que chaque `document_kind` de `data/sources_working.json` appartient directement à l’enum accepté par le registre documentaire final, afin de bloquer l’erreur avant la projection vers `data/sources.json` ;

- l’inventaire exhaustif, sous-partie par sous-partie, des notions spécialisées, avec vérification de chaque lien, explication intégrée, traitement antérieur ou justification contextuelle ;

- la couverture exacte de tous les arguments actifs ;
- pour une introduction nouvellement créée ou explicitement réécrite, l’existence d’une structure conforme ; une introduction historique préservée n’est pas normalisée rétroactivement ;
- la présence d’au moins un article Wikipédia français vérifié ;
- l’absence de doublon entre les orientations pour, contre et neutre ;
- le classement neutre des sources qui développent substantiellement les deux positions ;
- l’absence de quota minimal par paramètre documentaire ;
- l’absence de quota documentaire imposé aux pages Argument ;
- la cohérence entre les sources retenues et leurs usages déclarés ;
- la langue française des références utilisées sur la page Débat ;
- la vérification de la langue et de l’attribution des sources web et vidéo ;
- la présence du créateur ou de la chaîne pour toute vidéo YouTube ;
- la densité informative et la non-redondance des sous-parties ;
- l’présence obligatoire d’une rubrique « Enjeux du débat » qui expose au moins deux conséquences concrètes sans recopier le graphe ;
- l’absence de point final dans une simple notice `<ref>` ; toute note conservant un point doit être une phrase complète attestée par SHA-256 ;
- pour les résumés nouveaux ou explicitement réécrits, l’absence de métadiscours et d’auto-objection ; les résumés historiques préservés ne sont pas réécrits pour ce motif ;
- pour les résumés nouveaux ou explicitement réécrits, la présence réelle de l’expression attestant la force du résumé ;
- la vérification explicite des affirmations chiffrées lorsqu’elles existent.

La revue et le registre documentaire sont liés par SHA-256. La finalisation ne modifie pas `reviewed-copy/`.

## 3. Appliquer la revue

```bash
./wikidebia corpus-workspace-content-review <debate_id> \
  --work-id <work_id> \
  --apply \
  --confirm-review-sha256 <empreinte>
```

L’application crée atomiquement :

```text
content-reviewed-copy/
```

Cette copie contient notamment :

```text
data/fr_content_lock.json
data/sources.json
changes/fr_content_changeset.json
reviews/introduction_review.json
reviews/summary_style_review.json
reviews/fr/content_review.json
```

Les états antérieurs restent intacts :

```text
corpus/<debate_id>/
working-copy/
reviewed-copy/
content-reviewed-copy/
```

Le registre maître reçoit seulement les identifiants des sources françaises sélectionnées pour chaque argument. Le verrou de métadonnées françaises, les imports et le graphe restent inchangés. Après succès, la préparation anglaise passe à `ready_for_translation`.

La primitive basse `--apply` reste locale. Dans le workflow utilisateur `review-import`, son succès déclenche ensuite le **checkpoint français 2.16.13** : rendu FR sans interlangue, plan de reprise signé, publication/attestation distante, puis seulement préparation de la traduction anglaise.

## Rapport de tests du kit

Source interne : `kit/TEST_REPORT.txt`  
SHA-256 : `5d38e319f2e300b8309cb6882204ed45afabe14a1e2caade2e9f3a2b7fb5878d`

Wikidéb’IA Kit 2.16.47 — rapport de tests

Tests pytest : 1921 réussis
Norme : 1.2.88
Validateur : 0.4.105

Final publication validator fingerprint : PASSED ; la configuration anglaise finale transporte `validator.fingerprint_path` et calcule réellement l’empreinte du validateur.
Final checkpoint receipt-reference reconciliation : PASSED ; réparation uniquement à plan signé identique, avant publication finale.
Legacy unbound checkpoint adoption : PASSED ; un workflow sans empreinte de reçu est rattaché uniquement au reçu courant attesté par l’état français signé.
Render preflight evidence reconciliation : PASSED ; aucune valeur éditoriale n’est modifiée.
Historical keyword atomicity normalization : PASSED ; uniquement les métadonnées déjà attestées sont réconciliées.
Historical introduction provenance : PASSED ; le verrou français reste autoritatif.
Final publication orchestration : PASSED ; les capacités de 2.16.39 sont conservées.
Legacy non-canonical checkpoint status : PASSED ; un statut local historique non canonique est normalisé uniquement pour un workflow totalement non lié et déjà en final_publication.
Retrait des dates de création : PASSED ; les nouveaux plans sont indépendants du jour civil, les anciennes autorisations datées sont bloquées et les dates documentaires restent préservées.
Debate-first publication order : PASSED ; Debate précède les créations Argument, y compris après migration auditée d’un plan partiellement exécuté.

Signed plan cross-version resume : PASSED ; les versions producteur restent de la provenance, tandis que signature, schéma, manifeste et configuration restent bloquants.

Explicit French Git publication relay : PASSED ; 46 tests du relais : préflight global, conflits, reprises, transport Git, relecture et idempotence sur wiki simulé. Aucune publication réelle effectuée par ces tests.

French relay readback recovery : PASSED ; relectures bornées des métadonnées, contrôle de la révision parente, reprise des anciens reçus et absence de doublons après interruption.

Displayed-title translation scope : PASSED ; titres courts et nominaux conservés, critères de génération séparés et régressions sémantiques de traduction toujours bloquantes.

## Guide d’orchestration éditoriale

Source interne : `kit/GUIDE_EDITORIAL_ORCHESTRATION.md`  
SHA-256 : `dc36c96714363ce053912b8e49851cc1da8320cccf3a5eeb23457044e2d89ffc`

# Orchestration des revues éditoriales ChatGPT — Kit 2.16.7

## Usage normal

Pour lancer ou reprendre la préparation bilingue d'un débat existant :

```bash
./wikidebia workflow "Un revenu de base doit-il être instauré ?"
```

La commande réutilise un snapshot `graph-extract` compatible déjà présent lorsque c'est possible ; sinon elle effectue l'extraction en lecture seule. Elle initialise le corpus, lance les validations mécaniques et s'arrête au premier point où une décision éditoriale externe est requise.

## Continuité obligatoire sur GitHub

Une production longue doit rester reprenable depuis un autre compte ou une autre
session sans dépendre du contexte de conversation. Les règles suivantes font
partie de la méthode de travail :

1. Tout défaut reproductible rencontré dans le workflow est corrigé dans le code
   générique, avec un test de régression ciblé. Il ne doit pas être contourné en
   falsifiant un artefact du corpus ou en affaiblissant un contrôle de sécurité.
2. Le correctif cohérent est validé, commité et poussé sur la branche GitHub de
   travail dès qu'il est prêt. Les correctifs ne sont pas accumulés jusqu'à la
   fin de la traduction.
3. Après chaque phase ou checkpoint, une sauvegarde assainie est mise à jour sous
   `continuity/<debate_id>/latest/`, puis commitée et poussée. L'historique Git
   conserve les états antérieurs. Cette sauvegarde contient au minimum le corpus
   de travail complet nécessaire à la reprise, l'état d'orchestration, les ZIP de
   revue utiles, un handoff lisible et les pages wikicode créées ou modifiées sur
   le wiki pendant la phase.
   Après toute écriture distante, elle contient aussi obligatoirement les états
   signés `.state/published/<debate_id>/<langue>/latest.json`, tous les états
   historiques horodatés nécessaires pour relier le dernier checkpoint à cet
   état courant, les reçus `.state/receipts/<debate_id>/` et les plans/reçus du
   checkpoint et des corrections ultérieures. Un reçu de checkpoint sans toute
   sa succession d’états publiés signés n’est pas un point de reprise complet.
4. Le handoff indique le commit source, la phase atteinte, la prochaine commande,
   les validations exécutées, les écritures MediaWiki déjà attestées et les
   éventuels blocages. Un manifeste SHA-256 couvre tous les fichiers sauvegardés.
5. `private/`, les jetons, mots de passe, cookies, configurations Pywikibot,
   environnements virtuels, caches et autres secrets ne sont jamais copiés dans
   `continuity/`. Avant chaque commit, contrôler la liste des fichiers suivis et
   rechercher les chemins ou données privés accidentels.
6. Une projection de continuité conserve octet pour octet tout fichier déjà
   couvert par une empreinte de workflow ou de revue. Une amélioration de
   portabilité (par exemple remplacer un ancien chemin absolu par un chemin
   relatif) s'applique à la génération des nouveaux artefacts, jamais par
   réécriture rétroactive d'une preuve scellée. Si un artefact contient une
   donnée réellement sensible, la sauvegarde est bloquée et la reprise exige
   une migration explicite et attestée ; le fichier n'est pas normalisé en
   silence.

Les répertoires d'exécution (`.state/`, `corpus/`, `incoming/`, `outgoing/`) restent
ignorés et ne sont pas ajoutés de force. Seule leur projection assainie et
explicitement contrôlée sous `continuity/` est versionnée. Chaque reprise commence
par la lecture du handoff et la vérification de son manifeste avant de restaurer
les données dans les zones locales ignorées.

Après avoir actualisé les autres fichiers et le handoff d'un snapshot, projeter
la succession française signée et régénérer son manifeste avec :

```bash
./wikidebia continuity-sync <debate_id>
./wikidebia continuity-sync <debate_id> --check
```

La première commande copie octet pour octet les états horodatés, l'état courant
et les reçus du même Work, puis régénère `SHA256SUMS`. La seconde est sans écriture
et bloque si une pièce manque, si une révision régresse ou si un reçu sort du
Work. Les tests du dépôt vérifient aussi chaque snapshot `latest` commité afin
qu'une sauvegarde incomplète ne passe pas la validation GitHub.

Exemple :

```text
Revue du graphe préparée.
191 placements doivent être analysés par ChatGPT.

Envoyez ce fichier à ChatGPT :
outgoing/revenu_de_base_graph_review.zip

Après correction, placez le ZIP rendu dans `incoming/`, puis lancez :
./wikidebia review-import
```

Après le retour de ChatGPT, placer le ZIP corrigé dans `incoming/` puis lancer :

```bash
./wikidebia review-import
```

Si plusieurs paquets de revue valides sont présents, la commande indique les identifiants disponibles ; utiliser alors `./wikidebia review-import <debate_id>`.

Le kit vérifie le paquet, installe uniquement les fichiers autorisés, finalise et applique la revue, puis poursuit automatiquement jusqu'au prochain point éditorial. Aucun SHA-256 n'est à recopier manuellement.

L'état courant est consultable avec :

```bash
./wikidebia workflow-status revenu_de_base
```

## Contrat des paquets

Un paquet de revue contient uniquement :

- `REVIEW_PACKAGE.json` : provenance et empreintes ;
- `INSTRUCTIONS.md` : consignes de la revue ;
- `editable/` : seuls fichiers que ChatGPT peut modifier ;
- `context/` : sources nécessaires en lecture seule.

Le retour doit conserver exactement cette structure. Les fichiers de contexte, le manifeste et les instructions ne peuvent pas être modifiés. Les fichiers supplémentaires sont refusés. Les chemins dangereux, liens symboliques et paquets provenant d'un autre débat, d'un autre Work ou d'une ancienne revue sont refusés.

La création du ZIP utilise un remplacement atomique : une interruption ne peut
pas substituer une archive partielle à la dernière archive complète. Si le ZIP
complet a été écrit mais que l’enregistrement suivant de `workflow.json` a été
interrompu, la reprise le réadopte uniquement lorsque l’identité du débat et du
Work, les versions, l’empreinte complète de la base, chaque fichier éditable,
chaque contexte et les compteurs correspondent exactement. Sinon le ZIP
orphelin est ignoré et reconstruit depuis la base courante.

`outgoing/` est une zone privée exclue de Git. Aucun secret, cookie, fichier Pywikibot privé, configuration locale ou état de publication n'est inclus par les listes blanches de revue.

## Points éditoriaux orchestrés

Le cycle courant couvre successivement :

1. **revue combinée graphe + titres** : placements/relations, suppressions/fusions/déplacements, titres canoniques et titres affichés ; son réimport déclenche immédiatement le **checkpoint 1 graphe/titres** ;
2. **revue de contenu** : rubriques, mots-clés et documentation française ; l’introduction et les résumés des pages `preexisting` sont préservés par défaut, mais un delta explicitement autorisé sélectionne la valeur finale correspondante ; son réimport déclenche le **checkpoint 2 contenu** ;
3. traduction et documentation anglaises, y compris la recherche d'`established-name=` lorsqu'elle s'applique ;
4. première passe de convergence sémantique ;
5. deuxième passe indépendante de convergence.

Si une passe sémantique trouve une erreur certaine, la traduction est rouverte, les constatations sont fournies comme contexte dans un paquet de correction, puis les deux passes de convergence recommencent sur la nouvelle empreinte.

Si un ancien Work arrive après convergence avec un registre documentaire anglais incomplet au regard du contrat final, l'orchestrateur n'attend plus l'échec de `translated-copy` : il rassemble toutes les lacunes dans un paquet `en_documentation_correction` où seul `sources_en_working.json` est modifiable. Cette reprise est également préventive pour les nouvelles revues : les mêmes champs sont contrôlés avant la première passe de convergence.

Après validation du paquet combiné graphe/titres, le workflow publie le premier checkpoint avec des résumés personnalisés. Après validation de la revue française de contenu, il publie le second checkpoint, également avec des résumés personnalisés, avant toute traduction anglaise. Après deux passes anglaises propres et indépendantes, l'application, le rendu et la construction `release_ready` restent automatiques. Le parcours final s'arrête désormais à `publication_prepared` : le Work scelle sa baseline bilingue, construit les plans signés, préflight les pages en lecture seule et conserve l'aperçu. Aucune publication finale n'est autorisée à cette étape. Après vérification humaine du préflight, la commande `./wikidebia workflow-publish <debate_id> --confirm-preflight-sha256 <sha256>` recharge les plans exacts, relit les cibles, puis publie les créations anglaises et les seuls ajouts interlangues français ; le `release-copy` n'est installé qu'après succès. Un conflit ou une modification humaine bloque cette phase sans rouvrir la traduction ni les convergences déjà scellées. Les autres écritures pré-W11 restent limitées aux actions structurelles explicitement demandées.

## Commandes avancées

Toutes les primitives existantes restent disponibles (`corpus-review-graph --prepare/--finalize`, `corpus-promote`, `corpus-workspace-review`, `corpus-workspace-content-review`, `corpus-workspace-translation`, `corpus-workspace-semantic-convergence`, etc.). Elles constituent la couche d'audit/debug et restent autoritatives ; l'orchestrateur ne fait que les enchaîner et résoudre automatiquement leurs confirmations mécaniques.
## Blocage technique avant une revue

La validation initiale distingue désormais les anomalies éditoriales différables des erreurs structurelles. Un titre importé à reformuler n’empêche pas la création du paquet de revue des métadonnées. En revanche, un cycle, une relation invalide ou une incohérence d’occurrence reste bloquant.

Dans ce cas, l’utilisateur n’a pas à rechercher un rapport sous `.state/`. Le programme affiche les principaux diagnostics et crée automatiquement :

```text
outgoing/<debate_id>_initial_validation_diagnostic.zip
```

Ce fichier peut être envoyé tel quel à ChatGPT pour diagnostic. Après correction du kit ou des données, relancer exactement la même commande `./wikidebia workflow ...` : la validation bloquée est réessayée et le workflow reprend automatiquement.
## Appliquer une revue du graphe avec actions distantes

Lorsqu’un ZIP de revue rejetée contient des décisions structurelles explicites, utilisez :

```bash
./wikidebia review-import <debate_id> --execute-graph-actions
```

Cette commande valide d’abord la projection locale complète, préflight toutes les pages distantes concernées, puis applique dans l’ordre les modifications des pages mères, les redirections des doublons et les suppressions non fusionnées. Les actions possibles sont `remove`, `merge_redirect`, `move` et `relation_change`. Un doublon est remplacé par `#REDIRECTION [[Destination]]` et le résumé de la page mère mentionne `[[Destination]]`. Les résumés génériques `Corrections` ne sont pas utilisés. Après succès, une nouvelle revue complète du graphe est automatiquement préparée.


## Transaction de réimport et reprise

À partir du kit 2.16.8, un `review-import` reste transactionnel jusqu’à une frontière distante. En 2.16.13, la publication française après `fr_content_review` constitue elle aussi une frontière distante irréversible attestée. La revue n’est donc pas considérée comme définitivement consommée tant que l’avancement mécanique suivant n’a pas réussi. En cas d’échec, le workflow, la base revue et les artefacts mécaniques créés pendant la tentative sont restaurés ; le même ZIP peut être réimporté.

Les actions de graphe exécutées explicitement avec `--execute-graph-actions` constituent une frontière irréversible : si les écritures distantes ont réussi, leurs plans et reçus restent autoritatifs et le workflow reprend depuis l’état post-action au lieu de prétendre revenir avant les écritures.

## Compatibilité des composants lors de `upgrade`

À partir du gestionnaire 2.16.8, chaque composant est autoritatif pour sa propre version : `wikidebia-normes` pour `norm`, `wikidebia-validator` pour `validator`, et `wikidebia-kit` pour `kit`. Les autres numéros répétés dans leur `VERSIONS.json` sont des informations de provenance et ne doivent plus forcer le reconditionnement d’un composant inchangé. Les garde-fous portent sur la version propre du composant, l’anti-rétrogradation, la révision normative effectivement implémentée et les schémas/capacités déclarés.


### Protection des textes historiques dans `fr_content_review`

Lors d’une reprise de pages existantes, l’introduction et les résumés historiques sont préservés par défaut. Le paquet peut enregistrer des suggestions sans les appliquer. Après consentement valide, le texte final autorisé devient la valeur éditoriale sélectionnée pour tous les contrôles structurels, le verrou, le changeset, le rendu, le checkpoint 2 et la traduction ; l’historique demeure la provenance. Une portée structurée d’introduction peut limiter précisément les sous-parties ajoutées/modifiées/supprimées/réordonnées et les règles de création ne s’appliquent qu’aux portions réellement ajoutées ou substantiellement réécrites. Lorsqu’un delta historique est précisément demandé dans le ZIP, `review-import` exige une action propriétaire explicite : relancer le même paquet avec `--authorize-historical-changes` crée hors du ZIP une preuve scoped et permet la modification dans la même `fr_content_review`. L’absence historique d’un résumé demeure une absence sauf création nominativement autorisée. Le delta autorisé est publié au checkpoint français n°2, sans troisième publication.

## Publication française après la revue de contenu

La réussite du paquet `fr_content_review` déclenche automatiquement le rendu d’un checkpoint français sans `interlangue`, son préflight distant et son exécution avec les résumés MediaWiki individualisés. Le paquet `en_translation_review` n’est créé qu’après succès ou attestation `no_changes`. Si le workflow a été préparé avec une version antérieure et possède déjà un paquet anglais sans reçu français, une reprise `workflow` publie d’abord le même contenu français scellé, sans invalider le paquet anglais lié à cette empreinte.

## Diagnostic automatique des validations bloquées

Tout échec du validateur lancé par le workflow produit automatiquement dans `outgoing/` un paquet `<debate_id>_<rapport>_diagnostic.zip`. Le terminal peut rester volontairement concis, mais ce ZIP contient l'inventaire **exhaustif** des erreurs (`ERRORS.json`, `ERRORS.txt`), le rapport complet et les fichiers de contexte directement référencés par les diagnostics. Il peut être transmis tel quel à ChatGPT ; aucune recherche manuelle sous `.state/` n'est requise.



### Préflight documentaire pendant la revue anglaise

Avant de sceller la revue anglaise, le kit applique aux sources de `data/sources_en_working.json` les contrôles de métadonnées correspondant aux règles de rendu `WDV-DOC-002`, `WDV-DOC-003`, `WDV-DOC-005` et `WDV-DOC-009`. Le rapport `reports/en_documentary_review_preflight.json` identifie l'ID de la source, le champ, la valeur et la correction attendue. Les anomalies certaines de format (pagination ou date machine) sont distinguées des arbitrages de fond (date de consultation, identité contradictoire, vraie nature d'une édition ou numéro de collection). Un numéro de collection suspect dans `issue` est un avertissement, pas une conversion automatique. La vérification intervient avant la convergence sémantique et ne modifie jamais une citation historique ni un titre anglais validé. Le rapport est inclus comme contexte facultatif dans les paquets de reprise de traduction.

## Guide de traduction anglaise

Source interne : `kit/GUIDE_TRANSLATION_REVIEW.md`  
SHA-256 : `59148908c1a0375b5b03b51f947122b9ce6dfeccb524b1208e6af2f47fdd6440`

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

**Convention obligatoire pour le seul paramètre `date` du modèle anglais `{{Quote}}` traduit depuis `{{Citation}}`** : toute date complète (jour, mois, année) exprimée sous forme traduite utilise le format britannique `D Month YYYY`, avec le mois anglais en toutes lettres et sans suffixe ordinal. Exemples : `18 novembre 2026` → `18 November 2026` ; `1er janvier 2025` → `1 January 2025` ; `14 juillet 1789` → `14 July 1789`. Ne pas utiliser `November 18, 2026`, ni conserver un mois français. Les dates incomplètes et les formes historiques numériques inchangées conservent les règles précédentes : aucune précision n'est inventée. Cette exigence ne modifie ni les dates dans le corps des pages, ni les autres paramètres.

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
- `date-création` et `creation-date` sont obsolètes et ne sont jamais générés ni ajoutés à la publication ;
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
