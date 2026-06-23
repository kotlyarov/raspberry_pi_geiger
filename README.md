# Raspberry Pi Geiger Counter

Minimal Geiger counter for Raspberry Pi OS Lite. It can run as a command-line tool or as a tiny built-in HTTP JSON API without installing a GUI, desktop environment, browser, database, nginx, Apache, or a Python web framework.

The default command is:

```sh
geiger.sh -10
```

That counts impulses for the next 10 seconds and prints a result like:

```text
impulses=3 seconds=10 cps=0.300 cpm=18.0
```

When running in an interactive terminal, the app also shows a small counting-dot progress animation on stderr while it waits.

## What The App Does

- Counts pulses on BCM GPIO 17, physical pin 11.
- Uses active-low pulses by default, with the internal pull-up enabled.
- Accepts the shorthand `-10` to mean "count for 10 seconds".
- Prints raw impulses, CPS, and CPM.
- Can expose the same counting options through `http://<pi-ip>/geiger`.
- Includes simulation mode for development on non-Raspberry Pi computers.

The default input settings are near the top of `app.py`:

```python
GPIO_PIN = 17
DEFAULT_INTERVAL_SECONDS = 10.0
DEFAULT_PULL = "down"
DEFAULT_ACTIVE_STATE = "up"
DEFAULT_BOUNCE_MS = 0
```

Software dead-time/debounce defaults to 25 ms so one noisy pulse burst is less likely to be counted as many impulses. Set `--bounce-ms 0` to disable it.

## Hardware Safety

- Pulse input: BCM GPIO 17, physical pin 11.
- Ground: connect the Geiger interface ground to any Raspberry Pi GND pin.
- Raspberry Pi GPIO is 3.3V only. Never feed 5V into a GPIO pin.
- Use a 3.3V-safe Geiger interface, level shifter, optocoupler, transistor output, or other suitable protection circuit.
- GPIO 17 is a plain general-purpose GPIO pin. If you move the pulse input to another pin, pass its BCM number with `--pin`.

## Flash Raspberry Pi OS Lite 64-bit

Use Raspberry Pi Imager.

1. Choose Raspberry Pi 3.
2. Select Raspberry Pi OS Lite 64-bit.
3. Open OS customisation before writing the card.
4. Set hostname, username, password, locale, and Wi-Fi.
5. Enable SSH if you want to install remotely.
6. Write the image to the microSD card.

This project is intended for Lite. Do not install Raspberry Pi OS Desktop or the recommended applications.

## First Boot

Boot the Raspberry Pi and log in locally or by SSH.

If Wi-Fi was not configured in Raspberry Pi Imager, run:

```sh
sudo nmtui
```

Select `Activate a connection` or `Edit a connection`, choose your Wi-Fi
network, enter the password, and connect. Raspberry Pi OS Bookworm uses
NetworkManager for network connections, so use `nmtui` or `nmcli` to add or
change the SSID/password. Do not use `raspi-config` for the Wi-Fi connection
profile.

If the Wi-Fi radio is disabled because the WLAN country was not set, set the
country first in Raspberry Pi Imager when flashing the card. On an already
booted Pi, use `raspi-config` only for `Localisation Options > WLAN Country`,
then return to `sudo nmtui` for the network connection itself.

Check that the network works and NetworkManager sees the Wi-Fi networks:

```sh
ping -c 3 raspberrypi.com
nmcli dev wifi list
```

Install only the tools needed to clone from GitHub:

```sh
sudo apt update
sudo apt install -y --no-install-recommends git ca-certificates
```

Clone the app:

```sh
git clone https://github.com/kotlyarov/raspberry_pi_geiger.git
cd raspberry_pi_geiger
```

Run the installer:

```sh
chmod +x install.sh
./install.sh
```

The installer removes any previous `geiger-web.service`, `~/geiger-app`, and
`/usr/local/bin/geiger.sh` install before copying fresh files. It then enables
and starts the HTTP API service automatically, so it will come back after the Pi
boots. At the end it prints the Pi IP address and the generated `?pwd=` value.

## Minimal Runtime Packages

The installer installs only:

```text
python3-rpi.gpio
```

The previous GUI packages are no longer installed:

```text
openbox
python3-gpiozero
python3-lgpio
python3-tk
rpd-x-core
xinit
```

