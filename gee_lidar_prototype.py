import argparse
import sys
from pathlib import Path
import ee
import geemap
from core import utils, logging_config, data_ingest, geocoding

logger = logging_config.get_logger("GEE_LiDAR_Proto")
config = utils.load_config()

def main():
    parser = argparse.ArgumentParser(description="GEE-Centric LiDAR Flood Risk Pipeline")
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--coords", help="Coordinate 'lat,lon'")
    group.add_argument("--address", help="Indirizzo")
    
    parser.add_argument("--asset-id", required=True, help="ID Asset GEE del DTM LiDAR (es. users/me/lidar_avella)")
    parser.add_argument("--lidar-tif", help="Path locale GeoTIFF LiDAR da caricare se non esiste asset")
    parser.add_argument("--upload-asset", action="store_true", help="Carica il TIF locale su GEE prima dell'analisi")
    
    parser.add_argument("--buffer-km", type=float, default=5.0)
    parser.add_argument("--out-dir", default="output/gee_analysis")
    parser.add_argument("--scale", type=float, default=5.0, help="Scala di esportazione (metri)")
    
    args = parser.parse_args()

    # 1. Init GEE
    try:
        ee.Initialize()
    except Exception as e:
        logger.error(f"Errore init GEE: {e}")
        sys.exit(1)

    # 2. Location
    if args.address:
        coords = geocoding.geocode_address_to_coords(args.address)
        if coords is None:
            logger.error(f"Indirizzo non trovato: {args.address}")
            sys.exit(1)
        lat, lon = coords
    else:
        lat, lon = map(float, args.coords.split(","))

    coords_str = f"{lon},{lat}"
    roi = data_ingest.build_roi_from_coords(coords_str, args.buffer_km)
    
    # 3. Gestione Asset LiDAR
    if args.upload_asset and args.lidar_tif:
        logger.info(f"Caricamento {args.lidar_tif} su GEE asset {args.asset_id}...")
        data_ingest.upload_geotiff_to_gee(Path(args.lidar_tif), args.asset_id, overwrite=True)
        logger.info("Upload avviato. Nota: L'ingestione GEE è asincrona e richiede tempo.")
        # In uno script reale bisognerebbe attendere il task, qui assumiamo asset esistente o proseguiamo
    
    try:
        dem = ee.Image(args.asset_id).clip(roi)
    except Exception:
        logger.error(f"Impossibile accedere all'asset {args.asset_id}. Verifica permessi o upload.")
        sys.exit(1)

    # 4. Dati Ausiliari GEE
    lc_coll = config.get("gee_landcover_collection", "ESA/WorldCover/v100")
    landcover = ee.ImageCollection(lc_coll).first().clip(roi)
    
    chirps_coll = config.get("gee_chirps_collection", "UCSB-CHG/CHIRPS/DAILY")
    rain = ee.ImageCollection(chirps_coll)\
        .filterDate('2020-01-01', '2023-01-01')\
        .select('precipitation').max().clip(roi)

    # 5. Calcolo Indici (Server-Side)
    logger.info("Esecuzione calcoli idrologici su GEE...")
    
    # Slope
    slope = ee.Terrain.slope(dem)
    
    # Runoff (Mapping semplificato ESA WorldCover)
    # 50 = Built-up -> 0.7, Altro -> 0.3
    runoff = landcover.eq(50).multiply(0.7).add(
        landcover.neq(50).multiply(0.3)
    )
    
    # Flow Accumulation (Usa MERIT Hydro come fallback o calcolo costoso)
    # Per semplicità in questo prototipo usiamo una proxy basata su slope/area
    # In produzione: usare un asset flow acc pre-calcolato
    
    # Modello Rischio Semplificato GEE
    # Risk = (Rain * Runoff) / (Slope + 1)
    risk = rain.multiply(runoff).divide(slope.add(1)).rename('risk_index')
    
    # Normalizzazione (approssimata locale)
    stats = risk.reduceRegion(reducer=ee.Reducer.minMax(), geometry=roi, scale=args.scale, bestEffort=True)
    min_val = ee.Number(stats.get('risk_index_min'))
    max_val = ee.Number(stats.get('risk_index_max'))
    risk_norm = risk.subtract(min_val).divide(max_val.subtract(min_val))

    # 6. Export
    out_path = Path(args.out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    
    logger.info("Esportazione raster locali...")
    geemap.ee_export_image(dem, filename=str(out_path / "dem_gee.tif"), scale=args.scale, region=roi, file_per_band=False)
    geemap.ee_export_image(risk_norm, filename=str(out_path / "risk_gee.tif"), scale=args.scale, region=roi, file_per_band=False)
    
    # 7. Mappa HTML
    m = geemap.Map()
    m.centerObject(roi, 13)
    
    vis_dem = {'min': 0, 'max': 500, 'palette': ['006633', 'E5FFCC', '662A00', 'D8D8D8', 'F5F5F5']}
    vis_risk = {'min': 0, 'max': 1, 'palette': ['blue', 'yellow', 'orange', 'red']}
    
    m.addLayer(dem, vis_dem, 'LiDAR DTM')
    m.addLayer(risk_norm, vis_risk, 'Rischio Idrogeologico')
    
    map_out = out_path / "gee_risk_map.html"
    m.save(str(map_out))
    logger.info(f"Mappa interattiva salvata in {map_out}")

if __name__ == "__main__":
    main()