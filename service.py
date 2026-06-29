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

    def __init__(self):
        super().__init__()
        self.expected = False  # do we want a connection to be up?

    def _check_interval(self):
        return common.get_int("monitor_interval", 15) or 15

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

        while not self.abortRequested():
            if self.waitForAbort(self._check_interval()):
                break
            running = vpn.is_running()
            if self.expected and not running:
                if common.get_bool("reconnect_on_drop", True):
                    common.log("Connection dropped, attempting reconnect")
                    common.notify(common.L(32078))  # Reconnecting...
                    if not vpn.reconnect_last(quiet=True):
                        common.notify(common.L(32074))
                else:
                    self.expected = False
                    common.set_state(False)
            elif running and not common.get_state()["connected"]:
                # Connection came up out of band (e.g. via the plugin).
                common.set_state(True, server=common.get_state().get("server", ""))

        # Kodi is shutting down.
        if common.get_bool("disconnect_on_exit", False) and vpn.is_running():
            common.log("Disconnecting on exit")
            vpn.disconnect(quiet=True)


if __name__ == "__main__":
    common.log("ProtonVPN service starting")
    common.ensure_profile()
    ProtonService().loop()
    common.log("ProtonVPN service stopped")
