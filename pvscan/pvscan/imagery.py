"""Download dei ritagli di ortofoto (passata e attuale), allineati pixel per pixel."""
import hashlib
import io
import math
import os

import requests
from PIL import Image
from pyproj import Transformer

_to_3857 = Transformer.from_crs(4326, 3857, always_xy=True)
UA = {"User-Agent": "pvscan/0.1 (open-source rooftop PV change detection)"}
CACHE_DIR = os.environ.get("PVSCAN_CACHE", ".cache")


def crop_geometry(poly_ll, margin_m: float, res_m: float, max_px: int = 1024):
    """BBox in EPSG:3857 attorno all'edificio + dimensione in pixel."""
    pts = [_to_3857.transform(x, y) for x, y in poly_ll.exterior.coords]
    lat = poly_ll.centroid.y
    k = math.cos(math.radians(lat))  # 1 m reale = 1/k unita' 3857
    m = margin_m / k
    xs, ys = zip(*pts)
    bbox = (min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m)
    w = max(64, min(max_px, int((bbox[2] - bbox[0]) * k / res_m)))
    h = max(64, min(max_px, int((bbox[3] - bbox[1]) * k / res_m)))
    # risoluzione effettiva (m/pixel) sull'asse x
    eff_res = (bbox[2] - bbox[0]) * k / w
    return bbox, (w, h), eff_res


def _cache_path(key: str):
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, hashlib.md5(key.encode()).hexdigest() + ".jpg")


def fetch(source: dict, bbox, size) -> Image.Image:
    """Scarica un ritaglio da una sorgente WMS o ArcGIS export."""
    w, h = size
    bb = ",".join(f"{v:.3f}" for v in bbox)
    if source["type"] == "wms":
        params = {
            "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap",
            "LAYERS": source["layer"], "STYLES": "", "CRS": "EPSG:3857",
            "BBOX": bb, "WIDTH": w, "HEIGHT": h, "FORMAT": "image/jpeg",
        }
    elif source["type"] == "arcgis":
        params = {
            "bbox": bb, "bboxSR": 3857, "imageSR": 3857, "size": f"{w},{h}",
            "format": "jpg", "f": "image",
        }
    else:
        raise ValueError(f"Tipo sorgente sconosciuto: {source['type']}")

    key = source["url"] + str(sorted(params.items()))
    path = _cache_path(key)
    if os.path.exists(path):
        return Image.open(path).convert("RGB")

    r = requests.get(source["url"], params=params, headers=UA, timeout=60)
    r.raise_for_status()
    if not r.headers.get("content-type", "").startswith("image"):
        raise RuntimeError(f"Risposta non immagine: {r.text[:200]}")
    img = Image.open(io.BytesIO(r.content)).convert("RGB")
    img.save(path, quality=92)
    return img
