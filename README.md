# iMac Fan Control Suite

A collection of fan control scripts for iMac 27" Late 2009 (iMac11,1) running Linux distributions including openSUSE Tumbleweed and RaspberryOS (Debian-based).

## Overview

Three components work together to manage fan speeds via the `applesmc` kernel module:

| File | Purpose | GUI | Systemd |
|------|---------|-----|---------|
| `imac_fan_control.py` | Interactive GUI monitor & control | Yes | Difficult (no display) |
| `imac_fan_control_headless.py` | Automatic temp-based control, no GUI | No | Yes |
| `install.sh` | Automated installation script | N/A | N/A |
| Desktop autostart (`.desktop`) | Start GUI on user login | Yes | N/A |
| Service files (`.service`) | Start scripts as systemd services | N/A | Yes |

## Quick Start

### Option 0: Automated Installation (Recommended)

Use the included installation script for easy setup:

```bash
# Clone the repository
 git clone https://github.com/BirgerKo/imac-fan-control.git
 cd imac-fan-control

# Run the installer (as root)
 sudo ./install.sh
```

The installer will:
- Detect your OS (openSUSE or Debian/RaspberryOS)
- Install required kernel modules
- Install Python dependencies
- Copy files to `/opt/imac-fan-control/`
- Set up the headless service
- Configure GUI autostart

**Installer options:**
```bash
sudo ./install.sh              # Install both GUI and headless
sudo ./install.sh --headless   # Install headless service only
sudo ./install.sh --gui         # Install GUI only
sudo ./install.sh --uninstall   # Remove everything
```

### Prerequisites

All distributions require the `applesmc` and `coretemp` kernel modules:
```bash
sudo modprobe applesmc
sudo modprobe coretemp
```

**Note:** On RaspberryOS (Debian-based), you may need to install the `applesmc-dkms` package or build from source. The `install.sh` script handles this automatically.

### Option 1: GUI Mode (Manual + Monitor)
Run interactively with desktop autostart:

1. **Manual run:**
   ```bash
   sudo python3 imac_fan_control.py
   ```

2. **Auto-start on login (desktop):**
   - Copy `imac-fan-control.desktop` to `~/.config/autostart/`
   - Make executable: `chmod +x ~/.config/autostart/imac-fan-control.desktop`
   - Update the `Exec=` line in the `.desktop` file to point to your local script path
   - Log out and in, or reboot

### Option 2: Headless Systemd Service (Automatic)
Runs as root service; monitors TS0V temp and adjusts fan2 automatically.

1. **Copy service file:**
   ```bash
   sudo cp imac-fan-control-headless.service /etc/systemd/system/
   ```

2. **Enable & start:**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable imac-fan-control-headless.service
   sudo systemctl start imac-fan-control-headless.service
   ```

3. **Check status:**
   ```bash
   sudo systemctl status imac-fan-control-headless.service
   sudo journalctl -u imac-fan-control-headless.service -f
   ```

## Behavior Details

### GUI Script (`imac_fan_control.py`)
- **Fan 2 (HDD):** Set to manual 18,550 RPM on startup (per your request)
- Displays real-time RPM, temps, and manual override controls
- Restores all fans to automatic on exit
- Requires root: `sudo python3 imac_fan_control.py`

### Headless Script (`imac_fan_control_headless.py`)
- **Initialization:** Fan 2 → manual mode, 2000 RPM
- **Poll interval:** 10 seconds
- **Logic:**
  - If `TS0V > 48°C` → Fan 2 = 3000 RPM
  - If `TS0V < 47°C` → Fan 2 = 2000 RPM
- **Graceful shutdown:** SIGTERM/SIGINT restores fan to automatic mode
- Requires root (systemd runs as `User=root`)

## Repository Structure

```
.
├── imac_fan_control.py                    # GUI app
├── imac_fan_control_headless.py           # Headless daemon
├── install.sh                             # Automated installation script
├── imac-fan-control.desktop               # GUI autostart entry
├── imac-fan-control.service               # GUI systemd (optional, fragile)
├── imac-fan-control-headless.service      # Headless systemd (recommended)
├── imac-fan-control-gui.service           # GUI systemd (optional, fragile)
├── .gitignore
└── README.md
```

## Installation

### Clone the Repository

```bash
git clone https://github.com/BirgerKo/imac-fan-control.git
cd imac-fan-control
```

### For Target Machine

Copy all files to your target location (e.g., `~/imac-fan-control/`).

### RaspberryOS / Debian-Specific Setup

RaspberryOS (Debian-based) requires the `applesmc` kernel module, which may need manual installation:

#### Option A: Install from DKMS (if available)
```bash
sudo apt update
sudo apt install -y dkms applesmc-dkms
```

#### Option B: Build from Source (most reliable)
```bash
# Install build dependencies
sudo apt install -y git build-essential

