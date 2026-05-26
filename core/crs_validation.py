from pathlib import Path
from typing import List, Optional, Tuple

import rasterio

from core.logging_config import get_logger


logger = get_logger(__name__)


def check_crs_consistency(raster_paths: List[Path]) -> Tuple[bool, Optional[str]]:
    """
    Verifica che tutti i raster nella lista condividano lo stesso CRS.

    Ritorna (True, crs) se tutti i CRS sono consistenti, altrimenti (False, None).
    """
    if not raster_paths:
        logger.warning("Empty raster list for CRS check.")
        return True, None

    crs_list = []
    for path in raster_paths:
        try:
            with rasterio.open(path) as src:
                crs = src.crs.to_string() if src.crs is not None else None
                crs_list.append((path, crs))
                logger.debug("CRS for %s: %s", path, crs)
        except Exception as exc:
            logger.error("Failed to read CRS from %s: %s", path, exc)
            return False, None

    valid_crs = [crs for _, crs in crs_list if crs is not None]
    if not valid_crs:
        logger.warning("No valid CRS found in any raster.")
        return False, None

    unique_crs = set(valid_crs)
    if len(unique_crs) == 1:
        crs_val = next(iter(unique_crs))
        logger.info("All %d rasters have consistent CRS: %s", len(raster_paths), crs_val)
        return True, crs_val

    logger.error("CRS inconsistency detected across rasters:")
    for path, crs in crs_list:
        logger.error("  %s -> %s", path, crs)
    return False, None


def validate_rainfall_raster(rain_path: Path, dem_path: Path) -> bool:
    """
    Valida che il raster di pioggia sia compatibile con il DEM in termini di
    CRS, copertura spaziale e (in modo grossolano) di risoluzione.
    """
    logger.info("Validating rainfall raster %s against DEM %s...", rain_path, dem_path)
    try:
        with rasterio.open(rain_path) as rain, rasterio.open(dem_path) as dem:
            # 1. CRS
            if rain.crs != dem.crs:
                logger.error("CRS mismatch: Rain=%s, DEM=%s", rain.crs, dem.crs)
                return False

            # 2. Coverage
            rb = rain.bounds
            db = dem.bounds
            if not (
                rb.left <= db.left
                and rb.right >= db.right
                and rb.bottom <= db.bottom
                and rb.top >= db.top
            ):
                logger.warning(
                    "Rainfall raster doesn't fully cover DEM area.\n"
                    "  Rain bounds: %s\n  DEM bounds: %s",
                    rb,
                    db,
                )

            # 3. Risoluzione (warning se molto diversa)
            rain_res = rain.res
            dem_res = dem.res
            try:
                ratio_x = max(rain_res[0], dem_res[0]) / max(1e-6, min(rain_res[0], dem_res[0]))
                ratio_y = max(rain_res[1], dem_res[1]) / max(1e-6, min(rain_res[1], dem_res[1]))
                if ratio_x > 5 or ratio_y > 5:
                    logger.warning(
                        "Significant resolution difference: Rain=%s, DEM=%s",
                        rain_res,
                        dem_res,
                    )
            except Exception:
                # In caso di problemi nel calcolo, non blocchiamo la validazione.
                pass

            logger.info("Rainfall raster validation passed.")
            return True
    except Exception as exc:
        logger.error("Rainfall validation failed: %s", exc)
        return False


def ensure_same_crs(raster_paths: List[Path]) -> bool:
    """
    Controlla che tutti i raster condividano lo stesso CRS.
    Non tenta alcuna riproiezione, ma fornisce un warning dettagliato.
    """
    consistent, crs_val = check_crs_consistency(raster_paths)
    if not consistent:
        logger.error(
            "CRS validation failed for input rasters. "
            "Il modello continuerà, ma i risultati potrebbero non essere affidabili."
        )
        return False
    logger.debug("CRS validation succeeded with CRS: %s", crs_val)
    return True

