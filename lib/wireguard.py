# -*- coding: utf-8 -*-
#
# ProtonVPN - WireGuard backend
# Connection management via wg-quick. Liveness is derived from the interface
# existence plus the age of the latest handshake (cleaner than OpenVPN: a stale
# handshake means a dead tunnel even if the interface still exists).

import os
import re
import time
import subprocess

import xbmc

from lib import common
from lib import configs

PROP_IFACE = "protonvpn.wgiface"
PROP_UP = "protonvpn.wgup"

HANDSHAKE_STALE = 180   # seconds: no handshake within this window => dead
_UP_GRACE = 25          # seconds after bring-up before a missing handshake fails

_WG_CANDIDATES = ("/usr/bin/wg", "/usr/sbin/wg", "/sbin/wg",
                  "/opt/bin/wg", "/storage/.opt/bin/wg")
_WGQUICK_CANDIDATES = ("/usr/bin/wg-quick", "/usr/sbin/wg-quick",
                       "/sbin/wg-quick", "/opt/bin/wg-quick",
                       "/storage/.opt/bin/wg-quick")
_RESOLV_TOOLS = ("resolvconf", "resolvectl", "openresolv")


# --- tooling ---------------------------------------------------------------

def _first_existing(candidates, override=""):
    if override and os.path.exists(override):
        return override
    for c in candidates:
        if os.path.exists(c):
            return c
    return ""


def _wg_path():
    return _first_existing(_WG_CANDIDATES)


def _wgquick_path():
    return _first_existing(_WGQUICK_CANDIDATES,
                           common.get_setting("wg_quick_path", ""))


def available():
    return bool(_wg_path() and _wgquick_path())


def _has_resolvconf():
    paths = os.environ.get("PATH", "/usr/bin:/usr/sbin:/sbin:/bin").split(":")
    paths += ["/opt/bin", "/storage/.opt/bin"]
    for tool in _RESOLV_TOOLS:
        for d in paths:
            if d and os.path.exists(os.path.join(d, tool)):
                return True
    return False


def _run(cmd):
    if common.get_bool("use_sudo", False):
        cmd = ["sudo"] + cmd
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=45)
        return p.returncode, (p.stdout or b"").decode("utf-8", "ignore")
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)


# --- interface / handshake -------------------------------------------------

def _iface_from_path(path):
    return os.path.splitext(os.path.basename(path))[0]


def _iface_exists(iface):
    return bool(iface) and os.path.exists("/sys/class/net/%s" % iface)


def _wg_interfaces():
    rc, out = _run([_wg_path(), "show", "interfaces"])
    if rc != 0:
        return []
    return out.split()


def _active_iface():
    iface = common.get_prop(PROP_IFACE)
    if iface and _iface_exists(iface):
        return iface
    for name in _wg_interfaces():
        if name.startswith("pvpn-"):
            common.set_prop(PROP_IFACE, name)
            return name
    return ""


# Cache court du dernier handshake : la boucle du service (1 Hz quand
# connecte) et le snapshot stats interrogeaient chacun `wg show` a chaque
# tick -> 2-3 sous-processus/seconde en continu. Un TTL de 5 s divise cela
# sans effet perceptible : la fraicheur du handshake se juge sur une
# fenetre de 180 s, et l'age affiche (now - hs) reste exact.
_HS_CACHE = {"iface": "", "ts": 0.0, "val": 0}
_HS_CACHE_TTL = 5.0


def _latest_handshake(iface, cached=True):
    now = time.time()
    if (cached and _HS_CACHE["iface"] == iface
            and (now - _HS_CACHE["ts"]) < _HS_CACHE_TTL):
        return _HS_CACHE["val"]
    rc, out = _run([_wg_path(), "show", iface, "latest-handshakes"])
    if rc != 0:
        return 0
    best = 0
    for line in out.splitlines():
        parts = line.split()
        if parts:
            try:
                best = max(best, int(parts[-1]))
            except ValueError:
                pass
    _HS_CACHE["iface"] = iface
    _HS_CACHE["ts"] = now
    _HS_CACHE["val"] = best
    return best


def is_running():
    iface = _active_iface()
    if not _iface_exists(iface):
        return False
    hs = _latest_handshake(iface)
    if hs <= 0:
        try:
            up = int(common.get_prop(PROP_UP) or "0")
        except ValueError:
            up = 0
        return bool(up) and (time.time() - up) < _UP_GRACE
    return (time.time() - hs) < HANDSHAKE_STALE


