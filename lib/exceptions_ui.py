# -*- coding: utf-8 -*-
#
# ProtonVPN - liste des exceptions (pause du VPN), lancée depuis les
# paramètres. Enregistrée dans exceptions.json ; le service la relit dès
# qu'elle change.

import json

import xbmc
import xbmcgui

from lib import common
from lib import exceptions

L = common.L


def _installed():
    """[(id, nom, icône)] des addons de type plugin installés et activés."""
    req = {"jsonrpc": "2.0", "id": 1, "method": "Addons.GetAddons",
           "params": {"type": "xbmc.python.pluginsource", "enabled": True,
                      "properties": ["name", "thumbnail"]}}
    try:
        res = json.loads(xbmc.executeJSONRPC(json.dumps(req)))
        addons = (res.get("result") or {}).get("addons") or []
    except (ValueError, TypeError, AttributeError):
        addons = []
    out = []
    for a in addons:
        aid = a.get("addonid", "")
        if aid and aid != common.ADDON_ID:
            out.append((aid, a.get("name") or aid, a.get("thumbnail") or ""))
    out.sort(key=lambda x: x[1].lower())
    return out


def manage():
    """Coche les addons qui mettent le VPN en pause."""
    items = exceptions.load()
    current = {ex["id"] for ex in items}
    installed = _installed()
    known = {a[0] for a in installed}
    rows = list(installed)
    # Exceptions d'addons désinstallés depuis : affichées pour pouvoir les retirer.
    rows += [(ex["id"], ex["id"], "") for ex in items if ex["id"] not in known]
    if not rows:
        common.ok(L(32241))
        return
    options = []
    for aid, name, icon in rows:
        label2 = aid if aid in known else "%s · %s" % (aid, L(32258))
        li = xbmcgui.ListItem(name, label2)
        li.setArt({"icon": icon or "DefaultAddon.png", "thumb": icon or "DefaultAddon.png"})
        options.append(li)
    pre = [i for i, r in enumerate(rows) if r[0] in current]
    sel = xbmcgui.Dialog().multiselect(L(32250), options, preselect=pre, useDetails=True)
    if sel is None:
        return
    chosen = [rows[i][0] for i in sel]
    for ex in items:
        if ex["id"] not in chosen:
            common.event("Exceptions : %s retire" % exceptions.addon_name(ex["id"]))
    for aid in chosen:
        if aid not in current:
            common.event("Exceptions : %s ajoute" % exceptions.addon_name(aid))
    # Garde l'ordre existant, ajoute les nouveaux à la fin.
    kept = [ex for ex in items if ex["id"] in chosen]
    kept += [exceptions.new_entry(a) for a in chosen if a not in current]
    exceptions.save(kept)
    common.notify(L(32251) % len(chosen))
