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

Après validation du paquet combiné graphe/titres, le workflow publie le premier checkpoint avec des résumés personnalisés. Après validation de la revue française de contenu, il publie le second checkpoint, également avec des résumés personnalisés, avant toute traduction anglaise. Après deux passes anglaises propres et indépendantes, l'application, le rendu et la construction `release_ready` restent automatiques. À partir de 2.16.39, `release_ready` ouvre immédiatement une phase distincte `final_publication` : le Work scelle sa baseline bilingue (dernier checkpoint FR signé et première publication EN explicitement attestée), construit et préflighte tous les plans distants avant la première écriture, publie les créations anglaises puis les seuls ajouts interlangues français, et installe le `release-copy` uniquement après succès. Un conflit ou une modification humaine bloque cette phase sans rouvrir la traduction ni les convergences déjà scellées. Les autres écritures pré-W11 restent limitées aux actions structurelles explicitement demandées.

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

