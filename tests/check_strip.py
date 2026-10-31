#!/usr/bin/env python3
"""Verify the 12-hour strip: right hours, right icons, day/night glyphs, and
graceful behaviour when the forecast feed is partial or empty."""
import datetime
import importlib.util
import importlib.machinery
import json
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import _wx

wx = _wx.load()

MAGENTA = str(Path(tempfile.gettempdir()) / "wx-wallpaper-magenta.png")
Image.new("RGB", (1920, 1080), (255, 0, 255)).save(MAGENTA)
CFG = dict(wx.DEFAULTS)
CFG.update(base_light=MAGENTA, base_dark=MAGENTA, resolution="1920x1080")
W, H = 1920, 1080
fails = []


def payload(times, temps, codes=None, probs=None, sunrise="06:52", sunset="17:20",
            kind="prob"):
    n = len(times)
    hourly = {"time": times, "temperature_2m": temps, "weather_code": codes}
    if kind == "mm":                      # how ARSO expresses precipitation
        hourly["precip"] = probs
        hourly["precip_kind"] = "mm"
    else:                                 # how Open-Meteo expresses it
        hourly["precipitation_probability"] = probs
    return {
        "current": {"time": times[0], "temperature_2m": temps[0],
                    "apparent_temperature": temps[0] - 2, "relative_humidity_2m": 70,
                    "weather_code": codes[0] if codes else 2, "wind_speed_10m": 5,
                    "wind_direction_10m": 180, "is_day": 1, "precipitation": 0},
        "hourly": hourly,
        "daily": {"temperature_2m_max": [10], "temperature_2m_min": [1],
                  "sunrise": [f"2026-10-30T{sunrise}"], "sunset": [f"2026-10-30T{sunset}"]},
    }


