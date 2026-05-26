import logging
from pathlib import Path
from typing import Tuple

import numpy as np


logger = logging.getLogger(__name__)


def _ensure_output_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _bbox_from_coords(coords_str: str, buffer_km: float) -> Tuple[float, float, float, float]:
    """
    Calcola un bounding box (lon/lat) a partire da coords 'lon,lat' e buffer in km.
    """
    lon_str, lat_str = coords_str.split(",")
    lon = float(lon_str.strip())
    lat = float(lat_str.strip())
    dlat = buffer_km / 111.0
    dlon = buffer_km / (111.0 * np.cos(np.deg2rad(lat)))
    west = lon - dlon
    east = lon + dlon
    south = lat - dlat
    north = lat + dlat
    return west, south, east, north


def download_lidar_wms_from_coords(
    coords_str: str,
    buffer_km: float,
    service_url: str,
    layer_name: str,
    out_tif: Path,
    srs: str = "EPSG:4326",
    resolution_m: float = 1.0,
    wms_version: str = "1.3.0",
) -> Path:
    """
    Scarica un DTM LiDAR da un servizio WMS (es. Geoportale Nazionale)
    ritagliato su coords+buffer e lo salva come GeoTIFF.

    Nota: richiede che il server supporti formato `image/tiff`.
    """
    try:
        import requests  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "La funzione WMS richiede il pacchetto 'requests'. "
            "Installa con `pip install requests`."
        ) from exc

    west, south, east, north = _bbox_from_coords(coords_str, buffer_km)

    # Calcolo approssimativo delle dimensioni in pixel.
    # Il servizio Campania dichiara MaxWidth/MaxHeight=2048, quindi clampiamo
    # per evitare errori e dimensioni eccessive.
    mean_lat_rad = np.deg2rad((north + south) / 2.0)
    est_width = max(1, int((east - west) * 111_000.0 * np.cos(mean_lat_rad) / resolution_m))
    est_height = max(1, int((north - south) * 111_000.0 / resolution_m))
    
    max_size = 2048
    width = min(est_width, max_size)
    height = min(est_height, max_size)

    params = {
        "service": "WMS",
        "version": wms_version,
        "request": "GetMap",
        "layers": layer_name,
        "styles": "",
        "format": "image/tiff",
        "transparent": "false",
        "width": width,
        "height": height,
    }

    # BBOX e CRS dipendono dalla versione WMS
    if wms_version == "1.3.0":
        params["crs"] = srs
        params["bbox"] = f"{south},{west},{north},{east}"
    else:
        params["srs"] = srs
        params["bbox"] = f"{west},{south},{east},{north}"

    if width < est_width or height < est_height:
        logger.warning(
            "La risoluzione richiesta (%s m) genera un'immagine troppo grande (%dx%d). "
            "Ridimensiono a %dx%d (limite WMS). La risoluzione effettiva sarà inferiore.",
            resolution_m, est_width, est_height, width, height
        )

    logger.info(
        "Scarico DTM LiDAR via WMS da %s (layer=%s, bbox=%s, size=%dx%d)",
        service_url,
        layer_name,
        params["bbox"],
        width,
        height,
    )

    resp = requests.get(service_url, params=params, stream=True)
    try:
        resp.raise_for_status()
    except Exception as exc:  # pragma: no cover - network specific
        raise RuntimeError(
            f"Errore nella richiesta WMS GetMap: {resp.status_code}"
        ) from exc

    # Verifica che il server stia effettivamente restituendo un GeoTIFF
    content_type = resp.headers.get("Content-Type", "")
    if "tiff" not in content_type and "tif" not in content_type:
        # Salviamo comunque il contenuto per debug, ma avvisiamo che non è un TIFF.
        snippet = resp.content[:200].decode(errors="ignore")
        raise RuntimeError(
            "Il servizio WMS non ha restituito un GeoTIFF valido "
            f"(Content-Type={content_type!r}). Risposta iniziale: {snippet!r}"
        )

    _ensure_output_dir(out_tif)
    with out_tif.open("wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    logger.info("DTM LiDAR scaricato in %s", out_tif)
    return out_tif
