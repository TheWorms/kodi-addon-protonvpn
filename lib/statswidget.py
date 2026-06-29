# -*- coding: utf-8 -*-
#
# ProtonVPN - live stats dialog (WindowXMLDialog).
# A background thread refreshes Home-window properties once per second; the
# skin XML binds to them via $INFO[Window(home).Property(protonvpn.w_*)], so the
# GUI updates itself without us touching controls from the worker thread.

import threading
import time

import xbmc
import xbmcgui

from lib import common
from lib import stats

_HOME = xbmcgui.Window(10000)
_KEYS = ("state", "server", "ip", "uptime", "hs", "rx", "tx", "rate")
_CLOSE_ACTIONS = (9, 10, 92)  # parent dir / previous menu / nav back


def _set(key, value):
    _HOME.setProperty("protonvpn.w_" + key, value)


class StatsWidget(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self._stop = False
        self._thread = None
        self._last = None  # (timestamp, rx, tx)

    def onInit(self):
        self._stop = False
        self._refresh()
        self._thread = threading.Thread(target=self._loop)
        self._thread.daemon = True
        self._thread.start()

    def _loop(self):
        monitor = xbmc.Monitor()
        while not self._stop and not monitor.abortRequested():
            for _ in range(10):
                if self._stop:
                    return
                xbmc.sleep(100)
            self._refresh()

    def _refresh(self):
        snap = stats.snapshot()
        if not snap["connected"]:
            _set("state", "[COLOR grey]%s[/COLOR]" % common.L(32155))
            for key in _KEYS[1:]:
                _set(key, "-")
            self._last = None
            return

        _set("state", "[COLOR lime]%s[/COLOR]" % common.L(32154))
        bk = "WireGuard" if snap["backend"] == "wireguard" else "OpenVPN"
        _set("server", "%s  [COLOR grey](%s)[/COLOR]" % (snap["server"] or "-", bk))
        _set("ip", snap["ip"] or "-")
        _set("uptime", stats.human_duration(snap["uptime"]))
        _set("hs", ("%ds" % snap["hs_age"]) if snap["hs_age"] is not None else "-")
        _set("rx", stats.human_bytes(snap["rx"]))
        _set("tx", stats.human_bytes(snap["tx"]))

        now = time.time()
        rate = "-"
        if self._last:
            dt = now - self._last[0]
            if dt > 0:
                drx = max(0, snap["rx"] - self._last[1]) / dt
                dtx = max(0, snap["tx"] - self._last[2]) / dt
                rate = "\u2193 %s/s    \u2191 %s/s" % (
                    stats.human_bytes(drx), stats.human_bytes(dtx))
        self._last = (now, snap["rx"], snap["tx"])
        _set("rate", rate)

    def onAction(self, action):
        if action.getId() in _CLOSE_ACTIONS:
            self.close()

    def close(self):
        self._stop = True
        thread = self._thread
        if thread and thread.is_alive():
            try:
                thread.join(1.5)
            except RuntimeError:
                pass
        super().close()


def open_widget():
    win = StatsWidget("script-protonvpn-stats.xml", common.ADDON_PATH, "Default", "1080i")
    win.doModal()
    del win
