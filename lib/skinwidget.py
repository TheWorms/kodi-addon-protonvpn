# -*- coding: utf-8 -*-
#
# ProtonVPN - selectable Arctic Zephyr widget (restores the 0.4.1 mechanism).
#
# Registers a "ProtonVPN" entry in AZ's widget picker (clone of "System info"),
# rendered as a native row list reading protonvpn.* window properties. Patches:
#   shortcuts/overrides.xml : <shortcut widget="protonvpninfo" ...>
#   shortcuts/template.xml  : <other include="ProtonVPNInfoContent">
#   1080i/Includes.xml      : the ProtonVPNInfoItems <item> list
# Also cleans up the 0.5.0 home-overlay (Home.xml call + ProtonVPNHomePanel).
# remove() reverts everything. Only Arctic Zephyr is supported.

import os
import shutil

import xbmc
import xbmcvfs

from lib import common

_BEGIN = "<!-- ProtonVPN:BEGIN -->"
_END = "<!-- ProtonVPN:END -->"
_OVERLAY_CALL = "<include>ProtonVPNHomePanel</include>"
_LEGACY_REF = "<include>Includes_ProtonVPNWidget.xml</include>"
_LEGACY_FILE = "Includes_ProtonVPNWidget.xml"
_SRC = os.path.join(common.ADDON_PATH, "resources", "skin",
                    "Includes_ProtonVPNWidget.xml")

_SHORTCUT = ('<shortcut widget="protonvpninfo" type="ProtonVPN" label="ProtonVPN" '
            'icon="special://skin/extras/icons/sysinfo.png" widgetType="system" '
            'widgetTarget="system">$INCLUDE[skinshortcuts-template-ProtonVPNInfoContent]</shortcut>')

_TEMPLATE = ('    <other include="ProtonVPNInfoContent">\n'
            '        <controls>\n'
            '            <include>ProtonVPNInfoItems</include>\n'
            '        </controls>\n'
            '    </other>')


def _skin_id():
    try:
        return xbmc.getSkinDir() or ""
    except Exception:
        return ""


def is_supported():
    return _skin_id().startswith("skin.arctic.zephyr")


def _base():
    return xbmcvfs.translatePath("special://home/addons/%s/" % _skin_id())


def _res_dir():
    cand = os.path.join(_base(), "1080i")
    return cand if os.path.isdir(cand) else _base()


def _read(p):
    with open(p, "r", encoding="utf-8") as fh:
        return fh.read()


def _write(p, t):
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(t)


def _def():
    t = _read(_SRC)
    a = t.find("<include name=")
    b = t.rfind("</include>")
    return t[a:b + len("</include>")]


# Patch on Includes_Home.xml: swap the native system detail for ours, only for
# our widget (leaves the real "System info" widget untouched).
_HOME_TARGET = ('<include condition="!$PARAM[issettingslayout]">'
                'InfoSubWidgetSystemInclude</include>')
_HOME_REPLACE = (
    '<control type="group">\n'
    '            <visible>!String.IsEqual(Container(300).ListItem.Property(widget),protonvpninfo)</visible>\n'
    '            <include condition="!$PARAM[issettingslayout]">InfoSubWidgetSystemInclude</include>\n'
    '        </control>\n'
    '        <control type="group">\n'
    '            <visible>String.IsEqual(Container(300).ListItem.Property(widget),protonvpninfo)</visible>\n'
    '            <include>ProtonVPNDetailInclude</include>\n'
    '        </control>')


def _patch_home_includes(res):
    p = os.path.join(res, "Includes_Home.xml")
    if not os.path.isfile(p):
        common.log("Includes_Home.xml introuvable, detail non patche")
        return
    try:
        bak = p + ".pvpnbak"
        if os.path.exists(bak):
            shutil.copyfile(bak, p)          # restore clean first (idempotent)
        else:
            shutil.copyfile(p, bak)
        text = _read(p)
        if _HOME_TARGET in text and "ProtonVPNDetailInclude" not in text:
            _write(p, text.replace(_HOME_TARGET, _HOME_REPLACE, 1))
            common.log("detail systeme remplace par ProtonVPNDetailInclude")
        elif _HOME_TARGET not in text:
            common.log("ancre InfoSubWidgetSystemInclude introuvable dans Includes_Home.xml")
    except Exception as exc:
        common.log("patch Includes_Home.xml echoue: %s" % exc)


