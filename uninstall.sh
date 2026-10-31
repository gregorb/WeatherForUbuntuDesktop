#!/usr/bin/env bash
# Undo install.sh: stop the timer, remove the script and units, hand the desktop
# back to GNOME. Settings and old renders are kept unless you pass --purge.
set -euo pipefail

CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_DIR="$CONFIG_HOME/wx-wallpaper"
DATA_DIR="$DATA_HOME/wx-wallpaper"

purge=0
case "${1:-}" in
    --purge) purge=1 ;;
    "")      ;;
    *)       echo "usage: $0 [--purge]" >&2; exit 2 ;;
esac

for unit in wx-wallpaper.timer wx-wallpaper-unlock.service; do
    systemctl --user disable --now "$unit" 2>/dev/null || true
done
rm -f "$CONFIG_HOME/systemd/user/wx-wallpaper.service" \
      "$CONFIG_HOME/systemd/user/wx-wallpaper-unlock.service" \
      "$CONFIG_HOME/systemd/user/wx-wallpaper.timer"
systemctl --user daemon-reload
rm -f "$HOME/.local/bin/wx-wallpaper"

# give the wallpaper keys back to their defaults
if command -v gsettings >/dev/null; then
    for key in picture-uri picture-uri-dark picture-options; do
        gsettings reset org.gnome.desktop.background "$key" 2>/dev/null || true
    done
fi

if [ "$purge" -eq 1 ]; then
    rm -rf "$CONFIG_DIR" "$DATA_DIR"
    echo "removed settings ($CONFIG_DIR) and renders ($DATA_DIR)"
else
    echo "kept settings ($CONFIG_DIR) and renders ($DATA_DIR); rerun with --purge to delete them"
fi
echo "done - the wallpaper keys are back at their defaults; log out and in if GNOME still shows the weather"
