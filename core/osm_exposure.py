from pathlib import Path
from typing import Tuple

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.mask import mask

from core.logging_config import get_logger

try:
    import geopandas as gpd  # type: ignore
    from shapely.geometry import box  # type: ignore
except Exception:  # pragma: no cover - optional at runtime
    gpd = None
    box = None

try:
    import osmnx as ox  # type: ignore
except Exception:  # pragma: no cover - optional at runtime
    ox = None

try:
    import folium  # type: ignore
except Exception:  # pragma: no cover - optional at runtime
    folium = None


logger = get_logger(__name__)


def _require_geo_stack() -> None:
    if gpd is None or box is None or ox is None:
        raise RuntimeError(
            "OSM exposure requires osmnx, geopandas e shapely. "
            "Installa i pacchetti con: pip install osmnx geopandas shapely"
        )


def _bbox_from_coords(coords_str: str, buffer_km: float) -> Tuple[float, float, float, float]:
    lon_str, lat_str = coords_str.split(",")
    lon = float(lon_str.strip())
    lat = float(lat_str.strip())
    # Approximate degrees from km
    dlat = buffer_km / 111.0
    dlon = buffer_km / (111.0 * np.cos(np.deg2rad(lat)))
    north = lat + dlat
    south = lat - dlat
    east = lon + dlon
    west = lon - dlon
    return north, south, east, west


def download_osm_rivers_bbox(coords_str: str, buffer_km: float) -> "gpd.GeoDataFrame":
    """
    Scarica i corsi d'acqua OSM (waterway) per il bounding box definito da coords+buffer.
    """
    _require_geo_stack()
    north, south, east, west = _bbox_from_coords(coords_str, buffer_km)
    tags = {"waterway": True}
    logger.info(
        "Scarico corsi d'acqua OSM (waterway) per bbox N=%.4f S=%.4f E=%.4f W=%.4f",
        north,
        south,
        east,
        west,
    )
    # Usa features_from_polygon per compatibilità con versioni di osmnx
    bbox_poly = box(west, south, east, north)
    gdf = ox.features_from_polygon(bbox_poly, tags)
    if gdf.empty:
        logger.warning("Nessun corso d'acqua trovato in OSM per il bounding box indicato.")
    return gdf


def download_osm_buildings_bbox(coords_str: str, buffer_km: float) -> "gpd.GeoDataFrame":
    """
    Scarica i poligoni degli edifici OSM (building=*) per il bounding box definito da coords+buffer.
    """
    _require_geo_stack()
    north, south, east, west = _bbox_from_coords(coords_str, buffer_km)
    tags = {"building": True}
    logger.info(
        "Scarico edifici OSM (building) per bbox N=%.4f S=%.4f E=%.4f W=%.4f",
        north,
        south,
        east,
        west,
    )
    bbox_poly = box(west, south, east, north)
    gdf = ox.features_from_polygon(bbox_poly, tags)
    if gdf.empty:
        logger.warning("Nessun edificio trovato in OSM per il bounding box indicato.")
    return gdf


def download_osm_buildings_from_bbox(north: float, south: float, east: float, west: float) -> "gpd.GeoDataFrame":
    """
    Scarica gli edifici OSM per un bounding box specifico (lat/lon).
    """
    _require_geo_stack()
    tags = {"building": True}
    logger.info(
        "Scarico edifici OSM (building) per bbox N=%.4f S=%.4f E=%.4f W=%.4f",
        north, south, east, west,
    )
    bbox_poly = box(west, south, east, north)
    try:
        gdf = ox.features_from_polygon(bbox_poly, tags)
        if gdf.empty:
            logger.warning("Nessun edificio trovato in OSM.")
        return gdf
    except Exception as e:
        logger.error(f"Errore download OSM: {e}")
        return gpd.GeoDataFrame()


