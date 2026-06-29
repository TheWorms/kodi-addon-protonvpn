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


def snapshot():
    state = common.get_state()
    backend = common.get_prop("protonvpn.backend") or common.get_setting("last_backend", "")
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
