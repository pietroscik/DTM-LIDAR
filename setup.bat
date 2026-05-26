@echo off
echo 🌊 Hydro-GIS Auto Setup (Windows)
echo =================================

REM 1. Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python non trovato. Assicurati che sia nel PATH.
    pause
    exit /b 1
)

REM 2. Virtual Environment
if not exist "venv" (
    echo 📦 Creazione virtual environment...
    python -m venv venv
)

REM 3. Installazione Dipendenze
echo ⬇️ Attivazione venv e installazione dipendenze...
call venv\Scripts\activate
python -m pip install --upgrade pip
if exist "requirements.txt" (
    pip install -r requirements.txt
) else (
    echo ⚠️ requirements.txt non trovato. Installazione dipendenze base...
    pip install numpy rasterio geopandas shapely folium streamlit whitebox pysheds
)

REM 4. Setup WhiteboxTools
if not exist "whitebox_tools.exe" (
    echo 🔧 Download WhiteboxTools...
    powershell -Command "Invoke-WebRequest -Uri 'https://www.whiteboxgeo.com/GAT/WhiteboxTools_win_amd64.zip' -OutFile 'wbt.zip'"
    powershell -Command "Expand-Archive -Path 'wbt.zip' -DestinationPath '.'"
    
    REM Cerca e sposta l'eseguibile
    if exist "WBT\whitebox_tools.exe" (
        copy WBT\whitebox_tools.exe . >nul
        rmdir /s /q WBT
    )
    
    del wbt.zip
    echo ✅ WhiteboxTools installato.
) else (
    echo ✅ WhiteboxTools già presente.
)

echo.
echo 🎉 Setup completato!
echo.
echo Per avviare l'applicazione:
echo 1. venv\Scripts\activate
echo 2. python -m streamlit run streamlit_app.py
echo.
pause