# -*- coding: utf-8 -*-
#
# ProtonVPN
# Background service: optional auto-connect at boot, reconnect on drop,
# keep window-property state up to date, optional disconnect on shutdown,
# exceptions par addon (pause du VPN).

import os
import time

import xbmc

from lib import bypass
from lib import common
from lib import exceptions
from lib import ipv6guard
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
        # Exceptions (pause du VPN)
        self.items = []
        self.items_rev = None
        self.items_ts = 0.0
        self.had_media = False
        self.play_addon = ""     # addon de la lecture en cours
        self.last_browse = ("", 0.0)
        self.resume_at = 0.0     # fin du délai avant de relancer le tunnel

    _ITEMS_EVERY = 30       # secondes : liste des exceptions relue au plus tard
    _BROWSE_MEMORY = 10     # secondes : addon parcouru juste avant une lecture

    def onSettingsChanged(self):
        self._reload(force=True)

    # --- exceptions : pause du VPN ------------------------------------------

    def _reload(self, force=False):
        rev = exceptions.rev()
        if not force and rev == self.items_rev and \
                time.time() - self.items_ts < self._ITEMS_EVERY:
            return
        self.items = exceptions.load()
        self.items_rev = rev
        self.items_ts = time.time()

    def _pause(self, addon_id):
        name = exceptions.addon_name(addon_id)
        common.set_prop(exceptions.PROP_PAUSED, addon_id)
        common.set_prop(exceptions.PROP_PAUSED_CFG, common.get_setting("last_config", ""))
        self.expected = False
        self.resume_at = 0.0
        vpn.disconnect(quiet=True, pause=True)
        common.set_state(False)
        common.set_phase(common.PHASE_DISCONNECTED)
        common.event("Pause du VPN : %s" % name)
        common.notify(common.L(32255) % name)

    def _clear_pause(self):
        common.set_prop(exceptions.PROP_PAUSED, "")
        common.set_prop(exceptions.PROP_PAUSED_CFG, "")
        self.resume_at = 0.0

    def _resume(self, reason):
        cfg = common.get_prop(exceptions.PROP_PAUSED_CFG)
        self._clear_pause()
        if common.get_prop("protonvpn.desired") == "off":
            return
        common.event("Fin de la pause du VPN (%s) : reconnexion" % reason)
        self.expected = True  # en cas d'échec, la reconnexion auto prend le relais
        ok = vpn.connect(cfg, quiet=True) if cfg else vpn.reconnect_last(quiet=True)
        if ok:
            common.set_state(True, server=common.get_state().get("server", ""))
            common.set_phase(common.PHASE_CONNECTED)
            common.notify(common.L(32256))

    def _exceptions_tick(self, running):
        self._reload()
        ids = exceptions.active_ids(self.items)
        now = time.time()

        browse = exceptions.browsing()
        if browse:
            self.last_browse = (browse, now)
        addon = exceptions.playing()
        has_media = addon is not None
        if has_media and not self.had_media:
            # Début de lecture : addon d'origine, à défaut celui qu'on parcourait.
            recent = self.last_browse[0] if now - self.last_browse[1] < self._BROWSE_MEMORY else ""
            self.play_addon = addon or recent
        if not has_media:
            self.play_addon = ""
        self.had_media = has_media

        paused = common.get_prop(exceptions.PROP_PAUSED)
        if paused and (running or common.get_prop("protonvpn.desired") == "off"):
            self._clear_pause()  # connexion ou déconnexion manuelle pendant la pause
            paused = ""
        trigger = browse if browse in ids else ""
        if not trigger and has_media and self.play_addon in ids:
            trigger = self.play_addon
        if trigger:
            self.resume_at = 0.0
            if not paused and running:
                self._pause(trigger)
            return
        if not paused:
            return
        if has_media:
            self._resume("lecture hors exceptions")  # autre addon, fichier local...
            return
        if not self.resume_at:
            self.resume_at = now + max(0, common.get_int("pause_delay", 5))
        if now >= self.resume_at:
            self._resume("addon quitte")

    def _paused(self):
        return bool(common.get_prop(exceptions.PROP_PAUSED))

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
        self._reload(force=True)
        if self._paused():
            # Service relancé (mise à jour de l'addon) pendant une pause du
            # VPN : la pause continue, sa fin relancera le tunnel.
            pass
        elif common.get_bool("auto_connect", False):
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
        # Blocage IPv6 aligne sur l'etat reel du tunnel (Kodi arrete sans
        # deconnexion, tunnel WireGuard reste monte d'une session a l'autre).
        ipv6guard.sync(vpn.is_running())

        fails = 0
        disconnect_on_exit = common.get_bool("disconnect_on_exit", False)
        last_monitor = 0.0
        bypass.cleanup()  # route directe des versions 0.5.13 à 0.6.3
        while not self.abortRequested():
            # Tick every second while connected (or paused by an exception) so
            # the widget's Durée/Trafic update live and the end of a pause is
            # seen at once; fall back to the slower interval when idle.
            wait = 1 if vpn.is_running() or self._paused() else self._check_interval()
            if self.waitForAbort(wait):
                break

            running = vpn.is_running()
            self._sync_header()
            try:
                self._exceptions_tick(running)
            except Exception as exc:  # jamais bloquant pour le service
                common.log("exceptions : %s" % exc)
            running = vpn.is_running()
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
                    ipv6guard.sync(False)
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
                        ipv6guard.sync(False)
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
                ipv6guard.sync(True)

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
