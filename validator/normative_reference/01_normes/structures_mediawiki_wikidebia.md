## Contrat de paramètres 1.2.76

Les noms MediaWiki canoniques sont désormais `sujet-développé` / `expanded-topic` pour le cadrage développé du débat et `débat-dédié` / `dedicated-debate` pour la frontière vers un débat autonome. Les anciens noms sont des alias de lecture des formats historiques seulement et ne figurent dans aucune nouvelle sortie.

# Structures MediaWiki autorisées de Wikidéb'IA

- **Version du schéma :** 1.1
- **Révision corrective du paquet :** 1.0.7
- **Date de validation de cette version :** 2026-07-23
- **Statut :** source normative
- **Portée :** pages de débats et d'arguments en français et en anglais

## 1. Fonction de ce document

Ce document dépend du `cahier_des_charges_consolide_wikidebia.md` pour l'intention éditoriale et conserve l'autorité exclusive sur les noms de paramètres et sous-modèles autorisés.

Ce document recense exclusivement les paramètres et sous-modèles autorisés dans les pages MediaWiki produites pour Wikidéb'IA.

Il définit :

- les quatre structures autorisées ;
- le nom exact des modèles et sous-modèles ;
- le nom exact, l'orthographe, les accents, les majuscules et les traits d'union des paramètres ;
- l'ordre canonique des paramètres ;
- l’absence de paramètres de date de création dans les quatre structures.

Ce document **ne détermine pas** quels paramètres doivent effectivement apparaître dans une page générée. Les règles d'émission, les paramètres obligatoires, les paramètres conditionnels et les paramètres non utilisés par la génération sont définis dans `profils_rendu_wikidebia.md`.

## 2. Principes normatifs

1. Aucun paramètre, modèle ou sous-modèle absent de ce document ne peut être inventé.
2. Les paramètres émis dans une page doivent respecter l'ordre de la structure correspondante.
3. Un sous-modèle placé dans un paramètre peut être répété autant de fois que nécessaire.
4. L'existence d'un paramètre dans la structure autorisée n'oblige pas à l'émettre **lors de la création d'une page nouvelle**. Lors de la modification d'une page existante, tout paramètre top-level attesté comme présent est conservé, sauf suppression explicite enregistrée.
5. Sur une page nouvelle, les paramètres facultatifs vides sont omis conformément au profil de rendu ; sur une page existante, cette règle ne permet jamais de supprimer un paramètre historique présent. `articles-Wikipédia` et `wikipedia-articles` ne sont toutefois jamais facultatifs ni vides dans une sortie courante conforme.
6. Les structures française et anglaise ne doivent jamais être mélangées.
7. Les paramètres `date-création` et `creation-date` sont obsolètes et ne figurent dans aucune nouvelle page.
8. Les liens interlangues sont autorisés uniquement dans les structures françaises.
9. Les noms canoniques des pages sont enregistrés dans le manifeste et le registre du débat. Ils ne dépendent pas de l'utilisation de `nom-consacré=` / `established-name=` ni de leurs alias historiques `nom=` / `name=`.
10. `débats-connexes` et `related-debates` restent décrits comme paramètres historiquement autorisés par les modèles du wiki, mais le générateur courant ne les émet jamais sur une page nouvelle ; sur une page existante, leur préservation suit le contrat historique de modification.
11. Les valeurs `auteurs` et `authors` sont du texte MediaWiki ; elles ne reçoivent jamais la sérialisation littérale d’une liste JSON.

---

# 3. Page française de type Débat

