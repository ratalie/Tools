"""
Scalability Scanner for Lovable Projects
==========================================
Analiza proyectos Lovable (React + Supabase/TypeScript) en busca de
problemas de escalabilidad y rendimiento.
"""

import os
import re
import json
from dataclasses import dataclass, field


@dataclass
class ScalabilityFinding:
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW, INFO
    category: str
    title: str
    description: str
    file_path: str
    line_number: int = 0
    code_snippet: str = ""
    recommendation: str = ""


@dataclass
class ScalabilityReport:
    findings: list = field(default_factory=list)
    files_scanned: int = 0
    metrics: dict = field(default_factory=dict)
    summary: dict = field(default_factory=dict)

    def add(self, finding: ScalabilityFinding):
        self.findings.append(finding)

    def get_summary(self):
        counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        self.summary = counts
        return counts


# ─────────────────────────────────────────────
# Patrones de deteccion - Rendimiento React
# ─────────────────────────────────────────────

REACT_PERF_PATTERNS = [
    # Re-renders innecesarios
    (r"""useState\s*<.*>\s*\(\s*(?:new\s+(?:Date|Map|Set|Object)|{[^}]+}|\[[^\]]+\])""",
     "Object/array as useState initial value recreated on each render",
     "HIGH", "Performance/React"),

    # Inline objects en JSX (causan re-renders)
    (r"""style\s*=\s*\{\s*\{""",
     "Inline style object - creates new object on each render",
     "LOW", "Performance/React"),

    # useEffect sin dependencies
    (r"""useEffect\s*\(\s*(?:async\s*)?\(\)\s*=>\s*\{[^}]*\}\s*\)""",
     "useEffect without dependency array - runs on every render",
     "HIGH", "Performance/React"),

    # Fetching sin cache/deduplication
    (r"""useEffect\s*\([^)]*fetch\s*\(""",
     "fetch() inside useEffect without caching strategy",
     "MEDIUM", "Performance/Data Fetching"),

    # Large component detection (proxy: too many hooks)
    (r"""(?:const|let)\s+\[.*,\s*set\w+\]\s*=\s*useState""",
     None,  # counted separately
     None, None),

    # Missing key in lists
    (r"""\.map\s*\(\s*(?:\([^)]*\)|[^=]*)\s*=>\s*(?:<|\()(?!.*key\s*=)""",
     "Array .map() without key prop - causes reconciliation issues",
     "MEDIUM", "Performance/React"),
]

# Patrones de queries/datos
DATA_PATTERNS = [
    # N+1 queries (fetch inside loop/map)
    (r"""\.map\s*\(.*(?:await|fetch|supabase|\.from\()""",
     "Potential N+1 query - data fetching inside .map()",
     "HIGH", "Scalability/Data"),

    # Select * equivalente en Supabase
    (r"""\.from\s*\([^)]+\)\s*\.\s*select\s*\(\s*(?:['"]?\*['"]?|\s*)\)""",
     "SELECT * from Supabase - fetch only needed columns",
     "MEDIUM", "Scalability/Data"),

    # Falta de paginacion
    (r"""\.from\s*\([^)]+\)\s*\.\s*select\s*\([^)]*\)(?!.*(?:\.range|\.limit|pagination))""",
     "Supabase query without pagination/limit - may return too many rows",
     "MEDIUM", "Scalability/Data"),

    # Queries en componentes sin cache
    (r"""(?:useEffect|useCallback)\s*\([^)]*\.from\s*\(""",
     "Supabase query in component without react-query/SWR caching",
     "MEDIUM", "Scalability/Data"),

    # Realtime sin filtro
    (r"""\.channel\s*\([^)]*\)\s*\.on\s*\([^)]*\*""",
     "Realtime subscription without filter - receives all changes",
     "HIGH", "Scalability/Data"),
]

