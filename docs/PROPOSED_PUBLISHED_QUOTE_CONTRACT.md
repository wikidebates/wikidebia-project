# Proposition expérimentale : provenance des citations anglaises publiées

**Statut : projet de contrat, non actif.** La norme 1.2.88 et ses règles
RND-003, RND-004 et RND-006 restent applicables aux sorties actuelles.
La présente proposition et le module wikidebia_published_quote_review.py
préparent une migration conjointe des normes, du kit et du validateur.

## Deux provenances, une seule occurrence source

- Traduction IA : conserver le contrat Citation→Quote existant, y compris
  les métadonnées documentaires françaises conservées et la mention unique
  AI-translated quote. Ne pas modifier les anciens Works ni leurs reçus.
- Traduction publiée : donner la priorité à un passage anglais réellement
  publié, correspondant intégralement à la citation française. La source
  demeure verrouillée ; l'édition anglaise est citée pour elle-même. Aucun
  titre, auteur, pagination, éditeur ou date d'édition ne doit être inventé
  ni transféré mécaniquement de la notice française.
- Le routage MIA reste déterminé par le lien littéral de la Citation.
  Une recherche infructueuse, une panne, une ambiguïté et un reçu absent
  sont des situations distinctes. La modalité anticipée et la modalité
  intégrée réemploient les mêmes reçus. Une traduction IA reste possible
  avec son avertissement si aucune version publiable n'est retenue ;
  un échec technique ne devient jamais une preuve d'absence de traduction.
- Les arguments anglais réutilisés ne sont pas retraduits automatiquement.

## Preuves et décisions distinctes

1. Vérifier le retour du résolveur contre le verrou FR courant, l'empreinte
   de la requête et celle du retour. L'empreinte attendue doit provenir de
   l'exécution de confiance. Le reçu conserve la source stable, la preuve
   de l'occurrence actuelle et historique, le document EN (URL, révision,
   corps et blocs), les coordonnées exactes, les empreintes des fragments
   et la décision linguistique. Ne jamais substituer une autre édition
   ou un extrait raccourci sans nouvelle preuve. Un reçu importé ne
   confère aucun droit et une empreinte ne prouve pas la vérité d'une revue.
2. Reconstituer le texte exact ; conserver les omissions attestées et
   signaler les fragments discontinus par une ellipse explicite […]. Une
   mise en forme nécessaire doit être vérifiée au rendu, sans altérer
   le texte publié. La proposition expérimentale refuse pour l'instant
   les valeurs qui demandent un échappement wikicode.
3. Revue distincte de l'édition : vérifier auteur, titre publié, référence,
   lien EN, date, volume, page, etc. selon disponibilité. Une valeur
   inconnue reste absente après examen. Vérifier les crédits du traducteur
   et conditions d'attribution. Si le modèle ne permet pas de représenter
   une attribution nécessaire, la proposition reste bloquée.
4. Examen distinct des droits de réutilisation du passage exact pour le
   site cible : documenter le fondement (domaine public, licence compatible,
   permission explicite, ou exception de citation examinée), les preuves,
   la date, le responsable et les conditions. Aucun signal automatique
   du site source ne suffit. Ces catégories servent à structurer une
   revue, pas à présumer qu'une exception ou licence s'applique.
5. Contrôler les doublons dans tous les lots et par rapport aux pages
   publiques, pour toutes les citations, y compris les traductions IA.
   Ne pas créer de doublon entre pages distinctes. Un argument partagé
   ne constitue qu'une page. Les doublons historiques ou les conflits
   exigent un choix éditorial explicite ; ni suppression ni réécriture
   automatique de la citation française. Les diagnostics incomplets ne
   garantissent pas l'absence de doublon.
6. Revue de complétude indépendante, contrôles de ratio et de rendu,
   puis convergence sémantique et verrouillage existants. Ne pas confondre
   le statut d'une proposition ou un accord de réutilisation avec une
   autorisation de publication wiki.

## Modification normative et contrôles à activer ensemble

RND-003 : préserver le contrat historique pour IA ; pour une traduction
publiée, permettre la notice EN vérifiée et lier chaque valeur documentaire
modifiée au dossier d'édition et à la source française d'origine.

RND-004 : ajouter AI-translated quote uniquement pour les traductions IA.
Préserver les autres avertissements et ne pas retirer un avertissement
historique ambigu sans examen. Pas d'étiquette IA sur un passage publié
effectivement attesté.

RND-006 : maintenir la distinction entre adaptation documentaire ordinaire
et citation textuelle. Une citation publiée n'est pas une nouvelle traduction
libre d'une notice ou d'un extrait.

WDV-MWK-021 : deux branches explicites ; comparer les valeurs rendues au
verrou et contrôler séparément la provenance, le lien vers l'édition,
l'empreinte du passage et la présence/absence de l'avertissement. Refuser
une preuve inconnue, absente, altérée ou rattachée à une autre occurrence.
WDV-MWK-024 : conserver les revues de complétude, y compris pour les
passages publiés ; le faible ratio demeure un déclencheur de revue.

La compatibilité doit être fondée sur le schéma et les capacités, pas sur
le numéro du kit. Une absence de provenance nouvelle dans un ancien
verrou signifie l'ancien contrat IA, jamais une approbation publiée.
La migration doit mettre à jour simultanément les copies normatives,
catalogues, schémas, exemples, tests, métadonnées de livraison, mémoires
de traduction et gardes de rendu/publication pertinentes. Le validateur
doit vérifier lui-même les preuves structurées, et non seulement faire
confiance à des booléens générés par le kit.

## Portée de la première implémentation

Le module expérimental construit des candidats depuis des handoffs
inspectés et rejette les incohérences d'identité, de fragments, de décision
et de document. Une proposition exige des revues distinctes de l'édition,
des droits et de la complétude. Elle conserve la provenance, propose les
champs de la notice anglaise et n'ajoute pas l'avertissement IA. Elle ne
modifie aucun verrou ni modèle wiki. Les preuves déclaratives doivent être
vérifiées par les relecteurs ; aucun accès juridique automatique, aucune
approbation de publication, aucune règle normative active n'est introduite.

## Preuve autonome et contrôle indépendant

Le contrat pur `wikidebia_published_quote_contract.py` est également embarqué
à l'identique dans le validateur, sous `published_quote_contract.py`.
Le test inter-dépôts vérifie la parité des deux fichiers et leur compatibilité
avec un vrai retour synthétique du résolveur. Le dossier evidence-1 conserve
le candidat complet, la fiche de revue, la projection et les empreintes.
La vérification autonome recalcule la projection, contrôle le lien source
MIA, et exige le verrou FR, la page et l'occurrence reconstruite depuis la
provenance d'import comme entrées indépendantes. Une preuve importée de
l'autre occurrence ou modifiée n'est pas acceptée.
Ce contrat vérifie l'intégrité et les déclarations, non leur véracité. Il
reste expérimental jusqu'au raccordement complet aux verrous, au validateur
MediaWiki et aux contrôles globaux. Aucun changement de norme active ici.
