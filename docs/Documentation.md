# Documentazione Progetto: Valutazione Rischio di Alluvioni con DTM LIDAR

Questo documento fornisce una panoramica dettagliata del progetto "DTM LIDAR Flood Risk Assessment", esplorando la sua struttura, i componenti principali, le funzionalità di ciascun modulo e i layer di dati prodotti.

---

## 1. Scopo Generale del Progetto

Il progetto mira a sviluppare una pipeline flessibile e robusta per la valutazione del rischio di alluvioni. Sfrutta diverse fonti di dati geospaziali (LiDAR, DEM da GEE, dati OSM, copertura del suolo, precipitazioni) e tecniche avanzate di modellazione idrologica per identificare le aree a rischio e gli elementi esposti, supportando l'analisi e la pianificazione territoriale. Il sistema è progettato per essere configurabile e adattabile a diverse esigenze e contesti di dati.

---

## 2. Prototipi Principali

Il progetto include due script prototipo principali che dimostrano diversi approcci alla valutazione del rischio:

### 2.1. `flood_risk_prototype.py`

*   **Approccio**: Pipeline di **screening rapido multi-sorgente**. Progettata per essere veloce e flessibile, accetta dati da GEE (SRTM) o WMS (LiDAR) e utilizza parametri semplificati (pioggia e deflusso costanti) per una valutazione immediata.
*   **Workflow**:
    1.  **Acquisizione Dati**: Ottenimento del DEM da file LiDAR locali, WMS (es. Campania) o GEE (SRTM).
    2.  **Elaborazione DEM**: Condizionamento del DEM grezzo (attualmente un riempimento base delle depressioni, placeholder per future implementazioni più robuste).
    3.  **Calcolo Indici Idrologici**: Derivazione della Pendenza (Slope), Accumulo di Flusso (Flow Accumulation - con backend configurabile tra `pysheds`, `whitebox-tools` o un placeholder semplificato), Indice di Umidità Topografica (Topographic Wetness Index - TWI) e Indice di Potenza del Flusso (Stream Power Index - SPI).
    4.  **Modellazione del Rischio**: Calcolo di un indice di rischio combinato utilizzando input semplificati (deflusso costante 0.5, pioggia costante) per rapidità.
    5.  **Esposizione OSM**: (Opzionale) Identificazione degli edifici a rischio e export in GeoJSON.

### 2.2. `gee_lidar_prototype.py`

*   **Approccio**: Pipeline "GEE-centric", progettata per sfruttare la scalabilità e le capacità di elaborazione cloud di Google Earth Engine, in particolare per l'uso di DTM LiDAR ad alta risoluzione già residenti come asset GEE o caricati su di esso.
*   **Workflow**:
    1.  **Inizializzazione GEE**: Avvio dell'ambiente Google Earth Engine.
    2.  **Upload Asset (Opzionale)**: Possibilità di caricare GeoTIFF locali (DTM LiDAR, Accumulo di Flusso) come asset GEE.
    3.  **Definizione ROI**: Definizione dell'Area di Interesse (ROI) da coordinate e un buffer.
    4.  **Elaborazione in GEE**: Tutti i calcoli avvengono interamente all'interno di GEE. Utilizza il DTM LiDAR dall'asset GEE, la copertura del suolo ESA WorldCover e i dati di precipitazione CHIRPS.
    5.  **Calcolo Indici Idrologici GEE**: Calcolo di Pendenza, TWI e SPI usando le funzioni native di GEE (`ee.Terrain`). L'Accumulo di Flusso utilizza un asset GEE personalizzato o i dati MERIT Hydro.
    6.  **Derivazione Deflusso GEE**: Derivazione dei coefficienti di deflusso dalla copertura del suolo con una mappatura semplificata.
    7.  **Modellazione del Rischio GEE**: Calcolo di un indice di rischio di alluvioni più semplice basato su una formula diretta: `(Pioggia * CoeffDeflusso) / (Pendenza + 1)`.
    8.  **Output**: Esportazione dei raster elaborati (DEM, rischio, TWI, SPI) da GEE a file GeoTIFF locali. Generazione di una mappa interattiva HTML (Folium/geemap) per la visualizzazione.

