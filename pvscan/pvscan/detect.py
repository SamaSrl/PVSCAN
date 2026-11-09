"""Rilevamento euristico di pannelli fotovoltaici su un ritaglio ortofoto.

ATTENZIONE: e' un rilevatore di base (colore/scuro-bluastro + dimensione dei
blob) che produce *candidati* da verificare nel report. Per risultati seri
sostituisci `detect_panels` con un modello di segmentazione addestrato
(vedi README).
"""
import numpy as np
from PIL import Image, ImageDraw
from pyproj import Transformer
from scipy import ndimage

_to_3857 = Transformer.from_crs(4326, 3857, always_xy=True)


def polygon_mask(poly_ll, bbox, size) -> np.ndarray:
    """Maschera booleana dell'edificio nel ritaglio."""
    w, h = size
    minx, miny, maxx, maxy = bbox
    pts = []
    for x, y in poly_ll.exterior.coords:
        mx, my = _to_3857.transform(x, y)
        pts.append(((mx - minx) / (maxx - minx) * w, (maxy - my) / (maxy - miny) * h))
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).polygon(pts, fill=1)
    return np.array(m, dtype=bool)


def detect_panels(img: Image.Image, mask: np.ndarray, res_m: float,
                  min_component_m2: float = 15.0):
    """Restituisce (maschera_pannelli, area_pannelli_m2)."""
    rgb = np.array(img).astype(np.int16)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    v = rgb.max(axis=2)

    bluish_dark = (b > r + 8) & (b >= g - 5) & (v < 150)
    very_dark = v < 70
    m = (bluish_dark | very_dark) & mask

    m = ndimage.binary_opening(m, iterations=2)
    m = ndimage.binary_closing(m, iterations=2)

    min_px = int(min_component_m2 / (res_m ** 2))
    lab, n = ndimage.label(m)
    if n:
        sizes = ndimage.sum(m, lab, range(1, n + 1))
        keep = np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s >= min_px])
        m = keep
    area = float(m.sum()) * res_m ** 2
    return m, area


def overlay(img: Image.Image, panel_mask: np.ndarray) -> Image.Image:
    """Evidenzia in rosso i pixel rilevati come pannelli (per il report)."""
    a = np.array(img).copy()
    a[panel_mask] = (0.5 * a[panel_mask] + 0.5 * np.array([255, 0, 0])).astype(np.uint8)
    return Image.fromarray(a)
