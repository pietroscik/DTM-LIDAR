import sys
import os
import argparse
from pathlib import Path
from core import data_ingest, dem_processing, hydro_indices, risk_model, utils, logging_config, osm_exposure, reporting
import numpy as np
from datetime import datetime, timedelta

try:
    from core import lidar_sources
except ImportError:
    lidar_sources = None

logger = logging_config.get_logger("HydroGIS_Screening")

def main():
    parser = argparse.ArgumentParser(description="Hydro-GIS Rapid Screening Pipeline (SRTM/LiDAR)")
    parser.add_argument("--coords", required=True, help="lat,lon")
    parser.add_argument("--buffer-km", type=float, default=10.0)
    parser.add_argument("--out-dir", default="output/srtm_screening")
    parser.add_argument("--use-gee", action="store_true", help="Usa GEE come sorgente dati")
    parser.add_argument("--resolution", type=float, default=30.0, help="Risoluzione target in metri")
    parser.add_argument("--lidar-wms-url", help="URL WMS per DTM LiDAR")
    parser.add_argument("--lidar-wms-layer", help="Nome layer WMS")
    parser.add_argument("--rain-intensity", type=float, default=100.0, help="Intensità pioggia (mm/h)")
    parser.add_argument("--enable-osm-exposure", action="store_true", help="Abilita analisi esposizione OSM")
    parser.add_argument("--runoff-coeff", type=float, default=0.5, help="Coefficiente di deflusso costante (fallback)")
    parser.add_argument("--enable-chirps", action="store_true", help="Usa CHIRPS per pioggia reale")
    parser.add_argument("--local-landcover", type=Path, help="Path locale land cover (alternativa a GEE)")
    args = parser.parse_args()

    config = utils.load_config()
    wms_url = args.lidar_wms_url or config.get("lidar_wms_url")
    wms_layer = args.lidar_wms_layer or config.get("lidar_wms_layer")

    lat, lon = map(float, args.coords.split(","))
    coords_str = f"{lon},{lat}"
    
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Download DEM (WMS o GEE)
    dem_path = out_dir / "dem_raw.tif"
    
    if wms_url and wms_layer:
        if lidar_sources is None:
            logger.error("Modulo lidar_sources non disponibile. Impossibile usare WMS.")
            return
        logger.info(f"Acquisizione LiDAR da WMS: {wms_layer}...")
        lidar_sources.download_lidar_wms_from_coords(
            coords_str, args.buffer_km, wms_url, wms_layer, dem_path, resolution_m=args.resolution
        )
    else:
        logger.info("Acquisizione SRTM da GEE...")
        data_ingest.initialize_earth_engine()
        roi = data_ingest.build_roi_from_coords(coords_str, args.buffer_km)
        dem_dataset = config.get("gee_dem_dataset_id", "USGS/SRTMGL1_003")
        data_ingest.download_dem_from_gee(roi, dem_dataset, dem_path, scale=args.resolution)
    
    if not dem_path.exists():
        logger.error("DEM non creato. Interruzione.")
        return
    
    # 2. Elaborazione Rapida
    dem_cond = out_dir / "dem_cond.tif"
    slope_path = out_dir / "slope.tif"
    flow_acc_path = out_dir / "flow_acc.tif"
    twi_path = out_dir / "twi.tif"
    spi_path = out_dir / "spi.tif"
    risk_index_path = out_dir / "risk_index.tif"
    risk_class_path = out_dir / "risk_class.tif"
    
    dem_processing.condition_dem(dem_path, dem_cond)
    hydro_indices.compute_slope(dem_cond, slope_path)
    hydro_indices.compute_flow_accumulation(dem_cond, flow_acc_path)
    hydro_indices.compute_twi(dem_cond, flow_acc_path, twi_path)
    hydro_indices.compute_spi(flow_acc_path, slope_path, spi_path)
    
    # 3. Calcolo Rischio Avanzato
    runoff_path = out_dir / "runoff.tif"
    rain_path = out_dir / "rain.tif"
    
    data, profile, _ = utils.read_raster(dem_cond)
    
    # --- 1. Gestione Runoff (Land Cover) ---
    if args.local_landcover and args.local_landcover.exists():
        logger.info(f"Uso land cover locale: {args.local_landcover}")
        landcover.map_landcover_to_runoff(
            landcover_path=args.local_landcover,
            mapping=None, # Usa config
            out_path=runoff_path,
            reference_raster=dem_cond
        )
    elif args.use_gee:
        logger.info("Download land cover da GEE per calcolo runoff...")
        try:
            data_ingest.initialize_earth_engine()
            roi = data_ingest.build_roi_from_coords(coords_str, args.buffer_km)
            lc_path = out_dir / "landcover.tif"
            lc_coll = config.get("gee_landcover_collection", "ESA/WorldCover/v100")
            data_ingest.download_landcover_from_gee(roi, lc_coll, lc_path, scale=args.resolution)
            
            landcover.map_landcover_to_runoff(
                landcover_path=lc_path,
                mapping=None,
                out_path=runoff_path,
                reference_raster=dem_cond
            )
        except Exception as e:
            logger.error(f"Errore GEE Land Cover: {e}. Uso costante {args.runoff_coeff}.")
            utils.write_raster(runoff_path, np.full(data.shape, args.runoff_coeff, dtype="float32"), profile)
    else:
        logger.info(f"Uso runoff costante: {args.runoff_coeff}")
        utils.write_raster(runoff_path, np.full(data.shape, args.runoff_coeff, dtype="float32"), profile)

    # --- 2. Gestione Pioggia (CHIRPS) ---
    if args.use_gee and args.enable_chirps:
        logger.info("Download pioggia CHIRPS da GEE...")
        try:
            chirps_coll = config.get("gee_chirps_collection", "UCSB-CHG/CHIRPS/DAILY")
            end_date = datetime.now()
            start_date = end_date - timedelta(days=365*2)
            data_ingest.download_chirps_rain_from_gee(
                roi, chirps_coll, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"), 
                rain_path, statistic="max"
            )
        except Exception as e:
            logger.error(f"Errore GEE CHIRPS: {e}. Uso costante {args.rain_intensity}.")
            utils.write_raster(rain_path, np.full(data.shape, args.rain_intensity, dtype="float32"), profile)
    else:
        utils.write_raster(rain_path, np.full(data.shape, args.rain_intensity, dtype="float32"), profile)
    
    risk_model.compute_combined_risk_index(
        runoff_coeff_path=runoff_path, slope_path=slope_path, twi_path=twi_path, spi_path=spi_path,
        out_index_path=risk_index_path, out_class_path=risk_class_path,
        rain_raster_path=rain_path, rain_intensity=args.rain_intensity
    )
    
    # 4. Analisi Esposizione OSM
    if args.enable_osm_exposure:
        logger.info("Analisi Esposizione Edifici OSM...")
        import rasterio
        from rasterio.warp import transform_bounds
        with rasterio.open(dem_cond) as src:
            w, s, e, n = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
        
        buildings = osm_exposure.download_osm_buildings_from_bbox(n, s, e, w)
        if not buildings.empty:
            geojson_path = out_dir / "buildings_risk.geojson"
            osm_exposure.buildings_risk_to_geojson(buildings, risk_index_path, geojson_path)
    
    # 5. Reportistica
    report_path = out_dir / "report.md"
    reporting.write_report_markdown(
        out_path=report_path,
        area_description=f"Screening Rapido - {coords_str}",
        dem_path=dem_cond,
        risk_index_path=risk_index_path,
        extra_layers={
            "Slope": slope_path,
            "TWI": twi_path,
            "SPI": spi_path,
            "RiskClass": risk_class_path
        }
    )

    logger.info(f"Screening completato. Output in {out_dir}")

if __name__ == "__main__":
    main()