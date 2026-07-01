# -*- coding: utf-8 -*-
#
# ProtonVPN - backend dispatcher
# Presents a single connect/disconnect/is_running/reconnect API to the plugin
# and the background service, routing to the OpenVPN or WireGuard backend based
# on the chosen configuration. The active backend is tracked so disconnect and
# liveness checks always target the right one.

import os
import re

import xbmcvfs

from lib import common
from lib import configs
from lib import openvpn
from lib import wireguard

PROP_BACKEND = "protonvpn.backend"


def _set_active(backend):
    common.set_prop(PROP_BACKEND, backend or "")


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
    cfg = _resolve(config)
    if not cfg:
        if not quiet:
            common.notify(common.L(32076))
        return False
    backend = cfg.get("backend", "openvpn")
    mod = wireguard if backend == "wireguard" else openvpn
    ok = mod.connect(cfg, quiet=quiet)
    if ok:
        import time
        common.set_prop("protonvpn.desired", "on")
        common.set_setting("last_config", cfg["path"])
        common.set_setting("last_backend", backend)
        _set_active(backend)
        common.set_since(time.time())
        common.set_header("VPN \u00b7 %s" % (cfg.get("country") or cfg.get("label") or ""))
        common.event("connecte %s (%s)" % (cfg.get("label", ""), backend))
    return ok


def disconnect(quiet=False):
    backend = _active()
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
    common.event("deconnecte")
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
