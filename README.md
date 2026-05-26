# DTM LIDAR Flood Risk Assessment

Pipeline configurabile per la valutazione del rischio idrogeologico a partire da DEM (SRTM / LiDAR / LiDAR via WMS), copertura del suolo, pioggia (CHIRPS o raster locale) e dati OSM (fiumi + edifici).

Il progetto è pensato come prototipo avanzato ma coerente: tutta la logica è nei moduli `core/`, mentre gli script principali orchestrano scenari diversi (locale vs GEE, SRTM vs LiDAR).

---

## 1. Struttura del progetto

- `flood_risk_prototype.py`  
  **Pipeline di screening rapido multi-sorgente.**
  - Supporta DEM da SRTM (GEE) o LiDAR (WMS/Locale).
  - Calcola indici idrologici (Slope, TWI, SPI) e rischio base.
  - Usa parametri costanti per pioggia e deflusso per massima velocità.
  - Include analisi base esposizione OSM (GeoJSON).

- `gee_lidar_prototype.py`  
  Pipeline “GEE‑centrica” che usa un DTM LiDAR caricato come asset GEE e calcola rischio direttamente in GEE (modello più semplice, pensato per sperimentare con asset LiDAR in cloud).

- `streamlit_app.py`
  Interfaccia Web interattiva per caricare DTM, eseguire l'analisi e visualizzare i risultati su mappa.

- `core/` – Moduli riutilizzabili:
  - `data_ingest.py` – Ingestione dati (DEM da GEE, landcover, CHIRPS, upload asset GEE).
  - `dem_processing.py` – Condizionamento DEM e fusione LiDAR + DEM medium.
  - `hydro_indices.py` – Slope, flow accumulation (pysheds / Whitebox / placeholder), TWI, SPI.
  - `landcover.py` – Mappatura copertura del suolo → coefficiente di deflusso.
  - `lidar_sources.py` – Download DTM LiDAR via WMS (es. Geoportale Nazionale Campania).
  - `osm_exposure.py` – Download fiumi/edifici OSM, burn‑in DEM, edifici ad alto rischio, mappa Folium.
  - `postprocessing.py` – Post‑processing SPI → `Risk_Map_Optimized.tif` + overlay PNG.
  - `risk_model.py` – Modello di rischio combinato, parametri da `config.yaml`.
  - `reporting.py` – Report Markdown con statistiche sintetiche.
  - `logging_config.py` / `crs_validation.py` / `utils.py` – Logging, validazione CRS e utility I/O centralizzate.

- `config.yaml`  
  Configurazione centrale (dataset GEE, backend flow accumulation, pesi rischio, WMS LiDAR, ecc.).

- `scripts/`
  - `srtm_full_pipeline.py`: Pipeline completa SRTM (ex `SRTM/flood_risk_prototype.py`).
  - `reset_repository.py`: Script di pulizia output.

- `docs/`
  - Documentazione tecnica e guide.

- `output/`  
  Cartelle di output per i diversi scenari (es. `output/avella_srtm_full`, `output/tufino_15_lidar_campania`, ecc.). Ogni cartella contiene:
  - `dem_raw.tif`, `dem_conditioned.tif`
  - `slope.tif`, `flow_accumulation.tif`, `twi.tif`, `spi.tif`
  - `landcover.tif`, `runoff_coeff.tif`
  - `rain_chirps.tif` (se usata)
  - `risk_index.tif`, `risk_class.tif`
  - `Risk_Map_Optimized.tif`, `Risk_Map_Overlay.png`
  - `buildings_high_risk.geojson`, `buildings_high_risk.csv`, `buildings_risk_map.html` (se OSM abilitato)
  - `report.md`

---

## 2. Configurazione (`config.yaml`)

Parametri principali (già impostati per Campania):

- **Default di scenario**
  - `default_resolution_m` – Risoluzione DEM target (es. 30 m per SRTM).
  - `default_buffer_km` – Buffer intorno a coordinate/indirizzo (km).
  - `default_rain_intensity_mm` – Intensità di pioggia uniforme (se non si usa CHIRPS / raster locale).

- **Dataset GEE**
  - `gee_dem_dataset_id` – Id DEM (es. `USGS/SRTMGL1_003`).
  - `gee_landcover_collection` – ESA WorldCover (es. `ESA/WorldCover/v100`).
  - `gee_chirps_collection` – CHIRPS daily.
  - `gee_rain_start_date`, `gee_rain_end_date` – periodo da usare per aggregazione CHIRPS.

