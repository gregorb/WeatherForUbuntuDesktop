#!/usr/bin/env python3
"""Layout self-check for wx-wallpaper: render many weather scenarios onto a flat
magenta field and confirm every drawn pixel stays inside the panel, so nothing
can spill off the screen or collide with the panel edge."""
import importlib.util
import importlib.machinery
import itertools
import json
import sys
import tempfile
from pathlib import Path

from PIL import Image

import _wx

wx = _wx.load()

MAGENTA = str(Path(tempfile.gettempdir()) / "wx-wallpaper-magenta.png")
Image.new("RGB", (3840, 2160), (255, 0, 255)).save(MAGENTA)


def payload(code, is_day, temp, wind_deg=21, wind=3.1, imperial=False):
    return {
        "current": {"time": "2026-10-30T16:45", "temperature_2m": temp,
                    "apparent_temperature": temp - 8 if not imperial else temp - 15,
                    "relative_humidity_2m": 100, "weather_code": code,
                    "wind_speed_10m": wind, "wind_direction_10m": wind_deg,
                    "is_day": is_day, "precipitation": 4.0},
        "hourly": {"time": [f"2026-10-30T{h:02d}:00" for h in range(24)],
                   "temperature_2m": [temp + (h % 5) * 1.5 for h in range(24)],
                   "weather_code": [code] * 24,
                   "precipitation_probability": [100] * 24},
        "daily": {"temperature_2m_max": [temp + 6], "temperature_2m_min": [temp - 9],
                  "weather_code": [code], "sunrise": ["2026-10-30T06:52"],
                  "sunset": ["2026-10-30T17:20"]},
    }


def ink_bbox(img):
    """Bounding box of pixels that differ from the per-row background colour."""
    px = img.load()
    w, h = img.size
    minx, miny, maxx, maxy = w, h, -1, -1
    for y in range(h):
        bg = px[1, y]
        for x in range(w):
            p = px[x, y]
            if abs(p[0] - bg[0]) + abs(p[1] - bg[1]) + abs(p[2] - bg[2]) > 70:
                if x < minx:
                    minx = x
                if x > maxx:
                    maxx = x
                if y < miny:
                    miny = y
                if y > maxy:
                    maxy = y
    return minx, miny, maxx, maxy


def cases():
    extremes = [(-37, 0), (49, 1), (-9, 0), (7, 1)]
    for code, (temp, is_day) in itertools.product(sorted(wx.WMO), extremes):
        yield code, is_day, temp, "metric", "dark", "1920x1080", "left,top"
    for ax, ay in itertools.product(["left", "center", "right"],
                                    ["top", "center", "bottom"]):
        for res in ["1366x768", "1920x1080", "2560x1440", "3840x2160"]:
            yield 82, 1, -12, "imperial", "light", res, f"{ax},{ay}"
    # long strings everywhere
    yield 99, 0, -49, "imperial", "dark", "1366x768", "right,center"
    for frac in (0.0, 0.1, 0.25):
        yield 2, 1, 7, "metric", "dark", "1920x1080", f"right,center,{frac}"


fails = 0
runs = 0
for code, is_day, temp, units, theme, res, corner in cases():
    w, h = (int(v) for v in res.split("x"))
    cfg = dict(wx.DEFAULTS)
    parts = corner.split(",")
    parts += ["left", "top"][len(parts) - 1:] if len(parts) == 1 else []
    mode = "line" if runs % 7 == 0 else "strip"      # exercise both row-D modes
    cfg["width_frac"] = (1.0, 1.2, 1.6)[runs % 3]    # content-width and spread panels
    cfg.update(hourly=mode, base_light=MAGENTA, base_dark=MAGENTA, resolution=res,
               units=units, anchor_x=parts[0], anchor_y=parts[1],
               margin_x_frac=float(parts[2]) if len(parts) > 2 else 0.10,
               margin_y_frac=0.05)
    img = wx.render(payload(code, is_day, temp, wind=217.4), cfg,
                    "Radizel pri Mariboru, Slovenija", w, h, theme == "dark")
    lay = dict(wx.LAST_LAYOUT)
    x, y, x1, y1, s = lay["x"], lay["y"], lay["x1"], lay["y1"], lay["scale"]
    allow = int(34 * s)                       # drop-shadow bleed
    minx, miny, maxx, maxy = ink_bbox(img.convert("RGB"))
    runs += 1
    problems = []
    if maxx < 0:
        problems.append("nothing drawn")
    flush = float(cfg["margin_x_frac"]) == 0.0      # flush panels shadow to the edge
    if not flush and (minx < 1 or miny < 0 or maxx > w - 2 or maxy > h - 2):
        problems.append("ink touches canvas edge")
    if not (0 <= x and 0 <= y and x1 <= w and y1 <= h):
        problems.append(f"panel itself off-screen: ({x},{y},{x1},{y1}) in {w}x{h}")
    if minx < x - allow or maxx > x1 + allow or miny < y - allow or maxy > y1 + allow:
        problems.append(f"ink outside panel: ink=({minx},{miny},{maxx},{maxy}) "
                        f"panel=({x},{y},{x1},{y1}) allow={allow}")
    if problems:
        fails += 1
        print(f"FAIL {mode} w={cfg['width_frac']} code={code} day={is_day} t={temp} {units}/{theme}/{res}/{corner}"
              f" temp='{round(temp)}{'F' if units == 'imperial' else ''}'")
        for p in problems:
            print("      ", p)

print(f"{runs - fails}/{runs} layouts clean")
sys.exit(1 if fails else 0)
