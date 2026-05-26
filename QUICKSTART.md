# 🚀 Hydro-GIS: Guida Rapida

Benvenuto nel Digital Twin per la valutazione del rischio idrogeologico. Segui questi passaggi per configurare ed eseguire il sistema in pochi minuti.

---

## 1. Prerequisiti

*   **Python 3.9+** installato sul sistema (assicurati di selezionare "Add Python to PATH" durante l'installazione).
*   (Opzionale) Account **Google Earth Engine** se intendi scaricare dati SRTM/CHIRPS in tempo reale.

---

## 2. Installazione (Prima Esecuzione)

Apri il terminale (Prompt dei Comandi o PowerShell) nella cartella del progetto ed esegui questi comandi una sola volta:

### A. Crea l'ambiente virtuale (Consigliato)
Isola le librerie del progetto dal resto del sistema.

```bash
python -m venv .venv
```

### B. Attiva l'ambiente e installa le dipendenze

**Windows:**
```bash
.venv\Scripts\activate
pip install -r requirements.txt
```

*(Se usi Mac/Linux: `source .venv/bin/activate` seguito dal pip install)*

---

## 3. Avvio Rapido

Una volta installate le dipendenze, non serve più usare il terminale.

1.  Cerca il file **`run_analysis.bat`** nella cartella principale.
2.  Fai **Doppio Click**.
3.  Lo script rileverà automaticamente l'ambiente virtuale, avvierà il motore di calcolo e aprirà l'interfaccia Web nel tuo browser predefinito.

---

## 4. Verifica (Opzionale)

Se vuoi assicurarti che il "cervello" del modello funzioni correttamente prima di caricare dati reali, esegui lo script di autodiagnostica:

```bash
python verify_setup.py
```

Se vedi il messaggio **"✅ VERIFICA COMPLETATA"**, il sistema è perfettamente operativo.