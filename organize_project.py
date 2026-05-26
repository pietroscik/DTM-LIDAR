import os
import shutil
from pathlib import Path

def organize():
    print("📦 Riorganizzazione struttura progetto...")
    root = Path(".")
    
    # 1. Creazione cartelle base
    for folder in ["docs", "tests", "scripts", ".streamlit"]:
        os.makedirs(folder, exist_ok=True)
    
    # 2. Spostamento File Documentazione e Test
    moves = {
        "docs": [
            "Documentation.md", 
            "RELAZIONE TECNICA.md", 
            "Ecco la Guida Tecnica per configurare un.md",
            "Progetto Completo.md"
        ],
        "tests": [
            "test_config_validation.py", 
            "test_quick_validation.py",
            "test_streamlit_app.py"
        ],
        "scripts": [
            "reset_repository.py", 
            "cleanup_project.py"
        ]
    }
    
    for folder, files in moves.items():
        for f in files:
            src = root / f
            dst_folder = root / folder
            
            # Rinomina speciale per la guida AI
            dst_name = "AI_AGENT_GUIDE.md" if f.startswith("Ecco la Guida") else f
            dst = dst_folder / dst_name

            if src.exists():
                if dst.exists():
                    print(f" -> {folder}/{dst_name} esiste già. Rimuovo duplicato dalla root: {f}")
                    os.remove(src)
                else:
                    shutil.move(str(src), str(dst))
                    print(f" -> Spostato {f} in {folder}/{dst_name}")

    # 3. Gestione Configurazione Streamlit (config.toml -> .streamlit/config.toml)
    config_toml_src = root / "config.toml"
    config_toml_dst = root / ".streamlit" / "config.toml"
    if config_toml_src.exists():
        if config_toml_dst.exists():
            print(" -> .streamlit/config.toml esiste già. Rimuovo config.toml dalla root.")
            os.remove(config_toml_src)
        else:
            shutil.move(str(config_toml_src), str(config_toml_dst))
            print(" -> Spostato config.toml in .streamlit/config.toml")

    # 4. Gestione Pipeline SRTM (SRTM/ -> scripts/)
    srtm_old_dir = root / "SRTM"
    srtm_old_script = srtm_old_dir / "flood_risk_prototype.py"
    srtm_new_script = root / "scripts" / "srtm_full_pipeline.py"

    if srtm_old_script.exists():
        if srtm_new_script.exists():
            print(" -> scripts/srtm_full_pipeline.py esiste già. Rimuovo versione legacy in SRTM/.")
            os.remove(srtm_old_script)
        else:
            shutil.move(str(srtm_old_script), str(srtm_new_script))
            print(" -> Spostato SRTM/flood_risk_prototype.py in scripts/srtm_full_pipeline.py")
    
    # Rimuovi cartella SRTM se vuota
    if srtm_old_dir.exists() and not any(srtm_old_dir.iterdir()):
        os.rmdir(srtm_old_dir)
        print(" -> Rimossa cartella vuota SRTM/")

    print("✅ Struttura aggiornata e allineata.")

if __name__ == "__main__":
    organize()