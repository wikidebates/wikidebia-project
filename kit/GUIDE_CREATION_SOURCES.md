# Enregistrer les références retenues après revue documentaire

Pour les **corpus français nouveaux** dont le graphe et les titres sont déjà
verrouillés, le kit peut reporter une sélection explicitement vérifiée depuis
le carnet privé `data/creation_research.json` vers le registre canonique
`data/sources.json`. Il calcule la notice, l'identifiant `S…`, les usages
réciproques des arguments et les empreintes : l'IA ou le relecteur n'a pas à
recopier ces mêmes métadonnées dans plusieurs fichiers.

**Ce transfert n'est ni une recherche, ni une vérification indépendante, ni une
validation de page.** Un statut `consulted` signifie seulement qu'une
consultation a été déclarée. Le relecteur indiqué dans le retour doit avoir
réellement contrôlé la ressource, sa langue, les métadonnées et son apport à
chaque argument ; le kit ne peut authentifier indépendamment cette personne.
Une déclaration de l'IA non fondée ne doit jamais servir d'attestation.

## Procédure

Enregistrer d'abord les observations avec `editable/RESEARCH.json` du paquet
ordinaire puis `creation-import` (voir `GUIDE_CREATION_RESEARCH.md`). Lorsque
les recherches ont été conservées, préparer une **revue documentaire distincte** :

```sh
./wikidebia creation-package --corpus corpus/mon_debat \
  --research-only --page-id A0003
```

Le ZIP contient alors `editable/SOURCES.json` (vide par défaut) et
`context/SOURCES_HELP.md`. Le contexte fournit uniquement les notes des pages
sélectionnées et de leurs dépendances. Chaque décision de `SOURCES.json`
référence l'identifiant `R…` d'une notice déjà enregistrée et l'identifiant
`O…` de la consultation réellement faite pour la page. Elle consigne le
relecteur, la date, l'examen des métadonnées, la langue, l'attribution d'auteur,
le type de document et la justification de sélection. Le relecteur statue
**séparément pour chaque utilisation**. Les statuts, rôles et champs possibles
sont détaillés dans le fichier d'aide livré avec le paquet.

Laisser `decisions: []`, `reviewer: null`, `reviewed_at: null` ne change rien.
Toutes les attestations de sélection doivent être renseignées explicitement,
aucune n'est prévalidée. Ne pas modifier `context/` ou ajouter de fichiers au
ZIP. Le retour est importé comme les brouillons :

```sh
./wikidebia creation-import --corpus corpus/mon_debat \
  --archive incoming/retour_documentaire.zip
```

Les nouvelles notes et leur sélection **ne peuvent pas être importées dans le
même retour** : enregistrer d'abord les observations, puis effectuer leur
revue sur cette base stable. `SOURCES.json` n'est disponible qu'en mode
`--research-only` ; une rédaction de brouillon ne peut pas devenir une
approbation documentaire par le même acte.

## Conditions et contrôles

- Seules les ressources **francophones** déjà enregistrées dans ce corpus sont
  retenues par ce parcours initial. Les sources d'autres langues restent dans
  les notes et passent par la revue documentaire ordinaire (qui exige notamment
  l'examen d'une édition française disponible). Une langue `null` ne vaut pas
  une langue française.
- Une sélection doit citer une observation `consulted`, `supports`, liée à la
  page exacte, à l'identité documentaire exacte et au contenu/cadrage encore
  courants. Une recherche `located`, `no_result`, `uncertain` ou `context_only`
  ne vaut pas attestation de pertinence documentaire.
- Une observation périmée, dont l'échéance de réexamen est atteinte, ou
  consultée après la date de revue bloque le transfert. Le kit ne surveille pas
  les sites distants : les changements non signalés par les dates ou empreintes
  locales doivent toujours être recherchés par le relecteur.
- Les notices dont la langue, les éléments obligatoires, la date documentaire
  ou l'attribution d'auteur sont incorrects doivent être corrigées par une
  **nouvelle observation réelle**, non par une fabrication automatique. Les
  variantes d'une même URL/DOI sont conservées ; le relecteur doit justifier
  explicitement le choix d'une variante. Un conflit avec une source canonique
  déjà enregistrée bloque l'import, sans remplacement de métadonnées.
- Les sources existantes sont réutilisées par identité documentaire lorsque
  leurs métadonnées sont compatibles. Les usages sont propres à chaque page.
  Un doublon exact est ignoré et un usage contradictoire est refusé ; aucun
  état de vérification préexistant n'est écrasé.
- Les pages `Argument` utilisent `supports_summary`, avec une attestation que
  la source développe le raisonnement lui-même. La page `Débat` peut utiliser
  `supports_introduction`, `pro_reference`, `con_reference` ou
  `neutral_reference`, selon le rôle réellement examiné. Une bibliographie du
  débat exige une portée fondatrice ou panoramique lorsque le rôle l'exige.
- Les modifications de `data/sources.json`, des relations documentaires du
  registre et du journal `data/creation_source_reviews.json` sont préparées
  **dans la même transaction de corpus**. Le wikicode, les états de page, les
  validations, les lots et la publication distante ne sont pas modifiés.

La même commande `creation-import --recover` restaure le corpus antérieur ou
termine un transfert après interruption ; les mêmes limites POSIX et de
renommage que l'import des brouillons s'appliquent. Une divergence inattendue
bloque et conserve les sauvegardes pour examen. Le registre et le journal
restent dans le corpus privé exclu de Git.

Ce mécanisme **ne dispense pas** de rechercher les sources manquantes, de
contrôler l'adéquation des références aux pages, d'éditer la documentation
affichée en wikicode si nécessaire, de mener les revues de contenu/classification
et de passer le validateur complet avant publication.

## Quota

Le gain potentiel provient du réemploi des identifiants et des notices déjà
collectées, plutôt que d'une sortie répétitive de métadonnées et de liens.
Aucun gain de tokens facturés ou de crédits Codex n'a été mesuré ; la sélection
reste une tâche éditoriale. Aucune opération réseau, wiki ou modèle n'est
exécutée par le kit pendant la préparation ou l'import.

```sh
python -m pytest -q kit/tests/test_wikidebia_creation_sources.py
```
