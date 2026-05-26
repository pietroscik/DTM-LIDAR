import sys
import os
import pytest
import numpy as np
import rasterio
from rasterio.transform import from_origin
from pathlib import Path

# Aggiunge la root del progetto al path per permettere gli import
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

@pytest.fixture
def dummy_dem_path(tmp_path):
    """
    Crea un GeoTIFF DEM fittizio temporaneo per i test.
    """
    path = tmp_path / "test_dem.tif"
    # Crea una matrice 100x100 con valori di elevazione casuali
    data = np.random.rand(100, 100).astype("float32") * 100
    
    # Definisce una trasformazione geografica fittizia
    transform = from_origin(12.0, 42.0, 0.001, 0.001)
    
    with rasterio.open(
        path, "w", driver="GTiff", height=100, width=100, count=1, 
        dtype="float32", crs="EPSG:4326", transform=transform
    ) as dst:
        dst.write(data, 1)
    return path

@pytest.fixture
def mock_raster_data():
    """Restituisce dati raster grezzi per mocking."""
    return np.zeros((100, 100), dtype="float32")

@pytest.fixture
def mock_streamlit_env():
    """
    Fixture per mockare le dipendenze UI se necessario.
    """
    from unittest.mock import MagicMock
    modules_to_patch = [
        "streamlit", "streamlit_folium", "folium", "folium.plugins", "geopandas"
    ]
    patches = {}
    for mod in modules_to_patch:
        patches[mod] = MagicMock()
        sys.modules[mod] = patches[mod]
    return patches