# -*- coding: utf-8 -*-
#
# ProtonVPN - route directe (hors tunnel) des exceptions
#
# Les addons de la liste des exceptions en « route directe » ont leurs
# serveurs routés par la connexion normale ; le reste de Kodi reste dans le
# tunnel. Les destinations viennent de lib/exceptions.py.
#
# Mécanisme (indépendant de WireGuard ou OpenVPN) :
#   - table de routage dédiée TABLE, avec pour seule route la passerelle
#     de la box (route par défaut de la table main) ;
#   - une règle « ip rule » de priorité PREF par destination, avant les
#     règles de wg-quick (32764/32765) et sans être concernée par les routes
#     0/1 + 128/1 d'OpenVPN (elles sont dans la table main). Si le tunnel
#     monte alors que nos règles existent déjà, wg-quick se place devant
#     (1049/1048) : _reorder() le remet derrière, après chaque connexion et
#     à chaque passage du service.
#
# Addons qui annoncent leurs serveurs (Wtube) : la propriété PROP leur donne
# le numéro de la table ; ils ajoutent eux-mêmes une règle /32 par serveur
# vidéo, dans la même table et à la même priorité (caches Google hébergés
# chez le fournisseur d'accès, hors des plages connues). Ces règles sont
# gardées tant que l'addon est en route directe, purgées au-delà de
# MAX_HOST_RULES, retirées sinon. PROP_ADDON + id est publié pour chaque
# addon en route directe (même numéro de table), pour d'autres addons.

import subprocess

from lib import common
from lib import exceptions

TABLE = 1050
PREF = 1050
PROP = "protonvpn.bypass_table"     # lu par Wtube (inchangé depuis 0.5.13)
PROP_ADDON = "protonvpn.bypass."    # + id de l'addon
PROP_ADDONS = "protonvpn.bypass_addons"
MAX_HOST_RULES = 300                # règles /32 posées par les addons : purge au-delà


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
    """Destinations des règles de la route directe : {'1.2.3.0/24', ...}."""
    rc, out = _ip(["rule", "show"])
    found = set()
    if rc != 0:
        return found
    for line in out.splitlines():
        if not line.startswith("%d:" % PREF):
            continue
        parts = line.split()
        if "to" in parts:
            dest = parts[parts.index("to") + 1]
            found.add(dest if "/" in dest else dest + "/32")
    return found


def _wg_rule(args):
    """Règle posée par wg-quick (« not ... fwmark ... » ou « suppress_prefixlength »)."""
    return "suppress_prefixlength" in args or (args[:1] == ["not"] and "fwmark" in args)


def _reorder():
    """Remet les règles du tunnel WireGuard derrière celles de la route directe.

    wg-quick ajoute ses règles sans priorité : le noyau les place juste avant
    la première règle existante. Si nos règles (1050) existent déjà quand le
    tunnel monte (Kodi relancé, reconnexion), celles de wg-quick prennent
    1049 et 1048, passent devant, et tout repart dans le tunnel. On les
    replace dans l'ordre habituel de wg-quick, juste avant la table main
    (32764, 32765), en ajoutant la copie avant de retirer l'originale : le
    tunnel n'est jamais sans règle. Retourne le nombre de règles déplacées.
    """
    rc, out = _ip(["rule", "show"])
    if rc != 0:
        return 0
    rules = []
    for line in out.splitlines():
        head, sep, spec = line.partition(":")
        if not sep:
            continue
        try:
            rules.append((int(head.strip()), spec.split()))
        except ValueError:
            continue
    moved = 0
    for pref, args in rules:
        if not (0 < pref < PREF and args and _wg_rule(args)):
            continue
        target = 32766 - (PREF - pref)  # 1049 -> 32765, 1048 -> 32764
        placed = (target, args) in rules or \
            _ip(["rule", "add"] + args + ["pref", str(target)])[0] == 0
        if placed and _ip(["rule", "del"] + args + ["pref", str(pref)])[0] == 0:
            moved += 1
    if moved:
        common.log("route directe : %d regle(s) du tunnel replacee(s) apres les notres" % moved)
    return moved


