# ProtonVPN

Addon Kodi pour piloter **ProtonVPN** via OpenVPN, avec une interface graphique :
navigation par pays, connexion / déconnexion, connexion automatique au démarrage
et reconnexion en cas de coupure.

Conçu pour **CoreELEC / LibreELEC** et les autres installations Linux de Kodi
(testé sur Kodi 21 « Omega », ODROID-N2+). L'architecture s'inspire de
*VPN Manager for OpenVPN* de Zomboided.

> Addon indépendant, **non affilié à Proton AG**. « ProtonVPN » est une marque
> de Proton AG, utilisée ici uniquement à des fins de description.

- **Dépôt** : `github.com/TheWorms/kodi-addon-protonvpn`
- **Identifiant Kodi** : `service.protonvpn.manager` (nom du dossier, imposé par Kodi)
- **Nom affiché** : ProtonVPN
- **Licence** : GPL-2.0-or-later

---

## Sommaire

1. [Téléchargement](#1-téléchargement)
2. [Prérequis](#2-prérequis)
3. [Récupérer ses identifiants et configs ProtonVPN](#3-récupérer-ses-identifiants-et-configs-protonvpn)
4. [Installer l'addon](#4-installer-laddon)
5. [Configurer](#5-configurer)
6. [Utiliser](#6-utiliser)
7. [Comment ça marche](#7-comment-ça-marche)
8. [Dépannage](#8-dépannage)
9. [Limites connues](#9-limites-connues)

---

## 1. Téléchargement

Récupérer le zip installable depuis la page **Releases** du dépôt :

> https://github.com/TheWorms/kodi-addon-protonvpn/releases

Télécharger l'asset **`kodi-addon-protonvpn-0.1.0.zip`** (et non le « Source code (zip) »
généré automatiquement par GitHub, qui n'est pas installable tel quel dans Kodi).

## 2. Prérequis

- Kodi 19+ (testé sur Kodi 21 Omega, p. ex. CoreELEC sur ODROID-N2+).
- Le binaire **openvpn** présent sur le système :
  - **CoreELEC / LibreELEC** : installer l'addon *OpenVPN for LibreELEC* depuis
    le dépôt officiel (il fournit `/usr/sbin/openvpn`), ou vérifier `which openvpn`.
  - **Kodi sous Linux classique** : `sudo apt install openvpn`, puis activer
    l'option *Lancer OpenVPN avec sudo* dans les réglages (ou configurer le
    droit d'accès à `tun`).
- Sur CoreELEC / LibreELEC, Kodi tourne en root : aucun sudo nécessaire.

## 3. Récupérer ses identifiants et configs ProtonVPN

1. Se connecter sur https://account.protonvpn.com
2. **Account → OpenVPN / IKEv2 username** : noter l'**identifiant** et le
   **mot de passe** OpenVPN.
   ⚠️ Ce ne sont **pas** vos identifiants de connexion Proton (e-mail), mais une
   paire **dédiée** propre à OpenVPN.
3. **Downloads → OpenVPN configuration files** : choisir *Platform: Router* (ou
   Linux), *Protocol: UDP*, puis télécharger les configs (par pays ou
   « Download all »). Décompresser l'archive dans un dossier accessible depuis la
   box, par exemple `/storage/protonvpn/` sur CoreELEC.

## 4. Installer l'addon

1. Copier **`kodi-addon-protonvpn-0.1.0.zip`** sur la box (clé USB, partage réseau, `scp`…).
2. Dans Kodi : Système → Add-ons → activer **Sources inconnues**.
3. Add-ons → **Installer depuis un fichier zip** → sélectionner le zip.

L'addon apparaît ensuite dans **Add-ons → Programmes → ProtonVPN**.

## 5. Configurer

Add-ons → Programmes → **ProtonVPN** → *(menu contextuel)* **Paramètres** :

- **Configuration**
  - *Dossier des configurations ProtonVPN* → le dossier de l'étape 3.3.
  - *Identifiant OpenVPN* / *Mot de passe OpenVPN* → étape 3.2.
- **Connexion**
  - *Protocole préféré* : Les deux / UDP / TCP.
  - *NetShield* : filtrage DNS (`+f1` = malwares, `+f2` = malwares + pubs + traqueurs).
  - *NAT modéré*, *Délai de connexion*, *Exécutable OpenVPN*, *sudo* (avancé).
- **Service**
  - *Connexion automatique au démarrage* (+ *Code pays par défaut*).
  - *Reconnexion auto si la connexion tombe*.
  - *Déconnecter à la fermeture de Kodi*.

## 6. Utiliser

Ouvrir l'addon (Add-ons → Programmes → **ProtonVPN**) :

- **En-tête** : état courant (connecté / serveur / IP publique).
- **Connexion rapide (serveur aléatoire)**.
- **Reconnecter le dernier serveur**.
- **Parcourir par pays** → choisir un serveur pour s'y connecter.
- **Tous les serveurs**.
- **Déconnecter**.

Le service de fond maintient la connexion et la rétablit automatiquement en cas
de coupure (si l'option est activée).

## 7. Comment ça marche

- Chaque `.ovpn` téléchargé contient déjà le bon certificat CA et la clé
  tls-crypt : **rien de sensible n'est codé en dur** dans l'addon.
- À la connexion, l'addon copie la config choisie, y injecte le fichier
  d'authentification (identifiant + éventuel suffixe NetShield / NAT modéré) et
  lance `openvpn` dans sa propre session (il survit au process plugin).
- L'état est partagé entre le service et l'interface via des *window properties*
  (`protonvpn.connected`, `protonvpn.server`, `protonvpn.ip`).
- L'API *logicals* de ProtonVPN n'est utilisée que, en option, pour afficher la
  charge des serveurs — **désactivée par défaut**.

## 8. Dépannage

- **« Aucun fichier de configuration trouvé »** : vérifier le dossier (étape
  3.3) ; l'addon scanne récursivement les `*.ovpn`.
- **Échec de connexion / `AUTH_FAILED`** : revérifier l'identifiant OpenVPN
  (≠ e-mail Proton) et le mot de passe.
- **OpenVPN introuvable** : renseigner le chemin dans *Connexion → Exécutable
  OpenVPN*, ou installer le binaire.
- **Journaux** :
  - OpenVPN : `userdata/addon_data/service.protonvpn.manager/protonvpn.openvpn.log`
  - Kodi : filtrer sur `service.protonvpn.manager` dans `kodi.log`.

## 9. Limites connues

- Pas de *kill-switch* ni de bascule VPN par addon (à la Zomboided) dans cette
  v0.1 : périmètre volontairement réduit à un gestionnaire ProtonVPN propre.
- Drapeaux pays optionnels : déposer des PNG dans `resources/flags/<cc>.png`
  (ex. `nl.png`) pour les afficher dans la liste des pays.

---

## Licence

Distribué sous **GPL-2.0-or-later** (voir `LICENSE.txt`). Addon indépendant,
non affilié à Proton AG ni à Zomboided.
