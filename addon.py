# -*- coding: utf-8 -*-
#
# ProtonVPN - plugin GUI
# The active protocol (Settings -> Accueil -> default protocol) decides which
# servers are shown; the other backend is hidden. Import, connect, test,
# delete, stats and logs are all reachable from the launched add-on.

import sys
import os
from urllib.parse import urlencode, parse_qsl

import xbmc
import xbmcgui
import xbmcplugin

from lib import common
from lib import configs
from lib import vpn
from lib import stats
from lib import statswidget

HANDLE = int(sys.argv[1])
BASE = sys.argv[0]
ICON = os.path.join(common.ADDON_PATH, "resources", "icon.png")



def build_url(**kwargs):
    return BASE + "?" + urlencode(kwargs)


def add_item(label, url, folder=True, icon=None, info=None, context=None):
    li = xbmcgui.ListItem(label=label)
    li.setArt({"icon": icon or ICON, "thumb": icon or ICON})
    if info:
        li.setInfo("video", {"plot": info})
    if context:
        li.addContextMenuItems(context)
    xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=folder)


def _active_backend():
    return common.get_setting("default_protocol", "wireguard")


def _backend_name(backend):
    return "WireGuard" if backend == "wireguard" else "OpenVPN"


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------

def view_root():
    state = common.get_state()
    backend = _active_backend()
    total = len(configs.scan())

    # Status header
    if state["connected"]:
        ip = state.get("ip") or ""
        head = "[COLOR lime]%s[/COLOR] %s" % (common.L(32060), state["server"])
        if ip:
            head += "  (%s)" % ip
        add_item(head, build_url(action="status"))
    elif common.get_phase() == common.PHASE_RECONNECTING:
        add_item("[COLOR yellow]%s[/COLOR]" % common.L(32078), build_url(action="status"))
    else:
        add_item("[COLOR grey]%s[/COLOR]" % common.L(32061), build_url(action="status"))

    # Servers (all configs; the inactive backend is greyed out, not hidden)
    add_item("%s  [COLOR grey](%s, %d)[/COLOR]" % (common.L(32167), _backend_name(backend), total),
             build_url(action="servers"))
    add_item(common.L(32063), build_url(action="quick"))      # Quick connect

    # Disconnect button: always present; red when connected, grey otherwise.
    if state["connected"] or common.get_phase() == common.PHASE_RECONNECTING:
        add_item("[COLOR red]%s[/COLOR]" % common.L(32062), build_url(action="disconnect"))
    else:
        add_item("[COLOR grey]%s[/COLOR]" % common.L(32062), build_url(action="disconnect"))

    add_item(common.L(32130), build_url(action="test"))       # Test
    add_item(common.L(32145), build_url(action="import"))     # Import
    add_item(common.L(32151), build_url(action="widget"))     # Stats (live)
    add_item(common.L(32152), build_url(action="logs"))       # Logs
    # Browsable widget folders (so the skin widget picker -> Add-ons -> Programs
    # -> ProtonVPN can pick them as home widgets).
    add_item("%s \u00b7 %s" % (common.L(32186), common.L(32151)), build_url(action="wstats"))
    add_item("%s \u00b7 %s" % (common.L(32186), common.L(32152)), build_url(action="wlogs"))
    add_item(common.L(32007), build_url(action="settings"))   # Settings

    xbmcplugin.setContent(HANDLE, "files")
    xbmcplugin.endOfDirectory(HANDLE)


# ---------------------------------------------------------------------------
# Servers (active protocol only)
# ---------------------------------------------------------------------------

