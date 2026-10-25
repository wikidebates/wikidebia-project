# Publier depuis Codex avec les accès MediaWiki de Debian

Le relais permet à Codex de transmettre une demande de publication française par
Git, sans SSH, sans API GitHub et sans copier les identifiants du serveur.

1. Le propriétaire demande explicitement la publication de changements précis.
2. Codex prépare les textes avant/après et une demande liée à leurs SHA-256.
3. Codex envoie cette demande sur la branche distincte `wiki-fr-publication`.
4. Le relais Debian lit cette branche chaque minute et vérifie toutes les pages
   avant la première écriture. Il utilise la configuration Pywikibot existante.
5. Le journal local indique le résultat et les révisions des modifications.

Une fusion dans `main` ne déclenche pas de publication. Le minuteur de déploiement
du programme reste inchangé. Le relais de publication est un service distinct,
à installer et activer explicitement une seule fois.

## Activation initiale sur Debian

Après fusion du code du relais dans `main` et récupération sur le serveur,
exécuter **sous `webmaster` sur Debian**, depuis le checkout :

```bash
cd "/home/users/webmaster/files/Wikidéb'IA"
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
bash deploy/install-publication-relay.sh "$PWD"
```

Cette commande effectue un préflight sans écriture puis active le relais et lance
un premier passage. Les demandes explicitement envoyées pourront alors être
publiées. La configuration `private/pywikibot/` reste en place. Le compte wiki
attendu est lu dans `config/wikidebia.local.json`, avec le fichier exemple comme
valeur de repli. Le compte connecté doit correspondre exactement et posséder les
droits d'édition et de renommage ; la balise `chatgpt` doit être disponible.

Le compte Debian doit pouvoir lire la branche Git dédiée ; aucun droit de push
GitHub n'est nécessaire au serveur. Le démarrage automatique après fermeture de
session suppose le gestionnaire utilisateur persistant, déjà installé pour le
déploiement. Aucun changement de Tailscale ou de SSH n'est nécessaire.

## Envoi depuis Codex Cloud

Un dossier de demande contient `request.json` et les fichiers `before/` et `after/`
déclarés. Le schéma est `wikidebia-fr-publication-request-1.2` ; le site est fixé à
`https://fr.wikidebates.org` et la langue à `fr`. Les SHA-256 des textes et de la
demande empêchent une modification silencieuse du paquet. Ils ne constituent pas
une signature d'identité : l'autorisation de transport repose sur les droits Git
de la branche. Seules les personnes autorisées à publier doivent pouvoir y pousser.

Lorsque Cloudflare protège l’API, l’adaptateur ajoute automatiquement l’en-tête
`x-wikidebia-access` si la variable d’environnement `WIKIDEBIA_API_TOKEN` est
présente. Sa valeur reste hors du dépôt et des journaux.

Après l'autorisation explicite de l'utilisateur, envoyer le dossier préparé :

```bash
./wikidebia fr-publication-relay --enqueue DOSSIER_DEMANDE \
  --confirm-request-sha256 EMPREINTE_EXACTE
```

Cette commande utilise un dépôt temporaire de données ; elle ne change pas la
branche ou les fichiers de travail du projet. Le push est une avance rapide
normale. Le contenu d'un identifiant de demande déjà utilisé est immuable ; une
nouvelle correction exige un nouvel identifiant.
La branche `wiki-fr-publication` transporte des données : ne pas la fusionner dans
`main` et ne pas créer de PR pour ses demandes. Seul le code du relais fait l'objet
d'une PR normale.

Le relais n'exécute aucun code provenant de la branche de demandes et refuse les
liens symboliques. Seuls les textes de pages de contenu françaises peuvent être
mis à jour ou renommés. Aucune suppression, nouvelle page ou opération anglaise
n'est prise en charge. Les anciennes pages renommées restent des redirections.
Les liens hors du snapshot continuent ainsi de fonctionner.

### Périmètre des résumés et commentaires d’édition

Une demande de relecture ou de correction générale n’autorise ni l’ajout d’un
résumé d’argument (même vide à l’origine), ni sa réécriture, ni son retrait.
Le relais contrôle ce périmètre à l’envoi et avant toute mutation, y compris
avant les renommages. Le moteur `update` applique la même règle à la préparation
du plan et avant son exécution, en français comme en anglais.

Si l’utilisateur demande spécifiquement de modifier ou de restaurer un résumé,
la ligne de cette page dans `request.json` doit contenir, par exemple :

```json
"summary_change_authorization": {
  "decision": "explicit_user_request",
  "action": "restore",
  "instruction": "Restaure le résumé antérieur de cet argument."
}
```

`instruction` cite la demande réelle de l’utilisateur ; ne pas l’inventer à partir
d’un « corrige tout » ou d’une autorisation générale de publication. `action` vaut
`edit` ou `restore`. Pour `update`, le même objet doit figurer sur la page du
manifeste ; le plan le reprend et l’exécuteur vérifie sa concordance. La création
de nouvelles pages à partir d’un corpus reste distincte de la reprise de pages
existantes.

Les commentaires d’édition sont calculés à partir des champs réellement modifiés
(résumé, citations, références, introduction, relations, etc.). Un commentaire
fourni dans `edit_summary` doit correspondre à ce calcul ; il ne peut pas imposer
un libellé générique trompeur. Une restauration limitée au résumé porte le
commentaire « Restauration du résumé antérieur ; annulation des changements non
demandés ». Les commentaires des anciennes révisions, déjà enregistrés dans
l’historique MediaWiki, ne sont pas réécrits.