```mediawiki
{{Débat
|sujet=
|sujet-développé=
|avancement=
|avertissements-titre=
|avertissements-débat=
|introduction={{Sous-partie
|titre=
|contenu=
|avertissements=
}}
|articles-Wikipédia={{Article Wikipédia
|page=
}}
|arguments-pour={{Argument pour
|page=
|titre-affiché=
|avertissements=
}}
|arguments-contre={{Argument contre
|page=
|titre-affiché=
|avertissements=
}}
|avertissements-bibliographie=
|bibliographie-pour={{Référence bibliographique pour
|auteurs=
|article=
|ouvrage=
|volume=
|numéro=
|localisation=
|édition=
|lieu=
|date=
|lien=
|avertissements=
}}
|bibliographie-contre={{Référence bibliographique contre
|auteurs=
|article=
|ouvrage=
|volume=
|numéro=
|localisation=
|édition=
|lieu=
|date=
|lien=
|avertissements=
}}
|bibliographie-ni-pour-ni-contre={{Référence bibliographique
|auteurs=
|article=
|ouvrage=
|volume=
|numéro=
|localisation=
|édition=
|lieu=
|date=
|lien=
|avertissements=
}}
|avertissements-sitographie=
|sitographie-pour={{Référence sitographique pour
|lien=
|page=
|auteurs=
|site=
|date=
|avertissements=
}}
|sitographie-contre={{Référence sitographique contre
|lien=
|page=
|auteurs=
|site=
|date=
|avertissements=
}}
|sitographie-ni-pour-ni-contre={{Référence sitographique
|lien=
|page=
|auteurs=
|site=
|date=
|avertissements=
}}
|avertissements-vidéographie=
|vidéographie-pour={{Référence vidéographique pour
|titre=
|auteurs=
|lien=
|avertissements=
}}
|vidéographie-contre={{Référence vidéographique contre
|titre=
|auteurs=
|lien=
|avertissements=
}}
|vidéographie-ni-pour-ni-contre={{Référence vidéographique
|titre=
|auteurs=
|lien=
|avertissements=
}}
|rubriques=
|mots-clés=
|interlangue={{Lien interlangue
|langue=
|page=
}}
}}
```

---

# 4. Page française de type Argument

Le paramètre facultatif d’appellation consacrée est `nom-consacré`. L’ancien `nom` n’est qu’un alias historique de compatibilité pour des pages préexistantes attestées ; il n’est jamais généré sur une page nouvelle. Ce paramètre n’est ni le titre de la page ni un nom de site.

```mediawiki
{{Argument
|initialisation=
|nom-consacré=
|avertissements-titre=
|avertissements-argument=
|avertissements-résumé=
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
|avertissements-références=
|références-bibliographiques={{Référence bibliographique
|auteurs=
|article=
|ouvrage=
|volume=
|numéro=
|localisation=
|édition=
|lieu=
|date=
|lien=
|avertissements=
}}
|références-sitographiques={{Référence sitographique
|lien=
|page=
|auteurs=
|site=
|date=
|avertissements=
}}
|références-vidéographiques={{Référence vidéographique
|titre=
|auteurs=
|lien=
|avertissements=
}}
|avertissements-justifications=
|justifications={{Justification
|page=
|titre-affiché=
|avertissements=
}}
|avertissements-objections=
|objections={{Objection
|page=
|titre-affiché=
|avertissements=
}}
|débat-dédié=
|rubriques=
|mots-clés=
|interlangue={{Lien interlangue
|langue=
|page=
}}
}}
```

Le paramètre `débat-dédié` est conservé lorsqu’il existe dans une page historique importée. Sa valeur est verrouillée. Sur une telle frontière, les paramètres `justifications` et `objections` peuvent être omis lorsque cette décision et l’information du propriétaire sont attestées. L’équivalent anglais est `dedicated-debate`.

---

# 5. English Debate page

