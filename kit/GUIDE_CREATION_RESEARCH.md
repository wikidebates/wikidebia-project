# Conserver les recherches documentaires de création

Le ZIP de `creation-package` contient désormais un fichier facultatif
`editable/RESEARCH.json`. Un même retour peut enregistrer les brouillons et
leurs recherches avec `creation-import`, dans la même transaction et avec les
mêmes protections de reprise. Aucun appel de modèle ni accès réseau n'est ajouté.

## Parcours habituel

```sh
./wikidebia creation-package --corpus corpus/mon_debat
# Rendre le ZIP corrigé dans incoming/, puis :
./wikidebia creation-import --corpus corpus/mon_debat --archive incoming/retour.zip
```

Lire `context/RESEARCH_HELP.md` seulement pour remplir les notes. Le fichier vide
laisse les notes existantes intactes. Les anciens paquets sans ce fichier restent
importables, mais ne peuvent pas recevoir de nouveaux fichiers ajoutés manuellement.

`resources` conserve les métadonnées réellement trouvées, sans inventer auteur,
langue ou date. Une langue inconnue reste `null`. Chaque ressource nouvelle
possède une clé locale, par exemple `r1`, puis reçoit un identifiant stable `R...`.
Une observation ultérieure peut réutiliser cet identifiant sans recopier la notice.
`source:S0001` désigne une source du registre canonique existant, sans le modifier.

`observations` distingue `located` (ressource repérée) de `consulted`
(contenu effectivement consulté selon le rédacteur). Une consultation exige un
repère, un court extrait et une justification propre à l'argument. Son
appréciation (`supports`, `context_only`, `opposes`, `uncertain` ou `unassessed`)
reste une déclaration à relire, jamais un verdict automatique du kit. Une source
seulement repérée ne peut porter ni extrait prétendument consulté ni conclusion
de pertinence. Le format n'accepte aucun état `verified`.

`searches` conserve la requête exacte, l'outil ou catalogue, la date, les pages
concernées et le résultat : `found`, `no_result`, `inaccessible`, `not_relevant`.
Un résultat négatif ne prouve jamais l'inexistence d'une source. La date
`observed_at` ou `searched_at` n'est pas la date de publication `metadata.date`.
Ne pas reconstituer une recherche historique non enregistrée ni antidater une
consultation. Un champ `recheck_after` peut demander un nouvel examen à partir
d'une date explicite ; son absence ne garantit pas l'actualité de l'information.

## Ajouter des recherches sans réécrire les pages

```sh
./wikidebia creation-package --corpus corpus/mon_debat --research-only
./wikidebia creation-package --corpus corpus/mon_debat --research-only --page-id A0003
```

Sans sélecteur, les pages de la prochaine tâche sont proposées, y compris les
brouillons en attente de revue. `--page-id` peut être répété (20 pages au plus).
Pour le débat, utiliser son `debate_id` seul, sans le mélanger aux arguments.
Le corpus doit toujours être nouveau, son graphe/titres verrouillés et l'anglais
différé. Une page déjà validée ne peut pas être rouverte par cette option.

Les textes et les statuts de `RESPONSE.json` doivent tous rester `unchanged`.
Le kit refuse toute modification de texte ou d'avancement dans ce mode.
Les dépendances sont du contexte en lecture seule, non des pages implicitement
ouvertes à la recherche. La sélection explicite n'altère ni l'ordre ni les lots.

## Persistance et contexte ciblé

Les notes sont cumulatives dans `data/creation_research.json`, à l'intérieur du
corpus privé exclu de Git. Ce registre de travail a son propre schéma et son
empreinte d'intégrité. Il n'est pas une seconde source de statuts de production.
Les réponses identiques sont réutilisées sans duplication. Une nouvelle observation
conserve les anciennes ; des métadonnées concurrentes restent des variantes à
examiner, jamais une fusion silencieuse. Le rapprochement utilise les identités
DOI/URL/empreinte bibliographique déjà employées par le kit. Ce n'est pas une
résolution universelle des doublons ni une vérification distante.

`CORPUS_CONTEXT.json` inclut seulement les notes des pages sélectionnées et de
leurs dépendances, leurs notices utiles et les sources canoniques correspondantes.
Il ne demande pas de relire l'ensemble du carnet documentaire. Les notices
identiques sont conservées une seule fois, avec les observations propres à chaque
page. Une requête partagée conserve son périmètre exact.

Chaque observation est liée au texte de la page, au graphe/cadrage et aux
métadonnées de la ressource. Pour un retour combiné, elle vise le texte retourné
dans le même paquet. Un changement ultérieur produit `page_basis_changed` ou
`resource_basis_changed`. Une échéance atteinte produit `recheck_due`.
Les observations anciennes restent visibles mais leur pertinence doit être
réexaminée. Ces drapeaux ne détectent pas une modification du site distant :
le kit ne contacte jamais les sites cités dans ce parcours.

## Limites et garanties

Le registre canonique `sources.json`, ses usages réciproques, les attestations,
les pages anglaises et les statuts de validation ne sont pas modifiés par les
notes. Les sources finalement retenues exigent encore l'enregistrement et la
vérification par le workflow documentaire ordinaire. Une source repérée ou une
consultation déclarée n'est pas une référence publiable validée.

Tous les contrôles de l'import de brouillons restent actifs : provenance exacte,
immutabilité du contexte, refus de fichiers supplémentaires, de chemins/liens
locaux dangereux et de retours périmés. Une erreur documentaire refuse aussi les
brouillons du même retour, sans changement partiel du corpus. La reprise après
interruption utilise `creation-import --corpus corpus/mon_debat --recover`.
Les limites POSIX, des deux renommages, du verrou coopératif et des sauvegardes
conservées décrites dans `GUIDE_CREATION_IMPORT.md` restent applicables.
Ne pas modifier le corpus simultanément avec un autre outil.

Cette mémoire concerne le corpus courant, pas tous les débats du wiki.
Elle ne remplace aucune recherche d'omissions, revue documentaire ou validation
globale. Aucun gain de tokens/crédits n'a été mesuré : l'objectif est d'éviter
de redemander au modèle le travail documentaire déjà conservé et encore pertinent.

```sh
python -m pytest -q kit/tests/test_wikidebia_creation_research.py
```