def view_servers(backend=None):
    active = _active_backend()
    state = common.get_state()
    items = configs.scan()  # all backends; the inactive one is greyed out
    if not items:
        add_item("[COLOR orange]%s[/COLOR]" % common.L(32075), build_url(action="import"))
        add_item(common.L(32145), build_url(action="import"))
        xbmcplugin.endOfDirectory(HANDLE)
        return
    for cfg in items:
        tag = "WG" if cfg["backend"] == "wireguard" else cfg["proto"].upper()
        flag = os.path.join(common.ADDON_PATH, "resources", "flags",
                            "%s.png" % cfg["country"].lower())
        if not os.path.exists(flag):
            flag = ICON
        connected_here = state["connected"] and state.get("config") == cfg["path"]
        is_active = cfg["backend"] == active

        if connected_here:
            # Currently connected: this row disconnects.
            label = "[COLOR lime]\u25cf[/COLOR] %s  [COLOR grey](%s)[/COLOR]  \u2014 [COLOR red]%s[/COLOR]" % (
                cfg["label"], tag, common.L(32062))
            url = build_url(action="disconnect")
        elif is_active:
            label = "%s  [COLOR grey](%s)[/COLOR]" % (cfg["label"], tag)
            url = build_url(action="connect", id=cfg["id"])
        else:
            # Inactive backend: greyed out, not connectable from here.
            label = "[COLOR 66FFFFFF]%s  (%s)[/COLOR]" % (cfg["label"], tag)
            url = build_url(action="inactive", backend=cfg["backend"])

        context = [(common.L(32168),
                    "RunPlugin(%s)" % build_url(action="delete", id=cfg["id"]))]
        add_item(label, url, icon=flag, context=context,
                 info="%s  %s:%s" % (cfg["country_name"], cfg["remote"], cfg["port"]))
    xbmcplugin.setContent(HANDLE, "files")
    xbmcplugin.endOfDirectory(HANDLE)


def do_inactive(backend):
    common.notify(common.L(32180) % _backend_name(backend))
    if HANDLE >= 0:
        view_servers()


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def _root_or_pass():
    if HANDLE >= 0:
        view_root()


def do_connect(config_id):
    cfg = configs.find_by_id(config_id)
    if not cfg:
        common.notify(common.L(32076))
        _root_or_pass()
        return
    dialog = xbmcgui.DialogProgressBG()
    dialog.create(common.ADDON_NAME, common.L(32077) % cfg["label"])
    try:
        ok = vpn.connect(cfg, quiet=True)
    finally:
        dialog.close()
    if ok:
        ip = vpn.external_ip()
        if ip:
            common.set_state(True, server=cfg["label"], config=cfg["path"], ip=ip)
        common.notify(common.L(32073) % cfg["label"])
    else:
        common.notify(common.L(32074))
    _root_or_pass()


def do_quick():
    favs = configs.load_favorites()
    if favs:
        if common.get_setting("random_favorite", "false") == "true":
            import random
            target = random.choice(favs)
        else:
            target = favs[0]
        do_connect(target)
        return
    backend = _active_backend()
    cand = [c for c in configs.scan() if c["backend"] == backend]
    if not cand:
        common.ok(common.L(32076))
        _root_or_pass()
        return
    do_connect(cand[0]["id"])


def do_manage_favorites():
    items = configs.scan()
    if not items:
        common.ok(common.L(32076))
        return
    labels = ["%s  ·  %s  ·  %s" % (c["label"], c["backend"],
              c.get("country_name", c.get("country", ""))) for c in items]
    favs = set(configs.load_favorites())
    preselect = [i for i, c in enumerate(items) if c["id"] in favs]
    sel = xbmcgui.Dialog().multiselect(common.L(32211), labels,
                                       preselect=preselect)
    if sel is None:
        return
    configs.save_favorites([items[i]["id"] for i in sel])
    common.notify(common.L(32213) % len(sel))
    if HANDLE >= 0:
        view_root()


def do_pick_autoconnect():
    items = configs.scan()
    if not items:
        common.ok(common.L(32076))
        return
    labels = ["%s  ·  %s  ·  %s" % (c["label"], c["backend"],
              c.get("country_name", c.get("country", ""))) for c in items]
    sel = xbmcgui.Dialog().select(common.L(32214), labels)
    if sel < 0:
        return
    common.set_setting("autoconnect_id", items[sel]["id"])
    common.set_setting("autoconnect_label", items[sel]["label"])
    common.notify("%s : %s" % (common.L(32214), items[sel]["label"]))


def do_disconnect():
    vpn.disconnect()
    common.notify(common.L(32070))
    _root_or_pass()


def do_toggle():
    if common.get_state()["connected"]:
        vpn.disconnect()
        common.notify(common.L(32070))
    else:
        do_quick()
    if HANDLE >= 0:
        view_root()


def do_reconnect():
    dialog = xbmcgui.DialogProgressBG()
    dialog.create(common.ADDON_NAME, common.L(32064))
    try:
        vpn.reconnect_last(quiet=True)
    finally:
        dialog.close()
    _root_or_pass()


