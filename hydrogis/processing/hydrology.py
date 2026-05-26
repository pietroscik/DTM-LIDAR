from pathlib import Path

import numpy as np
import rasterio

from hydrogis.logging_config import get_logger
from hydrogis.config_utils import read_raster, write_raster, get_wbt, load_config


logger = get_logger(__name__)


# Backend configurabile per la flow accumulation:
# - "auto": prova pysheds, poi whitebox, infine placeholder
# - "pysheds": forza uso di pysheds (se disponibile)
# - "whitebox": forza uso di whitebox (se disponibile)
# - "placeholder": usa sempre l'approccio semplificato
_FLOW_ACC_BACKEND = "auto"

# Caricamento config
cfg = load_config()
if "flow_accumulation_backend" in cfg:
    _FLOW_ACC_BACKEND = cfg["flow_accumulation_backend"]


def compute_slope(dem_path: Path, out_path: Path) -> Path:
    dem, profile, transform = read_raster(dem_path)
    xres = transform.a
    yres = -transform.e

    dzdx = np.gradient(dem, axis=1) / xres
    dzdy = np.gradient(dem, axis=0) / yres
    slope = np.sqrt(dzdx**2 + dzdy**2)

    logger.info("Computed slope raster.")
    return write_raster(out_path, slope.astype("float32"), profile)


def compute_flow_accumulation_placeholder(
    dem_path: Path,
    out_path: Path,
) -> Path:
    """
    Placeholder for flow accumulation.

    Real implementations should rely on pysheds or similar libraries.
    """
    dem, profile, _ = read_raster(dem_path)

    # Extremely naive proxy: inverse of elevation normalized.
    arr = dem.filled(np.nan)
    arr_norm = (np.nanmax(arr) - arr) / (np.nanmax(arr) - np.nanmin(arr) + 1e-6)
    logger.info("Computed placeholder flow accumulation raster.")
    return write_raster(out_path, arr_norm.astype("float32"), profile)


def _compute_flow_accumulation_pysheds(
    dem_path: Path,
    out_path: Path,
) -> Path | None:
    """
    Calcola la flow accumulation usando pysheds, se disponibile.
    Ritorna il path di output in caso di successo, altrimenti None.
    """
    try:
        from pysheds.grid import Grid  # type: ignore
    except Exception:
        return None

    try:
        grid = Grid.from_raster(str(dem_path))
        dem = grid.read_raster(str(dem_path))

        # Classico workflow pysheds: fill -> flowdir -> accumulation
        grid.fill_depressions(dem, out_name="filled")
        grid.flowdir("filled", out_name="dir")
        # Usa schema di direzione D8 fornito da pysheds
        grid.accumulation("dir", out_name="acc", dirmap=grid.d8)

        acc = grid.view("acc", dtype="float32")
        acc = np.where(np.isfinite(acc), acc, 0.0)

        with rasterio.open(dem_path) as src:
            profile = src.profile

        logger.info("Computed flow accumulation raster using pysheds.")
        return write_raster(out_path, acc.astype("float32"), profile)
    except Exception as exc:
        logger.warning("pysheds flow accumulation failed: {}", exc)
        return None


def _compute_flow_accumulation_whitebox(
    dem_path: Path,
    out_path: Path,
) -> Path | None:
    """
    Calcola la flow accumulation usando WhiteboxTools, se disponibile.
    Ritorna il path di output in caso di successo, altrimenti None.
    """
    from tempfile import TemporaryDirectory

    try:
        with TemporaryDirectory() as tmpdir:
            from pathlib import Path as _Path

            tmpdir_path = _Path(tmpdir)
            filled = tmpdir_path / "dem_filled.tif"
            acc_path = tmpdir_path / "flow_acc.tif"

            wbt = get_wbt()
            wbt.work_dir = tmpdir

            # Fill depressions, poi D8 flow accumulation
            wbt.fill_depressions(
                dem=str(dem_path.resolve()),
                output=str(filled.resolve()),
            )
            wbt.d8_flow_accumulation(
                i=str(filled.resolve()),
                output=str(acc_path.resolve()),
                out_type="cells",
            )

            with rasterio.open(acc_path) as src:
                acc = src.read(1, masked=True)
                profile = src.profile

            logger.info("Computed flow accumulation raster using WhiteboxTools.")
            return write_raster(out_path, acc.astype("float32"), profile)
    except Exception as exc:
        logger.warning(f"WhiteboxTools flow accumulation failed: {exc}")
        return None


def compute_flow_accumulation(
    dem_path: Path,
    out_path: Path,
) -> Path:
    """
    Entry point ad alto livello per la flow accumulation.

    Logica:
    - se backend = 'pysheds': prova solo pysheds, altrimenti placeholder;
    - se backend = 'whitebox': prova solo whitebox, altrimenti placeholder;
    - se backend = 'placeholder': usa direttamente il proxy semplificato;
    - se backend = 'auto' (default): prova pysheds, poi whitebox,
      altrimenti torna al placeholder.
    """
    backend = _FLOW_ACC_BACKEND
    logger.info(f"Flow accumulation backend configurato: {backend}")

    if backend == "placeholder":
        return compute_flow_accumulation_placeholder(dem_path, out_path)

    if backend in ("pysheds", "auto"):
        res = _compute_flow_accumulation_pysheds(dem_path, out_path)
        if res is not None:
            return res
        if backend == "pysheds":
            logger.warning(
                "Flow accumulation backend impostato a 'pysheds' ma il calcolo è fallito; "
                "ricado sul placeholder."
            )

    if backend in ("whitebox", "auto"):
        res = _compute_flow_accumulation_whitebox(dem_path, out_path)
        if res is not None:
            return res
        if backend == "whitebox":
            logger.warning(
                "Flow accumulation backend impostato a 'whitebox' ma il calcolo è fallito; "
                "ricado sul placeholder."
            )

    logger.warning(
        "Flow accumulation realistica non disponibile (pysheds/whitebox assenti o falliti); "
        "uso il placeholder semplificato."
    )
    return compute_flow_accumulation_placeholder(dem_path, out_path)


def compute_twi(
    dem_path: Path,
    flow_acc_path: Path,
    out_path: Path,
) -> Path:
    dem, profile, transform = read_raster(dem_path)
    with rasterio.open(flow_acc_path) as src:
        facc = src.read(1, masked=True)

    xres = transform.a
    yres = -transform.e
    dzdx = np.gradient(dem, axis=1) / xres
    dzdy = np.gradient(dem, axis=0) / yres
    slope = np.sqrt(dzdx**2 + dzdy**2)

    contributing_area = facc + 1.0
    tan_beta = np.tan(np.arctan(slope))
    twi = np.log(contributing_area / (tan_beta + 1e-6))

    logger.info("Computed TWI raster.")
    return write_raster(out_path, twi.astype("float32"), profile)


def compute_spi(
    flow_acc_path: Path,
    slope_path: Path,
    out_path: Path,
) -> Path:
    with rasterio.open(flow_acc_path) as src:
        facc = src.read(1, masked=True)
        profile = src.profile

    with rasterio.open(slope_path) as src:
        slope = src.read(1, masked=True)

    spi = facc * slope
    logger.info("Computed SPI raster.")
    return write_raster(out_path, spi.astype("float32"), profile)
