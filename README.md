# ProtonVPN

Addon Kodi pour piloter **ProtonVPN** avec une interface simple, en **WireGuard**
ou **OpenVPN** au choix. Importe tes configurations, choisis un serveur (test +
connexion), vois l'état du VPN en direct, suis les stats et les journaux.

Conçu pour **CoreELEC / LibreELEC** et les autres Kodi sous Linux (testé Kodi 21
« Omega », ODROID-N2+).

> Addon indépendant, **non affilié à Proton AG**. « ProtonVPN » est une marque
> de Proton AG, utilisée à des fins de description.

- **Dépôt** : `github.com/TheWorms/kodi-addon-protonvpn`
- **Identifiant Kodi** : `service.protonvpn.manager`
- **Nom affiché** : ProtonVPN · **Licence** : GPL-2.0-or-later

---

## L'écran d'accueil (addon lancé)

```
●/○  État VPN  (serveur · IP)
Serveurs (WireGuard|OpenVPN, n)   ▸ serveurs du protocole actif
Connexion rapide                  → meilleur serveur du protocole par défaut
[Déconnecter]                     (si connecté)
Tester la connexion               → si OK : pays + IP publique
Importer une configuration
Stats
Journaux
Réglages
```

Le **protocole par défaut** (Réglages → Accueil) décide du backend affiché : en
WireGuard, les configs OpenVPN sont masquées, et inversement. Dans **Serveurs**,
choisir un serveur = test puis connexion (point vert = actif). Menu contextuel
sur un serveur → **Supprimer**.

> ⚠️ Ce menu apparaît quand tu **lances** l'addon (Add-ons → Extensions
> programmes → ProtonVPN → OK). Le menu contextuel → *Paramètres* ouvre la page
> de réglages (Accueil / WireGuard / OpenVPN / Avancé), pas ce menu.

## Prérequis

- **WireGuard** : `wg` + `wg-quick` et le support noyau WireGuard. Test rapide :
  ```bash
  which wg wg-quick
  ip link add wgtest type wireguard 2>&1 && echo OK && ip link del wgtest
  ```
  Sur CoreELEC/LibreELEC : selon le build, inclus au noyau ou via Entware
  (`opkg install wireguard-tools`).
- **OpenVPN** : binaire `openvpn` (addon *OpenVPN for LibreELEC*, ou
  `apt install openvpn`).

Sur CoreELEC/LibreELEC, Kodi tourne en root : pas de sudo nécessaire.

## Récupérer ses configurations

Sur https://account.protonvpn.com → **Downloads** :
- **WireGuard** : créer une clé pour l'appareil → télécharger le `.conf`
  (clés incluses, **aucun identifiant à saisir**).
- **OpenVPN** : télécharger les `.ovpn`, et renseigner l'identifiant
  **OpenVPN/IKEv2** (Account → OpenVPN/IKEv2, **≠ e-mail Proton**).

## Installer

1. Copier `kodi-addon-protonvpn-0.5.9.zip` sur la box.
2. Système → Add-ons → activer **Sources inconnues**.
3. Add-ons → **Installer depuis un fichier zip**.

## Utiliser

