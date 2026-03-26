"""
Testing Coverage Scanner for Lovable Projects
===============================================
Verifica si existen tests, frameworks configurados,
cobertura aproximada, y flujos criticos sin tests.
"""

import os
import re
import json
from dataclasses import dataclass, field


@dataclass
class TestingFinding:
    severity: str
    category: str
    title: str
    description: str
    file_path: str
    line_number: int = 0
    code_snippet: str = ""
    recommendation: str = ""


@dataclass
class TestingReport:
    findings: list = field(default_factory=list)
    files_scanned: int = 0
    metrics: dict = field(default_factory=dict)
    summary: dict = field(default_factory=dict)

    def add(self, finding: TestingFinding):
        self.findings.append(finding)

    def get_summary(self):
        counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        self.summary = counts
        return counts


class TestingScanner:
    """Escanea un proyecto Lovable para evaluar cobertura de tests."""

    SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", "coverage"}
    SRC_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx"}

    def __init__(self, project_path: str):
        self.project_path = os.path.abspath(project_path)
        self.report = TestingReport()
        self._metrics = {
            "test_files": 0,
            "test_lines": 0,
            "source_files": 0,
            "source_lines": 0,
            "test_frameworks": [],
            "test_patterns": [],
            "has_e2e": False,
            "has_unit": False,
            "has_integration": False,
            "coverage_config": False,
            "ci_tests": False,
            "critical_untested": [],
        }

    def scan(self) -> TestingReport:
        print("  [Testing] Escaneando archivos...")
        self._check_test_framework()
        self._scan_test_files()
        self._identify_critical_untested()
        self._check_ci_config()
        self._check_testing_utilities()
        self._generate_findings()

        self.report.metrics = self._metrics
        self.report.get_summary()
        return self.report

    def _check_test_framework(self):
        """Verifica que frameworks de testing esten instalados."""
        pkg_path = os.path.join(self.project_path, "package.json")
        if not os.path.exists(pkg_path):
            self.report.add(TestingFinding(
                severity="HIGH", category="Testing/Setup",
                title="No package.json found",
                description="Cannot determine test framework",
                file_path="(root)",
            ))
            return

        try:
            with open(pkg_path, "r") as f:
                pkg = json.load(f)

            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            scripts = pkg.get("scripts", {})

            # Test frameworks
            frameworks = {
                "vitest": "Vitest",
                "jest": "Jest",
                "@jest/core": "Jest",
                "@testing-library/react": "React Testing Library",
                "@testing-library/jest-dom": "Testing Library Jest DOM",
                "cypress": "Cypress (E2E)",
                "playwright": "Playwright (E2E)",
                "@playwright/test": "Playwright (E2E)",
            }

            found = []
            for dep, name in frameworks.items():
                if dep in deps:
                    found.append(name)
                    if "E2E" in name:
                        self._metrics["has_e2e"] = True

            self._metrics["test_frameworks"] = found

            if not found:
                self.report.add(TestingFinding(
                    severity="HIGH", category="Testing/Setup",
                    title="No testing framework installed",
                    description="No Vitest, Jest, Cypress, or Playwright found in dependencies",
                    file_path="package.json",
                    recommendation="Install Vitest (recommended for Vite projects): npm i -D vitest @testing-library/react",
                ))

            # Test script
            has_test_script = any(
                k in scripts for k in ["test", "test:unit", "test:e2e", "test:integration"]
            )
            if not has_test_script:
                self.report.add(TestingFinding(
                    severity="MEDIUM", category="Testing/Setup",
                    title="No 'test' script in package.json",
                    description="No npm test command configured",
                    file_path="package.json",
                    recommendation="Add 'test': 'vitest' to scripts in package.json",
                ))

            # Coverage config
            if any("coverage" in str(v) for v in scripts.values()):
                self._metrics["coverage_config"] = True
            if "c8" in deps or "istanbul" in str(deps) or "@vitest/coverage" in str(deps):
                self._metrics["coverage_config"] = True

            if not self._metrics["coverage_config"] and found:
                self.report.add(TestingFinding(
                    severity="LOW", category="Testing/Coverage",
                    title="No coverage configuration detected",
                    description="Code coverage helps track testing progress",
                    file_path="package.json",
                    recommendation="Add 'test:coverage': 'vitest run --coverage' to scripts",
                ))

        except Exception:
            pass

    def _scan_test_files(self):
        """Escanea archivos de test existentes."""
        test_patterns = [
            r"\.test\.\w+$",
            r"\.spec\.\w+$",
            r"__tests__",
        ]

        source_files = []
        test_files = []

        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]

            # Skip test/e2e directories for source count
            is_test_dir = any(p in root.lower() for p in ["__tests__", "test", "tests", "e2e", "cypress", "playwright"])

            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in self.SRC_EXTENSIONS:
                    continue

                fpath = os.path.join(root, fname)
                is_test = any(re.search(p, fname) for p in test_patterns) or is_test_dir

                if is_test:
                    test_files.append(fpath)
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            lines = len(f.readlines())
                        self._metrics["test_lines"] += lines
                    except Exception:
                        pass
                else:
                    source_files.append(fpath)
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            lines = len(f.readlines())
                        self._metrics["source_lines"] += lines
                    except Exception:
                        pass

        self._metrics["test_files"] = len(test_files)
        self._metrics["source_files"] = len(source_files)
        self.report.files_scanned = len(test_files) + len(source_files)

        # Analyze test quality
        for fpath in test_files:
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                rel = os.path.relpath(fpath, self.project_path)

                # Check for meaningful assertions
                assertions = len(re.findall(r"(?:expect|assert|should|toBe|toEqual|toHave|toContain)", content))
                test_blocks = len(re.findall(r"(?:it|test)\s*\(", content))

                if test_blocks > 0 and assertions == 0:
                    self.report.add(TestingFinding(
                        severity="MEDIUM", category="Testing/Quality",
                        title=f"Test file without assertions: {os.path.basename(fpath)}",
                        description="Tests without assertions don't verify behavior",
                        file_path=rel,
                        recommendation="Add expect() assertions to verify expected outcomes",
                    ))

                if "it.skip" in content or "test.skip" in content or "xit(" in content:
                    self.report.add(TestingFinding(
                        severity="LOW", category="Testing/Quality",
                        title=f"Skipped tests in {os.path.basename(fpath)}",
                        description="Skipped tests may indicate broken or incomplete tests",
                        file_path=rel,
                        recommendation="Fix or remove skipped tests",
                    ))

                # Detect test types
                if re.search(r"(?:render|screen|fireEvent|userEvent|getBy|queryBy|findBy)", content):
                    self._metrics["has_unit"] = True
                if re.search(r"(?:page\.goto|cy\.visit|browser\.url)", content):
                    self._metrics["has_e2e"] = True
                if re.search(r"(?:supabase|fetch|api|request)\s*\(", content) and "mock" not in content.lower():
                    self._metrics["has_integration"] = True

            except Exception:
                pass

    def _identify_critical_untested(self):
        """Identifica flujos criticos que probablemente no tienen tests."""
        critical_patterns = {
            "auth": (r"(?:login|signIn|signUp|signOut|register|auth)", "Authentication flow"),
            "payment": (r"(?:payment|checkout|stripe|billing|subscription)", "Payment/billing flow"),
            "form": (r"(?:onSubmit|handleSubmit|formData)", "Form submission"),
            "api": (r"(?:fetch|axios|supabase.*(?:insert|update|delete))", "API mutations"),
            "routing": (r"(?:ProtectedRoute|RequireAuth|PrivateRoute)", "Protected routes"),
        }

        # Get set of tested modules (rough heuristic)
        tested_modules = set()
        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            for fname in files:
                if re.search(r"\.(?:test|spec)\.", fname):
                    # Infer what module it tests
                    base = re.sub(r"\.(?:test|spec)\.\w+$", "", fname)
                    tested_modules.add(base.lower())

        src_dir = os.path.join(self.project_path, "src")
        if not os.path.isdir(src_dir):
            return

        for root, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in self.SRC_EXTENSIONS:
                    continue
                if re.search(r"\.(?:test|spec)\.", fname):
                    continue

                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                except Exception:
                    continue

                base = os.path.splitext(fname)[0].lower()
                has_test = base in tested_modules

                if not has_test:
                    for key, (pattern, desc) in critical_patterns.items():
                        if re.search(pattern, content, re.IGNORECASE):
                            rel = os.path.relpath(fpath, self.project_path)
                            self._metrics["critical_untested"].append((rel, desc))
                            self.report.add(TestingFinding(
                                severity="HIGH", category="Testing/Coverage",
                                title=f"Critical flow without tests: {desc}",
                                description=f"{os.path.basename(fpath)} contains {desc} logic but has no test file",
                                file_path=rel,
                                recommendation=f"Create {base}.test.tsx to test {desc}",
                            ))
                            break  # one finding per file

    def _check_ci_config(self):
        """Verifica si hay tests en CI/CD."""
        ci_files = [
            ".github/workflows",
            ".gitlab-ci.yml",
            "Jenkinsfile",
            ".circleci/config.yml",
            "vercel.json",
            "netlify.toml",
        ]

        for ci in ci_files:
            ci_path = os.path.join(self.project_path, ci)
            if os.path.exists(ci_path):
                if os.path.isdir(ci_path):
                    for fname in os.listdir(ci_path):
                        fpath = os.path.join(ci_path, fname)
                        try:
                            with open(fpath, "r") as f:
                                content = f.read()
                            if re.search(r"(?:npm\s+(?:run\s+)?test|vitest|jest|cypress|playwright)", content):
                                self._metrics["ci_tests"] = True
                        except Exception:
                            pass
                else:
                    try:
                        with open(ci_path, "r") as f:
                            content = f.read()
                        if re.search(r"(?:npm\s+(?:run\s+)?test|vitest|jest)", content):
                            self._metrics["ci_tests"] = True
                    except Exception:
                        pass

        if not self._metrics["ci_tests"]:
            self.report.add(TestingFinding(
                severity="MEDIUM", category="Testing/CI",
                title="No tests configured in CI/CD pipeline",
                description="Tests should run automatically on every push/PR",
                file_path="(project-wide)",
                recommendation="Add a test step to your CI pipeline (GitHub Actions, Vercel, etc.)",
            ))

    def _check_testing_utilities(self):
        """Verifica utilidades de testing (mocks, fixtures, etc.)."""
        src_dir = os.path.join(self.project_path, "src")
        if not os.path.isdir(src_dir):
            return

        has_msw = False
        has_test_utils = False

        pkg_path = os.path.join(self.project_path, "package.json")
        if os.path.exists(pkg_path):
            try:
                with open(pkg_path, "r") as f:
                    deps = json.load(f)
                all_deps = {**deps.get("dependencies", {}), **deps.get("devDependencies", {})}
                has_msw = "msw" in all_deps
            except Exception:
                pass

        # Check for test utilities
        util_patterns = ["test-utils", "testUtils", "test-helpers", "testHelpers", "setupTests", "setup-tests"]
        for root, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            for fname in files:
                if any(p in fname for p in util_patterns):
                    has_test_utils = True

        if self._metrics["test_files"] > 5 and not has_test_utils:
            self.report.add(TestingFinding(
                severity="LOW", category="Testing/Quality",
                title="No shared test utilities detected",
                description="Test helpers (custom renders, mock providers) reduce duplication",
                file_path="src/",
                recommendation="Create a test-utils.tsx with custom render wrapping providers",
            ))

        if self._metrics["test_files"] > 3 and not has_msw:
            self.report.add(TestingFinding(
                severity="INFO", category="Testing/Quality",
                title="MSW (Mock Service Worker) not installed",
                description="MSW provides realistic API mocking for tests",
                file_path="package.json",
                recommendation="Consider MSW for mocking Supabase/API calls in tests",
            ))

    def _generate_findings(self):
        """Genera hallazgos basados en metricas globales."""
        tf = self._metrics["test_files"]
        sf = self._metrics["source_files"]

        if tf == 0 and sf > 0:
            self.report.add(TestingFinding(
                severity="CRITICAL", category="Testing/Coverage",
                title="No test files found in the project",
                description=f"{sf} source files with zero tests",
                file_path="(project-wide)",
                recommendation="Start with tests for critical flows: auth, data mutations, form submissions",
            ))
        elif sf > 0:
            ratio = tf / sf
            if ratio < 0.1:
                self.report.add(TestingFinding(
                    severity="HIGH", category="Testing/Coverage",
                    title=f"Very low test coverage: {tf} test files for {sf} source files ({ratio:.0%})",
                    description="Most source files have no corresponding test",
                    file_path="(project-wide)",
                    recommendation="Aim for at least 1 test file per critical module",
                ))
            elif ratio < 0.3:
                self.report.add(TestingFinding(
                    severity="MEDIUM", category="Testing/Coverage",
                    title=f"Low test coverage: {tf} test files for {sf} source files ({ratio:.0%})",
                    description="Significant portions of code are untested",
                    file_path="(project-wide)",
                    recommendation="Gradually increase coverage, prioritizing business-critical code",
                ))

        if self._metrics["test_files"] > 0 and not self._metrics["has_e2e"]:
            self.report.add(TestingFinding(
                severity="MEDIUM", category="Testing/Coverage",
                title="No end-to-end (E2E) tests detected",
                description="E2E tests verify complete user flows",
                file_path="(project-wide)",
                recommendation="Add Playwright or Cypress for critical user journeys",
            ))
