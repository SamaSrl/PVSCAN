import folium
import pandas as pd
import streamlit as st
from shapely.geometry import shape
from streamlit_folium import st_folium
from folium.plugins import Draw
from pvscan import geo, pipeline

st.set_page_config(page_title="pvscan", layout="wide")
st.title("pvscan - fotovoltaico storico ancora presente")

cfg = pipeline.load_config()
mode = st.radio("Area", ["Citta' + raggio", "Disegna su mappa"], horizontal=True)
area = None

if mode == "Citta' + raggio":
    c1, c2 = st.columns([3, 1])
    city = c1.text_input("Citta'", "Treviso")
    km = c2.number_input("Raggio (km, linea d'aria)", 1, 60, 30)
    if city:
        try:
            lat, lon = geo.geocode(city)
            area = geo.circle_polygon(lat, lon, km)
            m = folium.Map([lat, lon], zoom_start=9)
            folium.GeoJson(area.__geo_interface__).add_to(m)
            st_folium(m, height=350, width=900)
        except Exception as e:
            st.error(str(e))
else:
    m = folium.Map([45.5, 12.2], zoom_start=9)
    Draw(export=False, draw_options={"polygon": True, "rectangle": True,
                                      "circle": False, "marker": False,
                                      "polyline": False, "circlemarker": False}).add_to(m)
    out = st_folium(m, height=450, width=900)
    d = (out or {}).get("last_active_drawing")
    if d:
        area = shape(d["geometry"])

if area is not None and st.button("Avvia analisi"):
    bar = st.progress(0.0, text="Avvio...")

    def progress(step, i, n):
        bar.progress(i / max(n, 1), text=f"{step}: {i}/{n}")

    rows, n = pipeline.run(area, cfg, "out", progress=progress)
    st.success(f"{n} edifici analizzati, {len(rows)} candidati")
    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df)
        st.download_button("Scarica CSV", df.to_csv(index=False), "risultati.csv")
        with open("out/report.html", encoding="utf-8") as f:
            st.components.v1.html(f.read(), height=700, scrolling=True)