---

## 3. Moduli Core (`core/`)

La directory `core/` contiene i moduli che implementano le funzionalità di base riutilizzabili in entrambe le pipeline:

*   **`data_ingest.py`**:
    *   **Scopo**: Gestisce tutte le operazioni di acquisizione dati.
    *   **Funzioni Chiave**:
        *   `load_dem_from_lidar`: Converte una nuvola di punti LiDAR (LAS/LAZ) in un DTM raster GeoTIFF usando `pdal` (con fallback `laspy` nel prototipo).
        *   `initialize_earth_engine`: Inizializza l'API di Google Earth Engine.
        *   `build_roi_from_coords`: Costruisce una geometria ROI (Region of Interest) per GEE da coordinate e un buffer.
        *   `download_dem_from_gee`, `download_landcover_from_gee`, `download_chirps_rain_from_gee`: Scarica rispettivamente DEM, copertura del suolo e dati di pioggia aggregati da GEE.
        *   `upload_geotiff_to_gee`: Carica un GeoTIFF locale come asset GEE.
*   **`dem_processing.py`**:
    *   **Scopo**: Elaborazione e condizionamento dei Modelli Digitali di Elevazione (DEM).
    *   **Funzioni Chiave**:
        *   `fill_pits_simple`: Riempimento base delle depressioni (placeholder).
        *   `merge_with_medium_dem`: Unisce un DEM LiDAR ad alta risoluzione con un DEM più grossolano (es. Copernicus), gestendo la riproiezione e i nodata.
        *   `condition_dem`: Punto di ingresso di alto livello per il condizionamento DEM.
*   **`geocoding.py`**:
    *   **Scopo**: Conversione di indirizzi testuali in coordinate geografiche.
    *   **Funzioni Chiave**:
        *   `geocode_address_to_coords`: Utilizza `geopy` (Nominatim di OpenStreetMap) per geocodificare un indirizzo in una stringa "lon,lat".
*   **`hydro_indices.py`**:
    *   **Scopo**: Calcolo di indici idrologici derivati dal DEM.
    *   **Funzioni Chiave**:
        *   `compute_slope`: Calcola la pendenza dal DEM.
        *   `compute_flow_accumulation`: Punto di ingresso per il calcolo dell'accumulo di flusso, con backend configurabili (`pysheds`, `whitebox-tools`, o placeholder).
        *   `compute_twi`: Calcola l'Indice di Umidità Topografica (TWI).
        *   `compute_spi`: Calcola l'Indice di Potenza del Flusso (SPI).
*   **`landcover.py`**:
    *   **Scopo**: Elaborazione dei dati di copertura del suolo.
    *   **Funzioni Chiave**:
        *   `_resample_to_match`: Ricampiona un raster per farlo corrispondere alla griglia di un raster di riferimento.
        *   `map_landcover_to_runoff`: Mappa le classi di copertura del suolo a coefficienti di deflusso.
        *   `map_landcover_to_manning_n`: Mappa le classi di copertura del suolo a coefficienti di rugosità di Manning.
*   **`lidar_sources.py`**:
    *   **Scopo**: Scaricare DTM LiDAR da servizi WMS.
    *   **Funzioni Chiave**:
        *   `_bbox_from_coords`: Calcola un bounding box (lon/lat) da coordinate centrali e un buffer.
        *   `download_lidar_wms_from_coords`: Scarica un DTM LiDAR da un servizio WMS, gestendo i parametri della richiesta e le dimensioni dell'immagine.
*   **`osm_exposure.py`**:
    *   **Scopo**: Analisi dell'esposizione utilizzando dati OpenStreetMap.
    *   **Funzioni Chiave**:
        *   `download_osm_rivers_bbox`, `download_osm_buildings_bbox`: Scarica fiumi e edifici da OSM per una data area.
        *   `burn_in_rivers_on_dem`: Modifica un DEM abbassando l'elevazione lungo i corsi d'acqua (river burn-in).
        *   `buildings_risk_to_geojson`: Identifica gli edifici più a rischio (es. top 10%) e li esporta in GeoJSON.
        *   `export_buildings_csv`, `export_buildings_folium_map`: Esporta i centroidi degli edifici in CSV e genera una mappa interattiva Folium.
