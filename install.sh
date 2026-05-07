#!/bin/sh
set -eu

APP_NAME="geiger-app"
INSTALL_DIR="$HOME/$APP_NAME"
APPLICATIONS_DIR="$HOME/.local/share/applications"
DESKTOP_DIR="$HOME/Desktop"
AUTOSTART_FLAG="$HOME/.geiger-startx-on-login"
PROFILE_FILE="$HOME/.profile"
SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

APT_PACKAGES_REQUIRED="
ca-certificates
git
openbox
python3
python3-gpiozero
python3-rpi.gpio
python3-tk
rpd-x-core
xinit
"
APT_PACKAGES_OPTIONAL="python3-lgpio"

if [ ! -f "$SOURCE_DIR/app.py" ]; then
    echo "Cannot find app.py in $SOURCE_DIR" >&2
    exit 1
fi

if [ "$(uname -m)" != "aarch64" ]; then
    echo "Warning: this installer is intended for Raspberry Pi OS Lite 64-bit." >&2
    echo "Continuing anyway; simulation mode can still be useful off-device." >&2
fi

echo "Installing minimal X/Openbox, git, Python, Tkinter, and GPIO packages..."
sudo apt update
sudo apt install -y --no-install-recommends $APT_PACKAGES_REQUIRED

if sudo apt install -y --no-install-recommends $APT_PACKAGES_OPTIONAL; then
    echo "Installed optional GPIO backend: $APT_PACKAGES_OPTIONAL"
else
    echo "Optional GPIO backend $APT_PACKAGES_OPTIONAL was not installed."
    echo "Continuing with python3-rpi.gpio, which is suitable for Raspberry Pi 3 B."
fi

echo "Copying app from $SOURCE_DIR to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
cp "$SOURCE_DIR/app.py" "$INSTALL_DIR/app.py"
cp "$SOURCE_DIR/README.md" "$INSTALL_DIR/README.md"
cp "$SOURCE_DIR/geiger-counter.desktop" "$INSTALL_DIR/geiger-counter.desktop"
chmod +x "$INSTALL_DIR/app.py"

echo "Creating desktop launcher..."
mkdir -p "$APPLICATIONS_DIR" "$DESKTOP_DIR"
sed "s|@APP_DIR@|$INSTALL_DIR|g" "$SOURCE_DIR/geiger-counter.desktop" > "$APPLICATIONS_DIR/geiger-counter.desktop"
cp "$APPLICATIONS_DIR/geiger-counter.desktop" "$DESKTOP_DIR/geiger-counter.desktop"
chmod +x "$APPLICATIONS_DIR/geiger-counter.desktop" "$DESKTOP_DIR/geiger-counter.desktop"

if [ ! -f "$HOME/.xinitrc" ]; then
    echo "Creating ~/.xinitrc for startx..."
    cat > "$HOME/.xinitrc" <<EOF
#!/bin/sh
if command -v openbox-session >/dev/null 2>&1; then
    openbox-session &
else
    openbox &
fi

exec python3 "$INSTALL_DIR/app.py"
EOF
    chmod +x "$HOME/.xinitrc"
else
    echo "Keeping existing ~/.xinitrc"
fi

if [ "${GEIGER_AUTOSTART:-0}" = "1" ]; then
    echo "Enabling optional startx-on-login for tty1..."
    touch "$AUTOSTART_FLAG"
    if [ ! -f "$PROFILE_FILE" ] || ! grep -q "GEIGER COUNTER AUTOSTART" "$PROFILE_FILE"; then
        cat >> "$PROFILE_FILE" <<'EOF'

# GEIGER COUNTER AUTOSTART
if [ -f "$HOME/.geiger-startx-on-login" ] && [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
    startx
fi
# END GEIGER COUNTER AUTOSTART
EOF
    fi
fi

echo
echo "Installed Geiger Counter."
echo "Run it with: startx"
echo "Or, from an existing X session: python3 $INSTALL_DIR/app.py"
echo "For non-Raspberry Pi testing: python3 $INSTALL_DIR/app.py --simulate"
echo "To update later: cd $SOURCE_DIR && git pull && ./install.sh"
echo "To disable optional login autostart: rm -f $AUTOSTART_FLAG"
