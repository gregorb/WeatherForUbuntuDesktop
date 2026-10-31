#!/usr/bin/env bash
# Install the weather wallpaper for the current user. No root, no system packages.
#
#   ./install.sh          copy the script into ~/.local/bin and start the timer
#   ./install.sh --link   symlink instead, so edits here take effect immediately
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$CONFIG_HOME/wx-wallpaper"
UNIT_DIR="$CONFIG_HOME/systemd/user"
DATA_DIR="$DATA_HOME/wx-wallpaper"

link=0
case "${1:-}" in
    --link) link=1 ;;
    "")     ;;
    *)      echo "usage: $0 [--link]" >&2; exit 2 ;;
esac

# ---------------------------------------------------------------- dependencies
if ! command -v python3 >/dev/null; then
    echo "python3 is required:  sudo apt install python3" >&2; exit 1
fi
if ! python3 -c "import PIL" 2>/dev/null; then
    echo "Pillow is required:    sudo apt install python3-pil" >&2; exit 1
fi
for font in /usr/share/fonts/truetype/ubuntu/Ubuntu-Th.ttf \
            /usr/share/fonts/truetype/ubuntu/Ubuntu-M.ttf \
            /usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf \
            /usr/share/fonts/opentype/font-awesome/FontAwesome.otf; do
    [ -r "$font" ] || echo "warning: $font is missing (apt install fonts-ubuntu fonts-font-awesome)" >&2
done
if ! command -v gsettings >/dev/null; then
    echo "warning: gsettings not found; this tool drives GNOME's wallpaper setting" >&2
fi

mkdir -p "$BIN_DIR" "$CONFIG_DIR" "$UNIT_DIR" "$DATA_DIR"

# ---------------------------------------------------------------- the script
if [ "$link" -eq 1 ]; then
    ln -sfn "$HERE/wx-wallpaper" "$BIN_DIR/wx-wallpaper"
    echo "linked  $BIN_DIR/wx-wallpaper -> $HERE/wx-wallpaper"
else
    install -m 0755 "$HERE/wx-wallpaper" "$BIN_DIR/wx-wallpaper"
    echo "installed  $BIN_DIR/wx-wallpaper"
fi

# ---------------------------------------------------------------- settings
if [ -e "$CONFIG_DIR/config.json" ]; then
    echo "keeping   $CONFIG_DIR/config.json (already configured)"
else
    install -m 0644 "$HERE/config.example.json" "$CONFIG_DIR/config.json"
    echo "wrote     $CONFIG_DIR/config.json from the example"
fi

# ---------------------------------------------------------------- scheduling
for unit in wx-wallpaper.service wx-wallpaper.timer; do
    install -m 0644 "$HERE/systemd/$unit" "$UNIT_DIR/$unit"
done
systemctl --user daemon-reload
systemctl --user enable --now wx-wallpaper.timer
echo "enabled   wx-wallpaper.timer (every 15 minutes)"

# ---------------------------------------------------------------- first render
echo
"$BIN_DIR/wx-wallpaper"
echo
systemctl --user list-timers wx-wallpaper.timer --no-pager | sed -n '1,2p'
