from math import cos, pi
from pathlib import Path
from typing import Optional

import rasterio

from core.logging_config import get_logger

try:
    import ee  # type: ignore
    import geemap  # type: ignore
except Exception:  # pragma: no cover - optional at runtime
    ee = None
    geemap = None

try:
    import pdal  # type: ignore
except Exception:  # pragma: no cover - optional at runtime
    pdal = None


logger = get_logger(__name__)


def ensure_output_dir(path: Path) -> None:
    """
    Create parent directory for a given output path if it does not exist.
    """
    path.parent.mkdir(parents=True, exist_ok=True)


def load_dem_from_lidar(
    lidar_path: Path,
    resolution: float,
    out_dem_tif: Path,
) -> Path:
    """
    Convert a LiDAR point cloud (.las/.laz) to a raster DTM GeoTIFF.

    This is a minimal PDAL-based pipeline placeholder. The exact PDAL JSON
    can be refined once sample data and requirements are available.
    """
    if pdal is None:
        raise RuntimeError("pdal is not available in the current environment.")

    ensure_output_dir(out_dem_tif)

    pipeline_json = [
        {
            "type": "readers.las",
            "filename": str(lidar_path),
        },
        {
            "type": "filters.range",
            "limits": "Classification[2:2]",  # ground points only placeholder
        },
        {
            "type": "filters.outlier",
            "method": "statistical",
            "mean_k": 8,
            "multiplier": 2.5,
        },
        {
            "type": "writers.gdal",
            "resolution": resolution,
            "output_type": "min",
            "gdaldriver": "GTiff",
            "filename": str(out_dem_tif),
        },
    ]

    pipeline = pdal.Pipeline(json=pipeline_json)
    logger.info("Running PDAL pipeline to create DTM: %s", out_dem_tif)
    pipeline.execute()

    return out_dem_tif


def initialize_earth_engine() -> None:
    """
    Initialize Google Earth Engine if available.
    """
    if ee is None:
        raise RuntimeError("earthengine-api (ee) is not available.")

    try:
        ee.Initialize()
    except Exception as exc:  # pragma: no cover - requires EE auth
        raise RuntimeError("Failed to initialize Earth Engine.") from exc


def build_roi_from_coords(
    coords: str,
    buffer_km: float,
):
    """
    Build an Earth Engine ROI geometry from "lon,lat" coords and a buffer.
    """
    if ee is None:
        raise RuntimeError("earthengine-api (ee) is not available.")

    try:
        lon_str, lat_str = coords.split(",")
        lon = float(lon_str.strip())
        lat = float(lat_str.strip())
    except Exception as exc:
        raise ValueError(f"Invalid coords string: {coords!r}") from exc

    # Approximate conversion of km to degrees at given latitude
    radius_m = buffer_km * 1000.0
    point = ee.Geometry.Point([lon, lat])
    roi = point.buffer(radius_m)
    return roi


def download_dem_from_gee(
    roi,
    dataset_id: str,
    out_dem_tif: Path,
    scale: float = 30.0,
) -> Path:
    """
    Download a DEM from Google Earth Engine and export it locally as GeoTIFF.

    Parameters
    ----------
    roi:
        Earth Engine geometry defining the area of interest.
    dataset_id:
        Earth Engine image ID, e.g. 'USGS/SRTMGL1_003'.
    out_dem_tif:
        Local path for the output GeoTIFF.
    scale:
        Target resolution in meters.
    """
    if ee is None or geemap is None:
        raise RuntimeError("earthengine-api/geemap are not available.")

    ensure_output_dir(out_dem_tif)

    # Alcuni DEM (es. COPERNICUS/DEM/GLO30) sono ImageCollection,
    # altri (es. USGS/SRTMGL1_003) sono Image singole.
    if dataset_id.startswith("COPERNICUS/DEM/"):
        # Filtra la collezione sull'area di interesse e crea un mosaico,
        # così da avere copertura completa sul ROI.
        collection = ee.ImageCollection(dataset_id).filterBounds(roi)
        image = collection.mosaic()
    else:
        image = ee.Image(dataset_id)

    dem = image.clip(roi)
    logger.info("Downloading DEM from GEE dataset %s", dataset_id)

    try:
        geemap.ee_export_image(
            dem,
            filename=str(out_dem_tif),
            scale=scale,
            region=roi,
            file_per_band=False,
        )
    except Exception as exc:  # pragma: no cover - network/EE-specific
        raise RuntimeError(
            f"Failed to export DEM from GEE for dataset {dataset_id!r}"
        ) from exc

    return out_dem_tif


def download_landcover_from_gee(
    roi,
    collection_id: str,
    out_tif: Path,
) -> Path:
    """
    Download a land cover raster from GEE (e.g. ESA WorldCover).
    """
    if ee is None or geemap is None:
        raise RuntimeError("earthengine-api/geemap are not available.")

    ensure_output_dir(out_tif)
    collection = ee.ImageCollection(collection_id)
    image = collection.first().clip(roi)

    logger.info("Downloading land cover from GEE collection %s", collection_id)
    geemap.ee_export_image(
        image,
        filename=str(out_tif),
        scale=10,
        region=roi,
        file_per_band=False,
    )

    return out_tif


def download_chirps_rain_from_gee(
    roi,
    collection_id: str,
    start_date: str,
    end_date: str,
    out_tif: Path,
    statistic: str = "max",
) -> Path:
    """
    Download aggregated CHIRPS rainfall (e.g. max or sum) from GEE.
    """
    if ee is None or geemap is None:
        raise RuntimeError("earthengine-api/geemap are not available.")

    ensure_output_dir(out_tif)

    coll = (
        ee.ImageCollection(collection_id)
        .filterDate(start_date, end_date)
        .select("precipitation")
    )

    if statistic == "sum":
        rain = coll.sum()
    else:
        rain = coll.max()

    rain = rain.clip(roi)

    logger.info(
        "Downloading CHIRPS rain (%s) from %s between %s and %s",
        statistic,
        collection_id,
        start_date,
        end_date,
    )

    geemap.ee_export_image(
        rain,
        filename=str(out_tif),
        scale=5000,
        region=roi,
        file_per_band=False,
    )

    return out_tif


def open_raster(path: Path):
    """
    Convenience wrapper to open a raster file with rasterio.
    """
    return rasterio.open(path)


def upload_geotiff_to_gee(
    image_path: Path,
    asset_id: str,
    overwrite: bool = False,
) -> None:
    """
    Upload a local GeoTIFF image to a Google Earth Engine asset.

    Parameters
    ----------
    image_path:
        Path to the local GeoTIFF file.
    asset_id:
        Target Earth Engine asset ID, e.g. 'users/username/dtm_avella_lidar'.
    overwrite:
        If True, replaces an existing asset with the same ID (if supported by
        the geemap helper being used).
    """
    if ee is None or geemap is None:
        raise RuntimeError("earthengine-api/geemap are not available.")

    initialize_earth_engine()

    logger.info(
        "Uploading GeoTIFF %s to Earth Engine asset %s (overwrite=%s)",
        image_path,
        asset_id,
        overwrite,
    )

    # geemap handles reading the GeoTIFF and creating the EE image
    geemap.ee_upload_image_to_asset(
        filename=str(image_path),
        asset_id=asset_id,
        overwrite=overwrite,
    )
