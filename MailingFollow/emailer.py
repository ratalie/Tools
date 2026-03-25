"""
Certfika Cold Email Automation
================================
Script para automatizar el envío de cold emails personalizados y follow-ups.
- Lee contactos desde Google Sheets
- Investiga cada empresa online
- Genera emails personalizados con IA (Claude)
- Envía desde Gmail (Google Workspace)
- Registra seguimientos en el Sheet
- Detecta respuestas automáticamente (interesados, no interesados, etc.)
"""

import json
import os
import re
import time
import base64
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import gspread
from anthropic import Anthropic
from duckduckgo_search import DDGS
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# ─────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────

CONFIG_FILE = "config.json"
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
]

EXTRA_COLUMNS = [
    "Estado",
    "Thread_ID",
    "Asunto_Email_1",
    "Investigacion",
    "Fecha_Email_1",
    "Fecha_Email_2",
    "Fecha_Email_3",
    "Fecha_Email_4",
    "Notas",
]

# Palabras clave para detectar NO interesados
PALABRAS_NO_INTERESADO = [
    "no me interesa", "no estamos interesados", "no interesa", "not interested",
    "no gracias", "no, gracias", "no thank", "gracias pero no",
    "por favor no", "please remove", "remove me", "unsubscribe",
    "dar de baja", "baja de", "bájame", "bajame", "bájenme", "bajenme",
    "no enviar", "no me envíen", "no me envien", "stop sending",
    "no quiero recibir", "no necesitamos", "no necesito",
    "en otro momento", "otro momento", "quizás más adelante",
    "quizas mas adelante", "más adelante", "mas adelante",
    "no es el momento", "not the right time", "not a good time",
    "no aplica", "does not apply",
]

# Palabras clave para detectar INTERESADOS
PALABRAS_INTERESADO = [
    "me interesa", "nos interesa", "interested", "quiero saber más",
    "quiero saber mas", "cuéntame", "cuentame", "más información",
    "mas informacion", "demo", "reunión", "reunion", "llamada",
    "podemos hablar", "agendemos", "disponible", "when can we",
    "me gustaría", "me gustaria", "quiero ver", "quiero conocer",
]


# ─────────────────────────────────────────────
# CARGA DE CONFIGURACIÓN
# ─────────────────────────────────────────────

def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


# ─────────────────────────────────────────────
# AUTENTICACIÓN GOOGLE
# ─────────────────────────────────────────────

def get_google_credentials():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"No se encontró '{CREDENTIALS_FILE}'. "
                    "Descargá las credenciales OAuth2 desde Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return creds


def get_gmail_service(creds):
    return build("gmail", "v1", credentials=creds)


def get_sheet(creds, spreadsheet_id):
    gc = gspread.authorize(creds)
    return gc.open_by_key(spreadsheet_id).sheet1


# ─────────────────────────────────────────────
# GESTIÓN DEL SHEET
# ─────────────────────────────────────────────

def ensure_columns(sheet):
    """Agrega las columnas de tracking si no existen, expandiendo el grid si es necesario."""
    headers = sheet.row_values(1)
    cols_to_add = [col for col in EXTRA_COLUMNS if col not in headers]

    if cols_to_add:
        needed = len(headers) + len(cols_to_add)
        if needed > sheet.col_count:
            sheet.add_cols(needed - sheet.col_count + 5)
            time.sleep(1)

        for col_name in cols_to_add:
            sheet.update_cell(1, len(headers) + 1, col_name)
            headers.append(col_name)
            time.sleep(0.5)

        print("✅ Columnas de tracking agregadas al Sheet.")

    return headers


def get_col(headers, col_name):
    try:
        return headers.index(col_name) + 1
    except ValueError:
        return None


def parse_date(value):
    if value:
        try:
            return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
        except ValueError:
            pass
    return None


def update_cell_safe(sheet, row, col, value):
    for attempt in range(3):
        try:
            sheet.update_cell(row, col, value)
            return
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                print(f"  ⚠️  No se pudo actualizar celda ({row}, {col}): {e}")


# ─────────────────────────────────────────────
# INVESTIGACIÓN DE EMPRESA
# ─────────────────────────────────────────────

def research_company(company_name):
    snippets = []
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(f"{company_name} qué hace empresa servicios", max_results=4))
            for r in results:
                body = r.get("body", "").strip()
                if body and len(body) > 50:
                    snippets.append(body)
                if len(snippets) >= 3:
                    break
    except Exception as e:
        print(f"  ⚠️  Error en búsqueda de {company_name}: {e}")

    return " | ".join(snippets)[:1200] if snippets else ""


