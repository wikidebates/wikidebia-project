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

## Intégration du verrou en brouillon

La revue anglaise peut maintenant porter `published_quote_contract` (valeur
`wikidebia-published-quote-evidence-1`) et une citation explicitement marquée
`translation_origin=published_translation` avec son dossier
`published_quote_evidence`. Sans marqueur, le chemin historique IA reste
strictement inchangé; une provenance inconnue ou contradictoire est refusée.
La finalisation reconstitue la projection à partir du verrou FR, de la
provenance d'import et des octets vérifiés de la page. Elle garde les
attestations de complétude et le seuil de seconde revue; la référence et le
texte anglais doivent correspondre exactement à la proposition. Les
champs source sans représentation ne sont pas supprimés silencieusement.
Un doublon exact entre deux arguments du même débat bloque la sélection
si l'un des passages est publié. Le profil est propagé aux verrous EN et
le validateur peut vérifier indépendamment le rendu attendu. Le contrôle
est testé sans accès distant. Le garde-fou ACTIVE=False dans le contrat
commun interdit le rendu canonique et l'acceptation normative de ce profil
jusqu'à la migration active des normes et des contrôles globaux. Ne pas
fusionner la PR dans cet état. Aucune autorisation juridique ou wiki n'est
déduite de ces tests.

## Contrôle des citations anglaises effectivement sélectionnées

Le contrat de l'index public est partagé à l'identique par le kit et le
validateur. Le contrôle final porte sur **toutes** les valeurs Quote du
verrou anglais, traductions IA comprises, et non sur les seuls passages
reconstitués dans les handoffs. Un index EN complet pour le périmètre
littéral, intègre et âgé au plus de 24 h est requis pour le profil publié;
les anciens parcours IA restent compatibles (contrôle sur option).
Le rapport est recalculé à la finalisation, lié aux identités de pages,
aux empreintes des citations, au verrou FR et à l'index, puis vérifié de
nouveau avant application et rendu. L'index sans texte est embarqué une
fois dans le dossier privé de preuves afin que le validateur puisse
recalculer lui-même le résultat, sans accès réseau. Il ne constitue pas
une bibliothèque de textes. Les contrôles d'anciens Works vérifient le
reçu à sa date, sans prétendre que le wiki actuel est identique.
Les doublons exacts entre deux pages du débat ou avec une page publique
bloquent; les variantes aux mêmes mots restent des signaux éditoriaux.
Seule une mise à jour autorisée avec titre et révision exacte permet
l'exclusion de sa propre page; un même titre seul ne suffit pas.
Les doublons historiques sans rapport avec la sélection et les 12 modèles
FR invalides ne bloquent pas arbitrairement une nouvelle page EN.
Aucune garantie concernant le rendu développé ou les chevauchements
partiels sur tout le wiki. Une actualisation avant publication reste à
intégrer; aucun droit ni autorisation de publication n'est accordé.
La migration normative et ACTIVE=False restent inchangés.

Le renouvellement documentaire est indépendant de la convergence sémantique :
le reçu original reste immuable, un nouvel index frais est sélectionné dans
le workspace et le contrôle est recalculé sur la même empreinte de périmètre
avant application, rendu et première autorisation de publication. Un échec
sur un index plus récent ne revient pas à un ancien succès. L'autorisation
conserve le résultat de ce contrôle, y compris lors de ses migrations.
Ce mécanisme ne résout pas encore les reprises après écritures partielles
ni la collecte automatique de l'index ; le profil reste inactif.

## Sélection dans le registre de travail

La commande `wikidebia_published_quote_selection.py` relie désormais les
preuves déjà relues au brouillon anglais existant. Elle ne remplace ni les
revues ni l'autorisation : les occurrences restent pending. Le verrou FR,
l'identité de page et de citation, le fichier de preuve privé et son contenu
sont contrôlés avant l'écriture atomique. La commande ne choisit pas entre
deux preuves et ne remplace jamais une autre traduction en cours. Les
répétitions de la même sélection ne modifient pas les décisions prises depuis.
L'index peut être sélectionné en même temps par son empreinte, mais il est
recontrôlé à la finalisation. La reprise des autorisations historiques sans
preuve nouvelle conserve leur format antérieur.

## Test d'intégration Work mixte

Un test synthétique traverse l'extraction/import du corpus, le verrou FR,
la préparation de revue EN, la sélection de preuve, le blocage d'un doublon
IA avec une page publique, la sélection d'un index plus récent, la convergence,
l'application et le rendu. Une page EN réutilisée reste hors des requêtes.
Le test vérifie le garde-fou inactif puis simule l'activation uniquement dans
le processus de test. Les revues et réponses du validateur générique dans la
fixture sont simulées; les tests spécifiques du validateur indépendant restent
nécessaires. Aucun droit, contenu wiki réel ou publication n'est attesté.

## Reprise d'une autorisation existante

Le contrôle de reprise reproduit la décision historique exacte à partir du
verrou et de l'index effectivement utilisés (original ou rafraîchi). Il
refuse un reçu absent, altéré, sans son index, rattaché à une autre release
ou temporellement incohérent. Les migrations de plan préservent la date de
l'autorisation documentaire initiale. Les anciens Works n'ont pas besoin
ni d'index ni d'espace de travail pour ce contrôle. Ce contrôle est local
et ne traite pas les pages déjà créées par le plan comme de nouveaux
conflits. Il ne prouve toutefois pas l'absence de nouveaux doublons sur
le wiki depuis la première autorisation. Une réévaluation fraîche avec
exclusion des seules créations attribuables au plan reste nécessaire pour
imposer une nouvelle décision documentaire à une reprise tardive.
