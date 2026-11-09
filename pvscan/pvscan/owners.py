"""Identificazione dell'attivita'/ente associato a un edificio.

Fonti usate (solo dati pubblici sulle *attivita'*, non su persone fisiche):
  1. tag OpenStreetMap dell'edificio (name, operator, addr:*)
  2. Google Places (Nearby Search, se GOOGLE_MAPS_API_KEY e' impostata)
  3. Nominatim reverse (indirizzo)

Il proprietario catastale NON e' ricavabile da fonti aperte: le visure
catastali richiedono accesso autorizzato e sono dati personali (GDPR).
"""
import os

import requests

UA = {"User-Agent": "pvscan/0.1 (open-source rooftop PV change detection)"}


def _osm_tags(tags: dict):
    name = tags.get("name") or tags.get("operator") or tags.get("brand")
    addr = " ".join(
        p for p in [tags.get("addr:street"), tags.get("addr:housenumber"),
                    tags.get("addr:city")] if p
    )
    return name, addr


def _google_places(lat, lon, radius_m, exclude_types):
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key:
        return None
    r = requests.post(
        "https://places.googleapis.com/v1/places:searchNearby",
        headers={
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.types",
        },
        json={
            "maxResultCount": 5,
            "locationRestriction": {"circle": {
                "center": {"latitude": lat, "longitude": lon}, "radius": radius_m}},
        },
        timeout=30,
    )
    if r.status_code != 200:
        return None
    out = []
    for p in r.json().get("places", []):
        types = set(p.get("types", []))
        if types & set(exclude_types):
            continue
        out.append(f'{p["displayName"]["text"]} ({p.get("formattedAddress", "")})')
    return out or None


def _reverse(lat, lon):
    r = requests.get(
        "https://nominatim.openstreetmap.org/reverse",
        params={"lat": lat, "lon": lon, "format": "json", "zoom": 18},
        headers=UA, timeout=30,
    )
    if r.status_code != 200:
        return ""
    return r.json().get("display_name", "")


def find_owner(building: dict, cfg: dict) -> dict:
    lon, lat = building["centroid"]
    name, addr = _osm_tags(building["tags"])
    places = _google_places(lat, lon, cfg.get("google_places_radius_m", 40),
                            cfg.get("exclude_types", []))
    if not addr:
        addr = _reverse(lat, lon)
    return {
        "osm_name": name or "",
        "google_places": "; ".join(places) if places else "",
        "address": addr,
    }
