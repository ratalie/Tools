"""
SEO Scanner for Lovable Projects
==================================
Analiza proyectos Lovable en busca de problemas de SEO y meta tags.
"""

import os
import re
import json
from dataclasses import dataclass, field


@dataclass
class SEOFinding:
    severity: str
    category: str
    title: str
    description: str
    file_path: str
    line_number: int = 0
    code_snippet: str = ""
    recommendation: str = ""


@dataclass
class SEOReport:
    findings: list = field(default_factory=list)
    files_scanned: int = 0
    summary: dict = field(default_factory=dict)

    def add(self, finding: SEOFinding):
        self.findings.append(finding)

    def get_summary(self):
        counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        self.summary = counts
        return counts


class SEOScanner:
    """Escanea un proyecto Lovable en busca de problemas de SEO."""

    SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", "coverage"}

    def __init__(self, project_path: str):
        self.project_path = os.path.abspath(project_path)
        self.report = SEOReport()

    def scan(self) -> SEOReport:
        print("  [SEO] Escaneando archivos...")
        self._check_index_html()
        self._check_meta_tags_in_components()
        self._check_robots_sitemap()
        self._check_semantic_html()
        self._check_routing()
        self._check_images_seo()
        self._check_package_json()
        self.report.get_summary()
        return self.report

    def _check_index_html(self):
        """Verifica index.html por meta tags basicos."""
        index_paths = [
            os.path.join(self.project_path, "index.html"),
            os.path.join(self.project_path, "public", "index.html"),
        ]

        found = False
        for idx_path in index_paths:
            if os.path.exists(idx_path):
                found = True
                rel = os.path.relpath(idx_path, self.project_path)
                self.report.files_scanned += 1
                try:
                    with open(idx_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    # Title tag
                    if not re.search(r"<title[^>]*>[^<]+</title>", content):
                        self.report.add(SEOFinding(
                            severity="HIGH", category="SEO/Meta",
                            title="Missing or empty <title> tag",
                            description="Title is the most important on-page SEO factor",
                            file_path=rel,
                            recommendation="Add a descriptive <title> unique to each page",
                        ))
                    elif re.search(r"<title>(?:Vite \+ React|React App|Vite App)</title>", content):
                        self.report.add(SEOFinding(
                            severity="HIGH", category="SEO/Meta",
                            title="Default/generic page title",
                            description="Page title is still the default Vite/React template",
                            file_path=rel,
                            recommendation="Replace with a descriptive title for your app",
                        ))

                    # Meta description
                    if not re.search(r"""<meta\s+[^>]*name\s*=\s*['"]description['"][^>]*>""", content):
                        self.report.add(SEOFinding(
                            severity="HIGH", category="SEO/Meta",
                            title="Missing meta description",
                            description="Search engines use this for snippets in results",
                            file_path=rel,
                            recommendation="Add <meta name='description' content='...'>",
                        ))

                    # Viewport
                    if not re.search(r"""<meta\s+[^>]*name\s*=\s*['"]viewport['"]""", content):
                        self.report.add(SEOFinding(
                            severity="HIGH", category="SEO/Meta",
                            title="Missing viewport meta tag",
                            description="Required for mobile-friendly rendering (Google ranking factor)",
                            file_path=rel,
                            recommendation="Add <meta name='viewport' content='width=device-width, initial-scale=1'>",
                        ))

                    # Open Graph
                    og_tags = ["og:title", "og:description", "og:image", "og:url"]
                    missing_og = [t for t in og_tags if t not in content]
                    if missing_og:
                        self.report.add(SEOFinding(
                            severity="MEDIUM", category="SEO/Social",
                            title=f"Missing Open Graph tags: {', '.join(missing_og)}",
                            description="OG tags control how links appear when shared on social media",
                            file_path=rel,
                            recommendation="Add og:title, og:description, og:image, og:url meta tags",
                        ))

                    # Twitter Card
                    if "twitter:card" not in content:
                        self.report.add(SEOFinding(
                            severity="LOW", category="SEO/Social",
                            title="Missing Twitter Card meta tags",
                            description="Controls appearance when shared on Twitter/X",
                            file_path=rel,
                            recommendation="Add <meta name='twitter:card' content='summary_large_image'>",
                        ))

                    # Canonical
                    if "canonical" not in content:
                        self.report.add(SEOFinding(
                            severity="MEDIUM", category="SEO/Meta",
                            title="Missing canonical URL",
                            description="Prevents duplicate content issues",
                            file_path=rel,
                            recommendation="Add <link rel='canonical' href='...'>",
                        ))

                    # Favicon
                    if not re.search(r"""<link\s+[^>]*rel\s*=\s*['"](?:icon|shortcut icon)['"]""", content):
                        self.report.add(SEOFinding(
                            severity="LOW", category="SEO/Meta",
                            title="Missing favicon",
                            description="Favicons help with branding in browser tabs and bookmarks",
                            file_path=rel,
                            recommendation="Add <link rel='icon' href='/favicon.ico'>",
                        ))

                    # Language
                    if not re.search(r"""<html[^>]*\slang\s*=""", content):
                        self.report.add(SEOFinding(
                            severity="MEDIUM", category="SEO/Meta",
                            title="Missing lang attribute on <html>",
                            description="Helps search engines understand content language",
                            file_path=rel,
                            recommendation="Add lang='en' or lang='es' to <html> tag",
                        ))

                    # Charset
                    if not re.search(r"""<meta\s+charset""", content, re.IGNORECASE):
                        self.report.add(SEOFinding(
                            severity="MEDIUM", category="SEO/Meta",
                            title="Missing charset declaration",
                            description="Prevents encoding issues",
                            file_path=rel,
                            recommendation="Add <meta charset='UTF-8'> as first child of <head>",
                        ))

                except Exception:
                    pass

        if not found:
            self.report.add(SEOFinding(
                severity="HIGH", category="SEO/Meta",
                title="No index.html found",
                description="Cannot verify meta tags without index.html",
                file_path="(root)",
            ))

    def _check_meta_tags_in_components(self):
        """Busca uso de react-helmet o similar para meta tags dinamicos."""
        src_dir = os.path.join(self.project_path, "src")
        if not os.path.isdir(src_dir):
            return

        has_helmet = False
        for root, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            for fname in files:
                if fname.endswith((".tsx", ".jsx", ".ts", ".js")):
                    self.report.files_scanned += 1
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                        if re.search(r"(?:react-helmet|@tanstack.*head|next/head|Helmet)", content):
                            has_helmet = True
                    except Exception:
                        pass

        if not has_helmet:
            self.report.add(SEOFinding(
                severity="MEDIUM", category="SEO/Meta",
                title="No dynamic meta tag management detected",
                description="SPAs need react-helmet or similar for per-page meta tags",
                file_path="(project-wide)",
                recommendation="Install react-helmet-async for dynamic title/description per route",
            ))

    def _check_robots_sitemap(self):
        """Verifica presencia de robots.txt y sitemap."""
        public_dir = os.path.join(self.project_path, "public")
        root_dir = self.project_path

        # robots.txt
        robots_found = False
        for base in [public_dir, root_dir]:
            if os.path.exists(os.path.join(base, "robots.txt")):
                robots_found = True
                break
        if not robots_found:
            self.report.add(SEOFinding(
                severity="MEDIUM", category="SEO/Crawling",
                title="Missing robots.txt",
                description="robots.txt guides search engine crawlers",
                file_path="public/",
                recommendation="Create public/robots.txt with at least 'User-agent: *\nAllow: /'",
            ))

        # sitemap.xml
        sitemap_found = False
        for base in [public_dir, root_dir]:
            if os.path.exists(os.path.join(base, "sitemap.xml")):
                sitemap_found = True
                break
        if not sitemap_found:
            self.report.add(SEOFinding(
                severity="LOW", category="SEO/Crawling",
                title="Missing sitemap.xml",
                description="Sitemaps help search engines discover all pages",
                file_path="public/",
                recommendation="Generate a sitemap.xml listing all public routes",
            ))

    def _check_semantic_html(self):
        """Verifica uso de HTML semantico en componentes."""
        src_dir = os.path.join(self.project_path, "src")
        if not os.path.isdir(src_dir):
            return

        total_divs = 0
        total_semantic = 0
        semantic_tags = ["<header", "<footer", "<nav", "<main", "<article", "<section", "<aside"]

        for root, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            for fname in files:
                if fname.endswith((".tsx", ".jsx")):
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                        total_divs += len(re.findall(r"<div[\s>]", content))
                        for tag in semantic_tags:
                            total_semantic += len(re.findall(rf"{tag}[\s>]", content))
                    except Exception:
                        pass

        if total_divs > 0:
            ratio = total_semantic / (total_divs + total_semantic) if (total_divs + total_semantic) > 0 else 0
            if ratio < 0.05 and total_divs > 20:
                self.report.add(SEOFinding(
                    severity="MEDIUM", category="SEO/Semantic",
                    title=f"Low semantic HTML usage ({ratio:.0%} semantic vs {total_divs} divs)",
                    description="Semantic HTML helps SEO and accessibility",
                    file_path="src/",
                    recommendation="Replace wrapper divs with <section>, <article>, <nav>, <header>, <footer>",
                ))

    def _check_routing(self):
        """Verifica configuracion de routing para SEO."""
        src_dir = os.path.join(self.project_path, "src")
        if not os.path.isdir(src_dir):
            return

        has_404 = False
        uses_hash_router = False

        for root, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            for fname in files:
                if fname.endswith((".tsx", ".jsx", ".ts", ".js")):
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()

                        if re.search(r"""(?:path\s*[:=]\s*['"]?\*|NotFound|404|path="\*")""", content):
                            has_404 = True

                        if "HashRouter" in content or "createHashRouter" in content:
                            uses_hash_router = True
                            rel = os.path.relpath(fpath, self.project_path)
                            self.report.add(SEOFinding(
                                severity="HIGH", category="SEO/Routing",
                                title="HashRouter detected - bad for SEO",
                                description="Hash-based URLs (#/path) are not indexed by search engines",
                                file_path=rel,
                                recommendation="Switch to BrowserRouter for clean URLs that search engines can index",
                            ))
                    except Exception:
                        pass

        if not has_404:
            self.report.add(SEOFinding(
                severity="LOW", category="SEO/Routing",
                title="No 404 page detected",
                description="A custom 404 helps users and search engines handle broken links",
                file_path="(project-wide)",
                recommendation="Add a catch-all route with a helpful 404 page",
            ))

    def _check_images_seo(self):
        """Verifica optimizacion de imagenes para SEO."""
        src_dir = os.path.join(self.project_path, "src")
        if not os.path.isdir(src_dir):
            return

        for root, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            for fname in files:
                if fname.endswith((".tsx", ".jsx")):
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            lines = f.readlines()

                        rel = os.path.relpath(fpath, self.project_path)
                        for line_num, line in enumerate(lines, 1):
                            # Images without width/height (CLS)
                            if re.search(r"<img\s+", line) and not re.search(r"(?:width|height|fill|className.*(?:w-|h-))", line):
                                self.report.add(SEOFinding(
                                    severity="MEDIUM", category="SEO/Performance",
                                    title="Image without explicit dimensions",
                                    description="Missing width/height causes Cumulative Layout Shift (CLS) - a Core Web Vital",
                                    file_path=rel,
                                    line_number=line_num,
                                    recommendation="Add width and height attributes or use CSS aspect-ratio",
                                ))
                    except Exception:
                        pass

    def _check_package_json(self):
        """Verifica dependencias SEO-related."""
        pkg_path = os.path.join(self.project_path, "package.json")
        if not os.path.exists(pkg_path):
            return

        try:
            with open(pkg_path, "r") as f:
                pkg = json.load(f)

            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

            # Check for SSR/SSG
            has_ssr = any(d in deps for d in ["next", "remix", "astro", "gatsby", "@analogjs/platform"])
            if not has_ssr:
                self.report.add(SEOFinding(
                    severity="INFO", category="SEO/Architecture",
                    title="Client-side rendered SPA (no SSR/SSG)",
                    description="Pure CSR apps have limited SEO since crawlers may not execute JavaScript",
                    file_path="package.json",
                    recommendation="For content-heavy sites, consider Next.js/Remix for SSR or pre-rendering",
                ))

            # Check for structured data
            has_schema = any(d in deps for d in ["schema-dts", "next-seo", "react-schemaorg"])
            if not has_schema:
                self.report.add(SEOFinding(
                    severity="LOW", category="SEO/Rich Results",
                    title="No structured data (JSON-LD) library detected",
                    description="Structured data enables rich results in Google",
                    file_path="package.json",
                    recommendation="Add JSON-LD structured data for key pages (Organization, Product, FAQ, etc.)",
                ))

        except Exception:
            pass
