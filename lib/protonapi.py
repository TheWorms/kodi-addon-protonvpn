# -*- coding: utf-8 -*-
#
# ProtonVPN
# Optional, best-effort enrichment from the public ProtonVPN logicals endpoint.
#
# This is purely cosmetic: it annotates the server list with current load so the
# GUI can show e.g. "NL#1 (load 23%)". The addon works fully without it; any
# failure is swallowed silently. Disabled by default in settings.

import json
import time
import urllib.request

from lib import common

_LOGICALS_URL = "https://api.protonvpn.ch/vpn/logicals"
_CACHE = {"ts": 0, "data": {}}
_TTL = 600  # seconds


def _fetch():
    headers = {
        "User-Agent": "ProtonVPN/4 (Kodi addon)",
        "Accept": "application/vnd.protonmail.v1+json",
        "x-pm-appversion": "LinuxVPN_4.0.0",
    }
    req = urllib.request.Request(_LOGICALS_URL, headers=headers)
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_map():
    """Return {DOMAIN_OR_NAME(upper): {'load': int, 'tier': int}} or {}."""
    if not common.get_bool("use_api", False):
        return {}
    now = time.time()
    if _CACHE["data"] and now - _CACHE["ts"] < _TTL:
        return _CACHE["data"]
    try:
        payload = _fetch()
    except Exception as exc:
        common.debug("logicals fetch failed: %s" % exc)
        return {}
    result = {}
    for srv in payload.get("LogicalServers", []):
        entry = {"load": srv.get("Load", 0), "tier": srv.get("Tier", 0)}
        name = (srv.get("Name") or "").upper()
        if name:
            result[name] = entry
        for node in srv.get("Servers", []):
            dom = (node.get("Domain") or "").upper()
            if dom:
                result[dom] = entry
    _CACHE.update({"ts": now, "data": result})
    return result


def annotate(cfg, lmap):
    """Return a load percentage int for a config, or None."""
    if not lmap:
        return None
    candidates = [cfg.get("label", "").upper(), cfg.get("remote", "").upper()]
    for key in candidates:
        if key and key in lmap:
            return lmap[key].get("load")
    return None
