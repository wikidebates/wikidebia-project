# Déploiement Debian depuis Codex Web

Codex Web modifie le dépôt GitHub. Après revue et fusion dans `main`, le serveur
vérifie GitHub toutes les cinq minutes, teste le commit récupéré dans un dossier
temporaire puis met à jour son checkout par avance rapide. Il n'accepte aucune
connexion entrante de Codex Cloud et ne nécessite pas SSH via Tailscale.

Ce déploiement met à jour le programme Wikidéb’IA. Il ne lance ni publication
MediaWiki, ni mise à jour distante des débats, ni service web. Ces opérations
restent des commandes explicites. Seuls les changements fusionnés dans `main`
sont concernés ; une modification encore présente dans un chat ou une PR ne
déclenche pas de déploiement.

## Installation initiale, une seule fois

Les commandes ci-dessous sont destinées au **serveur Debian**, pas à Codex Cloud.
Avant de les exécuter, fusionner les fichiers `deploy/` dans GitHub. Ne pas
écraser une installation existante : relever d'abord son chemin et son compte
propriétaire. Sur le serveur actuel, le dossier est
`/home/users/webmaster/files/Wikidéb'IA` et son propriétaire est `webmaster`.
Le compte `webmaster` doit pouvoir lire le dépôt GitHub et
écrire dans son checkout. Ne pas changer récursivement les droits d'une installation
existante sans l'avoir examinée.

Préparer les paquets et le service utilisateur, depuis le compte root :

```bash
apt-get update
apt-get install -y git python3 python3-venv python3-pip util-linux dbus-user-session
loginctl enable-linger webmaster
```

Depuis root, ouvrir une session sous `webmaster` (ignorer `su` si on utilise déjà
ce compte). `su -` ne définit pas
toujours le chemin du bus systemd utilisateur ; le préciser pour ce compte :

```bash
su - webmaster
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
systemctl --user show-environment >/dev/null
```

Si la dernière commande échoue, ne pas continuer : vérifier que
`dbus-user-session` est installé et que `loginctl enable-linger webmaster`
a bien démarré le gestionnaire utilisateur. Ne pas installer le minuteur en tant
que root.

Pour l'**installation existante**, depuis `webmaster`, après fusion des scripts
dans GitHub :

```bash
cd "/home/users/webmaster/files/Wikidéb'IA"
git status --short --branch
git pull --ff-only origin main
```

Le checkout doit être propre avant le pull. Si une modification locale est
présente, l'examiner et la préserver avant de continuer. Ne pas réappliquer
automatiquement un stash pendant les déploiements.

Pour une **nouvelle installation seulement**, depuis le compte propriétaire :

```bash
git clone --branch main https://github.com/wikidebates/wikidebia-project.git "$HOME/wikidebia"
cd "$HOME/wikidebia"
mkdir -p private/pywikibot
```

Un dépôt privé nécessite un accès GitHub en lecture configuré sous ce compte
(par exemple une clé de déploiement SSH en lecture seule). Ne pas placer de jeton
dans l'URL Git, dans le dépôt ou dans l'unité systemd. Le minuteur n'affiche pas
de demande interactive d'authentification.

S'il n'existe aucune configuration Pywikibot, créer cette configuration publique,
sans identifiant. Sur une installation existante, **conserver la configuration
et les secrets en place** :

```bash
test -e private/pywikibot/user-config.py || cat > private/pywikibot/user-config.py <<'PY'
from pathlib import Path
family = "wikidebates"
mylang = "fr"
family_files["wikidebates"] = str(
    Path(base_dir).resolve().parents[1] / "kit/families/wikidebates_family.py"
)
PY
```

Depuis le checkout à déployer, effectuer la validation initiale et installer le
minuteur (ces commandes peuvent prendre plusieurs minutes) :

```bash
bash deploy/install-timer.sh "$PWD" main
```

Python doit être compatible avec les dépendances du projet (Python 3.12 est la
version utilisée en CI). Les tests sont rejoués sur le Python du serveur. Un
échec empêche l'installation du minuteur ou le déploiement du nouveau code.

## Vérification et arrêt

Sous le même compte, consulter le résultat et le prochain passage :

```bash
systemctl --user list-timers wikidebia-deploy.timer
journalctl --user -u wikidebia-deploy.service -n 60 --no-pager
cat .state/deployed-commit
```

Un déploiement réussi affiche `Déploiement validé : <SHA>`. Le fichier
`.state/deployed-commit` n'est écrit qu'après succès des tests, de l'installation
des dépendances et de `doctor`. L'installation locale du minuteur ne prouve pas
encore le bon fonctionnement sur Debian : vérifier un premier passage automatique
dans le journal, y compris après fermeture de la session.

Pour suspendre le déploiement, notamment pendant une opération éditoriale :

```bash
systemctl --user stop wikidebia-deploy.timer
systemctl --user stop wikidebia-deploy.service
```

Puis le réactiver :

```bash
systemctl --user start wikidebia-deploy.timer
```

## Garde-fous et limites

- Pas de `git reset`, de `git clean`, de push Git ni de réécriture d'historique.
  Les modifications locales et les historiques divergents bloquent le déploiement.
- Les fichiers ignorés (corpus, secrets, journaux, configurations locales) restent
  dans le checkout du serveur. Ils ne sont pas copiés dans le dossier des tests.
  Un commit qui suit un chemin réservé, son contenu ou un fichier/lien remplaçant
  un de ses parents est refusé avant les tests et la mise à jour Git. Cela protège
  notamment `corpus` et `private` eux-mêmes, ainsi que le parent `config` de la
  configuration locale ; les exemples publics dans `config/` restent autorisés.
- Un verrou empêche deux déploiements simultanés. Il ne verrouille pas les autres
  commandes Wikidéb’IA : suspendre le minuteur pendant les opérations éditoriales.
- Une erreur de tests laisse le code installé inchangé. Si `pip` ou `doctor`
  échoue **après** l'avance rapide, le code est déjà mis à jour et l'environnement
  Python peut être partiellement modifié. Le service échoue, sans marquer le
  commit comme déployé, et retentera au passage suivant. Ce mécanisme n'est pas
  une bascule atomique avec retour arrière automatique. Consulter le journal,
  suspendre le minuteur puis corriger ; ne pas lancer de reset à l'aveugle.
- Les versions de dépendances déclarées sont actuellement des plages. Chaque
  déploiement enregistre les versions résolues dans l'environnement temporaire
  avec `pip freeze`, puis les utilise comme contraintes pour l'installation réelle.
  La validation et l'installation utilisent ainsi les mêmes versions pour les
  dépendances du programme. Deux déploiements distincts peuvent encore résoudre
  des versions différentes ; il n'y a pas de lockfile versionné.
- Le déployeur installé est une copie stable du script. Après un changement de
  son fonctionnement, relancer explicitement `install-timer.sh` pour le remplacer.
  Une fusion sur GitHub et la récupération du nouveau fichier `deploy/update.sh`
  ne suffisent donc pas à activer une correction du déployeur. Après avoir vérifié
  que le serveur a récupéré le commit corrigé, exécuter manuellement sous
  **`webmaster` sur Debian**, depuis le checkout :

  ```bash
  bash deploy/install-timer.sh "$PWD" main
  ```

  Vérifier ensuite le journal du service et le prochain passage du minuteur.
- Pour annuler une modification applicative, créer un commit de correction ou
  de revert sur GitHub, puis le fusionner. Les données privées ne sont pas
  sauvegardées par ce mécanisme ; conserver la sauvegarde habituelle du serveur.
