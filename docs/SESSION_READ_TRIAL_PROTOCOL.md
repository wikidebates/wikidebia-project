# Essai contrôlé de continuité de session IA — parcours technique de reprise

Ce document constitue le **protocole public immuable** à fournir à deux
conditions expérimentales, `control` et `handoff`. Il n'autorise aucune
écriture wiki, aucune modification des règles de traduction et aucune
modification du corpus. Les deux clones doivent partir du **même commit Git**,
avec la même version de cet unique fichier de protocole.

## Tâche technique à accomplir

Sur une copie isolée du dépôt, expliquer, preuves de fichiers/fonctions à
l'appui, comment le programme décide de reprendre en sécurité un Work
interrompu après une revue française ou un checkpoint de publication française.
Distinguer une reprise autorisée, une preuve/revue périmée et un blocage.
Vérifier la cohérence avec les garde-fous en place après le correctif #137,
sans rejouer d'écriture ni traduire des pages. Livrable final : un rapport
technique court mentionnant les chemins/fonctions et **trois invariants**
de sécurité, avec les tests existants qui les couvrent. Les conclusions
incertaines doivent être identifiées comme telles.

Une inspection de `AGENTS.md`, `kit/GUIDE_GLOBAL_RESUME.md`,
`kit/scripts/wikidebia_global_resume.py`,
`kit/scripts/wikidebia_french_checkpoint.py` et des tests pertinents est
autorisée, mais ne constitue pas une liste exhaustive obligatoire. Les
participants peuvent consulter d'autres fichiers publics si nécessaire.
Ne jamais lire ou exporter `private/`, `.state/` pour autre chose que
la journalisation de l'essai, `corpus/`, les jetons, les logs bruts ou
les données personnelles.

## Sessions et conditions

- **Session 1** (pour chaque condition) : trouver les principaux points
  d'entrée/fonctions, vérifier au moins une preuve et interrompre le travail
  **avant** le rapport final. Le contenu éditorial ne doit pas être modifié.
- **Session 2** : reprendre sans accès à la conversation de la session 1,
  poursuivre la recherche nécessaire puis rédiger le même rapport final.
- **Groupe control** : aucune passation narrative créée pour la session 2.
  Les états et outils techniques du dépôt restent toutefois disponibles.
- **Groupe handoff** : au terme de la session 1, joindre à la session 2
  uniquement une note courte suivant `docs/SESSION_HANDOFF.md`, contenant
  les chemins publics lus, décisions vérifiées, pistes écartées et SHA de
  commit. Les journaux de lecture ne font **pas** partie de cette note.

Utiliser deux clones indépendants sans changer de branche/commit durant les
deux conditions. Pour limiter les biais, ne pas communiquer à l'agent les
métriques de lecture du premier groupe avant la fin du second ; si possible,
alterner l'ordre des conditions sur plusieurs essais. Ne pas dissimuler de
texte source nécessaire à la qualité du diagnostic. Tout arrêt prématuré,
révision du protocole, différence de modèle/configuration ou changement de
base doit être consigné ; il invalide la comparaison correspondante.

## Instrumentation et validation

Lorsqu'une lecture complète d'un fichier suivi par Git est nécessaire,
utiliser volontairement `tools/session_read_capture.py`, avec un
`--session` pseudonyme distinct (deux sessions contiguës par clone).
L'outil ne peut pas capturer toutes les lectures effectuées dans une
conversation ou par les outils internes du modèle. Noter dans le bilan
toute lecture hors instrumentation ; ne pas l'inventer dans le journal.
Éviter toute sortie des contenus sensibles.

Après chaque condition, faire évaluer le rapport final selon ces mêmes
critères par une personne indépendante :
(1) fonctions/chemins vérifiables ;
(2) trois invariants compatibles avec les reçus/checkpoints signés ;
(3) absence de fausse autorisation d'écriture, de modification de contenu
français ou de régression de traduction. Consigner `passed`, `failed`
ou `not_reviewed`. Cette appréciation est une attestation humaine,
jamais calculée à partir d'une empreinte.

Dans chacun des clones, finaliser les preuves **après au moins deux sessions** :

```sh
python tools/session_read_trial_manifest.py \
  --condition control --task-id issue81_checkpoint_resume \
  --protocol docs/SESSION_READ_TRIAL_PROTOCOL.md \
  --task-completed --quality-review passed
```

Employer `--condition handoff` dans l'autre clone. Ne fournir
`--task-completed` que si le rapport a réellement été terminé ;
`--quality-review passed` uniquement si la revue indépendante a
réellement conclu au succès. Les valeurs par défaut sont un travail
inachevé et une qualité non revue. Le manifeste `.state/control-trial.json`
ou `.state/handoff-trial.json` reste local et ne doit pas être committé.

Pour rapprocher les deux résultats, copier **uniquement les fichiers privés
d'événements et de métadonnées** vers un environnement d'analyse isolé,
sans inclure de textes lus, secrets ni fichiers de corpus, puis lancer
`tools/session_read_compare.py` en précisant les quatre chemins. Le
comparateur exige même identifiant de tâche, même commit, empreinte du
protocole identique, journaux intacts et une revue qualité déclarée.
Il ne démontre ni l'absence d'autres lectures, ni des économies de crédits,
de tokens ou de temps. Sans deux véritables sessions IA par condition,
l'outil ne produit au mieux qu'un **test d'intégration instrumenté**,
pas un résultat expérimental de Codex Cloud.
