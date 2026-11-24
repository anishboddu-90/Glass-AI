#!/usr/bin/env bash
# Installs Glass for Linux into ~/.local (no root needed):
#   ./install.sh
# Then run `glass`, or bind `glass --toggle` to a keyboard shortcut.
set -euo pipefail
cd "$(dirname "$0")"

APP_DIR="$HOME/.local/share/glass-app"
BIN="$HOME/.local/bin"

command -v python3 >/dev/null || { echo "python3 is required."; exit 1; }

echo "→ Creating a private Python environment in $APP_DIR"
mkdir -p "$APP_DIR" "$BIN"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet "PySide6>=6.5" numpy keyring

echo "→ Copying the app"
rm -rf "$APP_DIR/glass"
cp -r glass "$APP_DIR/glass"

cat > "$BIN/glass" <<EOF
#!/usr/bin/env bash
cd "$APP_DIR" && exec "$APP_DIR/venv/bin/python" -m glass "\$@"
EOF
chmod +x "$BIN/glass"

mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/glass.desktop" <<EOF
[Desktop Entry]
Name=Glass
Comment=Liquid-glass AI sidebar
Exec=$BIN/glass
Terminal=false
Type=Application
Categories=Utility;
EOF

echo
echo "✓ Installed. Start it with:  glass"
echo "  Optional extras:"
echo "   • read replies aloud:      sudo apt install speech-dispatcher   (or espeak-ng)"
echo "   • screenshots on Wayland:  sudo apt install grim   (wlroots) — GNOME/KDE tools work too"
echo "   • start at login:          cp ~/.local/share/applications/glass.desktop ~/.config/autostart/"
echo "   • keyboard shortcut:       bind the command  glass --toggle  in your desktop's keyboard settings"
case ":$PATH:" in *":$BIN:"*) ;; *) echo "  NOTE: add $BIN to your PATH to run 'glass' from a terminal." ;; esac
