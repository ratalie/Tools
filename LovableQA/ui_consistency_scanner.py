"""
UI/UX Consistency Scanner for Lovable Projects
================================================
Detecta inconsistencias visuales, componentes duplicados,
Tailwind conflicts, y problemas de responsive design.
"""

import os
import re
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field


@dataclass
class UIFinding:
    severity: str
    category: str
    title: str
    description: str
    file_path: str
    line_number: int = 0
    code_snippet: str = ""
    recommendation: str = ""


@dataclass
class UIReport:
    findings: list = field(default_factory=list)
    files_scanned: int = 0
    summary: dict = field(default_factory=dict)

    def add(self, finding: UIFinding):
        self.findings.append(finding)

    def get_summary(self):
        counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        self.summary = counts
        return counts


# Tailwind conflicting class pairs
TAILWIND_CONFLICTS = [
    (r"flex\s+.*\bgrid\b", "flex and grid on same element"),
    (r"hidden\s+.*\b(?:block|flex|grid|inline)\b", "hidden with display class"),
    (r"static\s+.*\b(?:relative|absolute|fixed|sticky)\b", "conflicting position classes"),
    (r"(?:w-full|w-screen)\s+.*\bw-\d", "conflicting width classes"),
    (r"(?:h-full|h-screen)\s+.*\bh-\d", "conflicting height classes"),
    (r"(?:text-left)\s+.*\btext-(?:center|right)\b", "conflicting text alignment"),
    (r"(?:text-center)\s+.*\btext-(?:left|right)\b", "conflicting text alignment"),
    (r"(?:justify-start)\s+.*\bjustify-(?:center|end|between)\b", "conflicting justify"),
    (r"(?:items-start)\s+.*\bitems-(?:center|end)\b", "conflicting items alignment"),
    (r"(?:rounded-none)\s+.*\brounded-(?:sm|md|lg|xl|full)\b", "conflicting border-radius"),
    (r"(?:border-0)\s+.*\bborder-\d", "conflicting border width"),
    (r"(?:opacity-0)\s+.*\bopacity-(?:\d{2,}|100)\b", "conflicting opacity"),
]

# Hardcoded values que deberian ser tokens
HARDCODED_STYLE_PATTERNS = [
    (r"""(?:color|background(?:-color)?)\s*:\s*#[0-9a-fA-F]{3,8}""",
     "Hardcoded color value in inline style",
     "Consider using Tailwind classes or CSS variables for consistent theming"),
    (r"""(?:font-size|padding|margin|width|height|gap|border-radius)\s*:\s*\d+px""",
     "Hardcoded pixel value in inline style",
     "Use Tailwind spacing/sizing classes for consistency"),
    (r"""style\s*=\s*\{\s*\{[^}]{80,}""",
     "Large inline style object",
     "Extract to a CSS class or Tailwind utility classes"),
]


