# Mesurer les couts observables des paquets de creation francaise

Cette mesure est **facultative et hors parcours editorial**. Elle compare deux ZIP
**effectivement prepares depuis le meme etat du meme corpus**, avec exactement
les memes pages, normes et fichiers editables : l'un sans bibliotheque de
recherche et l'autre avec `--reuse-library`. Elle lit les fichiers existants ;
elle ne modifie pas le corpus, ne contacte aucun service, ne publie rien et
ne demande aucune generation au modele. Le logiciel refuse les paquets dont
les empreintes ne correspondent plus a leur recu de preparation local.

## Comparaison sur un argument

Preparer les deux variantes *avant* tout import ou modification du corpus :

```sh
./wikidebia creation-package --corpus corpus/mon_debat --research-only --page-id A0001
./wikidebia creation-package --corpus corpus/mon_debat --research-only --page-id A0001 --reuse-library
```

La bibliotheque doit deja exister (voir `GUIDE_CREATION_LIBRARY.md`). Les deux
commandes indiquent chacune un chemin `package_path` sous `outgoing/`.

```sh
./wikidebia creation-measure \
  --pair outgoing/mon_debat_creation_SANS.zip outgoing/mon_debat_creation_AVEC.zip
```

Remplacer `SANS.zip` et `AVEC.zip` par les **vrais chemins** fournis par les
commandes, et conserver les originaux, sans les editer. L'existence du recu
`.state/creation-import/` correspondant est obligatoire ; le rapport ne
pretend pas verifier l'authenticite d'un ZIP fourni arbitrairement.

Pour plusieurs lots ou debats, repeter `--pair` ; chaque paire est controlee
**separement**. Le rapport additionne les compteurs, sans compter deux fois un
meme couple. Limite : 32 paires par execution.

```sh
./wikidebia creation-measure \
  --pair outgoing/debat1_sans.zip outgoing/debat1_avec.zip \
  --pair outgoing/debat2_sans.zip outgoing/debat2_avec.zip
```

## Lire le JSON sans annoncer des economies inventees

- `baseline` et `reuse` donnent les octets du ZIP compresse, des fichiers
  decompresses, du contexte disponible, des instructions et des fichiers
  editables. Ces volumes sont **observables**, mais le modele peut ne pas lire
  chacun de ces fichiers. Les octets ne sont **pas** des tokens.
- `delta_bytes_reuse_minus_baseline` est une **difference signee** : une valeur
  positive signifie que la reutilisation a **ajoute du contexte**. Elle ne
  signifie jamais une economie. Le controle impose l'identite des fichiers
  editables et des contextes normatifs entre les variantes.
- `discovery_hints.candidate_links` compte les suggestions liees aux pages,
  `unique_notices` les notices distinctes transmises et
  `duplicate_notice_references_avoided` les repetitions de ces notices
  evitees dans le document de suggestions. Ces compteurs n'attestent ni la
  pertinence, ni une recherche reellement evitee.
- Les champs `actual_billed_tokens`, `actual_codex_cloud_credits`,
  `real_searches_avoided` et `actual_editorial_quality_change` restent
  **toujours null**. Seule la plateforme de calcul ou une observation
  independante pourrait donner ces informations. Cette commande ne les
  estime pas et n'utilise aucun ratio arbitraire d'octets par token.

**Exemple d'interpretation :** si le contexte disponible gagne 2 000 octets
lorsqu'on ajoute des pistes documentaires, il y a un **surcout potentiel de
contexte**, meme si ces pistes pourraient eviter une recherche ulterieure.
Seule une experience d'utilisation reelle permettrait de determiner si ce
surcout est compense.

## Pour mesurer les gains de quota reels

Construire plusieurs groupes de travaux comparables et observer les demandes
reelles faites au modele, avec et sans suggestions. Garder le meme modele,
le meme niveau d'effort, la meme portee de travail et la meme norme. Eviter
qu'un essai ne reutilise implicitement les conclusions de l'autre. Relever
**a part**, lorsqu'ils sont disponibles, les compteurs d'entree/sortie
rapportes par le fournisseur, la duree et le nombre de recherches repetees.
Ne jamais saisir un chiffre facture par supposition. Une baisse de volume
ZIP n'est pas une baisse prouvee de quota Codex Cloud.

Faire verifier independamment la couverture argumentative, la pertinence et
la verification des sources, les omissions et la qualite des redactions.
Un gain de consommation au prix d'une perte de qualite est un mauvais resultat.
Les exemples artificiels des tests ne sont pas un echantillon de vrais debats.

La mesure ne doit pas etre imposee a chaque travail : elle est une experience
ponctuelle pour decider des optimisations futures. Elle n'autorise pas une
publication et ne modifie pas les moteurs de traduction ou de publication.

Tests : `python -m pytest -q kit/tests/test_wikidebia_creation_measure.py`.
