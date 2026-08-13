# -*- coding: utf-8 -*-
#
# ProtonVPN
# Background service: optional auto-connect at boot, reconnect on drop,
# keep window-property state up to date, optional disconnect on shutdown.

import os
import time

import xbmc

from lib import common
from lib import vpn
from lib import configs
from lib import stats


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
        # 1) random favourite
        if common.get_bool("random_favorite", False):
            favs = configs.load_favorites()
            if favs:
                import random
                cfg = configs.find_by_id(random.choice(favs))
                if cfg:
                    common.log("Auto-connect: random favourite %s" % cfg["label"])
                    self.expected = True
                    vpn.connect(cfg, quiet=True)
                    return
        # 2) explicitly chosen server
        aid = common.get_setting("autoconnect_id", "")
        if aid:
            cfg = configs.find_by_id(aid)
            if cfg:
                common.log("Auto-connect: chosen server %s" % cfg["label"])
                self.expected = True
                vpn.connect(cfg, quiet=True)
                return
        # 3) fallback: last server, else first of default protocol
        last = common.get_setting("last_config", "")
        if last and os.path.exists(last):
            cfg = configs.parse_config(last)
            if cfg:
                common.log("Auto-connecting to last server %s" % cfg["label"])
                self.expected = True
                vpn.connect(cfg, quiet=True)
                return
        backend = common.get_setting("default_protocol", "wireguard")
        all_cfg = [c for c in configs.scan() if c["backend"] == backend] or configs.scan()
        if all_cfg:
            common.log("Auto-connecting to %s" % all_cfg[0]["label"])
            self.expected = True
            vpn.connect(all_cfg[0], quiet=True)

    def loop(self):
        try:
            configs.refresh_counts()
            stats.publish_home_props()
        except Exception:
            pass
        if common.get_bool("auto_connect", False):
            self.auto_connect()
        elif vpn.is_running():
            # Auto-connect is off: don't keep a tunnel left up by a previous
            # session (WireGuard interfaces survive a Kodi restart).
            common.log("Auto-connect off: tearing down leftover tunnel")
            vpn.disconnect(quiet=True)

        common.set_state(vpn.is_running(), server=common.get_state().get("server", ""))
        if vpn.is_running():
            self.expected = True
            common.set_phase(common.PHASE_CONNECTED)

        fails = 0
        disconnect_on_exit = common.get_bool("disconnect_on_exit", False)
        last_monitor = 0.0
        while not self.abortRequested():
            # Tick every second while connected so the widget's Durée/Trafic
            # update live; fall back to the slower interval when idle.
            wait = 1 if vpn.is_running() else self._check_interval()
            if self.waitForAbort(wait):
                break

            running = vpn.is_running()
            self._sync_header()
            # Les ticks a 1 Hz ne font que de l'affichage : resolution de
            # l'IP externe (appels HTTPS) uniquement a la cadence monitor,
            # pour ne jamais bloquer la machine a etats sur du reseau.
            due = (time.time() - last_monitor) >= self._check_interval()
            try:
                stats.publish_home_props(resolve_ip=due)
            except Exception:
                pass

            # If the user asked to disconnect (via the add-on), honour it: don't
            # treat the down tunnel as a drop and don't auto-reconnect.
            if common.get_prop("protonvpn.desired") == "off":
                self.expected = False
                fails = 0

            # Heavy work (reconnect / state sync) only at the monitor cadence,
            # or immediately on a detected drop.
            drop = self.expected and not running
            if (time.time() - last_monitor) < self._check_interval() and not drop:
                continue
            last_monitor = time.time()
            disconnect_on_exit = common.get_bool("disconnect_on_exit", False)

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
                if common.get_prop("protonvpn.desired") == "on":
                    self.expected = True
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
