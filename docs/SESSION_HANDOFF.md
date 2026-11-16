# Passation entre sessions IA et audit des relectures (issue #81)

Ce mécanisme **complète** `./wikidebia resume` et les handoffs techniques
existants : ceux-ci font autorité pour les états du Work, les plans, les reçus,
les révisions, les validations et les opérations distantes. Une note narrative
ne peut jamais autoriser une mutation ou remplacer une preuve signée.

## Une seule note de passation courte, dans la conversation de développement

Au début de chaque session, consulter d'abord `AGENTS.md`, puis
`./wikidebia resume` lorsqu'un Work local est en cause, et une éventuelle
note de passation liée à l'issue/PR. Ne relire que les fichiers dont la
conclusion n'est plus valide ou dont le contenu est nécessaire à la tâche.

Pour une enquête technique interrompue, la session sortante peut ajouter
un commentaire concis à l'issue/PR GitHub concernée, en utilisant le
format ci-dessous. **Ne pas créer de nouvelle base d'état, ni écraser
`.state/`, ni committer des informations privées.** La note doit être une
aide à l'orientation, non un nouvel état de production.

```text
Passation IA (issue/PR #…, branche …, commit …)
- Objet et dernier résultat vérifié : …
- Fichiers lus (chemins relatifs publics) : …
- Décisions et raisons / références à des preuves : …
- Hypothèses écartées (et test précis) : …
- En suspens et prochaine action vérifiable : …
- Fraîcheur : commit SHA + fichiers/empreintes à revérifier après changement
- Risques / frontières distantes : aucune, lecture possible, écriture possible
```

Pas de secrets, extraits confidentiels, tokens, logs bruts, corpus privés,
URLs d'authentification ni données provenant de `private/`, `.state/`,
`corpus/`, `incoming/` ou `outgoing/`. Si une piste n'est pas vérifiée,
la désigner comme hypothèse. Éviter les commentaires de passation quand
l'issue/PR et les preuves suffisent déjà. Une nouvelle session ne doit pas
croire une conclusion sans confronter le commit et les empreintes actuels.

## Audit optionnel des relectures

L'outil `tools/session_read_audit.py` accepte un **journal de lectures
explicitement observées**, jamais une inférence à partir de la simple présence
d'un fichier. Il fonctionne hors réseau et ne change aucun workflow.

Exemple de journal privé dans `.state/`, avec une ligne JSON par lecture
*effective et complète* d'un fichier suivi dans le dépôt :

```jsonl
{"session_id":"run_a","path":"kit/GUIDE_GLOBAL_RESUME.md","content_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
{"session_id":"run_a","path":"kit/GUIDE_GLOBAL_RESUME.md","content_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
{"session_id":"run_b","path":"kit/GUIDE_GLOBAL_RESUME.md","content_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
```

Dans une mesure réelle, utiliser le vrai SHA-256 des **octets lus**, pas
le SHA d'une version distante supposée équivalente. Les sessions doivent
figurer dans l'ordre chronologique et former des blocs contigus. Ne jamais
relever les contenus ni les valeurs de variables d'environnement. Le journal
privé peut contenir des chemins publics et des identifiants pseudonymisés,
mais **il ne doit pas être committé ni transmis dans une PR**.

```sh
python tools/session_read_audit.py --events .state/session-reads.jsonl
python -m pytest -q tools/test_session_read_audit.py
```

Le rapport JSON ne contient **aucun chemin, contenu ou identifiant de session**.
Il compte séparément :

- `repeated_reads_within_session` : relecture du même chemin et des mêmes
  octets au sein de la session courante ;
- `repeated_reads_across_sessions` : première lecture dans la session
  courante d'un chemin et d'octets déjà lus dans une session précédente ;
- `changed_content_reads` : première lecture d'une nouvelle empreinte
  pour un chemin déjà vu, donc **pas** une répétition.

Les comptes portent sur les événements **fournis**, pas sur toutes les
lectures réellement effectuées par Codex/ChatGPT. Une lecture partielle,
un `grep` et une exploration sémantique ne sont pas automatiquement capturés.
Aucun crédit ou token facturé n'est déduit de ces compteurs : les champs
`actual_billed_tokens`, `actual_codex_cloud_credits` et
`saved_time_seconds` restent `null`.

Pour évaluer l'effet des passations, faire deux sessions comparables à
entrées et objectifs identiques, distinguer les répétitions intra/inter,
comparer les résultats et documenter les changements de commit et de
contexte. Ne pas modifier les règles, prompts, corpus ni contrôles de
traduction afin d'obtenir de meilleurs chiffres.


### Capture facultative d'une lecture réelle

Pour une comparaison contrôlée de sessions dans un clone local disposant de
Git, utiliser le lecteur instrumenté ci-dessous **à la place d'une lecture
complète normale** du même fichier, uniquement pendant la période mesurée :

```sh
python tools/session_read_capture.py --session run_a \
  --path kit/GUIDE_GLOBAL_RESUME.md
python tools/session_read_capture.py --session run_b \
  --path kit/GUIDE_GLOBAL_RESUME.md
python tools/session_read_audit.py --events .state/session-reads.jsonl
```

Ce lecteur affiche sur stdout les octets exacts du fichier réellement ouvert,
calcule le SHA-256 de ces mêmes octets et écrit une seule ligne JSONL dans
`.state/session-reads.jsonl`. Il accepte uniquement un fichier **suivi par
Git**, interne au dépôt, sans lien symbolique et hors des répertoires privés.
Les journaux restent locaux, non suivis par Git, et les identifiants de
session doivent être pseudonymes, chronologiques et non entrelacés.
La capture échoue fermement si le journal existant est corrompu, trop
volumineux ou si la sortie ne peut pas être transmise correctement.

