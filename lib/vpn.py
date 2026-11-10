# -*- coding: utf-8 -*-
#
# ProtonVPN - backend dispatcher
# Presents a single connect/disconnect/is_running/reconnect API to the plugin
# and the background service, routing to the OpenVPN or WireGuard backend based
# on the chosen configuration. The active backend is tracked so disconnect and
# liveness checks always target the right one.

import os
import re
import time

import xbmcvfs

from lib import common
from lib import configs
from lib import openvpn
from lib import wireguard

PROP_BACKEND = "protonvpn.backend"
# Cross-process "connecting" flag: the plugin and the background service only
# share window properties, so this is the only lock preventing two concurrent
# bring-ups (e.g. two wg-quick up racing on the same interface). A stale flag
# (holder crashed) is ignored after _CONNECT_STALE seconds.
PROP_CONNECTING = "protonvpn.connecting"
_CONNECT_STALE = 120


def _set_active(backend):
    common.set_prop(PROP_BACKEND, backend or "")


def _connect_in_progress():
    try:
        ts = int(common.get_prop(PROP_CONNECTING) or "0")
    except ValueError:
        return False
    return bool(ts) and (time.time() - ts) < _CONNECT_STALE


def _active():
    return common.get_prop(PROP_BACKEND) or common.get_setting("last_backend", "")


def _resolve(config):
    """Accept a config dict or a path and return a parsed config dict."""
    if isinstance(config, dict):
        return config
    return configs.parse_config(xbmcvfs.translatePath(config))


def backend_available(backend):
    return wireguard.available() if backend == "wireguard" else openvpn.available()


def connect(config, quiet=False):
    if _connect_in_progress():
        common.log("connect skipped: another connection attempt is in progress")
        return False
    common.set_prop(PROP_CONNECTING, str(int(time.time())))
    try:
        return _connect_locked(config, quiet=quiet)
    finally:
        common.set_prop(PROP_CONNECTING, "")


def _connect_locked(config, quiet=False):
    cfg = _resolve(config)
    if not cfg:
        if not quiet:
            common.notify(common.L(32076))
        return False
    backend = cfg.get("backend", "openvpn")
    mod = wireguard if backend == "wireguard" else openvpn
    ok = mod.connect(cfg, quiet=quiet)
    if ok:
        common.set_prop("protonvpn.desired", "on")
        # Connexion manuelle pendant une pause du VPN : la pause s'arrête là.
        common.set_prop("protonvpn.paused", "")
        common.set_prop("protonvpn.paused_config", "")
        common.set_setting("last_config", cfg["path"])
        common.set_setting("last_backend", backend)
        _set_active(backend)
        common.set_since(time.time())
        common.set_header("VPN \u00b7 %s" % (cfg.get("country") or cfg.get("label") or ""))
        common.event("connecte %s (%s)" % (cfg.get("label", ""), backend))
        # Exceptions en route directe : wg-quick vient de poser ses règles,
        # parfois devant les nôtres ; remise en ordre sans attendre le service.
        from lib import bypass
        bypass.sync()
    return ok


def disconnect(quiet=False, pause=False):
    """pause=True : arrêt demandé par une exception « Pause du VPN ». Le
    souhait de connexion reste « on », le service relancera le tunnel."""
    backend = _active()
    if not pause:
        common.set_prop("protonvpn.desired", "off")
    if backend == "wireguard":
        wireguard.disconnect(quiet=quiet)
        openvpn.disconnect(quiet=True)
    else:
        openvpn.disconnect(quiet=quiet)
        wireguard.disconnect(quiet=True)
    _set_active("")
    common.set_since(0)
    common.set_header("")
    common.event("en pause" if pause else "deconnecte")
    return True


def is_running():
    backend = _active()
    if backend == "wireguard":
        return wireguard.is_running()
    if backend == "openvpn":
        return openvpn.is_running()
    # Unknown (e.g. after a Kodi restart with no property): probe both.
    return openvpn.is_running() or wireguard.is_running()


def reconnect_last(quiet=True):
    last = common.get_setting("last_config", "")
    if last and os.path.exists(xbmcvfs.translatePath(last)):
        return connect(last, quiet=quiet)
    return False


# --- External IP (best effort, display only) -------------------------------

def external_ip():
    import urllib.request
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                ip = resp.read().decode("utf-8").strip()
                if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
                    return ip
        except Exception:
            continue
    return ""
