"""
Security Scanner for Lovable Projects
======================================
Analiza proyectos Lovable (React + Supabase/TypeScript) en busca de
vulnerabilidades de seguridad comunes.
"""

import os
import re
from dataclasses import dataclass, field


@dataclass
class SecurityFinding:
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW, INFO
    category: str
    title: str
    description: str
    file_path: str
    line_number: int = 0
    code_snippet: str = ""
    recommendation: str = ""


@dataclass
class SecurityReport:
    findings: list = field(default_factory=list)
    files_scanned: int = 0
    summary: dict = field(default_factory=dict)

    def add(self, finding: SecurityFinding):
        self.findings.append(finding)

    def get_summary(self):
        counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        self.summary = counts
        return counts


# ─────────────────────────────────────────────
# Patrones de deteccion
# ─────────────────────────────────────────────

HARDCODED_SECRETS_PATTERNS = [
    (r"""(?:api[_-]?key|apikey|secret|password|token|auth)\s*[:=]\s*['"][A-Za-z0-9_\-]{16,}['"]""",
     "Possible hardcoded secret/API key"),
    (r"""(?:supabase_?(?:anon_?key|service_?role_?key|url))\s*[:=]\s*['"][^'"]+['"]""",
     "Hardcoded Supabase credential"),
    (r"""(?:NEXT_PUBLIC_|VITE_|REACT_APP_).*(?:SECRET|PRIVATE|SERVICE_ROLE)""",
     "Secret exposed via public env variable"),
    (r"""eyJhbGciOi[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+""",
     "Hardcoded JWT token found"),
    (r"""(?:sk_live|sk_test|pk_live|pk_test)_[A-Za-z0-9]{20,}""",
     "Stripe API key found"),
    (r"""ghp_[A-Za-z0-9]{36}""",
     "GitHub personal access token found"),
]

XSS_PATTERNS = [
    (r"""dangerouslySetInnerHTML\s*=\s*\{""",
     "dangerouslySetInnerHTML usage - potential XSS"),
    (r"""innerHTML\s*=""",
     "Direct innerHTML assignment - potential XSS"),
    (r"""document\.write\s*\(""",
     "document.write usage - potential XSS"),
    (r"""eval\s*\(""",
     "eval() usage - code injection risk"),
    (r"""new\s+Function\s*\(""",
     "new Function() - dynamic code execution"),
]

AUTH_PATTERNS = [
    (r"""(?:supabase|client)\s*\.\s*from\s*\(.*\)\s*\.\s*(?:select|insert|update|delete)""",
     "Direct Supabase query - verify RLS policies are enabled"),
    (r"""\.rpc\s*\(""",
     "Supabase RPC call - verify function security"),
    (r"""service_?role""",
     "Service role key reference - should only be server-side"),
    (r"""(?:anon|public)\s*[_-]?\s*key.*(?:insert|update|delete)""",
     "Potential write operation with anon key"),
]

INJECTION_PATTERNS = [
    (r"""(?:textSearchQuery|or|and|filter)\s*\(.*\$\{""",
     "Template literal in Supabase query - potential SQL injection"),
    (r"""\.sql\s*\(\s*`[^`]*\$\{""",
     "Template literal in raw SQL - SQL injection risk"),
    (r"""(?:exec|execSync|spawn|spawnSync)\s*\(.*\$\{""",
     "Template literal in shell command - command injection"),
    (r"""new\s+RegExp\s*\(.*(?:req\.|params\.|query\.|body\.)""",
     "User input in RegExp - ReDoS risk"),
]

CORS_PATTERNS = [
    (r"""(?:Access-Control-Allow-Origin|cors).*['"]\*['"]""",
     "Wildcard CORS origin - overly permissive"),
    (r"""credentials\s*:\s*['"]include['"]""",
     "Credentials included in requests - verify CORS is properly restricted"),
]

STORAGE_PATTERNS = [
    (r"""localStorage\.setItem\s*\(\s*['"](?:token|jwt|auth|session|secret|password|key)""",
     "Sensitive data stored in localStorage (accessible via XSS)"),
    (r"""sessionStorage\.setItem\s*\(\s*['"](?:token|jwt|auth|secret|password|key)""",
     "Sensitive data in sessionStorage"),
    (r"""document\.cookie\s*=(?!.*(?:httponly|HttpOnly|httpOnly))""",
     "Cookie set without HttpOnly flag"),
]

DEPENDENCY_VULNERABILITIES = [
    "react-scripts@<5.0.0",
    "axios@<1.6.0",
    "jsonwebtoken@<9.0.0",
    "lodash@<4.17.21",
    "express@<4.19.0",
    "node-fetch@<2.6.7",
]


