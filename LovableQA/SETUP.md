# LovableQA - QA Completo para Proyectos Lovable

Herramienta de analisis estatico que ejecuta 9 tipos de QA sobre proyectos construidos con Lovable (React + Supabase/TypeScript). Genera un reporte con score, hallazgos detallados, y un analisis inteligente con AI.

## Modulos de Analisis

### 1. Seguridad (`security`)
- Secretos/API keys hardcodeados
- Vulnerabilidades XSS (dangerouslySetInnerHTML, eval, innerHTML)
- Inyeccion SQL en queries Supabase
- Supabase: service_role en frontend, RLS ausente
- CORS inseguro, almacenamiento inseguro (localStorage)
- .gitignore y archivos .env
- Dependencias con vulnerabilidades conocidas

### 2. Escalabilidad (`scale`)
- Re-renders innecesarios en React
- Queries N+1 (fetch dentro de .map)
- SELECT * sin paginacion
- Falta de caching (react-query/SWR)
- Bundle size (dependencias pesadas)
- Arquitectura de componentes

### 3. Accesibilidad (`a11y`)
- WCAG 2.1: alt text, labels, roles semanticos
- Focus visible y navegacion por teclado
- Jerarquia de headings
- Landmarks (<main>, skip links, lang)
- Contraste de colores (heuristica)
- Media: captions, transcripts, autoplay

### 4. SEO (`seo`)
- Meta tags (title, description, viewport, charset)
- Open Graph y Twitter Cards
- robots.txt y sitemap.xml
- HTML semantico vs div soup
- Routing (HashRouter vs BrowserRouter, 404)
- SSR/SSG detection, structured data

### 5. UI/UX Consistencia (`ui`)
- Tailwind classes conflictivas
- Consistencia de colores, spacing, fonts
- Componentes duplicados o similares
- Responsive breakpoints (sm, md, lg)
- Design system (shadcn, tokens, theme)
- z-index, !important, inline styles

### 6. Calidad de Codigo (`quality`)
- TypeScript `any` usage
- console.log olvidados
- TODO/FIXME/HACK acumulados
- @ts-ignore, eslint-disable
- Empty catch blocks
- Configuracion: strict mode, ESLint, Prettier
- Codigo muerto (exports sin usar)

### 7. Testing Coverage (`testing`)
- Frameworks instalados (Vitest, Jest, Cypress, Playwright)
- Ratio test files vs source files
- Flujos criticos sin tests (auth, payments, forms)
- Calidad de tests (assertions, skipped tests)
- CI/CD test configuration
- E2E, unit, integration coverage

### 8. Performance / Core Web Vitals (`perf`)
- Imagenes: formato, tamano, lazy loading
- Code splitting (React.lazy, Suspense)
- Render-blocking scripts/CSS
- Fonts: formato, preconnect
- Memory leaks (timers, event listeners sin cleanup)
- Bundle analysis, compression
- Loading states y skeletons

### 9. API/Backend Health (`api`)
- Supabase Edge Functions: error handling, auth, validation
- Rate limiting
- CORS en functions
- Database: SECURITY DEFINER, search_path, triggers
- Frontend: API calls sin error handling, URLs hardcodeadas
- Validation library (Zod), error boundaries

## Requisitos

- Python 3.9+
- (Opcional) API key de Anthropic para analisis con IA

## Instalacion

```bash
cd LovableQA
pip install -r requirements.txt
```

## Configuracion

Opcion A - Variable de entorno:
```bash
export ANTHROPIC_API_KEY=sk-ant-xxxxx
```

Opcion B - Archivo config.json:
```bash
cp config.example.json config.json
# Editar config.json con tu API key
```

## Uso

### QA completo (todos los modulos)
```bash
python qa.py /ruta/a/tu/proyecto-lovable
```

### Modulos especificos
```bash
python qa.py /ruta/al/proyecto --modules security,perf,testing
python qa.py /ruta/al/proyecto -m a11y,seo,ui
python qa.py /ruta/al/proyecto -m quality,api
```

### Sin analisis AI
```bash
python qa.py /ruta/al/proyecto --no-ai
```

### Con salida personalizada y modo verbose
```bash
python qa.py /ruta/al/proyecto --output mi-reporte.txt --verbose
```

## Output

Genera dos archivos:
- `qa-report-YYYYMMDD-HHMMSS.txt` - Reporte legible con score, tabla resumen, hallazgos y recomendaciones
- `qa-report-YYYYMMDD-HHMMSS.json` - Datos estructurados para integracion con otras herramientas

### QA Score (0-100)

| Grado | Score | Significado |
|-------|-------|-------------|
| A     | 90+   | Excelente - pocas mejoras necesarias |
| B     | 75-89 | Bueno - algunas mejoras recomendadas |
| C     | 60-74 | Regular - varias areas necesitan atencion |
| D     | 40-59 | Deficiente - problemas significativos |
| F     | <40   | Critico - requiere atencion inmediata |

Formula: 100 - (CRITICAL * 15) - (HIGH * 8) - (MEDIUM * 3)

## Estructura de archivos

```
LovableQA/
  qa.py                      # Entry point principal
  security_scanner.py        # Modulo: seguridad
  scalability_scanner.py     # Modulo: escalabilidad
  a11y_scanner.py            # Modulo: accesibilidad
  seo_scanner.py             # Modulo: SEO
  ui_consistency_scanner.py  # Modulo: UI/UX consistencia
  code_quality_scanner.py    # Modulo: calidad de codigo
  testing_scanner.py         # Modulo: testing coverage
  performance_scanner.py     # Modulo: performance/CWV
  api_scanner.py             # Modulo: API/backend health
  report_generator.py        # Generador de reportes + AI
  config.json                # Configuracion (no commitear)
  config.example.json        # Template de configuracion
  requirements.txt           # Dependencias Python
  SETUP.md                   # Esta documentacion
```
