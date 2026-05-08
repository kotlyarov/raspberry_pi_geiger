#!/bin/sh
set -eu

APP_NAME="geiger-app"
INSTALL_DIR="$HOME/$APP_NAME"
BIN_DIR="/usr/local/bin"
BIN_PATH="$BIN_DIR/geiger.sh"
SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

APT_PACKAGES_REQUIRED="
python3-rpi.gpio
"

if [ ! -f "$SOURCE_DIR/app.py" ]; then
    echo "Cannot find app.py in $SOURCE_DIR" >&2
    exit 1
fi

if [ ! -f "$SOURCE_DIR/geiger.sh" ]; then
    echo "Cannot find geiger.sh in $SOURCE_DIR" >&2
    exit 1
fi

case "$(uname -m)" in
    aarch64|armv7l|armv6l)
        ;;
    *)
        echo "Warning: this installer is intended for Raspberry Pi OS Lite." >&2
        echo "Continuing anyway; use --simulate for off-device testing." >&2
        ;;
esac

echo "Installing minimal GPIO runtime..."
sudo apt update
sudo apt install -y --no-install-recommends $APT_PACKAGES_REQUIRED

if [ "${GEIGER_KEEP_APT_CACHE:-0}" != "1" ]; then
    echo "Cleaning apt package lists and cache to save disk space..."
    sudo apt clean
    sudo rm -rf /var/lib/apt/lists/*
fi

echo "Copying command-line app from $SOURCE_DIR to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
cp "$SOURCE_DIR/app.py" "$INSTALL_DIR/app.py"
cp "$SOURCE_DIR/geiger.sh" "$INSTALL_DIR/geiger.sh"
cp "$SOURCE_DIR/README.md" "$INSTALL_DIR/README.md"
chmod +x "$INSTALL_DIR/app.py" "$INSTALL_DIR/geiger.sh"

echo "Creating command: $BIN_PATH"
sudo mkdir -p "$BIN_DIR"
sudo ln -sf "$INSTALL_DIR/geiger.sh" "$BIN_PATH"

echo
echo "Installed Geiger Counter CLI."
echo "Run it with: geiger.sh -10"
echo "For non-Raspberry Pi testing: geiger.sh -10 --simulate"
echo "To update later: cd $SOURCE_DIR && git pull && ./install.sh"
