"""
Risk modeling module.

This module contains functions for computing flood risk indices
based on hydrological and terrain parameters.
"""

from pathlib import Path
from typing import Optional

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject

from hydrogis.logging_config import get_logger
from hydrogis.config_utils import read_raster, write_raster, load_config


logger = get_logger(__name__)


# Carica parametri di calibrazione dal file config.yaml
_RISK_WEIGHTS = {
    "twi": 0.4,
    "spi": 0.3,
    "runoff": 0.2,
    "slope": 0.1,
}
_RISK_THRESHOLDS = {
    "low": 0.33,
    "high": 0.66,
}

# Caricamento config
cfg = load_config()
rw = cfg.get("risk_weights", {})
if isinstance(rw, dict):
    _RISK_WEIGHTS.update({k: float(v) for k, v in rw.items() if k in _RISK_WEIGHTS})
rt = cfg.get("risk_thresholds", {})
if isinstance(rt, dict):
    _RISK_THRESHOLDS.update({k: float(v) for k, v in rt.items() if k in _RISK_THRESHOLDS})


def compute_simple_risk_index(
    runoff_coeff_path: Path,
    slope_path: Path,
    out_path: Path,
    rain_intensity: float = 100.0,
    rain_raster_path: Optional[Path] = None,
    max_value: Optional[float] = None,
) -> Path:
    """
    Compute a basic flood risk index raster.

    Risk = (Rain * RunoffCoeff) / (Slope + 1)

    If `rain_raster_path` is provided, it will be used as a spatially
    variable rain field (e.g. CHIRPS). Otherwise a uniform intensity is used.
    
    Args:
        runoff_coeff_path: Path to runoff coefficient raster.
        slope_path: Path to slope raster.
        out_path: Output path for risk index raster.
        rain_intensity: Uniform rain intensity value (default: 100.0 mm/h).
        rain_raster_path: Optional path to spatially variable rain raster.
        max_value: Optional maximum value to clip the risk index.
    
    Returns:
        Path to the output risk index raster.
    """
    runoff, profile, _ = read_raster(runoff_coeff_path)
    with rasterio.open(slope_path) as src:
        slope = src.read(1, masked=True)

    if rain_raster_path is not None:
        rain, rain_profile, _ = read_raster(rain_raster_path)
        rain_arr = rain.filled(np.nan)

        # Resample rain to match runoff grid if needed
        if rain_arr.shape != runoff.shape:
            dest = np.zeros_like(runoff, dtype="float32")
            with rasterio.open(rain_raster_path) as src:
                reproject(
                    source=rain_arr.astype("float32"),
                    destination=dest,
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=profile["transform"],
                    dst_crs=profile["crs"],
                    resampling=Resampling.bilinear,
                )
            rain_arr = dest

        rain_factor = rain_arr
    else:
        rain_factor = rain_intensity

    risk = (rain_factor * runoff) / (slope + 1.0)

    if max_value is not None:
        risk = np.clip(risk, 0, max_value)

    logger.info("Computed basic flood risk index raster.")
    return write_raster(out_path, risk.astype("float32"), profile)


def _normalize(arr: np.ndarray) -> np.ndarray:
    """Normalize array to [0, 1] range."""
    arr_f = arr.astype("float32")
    finite = np.isfinite(arr_f)
    if not np.any(finite):
        return np.zeros_like(arr_f, dtype="float32")
    min_val = np.nanmin(arr_f[finite])
    max_val = np.nanmax(arr_f[finite])
    if max_val - min_val < 1e-6:
        return np.zeros_like(arr_f, dtype="float32")
    return (arr_f - min_val) / (max_val - min_val)


