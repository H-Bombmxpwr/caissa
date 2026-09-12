"""Best-effort machine telemetry to show beside the engine.

Nothing here is required and nothing here is estimated. Core counts come from the
OS; heat and power draw are read from whatever the firmware chooses to publish,
which on Windows is a coin toss — plenty of desktops expose no thermal zone at
all, and a machine on mains power reports no discharge rate because it is not
discharging. Anything the machine will not tell us is reported as None so the
interface can say "not available" instead of inventing a number.

Probing costs a subprocess on Windows, so readings are cached and refreshed on a
background thread: callers always get the last known values immediately.
"""

import json
import platform
import subprocess
import threading
import time

try:                                                    # optional, and worth having
    import psutil
except ImportError:                                     # pragma: no cover - depends on install
    psutil = None

WINDOWS = platform.system().lower() == "windows"
REFRESH_SECONDS = 5.0                                   # firmware sensors move slowly
PROBE_TIMEOUT = 6

# One shell round trip for both sensors. Errors are swallowed per-sensor so a
# machine with a thermal zone but no battery still reports its temperature.
POWERSHELL_PROBE = r"""
$out = @{}
# LibreHardwareMonitor / OpenHardwareMonitor publish real per-package readings
# when one of them is running; nothing else on Windows reports CPU watts.
foreach ($ns in 'root/LibreHardwareMonitor', 'root/OpenHardwareMonitor') {
  try {
    $sensors = Get-CimInstance -Namespace $ns -ClassName Sensor -ErrorAction Stop
    $cpu = $sensors | Where-Object { $_.Identifier -like '/*cpu*' }
    $temp = $cpu | Where-Object { $_.SensorType -eq 'Temperature' -and $_.Name -match 'Package|Tdie|Tctl|CPU Total|Average' } | Select-Object -First 1
    if (-not $temp) { $temp = $cpu | Where-Object { $_.SensorType -eq 'Temperature' } | Sort-Object Value -Descending | Select-Object -First 1 }
    $watts = $cpu | Where-Object { $_.SensorType -eq 'Power' -and $_.Name -match 'Package|CPU' } | Select-Object -First 1
    if ($temp) { $out.monitor_temp_c = [double]$temp.Value; $out.monitor_name = [string]$temp.Name }
    if ($watts) { $out.monitor_power_w = [double]$watts.Value }
    if ($temp -or $watts) { $out.monitor = $ns; break }
  } catch {}
}
try {
  $zones = Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction Stop
  $max = ($zones | Select-Object -ExpandProperty CurrentTemperature | Measure-Object -Maximum).Maximum
  if ($max) { $out.thermal_zone_decikelvin = [int]$max }
} catch {}
try {
  $b = Get-CimInstance -Namespace root/wmi -ClassName BatteryStatus -ErrorAction Stop | Select-Object -First 1
  if ($b) {
    $out.discharge_mw = [int]$b.DischargeRate
    $out.charge_mw = [int]$b.ChargeRate
    $out.voltage_mv = [int]$b.Voltage
    $out.on_ac = [bool]$b.PowerOnline
  }
} catch {}
$out | ConvertTo-Json -Compress
"""


def cores():
    """Logical and physical core counts, physical only when psutil can tell us."""
    logical = None
    physical = None
    if psutil:
        logical = psutil.cpu_count(logical=True)
        physical = psutil.cpu_count(logical=False)
    if not logical:
        import os
        logical = os.cpu_count()
    return {"logical": logical, "physical": physical}


def _linux_temperature():
    if not psutil or not hasattr(psutil, "sensors_temperatures"):
        return None, None
    try:
        groups = psutil.sensors_temperatures()
    except Exception:                                   # noqa: BLE001 - platform dependent
        return None, None
    # Prefer the package sensor, then any core, then anything at all.
    for preferred in ("coretemp", "k10temp", "cpu_thermal", "acpitz", "zenpower"):
        for entry in groups.get(preferred, []):
            if entry.current:
                return round(float(entry.current), 1), preferred
    for label, entries in groups.items():
        for entry in entries:
            if entry.current:
                return round(float(entry.current), 1), label
    return None, None


