# -*- coding: utf-8 -*-
#
# ProtonVPN - exceptions par addon (trafic hors VPN)
#
# La liste des addons qui sortent sans VPN est rangée dans le profil de
# l'addon (exceptions.json), pas dans les réglages : le dialogue des réglages
# de Kodi réécrit ses valeurs à la fermeture et écraserait une liste modifiée
# pendant qu'il est ouvert.
#
# Deux méthodes par addon :
#   - ROUTE (route directe) : seules les adresses des serveurs de l'addon
#     sortent par la connexion normale (table de routage 1050, voir bypass.py),
#     le reste de Kodi reste dans le tunnel. Les adresses viennent :
#       * d'un profil intégré (plages de Google pour les addons YouTube) ;
#       * de l'addon lui-même s'il les annonce (Wtube : propriété
#         protonvpn.bypass_table, voir bypass.py) ;
#       * de l'apprentissage : le serveur d'une vidéo lue est noté et passe
#         en direct à la fin de la lecture (le basculer pendant la lecture
#         couperait la connexion en cours) ;
#       * de serveurs ajoutés à la main (nom, adresse IP ou plage).
#   - PAUSE (pause du VPN) : le tunnel s'arrête quand l'utilisateur ouvre
#     l'addon ou lit une de ses vidéos, et revient quelques secondes après.
#
# Kodi fait tourner tous ses addons dans un seul processus : le système ne
# sait pas quel addon envoie quel paquet. D'où ce tri par destination ou par
# moment, plutôt qu'un vrai tri par addon.

import ipaddress
import json
import os
import socket
import time
from urllib.parse import urlsplit

import xbmc

from lib import common

FILE = "exceptions.json"
ROUTE = "route"
PAUSE = "pause"
METHODS = (ROUTE, PAUSE)

PROP_REV = "protonvpn.exceptions_rev"        # change à chaque modification de la liste
PROP_PAUSED = "protonvpn.paused"             # id de l'addon qui a mis le tunnel en pause
PROP_PAUSED_CFG = "protonvpn.paused_config"  # configuration à relancer après la pause

MAX_HOSTS = 50   # serveurs appris par addon (les plus anciens sont oubliés)
MAX_IPS = 16     # adresses gardées par serveur (rotation des CDN)

# Plages IPv4 des services Google (youtube.com, googlevideo.com, ytimg.com),
# d'après la liste publiée par Google (goog.json), sans Google Cloud.
GOOGLE_RANGES = (
    "64.233.160.0/19", "66.102.0.0/20", "66.249.64.0/19", "72.14.192.0/18",
    "74.125.0.0/16", "108.170.192.0/18", "108.177.0.0/17", "142.250.0.0/15",
    "172.217.0.0/16", "172.253.0.0/16", "173.194.0.0/16", "192.178.0.0/15",
    "207.223.160.0/20", "208.65.152.0/22", "208.117.224.0/19", "209.85.128.0/17",
    "216.58.192.0/19", "216.239.32.0/19",
)
PROFILES = {"google": GOOGLE_RANGES}
ADDON_PROFILES = {
    "plugin.video.wtube": "google",
    "plugin.video.youtube": "google",
}
# Addons qui annoncent eux-mêmes leurs serveurs avant de s'y connecter.
ANNOUNCERS = ("plugin.video.wtube",)

# Ancienne option « YouTube hors du VPN » (0.5.13 à 0.5.17) : reprise une fois.
LEGACY_SETTING = "bypass_youtube"
LEGACY_ADDONS = ("plugin.video.wtube", "plugin.video.youtube")


# --- stockage -----------------------------------------------------------------

def _path():
    return common.profile_file(FILE)


def new_entry(addon_id, method=ROUTE):
    return {"id": addon_id, "method": method, "learn": True, "learned": [], "manual": []}


def _hosts(raw):
    out = []
    for h in raw if isinstance(raw, list) else []:
        if isinstance(h, dict) and isinstance(h.get("host"), str) and h["host"]:
            ips = [i for i in h.get("ips", []) if isinstance(i, str)][:MAX_IPS]
            out.append({"host": h["host"], "ips": ips, "ts": int(h.get("ts") or 0)})
    return out


def _clean(raw):
    if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not raw["id"]:
        return None
    method = raw.get("method") if raw.get("method") in METHODS else ROUTE
    return {
        "id": raw["id"],
        "method": method,
        "learn": raw.get("learn", True) is not False,
        "learned": _hosts(raw.get("learned"))[-MAX_HOSTS:],
        "manual": _hosts(raw.get("manual")),
    }