def compute_combined_risk_index(
    runoff_coeff_path: Path,
    slope_path: Path,
    twi_path: Path,
    spi_path: Path,
    out_index_path: Path,
    out_class_path: Path,
    rain_raster_path: Optional[Path] = None,
    rain_intensity: float = 100.0,
    low_threshold: Optional[float] = None,
    high_threshold: Optional[float] = None,
) -> None:
    """
    Compute a combined flood risk index using TWI, SPI, runoff, slope and rain.

    Conceptual formula:
      - Normalize TWI, SPI, slope and runoff.
      - RiskCore = 0.4*TWI_norm + 0.3*SPI_norm + 0.2*Runoff_norm
                   + 0.1*(1 - Slope_norm)
      - Risk = RiskCore * Rain_norm

    Then Risk is re-normalized to [0,1] and discretized in classes:
      1 = Basso, 2 = Medio, 3 = Alto
      
    Args:
        runoff_coeff_path: Path to runoff coefficient raster.
        slope_path: Path to slope raster.
        twi_path: Path to TWI raster.
        spi_path: Path to SPI raster.
        out_index_path: Output path for continuous risk index.
        out_class_path: Output path for classified risk (1,2,3).
        rain_raster_path: Optional path to rain raster.
        rain_intensity: Uniform rain intensity value.
        low_threshold: Threshold for low risk class (default from config).
        high_threshold: Threshold for high risk class (default from config).
    """
    runoff, profile, _ = read_raster(runoff_coeff_path)
    with rasterio.open(slope_path) as src:
        slope = src.read(1, masked=True)
    with rasterio.open(twi_path) as src:
        twi = src.read(1, masked=True)
    with rasterio.open(spi_path) as src:
        spi = src.read(1, masked=True)

    runoff_arr = runoff.filled(np.nan)
    slope_arr = slope.filled(np.nan)
    twi_arr = twi.filled(np.nan)
    spi_arr = spi.filled(np.nan)

    runoff_norm = _normalize(runoff_arr)
    slope_norm = _normalize(slope_arr)
    twi_norm = _normalize(twi_arr)
    spi_norm = _normalize(spi_arr)

    # High risk for low slopes -> 1 - slope_norm
    slope_factor = 1.0 - slope_norm

    # Pesi configurabili via config.yaml (risk_weights)
    tw = float(_RISK_WEIGHTS["twi"])
    sp = float(_RISK_WEIGHTS["spi"])
    ro = float(_RISK_WEIGHTS["runoff"])
    sl = float(_RISK_WEIGHTS["slope"])

    core = tw * twi_norm + sp * spi_norm + ro * runoff_norm + sl * slope_factor

    if rain_raster_path is not None:
        rain, rain_profile, _ = read_raster(rain_raster_path)
        rain_arr = rain.filled(np.nan)

        # Resample rain to match runoff grid if needed
        if rain_arr.shape != runoff_arr.shape:
            dest = np.zeros_like(runoff_arr, dtype="float32")
            with rasterio.open(rain_raster_path) as src:
                reproject(
                    source=rain_arr.astype("float32"),
                    destination=dest,
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=profile["transform"],
                    dst_crs=profile["crs"],
                    resampling=Resampling.bilinear,
                )
            rain_arr = dest

        rain_norm = _normalize(rain_arr)
    else:
        rain_norm = np.full_like(core, rain_intensity, dtype="float32")
        rain_norm = _normalize(rain_norm)

    risk = core * rain_norm
    risk_norm = _normalize(risk)

    # Soglie configurabili via config.yaml (risk_thresholds)
    if low_threshold is None:
        low_threshold = float(_RISK_THRESHOLDS["low"])
    if high_threshold is None:
        high_threshold = float(_RISK_THRESHOLDS["high"])

    # Create classes 1,2,3 based on thresholds
    risk_class = np.zeros_like(risk_norm, dtype="uint8")
    risk_class[(risk_norm > 0) & (risk_norm <= low_threshold)] = 1
    risk_class[(risk_norm > low_threshold) & (risk_norm <= high_threshold)] = 2
    risk_class[risk_norm > high_threshold] = 3

    write_raster(out_index_path, risk_norm.astype("float32"), profile)
    write_raster(out_class_path, risk_class, profile)

    logger.info(
        "Computed combined flood risk index and class rasters "
        "with thresholds low=%.2f, high=%.2f",
        low_threshold,
        high_threshold,
    )
