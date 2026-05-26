#!/usr/bin/env python
"""
Hydro-GIS CLI - Command line interface for running hydrological analysis.

Usage:
    python -m apps.cli.runner --dem input.tif --output output_dir/
"""

import argparse
import sys
from pathlib import Path

# Aggiungi la root del progetto al path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hydrogis import load_config, setup_logging, get_logger
from hydrogis.processing import (
    condition_dem,
    compute_slope,
    compute_flow_accumulation,
    compute_twi,
    compute_spi,
)
from hydrogis.models import compute_combined_risk_index


def main():
    parser = argparse.ArgumentParser(
        description="Hydro-GIS CLI - Flood risk assessment pipeline"
    )
    parser.add_argument(
        "--dem", 
        type=Path, 
        required=True, 
        help="Input DEM raster file (GeoTIFF)"
    )
    parser.add_argument(
        "--output", 
        type=Path, 
        required=True, 
        help="Output directory for results"
    )
    parser.add_argument(
        "--rain-intensity",
        type=float,
        default=100.0,
        help="Rain intensity in mm/h (default: 100.0)"
    )
    parser.add_argument(
        "--runoff",
        type=float,
        default=0.5,
        help="Runoff coefficient (default: 0.5)"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(log_level=args.log_level)
    logger = get_logger("hydrogis-cli")
    
    # Validate input
    if not args.dem.exists():
        logger.error(f"DEM file not found: {args.dem}")
        sys.exit(1)
    
    # Create output directory
    args.output.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Starting Hydro-GIS pipeline for DEM: {args.dem}")
    logger.info(f"Output directory: {args.output}")
    
    # Define output paths
    dem_cond = args.output / "dem_conditioned.tif"
    slope = args.output / "slope.tif"
    flow_acc = args.output / "flow_accumulation.tif"
    twi = args.output / "twi.tif"
    spi = args.output / "spi.tif"
    runoff_raster = args.output / "runoff.tif"
    rain_raster = args.output / "rain.tif"
    risk_index = args.output / "risk_index.tif"
    risk_class = args.output / "risk_class.tif"
    
    # Step 1: DEM Conditioning
    logger.info("Step 1: DEM conditioning (pit filling)...")
    condition_dem(args.dem, dem_cond)
    
    # Step 2: Compute Slope
    logger.info("Step 2: Computing slope...")
    compute_slope(dem_cond, slope)
    
    # Step 3: Flow Accumulation
    logger.info("Step 3: Computing flow accumulation...")
    compute_flow_accumulation(dem_cond, flow_acc)
    
    # Step 4: TWI
    logger.info("Step 4: Computing TWI (Topographic Wetness Index)...")
    compute_twi(dem_cond, flow_acc, twi)
    
    # Step 5: SPI
    logger.info("Step 5: Computing SPI (Stream Power Index)...")
    compute_spi(flow_acc, slope, spi)
    
    # Step 6: Create constant runoff and rain rasters
    from hydrogis.config_utils import read_raster, write_raster
    import numpy as np
    
    dem_data, profile, _ = read_raster(dem_cond)
    runoff_data = np.full(dem_data.shape, args.runoff, dtype="float32")
    rain_data = np.full(dem_data.shape, args.rain_intensity, dtype="float32")
    
    write_raster(runoff_raster, runoff_data, profile)
    write_raster(rain_raster, rain_data, profile)
    
    # Step 7: Combined Risk Index
    logger.info("Step 6: Computing combined risk index...")
    compute_combined_risk_index(
        runoff_coeff_path=runoff_raster,
        slope_path=slope,
        twi_path=twi,
        spi_path=spi,
        out_index_path=risk_index,
        out_class_path=risk_class,
        rain_raster_path=rain_raster,
    )
    
    logger.info("=" * 50)
    logger.info("Pipeline completed successfully!")
    logger.info(f"Results saved to: {args.output}")
    logger.info(f"  - Risk Index: {risk_index}")
    logger.info(f"  - Risk Classes: {risk_class}")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