def burn_in_rivers_on_dem(
    dem_path: Path,
    rivers_gdf: "gpd.GeoDataFrame",
    burn_depth: float = 5.0,
    out_dem_path: Path | None = None,
) -> Path:
    """
    Applica un 'burn-in' di burn_depth metri lungo i corsi d'acqua sul DEM.
    """
    if gpd is None:
        raise RuntimeError("geopandas è richiesto per il burn-in dei fiumi.")

    out_dem_path = out_dem_path or dem_path

    with rasterio.open(dem_path) as src:
        dem = src.read(1, masked=True)
        profile = src.profile
        dem_crs = src.crs
        dem_transform = src.transform
        shape = src.shape

    if rivers_gdf.empty:
        logger.warning("Rivers GeoDataFrame è vuoto; nessun burn-in applicato.")
        return out_dem_path

    rivers_proj = rivers_gdf.to_crs(dem_crs)
    # Filtra solo geometrie lineari/poligonali valide
    geom_list = [geom for geom in rivers_proj.geometry if geom is not None and not geom.is_empty]
    if not geom_list:
        logger.warning("Nessuna geometria valida per il burn-in trovata.")
        return out_dem_path

    logger.info("Rasterizzo i corsi d'acqua per il burn-in.")
    river_mask = rasterize(
        [(geom, 1) for geom in geom_list],
        out_shape=shape,
        transform=dem_transform,
        fill=0,
        dtype="uint8",
    )

    # Lavoriamo in float32 per poter usare NaN come fill value anche se il DEM è int16
    dem = dem.astype("float32")
    dem_arr = dem.filled(np.nan)
    dem_arr[river_mask == 1] -= burn_depth

    out_profile = profile.copy()
    out_profile.update(dtype="float32", count=1)

    out_dem_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out_dem_path, "w", **out_profile) as dst:
        dst.write(dem_arr, 1)

    logger.info("Burn-in applicato e DEM scritto in %s", out_dem_path)
    return out_dem_path


def buildings_risk_to_geojson(
    buildings_gdf: "gpd.GeoDataFrame",
    risk_raster_path: Path,
    out_geojson_path: Path,
    top_percent: float = 10.0,
) -> Path:
    """
    Calcola il valore massimo di rischio sotto ogni edificio e
    esporta solo gli edifici nel top 'top_percent'%% in GeoJSON.
    """
    if gpd is None:
        raise RuntimeError("geopandas è richiesto per l'esposizione edifici.")

    if buildings_gdf.empty:
        logger.warning("Nessun edificio OSM per il bounding box; GeoJSON non creato.")
        return out_geojson_path

    with rasterio.open(risk_raster_path) as src:
        risk_profile = src.profile
        risk_crs = src.crs

        # Reproject buildings to raster CRS
        buildings_proj = buildings_gdf.to_crs(risk_crs)
        max_vals = []
        logger.info("Calcolo rischio massimo per ogni edificio (può richiedere tempo)...")
        for geom in buildings_proj.geometry:
            if geom is None or geom.is_empty:
                max_vals.append(np.nan)
                continue
            try:
                out_image, _ = mask(src, [geom], crop=True)
                arr = out_image[0]
                nodata = risk_profile.get("nodata", None)
                if nodata is not None:
                    arr = np.ma.masked_equal(arr, nodata)
                else:
                    arr = np.ma.masked_invalid(arr)
                if arr.count() == 0:
                    max_vals.append(np.nan)
                else:
                    max_vals.append(float(arr.max()))
            except Exception:
                max_vals.append(np.nan)

    buildings_proj = buildings_proj.copy()
    buildings_proj["risk_max"] = max_vals

    vals = buildings_proj["risk_max"].replace([np.inf, -np.inf], np.nan).dropna()
    if vals.empty:
        logger.warning("Nessun valore di rischio valido sugli edifici; GeoJSON non creato.")
        return out_geojson_path

    threshold = float(np.nanpercentile(vals, 100 - top_percent))
    logger.info(
        "Soglia per edifici ad alto rischio (top %.1f%%): %.3f",
        top_percent,
        threshold,
    )

    high_risk = buildings_proj[buildings_proj["risk_max"] >= threshold]
    if high_risk.empty:
        logger.warning("Nessun edificio supera la soglia di alto rischio; GeoJSON vuoto.")

    out_geojson_path.parent.mkdir(parents=True, exist_ok=True)
    high_risk.to_file(out_geojson_path, driver="GeoJSON")
    logger.info("GeoJSON edifici ad alto rischio scritto in %s", out_geojson_path)
    return out_geojson_path