# ─────────────────────────────────────────────
# GENERACIÓN DE EMAILS CON IA
# ─────────────────────────────────────────────

EMAIL_SPECS = {
    1: {
        "tipo": "cold email inicial",
        "instrucciones": (
            "Es el PRIMER contacto. Personaliza el email basándote en la información de la empresa. "
            "Menciona un pain point específico relacionado con certificaciones digitales en su industria/contexto. "
            "Presenta Certfika como solución concreta. Sé directo, no vendas demasiado. Máximo 160 palabras."
        ),
    },
    2: {
        "tipo": "primer follow-up (3 días después del primer email)",
        "instrucciones": (
            "Es el PRIMER FOLLOW-UP. Breve recordatorio del email anterior. "
            "Pregunta si tuvieron oportunidad de verlo. Tono amigable, sin presión. Máximo 80 palabras."
        ),
    },
    3: {
        "tipo": "segundo follow-up (8 días después del primer email)",
        "instrucciones": (
            "Es el SEGUNDO FOLLOW-UP. Ofrece un ángulo nuevo: menciona un beneficio concreto de Certfika "
            "que sea especialmente relevante para su tipo de empresa. Máximo 110 palabras."
        ),
    },
    4: {
        "tipo": "tercer y último follow-up (14 días después del primer email)",
        "instrucciones": (
            "Es el ÚLTIMO EMAIL (breakup email). Sé honesto y directo. "
            "Di que es tu último contacto, deja la puerta abierta para el futuro. "
            "Sin presión, con respeto. Máximo 70 palabras."
        ),
    },
}


def generate_email(client, config, contact, investigacion, email_number, original_subject=""):
    spec = EMAIL_SPECS[email_number]
    empresa_info = (
        f"Información encontrada online sobre la empresa:\n{investigacion}"
        if investigacion
        else "No se encontró información específica de la empresa online."
    )

    system_prompt = (
        "Eres parte del equipo de Certfika (certfika.com), una plataforma para emitir y gestionar "
        "certificados digitales de manera profesional (para capacitaciones, cursos, eventos, logros). "
        "Los clientes ideales son empresas que hacen capacitaciones internas, consultoras, institutos "
        "educativos, organizaciones que dan cursos o talleres, y cualquier empresa que quiera certificar "
        "logros de sus empleados o alumnos. Escribes en español, tono profesional pero cercano."
    )

    user_prompt = f"""Escribe un {spec['tipo']} para este contacto:

Nombre: {contact['nombre']}
Empresa: {contact['empresa']}
Cargo: {contact.get('cargo', '')}
{empresa_info}

{spec['instrucciones']}

{"Asunto del email original: " + original_subject if original_subject and email_number > 1 else ""}

Responde ÚNICAMENTE con un JSON con este formato exacto (sin markdown, sin comentarios):
{{"asunto": "...", "cuerpo": "..."}}

Reglas:
- El cuerpo debe ser texto plano, sin HTML ni markdown.
- Comienza el cuerpo con el saludo al nombre del contacto.
- No uses frases genéricas como "Espero que estés bien".
- No menciones Certfika como "startup" o "startup innovadora".
- Firma siempre al final con: {config['firma']}"""

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=600,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = response.content[0].text.strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        print(f"  ❌ Error generando email: {e}")
    return None


# ─────────────────────────────────────────────
# ENVÍO DE EMAIL
# ─────────────────────────────────────────────

