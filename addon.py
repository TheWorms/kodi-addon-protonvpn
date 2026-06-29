# -*- coding: utf-8 -*-
#
# ProtonVPN
# Plugin GUI: browse servers by country, connect/disconnect, show status.
#
# Action entries (connect, disconnect, quick, ...) are folder items. Their
# handler performs the work and then re-renders the root menu in the same
# directory call, so Kodi always gets a properly ended directory.

import sys
import os
from urllib.parse import urlencode, parse_qsl

import xbmc
import xbmcgui
import xbmcplugin

from lib import common
from lib import configs
from lib import vpn
from lib import protonapi

HANDLE = int(sys.argv[1])
BASE = sys.argv[0]
ICON = os.path.join(common.ADDON_PATH, "resources", "icon.png")


def build_url(**kwargs):
    return BASE + "?" + urlencode(kwargs)


def add_item(label, url, folder=True, icon=None, info=None):
    li = xbmcgui.ListItem(label=label)
    li.setArt({"icon": icon or ICON, "thumb": icon or ICON})
    if info:
        li.setInfo("video", {"plot": info})
    xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=folder)


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

def view_root():
    state = common.get_state()
    folder = configs.config_folder()

    if not folder or not os.path.isdir(folder):
        add_item("[COLOR orange]%s[/COLOR]" % common.L(32075),
                 build_url(action="settings"))
        add_item(common.L(32007), build_url(action="settings"))
        xbmcplugin.endOfDirectory(HANDLE)
        return

    if state["connected"]:
        ip = state.get("ip") or ""
        head = "[COLOR lime]%s[/COLOR] %s" % (common.L(32060), state["server"])
        if ip:
            head += "  (%s)" % ip
        add_item(head, build_url(action="status"))
        add_item("[COLOR red]%s[/COLOR]" % common.L(32062),
                 build_url(action="disconnect"))
    else:
        add_item("[COLOR grey]%s[/COLOR]" % common.L(32061),
                 build_url(action="status"))

    add_item(common.L(32063), build_url(action="quick", mode="random"))
    last = common.get_setting("last_config", "")
    if last and os.path.exists(last):
        add_item(common.L(32064), build_url(action="reconnect"))

    add_item(common.L(32065), build_url(action="countries"))
    add_item(common.L(32066), build_url(action="all"))
    add_item(common.L(32007), build_url(action="settings"))

    xbmcplugin.setContent(HANDLE, "files")
    xbmcplugin.endOfDirectory(HANDLE)


def _proto_filter():
    pref = common.get_setting("protocol_pref", "0")  # 0 both, 1 udp, 2 tcp
    return {"0": "", "1": "udp", "2": "tcp"}.get(pref, "")


def view_countries():
    all_cfg = configs.filter_protocol(configs.scan(), _proto_filter())
    if not all_cfg:
        common.ok(common.L(32076))
        view_root()
        return
    for code, name, items in configs.group_by_country(all_cfg):
        flag = os.path.join(common.ADDON_PATH, "resources", "flags",
                            "%s.png" % code.lower())
        if not os.path.exists(flag):
            flag = ICON
        add_item("%s  [COLOR grey](%d)[/COLOR]" % (name, len(items)),
                 build_url(action="servers", country=code), icon=flag)
    xbmcplugin.setContent(HANDLE, "files")
    xbmcplugin.endOfDirectory(HANDLE)


def view_servers(country=None):
    all_cfg = configs.filter_protocol(configs.scan(), _proto_filter())
    if country:
        all_cfg = [c for c in all_cfg if c["country"] == country]
    lmap = protonapi.load_map()
    state = common.get_state()
    for cfg in all_cfg:
        label = "%s [COLOR grey](%s)[/COLOR]" % (cfg["label"], cfg["proto"].upper())
        load = protonapi.annotate(cfg, lmap)
        if load is not None:
            colour = "lime" if load < 50 else ("yellow" if load < 80 else "red")
            label += "  [COLOR %s]%d%%[/COLOR]" % (colour, load)
        if state["connected"] and state["config"] == cfg["path"]:
            label = "[COLOR lime]> [/COLOR]" + label
        add_item(label, build_url(action="connect", id=cfg["id"]), info=cfg["remote"])
    xbmcplugin.setContent(HANDLE, "files")
    xbmcplugin.endOfDirectory(HANDLE)


# ---------------------------------------------------------------------------
# Actions (each ends by re-rendering the root menu)
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


def do_quick(_mode):
    import random
    all_cfg = configs.filter_protocol(configs.scan(), _proto_filter())
    if not all_cfg:
        common.ok(common.L(32076))
        view_root()
        return
    do_connect(random.choice(all_cfg)["id"])


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


def do_settings():
    common.open_settings()
    view_root()


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def router(qs):
    params = dict(parse_qsl(qs))
    action = params.get("action")

    if action == "countries":
        view_countries()
    elif action == "servers":
        view_servers(params.get("country"))
    elif action == "all":
        view_servers(None)
    elif action == "connect":
        do_connect(params.get("id"))
    elif action == "quick":
        do_quick(params.get("mode", "random"))
    elif action == "disconnect":
        do_disconnect()
    elif action == "reconnect":
        do_reconnect()
    elif action == "status":
        do_status()
    elif action == "settings":
        do_settings()
    else:
        view_root()


if __name__ == "__main__":
    router(sys.argv[2][1:] if len(sys.argv) > 2 else "")
