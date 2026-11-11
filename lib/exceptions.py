# -*- coding: utf-8 -*-
#
# ProtonVPN - exceptions par addon : pause du VPN
#
# Le tunnel s'arrête quand l'utilisateur ouvre un addon de la liste ou lit
# une de ses vidéos, et revient quelques secondes après en être sorti
# (délai réglable). Toute la box est sans VPN pendant ce temps : Kodi fait
# tourner tous ses addons dans un seul processus, le système ne sait pas
# quel addon envoie quel paquet.
#
# La liste est rangée dans le profil de l'addon (exceptions.json), pas dans
# les réglages : le dialogue des réglages de Kodi réécrit ses valeurs à la
# fermeture et écraserait une liste modifiée pendant qu'il est ouvert.

import json
import os
import time

import xbmc

from lib import common

FILE = "exceptions.json"

PROP_REV = "protonvpn.exceptions_rev"        # change à chaque modification de la liste
PROP_PAUSED = "protonvpn.paused"             # id de l'addon qui a mis le tunnel en pause
PROP_PAUSED_CFG = "protonvpn.paused_config"  # configuration à relancer après la pause

# Ancienne option « YouTube hors du VPN » (0.5.13 à 0.5.17) : reprise une fois.
LEGACY_SETTING = "bypass_youtube"
LEGACY_ADDONS = ("plugin.video.wtube", "plugin.video.youtube")


# --- stockage -----------------------------------------------------------------

def _path():
    return common.profile_file(FILE)


def new_entry(addon_id):
    return {"id": addon_id}


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
        # Les champs des versions 0.6.0 à 0.6.3 (méthode, serveurs) sont ignorés.
        aid = raw.get("id") if isinstance(raw, dict) else None
        if isinstance(aid, str) and aid and aid not in seen:
            seen.add(aid)
            items.append(new_entry(aid))
    return items


def save(items, bump=True):
    path = _path()
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"version": 2, "addons": items}, fh, ensure_ascii=False, indent=1)
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
    common.event("Exceptions : %s ajouté (ancienne option YouTube hors du VPN)" % ", ".join(ids))
    return [new_entry(a) for a in ids]


def enabled():
    return common.get_bool("exceptions_enabled", True)


def active_ids(items=None):
    """Ids des addons en exception, ou rien si l'option est coupée."""
    if not enabled():
        return []
    return [ex["id"] for ex in (load() if items is None else items)]


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


# --- ce que fait l'utilisateur ---------------------------------------------------

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
    """Addon de la lecture en cours : None sans lecture, '' si inconnu."""
    try:
        if not xbmc.getCondVisibility("Player.HasMedia"):
            return None
    except Exception:
        return None
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
    for p in paths:
        addon = _plugin_of(p)
        if addon:
            return addon
    return ""
