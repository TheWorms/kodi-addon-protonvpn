<!-- logo:start -->
<p align="center"><img src="resources/icon.png" alt="Logo" width="160"></p>
<!-- logo:end -->

[Français](README.md) · **English**

# ProtonVPN

<!-- version:auto -->
**Version : 0.6.4**
<!-- /version:auto -->

Kodi add-on to drive **ProtonVPN** with a simple interface, in **WireGuard** or
**OpenVPN** as you prefer. Import your configurations, pick a server (test +
connect), see the live VPN status, follow stats and logs.

Designed for **CoreELEC / LibreELEC** and other Linux Kodi installs (tested on
Kodi 21 "Omega", ODROID-N2+).

> Independent add-on, **not affiliated with Proton AG**. "ProtonVPN" is a
> trademark of Proton AG, used for descriptive purposes.

- **Repository**: `github.com/TheWorms/kodi-addon-protonvpn`
- **Kodi id**: `service.protonvpn.manager`
- **Display name**: ProtonVPN · **License**: GPL-2.0-or-later

---

## Installation

**Recommended — TheWorms repository** (automatic updates).

Download the repository by clicking **[HERE](https://raw.githubusercontent.com/TheWorms/kodi-repo/main/zips/repository.theworms/repository.theworms.zip)**, then in Kodi:

1. **Add-ons** → **Install from zip file** → select the downloaded zip
   *(if Kodi blocks it, enable **Unknown sources** under Settings → Add-ons)*
2. **Install from repository** → **TheWorms Repository** → pick the add-on
3. Updates will then be automatic

**Manual install (alternative):** download the add-on zip from the [Releases](../../releases) page, then **Add-ons** → **Install from zip file**.

---

## The home screen (add-on launched)

```
●/○  VPN status  (server · IP)
Servers (WireGuard|OpenVPN, n)    ▸ servers of the active protocol
Quick connect                     → best server of the default protocol
[Disconnect]                      (if connected)
Test connection                   → if OK: country + public IP
Import a configuration
Stats
Logs
Settings
```

The **default protocol** (Settings → Home) decides which backend is shown: in
WireGuard, OpenVPN configs are hidden, and vice versa. In **Servers**, picking a
server = test then connect (green dot = active). Context menu on a server →
**Remove**.

> ⚠️ This menu appears when you **launch** the add-on (Add-ons → Program add-ons
> → ProtonVPN → OK). The context menu → *Settings* opens the settings page
> (Home / WireGuard / OpenVPN / Advanced), not this menu.

## Requirements

- **WireGuard**: `wg` + `wg-quick` and WireGuard kernel support. Quick test:
  ```bash
  which wg wg-quick
  ip link add wgtest type wireguard 2>&1 && echo OK && ip link del wgtest
  ```
  On CoreELEC/LibreELEC: depending on the build, included in the kernel or via
  Entware (`opkg install wireguard-tools`).
- **OpenVPN**: the `openvpn` binary (*OpenVPN for LibreELEC* add-on, or
  `apt install openvpn`).

On CoreELEC/LibreELEC, Kodi runs as root: no sudo needed.

## Getting your configurations

On https://account.protonvpn.com → **Downloads**:
- **WireGuard**: create a key for the device → download the `.conf` (keys
  included, **no credentials to enter**).
- **OpenVPN**: download the `.ovpn` files, and enter the **OpenVPN/IKEv2**
  credentials (Account → OpenVPN/IKEv2, **≠ Proton email**).

## Usage

- **Import a configuration**: select a `.ovpn` or `.conf` (up to 10). The VPN
  type is detected automatically. Files are copied into a folder managed by the
  add-on (`userdata/ProtonVPN/`), **created automatically** — nothing to browse.
  Per-backend import is also available in *Settings → WireGuard* and
  *Settings → OpenVPN*.
- **Servers**: lists the servers of the **active protocol** (the other is
  hidden). Pick one → test + connect (green dot = active). Context menu on a
  server → **Remove**.
- **Quick connect**: connects to the best server of the default protocol.
- **Test connection**: checks the last server (or the default protocol) and
  shows the **country + public IP** if OK.
- **Stats** / **Logs**: status, duration, handshake age (WireGuard), public IP,
  received/sent throughput, and the event log.

## Indicator in the skin header

The add-on publishes status on the home window:
`Window(home).Property(protonvpn.connected)` (`true`/`false`) and
`Window(home).Property(protonvpn.header)` (e.g. "VPN · FI"). A skin can show it
in its header, for example:

```
$INFO[Window(home).Property(protonvpn.header)]
```

Enable it via *Settings → Home → VPN indicator in the skin header*.

## Home widget (Arctic Zephyr)

On the **Arctic Zephyr (Reloaded)** skin, the add-on can install a **native
ProtonVPN widget**, selectable like the skin's other widgets. It shows cards —
**Status, Server, IP, Protocol, Duration, Traffic** — with a **"Tunnel status"**
detail panel (server, protocol, exit IP, connected since, session traffic).
Duration, traffic and throughput update **live** while the tunnel is active.

- **Install**: *Settings → Widget → Install the ProtonVPN widget*, then on the
  home screen *Customize → Widget* → choose **ProtonVPN** (filed under
  "System info").
- **Remove**: *Settings → Widget → Remove the ProtonVPN widget*.

> ⚠️ **Installing and removing the widget reloads the skin UI** (brief black
> screen, ~1–2 s): this is normal — the add-on modifies skin files and forces a
> reload to apply them.

> The widget modifies Arctic Zephyr files (backed up as `.pvpnbak`). **A skin
> update overwrites those changes** → just click "Install the ProtonVPN widget"
> again after each Arctic Zephyr update.

## Exceptions: pause the VPN for some add-ons

Some services block or throttle VPN addresses (YouTube, catch-up TV…). You
can pick add-ons that **pause the VPN**:

- the tunnel stops as soon as you **open one of these add-ons** or **play one
  of its videos** ("VPN paused" notification, "Paused" state on the widget);
- it comes back on its own **a few seconds after** you leave it (adjustable
  delay, 5 s by default, so it does not reconnect between two episodes);
- if you start playback from another add-on during the pause, the VPN comes
  back at once; a manual disconnect during the pause is respected.

Setting: *Settings → Exceptions* → **Add or remove add-ons…** (checklist of
installed add-ons).

> During the pause, **the whole box is without VPN**, not only the chosen
> add-on: Kodi runs all its add-ons in a single program, so the system cannot
> separate their traffic.

> Upgrading from 0.5.x: if the former "YouTube outside the VPN" option was
> checked, Wtube is added to the exceptions automatically.

## Settings

Organized into **Home / Servers / Exceptions / Widget / WireGuard / OpenVPN / Advanced**:
- **Home**: default protocol (WireGuard/OpenVPN, hides the other), quick connect,
  test, **auto-connect at startup** (random favorite *or* chosen server),
  auto-reconnect, disconnect on exit, header indicator.
- **Servers**: manage favorite servers, connect to a WireGuard / OpenVPN server,
  import a server configuration, remove.
- **Exceptions**: turn on the VPN pause for some add-ons, add or remove
  add-ons, delay before reconnecting (see dedicated section).
- **Widget**: install / remove the home widget (see dedicated section).
- **WireGuard**: WireGuard import, `wg-quick` path.
- **OpenVPN**: OpenVPN import, OpenVPN/IKEv2 credentials, UDP/TCP protocol,
  NetShield, moderate NAT, `openvpn` path.
- **Advanced**: connection timeout, monitoring interval, sudo, API.

> For WireGuard, NetShield / NAT / Bouncing are **frozen at generation** of the
> `.conf` on ProtonVPN's side (visible in the comments at the top of the file).

## Troubleshooting

- **WireGuard: tools not found** → install `wireguard-tools` and check kernel
  support.
- **OpenVPN: AUTH_FAILED** → OpenVPN/IKEv2 credentials (≠ email) + password.
- **Binary not found** → set the path in the settings.
- **Logs**: *Stats / Logs* view, or `protonvpn.openvpn.log` /
  `service.protonvpn.manager` in `kodi.log`.

## Limitations

- No kill-switch (would require iptables/nftables on the box).
- WireGuard: NetShield/NAT options not editable from the add-on.
- Home widget: **Arctic Zephyr only**; reinstall after a skin update (which
  overwrites the patched files).
- Exceptions: the pause turns the VPN off for **the whole box** while the
  add-on is in use; traffic is not split add-on by add-on.

---

Distributed under **GPL-2.0-or-later** (see `LICENSE.txt`). Independent project,
not affiliated with Proton AG.
