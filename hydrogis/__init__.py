"""
Hydro-GIS Digital Twin - Core Library

A Python package for hydrological analysis and flood risk assessment.
"""

__version__ = "1.0.0"
__author__ = "Hydro-GIS Team"

from hydrogis.config_utils import load_config, get_wbt, read_raster, write_raster
from hydrogis.logging_config import setup_logging, get_logger

__all__ = [
    "__version__",
    "load_config",
    "get_wbt",
    "read_raster",
    "write_raster",
    "setup_logging",
    "get_logger",
]
