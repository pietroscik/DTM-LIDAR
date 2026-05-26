import streamlit as st

st.set_page_config(page_title="Hydro-GIS: Flood Risk", layout="wide", page_icon="🌊", initial_sidebar_state="expanded")

import tempfile
import os
import sys
from pathlib import Path
import rasterio
from rasterio.warp import transform_bounds
import numpy as np
import folium
from folium import plugins
from streamlit_folium import st_folium
import matplotlib.pyplot as plt # Fallback per grafici statici
from datetime import datetime
import geopandas as gpd
try:
    import plotly.graph_objects as go
except ImportError:
    go = None

# Aggiungi la root del progetto al path per garantire l'importazione dei moduli core
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

# Import moduli core (assume che la cartella core/ sia nella stessa directory)
try:
    from core import dem_processing, hydro_indices, risk_model, osm_exposure, postprocessing, utils, data_ingest, lidar_sources, landcover
except ImportError as e:
    st.error(f"Errore nell'importazione dei moduli 'core'. Dettagli: {e}")
    st.stop()

# Carica configurazione globale
config = utils.load_config()
viz_config = config.get("visualization", {})
colormaps = viz_config.get("colormaps", {"dem": "terrain", "risk": "RdYlGn_r", "risk_optimized": "Reds"})
opacities = viz_config.get("opacity", {"dem": 0.6, "risk": 0.7, "risk_optimized": 0.5})

# --- Funzioni di Utilità ---

def add_raster_to_map(map_obj, raster_path, layer_name, colormap="Spectral_r", opacity=0.7):
    """Aggiunge un layer raster a una mappa Folium."""
    try:
        with rasterio.open(raster_path) as src:
            # Fix 3.7: Gestione memoria e Performance (Downsampling)
            # Se il raster è > 1 Megapixel, riduciamo la risoluzione per la visualizzazione web
            MAX_PIXELS = 1000 * 1000
            scale_factor = 1
            if src.width * src.height > MAX_PIXELS:
                scale_factor = (src.width * src.height / MAX_PIXELS) ** 0.5
            
            if scale_factor > 1:
                new_h = int(src.height / scale_factor)
                new_w = int(src.width / scale_factor)
                data = src.read(1, out_shape=(new_h, new_w), resampling=rasterio.enums.Resampling.bilinear)
            else:
                data = src.read(1)

            data = np.where(data == src.nodata, np.nan, data)
            
            # Calcola bounds per folium
            bounds = [[src.bounds.bottom, src.bounds.left], [src.bounds.top, src.bounds.right]]
            
            # Normalizzazione con percentili (2-98) per contrasto migliore
            valid_data = data[~np.isnan(data)]
            if valid_data.size > 0:
                min_val = np.nanpercentile(valid_data, 2)
                max_val = np.nanpercentile(valid_data, 98)
                
                # Clip data per evitare outlier
                data_clipped = np.clip(data, min_val, max_val)
                
                if max_val > min_val:
                    # Usa matplotlib per generare l'immagine colorata
                    cm = plt.get_cmap(colormap)
                    norm_data = (data_clipped - min_val) / (max_val - min_val)
                    colored_data = cm(norm_data)
                    
                    # Folium vuole (H, W, 4) float o uint8. Matplotlib ritorna float 0-1 RGBA.
                    # Gestione trasparenza: dove era NaN, alpha=0
                    colored_data[..., 3] = np.where(np.isnan(data), 0, opacity)
                    
                    image_overlay = folium.raster_layers.ImageOverlay(
                        image=colored_data,
                        bounds=bounds,
                        name=layer_name,
                        opacity=1.0, # Gestita nel canale alpha sopra
                        interactive=True,
                        cross_origin=False,
                        zindex=1
                    )
                    image_overlay.add_to(map_obj)
                    
                    # Zoom sui bounds
                    map_obj.fit_bounds(bounds)
    except Exception as e:
        st.warning(f"Impossibile visualizzare {layer_name} sulla mappa: {e}")