# ─────────────────────────────────────────────
# Scanner
# ─────────────────────────────────────────────

class SecurityScanner:
    """Escanea un proyecto Lovable en busca de vulnerabilidades."""

    SCAN_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json", ".env", ".html", ".sql"}
    SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", "coverage", "__pycache__"}

    def __init__(self, project_path: str):
        self.project_path = os.path.abspath(project_path)
        self.report = SecurityReport()

    def scan(self) -> SecurityReport:
        """Ejecuta todos los escaneos de seguridad."""
        print("  [Security] Escaneando archivos...")
        files = self._collect_files()
        self.report.files_scanned = len(files)

        for file_path in files:
            self._scan_file(file_path)

        self._check_config_files()
        self._check_env_files()
        self._check_package_json()
        self._check_supabase_config()

        self.report.get_summary()
        return self.report

    def _collect_files(self):
        files = []
        for root, dirs, filenames in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext in self.SCAN_EXTENSIONS or fname.startswith(".env"):
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

        # Skip .env scanning for pattern checks (handled separately)
        if os.path.basename(file_path).startswith(".env"):
            return

        all_patterns = [
            (HARDCODED_SECRETS_PATTERNS, "Secrets/Credentials", "CRITICAL"),
            (XSS_PATTERNS, "XSS", "HIGH"),
            (AUTH_PATTERNS, "Authentication/Authorization", "MEDIUM"),
            (INJECTION_PATTERNS, "Injection", "HIGH"),
            (CORS_PATTERNS, "CORS", "MEDIUM"),
            (STORAGE_PATTERNS, "Insecure Storage", "MEDIUM"),
        ]

        for patterns, category, default_severity in all_patterns:
            for pattern, description in patterns:
                for line_num, line in enumerate(lines, 1):
                    if re.search(pattern, line, re.IGNORECASE):
                        # Skip comments
                        stripped = line.strip()
                        if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*"):
                            continue

                        self.report.add(SecurityFinding(
                            severity=default_severity,
                            category=category,
                            title=description,
                            description=f"Pattern detected: {description}",
                            file_path=rel_path,
                            line_number=line_num,
                            code_snippet=line.strip()[:200],
                        ))

    def _check_env_files(self):
        """Verifica archivos .env por secretos expuestos."""
        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            for fname in files:
                if fname.startswith(".env"):
                    fpath = os.path.join(root, fname)
                    rel_path = os.path.relpath(fpath, self.project_path)

                    # .env files should not be committed
                    if fname == ".env" or fname == ".env.local":
                        self.report.add(SecurityFinding(
                            severity="HIGH",
                            category="Secrets/Credentials",
                            title=f"Environment file found: {fname}",
                            description="This file may contain secrets and should be in .gitignore",
                            file_path=rel_path,
                            recommendation="Ensure this file is in .gitignore and secrets are not committed",
                        ))

                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            for line_num, line in enumerate(f, 1):
                                if re.search(r"(?:SECRET|PRIVATE|SERVICE_ROLE|PASSWORD)", line, re.IGNORECASE):
                                    if not line.strip().startswith("#"):
                                        self.report.add(SecurityFinding(
                                            severity="CRITICAL",
                                            category="Secrets/Credentials",
                                            title="Secret in environment file",
                                            description=f"Potential secret found in {fname}",
                                            file_path=rel_path,
                                            line_number=line_num,
                                            code_snippet=line.split("=")[0].strip(),
                                            recommendation="Use a secret manager or ensure this file is never committed",
                                        ))
                    except Exception:
                        pass

    def _check_config_files(self):
        """Verifica configuraciones de seguridad."""
        # Check for missing security headers (vite.config, next.config, etc.)
        config_files = [
            "vite.config.ts", "vite.config.js",
            "next.config.js", "next.config.mjs",
        ]
        for cfg in config_files:
            cfg_path = os.path.join(self.project_path, cfg)
            if os.path.exists(cfg_path):
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    if "proxy" in content and "changeOrigin" in content:
                        self.report.add(SecurityFinding(
                            severity="INFO",
                            category="Configuration",
                            title="Proxy configuration detected",
                            description="Verify proxy targets are trusted and correctly configured",
                            file_path=cfg,
                        ))
                except Exception:
                    pass

        # Check .gitignore
        gitignore_path = os.path.join(self.project_path, ".gitignore")
        if os.path.exists(gitignore_path):
            try:
                with open(gitignore_path, "r") as f:
                    gitignore = f.read()
                required_entries = [".env", "credentials", "*.pem", "*.key"]
                for entry in required_entries:
                    if entry not in gitignore:
                        self.report.add(SecurityFinding(
                            severity="MEDIUM",
                            category="Configuration",
                            title=f"Missing .gitignore entry: {entry}",
                            description=f"Pattern '{entry}' not found in .gitignore",
                            file_path=".gitignore",
                            recommendation=f"Add '{entry}' to .gitignore to prevent accidental commits",
                        ))
            except Exception:
                pass
        else:
            self.report.add(SecurityFinding(
                severity="HIGH",
                category="Configuration",
                title="No .gitignore file found",
                description="Missing .gitignore increases risk of committing secrets",
                file_path="(root)",
                recommendation="Create a .gitignore with entries for .env, node_modules, credentials",
            ))

    def _check_package_json(self):
        """Verifica dependencias vulnerables conocidas."""
        pkg_path = os.path.join(self.project_path, "package.json")
        if not os.path.exists(pkg_path):
            return

        try:
            import json
            with open(pkg_path, "r") as f:
                pkg = json.load(f)

            all_deps = {}
            all_deps.update(pkg.get("dependencies", {}))
            all_deps.update(pkg.get("devDependencies", {}))

            # Check for known vulnerable version patterns
            for vuln in DEPENDENCY_VULNERABILITIES:
                pkg_name, version_constraint = vuln.rsplit("@", 1)
                if pkg_name in all_deps:
                    self.report.add(SecurityFinding(
                        severity="MEDIUM",
                        category="Dependencies",
                        title=f"Potentially vulnerable: {pkg_name}",
                        description=f"Version {all_deps[pkg_name]} installed. Known vulnerabilities in {version_constraint}",
                        file_path="package.json",
                        recommendation=f"Run 'npm audit' and update {pkg_name} to the latest version",
                    ))

            # Check if npm audit script exists
            scripts = pkg.get("scripts", {})
            if "audit" not in str(scripts):
                self.report.add(SecurityFinding(
                    severity="LOW",
                    category="Dependencies",
                    title="No audit script configured",
                    description="Consider adding a security audit step",
                    file_path="package.json",
                    recommendation="Add 'audit': 'npm audit' to scripts",
                ))

        except Exception:
            pass

    def _check_supabase_config(self):
        """Verifica configuracion de Supabase."""
        supabase_dirs = [
            os.path.join(self.project_path, "supabase"),
            os.path.join(self.project_path, "src", "integrations", "supabase"),
            os.path.join(self.project_path, "src", "lib"),
        ]

        found_supabase = False
        for sdir in supabase_dirs:
            if os.path.isdir(sdir):
                found_supabase = True
                for fname in os.listdir(sdir):
                    fpath = os.path.join(sdir, fname)
                    if not os.path.isfile(fpath):
                        continue
                    rel = os.path.relpath(fpath, self.project_path)
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()

                        if "service_role" in content.lower():
                            self.report.add(SecurityFinding(
                                severity="CRITICAL",
                                category="Supabase",
                                title="Service role key in client code",
                                description="Service role key bypasses RLS and should NEVER be in frontend code",
                                file_path=rel,
                                recommendation="Use only the anon key in frontend. Service role belongs server-side only",
                            ))

                        if "createClient" in content and "anon" not in content.lower():
                            self.report.add(SecurityFinding(
                                severity="INFO",
                                category="Supabase",
                                title="Supabase client creation - verify key type",
                                description="Ensure only the anon key is used in client-side code",
                                file_path=rel,
                            ))
                    except Exception:
                        pass

        # Check for RLS in migrations
        migrations_dir = os.path.join(self.project_path, "supabase", "migrations")
        if os.path.isdir(migrations_dir):
            has_rls = False
            for fname in os.listdir(migrations_dir):
                if fname.endswith(".sql"):
                    fpath = os.path.join(migrations_dir, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            content = f.read()
                        if "enable row level security" in content.lower() or "alter table" in content.lower() and "rls" in content.lower():
                            has_rls = True
                        if "create table" in content.lower() and "enable row level security" not in content.lower():
                            rel = os.path.relpath(fpath, self.project_path)
                            self.report.add(SecurityFinding(
                                severity="HIGH",
                                category="Supabase",
                                title="Table created without RLS",
                                description="Tables should have Row Level Security enabled",
                                file_path=rel,
                                recommendation="Add 'ALTER TABLE table_name ENABLE ROW LEVEL SECURITY;' after CREATE TABLE",
                            ))
                    except Exception:
                        pass

            if not has_rls and found_supabase:
                self.report.add(SecurityFinding(
                    severity="HIGH",
                    category="Supabase",
                    title="No RLS policies detected",
                    description="No Row Level Security policies found in migrations",
                    file_path="supabase/migrations/",
                    recommendation="Enable RLS on all tables and create appropriate policies",
                ))