def do_status():
    if common.get_state()["connected"]:
        ip = vpn.external_ip()
        if ip:
            st = common.get_state()
            common.set_state(True, server=st["server"], config=st["config"], ip=ip)
    _root_or_pass()


def _server_options(items):
    out = []
    for c in items:
        tag = "WG" if c["backend"] == "wireguard" else c["proto"].upper()
        out.append("%s  (%s) \u00b7 %s" % (c["label"], tag, c["country_name"]))
    return out


def _flag_art(cfg):
    flag = os.path.join(common.ADDON_PATH, "resources", "flags",
                        "%s.png" % cfg["country"].lower())
    return flag if os.path.exists(flag) else ICON


def do_pick_connect(backend=None):
    items = configs.scan()
    if backend:
        items = [c for c in items if c["backend"] == backend]
    if not items:
        common.ok(common.L(32076))
        return
    state = common.get_state()
    li_list = []
    for c in items:
        tag = "WG" if c["backend"] == "wireguard" else c["proto"].upper()
        li = xbmcgui.ListItem("%s  (%s)" % (c["label"], tag))
        connected = state["connected"] and state.get("config") == c["path"]
        li.setLabel2(("\u25cf " + common.L(32062)) if connected else common.L(32190))
        art = _flag_art(c)
        li.setArt({"icon": art, "thumb": art})
        li_list.append(li)
    heading = common.L(32167)
    if backend:
        heading = "%s \u2014 %s" % (common.L(32167), _backend_name(backend))
    idx = xbmcgui.Dialog().select(heading, li_list, useDetails=True)
    if idx < 0:
        return
    cfg = items[idx]
    if state["connected"] and state.get("config") == cfg["path"]:
        do_disconnect()
    else:
        do_connect(cfg["id"])


def do_pick_delete():
    items = configs.scan()
    if not items:
        common.ok(common.L(32076))
        return
    idx = xbmcgui.Dialog().select(common.L(32185), _server_options(items))
    if idx < 0:
        return
    cfg = items[idx]
    if common.yesno(common.L(32169) % cfg["label"]):
        if configs.delete_config(cfg["id"]):
            common.event("suppression %s" % cfg["label"])
            configs.refresh_counts()
            common.notify(common.L(32170) % cfg["label"])


def do_import_many():
    # Import every WireGuard (.conf) and OpenVPN (.ovpn) file found in a folder.
    folder = xbmcgui.Dialog().browse(0, common.L(32142), "files")
    if not folder:
        if HANDLE >= 0:
            view_root()
        return
    found = []
    for name in sorted(os.listdir(folder)):
        low = name.lower()
        if low.endswith(".conf") or low.endswith(".ovpn"):
            found.append(os.path.join(folder, name))
    if not found:
        common.ok(common.L(32144))
        if HANDLE >= 0:
            view_root()
        return
    added = dupe = full = bad = 0
    for src in found:
        cfg = configs.import_file(src)
        if not cfg:
            bad += 1
        elif cfg.get("_full"):
            full += 1
        elif cfg.get("_existed"):
            dupe += 1
        else:
            added += 1
            common.event("import %s (%s)" % (cfg["label"], cfg["backend"]))
    configs.refresh_counts()
    common.ok(common.L(32197) % (added, dupe, full + bad))
    if HANDLE >= 0:
        view_servers()


def do_import(kind=None):
    mask = {"wg": ".conf", "ovpn": ".ovpn"}.get(kind, ".ovpn|.conf")
    path = xbmcgui.Dialog().browse(1, common.L(32142), "files", mask, False, False)
    if not path or os.path.isdir(path):
        if HANDLE >= 0:
            view_root()
        return
    cfg = configs.import_file(path)
    if not cfg:
        common.ok(common.L(32144))
        if HANDLE >= 0:
            view_root()
        return
    if cfg.get("_full"):
        common.ok(common.L(32182) % (configs.MAX_PER_BACKEND, _backend_name(cfg["backend"])))
        if HANDLE >= 0:
            view_root()
        return
    if cfg.get("_existed"):
        common.ok(common.L(32176) % cfg["label"])
    else:
        common.event("import %s (%s)" % (cfg["label"], cfg["backend"]))
        configs.refresh_counts()
        common.notify(common.L(32143) % cfg["label"])
    if HANDLE >= 0:
        view_servers(cfg["backend"])