def plot_3d_terrain(dem_path, risk_path, vert_exag=1.5, colorscale='RdYlGn_r'):
    """Genera una visualizzazione 3D del terreno colorata in base al rischio."""
    if go is None:
        st.warning("Libreria 'plotly' non installata. Visualizzazione 3D disabilitata.")
        return None

    try:
        with rasterio.open(dem_path) as src:
            dem = src.read(1)
            # Sostituisci nodata con NaN per plotly
            nodata = src.nodata if src.nodata is not None else -9999
            dem = np.where(dem == nodata, np.nan, dem)
            # Maschera valori assurdi (es. -32768)
            dem = np.where(dem < -1000, np.nan, dem)
            
        with rasterio.open(risk_path) as src:
            risk = src.read(1)
            risk = np.where(risk == src.nodata, np.nan, risk)

        # --- FIX 1: Downsampling Dinamico per Mesh Uniforme ---
        # Calcola fattore per avere circa 150k punti (ottimo compromesso qualità/performance)
        total_pixels = dem.shape[0] * dem.shape[1]
        target_pixels = 150000 
        
        if total_pixels > target_pixels:
            downsample_factor = int(np.sqrt(total_pixels / target_pixels))
            downsample_factor = max(1, downsample_factor)
        else:
            downsample_factor = 1
            
        # Fix Specularità: Flip UD per allineare coordinate immagine (Top-Left) con Plotly (Bottom-Left)
        z_data = np.flipud(dem[::downsample_factor, ::downsample_factor])
        surface_color = np.flipud(risk[::downsample_factor, ::downsample_factor])

        # --- FIX 2: Conversione Unità (Metri -> Gradi approssimati) ---
        # Risolve il problema dei "picchi ad ago" causati dal mix LatLon/Metri.
        # 1 grado lat ~= 111 km.
        scale_factor = 1 / 111111.0
        z_data_deg = z_data * scale_factor * vert_exag

        fig = go.Figure(data=[go.Surface(z=z_data_deg, surfacecolor=surface_color, colorscale=colorscale, cmin=0, cmax=1)])
        
        fig.update_layout(
            title='Digital Twin 3D (Elevazione + Rischio)',
            scene=dict(
                aspectmode='data', # Ora che Z è in gradi, 'data' mantiene le proporzioni corrette
                xaxis_title="Lon",
                yaxis_title="Lat",
                zaxis_title="Elevazione (Scaled)",
                zaxis=dict(showticklabels=False) # Nascondi i tick perché sono in gradi
            ),
            autosize=True, margin=dict(l=0, r=0, b=0, t=30)
        )
        return fig
    except Exception as e:
        st.error(f"Errore generazione 3D: {e}")
        return None

def generate_technical_report(stats, params):
    """Genera il contenuto del report Markdown richiesto dalla Mission."""
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    return f"""# 🌊 Report Tecnico: Valutazione Rischio Idrogeologico
**Data Elaborazione:** {now}
**Modulo:** Hydro-GIS Digital Twin

## 1. Parametri di Simulazione
- **Intensità Pioggia:** {params['rain']} mm/h
- **Coefficiente Deflusso (Medio):** {params['runoff']}
- **Sorgente DTM:** Upload Utente (LIDAR/SRTM)

## 2. Statistiche Analisi
- **Rischio Medio (Indice 0-1):** {stats['mean']:.4f}
- **Picco di Rischio:** {stats['max']:.4f}
- **Copertura Analizzata:** {stats['pixels']} celle
- **Edifici Analizzati:** {stats.get('buildings_count', 'N/A')}
- **Edifici a Rischio Alto:** {stats.get('buildings_risk_count', 'N/A')}

## 3. Metodologia
L'analisi è stata condotta mediante pipeline idrologica automatizzata:
1. **Pre-processing:** Condizionamento DTM (Fill Sinks).
2. **Idrologia:** Calcolo Flow Accumulation, TWI (Topographic Wetness Index) e SPI (Stream Power Index).
3. **Modellazione:** Combinazione pesata di pericolosità idraulica e vulnerabilità territoriale.

---
*Generato automaticamente da Hydro-GIS Agent*
"""

# --- Caching della Pipeline ---
# NOTA: Rimosso @st.cache_data perché tempfile.mkdtemp() crea directory volatili.
# Se la cache viene colpita ma la cartella tmp è stata pulita dal sistema, l'app crasha.
# Per riabilitare la cache, bisognerebbe usare una directory di cache persistente.
def create_constant_raster_safe(reference_path: Path, out_path: Path, value: float):
    """Wrapper per creare raster costanti usando utils.write_raster."""
    data, profile, _ = utils.read_raster(reference_path)
    # Crea array costante mantenendo la shape
    arr = np.full(data.shape, value, dtype="float32")
    utils.write_raster(out_path, arr, profile)