# Patrones de bundle/assets
BUNDLE_PATTERNS = [
    # Importaciones pesadas sin tree-shaking
    (r"""import\s+\w+\s+from\s+['"](?:lodash|moment|date-fns)['"]""",
     "Full library import instead of specific module",
     "MEDIUM", "Bundle Size"),

    (r"""import\s*\{[^}]{200,}\}\s*from""",
     "Very large named import - consider code splitting",
     "LOW", "Bundle Size"),

    # Falta de lazy loading
    (r"""import\s+\w+\s+from\s+['"]\.\./(?:pages|views|screens)/""",
     "Direct page import - consider React.lazy() for code splitting",
     "LOW", "Bundle Size"),

    # Imagenes sin optimizar (referencia directa a grandes archivos)
    (r"""src\s*=\s*['"](?:.*\.(?:png|jpg|jpeg|gif|bmp))['"]""",
     "Image referenced directly - consider using optimized formats (WebP/AVIF)",
     "LOW", "Performance/Assets"),
]

# Patrones de arquitectura/escalabilidad
ARCHITECTURE_PATTERNS = [
    # Estado global excesivo
    (r"""createContext""",
     None,  # counted
     None, None),

    # Sin error boundaries
    (r"""componentDidCatch|ErrorBoundary""",
     None,  # counted
     None, None),

    # Operaciones pesadas en render
    (r"""(?:\.filter|\.sort|\.reduce|\.map)\s*\([^)]*\)\s*\.(?:filter|sort|reduce|map)""",
     "Chained array operations - consider useMemo for expensive computations",
     "MEDIUM", "Performance/React"),

    # localStorage sync excesivo
    (r"""localStorage\.(?:setItem|getItem)\s*\(""",
     None,  # counted
     None, None),

    # Falta de debounce/throttle en handlers
    (r"""on(?:Change|Input|Scroll|Resize)\s*=\s*\{(?!.*(?:debounce|throttle|useDebounce))""",
     "Event handler without debounce/throttle - may cause excessive updates",
     "LOW", "Performance/Events"),
]

# Patrones de Supabase escalabilidad
SUPABASE_SCALE_PATTERNS = [
    # Falta de indices (proxy: queries con .eq en columnas no obvias)
    (r"""\.(?:eq|neq|gt|lt|gte|lte)\s*\(\s*['"](?!id|created_at|updated_at|email|user_id)""",
     "Query filter on non-standard column - verify database index exists",
     "LOW", "Scalability/Database"),

    # Falta de .single() cuando se espera un solo resultado
    (r"""\.eq\s*\(\s*['"]id['"].*(?:\.select)(?!.*\.single\(\))""",
     "Query by ID without .single() - returns array instead of object",
     "LOW", "Scalability/Data"),

    # Storage sin CDN
    (r"""supabase\.storage\.from\s*\([^)]+\)\s*\.(?:getPublicUrl|createSignedUrl)""",
     "Supabase storage URL - consider CDN/caching for frequently accessed files",
     "INFO", "Scalability/Storage"),

    # Edge functions sin timeout
    (r"""Deno\.serve""",
     "Edge function detected - verify timeout and memory limits",
     "INFO", "Scalability/Serverless"),
]


# ─────────────────────────────────────────────
# Scanner
# ─────────────────────────────────────────────

