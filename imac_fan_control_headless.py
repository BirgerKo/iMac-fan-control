#!/usr/bin/env python3
"""Headless iMac fan control monitor (applesmc).

Sets fan2 to manual mode and 2000 RPM on startup. Then polls SMC temps every
10 seconds and adjusts fan2 to 3000 RPM if TS0V > 48°C, or back to 2000 RPM
if TS0V < 47°C.
"""

from pathlib import Path
from time import sleep
import sys
import signal

APPLESMC_BASE = Path("/sys/devices/platform/applesmc.768")
FAN_ID = 2
FAN_LOW_RPM = 2000
FAN_HIGH_RPM = 3000
TEMP_KEY = "TS0V"
POLL_SEC = 10

running = True


def _read_text(path: Path) -> str:
    try:
        return path.read_text().strip()
    except Exception:
        return ""


def _read_int(path: Path, default: int = 0) -> int:
    try:
        return int(_read_text(path))
    except Exception:
        return default


def _write_text(path: Path, value: str) -> None:
    path.write_text(str(value))


def find_temp_index(smc_key: str) -> int | None:
    for idx in range(1, 32):
        label_path = APPLESMC_BASE / f"temp{idx}_label"
        if not label_path.exists():
            continue
        if _read_text(label_path) == smc_key:
            return idx
    return None


def get_temp(smc_key: str) -> float | None:
    idx = find_temp_index(smc_key)
    if idx is None:
        return None
    raw = _read_int(APPLESMC_BASE / f"temp{idx}_input", 0)
    return raw / 1000.0


def set_fan_manual(manual: bool) -> None:
    _write_text(APPLESMC_BASE / f"fan{FAN_ID}_manual", "1" if manual else "0")


def set_fan_speed(rpm: int) -> None:
    _write_text(APPLESMC_BASE / f"fan{FAN_ID}_output", str(int(rpm)))


def _cleanup(signum, frame):
    global running
    running = False


def main():
    if not APPLESMC_BASE.is_dir():
        print(f"ERROR: applesmc sysfs not found at {APPLESMC_BASE}")
        sys.exit(1)

    signal.signal(signal.SIGINT, _cleanup)
    signal.signal(signal.SIGTERM, _cleanup)

    try:
        print(f"Enabling fan{FAN_ID} manual mode and setting {FAN_LOW_RPM} RPM")
        set_fan_manual(True)
        set_fan_speed(FAN_LOW_RPM)
    except PermissionError:
        print("ERROR: Root privileges required. Run with sudo.")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to initialize fan: {e}")
        sys.exit(1)

    while running:
        temp = get_temp(TEMP_KEY)
        if temp is None:
            print(f"WARNING: {TEMP_KEY} sensor not found")
        else:
            print(f"{TEMP_KEY}: {temp:.1f}°C")
            try:
                current = _read_int(APPLESMC_BASE / f"fan{FAN_ID}_input", 0)
            except Exception:
                current = 0

            if temp > 48 and current < FAN_HIGH_RPM:
                print(f"-> {TEMP_KEY} > 48°C: raising fan{FAN_ID} to {FAN_HIGH_RPM} RPM")
                set_fan_speed(FAN_HIGH_RPM)
            elif temp < 47 and current > FAN_LOW_RPM:
                print(f"-> {TEMP_KEY} < 47°C: lowering fan{FAN_ID} to {FAN_LOW_RPM} RPM")
                set_fan_speed(FAN_LOW_RPM)

        sleep(POLL_SEC)

    # Cleanup: restore automatic control
    try:
        print("Restoring fan to automatic mode")
        set_fan_manual(False)
    except Exception:
        pass


if __name__ == "__main__":
    main()
