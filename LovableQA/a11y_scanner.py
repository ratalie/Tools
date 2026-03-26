"""
Accessibility (a11y) Scanner for Lovable Projects
===================================================
Analiza proyectos Lovable en busca de problemas de accesibilidad
siguiendo WCAG 2.1 guidelines.
"""

import os
import re
from dataclasses import dataclass, field


@dataclass
class A11yFinding:
    severity: str
    category: str
    title: str
    description: str
    file_path: str
    line_number: int = 0
    code_snippet: str = ""
    recommendation: str = ""
    wcag_criteria: str = ""


@dataclass
class A11yReport:
    findings: list = field(default_factory=list)
    files_scanned: int = 0
    summary: dict = field(default_factory=dict)

    def add(self, finding: A11yFinding):
        self.findings.append(finding)

    def get_summary(self):
        counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        self.summary = counts
        return counts


# ─────────────────────────────────────────────
# Patrones de accesibilidad
# ─────────────────────────────────────────────

# Imagenes sin alt
IMG_PATTERNS = [
    (r"""<img\s+(?![^>]*alt\s*=)[^>]*>""",
     "Image without alt attribute",
     "HIGH", "WCAG 1.1.1 - Non-text Content",
     "Add descriptive alt text or alt='' for decorative images"),
    (r"""<img\s+[^>]*alt\s*=\s*['"]["'][^>]*>""",
     "Image with empty alt - verify it's decorative",
     "LOW", "WCAG 1.1.1",
     "Empty alt is valid only for decorative images"),
]

# Links y botones
INTERACTIVE_PATTERNS = [
    (r"""<a\s+(?![^>]*(?:aria-label|aria-labelledby))[^>]*href\s*=\s*['"][^'"]*['"][^>]*>\s*<(?:img|svg|Icon)""",
     "Link wrapping only image/icon without accessible label",
     "HIGH", "WCAG 2.4.4 - Link Purpose",
     "Add aria-label to describe the link destination"),
    (r"""<button\s+(?![^>]*(?:aria-label|aria-labelledby))[^>]*>\s*<(?:svg|Icon|img)""",
     "Button with only icon and no accessible label",
     "HIGH", "WCAG 4.1.2 - Name, Role, Value",
     "Add aria-label or visually hidden text describing the action"),
    (r"""onClick\s*=\s*\{[^}]*\}\s*(?!.*(?:role|button|Button|<a ))""",
     None, None, None, None),  # counted separately for div-with-onclick
    (r"""<div\s+[^>]*onClick""",
     "Clickable div without semantic element",
     "MEDIUM", "WCAG 4.1.2",
     "Use <button> or <a> instead of div with onClick for keyboard accessibility"),
    (r"""<span\s+[^>]*onClick""",
     "Clickable span without semantic element",
     "MEDIUM", "WCAG 4.1.2",
     "Use <button> or <a> instead of span with onClick"),
    (r"""tabIndex\s*=\s*['"]?-1['"]?""",
     "tabIndex=-1 removes element from tab order",
     "LOW", "WCAG 2.1.1 - Keyboard",
     "Verify this element doesn't need keyboard access"),
    (r"""tabIndex\s*=\s*['"]?[2-9]\d*['"]?""",
     "Positive tabIndex disrupts natural tab order",
     "MEDIUM", "WCAG 2.4.3 - Focus Order",
     "Use tabIndex=0 and DOM order instead of positive values"),
]

# Formularios
FORM_PATTERNS = [
    (r"""<input\s+(?![^>]*(?:aria-label|aria-labelledby|id\s*=\s*['"][^'"]*['"][^>]*<label))[^>]*>""",
     "Input without associated label",
     "HIGH", "WCAG 1.3.1 - Info and Relationships",
     "Add <label htmlFor> or aria-label to the input"),
    (r"""<select\s+(?![^>]*(?:aria-label|aria-labelledby))[^>]*>""",
     "Select without accessible label",
     "HIGH", "WCAG 1.3.1",
     "Add aria-label or associated <label> element"),
    (r"""<textarea\s+(?![^>]*(?:aria-label|aria-labelledby))[^>]*>""",
     "Textarea without accessible label",
     "HIGH", "WCAG 1.3.1",
     "Add aria-label or associated <label> element"),
    (r"""placeholder\s*=\s*['"][^'"]+['"](?![^>]*(?:aria-label|label))""",
     "Placeholder used as only label",
     "MEDIUM", "WCAG 1.3.1",
     "Placeholders disappear on input - add a persistent label"),
    (r"""type\s*=\s*['"](?:submit|reset)['"](?![^>]*(?:aria-label|value))""",
     "Submit/reset button without accessible name",
     "MEDIUM", "WCAG 4.1.2",
     "Add value or aria-label to the button"),
]

