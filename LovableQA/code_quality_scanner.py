"""
Code Quality / Tech Debt Scanner for Lovable Projects
=======================================================
Detecta TypeScript 'any', console.logs, TODO/FIXME, codigo muerto,
imports sin usar, y patrones de tech debt.
"""

import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field


@dataclass
class CodeQualityFinding:
    severity: str
    category: str
    title: str
    description: str
    file_path: str
    line_number: int = 0
    code_snippet: str = ""
    recommendation: str = ""


@dataclass
class CodeQualityReport:
    findings: list = field(default_factory=list)
    files_scanned: int = 0
    metrics: dict = field(default_factory=dict)
    summary: dict = field(default_factory=dict)

    def add(self, finding: CodeQualityFinding):
        self.findings.append(finding)

    def get_summary(self):
        counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        self.summary = counts
        return counts


class CodeQualityScanner:
    """Escanea un proyecto Lovable en busca de problemas de calidad de codigo."""

    SCAN_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
    SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", "coverage", "__pycache__"}

    def __init__(self, project_path: str):
        self.project_path = os.path.abspath(project_path)
        self.report = CodeQualityReport()
        self._metrics = {
            "any_count": 0,
            "console_log_count": 0,
            "todo_count": 0,
            "fixme_count": 0,
            "hack_count": 0,
            "ts_ignore_count": 0,
            "eslint_disable_count": 0,
            "empty_catch_count": 0,
            "long_functions": [],
            "deeply_nested": [],
            "duplicate_strings": Counter(),
            "total_files": 0,
            "total_lines": 0,
        }
        self._exports = defaultdict(set)  # file -> set of exports
        self._imports = defaultdict(set)  # module -> set of files importing it

    def scan(self) -> CodeQualityReport:
        print("  [Code Quality] Escaneando archivos...")
        files = self._collect_files()
        self.report.files_scanned = len(files)
        self._metrics["total_files"] = len(files)

        for file_path in files:
            self._scan_file(file_path)

        self._check_unused_exports()
        self._check_config_quality()
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
        self._metrics["total_lines"] += len(lines)

        # Track exports
        for match in re.finditer(r"export\s+(?:default\s+)?(?:function|const|class|type|interface|enum)\s+(\w+)", content):
            self._exports[rel_path].add(match.group(1))

        # Track imports
        for match in re.finditer(r"""from\s+['"]([^'"]+)['"]""", content):
            self._imports[match.group(1)].add(rel_path)

        # Line-by-line analysis
        nesting_depth = 0
        function_start = 0
        function_name = ""
        in_function = False
        brace_count = 0

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()

            # Skip comments for most checks
            is_comment = stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*")

            # --- TypeScript 'any' ---
            if not is_comment and re.search(r"""\b(?::\s*any\b|as\s+any\b|<any>)""", line):
                self._metrics["any_count"] += 1
                self.report.add(CodeQualityFinding(
                    severity="MEDIUM",
                    category="TypeScript",
                    title="TypeScript 'any' type usage",
                    description="'any' bypasses type checking and defeats the purpose of TypeScript",
                    file_path=rel_path,
                    line_number=line_num,
                    code_snippet=stripped[:150],
                    recommendation="Use a specific type, 'unknown', or a generic instead of 'any'",
                ))

            # --- console.log ---
            if not is_comment and re.search(r"""\bconsole\.(?:log|debug|info|warn|error)\s*\(""", line):
                self._metrics["console_log_count"] += 1
                # Only flag log/debug, not warn/error
                if re.search(r"""\bconsole\.(?:log|debug)\s*\(""", line):
                    self.report.add(CodeQualityFinding(
                        severity="LOW",
                        category="Code Quality",
                        title="console.log left in code",
                        description="Debug logs should be removed before production",
                        file_path=rel_path,
                        line_number=line_num,
                        code_snippet=stripped[:150],
                        recommendation="Remove console.log or use a proper logging library",
                    ))

            # --- TODO/FIXME/HACK ---
            todo_match = re.search(r"""\b(TODO|FIXME|HACK|XXX|TEMP|TEMPORARY)\b[:\s]*(.*)""", line, re.IGNORECASE)
            if todo_match:
                tag = todo_match.group(1).upper()
                desc = todo_match.group(2).strip()[:100]
                if tag == "TODO":
                    self._metrics["todo_count"] += 1
                elif tag == "FIXME":
                    self._metrics["fixme_count"] += 1
                elif tag in ("HACK", "XXX", "TEMP", "TEMPORARY"):
                    self._metrics["hack_count"] += 1

                severity = "MEDIUM" if tag in ("FIXME", "HACK", "XXX") else "LOW"
                self.report.add(CodeQualityFinding(
                    severity=severity,
                    category="Tech Debt",
                    title=f"{tag}: {desc}" if desc else f"{tag} comment found",
                    description=f"Unresolved {tag} in code",
                    file_path=rel_path,
                    line_number=line_num,
                    recommendation="Address the TODO/FIXME or create a ticket to track it",
                ))

            # --- @ts-ignore / @ts-nocheck / eslint-disable ---
            if "@ts-ignore" in line or "@ts-nocheck" in line:
                self._metrics["ts_ignore_count"] += 1
                self.report.add(CodeQualityFinding(
                    severity="MEDIUM",
                    category="TypeScript",
                    title="@ts-ignore/@ts-nocheck suppressing type errors",
                    description="Suppressed type errors may hide real bugs",
                    file_path=rel_path,
                    line_number=line_num,
                    recommendation="Fix the underlying type error instead of suppressing it",
                ))

            if "eslint-disable" in line:
                self._metrics["eslint_disable_count"] += 1
                if "eslint-disable-next-line" not in line:  # whole-file disable is worse
                    self.report.add(CodeQualityFinding(
                        severity="MEDIUM",
                        category="Code Quality",
                        title="ESLint rules disabled",
                        description="Disabling linting rules may hide code quality issues",
                        file_path=rel_path,
                        line_number=line_num,
                        recommendation="Fix the lint error or use eslint-disable-next-line for specific lines",
                    ))

            # --- Empty catch blocks ---
            if not is_comment and re.search(r"""catch\s*\([^)]*\)\s*\{\s*\}""", line):
                self._metrics["empty_catch_count"] += 1
                self.report.add(CodeQualityFinding(
                    severity="MEDIUM",
                    category="Error Handling",
                    title="Empty catch block - errors silently swallowed",
                    description="Catching errors without handling them hides bugs",
                    file_path=rel_path,
                    line_number=line_num,
                    recommendation="Log the error or handle it appropriately",
                ))

            # --- Nesting depth tracking ---
            if not is_comment:
                opens = line.count("{") - line.count("}")
                nesting_depth += opens
                if nesting_depth > 5:
                    self._metrics["deeply_nested"].append((rel_path, line_num, nesting_depth))

            # --- Magic numbers ---
            if not is_comment:
                magic = re.findall(r"""(?<!=\s)(?<!['".\w])\b(\d{3,})\b(?!\s*[;:,}\]])""", line)
                for num in magic:
                    if num not in ("100", "200", "201", "204", "301", "302", "400", "401", "403", "404", "500"):
                        self.report.add(CodeQualityFinding(
                            severity="LOW",
                            category="Code Quality",
                            title=f"Magic number: {num}",
                            description="Unnamed numeric literals make code harder to understand",
                            file_path=rel_path,
                            line_number=line_num,
                            code_snippet=stripped[:150],
                            recommendation="Extract to a named constant",
                        ))
                        break  # one per line

            # --- Duplicate string literals ---
            if not is_comment:
                strings = re.findall(r"""['"]([^'"]{10,60})['"]""", line)
                for s in strings:
                    if not s.startswith(("http", "/", "./", "../", "text-", "bg-", "flex", "grid")):
                        self._metrics["duplicate_strings"][s] += 1

    def _check_unused_exports(self):
        """Detecta exportaciones que nunca se importan (codigo muerto potencial)."""
        # Build set of all imported names
        all_imported_content = set()
        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext in self.SCAN_EXTENSIONS:
                    try:
                        with open(os.path.join(root, fname), "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                        # Collect imported names
                        for match in re.finditer(r"""import\s+\{([^}]+)\}""", content):
                            names = [n.strip().split(" as ")[0].strip() for n in match.group(1).split(",")]
                            all_imported_content.update(names)
                        # Default imports
                        for match in re.finditer(r"""import\s+(\w+)\s+from""", content):
                            all_imported_content.add(match.group(1))
                    except Exception:
                        pass

        # Check which exports are never imported (rough heuristic)
        unused_count = 0
        for file_path, exports in self._exports.items():
            for export_name in exports:
                if export_name not in all_imported_content:
                    # Skip common entry points and page components
                    if export_name in ("App", "default", "main", "Root"):
                        continue
                    if "page" in file_path.lower() or "index" in file_path.lower():
                        continue
                    unused_count += 1

        if unused_count > 10:
            self.report.add(CodeQualityFinding(
                severity="LOW",
                category="Tech Debt",
                title=f"~{unused_count} potentially unused exports detected",
                description="Exports that are never imported may be dead code",
                file_path="(project-wide)",
                recommendation="Run 'npx ts-prune' or 'npx knip' for accurate dead code detection",
            ))

    def _check_config_quality(self):
        """Verifica configuracion del proyecto."""
        # TypeScript config
        tsconfig = os.path.join(self.project_path, "tsconfig.json")
        if os.path.exists(tsconfig):
            try:
                with open(tsconfig, "r") as f:
                    content = f.read()
                    # Remove comments for JSON parsing
                    content_clean = re.sub(r"//.*$", "", content, flags=re.MULTILINE)
                    config = json.loads(content_clean)

                compiler = config.get("compilerOptions", {})

                if not compiler.get("strict"):
                    self.report.add(CodeQualityFinding(
                        severity="MEDIUM",
                        category="TypeScript",
                        title="TypeScript strict mode not enabled",
                        description="Strict mode catches more bugs at compile time",
                        file_path="tsconfig.json",
                        recommendation="Set 'strict': true in compilerOptions",
                    ))

                if compiler.get("noImplicitAny") is False:
                    self.report.add(CodeQualityFinding(
                        severity="MEDIUM",
                        category="TypeScript",
                        title="noImplicitAny is disabled",
                        description="Allows implicit 'any' types, weakening type safety",
                        file_path="tsconfig.json",
                        recommendation="Enable noImplicitAny (or strict mode)",
                    ))
            except Exception:
                pass
        else:
            # Check if it's a TS project without tsconfig
            pkg_path = os.path.join(self.project_path, "package.json")
            if os.path.exists(pkg_path):
                try:
                    with open(pkg_path, "r") as f:
                        content = f.read()
                    if "typescript" in content:
                        self.report.add(CodeQualityFinding(
                            severity="MEDIUM",
                            category="TypeScript",
                            title="TypeScript dependency found but no tsconfig.json",
                            description="Missing TypeScript configuration",
                            file_path="(root)",
                            recommendation="Run 'npx tsc --init' to generate tsconfig.json",
                        ))
                except Exception:
                    pass

        # ESLint config
        eslint_configs = [".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.cjs", "eslint.config.js", "eslint.config.mjs"]
        has_eslint = any(os.path.exists(os.path.join(self.project_path, c)) for c in eslint_configs)
        if not has_eslint:
            self.report.add(CodeQualityFinding(
                severity="MEDIUM",
                category="Code Quality",
                title="No ESLint configuration found",
                description="Linting catches bugs and enforces consistent code style",
                file_path="(root)",
                recommendation="Set up ESLint with TypeScript plugin",
            ))

        # Prettier
        prettier_configs = [".prettierrc", ".prettierrc.js", ".prettierrc.json", "prettier.config.js"]
        has_prettier = any(os.path.exists(os.path.join(self.project_path, c)) for c in prettier_configs)
        if not has_prettier:
            pkg_path = os.path.join(self.project_path, "package.json")
            if os.path.exists(pkg_path):
                try:
                    with open(pkg_path, "r") as f:
                        content = f.read()
                    if "prettier" not in content:
                        self.report.add(CodeQualityFinding(
                            severity="LOW",
                            category="Code Quality",
                            title="No Prettier configuration found",
                            description="Automatic code formatting ensures consistent style",
                            file_path="(root)",
                            recommendation="Install and configure Prettier",
                        ))
                except Exception:
                    pass

    def _generate_metric_findings(self):
        """Genera hallazgos basados en metricas globales."""
        if self._metrics["any_count"] > 10:
            self.report.add(CodeQualityFinding(
                severity="HIGH",
                category="TypeScript",
                title=f"High 'any' usage: {self._metrics['any_count']} instances",
                description="Excessive 'any' types significantly weaken type safety",
                file_path="(project-wide)",
                recommendation="Gradually replace 'any' with proper types. Use 'unknown' as safer alternative.",
            ))

        if self._metrics["todo_count"] + self._metrics["fixme_count"] > 15:
            total = self._metrics["todo_count"] + self._metrics["fixme_count"]
            self.report.add(CodeQualityFinding(
                severity="MEDIUM",
                category="Tech Debt",
                title=f"High TODO/FIXME count: {total} comments",
                description="Many unresolved TODO/FIXME indicate accumulated tech debt",
                file_path="(project-wide)",
                recommendation="Triage TODOs: resolve, create tickets, or remove stale ones",
            ))

        if self._metrics["ts_ignore_count"] > 5:
            self.report.add(CodeQualityFinding(
                severity="HIGH",
                category="TypeScript",
                title=f"Many @ts-ignore: {self._metrics['ts_ignore_count']} suppressions",
                description="Too many type error suppressions undermine TypeScript's value",
                file_path="(project-wide)",
                recommendation="Fix type errors instead of suppressing them",
            ))

        if self._metrics["empty_catch_count"] > 3:
            self.report.add(CodeQualityFinding(
                severity="HIGH",
                category="Error Handling",
                title=f"Multiple empty catch blocks: {self._metrics['empty_catch_count']}",
                description="Silent error swallowing makes debugging very difficult",
                file_path="(project-wide)",
                recommendation="At minimum, log caught errors. Better: handle them properly.",
            ))

        # Duplicate strings
        dupes = [(s, c) for s, c in self._metrics["duplicate_strings"].items() if c >= 4]
        if len(dupes) > 5:
            self.report.add(CodeQualityFinding(
                severity="LOW",
                category="Code Quality",
                title=f"{len(dupes)} string literals repeated 4+ times",
                description="Duplicated strings are error-prone and hard to update",
                file_path="(project-wide)",
                recommendation="Extract repeated strings to constants or i18n keys",
            ))

        # Deep nesting
        deep = [(f, l, d) for f, l, d in self._metrics["deeply_nested"] if d >= 6]
        if len(deep) > 3:
            self.report.add(CodeQualityFinding(
                severity="MEDIUM",
                category="Code Quality",
                title=f"Deeply nested code ({len(deep)} locations with 6+ levels)",
                description="Deep nesting makes code hard to read and maintain",
                file_path="(project-wide)",
                recommendation="Use early returns, extract functions, or flatten conditionals",
            ))


import json