- **LiDAR via WMS (DTM Campania)**
  - `lidar_wms_url` – URL servizio WMS.
  - `lidar_wms_layer` – Nome layer DTM (es. `EL.LIDAR.CAMPANIA.1x1.DTM`).
  - `lidar_wms_resolution_m` – Risoluzione richiesta al WMS (m).

- **Flow accumulation**
  - `flow_accumulation_backend` – `auto` | `pysheds` | `whitebox` | `placeholder`.
    - In pratica: `whitebox` è quello che stai usando ora.

- **Modello di rischio**
  - `risk_weights` – Pesi per TWI, SPI, runoff, slope nel rischio combinato.
  - `risk_thresholds` – Soglie per classi di rischio (basso/medio/alto).

- **Post‑processing SPI**
  - `spi_postprocessing.percentile` – Percentile SPI per definire aree rosse (es. 95).
  - `spi_postprocessing.buffer_meters` – Buffer fisico attorno alle celle SPI alte.

- **Land cover → runoff**
  - `landcover_runoff_mapping` – Mappatura classi ESA → coefficiente di deflusso (es. classe 50=urbano → 0.7, default=0.3).

---

## 3. Dipendenze principali

- Core raster: `numpy`, `rasterio`
- Idrologia: `scipy` (per median filter / dilation), `pysheds` (opzionale), `whitebox-tools` (eseguibile + pacchetto Python)
- GEE: `earthengine-api (ee)`, `geemap`
- Vettoriale / OSM: `geopandas`, `shapely`, `osmnx`
- Mappe HTML: `folium`, `geemap.foliumap`
- Logging: `loguru` (opzionale, altrimenti logging standard)
- LiDAR locale (opzionale): `pdal` oppure `laspy[lazrs]`

Per una installazione minimale focalizzata su SRTM + Whitebox + OSM:

```bash
pip install numpy rasterio scipy loguru geopandas shapely osmnx folium whitebox rasterio
pip install earthengine-api geemap
# opzionale per pysheds:
pip install pysheds
```

Assicurati inoltre che `whitebox_tools.exe` sia disponibile nella root del progetto (come nel repository attuale).

### 3.1 Docker (Consigliato)

Il progetto include un `Dockerfile` e `docker-compose.yml` per un setup immediato.

1.  **Build e Avvio**:
    ```bash
    docker-compose up --build
    ```
2.  **Accesso**:
    Apri il browser su `http://localhost:8501` per usare l'app Streamlit.
    
    I dati di output verranno salvati nella cartella del progetto grazie al volume montato.

---

## 4. Script principali e comandi di esecuzione

### 4.1 Pipeline principale: `flood_risk_prototype.py`

Questo script è ottimizzato per lo screening rapido su diverse fonti dati (SRTM, LiDAR WMS). Usa parametri semplificati (pioggia/deflusso costanti) per fornire un risultato immediato.

**Esempio A – Analisi completa SRTM + CHIRPS + OSM (Avella)**

```bash
python flood_risk_prototype.py \
  --coords "14.593131, 40.968531" \
  --buffer-km 5 \
  --out-dir output/avella_srtm_full \
  --use-gee \
  --rain-intensity 100 \
  --enable-osm-exposure
```

**Esempio B – LiDAR via WMS Campania + GEE (DEM LiDAR + landcover + CHIRPS + OSM)**

Usa WMS come sorgente DEM (parametri di default presi da `config.yaml` se non sovrascritti):

```bash
python flood_risk_prototype.py \
  --use-gee \
  --coords "14.593131, 40.968531" \
  --buffer-km 5 \
  --resolution 1.0 \
  --lidar-wms-url "http://wms.pcn.minambiente.it/ogc?map=/ms_ogc/WMS_v1.3/servizi-LiDAR/LIDAR_CAMPANIA.map" \
  --lidar-wms-layer "EL.LIDAR.CAMPANIA.1x1.DTM" \
  --out-dir output/avella_lidar_wms_full \
  --rain-intensity 100 \
  --enable-osm-exposure
```

**Esempio C – DEM locale LiDAR (`.las/.laz`) + pioggia uniforme (senza GEE)**

```bash
python flood_risk_prototype.py \
  --lidar-path "path/al/tuo_file.laz" \
  --coords "14.593131, 40.968531" \
  --buffer-km 5 \
  --resolution 1.0 \
  --out-dir output/avella_lidar_local \
  --rain-intensity 100 \
  --enable-osm-exposure
```

