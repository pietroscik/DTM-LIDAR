import sys
from pathlib import Path
import logging

# Aggiunge la root del progetto al path per importare i moduli core
current_path = Path(__file__).resolve().parent
if (current_path / "config.yaml").exists():
    PROJECT_ROOT = current_path
else:
    PROJECT_ROOT = current_path.parent
sys.path.append(str(PROJECT_ROOT))

try:
    from core.utils import load_config
    from core.logging_config import setup_logging, get_logger
except ImportError as e:
    print(f"Errore critico importazione moduli core: {e}")
    sys.exit(1)

# Configura logging
setup_logging(log_level="INFO")
logger = get_logger("ConfigValidator")

def validate_config():
    """
    Carica config.yaml e valida schema, tipi e vincoli logici.
    """
    logger.info("=== Avvio Validazione Configurazione (config.yaml) ===")
    
    config = load_config()
    if not config:
        logger.error("❌ Errore: config.yaml non trovato o vuoto.")
        return False

    all_passed = True

    # 1. Definizione Schema (Chiave -> (Tipo, [Sotto-chiavi obbligatorie]))
    schema = {
        "project": (dict, ["name", "version"]),
        "flow_accumulation_backend": (str, []),
        "risk_weights": (dict, ["twi", "spi", "runoff", "slope"]),
        "risk_thresholds": (dict, ["low", "high"]),
        "spi_postprocessing": (dict, ["percentile", "buffer_meters", "median_filter_size"]),
        "gee_dem_dataset_id": (str, []),
        "gee_landcover_collection": (str, []),
        "gee_chirps_collection": (str, []),
        "lidar_wms_url": (str, []),
        "lidar_wms_layer": (str, []),
        "landcover_runoff_mapping": (dict, []),
        "visualization": (dict, ["colormaps", "opacity"]),
    }

    # 2. Validazione Strutturale
    for key, (expected_type, required_subkeys) in schema.items():
        if key not in config:
            logger.error(f"❌ Chiave mancante: '{key}'")
            all_passed = False
            continue
        
        val = config[key]
        if not isinstance(val, expected_type):
            logger.error(f"❌ Tipo errato per '{key}': atteso {expected_type.__name__}, trovato {type(val).__name__}")
            all_passed = False
            continue
        
        if required_subkeys and isinstance(val, dict):
            for subkey in required_subkeys:
                if subkey not in val:
                    logger.error(f"❌ Sotto-chiave mancante in '{key}': '{subkey}'")
                    all_passed = False

    # 3. Validazione Logica (Valori)
    
    # Controllo somma pesi rischio ~ 1.0
    if "risk_weights" in config and isinstance(config["risk_weights"], dict):
        try:
            weights = config["risk_weights"]
            total = sum(float(w) for w in weights.values())
            if not (0.99 <= total <= 1.01):
                logger.warning(f"⚠️  I pesi di rischio (risk_weights) sommano a {total:.2f}, dovrebbero essere ~1.0")
        except ValueError:
            logger.error("❌ Valori non numerici in risk_weights")
            all_passed = False

    # Controllo soglie rischio
    if "risk_thresholds" in config and isinstance(config["risk_thresholds"], dict):
        try:
            low = float(config["risk_thresholds"].get("low", 0))
            high = float(config["risk_thresholds"].get("high", 0))
            if not (0 < low < high < 1):
                logger.error(f"❌ Soglie rischio non valide (atteso 0 < low < high < 1): low={low}, high={high}")
                all_passed = False
        except ValueError:
            logger.error("❌ Valori non numerici in risk_thresholds")
            all_passed = False

    # Controllo backend flow accumulation
    valid_backends = ["auto", "pysheds", "whitebox", "placeholder"]
    backend = config.get("flow_accumulation_backend")
    if backend and backend not in valid_backends:
        logger.warning(f"⚠️  Backend flow accumulation '{backend}' non standard. Validi: {valid_backends}")

    # 4. Esito
    if all_passed:
        logger.info("✅ Configurazione valida! Il sistema è pronto.")
        return True
    else:
        logger.error("❌ Validazione fallita. Controlla gli errori sopra.")
        return False

if __name__ == "__main__":
    success = validate_config()
    sys.exit(0 if success else 1)