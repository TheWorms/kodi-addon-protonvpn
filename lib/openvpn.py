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
    except PermissionError:
        # Le processus existe mais appartient a root (OpenVPN lance par sudo
        # depuis un Kodi non root) : vivant, la ligne de commande tranche.
        pass
    except OSError:
        return False
    confirmed = _proc_is_openvpn(pid)
    return True if confirmed is None else confirmed


def is_running():
    return _pid_alive(_read_pid())


# --- Auth + config preparation --------------------------------------------

def _write_private(path, text):
    """Ecrit un fichier lisible par son seul proprietaire, des sa creation
    (un chmod apres coup le laissait lisible par tous un court instant)."""
    try:
        os.remove(path)
    except OSError:
        pass
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _signal(pid, sig):
    """Envoie un signal a OpenVPN ; passe par sudo quand le processus
    appartient a root et que l'option sudo est active."""
    try:
        os.kill(pid, sig)
        return True
    except PermissionError:
        if not common.get_bool("use_sudo", False):
            return False
    except OSError:
        return False
    try:
        proc = subprocess.run(["sudo", "-n", "kill", "-%d" % int(sig), str(pid)],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=10)
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _write_auth():
    user = common.get_setting("vpn_username", "").strip()
    pwd = common.get_setting("vpn_password", "")
    if not user or not pwd:
        return False
    suffix = _NETSHIELD.get(common.get_setting("netshield", "0"), "")
    if common.get_bool("moderate_nat", False):
        suffix += "+nr"
    try:
        _write_private(_auth_path(), user + suffix + "\n" + pwd + "\n")
    except OSError as exc:
        common.error("Cannot write the credentials file: %s" % exc)
        return False
    return True


# 0.6.7 (audit du 12/11/2026) : un fichier .ovpn peut faire executer des
# commandes a OpenVPN (up, down, plugin...), en root si sudo est actif.
# ProtonVPN ne s'en sert que pour le DNS (update-resolv-conf) : ces scripts-la
# sont gardes, tous les autres retires de la copie lancee. Meme principe que
# PreUp/PostUp pour WireGuard.
_SCRIPT_DIRECTIVES = frozenset((
    "up", "down", "route-up", "route-pre-down", "ipchange", "client-connect",
    "client-disconnect", "learn-address", "auth-user-pass-verify", "tls-verify",
    "plugin", "config",
))
_ALLOWED_SCRIPTS = frozenset(("update-resolv-conf", "update-systemd-resolved"))
# dossiers systeme, ecrits par root seulement : un script du meme nom pose
# ailleurs (dossier de l'utilisateur, /tmp) n'est pas accepte
_ALLOWED_DIRS = frozenset(("/etc/openvpn", "/etc/openvpn/scripts", "/usr/share/openvpn",
                           "/usr/lib/openvpn", "/usr/libexec/openvpn"))


def _script_allowed(args):
    """La directive up/down appelle-t-elle le script DNS d'un dossier systeme ?"""
    arg = args.strip()
    if arg[:1] in ("'", '"'):
        arg = arg[1:].split(arg[0], 1)[0]
    words = arg.split()
    if len(words) != 1:
        return False  # arguments ou commande composee : refuse
    path = os.path.normpath(words[0])
    return (os.path.basename(path) in _ALLOWED_SCRIPTS
            and os.path.dirname(path) in _ALLOWED_DIRS)


def sanitize_config(text):
    """Copie du fichier sans les directives qui executent du code, sauf les
    scripts DNS de ProtonVPN. Retourne (texte, directives retirees)."""
    out, removed = [], []
    kept_script = False
    inline = None
    security = None
    for line in text.splitlines():
        stripped = line.strip()
        if inline:
            out.append(line)
            if stripped.lower() == "</%s>" % inline:
                inline = None
            continue
        m = re.match(r"^<([a-z0-9-]+)>$", stripped.lower())
        if m:
            inline = m.group(1)
            out.append(line)
            continue
        if not stripped or stripped[0] in "#;":
            out.append(line)
            continue
        parts = stripped.split(None, 1)
        directive = parts[0].lower().lstrip("-")
        args = parts[1] if len(parts) > 1 else ""
        if directive == "auth-user-pass":
            continue  # remplace par le fichier d'identifiants de l'addon
        if directive == "script-security":
            security = len(out)
            out.append(line)
            continue
        if directive in _SCRIPT_DIRECTIVES:
            if directive in ("up", "down") and _script_allowed(args):
                kept_script = True
                out.append(line)
            else:
                removed.append(stripped)
            continue
        out.append(line)
    if security is not None:
        # niveau 2 au plus (jamais 3 : mots de passe passes aux scripts), et
        # 1 s'il ne reste aucun script autorise
        out[security] = "script-security %d" % (2 if kept_script else 1)
    return "\n".join(out) + "\n", removed


def _prepare_config(src_ovpn):
    src = xbmcvfs.translatePath(src_ovpn)
    try:
        with open(src, "r", encoding="utf-8", errors="ignore") as fh:
            text = fh.read()
    except OSError as exc:
        common.error("Cannot read config %s: %s" % (src, exc))
        return ""
    text, removed = sanitize_config(text)
    for directive in removed:
        common.event("OpenVPN : directive retiree du fichier (execution de commande) : %s"
                     % directive[:80])
    dst = _current_cfg_path()
    try:
        _write_private(dst, text)
    except OSError as exc:
        common.error("Cannot write the OpenVPN run config: %s" % exc)
        return ""
    return dst


# --- Connect / disconnect --------------------------------------------------

def disconnect(quiet=False):
    pid = _read_pid()
    killed = False
    if _pid_alive(pid):
        killed = _signal(pid, signal.SIGTERM)
        for _ in range(10):
            if not _pid_alive(pid):
                break
            time.sleep(0.3)
        if _pid_alive(pid):
            _signal(pid, signal.SIGKILL)
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

    # sudo without NOPASSWD would die silently (no TTY): refuse explicitly
    # instead of letting the user believe the tunnel is up.
    if common.get_bool("use_sudo", False) and not common.sudo_available():
        common.error("use_sudo enabled but passwordless sudo (NOPASSWD) is unavailable")
        common.event("sudo sans mot de passe indisponible - VPN non lance")
        common.set_phase(common.PHASE_ERROR)
        if not quiet:
            common.ok(common.L(32218))
        return False

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

    # Debug only (not INFO), and never log the path of the credentials file.
    log_cmd = list(cmd)
    try:
        log_cmd[log_cmd.index(_auth_path())] = "<auth file>"
    except ValueError:
        pass
    common.debug("Starting OpenVPN: %s" % " ".join(log_cmd))
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
