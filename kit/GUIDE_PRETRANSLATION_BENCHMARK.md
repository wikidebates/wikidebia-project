# Benchmark des reprises prétraduction

La commande suivante mesure uniquement les opérations techniques locales qui
précèdent la traduction :

```bash
./wikidebia pretranslation-benchmark \
  --arguments 878 \
  --payload-bytes 2048 \
  --iterations 5 \
  --output .state/benchmarks/pretranslation.json
```

Le corpus est synthétique, déterministe et dépourvu de données wiki réelles. Il
utilise jusqu’à 20 arguments racines puis un arbre ternaire alternant
justifications et objections, afin de mesurer aussi la construction d’un graphe
ramifié. La commande ne contacte aucun wiki et n’appelle aucun modèle de
langage.

Une extraction locale déjà figée peut remplacer le fixture synthétique :

```bash
./wikidebia pretranslation-benchmark \
  --snapshot .state/graph-extract/<extraction> \
  --iterations 3 \
  --output .state/benchmarks/pretranslation-snapshot.json
```

Le chemin peut viser la racine de l’extraction ou son sous-répertoire `snapshot`.
Le manifeste, le graphe récursif, les chemins et les liens symboliques sont contrôlés.
La source est strictement en lecture seule ; tous les builds et reçus temporaires sont
créés hors de l’extraction puis supprimés. Le rapport distingue explicitement
`fixture.kind=synthetic` et `fixture.kind=snapshot` et conserve l’empreinte du manifeste.
Le chemin `--output` est refusé s’il vise l’extraction mesurée ou l’un de ses
sous-répertoires.

## Scénarios comparés

Le rapport scellé par SHA-256 compare trois chemins portant exactement le même contrat de
source, paramètres et versions :

1. `cold_build_validate_receipt` construit le corpus, lance le validateur puis
   écrit le reçu ;
2. `resume_after_build_before_receipt` simule une interruption après la
   construction : le build n’est pas refait, mais la source et la validation
   sont revérifiées avant d’écrire le reçu ;
3. `resume_exact_verified_receipt` vérifie la source et le reçu existant, sans
   reconstruire ni relancer le validateur.

Pour chaque scénario, le rapport fournit les échantillons, médiane, minimum et
maximum en secondes. Il indique aussi le nombre et la taille des fichiers du
fixture, les opérations évitées et l’empreinte commune du contrat.


## Profilage facultatif des lectures et hachages

Pour diagnostiquer les opérations *avant* la traduction, activer explicitement :

```bash
./wikidebia pretranslation-benchmark \
  --snapshot .state/graph-extract/<extraction> \
  --iterations 3 \
  --profile-file-io \
  --output .state/benchmarks/pretranslation-io.json
```

Sans `--profile-file-io`, l'outil garde les mêmes scénarios, mesures et
rapports qu'auparavant. Avec l'option, le rapport signé contient
`file_io_profile.counters` en plus des `stage_timings_seconds` déjà
disponibles. Pour chaque **étape nommée et chaque scénario**, les métriques
comportent leurs observations brutes, leur médiane, minimum et maximum :

- `read_bytes_calls`, `read_bytes_total_bytes`,
  `read_bytes_distinct_paths` et `read_bytes_repeated_calls` : appels
  réussis à `Path.read_bytes`, volume exact des octets retournés, nombre
  de chemins distincts et nombre de lectures répétées dans une étape ;
- `read_text_calls` et `read_text_total_characters` : appels réussis à
  `Path.read_text` et caractères Unicode reçus (**pas** des octets disque) ;
- `kit_sha256_calls` et `kit_sha256_input_bytes` : appels réussis et
  octets passés à `wikidebia_corpus_init.sha256_bytes`.

**Portée :** l'instrumentation concerne seulement le processus Python
principal, pendant les étapes instrumentées ; elle ne couvre pas les accès
via `open()` brut, les projections mémoire ni le **sous-processus isolé du
validateur**. Un compteur nul signifie *aucune opération observée par cette
instrumentation*, et non *aucune lecture disque*. Les métriques ne
constituent pas une mesure complète de l'I/O système ni des crédits Codex.

Le profilage ajoute lui-même un petit coût. Il faut donc effectuer **une
exécution séparée sans `--profile-file-io`** pour mesurer des durées
non perturbées. La comparaison d'empreintes et toutes les relectures
nécessaires pour déceler une modification de source entre vérification et
copie restent inchangées. Le traçage ne journalise pas les contenus
historiques ni les titres, et ne conserve aucun cache.

## Ce que le rapport ne mesure pas

Les temps dépendent de la machine, du cache disque et de la charge du moment.
Ils prouvent quelles opérations locales sont évitées ; ils ne prouvent pas une
économie de tokens ou de crédits Codex Cloud. Les champs
`estimated_tokens`, `actual_billed_tokens` et `actual_codex_cloud_credits`
restent donc explicitement à `null`. Une mesure de facturation exige une
télémétrie distincte du produit sur des exécutions comparables.

Le benchmark ne passe par aucune traduction et ne constitue pas une preuve
d’équivalence linguistique. Les contrôles de qualité éditoriale et sémantique
restent inchangés.
