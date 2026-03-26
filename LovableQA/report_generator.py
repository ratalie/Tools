"""
Report Generator for LovableQA
================================
Genera reportes de QA combinando hallazgos de todos los modulos,
con analisis inteligente via Claude AI.
"""

import json
import os
from datetime import datetime


MODULE_NAMES = {
    "security": "Seguridad",
    "scale": "Escalabilidad",
    "a11y": "Accesibilidad",
    "seo": "SEO",
    "ui": "UI/UX Consistencia",
    "quality": "Calidad de Codigo",
    "testing": "Testing Coverage",
    "perf": "Performance/CWV",
    "api": "API/Backend",
}


def generate_ai_summary(anthropic_client, reports: dict, project_name: str, modules: list) -> str:
    """Usa Claude para generar un resumen ejecutivo inteligente del QA."""

    # Build findings summary per module
    modules_data = {}
    for key in modules:
        report = reports.get(key)
        if not report or not report.findings:
            continue

        findings = []
        for f in report.findings[:15]:  # Top 15 per module
            entry = {
                "severity": f.severity,
                "category": f.category,
                "title": f.title,
                "file": f.file_path,
            }
            if hasattr(f, "line_number") and f.line_number:
                entry["line"] = f.line_number
            findings.append(entry)

        modules_data[MODULE_NAMES.get(key, key)] = {
            "total": len(report.findings),
            "summary": report.summary if report.summary else report.get_summary(),
            "top_findings": findings,
        }

        # Include metrics if available
        if hasattr(report, "metrics") and report.metrics:
            clean_metrics = {}
            for k, v in report.metrics.items():
                if isinstance(v, (str, int, float, bool)):
                    clean_metrics[k] = v
                elif isinstance(v, list) and len(v) < 10:
                    clean_metrics[k] = v
            if clean_metrics:
                modules_data[MODULE_NAMES.get(key, key)]["metrics"] = clean_metrics

    prompt = f"""Eres un QA Lead senior especializado en proyectos React + Supabase (proyectos Lovable).
Analiza estos hallazgos de un escaneo automatizado completo y genera un reporte ejecutivo.

PROYECTO: {project_name}
MODULOS ANALIZADOS: {', '.join(modules)}

RESULTADOS POR MODULO:
{json.dumps(modules_data, indent=2, default=str, ensure_ascii=False)}

Genera un reporte en espanol con estas secciones:

1. RESUMEN EJECUTIVO (2-3 parrafos)
   - Estado general del proyecto
   - Areas mas fuertes y mas debiles
   - Riesgos principales

2. HALLAZGOS CRITICOS (solo los que requieren accion inmediata)
   - Explicacion clara del riesgo
   - Impacto potencial si no se atiende

3. TOP 10 RECOMENDACIONES (las mas impactantes de todos los modulos)
   - Ordenadas por prioridad/impacto
   - Con pasos concretos de remediacion
   - Indicar a que modulo pertenece cada una

4. QUICK WINS (cosas faciles de arreglar con alto impacto)

5. PLAN DE ACCION SUGERIDO
   - Semana 1: urgentes (seguridad, bugs criticos)
   - Semana 2-3: importantes (escalabilidad, testing, performance)
   - Mes 1: mejoras (a11y, SEO, UI consistency, code quality)

Usa un tono profesional pero directo. No repitas el mismo hallazgo.
Si no hay hallazgos criticos en alguna area, destaca lo positivo."""

    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except Exception as e:
        return f"[Error generando analisis AI: {e}]"


def format_findings_table(findings, max_items=40):
    """Formatea hallazgos como tabla de texto."""
    if not findings:
        return "  No se encontraron hallazgos.\n"

    lines = []
    severity_icons = {
        "CRITICAL": "[!!!]",
        "HIGH": "[!! ]",
        "MEDIUM": "[!  ]",
        "LOW": "[.  ]",
        "INFO": "[i  ]",
    }

    for f in findings[:max_items]:
        icon = severity_icons.get(f.severity, "[?  ]")
        loc = f.file_path
        if hasattr(f, "line_number") and f.line_number:
            loc += f":{f.line_number}"
        lines.append(f"  {icon} {f.severity:<8} | {f.category:<25} | {f.title}")
        lines.append(f"           {loc}")
        if hasattr(f, "recommendation") and f.recommendation:
            lines.append(f"           -> {f.recommendation}")
        lines.append("")

    if len(findings) > max_items:
        lines.append(f"  ... y {len(findings) - max_items} hallazgos mas.")

    return "\n".join(lines)


