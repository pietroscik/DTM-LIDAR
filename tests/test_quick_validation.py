import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

# Setup path per importare core (supporta esecuzione da root o tests/)
current_path = Path(__file__).resolve().parent
if (current_path / "config.yaml").exists():
    PROJECT_ROOT = current_path
else:
    PROJECT_ROOT = current_path.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from core import dem_processing, hydro_indices, landcover, risk_model
from core.logging_config import get_logger, setup_logging


logger = get_logger(__name__)


def _create_test_raster(path: Path, data: np.ndarray) -> None:
    height, width = data.shape
    transform = from_origin(0.0, 0.0, 1.0, 1.0)
    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": transform,
        "nodata": -9999.0,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data.astype("float32"), 1)


def run_quick_pipeline_validation() -> None:
    """
    Esegue una validazione end-to-end minima del core del modello
    usando dati sintetici (senza GEE, OSM o I/O remoto).
    """
    # Ignora warning rasterio per dati sintetici non georeferenziati
    from rasterio.errors import NotGeoreferencedWarning
    warnings.filterwarnings("ignore", category=NotGeoreferencedWarning)

    setup_logging(log_level="DEBUG")
    logger.info("=== Starting Quick Pipeline Validation ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        logger.debug("Working in temporary directory: %s", tmp)

        # 1. DEM sintetico 100x100: piano inclinato
        ny, nx = 100, 100
        x = np.linspace(0, 100, nx)
        y = np.linspace(0, 50, ny)
        xv, yv = np.meshgrid(x, y)
        dem_data = xv + yv  # quota crescente verso NE

        dem_raw = tmp / "dem_raw.tif"
        _create_test_raster(dem_raw, dem_data)

        # 2. Conditioning DEM
        dem_cond = tmp / "dem_conditioned.tif"
        dem_processing.condition_dem(dem_raw, dem_cond)

        # 3. Indici idrologici
        slope_path = tmp / "slope.tif"
        flow_acc_path = tmp / "flow_acc.tif"
        twi_path = tmp / "twi.tif"
        spi_path = tmp / "spi.tif"

        hydro_indices.compute_slope(dem_cond, slope_path)
        hydro_indices.compute_flow_accumulation(dem_cond, flow_acc_path)
        hydro_indices.compute_twi(dem_cond, flow_acc_path, twi_path)
        hydro_indices.compute_spi(flow_acc_path, slope_path, spi_path)

        # 4. Land cover sintetico: metà urbano (classe 50), metà "altro"
        lc_arr = np.zeros((ny, nx), dtype="int32")
        lc_arr[:, : nx // 2] = 50
        landcover_path = tmp / "landcover.tif"
        _create_test_raster(landcover_path, lc_arr.astype("float32"))

        runoff_path = tmp / "runoff.tif"
        landcover.map_landcover_to_runoff(
            landcover_path=landcover_path,
            mapping={50: 0.7},
            out_path=runoff_path,
            reference_raster=dem_cond,
            default_coeff=0.3,
        )

        # 5. Pioggia sintetica uniforme
        rain_arr = np.full((ny, nx), 100.0, dtype="float32")
        rain_path = tmp / "rain.tif"
        _create_test_raster(rain_path, rain_arr)

        # 6. Rischio combinato
        risk_index_path = tmp / "risk_index.tif"
        risk_class_path = tmp / "risk_class.tif"

        risk_model.compute_combined_risk_index(
            runoff_coeff_path=runoff_path,
            slope_path=slope_path,
            twi_path=twi_path,
            spi_path=spi_path,
            out_index_path=risk_index_path,
            out_class_path=risk_class_path,
            rain_raster_path=rain_path,
            rain_intensity=100.0,
        )

        with rasterio.open(risk_index_path) as src:
            risk = src.read(1, masked=True)
            rmin = float(risk.min())
            rmax = float(risk.max())
            rmean = float(risk.mean())
            rstd = float(risk.std())

        logger.info(
            "Risk index statistics: min=%.4f, max=%.4f, mean=%.4f, std=%.4f",
            rmin,
            rmax,
            rmean,
            rstd,
        )

        assert 0.0 <= rmin <= 1.0, f"Risk index min out of range: {rmin}"
        assert 0.0 <= rmax <= 1.0, f"Risk index max out of range: {rmax}"

        logger.info(
            "Quick validation PASSED: risk_index in [0, 1] on synthetic dataset."
        )
        logger.info("=== Validation Complete ===")


if __name__ == "__main__":
    run_quick_pipeline_validation()
