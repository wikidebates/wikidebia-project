# Handoff — Les hommes doivent-ils rejoindre le combat féministe ?

- Branche : `codex/traduction-combat-feministe`
- Commit de référence du snapshot : commit contenant ce fichier
- Date du snapshot : 24 octobre 2026
- Phase : `published`
- Statut : publication bilingue terminée et attestée
- Work : `EDIT-20261023-001`

## Résultat final

Le workflow normal et idempotent a terminé la publication sans divergence :

- les 101 pages anglaises prévues sont créées et leur contenu distant
  correspond au plan signé ;
- les 101 pages françaises contiennent uniquement le lien interlangue attendu ;
- 100 opérations françaises ont été reconnues comme déjà faites et la
  dernière (`A0100`) a été exécutée par la reprise idempotente ;
- la relecture distante finale retrouve exactement les 101 pages anglaises et
  les 101 pages françaises attendues, sans anomalie de contenu, de révision ou
  de provenance d'édition.

Aucune correction française antérieure n'a été rejouée. Aucun titre affiché
français n'a été modifié et aucune forme `oe` n'a été remplacée par `œ`.

## Chaîne signée finale

- baseline :
  `5dfd553e6270157cda7f3561bd98f8fb81c7398640b00792f0f9b98845b4237d` ;
- préflight :
  `88eab051b06dbdce1aaf8abb550cee961a8dcb02c49895a409a872ba601bb041` ;
- autorisation :
  `a959f9e41e65e474ce60b5e493f6b96b27604277f2be94da8c1b1d1096e1396b` ;
- plan anglais :
  `2f3e1dc83966e6b771e7af0dc00808ac5caf0d6c70970dc747bbeeb9e7d099b9` ;
- reçu anglais :
  `f0852ab42fa307640b17e903c0c82755cd5f07dab932a367841999a628c73eba` ;
- état anglais :
  `cb6ac10d35a5655a215012b67e77d3120bd5c9685343ef2b794b4f3bdcb26f0f` ;
- plan français :
  `c109366e7967badee08dbb84ab96d78f6af1fd9e9599887b0ba5e5aa86abe141` ;
- reçu français :
  `25f75ab18c9adcdd526a0df91135cc3a43477c3ea595e707c8eead1319e97743` ;
- état français :
  `1b180e13b037a7c4f2f3d596931adf36d773996d34b5065a1bec5e56482c0caf` ;
- reçu bilingue terminal :
  `c3c0ace7bae3b3fa3e0ba2cce804eca60dff3b7045722317819a09b8e328795f`.

Les preuves autonomes sont conservées dans :

- `runtime/final-publication/` pour la baseline, les plans, le préflight,
  l'autorisation et les reçus de haut niveau ;
- `runtime/receipts/` pour les reçus d'exécution originaux ;
- `runtime/published/en/` et `runtime/published/fr/` pour les états signés ;
- `runtime/workflow/workflow.json` pour l'état final du workflow.

## Succession française préservée

La continuité contient les cinq états historiques français originaux, puis
l'état terminal du 24 octobre 2026. Le checkpoint historique reconnu est
`20261023T132822Z.json`. Les deux corrections post-checkpoint restent ordonnées
et inchangées :

1. restauration des titres affichés contextuels, reçu
   `4f2df84b11ac0e4bcbaa7eae413a9d432d5f783cac96a3ee49fb1f80fb18668c` ;
2. restauration des titres canoniques avec `oe`, reçu
   `f118b68b13dbf1f0128c596d6a53f6ce0bd984b97ede7fdd32b56a7b16b73109`.

Le validateur de continuité accepte ensuite un seul état bilingue terminal,
uniquement si les plans, les reçus d'exécution, les reçus de haut niveau et
les états anglais et français forment une chaîne signée cohérente. Toute
correction après cet état terminal ou toute divergence reste bloquante.

## Intégrité et reprise

`SHA256SUMS` couvre exactement chaque fichier de cette projection et exclut
seulement son propre fichier. La commande suivante doit rester un contrôle
sans écriture distante :

```text
./wikidebia continuity-sync les_hommes_doivent_ils_rejoindre_le_combat_feministe --check
```

La publication est close ; aucune nouvelle exécution de publication n'est
nécessaire en l'absence d'un nouveau Work explicitement autorisé.
