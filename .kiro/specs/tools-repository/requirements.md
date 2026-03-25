# Documento de Requisitos — Repositorio de Herramientas

## Introducción

Este documento define los requisitos para un repositorio monorepo que aloja múltiples herramientas de desarrollo y negocio. La primera herramienta existente (MailingFollow) es un sistema de automatización de emails personalizados con seguimiento, construido en Python. El repositorio debe proveer una estructura organizada, patrones comunes y un framework que facilite agregar nuevas herramientas en el futuro.

## Glosario

- **Repositorio**: El monorepo raíz que contiene todas las herramientas
- **Herramienta**: Un proyecto independiente dentro del repositorio que resuelve una necesidad específica de desarrollo o negocio
- **Manifiesto**: Archivo de metadatos (`tool.json`) que describe una herramienta: nombre, versión, descripción, dependencias y comandos disponibles
- **CLI_Central**: Interfaz de línea de comandos en la raíz del repositorio que permite listar, configurar y ejecutar herramientas
- **Catálogo**: Registro centralizado generado automáticamente a partir de los manifiestos de cada herramienta
- **Utilidades_Compartidas**: Módulo Python compartido (`shared/`) que provee funciones reutilizables entre herramientas (logging, configuración, autenticación Google)
- **MailingFollow**: Herramienta existente de automatización de cold emails personalizados con seguimiento de respuestas vía Gmail y Google Sheets

## Requisitos

### Requisito 1: Estructura del Repositorio

**Historia de Usuario:** Como desarrollador, quiero una estructura de directorios estandarizada para el monorepo, para que cada herramienta tenga una ubicación predecible y consistente.

#### Criterios de Aceptación

1. THE Repositorio SHALL organizar cada herramienta en un directorio independiente bajo la raíz con su propio archivo de dependencias y documentación
2. THE Repositorio SHALL contener un archivo README.md en la raíz que liste todas las herramientas disponibles con una descripción breve de cada una
3. THE Repositorio SHALL contener un directorio `shared/` para Utilidades_Compartidas reutilizables entre herramientas
4. WHEN se agrega una nueva Herramienta al Repositorio, THE Repositorio SHALL validar que la Herramienta contenga un Manifiesto (`tool.json`) con los campos obligatorios: nombre, versión, descripción y autor

### Requisito 2: Manifiesto de Herramienta

**Historia de Usuario:** Como desarrollador, quiero que cada herramienta tenga un archivo de metadatos estandarizado, para que el repositorio pueda descubrir y catalogar herramientas automáticamente.

#### Criterios de Aceptación

1. THE Manifiesto SHALL ser un archivo JSON llamado `tool.json` ubicado en la raíz del directorio de cada Herramienta
2. THE Manifiesto SHALL contener los campos obligatorios: `name` (string), `version` (string semver), `description` (string), `author` (string), `language` (string) y `entry_point` (string con el comando principal de ejecución)
3. THE Manifiesto SHALL contener un campo opcional `dependencies` (lista de strings) que indique las dependencias del sistema o de otras herramientas del Repositorio
4. THE Manifiesto SHALL contener un campo opcional `commands` (objeto) que mapee nombres de comandos a sus scripts de ejecución
5. WHEN el Manifiesto contiene un campo `version` que no sigue el formato semver (MAJOR.MINOR.PATCH), THE CLI_Central SHALL reportar un error de validación indicando el formato esperado

### Requisito 3: Catálogo Centralizado de Herramientas

**Historia de Usuario:** Como desarrollador, quiero un catálogo generado automáticamente con todas las herramientas disponibles, para poder descubrir y entender qué herramientas existen sin revisar cada directorio.

#### Criterios de Aceptación

1. THE CLI_Central SHALL generar el Catálogo leyendo los archivos Manifiesto de todos los directorios de herramientas en el Repositorio
2. THE Catálogo SHALL mostrar para cada Herramienta: nombre, versión, descripción, lenguaje y comandos disponibles
3. WHEN una Herramienta no contiene un Manifiesto válido, THE CLI_Central SHALL excluir esa Herramienta del Catálogo y emitir una advertencia indicando el directorio y el problema encontrado
4. THE CLI_Central SHALL serializar el Catálogo en formato JSON y escribirlo en un archivo `catalog.json` en la raíz del Repositorio
5. WHEN se ejecuta el comando de generación del Catálogo, THE CLI_Central SHALL parsear cada Manifiesto y producir el archivo `catalog.json`
6. FOR ALL Manifiestos válidos, parsear el Catálogo serializado y volver a serializarlo SHALL producir un resultado equivalente al original (propiedad round-trip)

### Requisito 4: CLI Central

**Historia de Usuario:** Como desarrollador, quiero una interfaz de línea de comandos centralizada, para poder listar, configurar y ejecutar cualquier herramienta del repositorio desde un solo punto de entrada.

#### Criterios de Aceptación

1. THE CLI_Central SHALL proveer un comando `list` que muestre todas las herramientas registradas en el Catálogo con su nombre, versión y descripción
2. THE CLI_Central SHALL proveer un comando `run <nombre_herramienta> [argumentos]` que ejecute el entry_point de la Herramienta especificada pasándole los argumentos proporcionados
3. WHEN el usuario ejecuta `run` con un nombre de Herramienta que no existe en el Catálogo, THE CLI_Central SHALL mostrar un mensaje de error indicando que la herramienta no fue encontrada y listar las herramientas disponibles
4. THE CLI_Central SHALL proveer un comando `init <nombre_herramienta>` que cree la estructura base de una nueva Herramienta con un Manifiesto plantilla, un README.md y un archivo de dependencias vacío
5. WHEN el usuario ejecuta `init` con un nombre que ya existe como directorio en el Repositorio, THE CLI_Central SHALL mostrar un error indicando que el directorio ya existe

