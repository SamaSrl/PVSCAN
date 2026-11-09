"""Geocoding, selezione area ed estrazione edifici da OpenStreetMap."""
import math
import time

import requests
from pyproj import Transformer
from shapely.geometry import Polygon, Point, box
from shapely.ops import transform

UA = {"User-Agent": "pvscan/0.1 (open-source rooftop PV change detection)"}
OVERPASS = "https://z.overpass-api.de/api/interpreter"
_to_m = Transformer.from_crs(4326, 3035, always_xy=True).transform


def geocode(query: str):
    """Restituisce (lat, lon) di un luogo tramite Nominatim."""
    r = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": query, "format": "json", "limit": 1},
        headers=UA,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if not data:
        raise ValueError(f"Luogo non trovato: {query}")
    return float(data[0]["lat"]), float(data[0]["lon"])


def circle_polygon(lat: float, lon: float, km: float, n: int = 96) -> Polygon:
    """Cerchio (raggio in linea d'aria) come poligono lon/lat."""
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        dlat = km / 111.32 * math.cos(a)
        dlon = km / (111.32 * math.cos(math.radians(lat))) * math.sin(a)
        pts.append((lon + dlon, lat + dlat))
    return Polygon(pts)


def area_m2(poly_ll: Polygon) -> float:
    return transform(_to_m, poly_ll).area


def _overpass(query: str, retries: int = 4):
    for attempt in range(retries):
        try:
            r = requests.post(OVERPASS, data={"data": query}, headers=UA, timeout=240)
            if r.status_code in (429, 504):
                time.sleep(10 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(5 * (attempt + 1))
    return {"elements": []}


def buildings(area_ll: Polygon, min_area_m2: float = 700, cell_deg: float = 0.1,
              progress=None):
    """Edifici OSM nell'area con superficie >= min_area_m2.

    L'area viene suddivisa in celle per non far andare in timeout Overpass.
    Ogni edificio: {id, poly (lon/lat), area_m2, centroid (lon, lat), tags}.
    """
    minx, miny, maxx, maxy = area_ll.bounds
    cells = []
    y = miny
    while y < maxy:
        x = minx
        while x < maxx:
            c = box(x, y, min(x + cell_deg, maxx), min(y + cell_deg, maxy))
            if c.intersects(area_ll):
                cells.append(c)
            x += cell_deg
        y += cell_deg

    found = {}
    for i, c in enumerate(cells):
        s, w, n, e = c.bounds[1], c.bounds[0], c.bounds[3], c.bounds[2]
        q = f'[out:json][timeout:180];way["building"]({s},{w},{n},{e});out geom tags;'
        data = _overpass(q)
        for el in data.get("elements", []):
            if el["id"] in found or "geometry" not in el:
                continue
            pts = [(p["lon"], p["lat"]) for p in el["geometry"]]
            if len(pts) < 4:
                continue
            poly = Polygon(pts)
            if not poly.is_valid or poly.is_empty:
                continue
            ctr = poly.centroid
            if not area_ll.contains(Point(ctr.x, ctr.y)):
                continue
            a = area_m2(poly)
            if a < min_area_m2:
                continue
            found[el["id"]] = {
                "id": el["id"],
                "poly": poly,
                "area_m2": a,
                "centroid": (ctr.x, ctr.y),
                "tags": el.get("tags", {}),
            }
        if progress:
            progress(i + 1, len(cells))
        time.sleep(1)  # cortesia verso Overpass
    return list(found.values())
