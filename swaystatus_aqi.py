#!/usr/bin/env python3
import sys
import json
import os
import urllib.request
import time


# Configuration
SWAYSTATUS_TOKEN = os.environ.get("SWAYSTATUS_TOKEN", "")

SWAYSTATUS_DATA_FILE = os.environ.get("SWAYSTATUS_DATA_FILE", "/tmp/swaystatus/swaystatus_airquality")
SWAYSTATUS_FORMATTED_FILE = SWAYSTATUS_DATA_FILE + "_formatted"

SWAYSTATUS_LOCATION = os.environ.get("SWAYSTATUS_LOCATION", "")

URL = f"https://api.waqi.info/feed/{SWAYSTATUS_LOCATION}/?token={SWAYSTATUS_TOKEN}"


def get_color(t, v):
    # Pollutants (AQI scale)
    if t in ["pm25", "no2", "co", "so2", "pm10", "o3", "aqi"]:
        return "⚪" if v<=0 else "🔵" if v<=25 else "🟢" if v<=50 else "🟡" if v<=100 else "🟠" if v<=150 else "🔴" if v<=200 else "🟣" if v<=300 else "🟤"
    
    return "⚪"


def format_aqi(full_data):
    try:
        d = full_data.get("data", {}).get("iaqi", {})
        
        # Extract name
        full_name = full_data.get("data", {}).get("city", {}).get("name", "N/A")
        point_name = full_name.split("(")[0].strip()
        
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
        
        return f"{name}: PM2.5{pc}{pv} | NO2{nc}{nv} | CO{coc}{cv} | 🌡️{t_rounded}°C | 💧{h_rounded}% | 📥{pres_rounded}hPa | 💨{w_rounded}m/s"
    except Exception:2
        return "N/A: PM2.5⚪-1 | NO2⚪-1 | CO⚪-1 | 🌡️-273°C | 💧-1% |  📥-1hPa | 💨36000m/s"

def fetch_and_save():
    try:
        with urllib.request.urlopen(URL) as response:
            data = json.load(response)
        
        tmp_file = SWAYSTATUS_DATA_FILE + ".tmp"
        with open(tmp_file, "w") as f:
            json.dump(data, f)
        os.rename(tmp_file, SWAYSTATUS_DATA_FILE)
        
        formatted = format_aqi(data)
        tmp_fmt = SWAYSTATUS_FORMATTED_FILE + ".tmp"
        with open(tmp_fmt, "w") as f:
            f.write(formatted)
        os.rename(tmp_fmt, SWAYSTATUS_FORMATTED_FILE)

        with open(SWAYSTATUS_DATA_FILE, "r") as f:
            saved_data = json.load(f)
        format_aqi(saved_data)
            
    except Exception as e:
        pass

if __name__ == "__main__":
    fetch_and_save()
    
    # Loop every 30 minutes (1800 seconds)
    while True:
        time.sleep(1800)
        fetch_and_save()
