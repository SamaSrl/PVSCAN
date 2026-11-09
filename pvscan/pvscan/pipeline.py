"""Pipeline: area -> edifici -> confronto ortofoto passata/attuale -> lista con indirizzi.

Uso CLI:
    python -m pvscan.pipeline --city Treviso --radius-km 30 --out out
    python -m pvscan.pipeline --geojson area.geojson --out out
"""
import argparse
import base64
import csv
import io
import json
import os
from concurrent.futures import ThreadPoolExecutor
from . import geo, imagery, detect, owners

import yaml
from pathlib import Path

def load_config():
    # Cerca config.yaml nella cartella superiore o nella posizione corretta
    path = Path(__file__).parent.parent / "config.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)

def analyze_building(b, cfg):
    s = cfg["search"]
    bbox, size, res = imagery.crop_geometry(
        b["poly"], s["margin_m"], s["resolution_m"])
    try:
        past = imagery.fetch(cfg["past_imagery"], bbox, size)
        now = imagery.fetch(cfg["current_imagery"], bbox, size)
    except Exception as e:  # tile mancante, rete, ecc.
        return None
    mask = detect.polygon_mask(b["poly"], bbox, size)
    pm, pa = detect.detect_panels(past, mask, res, s["min_component_m2"])
    nm, na = detect.detect_panels(now, mask, res, s["min_component_m2"])
    past_kwp = pa / s["m2_per_kwp"]
    now_kwp = na / s["m2_per_kwp"]
    if past_kwp < s["min_kwp"]:
        return None
    if now_kwp < s["unchanged_ratio"] * past_kwp:
        return None
    return {
        "building": b,
        "past_kwp": round(past_kwp, 1),
        "now_kwp": round(now_kwp, 1),
        "past_img": detect.overlay(past, pm),
        "now_img": detect.overlay(now, nm),
    }


def _b64(img, max_w=420):
    img = img.copy()
    img.thumbnail((max_w, max_w))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


def write_outputs(hits, out_dir, year):
    os.makedirs(out_dir, exist_ok=True)
    rows, feats, cards = [], [], []
    for h in hits:
        b, o = h["building"], h["owner"]
        lon, lat = b["centroid"]
        link = f"https://www.google.com/maps/@{lat},{lon},19z/data=!3m1!1e1"
        rows.append({
            "osm_id": b["id"], "lat": round(lat, 6), "lon": round(lon, 6),
            "roof_m2": round(b["area_m2"]), f"kwp_stimati_{year}": h["past_kwp"],
            "kwp_stimati_oggi": h["now_kwp"], "nome_osm": o["osm_name"],
            "google_places": o["google_places"], "indirizzo": o["address"],
            "google_maps": link,
        })
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point", "coordinates": [lon, lat]},
                      "properties": rows[-1]})
        cards.append(
            f"<div class=c><b>{o['google_places'] or o['osm_name'] or 'n.d.'}</b><br>"
            f"{o['address']}<br>{lat:.6f}, {lon:.6f} - ~{h['past_kwp']} kWp "
            f"({year}) / ~{h['now_kwp']} kWp (oggi) - <a href='{link}'>Maps</a><br>"
            f"<img src='data:image/jpeg;base64,{_b64(h['past_img'])}'> "
            f"<img src='data:image/jpeg;base64,{_b64(h['now_img'])}'></div>")

    if rows:
        with open(os.path.join(out_dir, "risultati.csv"), "w", newline="",
                  encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    with open(os.path.join(out_dir, "risultati.geojson"), "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f)
    with open(os.path.join(out_dir, "report.html"), "w", encoding="utf-8") as f:
        f.write("<meta charset=utf-8><style>body{font-family:sans-serif}"
                ".c{border:1px solid #ccc;margin:8px;padding:8px;max-width:900px}"
                "</style><h2>Candidati (da verificare a vista)</h2>"
                "<p>Sinistra: ortofoto passata, destra: attuale. In rosso i pixel "
                "classificati come pannelli.</p>" + "".join(cards))
    return rows


def run(area_poly, cfg, out_dir="out", progress=None, workers=4):
    s = cfg["search"]
    blds = geo.buildings(area_poly, s["min_roof_area_m2"],
                         progress=(lambda i, n: progress("Edifici OSM", i, n))
                         if progress else None)
    hits, done = [], 0
    with ThreadPoolExecutor(workers) as ex:
        for r in ex.map(lambda b: analyze_building(b, cfg), blds):
            done += 1
            if r:
                hits.append(r)
            if progress:
                progress("Confronto ortofoto", done, len(blds))
    for h in hits:
        h["owner"] = owners.find_owner(h["building"], cfg["owners"])
    rows = write_outputs(hits, out_dir, cfg["past_imagery"]["year"])
    return rows, len(blds)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city")
    ap.add_argument("--radius-km", type=float, default=30)
    ap.add_argument("--geojson", help="file GeoJSON con un poligono")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    cfg = load_config(a.config)
    if a.geojson:
        with open(a.geojson, encoding="utf-8") as f:
            gj = json.load(f)
        g = gj["features"][0]["geometry"] if gj.get("type") == "FeatureCollection" \
            else gj.get("geometry", gj)
        area = shape(g)
    elif a.city:
        lat, lon = geo.geocode(a.city)
        area = geo.circle_polygon(lat, lon, a.radius_km)
    else:
        ap.error("serve --city oppure --geojson")
    rows, n = run(area, cfg, a.out,
                  progress=lambda t, i, tot: print(f"{t}: {i}/{tot}", end="\r"))
    print(f"\nEdifici analizzati: {n} - candidati trovati: {len(rows)} -> {a.out}/")


if __name__ == "__main__":
    main()