def build_message(from_email, to_email, subject, body, thread_id=None, message_id=None):
    msg = MIMEMultipart("alternative")
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject

    if message_id:
        msg["In-Reply-To"] = message_id
        msg["References"] = message_id

    msg.attach(MIMEText(body, "plain", "utf-8"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    body_dict = {"raw": raw}
    if thread_id:
        body_dict["threadId"] = thread_id
    return body_dict


def send_email(gmail_service, from_email, to_email, subject, body, thread_id=None, message_id=None):
    msg_body = build_message(from_email, to_email, subject, body, thread_id, message_id)
    sent = gmail_service.users().messages().send(userId="me", body=msg_body).execute()
    return sent


# ─────────────────────────────────────────────
# ANÁLISIS DE RESPUESTAS
# ─────────────────────────────────────────────

def get_reply_text(gmail_service, thread_id, from_email):
    """Obtiene el texto de la primera respuesta que NO sea nuestra."""
    try:
        thread = gmail_service.users().threads().get(
            userId="me", id=thread_id, format="full"
        ).execute()
        messages = thread.get("messages", [])

        for msg in messages[1:]:  # Saltar el primer mensaje (el nuestro)
            headers = {h["name"].lower(): h["value"] for h in msg["payload"]["headers"]}
            sender = headers.get("from", "")

            if from_email.lower() in sender.lower():
                continue  # Es nuestro propio mensaje, saltar

            # Extraer texto del mensaje
            body_text = ""
            payload = msg.get("payload", {})

            if payload.get("body", {}).get("data"):
                body_text = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")
            elif payload.get("parts"):
                for part in payload["parts"]:
                    if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                        body_text += base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")

            return body_text.lower().strip()

    except Exception as e:
        print(f"  ⚠️  No se pudo leer el hilo {thread_id}: {e}")
    return ""


def classify_reply(reply_text):
    """
    Clasifica la respuesta del contacto.
    Retorna: 'no_interesado', 'interesado', 'respondido' (respuesta neutral)
    """
    if not reply_text:
        return None

    for keyword in PALABRAS_NO_INTERESADO:
        if keyword in reply_text:
            return "no_interesado"

    for keyword in PALABRAS_INTERESADO:
        if keyword in reply_text:
            return "interesado"

    return "respondido"  # Respondió algo pero no detectamos intención clara


def get_thread_message_id(gmail_service, thread_id):
    try:
        thread = gmail_service.users().threads().get(userId="me", id=thread_id).execute()
        messages = thread.get("messages", [])
        if messages:
            headers = {h["name"].lower(): h["value"] for h in messages[0]["payload"]["headers"]}
            return headers.get("message-id", "")
    except Exception:
        pass
    return ""


def has_reply(gmail_service, thread_id, from_email):
    """Verifica si hay alguna respuesta en el hilo."""
    try:
        thread = gmail_service.users().threads().get(userId="me", id=thread_id).execute()
        messages = thread.get("messages", [])
        if len(messages) <= 1:
            return False
        for msg in messages[1:]:
            headers = {h["name"].lower(): h["value"] for h in msg["payload"]["headers"]}
            sender = headers.get("from", "")
            if from_email.lower() not in sender.lower():
                return True
    except Exception:
        pass
    return False


# ─────────────────────────────────────────────
# LÓGICA PRINCIPAL
# ─────────────────────────────────────────────

def process_contacts():
    config = load_config()

    print("🔐 Autenticando con Google...")
    creds = get_google_credentials()
    gmail = get_gmail_service(creds)
    sheet = get_sheet(creds, config["spreadsheet_id"])
    anthropic_client = Anthropic(api_key=config["anthropic_api_key"])

    print("📋 Leyendo contactos del Sheet...")
    headers = ensure_columns(sheet)
    records = sheet.get_all_records()

    today = datetime.now().date()
    follow_up_days = config.get("follow_up_days", [3, 4, 6])

    sent_count = 0
    skip_count = 0
    interesados = 0
    no_interesados = 0

    for i, record in enumerate(records, start=2):
        first_name = str(record.get("First Name", "")).strip()
        last_name = str(record.get("Last Name", "")).strip()
        nombre = f"{first_name} {last_name}".strip()
        empresa = str(record.get("Company Name", "")).strip()
        cargo = str(record.get("Title", "")).strip()
        email = str(record.get("Email", "")).strip()

        estado = str(record.get("Estado", "")).strip() or "Pendiente"
        thread_id = str(record.get("Thread_ID", "")).strip()
        asunto_original = str(record.get("Asunto_Email_1", "")).strip()
        investigacion = str(record.get("Investigacion", "")).strip()

        if not email or "@" not in email:
            continue

        if estado in ["Respondido", "Interesado", "No Interesado", "Descartado", "Email4_Enviado"]:
            skip_count += 1
            continue

        # ── Verificar respuestas en el hilo ──
        if thread_id and has_reply(gmail, thread_id, config["from_email"]):
            reply_text = get_reply_text(gmail, thread_id, config["from_email"])
            clasificacion = classify_reply(reply_text)

            if clasificacion == "no_interesado":
                update_cell_safe(sheet, i, get_col(headers, "Estado"), "No Interesado")
                update_cell_safe(sheet, i, get_col(headers, "Notas"), "Respondió: no interesado")
                print(f"  🚫 {nombre} ({empresa}) — No interesado, descartado.")
                no_interesados += 1
                skip_count += 1
                continue

            elif clasificacion == "interesado":
                update_cell_safe(sheet, i, get_col(headers, "Estado"), "Interesado")
                update_cell_safe(sheet, i, get_col(headers, "Notas"), "Respondió: interesado ⭐")
                print(f"  ⭐ {nombre} ({empresa}) — ¡Interesado! Marcado para seguimiento manual.")
                interesados += 1
                skip_count += 1
                continue

            else:
                # Respondió algo neutro — marcar como Respondido y no enviar más
                update_cell_safe(sheet, i, get_col(headers, "Estado"), "Respondido")
                print(f"  ✅ {nombre} ({empresa}) — Respondió (revisar manualmente).")
                skip_count += 1
                continue

        # ── Determinar qué email enviar ──
        fecha1 = parse_date(record.get("Fecha_Email_1"))
        fecha2 = parse_date(record.get("Fecha_Email_2"))
        fecha3 = parse_date(record.get("Fecha_Email_3"))
        fecha4 = parse_date(record.get("Fecha_Email_4"))

        email_num = None
        if not fecha1:
            email_num = 1
        elif not fecha2 and (today - fecha1).days >= follow_up_days[0]:
            email_num = 2
        elif fecha2 and not fecha3 and (today - fecha2).days >= follow_up_days[1]:
            email_num = 3
        elif fecha3 and not fecha4 and (today - fecha3).days >= follow_up_days[2]:
            email_num = 4

        if not email_num:
            skip_count += 1
            continue

        print(f"\n📧 [{i-1}/{len(records)}] {nombre} — {empresa} (Email {email_num})")

        if email_num == 1 and not investigacion:
            print(f"  🔍 Investigando {empresa}...")
            investigacion = research_company(empresa)
            if investigacion:
                update_cell_safe(sheet, i, get_col(headers, "Investigacion"), investigacion)
            time.sleep(1)

        print(f"  ✍️  Generando email con IA...")
        email_data = generate_email(
            anthropic_client,
            config,
            {"nombre": nombre, "empresa": empresa, "cargo": cargo, "email": email},
            investigacion,
            email_num,
            asunto_original,
        )

        if not email_data:
            print(f"  ❌ No se pudo generar el email. Saltando.")
            continue

        asunto = email_data["asunto"]
        cuerpo = email_data["cuerpo"]

        asunto_envio = f"Re: {asunto_original}" if email_num > 1 and asunto_original else asunto

        orig_message_id = ""
        if thread_id and email_num > 1:
            orig_message_id = get_thread_message_id(gmail, thread_id)

        try:
            sent = send_email(
                gmail,
                config["from_email"],
                email,
                asunto_envio,
                cuerpo,
                thread_id=thread_id if email_num > 1 else None,
                message_id=orig_message_id if email_num > 1 else None,
            )
            sent_count += 1
            print(f"  ✅ Email {email_num} enviado a {email}")

            fecha_col = get_col(headers, f"Fecha_Email_{email_num}")
            estado_map = {
                1: "Email1_Enviado",
                2: "Email2_Enviado",
                3: "Email3_Enviado",
                4: "Email4_Enviado",
            }
            update_cell_safe(sheet, i, fecha_col, str(today))
            update_cell_safe(sheet, i, get_col(headers, "Estado"), estado_map[email_num])

            if email_num == 1:
                update_cell_safe(sheet, i, get_col(headers, "Thread_ID"), sent.get("threadId", ""))
                update_cell_safe(sheet, i, get_col(headers, "Asunto_Email_1"), asunto)

        except Exception as e:
            print(f"  ❌ Error enviando email a {email}: {e}")

        time.sleep(config.get("delay_between_emails", 30))

    print(f"\n{'─'*50}")
    print(f"🏁 Proceso completado.")
    print(f"   ✅ Emails enviados:      {sent_count}")
    print(f"   ⭐ Interesados:          {interesados}")
    print(f"   🚫 No interesados:       {no_interesados}")
    print(f"   ⏭️  Contactos saltados:   {skip_count}")


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("  Certfika Email Automation 🚀")
    print("=" * 50)
    process_contacts()
