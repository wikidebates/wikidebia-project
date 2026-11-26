# Raccordement expérimental au résolveur de citations

Ce raccordement est une interface documentaire **en lecture seule**, et non une
nouvelle procédure de publication. Il est testé contre le commit
`bbd7b888b9d1edc6d7499cb8844855afdc42e7d4` du dépôt
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
automatiquement. Un contrôle inter-lots et inter-pages devra précéder toute
utilisation éditoriale de ces passages.

## Limites avant activation en production

- Le registre doit être accessible aux deux modalités. Le transfert privé,
  vérifié et portable des reçus entre l'environnement de campagne et
  l'environnement Codex n'est pas implémenté par ce raccordement.
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
