import zipfile
import os

def analyze_zip(zip_path):
    if not os.path.exists(zip_path):
        print(f"❌ File non trovato: {zip_path}")
        return

    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            files = z.namelist()
            print(f"📂 Analisi contenuto di: {zip_path}")
            print(f"   Totale file: {len(files)}")
            
            # Cerca binario Linux (senza estensione)
            linux_bin = [f for f in files if f.endswith("whitebox_tools") and not f.endswith(".exe") and not f.endswith(".rs")]
            # Cerca binario Windows
            win_bin = [f for f in files if f.endswith("whitebox_tools.exe")]
            
            if linux_bin:
                print(f"✅ Binario Linux trovato: {linux_bin[0]}")
                print(f"   Path interno: {os.path.dirname(linux_bin[0])}")
            elif win_bin:
                print(f"⚠️  Trovato solo binario Windows: {win_bin[0]}")
                print("   Questo zip NON funzionerà su Docker (Linux). Devi scaricare 'WhiteboxTools_linux_amd64.zip'.")
            else:
                print("❌ Nessun binario 'whitebox_tools' trovato.")
                if any("src/" in f for f in files) or any("Cargo.toml" in f for f in files):
                    print("   🛑 ATTENZIONE: Hai scaricato il CODICE SORGENTE.")
                    print("   Docker non può usarlo direttamente. Scarica il file 'WhiteboxTools_linux_amd64.zip' dalle Release.")
                else:
                    print("   Primi 10 file nel zip:")
                    for f in files[:10]:
                        print(f"   - {f}")

    except zipfile.BadZipFile:
        print("❌ Il file non è un archivio zip valido.")

if __name__ == "__main__":
    analyze_zip("WhiteboxTools_linux_amd64.zip")