def generate_full_report(reports: dict, project_name: str, project_path: str,
                         modules: list, ai_summary: str = None,
                         output_path: str = None) -> str:
    """Genera el reporte completo de QA con todos los modulos."""

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}

    report = []
    report.append("=" * 70)
    report.append(f"  LOVABLE QA REPORT - {project_name.upper()}")
    report.append(f"  Fecha: {now}")
    report.append(f"  Modulos: {', '.join(modules)}")
    report.append("=" * 70)

    # Calculate global score
    total_critical = 0
    total_high = 0
    total_medium = 0
    total_low = 0
    total_info = 0
    total_files = 0

    for key, r in reports.items():
        if not r.summary:
            r.get_summary()
        total_critical += r.summary.get("CRITICAL", 0)
        total_high += r.summary.get("HIGH", 0)
        total_medium += r.summary.get("MEDIUM", 0)
        total_low += r.summary.get("LOW", 0)
        total_info += r.summary.get("INFO", 0)
        total_files += r.files_scanned

    score = max(0, 100 - (total_critical * 15) - (total_high * 8) - (total_medium * 3))
    grade = "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D" if score >= 40 else "F"

    report.append(f"\n  QA SCORE: {score}/100 ({grade})")
    report.append(f"  Archivos escaneados: {total_files}")
    report.append(f"  Total hallazgos: {total_critical + total_high + total_medium + total_low + total_info}")

    # Summary table
    report.append(f"\n{'─' * 70}")
    report.append("  RESUMEN DE HALLAZGOS POR MODULO")
    report.append(f"{'─' * 70}")
    report.append(f"  {'Modulo':<22} {'CRIT':>6} {'HIGH':>6} {'MED':>6} {'LOW':>6} {'INFO':>6} {'Total':>7}")
    report.append(f"  {'─' * 64}")

    for key in modules:
        r = reports.get(key)
        if not r:
            continue
        s = r.summary
        name = MODULE_NAMES.get(key, key)[:22]
        total = sum(s.values())
        report.append(
            f"  {name:<22} {s.get('CRITICAL',0):>6} {s.get('HIGH',0):>6} "
            f"{s.get('MEDIUM',0):>6} {s.get('LOW',0):>6} {s.get('INFO',0):>6} {total:>7}"
        )

    report.append(f"  {'─' * 64}")
    total_all = total_critical + total_high + total_medium + total_low + total_info
    report.append(
        f"  {'TOTAL':<22} {total_critical:>6} {total_high:>6} "
        f"{total_medium:>6} {total_low:>6} {total_info:>6} {total_all:>7}"
    )

    # Metrics section (from scale, quality, testing, perf, api)
    metrics_modules = ["scale", "quality", "testing", "perf", "api"]
    has_metrics = any(
        hasattr(reports.get(m), "metrics") and reports.get(m).metrics
        for m in metrics_modules if m in modules
    )

    if has_metrics:
        report.append(f"\n{'─' * 70}")
        report.append("  METRICAS DEL PROYECTO")
        report.append(f"{'─' * 70}")

        for m_key in metrics_modules:
            if m_key not in modules:
                continue
            r = reports.get(m_key)
            if not r or not hasattr(r, "metrics") or not r.metrics:
                continue

            report.append(f"\n  [{MODULE_NAMES.get(m_key, m_key)}]")
            for k, v in r.metrics.items():
                if isinstance(v, (str, int, float, bool)):
                    report.append(f"    {k:<30} {v}")
                elif isinstance(v, list) and len(v) <= 5:
                    report.append(f"    {k:<30} {len(v)} items")

    # AI Summary
    if ai_summary:
        report.append(f"\n{'=' * 70}")
        report.append("  ANALISIS INTELIGENTE (AI)")
        report.append(f"{'=' * 70}")
        report.append(ai_summary)

    # Detailed findings per module
    for key in modules:
        r = reports.get(key)
        if not r or not r.findings:
            continue

        name = MODULE_NAMES.get(key, key)
        report.append(f"\n{'─' * 70}")
        report.append(f"  HALLAZGOS: {name.upper()}")
        report.append(f"{'─' * 70}")

        sorted_findings = sorted(r.findings, key=lambda f: severity_order.get(f.severity, 5))
        report.append(format_findings_table(sorted_findings))

    report.append(f"\n{'=' * 70}")
    report.append("  FIN DEL REPORTE")
    report.append(f"{'=' * 70}")

    full_report = "\n".join(report)

    # Save report
    if output_path is None:
        output_path = os.path.join(project_path, f"qa-report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt")

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_report)
        print(f"\n  Reporte guardado en: {output_path}")
    except Exception as e:
        print(f"\n  Error guardando reporte: {e}")

    # Save JSON version
    json_data = {
        "project": project_name,
        "date": now,
        "score": score,
        "grade": grade,
        "modules_run": modules,
        "totals": {
            "critical": total_critical,
            "high": total_high,
            "medium": total_medium,
            "low": total_low,
            "info": total_info,
        },
    }

    for key in modules:
        r = reports.get(key)
        if not r:
            continue
        module_data = {
            "summary": r.summary,
            "findings": [
                {
                    "severity": f.severity,
                    "category": f.category,
                    "title": f.title,
                    "description": f.description,
                    "file": f.file_path,
                    "line": getattr(f, "line_number", 0),
                    "recommendation": getattr(f, "recommendation", ""),
                }
                for f in r.findings
            ],
        }
        if hasattr(r, "metrics") and r.metrics:
            clean = {}
            for k, v in r.metrics.items():
                if isinstance(v, (str, int, float, bool)):
                    clean[k] = v
                elif isinstance(v, list):
                    clean[k] = [item if isinstance(item, (str, int, float)) else str(item) for item in v[:20]]
            module_data["metrics"] = clean

        json_data[key] = module_data

    json_path = output_path.replace(".txt", ".json")
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False, default=str)
        print(f"  Reporte JSON en: {json_path}")
    except Exception as e:
        print(f"  Error guardando JSON: {e}")

    return full_report
