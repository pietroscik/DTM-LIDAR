import sys
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

# 1. Setup dei Mock per le dipendenze esterne (GEE, Geemap)
# Devono essere definiti prima di importare il modulo core.data_ingest
mock_ee = MagicMock()
mock_geemap = MagicMock()

module_patches = {
    "ee": mock_ee,
    "geemap": mock_geemap
}

@patch.dict(sys.modules, module_patches)
class TestDataIngest:
    
    def setup_method(self):
        """Eseguito prima di ogni test."""
        # Importiamo il modulo (userà i mock definiti sopra)
        from core import data_ingest
        self.data_ingest = data_ingest
        
        # Assicuriamoci che il modulo veda le librerie come presenti
        self.data_ingest.ee = mock_ee
        self.data_ingest.geemap = mock_geemap
        
        # Reset dei mock
        mock_ee.reset_mock()
        mock_geemap.reset_mock()

    def test_upload_geotiff_to_gee_success(self):
        """
        Verifica che la funzione chiami geemap.ee_upload_image_to_asset con i parametri corretti.
        """
        # Parametri di test
        fake_path = Path("output/test_dem.tif")
        fake_asset = "users/test_user/my_asset"
        
        # Mockiamo initialize_earth_engine per evitare chiamate reali
        with patch("core.data_ingest.initialize_earth_engine") as mock_init:
            # Esecuzione
            self.data_ingest.upload_geotiff_to_gee(fake_path, fake_asset, overwrite=True)
            
            # Verifiche
            mock_init.assert_called_once() # Deve inizializzare GEE
            mock_geemap.ee_upload_image_to_asset.assert_called_once_with(
                filename=str(fake_path),
                asset_id=fake_asset,
                overwrite=True
            )

    def test_upload_geotiff_to_gee_missing_libraries(self):
        """
        Verifica che venga sollevato un errore se ee o geemap non sono installati.
        """
        # Simuliamo l'assenza delle librerie
        self.data_ingest.ee = None
        self.data_ingest.geemap = None
        
        with pytest.raises(RuntimeError, match="earthengine-api/geemap are not available"):
            self.data_ingest.upload_geotiff_to_gee(Path("test.tif"), "asset_id")