def do_delete(config_id):
    cfg = configs.find_by_id(config_id)
    name = cfg["label"] if cfg else config_id
    if common.yesno(common.L(32169) % name):
        if configs.delete_config(config_id):
            common.event("suppression %s" % name)
            common.notify(common.L(32170) % name)
    if HANDLE >= 0:
        view_servers()
    else:
        xbmc.executebuiltin("Container.Refresh")


def _pick_test_config():
    last = common.get_setting("last_config", "")
    if last and os.path.exists(last):
        cfg = configs.parse_config(last)
        if cfg:
            return cfg
    backend = _active_backend()
    cand = [c for c in configs.scan() if c["backend"] == backend]
    return cand[0] if cand else None


def do_test():
    cfg = _pick_test_config()
    if not cfg:
        common.ok(common.L(32076))
        if HANDLE >= 0:
            view_root()
        return
    dialog = xbmcgui.DialogProgressBG()
    dialog.create(common.ADDON_NAME, common.L(32077) % cfg["label"])
    try:
        ok = vpn.connect(cfg, quiet=True)
    finally:
        dialog.close()
    if ok:
        ip = vpn.external_ip()
        if ip:
            common.set_state(True, server=cfg["label"], config=cfg["path"], ip=ip)
        msg = common.L(32131) % cfg["label"]
        msg += "\n%s : %s" % (common.L(32166), cfg["country_name"])
        if ip:
            msg += "\n%s : %s" % (common.L(32157), ip)
        common.ok(msg)
    else:
        common.ok(common.L(32074))
    if HANDLE >= 0:
        view_root()


# ---------------------------------------------------------------------------
# Stats / logs
# ---------------------------------------------------------------------------

def do_widget():
    statswidget.open_widget()
    if HANDLE >= 0:
        view_root()


def do_install_panel():
    from lib import skinwidget
    skinwidget.install()
    if HANDLE >= 0:
        view_root()


def do_remove_panel():
    from lib import skinwidget
    skinwidget.remove()
    if HANDLE >= 0:
        view_root()


def _wrow(label, value, url, icon=None):
    # Field on the main label, value on label2 (two-column "system info" look),
    # and the field:value also kept in the label for views that show one line.
    li = xbmcgui.ListItem("%s : %s" % (label, value))
    try:
        li.setLabel2(value)
    except Exception:
        pass
    art = icon or ICON
    li.setArt({"icon": art, "thumb": art})
    xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=False)


def _media(name):
    return os.path.join(common.ADDON_PATH, "resources", "skins", "Default", "media", name)


def _flag_for_server(server):
    # server looks like "FR#679" -> flag resources/flags/fr.png
    if server and len(server) >= 2 and server[:2].isalpha():
        cc = server[:2].lower()
        p = os.path.join(common.ADDON_PATH, "resources", "flags", "%s.png" % cc)
        if os.path.exists(p):
            return p
    return None


def view_wstats():
    """Directory meant to be used as an always-on skin home widget (live stats),
    laid out like Kodi's System Information panel: field + value rows."""
    snap = stats.snapshot()
    target = build_url(action="widget")
    dot_on = _media("dot_on.png")
    dot_off = _media("dot_off.png")
    if snap["connected"]:
        _wrow(common.L(32153), common.L(32201), target, dot_on)          # État : Connecté
        _wrow(common.L(32203), _backend_name(snap["backend"]), target)   # Protocole
        flag = _flag_for_server(snap["server"]) or ICON
        _wrow(common.L(32156), snap["server"] or "-", target, flag)      # Serveur
        _wrow(common.L(32157), snap["ip"] or "-", target)                # IP publique
        if snap.get("iface"):
            _wrow(common.L(32204), snap["iface"], target)                # Interface
        _wrow(common.L(32158), stats.human_duration(snap["uptime"]), target)  # Durée
        _wrow(common.L(32160), stats.human_bytes(snap["rx"]), target)    # Reçu
        _wrow(common.L(32161), stats.human_bytes(snap["tx"]), target)    # Envoyé
    else:
        _wrow(common.L(32153), common.L(32202), target, dot_off)         # État : Déconnecté
        wg, ovpn = configs.counts()
        _wrow(common.L(32174), "%d / %d" % (wg, configs.MAX_PER_BACKEND), target)    # WireGuard
        _wrow(common.L(32175), "%d / %d" % (ovpn, configs.MAX_PER_BACKEND), target)  # OpenVPN
    xbmcplugin.setContent(HANDLE, "files")
    xbmcplugin.endOfDirectory(HANDLE)


