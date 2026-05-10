#!/bin/sh
set -eu

APP_NAME="geiger-app"
INSTALL_DIR="$HOME/$APP_NAME"
BIN_DIR="/usr/local/bin"
BIN_PATH="$BIN_DIR/geiger.sh"
PASSWORD_PATH="$INSTALL_DIR/password.txt"
SERVICE_NAME="geiger-web.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"
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

echo "Preparing HTTP password..."
if [ ! -f "$PASSWORD_PATH" ]; then
    old_umask=$(umask)
    umask 077
    python3 -c 'import secrets, string; alphabet = string.ascii_letters + string.digits; print("".join(secrets.choice(alphabet) for _ in range(10)))' > "$PASSWORD_PATH"
    umask "$old_umask"
fi
chmod 600 "$PASSWORD_PATH"

password=$(tr -d '\r\n' < "$PASSWORD_PATH")
password_length=$(printf '%s' "$password" | wc -c | tr -d ' ')
if [ "$password_length" -ne 10 ]; then
    echo "Password in $PASSWORD_PATH must be exactly 10 characters long" >&2
    exit 1
fi

if command -v systemctl >/dev/null 2>&1; then
    echo "Installing systemd service: $SERVICE_NAME"
    service_tmp=$(mktemp)
    cat > "$service_tmp" <<EOF
[Unit]
Description=Geiger Counter HTTP API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$BIN_PATH --serve --host 0.0.0.0 --port 80 --password-file $PASSWORD_PATH --no-progress
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
    sudo cp "$service_tmp" "$SERVICE_PATH"
    rm -f "$service_tmp"
    sudo chmod 644 "$SERVICE_PATH"
    sudo systemctl daemon-reload
else
    echo "systemctl not found; skipping systemd service installation." >&2
fi

echo
echo "Installed Geiger Counter CLI and HTTP API."
echo "Run it with: geiger.sh -10"
echo "Start HTTP API with: sudo systemctl enable --now $SERVICE_NAME"
echo "Password file: $PASSWORD_PATH"
echo "HTTP request: http://<raspberry-pi-ip>/geiger?pwd=<password>&s=10&pin=17"
echo "For non-Raspberry Pi testing: geiger.sh -10 --simulate"
echo "To update later: cd $SOURCE_DIR && git pull && ./install.sh"