def load():
    """Liste ordonnée des exceptions. Au tout premier appel, reprend
    l'ancienne option « YouTube hors du VPN » puis crée le fichier."""
    path = _path()
    if not os.path.exists(path):
        items = _migrate()
        save(items)
        return items
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        common.log("exceptions : fichier illisible (%s), liste vide" % exc)
        return []
    items, seen = [], set()
    for raw in data.get("addons", []) if isinstance(data, dict) else []:
        ex = _clean(raw)
        if ex and ex["id"] not in seen:
            seen.add(ex["id"])
            items.append(ex)
    return items


def save(items, bump=True):
    path = _path()
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "addons": items}, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except OSError as exc:
        common.log("exceptions : écriture impossible (%s)" % exc)
        return False
    if bump:
        common.set_prop(PROP_REV, "%.3f" % time.time())
    return True


def _migrate():
    try:
        legacy = common.get_bool(LEGACY_SETTING, False)
    except Exception:
        legacy = False
    if not legacy:
        return []
    ids = [a for a in LEGACY_ADDONS if has_addon(a)] or [LEGACY_ADDONS[0]]
    common.set_setting(LEGACY_SETTING, "false")
    common.event("Exceptions : %s ajouté en route directe (ancienne option "
                 "YouTube hors du VPN)" % ", ".join(ids))
    return [new_entry(a) for a in ids]


def by_id(items, addon_id):
    for ex in items:
        if ex["id"] == addon_id:
            return ex
    return None


def enabled():
    return common.get_bool("exceptions_enabled", True)


def active(items=None):
    """Exceptions en vigueur : la liste, ou rien si l'option est coupée."""
    if not enabled():
        return []
    return load() if items is None else items


def rev():
    return common.get_prop(PROP_REV)


# --- addons -------------------------------------------------------------------

def has_addon(addon_id):
    try:
        return bool(xbmc.getCondVisibility("System.HasAddon(%s)" % addon_id))
    except Exception:
        return False


def addon_name(addon_id):
    try:
        import xbmcaddon
        return xbmcaddon.Addon(addon_id).getAddonInfo("name") or addon_id
    except Exception:
        return addon_id


def profile_ranges(addon_id):
    return PROFILES.get(ADDON_PROFILES.get(addon_id, ""), ())


def announces(addon_id):
    return addon_id in ANNOUNCERS


# --- adresses -----------------------------------------------------------------

def _public(ip):
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr.version == 4 and addr.is_global


