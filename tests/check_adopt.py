#!/usr/bin/env python3
"""Guard the adoption rule: a background picked in GNOME Settings must not
only be drawn on, it must also land in the config, so the next boot paints
on the same image instead of reverting to whatever base the config still
names (which is what made the wallpaper revert after every login)."""
import json
import sys
import tempfile
from pathlib import Path

from PIL import Image

import _wx

wx = _wx.load()

TMP = Path(tempfile.mkdtemp())
MAGENTA = str(TMP / "magenta.png")
PICK = str(TMP / "pick.png")          # the background chosen in GNOME
Image.new("RGB", (1920, 1080), (255, 0, 255)).save(MAGENTA)
Image.new("RGB", (1920, 1080), (0, 128, 128)).save(PICK)

CFG = dict(wx.DEFAULTS)
CFG.update(base_light=MAGENTA, base_dark=MAGENTA, resolution="1920x1080")
fails = []


def check(name, cond, detail=""):
    print(f"{'ok  ' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        fails.append(name)


def run_main(current_pick):
    """One main() run with --cached, gsettings replaced by a stub returning
    current_pick, and settings/cache/renders all pointed at scratch space."""
    cfg_file = TMP / "config.json"
    cfg_file.write_text(json.dumps(CFG))
    cache = TMP / "last-weather.json"
    cache.write_text(json.dumps({
        "current": {"time": "2026-11-02T10:00", "temperature_2m": 7.4,
                    "apparent_temperature": 5.4, "relative_humidity_2m": 70,
                    "weather_code": 2, "wind_speed_10m": 5,
                    "wind_direction_10m": 180, "is_day": 1, "precipitation": 0},
        "hourly": {"time": ["2026-11-02T10:00", "2026-11-02T11:00"],
                   "temperature_2m": [7.4, 7.8], "weather_code": [2, 3],
                   "precipitation_probability": [10, 20]},
        "daily": {"temperature_2m_max": [10], "temperature_2m_min": [1],
                  "sunrise": ["2026-11-02T07:10"], "sunset": ["2026-11-02T17:05"]},
        "latitude": 46.1, "longitude": 15.1, "provider": "test"}))
    data_dir = TMP / "data"
    applied = []
    real = (wx.CONFIG_DIR, wx.CONFIG_FILE, wx.CACHE_FILE, wx.DATA_DIR,
            wx.dark_mode, wx.current_wallpaper, wx.apply_wallpaper, wx.log,
            sys.argv)
    wx.CONFIG_DIR, wx.CONFIG_FILE = TMP, cfg_file
    wx.CACHE_FILE, wx.DATA_DIR = cache, data_dir
    wx.dark_mode = lambda: True
    wx.current_wallpaper = lambda dark: current_pick
    wx.apply_wallpaper = applied.append
    wx.log = lambda *_a: None
    sys.argv = ["wx-wallpaper", "--cached"]
    try:
        code = wx.main()
    finally:
        (wx.CONFIG_DIR, wx.CONFIG_FILE, wx.CACHE_FILE, wx.DATA_DIR,
         wx.dark_mode, wx.current_wallpaper, wx.apply_wallpaper, wx.log,
         sys.argv) = real
    return code, json.loads(cfg_file.read_text()), applied


# 1. a pick in GNOME Settings is drawn on AND remembered in the config
code, saved, applied = run_main(PICK)
check("the run succeeds and applies a fresh render",
      code == 0 and len(applied) == 1
      and applied[0].parent == TMP / "data",
      f"code={code} applied={applied}")
check("the picked background is remembered as the dark base",
      saved.get("base_dark") == PICK, f"got {saved.get('base_dark')}")
check("the untouched light base stays as configured",
      saved.get("base_light") == MAGENTA)

# 2. with no pick (GNOME still shows one of our own renders) the config is left alone
code, saved, applied = run_main(None)
check("without a pick the base in the config does not change",
      code == 0 and saved.get("base_dark") == MAGENTA)

sys.exit(1 if fails else 0)
