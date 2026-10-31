#!/usr/bin/env python3
"""Wi-Fi -> location mapping: precedence, fallbacks, caching, and SSID parsing."""
import copy
import importlib.util
import importlib.machinery
import urllib.parse
from pathlib import Path

import _wx

wx = _wx.load()

REAL_SSID = wx.active_ssid           # keep it: monkeypatching must be reversible
REAL_SH = wx.sh
fails = []
GEOCODE = {"Ljubljana": (46.0546, 14.5058), "Maribor": (46.5547, 15.6459),
           "Zagorje ob Savi": (46.1318, 14.9969)}
calls = []


def fake_http(url, timeout):
    calls.append(url)
    if "geocoding-api" in url:
        name = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["name"][0]
        if name not in GEOCODE:
            raise RuntimeError("unknown place")
        lat, lon = GEOCODE[name]
        return {"results": [{"latitude": lat, "longitude": lon, "name": name}]}
    raise RuntimeError("no IP geolocation in tests")


wx.http_json = fake_http


def base_cfg(**over):
    cfg = {"networks": {"Home-5G": "Zagorje ob Savi", "Office": "Maribor"},
           "place_coords": {}, "place": "auto", "latitude": 46.0546,
           "longitude": 14.5058, "place_name": "Ljubljana", "timeout": 5}
    cfg.update(over)
    return cfg


def resolve(ssid, cfg):
    """resolve_place under a chosen SSID -> flat dict of what it decided."""
    cfg = copy.deepcopy(cfg)          # every case gets its own cache dict
    wx.active_ssid = lambda c: ssid
    calls.clear()
    try:
        lat, lon, label, src = wx.resolve_place(cfg)
    finally:
        wx.active_ssid = REAL_SSID
    return {"lat": lat, "lon": lon, "label": label, "src": src,
            "cfg": cfg, "calls": len(calls)}


def check(name, cond, detail=""):
    print(f"{'ok  ' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        fails.append(name)


# ---- precedence and fallbacks
r = resolve("Home-5G", base_cfg())
check("mapped SSID beats the pinned default",
      (r["label"], r["src"]) == ("Zagorje ob Savi", "Wi-Fi Home-5G"),
      f"({r['label']}, {r['src']})")
r = resolve("Office", base_cfg())
check("second network maps to its own place",
      (r["label"], round(r["lon"], 4)) == ("Maribor", 15.6459), f"({r['label']})")
r = resolve("CafeGuest", base_cfg())
check("unmapped SSID uses the default", (r["label"], r["src"]) == ("Ljubljana", "default"),
      f"({r['label']}, {r['src']})")
r = resolve(None, base_cfg())
check("no Wi-Fi uses the default", (r["label"], r["src"]) == ("Ljubljana", "default"))

# ---- caching
r1 = resolve("Home-5G", base_cfg(networks={"Home-5G": "Maribor"}))
r2 = resolve("Home-5G", r1["cfg"])
check("coordinates cached in config",
      r2["cfg"]["place_coords"].get("Maribor") == [46.5547, 15.6459],
      f"({r2['cfg']['place_coords']})")
check("first lookup geocodes, second does not", (r1["calls"], r2["calls"]) == (1, 0),
      f"({r1['calls']} then {r2['calls']} calls)")

# ---- a broken mapping must not lose the location
r = resolve("Broken", base_cfg(networks={"Broken": "Nodoesuchplace"}))
check("unresolvable mapping falls back to the default",
      (r["label"], r["src"]) == ("Ljubljana", "default"), f"({r['label']}, {r['src']})")

# ---- explicit coordinates in the table skip geocoding
r = resolve("Flat", base_cfg(networks={"Flat": {"name": "Flatville",
                                                "latitude": 45.5, "longitude": 14.5}}))
check("dict entry with lat/lon used verbatim, no geocode",
      (r["label"], r["lat"], r["lon"], r["calls"]) == ("Flatville", 45.5, 14.5, 0),
      f"({r['label']}, {r['lat']}, {r['lon']}, {r['calls']} calls)")

# ---- the default pin must survive a network hit
r = resolve("Home-5G", base_cfg(networks={"Home-5G": "Maribor"}))
cfg = r["cfg"]
check("default pin untouched by a network hit",
      (cfg["latitude"], cfg["longitude"], cfg["place_name"]) ==
      (46.0546, 14.5058, "Ljubljana"), f"({cfg['latitude']}, {cfg['longitude']})")

# ---- SSID detection
class FakeSh:
    """Stand in for nmcli: association query and profile list, separately."""
    def __init__(self, wifi_out, conn_out=""):
        self.wifi_out, self.conn_out = wifi_out, conn_out
        self.n = 0

    def __call__(self, cmd, **kw):
        self.n += 1
        out = (self.wifi_out if cmd[:4] == ["nmcli", "-t", "-f", "active,ssid"]
               else self.conn_out)
        return type("R", (), {"stdout": out, "returncode": 0, "stderr": ""})()


wx.sh = FakeSh("no:Guest\nyes:Home:5G\n")
got = REAL_SSID({"networks": {"x": "y"}})
check("SSID containing ':' parsed intact", got == "Home:5G", f"({got!r})")

sh = FakeSh("no:Guest\nno:Other\n", "CafeProfile:802-11-wireless:wlp42s0\nlo:loopback:lo\n")
wx.sh = sh
got = REAL_SSID({"networks": {"x": "y"}})
check("falls back to the active wireless profile name", got == "CafeProfile", f"({got!r})")

sh = FakeSh("\n", "lo:loopback:lo\n")
wx.sh = sh
check("wired machine reports no network", REAL_SSID({"networks": {"x": "y"}}) is None)

sh = FakeSh("", "")
wx.sh = sh
check("no nmcli call when no networks are configured",
      REAL_SSID({"networks": {}}) is None and sh.n == 0, f"({sh.n} calls)")


def boom(cmd, **kw):
    raise OSError("nmcli missing")


wx.sh = boom
check("missing nmcli degrades to None", REAL_SSID({"networks": {"a": "b"}}) is None)
wx.sh = REAL_SH

print("\n" + ("ALL NETWORK CHECKS PASSED" if not fails else f"FAILURES: {fails}"))