def view_wlogs():
    """Directory meant to be used as a skin home widget (event log)."""
    lines = common.read_events(40)
    target = build_url(action="logs")
    if not lines:
        lines = [common.L(32155)]
    for line in reversed(lines):
        li = xbmcgui.ListItem(line)
        li.setArt({"icon": ICON, "thumb": ICON})
        xbmcplugin.addDirectoryItem(HANDLE, target, li, isFolder=False)
    xbmcplugin.setContent(HANDLE, "files")
    xbmcplugin.endOfDirectory(HANDLE)


def do_make_widget(kind):
    import json
    if kind == "logs":
        title = "ProtonVPN \u2014 " + common.L(32152)
        path = build_url(action="wlogs")
    else:
        title = "ProtonVPN \u2014 " + common.L(32151)
        path = build_url(action="wstats")
    req = {
        "jsonrpc": "2.0", "id": 1, "method": "Favourites.AddFavourite",
        "params": {"title": title, "type": "window", "window": "programs",
                   "windowparameter": path, "thumbnail": ICON},
    }
    try:
        xbmc.executeJSONRPC(json.dumps(req))
        common.notify(common.L(32189) % title)
    except Exception:
        common.ok(common.L(32074))


def do_make_shortcut():
    import json
    title = "ProtonVPN \u2014 " + common.L(32167)  # Serveurs
    path = build_url(action="servers")
    req = {
        "jsonrpc": "2.0", "id": 1, "method": "Favourites.AddFavourite",
        "params": {"title": title, "type": "window", "window": "programs",
                   "windowparameter": path, "thumbnail": ICON},
    }
    try:
        xbmc.executeJSONRPC(json.dumps(req))
        common.notify(common.L(32195) % title)
    except Exception:
        common.ok(common.L(32074))


def do_widget_help():
    xbmcgui.Dialog().textviewer(common.L(32186), common.L(32193))


def do_logs():
    lines = common.read_events(120)
    text = "\n".join(lines) if lines else common.L(32155)
    xbmcgui.Dialog().textviewer(common.L(32152), text)
    if HANDLE >= 0:
        view_root()


def do_settings():
    common.open_settings()
    view_root()


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def router(qs):
    params = dict(parse_qsl(qs))
    action = params.get("action")

    if action == "servers":
        view_servers()
    elif action == "inactive":
        do_inactive(params.get("backend", ""))
    elif action == "connect":
        do_connect(params.get("id"))
    elif action == "quick":
        do_quick()
    elif action == "pickconnect":
        do_pick_connect(params.get("backend"))
    elif action == "importmany":
        do_import_many()
    elif action == "pickdelete":
        do_pick_delete()
    elif action == "disconnect":
        do_disconnect()
    elif action == "toggle":
        do_toggle()
    elif action == "favorites":
        do_manage_favorites()
    elif action == "pickautoconnect":
        do_pick_autoconnect()
    elif action == "reconnect":
        do_reconnect()
    elif action == "status":
        do_status()
    elif action == "import":
        do_import(params.get("kind"))
    elif action == "delete":
        do_delete(params.get("id"))
    elif action == "test":
        do_test()
    elif action == "widget":
        do_widget()
    elif action == "wstats":
        view_wstats()
    elif action == "wlogs":
        view_wlogs()
    elif action == "makewidget":
        do_make_widget(params.get("kind"))
    elif action == "makeshortcut":
        do_make_shortcut()
    elif action == "widgethelp":
        do_widget_help()
    elif action == "installpanel":
        do_install_panel()
    elif action == "removepanel":
        do_remove_panel()
    elif action == "logs":
        do_logs()
    elif action == "settings":
        do_settings()
    else:
        view_root()


if __name__ == "__main__":
    router(sys.argv[2][1:] if len(sys.argv) > 2 else "")
