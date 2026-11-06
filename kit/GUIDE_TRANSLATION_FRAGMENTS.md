# Traduction et reprise argument par argument

Pour préparer uniquement le prochain argument incomplet :

```text
./wikidebia corpus-workspace-translation-fragment <debate_id> \
  --work-id <work_id> --prepare-next
```

La commande choisit le premier argument incomplet dans l’ordre des unités,
écrit un fragment éditable sous `reviews/en/argument-fragments/` et produit un
contexte signé contenant uniquement sa source française, sa traduction, son
vocabulaire pertinent et ses relations directes. Elle indique les octets évités
par rapport au paquet complet de l’unité.

Après modification du fragment, le sceller puis l’appliquer :

```text
./wikidebia corpus-workspace-translation-fragment <debate_id> \
  --work-id <work_id> --unit-id U001 --page-id A0001 --seal \
  --reviewer <identité> --note <note-explicite>

./wikidebia corpus-workspace-translation-fragment <debate_id> \
  --work-id <work_id> --unit-id U001 --page-id A0001 --apply \
  --confirm-fragment-sha256 <empreinte>
```

Chaque fragment est lié à l’empreinte de l’argument et de sa source française.
Son application préserve le bloc français, écrit un reçu signé et ne ferme pas
silencieusement l’unité. Les paquets suivants excluent l’argument uniquement si
ce reçu correspond encore exactement à l’état courant. Le vocabulaire partagé,
les libellés relationnels et la décision finale de l’unité restent revus par le
correctif d’unité lorsque tous ses arguments sont terminés.

La capsule de reprise globale référence automatiquement le fragment actif. Une
interruption après application ne fait donc perdre aucun autre argument et la
commande `./wikidebia resume` retrouve le prochain geste exact.