def _windows_probe():
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", POWERSHELL_PROBE],
            capture_output=True, text=True, timeout=PROBE_TIMEOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    text = (out.stdout or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class CpuLoad:
    """Whole-machine CPU load, measured from our own reading of the CPU time counters.

    ``psutil.cpu_percent(interval=None)`` reports the load since the last call made
    anywhere in the process, and keeps that "last call" in module-level state. The
    live-analysis panel polls several times a second across many server threads, so
    that shared state gets reset out from under us and a poll lands on a zero-length
    interval — reporting 0% while the engine has every core pinned.

    Taking the ``cpu_times()`` snapshot ourselves removes the shared state: the window
    is the one between our own two samples, whoever else is asking. Readings are cached
    between samples so rapid polling is cheap as well as correct.
    """

    MIN_INTERVAL = 0.5

    def __init__(self):
        self.lock = threading.Lock()
        self.percent = None
        self.previous = None
        self.sampled_at = 0.0

    @staticmethod
    def _times():
        if not psutil:
            return None
        try:
            return psutil.cpu_times()
        except Exception:                               # noqa: BLE001
            return None

    def read(self):
        now = time.monotonic()
        with self.lock:
            if self.percent is not None and now - self.sampled_at < self.MIN_INTERVAL:
                return self.percent
            current = self._times()
            if current is None:
                return self.percent
            previous, self.previous, self.sampled_at = self.previous, current, now
            if previous is None:
                return self.percent                     # first sample: nothing to compare to
            total = sum(current) - sum(previous)
            idle = current.idle - previous.idle
            if total <= 0:
                return self.percent                     # the counters have not moved yet
            self.percent = round(max(0.0, min(100.0, 100.0 * (total - idle) / total)), 1)
            return self.percent


CPU_LOAD = CpuLoad()


class Telemetry:
    """Cached sensor readings, refreshed off the request thread."""

    def __init__(self):
        self.lock = threading.Lock()
        self.reading = {"temperature_c": None, "temperature_source": None,
                        "power_w": None, "power_source": None, "sampled_at": 0}
        self.refreshing = False

    def snapshot(self):
        with self.lock:
            reading = dict(self.reading)
            stale = time.time() - reading["sampled_at"] > REFRESH_SECONDS
            if stale and not self.refreshing:
                self.refreshing = True
                threading.Thread(target=self._refresh, daemon=True).start()
        return reading

    def _refresh(self):
        try:
            fresh = self._sample()
        except Exception:                               # noqa: BLE001 - telemetry never fails loudly
            fresh = {"temperature_c": None, "temperature_source": None,
                     "power_w": None, "power_source": None}
        fresh["sampled_at"] = time.time()
        with self.lock:
            self.reading = fresh
            self.refreshing = False

    def _sample(self):
        temperature, source = _linux_temperature()
        power = None
        power_source = None
        if psutil and hasattr(psutil, "sensors_battery"):
            try:
                battery = psutil.sensors_battery()
                if battery is not None:
                    power_source = "mains" if battery.power_plugged else "battery"
            except Exception:                           # noqa: BLE001
                pass
        if WINDOWS:
            probe = _windows_probe()
            if probe.get("monitor_temp_c"):
                temperature = round(float(probe["monitor_temp_c"]), 1)
                source = (probe.get("monitor_name") or "CPU") + " via " + probe["monitor"].split("/")[-1]
            if probe.get("monitor_power_w"):
                power = round(float(probe["monitor_power_w"]), 1)
                power_source = "CPU package"
            decikelvin = probe.get("thermal_zone_decikelvin")
            if temperature is None and decikelvin:
                # ACPI reports tenths of a Kelvin; below freezing means a bogus zone.
                celsius = decikelvin / 10.0 - 273.15
                if -20 < celsius < 150:
                    temperature, source = round(celsius, 1), "ACPI thermal zone"
            if probe.get("on_ac") is not None:
                power_source = "mains" if probe["on_ac"] else "battery"
            milliwatts = probe.get("discharge_mw") or 0
            if power is None and milliwatts:
                power = round(milliwatts / 1000.0, 1)
                power_source = "whole machine, on battery"
            elif power is None and probe.get("charge_mw"):
                power = round(probe["charge_mw"] / 1000.0, 1)
                power_source = "charging"
        return {"temperature_c": temperature, "temperature_source": source,
                "power_w": power, "power_source": power_source}


TELEMETRY = Telemetry()


def system():
    """Whole-machine load, heat and power, as far as this machine will say."""
    out = {"cores": cores(), "cpu_percent": None, "cpu_mhz": None,
           "memory_used_mb": None, "memory_total_mb": None, "psutil": bool(psutil)}
    if psutil:
        try:
            out["cpu_percent"] = CPU_LOAD.read()
            memory = psutil.virtual_memory()
            out["memory_used_mb"] = round(memory.used / 1048576)
            out["memory_total_mb"] = round(memory.total / 1048576)
            frequency = psutil.cpu_freq()
            if frequency and frequency.current:
                out["cpu_mhz"] = round(frequency.current)
        except Exception:                               # noqa: BLE001
            pass
    out.update(TELEMETRY.snapshot())
    return out
