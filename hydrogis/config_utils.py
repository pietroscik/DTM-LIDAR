"""Utility functions for configuration and raster I/O."""

import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np
import rasterio
import whitebox
import yaml
from rasterio.transform import Affine

from hydrogis.logging_config import get_logger


logger = get_logger(__name__)


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Carica la configurazione da config.yaml.
    
    Args:
        config_path: Percorso opzionale al file di configurazione.
                     Se None, cerca config.yaml nella root del progetto.
    
    Returns:
        Dizionario con la configurazione caricata.
    """
    if config_path is None:
        # hydrogis/config_utils.py -> parents[1] = root del progetto
        config_path = Path(__file__).resolve().parents[1] / "config.yaml"
    
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def get_wbt() -> whitebox.WhiteboxTools:
    """
    Configura e restituisce un'istanza di WhiteboxTools.
    
    Returns:
        Istanza configurata di WhiteboxTools.
    """
    wbt = whitebox.WhiteboxTools()
    wbt.set_verbose_mode(False)

    # 1. Priorità: Variabile d'ambiente
    wbt_path = os.environ.get("WBT_PATH")
    if wbt_path:
        wbt.set_whitebox_dir(
            os.path.dirname(wbt_path) if os.path.isfile(wbt_path) else wbt_path
        )
        return wbt

    # 2. Priorità: Cerca nella root del progetto (Portable mode)
    root_path = Path(__file__).resolve().parents[1]
    local_exe = root_path / "whitebox_tools.exe"
    if local_exe.exists():
        logger.info(f"Rilevato WhiteboxTools locale in: {local_exe}")
        wbt.set_whitebox_dir(str(root_path))

    return wbt


def read_raster(path: Path) -> Tuple[np.ndarray, Dict[str, Any], Affine]:
    """
    Legge un raster e restituisce (data, profile, transform).
    
    Args:
        path: Percorso al file raster.
    
    Returns:
        Tupla contenente (array dei dati, profilo metadata, trasformazione affine).
    """
    with rasterio.open(path) as src:
        data = src.read(1, masked=True)
        profile = src.profile
        transform = src.transform
    return data, profile, transform


def write_raster(
    path: Path, 
    data: np.ndarray, 
    profile: Dict[str, Any]
) -> Path:
    """
    Scrive un array numpy su disco come GeoTIFF.
    
    Args:
        path: Percorso di output del file raster.
        data: Array numpy contenente i dati.
        profile: Profilo metadata di rasterio.
    
    Returns:
        Percorso del file scritto.
    """
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
                if np.issubdtype(dt, np.unsignedinteger):
                    profile["nodata"] = 0
                else:
                    profile["nodata"] = info.min
        elif np.issubdtype(dt, np.floating):
            if nodata == 0 or nodata is None:
                profile["nodata"] = -9999.0

    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)
    return path
