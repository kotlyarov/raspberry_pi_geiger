#!/bin/sh
set -eu

APP_NAME="geiger-app"
INSTALL_DIR="$HOME/$APP_NAME"
BIN_DIR="/usr/local/bin"
BIN_PATH="$BIN_DIR/geiger.sh"
API_KEY_PATH="$INSTALL_DIR/api.key"
TLS_CERT_PATH="$INSTALL_DIR/server.crt"
TLS_KEY_PATH="$INSTALL_DIR/server.key"
SERVICE_NAME="geiger-web.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"
SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

APT_PACKAGES_REQUIRED="
openssl
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

echo "Preparing HTTPS API key..."
if [ ! -f "$API_KEY_PATH" ]; then
    old_umask=$(umask)
    umask 077
    python3 -c 'import secrets; print(secrets.token_urlsafe(32))' > "$API_KEY_PATH"
    umask "$old_umask"
fi
chmod 600 "$API_KEY_PATH"

api_key=$(tr -d '\r\n' < "$API_KEY_PATH")
api_key_length=$(printf '%s' "$api_key" | wc -c | tr -d ' ')
if [ "$api_key_length" -lt 1 ] || [ "$api_key_length" -gt 256 ]; then
    echo "API key in $API_KEY_PATH must be 1-256 characters long" >&2
    exit 1
fi

echo "Preparing self-signed TLS certificate..."
if [ ! -f "$TLS_CERT_PATH" ] || [ ! -f "$TLS_KEY_PATH" ]; then
    rm -f "$TLS_CERT_PATH" "$TLS_KEY_PATH"
    tls_san="DNS:raspberrypi.local,IP:127.0.0.1"
    primary_ip=$(hostname -I 2>/dev/null | awk '{print $1}' || true)
    if [ -n "$primary_ip" ]; then
        tls_san="$tls_san,IP:$primary_ip"
    fi

    openssl req -x509 -newkey rsa:2048 -sha256 -nodes -days 3650 \
        -keyout "$TLS_KEY_PATH" \
        -out "$TLS_CERT_PATH" \
        -subj "/CN=raspberry-pi-geiger" \
        -addext "subjectAltName=$tls_san"
fi
chmod 600 "$TLS_KEY_PATH"
chmod 644 "$TLS_CERT_PATH"

if command -v systemctl >/dev/null 2>&1; then
    echo "Installing systemd service: $SERVICE_NAME"
    service_tmp=$(mktemp)
    cat > "$service_tmp" <<EOF
[Unit]
Description=Geiger Counter HTTPS API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$BIN_PATH --serve --host 0.0.0.0 --port 443 --api-key-file $API_KEY_PATH --cert-file $TLS_CERT_PATH --tls-key-file $TLS_KEY_PATH --no-progress
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
echo "Installed Geiger Counter CLI and HTTPS API."
echo "Run it with: geiger.sh -10"
echo "Start HTTPS API with: sudo systemctl enable --now $SERVICE_NAME"
echo "API key file: $API_KEY_PATH"
echo "HTTPS request: https://<raspberry-pi-ip>/geiger?key=<key>&s=10&pin=17"
echo "For non-Raspberry Pi testing: geiger.sh -10 --simulate"
echo "To update later: cd $SOURCE_DIR && git pull && ./install.sh"
