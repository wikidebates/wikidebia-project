# Clôture bilingue strictement hors ligne (preuve par langue)

Cette voie **ne publie rien** sur MediaWiki, ne relance aucune traduction et ne
réexécute aucun plan. Elle ne remplace **pas** le reçu final intégré de
`corpus-workspace-reconcile-publication`. Elle produit un reçu de
**réconciliation locale distinct**, après vérification de quatre preuves
historiques signées et des états publiés FR/EN.

## Prérequis

* Le Work doit porter une `release-copy` gelée et son empreinte
  `release_copy.tree_sha256`.
* Les plans **effectivement exécutés**, leurs reçus signés et les états
  `.state/published/<débat>/{fr,en}/latest.json` doivent déjà exister. Les
  historiques de publication doivent attester les mêmes révisions et empreintes.
  Si un plan a été remplacé après exécution, sélectionner la bonne version
  **historique** plutôt que de reconstruire un nouveau plan.
* Les preuves doivent être disponibles **localement**. Le simple nom d'un
  fichier, un checkpoint de progression ou un bilan « 725/725 » ne constitue
  pas une preuve de révision. Aucun reçu manquant ne peut être synthétisé.

Créer un sélecteur JSON dans le projet (par exemple
`.state/evidence/mon_debat/EDIT-20261120-001/selector.json`) :

```json
{
  "schema": "wikidebia-offline-bilingual-evidence-1.0",
  "debate_id": "mon_debat",
  "work_id": "EDIT-20261120-001",
  "english_plan": ".state/final-publication/mon_debat/EDIT-20261120-001/english-plan.json",
  "english_receipt": ".state/receipts/mon_debat/publication-en-20261120T123456Z.json",
  "french_plan": ".state/final-publication/mon_debat/EDIT-20261120-001/french-plan.json",
  "french_receipt": ".state/receipts/mon_debat/20261120T123500Z.json"
}
```

Les **chemins sont des exemples** : retrouver les noms exacts sur le disque.
`english_receipt` doit désigner le reçu d'attestation d'état publié anglais
(`wikidebia-publication-state-receipt-1.0`), et `french_receipt` le reçu
d'exécution ou d'attestation du plan de mise à jour français
(`wikidebia-remote-update-receipt-1.0`). Les fichiers
`english-publication-receipt.json` et `french-publication-receipt.json`
de l'orchestrateur final sont **des enveloppes** et ne les remplacent pas.

## Preuve facultative pour les graphes français renommés

Une release peut contenir des graphes français dont seuls certains paramètres
`page=` ont changé d'orthographe. Ces changements ne sont pas acceptés sur
la seule base d'une similarité de chaînes. Avant de les autoriser à la
réconciliation, produire **en lecture seule** un inventaire de leurs
identités MediaWiki :

```sh
./wikidebia corpus-workspace-prove-fr-relation-pageids mon_debat \\
  --work-id EDIT-20261120-001
```

Ce programme relit en groupes uniquement les pages françaises dont les
empreintes diffèrent, exige la **même révision et le même contenu** que l'état
publié signé, masque temporairement les **seuls noms de cibles relationnelles**
et compare tous les autres octets. Les libellés, l'ordre, les ancres,
doublons, commentaires et contenus non relationnels doivent être inchangés.
Chaque titre de relation, ancien et nouveau, est résolu via
`action=query&prop=info&redirects=1` et doit désigner le **même pageid** ;
les résolutions sont relues une deuxième fois, puis les révisions françaises
sont revérifiées. Une page absente, un alias qui ne pointe pas vers la même
page, une transformation ambiguë ou une réponse incomplète bloque.

Le reçu local produit est
`.state/post-publication/<débat>/<Work>/fr-relation-pageids.json`.
Pour utiliser cette preuve lors de la clôture, ajouter le champ optionnel
suivant au sélecteur JSON :

```json
"relation_pageids_proof": ".state/post-publication/mon_debat/EDIT-20261120-001/fr-relation-pageids.json"
```

Ce fragment est à **ajouter à l'objet JSON existant**, en veillant à placer
une virgule entre les champs. En l'absence d'écart français, ce champ doit
être omis. La clôture compare le contenu complet de chaque page divergente
avec la preuve signée et refuse tout écart non autorisé. Une preuve obtenue
dans le passé ne constitue pas une autorisation de publier aujourd'hui :
aucune écriture MediaWiki n'est effectuée par ces deux commandes.

## Limites techniques

L'identifiant `pageid` prouve l'identité d'une cible de relation, **pas**
l'identité d'un texte éditorial ou le caractère autorisé d'une publication.
La collecte s'arrête en cas de format de relation inconnu, notamment les
anciennes relations hors du modèle principal ; ces cas doivent rester
bloqués jusqu'à une procédure explicite. Aucune comparaison de nombre seul
(« 37 liens ») ne remplace l'égalité occurrence par occurrence.

## Commande

```sh
./wikidebia corpus-workspace-reconcile-offline-bilingual mon_debat \
  --work-id EDIT-20261120-001 \
  --evidence .state/evidence/mon_debat/EDIT-20261120-001/selector.json
```

Le vérificateur refuse notamment les empreintes divergentes, les identités
croisées, les inventaires incomplets, tout français de release non strictement identique au texte attesté, les révisions finales différentes des
reçus, une opération française autre que l'ajout interlangue attesté, les plans
partiels et les sauvegardes incompatibles. Les preuves sont contrôlées **avant**
la promotion locale. Après vérification, un checkpoint d'installation est
scellé, une copie précédente est conservée dans `archives/debates/`, et le
Work local est marqué `published`. La relance après interruption vérifie
exactement la même chaîne de preuves et le contenu de la sauvegarde.

**Limite importante :** l'outil confirme des **attestations locales déjà
produites par des lectures distantes**, pas l'état MediaWiki en temps réel. Il
ne prouve pas de lui-même le contenu des vrais résumés/tags des révisions
historiques ni l'identité MediaWiki des cibles de liens renommées. Pour les
37 changements de graphes à cible prétendument identique, conserver une
preuve distincte d'inventaire de `pageid` et de l'ordre, du libellé et des
ancres ; **ne pas utiliser cette commande comme autorisation d'enrichir le
français publié**. Si les reçus ou inventaires nécessaires manquent, la
clôture est bloquée plutôt que déduite.

L'opération ne modifie pas le workflow de publication finale, ne crée pas de
reçu de publication finale intégré et ne contacte jamais les wikis. Elle ne
doit pas être lancée pour un débat **déjà clôturé hors ligne** par une autre
méthode et dont le dossier est figé.
