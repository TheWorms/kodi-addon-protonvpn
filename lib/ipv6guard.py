# -*- coding: utf-8 -*-
#
# ProtonVPN - protection IPv6
#
# Les tunnels montes par l'addon ne transportent que l'IPv4 : l'IPv6 est
# retiree des configs WireGuard (ip6tables absent des kernels embarques) et
# les fichiers OpenVPN de Proton n'en routent pas. Sur une machine qui a de
# l'IPv6, ce trafic partait donc en direct, hors du VPN, avec l'adresse
# reelle, alors que l'addon affichait « connecte ».
#
# Tant que le tunnel est monte, une route « unreachable 2000::/3 » (toute
# l'IPv6 publique) est posee : les applications retombent aussitot sur
# l'IPv4, qui passe par le tunnel. Le reseau local en IPv6 n'est pas touche
# (ses prefixes sont plus precis, fe80::/10 est hors de 2000::/3). La route
# est retiree a la deconnexion et ne survit pas a un redemarrage.
#
# Sans effet sur une machine qui n'a pas de route IPv6 par defaut.

import os
import shutil
import subprocess

import xbmcvfs

from lib import common

PREFIX = "2000::/3"
# Temoin : la route a ete posee par l'addon. On ne retire jamais une route
# « unreachable 2000::/3 » que quelqu'un d'autre aurait mise.
MARKER = "ipv6guard.on"
PROP_WARNED = "protonvpn.ipv6warned"

_IP_CANDIDATES = ("/usr/sbin/ip", "/sbin/ip", "/usr/bin/ip", "/bin/ip",
                  "/opt/sbin/ip", "/opt/bin/ip",
                  "/storage/.opt/sbin/ip", "/storage/.opt/bin/ip")


def _ip_path():
    for candidate in _IP_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    return shutil.which("ip") or ""


def _run(args, privileged=False):
    ip = _ip_path()
    if not ip:
        return 1, "commande ip introuvable"
    cmd = [ip] + args
    if privileged and common.get_bool("use_sudo", False):
        cmd = ["sudo", "-n"] + cmd
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=15)
        return proc.returncode, (proc.stdout or b"").decode("utf-8", "ignore")
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)


def _proc_default_route():
    """Route IPv6 par defaut lue dans /proc, sans la commande ip (fichier
    absent quand le kernel n'a pas d'IPv6)."""
    try:
        with open("/proc/net/ipv6_route", "r") as fh:
            for line in fh:
                f = line.split()
                # destination ::/0, hors loopback, hors route de rejet (0x200)
                if (len(f) >= 10 and f[0] == "0" * 32 and f[1] == "00"
                        and f[9] != "lo" and not int(f[8], 16) & 0x200):
                    return True
    except (OSError, ValueError):
        pass
    return False


def _state():
    """(route IPv6 par defaut presente, blocage present).
    Sans commande ip utilisable, la route par defaut est cherchee dans
    /proc : le blocage sera impossible, mais l'utilisateur sera prevenu."""
    rc, out = _run(["-6", "route", "show"])
    if rc != 0:
        return _proc_default_route(), False
    default = blocked = False
    for line in out.splitlines():
        words = line.split()
        if not words:
            continue
        if words[0] == "default":
            default = True
        elif words[0] == "unreachable" and words[1:2] == [PREFIX]:
            blocked = True
    return default, blocked


def _ipv6_endpoint(path):
    """La config joint-elle le serveur VPN en IPv6 ? Bloquer l'IPv6 couperait
    alors le tunnel lui-meme (les fichiers ProtonVPN utilisent des adresses
    IPv4, c'est un garde-fou pour les configs d'une autre origine)."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            text = fh.read()
    except OSError:
        return False
    for line in text.splitlines():
        low = line.strip().lower()
        if low.startswith("endpoint"):
            value = low.split("=", 1)[-1].strip()
            if value.startswith("[") or value.count(":") > 1:
                return True
        elif low.startswith("remote "):
            parts = low.split()
            if len(parts) > 1 and ":" in parts[1]:
                return True
        elif low.startswith("proto "):
            parts = low.split()
            if len(parts) > 1 and parts[1].endswith("6"):
                return True
    return False


def _marker():
    return common.profile_file(MARKER)


def _warn_once(reason):
    """Une notification par connexion, pas une a chaque controle du service."""
    if common.get_prop(PROP_WARNED) == "1":
        return
    common.set_prop(PROP_WARNED, "1")
    common.event("IPv6 active et NON bloquee, elle passe hors du VPN : %s" % reason)
    common.notify(common.L(32261), time=8000)


def enable(config_path=""):
    """A appeler quand le tunnel est monte (sans risque de le rappeler).
    Retourne True si l'IPv6 ne peut pas sortir hors du tunnel."""
    if not common.get_bool("block_ipv6", True):
        disable()
        return False
    default, blocked = _state()
    if blocked:
        return True
    if not default:
        return True   # pas d'IPv6 routee sur cette machine : rien a proteger
    path = config_path or xbmcvfs.translatePath(common.get_setting("last_config", ""))
    if path and _ipv6_endpoint(path):
        _warn_once("le serveur VPN est joint en IPv6, blocage impossible")
        return False
    _rc, out = _run(["-6", "route", "add", "unreachable", PREFIX, "metric", "1"],
                    privileged=True)
    if _state()[1]:
        try:
            with open(_marker(), "w", encoding="utf-8") as fh:
                fh.write(PREFIX + "\n")
        except OSError:
            pass
        common.set_prop(PROP_WARNED, "")
        common.event("IPv6 bloquee pendant la connexion (elle ne passe pas par le tunnel)")
        return True
    _warn_once((out or "").strip()[:120] or "route refusee")
    return False


def disable():
    """A appeler quand le tunnel est demonte. Ne retire que la route posee
    par l'addon."""
    common.set_prop(PROP_WARNED, "")
    marker = _marker()
    if not os.path.exists(marker):
        return
    if _state()[1]:
        _run(["-6", "route", "del", "unreachable", PREFIX], privileged=True)
        if _state()[1]:
            common.event("IPv6 : route de blocage non retiree "
                         "(elle disparaitra au redemarrage)")
            return
        common.event("IPv6 retablie")
    try:
        os.remove(marker)
    except OSError:
        pass


def sync(running):
    """Aligne le blocage sur l'etat du tunnel. Appele par le service au
    demarrage puis a chaque controle : rattrape un Kodi arrete sans
    deconnexion, un reglage change en cours de route, une IPv6 arrivee
    apres la connexion."""
    try:
        if running:
            enable()
        else:
            disable()
    except Exception as exc:   # jamais bloquant pour le service
        common.log("ipv6guard : %s" % exc)
