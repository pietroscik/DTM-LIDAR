#!/bin/bash
# setup_auto.sh - Configurazione automatica ambiente Hydro-GIS
# Eseguire con: bash setup_auto.sh

echo "🌊 Hydro-GIS Auto Setup"
echo "======================="

# 1. Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 non trovato. Installalo prima di proseguire."
    exit 1
fi

# 2. Virtual Environment
if [ ! -d "venv" ]; then
    echo "📦 Creazione virtual environment..."
    python3 -m venv venv
fi

# Attivazione (funziona nello script, ma l'utente deve farlo nella sua shell)
source venv/bin/activate || source venv/Scripts/activate

# 3. Installazione Dipendenze
echo "⬇️ Installazione dipendenze Python..."
pip install --upgrade pip
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    echo "⚠️ requirements.txt non trovato. Installazione dipendenze base..."
    pip install numpy rasterio geopandas shapely folium streamlit whitebox pysheds
fi

# 4. Setup WhiteboxTools (Download automatico se mancante)
if [ ! -f "whitebox_tools" ] && [ ! -f "whitebox_tools.exe" ]; then
    echo "🔧 Download WhiteboxTools..."
    # URL fisso per Linux (default per server/docker) o Windows se rilevato
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
        WBT_URL="https://www.whiteboxgeo.com/GAT/WhiteboxTools_win_amd64.zip"
    else
        WBT_URL="https://www.whiteboxgeo.com/GAT/WhiteboxTools_linux_amd64.zip"
    fi
    
    wget -q "$WBT_URL" -O wbt.zip || curl -L "$WBT_URL" -o wbt.zip
    unzip -o wbt.zip
    
    # Cerca e sposta l'eseguibile nella root (dove utils.py lo cerca)
    find . -name "whitebox_tools*" -type f -exec mv {} . \;
    rm -rf WBT wbt.zip
    echo "✅ WhiteboxTools installato nella root."
else
    echo "✅ WhiteboxTools già presente."
fi

echo ""
echo "🎉 Setup completato!"
echo "👉 Per attivare l'ambiente: source venv/bin/activate (Linux/Mac) o venv\Scripts\activate (Windows)"