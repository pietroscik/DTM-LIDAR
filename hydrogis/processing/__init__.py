"""
Hydrological processing modules.

This package contains modules for DEM processing, hydrological indices computation,
and terrain analysis.
"""

from hydrogis.processing.dem import (
    fill_pits,
    condition_dem,
)
from hydrogis.processing.hydrology import (
    compute_slope,
    compute_flow_accumulation,
    compute_twi,
    compute_spi,
)

__all__ = [
    "fill_pits",
    "condition_dem",
    "compute_slope",
    "compute_flow_accumulation",
    "compute_twi",
    "compute_spi",
]
