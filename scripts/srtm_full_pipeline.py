from pathlib import Path
import sys

import argparse

# Ensure project root is on sys.path so that `core` can be imported
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import (
    data_ingest,
    dem_processing,
    hydro_indices,
    landcover,
    osm_exposure,
    postprocessing,
    reporting,
    risk_model,
    utils,
    logging_config,
)

logging_config.setup_logging(log_level="INFO")
logger = logging_config.get_logger("SRTM_Full_Pipeline")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "SRTM-based prototype pipeline for flood risk assessment. "
            "Usare solo per analisi esplorative a bassa risoluzione."
        )
    )
    parser.add_argument(
        "--coords",
        type=str,
        required=True,
        help="Coordinates 'lon,lat' for the area of interest.",
    )
    parser.add_argument(
        "--buffer-km",
        type=float,
        default=5.0,
        help="Buffer radius around coords in kilometers.",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        required=True,
        help="Output directory for generated rasters and report.",
    )
    parser.add_argument(
        "--chirps-start",
        type=str,
        default="2020-01-01",
        help="Start date for CHIRPS aggregation (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--chirps-end",
        type=str,
        default="2023-01-01",
        help="End date for CHIRPS aggregation (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--enable-osm-exposure",
        action="store_true",
        help=(
            "Scarica fiumi/edifici da OSM, applica burn-in sul DEM e "
            "calcola edifici ad alto rischio (GeoJSON)."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    coords_str = args.coords
    area_desc = coords_str

    dem_raw = out_dir / "dem_raw.tif"
    dem_cond = out_dir / "dem_conditioned.tif"
    slope_path = out_dir / "slope.tif"
    flow_acc_path = out_dir / "flow_accumulation.tif"
    twi_path = out_dir / "twi.tif"
    spi_path = out_dir / "spi.tif"
    landcover_path = out_dir / "landcover.tif"
    runoff_path = out_dir / "runoff_coeff.tif"
    rain_raster_path = out_dir / "rain_chirps.tif"
    risk_index_path = out_dir / "risk_index.tif"
    risk_class_path = out_dir / "risk_class.tif"
    risk_spi_optimized_path = out_dir / "Risk_Map_Optimized.tif"
    risk_overlay_png = out_dir / "Risk_Map_Overlay.png"
    buildings_folium_html = out_dir / "buildings_risk_map.html"
    buildings_csv = out_dir / "buildings_high_risk.csv"
    report_path = out_dir / "report.md"

    # Carica configurazione
    config = utils.load_config()
    dem_dataset = config.get("gee_dem_dataset_id", "USGS/SRTMGL1_003")
    lc_collection = config.get("gee_landcover_collection", "ESA/WorldCover/v100")
    chirps_collection = config.get("gee_chirps_collection", "UCSB-CHG/CHIRPS/DAILY")

    logger.info("Modalità SRTM (coarse screening) attiva.")

    # 1. GEE initialization and SRTM/WorldCover/CHIRPS download
    logger.info("Initializing Google Earth Engine.")
    data_ingest.initialize_earth_engine()
    roi = data_ingest.build_roi_from_coords(
        coords=coords_str,
        buffer_km=args.buffer_km,
    )

    logger.info("Downloading DEM from GEE (SRTM).")
    data_ingest.download_dem_from_gee(
        roi=roi,
        dataset_id=dem_dataset,
        out_dem_tif=dem_raw,
        scale=30.0,
    )

    # 1b. Hydro-enforcement: optional burn-in using OSM rivers
    if args.enable_osm_exposure:
        logger.info("OSM exposure abilitata: scarico fiumi per burn-in DEM.")
        rivers_gdf = osm_exposure.download_osm_rivers_bbox(
            coords_str=coords_str,
            buffer_km=args.buffer_km,
        )
        osm_exposure.burn_in_rivers_on_dem(
            dem_path=dem_raw,
            rivers_gdf=rivers_gdf,
            burn_depth=5.0,
            out_dem_path=dem_raw,
        )

    logger.info("Downloading land cover from GEE (ESA WorldCover).")
    data_ingest.download_landcover_from_gee(
        roi=roi,
        collection_id=lc_collection,
        out_tif=landcover_path,
    )

    logger.info("Downloading CHIRPS rainfall from GEE.")
    data_ingest.download_chirps_rain_from_gee(
        roi=roi,
        collection_id=chirps_collection,
        start_date=args.chirps_start,
        end_date=args.chirps_end,
        out_tif=rain_raster_path,
        statistic="max",
    )

    # 2. DEM conditioning
    dem_processing.condition_dem(dem_raw, dem_cond)

    # 3. Hydrological indices
    hydro_indices.compute_slope(dem_cond, slope_path)
    hydro_indices.compute_flow_accumulation(dem_cond, flow_acc_path)
    hydro_indices.compute_twi(dem_cond, flow_acc_path, twi_path)
    hydro_indices.compute_spi(flow_acc_path, slope_path, spi_path)

    # 4. Land cover -> runoff
    # Passiamo None come mapping per forzare il caricamento da config.yaml
    landcover.map_landcover_to_runoff(
        landcover_path=landcover_path,
        mapping=None,
        out_path=runoff_path,
        reference_raster=dem_cond,
    )

    # 5. Combined risk index using CHIRPS rain raster
    logger.info("Computing combined risk index using CHIRPS rain raster.")
    risk_model.compute_combined_risk_index(
        runoff_coeff_path=runoff_path,
        slope_path=slope_path,
        twi_path=twi_path,
        spi_path=spi_path,
        out_index_path=risk_index_path,
        out_class_path=risk_class_path,
        rain_raster_path=rain_raster_path,
    )

    # 6. SPI-based post-processing: optimized risk map + overlay
    logger.info(
        "Creating SPI-based optimized risk map (median filter + 95th percentile)."
    )
    postprocessing.create_optimized_risk_from_spi(
        spi_path=spi_path,
        out_risk_path=risk_spi_optimized_path,
        percentile=95.0,
    )
    logger.info("Creating DEM + Optimized Risk overlay image.")
    postprocessing.plot_risk_overlay(
        dem_path=dem_cond,
        risk_mask_path=risk_spi_optimized_path,
        out_png_path=risk_overlay_png,
    )
    # 7. OSM buildings exposure: high-risk buildings (GeoJSON, HTML, CSV)
    if args.enable_osm_exposure:
        logger.info(
            "OSM exposure abilitata: scarico edifici e calcolo edifici ad alto rischio."
        )
        buildings_gdf = osm_exposure.download_osm_buildings_bbox(
            coords_str=coords_str,
            buffer_km=args.buffer_km,
        )
        # Edifici che cadono in celle con rischio SPI ottimizzato > 0
        buildings_at_risk = osm_exposure.buildings_in_risk_mask(
            buildings_gdf=buildings_gdf,
            risk_mask_path=risk_spi_optimized_path,
        )
        # GeoJSON (manteniamo anche questo, utile per WebGIS)
        osm_exposure.buildings_risk_to_geojson(
            buildings_gdf=buildings_at_risk,
            risk_raster_path=risk_index_path,
            out_geojson_path=out_dir / "buildings_high_risk.geojson",
            top_percent=10.0,
        )
        # CSV con coordinate centroidi edifici critici
        osm_exposure.export_buildings_csv(
            buildings_gdf=buildings_at_risk,
            out_csv_path=buildings_csv,
        )
        # Mappa HTML Folium con edifici a rischio in rosso
        # coords_str è "lon,lat"
        lon_str, lat_str = coords_str.split(",")
        center_lon = float(lon_str.strip())
        center_lat = float(lat_str.strip())
        osm_exposure.export_buildings_folium_map(
            buildings_gdf=buildings_at_risk,
            center_coords=(center_lon, center_lat),
            out_html_path=buildings_folium_html,
        )

    # 8. Report
    reporting.write_report_markdown(
        out_path=report_path,
        area_description=area_desc + " (SRTM coarse screening)",
        dem_path=dem_cond,
        risk_index_path=risk_index_path,
        extra_layers={
            "TWI": twi_path,
            "SPI": spi_path,
            "RiskClass": risk_class_path,
        },
    )

    logger.info("SRTM pipeline completata. Report scritto in %s", report_path)


if __name__ == "__main__":
    main()
