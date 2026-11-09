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
                  min_component_m2: float = 12.0):
    """Restituisce (maschera_pannelli, area_pannelli_m2) con logica HSV + Geometrica."""
    # Convertiamo l'immagine in RGB e in float per calcoli precisi
    img_rgb = img.convert("RGB")
    arr_rgb = np.array(img_rgb)
    
    # Conversione in HSV tramite Pillow per una stima del colore indipendente dall'ombra
    img_hsv = img_rgb.convert("HSV")
    arr_hsv = np.array(img_hsv)
    
    # Canali HSV (in PIL H è 0-255, S è 0-255, V è 0-255)
    h_chan = arr_hsv[..., 0]
    s_chan = arr_hsv[..., 1]
    v_chan = arr_hsv[..., 2]
    
    r, g, b = arr_rgb[..., 0], arr_rgb[..., 1], arr_rgb[..., 2]

    # 1. Criterio cromatico avanzato (Spazio HSV + RGB potenziato)
    # I pannelli fotovoltaici tipicamente hanno una tonalità blu/azzurra (H tra 90 e 170 circa in PIL) 
    # e una saturazione moderata/bassa ma superiore allo sfondo grigio neutro, oppure sono molto scuri.
    is_bluish = (h_chan >= 85) & (h_chan <= 175) & (s_chan > 25) & (v_chan < 180)
    
    # Criterio ausiliario RGB (Blu marcatamente superiore al rosso)
    rgb_bluish_dark = (b.astype(np.int16) > r.astype(np.int16) + 10) & (v_chan < 140)
    
    # Zona scura generale (es. tetti neri o celle in ombra profonda) ma vincolata alla maschera
    very_dark = (v_chan < 55) & (s_chan < 50)

    m = (is_bluish | rgb_bluish_dark | very_dark) & mask

    # 2. Pulizia morfologica di base per rimuovere il rumore pixel-per-pixel
    m = ndimage.binary_opening(m, iterations=1)
    m = ndimage.binary_closing(m, iterations=2)

    # 3. Filtraggio per dimensione e geometria (Eliminazione falsi positivi come comignoli o macchie)
    min_px = int(min_component_m2 / (res_m ** 2))
    lab, n = ndimage.label(m)
    
    if n > 0:
        # Estraiamo le proprietà delle componenti con scikit-image o scipy.ndimage
        slices = ndimage.find_objects(lab)
        valid_mask = np.zeros_like(m, dtype=bool)
        
        for i, slc in enumerate(slices):
            if slc is None:
                continue
            component_mask = (lab[slc] == (i + 1))
            size_px = component_mask.sum()
            
            # Filtro dimensione minima
            if size_px < min_px:
                continue
                
            # Filtro geometrico avanzato (Rapporto di forma / Eccentricità approssimata)
            # Un pannello o un gruppo di pannelli non è un pixel solitario o una linea infinita
            ymin, ymax = slc[0].start, slc[0].stop
            xmin, xmax = slc[1].start, slc[1].stop
            h_box = ymax - ymin
            w_box = xmax - xmin
            
            if h_box == 0 or w_box == 0:
                continue
                
            aspect_ratio = max(h_box, w_box) / min(h_box, w_box)
            
            # I banchi di pannelli raramente hanno un aspect ratio estremo (> 6:1) nei tetti residenziali/industriali standard
            # E scartiamo oggetti troppo "buchi" o vuoti se necessario
            if aspect_ratio < 7.0:
                valid_mask[slc] |= component_mask
                
        m = valid_mask

    area = float(m.sum()) * (res_m ** 2)
    return m, area


def overlay(img: Image.Image, panel_mask: np.ndarray) -> Image.Image:
    """Evidenzia in rosso semi-trasparente i pixel rilevati come pannelli."""
    a = np.array(img.convert("RGB")).copy()
    # Sovrapposizione colore rosso vivida ma trasparente (50%)
    overlay_color = np.array([255, 0, 0], dtype=np.float32)
    target_pixels = panel_mask
    if target_pixels.any():
        a[target_pixels] = (0.4 * a[target_pixels].astype(np.float32) + 0.6 * overlay_color).astype(np.uint8)
    return Image.fromarray(a)
