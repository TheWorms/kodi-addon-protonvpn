# -*- coding: utf-8 -*-
#
# ProtonVPN - dialogues des exceptions, lancés depuis les paramètres
# (catégorie Exceptions). La liste est enregistrée dans exceptions.json ;
# le service la relit dès qu'elle change.

import json
import time

import xbmc
import xbmcgui

from lib import common
from lib import exceptions

L = common.L


def _yes_no(flag):
    return xbmc.getLocalizedString(107 if flag else 106)  # Oui / Non


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


def _art(name):
    import os
    return os.path.join(common.ADDON_PATH, "resources", "icons", name + ".png")


def method_icon(method):
    return _art("pause" if method == exceptions.PAUSE else "route")


def method_label(method):
    return L(32231) if method == exceptions.PAUSE else L(32230)


def summary(ex):
    """« Route directe · plages Google + 2 serveur(s) » ou « Pause du VPN »."""
    if ex["method"] == exceptions.PAUSE:
        return L(32231)
    parts = []
    if exceptions.profile_ranges(ex["id"]):
        parts.append(L(32259))
    n = len(ex["learned"]) + len(ex["manual"])
    if n:
        parts.append(L(32260) % n)
    return L(32230) + (" · " + " + ".join(parts) if parts else "")


def _item(label, label2="", icon=""):
    li = xbmcgui.ListItem(label, label2)
    if icon:
        li.setArt({"icon": icon, "thumb": icon})
    return li


# --- Ajouter ou retirer des addons --------------------------------------------

def manage():
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
    methods = {ex["id"]: method_label(ex["method"]) for ex in items}
    options = []
    for aid, name, icon in rows:
        label2 = methods.get(aid, aid)
        if aid not in known:
            label2 = "%s · %s" % (aid, L(32258))
        options.append(_item(name, label2, icon or "DefaultAddon.png"))
    pre = [i for i, r in enumerate(rows) if r[0] in current]
    sel = xbmcgui.Dialog().multiselect(L(32250), options, preselect=pre, useDetails=True)
    if sel is None:
        return
    chosen = [rows[i][0] for i in sel]
    kept = [ex for ex in items if ex["id"] in chosen]
    added = [exceptions.new_entry(a) for a in chosen if a not in current]
    for ex in items:
        if ex["id"] not in chosen:
            common.event("Exceptions : %s retire" % exceptions.addon_name(ex["id"]))
    for ex in added:
        common.event("Exceptions : %s ajoute (route directe)" % exceptions.addon_name(ex["id"]))
    exceptions.save(kept + added)
    common.notify(L(32251) % len(chosen))


# --- Régler un addon de la liste ----------------------------------------------

def edit():
    """Liste des exceptions : icône de la méthode, nom de l'addon, détail.
    La première ligne ouvre l'ajout / retrait d'addons."""
    while True:
        items = exceptions.load()
        options = [_item(L(32224), L(32225), _art("ajouter"))]
        options += [_item(exceptions.addon_name(ex["id"]), summary(ex), method_icon(ex["method"]))
                    for ex in items]
        options.append(_item(L(32262), "", _art("valider")))
        sel = xbmcgui.Dialog().select(L(32250), options, useDetails=True)
        if sel < 0 or sel == len(options) - 1:
            return
        if sel == 0:
            manage()
        else:
            _edit_one(items[sel - 1]["id"])


def _edit_one(addon_id):
    name = exceptions.addon_name(addon_id)
    while True:
        items = exceptions.load()
        ex = exceptions.by_id(items, addon_id)
        if not ex:
            return
        opts = [(L(32234) % method_label(ex["method"]), "method")]
        if ex["method"] == exceptions.ROUTE:
            ranges = exceptions.profile_ranges(addon_id)
            if ranges:
                opts.append((L(32235) % len(ranges), "profile"))
            if exceptions.announces(addon_id):
                opts.append((L(32252) % name, "announce"))
            else:
                opts.append((L(32236) % len(ex["learned"]), "learned"))
                opts.append((L(32237) % _yes_no(ex["learn"]), "learn"))
            opts.append((L(32238) % len(ex["manual"]), "manual"))
        opts.append((L(32239), "remove"))
        opts.append((L(32262), "ok"))
        sel = xbmcgui.Dialog().select(name, [o[0] for o in opts])
        if sel < 0 or opts[sel][1] == "ok":
            return
        act = opts[sel][1]
        if act == "method":
            _choose_method(items, ex, name)
        elif act == "profile":
            common.ok(L(32254), heading=name)
        elif act == "announce":
            common.ok(L(32253) % name, heading=name)
        elif act == "learned":
            _forget_learned(items, ex, name)
        elif act == "learn":
            ex["learn"] = not ex["learn"]
            exceptions.save(items)
        elif act == "manual":
            _manual(items, ex, name)
        elif act == "remove":
            if common.yesno(L(32248) % name):
                items.remove(ex)
                exceptions.save(items)
                common.event("Exceptions : %s retire" % name)
                return


def _choose_method(items, ex, name):
    """Deux boutons explicites (plus une annulation) : Kodi ferme une liste
    dès qu'on choisit une ligne, ce qui ressemblait à un choix sans validation."""
    delay = max(0, common.get_int("pause_delay", 5))
    text = "[B]%s[/B] : %s[CR][CR][B]%s[/B] : %s[CR][CR]%s" % (
        L(32230), L(32232) % name, L(32231), L(32233) % (name, delay),
        L(32261) % method_label(ex["method"]))
    res = xbmcgui.Dialog().yesnocustom(name, text, xbmc.getLocalizedString(222),
                                       nolabel=L(32230), yeslabel=L(32231))
    if res not in (0, 1):
        return  # annulé
    method = exceptions.PAUSE if res == 1 else exceptions.ROUTE
    if method != ex["method"]:
        ex["method"] = method
        exceptions.save(items)
        common.event("Exceptions : %s en %s" % (name, method_label(method).lower()))
        common.notify("%s : %s" % (name, method_label(method)), icon=method_icon(method))


def _host_label(h):
    ips = ", ".join(h["ips"][:3]) + (" …" if len(h["ips"]) > 3 else "")
    return ips or "?"


def _forget_learned(items, ex, name):
    if not ex["learned"]:
        common.ok(L(32246) % name, heading=name)
        return
    options = [_item(h["host"], _host_label(h)) for h in ex["learned"]]
    sel = xbmcgui.Dialog().multiselect(L(32247), options,
                                       preselect=list(range(len(options))), useDetails=True)
    if sel is None or len(sel) == len(options):
        return
    ex["learned"] = [ex["learned"][i] for i in sel]
    exceptions.save(items)


def _manual(items, ex, name):
    while True:
        options = [_item(L(32242))] + [_item(h["host"], _host_label(h)) for h in ex["manual"]]
        sel = xbmcgui.Dialog().select(name, options, useDetails=True)
        if sel < 0:
            return
        if sel > 0:
            h = ex["manual"][sel - 1]
            if common.yesno(L(32240) % h["host"]):
                ex["manual"].remove(h)
                exceptions.save(items)
            continue
        text = xbmcgui.Dialog().input(L(32243))
        if not text:
            continue
        kind, value = exceptions.parse_target(text)
        if not kind:
            common.ok(L(32245))
            continue
        if any(h["host"] == value for h in ex["manual"]):
            continue
        ips = exceptions.resolve(value)
        if kind == "host" and not ips and not common.yesno(L(32244) % value):
            continue
        ex["manual"].append({"host": value, "ips": ips, "ts": int(time.time())})
        exceptions.save(items)
        common.event("Exceptions : %s ajoute a la main pour %s" % (value, name))