def run_risk_pipeline(dem_bytes, rain_intensity, runoff_coeff_val, runoff_bytes=None, rain_bytes=None, landcover_bytes=None, analyze_osm=False):
    """
    Esegue la pipeline idrologica. Cachata per evitare ricalcoli se i parametri non cambiano.
    Ritorna un dizionario con i percorsi dei file generati in una temp dir persistente per la sessione.
    """
    # Creiamo una directory temporanea unica per questa combinazione di parametri
    # Nota: In produzione, gestire la pulizia di queste cartelle è importante.
    # Usiamo una cartella locale 'temp' mappata nel volume Docker per vedere i file su host
    local_tmp_base = Path("temp")
    local_tmp_base.mkdir(exist_ok=True)
    tmp_dir = tempfile.mkdtemp(dir=local_tmp_base)
    tmp_path = Path(tmp_dir)
    
    paths = {
        "dem_raw": tmp_path / "dem_raw.tif",
        "dem_cond": tmp_path / "dem_cond.tif",
        "slope": tmp_path / "slope.tif",
        "flow_acc": tmp_path / "flow_acc.tif",
        "twi": tmp_path / "twi.tif",
        "spi": tmp_path / "spi.tif",
        "landcover": tmp_path / "landcover.tif",
        "runoff": tmp_path / "runoff.tif",
        "rain": tmp_path / "rain.tif",
        "risk_index": tmp_path / "risk_index.tif",
        "risk_class": tmp_path / "risk_class.tif",
        "buildings_geojson": tmp_path / "buildings_risk.geojson",
        "risk_optimized": tmp_path / "Risk_Map_Optimized.tif"
    }

    # Scrittura input
    with open(paths["dem_raw"], "wb") as f:
        f.write(dem_bytes)

    # 1. Pipeline Core
    dem_processing.condition_dem(paths["dem_raw"], paths["dem_cond"])
    hydro_indices.compute_slope(paths["dem_cond"], paths["slope"])
    hydro_indices.compute_flow_accumulation(paths["dem_cond"], paths["flow_acc"])
    hydro_indices.compute_twi(paths["dem_cond"], paths["flow_acc"], paths["twi"])
    hydro_indices.compute_spi(paths["flow_acc"], paths["slope"], paths["spi"])

    # 2. Input Sintetici
    # Gestione Runoff: Se fornito file usa quello, altrimenti costante
    if runoff_bytes:
        with open(paths["runoff"], "wb") as f: f.write(runoff_bytes)
    elif landcover_bytes:
        with open(paths["landcover"], "wb") as f: f.write(landcover_bytes)
        # Calcola runoff da landcover usando il mapping di default (da config.yaml)
        landcover.map_landcover_to_runoff(
            landcover_path=paths["landcover"],
            mapping=None, 
            out_path=paths["runoff"],
            reference_raster=paths["dem_cond"]
        )
    else:
        create_constant_raster_safe(paths["dem_cond"], paths["runoff"], runoff_coeff_val)

    # Gestione Pioggia: Se fornito file usa quello, altrimenti costante
    if rain_bytes:
        with open(paths["rain"], "wb") as f: f.write(rain_bytes)
    else:
        create_constant_raster_safe(paths["dem_cond"], paths["rain"], rain_intensity)

    # 3. Calcolo Rischio
    risk_model.compute_combined_risk_index(
        runoff_coeff_path=paths["runoff"], slope_path=paths["slope"],
        twi_path=paths["twi"], spi_path=paths["spi"],
        out_index_path=paths["risk_index"], out_class_path=paths["risk_class"],
        rain_raster_path=paths["rain"], rain_intensity=rain_intensity
    )

    # 4. Post-processing (Mappa Ottimizzata)
    postprocessing.create_optimized_risk_from_spi(paths["spi"], paths["risk_optimized"])

    # 5. Analisi Esposizione OSM (Opzionale)
    stats = {'warnings': []}
    if analyze_osm:
        try:
            # Ottieni bounds dal DTM processato
            with rasterio.open(paths["dem_cond"]) as src:
                bounds = src.bounds
                crs = src.crs
            
            # Trasforma bounds in Lat/Lon (EPSG:4326) per OSM
            w, s, e, n = transform_bounds(crs, "EPSG:4326", *bounds)
            
            # Scarica edifici
            buildings = osm_exposure.download_osm_buildings_from_bbox(n, s, e, w)
            stats['buildings_count'] = len(buildings)
            
            if not buildings.empty:
                # Calcola rischio per edificio
                osm_exposure.buildings_risk_to_geojson(
                    buildings, paths["risk_index"], paths["buildings_geojson"], top_percent=20.0
                )
                if paths["buildings_geojson"].exists():
                    gdf_risk = gpd.read_file(paths["buildings_geojson"])
                    stats['buildings_risk_count'] = len(gdf_risk)
        except Exception as ex:
            error_msg = f"Errore durante l'analisi OSM: {ex}"
            stats['warnings'].append(error_msg)
            print(error_msg)

    # 4. Calcolo Statistiche per Report
    with rasterio.open(paths["risk_index"]) as src:
        data = src.read(1, masked=True)
        valid_data = data[data != src.nodata]
        stats['mean'] = float(valid_data.mean()) if valid_data.size > 0 else 0.0
        stats['max'] = float(valid_data.max()) if valid_data.size > 0 else 0.0
        stats['pixels'] = int(valid_data.size)
    
    return paths, stats

