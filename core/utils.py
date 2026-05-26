import os
from pathlib import Path

import numpy as np
import rasterio
import whitebox
import yaml

from core.logging_config import get_logger


logger = get_logger(__name__)


def load_config():
    """Carica la configurazione da config.yaml nella root del progetto."""
    # core/utils.py -> parents[1] = root del progetto
    config_path = Path(__file__).resolve().parents[1] / "config.yaml"
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}


def get_wbt():
    """Configura e restituisce un'istanza di WhiteboxTools."""
    wbt = whitebox.WhiteboxTools()
    wbt.set_verbose_mode(False)

    # 1. Priorità: Variabile d'ambiente
    wbt_path = os.environ.get("WBT_PATH")
    if wbt_path:
        # Se WBT_PATH è un file (eseguibile), usa la directory padre; altrimenti usa il path così com'è
        wbt.set_whitebox_dir(os.path.dirname(wbt_path) if os.path.isfile(wbt_path) else wbt_path)
        return wbt

    # 2. Priorità: Cerca nella root del progetto (Portable mode per Windows)
    root_path = Path(__file__).resolve().parents[1]
    local_exe = root_path / "whitebox_tools.exe"
    if local_exe.exists():
        logger.info(f"Rilevato WhiteboxTools locale in: {local_exe}")
        wbt.set_whitebox_dir(str(root_path))

    return wbt


def read_raster(path: Path):
    """Legge un raster e restituisce (data, profile, transform)."""
    with rasterio.open(path) as src:
        data = src.read(1, masked=True)
        profile = src.profile
        transform = src.transform
    return data, profile, transform


def write_raster(path: Path, data, profile) -> Path:
    """Scrive un array numpy su disco come GeoTIFF, gestendo nodata in modo sicuro."""
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = profile.copy()

    # Aggiorna dtype e band count
    profile.update(dtype=data.dtype, count=1)

    # Gestione sicura del nodata in base al tipo dati
    dt = np.dtype(data.dtype)
    nodata = profile.get("nodata", None)

    if nodata is not None:
        if np.issubdtype(dt, np.integer):
            info = np.iinfo(dt)
            if nodata < info.min or nodata > info.max:
                # Unsigned -> 0, signed -> min
                if np.issubdtype(dt, np.unsignedinteger):
                    profile["nodata"] = 0
                else:
                    profile["nodata"] = info.min
        elif np.issubdtype(dt, np.floating):
            # Standard float nodata
            if nodata == 0 or nodata is None:
                profile["nodata"] = -9999.0

    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)
    return path
