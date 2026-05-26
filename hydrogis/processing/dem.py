from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import Resampling as WarpResampling, reproject

from hydrogis.logging_config import get_logger
from hydrogis.config_utils import read_raster, write_raster, get_wbt


logger = get_logger(__name__)


def _fill_pits_whitebox(dem_path: Path, out_path: Path) -> bool:
    """Tenta il riempimento depressioni con WhiteboxTools."""
    try:
        wbt = get_wbt()
        # Usa resolve() per path assoluti, WBT a volte ha problemi con relativi
        if wbt.fill_depressions(str(dem_path.resolve()), str(out_path.resolve())) == 0:
            # Verifica che il file sia stato creato e sia un GeoTIFF valido
            if out_path.exists():
                try:
                    with rasterio.open(out_path) as src:
                        _ = src.profile  # Tenta di leggere l'header
                    return True
                except Exception as e:
                    logger.warning(f"WhiteboxTools ha generato un file corrotto: {e}")
                    try:
                        out_path.unlink()
                    except Exception:
                        pass
    except Exception as e:
        logger.warning(f"WhiteboxTools fill_depressions failed: {e}")
    return False


def _fill_pits_pysheds(dem_path: Path, out_path: Path) -> bool:
    """Tenta il riempimento depressioni con Pysheds."""
    try:
        from pysheds.grid import Grid
        grid = Grid.from_raster(str(dem_path))
        dem = grid.read_raster(str(dem_path))
        filled = grid.fill_depressions(dem)
        
        # Recuperiamo profile originale per coerenza
        _, profile, _ = read_raster(dem_path)
        write_raster(out_path, filled.astype("float32"), profile)
        return True
    except Exception as e:
        logger.warning(f"Pysheds fill_depressions failed: {e}")
        # Pulizia in caso di file parziale
        if out_path.exists():
            try:
                out_path.unlink()
            except Exception:
                pass
    return False


def fill_pits(dem_path: Path, out_path: Path) -> Path:
    """
    Riempimento depressioni idrologiche (Pit Filling).
    Tenta Whitebox -> Pysheds -> Fallback semplice (NoData handling).
    """
    # 1. Whitebox
    if _fill_pits_whitebox(dem_path, out_path):
        logger.info("Pit filling completato con WhiteboxTools.")
        return out_path
        
    # 2. Pysheds
    if _fill_pits_pysheds(dem_path, out_path):
        logger.info("Pit filling completato con Pysheds.")
        return out_path

    # 3. Fallback
    logger.warning("Backend idrologici non disponibili. Eseguo solo gestione NoData.")
    dem, profile, _ = read_raster(dem_path)
    dem = dem.astype("float32")
    filled = dem.filled(np.nan)
    return write_raster(out_path, filled, profile)


def merge_with_medium_dem(
    lidar_dem_path: Path,
    medium_dem_path: Path,
    out_path: Path,
) -> Path:
    """
    Fonde un DEM LiDAR con un DEM 'medium' (es. Copernicus).

    Regole:
    - griglia e CRS del DEM LiDAR sono presi come riferimento;
    - dove il LiDAR è valido, mantiene il LiDAR;
    - dove il LiDAR è nodata, usa il DEM medium;
    - applica comunque un floor a 0 m sulle quote risultanti.
    """
    with rasterio.open(lidar_dem_path) as src_l:
        lidar = src_l.read(1, masked=True)
        profile = src_l.profile
        dst_transform = src_l.transform
        dst_crs = src_l.crs
        dst_height = src_l.height
        dst_width = src_l.width

    with rasterio.open(medium_dem_path) as src_m:
        medium = src_m.read(1, masked=True)
        src_transform = src_m.transform
        src_crs = src_m.crs

    # Reproject medium DEM to LiDAR grid
    dest_med = np.zeros((dst_height, dst_width), dtype="float32")
    reproject(
        source=medium.filled(np.nan).astype("float32"),
        destination=dest_med,
        src_transform=src_transform,
        src_crs=src_crs,
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        resampling=WarpResampling.bilinear,
    )

    lidar_arr = lidar.filled(np.nan).astype("float32")

    # 1) Tratta come mancanti solo valori chiaramente non fisici (range fuori scala)
    #    per un DEM (es. grandi negativi o valori molto elevati tipici dei nodata).
    nodata_like = (lidar_arr <= -1000.0) | (lidar_arr >= 9000.0)
    lidar_arr[nodata_like] = np.nan

    # 2) Heuristica per coprire i “tagli” dei fogli LiDAR:
    #    celle LiDAR = 0 m ma Copernicus indica una quota ben sopra il mare
    #    sono molto probabilmente fuori copertura LiDAR, non vere depressioni.
    suspicious_zero = (
        (lidar_arr == 0.0)
        & np.isfinite(dest_med)
        & (dest_med > 5.0)
    )
    lidar_arr[suspicious_zero] = np.nan

    fused = lidar_arr.copy()

    # Dove il LiDAR è nodata/NaN (inclusi i casi sospetti), usa il DEM medium
    lidar_valid = np.isfinite(lidar_arr)
    fused[~lidar_valid] = dest_med[~lidar_valid]

    # Nessun floor a 0 m: manteniamo eventuali quote negative reali per non
    # introdurre bias in aree depresse o sotto il livello del mare.

    logger.info("Merged LiDAR DEM with medium DEM into %s", out_path)
    return write_raster(out_path, fused.astype("float32"), profile)


def condition_dem(
    dem_path: Path,
    out_path: Path,
) -> Path:
    """
    High-level DEM conditioning entry point.
    """
    return fill_pits(dem_path, out_path)
