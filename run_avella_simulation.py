import subprocess
import sys
from pathlib import Path

def run_simulation():
    print("==================================================")
    print("   🌊 HYDRO-GIS: SIMULAZIONE AVELLA (SRTM)")
    print("==================================================\n")
    
    # 1. Configurazione Percorsi
    root_dir = Path(__file__).parent
    script_path = root_dir / "scripts" / "srtm_full_pipeline.py"
    out_dir = root_dir / "output" / "avella_srtm_screening"
    
    if not script_path.exists():
        print(f"❌ Errore: Script non trovato in {script_path}")
        return

    # 2. Parametri Simulazione
    # Avella: Lon 14.593131, Lat 40.968531
    params = [
        "--coords", "14.593131, 40.968531",
        "--buffer-km", "5",
        "--out-dir", str(out_dir),
        "--enable-osm-exposure"
    ]
    
    cmd = [sys.executable, str(script_path)] + params
    
    print(f"📍 Target: Avella (14.593131, 40.968531)")
    print(f"📂 Output: {out_dir}")
    print(f"🚀 Esecuzione comando: python {script_path.name} ...\n")
    
    # 3. Esecuzione Pipeline
    try:
        # Esegue lo script ereditando l'ambiente corrente (per credenziali GEE)
        subprocess.check_call(cmd, cwd=root_dir)
    except subprocess.CalledProcessError as e:
        print(f"\n❌ ERRORE: La pipeline è terminata con codice {e.returncode}")
        print("Suggerimento: Verifica di aver autenticato Earth Engine (earthengine authenticate)")
        return
    except KeyboardInterrupt:
        print("\n⚠️ Interrotto dall'utente.")
        return

    # 4. Verifica Output
    print("\n>>> Verifica Risultati...")
    report_file = out_dir / "report.md"
    
    if report_file.exists():
        print(f"✅ SUCCESSO: Report generato in {report_file}")
        print("-" * 40)
        with open(report_file, "r", encoding="utf-8") as f:
            print(f.read())
        print("-" * 40)
    else:
        print(f"❌ FALLITO: Il file {report_file} non è stato creato.")

if __name__ == "__main__":
    run_simulation()