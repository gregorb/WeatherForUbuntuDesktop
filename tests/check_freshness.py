#!/usr/bin/env python3
"""Guard the freshness rules: the retries that win the race against a network
that is still waking up after login, the unlock-triggered refresh decision, and
what a panel older than stale_after_min is still allowed to show."""
import datetime
import json
import tempfile
import time
from pathlib import Path

from PIL import Image

import _wx

wx = _wx.load()

MAGENTA = str(Path(tempfile.gettempdir()) / "wx-wallpaper-magenta.png")
Image.new("RGB", (1920, 1080), (255, 0, 255)).save(MAGENTA)
CFG = dict(wx.DEFAULTS)
CFG.update(base_light=MAGENTA, base_dark=MAGENTA, resolution="1920x1080")
W, H = 1920, 1080
fails = []


def check(name, cond, detail=""):
    print(f"{'ok  ' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        fails.append(name)


def payload(times, temps, codes=None, probs=None):
    n = len(times)
    return {
        "current": {"time": times[0], "temperature_2m": temps[0],
                    "apparent_temperature": temps[0] - 2, "relative_humidity_2m": 70,
                    "weather_code": codes[0] if codes else 2, "wind_speed_10m": 5,
                    "wind_direction_10m": 180, "is_day": 1, "precipitation": 0},
        "hourly": {"time": times, "temperature_2m": temps, "weather_code": codes,
                   "precipitation_probability": probs},
        "daily": {"temperature_2m_max": [10], "temperature_2m_min": [1],
                  "sunrise": [f"{times[0][:10]}T07:10"], "sunset": [f"{times[0][:10]}T17:05"]},
    }


# ---- 1. the login race: one failed attempt must not paint last night's weather
logs, sleeps, calls = [], [], []
real_log, real_fetch, real_time_sleep = wx.log, wx.fetch_weather, time.sleep
wx.log = logs.append
wx.time.sleep = sleeps.append          # watch the backoff without waiting for it
try:
    DNS_ERR = "[Errno -2] Name or service not known"

    def make_flaky(succeeds_on, err=DNS_ERR):
        def flaky(*_args):
            calls.append(1)
            if len(calls) < succeeds_on:
                raise RuntimeError(err)
            return {"ok": len(calls)}
        return flaky

    # every provider failing on DNS means Wi-Fi is still associating after
    # login/unlock: the retry waits a full dns_retry_wait, flat
    wx.fetch_weather = make_flaky(3)
    out = wx.fetch_weather_retry(0, 0, {"fetch_retries": 2, "dns_retry_wait": 60}, "x")
    check("a third attempt still beats the login race", out == {"ok": 3},
          f"({len(calls)} attempts)")
    check("a pure DNS outage retries a minute later, every time",
          sleeps == [60, 60], f"({sleeps})")
    check("the journal names the likely culprit",
          any("Wi-Fi still connecting" in m for m in logs), f"({logs!r})")

    # other failures (server down, route black-holing) keep the short ladder
    calls.clear(); sleeps.clear(); logs.clear()
    wx.fetch_weather = make_flaky(3, err="The read operation timed out")
    wx.fetch_weather_retry(0, 0, {"fetch_retries": 2, "fetch_retry_wait": 4}, "x")
    check("non-DNS failures keep the short doubling ladder", sleeps == [4, 8],
          f"({sleeps})")
    check("...and the default DNS wait is one minute",
          "dns_retry_wait" in json.dumps(wx.DEFAULTS)
          and wx.DEFAULTS["dns_retry_wait"] == 60)

    calls.clear(); sleeps.clear()
    wx.fetch_weather = make_flaky(99)
    try:
        wx.fetch_weather_retry(0, 0, {"fetch_retries": 1, "dns_retry_wait": 0}, "x")
        check("total outage still raises, so main() reaches the cache", False)
    except RuntimeError:
        check("total outage still raises, so main() reaches the cache",
              len(calls) == 2, f"({len(calls)} attempts)")

    calls.clear(); sleeps.clear()
    wx.fetch_weather = make_flaky(1)
    wx.fetch_weather_retry(0, 0, {}, "x")
    check("a working network is not delayed (defaults: 2 retries, 15 s base)",
          len(calls) == 1 and sleeps == [])
finally:
    wx.log, wx.fetch_weather = real_log, real_fetch
    wx.time.sleep = real_time_sleep

# ---- 1b. classifying *why* the whole chain failed
import socket
import urllib.error

gai = socket.gaierror(-2, "Name or service not known")
wrapped = urllib.error.URLError(gai)          # what urlopen actually raises
both_dns = wx.WeatherUnavailable({"arso": wrapped, "open-meteo": gai})
mixed = wx.WeatherUnavailable({"arso": wrapped, "open-meteo": RuntimeError("HTTP 500")})
check("gaierror, its URLError wrapper and bare text all read as DNS",
      wx.is_dns_outage(gai) and wx.is_dns_outage(wrapped)
      and wx.is_dns_outage(RuntimeError(f"<urlopen error {DNS_ERR}>")))
check("every provider on DNS is an outage", bool(wx.is_dns_outage(both_dns)))
check("one provider answering-with-500 means it is not a DNS outage",
      not wx.is_dns_outage(mixed))
check("timeouts are not DNS",
      not wx.is_dns_outage(RuntimeError("The read operation timed out")))
check("WeatherUnavailable still reads as a RuntimeError to main()",
      isinstance(both_dns, RuntimeError)
      and "arso" in str(both_dns) and "open-meteo" in str(both_dns))

def down_arso(*_a, **_k):
    raise gai


def down_om(*_a, **_k):
    raise wrapped


real_arso, real_om = wx.fetch_arso, wx.fetch_open_meteo
wx.fetch_arso, wx.fetch_open_meteo = down_arso, down_om
wx.log = logs.append
try:
    try:
        wx.fetch_weather(0, 0, {}, "x")
        check("fetch_weather raises WeatherUnavailable with per-provider causes", False)
    except wx.WeatherUnavailable as exc:
        check("fetch_weather raises WeatherUnavailable with per-provider causes",
              set(exc.failures) == {"arso", "open-meteo"} and wx.is_dns_outage(exc))
finally:
    wx.log = real_log
    wx.fetch_arso, wx.fetch_open_meteo = real_arso, real_om

# ---- 2. the unlock decision (watch_unlock feeds each gdbus monitor line
#      joined with the one before it: current gdbus prints the whole signal
#      on one line, '...ActiveChanged (false,)', older builds split the
#      boolean onto the line after the member=ActiveChanged header)
UNLOCK = ("signal sender=:1.63 -> dest=(null destination) serial=245 "
          "path=/org/gnome/ScreenSaver; interface=org.gnome.ScreenSaver; "
          "member=ActiveChanged\n   boolean false")
LOCK = UNLOCK.replace("boolean false", "boolean true")
NOISE = ("signal sender=:1.63 -> dest=(null destination) serial=246 "
         "path=/org/gnome/ScreenSaver; interface=org.freedesktop.DBus.Properties; "
         "member=PropertiesChanged   s \"org.gnome.ScreenSaver\"")
check("an unlock line is recognised", wx.unlock_seen(UNLOCK))
check("a lock is not", not wx.unlock_seen(LOCK))
check("other ScreenSaver traffic is not", not wx.unlock_seen(NOISE))
NEW_UNLOCK = ("/org/gnome/ScreenSaver: org.gnome.ScreenSaver.ActiveChanged (false,)\n")
NEW_LOCK = ("/org/gnome/ScreenSaver: org.gnome.ScreenSaver.ActiveChanged (true,)\n")
NEW_NOISE = ("/org/gnome/ScreenSaver: org.freedesktop.DBus.Properties."
             "PropertiesChanged ('org.gnome.ScreenSaver', {'Active': <false>}, [])\n")
check("the one-line gdbus format is recognised", wx.unlock_seen(NEW_UNLOCK))
check("...its lock is not", not wx.unlock_seen(NEW_LOCK))
check("...its PropertiesChanged noise is not", not wx.unlock_seen(NEW_NOISE))


def unlocks(lines):
    """How many unlocks watch_unlock sees in a stream of monitor lines."""
    hits, prev = 0, ""
    for line in lines:
        if wx.unlock_seen(prev + line):
            hits, prev = hits + 1, ""
        else:
            prev = line if "ActiveChanged" in line else ""
    return hits


check("a legacy signal split over two lines is still one unlock",
      unlocks(UNLOCK.split("\n", 1)) == 1)
check("a legacy lock right after an unlock is not mistaken for another unlock",
      unlocks([UNLOCK.split("\n", 1)[1], *LOCK.split("\n", 1)]) == 0)
check("a session's worth of both formats yields exactly its two unlocks",
      unlocks([NEW_LOCK, NEW_NOISE, *UNLOCK.split("\n", 1), NEW_UNLOCK]) == 2)

base = {"refresh_on_unlock": True, "unlock_min_gap": 300}
check("unlocked with no cached reading at all: refresh", wx.unlock_refresh_due(UNLOCK, base, None))
check("unlocked with a 10-minute-old reading: refresh", wx.unlock_refresh_due(UNLOCK, base, 600))
check("unlocked seconds after a timer run: stay put", not wx.unlock_refresh_due(UNLOCK, base, 60))
check("a lock never refreshes, however stale the cache", not wx.unlock_refresh_due(LOCK, base, None))
check("refresh_on_unlock=false is honoured",
      not wx.unlock_refresh_due(UNLOCK, {"refresh_on_unlock": False}, None))
check("unlock_min_gap=0 refreshes on every unlock",
      bool(wx.unlock_refresh_due(UNLOCK, {"unlock_min_gap": 0}, 1)))
check("the one-line unlock format carries the same decision",
      wx.unlock_refresh_due(NEW_UNLOCK, base, 600)
      and not wx.unlock_refresh_due(NEW_LOCK, base, None))

# ---- 3. what a panel older than stale_after_min may still show
now = datetime.datetime.now()
# start half an hour off the hour so no cell ever lands exactly on the
# 60-minute staleness boundary and makes the expectation time-dependent
start = now - datetime.timedelta(hours=10, minutes=30)
times = [(start + datetime.timedelta(hours=k)).strftime("%Y-%m-%dT%H:%M")
         for k in range(12)]
temps = [8, 7, 7, 6, 6, 5, 5, 6, 7, 8, 9, 10]
codes = [1, 2, 3, 61, 63, 95, 71, 75, 0, 1, 2, 3]
probs = [0, 5, 20, 60, 80, 95, 40, 30, 55, 70, 0, 10]

live = payload(times, temps, codes, probs)
live["provider"] = "arso"
stale = json.loads(json.dumps(live))
stale.update(_cached="23:30", _age_min=600)

img_live = wx.render(live, CFG, "Zagorje", W, H, True).convert("RGB")
lay_live = dict(wx.LAST_LAYOUT)
img_stale = wx.render(stale, CFG, "Zagorje", W, H, True).convert("RGB")
lay_stale = dict(wx.LAST_LAYOUT)

check("a fresh render is not stale", lay_live["stale"] is False)
check("a 10-hour-old cached render is stale", lay_stale["stale"] is True)
wx.render({**json.loads(json.dumps(stale)), "_age_min": 45}, CFG, "Zagorje", W, H, True)
check("45 minutes old stays under the default 60-minute limit",
      wx.LAST_LAYOUT["stale"] is False)
wx.render(json.loads(json.dumps(stale)), {**CFG, "stale_after_min": 30},
          "Zagorje", W, H, True)
check("...and a 30-minute limit makes the same reading stale",
      wx.LAST_LAYOUT["stale"] is True)
wx.render(stale, CFG, "Zagorje", W, H, True)
lay_stale = dict(wx.LAST_LAYOUT)

check("the big number slot is left empty", lay_stale["temp_text"] == "",
      f"({lay_stale['temp_text']!r})")
check("...and it keeps exactly the space the number had",
      lay_stale["height"] == lay_live["height"],
      f"({lay_stale['height']} vs {lay_live['height']} px tall)")
def band_ink(im, box):
    """Pixels inside a window that stand out from the window's own background."""
    band = im.crop(box).convert("L")
    px = band.load()
    vals = sorted(px[x, y] for x in range(band.size[0]) for y in range(band.size[1]))
    floor = vals[len(vals) // 4] + 30
    return sum(1 for x in range(band.size[0]) for y in range(band.size[1])
               if px[x, y] > floor)


n_top, n_bot = lay_stale["temp_ink"]          # where "0°" would have been drawn
slot = (int(lay_stale["x"] + lay_stale["inner"] + 1), int(n_top) - 1,
        int(lay_stale["x"] + lay_stale["inner"] + 1 + 120 * lay_stale["scale"]),
        int(n_bot) + 1)
check("not even a dash or placeholder is drawn in the number slot",
      band_ink(img_stale, slot) <= 2, f"({band_ink(img_stale, slot)} lit pixels)")
check("a live panel does fill that same slot",
      band_ink(img_live, (lay_live["x"] + lay_live["inner"] + 1,
                          int(lay_live["temp_ink"][0]) - 1,
                          lay_live["x"] + lay_live["inner"] + 1
                          + int(120 * lay_live["scale"]),
                          int(lay_live["temp_ink"][1]) + 1)) > 40,
      "(the number is there when the data is fresh)")
check("humidity, feels-like and current rain chips are gone",
      not any(v.endswith("%") for v in lay_stale["chips"]), f"({lay_stale['chips']})")
check("today's high and low survive", lay_stale["chips"] == ["10°", "1°"],
      f"({lay_stale['chips']})")
check("a live panel still carries all the instant values",
      lay_live["temp_text"] == "8°" and sum(v.endswith("%") for v in lay_live["chips"]) == 2,
      f"({lay_live['chips']})")

behind = [b for b in lay_stale["cell_behind"]]
check("cells the clock left behind are flagged, recent ones are not",
      behind[:10] == [True] * 10 and behind[10:] == [False] * 2, f"({behind})")
check("a live panel blanks nothing", not any(lay_live["cell_behind"]))

foot = wx.footer_text(stale, now, True)
check("the footer says 'stale', not 'cached'",
      "stale" in foot and "cached" not in foot, f"({foot!r})")
check("a merely cached footer keeps saying 'cached'",
      "cached" in wx.footer_text({"_cached": "23:30"}, now))
check("a fresh footer has no stale marker", lay_live["footer_stale"] is None)


def band_max(im, x0, x1, y, hgt):
    return max(sum(im.getpixel((x, yy))[:3])
               for x in range(int(x0), int(x1)) for yy in range(int(y), int(y) + hgt))


# the word "stale" must read as the same faint ink as the panel outline, while
# the rest of the footer keeps its normal brightness
sx0, sx1, sy = lay_stale["footer_stale"]
fh = int(21 * lay_stale["scale"]) + 2
glass_ref = min(sum(img_stale.getpixel((x, int(sy) - 30))[:3])
                for x in range(int(sx0) + 2, int(sx1) - 2, 3))
stale_b = band_max(img_stale, sx0 + 1, sx1, sy, fh)      # +1 dodges pre-segment AA
prev_b = band_max(img_stale, lay_stale["x"] + lay_stale["inner"], sx0 - 4, sy, fh)
mid_x = lay_stale["x"] + lay_stale["width"] // 2
hair_b = band_max(img_stale, mid_x - 30, mid_x + 30, lay_stale["y"] + 1, 2)
d_stale, d_prev, d_hair = stale_b - glass_ref, prev_b - glass_ref, hair_b - glass_ref
check("the word 'stale' is still legible ink", d_stale > 15, f"(+{d_stale} over glass)")
check("the word 'stale' is much dimmer than the footer beside it",
      d_stale < 0.5 * d_prev, f"(+{d_stale} vs +{d_prev})")
check("the word 'stale' is as faint as the panel's hairline",
      0.25 * d_hair <= d_stale <= 2.0 * d_hair, f"(+{d_stale} vs hairline +{d_hair})")


def cell_ink(im, lay, i, top_off, height, half):
    """Ink inside one cell's content window, measured against the cell's own
    background so panel opacity does not matter."""
    mid = lay["strip_x"] + lay["cell_w"] * (i + 0.5)
    x0, x1 = int(mid - half), int(mid + half)
    top = int(lay["strip_y"] + top_off)
    band = im.crop((x0, top, x1, top + height)).convert("L")
    px = band.load()
    vals = sorted(px[x, y] for x in range(band.size[0]) for y in range(band.size[1]))
    floor = vals[len(vals) // 4] + 30
    return sum(1 for x in range(band.size[0]) for y in range(band.size[1])
               if px[x, y] > floor)


s = lay_stale["scale"]
zone = (int(21 * s), int(80 * s))          # everything below the hour label
gone = cell_ink(img_stale, lay_stale, 0, *zone, int(16 * s))
kept = cell_ink(img_stale, lay_stale, 11, *zone, int(16 * s))
check("a left-behind cell really is empty below its hour label", gone <= 2,
      f"({gone} lit pixels)")
check("the newest cell is still full of content", kept > 30, f"({kept} lit pixels)")
label = cell_ink(img_stale, lay_stale, 0, 0, int(21 * s), int(16 * s))
check("but its hour label is still drawn", label > 10, f"({label} lit pixels)")
check("and the stale panel stays fully on screen",
      lay_stale["x"] >= 0 and lay_stale["y"] >= 0
      and lay_stale["x1"] <= W and lay_stale["y1"] <= H,
      f"({lay_stale['x']},{lay_stale['y']})-({lay_stale['x1']},{lay_stale['y1']})")

print("\n" + ("ALL FRESHNESS CHECKS PASSED" if not fails else f"FAILURES: {fails}"))
raise SystemExit(1 if fails else 0)
