#!/usr/bin/env python3
import sys
import json
import os
import urllib.request
import time

# Configuration
TOKEN = os.environ.get("TOKEN", "")
DATA_FILE = os.environ.get("DATA_FILE", "/tmp/swaystatus/swaystatus_airquality")
URL = f"https://api.waqi.info/feed/wroclaw/?token={TOKEN}"

def fetch_and_save():
    try:
        with urllib.request.urlopen(URL) as response:
            data = json.load(response)
        
        tmp_file = DATA_FILE + ".tmp"
        with open(tmp_file, "w") as f:
            json.dump(data, f)
        os.rename(tmp_file, DATA_FILE)
    except Exception as e:
        pass

if __name__ == "__main__":
    fetch_and_save()
    
    # Loop every 30 minutes (1800 seconds)
    while True:
        time.sleep(1800)
        fetch_and_save()
