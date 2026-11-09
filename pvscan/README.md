# pvscan

Trova tetti con impianti fotovoltaici installati nel periodo 2010-2013 (>= ~70 kWp,
circa 200 moduli) che sono **ancora presenti oggi**, e produce una lista di
coordinate con attivita'/indirizzo associati.

## Come funziona

1. **Area**: citta' + raggio in km (linea d'aria) oppure poligono disegnato su mappa
   (app Streamlit) o file GeoJSON (CLI).
2. **Tetti candidati**: edifici OpenStreetMap con superficie >= `min_roof_area_m2`
   (700 m2 di default: sotto non ci stanno ~70 kWp).
3. **Confronto**: ritaglio ortofoto 2012 (Geoportale Nazionale, WMS) vs ortofoto
   attuale (Esri World Imagery), allineati pixel per pixel.
4. **Rilevamento pannelli** + stima kWp (`m2_per_kwp`). Si tiene il tetto se nel 2012
   c'erano >= 70 kWp stimati e oggi ce n'e' almeno l'80%.
5. **Chi e'**: nome/indirizzo da tag OSM, Google Places (opzionale) o Nominatim.
6. Output in `out/`: `risultati.csv`, `risultati.geojson`, `report.html`
   (affiancamento prima/dopo con i pannelli evidenziati).

## Installazione

```bash
pip install -r requirements.txt
export GOOGLE_MAPS_API_KEY=...   # opzionale, per i nomi delle attivita'
```

## Uso

```bash
streamlit run app.py
python -m pvscan.pipeline --city Treviso --radius-km 30 --out out
python -m pvscan.pipeline --geojson area.geojson --out out
```

## Limiti importanti

- **Il rilevatore e' euristico** (colore scuro/bluastro + dimensione dei blob):
  genera falsi positivi (tetti scuri, ombre, lucernari). Il `report.html` serve a
  verificare a occhio. Per risultati affidabili sostituisci `detect.detect_panels`
  con un modello di segmentazione addestrato su pannelli FV aerei.
- **Copertura 2012**: l'ortofoto 2012 mostra gli impianti installati fino a quella data
  (2010-2012); quelli del 2013 richiedono un'ortofoto successiva (aggiungi un'altra
  sorgente in `config.yaml`). Verifica nome layer/anno con GetCapabilities.
- **Proprietario**: il dato catastale non e' disponibile da fonti aperte (visure con
  accesso autorizzato e dati personali GDPR). Il tool restituisce l'attivita'
  presente all'indirizzo (OSM/Google Places), utile per contatti commerciali B2B.
  Usa i dati nel rispetto del GDPR e dei termini d'uso delle fonti (Esri, Google, OSM).
- **Incrocio con GSE**: Atlaimpianti (atla.gse.it) elenca gli impianti FV per comune e
  potenza: utile per validare i candidati.
- Esri World Imagery: i termini limitano il download massivo; per uso intensivo usa
  ortofoto regionali/AGEA recenti.
- Scala: 30 km di raggio = migliaia di edifici >700 m2 e 2 richieste immagine
  ciascuno; la cache (`.cache/`) evita ripetizioni.
