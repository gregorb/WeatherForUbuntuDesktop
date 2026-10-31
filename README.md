# Weather For Ubuntu Desktop

A live weather readout painted onto your GNOME desktop background on Ubuntu
(26.04, GNOME Shell 50, Wayland). It is not an extension, a Conky overlay or a
second window: every refresh renders one PNG — the normal wallpaper with the
weather drawn over it — and hands that file to GNOME as the wallpaper.

The panel shows the current conditions for your location, the next 12 hours hour
by hour, and where the numbers came from. It follows GNOME's light/dark setting
and the screen you actually have.

    ┌──────────────────────────────────────────────────────────────────────┐
    │  @ Zagorje ob Savi   Fri 22:00                        Mostly clear   │
    │ ┃                                                                    │
    │ ┃     8°            [icon]                        [>] 11 km/h SE     │
    │ ┃                                                                    │
    │ ┃     RH 86%   Feels 6°   Hi 13°   Lo 4°   Rain 0.2mm                │
    │ ┃                                                                    │
    │ ┃     22   23   00   01   02   03   04   05   06   07   08   09      │
    │ ┃     cl   cl   ra   ra   cl   su   su   cl   ov   ov   ov   cl      │
    │ ┃     6°   6°   6°   5°   5°   4°   4°   4°   5°   5°   6°   6°      │
    │ ┃     _    _    ##   ###  _    _    _    _    #    #    _    _       │
    │ ┃     0mm  0mm  1mm  2mm  0mm  0mm  0mm  0mm  1mm  1mm  0mm  0mm     │
    │ ┃                                                                    │
    │ ┃     updated 22:38 · ARSO            sunrise 06:38   sunset 16:49   │
    └──────────────────────────────────────────────────────────────────────┘
      ^ hairline outline, rounded corners, soft drop shadow under the panel
      ┃ vertical accent bar, tinted by the current condition (or night blue)

The `@`, `[icon]`, `[>]` and the `cl / ra / su` letters above are FontAwesome
glyphs: a pin, the condition symbol, a wind-direction arrow, and one weather
icon per hour.

## Requirements

* Ubuntu with GNOME on Wayland or X11 (`gsettings` must exist)
* `python3` with **Pillow** — `sudo apt install python3-pil`
* Ubuntu and FontAwesome fonts — `sudo apt install fonts-ubuntu fonts-font-awesome`
* systemd user services (the Ubuntu default)

No API keys, no accounts, no root.

## Install

    cd ~/WeatherForUbuntuDesktop
    ./install.sh

That copies `wx-wallpaper` to `~/.local/bin`, copies the three systemd user
units to `~/.config/systemd/user`, enables the refresh timer and the unlock
watcher, and renders once so you see something immediately. Your desktop wallpaper is kept as the image the panel is
drawn onto, so the desktop still looks like your desktop.

Verify:

    wx-wallpaper --status                       # config, Wi-Fi, cache, current URI
    journalctl --user -u wx-wallpaper -u wx-wallpaper-unlock -f        # watch a refresh happen
    systemctl --user list-timers wx-wallpaper.timer
    systemctl --user status wx-wallpaper-unlock.service   # "watching for desktop unlocks"

Try a change without touching the desktop:

    wx-wallpaper --dry-run --output /tmp/preview.png

## Configuration

Everything lives in `~/.config/wx-wallpaper/config.json`. Values are re-read on
every refresh, so there is nothing to restart — edit, wait for the next run, or
force one with `systemctl --user start wx-wallpaper.service`.