# --- connect / disconnect --------------------------------------------------

def _sanitize_conf(text):
    """Adapt a Proton WireGuard config for minimal kernels (CoreELEC):
    - drop IPv6 from AllowedIPs/Address so wg-quick never touches ip6tables
      (many embedded kernels lack the ip6tables 'raw' table);
    - drop the DNS line when no resolvconf-like tool is available, otherwise
      wg-quick aborts the whole bring-up.
    """
    keep_dns = _has_resolvconf()
    out = []
    for line in text.splitlines():
        low = line.strip().lower()
        if low.startswith("dns") and not keep_dns:
            continue
        if low.startswith("allowedips") or low.startswith("address"):
            try:
                key, val = line.split("=", 1)
            except ValueError:
                out.append(line)
                continue
            v4 = [p.strip() for p in val.split(",") if p.strip() and ":" not in p]
            if low.startswith("allowedips") and not v4:
                v4 = ["0.0.0.0/0"]
            if v4:
                out.append("%s= %s" % (key, ", ".join(v4)))
            continue
        out.append(line)
    return "\n".join(out) + "\n"


def _prepare_runconf(src, iface):
    """Copy the config into the run dir under <iface>.conf (so wg-quick derives
    the right interface name) after sanitising it for the local kernel."""
    try:
        with open(src, "r", encoding="utf-8", errors="ignore") as fh:
            text = fh.read()
    except OSError as exc:
        common.error("Cannot read WG config %s: %s" % (src, exc))
        return ""
    text = _sanitize_conf(text)
    dst = os.path.join(configs.run_dir(), iface + ".conf")
    try:
        with open(dst, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(dst, 0o600)
    except OSError as exc:
        common.error("Cannot write WG run config: %s" % exc)
        return ""
    return dst


def _wait_handshake(iface, timeout):
    monitor = xbmc.Monitor()
    deadline = time.time() + timeout
    while time.time() < deadline:
        if monitor.abortRequested():
            return False
        if _latest_handshake(iface, cached=False) > 0:
            return True
        if not _iface_exists(iface):
            return False
        if monitor.waitForAbort(1.0):
            return False
    return False


def disconnect(quiet=False):
    iface = _active_iface()
    if not iface:
        common.set_state(False)
        common.set_phase(common.PHASE_DISCONNECTED)
        return True
    runconf = os.path.join(configs.run_dir(), iface + ".conf")
    target = runconf if os.path.exists(runconf) else iface
    _run([_wgquick_path(), "down", target])
    _HS_CACHE["iface"] = ""
    common.set_prop(PROP_IFACE, "")
    common.set_prop(PROP_UP, "")
    common.set_state(False)
    common.set_phase(common.PHASE_DISCONNECTED)
    if not quiet:
        common.notify(common.L(32070))
    return True


def connect(config, quiet=False):
    if not available():
        common.error("WireGuard tools (wg/wg-quick) not found")
        common.set_phase(common.PHASE_ERROR)
        if not quiet:
            common.ok(common.L(32140))
        return False

    src = config["path"] if isinstance(config, dict) else config
    name = (config.get("label") if isinstance(config, dict) else None) \
        or _iface_from_path(src)
    iface = _iface_from_path(src)

    # Bring down any stale managed tunnel first.
    disconnect(quiet=True)

    if common.get_phase() != common.PHASE_RECONNECTING:
        common.set_phase(common.PHASE_CONNECTING)

    runconf = _prepare_runconf(src, iface)
    if not runconf:
        common.set_phase(common.PHASE_ERROR)
        return False

    rc, out = _run([_wgquick_path(), "up", runconf])
    if rc != 0:
        common.error("wg-quick up failed (%s): %s" % (rc, out))
        common.set_phase(common.PHASE_ERROR)
        if not quiet:
            common.ok(common.L(32141) % (out.strip()[:300] or rc))
        return False

    common.set_prop(PROP_IFACE, iface)
    common.set_prop(PROP_UP, str(int(time.time())))

    timeout = common.get_int("connect_timeout", 30) or 30
    if _wait_handshake(iface, timeout):
        common.set_state(True, server=name, config=src)
        common.set_phase(common.PHASE_CONNECTED)
        if not quiet:
            common.notify(common.L(32073) % name)
        return True

    disconnect(quiet=True)
    common.set_phase(common.PHASE_ERROR)
    if not quiet:
        common.notify(common.L(32074))
    return False