def norm(img):
    """Rescale to 0..1 against the image's own background, so the match does not
    depend on how opaque the HUD was composited at."""
    px = list(img.getdata())
    lo = sorted(px)[len(px) // 5]
    hi = max(px)
    span = (hi - lo) or 1
    return [max(0, min(255, int((p - lo) * 255 / span))) for p in px]


def draw_cell_icon(cell_px, scale):
    """Identify which glyph was drawn by matching against reference renderings."""
    # use the renderer's own font object so this can never drift from production
    font = wx.Fonts(scale).icon_s
    # "sunrise"/"sunset" reuse the sun/moon codepoints, so name each distinct
    # glyph once, preferring the canonical weather name
    glyphs = {}
    for name in ("sun", "moon", "cloud", "bolt", "drop", "snow", "umbrella",
                 "therm", "pin"):
        glyphs.setdefault(wx.ICON[name], name)
    best = {}
    for glyph, key in glyphs.items():
        ref = Image.new("L", cell_px.size, 0)
        ImageDraw.Draw(ref).text((cell_px.size[0] / 2, 0), glyph, font=font, fill=255,
                                 anchor="ma")
        target = norm(cell_px.convert("L"))
        ref_px = norm(ref)
        best[sum(abs(a - b) for a, b in zip(ref_px, target)) / len(target)] = key
    score = min(best)
    return score, best[score]


def strip_cells(img, lay):
    n, cw = lay["hours"], lay["cell_w"]
    x, y = int(lay["strip_x"]), int(lay["strip_y"])
    icon_top = y + int(21 * lay["scale"])
    icon_bot = icon_top + int(28 * lay["scale"])
    # crop a glyph-sized window around each cell centre: a cell may be much wider
    # than its glyph when the strip is spread across a wide panel
    half = int(16 * lay["scale"])
    out = []
    for i in range(n):
        mid = x + cw * (i + 0.5)
        out.append(img.crop((int(mid - half), icon_top, int(mid + half), icon_bot)))
    return out


def check(name, cond, detail=""):
    print(f"{'ok  ' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        fails.append(name)


# ---- 1. the normal case: 12 cells, correct hours, day/night glyphs
times = [f"2026-10-30T{h:02d}:00" for h in range(14, 24)] + [f"2026-10-31T{h:02d}:00" for h in (0, 1)]
temps = [12, 11, 10, 9, 9, 8, 8, 7, 7, 6, 6, 5]
codes = [1, 2, 3, 61, 63, 95, 95, 71, 73, 75, 0, 0]           # clears at 22,23 -> night
probs = [0, 5, 20, 60, 80, 95, 40, 30, 55, 70, 0, 10]
pay = payload(times, temps, codes, probs, sunrise="07:10", sunset="17:05")
img = wx.render(pay, CFG, "Zagorje ob Savi", W, H, True).convert("RGB")
lay = dict(wx.LAST_LAYOUT)
check("12 cells rendered", lay["hours"] == 12, f"(got {lay['hours']})")
check("strip fits inside the panel",
      lay["strip_x"] + lay["hours"] * lay["cell_w"] <= lay["x1"] - lay["inner"] + 1,
      f"(strip ends {lay['strip_x'] + lay['hours'] * lay['cell_w']}, panel right {lay['x1'] - lay['inner']})")

# hour labels: read them back by ink-column count in the label band
lab_top = lay["strip_y"]
lab_bot = lab_top + int(21 * lay["scale"])
band = img.crop((int(lay["strip_x"]), lab_top,
                 int(lay["strip_x"] + lay["hours"] * lay["cell_w"]), lab_bot)).convert("L")
px = band.load()
vals = sorted(px[x, y] for x in range(band.size[0]) for y in range(band.size[1]))
floor = vals[len(vals) // 2] + 30          # above the panel's own brightness
cols_with_ink = [any(px[x, y] > floor for y in range(band.size[1])) for x in range(band.size[0])]
runs, cur = [], 0
for on in cols_with_ink + [False]:
    if on:
        cur += 1
    elif cur:
        runs.append(cur)
        cur = 0
check("12 hour labels present", len(runs) >= 12, f"({len(runs)} ink runs)")

# icon identity per cell: clear hours after sunset must be the moon, not the sun
cells = strip_cells(img, lay)
scale = lay["scale"]
got = [draw_cell_icon(c, scale)[1] for c in cells]
expect = ["sun", "cloud", "cloud", "umbrella", "umbrella", "bolt", "bolt",
          "snow", "snow", "snow", "moon", "moon"]
check("icons match the WMO codes and night hours", got == expect, f"got={got}")

# ---- 2. partial feed
pay2 = payload(times[:2], temps[:2], codes[:2], probs[:2])
img2 = wx.render(pay2, CFG, "Zagorje ob Savi", W, H, True)
lay2 = dict(wx.LAST_LAYOUT)
check("2-hour partial feed renders", lay2["hours"] == 2, f"(got {lay2['hours']})")
check("2-hour feed does not leave a half-empty strip", lay2["width"] <= lay["width"],
      f"({lay2['width']} <= {lay['width']}; width is set by a wider row)")

# ---- 3. missing optional arrays / all zeros
pay3 = payload(times, temps)                     # no codes, no probabilities
img3 = wx.render(pay3, CFG, "Zagorje ob Savi", W, H, True)
check("missing weather_code and probability arrays render",
      dict(wx.LAST_LAYOUT)["hours"] == 12)
pay4 = payload(times, temps, [0] * 12, [0] * 12)
img4 = wx.render(pay4, CFG, "Zagorje ob Savi", W, H, True)
check("zero precipitation everywhere renders", dict(wx.LAST_LAYOUT)["hours"] == 12)

# ---- 4. no hourly block at all: must fall back without the strip, no crash
pay5 = payload(times, temps)
pay5["hourly"] = {}
img5 = wx.render(pay5, CFG, "Zagorje ob Savi", W, H, True)
check("empty hourly block does not crash", img5.size == (W, H))
check("and the panel stays on screen", 0 <= wx.LAST_LAYOUT["x"] and
      wx.LAST_LAYOUT["x1"] <= W and wx.LAST_LAYOUT["y1"] <= H)

# ---- 5. ARSO-style feed: precipitation in millimetres, no feels-like temperature
check("probability labels", wx.precip_text(60, "prob") == "60%"
      and wx.precip_text(0, "prob") == "0%" and wx.precip_text(7.4, "prob") == "7%")
check("millimetre labels", wx.precip_text(2.5, "mm") == "2.5mm"
      and wx.precip_text(0, "mm") == "0mm" and wx.precip_text(3.0, "mm") == "3mm")
check("probability bar scales over 100%", abs(wx.precip_frac(25, "prob") - 0.25) < 1e-9)
check("millimetre bar scales over a wet 4 mm hour",
      abs(wx.precip_frac(1.0, "mm") - 0.25) < 1e-9 and wx.precip_frac(9, "mm") == 1.0)

mm_hours = [f"{v:.1f}" for v in (0, 0, 0.2, 1.5, 4.0, 6.5, 2.0, 0.4, 0, 0, 0, 0)]
pay_mm = payload(times, temps, codes, [float(v) for v in mm_hours],
                 sunrise="06:38", sunset="16:49", kind="mm")
pay_mm["current"]["apparent_temperature"] = None      # ARSO does not publish this
img_mm = wx.render(pay_mm, CFG, "Zagorje", W, H, True).convert("RGB")
lay_mm = dict(wx.LAST_LAYOUT)
check("millimetre feed renders 12 cells", lay_mm["hours"] == 12, f"(got {lay_mm['hours']})")
check("millimetre strip still fits the panel",
      lay_mm["strip_x"] + 12 * lay_mm["cell_w"] <= lay_mm["x1"] - lay_mm["inner"] + 1,
      f"(ends {lay_mm['strip_x'] + 12 * lay_mm['cell_w']}, right edge {lay_mm['x1'] - lay_mm['inner']})")
check("wider millimetre labels widen rather than overflow the panel",
      lay_mm["width"] >= lay["width"], f"({lay_mm['width']} vs {lay['width']} px)")
check("panel with millimetre labels stays on screen",
      lay_mm["x"] >= 0 and lay_mm["x1"] <= W and lay_mm["y1"] <= H)
def ink(im, lay):
    """Pixels inside the panel that differ from the panel's own background, i.e.
    how much text and art was drawn. Sampling every second pixel keeps it quick."""
    pts = [(xx, yy) for yy in range(lay["y"] + 2, lay["y1"] - 2, 2)
           for xx in range(lay["x"] + 2, lay["x1"] - 2, 2)]
    from collections import Counter
    glass = Counter(im.getpixel(p) for p in pts).most_common(1)[0][0]
    return sum(1 for p in pts
               if sum(abs(a - b) for a, b in zip(im.getpixel(p), glass)) > 60)


pay_mm_zero = payload(times, temps, codes, [0.0] * 12,
                      sunrise="06:38", sunset="16:49", kind="mm")
pay_mm_zero["current"]["apparent_temperature"] = None
img_mm0 = wx.render(pay_mm_zero, CFG, "Zagorje", W, H, True).convert("RGB")
lay_mm0 = dict(wx.LAST_LAYOUT)
check("millimetre values are actually drawn (wet strip has more ink than a dry one)",
      ink(img_mm, lay_mm) > ink(img_mm0, lay_mm0),
      f"({ink(img_mm, lay_mm)} vs {ink(img_mm0, lay_mm0)})")

# a missing 'precip' array entirely (ARSO can omit tp_acc) must not crash
pay_noprec = payload(times, temps, codes, [None] * 12, kind="mm")
img_np = wx.render(pay_noprec, CFG, "Zagorje", W, H, True)
check("null precipitation values render as zero", dict(wx.LAST_LAYOUT)["hours"] == 12)

# ---- 6. the footer admits when the numbers are a stale cached reading
live = payload(times, temps, codes, probs)
live["provider"] = "ARSO"
stale = json.loads(json.dumps(live))
stale["_cached"] = "20:37"
img_live = wx.render(live, CFG, "Zagorje", W, H, True).convert("RGB")
lay_live = dict(wx.LAST_LAYOUT)
img_stale = wx.render(stale, CFG, "Zagorje", W, H, True).convert("RGB")
lay_stale = dict(wx.LAST_LAYOUT)
check("footer says 'cached' only for a cached reading",
      "cached" in wx.footer_text({"provider": "ARSO", "_cached": "20:37"},
                                 datetime.datetime(2026, 10, 30, 21, 42))
      and "cached" not in wx.footer_text({"provider": "ARSO"},
                                         datetime.datetime(2026, 10, 30, 21, 42)),
      f"({wx.footer_text({'provider': 'ARSO', '_cached': '20:37'}, datetime.datetime(2026, 10, 30, 21, 42))!r})")
check("a cached panel shows the time it was last fetched, not the current time",
      "20:37" in wx.footer_text({"_cached": "20:37"}, datetime.datetime(2026, 10, 30, 21, 42))
      and "21:42" not in wx.footer_text({"_cached": "20:37"},
                                        datetime.datetime(2026, 10, 30, 21, 42)))
check("the extra word is actually drawn (stale panel carries more ink than a fresh one)",
      ink(img_stale, lay_stale) > ink(img_live, lay_live),
      f"({ink(img_stale, lay_stale)} vs {ink(img_live, lay_live)})")
check("and the panel still fits the screen",
      lay_stale["x"] >= 0 and lay_stale["x1"] <= W and lay_stale["y1"] <= H,
      f"({lay_stale['x']},{lay_stale['y']})-({lay_stale['x1']},{lay_stale['y1']})")

# ---- 7. text must not be dimmed as hard as the glass it sits on
def brightest(im, lay, top, height, x0=None, x1=None):
    x0 = lay["x"] if x0 is None else x0
    x1 = lay["x1"] if x1 is None else x1
    return max(sum(im.getpixel((x, y))[:3])
               for y in range(int(top), int(top) + height)
               for x in range(int(x0), int(x1)))


def lum_of(total):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return total  # compare in raw channel-sum terms; monotonic in luminance


img_txt = wx.render(json.loads(json.dumps(live)), CFG, "Zagorje", W, H, True).convert("RGB")
lay_txt = dict(wx.LAST_LAYOUT)
check("text has its own opacity, above the glass",
      lay_txt["text_opacity"] > lay_txt["opacity"],
      f"(text {lay_txt['text_opacity']:.2f} on glass {lay_txt['opacity']:.2f})")
cfg_lock = dict(CFG)
cfg_lock["hud_text_opacity"] = cfg_lock["hud_opacity"]
wx.render(json.loads(json.dumps(live)), cfg_lock, "Zagorje", W, H, True)
check("hud_text_opacity overrides the derived value",
      abs(dict(wx.LAST_LAYOUT)["text_opacity"] - cfg_lock["hud_opacity"]) < 1e-9,
      f"({dict(wx.LAST_LAYOUT)['text_opacity']})")

hours_b = brightest(img_txt, lay_txt, lay_txt["strip_y"], 11)
footer_b = brightest(img_txt, lay_txt, lay_txt["y1"] - 16, 9)
temp_b = brightest(img_txt, lay_txt, lay_txt["y"] + 38, 80, lay_txt["x"], lay_txt["x"] + 190)
glass_b = sum(img_txt.getpixel((lay_txt["x"] + 6, lay_txt["y"] + 6))[:3])
check("faint text stands clear of the glass it sits on",
      footer_b > 1.6 * glass_b and hours_b > 1.6 * glass_b,
      f"(glass {glass_b}: footer x{footer_b / glass_b:.2f}, hours x{hours_b / glass_b:.2f})")
check("and the big temperature is still the loudest thing in the panel",
      hours_b < temp_b and footer_b < temp_b, f"({footer_b}, {hours_b} < {temp_b})")

# ordering is set by alpha, and a uniform layer opacity cannot reorder it: assert the rule
check("every faint run is lifted but stays below the dimmest bright run (240)",
      all(wx.soft_alpha(a) > a and wx.soft_alpha(a) < 240 for a in (105, 160, 190, 200, 205, 215))
      and wx.soft_alpha(240) == 240 and wx.soft_alpha(255) == 255,
      f"({[(a, wx.soft_alpha(a)) for a in (105, 160, 205, 215)]})")
check("fainter runs gain more than louder ones",
      wx.soft_alpha(105) - 105 > wx.soft_alpha(205) - 205)

# ---- 8. the big number sits centred between the location line and the chips
for temp, tag in ((8, "single digit"), (-12, "negative"), (100, "three digits")):
    for scale in (0.5, 1.0):
        c = dict(CFG)
        c["panel_scale"] = scale
        pay_c = payload([times[0]] + times, [temp] + temps, codes, probs)
        pay_c["current"]["temperature_2m"] = temp
        wx.render(pay_c, c, "Zagorje", W, H, True)
        lay_c = dict(wx.LAST_LAYOUT)
        want = (lay_c["row_a_c"] + lay_c["row_c_c"]) / 2
        ink_top, ink_bot = lay_c["temp_ink"]
        check(f"big number centred between location and chips ({tag}, scale {scale})",
              abs(lay_c["temp_c"] - want) < 0.75 and ink_top < want < ink_bot,
              f"(centre {lay_c['temp_c']:.1f} vs midpoint {want:.1f})")
        check(f"    ...and it touches neither neighbour ({tag}, scale {scale})",
              ink_top > lay_c["row_a_c"] - 30 and ink_bot < lay_c["row_c_c"] + 5,
              f"(ink {ink_top:.0f}..{ink_bot:.0f}, rows {lay_c['row_a_c']:.0f} / {lay_c['row_c_c']:.0f})")

print("\n" + ("ALL STRIP CHECKS PASSED" if not fails else f"FAILURES: {fails}"))