def buildings_in_risk_mask(
    buildings_gdf: "gpd.GeoDataFrame",
    risk_mask_path: Path,
) -> "gpd.GeoDataFrame":
    """
    Seleziona gli edifici che intersecano celle con rischio > 0
    nella mappa di rischio binaria (es. Risk_Map_Optimized).
    """
    if gpd is None:
        raise RuntimeError("geopandas è richiesto per l'esposizione edifici.")

    if buildings_gdf.empty:
        logger.warning("Nessun edificio OSM per il bounding box.")
        return buildings_gdf

    with rasterio.open(risk_mask_path) as src:
        mask_profile = src.profile
        mask_crs = src.crs

        buildings_proj = buildings_gdf.to_crs(mask_crs)
        risk_flags = []
        logger.info("Verifico intersezione edifici con la mappa di rischio binaria...")
        for geom in buildings_proj.geometry:
            if geom is None or geom.is_empty:
                risk_flags.append(False)
                continue
            try:
                out_image, _ = mask(src, [geom], crop=True)
                arr = out_image[0]
                nodata = mask_profile.get("nodata", None)
                if nodata is not None:
                    arr = np.ma.masked_equal(arr, nodata)
                else:
                    arr = np.ma.masked_invalid(arr)
                risk_flags.append(bool((arr > 0).any()))
            except Exception:
                risk_flags.append(False)

    buildings_proj = buildings_proj.copy()
    buildings_proj["at_risk"] = risk_flags
    return buildings_proj[buildings_proj["at_risk"]]


def export_buildings_csv(
    buildings_gdf: "gpd.GeoDataFrame",
    out_csv_path: Path,
) -> Path:
    """
    Esporta un CSV con le coordinate (lon, lat) dei centroidi
    degli edifici forniti.
    """
    if gpd is None:
        raise RuntimeError("geopandas è richiesto per l'esportazione CSV edifici.")

    if buildings_gdf.empty:
        logger.warning("Nessun edificio da esportare in CSV.")
        return out_csv_path

    records = []
    # pandas/GeoPandas moderni usano .items() invece di .iteritems()
    for idx, geom in buildings_gdf.geometry.items():
        if geom is None or geom.is_empty:
            continue
        centroid = geom.centroid
        records.append(
            {
                "id": idx,
                "lon": float(centroid.x),
                "lat": float(centroid.y),
            }
        )

    if not records:
        logger.warning("Nessun centroide valido per edifici; CSV vuoto.")
        return out_csv_path

    import csv

    out_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with out_csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "lon", "lat"])
        writer.writeheader()
        writer.writerows(records)

    logger.info("CSV edifici critici scritto in %s", out_csv_path)
    return out_csv_path


def export_buildings_folium_map(
    buildings_gdf: "gpd.GeoDataFrame",
    center_coords: Tuple[float, float],
    out_html_path: Path,
) -> Path:
    """
    Crea una mappa Folium con gli edifici forniti (poligoni)
    colorati in rosso.
    """
    if folium is None:
        raise RuntimeError(
            "folium è richiesto per creare la mappa HTML. "
            "Installa con `pip install folium`."
        )

    if gpd is None:
        raise RuntimeError("geopandas è richiesto per la mappa HTML edifici.")

    out_html_path.parent.mkdir(parents=True, exist_ok=True)

    m = folium.Map(location=[center_coords[1], center_coords[0]], zoom_start=13)

    if buildings_gdf.empty:
        logger.warning("Nessun edificio da mostrare sulla mappa HTML.")
    else:
        # Converti in GeoJSON
        folium.GeoJson(
            buildings_gdf.to_crs(epsg=4326),
            name="Edifici a rischio",
            style_function=lambda x: {
                "fillColor": "red",
                "color": "red",
                "weight": 1,
                "fillOpacity": 0.7,
            },
        ).add_to(m)

    folium.LayerControl().add_to(m)
    m.save(str(out_html_path))
    logger.info("Mappa HTML edifici a rischio scritta in %s", out_html_path)
    return out_html_path
