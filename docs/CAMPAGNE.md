# Campagne automatique

Du lundi au vendredi à 7 h, pour chaque mode (stage puis job) : recherche d'emails jusqu'à 30 entreprises prêtes, résumé sur Telegram, envoi après « Envoyer », réponse avant 16 h. Décision D213.

## Installation, dans l'ordre

### 1. Mettre la base à jour

Application arrêtée (elle ne doit pas tourner pendant la migration 0019) :

```bash
cd ~/Bureau/workspace/chasseur
cp data/chasseur_v2.db "data/chasseur_v2_avant_0019.db"
venv/bin/alembic upgrade head
```

Redémarrer ensuite l'application : l'ancienne version ne connaît pas les verrous.

### 2. Créer le bot

1. Dans Telegram, ouvrir une conversation avec **@BotFather** (compte vérifié) et envoyer `/newbot`.
2. Donner un nom, puis un identifiant qui finit par `bot`.
3. Garder le jeton qu'il affiche (`123456:ABC...`) : c'est un secret. En cas de fuite, `/revoke` chez @BotFather.
4. Ouvrir la conversation avec le nouveau bot et lui envoyer un message (`/start`) : il ne peut pas écrire le premier.

### 3. Mettre le jeton dans .env, puis trouver ton identifiant

Dans `.env` : `TELEGRAM_BOT_TOKEN=` suivi du jeton. Puis, juste après avoir écrit au bot :

```bash
venv/bin/python - <<'FIN'
import os, requests
from shared import config  # charge .env
r = requests.get(f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/getUpdates", timeout=15).json()
for m in r.get("result", []):
    qui = m.get("message", {}).get("from", {})
    print(qui.get("id"), qui.get("first_name"))
FIN
```

Le nombre affiché à côté de ton prénom est ton identifiant. Rien d'affiché : renvoyer un message au bot et recommencer.

### 4. Variables de .env

```
TELEGRAM_BOT_TOKEN=le jeton
TELEGRAM_CHAT_ID=ton identifiant (nombre positif, pas un groupe)
CAMPAGNE_VALIDATION=telegram
CAMPAGNE_HEURE_LIMITE=16:00
CAMPAGNE_FIN=demander
PLAFOND_ENVOIS_JOUR=50
```

Les autres réglages sont dans [CONFIGURATION.md](CONFIGURATION.md). Vides, ils prennent leur défaut.

### 5. Tester un message

```bash
venv/bin/python -c "from shared import config, telegram; print('message', telegram.depuis_env().envoyer('Test du Chasseur'))"
```

Le message arrive sur ton téléphone. Puis une petite campagne, **mode essai activé** (Paramètres, compte d'envoi) : les mails arrivent chez toi.

```bash
venv/bin/python scripts/campagne.py --utilisateur 1 --modes stage --cible 2
```

### 6. Installer les unités

```bash
mkdir -p ~/.config/systemd/user
cp deploy/systemd/chasseur-campagne.service deploy/systemd/chasseur-campagne.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now chasseur-campagne.timer
systemctl --user list-timers chasseur-campagne.timer
```

- **Changer l'heure** : `systemctl --user edit chasseur-campagne.timer`, puis (la ligne vide efface l'ancienne heure) :
  ```ini
  [Timer]
  OnCalendar=
  OnCalendar=Mon..Fri *-*-* 08:30:00
  ```