def sample_raster_values(coords, raster_paths):
    """Campiona i valori dai raster nel punto specificato (lat, lon)."""
    results = {}
    try:
        # Converti lat/lon in coordinate del raster (assumiamo CRS coerenti o riproiettiamo se necessario)
        # Per semplicità qui usiamo rasterio.sample che gestisce le coordinate se passate correttamente
        # Nota: rasterio.sample vuole [(x, y)]
        xy = [(coords['lng'], coords['lat'])]
        
        for name, path in raster_paths.items():
            if path.exists():
                with rasterio.open(path) as src:
                    # Verifica rapida se il punto è dentro i bounds
                    if (src.bounds.left <= xy[0][0] <= src.bounds.right and 
                        src.bounds.bottom <= xy[0][1] <= src.bounds.top):
                        # Campiona
                        val_gen = src.sample(xy)
                        val = next(val_gen)[0]
                        # Gestione nodata
                        if val == src.nodata:
                            results[name] = "N/A"
                        else:
                            results[name] = float(val)
    except Exception as e:
        print(f"Errore sampling: {e}")
    return results

def add_legend(map_obj, title="Legenda Rischio"):
    """Aggiunge una legenda HTML alla mappa."""
    legend_html = f"""
     <div style="position: fixed; 
     bottom: 50px; left: 50px; width: 150px; height: 130px; 
     border:2px solid grey; z-index:9999; font-size:14px;
     background-color:white; opacity: 0.8;
     padding: 10px;">
     <b>{title}</b><br>
     <i style="background: #d73027; width: 10px; height: 10px; display: inline-block;"></i> Alto (0.8-1.0)<br>
     <i style="background: #fc8d59; width: 10px; height: 10px; display: inline-block;"></i> Medio-Alto (0.6-0.8)<br>
     <i style="background: #fee08b; width: 10px; height: 10px; display: inline-block;"></i> Medio (0.4-0.6)<br>
     <i style="background: #d9ef8b; width: 10px; height: 10px; display: inline-block;"></i> Basso (0.2-0.4)<br>
     <i style="background: #1a9850; width: 10px; height: 10px; display: inline-block;"></i> Nullo (0-0.2)<br>
     </div>
     """
    map_obj.get_root().html.add_child(folium.Element(legend_html))

def get_download_link(file_path, file_name, label):
    with open(file_path, "rb") as f:
        data = f.read()
    return st.download_button(label=label, data=data, file_name=file_name, mime="image/tiff")

# --- UI Layout ---
st.title("🌊 Hydro-GIS: Digital Twin Territoriale")
st.markdown("**Digital Twin Territoriale - Modulo di Validazione Rapida**")

# Inizializzazione stato coordinate (Default: Avella)
if 'map_coords' not in st.session_state:
    st.session_state.map_coords = {'lat': 40.9685, 'lon': 14.5931}

if 'results' not in st.session_state:
    st.session_state.results = None