# Clone and build applesmc
git clone https://github.com/guillaumevincent/applesmc.git
cd applesmc
make
sudo make install

# Load the module
sudo modprobe applesmc
```

#### Option C: Use the Install Script (Recommended)
```bash
sudo ./install.sh
```
The install script automatically handles module installation for both openSUSE and Debian-based systems.

#### Headless service (recommended)
```bash
sudo cp imac-fan-control-headless.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable imac-fan-control-headless.service
sudo systemctl start imac-fan-control-headless.service
```
**Note:** Update the `ExecStart` path in the `.service` file to match your installation location.

#### GUI with autostart (optional)
```bash
mkdir -p ~/.config/autostart
cp imac-fan-control.desktop ~/.config/autostart/
chmod +x ~/.config/autostart/imac-fan-control.desktop
# Log out and back in to activate
```
**Note:** Update the `Exec=` path in the `.desktop` file to point to your local `imac_fan_control.py` location.

#### Using the Install Script (Recommended)
The `install.sh` script automates all installation steps:
```bash
sudo ./install.sh
```
This will handle OS detection, kernel module installation, file placement, and service setup automatically.

## Troubleshooting

### "applesmc sysfs not found"
- Ensure kernel modules are loaded: `sudo modprobe applesmc coretemp`
- Check: `ls /sys/devices/platform/applesmc.768/`

### Service won't start
- Check logs: `sudo journalctl -u imac-fan-control-headless.service -n 50`
- Verify the `ExecStart` path in the `.service` file matches your script location
- Ensure Python 3 is at `/usr/bin/python3`

### GUI won't display (systemd)
- GUI services under systemd are fragile; use desktop autostart instead
- If needed, manually run: `sudo python3 imac_fan_control.py`

### Fan not responding
- Verify `applesmc` module supports your iMac model
- Check fan exists: `cat /sys/devices/platform/applesmc.768/fan2_input`
- Test manual write: `echo 2000 > /sys/devices/platform/applesmc.768/fan2_output` (as root)

## Environment Variables

Only the headless script needs environment configuration (via systemd, already set).

For GUI service (if using systemd), ensure:
- `DISPLAY` environment variable points to correct X server (e.g., `:0`)
- User running GUI has X11 authority

## Notes

- **Root required:** Both scripts need root to write to `applesmc` sysfs files
- **Overlapping control:** Don't run both GUI + headless simultaneously on same fan (unpredictable behavior)
- **Temperature keys:** TS0V = "Wireless Module" temp (drives fan2 in headless mode)
- **Fan IDs:** 1=ODD, 2=HDD, 3=CPU

## Support

For applesmc kernel module issues, see:
- `modprobe applesmc`
- `/sys/devices/platform/applesmc.768/` (verify files exist)

---

**Created:** 2026-03-24  
**Updated:** 2026-10-13  
**Target:** openSUSE Tumbleweed, RaspberryOS (Debian-based), iMac 27" Late 2009
