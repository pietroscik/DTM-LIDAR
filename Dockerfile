# Stage 1: Builder (Compilazione e Installazione Dipendenze)
FROM python:3.11-slim AS builder

WORKDIR /app

# Installazione dipendenze di sistema per la build
# libgdal-dev e libspatialindex-dev servono per compilare eventuali pacchetti Python
RUN apt-get update && apt-get install -y \
    build-essential \
    libgdal-dev \
    libspatialindex-dev \
    unzip \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Configurazione variabili d'ambiente per compilazione GDAL
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

# Creazione virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Installazione dipendenze Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Installazione WhiteboxTools
RUN wget -q https://www.whiteboxgeo.com/GAT/WhiteboxTools_linux_amd64.zip -O wbt.zip \
    && unzip wbt.zip \
    && WBT_BIN=$(find . -type f -name "whitebox_tools" | head -n 1) \
    && if [ -z "$WBT_BIN" ]; then echo "❌ ERRORE: Binario 'whitebox_tools' non trovato nel zip."; exit 1; fi \
    && chmod +x "$WBT_BIN" \
    && mv "$WBT_BIN" /usr/local/bin/whitebox_tools

# Stage 2: Runtime (Immagine Finale Leggera)
FROM python:3.11-slim

WORKDIR /app

# Installazione dipendenze di runtime
# libgdal32 e libspatialindex6 sono le librerie condivise necessarie
RUN apt-get update && apt-get install -y \
    libgdal32 \
    libspatialindex6 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copia del virtual environment e del binario WBT dal builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY --from=builder /usr/local/bin/whitebox_tools /usr/local/bin/whitebox_tools
ENV WBT_PATH="/usr/local/bin/whitebox_tools"

# Copia del codice sorgente
COPY . .

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "streamlit_app.py", "--server.address=0.0.0.0"]