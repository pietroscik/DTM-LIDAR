import subprocess
import sys
import os
from pathlib import Path

def run_verification():
    print("==================================================")
    print("   🛡️  HYDRO-GIS SYSTEM VERIFICATION PROTOCOL")
    print("==================================================\n")

    # 0. System Check
    print(">>> [1/3] Controllo Ambiente...")
    
    # Check WhiteboxTools (installato da setup_auto.sh)
    wbt_name = "whitebox_tools.exe" if os.name == 'nt' else "whitebox_tools"
    wbt_found = False
    for loc in [Path(wbt_name), Path("WBT") / wbt_name, Path("/usr/local/bin") / wbt_name]:
        if loc.exists():
            print(f"✅ WhiteboxTools trovato: {loc}")
            wbt_found = True
            break
    
    if not wbt_found and not os.environ.get("WBT_PATH"):
        print("⚠️  WhiteboxTools non trovato nei percorsi standard. Assicurati che sia nel PATH o esegui setup_auto.sh")

    # Check Config
    if Path("config.yaml").exists():
        print("✅ Configurazione presente.")
    else:
        print("❌ config.yaml mancante!")

    # 1. Reset
    print("\n>>> [2/3] Reset Repository (Pulizia Output/Cache)...")
    reset_script = "scripts/reset_repository.py" if Path("scripts/reset_repository.py").exists() else "reset_repository.py"
    if Path(reset_script).exists():
        try:
            subprocess.check_call([sys.executable, reset_script])
        except subprocess.CalledProcessError:
            print("❌ Errore critico durante il reset.")
            sys.exit(1)
    else:
        print(f"⚠️  Script di reset '{reset_script}' non trovato. Skipping.")
    
    print("\n>>> [3/3] Avvio Test di Validazione (Pipeline Sintetica)...")
    test_script = "tests/test_quick_validation.py" if Path("tests/test_quick_validation.py").exists() else "test_quick_validation.py"
    if Path(test_script).exists():
        try:
            subprocess.check_call([sys.executable, test_script])
            print("\n✅ VERIFICA COMPLETATA: Il sistema è pulito, configurato e funzionante.")
        except subprocess.CalledProcessError:
            print("\n❌ TEST FALLITO: Controlla i log sopra.")
            sys.exit(1)
    else:
        print(f"❌ Script di test '{test_script}' non trovato.")
        sys.exit(1)

if __name__ == "__main__":
    run_verification()