# -*- coding: utf-8 -*-
#
# ProtonVPN
# Common helpers: settings, paths, logging, notifications, country names.
#
# This file is part of ProtonVPN.
# Licensed under GPL-2.0-or-later.

import os

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")
ADDON_NAME = ADDON.getAddonInfo("name")
ADDON_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo("path"))
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))

# Window properties used to share state between the service and the plugin GUI.
PROP_CONNECTED = "protonvpn.connected"   # "true" / "false"
PROP_SERVER = "protonvpn.server"         # human readable name of current server
PROP_CONFIG = "protonvpn.config"         # absolute path of current .ovpn
PROP_IP = "protonvpn.ip"                 # last known external IP
PROP_PHASE = "protonvpn.phase"           # connection state machine phase

# Connection state machine. A single shared phase keeps the service and the
# plugin GUI in agreement (inspired by the official clients' state model).
PHASE_DISCONNECTED = "disconnected"
PHASE_CONNECTING = "connecting"
PHASE_CONNECTED = "connected"
PHASE_RECONNECTING = "reconnecting"
PHASE_ERROR = "error"


def get_addon():
    # Use the current add-on context; fall back to the cached handle if Kodi is
    # tearing the add-on down (avoids "Unknown addon id" at shutdown).
    try:
        return xbmcaddon.Addon()
    except Exception:
        return ADDON


def ensure_profile():
    if not xbmcvfs.exists(PROFILE):
        xbmcvfs.mkdirs(PROFILE)
    return PROFILE


def profile_file(name):
    ensure_profile()
    return os.path.join(PROFILE, name)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def get_setting(key, default=""):
    try:
        val = get_addon().getSetting(key)
    except Exception:
        return default
    return val if val != "" else default


def get_bool(key, default=False):
    try:
        val = get_addon().getSetting(key)
    except Exception:
        return default
    if val == "":
        return default
    return val.lower() == "true"


def get_int(key, default=0):
    try:
        return int(get_addon().getSetting(key))
    except Exception:
        return default


def set_setting(key, value):
    try:
        get_addon().setSetting(key, str(value))
    except Exception:
        pass


def open_settings():
    get_addon().openSettings()


# ---------------------------------------------------------------------------
# Logging / notifications
# ---------------------------------------------------------------------------

def _log(level, msg):
    xbmc.log("[%s] %s" % (ADDON_ID, msg), level)


def log(msg):
    _log(xbmc.LOGINFO, msg)


def debug(msg):
    _log(xbmc.LOGDEBUG, msg)


def error(msg):
    _log(xbmc.LOGERROR, msg)


def L(string_id):
    # Localised string lookup.
    return get_addon().getLocalizedString(string_id)


def notify(message, heading=None, icon=None, time=4000):
    if heading is None:
        heading = ADDON_NAME
    if icon is None:
        icon = os.path.join(ADDON_PATH, "resources", "icon.png")
    xbmcgui.Dialog().notification(heading, message, icon, time)


def ok(message, heading=None):
    if heading is None:
        heading = ADDON_NAME
    xbmcgui.Dialog().ok(heading, message)


def yesno(message, heading=None):
    if heading is None:
        heading = ADDON_NAME
    return xbmcgui.Dialog().yesno(heading, message)


# ---------------------------------------------------------------------------
# State (shared via window properties on the Home window)
# ---------------------------------------------------------------------------

_HOME = xbmcgui.Window(10000)


def set_state(connected, server="", config="", ip=""):
    _HOME.setProperty(PROP_CONNECTED, "true" if connected else "false")
    _HOME.setProperty(PROP_SERVER, server)
    _HOME.setProperty(PROP_CONFIG, config)
    if ip:
        _HOME.setProperty(PROP_IP, ip)
    if not connected:
        _HOME.setProperty(PROP_SERVER, "")
        _HOME.setProperty(PROP_CONFIG, "")


def set_phase(phase):
    _HOME.setProperty(PROP_PHASE, phase)


def get_phase():
    return _HOME.getProperty(PROP_PHASE) or PHASE_DISCONNECTED


def set_prop(key, value):
    _HOME.setProperty(key, value or "")


def get_prop(key):
    return _HOME.getProperty(key)


# Skin header indicator + connection start time (shared via Home window so a
# skin can read Window(home).Property(protonvpn.header)).
PROP_HEADER = "protonvpn.header"
PROP_SINCE = "protonvpn.since"


def set_header(text):
    _HOME.setProperty(PROP_HEADER, text or "")


