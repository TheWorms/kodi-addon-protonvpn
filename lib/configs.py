# -*- coding: utf-8 -*-
#
# ProtonVPN
# Discovery and parsing of ProtonVPN configuration files (OpenVPN + WireGuard).
#
# The user imports their configuration files (downloaded from the ProtonVPN
# dashboard) into the addon, or points it at a folder. Two backends are
# supported and auto-detected from the file content:
#   - OpenVPN   (*.ovpn)            : "remote"/"proto" directives
#   - WireGuard (*.conf, [Interface]/[Peer])
# Every file already contains the credentials it needs (CA + tls-crypt key for
# OpenVPN, the key pair for WireGuard), so nothing sensitive is hardcoded.

import os
import re
import glob

import xbmcvfs

from lib import common

# --- OpenVPN file-name / content patterns ----------------------------------
# Names look like: lu-10_protonvpn_udp.ovpn, nl-01.protonvpn.udp.ovpn,
# node-nl-15.protonvpn.net.udp.ovpn, us-ny-03.protonvpn.tcp.ovpn
_CC_RE = re.compile(r"(?:^|node-)([a-z]{2})[-_]", re.IGNORECASE)
_REMOTE_RE = re.compile(r"^\s*remote\s+(\S+)\s+(\d+)", re.IGNORECASE | re.MULTILINE)
_PROTO_RE = re.compile(r"^\s*proto\s+(tcp|udp)", re.IGNORECASE | re.MULTILINE)

# --- WireGuard patterns ----------------------------------------------------
_WG_LABEL_RE = re.compile(r"#\s*([A-Za-z]{2})#(\d+)")
_WG_NAME_RE = re.compile(r"([A-Za-z]{2})[-_#](\d+)")
_WG_ENDPOINT_RE = re.compile(r"^\s*Endpoint\s*=\s*\[?([^\]\s:]+)\]?:(\d+)",
                             re.IGNORECASE | re.MULTILINE)


# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------

def _read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            return fh.read()
    except OSError as exc:
        common.error("Could not read %s: %s" % (path, exc))
        return ""


def _write_text(path, text):
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return True
    except OSError as exc:
        common.error("Could not write %s: %s" % (path, exc))
        return False


def _store_base():
    # An addon-managed, auto-created folder under userdata so the user never has
    # to browse to it: special://profile -> <userdata>/ProtonVPN/
    base = xbmcvfs.translatePath("special://profile/ProtonVPN")
    if not os.path.isdir(base):
        try:
            os.makedirs(base)
        except OSError:
            pass
    return base


def _profile_sub(name):
    path = os.path.join(_store_base(), name)
    if not os.path.isdir(path):
        try:
            os.makedirs(path)
        except OSError:
            pass
    return path


def store_base():
    return _store_base()


def wg_store():
    return _profile_sub("wg")


def ovpn_store():
    return _profile_sub("ovpn")


def run_dir():
    return _profile_sub("run")


# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------

def _detect_backend(path, text):
    low = text.lower()
    if "[interface]" in low and "[peer]" in low:
        return "wireguard"
    if "remote " in text or text.lstrip().startswith("client") \
            or path.lower().endswith(".ovpn"):
        return "openvpn"
    if path.lower().endswith(".conf"):
        return "wireguard"
    return ""


# ---------------------------------------------------------------------------
# OpenVPN parsing
# ---------------------------------------------------------------------------

def _label_from_name(filename):
    base = os.path.basename(filename)
    # Strip ".protonvpn..." or "_protonvpn_..." tail and the .ovpn extension.
    base = re.sub(r"[._]protonvpn.*$", "", base, flags=re.IGNORECASE)
    base = re.sub(r"\.ovpn$", "", base, flags=re.IGNORECASE)
    base = base.replace("node-", "")
    return base


def _country_from(filename, text):
    m = _CC_RE.search(os.path.basename(filename))
    if m:
        return m.group(1).upper()
    rm = _REMOTE_RE.search(text)
    if rm:
        dm = _CC_RE.search(rm.group(1))
        if dm:
            return dm.group(1).upper()
    return "??"


def _parse_openvpn(path, text):
    if "remote " not in text and "remote\t" not in text:
        return None
    proto_m = _PROTO_RE.search(text)
    remote_m = _REMOTE_RE.search(text)
    country = _country_from(path, text)
    return {
        "id": os.path.basename(path),
        "path": os.path.abspath(path),
        "backend": "openvpn",
        "country": country,
        "country_name": common.country_name(country),
        "label": _label_from_name(path),
        "proto": (proto_m.group(1).lower() if proto_m else "udp"),
        "remote": (remote_m.group(1) if remote_m else ""),
        "port": (int(remote_m.group(2)) if remote_m else 1194),
    }


