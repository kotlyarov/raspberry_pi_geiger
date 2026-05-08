# Raspberry Pi Geiger Counter

Minimal command-line Geiger counter for Raspberry Pi OS Lite. This prototype counts pulses on a GPIO pin for a fixed interval and prints the result without installing a GUI, desktop environment, browser, database, or web server.

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
- Includes simulation mode for development on non-Raspberry Pi computers.

The default input settings are near the top of `app.py`:

```python
GPIO_PIN = 17
DEFAULT_INTERVAL_SECONDS = 10.0
DEFAULT_PULL = "up"
DEFAULT_ACTIVE_STATE = "low"
DEFAULT_BOUNCE_MS = None
```

Debounce is not enabled by default.

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
sudo raspi-config
```

Then configure wireless LAN from the system options, reboot if needed, and log in again.

Check that the network works:

```sh
ping -c 3 raspberrypi.com
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

Enable RPi.GPIO debounce:

```sh
geiger.sh -10 --bounce-ms 5
```

If Raspberry Pi GPIO edge detection is unavailable, the app automatically falls back to polling the pin every 1 ms. To use a different fallback polling interval:

```sh
geiger.sh -10 --poll-interval-ms 0.5
```

Show all options:

```sh
geiger.sh --help
```

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
