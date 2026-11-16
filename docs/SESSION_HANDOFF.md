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