class ScalabilityScanner:
    """Escanea un proyecto Lovable en busca de problemas de escalabilidad."""

    SCAN_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
    SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", "coverage", "__pycache__"}

    def __init__(self, project_path: str):
        self.project_path = os.path.abspath(project_path)
        self.report = ScalabilityReport()
        self._metrics = {
            "total_components": 0,
            "total_lines": 0,
            "max_component_lines": 0,
            "max_component_file": "",
            "useState_count": 0,
            "useEffect_count": 0,
            "context_count": 0,
            "error_boundary_count": 0,
            "localStorage_calls": 0,
            "supabase_queries": 0,
            "total_dependencies": 0,
            "large_files": [],
        }

    def scan(self) -> ScalabilityReport:
        """Ejecuta todos los escaneos de escalabilidad."""
        print("  [Scalability] Escaneando archivos...")
        files = self._collect_files()
        self.report.files_scanned = len(files)

        for file_path in files:
            self._scan_file(file_path)

        self._analyze_project_structure()
        self._check_package_json()
        self._generate_metric_findings()

        self.report.metrics = self._metrics
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
        line_count = len(lines)
        self._metrics["total_lines"] += line_count

        # Detect components
        is_component = bool(re.search(r"""(?:export\s+(?:default\s+)?(?:function|const)|function\s+\w+)\s*\(""", content))
        if is_component:
            self._metrics["total_components"] += 1
            if line_count > self._metrics["max_component_lines"]:
                self._metrics["max_component_lines"] = line_count
                self._metrics["max_component_file"] = rel_path

        # Count metrics
        self._metrics["useState_count"] += len(re.findall(r"useState", content))
        self._metrics["useEffect_count"] += len(re.findall(r"useEffect", content))
        self._metrics["context_count"] += len(re.findall(r"createContext", content))
        self._metrics["error_boundary_count"] += len(re.findall(r"(?:componentDidCatch|ErrorBoundary)", content))
        self._metrics["localStorage_calls"] += len(re.findall(r"localStorage\.", content))
        self._metrics["supabase_queries"] += len(re.findall(r"\.from\s*\(", content))

        # Large file warning
        if line_count > 300:
            self._metrics["large_files"].append((rel_path, line_count))
            self.report.add(ScalabilityFinding(
                severity="MEDIUM",
                category="Architecture",
                title=f"Large file ({line_count} lines)",
                description="Large files are harder to maintain and may indicate a component that should be split",
                file_path=rel_path,
                recommendation="Consider breaking this into smaller, focused components/modules",
            ))

        # Count useState per file (too many = complex component)
        state_count = len(re.findall(r"useState", content))
        if state_count > 6:
            self.report.add(ScalabilityFinding(
                severity="MEDIUM",
                category="Architecture",
                title=f"Component with {state_count} useState hooks",
                description="Too many state variables suggest this component has too many responsibilities",
                file_path=rel_path,
                recommendation="Extract logic into custom hooks or break into smaller components",
            ))

        # Pattern matching
        all_patterns = [
            REACT_PERF_PATTERNS,
            DATA_PATTERNS,
            BUNDLE_PATTERNS,
            ARCHITECTURE_PATTERNS,
            SUPABASE_SCALE_PATTERNS,
        ]

        for pattern_group in all_patterns:
            for pattern_tuple in pattern_group:
                pattern, description, severity, category = pattern_tuple
                if description is None:  # counting-only patterns
                    continue

                for line_num, line in enumerate(lines, 1):
                    if re.search(pattern, line, re.IGNORECASE):
                        stripped = line.strip()
                        if stripped.startswith("//") or stripped.startswith("*"):
                            continue

                        self.report.add(ScalabilityFinding(
                            severity=severity,
                            category=category,
                            title=description,
                            description=f"Scalability concern: {description}",
                            file_path=rel_path,
                            line_number=line_num,
                            code_snippet=line.strip()[:200],
                        ))

    def _analyze_project_structure(self):
        """Analiza la estructura del proyecto para patrones de escalabilidad."""
        src_dir = os.path.join(self.project_path, "src")
        if not os.path.isdir(src_dir):
            self.report.add(ScalabilityFinding(
                severity="INFO",
                category="Architecture",
                title="No src/ directory found",
                description="Non-standard project structure",
                file_path="(root)",
            ))
            return

        # Check for proper folder structure
        expected_dirs = ["components", "pages", "hooks", "lib", "utils", "types"]
        existing_dirs = [d for d in os.listdir(src_dir)
                        if os.path.isdir(os.path.join(src_dir, d))]

        if "hooks" not in existing_dirs and self._metrics["useState_count"] > 10:
            self.report.add(ScalabilityFinding(
                severity="MEDIUM",
                category="Architecture",
                title="No hooks/ directory but many useState calls",
                description="Consider extracting reusable logic into custom hooks",
                file_path="src/",
                recommendation="Create src/hooks/ and extract reusable stateful logic",
            ))

        if "types" not in existing_dirs:
            self.report.add(ScalabilityFinding(
                severity="LOW",
                category="Architecture",
                title="No types/ directory",
                description="Centralized types improve maintainability at scale",
                file_path="src/",
                recommendation="Create src/types/ for shared TypeScript interfaces",
            ))

        # Check components directory depth (flat = harder to scale)
        comp_dir = os.path.join(src_dir, "components")
        if os.path.isdir(comp_dir):
            component_files = []
            for root, dirs, files in os.walk(comp_dir):
                dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
                for f in files:
                    if f.endswith((".tsx", ".jsx")):
                        component_files.append(os.path.join(root, f))

            if len(component_files) > 20:
                # Check if flat
                direct_files = [f for f in os.listdir(comp_dir)
                               if os.path.isfile(os.path.join(comp_dir, f))]
                if len(direct_files) > 15:
                    self.report.add(ScalabilityFinding(
                        severity="MEDIUM",
                        category="Architecture",
                        title=f"Flat components/ with {len(direct_files)} files",
                        description="Many components in a flat directory makes navigation harder at scale",
                        file_path="src/components/",
                        recommendation="Organize components into feature-based subdirectories",
                    ))

    def _check_package_json(self):
        """Verifica dependencias relevantes para escalabilidad."""
        pkg_path = os.path.join(self.project_path, "package.json")
        if not os.path.exists(pkg_path):
            return

        try:
            with open(pkg_path, "r") as f:
                pkg = json.load(f)

            deps = pkg.get("dependencies", {})
            dev_deps = pkg.get("devDependencies", {})
            all_deps = {**deps, **dev_deps}
            self._metrics["total_dependencies"] = len(all_deps)

            # Check for caching solution
            has_cache = any(d in all_deps for d in ["@tanstack/react-query", "swr", "react-query"])
            if not has_cache and self._metrics["supabase_queries"] > 3:
                self.report.add(ScalabilityFinding(
                    severity="HIGH",
                    category="Scalability/Data",
                    title="No data caching library (react-query/SWR)",
                    description=f"Found {self._metrics['supabase_queries']} Supabase queries without a caching layer",
                    file_path="package.json",
                    recommendation="Install @tanstack/react-query for automatic caching, deduplication, and background refetching",
                ))

            # Check for state management at scale
            if self._metrics["total_components"] > 15 and self._metrics["context_count"] > 3:
                has_state_lib = any(d in all_deps for d in ["zustand", "jotai", "recoil", "redux", "@reduxjs/toolkit"])
                if not has_state_lib:
                    self.report.add(ScalabilityFinding(
                        severity="MEDIUM",
                        category="Architecture",
                        title="Multiple contexts without state management library",
                        description=f"{self._metrics['context_count']} contexts found - may cause unnecessary re-renders",
                        file_path="package.json",
                        recommendation="Consider zustand or jotai for more efficient state management",
                    ))

            # Check bundle size concerns
            heavy_deps = {
                "moment": "Use date-fns or dayjs instead (~70KB smaller)",
                "lodash": "Import specific functions: lodash/get instead of lodash",
                "antd": "Very large UI library - ensure tree-shaking is configured",
                "@mui/material": "Large UI library - ensure tree-shaking",
            }
            for dep, suggestion in heavy_deps.items():
                if dep in deps:
                    self.report.add(ScalabilityFinding(
                        severity="MEDIUM",
                        category="Bundle Size",
                        title=f"Heavy dependency: {dep}",
                        description=suggestion,
                        file_path="package.json",
                        recommendation=suggestion,
                    ))

            # Too many dependencies
            if len(deps) > 40:
                self.report.add(ScalabilityFinding(
                    severity="MEDIUM",
                    category="Architecture",
                    title=f"High dependency count: {len(deps)} production dependencies",
                    description="Many dependencies increase bundle size and maintenance burden",
                    file_path="package.json",
                    recommendation="Audit dependencies with 'npx depcheck' and remove unused packages",
                ))

        except Exception:
            pass

    def _generate_metric_findings(self):
        """Genera hallazgos basados en metricas globales."""
        if self._metrics["error_boundary_count"] == 0 and self._metrics["total_components"] > 5:
            self.report.add(ScalabilityFinding(
                severity="MEDIUM",
                category="Reliability",
                title="No Error Boundaries detected",
                description="Without error boundaries, a single component error crashes the entire app",
                file_path="(project-wide)",
                recommendation="Add ErrorBoundary components around critical sections",
            ))

        if self._metrics["total_components"] > 0:
            avg_state = self._metrics["useState_count"] / self._metrics["total_components"]
            if avg_state > 4:
                self.report.add(ScalabilityFinding(
                    severity="MEDIUM",
                    category="Architecture",
                    title=f"High average state per component: {avg_state:.1f}",
                    description="Components have many state variables on average, suggesting tightly coupled logic",
                    file_path="(project-wide)",
                    recommendation="Extract shared state logic into custom hooks or a state management solution",
                ))