*   **`postprocessing.py`**:
    *   **Scopo**: Raffinamento dei dati di rischio grezzi e visualizzazione.
    *   **Funzioni Chiave**:
        *   `create_optimized_risk_from_spi`: Applica filtro mediano, soglia percentile e buffer (dilatazione morfologica) all'SPI per creare una mappa di rischio binaria ottimizzata.
        *   `plot_risk_overlay`: Genera un'immagine PNG di sovrapposizione del DEM con le aree di rischio.
*   **`reporting.py`**:
    *   **Scopo**: Generazione di report riassuntivi.
    *   **Funzioni Chiave**:
        *   `_raster_stats`: Calcola statistiche di base (min, max, media, dev.std) per un raster.
        *   `write_report_markdown`: Genera un report in Markdown con le statistiche dei layer principali.
*   **`risk_model.py`**:
    *   **Scopo**: Logica principale per il calcolo e la classificazione del rischio di alluvioni.
    *   **Funzioni Chiave**:
        *   `_normalize`: Normalizza un array NumPy in un intervallo [0, 1].
        *   `compute_simple_risk_index`: Calcola un indice di rischio di base `(Pioggia * Deflusso) / (Pendenza + 1)`.
        *   `compute_combined_risk_index`: Calcola un indice di rischio combinato più avanzato e configurabile, basato su una somma ponderata di indici idrologici normalizzati e precipitazioni, con soglie di classificazione.
*   **`utils.py`**:
    *   **Scopo**: Modulo di utilità centralizzato per I/O raster e configurazione.
    *   **Funzioni Chiave**:
        *   `load_config`: Carica la configurazione da `config.yaml`.
        *   `get_wbt`: Configura e restituisce l'istanza di WhiteboxTools (supporta Docker).
        *   `read_raster`, `write_raster`: Funzioni unificate per lettura/scrittura GeoTIFF con gestione sicura dei nodata.
*   **`crs_validation.py`**:
    *   **Scopo**: Validazione della coerenza dei sistemi di riferimento (CRS).
    *   **Funzioni Chiave**:
        *   `check_crs_consistency`: Verifica che una lista di raster condivida lo stesso CRS.
        *   `validate_rainfall_raster`: Controlla la compatibilità spaziale tra raster pioggia e DEM.
*   **`logging_config.py`**:
    *   **Scopo**: Configurazione centralizzata del logging (supporta `loguru` o standard logging).
    *   **Funzioni Chiave**:
        *   `setup_logging`, `get_logger`: Inizializza i logger per i vari moduli.

---

## 4. Layer di Dati e Output Generati

Il progetto produce una varietà di layer di dati geospaziali e output per l'analisi e la visualizzazione:

*   **`dem_raw.tif`**: DEM grezzo acquisito (da LiDAR o GEE).
*   **`dem_conditioned.tif`**: DEM processato e condizionato.
*   **`slope.tif`**: Mappa della pendenza derivata dal DEM.
*   **`flow_accumulation.tif`**: Mappa dell'accumulo di flusso.
*   **`twi.tif`**: Mappa dell'Indice di Umidità Topografica.
*   **`spi.tif`**: Mappa dell'Indice di Potenza del Flusso.
*   **`landcover.tif`**: Mappa della copertura del suolo (da GEE).
*   **`runoff_coeff.tif`**: Mappa dei coefficienti di deflusso derivati dalla copertura del suolo.
*   **`rain_chirps.tif`**: Mappa delle precipitazioni (da CHIRPS GEE).
*   **`risk_index.tif`**: Mappa dell'indice di rischio di alluvioni (valori continui normalizzati).
*   **`risk_class.tif`**: Mappa delle classi di rischio (1=Basso, 2=Medio, 3=Alto).
*   **`Risk_Map_Optimized.tif`**: Maschera di rischio binaria ottimizzata (dopo post-processing SPI).
*   **`Risk_Map_Overlay.png`**: Immagine PNG di sovrapposizione DEM + mappa di rischio ottimizzata.
*   **`report.md`**: Report testuale in Markdown con statistiche riassuntive.
*   **`buildings_high_risk.geojson`**: GeoJSON degli edifici identificati come ad alto rischio.
*   **`buildings_high_risk.csv`**: CSV con le coordinate dei centroidi degli edifici ad alto rischio.
*   **`buildings_risk_map.html`**: Mappa HTML interattiva (Folium) con gli edifici a rischio evidenziati.
*   **`lidar_risk_map.html`** (solo da `gee_lidar_prototype.py`): Mappa HTML interattiva che visualizza i layer elaborati in GEE.

