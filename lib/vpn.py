# -*- coding: utf-8 -*-
#
# ProtonVPN
# OpenVPN process management: connect, disconnect, status.
#
# The OpenVPN process is started in its own session (setsid) so it survives the
# short-lived plugin process that launches it. Both the service and the plugin
# coordinate through a pidfile and the OpenVPN log, plus window properties.

import os
import re
import time
import signal
import subprocess

import xbmc
import xbmcvfs

from lib import common

AUTH_FILE = "protonvpn.auth"
CURRENT_CFG = "protonvpn.current.ovpn"
LOG_FILE = "protonvpn.openvpn.log"
PID_FILE = "protonvpn.pid"

_COMPLETED = "Initialization Sequence Completed"
_AUTH_FAILED = "AUTH_FAILED"

# NetShield is selected by appending a label to the OpenVPN username.
# Per ProtonVPN documentation: +f1 = block malware, +f2 = block malware,
# ads and trackers. Empty = no filtering.
_NETSHIELD = {"0": "", "1": "+f1", "2": "+f2"}


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _log_path():
    return common.profile_file(LOG_FILE)


def _pid_path():
    return common.profile_file(PID_FILE)


def _auth_path():
    return common.profile_file(AUTH_FILE)


def _current_cfg_path():
    return common.profile_file(CURRENT_CFG)


def openvpn_path():
    override = common.get_setting("openvpn_path", "")
    if override and os.path.exists(override):
        return override
    for candidate in ("/usr/sbin/openvpn", "/usr/bin/openvpn",
                      "/sbin/openvpn", "/bin/openvpn"):
        if os.path.exists(candidate):
            return candidate
    return "openvpn"  # rely on PATH as a last resort


# ---------------------------------------------------------------------------
# PID handling
# ---------------------------------------------------------------------------

def _read_pid():
    try:
        with open(_pid_path(), "r") as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return 0


def _pid_alive(pid):
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def is_running():
    return _pid_alive(_read_pid())


# ---------------------------------------------------------------------------
# Auth + config preparation
# ---------------------------------------------------------------------------

def _write_auth():
    user = common.get_setting("vpn_username", "").strip()
    pwd = common.get_setting("vpn_password", "")
    if not user or not pwd:
        return False
    suffix = _NETSHIELD.get(common.get_setting("netshield", "0"), "")
    if common.get_bool("moderate_nat", False):
        # Moderate NAT is requested with the +nr label (ProtonVPN docs).
        suffix += "+nr"
    path = _auth_path()
    with open(path, "w") as fh:
        fh.write(user + suffix + "\n")
        fh.write(pwd + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return True


def _prepare_config(src_ovpn):
    """Copy the chosen .ovpn into the profile, stripping any auth-user-pass
    directive so we can supply the credentials file ourselves."""
    src = xbmcvfs.translatePath(src_ovpn)
    try:
        with open(src, "r", encoding="utf-8", errors="ignore") as fh:
            text = fh.read()
    except OSError as exc:
        common.error("Cannot read config %s: %s" % (src, exc))
        return ""
    text = re.sub(r"^\s*auth-user-pass.*$", "", text, flags=re.MULTILINE)
    dst = _current_cfg_path()
    with open(dst, "w") as fh:
        fh.write(text)
    return dst


# ---------------------------------------------------------------------------
# Connect / disconnect
# ---------------------------------------------------------------------------

def disconnect(quiet=False):
    pid = _read_pid()
    killed = False
    if _pid_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
            killed = True
        except OSError:
            pass
        # Give it a moment, then force.
        for _ in range(10):
            if not _pid_alive(pid):
                break
            time.sleep(0.3)
        if _pid_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
    # Belt and braces: clean up any stray openvpn started by us.
    try:
        if os.path.exists(_pid_path()):
            os.remove(_pid_path())
    except OSError:
        pass
    common.set_state(False)
    if killed and not quiet:
        common.notify(common.L(32070))  # "Disconnected"
    return True


def _tail_log_for(token, timeout):
    deadline = time.time() + timeout
    monitor = xbmc.Monitor()
    log = _log_path()
    while time.time() < deadline:
        if monitor.abortRequested():
            return None
        try:
            with open(log, "r", encoding="utf-8", errors="ignore") as fh:
                content = fh.read()
        except OSError:
            content = ""
        if _AUTH_FAILED in content:
            return False
        if token in content:
            return True
        if monitor.waitForAbort(1.0):
            return None
    return False


def connect(config, label=None, quiet=False):
    """Connect using the given config dict (from lib.configs) or path."""
    if isinstance(config, dict):
        src = config["path"]
        name = label or config.get("label") or os.path.basename(src)
    else:
        src = config
        name = label or os.path.basename(src)

    if not _write_auth():
        if not quiet:
            common.ok(common.L(32071))  # credentials missing
        return False

    # Drop any existing connection first.
    if is_running():
        disconnect(quiet=True)

    cfg = _prepare_config(src)
    if not cfg:
        return False

    # Reset the log so we only read this session's output.
    try:
        open(_log_path(), "w").close()
    except OSError:
        pass

    cmd = [
        openvpn_path(),
        "--config", cfg,
        "--auth-user-pass", _auth_path(),
        "--writepid", _pid_path(),
        "--log", _log_path(),
        "--verb", "3",
    ]
    if common.get_bool("use_sudo", False):
        cmd = ["sudo"] + cmd

    common.log("Starting OpenVPN: %s" % " ".join(cmd))
    try:
        # New session so OpenVPN outlives the launching (plugin) process.
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        common.error("Failed to launch OpenVPN: %s" % exc)
        if not quiet:
            common.ok(common.L(32072) % exc)  # launch failed
        return False

    timeout = common.get_int("connect_timeout", 30) or 30
    result = _tail_log_for(_COMPLETED, timeout)

    if result is True:
        common.set_state(True, server=name, config=src)
        common.set_setting("last_config", src)
        if not quiet:
            common.notify(common.L(32073) % name)  # "Connected to %s"
        return True

    # Failed: tidy up.
    disconnect(quiet=True)
    if result is False:
        if not quiet:
            common.notify(common.L(32074))  # connection failed / auth
    return False


def reconnect_last(quiet=True):
    last = common.get_setting("last_config", "")
    if last and os.path.exists(xbmcvfs.translatePath(last)):
        return connect(last, quiet=quiet)
    return False


# ---------------------------------------------------------------------------
# External IP (best effort, display only)
# ---------------------------------------------------------------------------

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
