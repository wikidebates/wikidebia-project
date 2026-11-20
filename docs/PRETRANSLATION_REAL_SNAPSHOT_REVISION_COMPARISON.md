# Comparer deux versions de Wikidéb'IA sur une extraction réelle figée — mode local

## Objectif

Après les [PR #178](https://github.com/wikidebates/wikidebia-project/pull/178), [#179](https://github.com/wikidebates/wikidebia-project/pull/179), [#181](https://github.com/wikidebates/wikidebia-project/pull/181) et [#182](https://github.com/wikidebates/wikidebia-project/pull/182), les gains ont été mesurés **sur des corpus synthétiques**. Le benchmark existant `./wikidebia pretranslation-benchmark --snapshot ...` sait mesurer un snapshot local réel en lecture seule, mais une exécution isolée ne prouve pas l'amélioration **avant/après** sur cette même source.

L'outil `tools/pretranslation_compare_revisions.py` compare deux versions du dépôt **sur le même snapshot figé**, sans contacter les wikis et sans envoyer le corpus, les titres ou les pages vers GitHub. Il utilise uniquement l'historique Git **déjà disponible localement**, le même environnement Python et le script de benchmark de référence, puis vérifie les empreintes et les reçus de chaque exécution.

## Commande sur le serveur Debian

À la racine du dépôt Wikidéb'IA mis à jour et vérifié, avec un snapshot complet **déjà extrait et figé** disponible sous `.state/graph-extract/` :

```bash
.venv/bin/python tools/pretranslation_compare_revisions.py \
  --snapshot .state/graph-extract/NOM_DU_DOSSIER \
  --iterations 3 \
  --output .state/benchmarks/comparaison-pretraduction-reelle.json
```

Remplacer uniquement `NOM_DU_DOSSIER` par le répertoire d'extraction réel, ou transmettre son sous-répertoire `snapshot`. Cette commande ne crée ni compte, ni traduction, ni publication. Le fichier de rapport est local, dans `.state/` ignoré par Git, hors de l'extraction. **Ne jamais placer `--output` dans le snapshot.**

Par défaut, la comparaison oppose :

- **Référence** `ba366eb79b7dc2dc7c1cfe32a54508ed0feac20a` : après les améliorations du validateur #178/#179, mais avant les améliorations du parseur #181/#182 ;
- **Candidate** `HEAD` : le commit Git installé localement au moment de l'exécution. Pour mesurer #181 et #182, le serveur doit déjà disposer du code fusionné de #182 (`1aab5209d1c0520196a21bd0d15ddea851bc2402`) ou d'un commit ultérieur qui le contient.

Pour comparer **l'ensemble de la série** depuis avant la PR #178, préciser explicitement :

```bash
.venv/bin/python tools/pretranslation_compare_revisions.py \
  --snapshot .state/graph-extract/NOM_DU_DOSSIER \
  --baseline 065bb4af6c895a456d7a92e1c9615115f134d5d7 \
  --iterations 3 \
  --output .state/benchmarks/comparaison-toute-serie.json
```

Les deux révisions sont indiquées comme des SHA Git complets ; seules les valeurs `HEAD` ou SHA complets sont acceptées, pour éviter des références mobiles ou des options Git ambiguës. Un historique Git incomplet qui ne contient pas le commit historique provoque un **échec explicite** : aucune commande `git fetch`, `git checkout`, `git reset`, `git pull` ou modification du dépôt n'est effectuée automatiquement. L'outil n'installe aucune dépendance.

## Protocole et contrôle des résultats

1. Vérification de la présence locale des deux commits Git, puis matérialisation temporaire de leurs **fichiers suivis par Git** avec `git archive`. Le dépôt de travail, le dossier `.git` et le snapshot sont préservés. Les liens symboliques et entrées d'archives présentant un risque de sortie du répertoire temporaire sont rejetés ; les archives temporaires sont supprimées.
2. **Comparaison SHA-256 exacte du script** `kit/scripts/wikidebia_pretranslation_benchmark.py` dans les deux révisions. Si l'instrument de mesure diffère, le comparateur refuse de produire une conclusion biaisée.
3. Chaque version est exécutée dans un **processus Python isolé**, avec **le même interpréteur**, les mêmes bibliothèques et un environnement restreint sans variables de secrets, jetons d'accès ou identifiants Pywikibot.
4. **Reconstruction de contrôle indépendante dans chaque version**, avec un horodatage déterministe. Le comparateur confronte le SHA-256 de **chaque fichier généré** et le contrat de construction. Toute différence de contenu, y compris si les deux builds passent séparément leurs validations, **bloque la comparaison avant même de chronométrer**. Les noms et empreintes individuels restent en mémoire locale et ne sont pas présents dans le rapport final ; seul le nombre total de fichiers comparés est conservé.
5. Alternance de l'ordre des versions sur **3 à 20 passages**. Chaque passage exécute les trois scénarios du benchmark avec une itération : construction initiale avec validation et reçu ; reprise interrompue avec nouvelle validation ; reprise exacte avec contrôle du reçu déjà enregistré.
6. Vérification du **SHA-256 signé de chaque rapport**, des validations et reçus exigés par le benchmark, de l'absence d'accès wiki/LLM et de la **constance des empreintes du manifeste et du contrat de construction** ainsi que l'identité des fichiers reconstruits entre les deux versions et pendant toutes les répétitions. Toute divergence invalide le rapport complet, sans utiliser les mesures partielles.
7. Génération d'un rapport JSON signé contenant les **durées brutes**, médianes, écarts-types, durées par étape, gains (y compris négatifs), commits et versions installées des bibliothèques `jsonschema` / `referencing`.

Le rapport **ne conserve ni texte, ni titre des pages, ni chemin privé du snapshot, ni noms de fichiers générés**. Il conserve toutefois ses empreintes SHA-256 et quelques statistiques de volume afin de permettre une vérification de l'équivalence sans révéler son contenu. Le rapport peut rester strictement local.

## Bien interpréter les performances

Les optimisations de validation statique de #178/#179 sont appliquées uniquement avec les versions `jsonschema==4.26.0` et `referencing==0.37.0` attestées par les tests correspondants. Les autres versions conservent les vérifications complètes, mais **les gains mesurés peuvent alors être différents** ; le comparateur indique les versions installées, sans les modifier.

En particulier, ne pas confondre :

- gain sur `cold_build_validate_receipt` : réduction du temps de **construction locale, validation et écriture du reçu**, mais **pas du temps de traduction** ;
- gain sur `resume_after_build_before_receipt` : réduction potentielle des opérations reprises (le corpus n'est pas reconstruit) ;
- gain sur `resume_exact_verified_receipt` : ce scénario conserve les contrôles d'empreintes et de reçu, et les optimisations du parseur ne devraient pas lui apporter un grand gain.

Le rapport **ne mesure jamais les tokens consommés ni les crédits facturés par Codex**. Un résultat nul ou négatif doit être conservé et communiqué, pas filtré.

## Limites et confidentialité

Aucune extraction réelle n'est disponible sur les runners GitHub Actions de cette PR. La CI teste le comparateur sur un **snapshot synthétique complet traité comme entrée locale**, avec un historique Git local, ainsi que les erreurs possibles (archives dangereuses, modifications en cours, rapport modifié, liens symboliques, paramètre de sortie incorrect). Les mesures réelles ne peuvent être obtenues que là où existe une extraction figée, avec les autorisations de lecture adéquates.

L'outil **ne touche pas** aux protections de provenance, à la vérification des octets lors de la copie, aux deux checkpoints français, à la qualité de traduction, aux revues sémantiques bilingues ni à la publication MediaWiki. Les données sources et les reçus du workflow éditorial normal restent intacts.