def _restore_home_includes(res):
    p = os.path.join(res, "Includes_Home.xml")
    bak = p + ".pvpnbak"
    if os.path.exists(bak):
        shutil.copyfile(bak, p)


def _strip_markers(text):
    while _BEGIN in text and _END in text:
        i = text.find(_BEGIN)
        j = text.find(_END, i)
        if j < 0:
            break
        j += len(_END)
        start = text.rfind("\n", 0, i)
        end = text.find("\n", j)
        start = start if start >= 0 else 0
        end = end + 1 if end >= 0 else j
        text = text[:start] + text[end:]
    return text


def _marker(inner):
    return "\n%s\n%s\n%s\n" % (_BEGIN, inner, _END)


def _flag(installed):
    try:
        common.set_setting("panel_installed", "true" if installed else "false")
    except Exception:
        pass


def _clean_overlay(res):
    """Remove the 0.5.0 home overlay (Home.xml call) if present."""
    home = os.path.join(res, "Home.xml")
    if os.path.isfile(home):
        h = _read(home)
        h = h.replace("    " + _OVERLAY_CALL + "\n", "").replace(_OVERLAY_CALL, "")
        _write(home, h)
    legacy = os.path.join(res, _LEGACY_FILE)
    if os.path.exists(legacy):
        try:
            os.remove(legacy)
        except Exception:
            pass


def install():
    if not is_supported():
        common.ok(common.L(32205))
        return False
    res = _res_dir()
    sc = os.path.join(_base(), "shortcuts")
    includes = os.path.join(res, "Includes.xml")
    overrides = os.path.join(sc, "overrides.xml")
    template = os.path.join(sc, "template.xml")
    if not (os.path.isfile(includes) and os.path.isfile(overrides)
            and os.path.isfile(template)):
        common.ok(common.L(32205))
        return False
    try:
        for f in (includes, overrides, template,
                  os.path.join(res, "Home.xml")):
            bak = f + ".pvpnbak"
            if os.path.isfile(f) and not os.path.exists(bak):
                shutil.copyfile(f, bak)

        _clean_overlay(res)

        # Includes.xml: items (strip any previous block first)
        itext = _strip_markers(_read(includes))
        itext = itext.replace("    " + _LEGACY_REF + "\n", "").replace(_LEGACY_REF, "")
        k = itext.rfind("</includes>")
        itext = itext[:k] + _marker(_def()) + itext[k:]
        _write(includes, itext)

        # overrides.xml: shortcut after the systeminfo one (leading ws only)
        otext = _strip_markers(_read(overrides))
        anchor = otext.find('widget="systeminfo"')
        line_start = otext.rfind("\n", 0, anchor) + 1
        eol = otext.find("\n", anchor)
        lead = otext[line_start:anchor]
        indent = lead[:len(lead) - len(lead.lstrip())]
        block = "%s%s\n%s%s\n%s%s\n" % (indent, _BEGIN, indent, _SHORTCUT,
                                        indent, _END)
        otext = otext[:eol + 1] + block + otext[eol + 1:]
        _write(overrides, otext)

        # template.xml: content template after SystemInfoContent
        ttext = _strip_markers(_read(template))
        si = ttext.find('<other include="SystemInfoContent">')
        close = ttext.find("</other>", si) + len("</other>")
        ttext = ttext[:close] + _marker(_TEMPLATE) + ttext[close:]
        _write(template, ttext)

        _patch_home_includes(res)
        _flag(True)
        common.notify(common.L(32206))
        xbmc.executebuiltin("ReloadSkin()")
        return True
    except Exception as exc:
        common.log("widget install failed: %s" % exc)
        common.ok(common.L(32207))
        return False


def remove():
    res = _res_dir()
    sc = os.path.join(_base(), "shortcuts")
    for p in (os.path.join(res, "Includes.xml"),
              os.path.join(sc, "overrides.xml"),
              os.path.join(sc, "template.xml")):
        if os.path.isfile(p):
            _write(p, _strip_markers(_read(p)))
    try:
        _clean_overlay(res)
        _restore_home_includes(res)
        xbmc.executebuiltin("Skin.Reset(protonvpn.widget)")
        _flag(False)
        common.notify(common.L(32208))
        xbmc.executebuiltin("ReloadSkin()")
        return True
    except Exception as exc:
        common.log("widget remove failed: %s" % exc)
        common.ok(common.L(32207))
        return False
