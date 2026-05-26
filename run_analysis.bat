@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo   Hydro-GIS Analysis Launcher
echo ==========================================

REM 1. Cerca ambiente virtuale
if exist ".venv\Scripts\activate.bat" (
    echo [*] Attivazione virtualenv: .venv
    call ".venv\Scripts\activate.bat"
) else if exist "venv\Scripts\activate.bat" (
    echo [*] Attivazione virtualenv: venv
    call "venv\Scripts\activate.bat"
) else (
    echo [!] Nessun virtualenv trovato (cercato .venv, venv).
    echo     Uso interprete Python di sistema.
)

REM 2. Verifica installazione
python -c "import streamlit" >nul 2>&1
if %errorlevel% neq 0 (
    echo [X] Errore: Streamlit non trovato.
    echo     Esegui: pip install -r requirements.txt
    pause
    exit /b 1
)

REM 3. Avvio
echo [*] Avvio applicazione...
streamlit run streamlit_app.py

if %errorlevel% neq 0 (
    echo.
    echo [!] Applicazione terminata con codice errore %errorlevel%
    pause
)