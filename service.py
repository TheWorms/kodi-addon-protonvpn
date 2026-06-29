# -*- coding: utf-8 -*-
#
# ProtonVPN
# Background service: optional auto-connect at boot, reconnect on drop,
# keep window-property state up to date, optional disconnect on shutdown.

import os

import xbmc

from lib import common
from lib import vpn
from lib import configs


class ProtonService(xbmc.Monitor):

    # Exponential-ish backoff between reconnection attempts, and a ceiling on
    # consecutive failures before we stop trying and surface an error. This
    # mirrors how the official daemon avoids hammering a dead endpoint.
    _BACKOFF = [5, 15, 30, 60]
    _MAX_FAILS = 5

    def __init__(self):
        super().__init__()
        self.expected = False  # do we want a connection to be up?

    def _check_interval(self):
        return common.get_int("monitor_interval", 15) or 15

    def _sync_header(self):
        if not common.get_bool("header_indicator", True):
            common.set_header("")
            return
        state = common.get_state()
        if state["connected"]:
            if not common.get_prop(common.PROP_HEADER):
                common.set_header("VPN \u00b7 %s" % (state.get("server", "") or ""))
        else:
            common.set_header("")

    def auto_connect(self):
        if not common.get_bool("auto_connect", False):
            return
        folder = configs.config_folder()
        if not folder or not os.path.isdir(folder):
            common.debug("auto-connect skipped: config folder not set")
            return
        last = common.get_setting("last_config", "")
        if last and os.path.exists(last):
            common.log("Auto-connecting to last server")
            self.expected = True
            vpn.connect(last, quiet=True)
            return
        # No last server: pick the first config of the preferred country.
        pref_country = common.get_setting("default_country", "").upper()
        all_cfg = configs.scan()
        if pref_country:
            cand = [c for c in all_cfg if c["country"] == pref_country]
            all_cfg = cand or all_cfg
        if all_cfg:
            common.log("Auto-connecting to %s" % all_cfg[0]["label"])
            self.expected = True
            vpn.connect(all_cfg[0], quiet=True)

    def loop(self):
        common.set_state(vpn.is_running(), server=common.get_state().get("server", ""))
        self.auto_connect()
        if vpn.is_running():
            self.expected = True
            common.set_phase(common.PHASE_CONNECTED)

        fails = 0
        disconnect_on_exit = common.get_bool("disconnect_on_exit", False)
        while not self.abortRequested():
            if self.waitForAbort(self._check_interval()):
                break
            disconnect_on_exit = common.get_bool("disconnect_on_exit", False)
            running = vpn.is_running()
            self._sync_header()

            if self.expected and not running:
                if not common.get_bool("reconnect_on_drop", True):
                    self.expected = False
                    common.set_state(False)
                    common.set_phase(common.PHASE_DISCONNECTED)
                    continue

                if fails == 0:
                    common.event("connexion perdue - reconnexion")
                    common.notify(common.L(32078))  # "dropped - reconnecting"
                common.set_phase(common.PHASE_RECONNECTING)
                common.log("Connection dropped, reconnect attempt %d" % (fails + 1))

                if vpn.reconnect_last(quiet=True):
                    fails = 0
                else:
                    fails += 1
                    if fails >= self._MAX_FAILS:
                        common.event("abandon apres %d echecs" % fails)
                        common.log("Giving up after %d reconnect failures" % fails)
                        self.expected = False
                        common.set_state(False)
                        common.set_phase(common.PHASE_ERROR)
                        common.set_header("")
                        common.notify(common.L(32074))
                        fails = 0
                    else:
                        # Back off (abort-aware) before the next attempt.
                        delay = self._BACKOFF[min(fails - 1, len(self._BACKOFF) - 1)]
                        if self.waitForAbort(delay):
                            break
            elif running:
                # Healthy: keep shared state consistent (e.g. if the tunnel was
                # brought up out of band by the plugin).
                fails = 0
                if not common.get_state()["connected"]:
                    common.set_state(True, server=common.get_state().get("server", ""))
                common.set_phase(common.PHASE_CONNECTED)

        # Kodi is shutting down: use the value cached during the loop so we don't
        # touch the add-on API while it is being torn down.
        if disconnect_on_exit and vpn.is_running():
            common.log("Disconnecting on exit")
            vpn.disconnect(quiet=True)


if __name__ == "__main__":
    common.log("ProtonVPN service starting")
    common.ensure_profile()
    ProtonService().loop()
    common.log("ProtonVPN service stopped")