La capture est facultative, limitée aux lectures complètes de fichiers
de taille raisonnable (512 Ko maximum). Elle n'intercepte pas les autres
lecteurs, les appels GitHub du connecteur ChatGPT, les lectures partielles,
les requêtes de recherche ou les traitements internes des modèles. Les
lectures hors de ce lecteur **ne figurent pas dans le rapport** : ne jamais
les présenter comme des économies. Ne pas imposer cet outil au traducteur,
à la publication ou aux mécanismes de reprise.

### Première observation ponctuelle, sans essai A/B

Sur l'issue #81 et la PR #133, la comparaison rétrospective des appels
`fetch_file` explicitement visibles montre, pour la session de
développement initiale, 19 lectures de fichiers dont 17 chemins distincts
et 2 répétitions exactes dans la même session. Dans la reprise suivante,
l'étape initiale a nécessité 3 lectures complètes : 2 chemins nouveaux,
et `AGENTS.md` dont le blob Git avait changé. Aucune des 3 lectures
n'a donc répété un contenu inchangé de la première session.

Cette observation repose sur l'identité des blobs Git à deux commits
(`3fabfb94` puis `6fcee356`), pas sur une collecte automatique
d'événements JSONL. Elle ne couvre ni les autres consultations du dépôt,
ni les usages internes du modèle, ni un scénario à objectifs identiques.
Elle ne permet pas de conclure à une économie de temps, de crédits ou de
tokens. Un véritable essai A/B nécessitera des tâches comparables, des
événements observés dans les deux branches et la même base de code.


## Comparaison de deux reprises réellement observées

Utiliser des **clones isolés issus du même commit**, un même objectif
technique, le même protocole d'essai et le même nombre de sessions. Le groupe
`control` réalise la reprise sans note narrative ; le groupe `handoff`
reçoit une note de passation concise. L'ordre des essais, les modifications
du dépôt et le résultat de la tâche doivent être consignés hors des journaux
publics. La qualité doit être **revue séparément** : le SHA-256 ne prouve
jamais la qualité sémantique.

Pour chaque groupe, capturer seulement les lectures explicites des fichiers
suivis par Git via `tools/session_read_capture.py`. Après les sessions
`control`, conserver le journal local sous
`.state/control.jsonl`, puis créer un nouveau journal local pour les
sessions `handoff`, conservé sous `.state/handoff.jsonl`. Éviter de
fusionner les deux journaux : ils doivent rester indépendants.

Préparer deux fichiers de métadonnées privés, par exemple
`.state/control-trial.json` et `.state/handoff-trial.json`, avec
exactement les champs suivants (les valeurs en majuscules sont à remplacer
par les données **vérifiées**, jamais par des valeurs d'exemple) :

```json
{
  "schema": "wikidebia-session-read-trial-1.0",
  "condition": "control",
  "task_id": "IDENTIFIANT_PUBLIC_DE_L_ESSAI",
  "base_commit": "COMMIT_GIT_DE_40_CARACTERES",
  "protocol_sha256": "SHA256_DU_MÊME_PROTOCOLE",
  "events_sha256": "SHA256_DU_JOURNAL_CONTROL",
  "task_completed": true,
  "quality_review": "passed",
  "coverage": "instrumented_complete_file_reads_only"
}
```

Le fichier `handoff-trial.json` a le même `task_id`,
`base_commit` et `protocol_sha256`, mais `condition` vaut
`handoff` et `events_sha256` correspond à l'autre journal.
L'empreinte du journal s'obtient avec
`sha256sum .state/control.jsonl`. Le résultat de la tâche et la revue
qualité (`passed`, `failed` ou `not_reviewed`) doivent refléter
l'évaluation effectuée par un humain ; l'outil ne les devine pas.

```sh
python tools/session_read_compare.py \
  --control-events .state/control.jsonl \
  --control-manifest .state/control-trial.json \
  --handoff-events .state/handoff.jsonl \
  --handoff-manifest .state/handoff-trial.json
```

Le comparateur refuse les tâches, commits, protocoles ou empreintes de
journaux divergents, les identifiants de conditions incorrects et les
fichiers dangereux. Il ne fournit une **différence descriptive** que si
chaque groupe contient au moins deux sessions, que leur nombre est égal et
que les deux tâches sont terminées avec une revue de qualité déclarée
`passed`. Une revue non faite, une erreur ou une tâche inachevée produit
un résultat explicitement non comparable, sans masquer les nombres de
lectures.

Même lorsque la comparaison descriptive est possible, les champs
`causal_savings_established` et
`experimental_equivalence_automatically_verified` restent
`false`. Le commit, le protocole et le contrôle qualité sont attestés
par les opérateurs, non établis automatiquement. Les économies de tokens,
crédits et temps restent `null`. Le rapport ne contient ni chemins,
ni IDs des sessions, ni textes lus, ni contenus privés.

**Sécurité du lecteur** : les fichiers portant des noms sensibles, les
liens symboliques (y compris remplacés entre le contrôle Git et la
lecture), les sorties tronquées et les journaux existants trop permissifs
sont refusés. La capture reste opt-in et n'altère ni la traduction, ni la
publication, ni les checkpoints.