```mediawiki
{{Debate
|topic=
|expanded-topic=
|progress=
|title-warnings=
|debate-warnings=
|introduction={{Subsection
|title=
|content=
|warnings=
}}
|wikipedia-articles={{Wikipedia article
|page=
}}
|pro-arguments={{Pro argument
|page=
|displayed-title=
|warnings=
}}
|con-arguments={{Con argument
|page=
|displayed-title=
|warnings=
}}
|pro-bibliography={{Pro bibliographical reference
|authors=
|article=
|work=
|volume=
|issue=
|location=
|publisher=
|place=
|date=
|link=
|warnings=
}}
|con-bibliography={{Con bibliographical reference
|authors=
|article=
|work=
|volume=
|issue=
|location=
|publisher=
|place=
|date=
|link=
|warnings=
}}
|bibliography={{Bibliographical reference
|authors=
|article=
|work=
|volume=
|issue=
|location=
|publisher=
|place=
|date=
|link=
|warnings=
}}
|pro-webliography={{Pro web reference
|link=
|page=
|authors=
|site=
|date=
|warnings=
}}
|con-webliography={{Con web reference
|link=
|page=
|authors=
|site=
|date=
|warnings=
}}
|webliography={{Web reference
|link=
|page=
|authors=
|site=
|date=
|warnings=
}}
|pro-videography={{Pro video reference
|title=
|authors=
|link=
|warnings=
}}
|con-videography={{Con video reference
|title=
|authors=
|link=
|warnings=
}}
|videography={{Video reference
|title=
|authors=
|link=
|warnings=
}}
|sections=
|keywords=
}}
```

---

# 6. English Argument page

The optional conventional-label parameter is `established-name`. Legacy `name` is accepted only for exact preservation of attested pre-existing pages and is never generated on a new page. It is unrelated to page titles, website names, or generic JSON fields named `name`.

```mediawiki
{{Argument
|initialization=
|established-name=
|title-warnings=
|argument-warnings=
|summary-warnings=
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
|warnings=
}}
|reference-warnings=
|bibliography={{Bibliographical reference
|authors=
|article=
|work=
|volume=
|issue=
|location=
|publisher=
|place=
|date=
|link=
|warnings=
}}
|webliography={{Web reference
|link=
|page=
|authors=
|site=
|date=
|warnings=
}}
|videography={{Video reference
|title=
|authors=
|link=
|warnings=
}}
|justification-warnings=
|justifications={{Justification
|page=
|displayed-title=
|warnings=
}}
|objection-warnings=
|objections={{Objection
|page=
|displayed-title=
|warnings=
}}
|dedicated-debate=
|sections=
|keywords=
}}
```

---

# 7. Autorité et évolution du schéma

Toute modification de l'une de ces structures exige :

1. une nouvelle version du présent document ;
2. une mise à jour du profil de rendu concerné ;
3. une mise à jour des schémas JSON et du validateur ;
4. une mention de la version utilisée dans le manifeste de chaque débat ;
5. l'absence de modification silencieuse des paquets de débats déjà validés.

Les anciens paquets conservent la version de structure avec laquelle ils ont été créés.

---

# Addendum intégré 1.1.0 — 25 juillet 2026

La source normative active est désormais `WIKIDEBIA_NORME_CONSOLIDEE_1.1.0.md`. Pour toutes les variantes de `Référence bibliographique` et `Bibliographical reference`, le paramètre `page=` est autorisé immédiatement après `localisation=`/`location=`. Il contient uniquement une page ou une plage normalisée (`36` ou `36-37`). `localisation=`/`location=` ne reçoit plus de pagination pure. Les dates de consultation sont interdites dans le paramètre documentaire `date=`.

Les statuts correctifs et la date spécifique de W10.R1 sont définis par la norme consolidée. Les anciennes dispositions incompatibles de ce fichier sont historiques.
# Addendum intégré 1.1.4 — structure historique

La source normative active unique était `WIKIDEBIA_NORME_CONSOLIDEE_1.1.4.md` ; cet addendum est remplacé par l’addendum 1.1.5 ci-dessous. `page=` reste autorisé dans les références bibliographiques. L’ancienne révision autorisait `<references />`; la norme 1.2.0 conserve uniquement les appels `<ref>…</ref>` dans `contenu=`/`content=`. Jusqu’à la révision 1.2.26, les pages Argument générées n’employaient pas `nom`, `name`, `initialisation`, `initialization`, `citations`, `quotes`, `débat-dédié` ni `dedicated-debate`. Depuis 1.2.27, `citations` et `quotes` sont rendus uniquement à partir des verrous éditoriaux ; les autres paramètres de cette liste restent non générés sur les pages nouvelles ; `initialisation` / `initialization` est toutefois conservé à l’identique sur une page historique verrouillée. Les dispositions incompatibles antérieures sont de provenance seulement.