### Requisito 5: Utilidades Compartidas

**Historia de Usuario:** Como desarrollador, quiero un módulo de utilidades compartidas, para reutilizar funciones comunes entre herramientas y evitar duplicación de código.

#### Criterios de Aceptación

1. THE Utilidades_Compartidas SHALL proveer un módulo de autenticación Google reutilizable que gestione credenciales OAuth2, refresco de tokens y almacenamiento del token
2. THE Utilidades_Compartidas SHALL proveer un módulo de logging estandarizado que formatee mensajes con timestamp, nivel de severidad y nombre de la Herramienta que lo invoca
3. THE Utilidades_Compartidas SHALL proveer un módulo de carga de configuración que lea archivos JSON y valide la presencia de campos obligatorios definidos por cada Herramienta
4. WHEN una Herramienta importa un módulo de Utilidades_Compartidas que no existe, THE sistema SHALL lanzar un ImportError con un mensaje descriptivo indicando los módulos disponibles
5. THE Utilidades_Compartidas SHALL ser instalables como paquete Python local (vía `pip install -e shared/`) para que cada Herramienta pueda importarlas sin manipular sys.path

### Requisito 6: Integración de MailingFollow

**Historia de Usuario:** Como desarrollador, quiero integrar la herramienta MailingFollow existente en la estructura del repositorio, para que siga el estándar definido y aproveche las utilidades compartidas.

#### Criterios de Aceptación

1. THE Repositorio SHALL contener la Herramienta MailingFollow en el directorio `MailingFollow/` con un Manifiesto válido que describa sus tres scripts: `emailer.py`, `import_contacts.py` y `verify_emails.py`
2. THE MailingFollow SHALL incluir un README.md actualizado que documente el propósito de la herramienta, los requisitos previos (APIs de Google, API key de Anthropic), la configuración necesaria y los comandos disponibles
3. WHEN el usuario ejecuta `run MailingFollow emailer` a través de la CLI_Central, THE CLI_Central SHALL ejecutar el script `emailer.py` de MailingFollow en el directorio correcto
4. THE MailingFollow SHALL excluir archivos sensibles (`credentials.json`, `token.json`, `config.json`, archivos CSV) del control de versiones mediante entradas en `.gitignore`
5. THE MailingFollow SHALL incluir un archivo `config.example.json` con la estructura de configuración esperada y valores placeholder en lugar de credenciales reales

### Requisito 7: Framework para Nuevas Herramientas

**Historia de Usuario:** Como desarrollador, quiero un proceso estandarizado para agregar nuevas herramientas, para que cualquier miembro del equipo pueda contribuir herramientas que sigan los mismos patrones.

#### Criterios de Aceptación

1. WHEN el usuario ejecuta `init <nombre>` a través de la CLI_Central, THE CLI_Central SHALL crear un directorio con la siguiente estructura: `<nombre>/tool.json`, `<nombre>/README.md`, `<nombre>/requirements.txt` y `<nombre>/main.py`
2. THE CLI_Central SHALL generar el Manifiesto plantilla con el nombre proporcionado, versión "0.1.0", campos de descripción y autor vacíos, y el entry_point apuntando a `main.py`
3. THE CLI_Central SHALL generar el README.md plantilla con secciones predefinidas: Descripción, Requisitos, Configuración, Uso y Estructura de archivos
4. WHEN el usuario ejecuta `init` sin proporcionar un nombre de herramienta, THE CLI_Central SHALL mostrar un mensaje de uso indicando el formato correcto del comando

### Requisito 8: Gestión de Dependencias

**Historia de Usuario:** Como desarrollador, quiero que cada herramienta gestione sus dependencias de forma aislada, para evitar conflictos entre versiones de paquetes de distintas herramientas.

#### Criterios de Aceptación

1. THE Repositorio SHALL documentar en el README.md raíz la recomendación de usar un entorno virtual Python independiente por cada Herramienta
2. THE CLI_Central SHALL proveer un comando `setup <nombre_herramienta>` que cree un entorno virtual en el directorio de la Herramienta e instale sus dependencias desde `requirements.txt`
3. WHEN el archivo `requirements.txt` de una Herramienta no existe o está vacío, THE CLI_Central SHALL crear el entorno virtual sin instalar dependencias adicionales y emitir una advertencia
4. IF el comando `setup` falla durante la instalación de dependencias, THEN THE CLI_Central SHALL mostrar el error completo de pip y mantener el entorno virtual creado para depuración

### Requisito 9: Control de Versiones y Seguridad

**Historia de Usuario:** Como desarrollador, quiero que el repositorio tenga configuraciones de seguridad adecuadas, para que credenciales y datos sensibles no se suban accidentalmente al control de versiones.

#### Criterios de Aceptación

1. THE Repositorio SHALL contener un archivo `.gitignore` en la raíz que excluya patrones comunes de archivos sensibles: `**/credentials.json`, `**/token.json`, `**/config.json`, `**/*.csv`, `**/__pycache__/`, `**/.env` y `**/venv/`
2. THE Repositorio SHALL contener un archivo `.gitignore` que excluya directorios de entornos virtuales Python (`**/venv/`, `**/.venv/`, `**/env/`)
3. WHEN el usuario ejecuta `init` para crear una nueva Herramienta, THE CLI_Central SHALL generar un archivo `config.example.json` vacío como plantilla de configuración en el directorio de la Herramienta