def set_since(epoch):
    _HOME.setProperty(PROP_SINCE, str(int(epoch)) if epoch else "")


def get_since():
    try:
        return int(_HOME.getProperty(PROP_SINCE) or "0")
    except ValueError:
        return 0


# ---------------------------------------------------------------------------
# Event log (for the Stats / Journaux view)
# ---------------------------------------------------------------------------

EVENTS_FILE = "protonvpn.events.log"
_EVENTS_MAX = 200


def event(msg):
    import time
    line = "%s  %s" % (time.strftime("%H:%M:%S"), msg)
    log(msg)
    try:
        path = profile_file(EVENTS_FILE)
        lines = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                lines = fh.read().splitlines()
        lines.append(line)
        lines = lines[-_EVENTS_MAX:]
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    except OSError:
        pass


def read_events(limit=80):
    try:
        path = profile_file(EVENTS_FILE)
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            lines = fh.read().splitlines()
        return lines[-limit:]
    except OSError:
        return []


def get_state():
    return {
        "connected": _HOME.getProperty(PROP_CONNECTED) == "true",
        "server": _HOME.getProperty(PROP_SERVER),
        "config": _HOME.getProperty(PROP_CONFIG),
        "ip": _HOME.getProperty(PROP_IP),
    }


# ---------------------------------------------------------------------------
# Country code -> name (ISO 3166-1 alpha-2). Used to group ProtonVPN configs.
# Display name is localised lightly: French names for a few common ones,
# English fallback otherwise. ProtonVPN also uses "UK" for the United Kingdom.
# ---------------------------------------------------------------------------

COUNTRY_NAMES = {
    "AR": "Argentina", "AT": "Austria", "AU": "Australia", "BE": "Belgium",
    "BG": "Bulgaria", "BR": "Brazil", "CA": "Canada", "CH": "Switzerland",
    "CL": "Chile", "CO": "Colombia", "CR": "Costa Rica", "CY": "Cyprus",
    "CZ": "Czechia", "DE": "Germany", "DK": "Denmark", "EE": "Estonia",
    "EG": "Egypt", "ES": "Spain", "FI": "Finland", "FR": "France",
    "GB": "United Kingdom", "UK": "United Kingdom", "GE": "Georgia",
    "GR": "Greece", "HK": "Hong Kong", "HR": "Croatia", "HU": "Hungary",
    "ID": "Indonesia", "IE": "Ireland", "IL": "Israel", "IN": "India",
    "IS": "Iceland", "IT": "Italy", "JP": "Japan", "KR": "South Korea",
    "LT": "Lithuania", "LU": "Luxembourg", "LV": "Latvia", "MD": "Moldova",
    "MX": "Mexico", "MY": "Malaysia", "NL": "Netherlands", "NO": "Norway",
    "NZ": "New Zealand", "PH": "Philippines", "PL": "Poland", "PT": "Portugal",
    "RO": "Romania", "RS": "Serbia", "SE": "Sweden", "SG": "Singapore",
    "SI": "Slovenia", "SK": "Slovakia", "TH": "Thailand", "TR": "Turkey",
    "TW": "Taiwan", "UA": "Ukraine", "US": "United States", "VN": "Vietnam",
    "ZA": "South Africa",
}

# A small French override set (Thib runs a French locale). Falls back to the
# English name above when a code is not listed here.
COUNTRY_NAMES_FR = {
    "AT": "Autriche", "AU": "Australie", "BE": "Belgique", "BR": "Bresil",
    "CA": "Canada", "CH": "Suisse", "CZ": "Tchequie", "DE": "Allemagne",
    "DK": "Danemark", "ES": "Espagne", "FI": "Finlande", "FR": "France",
    "GB": "Royaume-Uni", "UK": "Royaume-Uni", "GR": "Grece", "HU": "Hongrie",
    "IE": "Irlande", "IS": "Islande", "IT": "Italie", "JP": "Japon",
    "NL": "Pays-Bas", "NO": "Norvege", "NZ": "Nouvelle-Zelande",
    "PL": "Pologne", "PT": "Portugal", "RO": "Roumanie", "SE": "Suede",
    "SG": "Singapour", "US": "Etats-Unis", "ZA": "Afrique du Sud",
}


def country_name(code):
    code = (code or "").upper()
    lang = xbmc.getLanguage(xbmc.ISO_639_1) if hasattr(xbmc, "ISO_639_1") else ""
    if lang == "fr" and code in COUNTRY_NAMES_FR:
        return COUNTRY_NAMES_FR[code]
    return COUNTRY_NAMES.get(code, code)
