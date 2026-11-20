# Vérification du contrat source et construction du corpus : résolution du dossier snapshot

## Contexte et priorités

Après les optimisations du validateur jusqu'à la [PR #187](https://github.com/wikidebates/wikidebia-project/pull/187), les mesures sur une extraction réelle de **680 arguments** sous Debian Python 3.13.5 montrent encore environ **0,664 s** pour construire le corpus et **0,253 s** pour vérifier le contrat source avant une reprise. Ces durées sont des médianes de cinq répétitions et ne mesurent ni la traduction ni la publication.

L'objectif de cette correction est de réduire les calculs de chemins redondants sans modifier les pages importées, le graphe, les schémas, les empreintes ni les règles de sûreté.

## Audit détaillé sans corpus privé

Un premier profilage sur une **extraction entièrement synthétique de 680 arguments**, exécuté dans la [PR #188](https://github.com/wikidebates/wikidebia-project/pull/188), a montré que `verify_extraction` absorbe presque tout le temps de `compute_build_contract`. La fonction `_snapshot_page_path`, appelée une fois par page pendant la vérification puis encore une fois pendant l'import, reconstruisait et résolvait le **même chemin racine** à chaque appel, alors que la résolution de **chaque page** doit, elle, rester fraîche.

Exemple de ce profilage, soumis aux variations des machines GitHub Actions :

| Étape instrumentée | Durée observée |
| --- | ---: |
| Contrat source | 0,302–0,308 s |
| Vérification complète de l'extraction | 0,297–0,303 s |
| Résolution des chemins des 681 pages | 0,093–0,095 s |
| Construction du corpus | 1,047–1,083 s |
| Copie et analyse des pages | 0,524–0,535 s |

Les durées des fonctions appelées s'imbriquent : ne pas les additionner. Les écarts entre runners GitHub Actions peuvent être importants ; les mesures **appariées** ci-dessous sont plus fiables pour comparer les révisions.

## Correction proposée

`_snapshot_page_path(snapshot_root, relative, *, _resolved_root=None)` accepte désormais un paramètre **interne facultatif** contenant le résultat déjà calculé de `snapshot_root.resolve()`. Les deux opérations qui parcourent toutes les pages — `verify_extraction` et `copy_import_pages` — résolvent la racine **une seule fois par invocation** et la réutilisent pour leurs propres appels. Les autres appelants continuent à obtenir la résolution d'origine, sans changement d'API obligatoire.

### Sûreté conservée

- **Chaque page** passe toujours par `path.resolve().relative_to(root)` : le chemin final est résolu à nouveau pour chaque fichier, y compris lorsqu'une page est un lien symbolique interne autorisé.
- Les chemins absolus, non portables, avec `..`, les liens pointant hors du snapshot ou une racine qui serait remplacée par un lien externe sont toujours rejetés ; si la racine change pendant une vérification, l'ancien périmètre constitue une borne conservatrice.
- `verify_extraction` continue à contrôler la **taille**, l'**identité** (`st_dev`, `st_ino`), les timestamps `mtime_ns/ctime_ns`, les **SHA-256 de toutes les pages**, le manifeste de snapshot et le manifeste de paquet audité. Le cache de hachage reste limité à l'invocation et réévalue la signature avant toute réutilisation.
- `copy_import_pages` continue à **relire et re-hacher exactement les octets qui sont copiés et analysés**, afin de détecter toute modification entre l'audit et l'import. Aucun cache persistant ou critère de confiance nouveau n'est introduit.
- Aucun `mediawiki`, aucune traduction, aucun changement de structure du graphe ou de contenu éditorial n'intervient.

Les tests du kit complètent désormais les régressions de chemins et de symlinks par quatre nouveaux cas qui vérifient : une seule résolution de la racine au cours de chaque parcours ; une résolution toujours indépendante pour chaque page ; identité des fichiers importés ; équivalence des erreurs de chemins non portables ; rejet d'une page pointant hors du snapshot ; et refus explicite d'une racine redirigée en cours d'opération.

## Comparaison appariée sur le même corpus synthétique

La [CI de la PR #188](https://github.com/wikidebates/wikidebia-project/pull/188) exécute `tools/pretranslation_compare_revisions.py` sur **le même snapshot synthétique de 680 arguments** et compare les révisions avec **toutes leurs validations et leurs reçus**. Ce comparateur refuse de fournir un résultat si un seul fichier construit diffère. Une première comparaison de **3 passages alternés**, [Actions #44763847588](https://github.com/wikidebates/wikidebia-project/actions/runs/44763847588), a confirmé :

- **694 fichiers construits avec SHA-256 strictement identiques**, contrat source inchangé, validations et reçus individuels signés vérifiés.
- Vérification du contrat source lors de la reprise interrompue : médiane **0,206918 → 0,192526 s** (**−6,96 %**).
- Vérification du contrat source lors de la reprise exacte : médiane **0,205545 → 0,192205 s** (**−6,49 %**).
- Étape de construction du corpus : médiane **0,758306 → 0,723646 s** (**−4,57 %**).
- Reprise exacte : médiane **0,296739 → 0,284543 s** (**−4,11 %**).
- Préparation complète : médiane **1,669149 → 1,680781 s** (**+0,70 %**) à cause de la variabilité des autres étapes dans cet échantillon de trois ; **aucun gain global fiable ne doit être affirmé sur cette première mesure**.

Une seconde comparaison appariée de **cinq répétitions alternées** a ensuite été validée dans [GitHub Actions #44764566600](https://github.com/wikidebates/wikidebia-project/actions/runs/44764566600), avec les mêmes garanties : **694 fichiers identiques**, contrats inchangés, reçus signés vérifiés et aucune consultation des wikis.

| Étape / scénario sur 680 arguments synthétiques | Avant | Après | Variation |
| --- | ---: | ---: | ---: |
| Vérification source avant reprise exacte | 0,145107 s | 0,134875 s | **−7,05 %** |
| Construction du corpus | 0,544684 s | 0,525637 s | **−3,50 %** |
| Préparation complète avec validation | 1,358339 s | 1,331558 s | **−1,97 %** |
| Reprise exacte avec reçu vérifié | 0,216546 s | 0,206622 s | **−4,58 %** |
| Reprise après construction avant reçu | 1,030276 s | 1,025691 s | −0,45 % (pas d'accélération nette du scénario) |

Ces durées proviennent de GitHub Actions Ubuntu Python 3.12, **pas** du serveur Debian. Les deux campagnes comportent des temps absolus très différents, reflétant probablement les caractéristiques ou la charge des runners : **ne pas** comparer les absolus entre campagnes. En revanche, la direction des gains de vérification source et de construction est cohérente **au sein** de chaque comparaison appariée.

## Conditions d'intégration

Le kit est livré avec `kit/PACKAGE_MANIFEST_SHA256.json`, `kit/PACKAGE_RECEIPT.json` et `kit/TEST_REPORT.txt` : leur régénération depuis les résultats JUnit et l'auto-vérification officielle demeurent **obligatoires**. Le workflow expérimental de profilage doit être supprimé avant toute fusion.

Après une éventuelle fusion, le serveur Debian peut comparer les révisions sur la **même extraction figée** à l'aide de `tools/pretranslation_compare_revisions.py`, avec la version de référence `11e9643b7205de2dd86bf4a3574beee95324ab97` et les cinq répétitions. Une accélération n'est considérée validée sur Debian que si **tous les contrôles de qualité et d'identité des fichiers** réussissent.