with st.sidebar:
    st.header("1. Input Dati")
    input_mode = st.radio("Sorgente Dati", ["Seleziona su Mappa", "Carica File Locale"])
    
    dem_source_bytes = None
    
    if input_mode == "Carica File Locale":
        uploaded_file = st.file_uploader("Carica DTM (GeoTIFF)", type=["tif", "tiff"])
        if uploaded_file:
            dem_source_bytes = uploaded_file.getvalue()
    else:
        st.info("Clicca sulla mappa o inserisci le coordinate.")
        # Input numerici collegati allo stato della sessione
        # Rimosso key per evitare conflitti con aggiornamenti da mappa (StreamlitAPIException)
        lat_in = st.number_input("Latitudine", value=st.session_state.map_coords['lat'], format="%.5f")
        lon_in = st.number_input("Longitudine", value=st.session_state.map_coords['lon'], format="%.5f")
        
        # Aggiorna lo stato se l'input manuale cambia
        if lat_in != st.session_state.map_coords['lat']:
            st.session_state.map_coords['lat'] = lat_in
        if lon_in != st.session_state.map_coords['lon']:
            st.session_state.map_coords['lon'] = lon_in
        
        buffer_km = st.slider("Raggio Analisi (km)", 1.0, 20.0, 5.0)
        data_source = st.selectbox(
            "Fonte Dati Elevazione", 
            ["SRTM (Globale, 30m)", "LiDAR Campania (WMS, 1m)"],
            help="SRTM usa Google Earth Engine. LiDAR usa il Geoportale Nazionale."
        )
    
    st.header("2. Parametri Simulazione")
    
    # --- Selezione Pioggia ---
    rain_source = st.radio("Modello Pioggia", ["Simulazione (Costante)", "Dati Reali (CHIRPS/GEE)"], help="CHIRPS richiede GEE.")
    
    rain_intensity = 100.0 # Default
    chirps_start = datetime(2022, 1, 1)
    chirps_end = datetime(2023, 1, 1)
    
    if rain_source == "Simulazione (Costante)":
        rain_intensity = st.slider("Intensità Pioggia (mm/h)", 0.0, 200.0, 100.0)
    else:
        st.info("Scarica pioggia max giornaliera da CHIRPS (1981-Oggi).")
        col_d1, col_d2 = st.columns(2)
        chirps_start = col_d1.date_input("Dal", value=datetime(2022, 1, 1))
        chirps_end = col_d2.date_input("Al", value=datetime(2023, 1, 1))

    # --- Selezione Runoff ---
    st.header("2. Modello Deflusso")
    runoff_source = st.radio(
        "Coefficiente di Deflusso", 
        ["Costante (Slider)", "Land Cover Reale (GEE)", "Carica Raster Locale"], 
        help="ESA richiede GEE."
    )
    
    runoff_coeff_val = 0.5
    if runoff_source == "Costante (Slider)":
        runoff_coeff_val = st.slider("Coeff. Deflusso (0-1)", 0.0, 1.0, 0.5, help="0.9=Urbano, 0.3=Vegetazione")
    elif runoff_source == "Land Cover Reale (GEE)":
        st.info("🌍 Usa ESA WorldCover 10m per mappatura automatica")
        st.markdown("""
        **Mappatura automatica:**
        - 🌲 Alberi (10): 0.15 | 🌿 Arbusti (20): 0.20
        - 🌾 Erbacee (30): 0.25 | 🚜 Coltivato (40): 0.35
        - 🏙️ Urbano (50): 0.70 | 🪨 Nudo (60): 0.40
        - 💧 Acqua (80): 0.00 | 🌊 Zone Umide (90): 0.10
        """)
    
    # Variabile per gestire l'upload locale del runoff (se selezionato)
    uploaded_runoff = None
    
    with st.expander("Opzioni Avanzate (Raster)"):
        if runoff_source == "Carica Raster Locale":
            uploaded_runoff = st.file_uploader("Mappa Runoff (GeoTIFF)", type=["tif"], help="Sostituisce il valore costante")
        uploaded_rain_map = st.file_uploader("Mappa Pioggia (Opzionale)", type=["tif"], help="Sostituisce l'intensità costante")
        analyze_osm_check = st.checkbox("Analisi Esposizione Edifici (OSM)", value=False, help="Scarica edifici da OpenStreetMap e calcola il rischio puntuale.")

    # Disabilita bottone se in modalità upload ma nessun file caricato
    disable_run = (input_mode == "Carica File Locale" and dem_source_bytes is None)
    run_btn = st.button("🚀 Esegui Analisi", type="primary", disabled=disable_run)

