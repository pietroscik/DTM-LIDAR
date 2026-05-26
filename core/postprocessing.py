from pathlib import Path

import numpy as np
import rasterio

from core.logging_config import get_logger


logger = get_logger(__name__)


# Parametri di post-processing SPI caricabili da config.yaml
_SPI_POSTPROC = {
    "percentile": 95.0,
    "buffer_meters": 30.0,
    "median_filter_size": 3,
}

try:  # pragma: no cover - dipendenza opzionale
    import yaml  # type: ignore
    from pathlib import Path as _Path

    cfg_path = _Path(__file__).resolve().parents[1] / "config.yaml"
    if cfg_path.exists():
        with cfg_path.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        sp = cfg.get("spi_postprocessing", {})
        if isinstance(sp, dict):
            if "percentile" in sp:
                _SPI_POSTPROC["percentile"] = float(sp["percentile"])
            if "buffer_meters" in sp:
                _SPI_POSTPROC["buffer_meters"] = float(sp["buffer_meters"])
            if "median_filter_size" in sp:
                _SPI_POSTPROC["median_filter_size"] = int(sp["median_filter_size"])
except Exception:
    pass


def create_optimized_risk_from_spi(
    spi_path: Path,
    out_risk_path: Path,
    percentile: float = _SPI_POSTPROC["percentile"],
    buffer_meters: float = _SPI_POSTPROC["buffer_meters"],
    median_filter_size: int = _SPI_POSTPROC["median_filter_size"],
) -> Path:
    """
    Post-process SPI raster to create a cleaner, thresholded risk map.

    Steps:
    - Apply a 3x3 median filter to reduce salt-and-pepper noise.
    - Compute the given percentile on filtered SPI (ignoring nodata).
    - Mark as "at risk" only pixels above that percentile.
    - Optionally apply a buffer (morphological dilation) of N pixels
      around the risk zones to approximate a safety distance.
    - Save a binary mask (0/1) as GeoTIFF.
    """
    try:
        from scipy.ndimage import median_filter, binary_dilation  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "scipy is required for median filtering and buffering. "
            "Install it with `pip install scipy`."
        ) from exc

    with rasterio.open(spi_path) as src:
        spi = src.read(1, masked=True)
        profile = src.profile
        # risoluzione effettiva del raster (attenzione al segno su y)
        res_x, res_y = src.res
        pixel_size_x = abs(res_x)
        pixel_size_y = abs(res_y)

    # Calcola automaticamente il buffer in pixel a partire da un buffer
    # fisico (metri) e dalla risoluzione del raster SPI.
    # Questo rende il modello coerente tra SRTM/Copernicus (~30 m) e LiDAR (1–2 m).
    pixel_size = (
        (pixel_size_x + pixel_size_y) / 2.0 if (pixel_size_x > 0 and pixel_size_y > 0) else pixel_size_x or pixel_size_y
    )
    if pixel_size <= 0:
        buffer_pixels = 1
    else:
        buffer_pixels = max(1, int(round(buffer_meters / pixel_size)))

    spi_arr = spi.filled(np.nan).astype("float32")
    logger.info("Applying %dx%d median filter to SPI raster.", median_filter_size, median_filter_size)
    filtered = median_filter(spi_arr, size=median_filter_size)

    finite_mask = np.isfinite(filtered)
    if not np.any(finite_mask):
        logger.warning(
            "No valid SPI values found for percentile computation; "
            "creating an empty optimized risk mask."
        )
        risk_mask = np.zeros_like(filtered, dtype="uint8")

        out_risk_path.parent.mkdir(parents=True, exist_ok=True)
        profile = profile.copy()
        profile.update(dtype="uint8", count=1, nodata=0)

        with rasterio.open(out_risk_path, "w", **profile) as dst:
            dst.write(risk_mask, 1)

        logger.info(
            "Written empty optimized risk mask to %s due to invalid SPI.",
            out_risk_path,
        )
        return out_risk_path

    thresh = float(np.nanpercentile(filtered[finite_mask], percentile))
    logger.info("SPI %s-th percentile threshold: %.3f", percentile, thresh)

    risk_mask = np.zeros_like(filtered, dtype="uint8")
    risk_mask[(filtered > thresh) & finite_mask] = 1

    # Apply buffer (dilation) of N pixels to expand risk zones
    if buffer_pixels > 0:
        logger.info("Applying %d-pixel buffer (dilation) around risk zones.", buffer_pixels)
        risk_mask = binary_dilation(
            risk_mask.astype(bool),
            iterations=buffer_pixels,
        ).astype("uint8")

    # Prepare profile for uint8 mask
    out_risk_path.parent.mkdir(parents=True, exist_ok=True)
    profile = profile.copy()
    profile.update(dtype="uint8", count=1, nodata=0)

    with rasterio.open(out_risk_path, "w", **profile) as dst:
        dst.write(risk_mask, 1)

    logger.info("Written optimized (buffered) risk mask to %s", out_risk_path)
    return out_risk_path


def plot_risk_overlay(
    dem_path: Path,
    risk_mask_path: Path,
    out_png_path: Path,
) -> Path:
    """
    Create a visual overlay: DEM in grayscale, risk mask in red with alpha.
    """
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "matplotlib is required for plotting. "
            "Install it with `pip install matplotlib`."
        ) from exc

    with rasterio.open(dem_path) as src:
        dem = src.read(1, masked=True).filled(np.nan)

    with rasterio.open(risk_mask_path) as src:
        risk = src.read(1, masked=True).filled(0)

    vmin = np.nanmin(dem)
    vmax = np.nanmax(dem)

    fig, ax = plt.subplots(figsize=(8, 6))
    im_dem = ax.imshow(dem, cmap="gray", vmin=vmin, vmax=vmax)
    ax.imshow(
        np.where(risk > 0, 1, 0),
        cmap="Reds",
        alpha=0.6,
        vmin=0,
        vmax=1,
    )
    ax.set_title("DEM + Optimized Risk Map (SPI-based)")
    ax.set_axis_off()

    out_png_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_png_path, dpi=200)
    plt.close(fig)

    logger.info("Written DEM+Risk overlay image to %s", out_png_path)
    return out_png_path