# Addendum 1.1.5 — historique, remplacé par 1.1.7

La source normative active unique est `WIKIDEBIA_NORME_CONSOLIDEE_1.1.9.md`. Chaque titre affiché et chaque ensemble de rubriques fait l’objet d’une décision page par page ; aucun quota global ne remplace cette revue. Une rubrique ubiquitaire est admise lorsque sa pertinence est justifiée pour chaque nœud. Cette ancienne révision exigeait un reçu de test dans l’espace utilisateur ; cette disposition est remplacée par le test canonique de la page Débat en 1.2.3. Toute disposition antérieure incompatible est historique.


# Addendum intégré 1.1.7 — règle active

Chaque rubrique retenue est justifiée individuellement au moyen d’une structure générique ; aucune rubrique ne reçoit de traitement spécial. Les dates et chemins propres à un corpus sont déclarés par son manifeste et ne sont pas codés dans le moteur de validation. Toute disposition antérieure incompatible est historique.


# Addendum actif 1.2.0 — structure corrigée

La règle structurelle introduite en 1.2.0 s’applique cumulativement : lorsqu’un lien interlangue est fonctionnellement requis, la page Débat française emploie exclusivement `{{Lien interlangue}}`. La page Debate anglaise n’emploie pas `type=` et contient, dans cet ordre, `topic=` puis `expanded-topic=`. Les balises `<references />` ne font partie d’aucune sortie générée. Pendant `translation_status.en=deferred`, le lien interlangue français est omis conformément au workflow différé. Toute disposition antérieure incompatible est historique.


# Addendum intégré 1.2.1 — contrainte de contenu français

Les structures MediaWiki ne changent pas. Dans les valeurs rédactionnelles françaises (`contenu=`, `résumé=` et passages équivalents), une incise parenthétique est rendue avec des parenthèses et non avec deux tirets cadratins.


# Addendum intégré 1.2.2 — cohérence des exemples

Les structures actives sont celles décrites ci-dessus : `{{Lien interlangue}}` sur les pages françaises lorsque la langue cible est prête, `topic` puis `expanded-topic` sur la page Debate anglaise et aucune balise `<references />`. Pendant une traduction différée, aucun lien provisoire n’est généré ; l’ajout canonique ultérieur suit le workflow interlangue explicite.


# Addendum intégré 1.2.2 (historique, complété par 1.2.3) — cohérence de livraison

Les règles 1.2.0 et 1.2.1 restent intégrées. Les exemples, profils et contrôles actifs sont ceux de la norme 1.2.2 : lien `{{Lien interlangue}}` présent dès la création française, aucune balise `<references />`, structure anglaise `topic` puis `expanded-topic`, autonomie référentielle des titres canoniques et parenthèses pour les incises françaises.

# Addendum intégré 1.2.6 — contraintes des valeurs de métadonnées

Les structures MediaWiki ne changent pas. Dans les pages Débat/Debate, `sujet` et `topic` commencent par une majuscule. `sujet-développé` et `expanded-topic` contiennent un complément non interrogatif compatible avec les en-têtes « Arguments pour et contre… » et « Pros and cons of… ». Les valeurs `rubriques` et `sections` sont triées alphabétiquement dans la langue de la page.

# Addendum intégré 1.2.7 — absence de changement structurel

Les structures MediaWiki sont inchangées par rapport à 1.2.6. La révision 1.2.7 porte uniquement sur la cohérence de livraison.


## Correctif 1.2.10



### Liens Wikipédia inline dans les introductions et résumés

Les modèles suivants sont admis dans `Sous-partie.contenu`, `Subsection.content`, `Argument.résumé` et `Argument.summary` :

```mediawiki
{{Lien Wikipédia|article=Titre de la page}}
{{Lien Wikipédia|article=Titre de la page|texte-affiché=texte visible}}
{{Wikipedia link|article=Page title}}
{{Wikipedia link|article=Page title|displayed-text=visible text}}
```

