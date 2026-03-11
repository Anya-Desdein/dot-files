#!/usr/bin/env python3
import sys
import json
import os
import glob
import urllib.request
import urllib.error
import time


# WAQI Configuration
WAQI_TOKEN = os.environ.get("WAQI_TOKEN", "")

SWAYSTATUS_DIR = os.environ.get("SWAYSTATUS_DIR", "/tmp/swaystatus").rstrip("/")
SWAYSTATUS_DATA_FILE = os.path.join(SWAYSTATUS_DIR, "swaystatus_airquality")
SWAYSTATUS_FORMATTED_FILE = SWAYSTATUS_DATA_FILE + "_formatted"

WAQI_LOCATION = os.environ.get("WAQI_LOCATION", "")

URL = f"https://api.waqi.info/feed/{WAQI_LOCATION}/?token={WAQI_TOKEN}"

# OpenUV configuration
OPENUV_TOKEN = os.environ.get("OPENUV_TOKEN", "")

OPENUV_LAT = os.environ.get("OPENUV_LAT", "37.7749")
OPENUV_LNG = os.environ.get("OPENUV_LNG", "-122.4194")
OPENUV_ALT = os.environ.get("OPENUV_ALT", "0")

OPENUV_DATA_FILE = os.path.join(SWAYSTATUS_DIR, "swaystatus_uv")
OPENUV_FORMATTED_FILE = OPENUV_DATA_FILE + "_formatted"
OPENUV_LOCATION_NAME = os.environ.get("OPENUV_LOCATION_NAME", "UV")


def time_to_burn_min(uv, skin_type):
    # Minutes to burn at given UVI for Fitzpatrick skin type. Returns None if no risk (UVI 0).
    mult = SKIN_TYPE_MULT.get(skin_type, SKIN_TYPE_MULT[1])
    if uv is None or uv <= 0:
        return None
    return (200 * mult) / (3 * uv)


# Fitzpatrick skin type 1–6; multiplier for time-to-burn: (200 * mult) / (3 * UVI) = minutes
SKIN_TYPE_MULT = {1: 2.5, 2: 3, 3: 4, 4: 5, 5: 8, 6: 15}
def _parse_skin_type():
    try:
        n = int(os.environ.get("OPENUV_SKIN_TYPE", "3").strip())
        return n if 1 <= n <= 6 else 3
    except (ValueError, TypeError):
        return 3


def get_uv_color(uv):
    # WHO UV index scale: 0-2 low, 3-5 moderate, 6-7 high, 8-10 very high, 11+ extreme
    # Expanded for more granularity
    if uv is None or uv < 0:
        return "⚪"
    if uv <= 1:
        return "🔵"
    if uv <= 2:
        return "🟢"
    if uv <= 5:
        return "🟡"
    if uv <= 7:
        return "🟠"
    if uv <= 10:
        return "🔴"
    return "🟣"


def get_color(t, v):
    # Pollutants (AQI scale)
    if t in ["pm25", "no2", "co", "so2", "pm10", "o3"]:
        return "⚪" if v<=0 else "🔵" if v<=25 else "🟢" if v<=50 else "🟡" if v<=100 else "🟠" if v<=150 else "🔴" if v<=200 else "🟣" if v<=300 else "🟤"
    
    return "⚪"


def _num(val, default=None):
    # Return float(val), or default if missing/invalid. Omit default for None.
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def format_uv(full_data):
    try:
        res = full_data.get("result", {}) if full_data else {}
        
        uv = _num(res.get("uv"), 666)
        uv_max = _num(res.get("uv_max"), 666)
        OPENUV_SKIN_TYPE = _parse_skin_type()
        
        parts = []
        if uv is not None:
            parts.append(f"UV{get_uv_color(uv)}{round(uv, 1)}")
        else:
            parts.append("UV666")
        if uv_max is not None:
            parts.append(f"UVmax{get_uv_color(uv_max)}{round(uv_max, 1)}")
        else:
            parts.append("UVmax666")

        burn_min = time_to_burn_min(uv_max, OPENUV_SKIN_TYPE)
        if burn_min is not None:
            parts.append(f"🔥{int(round(burn_min))}m")
        else:
            parts.append("🔥-∞m")

        return " | ".join(parts) if parts else "UV666 | UVmax666 | 🔥-∞m"
    except Exception:
        return "UV666 | UVmax666 | 🔥-∞m"

