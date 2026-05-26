from pathlib import Path
from typing import Dict, Optional

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject

from core.logging_config import get_logger
from core.utils import load_config


logger = get_logger(__name__)


def _read_landcover(path: Path):
    with rasterio.open(path) as src:
        lc = src.read(1, masked=True)
        profile = src.profile
    return lc, profile


def _write_raster(path: Path, data, profile) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = profile.copy()
    profile.update(dtype=data.dtype, count=1)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)
    return path


def _resample_to_match(
    source_path: Path,
    reference_path: Path,
):
    """
    Resample a source raster to match the grid of a reference raster.
    """
    with rasterio.open(reference_path) as ref:
        ref_profile = ref.profile
        dst_height = ref.height
        dst_width = ref.width
        dst_transform = ref.transform
        dst_crs = ref.crs

    with rasterio.open(source_path) as src:
        src_data = src.read(1)
        src_transform = src.transform
        src_crs = src.crs

    dest = np.zeros((dst_height, dst_width), dtype=src_data.dtype)

    reproject(
        source=src_data,
        destination=dest,
        src_transform=src_transform,
        src_crs=src_crs,
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        resampling=Resampling.nearest,
    )

    profile = ref_profile.copy()
    profile.update(dtype=dest.dtype, count=1, height=dst_height, width=dst_width)
    return np.ma.masked_array(dest), profile


def map_landcover_to_runoff(
    landcover_path: Path,
    mapping: Optional[Dict[int, float]],
    out_path: Path,
    reference_raster: Optional[Path] = None,
    default_coeff: float = 0.0,
) -> Path:
    """
    Map land cover classes to runoff coefficients.

    If `reference_raster` is provided, the land cover will be resampled
    to match its grid before mapping classes.
    """
    if mapping is None:
        cfg = load_config()
        mapping = cfg.get("landcover_runoff_mapping", {})
        default_coeff = cfg.get("landcover_default_coeff", default_coeff)
        # Assicura che le chiavi siano int e i valori float
        mapping = {int(k): float(v) for k, v in mapping.items()}
        if not mapping:
            logger.warning(f"Nessuna mappatura runoff trovata nel config. Uso solo default_coeff={default_coeff}.")

    if reference_raster is not None:
        lc, profile = _resample_to_match(landcover_path, reference_raster)
    else:
        lc, profile = _read_landcover(landcover_path)

    arr = lc.filled(0).astype("int32")

    # inizializza il raster di runoff con un coefficiente di default
    runoff = np.full_like(arr, default_coeff, dtype="float32")
    for cls, coeff in mapping.items():
        runoff[arr == cls] = coeff

    logger.info(f"Created runoff coefficient raster from land cover ({len(mapping)} classes mapped).")
    return _write_raster(out_path, runoff, profile)


def map_landcover_to_manning_n(
    landcover_path: Path,
    mapping: Dict[int, float],
    out_path: Path,
    reference_raster: Optional[Path] = None,
) -> Path:
    """
    Map land cover classes to Manning's n roughness coefficients.

    If `reference_raster` is provided, the land cover will be resampled
    to match its grid before mapping classes.
    """
    if reference_raster is not None:
        lc, profile = _resample_to_match(landcover_path, reference_raster)
    else:
        lc, profile = _read_landcover(landcover_path)

    arr = lc.filled(0).astype("int32")

    manning = np.zeros_like(arr, dtype="float32")
    for cls, n_val in mapping.items():
        manning[arr == cls] = n_val

    logger.info("Created Manning n raster from land cover.")
    return _write_raster(out_path, manning, profile)