# Estructura semantica
SEMANTIC_PATTERNS = [
    (r"""<div\s+[^>]*role\s*=\s*['"](?:banner|navigation|main|contentinfo)['"]""",
     "ARIA landmark role used instead of semantic HTML",
     "LOW", "WCAG 1.3.1",
     "Prefer <header>, <nav>, <main>, <footer> over div with role"),
    (r"""<h[1-6]""",
     None, None, None, None),  # counted for heading analysis
]

# Color y contraste
COLOR_PATTERNS = [
    (r"""(?:color|background(?:-color)?)\s*:\s*(?:#[0-9a-fA-F]{3,8}|rgb|hsl)""",
     None, None, None, None),  # counted for analysis
    (r"""opacity\s*:\s*(?:0\.[0-4]\d*|0\.5)""",
     "Low opacity may cause contrast issues",
     "LOW", "WCAG 1.4.3 - Contrast",
     "Verify text contrast ratio meets 4.5:1 minimum"),
    (r"""text-(?:xs|sm)\b.*(?:text-gray-[3-4]00|text-slate-[3-4]00|text-neutral-[3-4]00)""",
     "Small text with light gray color - likely contrast issue",
     "MEDIUM", "WCAG 1.4.3 - Contrast",
     "Small text needs 4.5:1 contrast ratio. Use darker colors."),
]

# Focus y teclado
FOCUS_PATTERNS = [
    (r"""outline\s*:\s*(?:none|0)\b""",
     "Focus outline removed - keyboard users lose visual focus indicator",
     "HIGH", "WCAG 2.4.7 - Focus Visible",
     "Replace with custom focus-visible styles instead of removing outline"),
    (r"""focus:outline-none""",
     "Tailwind focus:outline-none removes keyboard focus indicator",
     "HIGH", "WCAG 2.4.7 - Focus Visible",
     "Use focus-visible:ring-2 or similar instead of removing outline entirely"),
    (r"""\*\s*\{[^}]*outline\s*:\s*(?:none|0)""",
     "Global outline removal - affects all focusable elements",
     "CRITICAL", "WCAG 2.4.7 - Focus Visible",
     "Never remove outline globally. Use :focus-visible for custom styles."),
]

# ARIA
ARIA_PATTERNS = [
    (r"""aria-hidden\s*=\s*['"]true['"][^>]*(?:onClick|href|tabIndex\s*=\s*['"]0)""",
     "Interactive element hidden from assistive technology",
     "HIGH", "WCAG 4.1.2",
     "Don't use aria-hidden on interactive elements"),
    (r"""role\s*=\s*['"]presentation['"][^>]*(?:onClick|href)""",
     "Presentation role on interactive element",
     "HIGH", "WCAG 4.1.2",
     "Remove role=presentation from interactive elements"),
    (r"""aria-live\s*=\s*['"]assertive['"]""",
     "aria-live=assertive interrupts user - use polite when possible",
     "LOW", "WCAG 4.1.3",
     "Use aria-live='polite' unless the update is truly urgent"),
]

# Media
MEDIA_PATTERNS = [
    (r"""<video\s+(?![^>]*(?:track|captions|subtitles))""",
     "Video without captions/subtitles track",
     "HIGH", "WCAG 1.2.2 - Captions",
     "Add <track kind='captions'> for hearing-impaired users"),
    (r"""<audio\s+(?![^>]*(?:transcript))""",
     "Audio without transcript reference",
     "MEDIUM", "WCAG 1.2.1 - Audio-only",
     "Provide a text transcript for audio content"),
    (r"""autoPlay|autoplay""",
     "Autoplay media may be disorienting",
     "MEDIUM", "WCAG 1.4.2 - Audio Control",
     "Ensure users can pause/stop auto-playing media"),
]


