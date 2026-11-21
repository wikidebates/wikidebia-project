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
- La `creation-date` d’une nouvelle page anglaise est déterminée par la première création distante dans le fuseau de publication et n’est jamais copiée ni comparée à `date-création` française. Une page anglaise préexistante peut conserver sa date historique attestée.
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

`date=` contient la date de publication ou de mise à jour substantielle. Lorsqu’une date complète est connue, elle est écrite en langage naturel dans la langue de la page (`25 juin 2012` en français, `25 June 2012` en anglais), jamais au format machine `2012-06-25`. Une année seule, par exemple `2012`, reste admise lorsqu’elle est la seule précision documentaire disponible. Une date de consultation n’est jamais placée dans `date=`. Lorsque la date documentaire n’est pas vérifiable, le paramètre est omis. Aucune date ne peut être inventée. Cette règle ne concerne pas `date-création` ni `creation-date`, qui restent obligatoirement au format `AAAA-MM-JJ`.

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
|date-création=AAAA-MM-JJ
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
|date-création=AAAA-MM-JJ
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
|creation-date=YYYY-MM-DD
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
|creation-date=YYYY-MM-DD
}}
```

Les pages anglaises ne contiennent pas de lien interlangue.

Dans une traduction FR→EN, `argument-warnings=Argument generated by AI` n'est pas ajouté par défaut au seul motif que le fichier anglais vient d'être généré. `title-warnings` et `argument-warnings` sont traduits uniquement à partir des valeurs françaises présentes selon la table normative active ; un paramètre absent en français reste absent en anglais.

## 9. Dates de création

La date de création est une décision de production distincte de la date des sources. Elle seule utilise systématiquement le format machine `AAAA-MM-JJ` dans `date-création` et `creation-date`; les dates documentaires complètes utilisent le langage naturel. Chaque paquet déclare la date attendue pour chaque langue dans son manifeste ou son profil local. Le validateur compare cette valeur au wikicode, au registre et aux manifestes de pages. Le moteur générique ne contient aucune date propre à un corpus.

La date devient immuable dès la première validation du fichier de la page. Elle ne change ni lors d’une correction, ni lors d’un enrichissement, ni lors d’une nouvelle tentative d’import. L'ajout ultérieur d'un lien interlangue après une phase `deferred` est un enrichissement de la page existante : il ne change jamais sa date de création.

Les décisions propres à un corpus, y compris une date corrective historique, sont conservées dans son profil local ou ses rapports de migration, jamais dans la norme universelle.

## 9.1 Préservation automatique des pages historiques lors d’une reprise

Lorsqu’une page du nouveau corpus correspond à une page distante attestée dans l’état publié et que la révision distante courante correspond encore exactement à cet état, le kit construit un contenu effectif dérivé. Il y recopie uniquement les paramètres de cycle de vie protégés de la page distante : date de création, avertissements, avancement et paramètres historiques explicitement énumérés par le profil de rendu. Le reste du contenu provient du nouveau corpus validé.

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

Pour une création anglaise FR→EN, le résumé de modification est individualisé à partir du titre français verrouillé, sous la forme `Translation of the French page: [[:fr:X|X]]`, les balises `chatgpt` et `translated-fr` sont appliquées. Une nouvelle page anglaise ne transporte jamais `|initialisation=`/`|initialization=` depuis la page française : `initialization` n’est pas projeté depuis le wiki français. Sa `creation-date` est le jour civil de la publication distante, calculé dans le fuseau `Europe/Paris`, et appartient au premier acte de création distant ; elle n’est ni traduite ni copiée depuis `date-création`. L’ajout interlangue français ultérieur utilise le titre anglais verrouillé et préserve les autres paramètres historiques.

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
- conserve l’ordre des autres phases, les garde-fous de publication et la date civile réelle de chaque création anglaise ;
- lorsqu’une publication a déjà commencé sous l’ancien ordre, les pages déjà créées restent intactes et un plan successeur audité place `Debate` avant les seules créations `Argument` restantes.

