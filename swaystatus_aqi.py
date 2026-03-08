#!/usr/bin/env python3
import sys
import json
import os
import urllib.request
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
OPENUV_LAT = os.environ.get("OPENUV_LAT", "")
OPENUV_LNG = os.environ.get("OPENUV_LNG", "")
OPENUV_ALT = os.environ.get("OPENUV_ALT", "0")
OPENUV_DATA_FILE = os.path.join(SWAYSTATUS_DIR, "swaystatus_uv")
OPENUV_FORMATTED_FILE = OPENUV_DATA_FILE + "_formatted"
OPENUV_LOCATION_NAME = os.environ.get("OPENUV_LOCATION_NAME", "UV")

# Fitzpatrick skin type 1–6; multiplier for time-to-burn: (200 * mult) / (3 * UVI) = minutes
SKIN_TYPE_MULT = {1: 2.5, 2: 3, 3: 4, 4: 5, 5: 8, 6: 15}


def _parse_skin_type():
    try:
        n = int(os.environ.get("OPENUV_SKIN_TYPE", "1").strip())
        return n if 1 <= n <= 6 else 1
    except (ValueError, TypeError):
        return 1


OPENUV_SKIN_TYPE = _parse_skin_type()


def get_color(t, v):
    # Pollutants (AQI scale)
    if t in ["pm25", "no2", "co", "so2", "pm10", "o3", "aqi"]:
        return "⚪" if v<=0 else "🔵" if v<=25 else "🟢" if v<=50 else "🟡" if v<=100 else "🟠" if v<=150 else "🔴" if v<=200 else "🟣" if v<=300 else "🟤"
    
    return "⚪"


def get_uv_color(uv):
    # WHO UV index scale: 0-2 low, 3-5 moderate, 6-7 high, 8-10 very high, 11+ extreme
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


def time_to_burn_min(uv, skin_type):
    """Minutes to burn at given UVI for Fitzpatrick skin type. Returns None if no risk (UVI 0)."""
    mult = SKIN_TYPE_MULT.get(skin_type, SKIN_TYPE_MULT[1])
    if uv is None or uv <= 0:
        return None
    return (200 * mult) / (3 * uv)


def format_uv(full_data):
    try:
        res = full_data.get("result", {}) if full_data else {}
        uv = res.get("uv")
        uv_max = res.get("uv_max")
        uv_c = get_uv_color(uv)
        uv_max_c = get_uv_color(uv_max)
        uv_val = round(uv, 1) if uv is not None else "?"
        uv_max_val = round(uv_max, 1) if uv_max is not None else "?"
        burn_min = time_to_burn_min(uv_max, OPENUV_SKIN_TYPE)
        if burn_min is not None:
            burn_str = f"🔥{int(round(burn_min))}m"
        else:
            burn_str = "🔥∞"
        return f"UV{uv_c}{uv_val} | UVmax{uv_max_c}{uv_max_val} | {burn_str}"
    except Exception:
        return "UV⚪? | UVmax⚪? | 🔥?"


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

        pv = d.get("pm25",{}).get("v",-1)
        nv = d.get("no2",{}).get("v",-1)
        cv = d.get("co",{}).get("v",-1)
        hv = d.get("h",{}).get("v",-1)
        pres = d.get("p",{}).get("v",-1)
        tv = d.get("t",{}).get("v",-273.15) # Absolute zero
        wv = d.get("w",{}).get("v",36000) # Speed of sound

        pc  = get_color("pm25", pv)
        nc  = get_color("no2", nv)
        coc = get_color("co", cv)
        h, pres, t, w = hv, pres, tv, wv
        name = point_name
        
        t_rounded = round(t)
        h_rounded = round(h)
        pres_rounded = round(pres)
        w_rounded = round(w)
        
        after_co = f" | {uv_str}" if uv_str else ""
        return f"{name}: PM2.5{pc}{pv} | NO2{nc}{nv} | CO{coc}{cv}{after_co} | 🌡️{t_rounded}°C | 💧{h_rounded}% | 📥{pres_rounded}hPa | 💨{w_rounded}m/s"
    except Exception:
        return "N/A: PM2.5⚪-1 | NO2⚪-1 | CO⚪-1 | 🌡️-273°C | 💧-1% |  📥-1hPa | 💨36000m/s"

def _read_uv_str():
    try:
        if os.path.isfile(OPENUV_DATA_FILE):
            with open(OPENUV_DATA_FILE, "r") as f:
                return format_uv(json.load(f))
    except Exception:
        pass
    return None


def fetch_and_save():
    try:
        with urllib.request.urlopen(URL) as response:
            data = json.load(response)
        
        tmp_file = SWAYSTATUS_DATA_FILE + ".tmp"
        with open(tmp_file, "w") as f:
            json.dump(data, f)
        os.rename(tmp_file, SWAYSTATUS_DATA_FILE)
        
        uv_str = _read_uv_str() or "UV⚪? | UVmax⚪? | 🔥?"
        formatted = format_aqi(data, uv_str=uv_str)
        tmp_fmt = SWAYSTATUS_FORMATTED_FILE + ".tmp"
        with open(tmp_fmt, "w") as f:
            f.write(formatted)
        os.rename(tmp_fmt, SWAYSTATUS_FORMATTED_FILE)

        with open(SWAYSTATUS_DATA_FILE, "r") as f:
            saved_data = json.load(f)
        format_aqi(saved_data, uv_str=_read_uv_str() or "UV⚪? | UVmax⚪? | 🔥?")
            
    except Exception as e:
        pass


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
    except Exception:
        pass


if __name__ == "__main__":
    fetch_uv_and_save()
    fetch_and_save()

    # Loop every 30 minutes (1800 seconds)
    while True:
        time.sleep(1800)
        fetch_uv_and_save()
        fetch_and_save()