# --- Mappa di Selezione (Solo modalità Mappa) ---
if input_mode == "Seleziona su Mappa":
    st.subheader("📍 Selezione Area di Interesse")
    
    m = folium.Map(location=[st.session_state.map_coords['lat'], st.session_state.map_coords['lon']], zoom_start=12)
    m.add_child(folium.LatLngPopup())
    
    # Marker centro attuale
    folium.Marker(
        [st.session_state.map_coords['lat'], st.session_state.map_coords['lon']],
        popup="Centro Analisi",
        icon=folium.Icon(color="red", icon="info-sign")
    ).add_to(m)
    
    # Cerchio buffer
    folium.Circle(
        radius=buffer_km * 1000,
        location=[st.session_state.map_coords['lat'], st.session_state.map_coords['lon']],
        color="blue", fill=True, fill_opacity=0.1
    ).add_to(m)
    
    map_data = st_folium(m, height=400, width="100%", key="input_map")
    
    # Gestione click sulla mappa
    if map_data['last_clicked']:
        clicked = map_data['last_clicked']
        # Aggiorna solo se le coordinate sono cambiate significativamente (evita loop)
        if abs(clicked['lat'] - st.session_state.map_coords['lat']) > 0.0001 or abs(clicked['lng'] - st.session_state.map_coords['lon']) > 0.0001:
            st.session_state.map_coords['lat'] = clicked['lat']
            st.session_state.map_coords['lon'] = clicked['lng']
            st.rerun()

# --- Logica Esecuzione ---
if run_btn:
    # Se siamo in modalità mappa, dobbiamo prima scaricare il DTM
    if input_mode == "Seleziona su Mappa":
        with st.spinner(f"Scaricamento dati ({data_source}) in corso..."):
            dl_path = None
            try:
                # File temporaneo per il download
                with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_dl:
                    dl_path = Path(tmp_dl.name)
                
                coords_str = f"{st.session_state.map_coords['lon']},{st.session_state.map_coords['lat']}"
                
                if "SRTM" in data_source:
                    data_ingest.initialize_earth_engine()
                    roi = data_ingest.build_roi_from_coords(coords_str, buffer_km)
                    data_ingest.download_dem_from_gee(roi, "USGS/SRTMGL1_003", dl_path, scale=30)
                elif "LiDAR" in data_source:
                    wms_url = "http://wms.pcn.minambiente.it/ogc?map=/ms_ogc/WMS_v1.3/servizi-LiDAR/LIDAR_CAMPANIA.map"
                    layer = "EL.LIDAR.CAMPANIA.1x1.DTM"
                    lidar_sources.download_lidar_wms_from_coords(
                        coords_str, buffer_km, wms_url, layer, dl_path, resolution_m=1.0
                    )
                
                # Leggi i byte dal file scaricato
                with open(dl_path, "rb") as f:
                    dem_source_bytes = f.read()
                    
                # Validazione rapida: controlla se il file è vuoto o troppo piccolo
                if len(dem_source_bytes) < 1000:
                    st.error("Il file scaricato sembra vuoto o corrotto. Verifica la copertura dell'area selezionata.")
                    dem_source_bytes = None
                
                # Pulizia
                os.remove(dl_path)
                
            except Exception as e:
                st.error(f"Errore durante il download dei dati: {e}")
                if dl_path and os.path.exists(dl_path):
                    os.remove(dl_path)
                st.stop()

    # --- Gestione Pioggia Reale (CHIRPS) ---
    rain_bytes_input = None
    if run_btn and rain_source == "Dati Reali (CHIRPS/GEE)":
        with st.spinner("Scaricamento dati pioggia CHIRPS..."):
            try:
                data_ingest.initialize_earth_engine()
                coords_str = f"{st.session_state.map_coords['lon']},{st.session_state.map_coords['lat']}"
                roi = data_ingest.build_roi_from_coords(coords_str, buffer_km)
                
                with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_rain:
                    rain_dl_path = Path(tmp_rain.name)
                
                data_ingest.download_chirps_rain_from_gee(
                    roi, "UCSB-CHG/CHIRPS/DAILY", 
                    str(chirps_start), str(chirps_end), 
                    rain_dl_path, statistic="max"
                )
                
                with open(rain_dl_path, "rb") as f:
                    rain_bytes_input = f.read()
                os.remove(rain_dl_path)
                
            except Exception as e:
                st.error(f"Errore download CHIRPS: {e}. Assicurati di aver autenticato GEE.")
                st.stop()
    elif uploaded_rain_map:
        rain_bytes_input = uploaded_rain_map.getvalue()

    # --- Gestione Land Cover (ESA) ---
    landcover_bytes_input = None
    if run_btn and runoff_source == "Land Cover Reale (GEE)":
        with st.spinner("Scaricamento Land Cover ESA..."):
            try:
                data_ingest.initialize_earth_engine()
                coords_str = f"{st.session_state.map_coords['lon']},{st.session_state.map_coords['lat']}"
                roi = data_ingest.build_roi_from_coords(coords_str, buffer_km)
                
                with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_lc:
                    lc_dl_path = Path(tmp_lc.name)
                
                lc_coll = config.get("gee_landcover_collection", "ESA/WorldCover/v100")
                data_ingest.download_landcover_from_gee(roi, lc_coll, lc_dl_path)
                
                with open(lc_dl_path, "rb") as f:
                    landcover_bytes_input = f.read()
                os.remove(lc_dl_path)
            except Exception as e:
                st.error(f"Errore download Land Cover: {e}")
                st.stop()

    if dem_source_bytes:
        with st.spinner("Elaborazione idrologica in corso... (potrebbe richiedere qualche secondo)"):
            try:
                # Esegui pipeline (cachata)
                paths, stats = run_risk_pipeline(
                    dem_source_bytes, 
                    rain_intensity, 
                    runoff_coeff_val,
                    uploaded_runoff.getvalue() if uploaded_runoff and runoff_source == "Carica Raster Locale" else None,
                    rain_bytes_input,
                    landcover_bytes_input,
                    analyze_osm_check
                )
                # Salviamo sia i percorsi che le statistiche come tupla
                st.session_state.results = (paths, stats)
                
                if stats.get('warnings'):
                    for w in stats['warnings']:
                        st.warning(w)
                        
                st.success("Analisi completata!")
            except Exception as e:
                st.error(f"Errore durante l'elaborazione: {e}")
                # st.exception(e) # Decommentare per debug

