# Certfika Email Automation — Guía de Setup

Esta guía te lleva paso a paso para dejar la automatización funcionando.
Tiempo estimado: 20-30 minutos.

---

## Estructura de archivos

```
certfika_automation/
├── emailer.py          ← Script principal
├── config.json         ← Tu configuración (editarlo)
├── credentials.json    ← Lo descargás de Google Cloud (paso 2)
├── token.json          ← Se genera solo la primera vez
└── requirements.txt    ← Dependencias Python
```

---

## Paso 1 — Instalar Python y dependencias

Necesitás Python 3.9 o superior. Verificá con:

```bash
python --version
```

Luego instalá las dependencias:

```bash
pip install -r requirements.txt
```

---

## Paso 2 — Configurar Google Cloud (Gmail + Sheets API)

### 2.1 — Crear proyecto en Google Cloud

1. Ir a [console.cloud.google.com](https://console.cloud.google.com)
2. Crear un nuevo proyecto (ej: "Certfika Automation")
3. Seleccionarlo como proyecto activo

### 2.2 — Activar las APIs necesarias

En el menú lateral: **APIs y servicios → Biblioteca**

Buscar y activar:
- ✅ **Gmail API**
- ✅ **Google Sheets API**

### 2.3 — Crear credenciales OAuth2

1. Ir a **APIs y servicios → Credenciales**
2. Clic en **"+ Crear credenciales" → "ID de cliente OAuth"**
3. Tipo de aplicación: **"Aplicación de escritorio"**
4. Nombre: "Certfika Emailer" (cualquier nombre)
5. Clic en **Crear**
6. Descargar el archivo JSON
7. Renombrarlo a `credentials.json` y copiarlo en esta carpeta

### 2.4 — Configurar pantalla de consentimiento OAuth

1. Ir a **APIs y servicios → Pantalla de consentimiento OAuth**
2. Tipo: **Externo** (aunque sea solo para uso interno, es más fácil)
3. Completar nombre de app y email de contacto
4. En "Usuarios de prueba", agregar el email de HumanTech desde el que van a salir los mails
5. Guardar

> ⚠️ No hace falta publicar la app. Con estar en "modo de prueba" alcanza.

---

## Paso 3 — Preparar tu Google Sheet

Tu Sheet necesita estas columnas **exactamente** (el script agrega las de tracking solo):

| Columna obligatoria | Descripción |
|---------------------|-------------|
| `Nombre`            | Nombre del contacto |
| `Empresa`           | Nombre de la empresa |
| `Email`             | Email de contacto |

El script va a agregar automáticamente estas columnas la primera vez que corra:

| Columna automática | Descripción |
|--------------------|-------------|
| `Estado`           | Pendiente / Email1_Enviado / … / Respondido / Descartado |
| `Thread_ID`        | ID del hilo de Gmail (para mantener el threading) |
| `Asunto_Email_1`   | Asunto del primer email enviado |
| `Investigacion`    | Resumen de la búsqueda online de la empresa |
| `Fecha_Email_1`    | Fecha de envío del primer email |
| `Fecha_Email_2`    | Fecha de envío del follow-up 1 |
| `Fecha_Email_3`    | Fecha de envío del follow-up 2 |
| `Fecha_Email_4`    | Fecha de envío del follow-up 3 |
| `Notas`            | Campo libre para notas manuales |

**Importante:** Si querés marcar un contacto como "Respondido" o "Descartado" manualmente, editá la columna `Estado` directamente en el Sheet.

---

## Paso 4 — Configurar config.json

Abrí el archivo `config.json` y completá:

```json
{
  "spreadsheet_id": "1aBcDeFgHiJkLmNoPqRsTuVwXyZ...",  ← ID del Sheet
  "from_email": "tu@humantech.com.ar",
  "anthropic_api_key": "sk-ant-...",
  "follow_up_days": [4, 4, 6],
  "delay_between_emails": 30,
  "firma": "Tu Nombre\nEquipo Certfika\ncertfika.com"
}
```

**¿Dónde está el ID del Sheet?**
En la URL: `docs.google.com/spreadsheets/d/`**`ESTE_ES_EL_ID`**`/edit`

**¿Cómo obtengo la API Key de Anthropic?**
En [console.anthropic.com](https://console.anthropic.com) → API Keys → Create Key

---

## Paso 5 — Primera ejecución (autenticación)

La primera vez que corras el script, se abrirá el navegador para autenticarte:

```bash
python emailer.py
```

1. Se abre el navegador con la pantalla de Google
2. Iniciás sesión con el email de HumanTech
3. Aceptás los permisos (Gmail + Sheets)
4. Se crea `token.json` automáticamente
5. El script empieza a procesar contactos

A partir de ese momento, el script corre sin necesidad de abrir el navegador.

---

## Paso 6 — Programar ejecución diaria (opcional)

### En Mac/Linux (cron)

```bash
# Abrir crontab
crontab -e

# Ejecutar todos los días a las 9am
0 9 * * * cd /ruta/a/certfika_automation && python emailer.py >> log.txt 2>&1
```

### En Windows (Task Scheduler)

1. Buscar "Programador de tareas" en el menú inicio
2. Crear tarea básica
3. Disparador: Diariamente a las 9:00 AM
4. Acción: Iniciar programa → `python` con argumentos `emailer.py`
5. Directorio de inicio: la carpeta del proyecto

---

## Secuencia de emails

| Email | Cuándo | Tipo |
|-------|--------|------|
| Email 1 | Día 0 | Cold email personalizado (investigación de empresa) |
| Email 2 | Día 4 | Follow-up 1 — recordatorio breve |
| Email 3 | Día 8 | Follow-up 2 — ángulo nuevo / beneficio específico |
| Email 4 | Día 14 | Follow-up 3 — breakup email, cierre del ciclo |

Si en cualquier momento el contacto responde, el script lo detecta automáticamente y marca como **Respondido** (no envía más emails).

---

## Preguntas frecuentes

**¿Desde qué email salen los mails?**
Desde la cuenta de Google Workspace de HumanTech que configurés en `from_email`.

**¿Cómo le respondo a alguien que contestó?**
Los replies del contacto llegarán a tu inbox de Gmail normalmente. Respondé desde ahí.

**¿Puedo desactivar un contacto?**
Sí, cambiá su `Estado` a "Descartado" en el Sheet y el script lo omitirá.

**¿Qué pasa si el script corre dos veces el mismo día?**
No envía emails duplicados — verifica las fechas antes de enviar.

**¿Puedo editar un email antes de enviarlo?**
Por ahora el proceso es automático. Si querés revisión previa, avisame y lo adaptamos para que genere borradores en Gmail en vez de enviar directamente.

---

## Soporte

Cualquier problema, compartí el error exacto de la terminal y te ayudo a resolverlo.