`article` est obligatoire et non vide. Les paramètres d’affichage sont facultatifs, non vides et propres à la langue. Ils sont omis lorsque la seule différence est la majuscule initiale : `L'{{Lien Wikipédia|article=effet placebo}}` est conforme. Aucun autre paramètre n’est admis. Ces modèles sont interdits dans les titres, les champs documentaires et le corps des notes `<ref>…</ref>`.

Implémentation de référence du modèle français :

```mediawiki
<span class="hover-wikipedia">[https://fr.wikipedia.org/wiki/{{{article}}} {{{texte-affiché|{{{article}}}}}}]</span>
```

Le modèle anglais conserve la même fonction de lien explicatif au survol avec les paramètres `article` et `displayed-text`.

### Appels inline dans les introductions

```mediawiki
Texte factuel<ref>Jean Dupont, « Titre de l’article », ''Nom de la revue'', 25 juin 2012, p. 36-37, [https://example.org texte intégral].</ref>.
```

La forme anglaise rédige de la même manière le contenu directement dans `<ref>…</ref>`, avec une date telle que `25 June 2012`. Aucun modèle MediaWiki — y compris `{{Référence}}`, `{{Reference}}` ou un modèle documentaire spécialisé — n’est utilisé dans une note d’introduction. Les modèles documentaires spécialisés restent réservés aux neuf paramètres structurés de Débat/Debate et aux familles documentaires des pages Argument.

### Couverture documentaire des pages de débat

Les paramètres documentaires de la page Débat ou Debate sont remplis selon la pertinence réelle des sources, sans quota par paramètre. Une catégorie peut contenir une seule référence ; si aucune source pertinente n’est retenue, le paramètre est entièrement omis. Une même référence ne figure jamais dans plusieurs orientations ; une source développant substantiellement les deux positions est classée uniquement dans la documentation neutre.

### Dates et acronymes

Les sous-paramètres documentaires `date=` utilisent le langage naturel. Lorsqu’un acronyme courant existe, il figure dans `sujet-développé` ou `expanded-topic`.


## Correctif 1.2.11 — jonction de modèles adjacents

Dans une valeur contenant plusieurs sous-modèles successifs, la fermeture du premier et l’ouverture du suivant sont jointes sans caractère intermédiaire :

```mediawiki
}}{{
```

La forme suivante est interdite, y compris avec des espaces, tabulations ou plusieurs lignes vides :

```mediawiki
}}
{{
```

Cette règle vaut pour les pages Débat, Debate et Argument, en français comme en anglais. Elle s’applique aux fichiers individuels et aux agrégats.


## Reprise distante d’un corpus publié — révision 1.2.16

Une reprise compare obligatoirement le dernier état publié signé, l’état distant courant et le nouveau corpus validé. Le kit produit un plan signé comprenant `create`, `skip`, `update`, `move`, `redirect`, `delete`, `manual_review` et `blocked`. Une page absente du nouveau manifeste n’est jamais supprimée sans preuve d’appartenance à la version antérieure du même débat.

Les mises à jour et suppressions vérifient la révision ou l’empreinte attendue et utilisent le contrôle de concurrence MediaWiki. Toute modification humaine ou provenance indéterminée est classée `manual_review`. Les déplacements et fusions sont déclarés explicitement. Les suppressions sont exécutées seulement après vérification du nouveau graphe publié. Les opérations sont idempotentes et donnent lieu à un reçu final et à un nouvel état publié signé.

Le validateur contrôle localement les structures et la cohérence des plans, mais toutes les lectures et écritures MediaWiki restent dans le kit.


## Contraintes MediaWiki 1.2.23

Dans `{{Débat}}` et `{{Debate}}`, `sujet-développé` et `expanded-topic` commencent normalement par une minuscule. Dans les modèles sitographiques de toute page, `page=site` est interdit et `auteurs/authors=site` est interdit après la seconde vérification d’attribution. Les mêmes contraintes sont contrôlées dans le registre pour la vidéographie.


## Paramètres protégés des pages préexistantes — révision 1.2.33

Les structures présentant `avancement=Débat construit`, `progress=Constructed debate` et les avertissements IA décrivent une page nouvellement créée. Une modification conserve exactement l’état antérieur de ces paramètres. Le manifeste de page porte `page_origin` et un instantané `preserved_parameters`; le validateur refuse toute suppression, addition ou réécriture non autorisée.