In questo caso il DEM è generato da PDAL se disponibile, altrimenti dal fallback `laspy`.

**Esempio D – Uso di un raster di pioggia locale al posto di CHIRPS**

```bash
python flood_risk_prototype.py \
  --use-gee \
  --coords "14.593131, 40.968531" \
  --buffer-km 5 \
  --out-dir output/avella_local_rain \
  --local-rain-raster "path/pioggia_locale.tif" \
  --rain-intensity 100 \
  --enable-osm-exposure
```

Se `--local-rain-raster` esiste, viene usato al posto di CHIRPS (con validazione CRS/copri‑copertura).

### 4.2 Pipeline SRTM di screening: `SRTM/flood_risk_prototype.py`

Pipeline completa per analisi SRTM a 30m. Include il download di Land Cover e Pioggia reale (CHIRPS), post-processing avanzato e generazione report.

Esempio:

```bash
python SRTM/flood_risk_prototype.py \
  --coords "14.593131, 40.968531" \
  --buffer-km 5 \
  --out-dir output/avella_srtm_screening \
  --enable-osm-exposure
```

### 4.3 Pipeline GEE‑centrica LiDAR: `gee_lidar_prototype.py`

Usa un DTM LiDAR caricato come asset GEE (`--asset-id`) e calcola in GEE: pendenza, TWI, SPI, indice di rischio semplice `(Pioggia * Runoff) / (Pendenza + 1)`, poi esporta i raster e una mappa HTML.

Esempio (asset già caricato):

```bash
python gee_lidar_prototype.py \
  --asset-id "users/tuo_user/dtm_avella_lidar" \
  --coords "14.593131, 40.968531" \
  --buffer-km 5 \
  --chirps-start "2020-01-01" \
  --chirps-end "2023-01-01" \
  --out-dir output/avella_gee_lidar \
  --scale 5
```

Se vuoi caricare un nuovo GeoTIFF LiDAR come asset GEE:

```bash
python gee_lidar_prototype.py \
  --lidar-tif "path/dtm_lidar.tif" \
  --asset-id "users/tuo_user/dtm_avella_lidar" \
  --upload-asset \
  --coords "14.593131, 40.968531" \
  --buffer-km 5 \
  --out-dir output/avella_gee_lidar \
  --scale 5
```

---

## 5. Note su OSM e Folium

- L’opzione `--enable-osm-exposure` attiva:
  - download fiumi OSM (per burn‑in DEM);
  - download edifici OSM, selezione di quelli che intersecano `Risk_Map_Optimized.tif`;
  - export GeoJSON (`buildings_high_risk.geojson`), CSV (`buildings_high_risk.csv`) e mappa HTML (`buildings_risk_map.html`).

- La visualizzazione di base di un WMS LiDAR su mappa Folium può essere fatta anche al di fuori della pipeline, ad esempio:

```python
import folium

m = folium.Map(location=[40.968531, 14.593131], zoom_start=12)
folium.WmsTileLayer(
    url="http://wms.pcn.minambiente.it/ogc?map=/ms_ogc/WMS_v1.3/servizi-LiDAR/LIDAR_CAMPANIA.map",
    layers="EL.LIDAR.CAMPANIA.1x1.DTM",
    fmt="image/png",
    transparent=False,
    version="1.3.0",
    name="DTM LiDAR Campania",
).add_to(m)
folium.LayerControl().add_to(m)
m.save("avella_simple_map.html")
```

---

## 6. Allineamento e buone pratiche

- Usa `flood_risk_prototype.py` come entry‑point principale per nuovi scenari: è quello più aggiornato e configurato.
- Tieni `config.yaml` come unica fonte di verità per:
  - dataset GEE,
  - backend flow accumulation,
  - pesi/soglie del modello di rischio,
  - parametri WMS LiDAR,
  - mapping landcover → runoff.
- Considera `SRTM/flood_risk_prototype.py` e `gee_lidar_prototype.py` come varianti specializzate:
  - SRTM screening (veloce, bassa risoluzione),
  - GEE LiDAR (tutto in cloud).

Per nuove funzionalità (es. altri WMS o altri DEM medium) è consigliabile:
1. Aggiungere i parametri in `config.yaml`,
2. Integrare la logica nei moduli `core/`,
3. Richiamare i moduli da `flood_risk_prototype.py` mantenendo la pipeline coerente.