| key            | meaning                                                        |
| -------------- | -------------------------------------------------------------- |
| `place`        | `"auto"` (geolocate from your public IP) or a place name, e.g. `"Maribor,SI"` |
| `latitude` / `longitude` / `place_name` | auto-filled once a place resolves, then pinned so later runs need no geocoding |
| `units`        | `"metric"` or `"imperial"`                                      |
| `networks`     | Wi-Fi SSID -> place table, checked **before** the default location: `{"Home-5G": "Zagorje ob Savi"}`. A value may be `"Place"` or `{"name": "Place", "latitude": ..., "longitude": ...}` |
| `providers`    | `["arso", "open-meteo"]` — weather sources tried in order; the first that answers wins |
| `place_coords` / `arso_places` | auto-filled caches (place -> coordinates, place -> ARSO station) |
| `anchor_x` / `anchor_y` | `left`/`center`/`right` and `top`/`center`/`bottom` |
| `margin_x_frac` / `margin_y_frac` | inset from the anchored edge, as a fraction of screen width/height (`0.05` = 5 %) |
| `panel_scale`  | panel size relative to a 1920x1080 reference (`0.5` = half size) |
| `width_frac`   | panel width as a multiple of its natural width; the hourly strip spreads to fill the extra room |
| `hourly`       | `strip` (12 hour-by-hour cells), `line` (trend sparkline), `off` |
| `hud_opacity`  | opacity of the panel glass (`1.0` = solid, `0.25` = barely there) |
| `hud_text_opacity` | `null` = letters stay clearer than the glass; set a number to damp text exactly as much as the glass |
| `base_light` / `base_dark` | the wallpaper the panel is drawn onto, per GNOME colour scheme |
| `resolution`   | `null` = read from Mutter; or force e.g. `"2560x1440"` |
| `keep_files`   | how many renders to retain in `~/.local/share/wx-wallpaper` |
| `timeout`      | per-request HTTP timeout in seconds |
| `fetch_retries` / `fetch_retry_wait` | if every provider fails, retry the whole chain this many times, waiting this many seconds first and doubling each time — the point is the first minute after login, when DNS is often not up yet |
| `dns_retry_wait` | when *every* provider fails on a DNS lookup, wait this many seconds before retrying (no doubling) — that exact failure mode means Wi-Fi has not associated yet, and no shorter wait will change the outcome |
| `stale_after_min` | once a cached reading is older than this it stops pretending: the current temperature, condition, wind and instant chips disappear (their slots stay, empty, same size), hourly cells the clock passed more than this long ago keep only their hour label, and the footer reads `stale` instead of `cached` |
| `refresh_on_unlock` / `unlock_min_gap` | used by `wx-wallpaper-unlock.service`: refresh on desktop unlock, but not if the cache is only `unlock_min_gap` seconds old — the timer just drew this same panel |

Two handy commands:

    wx-wallpaper --place Maribor,SI    # move, and unpin the old coordinates
    wx-wallpaper --place auto          # re-detect from your public IP

### Which location, and which source

Location is resolved in this order, and the journal says which one won
(`Zagorje ob Savi [Wi-Fi A1-8C2490] via ARSO`):

1. the Wi-Fi network listed in `networks`, if `nmcli` reports it (`--status` prints the detected SSID)
2. pinned `latitude` / `longitude`
3. `place`, geocoded through Open-Meteo
4. public-IP geolocation

Weather comes from whichever provider answers first:

