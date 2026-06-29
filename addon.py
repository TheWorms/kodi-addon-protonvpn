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
from lib import statswidget

HANDLE = int(sys.argv[1])
BASE = sys.argv[0]
ICON = os.path.join(common.ADDON_PATH, "resources", "icon.png")

MAX_CONFIGS = 10


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

def do_connect(config_id):
    cfg = configs.find_by_id(config_id)
    if not cfg:
        common.notify(common.L(32076))
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
        common.notify(common.L(32073) % cfg["label"])
    else:
        common.notify(common.L(32074))
    view_root()


def do_quick():
    backend = _active_backend()
    cand = [c for c in configs.scan() if c["backend"] == backend]
    if not cand:
        common.ok(common.L(32076))
        view_root()
        return
    do_connect(cand[0]["id"])


def do_disconnect():
    vpn.disconnect()
    view_root()


def do_reconnect():
    dialog = xbmcgui.DialogProgressBG()
    dialog.create(common.ADDON_NAME, common.L(32064))
    try:
        vpn.reconnect_last(quiet=True)
    finally:
        dialog.close()
    view_root()


def do_status():
    if common.get_state()["connected"]:
        ip = vpn.external_ip()
        if ip:
            st = common.get_state()
            common.set_state(True, server=st["server"], config=st["config"], ip=ip)
    view_root()


def do_import(kind=None):
    if len(configs.scan()) >= MAX_CONFIGS:
        common.ok(common.L(32163) % MAX_CONFIGS)
        if HANDLE >= 0:
            view_root()
        return
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
    if cfg.get("_existed"):
        common.ok(common.L(32176) % cfg["label"])
    else:
        common.event("import %s (%s)" % (cfg["label"], cfg["backend"]))
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
    elif action == "disconnect":
        do_disconnect()
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
    elif action == "logs":
        do_logs()
    elif action == "settings":
        do_settings()
    else:
        view_root()


if __name__ == "__main__":
    router(sys.argv[2][1:] if len(sys.argv) > 2 else "")