Le schéma 1.1 oblige un ancien relais à refuser une nouvelle demande plutôt que
de l’exécuter avec l’ancien commentaire fixe. Déployer le code actuel avant de
traiter les nouvelles demandes. Les demandes 1.0 achevées et leurs reçus restent
immuables et sont ignorés sans rejouer les écritures ; toute demande encore à
traiter doit satisfaire aux nouveaux contrôles.

### Conservation des citations existantes

Une relecture ou une correction générale n’autorise pas la suppression ou la
réécriture d’une citation existante. Une source non retrouvée ou non vérifiée,
une référence ancienne, un désaccord avec son contenu ou un doublon ne permettent
pas de la retirer, de la masquer ou de la remplacer par un résumé. Signaler le
problème à l’utilisateur et attendre une demande spécifique. Les citations,
attributions et références originales sont conservées entre-temps.

Le relais et le moteur `update` comparent toutes les occurrences des modèles
`Citation` et `Quote` avant la première mutation et avant chaque édition. Ce
contrôle couvre également les citations placées hors du champ habituel
`citations`/`quotes`, ainsi que le retrait d’un seul exemplaire d’une citation
présente plusieurs fois. Un ajout ne permet pas de compenser la suppression
d’une autre citation. L’ajout d’une nouvelle citation conserve les anciennes.

Une modification expressément demandée nécessite sur chaque page concernée :

```json
"citation_change_authorization": {
  "decision": "explicit_user_request",
  "action": "restore",
  "instruction": "Rétablis les citations que tu as supprimées."
}
```

`instruction` cite la demande réelle. Comme pour les résumés, cet objet est
porté par la page de la demande ou du manifeste et vérifié par l’exécuteur ;
une autorisation de publication ou de modification du résumé ne le remplace pas.
Une restauration limitée au champ `citations` porte le commentaire « Restauration
des citations antérieures ; annulation des retraits non demandés ».

Les nouvelles demandes 1.2 exigent le code comprenant ce contrôle et ce commentaire.
Les demandes achevées 1.0 et 1.1 restent immuables et ne sont pas rejouées. Une
demande ancienne encore à traiter ne peut pas contourner la protection des citations.

## Vérification sur Debian

```bash
systemctl --user list-timers wikidebia-publish-fr.timer
journalctl --user -u wikidebia-publish-fr.service -n 80 --no-pager
ls .state/fr-publication-relay/
```

Le fichier `.state/fr-publication-relay/IDENTIFIANT.json` n'indique `completed`
qu'après relecture de toutes les cibles. Le relais n'envoie pas de reçu vers GitHub :
une demande poussée ou un minuteur actif ne prouvent donc pas la publication.
Le journal et le reçu Debian permettent de la confirmer.

Une page modifiée depuis la préparation ou une collision bloque la demande
entière avant les écritures initiales. Une modification tierce pendant l'exécution
arrête la suite ; les modifications déjà effectuées sont journalisées. Il n'y a
pas de transaction multi-pages ni de retour arrière automatique. Un échec réseau
peut être repris au passage suivant ; les renommages déjà effectués sont reconnus
par leurs redirections et leurs contenus. Un conflit éditorial exige une nouvelle
revue ; il n'est pas retenté en boucle.

Après une édition, le relais relit la révision exacte jusqu'à huit fois, avec deux
secondes entre les lectures, pour attendre la visibilité des métadonnées MediaWiki.
L'identifiant, la révision parente, le compte, le résumé, la balise `chatgpt` et le
SHA-256 du contenu doivent tous correspondre. L'édition n'est pas répétée pendant
ces vérifications ; une divergence persistante reste bloquante et son champ est
indiqué dans le journal.

Le reçu conserve aussi la révision renvoyée par chaque édition avant sa relecture.
Lors d'une reprise explicite, une édition interrompue est vérifiée et ajoutée au
journal avant toute nouvelle écriture, sans être répétée. Les anciens reçus qui
n'avaient enregistré que `update_requested` sont conservés : le relais vérifie
alors la révision courante et sa révision parente avant de poursuivre.

Après diagnostic et résolution d'un conflit, une reprise explicite est possible :

Si la seule divergence de contenu est un unique saut de ligne final retiré lors
de l'enregistrement MediaWiki, le relais actuel reconnaît la cible signée à la
relecture. Les empreintes des fichiers de demande restent exactes ; les autres
espaces, sauts de ligne et métadonnées ne sont pas normalisés. Déployer ce
correctif avant de reprendre un ancien reçu bloqué pour ce motif. La reprise
vérifie la révision déjà écrite et complète le journal sans répéter l'édition.

```bash
./wikidebia fr-publication-relay --execute --retry IDENTIFIANT
```

Pour suspendre le relais, arrêter d'abord le minuteur puis laisser finir le passage
en cours avant une autre opération éditoriale :

```bash
systemctl --user stop wikidebia-publish-fr.timer
systemctl --user is-active wikidebia-publish-fr.service
```

Le relais et le déploiement partagent un verrou empêchant leur exécution simultanée.
Les autres commandes éditoriales du projet ne prennent pas ce verrou : ne pas les
exécuter simultanément avec le relais. Aucune manipulation du stash, des corpus
ou des secrets existants n'est effectuée par l'installation.