def format_aqi(full_data, uv_str=None):
    try:
        d = full_data.get("data", {}).get("iaqi", {})
        
        full_name = full_data.get("data", {}).get("city", {}).get("name", "N/A")
        point_name = full_name.split("(")[0].strip()

        # Remove me if you want full name
        if " - " in point_name:
            point_name = point_name.split(" - ", 1)[0].strip()
        elif "," in point_name:
            point_name = point_name.split(",", 1)[0].strip()

        pv = _num(d.get("pm25", {}).get("v"), -1)
        nv = _num(d.get("no2", {}).get("v"), -1)
        cv = _num(d.get("co", {}).get("v"), -1)
        hv = _num(d.get("h", {}).get("v"), -1)
        tv = _num(d.get("t", {}).get("v"), -273.15)

        pc  = get_color("pm25", pv)
        nc  = get_color("no2", nv)
        coc = get_color("co", cv)

        parts = [f"{point_name}:"]
        if pv >= 0:
            parts.append(f"PM2.5{pc}{pv}")
        if nv >= 0:
            parts.append(f"NO2{nc}{nv}")
        if cv >= 0:
            parts.append(f"CO{coc}{cv}")
        if uv_str:
            parts.append(uv_str)
        if tv > -273.15:
            parts.append(f"🌡️{round(tv)}°C")
        if hv >= 0:
            parts.append(f"💧{round(hv)}%")
        return " | ".join(parts) if len(parts) > 1 else ""
    except Exception:
        return ""

def _read_uv_str():
    try:
        if os.path.isfile(OPENUV_DATA_FILE):
            with open(OPENUV_DATA_FILE, "r") as f:
                return format_uv(json.load(f))
    except Exception:
        pass
    return None


def _is_network_error(e):
    # True if error is likely transient (network not ready, e.g. after reboot).
    if isinstance(e, urllib.error.URLError):
        return True
    if isinstance(e, OSError) and getattr(e, "errno", None) in (-3, None):
        return True  # errno -3: temporary failure in name resolution
    return False


def fetch_aqi_and_save():
    try:
        with urllib.request.urlopen(URL) as response:
            data = json.load(response)
        
        tmp_file = SWAYSTATUS_DATA_FILE + ".tmp"
        with open(tmp_file, "w") as f:
            json.dump(data, f)
        os.rename(tmp_file, SWAYSTATUS_DATA_FILE)
        
        uv_str = _read_uv_str() or ""
        formatted = format_aqi(data, uv_str=uv_str)
        tmp_fmt = SWAYSTATUS_FORMATTED_FILE + ".tmp"
        with open(tmp_fmt, "w") as f:
            f.write(formatted)
        os.rename(tmp_fmt, SWAYSTATUS_FORMATTED_FILE)            
    except Exception as e:
        if _is_network_error(e):
            raise


def fetch_uv_and_save():
    if not OPENUV_TOKEN or not OPENUV_LAT or not OPENUV_LNG:
        return
    try:
        url = f"https://api.openuv.io/api/v1/uv?lat={OPENUV_LAT}&lng={OPENUV_LNG}&alt={OPENUV_ALT}&dt="
        req = urllib.request.Request(url, headers={"x-access-token": OPENUV_TOKEN})
        with urllib.request.urlopen(req) as response:
            data = json.load(response)
        tmp_file = OPENUV_DATA_FILE + ".tmp"
        with open(tmp_file, "w") as f:
            json.dump(data, f)
        os.rename(tmp_file, OPENUV_DATA_FILE)
        formatted = format_uv(data)
        tmp_fmt = OPENUV_FORMATTED_FILE + ".tmp"
        with open(tmp_fmt, "w") as f:
            f.write(formatted)
        os.rename(tmp_fmt, OPENUV_FORMATTED_FILE)
    except Exception as e:
        if _is_network_error(e):
            raise


def run_until_ok(fn, max_retries=10, delay=1):
    # Run fn(); on network errors retry up to max_retries times with delay between.
    for attempt in range(max_retries):
        try:
            fn()
            return
        except Exception as e:
            if _is_network_error(e) and attempt < max_retries - 1:
                time.sleep(delay)
                continue
            raise


if __name__ == "__main__":
    os.makedirs(SWAYSTATUS_DIR, exist_ok=True)
    for f in glob.glob(os.path.join(SWAYSTATUS_DIR, "*.tmp")):
        try:
            os.remove(f)
        except OSError:
            pass
    # After reboot network may not be ready; retry until we get data or give up
    try:
        run_until_ok(fetch_uv_and_save)
    except Exception:
        pass
    try:
        run_until_ok(fetch_aqi_and_save)
    except Exception:
        pass

    # Loop every 30 minutes (1800 seconds)
    while True:
        time.sleep(1800)
        try:
            fetch_uv_and_save()
        except Exception:
            pass
        try:
            fetch_aqi_and_save()
        except Exception:
            pass