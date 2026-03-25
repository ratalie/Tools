"""
Certfika Contact Importer
==========================
Agrega contactos nuevos desde un CSV de Apollo al Google Sheet existente.
- No borra nada del Sheet actual
- Evita duplicados (chequea por email)
- Solo agrega las columnas que ya existen en el Sheet
"""

import csv
import json
import time
import os
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
import gspread

CONFIG_FILE = "config.json"
TOKEN_FILE = "token.json"
CREDENTIALS_FILE = "credentials.json"

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Archivo CSV a importar (ponlo en la misma carpeta)
CSV_FILE = "apollo-contacts-export.csv"


def get_credentials():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return creds


def main():
    with open(CONFIG_FILE) as f:
        config = json.load(f)

    print("🔐 Autenticando con Google...")
    creds = get_credentials()
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(config["spreadsheet_id"]).sheet1

    print("📋 Leyendo Sheet actual...")
    headers = sheet.row_values(1)
    all_rows = sheet.get_all_values()

    # Obtener emails existentes para evitar duplicados
    try:
        email_col = headers.index("Email")
    except ValueError:
        print("❌ No se encontró columna 'Email' en el Sheet.")
        return

    existing_emails = set()
    for row in all_rows[1:]:  # Saltar header
        if len(row) > email_col:
            email = row[email_col].strip().lower()
            if email:
                existing_emails.add(email)

    print(f"   Contactos actuales en el Sheet: {len(existing_emails)}")

    # Leer CSV
    print(f"\n📂 Leyendo {CSV_FILE}...")
    with open(CSV_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        csv_rows = list(reader)

    print(f"   Contactos en el CSV: {len(csv_rows)}")

    # Filtrar nuevos (no duplicados, con email válido)
    nuevos = []
    sin_email = 0
    duplicados = 0

    for row in csv_rows:
        email = row.get("Email", "").strip()

        if not email or "@" not in email:
            sin_email += 1
            continue

        if email.lower() in existing_emails:
            duplicados += 1
            continue

        nuevos.append(row)

    print(f"   Sin email: {sin_email}")
    print(f"   Duplicados (ya en el Sheet): {duplicados}")
    print(f"   ✅ Nuevos a agregar: {len(nuevos)}")

    if not nuevos:
        print("\n✅ No hay contactos nuevos para agregar.")
        return

    # Armar filas en el mismo orden de columnas del Sheet
    rows_to_append = []
    for contact in nuevos:
        row = []
        for col in headers:
            # Solo agregar columnas que existen en el CSV
            # Las columnas de tracking (Estado, Thread_ID, etc.) quedan vacías
            value = contact.get(col, "")
            row.append(str(value) if value else "")
        rows_to_append.append(row)

    # Agregar al Sheet en lotes de 50
    print(f"\n📤 Agregando {len(rows_to_append)} contactos al Sheet...")
    batch_size = 50
    added = 0

    for i in range(0, len(rows_to_append), batch_size):
        batch = rows_to_append[i:i + batch_size]
        sheet.append_rows(batch, value_input_option="USER_ENTERED")
        added += len(batch)
        print(f"   {added}/{len(rows_to_append)} agregados...")
        time.sleep(1)

    print(f"\n{'─'*50}")
    print(f"🏁 Importación completada.")
    print(f"   ✅ Nuevos contactos agregados: {added}")
    print(f"   ⏭️  Duplicados omitidos:        {duplicados}")
    print(f"   ⚠️  Sin email (omitidos):        {sin_email}")
    print(f"\nEl script emailer.py los enviará automáticamente mañana a las 8:30am.")


if __name__ == "__main__":
    main()