Packages are installed with `--no-install-recommends`. After installing, the script also runs `apt clean` and removes apt package lists to save disk space. If you want to keep apt package lists for later package work, install with:

```sh
GEIGER_KEEP_APT_CACHE=1 ./install.sh
```

## Installed Files

The installer copies the app to:

```text
~/geiger-app
```

It creates this command:

```text
/usr/local/bin/geiger.sh
```

It also creates a fresh local-only HTTP API password file:

```text
~/geiger-app/password.txt
```

These files are generated on the Raspberry Pi and should not be committed to Git.

## Run The Counter

Count for 10 seconds:

```sh
geiger.sh -10
```

Count for 60 seconds:

```sh
geiger.sh -60
```

Disable the progress animation:

```sh
geiger.sh -10 --no-progress
```

Run from the cloned repository before installing:

```sh
./geiger.sh -10
```

For testing on a non-Raspberry Pi computer:

```sh
./geiger.sh -10 --simulate
```

You can also force simulation mode with:

```sh
GEIGER_SIMULATE=1 geiger.sh -10
```

## Useful Options

Use a different BCM GPIO pin:

```sh
geiger.sh -10 --pin 22
```

Count active-high pulses instead of active-low pulses:

```sh
geiger.sh -10 --active-high --pull down
```

Use a smaller software dead-time/debounce:

```sh
geiger.sh -10 --bounce-ms 5
```

For a noisy signal that counts far more impulses than the Geiger counter clicks, try a larger software dead-time:

```sh
geiger.sh -10 --bounce-ms 50
geiger.sh -10 --bounce-ms 100
```

If Raspberry Pi GPIO edge detection is unavailable, the app automatically falls back to polling the pin every 1 ms. To use a different fallback polling interval:

```sh
geiger.sh -10 --poll-interval-ms 0.5
```

Show all options:

```sh
geiger.sh --help
```

## Run The HTTP API

The installer creates, enables, and starts a lightweight systemd service that
listens on port 80.

Read the generated 10-character password:

```sh
cat ~/geiger-app/password.txt
```

Then call the Raspberry Pi over HTTP:

```sh
curl "http://192.168.0.1/geiger?pwd=XXXXXXXXXX&s=10&pin=17"
```

The response is JSON:

```json
{"impulses":3,"seconds":10,"cps":0.3,"cpm":18.0,"pin":17,"pull":"up","active_state":"low","bounce_ms":25,"poll_interval_ms":1.0,"simulate":false}
```

The `pwd` query parameter must match the 10-character password stored in `~/geiger-app/password.txt`. The endpoint accepts the same counting options as the CLI:

```text
s=10
seconds=10
pin=17
pull=up|down|off
active=low|high
active-low=1
active-high=1
bounce-ms=25
poll-interval-ms=1
simulate=1
```

To run the HTTP API manually instead of through systemd:

```sh
sudo geiger.sh --serve \
  --password-file ~/geiger-app/password.txt
```

## Browser Pages

The repository includes standalone browser pages:

```text
web/index.html
web/coin.html
web/cardguess.html
web/cardguess-light.html
web/cardguess-binary.html
```

Open `web/index.html` on another computer to choose a page. `web/coin.html` contains the Raspberry Pi counter-backed coin toss interface. Its Settings menu asks for the Raspberry Pi IP or host, password, seconds, and optional GPIO settings, and stores the Pi host and password in that browser's local storage so you do not need to re-enter them every time. `web/cardguess.html`, `web/cardguess-light.html`, and `web/cardguess-binary.html` contain card-pair guessing interfaces backed by the same Pi counter API.

## Troubleshooting

If you see this warning:

```text
geiger: edge detection unavailable (Failed to add edge detection); using GPIO polling every 1 ms
```

the app is still running. It means `python3-rpi.gpio` could read the GPIO pin but could not enable kernel edge interrupts, so the app switched to a tiny polling loop instead.

If counting stays at zero, try:

```sh
geiger.sh -10 --active-high --pull down
geiger.sh -10 --pin 22
```

If you choose to use GPIO 4 instead, also check that 1-Wire is disabled.

## Updating Later

Because the app is installed from Git, later updates are simple:

```sh
cd ~/raspberry_pi_geiger
git pull
./install.sh
```