- **Lancer tout de suite** : `systemctl --user start --no-block chasseur-campagne.service`. **Suivre** : `journalctl --user -fu chasseur-campagne.service`.
- **PC éteint à 7 h** : la campagne part à l'ouverture de session suivante (`Persistent=true`), y compris le samedi pour celle du vendredi. Après 16 h, elle prépare sans rien pouvoir envoyer.
- **Session fermée** : sans `loginctl enable-linger`, les unités ne tournent que session ouverte (verrouillée, c'est bon). Avec, dès le démarrage du PC ; la règle polkit plus bas devient alors nécessaire, et le réveil n'est plus garanti.
- **Application au démarrage** (facultatif) : `cp deploy/systemd/chasseur.service ~/.config/systemd/user/ && systemctl --user daemon-reload && systemctl --user enable --now chasseur.service`. Arrêter d'abord celle lancée à la main (même port).

### 7. Tester le réveil, capot ouvert puis fermé

Brancher le secteur, laisser la session ouverte. Minuteur temporaire dans 5 minutes : il note l'heure, attend 3 minutes, note l'heure à nouveau.

```bash
systemd-run --user --unit=test-reveil --on-calendar="$(date -d '+5 min' '+%F %T')" \
  --timer-property=WakeSystem=true --timer-property=AccuracySec=1s \
  sh -c 'date "+réveillé à %T"; sleep 180; date "+toujours réveillé à %T"'
systemctl --user show test-reveil.timer -p WakeSystem -p NextElapseUSecRealtime
systemctl suspend
```

La deuxième commande doit afficher `WakeSystem=yes`. Attendre 10 minutes **sans toucher au PC**, puis :

```bash
journalctl --user -u test-reveil.service -o cat --since "-20 min"
journalctl -k --since "-20 min" -o short-iso | grep "PM: suspend"
systemctl --user stop test-reveil.timer 2>/dev/null
```

| Résultat | Sens |
|---|---|
| Un `suspend entry`, un `suspend exit` à l'heure prévue, les deux lignes à 3 minutes d'écart | Réveil bon, pas de remise en veille |
| Un second `suspend entry` juste après, ou plus de 3 minutes d'écart | Réveillé puis remis en veille : voir « Capot » |
| `suspend exit` bien avant l'heure | Réveillé par autre chose (capot, USB, réseau) : recommencer |
| `suspend exit` seulement quand tu as touché au PC | Pas de réveil : `WakeSystem` non affiché à `yes`, ou `systemd --user` sans `CAP_WAKE_ALARM` |

Recommencer ensuite **capot fermé** : lancer `sleep 20 && systemctl suspend` à la place de `systemctl suspend`, et fermer le capot pendant les 20 secondes.

## Capot fermé, sur secteur

Deux programmes gèrent le capot. Session KDE ouverte, c'est **PowerDevil** : il prend un verrou (`handle-lid-switch`) et logind ne fait rien. Sans session (écran de connexion, linger seul), c'est **logind**. Pour qu'un réveil par le minuteur ne soit pas suivi d'une remise en veille, aucun des deux ne doit mettre en veille capot fermé, et aucune veille automatique ne doit suivre l'inactivité.

Regarder, sans rien changer :

```bash
systemd-inhibit --list | grep -i lid
grep -A3 SuspendAndShutdown ~/.config/powerdevilrc
busctl get-property org.freedesktop.login1 /org/freedesktop/login1 org.freedesktop.login1.Manager HandleLidSwitch HandleLidSwitchExternalPower IdleAction
```

État relevé le 25 novembre 2026 (Lenovo 83J3, Fedora 44, Plasma 6.7) :

| Réglage | Valeur | Effet |
|---|---|---|
| KDE, secteur, fermeture du capot (`LidAction`) | 64 | éteint l'écran, pas de veille : **bon** |
| KDE, secteur, inactivité (`AutoSuspendAction`) | 0 | pas de veille automatique : **bon** |
| KDE, batterie, fermeture du capot | non réglé | défaut de KDE, veille : **un réveil capot fermé sur batterie n'est pas sûr** |
| logind `HandleLidSwitch` | `suspend` | veille, seulement si PowerDevil ne tourne pas |
| logind `HandleLidSwitchExternalPower` | vide | non réglé, donc `HandleLidSwitch` s'applique aussi sur secteur |
| logind `IdleAction` | `ignore` | pas de veille automatique |
| Horloge (`rtc_cmos use_acpi_alarm`), veille | Y, s2idle | l'alarme peut réveiller depuis s2idle |

- **Session KDE ouverte, verrouillée ou non, sur secteur** : rien à changer d'après ces réglages. Pour les vérifier à l'écran : Configuration du système, Gestion de l'énergie, onglet « Sur secteur » : « À la fermeture du capot » = « Éteindre l'écran » (ou « Ne rien faire »), « En cas d'inactivité » = « Ne rien faire ».
- **Sans session ouverte** (écran de connexion, linger) : logind remet en veille capot fermé. Pour l'éviter sur secteur seulement, créer ce fichier puis redémarrer le PC (redémarrer `systemd-logind` en cours de session est à éviter) :
  ```bash
  sudo mkdir -p /etc/systemd/logind.conf.d
  printf '[Login]\nHandleLidSwitchExternalPower=ignore\n' | sudo tee /etc/systemd/logind.conf.d/50-chasseur-capot.conf
  ```
  Retour arrière : supprimer le fichier et redémarrer. Sur batterie, fermer le capot continue de mettre en veille.
- **Chaleur** : capot fermé, PC réveillé et au travail, laisser les grilles dégagées ; jamais dans un sac. Sur secteur, rien ne le remettra en veille tout seul : choisir « Mettre en veille » ou « Éteindre » à la fin, ou `CAMPAGNE_FIN=veille`.
- Seul le test de l'étape 7 prouve le réveil capot fermé : ces réglages ne disent pas ce que fait le micrologiciel.

## Déroulé

- **Préparation** de tous les modes, l'un après l'autre. File vide : nouvelle recherche d'entreprises selon le profil du mode. Arrêt du mode : cible atteinte, durée ou nombre d'entreprises maximal, recherche web en panne, plus rien à trouver.
- **Résumé** par mode, avec « Envoyer » et « Voir d'abord » (objet, pièces jointes, texte du mail). Il dit « ENVOI RÉEL aux entreprises » ou « MODE ESSAI : les mails arriveront chez toi », d'après le réglage du compte d'envoi. Seules les entreprises et les adresses du résumé peuvent partir. Sans réponse à l'heure limite, rien n'est envoyé et la sélection reste prête dans l'interface.
- **Envoi** : celui de l'interface, 2 à 5 minutes entre deux mails. 30 mails prennent environ 1 h 45.
- **Connexion à internet** : vérifiée au démarrage (api.telegram.org ou www.wikidata.org doit répondre). Absente, ou coupée pendant une recherche, un envoi ou un message : pause, nouvel essai toutes les 30 s, reprise dès son retour. Une entreprise lue pendant une coupure est refaite, un mail non parti est renvoyé, et la coupure ne compte pas comme une panne de la recherche web. Après 30 minutes sans connexion : arrêt propre, noté dans le journal de la campagne ; le message Telegram part dès le retour de la connexion (attendu 12 h au plus, le service reste actif jusque-là ; une autre campagne peut partir).
- **Plafond du jour** (`PLAFOND_ENVOIS_JOUR`, 50) : 30 en stage, 20 en job. Un envoi fait à la main le même jour compte aussi. Les entreprises job préparées en trop servent le lendemain.
- **Suivi** : envois et statuts dans l'interface comme d'habitude ; bilan et journal dans « Entreprises à contacter », « Dernière campagne automatique ».

## Application ouverte en même temps

Oui. La base est en WAL, une écriture attend l'autre 30 s au plus, et chaque traitement n'écrit que les lignes qu'il a touchées. Un verrou empêche l'interface et la campagne de chercher ou d'envoyer en même temps : l'interface répond « Campagne automatique en cours », la campagne attend 15 minutes au plus. Pendant qu'elle attend ta réponse, l'interface est libre. Une seule campagne à la fois. Le bouton « Arrêter » de l'interface n'arrête pas la campagne : `systemctl --user stop chasseur-campagne.service`.

## Extinction et veille

À la fin, le message Telegram propose « Éteindre le PC » et « Mettre en veille jusqu'à la prochaine campagne » (`CAMPAGNE_FIN`). Deux minutes pour annuler. Refusé si une recherche, une analyse ou un envoi tourne dans l'application, ou si le message d'annulation n'est pas parti. Proposé aussi quand des listes attendent ta réponse : éteindre y renonce, sans rien envoyer. Si tu cliques sur « Envoyer » pendant les deux minutes, l'extinction est annulée.

- **Réveil** : `WakeSystem=true` du minuteur, sans root. `rtcwake` n'est pas employé : `/dev/rtc0` demande root, et polkit ne peut pas l'autoriser. La veille est refusée si le minuteur n'est pas actif, n'a pas `WakeSystem=true`, ou si `systemd --user` n'a pas `CAP_WAKE_ALARM`. Cette capacité est donnée à l'ouverture d'une session locale ; avec le seul linger, elle peut manquer.
- **Le vendredi**, la prochaine campagne est le lundi à 7 h.
- **Après une extinction**, rien ne rallume le PC : la campagne part à l'ouverture de session suivante.
- **Autorisation** : session ouverte au premier plan, aucune. Sinon (linger sans session, autre session active), installer la règle, limitée à ton utilisateur, à `power-off` et à `suspend` :
  ```bash
  sed "s/UTILISATEUR/$USER/" deploy/polkit/50-chasseur-extinction.rules | sudo tee /etc/polkit-1/rules.d/50-chasseur-extinction.rules >/dev/null
  ```
  La retirer : `sudo rm /etc/polkit-1/rules.d/50-chasseur-extinction.rules`.

## Sécurité

- Un clic n'est accepté que si son auteur et la conversation sont `TELEGRAM_CHAT_ID` ; chaque bouton porte un jeton de la campagne, donc un vieux bouton ne fait rien.
- Le jeton du bot est un secret : toute personne qui l'a peut lire les messages du bot. Les résumés contiennent les noms et les adresses des entreprises, et « Voir d'abord » le texte de ton mail : ils passent par les serveurs de Telegram.
- Ne pas suspendre la campagne dans un terminal (Ctrl+Z) : elle ne répond plus et garde son verrou, donc aucune autre ne démarre. Pour l'arrêter : Ctrl+C.
- Rien d'autre ne doit interroger ce bot (`getUpdates`) pendant une campagne.