## Correctif actif — traduction FR→EN des paramètres de cycle de vie et d'avertissement

Lorsqu'une page anglaise est produite par traduction d'une page française, sa génération de fichier ne constitue pas une « création de zéro » pour l'attribution des métadonnées. La page anglaise cible éventuellement préexistante est ignorée comme source éditoriale. Les paramètres `progress`, `title-warnings`, `debate-warnings` et `argument-warnings` sont issus exclusivement des valeurs présentes dans la page française et traduits par la table normative de `docs/GUIDE_TRADUCTION_METADONNEES_FR_EN.md`. L'absence d'un paramètre français entraîne son absence dans la projection anglaise. Les valeurs par défaut `Constructed debate`, `Debate generated by AI` et `Argument generated by AI` sont réservées aux pages réellement créées de zéro, non aux fichiers nouvellement générés par traduction.

Pour une page Debate traduite, `related-debates` peut être présent uniquement pour les entrées de `débats-connexes` dont la page anglaise correspondante est vérifiée comme existante.

# Addendum actif 1.2.34 — paramètre interlangue conditionnel

Dans les structures françaises, `interlangue` est absent lorsque `translation_status.en=deferred`. Il devient obligatoire uniquement lorsque l'anglais est `ready` ou `published`, sous la forme unique `{{Lien interlangue|langue=en|page=Titre canonique anglais verrouillé}}`. Les structures anglaises ne comportent jamais ce paramètre. Les exemples plus anciens avec lien immédiat sont des exemples du profil bilingue prêt et ne s'appliquent pas au profil français différé.

## Correctif 1.2.35 — absence d'interlangue pendant la traduction différée

Pour une page française sous `translation_status.en=deferred`, le paramètre `interlangue` est absent. Dès la sortie de cet état, sa présence et sa cible sont de nouveau contrôlées strictement.

## Ponctuation des notes de référence (1.2.44)

Une simple notice documentaire placée dans `<ref>…</ref>` ne se termine pas par un point avant `</ref>`. Le point de la phrase principale vient après l’appel de note. Un point terminal interne est réservé à une phrase explicative complète et doit être attesté dans la revue par l’empreinte du corps exact de la note.

## Cohérence locale des liens Wikipédia explicatifs (1.2.45)

Les notions spécialisées de même rang énumérées ou comparées dans un même passage sont revues comme un groupe. Lier une seule notion alors que les notions voisines disposent d’articles pertinents et présentent le même besoin explicatif est interdit sans justification explicite. Le registre `wikipedia_link_groups` consigne la sous-partie, les termes, les articles, la décision et toute exception.



## Inventaire général des notions spécialisées (1.2.46)

La revue ne se limite pas aux séries de notions comparables. Chaque sous-partie est examinée intégralement et reçoit une entrée dans `specialized_term_inventory`. Toute notion susceptible d’arrêter un lecteur est liée, expliquée, rattachée à un traitement antérieur ou déclarée intelligible en contexte avec une justification spécifique. Tous les liens Wikipédia réellement présents sont recensés. Le registre `wikipedia_link_groups` de 1.2.45 est remplacé comme mécanisme actif par cet inventaire général.


### Règle 1.2.59 — création d’une traduction anglaise

Pour un `Argument` anglais **nouvellement créé par traduction FR→EN**, `initialization` est absent, même si la page française source possède `initialisation`. Les paramètres de date de création sont exclus du rendu et ne sont jamais conservés lors d’une mise à jour.


## Contrat de traduction 1.2.66

Les structures MediaWiki ne changent pas. Pour une page traduite, la valeur anglaise de `displayed-title` est toutefois issue du `titre-affiché` français correspondant, et non du titre canonique anglais. Les valeurs multiligne de `summary=` et `quotes=` sont analysées comme des paramètres complets, y compris lorsqu'elles contiennent des sous-modèles. `concept_id` est une donnée de registre et n'est jamais rendu comme paramètre MediaWiki.
