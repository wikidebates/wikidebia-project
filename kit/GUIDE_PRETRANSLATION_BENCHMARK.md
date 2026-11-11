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
