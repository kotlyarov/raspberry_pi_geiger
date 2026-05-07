#!/bin/sh
set -eu

APP_NAME="geiger-app"
BOOT_SOURCE="/boot/firmware/$APP_NAME"
BOOT_SOURCE_FALLBACK="/boot/$APP_NAME"
INSTALL_DIR="$HOME/$APP_NAME"
APPLICATIONS_DIR="$HOME/.local/share/applications"
DESKTOP_DIR="$HOME/Desktop"
OPENBOX_DIR="$HOME/.config/openbox"

if [ -d "$BOOT_SOURCE" ]; then
    SOURCE_DIR="$BOOT_SOURCE"
elif [ -d "$BOOT_SOURCE_FALLBACK" ]; then
    SOURCE_DIR="$BOOT_SOURCE_FALLBACK"
else
    SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
fi

if [ ! -f "$SOURCE_DIR/app.py" ]; then
    echo "Cannot find app.py in $SOURCE_DIR" >&2
    exit 1
fi

echo "Installing minimal X/Openbox and Python packages..."
sudo apt update
sudo apt install -y --no-install-recommends rpd-x-core openbox xinit python3-tk python3-gpiozero

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
    echo "Creating optional Openbox autostart..."
    mkdir -p "$OPENBOX_DIR"
    cat > "$OPENBOX_DIR/autostart" <<EOF
# Remove or rename this file to disable Geiger Counter autostart.
python3 "$INSTALL_DIR/app.py" &
EOF
fi

echo
echo "Installed Geiger Counter."
echo "Run it with: startx"
echo "Or, from an existing X session: python3 $INSTALL_DIR/app.py"
echo "For non-Raspberry Pi testing: python3 $INSTALL_DIR/app.py --simulate"
