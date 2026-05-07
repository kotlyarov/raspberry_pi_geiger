# Raspberry Pi Geiger Counter

Lightweight Tkinter GUI for counting Geiger tube interface pulses on Raspberry Pi OS Lite. This version targets a Raspberry Pi 3 B running Raspberry Pi OS Lite 64-bit Trixie, image built 2026-04-21, with a minimal X/Openbox GUI installed by the project installer.

It does not use Electron, a browser app, a database, or a web server.

## What The App Does

- Counts pulses on BCM GPIO 4, physical pin 7.
- Lets you edit the counting interval, defaulting to 10 seconds.
- Disables Start while counting.
- Shows raw pulse count, CPM, CPS, and status.
- Re-enables Start when the interval finishes.
- Includes simulation mode for development on non-Raspberry Pi computers.

The input constants are near the top of `app.py`:

```python
GPIO_PIN = 4
DEFAULT_INTERVAL_SECONDS = 10
PULL_UP = True
ACTIVE_STATE = False
BOUNCE_TIME = None
```

Debounce is not enabled by default.

## Hardware Safety

- Pulse input: BCM GPIO 4, physical pin 7.
- Ground: connect the Geiger interface ground to any Raspberry Pi GND pin.
- Raspberry Pi GPIO is 3.3V only. Never feed 5V into a GPIO pin.
- Use a 3.3V-safe Geiger interface, level shifter, optocoupler, transistor output, or other suitable protection circuit.
- GPIO 4 is also the usual Raspberry Pi 1-Wire pin. If 1-Wire is enabled, it can conflict with this app. Disable 1-Wire or change `GPIO_PIN` in `app.py`.

## Flash Raspberry Pi OS Lite 64-bit

Use Raspberry Pi Imager.

1. Choose Raspberry Pi 3.
2. Select Raspberry Pi OS Lite 64-bit, Trixie, image built 2026-04-21.
3. Open OS customisation before writing the card.
4. Set hostname, username, password, locale, and Wi-Fi.
5. Enable SSH if you want to install remotely.
6. Write the image to the microSD card.

This project is intended for Lite. Do not install Raspberry Pi OS Desktop or the recommended applications.

You no longer need to copy this project onto the SD card boot partition. The Pi should connect to the Internet, clone the Git repository, and install from the clone.

## First Boot

Boot the Raspberry Pi 3 B and log in locally or by SSH.

If Wi-Fi was not configured in Raspberry Pi Imager, run:

```sh
sudo raspi-config
```

Then configure wireless LAN from the system options, reboot if needed, and log in again.

Check that the network works:

```sh
ping -c 3 raspberrypi.com
```

Update package lists and install Git so the repository can be cloned:

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

The installer installs the required runtime packages:

```text
ca-certificates
git
openbox
python3
python3-gpiozero
python3-rpi.gpio
python3-tk
rpd-x-core
xinit
```

It also tries to install `python3-lgpio` as an optional GPIO backend when that package is available. If that optional package cannot be installed, the app can still use `python3-rpi.gpio` on Raspberry Pi 3 B.

Packages are installed with `--no-install-recommends` to keep the system small. The installer does not install the full desktop environment and does not install the recommended applications bundle.

## Installed Files

The installer copies the runnable app to:

```text
~/geiger-app
```

It creates desktop launchers in:

```text
~/.local/share/applications/geiger-counter.desktop
~/Desktop/geiger-counter.desktop
```

If `~/.xinitrc` does not already exist, the installer creates one so `startx` launches Openbox and the Geiger Counter app.

## Run The App

From the text console:

```sh
startx
```

From an existing X session:

```sh
python3 ~/geiger-app/app.py
```

For testing on a non-Raspberry Pi computer:

```sh
python3 ~/geiger-app/app.py --simulate
```

You can also force simulation mode with:

```sh
GEIGER_SIMULATE=1 python3 ~/geiger-app/app.py
```

## Optional Login Autostart

Autostart is disabled by default.

To make the Pi run `startx` automatically after you log in on tty1, install with:

```sh
GEIGER_AUTOSTART=1 ./install.sh
```

To disable it later:

```sh
rm -f ~/.geiger-startx-on-login
```

The installer adds a small marked block to `~/.profile` only when `GEIGER_AUTOSTART=1` is used. The block does nothing unless `~/.geiger-startx-on-login` exists.

## Updating Later

Because the app is installed from Git, later updates are simple:

```sh
cd ~/raspberry_pi_geiger
git pull
./install.sh
```

Then run:

```sh
startx
```

or restart the app if it is already open.

## Use

1. Enter a count interval in seconds.
2. Press Start.
3. Wait for the interval to finish.
4. Read raw pulse count, CPM, CPS, and status.

The Start button is disabled while the app is counting.
