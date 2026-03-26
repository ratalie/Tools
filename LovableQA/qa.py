"""
LovableQA - QA Automatizado para Proyectos Lovable
====================================================
Herramienta completa de QA que ejecuta 7 tipos de analisis sobre
proyectos construidos con Lovable (React + Supabase/TypeScript):

1. Seguridad          2. Escalabilidad      3. Accesibilidad (a11y)
4. SEO                5. UI/UX Consistencia  6. Calidad de Codigo
7. Testing Coverage   8. Performance/CWV     9. API/Backend Health

Uso:
    python qa.py <ruta_al_proyecto> [opciones]

Opciones:
    --no-ai          Omitir analisis con IA (no requiere API key)
    --modules <list> Modulos a ejecutar (separados por coma)
                     Opciones: security,scale,a11y,seo,ui,quality,testing,perf,api
                     Default: todos
    --output <path>  Ruta de salida para el reporte
    --verbose        Mostrar hallazgos criticos en tiempo real
"""

import argparse
import json
import os
import sys
import time

from security_scanner import SecurityScanner, SecurityReport
from scalability_scanner import ScalabilityScanner, ScalabilityReport
from a11y_scanner import A11yScanner, A11yReport
from seo_scanner import SEOScanner, SEOReport
from ui_consistency_scanner import UIConsistencyScanner, UIReport
from code_quality_scanner import CodeQualityScanner, CodeQualityReport
from testing_scanner import TestingScanner, TestingReport
from performance_scanner import PerformanceScanner, PerfReport
from api_scanner import APIScanner, APIReport
from report_generator import generate_full_report, generate_ai_summary


CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

ALL_MODULES = ["security", "scale", "a11y", "seo", "ui", "quality", "testing", "perf", "api"]

MODULE_INFO = {
    "security":  ("Seguridad",           SecurityScanner,       SecurityReport),
    "scale":     ("Escalabilidad",       ScalabilityScanner,    ScalabilityReport),
    "a11y":      ("Accesibilidad",       A11yScanner,           A11yReport),
    "seo":       ("SEO",                 SEOScanner,            SEOReport),
    "ui":        ("UI/UX Consistencia",  UIConsistencyScanner,  UIReport),
    "quality":   ("Calidad de Codigo",   CodeQualityScanner,    CodeQualityReport),
    "testing":   ("Testing Coverage",    TestingScanner,        TestingReport),
    "perf":      ("Performance/CWV",     PerformanceScanner,    PerfReport),
    "api":       ("API/Backend Health",  APIScanner,            APIReport),
}


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def validate_project(project_path: str) -> bool:
    """Verifica que la ruta sea un proyecto Lovable/React valido."""
    if not os.path.isdir(project_path):
        print(f"  Error: '{project_path}' no es un directorio valido.")
        return False

    markers = ["package.json", "src"]
    found = [m for m in markers if os.path.exists(os.path.join(project_path, m))]

    if not found:
        print(f"  Advertencia: No se encontraron marcadores tipicos de un proyecto React.")
        print(f"  Buscados: {markers}")
        resp = input("  Continuar de todas formas? (s/n): ").strip().lower()
        if resp != "s":
            return False

    return True


def get_project_name(project_path: str) -> str:
    """Obtiene el nombre del proyecto desde package.json o el directorio."""
    pkg_path = os.path.join(project_path, "package.json")
    if os.path.exists(pkg_path):
        try:
            with open(pkg_path, "r") as f:
                pkg = json.load(f)
            return pkg.get("name", os.path.basename(project_path))
        except Exception:
            pass
    return os.path.basename(project_path)


def print_phase_summary(name, report, phase_num, verbose=False):
    """Imprime resumen de una fase de escaneo."""
    summary = report.get_summary()
    total = len(report.findings)
    print(f"  Archivos escaneados: {report.files_scanned}")
    print(f"  Hallazgos: {total}")
    if total > 0:
        parts = []
        for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            count = summary.get(sev, 0)
            if count > 0:
                parts.append(f"{sev}: {count}")
        print(f"    {' | '.join(parts)}")

    if verbose:
        for f in report.findings:
            if f.severity in ("CRITICAL", "HIGH"):
                loc = f.file_path
                if hasattr(f, 'line_number') and f.line_number:
                    loc += f":{f.line_number}"
                print(f"    [{f.severity}] {f.title} - {loc}")


