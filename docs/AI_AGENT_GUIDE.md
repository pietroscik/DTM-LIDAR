Ecco la Guida Tecnica per configurare un AI Agent (usando framework come LangChain, CrewAI o AutoGPT) dedicato all'analisi idrogeologica.

Questa guida definisce il "Cervello", gli "Strumenti" e le "Regole di Ingaggio" del tuo agente.

1. Architettura dell'Agente (Il Concetto)
L'agente non deve solo "parlare", deve agire. La struttura logica sarà:

Input: Coordinate o Shapefile dell'area.

Cervello (LLM): Pianifica i passaggi (es. "Devo scaricare il DEM").

Mani (Tools): Esegue script Python, interroga API (Google Earth Engine), gestisce file.

Occhi (Feedback): Legge gli errori del codice e si autocorregge.


Shutterstock
2. System Instruction (Il "Prompt Master")
Copia e incolla questa istruzione nel "System Prompt" del tuo Agente. Questa definisce la sua identità e competenza.

ROLE: Sei Hydro-G.I.S., un Agente AI esperto in Idraulica Computazionale, Geomorfologia e Python Scripting.

MISSION: Il tuo obiettivo è elaborare autonomamente un progetto di valutazione del rischio alluvionale partendo da coordinate geografiche. Devi produrre mappe georeferenziate (.tif) e un report tecnico.

CAPABILITIES & CONSTRAINTS:

Python First: Per ogni analisi, DEVI scrivere ed eseguire codice Python reale. Non inventare dati.

Library Access: Hai accesso a geemap, earthengine-api, pysheds, rasterio, whitebox.

Data Sourcing: Usa Google Earth Engine per scaricare DTM (SRTM/NASA) e Land Cover (ESA WorldCover). Se i dati mancano, simula con un DTM sintetico ma avvisa l'utente.

Methodology:

Pulisci il DEM (Fill Sinks / Breaching).

Calcola Flow Direction e Flow Accumulation.

Calcola indici: TWI (Topographic Wetness Index), SPI (Stream Power Index).

Integra Land Cover per stimare il coefficiente di deflusso (Runoff C).

Error Handling: Se uno script fallisce, leggi l'errore, correggi il codice e riprova fino a 3 volte.

OUTPUT:

I file raster generati salvati in locale.

Un file Markdown con l'interpretazione dei risultati (Aree critiche identificate).

3. Definizione degli Strumenti (Tools)
Affinché l'agente funzioni, devi dargli accesso a queste funzioni specifiche. Se usi LangChain o CrewAI, ecco come configurare i tools in Python:

A. Tool: Python Code Interpreter (Fondamentale)
L'agente deve poter eseguire il codice che scrive.

Librerie pre-installate necessarie nell'ambiente: pysheds, geemap, rasterio, numpy, matplotlib, whitebox.

B. Tool: File System Manager
L'agente deve poter leggere e scrivere file sul disco.

Permessi: Read/Write nella cartella ./project_data.

C. Tool: Earth Engine Connector
Una funzione specifica per autenticarsi senza chiedere ogni volta all'utente.

4. Workflow Operativo (La Catena di Pensiero)
Quando attivi l'agente, lui seguirà questo Chain of Thought (CoT). Puoi usare questo elenco per verificare se sta ragionando correttamente:

PLAN: "Ricevute coordinate (Lat/Lon). Definisco l'area di interesse (Bounding Box)."

ACQUIRE: "Scrivo script Python con geemap per scaricare il DTM SRTM e il Land Cover ESA. Eseguo."

CHECK: "I file .tif sono stati salvati? Sono validi? Se sì, procedo."

PROCESS (Hydrology): "Uso pysheds. Carico DTM -> Fill Pits -> Flow Dir -> Accumulation. Salvo i risultati intermedi."

PROCESS (Risk): "Calcolo SPI e TWI. Incrocio con Land Cover. Genero Mappa Rischio combinata."

REPORT: "Analizzo le statistiche dei raster. Dove sono i pixel rossi? Scrivo il report finale."

5. Esempio di Codice per Creare l'Agente (usando CrewAI)
Ecco uno scheletro di codice Python per "costruire" questo agente sul tuo computer. Richiede la libreria crewai.

Python
from crewai import Agent, Task, Crew, Process
from langchain_community.tools import Tool

# 1. Definizione dell'Agente
hydro_agent = Agent(
    role='Senior Hydrologist Developer',
    goal='Scaricare dati satellitari ed eseguire analisi di rischio idrogeologico complete',
    backstory="""Sei un ingegnere civile specializzato in Python e GIS. 
    Il tuo lavoro è automatizzare la creazione di mappe di rischio alluvionale 
    senza intervento umano, correggendo i tuoi stessi bug.""",
    verbose=True,
    allow_delegation=False,
    # Qui inseriresti il tool "Python REPL" per fargli eseguire codice
    # tools=[python_repl_tool] 
)

# 2. Definizione del Task (Il Progetto)
analysis_task = Task(
    description="""
    1. Analizza l'area alle coordinate: {coords}.
    2. Scarica DEM e LandCover da Google Earth Engine (usa geemap).
    3. Calcola il TWI (Topographic Wetness Index) e SPI (Stream Power Index).
    4. Salva i file GeoTIFF finali nella cartella 'output'.
    5. Scrivi un report 'analisi.md' spiegando dove sono i rischi maggiori.
    """,
    agent=hydro_agent,
    expected_output="Un set di file .tif e un report testuale."
)

# 3. Avvio della Crew
crew = Crew(
    agents=[hydro_agent],
    tasks=[analysis_task],
    process=Process.sequential
)

# ESECUZIONE
result = crew.kickoff(inputs={'coords': '43.7696, 11.2558'})
print(result)
Come usare questa guida
Se usi ChatGPT Plus (o Claude):
Attiva la modalità "Data Analyst" (o carica i file). Incolla il System Instruction (Punto 2) all'inizio della chat. Poi digli: "Esegui il progetto per le coordinate X, Y usando i file che ti dico di generare o scaricare". (Nota: ChatGPT non può accedere a Earth Engine direttamente, ma può scriverti il codice perfetto da copiare).

Se vuoi l'Automazione Totale:
Devi installare Python e CrewAI (come nell'esempio al Punto 5). Copia il codice, inserisci la tua chiave API di OpenAI, e lancia lo script. L'agente lavorerà nel terminale, scaricherà i dati, elaborerà e ti consegnerà i file finiti.