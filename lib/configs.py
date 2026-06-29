# -*- coding: utf-8 -*-
#
# ProtonVPN
# Discovery and parsing of ProtonVPN OpenVPN configuration files.
#
# The reliable, API-free core of the addon: the user downloads their OpenVPN
# config files from the ProtonVPN dashboard (Downloads -> OpenVPN configuration
# files) and points the addon at the folder. Every .ovpn already contains the
# correct CA certificate and tls-crypt key, so nothing sensitive is hardcoded.

import os
import re
import glob

import xbmcvfs

from lib import common

# ProtonVPN file names look like:
#   nl-01.protonvpn.udp.ovpn
#   node-nl-15.protonvpn.net.udp.ovpn
#   us-ny-03.protonvpn.tcp.ovpn
#   is-free-01.protonvpn.udp.ovpn
# We extract the leading ISO country code and a short label for display.

_CC_RE = re.compile(r"(?:^|node-)([a-z]{2})[-_]", re.IGNORECASE)
_REMOTE_RE = re.compile(r"^\s*remote\s+(\S+)\s+(\d+)", re.IGNORECASE | re.MULTILINE)
_PROTO_RE = re.compile(r"^\s*proto\s+(tcp|udp)", re.IGNORECASE | re.MULTILINE)


def _read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            return fh.read()
    except OSError as exc:
        common.error("Could not read %s: %s" % (path, exc))
        return ""


def _label_from_name(filename):
    # Strip the ".protonvpn.*.ovpn" tail, keep the meaningful part.
    base = os.path.basename(filename)
    base = re.sub(r"\.protonvpn.*$", "", base, flags=re.IGNORECASE)
    base = re.sub(r"\.(ovpn)$", "", base, flags=re.IGNORECASE)
    base = base.replace("node-", "")
    return base


def _country_from(filename, text):
    m = _CC_RE.search(os.path.basename(filename))
    if m:
        return m.group(1).upper()
    # Fall back to the remote domain (e.g. node-nl-15.protonvpn.net).
    rm = _REMOTE_RE.search(text)
    if rm:
        dm = _CC_RE.search(rm.group(1))
        if dm:
            return dm.group(1).upper()
    return "??"


def parse_config(path):
    """Return a dict describing one .ovpn file, or None if not parseable."""
    text = _read_text(path)
    if "remote " not in text and "remote\t" not in text:
        return None
    proto_m = _PROTO_RE.search(text)
    remote_m = _REMOTE_RE.search(text)
    country = _country_from(path, text)
    return {
        "id": os.path.basename(path),
        "path": os.path.abspath(path),
        "country": country,
        "country_name": common.country_name(country),
        "label": _label_from_name(path),
        "proto": (proto_m.group(1).lower() if proto_m else "udp"),
        "remote": (remote_m.group(1) if remote_m else ""),
        "port": (int(remote_m.group(2)) if remote_m else 1194),
    }


def config_folder():
    raw = common.get_setting("config_folder", "")
    if not raw:
        return ""
    return xbmcvfs.translatePath(raw)


def scan(folder=None):
    """Scan the configured folder (recursively) and return parsed configs."""
    folder = folder or config_folder()
    if not folder or not os.path.isdir(folder):
        return []
    found = []
    for root, _dirs, _files in os.walk(folder):
        for path in glob.glob(os.path.join(root, "*.ovpn")):
            cfg = parse_config(path)
            if cfg:
                found.append(cfg)
    # Stable sort: country, then label.
    found.sort(key=lambda c: (c["country_name"], c["label"]))
    return found


def group_by_country(configs):
    """Return an ordered list of (code, name, [configs]) grouped by country."""
    buckets = {}
    for cfg in configs:
        buckets.setdefault(cfg["country"], []).append(cfg)
    rows = []
    for code, items in buckets.items():
        rows.append((code, common.country_name(code), items))
    rows.sort(key=lambda r: r[1])
    return rows


def filter_protocol(configs, proto):
    """proto is 'udp', 'tcp' or '' for both."""
    if not proto:
        return configs
    return [c for c in configs if c["proto"] == proto]


def find_by_id(config_id):
    for cfg in scan():
        if cfg["id"] == config_id:
            return cfg
    return None
