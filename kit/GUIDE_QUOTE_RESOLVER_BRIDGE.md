# Raccordement expérimental au résolveur de citations

Ce raccordement est une interface documentaire **en lecture seule**, et non une
nouvelle procédure de publication. Il est testé contre le commit
`d3d7c0508a74a6988c6d4512b270259a96f79f35` du dépôt
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

Le premier mode revalide les reçus disponibles et recherche les passages
manquants. Le second ne relance pas de recherche de correspondance mais
revalide les sources épinglées et documents cibles. Les paquets privés
nécessitant une décision de revue sont traités par le protocole existant du
résolveur. Une abstention n'établit pas l'absence de traduction publiée.

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
