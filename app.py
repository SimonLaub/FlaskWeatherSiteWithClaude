from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import requests
from flask import Flask, render_template

app = Flask(__name__)

DMI_OBSERVATIONS_URL = "https://opendataapi.dmi.dk/v2/metObs/collections/observation/items"
DMI_RADAR_IMAGE_URL = "https://www.dmi.dk/dmidk_byvejrWS/rest/image/gif/Radar/"
METEOALARM_DENMARK_FEED = "https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-denmark"

ATOM_NS = "{http://www.w3.org/2005/Atom}"
CAP_NS = "{urn:oasis:names:tc:emergency:cap:1.2}"

COPENHAGEN_TZ = ZoneInfo("Europe/Berlin")
DISPLAY_FORMAT = "%d-%m-%Y kl. %H:%M"

STATIONS = [
    {"id": "06102", "name": "Horsens (Bygholm)"},
    {"id": "06120", "name": "Odense"},
    {"id": "06060", "name": "Karup"},
    {"id": "06041", "name": "Skagen"},
    {"id": "06109", "name": "Askov"},
    {"id": "06190", "name": "Bornholm"},
]


def get_latest_temperature(station_id):
    params = {
        "stationId": station_id,
        "parameterId": "temp_dry",
        "limit": 1,
        "sortorder": "observed,DESC",
    }
    try:
        response = requests.get(DMI_OBSERVATIONS_URL, params=params, timeout=10)
        response.raise_for_status()
        features = response.json().get("features", [])
    except requests.RequestException:
        return None

    if not features:
        return None

    feature = features[0]
    props = feature["properties"]
    lon, lat = feature["geometry"]["coordinates"]
    return {"value": props["value"], "observed": props["observed"], "lat": lat, "lon": lon}


def get_active_warnings():
    try:
        response = requests.get(METEOALARM_DENMARK_FEED, timeout=10)
        response.raise_for_status()
        root = ElementTree.fromstring(response.content)
    except (requests.RequestException, ElementTree.ParseError):
        return None

    warnings = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        title_el = entry.find(f"{ATOM_NS}title")
        summary_el = entry.find(f"{ATOM_NS}summary")
        info_el = entry.find(f"{CAP_NS}info")

        area = None
        severity = None
        event = None
        effective = None
        expires = None
        if info_el is not None:
            area_el = info_el.find(f"{CAP_NS}area/{CAP_NS}areaDesc")
            area = area_el.text if area_el is not None else None
            severity_el = info_el.find(f"{CAP_NS}severity")
            severity = severity_el.text if severity_el is not None else None
            event_el = info_el.find(f"{CAP_NS}event")
            event = event_el.text if event_el is not None else None
            effective_el = info_el.find(f"{CAP_NS}effective")
            effective = effective_el.text if effective_el is not None else None
            expires_el = info_el.find(f"{CAP_NS}expires")
            expires = expires_el.text if expires_el is not None else None

        warnings.append({
            "title": title_el.text if title_el is not None else "Varsel",
            "summary": summary_el.text if summary_el is not None else "",
            "area": area,
            "severity": severity,
            "event": event,
            "effective": effective,
            "expires": expires,
        })
    return warnings


def get_radar_timestamp():
    try:
        response = requests.head(DMI_RADAR_IMAGE_URL, timeout=10)
        response.raise_for_status()
        response_time = parsedate_to_datetime(response.headers["Date"])
        age_seconds = int(response.headers.get("Age", 0))
    except (requests.RequestException, KeyError, ValueError):
        return None

    image_time = response_time - timedelta(seconds=age_seconds)
    return image_time.astimezone(COPENHAGEN_TZ)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/weather")
def weather():
    readings = []
    for station in STATIONS:
        latest = get_latest_temperature(station["id"])
        readings.append({
            "name": station["name"],
            "temp": latest["value"] if latest else None,
            "observed": latest["observed"] if latest else None,
            "lat": latest["lat"] if latest else None,
            "lon": latest["lon"] if latest else None,
        })
    return render_template("weather.html", readings=readings)


@app.route("/radar")
def radar():
    warnings = get_active_warnings()
    radar_timestamp = get_radar_timestamp()
    checked_at = datetime.now(tz=COPENHAGEN_TZ)
    return render_template(
        "radar.html",
        radar_image_url=DMI_RADAR_IMAGE_URL,
        warnings=warnings,
        radar_timestamp=radar_timestamp.strftime(DISPLAY_FORMAT) if radar_timestamp else None,
        checked_at=checked_at.strftime(DISPLAY_FORMAT),
    )


if __name__ == "__main__":
    app.run(debug=True)
