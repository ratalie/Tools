"""
API / Backend Health Scanner for Lovable Projects
===================================================
Analiza Edge Functions, Supabase functions, API calls,
error handling, rate limiting, y validacion de inputs.
"""

import os
import re
import json
from dataclasses import dataclass, field


@dataclass
class APIFinding:
    severity: str
    category: str
    title: str
    description: str
    file_path: str
    line_number: int = 0
    code_snippet: str = ""
    recommendation: str = ""


@dataclass
class APIReport:
    findings: list = field(default_factory=list)
    files_scanned: int = 0
    metrics: dict = field(default_factory=dict)
    summary: dict = field(default_factory=dict)

    def add(self, finding: APIFinding):
        self.findings.append(finding)

    def get_summary(self):
        counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        self.summary = counts
        return counts


class APIScanner:
    """Escanea un proyecto Lovable en busca de problemas en API/Backend."""

    SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", "coverage"}

    def __init__(self, project_path: str):
        self.project_path = os.path.abspath(project_path)
        self.report = APIReport()
        self._metrics = {
            "edge_functions": 0,
            "supabase_rpcs": 0,
            "api_calls": 0,
            "unhandled_errors": 0,
            "has_rate_limiting": False,
            "has_input_validation": False,
            "has_zod": False,
            "cors_configs": 0,
        }

    def scan(self) -> APIReport:
        print("  [API/Backend] Escaneando archivos...")
        self._scan_edge_functions()
        self._scan_api_calls()
        self._scan_supabase_functions()
        self._check_validation_library()
        self._check_error_handling_patterns()
        self._generate_findings()

        self.report.metrics = self._metrics
        self.report.get_summary()
        return self.report

    def _scan_edge_functions(self):
        """Escanea Supabase Edge Functions."""
        functions_dir = os.path.join(self.project_path, "supabase", "functions")
        if not os.path.isdir(functions_dir):
            return

        for func_dir in os.listdir(functions_dir):
            func_path = os.path.join(functions_dir, func_dir)
            if not os.path.isdir(func_path):
                continue

            self._metrics["edge_functions"] += 1
            index_file = os.path.join(func_path, "index.ts")

            if not os.path.exists(index_file):
                rel = os.path.relpath(func_path, self.project_path)
                self.report.add(APIFinding(
                    severity="MEDIUM", category="API/Structure",
                    title=f"Edge function without index.ts: {func_dir}",
                    description="Edge function directory exists but has no entry point",
                    file_path=rel,
                ))
                continue

            try:
                with open(index_file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    lines = content.split("\n")
            except Exception:
                continue

            rel = os.path.relpath(index_file, self.project_path)
            self.report.files_scanned += 1

            # Check CORS headers
            if "Access-Control" in content:
                self._metrics["cors_configs"] += 1
                if "'*'" in content and "Allow-Origin" in content:
                    self.report.add(APIFinding(
                        severity="MEDIUM", category="API/CORS",
                        title=f"Wildcard CORS in edge function: {func_dir}",
                        description="Access-Control-Allow-Origin: * allows any domain",
                        file_path=rel,
                        recommendation="Restrict to your specific domain(s)",
                    ))

            # Check for error handling
            has_try_catch = "try" in content and "catch" in content
            if not has_try_catch:
                self.report.add(APIFinding(
                    severity="HIGH", category="API/Error Handling",
                    title=f"Edge function without try/catch: {func_dir}",
                    description="Unhandled errors crash the function and return 500",
                    file_path=rel,
                    recommendation="Wrap handler in try/catch and return proper error responses",
                ))

            # Check for input validation
            has_validation = bool(re.search(r"(?:z\.|zod|validate|schema|\.parse\(|typeof|instanceof)", content, re.IGNORECASE))
            if not has_validation:
                self.report.add(APIFinding(
                    severity="HIGH", category="API/Validation",
                    title=f"Edge function without input validation: {func_dir}",
                    description="No input validation detected - trusting client data is dangerous",
                    file_path=rel,
                    recommendation="Validate all inputs with Zod or manual checks before processing",
                ))

            # Check for auth verification
            has_auth = bool(re.search(r"(?:authorization|bearer|jwt|getUser|auth\.getUser|supabaseClient)", content, re.IGNORECASE))
            if not has_auth:
                self.report.add(APIFinding(
                    severity="MEDIUM", category="API/Auth",
                    title=f"Edge function without auth check: {func_dir}",
                    description="No authentication verification detected",
                    file_path=rel,
                    recommendation="Verify JWT/auth token before processing requests",
                ))

            # Check for rate limiting
            if re.search(r"(?:rate.?limit|throttle|x-ratelimit)", content, re.IGNORECASE):
                self._metrics["has_rate_limiting"] = True

            # Check for proper HTTP method handling
            if not re.search(r"""(?:req\.method|request\.method)\s*[!=]==?\s*['"]""", content):
                if "Deno.serve" in content:
                    self.report.add(APIFinding(
                        severity="LOW", category="API/Structure",
                        title=f"Edge function without HTTP method check: {func_dir}",
                        description="Function handles all HTTP methods the same way",
                        file_path=rel,
                        recommendation="Check request.method and handle GET/POST/etc. appropriately",
                    ))

            # Check for response status codes
            if not re.search(r"""new Response\s*\([^)]*\{\s*status\s*:\s*(?:4|5)\d{2}""", content):
                self.report.add(APIFinding(
                    severity="LOW", category="API/Error Handling",
                    title=f"Edge function may not return proper error status codes: {func_dir}",
                    description="Always return appropriate HTTP status codes (400, 401, 404, 500)",
                    file_path=rel,
                    recommendation="Return 400 for bad input, 401 for auth errors, 500 for server errors",
                ))

            # Check for secrets in code
            for line_num, line in enumerate(lines, 1):
                if re.search(r"""(?:api[_-]?key|secret|password)\s*[:=]\s*['"][^'"]{10,}['"]""", line, re.IGNORECASE):
                    self.report.add(APIFinding(
                        severity="CRITICAL", category="API/Security",
                        title=f"Hardcoded secret in edge function: {func_dir}",
                        description="Secrets must use Deno.env.get() not hardcoded values",
                        file_path=rel, line_number=line_num,
                        recommendation="Use Deno.env.get('SECRET_NAME') and store in Supabase secrets",
                    ))

    def _scan_api_calls(self):
        """Escanea llamadas a APIs desde el frontend."""
        src_dir = os.path.join(self.project_path, "src")
        if not os.path.isdir(src_dir):
            return

        for root, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in (".ts", ".tsx", ".js", ".jsx"):
                    continue

                fpath = os.path.join(root, fname)
                self.report.files_scanned += 1

                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        lines = content.split("\n")
                except Exception:
                    continue

                rel = os.path.relpath(fpath, self.project_path)

                for line_num, line in enumerate(lines, 1):
                    stripped = line.strip()
                    if stripped.startswith("//") or stripped.startswith("*"):
                        continue

                    # Fetch without error handling
                    if re.search(r"""(?:fetch|axios\.\w+)\s*\(""", line):
                        self._metrics["api_calls"] += 1
                        # Check surrounding context for error handling
                        context = "\n".join(lines[max(0, line_num-3):min(len(lines), line_num+8)])
                        if "catch" not in context and "try" not in context and ".catch" not in context:
                            self._metrics["unhandled_errors"] += 1
                            self.report.add(APIFinding(
                                severity="MEDIUM", category="API/Error Handling",
                                title="API call without error handling",
                                description="Network requests can fail - unhandled errors crash the UI",
                                file_path=rel, line_number=line_num,
                                code_snippet=stripped[:150],
                                recommendation="Wrap in try/catch or add .catch() handler",
                            ))

                    # Hardcoded API URLs (not from env)
                    if re.search(r"""(?:fetch|axios|supabase\.functions\.invoke)\s*\(\s*['"]https?://(?!localhost)""", line):
                        self.report.add(APIFinding(
                            severity="MEDIUM", category="API/Configuration",
                            title="Hardcoded API URL",
                            description="API URLs should come from environment variables",
                            file_path=rel, line_number=line_num,
                            code_snippet=stripped[:150],
                            recommendation="Use import.meta.env.VITE_API_URL or similar",
                        ))

                    # Supabase RPC calls
                    if re.search(r"""\.rpc\s*\(""", line):
                        self._metrics["supabase_rpcs"] += 1

    def _scan_supabase_functions(self):
        """Escanea funciones SQL de Supabase."""
        migrations_dir = os.path.join(self.project_path, "supabase", "migrations")
        if not os.path.isdir(migrations_dir):
            return

        for fname in os.listdir(migrations_dir):
            if not fname.endswith(".sql"):
                continue

            fpath = os.path.join(migrations_dir, fname)
            self.report.files_scanned += 1

            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    lines = content.split("\n")
            except Exception:
                continue

            rel = os.path.relpath(fpath, self.project_path)

            for line_num, line in enumerate(lines, 1):
                # Functions with SECURITY DEFINER (run as owner, not caller)
                if re.search(r"security\s+definer", line, re.IGNORECASE):
                    self.report.add(APIFinding(
                        severity="HIGH", category="API/Database",
                        title="SECURITY DEFINER function",
                        description="Function runs with owner privileges, bypassing RLS",
                        file_path=rel, line_number=line_num,
                        recommendation="Use SECURITY INVOKER unless you specifically need elevated privileges",
                    ))

                # Functions without search_path
                if re.search(r"create\s+(?:or\s+replace\s+)?function", line, re.IGNORECASE):
                    context = "\n".join(lines[line_num-1:min(len(lines), line_num+10)])
                    if "search_path" not in context.lower():
                        self.report.add(APIFinding(
                            severity="MEDIUM", category="API/Database",
                            title="Function without explicit search_path",
                            description="Without search_path, function may resolve to unexpected schemas",
                            file_path=rel, line_number=line_num,
                            recommendation="Add SET search_path = public; to function definition",
                        ))

                # Triggers without audit
                if re.search(r"create\s+trigger", line, re.IGNORECASE):
                    self.report.add(APIFinding(
                        severity="INFO", category="API/Database",
                        title="Database trigger detected",
                        description="Verify trigger logic and ensure it handles errors gracefully",
                        file_path=rel, line_number=line_num,
                        recommendation="Test triggers thoroughly - they run silently and can cause data issues",
                    ))

    def _check_validation_library(self):
        """Verifica si hay una libreria de validacion."""
        pkg_path = os.path.join(self.project_path, "package.json")
        if not os.path.exists(pkg_path):
            return

        try:
            with open(pkg_path, "r") as f:
                pkg = json.load(f)
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

            validators = {
                "zod": "Zod",
                "yup": "Yup",
                "joi": "Joi",
                "class-validator": "class-validator",
                "superstruct": "Superstruct",
                "valibot": "Valibot",
            }

            found = [name for dep, name in validators.items() if dep in deps]
            self._metrics["has_input_validation"] = bool(found)
            self._metrics["has_zod"] = "zod" in deps

            if not found:
                self.report.add(APIFinding(
                    severity="MEDIUM", category="API/Validation",
                    title="No input validation library installed",
                    description="Without schema validation, bad data can corrupt your database",
                    file_path="package.json",
                    recommendation="Install Zod for type-safe runtime validation: npm i zod",
                ))

        except Exception:
            pass

    def _check_error_handling_patterns(self):
        """Verifica patrones de error handling global."""
        src_dir = os.path.join(self.project_path, "src")
        if not os.path.isdir(src_dir):
            return

        has_error_boundary = False
        has_global_error_handler = False
        has_toast_errors = False

        for root, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            for fname in files:
                if not fname.endswith((".ts", ".tsx", ".js", ".jsx")):
                    continue

                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                    if "ErrorBoundary" in content or "componentDidCatch" in content:
                        has_error_boundary = True
                    if re.search(r"(?:window\.onerror|window\.addEventListener.*(?:error|unhandledrejection))", content):
                        has_global_error_handler = True
                    if re.search(r"(?:toast\.error|toast\(.*error|sonner|react-toastify|react-hot-toast)", content, re.IGNORECASE):
                        has_toast_errors = True
                except Exception:
                    pass

        if not has_error_boundary:
            self.report.add(APIFinding(
                severity="MEDIUM", category="API/Error Handling",
                title="No React Error Boundary detected",
                description="Without error boundaries, component errors crash the entire app",
                file_path="(project-wide)",
                recommendation="Add ErrorBoundary components to catch and display errors gracefully",
            ))

        if not has_toast_errors and self._metrics["api_calls"] > 3:
            self.report.add(APIFinding(
                severity="LOW", category="API/UX",
                title="No error notification system detected",
                description="Users need feedback when API calls fail",
                file_path="(project-wide)",
                recommendation="Use react-hot-toast or sonner to show error messages to users",
            ))

    def _generate_findings(self):
        """Genera hallazgos basados en metricas globales."""
        if self._metrics["edge_functions"] > 0 and not self._metrics["has_rate_limiting"]:
            self.report.add(APIFinding(
                severity="HIGH", category="API/Security",
                title="No rate limiting on edge functions",
                description=f"{self._metrics['edge_functions']} edge functions without rate limiting",
                file_path="supabase/functions/",
                recommendation="Implement rate limiting using Upstash Redis or custom headers",
            ))

        if self._metrics["unhandled_errors"] > 5:
            self.report.add(APIFinding(
                severity="HIGH", category="API/Error Handling",
                title=f"Many API calls without error handling: {self._metrics['unhandled_errors']}",
                description="Multiple unhandled API calls will cause crashes when the network fails",
                file_path="(project-wide)",
                recommendation="Wrap all API calls in try/catch. Better: use react-query which handles errors automatically.",
            ))