- **Importer une configuration** : sélectionne un `.ovpn` ou `.conf` (jusqu'à 10).
  Le type de VPN est reconnu automatiquement. Les fichiers sont copiés dans un
  dossier géré par l'addon (`userdata/ProtonVPN/`), **créé automatiquement** —
  rien à parcourir. Import dédié par backend aussi dans *Réglages → WireGuard*
  et *Réglages → OpenVPN*.
- **Serveurs** : liste les serveurs du **protocole actif** (l'autre est masqué).
  Choisis-en un → test + connexion (point vert = actif). Menu contextuel sur un
  serveur → **Supprimer**.
- **Connexion rapide** : se connecte au meilleur serveur du protocole par défaut.
- **Tester la connexion** : vérifie le dernier serveur (ou le protocole par
  défaut) et affiche le **pays + l'IP publique** si OK.
- **Stats** / **Journaux** : état, durée, âge du handshake (WireGuard), IP
  publique, débit reçu/envoyé, et le journal des événements.

## Indicateur dans le header du skin

L'addon publie l'état sur la fenêtre d'accueil :
`Window(home).Property(protonvpn.connected)` (`true`/`false`) et
`Window(home).Property(protonvpn.header)` (ex. « VPN · FI »). Un skin peut
l'afficher dans son header, par exemple :

```
$INFO[Window(home).Property(protonvpn.header)]
```

Activable via *Réglages → Accueil → Indicateur VPN dans le header du skin*.

## Widget d'accueil (Arctic Zephyr)

Sur le skin **Arctic Zephyr (Reloaded)**, l'addon peut installer un **widget
ProtonVPN natif**, sélectionnable comme les autres widgets du skin. Il s'affiche
en cartes — **État, Serveur, IP, Protocole, Durée, Trafic** — avec un panneau de
détail **« État du tunnel »** (serveur, protocole, IP de sortie, connecté depuis,
trafic de session). Durée, trafic et débit se mettent à jour **en direct** quand
le tunnel est actif.

- **Installer** : *Réglages → Widget → Installer le widget ProtonVPN*, puis sur
  l'accueil *Personnaliser → Widget* → choisir **ProtonVPN** (rangé sous
  « Infos système »).
- **Retirer** : *Réglages → Widget → Retirer le widget ProtonVPN*.

> ⚠️ **L'installation et la désinstallation du widget rechargent l'interface du
> skin** (bref écran noir, ~1–2 s) : c'est normal, l'addon modifie des fichiers
> du skin et force un rechargement pour les prendre en compte.

> Le widget modifie des fichiers d'Arctic Zephyr (sauvegardés en `.pvpnbak`).
> **Une mise à jour du skin écrase ces modifications** → il suffit de recliquer
> « Installer le widget ProtonVPN » après chaque mise à jour d'Arctic Zephyr.

## Réglages

Organisés en **Accueil / Serveurs / Widget / WireGuard / OpenVPN / Avancé** :
- **Accueil** : protocole par défaut (WireGuard/OpenVPN, masque l'autre),
  connexion rapide, test, **connexion auto au démarrage** (favori aléatoire
  *ou* serveur choisi), reconnexion auto, déconnexion à la fermeture,
  indicateur header.
- **Serveurs** : gérer les serveurs favoris, se connecter à un serveur
  WireGuard / OpenVPN, importer une configuration serveur, supprimer.
- **Widget** : installer / retirer le widget d'accueil (voir section dédiée).
- **WireGuard** : import WireGuard, chemin `wg-quick`.
- **OpenVPN** : import OpenVPN, identifiants OpenVPN/IKEv2, protocole UDP/TCP,
  NetShield, NAT modéré, chemin `openvpn`.
- **Avancé** : délai de connexion, intervalle de surveillance, sudo, API.

> Pour WireGuard, NetShield / NAT / Bouncing sont **figés à la génération** du
> `.conf` côté ProtonVPN (visible dans les commentaires en tête du fichier).

## Dépannage

- **WireGuard : outils introuvables** → installer `wireguard-tools` et vérifier
  le support noyau.
- **OpenVPN : AUTH_FAILED** → identifiant OpenVPN/IKEv2 (≠ e-mail) + mot de passe.
- **Binaire introuvable** → renseigner le chemin dans les réglages.
- **Journaux** : vue *Stats / Journaux*, ou `protonvpn.openvpn.log` /
  `service.protonvpn.manager` dans `kodi.log`.

## Limites

- Pas de kill-switch (nécessiterait iptables/nftables sur la box).
- WireGuard : options NetShield/NAT non modifiables depuis l'addon.
- Widget d'accueil : **Arctic Zephyr uniquement** ; à réinstaller après une mise
  à jour du skin (qui écrase les fichiers patchés).

---

Distribué sous **GPL-2.0-or-later** (voir `LICENSE.txt`). Projet indépendant,
non affilié à Proton AG.
