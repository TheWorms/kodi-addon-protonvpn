# -*- coding: utf-8 -*-
#
# ProtonVPN - live statistics for the Stats / Journaux view.
# Best-effort, display only. Numbers come from the kernel (WireGuard via
# `wg show`, OpenVPN via the tun interface counters in /sys).

import os
import time

from lib import common
from lib import vpn
from lib import wireguard


def _read_int(path):
    try:
        with open(path, "r") as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return 0


def _wg_transfer(iface):
    rc, out = wireguard._run([wireguard._wg_path(), "show", iface, "transfer"])
    rx = tx = 0
    if rc == 0:
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 3:
                try:
                    rx += int(parts[-2])
                    tx += int(parts[-1])
                except ValueError:
                    pass
    return rx, tx


def _find_tun():
    try:
        for name in sorted(os.listdir("/sys/class/net")):
            if name.startswith(("tun", "tap")):
                return name
    except OSError:
        pass
    return ""


_IP_CACHE = {"ip": "", "ts": 0.0, "fail_ts": 0.0}


def _external_ip_cached(ttl=60, fail_ttl=45):
    now = time.time()
    if _IP_CACHE["ip"] and (now - _IP_CACHE["ts"]) < ttl:
        return _IP_CACHE["ip"]
    # Cache negatif : apres un echec, ne pas retenter avant fail_ttl.
    # Sans cela, des que la resolution echouait, on relancait jusqu'a
    # 2 requetes HTTPS (timeout 5 s chacune) A CHAQUE appel -- precisement
    # dans le scenario ou le tunnel est monte mais Internet coupe
    # (= une chute en cours).
    if _IP_CACHE["fail_ts"] and (now - _IP_CACHE["fail_ts"]) < fail_ttl:
        return _IP_CACHE["ip"]
    try:
        ip = vpn.external_ip() or ""
    except Exception:
        ip = ""
    if ip:
        _IP_CACHE["ip"] = ip
        _IP_CACHE["ts"] = now
        _IP_CACHE["fail_ts"] = 0.0
    else:
        _IP_CACHE["fail_ts"] = now
    return _IP_CACHE["ip"]


def snapshot(resolve_ip=True):
    """resolve_ip=False : ne JAMAIS declencher de requete reseau ; se contenter
    de la derniere IP connue. Utilise par la boucle a 1 Hz du service pour ne
    pas bloquer la machine a etats sur des appels HTTPS."""
    state = common.get_state()
    backend = (common.get_prop("protonvpn.backend")
               or common.get_setting("last_backend", "")).strip().lower()
    snap = {
        "connected": bool(state["connected"]),
        "backend": backend,
        "server": state.get("server", ""),
        "ip": state.get("ip", ""),
        "uptime": 0,
        "hs_age": None,
        "rx": 0,
        "tx": 0,
        "iface": "",
    }
    since = common.get_since()
    if since:
        snap["uptime"] = max(0, int(time.time()) - since)

    if not snap["connected"]:
        return snap

    if not snap["ip"]:
        snap["ip"] = _external_ip_cached() if resolve_ip else _IP_CACHE["ip"]

    if backend == "wireguard":
        iface = wireguard._active_iface()
        snap["iface"] = iface
        if iface:
            hs = wireguard._latest_handshake(iface)
            if hs > 0:
                snap["hs_age"] = max(0, int(time.time()) - hs)
            snap["rx"], snap["tx"] = _wg_transfer(iface)
    else:
        iface = _find_tun()
        snap["iface"] = iface
        if iface:
            base = "/sys/class/net/%s/statistics/" % iface
            snap["rx"] = _read_int(base + "rx_bytes")
            snap["tx"] = _read_int(base + "tx_bytes")
    return snap


# --- formatting helpers ----------------------------------------------------

def human_bytes(n):
    n = float(n or 0)
    for unit in ("o", "Ko", "Mo", "Go", "To"):
        if n < 1024 or unit == "To":
            return ("%.0f %s" % (n, unit)) if unit == "o" else ("%.1f %s" % (n, unit))
        n /= 1024
    return "%.1f To" % n


def human_duration(seconds):
    seconds = int(seconds or 0)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return "%dh %02dm" % (h, m)
    return "%02d:%02d" % (m, s)


# ---------------------------------------------------------------------------
# Home-window properties (always-on status panel)
#
# The service publishes these every cycle so a skin element on the home screen
# can show live VPN status, independently of the popup dialog. Properties are
# raw values (no colour tags) under the "protonvpn." prefix on Window(10000):
#   protonvpn.connected   "true" / "false"
#   protonvpn.state       localized "Connecté" / "Déconnecté"
#   protonvpn.backend     "WireGuard" / "OpenVPN" / ""
#   protonvpn.server      e.g. "FR#679"
#   protonvpn.country     localized country name (from the server prefix)
#   protonvpn.ip          public IP
#   protonvpn.iface       tunnel interface
#   protonvpn.uptime      human duration
#   protonvpn.rx / .tx    human bytes
#   protonvpn.rate        "↓ x/s  ↑ y/s"
#   protonvpn.flag        absolute path to the country flag png (or "")
# ---------------------------------------------------------------------------

import xbmcgui  # noqa: E402

_HOME_WIN = xbmcgui.Window(10000)
_RATE_LAST = {}


def _flag_path(server):
    if server and len(server) >= 2 and server[:2].isalpha():
        p = os.path.join(common.ADDON_PATH, "resources", "flags",
                         "%s.png" % server[:2].lower())
        if os.path.exists(p):
            return p
    return ""


def publish_home_props(resolve_ip=True):
    """Publish the current VPN state into Window(10000) properties.
    resolve_ip=False : aucun appel reseau (voir snapshot)."""
    def setp(key, value):
        try:
            _HOME_WIN.setProperty("protonvpn." + key, value)
        except Exception:
            pass
    try:
        snap = snapshot(resolve_ip=resolve_ip)
    except Exception:
        return
    if not snap.get("connected"):
        setp("connected", "false")
        setp("state", common.L(32202))   # Déconnecté
        for k in ("backend", "server", "country", "ip", "iface",
                  "uptime", "rx", "tx", "rate", "flag"):
            setp(k, "")
        _RATE_LAST.clear()
        _IP_CACHE["ip"] = ""
        _IP_CACHE["fail_ts"] = 0.0
        return

    setp("connected", "true")
    setp("state", common.L(32201))        # Connecté
    setp("backend", "WireGuard" if snap["backend"] == "wireguard" else "OpenVPN")
    server = snap.get("server") or ""
    setp("server", server)
    cc = server[:2].lower() if len(server) >= 2 and server[:2].isalpha() else ""
    setp("country", common.country_name(cc) if cc else "")
    setp("flag", _flag_path(server))
    setp("ip", snap.get("ip") or "")
    setp("iface", snap.get("iface") or "")
    setp("uptime", human_duration(snap.get("uptime") or 0))
    setp("rx", human_bytes(snap.get("rx") or 0))
    setp("tx", human_bytes(snap.get("tx") or 0))

    now = time.time()
    rate = ""
    if _RATE_LAST:
        dt = now - _RATE_LAST.get("t", now)
        if dt > 0:
            drx = max(0, (snap.get("rx") or 0) - _RATE_LAST.get("rx", 0)) / dt
            dtx = max(0, (snap.get("tx") or 0) - _RATE_LAST.get("tx", 0)) / dt
            rate = "\u2193 %s/s  \u2191 %s/s" % (human_bytes(drx), human_bytes(dtx))
    _RATE_LAST.update(t=now, rx=snap.get("rx") or 0, tx=snap.get("tx") or 0)
    setp("rate", rate)