# --- Visualizzazione Risultati ---
if st.session_state.results:
    res, stats = st.session_state.results
    
    st.divider()
    st.subheader("📊 Risultati Analisi")
    
    # Creazione Tabs per organizzazione professionale
    tab_map, tab_3d, tab_stats, tab_download = st.tabs(["🗺️ Mappa 2D", "🏔️ Digital Twin 3D", "📊 Statistiche", "📥 Export"])
    
    with tab_map:
        # Inizializza mappa centrata sull'area analizzata
        # Usiamo le coordinate di input se disponibili, altrimenti default
        center = [st.session_state.map_coords['lat'], st.session_state.map_coords['lon']]
        
        # Fix 3.2: Scala grafica e controlli UX
        m = folium.Map(location=center, zoom_start=13, tiles="CartoDB positron", control_scale=True)
        
        # Aggiunta plugin UX
        plugins.MousePosition(position='bottomleft', separator=' | ', prefix="Coords: ").add_to(m)
        plugins.Fullscreen().add_to(m)
        plugins.MeasureControl(position='topright', primary_length_unit='meters', secondary_length_unit='kilometers').add_to(m)
        
        # Freccia Nord (Icona standard)
        north_arrow_url = "https://upload.wikimedia.org/wikipedia/commons/1/1a/North_arrow_1.png"
        plugins.FloatImage(north_arrow_url, bottom=5, left=5, width="40px").add_to(m)
        
        # Legenda Rischio
        add_legend(m, title="Indice Rischio")
        
        # Aggiungi Layer Raster
        add_raster_to_map(m, res["dem_cond"], "DTM (Elevazione)", colormap=colormaps.get("dem", "terrain"), opacity=opacities.get("dem", 0.6))
        add_raster_to_map(m, res["risk_index"], "Indice di Rischio", colormap=colormaps.get("risk", "RdYlGn_r"), opacity=opacities.get("risk", 0.7))
        add_raster_to_map(m, res["risk_optimized"], "Aree Critiche (Post-Proc)", colormap=colormaps.get("risk_optimized", "Reds"), opacity=opacities.get("risk_optimized", 0.5))
        
        # Aggiungi Edifici a Rischio se presenti
        if analyze_osm_check and res["buildings_geojson"].exists():
            folium.GeoJson(
                str(res["buildings_geojson"]),
                name="Edifici a Rischio",
                style_function=lambda x: {'color': 'red', 'fillColor': 'red', 'weight': 1},
                tooltip=folium.GeoJsonTooltip(fields=['risk_max'], aliases=['Rischio Max:'])
            ).add_to(m)

        folium.LayerControl().add_to(m)
        
        # Fix 3.1: Interattività (Click per ispezionare)
        map_data = st_folium(m, width="100%", height=600, key="result_map")
        
        if map_data and map_data.get("last_clicked"):
            clicked = map_data["last_clicked"]
            st.info(f"📍 Punto selezionato: {clicked['lat']:.5f}, {clicked['lng']:.5f}")
            
            # Campiona valori
            samples = sample_raster_values(clicked, {
                "Elevazione (m)": res["dem_cond"],
                "Rischio (0-1)": res["risk_index"],
                "Pendenza (deg)": res["slope"],
                "Accumulo Flusso": res["flow_acc"]
            })
            
            # Visualizza in colonne
            cols = st.columns(len(samples))
            for idx, (k, v) in enumerate(samples.items()):
                val_str = f"{v:.2f}" if isinstance(v, float) else str(v)
                cols[idx].metric(k, val_str)

    with tab_3d:
        st.markdown("Visualizzazione tridimensionale del terreno. Il colore indica l'indice di rischio (Verde=Basso, Rosso=Alto).")
        vert_exag = st.slider("Esagerazione Verticale", 0.1, 5.0, 1.5, 0.1)
        with st.spinner("Generazione modello 3D..."):
            fig_3d = plot_3d_terrain(res["dem_cond"], res["risk_index"], vert_exag, colorscale=colormaps.get("risk", "RdYlGn_r"))
            if fig_3d:
                st.plotly_chart(fig_3d, use_container_width=True)

    with tab_stats:
        col1, col2, col3 = st.columns(3)
        col1.metric("Rischio Medio", f"{stats['mean']:.3f}")
        col2.metric("Picco Rischio", f"{stats['max']:.3f}")
        col3.metric("Celle Analizzate", f"{stats['pixels']}")
        
        if analyze_osm_check:
            st.metric("Edifici a Rischio (Top 20%)", f"{stats.get('buildings_risk_count', 0)} / {stats.get('buildings_count', 0)}")
        
        st.markdown("### Parametri Input")
        st.json({
            "Pioggia": f"{rain_intensity} mm/h" if rain_source == "Simulazione (Costante)" else "CHIRPS (Reale)",
            "Coeff. Deflusso": f"{runoff_coeff_val}" if runoff_source == "Costante (Slider)" else "ESA WorldCover (Variabile)",
            "Sorgente": "Upload" if input_mode == "Carica File Locale" else data_source
        })

    with tab_download:
        st.subheader("Download Risultati")
        
        # 1. Download Report Markdown
        report_md = generate_technical_report(stats, {'rain': rain_intensity, 'runoff': runoff_coeff_val})
        st.download_button("📄 Scarica Report Tecnico (MD)", report_md, file_name="report_rischio.md")
        
        # 2. Download GeoTIFF Rischio
        try:
            with open(res["risk_index"], "rb") as f:
                risk_data = f.read()
            st.download_button(
                "🌍 Scarica Mappa Rischio (GeoTIFF)", 
                risk_data, 
                file_name="risk_map.tif", 
                mime="image/tiff"
            )
        except FileNotFoundError:
            st.error("File di rischio non trovato (sessione scaduta?). Riesegui l'analisi.")

        # 3. Download Land Cover
        if res["landcover"].exists():
             get_download_link(res["landcover"], "landcover.tif", "🌿 Scarica Land Cover (GeoTIFF)")

        # 4. Download Edifici
        if analyze_osm_check and res["buildings_geojson"].exists():
            try:
                with open(res["buildings_geojson"], "rb") as f:
                    geojson_data = f.read()
                st.download_button(
                    "🏠 Scarica Edifici a Rischio (GeoJSON)", 
                    geojson_data, 
                    file_name="buildings_risk.geojson", 
                    mime="application/geo+json"
                )
            except FileNotFoundError:
                st.warning("File GeoJSON edifici non trovato.")