#!/usr/bin/env python
"""
Hydro-GIS CLI - Command line interface for running hydrological analysis.

Usage:
    python -m apps.cli.runner --dem input.tif --output output_dir/
"""

import argparse
import sys
import time
from pathlib import Path

# Aggiungi la root del progetto al path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np

from hydrogis import load_config, setup_logging, get_logger
from hydrogis.processing import (
    condition_dem,
    compute_slope,
    compute_flow_accumulation,
    compute_twi,
    compute_spi,
)
from hydrogis.models import compute_combined_risk_index
from hydrogis.config_utils import read_raster, write_raster


def validate_args(args, logger):
    """Valida gli argomenti forniti dall'utente."""
    if not args.dem.exists():
        logger.error(f"DEM file not found: {args.dem}")
        return False
    
    if args.rain_intensity <= 0:
        logger.error("Rain intensity must be a positive value")
        return False
    
    if not 0 <= args.runoff <= 1:
        logger.error("Runoff coefficient must be between 0 and 1")
        return False
    
    return True


def create_output_paths(output_dir: Path) -> dict:
    """Crea un dizionario con tutti i path di output."""
    return {
        "dem_cond": output_dir / "dem_conditioned.tif",
        "slope": output_dir / "slope.tif",
        "flow_acc": output_dir / "flow_accumulation.tif",
        "twi": output_dir / "twi.tif",
        "spi": output_dir / "spi.tif",
        "runoff": output_dir / "runoff.tif",
        "rain": output_dir / "rain.tif",
        "risk_index": output_dir / "risk_index.tif",
        "risk_class": output_dir / "risk_class.tif",
    }


def run_pipeline(args, paths: dict, logger) -> bool:
    """Esegue la pipeline di elaborazione idrologica."""
    steps = [
        ("DEM conditioning (pit filling)", lambda: condition_dem(args.dem, paths["dem_cond"])),
        ("Computing slope", lambda: compute_slope(paths["dem_cond"], paths["slope"])),
        ("Computing flow accumulation", lambda: compute_flow_accumulation(paths["dem_cond"], paths["flow_acc"])),
        ("Computing TWI (Topographic Wetness Index)", lambda: compute_twi(paths["dem_cond"], paths["flow_acc"], paths["twi"])),
        ("Computing SPI (Stream Power Index)", lambda: compute_spi(paths["flow_acc"], paths["slope"], paths["spi"])),
        ("Creating runoff and rain rasters", lambda: create_constant_rasters(args, paths, logger)),
        ("Computing combined risk index", lambda: compute_combined_risk_index(
            runoff_coeff_path=paths["runoff"],
            slope_path=paths["slope"],
            twi_path=paths["twi"],
            spi_path=paths["spi"],
            out_index_path=paths["risk_index"],
            out_class_path=paths["risk_class"],
            rain_raster_path=paths["rain"],
        )),
    ]
    
    total_steps = len(steps)
    
    for i, (description, step_func) in enumerate(steps, 1):
        logger.info(f"Step {i}/{total_steps}: {description}...")
        start_time = time.time()
        
        try:
            step_func()
            elapsed = time.time() - start_time
            logger.info(f"  ✓ Completed in {elapsed:.2f}s")
        except Exception as e:
            logger.error(f"  ✗ Failed at step {i}: {str(e)}")
            return False
    
    return True


def create_constant_rasters(args, paths: dict, logger):
    """Crea raster costanti per runoff e pioggia."""
    dem_data, profile, _ = read_raster(paths["dem_cond"])
    
    runoff_data = np.full(dem_data.shape, args.runoff, dtype="float32")
    rain_data = np.full(dem_data.shape, args.rain_intensity, dtype="float32")
    
    write_raster(paths["runoff"], runoff_data, profile)
    write_raster(paths["rain"], rain_data, profile)
    
    logger.debug(f"Created constant rasters: runoff={args.runoff}, rain={args.rain_intensity} mm/h")


def print_summary(args, paths: dict, logger, total_time: float):
    """Stampa un riepilogo finale dell'elaborazione."""
    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETED SUCCESSFULLY")
    logger.info("=" * 60)
    logger.info(f"Input DEM: {args.dem}")
    logger.info(f"Output directory: {args.output}")
    logger.info(f"Total processing time: {total_time:.2f}s")
    logger.info("-" * 60)
    logger.info("Generated files:")
    
    for key, path in paths.items():
        if path.exists():
            size_mb = path.stat().st_size / (1024 * 1024)
            logger.info(f"  ✓ {key:<20} : {path.name:<30} ({size_mb:.2f} MB)")
        else:
            logger.warning(f"  ✗ {key:<20} : {path.name} (missing)")
    
    logger.info("-" * 60)
    logger.info("Key outputs:")
    logger.info(f"  • Risk Index: {paths['risk_index']}")
    logger.info(f"  • Risk Classes: {paths['risk_class']}")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Hydro-GIS CLI - Flood risk assessment pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m apps.cli.runner --dem dem.tif --output results/
    python -m apps.cli.runner --dem dem.tif --output results/ --rain-intensity 150 --runoff 0.7
    python -m apps.cli.runner --dem dem.tif --output results/ --log-level DEBUG
        """
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
        help="Runoff coefficient (default: 0.5, range: 0-1)"
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
    if not validate_args(args, logger):
        sys.exit(1)
    
    # Create output directory
    args.output.mkdir(parents=True, exist_ok=True)
    
    # Create output paths
    paths = create_output_paths(args.output)
    
    logger.info("╔" + "═" * 58 + "╗")
    logger.info("║" + " " * 15 + "Hydro-GIS Pipeline Started" + " " * 15 + "║")
    logger.info("╚" + "═" * 58 + "╝")
    logger.info(f"DEM: {args.dem}")
    logger.info(f"Output: {args.output}")
    logger.info(f"Parameters: rain={args.rain_intensity} mm/h, runoff={args.runoff}")
    
    # Execute pipeline
    start_time = time.time()
    
    try:
        success = run_pipeline(args, paths, logger)
        
        if not success:
            logger.error("Pipeline failed. Check logs for details.")
            sys.exit(1)
        
        total_time = time.time() - start_time
        print_summary(args, paths, logger, total_time)
        
    except KeyboardInterrupt:
        logger.warning("\nPipeline interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.exception(f"Unexpected error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
