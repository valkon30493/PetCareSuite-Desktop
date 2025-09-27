# pip install packaging
import json, sys, webbrowser
from urllib.request import urlopen
from urllib.error import URLError, HTTPError
from packaging import version
from version import APP_VERSION, CHANNEL

BASE_URL = "https://<your-domain>/petwellnessapp"  # <- change this

def _appcast_url():
    return f"{BASE_URL}/{CHANNEL}/appcast.json"

def check_for_update(timeout_seconds: int = 5):
    try:
        with urlopen(_appcast_url(), timeout=timeout_seconds) as r:
            data = json.load(r)
        latest = data.get("latest", APP_VERSION)
        if version.parse(latest) > version.parse(APP_VERSION):
            return data
    except (URLError, HTTPError, ValueError):
        return None
    return None

def start_update_flow(appcast: dict):
    url = appcast.get("win_url") or appcast.get("mac_url") or appcast.get("url")
    if url:
        webbrowser.open(url)
        return True
    return False