class UIConsistencyScanner:
    """Escanea un proyecto Lovable en busca de inconsistencias UI/UX."""

    SCAN_EXTENSIONS = {".tsx", ".jsx", ".css", ".scss"}
    SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", "coverage"}

    def __init__(self, project_path: str):
        self.project_path = os.path.abspath(project_path)
        self.report = UIReport()
        self._color_usage = Counter()
        self._font_sizes = Counter()
        self._spacing_values = Counter()
        self._component_names = defaultdict(list)  # name -> [file_paths]
        self._button_variants = []
        self._breakpoint_usage = Counter()

    def scan(self) -> UIReport:
        print("  [UI/UX] Escaneando archivos...")
        files = self._collect_files()
        self.report.files_scanned = len(files)

        for file_path in files:
            self._scan_file(file_path)

        self._analyze_color_consistency()
        self._analyze_spacing_consistency()
        self._check_duplicate_components()
        self._check_responsive_coverage()
        self._check_design_system()
        self._check_tailwind_config()

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

        # Track component names
        comp_match = re.findall(r"""(?:export\s+(?:default\s+)?(?:function|const)\s+|function\s+)(\w+)""", content)
        for name in comp_match:
            if name[0].isupper():  # React components start uppercase
                self._component_names[name].append(rel_path)

        # Collect Tailwind color classes
        tw_colors = re.findall(r"""(?:text|bg|border|ring|shadow)-(?:(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3})""", content)
        self._color_usage.update(tw_colors)

        # Collect spacing values
        tw_spacing = re.findall(r"""(?:p|m|gap|space)-(?:x-|y-)?(\d+(?:\.\d+)?|\[\d+px\])""", content)
        self._spacing_values.update(tw_spacing)

        # Collect font sizes
        tw_fonts = re.findall(r"""text-(?:xs|sm|base|lg|xl|2xl|3xl|4xl|5xl|6xl|7xl|8xl|9xl)""", content)
        self._font_sizes.update(tw_fonts)

        # Track responsive breakpoints
        breakpoints = re.findall(r"""(?:sm|md|lg|xl|2xl):""", content)
        self._breakpoint_usage.update(breakpoints)

        # Check for Tailwind conflicts
        for line_num, line in enumerate(lines, 1):
            # Extract className strings
            class_matches = re.findall(r"""className\s*=\s*[{'"]\s*`?([^'"`}]+)""", line)
            for class_str in class_matches:
                for conflict_pattern, conflict_desc in TAILWIND_CONFLICTS:
                    if re.search(conflict_pattern, class_str):
                        self.report.add(UIFinding(
                            severity="MEDIUM",
                            category="UI/Tailwind",
                            title=f"Conflicting Tailwind classes: {conflict_desc}",
                            description=f"Classes in the same element conflict with each other",
                            file_path=rel_path,
                            line_number=line_num,
                            code_snippet=class_str[:150],
                            recommendation="Remove one of the conflicting classes",
                        ))

            # Check hardcoded styles
            for pattern, desc, rec in HARDCODED_STYLE_PATTERNS:
                if re.search(pattern, line):
                    stripped = line.strip()
                    if stripped.startswith("//") or stripped.startswith("*"):
                        continue
                    self.report.add(UIFinding(
                        severity="LOW",
                        category="UI/Consistency",
                        title=desc,
                        description="Hardcoded values make theming and consistency harder",
                        file_path=rel_path,
                        line_number=line_num,
                        code_snippet=line.strip()[:150],
                        recommendation=rec,
                    ))

            # Check for !important abuse
            if "!important" in line and not line.strip().startswith("//"):
                self.report.add(UIFinding(
                    severity="LOW",
                    category="UI/CSS",
                    title="!important usage",
                    description="!important makes styles hard to override and maintain",
                    file_path=rel_path,
                    line_number=line_num,
                    recommendation="Fix specificity issues instead of using !important",
                ))

            # Check for z-index chaos
            z_match = re.search(r"""z-(?:\[(\d+)\]|(\d{2,}))""", line)
            if z_match:
                val = z_match.group(1) or z_match.group(2)
                if val and int(val) > 50:
                    self.report.add(UIFinding(
                        severity="LOW",
                        category="UI/CSS",
                        title=f"High z-index value: {val}",
                        description="High z-index values indicate potential stacking context issues",
                        file_path=rel_path,
                        line_number=line_num,
                        recommendation="Use a z-index scale (10, 20, 30...) defined in Tailwind config",
                    ))

    def _analyze_color_consistency(self):
        """Analiza consistencia de colores."""
        if len(self._color_usage) > 20:
            self.report.add(UIFinding(
                severity="MEDIUM",
                category="UI/Consistency",
                title=f"High color variety: {len(self._color_usage)} different color classes used",
                description="Too many color variations suggest inconsistent design",
                file_path="(project-wide)",
                recommendation="Define a color palette in tailwind.config and stick to it",
            ))

        # Check for similar but different shades
        color_groups = defaultdict(list)
        for color_class in self._color_usage:
            base = re.match(r"(?:text|bg|border)-(\w+)-", color_class)
            if base:
                color_groups[base.group(1)].append(color_class)

        for color, variants in color_groups.items():
            if len(set(variants)) > 5:
                self.report.add(UIFinding(
                    severity="LOW",
                    category="UI/Consistency",
                    title=f"Many shades of '{color}': {len(set(variants))} variants",
                    description=f"Using many shades of the same color suggests inconsistency",
                    file_path="(project-wide)",
                    recommendation=f"Standardize on 2-3 shades of {color} for consistency",
                ))

    def _analyze_spacing_consistency(self):
        """Analiza consistencia de spacing."""
        custom_spacing = [s for s in self._spacing_values if s.startswith("[")]
        if len(custom_spacing) > 5:
            self.report.add(UIFinding(
                severity="LOW",
                category="UI/Consistency",
                title=f"Many custom spacing values: {len(custom_spacing)} arbitrary values",
                description="Arbitrary values ([Npx]) bypass the design system",
                file_path="(project-wide)",
                recommendation="Use standard Tailwind spacing scale (1, 2, 3, 4, 6, 8, 12, 16...)",
            ))

    def _check_duplicate_components(self):
        """Detecta componentes con nombres similares o duplicados."""
        for name, files in self._component_names.items():
            if len(files) > 1:
                self.report.add(UIFinding(
                    severity="MEDIUM",
                    category="UI/Architecture",
                    title=f"Duplicate component name: {name} ({len(files)} files)",
                    description=f"Found in: {', '.join(files[:5])}",
                    file_path=files[0],
                    recommendation="Consolidate into a single reusable component",
                ))

        # Check for similar names (e.g., Button, CustomButton, MyButton)
        base_names = defaultdict(list)
        for name in self._component_names:
            cleaned = re.sub(r"(?:Custom|My|App|Base|Default|New|Main|Primary)", "", name)
            if cleaned and cleaned != name:
                base_names[cleaned].append(name)

        for base, variants in base_names.items():
            if len(variants) > 1:
                self.report.add(UIFinding(
                    severity="LOW",
                    category="UI/Architecture",
                    title=f"Similar component names: {', '.join(variants)}",
                    description="Components with similar names may be duplicated functionality",
                    file_path="(project-wide)",
                    recommendation="Review if these can be consolidated with props/variants",
                ))

    def _check_responsive_coverage(self):
        """Verifica que hay soporte responsive."""
        total_breakpoints = sum(self._breakpoint_usage.values())

        if total_breakpoints == 0:
            self.report.add(UIFinding(
                severity="HIGH",
                category="UI/Responsive",
                title="No responsive breakpoints detected",
                description="No sm:, md:, lg: classes found - app may not be mobile-friendly",
                file_path="(project-wide)",
                recommendation="Add responsive classes for mobile (sm:), tablet (md:), desktop (lg:)",
            ))
        else:
            used = set(self._breakpoint_usage.keys())
            expected = {"sm:", "md:", "lg:"}
            missing = expected - used
            if missing:
                self.report.add(UIFinding(
                    severity="MEDIUM",
                    category="UI/Responsive",
                    title=f"Missing breakpoints: {', '.join(missing)}",
                    description=f"Only using: {', '.join(used)}",
                    file_path="(project-wide)",
                    recommendation=f"Add {', '.join(missing)} breakpoints for full responsive coverage",
                ))

    def _check_design_system(self):
        """Verifica si hay un sistema de diseno establecido."""
        src_dir = os.path.join(self.project_path, "src")
        if not os.path.isdir(src_dir):
            return

        # Check for UI library (shadcn, radix, etc.)
        pkg_path = os.path.join(self.project_path, "package.json")
        has_ui_lib = False
        if os.path.exists(pkg_path):
            try:
                with open(pkg_path, "r") as f:
                    pkg = json.load(f)
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                ui_libs = ["@radix-ui", "@shadcn", "@headlessui", "@chakra-ui", "@mui", "antd"]
                has_ui_lib = any(any(d.startswith(lib) for d in deps) for lib in ui_libs)
            except Exception:
                pass

        # Check for components/ui directory (shadcn pattern)
        ui_dir = os.path.join(src_dir, "components", "ui")
        has_ui_dir = os.path.isdir(ui_dir)

        if not has_ui_lib and not has_ui_dir:
            self.report.add(UIFinding(
                severity="INFO",
                category="UI/Design System",
                title="No UI component library detected",
                description="No shadcn/ui, Radix, Chakra, or MUI found",
                file_path="(project-wide)",
                recommendation="Consider using a component library for consistent UI patterns",
            ))

        # Check for theme/design tokens file
        theme_patterns = ["theme", "tokens", "design-system", "globals.css", "global.css"]
        has_theme = False
        for root, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            for fname in files:
                if any(p in fname.lower() for p in theme_patterns):
                    has_theme = True
                    break

        if not has_theme:
            self.report.add(UIFinding(
                severity="LOW",
                category="UI/Design System",
                title="No theme/design tokens file detected",
                description="Centralized design tokens improve consistency",
                file_path="src/",
                recommendation="Create a theme file with colors, spacing, and typography tokens",
            ))

    def _check_tailwind_config(self):
        """Verifica configuracion de Tailwind."""
        tw_configs = ["tailwind.config.js", "tailwind.config.ts", "tailwind.config.cjs"]
        for cfg_name in tw_configs:
            cfg_path = os.path.join(self.project_path, cfg_name)
            if os.path.exists(cfg_path):
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    if "extend" not in content or "colors" not in content:
                        self.report.add(UIFinding(
                            severity="LOW",
                            category="UI/Design System",
                            title="Tailwind config without custom color palette",
                            description="Default Tailwind colors may not match your brand",
                            file_path=cfg_name,
                            recommendation="Extend Tailwind with your brand colors in theme.extend.colors",
                        ))

                    if "fontFamily" not in content:
                        self.report.add(UIFinding(
                            severity="LOW",
                            category="UI/Design System",
                            title="No custom font family in Tailwind config",
                            description="Custom fonts help brand consistency",
                            file_path=cfg_name,
                            recommendation="Add fontFamily to theme.extend for your brand fonts",
                        ))
                except Exception:
                    pass
                return

        # No tailwind config found
        pkg_path = os.path.join(self.project_path, "package.json")
        if os.path.exists(pkg_path):
            try:
                with open(pkg_path, "r") as f:
                    content = f.read()
                if "tailwindcss" in content:
                    self.report.add(UIFinding(
                        severity="MEDIUM",
                        category="UI/Design System",
                        title="Tailwind installed but no config file found",
                        description="Without config, you can't customize the design system",
                        file_path="(root)",
                        recommendation="Run 'npx tailwindcss init' to create a config file",
                    ))
            except Exception:
                pass
