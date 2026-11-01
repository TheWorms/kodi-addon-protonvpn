# -*- coding: utf-8 -*-
#
# ProtonVPN - YouTube hors du tunnel (routage direct)
#
# YouTube freine fortement les adresses de VPN (HTTP 429, « confirm you're
# not a bot »). Option : le trafic vers les plages d'adresses de Google /
# YouTube sort par la connexion normale, le reste reste dans le tunnel.
#
# Mécanisme (indépendant de WireGuard ou OpenVPN) :
#   - table de routage dédiée TABLE, avec pour seule route la passerelle
#     de la box (route par défaut de la table main) ;
#   - une règle « ip rule » de priorité PREF par plage Google, avant les
#     règles de wg-quick (32764/32765) et sans être concernée par les routes
#     0/1 + 128/1 d'OpenVPN (elles sont dans la table main). Si le tunnel
#     monte alors que nos règles existent déjà, wg-quick se place devant
#     (1049/1048) : _reorder() le remet derrière, après chaque connexion et
#     à chaque passage du service.
#
# Les serveurs vidéo de YouTube peuvent être hébergés chez le fournisseur
# d'accès (caches Google « GGC ») hors de ces plages : l'addon YouTube
# (Wtube) ajoute lui-même une règle /32 pour chaque serveur qu'il utilise,
# dans la même table et à la même priorité, quand la propriété PROP est
# publiée. Tout est retiré quand l'option est désactivée.

import subprocess

from lib import common

TABLE = 1050
PREF = 1050
PROP = "protonvpn.bypass_table"   # propriété Home lue par Wtube
MAX_HOST_RULES = 300              # règles /32 ajoutées par Wtube : purge au-delà

# Plages IPv4 des services Google (dont youtube.com, googlevideo.com,
# ytimg.com) d'après la liste publiée par Google (goog.json), sans les
# plages Google Cloud des clients.
GOOGLE_RANGES = (
    "64.233.160.0/19", "66.102.0.0/20", "66.249.64.0/19", "72.14.192.0/18",
    "74.125.0.0/16", "108.170.192.0/18", "108.177.0.0/17", "142.250.0.0/15",
    "172.217.0.0/16", "172.253.0.0/16", "173.194.0.0/16", "192.178.0.0/15",
    "207.223.160.0/20", "208.65.152.0/22", "208.117.224.0/19", "209.85.128.0/17",
    "216.58.192.0/19", "216.239.32.0/19",
)


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
    """Destinations des règles de cette option : {'1.2.3.0/24', ...}."""
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
    """Remet les règles du tunnel WireGuard derrière celles de l'option.

    wg-quick ajoute ses règles sans priorité : le noyau les place juste avant
    la première règle existante. Si nos règles (1050) existent déjà quand le
    tunnel monte (Kodi relancé, reconnexion), celles de wg-quick prennent
    1049 et 1048, passent devant, et YouTube repart dans le tunnel. On les
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
        common.log("bypass YouTube : %d regle(s) du tunnel replacee(s) apres les notres" % moved)
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
            if dev.startswith(("wg", "tun", "proton")):
                continue  # jamais vers le tunnel lui-même
            return parts[parts.index("via") + 1], dev
    return None


def enable():
    """Pose la table et les règles (idempotent). True si actif."""
    gw = _gateway()
    if not gw:
        common.log("bypass YouTube : passerelle introuvable, option inactive")
        common.set_prop(PROP, "")
        return False
    rc, out = _ip(["route", "replace", "default", "via", gw[0], "dev", gw[1], "table", str(TABLE)])
    if rc != 0:
        common.log("bypass YouTube : table %d impossible (%s)" % (TABLE, out.strip()[:200]))
        common.set_prop(PROP, "")
        return False
    existing = _rules()
    added = 0
    for cidr in GOOGLE_RANGES:
        if cidr not in existing:
            if _ip(["rule", "add", "to", cidr, "lookup", str(TABLE), "pref", str(PREF)])[0] == 0:
                added += 1
    # Les /32 ajoutées par Wtube s'accumulent au fil des vidéos : purge simple.
    hosts = [d for d in existing if d.endswith("/32")]
    if len(hosts) > MAX_HOST_RULES:
        for dest in hosts:
            _ip(["rule", "del", "to", dest, "lookup", str(TABLE), "pref", str(PREF)])
    _reorder()
    if added or common.get_prop(PROP) != str(TABLE):
        common.event("YouTube hors VPN : actif (via %s)" % gw[0])
    common.set_prop(PROP, str(TABLE))
    return True


def disable():
    """Retire toutes les règles et la table de cette option."""
    removed = 0
    for dest in _rules():
        if _ip(["rule", "del", "to", dest, "lookup", str(TABLE), "pref", str(PREF)])[0] == 0:
            removed += 1
    _ip(["route", "flush", "table", str(TABLE)])
    if removed or common.get_prop(PROP):
        common.event("YouTube hors VPN : desactive")
    common.set_prop(PROP, "")


def sync():
    """Applique le réglage ; appelé régulièrement par le service (suit aussi
    un changement de passerelle de la box)."""
    try:
        if common.get_bool("bypass_youtube", False):
            enable()
        elif common.get_prop(PROP) or _rules():
            disable()
    except Exception as exc:  # le service ne doit jamais tomber à cause de l'option
        common.log("bypass YouTube : %s" % exc)
