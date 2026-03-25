"""
Certfika Email Verifier
========================
Verifica si los emails del Sheet son válidos antes de enviar follow-ups.

Estrategia:
1. Emails con Email Status = "Unavailable" → marca como Descartado directo
2. Emails ya rebotados (Estado = "Rebotado") → ya están marcados
3. Emails con "Extrapolated" u otros → verifica por DNS + SMTP
4. Actualiza columna "Estado" y "Email_Verificado" en el Sheet
"""

import time
import socket
import smtplib
import dns.resolver
import re
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
import gspread
import json

# ─────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────

CONFIG_FILE = "config.json"
TOKEN_FILE = "token.json"
CREDENTIALS_FILE = "credentials.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

# Email desde el que haremos el SMTP check (el tuyo de HumanTech)
FROM_EMAIL = "mirella@humantech.pe"


# ─────────────────────────────────────────────
# AUTENTICACIÓN GOOGLE
# ─────────────────────────────────────────────

def get_credentials():
    creds = None
    if __import__('os').path.exists(TOKEN_FILE):
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


def get_sheet(creds, spreadsheet_id):
    gc = gspread.authorize(creds)
    return gc.open_by_key(spreadsheet_id).sheet1


# ─────────────────────────────────────────────
# VERIFICACIÓN DE EMAIL
# ─────────────────────────────────────────────

def is_valid_syntax(email):
    """Verifica que el email tiene formato válido."""
    pattern = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def get_mx_records(domain):
    """Obtiene los servidores MX del dominio."""
    try:
        records = dns.resolver.resolve(domain, 'MX')
        mx_list = sorted([(r.preference, str(r.exchange).rstrip('.')) for r in records])
        return [mx for _, mx in mx_list]
    except Exception:
        return []


def smtp_verify(email, mx_servers, from_email, timeout=10):
    """
    Verifica si el buzón existe via SMTP sin enviar email.
    Retorna: 'valid', 'invalid', 'catch_all', 'unknown'
    """
    if not mx_servers:
        return 'invalid'

    for mx in mx_servers[:2]:  # Intentar con los 2 primeros MX
        try:
            with smtplib.SMTP(timeout=timeout) as smtp:
                smtp.connect(mx, 25)
                smtp.helo('humantech.pe')
                smtp.mail(from_email)
                code, _ = smtp.rcpt(email)

                if code == 250:
                    # Verificar si es catch-all (acepta cualquier email)
                    fake_email = f"zz_fake_nonexistent_xyz123@{email.split('@')[1]}"
                    smtp.mail(from_email)
                    fake_code, _ = smtp.rcpt(fake_email)
                    if fake_code == 250:
                        return 'catch_all'  # Acepta todo, no podemos saber
                    return 'valid'
                elif code in [550, 551, 552, 553, 554]:
                    return 'invalid'
                else:
                    return 'unknown'

        except smtplib.SMTPConnectError:
            continue
        except smtplib.SMTPServerDisconnected:
            continue
        except socket.timeout:
            continue
        except Exception:
            continue

    return 'unknown'


def verify_email(email):
    """Verificación completa de un email."""
    if not is_valid_syntax(email):
        return 'invalid', 'Sintaxis incorrecta'

    domain = email.split('@')[1]
    mx_servers = get_mx_records(domain)

    if not mx_servers:
        return 'invalid', 'Dominio sin servidor de correo'

    result = smtp_verify(email, mx_servers, FROM_EMAIL)

    labels = {
        'valid': 'Verificado OK',
        'invalid': 'Buzón no existe',
        'catch_all': 'Catch-all (no verificable)',
        'unknown': 'No se pudo verificar',
    }

    return result, labels.get(result, result)


# ─────────────────────────────────────────────
# LÓGICA PRINCIPAL
# ─────────────────────────────────────────────

def process_verification():
    with open(CONFIG_FILE) as f:
        config = json.load(f)

    print("🔐 Autenticando con Google...")
    creds = get_credentials()
    sheet = get_sheet(creds, config["spreadsheet_id"])

    print("📋 Leyendo contactos del Sheet...")
    headers = sheet.row_values(1)
    records = sheet.get_all_records()

    # Asegurar columna "Email_Verificado"
    if "Email_Verificado" not in headers:
        sheet.update_cell(1, len(headers) + 1, "Email_Verificado")
        headers.append("Email_Verificado")
        time.sleep(0.5)

    col_estado = headers.index("Estado") + 1 if "Estado" in headers else None
    col_email_status = headers.index("Email Status") + 1 if "Email Status" in headers else None
    col_verificado = headers.index("Email_Verificado") + 1

    total = len(records)
    descartados = 0
    validos = 0
    dudosos = 0
    errores = 0

    for i, record in enumerate(records, start=2):
        email = str(record.get("Email", "")).strip()
        apollo_status = str(record.get("Email Status", "")).strip()
        estado_actual = str(record.get("Estado", "")).strip()
        verificado_actual = str(record.get("Email_Verificado", "")).strip()

        if not email or "@" not in email:
            continue

        # Ya procesado antes
        if verificado_actual and estado_actual == "Descartado":
            descartados += 1
            continue

        print(f"[{i-1}/{total}] {email} (Apollo: {apollo_status})", end=" → ")

        # ── Paso 1: Descartar directo si Apollo dice Unavailable ──
        if apollo_status.lower() == "unavailable":
            if col_estado:
                sheet.update_cell(i, col_estado, "Descartado")
            sheet.update_cell(i, col_verificado, "Descartado (Apollo: Unavailable)")
            print("❌ Descartado (Apollo Unavailable)")
            descartados += 1
            time.sleep(0.3)
            continue

        # ── Paso 2: Si ya fue marcado como rebotado, descartar ──
        if estado_actual.lower() in ["rebotado", "bounce"]:
            sheet.update_cell(i, col_verificado, "Descartado (rebotó)")
            print("❌ Descartado (rebotó)")
            descartados += 1
            time.sleep(0.3)
            continue

        # ── Paso 3: Verificar por SMTP los demás ──
        result, label = verify_email(email)
        sheet.update_cell(i, col_verificado, label)

        if result == 'invalid':
            if col_estado:
                sheet.update_cell(i, col_estado, "Descartado")
            print(f"❌ {label}")
            descartados += 1
        elif result == 'valid':
            print(f"✅ {label}")
            validos += 1
        elif result == 'catch_all':
            print(f"⚠️  {label}")
            dudosos += 1
        else:
            print(f"❓ {label}")
            errores += 1

        time.sleep(1.5)  # Evitar bloqueos por parte de los servidores

    print(f"\n{'─'*50}")
    print(f"🏁 Verificación completada.")
    print(f"   ✅ Válidos:      {validos}")
    print(f"   ❌ Descartados:  {descartados}")
    print(f"   ⚠️  Catch-all:    {dudosos}")
    print(f"   ❓ Sin verificar: {errores}")
    print(f"\nLos descartados ya no recibirán follow-ups.")


if __name__ == "__main__":
    print("=" * 50)
    print("  Certfika Email Verifier 🔍")
    print("=" * 50)
    process_verification()
