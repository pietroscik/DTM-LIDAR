import shutil
import os
import stat
from pathlib import Path

def on_rm_error(func, path, exc_info):
    """
    Gestore errori per shutil.rmtree.
    Tenta di rimuovere il flag read-only (comune su Windows) e riprova.
    """
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass

def reset_repo():
    """
    Riporta il repository a uno stato pulito eliminando:
    - Cartelle di output (output/, temp/)
    - Cache di Python (__pycache__, .pytest_cache)
    - File di log
    """
    # Rileva root del progetto (supporta esecuzione da root o da scripts/)
    current_path = Path(__file__).resolve().parent
    if (current_path / "config.yaml").exists():
        root = current_path
    else:
        root = current_path.parent

    print(f"🧹 Avvio pulizia repository in: {root}")

    # Cartelle da rimuovere completamente
    dirs_to_clean = [
        root / "output",
        root / "temp",
        root / "logs",
        root / ".pytest_cache",
        root / ".mypy_cache"
    ]

    # Pattern da rimuovere ricorsivamente
    patterns = ["__pycache__", "*.pyc", "*.pyo", "*.log", ".DS_Store"]
    
    # 1. Rimozione Cartelle Output/Temp
    for d in dirs_to_clean:
        if d.exists():
            try:
                shutil.rmtree(d, onerror=on_rm_error)
                if d.exists():
                    print(f"⚠️  Rimozione parziale: {d.name} (file in uso?)")
                else:
                    print(f"✅ Rimossa cartella: {d.name}")
            except Exception as e:
                print(f"❌ Errore rimozione {d.name}: {e}")

    # 2. Pulizia Ricorsiva (Cache, Log)
    for pattern in patterns:
        for p in root.rglob(pattern):
            if p.is_dir():
                try:
                    shutil.rmtree(p, onerror=on_rm_error)
                    if not p.exists():
                        print(f"✅ Rimossa cache: {p.relative_to(root)}")
                except Exception:
                    pass
            elif p.is_file() and p.name != "reset_repository.py":
                try:
                    p.unlink()
                    print(f"✅ Rimosso file: {p.relative_to(root)}")
                except Exception:
                    pass

    print("✨ Repository inizializzato a nuovo. Pronto per una nuova esecuzione.")

if __name__ == "__main__":
    reset_repo()