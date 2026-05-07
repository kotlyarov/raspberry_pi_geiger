# Raspberry Pi Geiger Counter

Lightweight Tkinter GUI for counting Geiger tube interface pulses on a minimal Raspberry Pi OS Lite install. It is intended for old Raspberry Pi hardware and a small X/Openbox session, not the full Raspberry Pi OS Desktop.

## Files

- `app.py`: Tkinter GUI and GPIO pulse counter.
- `install.sh`: first-boot installer for Raspberry Pi OS Lite.
- `geiger-counter.desktop`: launcher template used by the installer.
- `README.md`: this guide.

## Hardware Safety

- Pulse input: BCM GPIO 4, physical pin 7.
- Ground: connect the Geiger interface ground to any Raspberry Pi GND pin.
- GPIO inputs are 3.3V only. Never feed 5V into a Raspberry Pi GPIO pin.
- Use a 3.3V-safe Geiger interface, level shifter, optocoupler, transistor output, or other suitable protection circuit.
- GPIO 4 is also the usual Raspberry Pi 1-Wire pin. If 1-Wire is enabled, it can conflict with this app. Disable 1-Wire or change `GPIO_PIN` in `app.py`.

The default input settings are near the top of `app.py`:

```python
GPIO_PIN = 4
DEFAULT_INTERVAL_SECONDS = 10
PULL_UP = True
ACTIVE_STATE = False
BOUNCE_TIME = None
```

Debounce is not enabled by default.

## Flash Raspberry Pi OS Lite

1. Use Raspberry Pi Imager or another imaging tool.
2. Select Raspberry Pi OS Lite 32-bit Trixie, release 21 Apr 2026.
3. Flash the image to a microSD card.
4. Configure hostname, user, password, Wi-Fi, and SSH if you need them.

Do not install Raspberry Pi OS Desktop or the recommended applications for this project.

## Copy The App To The Boot Partition

After flashing, mount the SD card boot partition on your computer.

Create this folder on the boot partition:

```text
geiger-app
```

Copy these files into it:

```text
app.py
install.sh
geiger-counter.desktop
README.md
```

On Raspberry Pi OS, that folder will normally appear after boot as:

```text
/boot/firmware/geiger-app
```

The installer also falls back to:

```text
/boot/geiger-app
```

## First Boot Install

Boot the Raspberry Pi, log in, then run:

```sh
cd /boot/firmware/geiger-app
chmod +x install.sh
./install.sh
```

If your system exposes the boot partition at `/boot/geiger-app`, use:

```sh
cd /boot/geiger-app
chmod +x install.sh
./install.sh
```

The installer installs only the minimal GUI packages:

```sh
sudo apt install -y --no-install-recommends rpd-x-core openbox xinit python3-tk python3-gpiozero
```

It copies the app to:

```text
~/geiger-app
```

It creates launchers in:

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

For testing on a non-Raspberry Pi machine:

```sh
python3 ~/geiger-app/app.py --simulate
```

You can also force simulation mode with:

```sh
GEIGER_SIMULATE=1 python3 ~/geiger-app/app.py
```

## Optional Autostart

The installer does not enable boot autostart by default.

To create an Openbox autostart file during install, run:

```sh
GEIGER_AUTOSTART=1 ./install.sh
```

To disable it later:

```sh
mv ~/.config/openbox/autostart ~/.config/openbox/autostart.disabled
```

The `~/.xinitrc` file controls what runs when you type `startx`. Edit or remove that file if you want `startx` to open only Openbox.

## Use

1. Enter a count interval in seconds.
2. Press Start.
3. The Start button is disabled while pulses are counted.
4. When the interval ends, the app shows raw pulse count, CPM, CPS, and status, then re-enables Start.