class A11yScanner:
    """Escanea un proyecto Lovable en busca de problemas de accesibilidad."""

    SCAN_EXTENSIONS = {".tsx", ".jsx", ".html", ".vue"}
    SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", "coverage"}

    def __init__(self, project_path: str):
        self.project_path = os.path.abspath(project_path)
        self.report = A11yReport()
        self._heading_counts = {i: 0 for i in range(1, 7)}
        self._has_main_landmark = False
        self._has_skip_link = False
        self._has_lang_attr = False

    def scan(self) -> A11yReport:
        print("  [a11y] Escaneando archivos...")
        files = self._collect_files()
        self.report.files_scanned = len(files)

        for file_path in files:
            self._scan_file(file_path)

        self._check_global_a11y()
        self.report.get_summary()
        return self.report

    def _collect_files(self):
        files = []
        for root, dirs, filenames in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext in self.SCAN_EXTENSIONS:
                    files.append(os.path.join(root, fname))
        return files

    def _scan_file(self, file_path: str):
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                lines = content.split("\n")
        except Exception:
            return

        rel_path = os.path.relpath(file_path, self.project_path)

        # Count headings
        for level in range(1, 7):
            self._heading_counts[level] += len(re.findall(rf"<h{level}[\s>]", content))

        # Check landmarks
        if re.search(r"""<main[\s>]|role\s*=\s*['"]main['"]""", content):
            self._has_main_landmark = True
        if re.search(r"""skip.*(?:nav|content|link)|skipTo""", content, re.IGNORECASE):
            self._has_skip_link = True
        if re.search(r"""lang\s*=\s*['"][a-z]{2}""", content):
            self._has_lang_attr = True

        all_patterns = [
            IMG_PATTERNS, INTERACTIVE_PATTERNS, FORM_PATTERNS,
            COLOR_PATTERNS, FOCUS_PATTERNS, ARIA_PATTERNS,
            MEDIA_PATTERNS,
        ]

        for pattern_group in all_patterns:
            for pattern_tuple in pattern_group:
                pattern, description, severity, wcag, recommendation = pattern_tuple
                if description is None:
                    continue

                for line_num, line in enumerate(lines, 1):
                    if re.search(pattern, line, re.IGNORECASE):
                        stripped = line.strip()
                        if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("{/*"):
                            continue

                        self.report.add(A11yFinding(
                            severity=severity,
                            category="Accessibility",
                            title=description,
                            description=f"a11y: {description}",
                            file_path=rel_path,
                            line_number=line_num,
                            code_snippet=line.strip()[:200],
                            recommendation=recommendation,
                            wcag_criteria=wcag,
                        ))

    def _check_global_a11y(self):
        """Verificaciones a nivel de proyecto."""
        if not self._has_main_landmark:
            self.report.add(A11yFinding(
                severity="MEDIUM",
                category="Accessibility",
                title="No <main> landmark found",
                description="Screen readers use landmarks to navigate. <main> is essential.",
                file_path="(project-wide)",
                recommendation="Wrap primary content in <main> element",
                wcag_criteria="WCAG 1.3.1",
            ))

        if not self._has_skip_link:
            self.report.add(A11yFinding(
                severity="MEDIUM",
                category="Accessibility",
                title="No skip navigation link found",
                description="Keyboard users must tab through all nav items to reach content",
                file_path="(project-wide)",
                recommendation="Add a 'Skip to content' link as first focusable element",
                wcag_criteria="WCAG 2.4.1 - Bypass Blocks",
            ))

        if not self._has_lang_attr:
            self.report.add(A11yFinding(
                severity="MEDIUM",
                category="Accessibility",
                title="No lang attribute detected",
                description="Screen readers need lang to pronounce content correctly",
                file_path="(project-wide)",
                recommendation="Add lang attribute to <html> element (e.g., lang='en' or lang='es')",
                wcag_criteria="WCAG 3.1.1 - Language of Page",
            ))

        # Heading hierarchy
        if self._heading_counts[1] == 0 and sum(self._heading_counts.values()) > 0:
            self.report.add(A11yFinding(
                severity="MEDIUM",
                category="Accessibility",
                title="No <h1> found but other headings exist",
                description="Every page should have exactly one h1",
                file_path="(project-wide)",
                recommendation="Add one <h1> as the main page title",
                wcag_criteria="WCAG 1.3.1",
            ))

        if self._heading_counts[1] > 3:
            self.report.add(A11yFinding(
                severity="LOW",
                category="Accessibility",
                title=f"Multiple h1 elements ({self._heading_counts[1]} found)",
                description="Pages should typically have one h1. Multiple may confuse screen readers.",
                file_path="(project-wide)",
                recommendation="Use one h1 per page; use h2-h6 for subsections",
                wcag_criteria="WCAG 1.3.1",
            ))

        # Check for heading level skips (e.g., h1 -> h3 without h2)
        prev_level = 0
        for level in range(1, 7):
            if self._heading_counts[level] > 0:
                if prev_level > 0 and level - prev_level > 1:
                    self.report.add(A11yFinding(
                        severity="LOW",
                        category="Accessibility",
                        title=f"Heading level skip: h{prev_level} -> h{level}",
                        description="Skipping heading levels confuses screen reader navigation",
                        file_path="(project-wide)",
                        recommendation=f"Add h{prev_level + 1} between h{prev_level} and h{level}",
                        wcag_criteria="WCAG 1.3.1",
                    ))
                prev_level = level