def _gateway():
    """(passerelle, interface) de la route par défaut de la table main."""
    rc, out = _ip(["route", "show", "default", "table", "main"])
    if rc != 0:
        return None
    for line in out.splitlines():
        parts = line.split()
        if "via" in parts and "dev" in parts:
            dev = parts[parts.index("dev") + 1]
            if dev.startswith(("wg", "tun", "proton", "pvpn")):
                continue  # jamais vers le tunnel lui-même
            return parts[parts.index("via") + 1], dev
    return None


def _del(dest):
    return _ip(["rule", "del", "to", dest, "lookup", str(TABLE), "pref", str(PREF)])[0] == 0


def _publish(announce, routed):
    common.set_prop(PROP, str(TABLE) if announce else "")
    old = [a for a in common.get_prop(PROP_ADDONS).split(",") if a]
    for addon_id in old:
        if addon_id not in routed:
            common.set_prop(PROP_ADDON + addon_id, "")
    for addon_id in routed:
        common.set_prop(PROP_ADDON + addon_id, str(TABLE))
    common.set_prop(PROP_ADDONS, ",".join(routed))


def _apply(dest, announce, routed):
    """Pose la table et les règles voulues, retire les autres. True si actif."""
    gw = _gateway()
    if not gw:
        common.log("route directe : passerelle introuvable, exceptions inactives")
        _publish(False, [])
        return False
    rc, out = _ip(["route", "replace", "default", "via", gw[0], "dev", gw[1], "table", str(TABLE)])
    if rc != 0:
        common.log("route directe : table %d impossible (%s)" % (TABLE, out.strip()[:200]))
        _publish(False, [])
        return False
    existing = _rules()
    added = removed = 0
    for cidr in dest:
        if cidr not in existing and \
                _ip(["rule", "add", "to", cidr, "lookup", str(TABLE), "pref", str(PREF)])[0] == 0:
            added += 1
    extra = [d for d in existing if d not in dest]
    # /32 posées par un addon qui annonce ses serveurs : gardées (purge simple
    # au-delà de MAX_HOST_RULES) tant qu'il est en route directe.
    hosts = [d for d in extra if d.endswith("/32")] if announce else []
    if len(hosts) > MAX_HOST_RULES:
        hosts = []
    for d in extra:
        if d not in hosts and _del(d):
            removed += 1
    _reorder()
    was = common.get_prop(PROP_ADDONS)
    _publish(announce, routed)
    if added or removed or was != ",".join(routed):
        names = ", ".join(exceptions.addon_name(a) for a in routed)
        common.event("Route directe : %s (%d regle(s), via %s)" % (names, len(dest), gw[0]))
    return True


def _clear():
    removed = sum(1 for d in _rules() if _del(d))
    _ip(["route", "flush", "table", str(TABLE)])
    if removed or common.get_prop(PROP) or common.get_prop(PROP_ADDONS):
        common.event("Route directe : desactivee")
    _publish(False, [])


def sync(items=None, skip_ips=()):
    """Applique la liste des exceptions (items : liste déjà chargée, sinon
    relue). Appelé régulièrement par le service : suit aussi un changement
    de passerelle de la box."""
    try:
        active = exceptions.active(items)
        dest = exceptions.destinations(active, skip_ips)
        routed = exceptions.route_ids(active)
        announce = any(exceptions.announces(a) for a in routed)
        if routed:
            _apply(dest, announce, routed)
        elif common.get_prop(PROP_ADDONS) or common.get_prop(PROP) or _rules():
            _clear()
    except Exception as exc:  # le service ne doit jamais tomber à cause des exceptions
        common.log("route directe : %s" % exc)
