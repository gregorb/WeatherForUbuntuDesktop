#!/usr/bin/env python3
"""Provider checks: ARSO field conversion, unit handling, and the fallback chain."""
import importlib.util
import importlib.machinery
import json
from pathlib import Path

import _wx

wx = _wx.load()

fails = []


def check(name, cond, detail=""):
    print(f"{'ok  ' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        fails.append(name)


# ---------- icon decoding
cases = [("clear_night", 0, False), ("clear_day", 0, True),
         ("partCloudy_night", 1, False), ("prevCloudy_day", 2, True),
         ("overcast_night", 3, False), ("overcast_lightRA_day", 61, True),
         ("overcast_modRA_night", 63, False), ("lightRA", 61, None),
         ("modRA", 63, None), ("lightFG", 45, None),
         ("prevCloudy_lightFG_night", 45, False),
         ("overcast_heavySN_day", 75, True), ("", None, None)]
got = [wx.arso_decode(c) for c, *_ in cases]
check("ARSO icons decode to WMO codes + day/night",
      all(g == (exp_code, exp_day) for g, (_, exp_code, exp_day) in zip(got, cases)),
      f"{[g for g in got]}")

# ---------- wind direction: English icon preferred, Slovene letters as fallback
check("direction from English ddff_icon",
      wx.arso_direction({"ddff_icon": "lightSW", "dd_shortText": "JZ"}) == 225.0)
check("direction from Slovene dd_shortText (S = sever = north)",
      wx.arso_direction({"ddff_icon": "", "dd_shortText": "S"}) == 0.0
      and wx.arso_direction({"ddff_icon": "", "dd_shortText": "JV"}) == 135.0)

# ---------- queries: ARSO titles are shorter than what users type
q = wx._arso_queries("Zagorje ob Savi")
check("progressive queries, longest first", q[:3] == ["Zagorje ob Savi", "Zagorje ob", "Zagorje"],
      f"({q[:3]})")
check("diacritic-free retry present", "Brezice" in wx._arso_queries("Brežice"),
      f"({wx._arso_queries('Brežice')})")
check("trailing country suffix dropped", wx._arso_queries("Maribor, SI")[:2] == ["Maribor SI", "Maribor"])

# ---------- live conversion, checked against the raw ARSO payload
real_http = wx.http_json
raw = {}


def spy_http(url, timeout):
    body = real_http(url, timeout)
    if "api/1.0/location/" in url:
        raw["location"] = body
    return body


wx.http_json = spy_http
cfg = dict(wx.DEFAULTS)
cfg["units"] = "metric"
metric = wx.fetch_arso(46.1318, 14.9969, cfg, "Zagorje ob Savi")
row = raw["location"]["observation"]["features"][0]["properties"]["days"][0]["timeline"][-1]
day = raw["location"]["observation"]["features"][0]["properties"]["days"][0]

cur = metric["current"]
check("temperature passed through", abs(cur["temperature_2m"] - float(row["t"])) < 0.01,
      f"({cur['temperature_2m']} vs raw {row['t']})")
check("humidity passed through", cur["relative_humidity_2m"] == float(row["rh"]))
check("wind converted m/s -> km/h",
      abs(cur["wind_speed_10m"] - round(float(row["ff_val"]) * 3.6, 1)) < 0.11,
      f"({cur['wind_speed_10m']} km/h from {row['ff_val']} m/s)")
check("UTC observation time shifted to local",
      cur["time"][11:16] != row["valid"][11:16] or row["valid"].endswith("+01:00"),
      f"(raw {row['valid']} -> local {cur['time']})")
_dawn, _dusk = int(day["sunrise"][11:13]), int(day["sunset"][11:13])
_want_day = 1 if _dawn <= int(cur["time"][11:13]) < _dusk else 0
check("day/night recognised against the local clock",
      cur["is_day"] == _want_day,
      f"(local {cur['time'][11:16]}, dawn {_dawn:02d}, dusk {_dusk:02d}, "
      f"is_day={cur['is_day']})")
check("sunrise/sunset passed in the shape the renderer reads",
      metric["daily"]["sunrise"][0][11:16] == day["sunrise"][11:16]
      and metric["daily"]["sunset"][0][11:16] == day["sunset"][11:16],
      f"({metric['daily']['sunrise'][0][11:16]}, {metric['daily']['sunset'][0][11:16]})")
check("daily high/low from ARSO txsyn/tnsyn",
      metric["daily"]["temperature_2m_max"] and metric["daily"]["temperature_2m_min"],
      f"({metric['daily']['temperature_2m_max']}/{metric['daily']['temperature_2m_min']})")
check("feels-like absent, not fabricated", cur["apparent_temperature"] is None)
check("provider labelled", metric["provider"] == "ARSO" and metric["provider_place"] == "Zagorje")

hh = metric["hourly"]
check("hourly series is long enough for the strip", len(hh["time"]) >= 12, f"({len(hh['time'])} rows)")
check("hourly precip declared as millimetres", hh["precip_kind"] == "mm")
check("hourly precipitation never negative", all(p >= 0 for p in hh["precip"]))
check("hourly stamps strictly increasing",
      all(hh["time"][i] < hh["time"][i + 1] for i in range(len(hh["time"]) - 1)))
check("every hour has a decodable condition code",
      all(0 <= c <= 99 for c in hh["weather_code"]))

cfg_i = dict(wx.DEFAULTS)
cfg_i["units"] = "imperial"
imp = wx.fetch_arso(46.1318, 14.9969, cfg_i, "Zagorje ob Savi")
check("imperial converts temperature",
      abs(imp["current"]["temperature_2m"] - (metric["current"]["temperature_2m"] * 9 / 5 + 32)) < 0.11,
      f"({imp['current']['temperature_2m']}F vs {metric['current']['temperature_2m']}C)")
_ms = metric["current"]["wind_speed_10m"] / 3.6          # km/h back to m/s
check("imperial converts wind by the right factor",
      abs(imp["current"]["wind_speed_10m"] - _ms * 2.23694) <= 0.11,
      f"({imp['current']['wind_speed_10m']} mph vs {metric['current']['wind_speed_10m']} km/h, "
      f"{_ms:.1f} m/s)")

# ---------- fallback chain
log_lines = []
wx.log = lambda m: log_lines.append(m)


def arso_down(url, timeout):
    if "vreme.si" in url:
        raise RuntimeError("simulated ARSO outage")
    return real_http(url, timeout)


wx.http_json = arso_down
out = wx.fetch_weather(46.1318, 14.9969, dict(wx.DEFAULTS), "Zagorje ob Savi")
check("ARSO outage falls back to Open-Meteo", out["provider"] == "Open-Meteo",
      f"({out['provider']})")
check("fallback is logged", any("fell back" in l for l in log_lines), f"({log_lines[-1][:70]})")

log_lines.clear()
wx.http_json = lambda url, timeout: (_ for _ in ()).throw(RuntimeError("everything is down"))
try:
    wx.fetch_weather(46.1318, 14.9969, dict(wx.DEFAULTS), "Zagorje ob Savi")
    check("total outage raises so the caller can use its cache", False, "(nothing raised)")
except RuntimeError as exc:
    msg = str(exc)
    check("total outage raises so the caller can use its cache",
          "no weather provider answered" in msg, f"({msg})")
    check("both failures named in the error", "arso" in msg and "open-meteo" in msg)

wx.http_json = real_http
only_arso = dict(wx.DEFAULTS)
only_arso["providers"] = ["arso"]
d = wx.fetch_weather(46.1318, 14.9969, only_arso, "Zagorje ob Savi")
check("providers list is honoured (arso only)", d["provider"] == "ARSO")
only_om = dict(wx.DEFAULTS)
only_om["providers"] = ["open-meteo"]
check("providers list is honoured (open-meteo only)",
      wx.fetch_weather(46.1318, 14.9969, only_om, "Zagorje ob Savi")["provider"] == "Open-Meteo")
bad = dict(wx.DEFAULTS)
bad["providers"] = ["bogus", "open-meteo"]
check("unknown provider name skipped, next one used",
      wx.fetch_weather(46.1318, 14.9969, bad, "Zagorje ob Savi")["provider"] == "Open-Meteo")

# a location ARSO does not cover must silently move to the fallback
check("non-Slovenian place falls back",
      wx.fetch_weather(52.52, 13.405, dict(wx.DEFAULTS), "Berlin")["provider"] == "Open-Meteo")

wx.log = lambda m: print(f"[wx-wallpaper] {m}", file=__import__("sys").stderr)
print("\n" + ("ALL PROVIDER CHECKS PASSED" if not fails else f"FAILURES: {fails}"))
