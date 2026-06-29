# -*- coding: utf-8 -*-
#
# ProtonVPN - OpenVPN backend
# Process management: connect, disconnect, liveness.
#
# OpenVPN is started in its own session (start_new_session) so it survives the
# short-lived plugin process. The service and the plugin coordinate through a
# pidfile and the OpenVPN log, plus shared window properties (in lib.common).

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

# NetShield / Moderate NAT are requested by appending a label to the username.
_NETSHIELD = {"0": "", "1": "+f1", "2": "+f2"}


def _log_path():
    return common.profile_file(LOG_FILE)


def _pid_path():
    return common.profile_file(PID_FILE)


def _auth_path():
    return common.profile_file(AUTH_FILE)


def _current_cfg_path():
    return common.profile_file(CURRENT_CFG)


def binary_path():
    override = common.get_setting("openvpn_path", "")
    if override and os.path.exists(override):
        return override
    for candidate in ("/usr/sbin/openvpn", "/usr/bin/openvpn",
                      "/sbin/openvpn", "/bin/openvpn",
                      "/opt/bin/openvpn", "/storage/.opt/bin/openvpn"):
        if os.path.exists(candidate):
            return candidate
    return "openvpn"


def available():
    return os.path.exists(binary_path()) or binary_path() == "openvpn"


# --- PID handling ----------------------------------------------------------

def _read_pid():
    try:
        with open(_pid_path(), "r") as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return 0


def _proc_is_openvpn(pid):
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as fh:
            return b"openvpn" in fh.read().lower()
    except OSError:
        return None


def _pid_alive(pid):
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    confirmed = _proc_is_openvpn(pid)
    return True if confirmed is None else confirmed


def is_running():
    return _pid_alive(_read_pid())


# --- Auth + config preparation --------------------------------------------

def _write_auth():
    user = common.get_setting("vpn_username", "").strip()
    pwd = common.get_setting("vpn_password", "")
    if not user or not pwd:
        return False
    suffix = _NETSHIELD.get(common.get_setting("netshield", "0"), "")
    if common.get_bool("moderate_nat", False):
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


# --- Connect / disconnect --------------------------------------------------

def disconnect(quiet=False):
    pid = _read_pid()
    killed = False
    if _pid_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
            killed = True
        except OSError:
            pass
        for _ in range(10):
            if not _pid_alive(pid):
                break
            time.sleep(0.3)
        if _pid_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
    try:
        if os.path.exists(_pid_path()):
            os.remove(_pid_path())
    except OSError:
        pass
    common.set_state(False)
    common.set_phase(common.PHASE_DISCONNECTED)
    if killed and not quiet:
        common.notify(common.L(32070))
    return True


def _tail_log_for(token, timeout, pid=0):
    deadline = time.time() + timeout
    monitor = xbmc.Monitor()
    log = _log_path()
    grace = time.time() + 4
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
        if pid and time.time() > grace and not _pid_alive(pid):
            return False
        if monitor.waitForAbort(1.0):
            return None
    return False


def connect(config, quiet=False):
    src = config["path"] if isinstance(config, dict) else config
    name = (config.get("label") if isinstance(config, dict) else None) \
        or os.path.basename(src)

    if not _write_auth():
        if not quiet:
            common.ok(common.L(32071))  # credentials missing
        common.set_phase(common.PHASE_ERROR)
        return False

    if is_running():
        disconnect(quiet=True)

    cfg = _prepare_config(src)
    if not cfg:
        common.set_phase(common.PHASE_ERROR)
        return False

    try:
        open(_log_path(), "w").close()
    except OSError:
        pass

    if common.get_phase() != common.PHASE_RECONNECTING:
        common.set_phase(common.PHASE_CONNECTING)

    cmd = [
        binary_path(),
        "--config", cfg,
        "--auth-user-pass", _auth_path(),
        "--auth-retry", "nointeract",
        "--auth-nocache",
        "--connect-retry-max", "3",
        "--remap-usr1", "SIGTERM",
        "--persist-tun",
        "--nobind",
        "--mute-replay-warnings",
        "--writepid", _pid_path(),
        "--log", _log_path(),
        "--verb", "3",
    ]
    if common.get_bool("use_sudo", False):
        cmd = ["sudo"] + cmd

    common.log("Starting OpenVPN: %s" % " ".join(cmd))
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        common.error("Failed to launch OpenVPN: %s" % exc)
        common.set_phase(common.PHASE_ERROR)
        if not quiet:
            common.ok(common.L(32072) % exc)
        return False

    timeout = common.get_int("connect_timeout", 30) or 30
    result = _tail_log_for(_COMPLETED, timeout, pid=proc.pid)

    if result is True:
        common.set_state(True, server=name, config=src)
        common.set_phase(common.PHASE_CONNECTED)
        if not quiet:
            common.notify(common.L(32073) % name)
        return True

    disconnect(quiet=True)
    common.set_phase(common.PHASE_ERROR)
    if result is False and not quiet:
        common.notify(common.L(32074))
    return False