# ---------------------------------------------------------------------------
# WireGuard parsing
# ---------------------------------------------------------------------------

def _parse_wireguard(path, text):
    cc, num = "", ""
    m = _WG_LABEL_RE.search(text)
    if not m:
        m = _WG_NAME_RE.search(os.path.basename(path))
    if m:
        cc, num = m.group(1).upper(), m.group(2)
    label = ("%s#%s" % (cc, num)) if cc else os.path.splitext(os.path.basename(path))[0]
    ep = _WG_ENDPOINT_RE.search(text)
    remote = ep.group(1) if ep else ""
    port = int(ep.group(2)) if ep else 51820
    country = cc or "??"
    return {
        "id": os.path.basename(path),
        "path": os.path.abspath(path),
        "backend": "wireguard",
        "country": country,
        "country_name": common.country_name(country),
        "label": label,
        "proto": "wireguard",
        "remote": remote,
        "port": port,
    }


def parse_config(path):
    """Return a dict describing one config file, or None if not parseable."""
    text = _read_text(path)
    if not text:
        return None
    backend = _detect_backend(path, text)
    if backend == "wireguard":
        return _parse_wireguard(path, text)
    if backend == "openvpn":
        return _parse_openvpn(path, text)
    return None


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def _wg_iface_for(label):
    slug = re.sub(r"[^a-z0-9]", "", (label or "").lower())[:10] or "wg"
    return "pvpn-" + slug


def import_file(src):
    """Copy a user-selected config file into the managed store and return its
    parsed entry (with key ``_existed`` set True when an identical target was
    already present), or None if the file is not a supported config."""
    src = xbmcvfs.translatePath(src)
    text = _read_text(src)
    if not text:
        return None
    backend = _detect_backend(src, text)
    if backend == "wireguard":
        tmp = _parse_wireguard(src, text)
        iface = _wg_iface_for(tmp["label"])
        dst = os.path.join(wg_store(), iface + ".conf")
    elif backend == "openvpn":
        base = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(src))
        if not base.lower().endswith(".ovpn"):
            base += ".ovpn"
        dst = os.path.join(ovpn_store(), base)
    else:
        return None

    if os.path.exists(dst):
        # Already imported: don't clobber, just report it back to the caller.
        cfg = parse_config(dst)
        if cfg:
            cfg["_existed"] = True
        return cfg

    if not _write_text(dst, text):
        return None
    cfg = parse_config(dst)
    if cfg:
        cfg["_existed"] = False
    return cfg


def delete_config(config_id):
    cfg = find_by_id(config_id)
    if not cfg:
        return False
    try:
        os.remove(cfg["path"])
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def config_folder():
    # The store is now auto-managed under userdata/ProtonVPN, so there is no
    # user-set folder to read. Kept for backward compatibility.
    return ""


def scan(folder=None):
    """Return parsed configs from the managed import stores plus the optional
    user folder (recursively)."""
    found = []
    seen = set()

    def _add(path):
        ap = os.path.abspath(path)
        if ap in seen:
            return
        cfg = parse_config(path)
        if cfg:
            seen.add(ap)
            found.append(cfg)

    for store in (wg_store(), ovpn_store()):
        try:
            names = os.listdir(store)
        except OSError:
            names = []
        for name in names:
            _add(os.path.join(store, name))

    folder = folder if folder is not None else config_folder()
    if folder and os.path.isdir(folder):
        for root, _dirs, _files in os.walk(folder):
            for pattern in ("*.ovpn", "*.conf"):
                for path in glob.glob(os.path.join(root, pattern)):
                    _add(path)

    found.sort(key=lambda c: (c["country_name"], c["backend"], c["label"]))
    return found


def group_by_country(configs):
    buckets = {}
    for cfg in configs:
        buckets.setdefault(cfg["country"], []).append(cfg)
    rows = []
    for code, items in buckets.items():
        rows.append((code, common.country_name(code), items))
    rows.sort(key=lambda r: r[1])
    return rows


def filter_protocol(configs, proto):
    """proto is 'udp', 'tcp' or '' for both. Only applies to OpenVPN configs;
    WireGuard configs are always kept (protocol selection is not applicable)."""
    if not proto:
        return configs
    return [c for c in configs
            if c["backend"] != "openvpn" or c["proto"] == proto]


def find_by_id(config_id):
    for cfg in scan():
        if cfg["id"] == config_id:
            return cfg
    return None
