# SONGXS — Catalog Ingestion Tool

## Setup
1. Coloca `credentials.json` (Google Cloud OAuth) en esta carpeta
2. Instala dependencias: `py -m pip install -r requirements.txt`
3. Corre: `py app.py`
4. Abre: http://127.0.0.1:5000

## Flujo
1. Exporta playlist desde Exportify (http://127.0.0.1:3000)
2. Arrastra el CSV a SONGXS
3. Ingresa nombre y email del artista
4. Click en el botón — crea carpeta en Drive, sube Sheet y envía email

## Archivos necesarios
- `credentials.json` — Google Cloud OAuth credentials (no incluido por seguridad)
- `google_token.json` — se genera automáticamente al autenticar

## Carpeta Drive
READY-TO-INGEST ID: 1_7I5T3s04L4WLJh11CI9yiHwgzpu81Nn
