import json
from pathlib import Path
from typing import Dict, List

import numpy as np
import rasterio

from core.logging_config import get_logger


logger = get_logger(__name__)


def _raster_stats(path: Path) -> Dict[str, float]:
    with rasterio.open(path) as src:
        data = src.read(1, masked=True)
    arr = data.compressed()
    return {
        "min": float(arr.min()) if arr.size else float("nan"),
        "max": float(arr.max()) if arr.size else float("nan"),
        "mean": float(arr.mean()) if arr.size else float("nan"),
        "std": float(arr.std()) if arr.size else float("nan"),
    }


def write_report_markdown(
    out_path: Path,
    area_description: str,
    dem_path: Path,
    risk_index_path: Path,
    extra_layers: Dict[str, Path],
) -> Path:
    """
    Generate a minimal Markdown report summarizing key outputs.
    """
    dem_stats = _raster_stats(dem_path)
    risk_stats = _raster_stats(risk_index_path)

    extra_stats = {
        name: _raster_stats(path) for name, path in extra_layers.items()
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines: List[str] = []
    lines.append(f"# Analisi Rischio Idrogeologico - {area_description}\n")
    lines.append("## Dati DEM\n")
    lines.append(f"- Min: {dem_stats['min']:.3f}")
    lines.append(f"- Max: {dem_stats['max']:.3f}")
    lines.append(f"- Mean: {dem_stats['mean']:.3f}")
    lines.append(f"- Std: {dem_stats['std']:.3f}\n")

    lines.append("## Indice di Rischio\n")
    lines.append(f"- Min: {risk_stats['min']:.3f}")
    lines.append(f"- Max: {risk_stats['max']:.3f}")
    lines.append(f"- Mean: {risk_stats['mean']:.3f}")
    lines.append(f"- Std: {risk_stats['std']:.3f}\n")

    if extra_stats:
        lines.append("## Layer Aggiuntivi\n")
        for name, stats in extra_stats.items():
            lines.append(f"### {name}")
            lines.append(f"- Min: {stats['min']:.3f}")
            lines.append(f"- Max: {stats['max']:.3f}")
            lines.append(f"- Mean: {stats['mean']:.3f}")
            lines.append(f"- Std: {stats['std']:.3f}\n")

    with out_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info("Written Markdown report to %s", out_path)
    return out_path