def parse_target(text):
    """Saisie manuelle -> ('cidr', '203.0.113.0/24') ou ('host', 'nom') ou
    (None, ''). Les noms ne prennent pas de joker : une route vise des
    adresses, pas un domaine entier."""
    text = (text or "").strip().lower()
    for prefix in ("https://", "http://"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    if "/" in text and not _looks_cidr(text):
        text = text.split("/", 1)[0]          # chemin d'une adresse web
    if text.count(":") == 1:
        text = text.split(":", 1)[0]          # port
    if not text:
        return None, ""
    try:
        net = ipaddress.ip_network(text, strict=False)
        return ("cidr", str(net)) if net.version == 4 else (None, "")
    except ValueError:
        pass
    labels = text.split(".")
    if len(labels) >= 2 and not labels[-1].isdigit() and all(
            l and len(l) <= 63 and l.replace("-", "").isalnum() for l in labels):
        return "host", text
    return None, ""


def _looks_cidr(text):
    head, _, tail = text.partition("/")
    return tail.isdigit() and head.replace(".", "").isdigit()


def resolve(host):
    """Adresses IPv4 publiques d'un nom (liste triée, vide si introuvable)."""
    kind, value = parse_target(host)
    if kind == "cidr":
        return [value[:-3]] if value.endswith("/32") else [value]
    if kind != "host":
        return []
    try:
        infos = socket.getaddrinfo(value, None, socket.AF_INET, socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        return []
    return sorted({i[4][0] for i in infos if _public(i[4][0])})


def merge_ips(new, old):
    """Nouvelles adresses d'abord, anciennes ensuite (les CDN tournent)."""
    out = list(new)
    out += [i for i in old if i not in out]
    return out[:MAX_IPS]


def uncovered(ex, ips):
    """Adresses (parmi ips) qui ne sortent pas encore en direct pour cet addon."""
    nets = [ipaddress.ip_network(c) for c in profile_ranges(ex["id"])]
    known = set()
    for h in ex["learned"] + ex["manual"]:
        for i in h["ips"]:
            if "/" in i:
                nets.append(ipaddress.ip_network(i))
            else:
                known.add(i)
    out = []
    for ip in ips:
        if ip in known:
            continue
        addr = ipaddress.ip_address(ip)
        if not any(addr in n for n in nets):
            out.append(ip)
    return out


def destinations(items, skip_ips=()):
    """{'1.2.3.0/24': addon_id} pour les exceptions en route directe.
    skip_ips : adresses apprises pendant la lecture en cours, mises en
    service seulement à la fin de celle-ci."""
    out = {}
    for ex in items:
        if ex["method"] != ROUTE:
            continue
        for cidr in profile_ranges(ex["id"]):
            out.setdefault(cidr, ex["id"])
        for h in ex["learned"] + ex["manual"]:
            for ip in h["ips"]:
                if ip not in skip_ips:
                    out.setdefault(ip if "/" in ip else ip + "/32", ex["id"])
    return out


def route_ids(items):
    return [ex["id"] for ex in items if ex["method"] == ROUTE]


def pause_ids(items):
    return [ex["id"] for ex in items if ex["method"] == PAUSE]


# --- lecture en cours -----------------------------------------------------------

def _plugin_of(path):
    if path.startswith("plugin://"):
        return path[len("plugin://"):].split("/", 1)[0].split("?", 1)[0]
    return ""


def browsing():
    """Addon dont l'utilisateur parcourt les menus ('' sinon)."""
    try:
        name = xbmc.getInfoLabel("Container.PluginName")
        if name:
            return name
        return _plugin_of(xbmc.getInfoLabel("Container.FolderPath"))
    except Exception:
        return ""


def playing():
    """(addon, url) de la lecture en cours : addon '' si inconnu, url '' si
    le flux n'est pas une adresse http(s) publique."""
    try:
        if not xbmc.getCondVisibility("Player.HasMedia"):
            return None, ""
    except Exception:
        return None, ""
    paths = []
    try:
        paths.append(xbmc.Player().getPlayingFile() or "")
    except Exception:
        pass
    for label in ("Player.Filenameandpath", "Player.FolderPath"):
        try:
            paths.append(xbmc.getInfoLabel(label) or "")
        except Exception:
            pass
    addon, url = "", ""
    for p in paths:
        addon = addon or _plugin_of(p)
        if not url and p.startswith(("http://", "https://")):
            url = p
    return addon, url


def stream_host(url):
    """Serveur d'une adresse de flux ('' pour un relais local, la box, un NAS)."""
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""
    if not host or host == "localhost":
        return ""
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return host          # un nom : il sera résolu
    return host if _public(host) else ""


def learn(items, addon_id, host):
    """Note le serveur d'une lecture. Retourne les adresses nouvelles (à
    mettre en service à la fin de la lecture), [] si rien à apprendre."""
    ex = by_id(items, addon_id)
    if not ex or ex["method"] != ROUTE or not ex["learn"] or announces(addon_id) or not host:
        return []
    ips = resolve(host)
    new = uncovered(ex, ips) if ips else []
    if not new:
        return []
    for h in ex["learned"]:
        if h["host"] == host:
            h["ips"] = merge_ips(ips, h["ips"])
            h["ts"] = int(time.time())
            return new
    ex["learned"].append({"host": host, "ips": ips, "ts": int(time.time())})
    del ex["learned"][:-MAX_HOSTS]
    return new


def refresh(items):
    """Résout de nouveau les serveurs connus (rotation des CDN). Retourne
    {(addon_id, host): ips} pour ceux qui ont changé ; ne modifie rien."""
    changes = {}
    for ex in items:
        if ex["method"] != ROUTE:
            continue
        for h in ex["learned"] + ex["manual"]:
            if parse_target(h["host"])[0] != "host":
                continue
            ips = resolve(h["host"])
            if ips and merge_ips(ips, h["ips"]) != h["ips"]:
                changes[(ex["id"], h["host"])] = ips
    return changes


def apply_refresh(changes):
    """Reporte refresh() sur la liste relue à l'instant (une modification
    faite entre-temps dans les réglages n'est pas écrasée)."""
    if not changes:
        return False
    items = load()
    done = False
    for (addon_id, host), ips in changes.items():
        ex = by_id(items, addon_id)
        for h in (ex["learned"] + ex["manual"]) if ex else []:
            if h["host"] == host:
                h["ips"] = merge_ips(ips, h["ips"])
                done = True
    if done:
        save(items)
    return done
