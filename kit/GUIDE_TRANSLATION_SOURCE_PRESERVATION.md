# Traduire un import français publié sans le réécrire

Ce mode de reprise distingue la fidélité à une source publiée de sa validation
documentaire actuelle. Il ne s'applique pas à la création de pages françaises.

Lorsque le propriétaire demande de conserver le graphe publié malgré des
réserves de placement, documenter chacune d’elles dans la revue. Marquer les
occurrences concernées `preserved_for_translation`, garder leur parent et
leur fonction publiés, renseigner le motif et laisser `direct_fit` à `false`.
Compléter la revue normale pour les autres occurrences. Consigner la décision
du propriétaire dans les notes, puis exécuter localement
`./wikidebia corpus-review-graph DEBAT --finalize --preserve-imported-source`.
Le kit vérifie les révisions et les empreintes des imports ainsi que les cibles,
les orientations et l’ordre des liens. Il scelle le registre de placements.
Promouvoir le build et créer le workspace en local. Appliquer la revue des
titres en mode `keep` et continuer par le gel ci-dessous. Le checkpoint
ordinaire de publication française refuse cette revue de préservation.

Après import, revue du graphe et application des titres français sans changement,
revoir les formes lexicales du vocabulaire de travail puis exécuter :

```bash
python kit/scripts/wikidebia_translation_review.py DEBAT --work-id WORK \
  --project-root . --freeze-imported-source --reviewer "Nom du relecteur" \
  --note "Justification explicite de la conservation de cet import publié."
```

Le gel exige une révision distante positive et une empreinte exacte pour chaque
page. Le graphe revu doit encore correspondre aux relations importées. Il produit
`data/source_preservation_receipt.json` et les verrous français dans une nouvelle
copie. Il refuse tout écrasement et toute divergence du snapshot.

Ce reçu atteste la conservation, **pas** l'authenticité des citations, la validité
actuelle des chiffres ou une nouvelle approbation documentaire française. Les
champs correspondants restent explicitement faux. Les références historiques
brutes restent conservées ; elles ne deviennent pas des sources anglaises.

La préparation, la revue individuelle, la recherche documentaire anglophone, les
deux passes de convergence, l'application, le rendu et la release utilisent
ensuite les commandes habituelles. Les incertitudes historiques sont consignées
séparément et ne justifient aucune suppression de citation ni ajout de résumé.

Le rendu français ajoute seulement le lien interlangue. Le validateur le compare
exactement au fichier importé, puis vérifie la cible du lien. Les règles de
création ne réécrivent donc pas les paramètres historiques. Les rares répétitions
de mots-clés et absences de classement ne sont acceptées que si elles reproduisent
exactement l'import attesté. Les sources originales restent inchangées, y compris
une éventuelle absence de saut de ligne final.

Les sections anglaises sont triées alphabétiquement ; les mots-clés gardent
l'ordre et les répétitions français. Le dictionnaire bilingue conserve les
concepts sans fusionner deux termes distincts. Chaque libellé de relation est
traduit dans son contexte ; le titre affiché principal d'un nœud ne remplace pas
ses autres libellés. Les citations **et** les textes situés entre elles entrent
dans l'empreinte sémantique et sont contrôlés au rendu.

Dans ce parcours, une mention historique `collection` est conservée à
l’identique sur une ligne « Collection » immédiatement après sa citation
anglaise. Le modèle `Quote` garde ses paramètres publiés. Le validateur compare
la mention et sa position à la citation française gelée.

Une revue scellée peut être rouverte avec `--reopen-review`, `--reviewer` et
`--note` tant qu'aucun rendu final n'existe. La revue et toute copie déjà appliquée
sont archivées après vérification de leur empreinte. Rien n'est remplacé ni
publié ; la refinalisation exige une nouvelle convergence sur l'empreinte courante.

Un paquet `release_ready` reste local. La commande `publish-preserved DEBAT
--work-id WORK` rattache la release au workflow et prépare le préflight en
lecture seule. La publication exige la confirmation de son empreinte avec
`workflow-publish DEBAT --confirm-preflight-sha256 EMPREINTE`.
Pour contrôler l'avancement sans déclencher d'écriture distante :
`./wikidebia corpus-workspace-status DEBAT --work-id WORK` ou
`./wikidebia resume --debate-id DEBAT --work-id WORK`.
Après une interruption, `resume` indique l'empreinte courante et la commande
correspondante. Lorsque les deux reçus d’écriture sont présents, l’option
`--verify-only` reprend uniquement le contrôle public. Le kit conserve pour
chaque page vérifiée le titre, la révision observée et l’empreinte du contenu.
Il reprend les contrôles manquants ou âgés de plus d’une heure et relit tout
si le plan, l’inventaire des pages ou le manifeste a changé.

La confirmation conserve le préflight approuvé pendant la nouvelle lecture
distante. Une interruption avant l’autorisation permet de relancer la même
confirmation. Si une ancienne version du kit avait remplacé ce préflight
avant de s’arrêter, `resume` propose une nouvelle préparation à confirmer.
Le verrou de publication est propre au débat et le système le libère à
l’arrêt du processus. `workflow-publish` renvoie le code 2 si la publication
reste bloquée ou incomplète.
`continuity-sync DEBAT --work-id WORK` projette
les preuves signées de préservation et de publication finale sans exiger un
checkpoint français inexistant dans ce parcours. `continuity-sync --check`
contrôle la projection sans la modifier.
