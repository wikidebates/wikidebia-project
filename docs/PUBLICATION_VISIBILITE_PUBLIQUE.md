# Attestation indépendante de visibilité publique — publication bilingue

Le statut « publié et vérifié » n'est autorisé qu'après une vérification publique, anonyme et exhaustive, distincte des reçus d'écriture.

## Parcours et preuves

Après les écritures anglaises et françaises, mais avant l'installation locale et le reçu final :

1. Le kit ouvre l'URL publique du débat anglais par une connexion HTTPS indépendante, sans cookie, session bot ou jeton.
2. Il vérifie toutes les pages anglaises du plan (créées, ignorées, mises à jour ou réutilisées) au bon titre, avec le modèle attendu et le contenu attesté, dans l'API publique et le HTML public.
3. Il vérifie chaque page française du plan : le paramètre interlangue du wikitexte public doit pointer vers la bonne page anglaise et le HTML public doit contenir ce lien.
4. Il conserve un rapport local signé dans .state/final-publication/<débat>/<Work>/public-visibility-report.json, indiquant l'URL contrôlée, les nombres de pages et liens vérifiés et les écarts exacts.

Les pages anglaises réutilisées tardivement sont comprises lorsqu'elles figurent dans le reçu de réutilisation. Les descendants exclus du plan ne sont pas inventés comme des publications.

## Bilan obligatoire

- « publié et vérifié » : la totalité des pages anglaises et des liens français sont vérifiés par lecture publique.
- « publication partielle » : une page manque, une cible diffère, une page est redirigée, le contenu attendu ne correspond pas, ou le HTML public n'affiche pas le lien.
- « visibilité publique non confirmée » : panne réseau ou API, réponse publique incomplète, accès bloqué, ou vérification impossible.

Les deux derniers états empêchent de créer le reçu final et bloquent le workflow avant son statut terminal. Le programme conserve les reçus d'écriture déjà réalisés pour reprendre sans rééditer les wikis. Une nouvelle tentative peut répéter uniquement la vérification publique.

Le reçu final lie l'URL publique et l'empreinte du rapport. Une reprise de publication déjà terminée conserve la preuve initiale et écrit le nouveau contrôle dans public-visibility-recheck.json.

## Audit autonome (strictement en lecture publique)

    ./.venv/bin/python kit/scripts/wikidebia_public_visibility.py mon_debat --work-id EDIT-20261121-001 --project-root .

Cette commande requiert les plans définitifs et l'accès HTTPS public. Elle ne publie rien et retourne un statut d'échec si toutes les vérifications ne réussissent pas.

## Limites

L'attestation publique contrôle le contenu, les titres, le rendu HTML et les destinations, mais ne remplace pas une revue éditoriale du fond. Les débats historiques déjà clôturés ne sont ni republiés ni rétroactivement transformés en nouveaux reçus vérifiés.
