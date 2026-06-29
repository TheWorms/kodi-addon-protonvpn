# ProtonVPN

Addon Kodi pour piloter **ProtonVPN** avec une interface graphique, en
**OpenVPN** ou **WireGuard** au choix. Importez vos fichiers de configuration,
parcourez les serveurs par pays, connectez/déconnectez, connexion automatique
au démarrage et reconnexion en cas de coupure.

Conçu pour **CoreELEC / LibreELEC** et les autres installations Linux de Kodi
(testé sur Kodi 21 « Omega », ODROID-N2+).

> Addon indépendant, **non affilié à Proton AG**. « ProtonVPN » est une marque
> de Proton AG, utilisée ici à des fins de description.

- **Dépôt** : `github.com/TheWorms/kodi-addon-protonvpn`
- **Identifiant Kodi** : `service.protonvpn.manager` (nom du dossier, imposé par Kodi)
- **Nom affiché** : ProtonVPN
- **Licence** : GPL-2.0-or-later

---

## Sommaire

1. [Téléchargement](#1-téléchargement)
2. [Prérequis](#2-prérequis)
3. [Récupérer ses configurations ProtonVPN](#3-récupérer-ses-configurations-protonvpn)
4. [Installer l'addon](#4-installer-laddon)
5. [Importer ses configurations](#5-importer-ses-configurations)
6. [Configurer](#6-configurer)
7. [Utiliser](#7-utiliser)
8. [OpenVPN ou WireGuard ?](#8-openvpn-ou-wireguard-)
9. [Comment ça marche](#9-comment-ça-marche)
10. [Dépannage](#10-dépannage)
11. [Limites connues](#11-limites-connues)

---

## 1. Téléchargement

Récupérer le zip installable depuis la page **Releases** :

> https://github.com/TheWorms/kodi-addon-protonvpn/releases

Télécharger l'asset **`kodi-addon-protonvpn-0.3.0.zip`** (et non le « Source
code (zip) » généré par GitHub, qui n'est pas installable tel quel).

## 2. Prérequis

Selon le backend que vous comptez utiliser :

**OpenVPN** — le binaire `openvpn` présent sur le système.
- CoreELEC/LibreELEC : addon *OpenVPN for LibreELEC* (fournit `/usr/sbin/openvpn`).
- Linux classique : `sudo apt install openvpn`.

**WireGuard** — `wg` et `wg-quick` présents, **plus** le support noyau WireGuard.
- Vérifier rapidement sur la box :
  ```bash
  which wg wg-quick
  ip link add wgtest type wireguard 2>&1 && echo "WG noyau OK" && ip link del wgtest
  ```
- CoreELEC/LibreELEC : selon le build, WireGuard est inclus dans le noyau ou
  s'ajoute via Entware (`opkg install wireguard-tools`). Sans `wg-quick`,
  l'addon le signalera à la connexion.

Sur CoreELEC/LibreELEC, Kodi tourne en root : pas de sudo nécessaire.

## 3. Récupérer ses configurations ProtonVPN

Sur https://account.protonvpn.com → **Downloads** :

- **OpenVPN** : *OpenVPN configuration files* → Platform Router/Linux, UDP ou
  TCP, télécharger les `.ovpn`. Les identifiants OpenVPN/IKEv2 (Account →
  OpenVPN/IKEv2, **différents de votre e-mail**) sont à saisir dans les réglages.
- **WireGuard** : *WireGuard configuration* → créer une clé pour l'appareil
  (ex. « Cormoran »), choisir NetShield / NAT / etc., télécharger le `.conf`.
  Tout est dans le fichier (clés comprises) : **aucun identifiant à saisir**.

## 4. Installer l'addon

1. Copier **`kodi-addon-protonvpn-0.3.0.zip`** sur la box.
2. Système → Add-ons → activer **Sources inconnues**.
3. Add-ons → **Installer depuis un fichier zip** → sélectionner le zip.

L'addon apparaît dans **Add-ons → Programmes → ProtonVPN**.

## 5. Importer ses configurations

Ouvrir l'addon → **Importer une configuration**, puis sélectionner un fichier
`.ovpn` (OpenVPN) ou `.conf` (WireGuard). Répéter pour autant de serveurs que
souhaité — vous pourrez ensuite choisir lequel utiliser dans la liste. Le
backend est déduit automatiquement du type de fichier (tag **WG** ou
**UDP/TCP** dans la liste).

> Alternative : pointer un dossier de configs via *Réglages → Configuration →
> Dossier de configurations* (facultatif) ; l'addon le scanne récursivement
> (`.ovpn` et `.conf`).

## 6. Configurer

Add-ons → Programmes → **ProtonVPN** → *(menu contextuel)* **Paramètres** :

- **Configuration**
  - *Importer une configuration* (bouton).
  - *Identifiant / Mot de passe ProtonVPN (OpenVPN/IKEv2)* → **OpenVPN
    uniquement** (le WireGuard n'en a pas besoin).
  - *Dossier de configurations* (facultatif).
- **Connexion**
  - *Protocole préféré (OpenVPN)*, *NetShield (OpenVPN)*, *NAT modéré
    (OpenVPN)* : pour WireGuard, ces options sont figées à la génération du
    `.conf` côté ProtonVPN (voir les commentaires en tête du fichier).
  - *Délai de connexion*, *Exécutable OpenVPN*, *Exécutable wg-quick*, *sudo*.
- **Service** : connexion automatique au démarrage (+ pays par défaut),
  reconnexion auto, déconnexion à la fermeture de Kodi.

## 7. Utiliser

Ouvrir l'addon :

- **En-tête** : état courant (connecté / serveur / IP, ou « reconnexion »).
- **Connexion rapide (serveur aléatoire)**, **Reconnecter le dernier serveur**.
- **Parcourir par pays** → choisir un serveur (le backend suit le type).
- **Tous les serveurs**, **Importer une configuration**, **Tester la connexion**.

## 8. OpenVPN ou WireGuard ?

- **WireGuard** : plus rapide à établir, plus léger, et plus stable à surveiller
  (l'addon mesure l'âge du dernier *handshake*). NetShield/NAT/Bouncing sont
  choisis au moment de générer le `.conf`.
- **OpenVPN** : compatible partout, NetShield/NAT réglables à la volée via les
  réglages (suffixes d'identifiant), choix UDP/TCP.

Vous pouvez importer les deux et basculer en choisissant la config voulue.

## 9. Comment ça marche

- Chaque fichier importé contient déjà ses secrets (CA + tls-crypt pour
  OpenVPN, paire de clés pour WireGuard) : **rien de sensible n'est codé en
  dur**. Les fichiers sont copiés dans l'espace privé de l'addon en `0600`.
- **OpenVPN** est lancé en sous-processus durci (sortie propre sur tunnel mort,
  ré-auth non-interactive…). **WireGuard** est monté via `wg-quick up/down`.
- Un service de fond surveille la connexion et la rétablit avec un *backoff*
  (5/15/30/60 s), via une machine à états partagée avec l'interface.

## 10. Dépannage

- **WireGuard : « outils introuvables »** → installer `wireguard-tools`
  (`wg`, `wg-quick`) et vérifier le support noyau (cf. §2).
- **WireGuard ne monte pas** → consulter la sortie de `wg-quick` remontée par
  l'addon ; souvent un souci de DNS (géré : la ligne `DNS` est retirée si aucun
  resolvconf n'est présent) ou de droits (activer *sudo* hors CoreELEC).
- **OpenVPN : AUTH_FAILED** → identifiant OpenVPN/IKEv2 (≠ e-mail) + mot de passe.
- **Binaire introuvable** → renseigner *Exécutable OpenVPN* / *Exécutable
  wg-quick* dans les réglages.
- **Journaux** : OpenVPN dans
  `addon_data/service.protonvpn.manager/protonvpn.openvpn.log` ; pour le reste,
  filtrer `service.protonvpn.manager` dans `kodi.log`.

## 11. Limites connues

- Pas de *kill-switch* (nécessiterait des règles iptables/nftables sur la box).
- WireGuard : NetShield/NAT/Bouncing ne sont pas modifiables depuis l'addon
  (ils sont fixés à la génération du `.conf`).
- Drapeaux pays optionnels : déposer des PNG dans `resources/flags/<cc>.png`.

---

## Licence

Distribué sous **GPL-2.0-or-later** (voir `LICENSE.txt`). Projet indépendant,
non affilié à Proton AG.
