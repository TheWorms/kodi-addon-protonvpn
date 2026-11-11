# -*- coding: utf-8 -*-
#
# ProtonVPN - nettoyage de l'ancienne route directe
#
# Les versions 0.5.13 à 0.6.3 sortaient certains serveurs du tunnel par une
# table de routage dédiée (TABLE) et des règles « ip rule » de priorité PREF.
# Cette méthode a été retirée au profit de la pause du VPN : au démarrage du
# service, tout ce qui en reste est effacé (règles, table, propriétés lues
# par Wtube).

import subprocess

from lib import common

TABLE = 1050
PREF = 1050
PROPS = ("protonvpn.bypass_table", "protonvpn.bypass_addons")


def _ip(args):
    cmd = ["ip", "-4"] + list(args)
    if common.get_bool("use_sudo", False):
        cmd = ["sudo", "-n"] + cmd
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
        return p.returncode, (p.stdout or b"").decode("utf-8", "ignore")
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)


def _rules():
    rc, out = _ip(["rule", "show"])
    found = set()
    for line in out.splitlines() if rc == 0 else ():
        parts = line.split()
        if parts and parts[0] == "%d:" % PREF and "to" in parts:
            found.add(parts[parts.index("to") + 1])
    return found


def cleanup():
    """Efface la route directe des anciennes versions. Ne lève jamais."""
    try:
        removed = 0
        for dest in _rules():
            if _ip(["rule", "del", "to", dest, "lookup", str(TABLE), "pref", str(PREF)])[0] == 0:
                removed += 1
        _ip(["route", "flush", "table", str(TABLE)])
        for prop in PROPS:
            common.set_prop(prop, "")
        if removed:
            common.event("Ancienne route directe retiree (%d regle(s))" % removed)
    except Exception as exc:
        common.log("nettoyage route directe : %s" % exc)
