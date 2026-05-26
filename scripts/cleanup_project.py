import os
from pathlib import Path

def cleanup_duplicates():
    """
    Rimuove i file dalla root se esistono con lo stesso nome nella cartella core/.
    Mantiene intatti gli entry point e i file di configurazione essenziali.
    """
    # Definisci i percorsi
    root_dir = Path(".")
    core_dir = root_dir / "core"

    if not core_dir.exists():
        print(f"Errore: La cartella {core_dir} non esiste. Assicurati di essere nella root del progetto.")
        return

    # Lista dei file in core/ (i moduli "verità")
    core_files = {f.name for f in core_dir.iterdir() if f.is_file() and f.name.endswith(".py")}

    print(f"🔍 Analisi duplicati basata su {len(core_files)} moduli in core/...")

    # File da NON toccare mai, anche se per assurdo esistessero in core (sicurezza)
    whitelist = {
        "flood_risk_prototype.py",
        "gee_lidar_prototype.py",
        "streamlit_app.py",
        "conftest.py",
        "setup.py"
    }

    deleted_count = 0

    for filename in core_files:
        root_file = root_dir / filename
        
        # Se il file esiste nella root e non è whitelisted
        if root_file.exists() and root_file.is_file() and filename not in whitelist:
            try:
                os.remove(root_file)
                print(f"🗑️  Eliminato duplicato: {filename}")
                deleted_count += 1
            except Exception as e:
                print(f"❌ Errore eliminazione {filename}: {e}")

    print("-" * 40)
    print(f"✅ Pulizia completata. Rimossi {deleted_count} file.")

if __name__ == "__main__":
    cleanup_duplicates()