def main():
    parser = argparse.ArgumentParser(
        description="LovableQA - QA completo para proyectos Lovable (React + Supabase)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modulos disponibles:
  security  - Secretos, XSS, inyecciones, RLS, CORS
  scale     - N+1 queries, re-renders, cache, bundle size
  a11y      - Accesibilidad WCAG 2.1 (alt, labels, focus, semantics)
  seo       - Meta tags, OG, robots, sitemap, semantic HTML
  ui        - Tailwind conflicts, responsive, design system, colores
  quality   - TypeScript any, console.log, TODO/FIXME, tech debt
  testing   - Test coverage, frameworks, flujos criticos sin tests
  perf      - Core Web Vitals, lazy loading, images, bundle
  api       - Edge functions, error handling, validation, rate limiting

Ejemplos:
  python qa.py ./mi-proyecto                    # Todos los modulos
  python qa.py ./mi-proyecto --modules security,perf
  python qa.py ./mi-proyecto --no-ai --verbose
        """,
    )
    parser.add_argument("project_path", help="Ruta al proyecto Lovable a analizar")
    parser.add_argument("--no-ai", action="store_true", help="Omitir analisis con IA")
    parser.add_argument("--modules", "-m", help="Modulos a ejecutar (separados por coma). Default: todos")
    parser.add_argument("--output", "-o", help="Ruta de salida para el reporte")
    parser.add_argument("--verbose", "-v", action="store_true", help="Mostrar hallazgos criticos en tiempo real")

    args = parser.parse_args()
    project_path = os.path.abspath(args.project_path)

    # Parse modules
    if args.modules:
        modules = [m.strip().lower() for m in args.modules.split(",")]
        invalid = [m for m in modules if m not in ALL_MODULES]
        if invalid:
            print(f"  Error: Modulos invalidos: {', '.join(invalid)}")
            print(f"  Disponibles: {', '.join(ALL_MODULES)}")
            sys.exit(1)
    else:
        modules = ALL_MODULES

    print("=" * 60)
    print("  LovableQA - Analisis Completo de Calidad")
    print("=" * 60)

    if not validate_project(project_path):
        sys.exit(1)

    project_name = get_project_name(project_path)
    print(f"\n  Proyecto: {project_name}")
    print(f"  Ruta:     {project_path}")
    print(f"  Modulos:  {', '.join(modules)}")

    config = load_config()
    reports = {}
    start_time = time.time()

    # Run each selected module
    for phase_num, module_key in enumerate(modules, 1):
        name, ScannerClass, ReportClass = MODULE_INFO[module_key]

        print(f"\n{'─' * 60}")
        print(f"  FASE {phase_num}/{len(modules)}: {name}")
        print(f"{'─' * 60}")

        scanner = ScannerClass(project_path)
        report = scanner.scan()
        reports[module_key] = report

        print_phase_summary(name, report, phase_num, args.verbose)

    # Fill empty reports for unselected modules
    for key in ALL_MODULES:
        if key not in reports:
            _, _, ReportClass = MODULE_INFO[key]
            reports[key] = ReportClass()

    # AI Analysis
    ai_summary = None
    if not args.no_ai:
        api_key = config.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            print(f"\n{'─' * 60}")
            print(f"  FASE FINAL: Analisis Inteligente (AI)")
            print(f"{'─' * 60}")
            try:
                from anthropic import Anthropic
                client = Anthropic(api_key=api_key)
                ai_summary = generate_ai_summary(client, reports, project_name, modules)
                print("  Analisis AI completado.")
            except Exception as e:
                print(f"  Error en analisis AI: {e}")
        else:
            print("\n  [Info] Sin API key de Anthropic. Usa --no-ai o configura ANTHROPIC_API_KEY.")
            print("         El reporte se generara sin analisis AI.")

    # Generate report
    print(f"\n{'─' * 60}")
    print("  Generando Reporte Final...")
    print(f"{'─' * 60}")

    report_text = generate_full_report(
        reports=reports,
        project_name=project_name,
        project_path=project_path,
        modules=modules,
        ai_summary=ai_summary,
        output_path=args.output,
    )

    elapsed = time.time() - start_time

    # Final score
    total_findings = sum(len(r.findings) for r in reports.values())
    total_critical = sum(r.summary.get("CRITICAL", 0) for r in reports.values() if r.summary)
    total_high = sum(r.summary.get("HIGH", 0) for r in reports.values() if r.summary)

    print(f"\n{'=' * 60}")
    print(f"  RESULTADO FINAL")
    print(f"{'=' * 60}")
    print(f"  Total hallazgos:  {total_findings}")
    print(f"  Criticos:         {total_critical}")
    print(f"  Altos:            {total_high}")
    print(f"  Tiempo total:     {elapsed:.1f}s")
    print(f"  QA completado.")


if __name__ == "__main__":
    main()