1. **ARSO** — the Slovenian environment agency, i.e. the API [vreme.si](https://vreme.si) calls. Official Slovenian data, undocumented interface, Slovenia only.
2. **Open-Meteo** — documented, global, no key.

If ARSO is unreachable or its reply is malformed, the log says `provider arso
failed: …` and the panel is drawn from Open-Meteo. Two differences are visible:
the rain column shows **millimetres fallen** (`2.5mm`) instead of a probability,
and there is no *Feels* chip, because ARSO publishes neither. A place outside
Slovenia simply falls through to Open-Meteo.

### Refresh schedule

Three units keep the panel current:

* `wx-wallpaper.timer` fires at six minutes past every quarter hour
  (`OnCalendar=*:6/15` — :06 :21 :36 :51, so the providers have had time to
  publish the measurement taken at the rounded quarter), 40
  seconds after you log in, and `Persistent=true` makes a missed run catch up
  when the machine wakes.
* `wx-wallpaper.service` is the one-shot render the timer runs (`systemctl
  --user start wx-wallpaper.service` forces one right now).
* `wx-wallpaper-unlock.service` stays resident for the whole session and
  refreshes the moment you unlock the desktop — it watches `ActiveChanged(false)`
  on `org.gnome.ScreenSaver` via `gdbus`, so no new dependency. Unlocking is the
  first thing you do after logging in, and the timer's 40-second delay may not
  have fired (or may have raced the network, see below).

To change the schedule, edit the installed unit and run `systemctl --user daemon-reload`.

**If the network is down** — which is routine in the first minute after login
or unlock, before Wi-Fi has finished associating — the whole provider chain is
retried (`fetch_retries` attempts) before falling back to the last good
reading. The pause between attempts is `fetch_retry_wait` with doubling for
ordinary failures, but a flat `dns_retry_wait` (a minute) when every provider
died on a hostname lookup specifically — that signature means the Wi-Fi
association is still in progress, so the script waits for it rather than
burning its retries on a network that does not exist yet. A cached reading's
footer then says `updated 23:30 · cached · ARSO` — the time of the last
successful fetch, not the current clock. The clock in the top line is different:
both providers stamp their own measurement time on the reading (ARSO's
observation `valid` time, Open-Meteo's `current.time`), and that is what the
panel shows, falling back to the machine clock only if a feed carries neither.

**Once that cached reading is older than `stale_after_min` (an hour), it stops
being presented as current.** The big temperature, the condition name and icon,
the wind, and the humidity/feels-like/current-rain chips are all withheld — the
slots stay exactly the same size and simply show nothing. Hourly cells the clock
has left behind keep only their hour label, and the footer says `stale`. What
remains — today's high/low, sunrise/sunset, and the hours still ahead — is what
the reading can still honestly state. With no reading at all the desktop is left
alone rather than blanked.

## Uninstall

    ./uninstall.sh            # stop the timer, remove script and units, reset the wallpaper keys
    ./uninstall.sh --purge    # ... and delete settings and saved renders too

## Troubleshooting

* **Nothing changed on screen.** GNOME reloads the wallpaper only when the *path*
  changes; every render is a new file, so check `wx-wallpaper --status` for the
  URI and `journalctl --user -u wx-wallpaper -u wx-wallpaper-unlock` for errors.
* **The panel is off-screen or the wrong size.** Check `resolution` (null is
  usually right) and the `margin_*_frac` values; the panel never grows past the
  screen, but a huge `panel_scale` with a big `margin` can push it around.
* **Text is hard to read.** Raise `hud_opacity`, or set `hud_text_opacity` closer
  to `1.0`. At very low glass opacity the wallpaper behind the panel does most of
  the work, so bright desktop areas wash the small text out.
* **Wrong town.** `wx-wallpaper --status` shows the SSID it sees and what that SSID
  maps to; `--place Someplace` pins a place explicitly.
* **Weather looks stale.** `--status` prints `cache_age_s` and `last_provider`.
  A panel with an empty temperature slot and a `stale` footer means every fetch
  failed and even the cache is past `stale_after_min`; the reason is in
  `journalctl --user -u wx-wallpaper -u wx-wallpaper-unlock` (usually `Name or service not known` at
  login, which the retries then overcome).

---

# Development notes

## Repository layout

    wx-wallpaper              the whole tool: fetch, translate, render, apply
    install.sh                copy/symlink the script, install units, start the timer
    uninstall.sh              the reverse, with --purge
    config.example.json       what install.sh copies to ~/.config/wx-wallpaper/config.json
    systemd/                  user service, refresh timer, unlock watcher service
    tests/                    five standalone test scripts (see "Tests")

After `install.sh` the running copies are `~/.local/bin/wx-wallpaper`,
`~/.config/wx-wallpaper/config.json`, `~/.config/systemd/user/wx-wallpaper.*` and
the renders in `~/.local/share/wx-wallpaper/`. The repository is the source of
truth; `install.sh` copies by default, or use `./install.sh --link` while
developing so edits here take effect on the next refresh.

## How a refresh flows

    systemd timer (*/15 +6min, +40s after login)   unlock watcher (ActiveChanged=false)
        │                                         │
        ▼                                         ▼
    main() ── resolve_place(cfg) ──────────────────────────────────────────────
        │      networks[SSID] → pinned lat/lon → place geocode → public IP
        │      anything discovered is written back into the config
        ▼
    fetch_weather_retry()   retries the chain with doubling waits (login DNS race)
        │      ├─ fetch_arso()       vreme.si API ── translate ─┐
        │      │                       (fails → try next)       │
        │      └─ fetch_open_meteo()                            ├─ one common shape
        │                                                       ┘
        │      all failed → read last-weather.json; footer gains "· cached",
        │        or "· stale" plus dropped "now" values when older than stale_after_min
        ▼
    render(data, cfg, label, w, h, dark)
        │      base wallpaper ─ tint ─ shadow ─ glass layer (hud_opacity)
        │                                   └─ text layer (hud_text_opacity)
        ▼
    apply_wallpaper(path) ── gsettings picture-uri + picture-uri-dark ── GNOME reloads
        │
        ▼
    prune() keeps the newest `keep_files` renders

`render()` stores the geometry it chose in `LAST_LAYOUT`, which is what the tests
read back instead of guessing at pixels.

## Anatomy of the panel

Rows are laid out top to bottom from a measured text pass, so the panel can
never be too small for its own content. `s` is `panel_scale` adjusted for screen
size; every spacing below is multiplied by it.

       x0 ─────────────────────────────────────────────────────────── x1
       │                                                          rx  │
       │  cx      place_line (@ + "Place  Fri 22:00")     cond_name   │  row A
       │                                                              │  │   f.small / f.cond
       │                                       gap_a = 20s            │  │   height 44s
       │  ┃                                                           │  │
       │  ┃   temp_str (f.big, ink-centred)  icon  arrow  wind_txt    │  row B
       │  ┃                                     icon_xl       f.body  │  height th
       │  ┃                                       gap_b = 24s         │  │
       │  ┃   chip: RH 86% | Feels 6° | Hi 13° | Lo 4° | Rain 0.2mm   │  row C
       │  ┃                                       gap_c = 20s         │  │   height 40s
       │  ┃   22   23   00 ... 12 hourly cells ...                    │  row D1  hour_h  21s
       │  ┃   cl   ra   su ...                                        │          icon_h  28s
       │  ┃   6°   6°   5° ...                                        │          temp_h  31s
       │  ┃   _    ##   _  ...  rain bar (precip_frac)                │          rain_h  + bar_h
       │  ┃   0mm  1mm  0mm ...                                       │
       │  ┃                                       foot_h              │
       │  ┃   updated 22:38 · ARSO         sunrise 06:38 sunset 16:49 │  footer
       │                                                              │  │
       x0 ─────────────────────────────────────────────────────────── x1
       └─ accent bar: rounded rectangle from y0+28s to y1-28s, 5s wide,
          tinted by the WMO condition colour, night blue after sunset

| part | what decides it |
| --- | --- |
| panel size | measured text width of the widest row × `width_frac`; height is the sum of the row bands above |
| position | `anchor_x`/`anchor_y` pick the edge, `margin_*_frac` the inset; clamped so the panel is always fully on screen |
| `cx`, `rx` | left content edge (`x0 + inner + 10s`) and right content edge (`x1 - inner`) |
| big temperature | centred on the line halfway between row A and row C, using the digits' own ink box (`font.getbbox`) rather than the font box — a `8°` has no descender, so a metrically centred box reads as too low |
| chips | a list built per run; the feels-like chip is skipped when the provider has no apparent temperature |
| hourly strip | 12 cells starting at the current hour; `width_frac` spread beyond the natural width is given to the cells |
| accent bar and hairline | condition tint from the WMO table; `NIGHT_TINT` when `is_day` is 0 |

## Rendering rules

* **The GNOME reload rule.** `picture-uri` is re-read only when the value
  changes, so overwriting one PNG in place does nothing. Every render is
  `wx-<timestamp>.png`, both `picture-uri` and `picture-uri-dark` are set (so a
  light/dark switch keeps working), and old files are pruned.
* **Two compositing layers.** The panel glass, accent bar, bars and vector art
  are drawn on one layer at `hud_opacity`; all text and glyphs on a second layer
  at `hud_text_opacity` (derived as `glass + 0.7 × headroom` when null). Damping
  the letters by the same factor as a half-transparent panel made the small text
  muddy.
* **`ImageDraw.Draw(layer, "RGBA")`.** Draw with the `"RGBA"` blend mode: the
  default mode *replaces* alpha, which previously punched a translucent groove
  wherever the hairline outline was drawn.
* **Fonts.** Static Ubuntu TTFs plus `FontAwesome.otf`. The variable
  `Ubuntu[wdth,wght].ttf` cannot be used: Pillow 12 does not expose
  `variation_name` selection. `ICON["sunrise"]` and `ICON["sunset"]` deliberately
  reuse the sun/moon codepoints, so anything matching glyphs by identity must
  dedupe by codepoint.
* **Text on the glass layer must go through `alpha_composite`.** `ImageDraw` in
  `"RGBA"` mode *blends* shapes into the layer but *replaces* pixels for text:
  drawing low-alpha text straight onto the glass punches translucent holes in
  the panel instead of shading it. The `stale` marker is rendered to its own
  image and composited, the way `dir_arrow` already does.
* **The `stale` marker is hairline ink.** The word is drawn on the glass layer
  in the hairline colour, so it is exactly as faint as the panel outline while
  the rest of the footer keeps its text-layer brightness; `LAST_LAYOUT`'s
  `footer_stale` gives the word's pixel box so tests can compare its contrast
  against both the outline and the adjacent footer.
* **Stale data loses its glyphs, not its geometry.** When the cached reading is
  older than `stale_after_min`, the current temperature, condition, wind and
  instant chips draw nothing — but the number slot is still measured with
  `temp_m` (a stand-in `"0°"`) so a stale panel and a fresh one differ only by
  missing text, never by size or position. `LAST_LAYOUT` carries `stale`,
  `temp_text`, `chips` and `cell_behind`, so tests can assert both the state and
  the pixels (an empty slot must measure zero lit pixels, the same slot on a
  fresh panel must not).
* **Past-cell blanking is gated on staleness.** Hourly cells draw their label,
  then skip icon/temperature/precipitation when `behind and stale`; a live feed
  starts at the current hour, so the gate only ever fires for cached readings
  (and keeps fixed-timestamp test payloads drawing full cells).
* **Opacity is verifiable.** `hud_text_opacity` lands in `LAST_LAYOUT`, and tests
  compare rendered pixel values rather than trusting the arithmetic.

## Provider translation

ARSO's payload is GeoJSON-ish with `days[].timeline[]` rows of strings, so
`fetch_arso()` converts it into the Open-Meteo-shaped dict the renderer reads:

* `clouds_icon_wwsyn_icon` / `wwsyn_icon` (`overcast_lightRA_night`) → WMO code +
  day/night via `ARSO_CLOUD` and `ARSO_PHENOM`, indexed by intensity
* `ddff_icon` carries an English compass point; `dd_shortText` is Slovene, where
  `S` means *sever* (north), so the English one is preferred
* `tp_acc` **accumulates and resets to zero**, so hourly amounts are differences
  of successive values, floored at 0
* sunrise/sunset come from the day object; day/night falls back to local clock
  between them when an icon lacks a `day`/`night` suffix
* station lookup tries the whole place name, then progressively fewer words, then
  a diacritic-free form (`Brežice` → `Brezice`), and rejects a station more than
  ~35 km from the configured coordinates as a different town

Cache files keep the `provider` field, so an offline panel still names the source
its numbers came from.

## Tests

Five standalone scripts, no test runner needed:

    python3 tests/check_providers.py   # ~40 s, hits the network
    python3 tests/check_strip.py       # ~2 min
    python3 tests/check_networks.py    # ~5 s
    python3 tests/check_freshness.py   # ~30 s
    python3 tests/selftest.py          # ~4 min, 152 layout combinations

They import the repository copy of the script. Set `WX_SCRIPT` to test the
installed one instead:

    WX_SCRIPT=~/.local/bin/wx-wallpaper python3 tests/check_strip.py

What they guard:

* `check_providers.py` — icon/wmo decoding, compass handling, the progressive
  station query, live field-by-field comparison against a real ARSO reply,
  unit conversion, the fallback chain, and that a total outage raises so `main()`
  can reach the cache. Some checks use live data, so it needs a network.
* `check_strip.py` — the 12-cell strip (correct hours, day/night glyphs, partial
  and empty feeds), both precipitation dialects (probability and millimetres),
  the cached-reading footer, the text-vs-glass opacity rule, and that the big
  temperature stays centred between its neighbours without touching either.
* `check_freshness.py` — the retry ladder of `fetch_weather_retry` in both
  moods (generic failures double from `fetch_retry_wait`; an all-DNS outage
  waits `dns_retry_wait` flat), `is_dns_outage` / `WeatherUnavailable`
  classification (with `fetch_weather` and `time.sleep` stubbed, so backoff
  waits are observed, not slept), the hairline-faint `stale` marker, the unlock decision (`unlock_seen` / `unlock_refresh_due` fed captured
  `gdbus monitor` lines, plus the config and cache-age gates), and the stale
  panel: empty number slot that keeps its size and fills on a fresh panel,
  instant chips dropped while daily ones survive, exactly the left-behind cells
  flagged and pixel-empty, and the cached-vs-stale footer wording. Timestamps
  in test payloads sit off the exact hour so nothing ever lands on the
  60-minute boundary and goes time-dependent.
* `check_networks.py` — SSID detection (assoc SSID, fallback to the active
  802-11-wireless profile, `None` when wired or `nmcli` is missing) and the whole
  Wi-Fi → place → coordinates precedence, with the network calls mocked.
* `selftest.py` — every combination of WMO code, day/night, temperature, units,
  theme, resolution and screen corner, asserting every ink pixel stays inside the
  panel (allowing for the drop shadow) and the panel itself stays on screen.

## Known limitations

* ARSO covers Slovenia only, and its API is undocumented — treat any parsing
  change there as something to re-verify against a live reply.
* A cached panel shows the weather as of the last successful fetch; past the
  stale limit it hides what is no longer true, but future hours still carry the
  forecast values from that fetch — a forecast that aged is still that forecast.
* On GNOME 50 the screenshot D-Bus API is refused (`Screenshot is not allowed`)
  and `org.gnome.mutter unsafe-mode` no longer exists, so visual changes can only
  be verified by measuring rendered pixels — which is what the tests do.
* Multi-monitor setups take the resolution from Mutter's current state; the panel
  is placed on the detected screen size.
