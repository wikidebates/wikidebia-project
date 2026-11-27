# Raccordement expérimental au résolveur de citations

Ce raccordement est une interface documentaire **en lecture seule**, et non une
nouvelle procédure de publication. Il est testé contre le commit
`7b8d3723c76af0cd937211392282c9cd909e8127` du dépôt
[wikidebia-quote-resolver](https://github.com/wikinuma/wikidebia-quote-resolver).

## Produire les requêtes à partir du Work

Après verrouillage du français (revue de contenu appliquée ou source historique
gelée), utiliser l'interpréteur Python du kit :

```bash
python kit/scripts/wikidebia_quote_bridge.py DEBAT --work-id WORK export
```

L'export vérifie le workspace, le corpus et l'arbre du contenu français, puis
reprend les paramètres littéraux de chaque Citation verrouillée des arguments
actifs à traduire. Les pages anglaises réutilisées sont exclues. Le titre et la
révision viennent de la provenance d'import; l'empreinte du fichier importé est
contrôlée. Une révision absente reste nulle. Aucun nouveau numéro de révision
n'est déduit d'un titre. Le résolveur devra rattacher les paramètres à une
occurrence unique de la révision réelle.

Les requêtes, de 200 occurrences au maximum, sont écrites dans
`.state/editorial-workspaces/DEBAT/WORK/audits/quote-resolver/requests/`, sous
leur empreinte, avec un fichier privé (0600). La sortie standard donne seulement
les compteurs, empreintes et chemins. L'option répétable `--page-id` sélectionne
les arguments souhaités; `--batch-size` réduit la taille des lots. Les citations
sans lien MIA sont transmises au classificateur local du résolveur et ne
déclenchent aucune recherche distante.

## Résoudre à la demande ou réutiliser les travaux anticipés

Depuis le checkout du résolveur, avec la même base d'état privée que la
campagne anticipée :

```bash
python translation_handoff.py --state "$STATE" prepare --request "$REQUEST"
python translation_handoff.py --state "$STATE" prepare --request "$REQUEST" --lookup-only
```

Le premier mode correspond à la récupération intégrée : il revalide les
reçus disponibles et recherche les passages manquants. Le second correspond
à la récupération anticipée : il réemploie les reçus de la campagne déjà
effectuée (dans la même base, ou importés dans une autre base privée), sans
relancer de recherche de correspondance. Les deux modes revalident les
sources épinglées et documents cibles. Les paquets privés nécessitant une
décision de revue sont traités par le protocole existant du résolveur.

Le mode anticipé sans reçu renvoie `insufficient_evidence` avec le motif
`prepared_receipt_not_found_search_not_run`. Un reçu non revalidé renvoie
`retry_documentary`. Aucun de ces états ne prouve l'absence de traduction
publiée et aucun ne préremplit de citation. Le mode intégré peut alors être
demandé explicitement. Les citations non-MIA suivent le routage IA.
Le test inter-dépôts compare les deux modes sur des bases distinctes :
même occurrence, même reçu, même passage exact, et aucune recherche
supplémentaire dans le mode anticipé.


### Commande de préparation intégrée au kit (expérimentale)

Dans un environnement disposant du dépôt résolveur, de son commit épinglé et
des dépendances déjà installées, il est possible d'enchaîner export,
préparation et inspection de tous les lots du Work :

    python kit/scripts/wikidebia_quote_prepare.py DEBAT --work-id WORK \
      --resolver-root /chemin/vers/resolver --state /chemin/prive/etat \
      --mode prepared

Utiliser `--mode integrated` pour réutiliser les reçus existants et rechercher
les passages manquants. Le mode `prepared` exige une base privée existante
(éventuellement alimentée par un transfert sélectif) et ne recherche pas
les correspondances absentes. Le répertoire d'état doit être privé (0700),
hors des dépôts, ou dans `.state/quote-resolver` du projet / `.cache` du
résolveur ; il ne peut pas se trouver dans un Work ou un verrou éditorial. Les deux modes interrogent encore les sources
épinglées pour revalider les preuves. Les plafonds `--audit-budget` et
`--retrieval-budget` sont communs à tous les lots; `--timeout` borne chaque
processus. `--page-id` et `--batch-size` limitent le périmètre.

La commande exécute les modules Python et, en mode intégré, les catalogues
et l'index bibliographique issus de l'objet Git épinglé, dans un répertoire
temporaire privé. Aucun fichier Python non suivi, aucune modification locale,
aucune variable d'environnement secrète du kit n'est transmis. Les résultats
restent dans la base privée et les répertoires de handoff existants; le bilan
contient les chemins et empreintes vérifiés, pas les passages. En cas d'échec
partiel, les retours déjà écrits restent privés; aucune préparation globale
réussie n'est annoncée. L'opérateur doit encore traiter les paquets de revue
et les contrôles des droits. Aucun déclenchement automatique dans le flux
normal ni sélection ou publication de citation n'est introduit.

## Inspecter le retour contre le verrou courant

```bash
python kit/scripts/wikidebia_quote_bridge.py DEBAT --work-id WORK inspect \
  --request "$REQUEST" --handoff "$HANDOFF" --handoff-sha "$SHA"
```

L'empreinte SHA est celle fournie par le résolveur à la préparation. La
commande relit le verrou français courant, reconstitue les identités attendues,
contrôle la couverture exacte du retour, les empreintes de requête, paquet,
reçu et fragments, ainsi que leur rattachement aux paramètres source.
Elle donne un bilan agrégé sans recopier les citations. Elle ne crée aucun
nouveau reçu de revue linguistique, n'approuve aucun droit et ne préremplit
aucune citation anglaise. Un digest est un contrôle d'intégrité, pas une
preuve indépendante de la véracité d'une décision éditoriale.

Les citations identiques présentes sur plusieurs pages françaises actives
sont signalées à l'export; les passages anglais identiques retrouvés dans
un même lot sont signalés à l'inspection. Aucun doublon n'est supprimé
automatiquement. Le contrôle inter-lots décrit ci-dessous doit précéder
utilisation éditoriale de ces passages.

## Limites avant activation en production

- Le transfert privé est disponible dans registry_transfer.py du résolveur.
  Le parcours automatique du kit et le transport effectif entre les deux
  environnements restent à intégrer.
- Les citations sans révision française, modifiées ou ambiguës ne sont pas
  automatiquement rattachées. Il ne faut pas inventer de révision.
- Les règles actuelles de traduction demeurent inchangées. Une future
  modification normative doit distinguer la provenance publiée de la
  traduction IA, vérifier les références d'édition anglaises, les droits,
  les doublons et conserver les contrôles existants de complétude et de rendu.
- Les commandes n'écrivent ni dans les verrous français, ni dans les fiches de
  traduction, ni dans les wikis. Ne pas employer un retour de ce module comme
  attestation de publication ou de conformité.

Les tests ciblés emploient les fixtures de workspace du kit. Le test
inter-dépôts utilise les vrais parseurs et registres avec des documents,
révisions et décisions synthétiques, sans appel wiki ni modèle. Le replay
documentaire sur les sources publiques reste un test du dépôt résolveur.


## Transfert sélectif et doublons entre lots

Le résolveur accepte les fichiers de requête privés du kit. Sa commande
registry_transfer.py select calcule un sélecteur à partir des lots (options
--request répétables), constitué uniquement d'empreintes. Il permet
d'exporter les reçus utiles depuis la base de campagne. Voir
experiments/REGISTRY-TRANSFER.md. Les lots de plusieurs verrous ou ayant des
occurrences communes sont refusés. Le test inter-dépôts utilise les vrais
fichiers, transfère vers une seconde base et résout sans nouvelle recherche.

Contrôler ensemble les retours du débat:

    python kit/scripts/wikidebia_quote_duplicates.py DEBAT --work-id WORK \
      --batch REQUEST_1 HANDOFF_1 SHA_1 \
      --batch REQUEST_2 HANDOFF_2 SHA_2

Chaque lot est revérifié contre le verrou; une occurrence répétée ou manquante
bloque le bilan complet. --allow-partial permet un diagnostic explicitement
incomplet. Le rapport sépare les textes exacts après normalisation Unicode
NFC et des espaces, les mêmes mots avec ponctuation/casse différente, les
chevauchements de coordonnées du même document, les similitudes lexicales
élevées et les chevauchements partiels. Une référence à la même œuvre ne
suffit pas. Seuls identifiants, empreintes et mesures sont émis; aucune
suppression ou correction. Les comparaisons lexicales sont bornées et ne
détectent pas toutes les paraphrases; les limites de longueur, de paires et
de calcul sont signalées sans affecter les groupes exacts. Les ellipses
explicites et les fragments discontinus ne sont jamais réunis en un
prétendu passage contigu.

Le périmètre FR comprend toutes les Citation du verrou des arguments actifs,
même sur les pages EN réutilisées. Le périmètre EN ne couvre que les passages
publiés reconstruits dans les handoffs fournis, et non les citations traduites
par IA, les pages EN réutilisées ou le wiki public entier. Diagnostic
éditorial uniquement, pas verrou de publication.


## Comparaison avec les citations publiques des deux wikis

Le module public_quote_index.py du résolveur produit un instantané privé
des modèles Citation (FR) et Quote (EN), tous fournisseurs confondus.
Il peut être rafraîchi par révision; voir experiments/PUBLIC-QUOTE-INDEX.md.
La comparaison est facultative et indépendante de la résolution MIA:

    python kit/scripts/wikidebia_quote_duplicates.py DEBAT --work-id WORK \
      --batch REQUEST_1 HANDOFF_1 SHA_1 \
      --public-index fr FR_INDEX FR_SHA --public-index en EN_INDEX EN_SHA

Le kit vérifie l'empreinte, le contrat de normalisation, la langue, la
couverture et les révisions enregistrées dans l'instantané. Il compare les
citations FR actives et les fragments EN déjà inspectés aux empreintes
publiques. Seule la révision FR importée elle-même est exclue : une page
de même titre à une autre révision reste à examiner, car le titre peut être
réutilisé. Une citation non épinglée ne bénéficie pas de cette exclusion. En anglais, tous les résultats sont signalés si la cible
n'est pas encore déterminée. Les doublons historiques restent des anomalies.

Par défaut, un index incomplet ou âgé de plus de 24 heures est refusé.
--max-index-age-hours permet de définir un seuil (au plus sept jours);
--allow-partial-public-index permet uniquement un diagnostic limité, dont
la couverture est explicitement qualifiée. Une empreinte confirme
l'intégrité de l'index transmis, non l'état actuel du wiki. Les résultats
sont des identités et des mesures, sans texte. L'index global repère
l'égalité du wikicode normalisé et les mêmes mots; il ne garantit pas
l'équivalence du rendu ni le repérage des chevauchements partiels et
paraphrases sur tout le wiki. Le contrôle lexical inter-lots reste distinct.
Aucune publication n'est autorisée sur la seule base de ce rapport.

## Préparation de la migration vers les citations publiées

Le contrat expérimental est décrit dans docs/PROPOSED_PUBLISHED_QUOTE_CONTRACT.md
à la racine du dépôt. Le module wikidebia_published_quote_review.py prépare
les propositions et leurs revues sans modifier la traduction. Les règles
actives de rendu et de publication restent inchangées : aucune proposition
n'est une citation anglaise verrouillée ni un droit de publication.


Produire les candidats et fiches de revue privées :

    python kit/scripts/wikidebia_published_quote_review.py DEBAT --work-id WORK \
      --request REQUEST --handoff HANDOFF --handoff-sha SHA

Les fichiers immuables sont placés dans audits/quote-resolver/published-quotes
du workspace. Copier la fiche de revue vierge vers un nouveau fichier privé
avant de la renseigner à partir des preuves effectivement consultées. Ne pas
inventer d'autorisation ou compléter une fiche sans revue.

Vérifier une fiche renseignée contre le retour et le verrou courants :

    python kit/scripts/wikidebia_published_quote_review.py DEBAT --work-id WORK \
      --request REQUEST --handoff HANDOFF --handoff-sha SHA \
      --candidate-sha CANDIDATE_SHA --review REVIEW_FILE

Le résultat est une proposition privée et non un verrou de traduction.
L'échappement du wikicode qui exigerait une preuve de rendu est pour
l'instant refusé, sans réécrire le passage. L'empreinte de la fiche reste
liée à l'occurrence et au retour inspectés.

## Contrôle final des doublons avant verrouillage anglais (expérimental)

Après production de l'index EN avec public_quote_index.py, importer son
instantané privé et son empreinte de confiance :

    python kit/scripts/wikidebia_quote_index_stage.py DEBAT --work-id WORK \
      --index EN_INDEX --sha256 EN_SHA

Renseigner `quote_public_index_sha256` avec cette empreinte dans la revue
anglaise de travail. Le profil de citation publiée exige cette preuve;
un parcours IA historique peut l'utiliser sur option. La finalisation
contrôle les textes réellement sélectionnés et écrit un diagnostic sans
texte dans reports/en_quote_duplicate_audit.json. Un doublon exact bloque;
les mêmes mots avec une forme différente demandent examen. Le validateur
recalcule le reçu avec l'index embarqué dans le dossier privé de preuves.
Le contrôle ne se substitue pas aux preuves de droits, de complétude, ni
à la vérification du wiki public avant publication. Un instantané périmé
avant application ou rendu doit être actualisé; l'automatisation du
rafraîchissement sans refaire la revue sémantique reste à intégrer.

### Actualiser l'index sans rouvrir la revue

La commande précédente accepte `--refresh` après production d'un index EN
actualisé par le résolveur. Elle sélectionne cet instantané privé pour le
Work sans modifier la revue, ses empreintes ni les copies verrouillées.
Avant application, rendu et première autorisation de publication, le kit
recalcule le contrôle sur les mêmes citations avec l'instantané choisi le
plus récent (ou l'original s'il est encore frais). Un doublon nouveau
bloque; un retour à un index plus ancien est refusé. Les diagnostics sont
conservés dans les audits privés. L'autorisation initiale enregistre le
contrôle de prépublication. Les publications déjà autorisées et reprises
restent régies par leur contrat de reprise existant; une vérification
adaptée aux écritures partielles reste nécessaire avant activation. La
production automatique de l'index est encore distincte de sa sélection.

## Sélection des propositions dans la revue anglaise ouverte

Après la préparation normale de la revue anglaise, sélectionner les dossiers
`evidence` issus de fiches réellement relues, sans recopier leurs citations ni
leurs références manuellement :

    python kit/scripts/wikidebia_published_quote_selection.py DEBAT --work-id WORK \\
      --evidence EVIDENCE_1.json --evidence EVIDENCE_2.json \\
      --index-sha256 EN_INDEX_SHA

Les fichiers doivent être ceux du répertoire privé content-addressed du Work.
Le SHA de l'index est celui déjà placé dans le workspace par le module de
staging. L'index peut être ajouté plus tard, mais la finalisation du profil
publié exige toujours un index frais et complet. La sélection est atomique,
idempotente, et ne choisit pas entre propositions concurrentes. Elle refuse
une citation déjà travaillée ou approuvée, sauf répétition strictement
identique de la même sélection. Elle ne renseigne aucune attestation de
complétude supplémentaire et ne change pas les statuts de revue ; il faut
achever les contrôles éditoriaux habituels avant de finaliser. Aucun verrou
FR, aucune revue scellée, aucune page wiki n'est modifié. Profil encore
expérimental, non publiable.


## Collecte et actualisation en une commande

Dans un environnement qui possède déjà le dépôt expérimental et les
dépendances Python du résolveur :

    python kit/scripts/wikidebia_quote_index_collect.py DEBAT --work-id WORK \
      --resolver-root /chemin/vers/wikidebia-quote-resolver

La commande exécute le producteur public existant, au commit épinglé dans
le kit et la CI. Elle n'effectue ni clone ni installation, ne lit pas les
fichiers Python modifiés du checkout et ne transmet pas les identifiants
de publication ou les secrets de l'environnement. Elle réutilise un
index déjà sélectionné et frais, sauf avec --force; sinon elle collecte
les révisions courantes et télécharge seulement le contenu nécessaire.
--previous-sha256 permet de désigner un index préalablement placé dans le
Work; le budget de requêtes et la durée du processus sont bornés.
Un échec ou une interruption après le début de la collecte laisse un
marqueur bloquant : il est interdit de continuer sur l'ancien index.
Seul un nouvel instantané complet, intègre et postérieur au début de
cette tentative permet de reprendre. La sélection des propositions et
la finalisation du brouillon utilisent le plus récent instantané
sélectionné. Aucun appel réseau n'est ajouté aux étapes hors ligne.
Exécuter cette commande avant la première publication pour renouveler
l'index si nécessaire. L'autorisation historique d'une reprise reste
distincte : le contrôle frais de ses écritures partielles n'est pas
encore implémenté.


## Reprendre une publication anglaise partielle

Pour les Works ayant opté pour le contrôle global, avant de reprendre des
écritures EN sans reçu anglais final, produire un index postérieur à
l'autorisation initiale avec la commande de collecte et --force. La
publication reproduit le reçu documentaire historique, puis effectue un
nouveau contrôle sur l'index complet et frais. Pour chaque destination
déjà présente dans cet index, elle relit sa révision courante, son contenu
et, si elle a été écrite, les preuves MediaWiki (identité de page/révision,
parent, auteur, résumé, balises, date). Seule une révision conforme au
plan autorisé peut être exclue pour son propre argument. Un doublon sur
une autre page reste bloquant, même si cette page appartient aussi au plan.
Une révision changée depuis l'index impose un nouvel examen. Le reçu
historique et la release restent immuables. Les diagnostics de reprise
sont privés et n'autorisent pas de nouvelle écriture par eux-mêmes.

Le contrôle est non atomique; il ne garantit pas l'absence de modifications
concurrentes après la lecture ni ne distingue deux écritures strictement
identiques du même compte. Il ne s'applique pas aux reprises en lecture
seule, aux publications EN déjà accompagnées de leur reçu final, ni aux
Works historiques sans contrôle global. Le profil publié reste expérimental.


## Unicité dans le futur parcours actif, même sans citation publiée

Le contrôle des doublons ne dépend pas de la réussite de la recherche MIA.
Lors d'une nouvelle finalisation avec des citations, le futur profil actif
exigera un index public complet et frais, y compris pour un Work entièrement
traduit par IA. Un index local déjà sélectionné est utilisé même si son SHA
n'a pas été recopié dans le brouillon. Le reçu et le contrat d'unicité sont
liés aux deux verrous EN et vérifiés par le validateur indépendant.
Les revues historiques déjà scellées restent lisibles sans preuve inventée.
L'activation générale reste volontairement bloquée dans cette branche.