---

## 5. Punti di Forza e Debolezza

### Punti di Forza:

*   **Modularità e Riusabilità**: Codice ben organizzato in moduli dedicati.
*   **Flessibilità Fonti Dati**: Supporto per LiDAR locale, GEE e servizi WMS.
*   **Configurabilità**: Parametri chiave del modello (pesi, soglie, backend FA) configurabili esternamente.
*   **Elaborazione Idrologica Robusta**: Backend configurabile per l'accumulo di flusso, calcoli standard di TWI/SPI.
*   **Gestione Avanzata DEM**: Funzione di fusione DEM sofisticata.
*   **Analisi dell'Esposizione**: Integrazione con dati OSM per edifici e fiumi, con strumenti di modifica DEM e identificazione asset a rischio.
*   **Post-Elaborazione e Visualizzazione**: Raffinamento dei dati di rischio e produzione di output visivi e testuali utili.
*   **Gestione Errori**: Buona gestione delle dipendenze opzionali.

### Punti di Debolezza:

*   **Implementazioni Placeholder**: Il riempimento delle depressioni (`fill_pits_simple`) e il fallback di accumulo di flusso sono ancora semplici placeholder, che possono influire sull'accuratezza rispetto a condizionamenti idrologici avanzati.
*   **Discrepanza Modelli di Rischio**: Il modello GEE è significativamente più semplice e meno configurabile di quello locale.
*   **Dipendenza da PDAL**: L'installazione di PDAL può essere complessa; il fallback `laspy` è presente ma non è una soluzione equivalente per tutte le funzionalità di PDAL.
*   **Specificità GEE**: Il modello GEE utilizza MERIT Hydro a 90m per l'accumulo di flusso come fallback, potenzialmente incongruente con LiDAR ad alta risoluzione.
*   **Mancanza di Test Unitari**: Assenza di un framework di test visibile, rendendo difficile garantire la correttezza e prevenire regressioni.

---

## 6. Miglioramenti Proposti

Per migliorare la robustezza, l'accuratezza, l'efficienza e la manutenibilità del progetto:

*   **Struttura del Codice**:
    *   **Gestione Dipendenze**: Chiarire la strategia per le dipendenze richieste vs. opzionali.
*   **Robustezza e Accuratezza**:
    *   **Condizionamento DEM Avanzato**: Sostituire i placeholder di riempimento depressioni con implementazioni più robuste basate su `pysheds` o `whitebox-tools`. Considerare l'enforcement di infrastrutture.
    *   **Unificazione Modelli di Rischio**: Allineare il modello di rischio GEE con la logica più sofisticata e configurabile del `risk_model.py`, includendo normalizzazione e pesi.
    *   **Estensione Pioggia Locale**: Implementare l'ingestione di dati raster di pioggia locali nella pipeline `flood_risk_prototype.py`.
    *   **Mappatura Dinamica Land Cover**: Caricare le mappature di runoff/Manning da `config.yaml` o file dedicati.
*   **Efficienza**:
    *   **Ottimizzazione I/O Raster**: Implementare caching per letture raster ripetute.
    *   **Parallelizzazione**: Utilizzare `multiprocessing` o `dask` per l'elaborazione di geometrie complesse o grandi quantità di dati.
    *   **Scala Esportazione GEE**: Ottimizzare il parametro `scale` in `geemap.ee_export_image` per evitare esportazioni eccessivamente grandi.
*   **Testing**:
    *   **Test Unitari e di Integrazione**: Introdurre un framework di test (es. `pytest`) per garantire la correttezza di funzioni individuali e intere pipeline.
    *   **Integrazione Continua (CI)**: Configurare una pipeline CI per l'esecuzione automatica dei test.
