"""
Performance / Core Web Vitals Scanner for Lovable Projects
============================================================
Detecta problemas de rendimiento: imagenes sin optimizar, JS bloqueante,
falta de lazy loading, fonts, Suspense boundaries, etc.
"""

import os
import re
import json
from dataclasses import dataclass, field


@dataclass
class PerfFinding:
    severity: str
    category: str
    title: str
    description: str
    file_path: str
    line_number: int = 0
    code_snippet: str = ""
    recommendation: str = ""
    web_vital: str = ""  # LCP, FID, CLS, INP, TTFB


@dataclass
class PerfReport:
    findings: list = field(default_factory=list)
    files_scanned: int = 0
    metrics: dict = field(default_factory=dict)
    summary: dict = field(default_factory=dict)

    def add(self, finding: PerfFinding):
        self.findings.append(finding)

    def get_summary(self):
        counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        self.summary = counts
        return counts


class PerformanceScanner:
    """Escanea un proyecto Lovable en busca de problemas de rendimiento."""

    SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", "coverage"}
    SRC_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx"}

    def __init__(self, project_path: str):
        self.project_path = os.path.abspath(project_path)
        self.report = PerfReport()
        self._metrics = {
            "total_images": 0,
            "lazy_loaded_images": 0,
            "suspense_boundaries": 0,
            "lazy_components": 0,
            "memo_components": 0,
            "usememo_count": 0,
            "usecallback_count": 0,
            "large_assets": [],
            "has_web_vitals": False,
            "has_loading_states": 0,
        }

    def scan(self) -> PerfReport:
        print("  [Performance] Escaneando archivos...")
        self._scan_source_files()
        self._check_assets()
        self._check_html_perf()
        self._check_package_perf()
        self._check_build_config()
        self._generate_findings()

        self.report.metrics = self._metrics
        self.report.get_summary()
        return self.report

    def _scan_source_files(self):
        src_dir = os.path.join(self.project_path, "src")
        if not os.path.isdir(src_dir):
            return

        for root, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in self.SRC_EXTENSIONS:
                    continue

                fpath = os.path.join(root, fname)
                self.report.files_scanned += 1

                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        lines = content.split("\n")
                except Exception:
                    continue

                rel_path = os.path.relpath(fpath, self.project_path)

                # Count metrics
                self._metrics["suspense_boundaries"] += len(re.findall(r"<Suspense", content))
                self._metrics["lazy_components"] += len(re.findall(r"(?:React\.)?lazy\s*\(", content))
                self._metrics["memo_components"] += len(re.findall(r"(?:React\.)?memo\s*\(", content))
                self._metrics["usememo_count"] += len(re.findall(r"\buseMemo\b", content))
                self._metrics["usecallback_count"] += len(re.findall(r"\buseCallback\b", content))
                self._metrics["has_loading_states"] += len(re.findall(r"(?:isLoading|loading|skeleton|Skeleton|Spinner)", content))

                if "web-vitals" in content or "reportWebVitals" in content:
                    self._metrics["has_web_vitals"] = True

                # Image analysis
                img_tags = re.findall(r"<img\s+[^>]*>", content)
                self._metrics["total_images"] += len(img_tags)
                for img in img_tags:
                    if 'loading="lazy"' in img or "loading={'lazy'}" in img:
                        self._metrics["lazy_loaded_images"] += 1

                # Line-by-line checks
                for line_num, line in enumerate(lines, 1):
                    stripped = line.strip()
                    if stripped.startswith("//") or stripped.startswith("*"):
                        continue

                    # Large inline SVGs
                    if "<svg" in line and len(line) > 500:
                        self.report.add(PerfFinding(
                            severity="LOW", category="Performance/Assets",
                            title="Large inline SVG",
                            description="Large inline SVGs bloat component size",
                            file_path=rel_path, line_number=line_num,
                            recommendation="Extract SVG to a separate file and import it",
                            web_vital="LCP",
                        ))

                    # Synchronous heavy operations in render
                    if re.search(r"""JSON\.parse\s*\(\s*JSON\.stringify""", line):
                        self.report.add(PerfFinding(
                            severity="MEDIUM", category="Performance/Computation",
                            title="Deep clone via JSON.parse(JSON.stringify()) in render path",
                            description="Expensive operation that runs on every render",
                            file_path=rel_path, line_number=line_num,
                            recommendation="Use structuredClone() or wrap in useMemo",
                            web_vital="INP",
                        ))

                    # Heavy sync operations
                    if re.search(r"""\.sort\s*\(.*\)\.filter\s*\(.*\)\.map\s*\(""", line):
                        self.report.add(PerfFinding(
                            severity="MEDIUM", category="Performance/Computation",
                            title="Chained sort+filter+map in render",
                            description="Multiple array transformations on every render",
                            file_path=rel_path, line_number=line_num,
                            recommendation="Wrap in useMemo with proper dependencies",
                            web_vital="INP",
                        ))

                    # setTimeout/setInterval without cleanup
                    if re.search(r"""(?:setTimeout|setInterval)\s*\(""", line):
                        # Check if in useEffect with cleanup
                        context = "\n".join(lines[max(0, line_num-5):min(len(lines), line_num+10)])
                        if "useEffect" in context and "clearTimeout" not in context and "clearInterval" not in context:
                            self.report.add(PerfFinding(
                                severity="MEDIUM", category="Performance/Memory",
                                title="Timer without cleanup in useEffect",
                                description="Timers without cleanup cause memory leaks on unmount",
                                file_path=rel_path, line_number=line_num,
                                recommendation="Return a cleanup function: return () => clearTimeout/clearInterval(id)",
                            ))

                    # Event listeners without cleanup
                    if re.search(r"""addEventListener\s*\(""", line):
                        context = "\n".join(lines[max(0, line_num-3):min(len(lines), line_num+15)])
                        if "removeEventListener" not in context:
                            self.report.add(PerfFinding(
                                severity="MEDIUM", category="Performance/Memory",
                                title="addEventListener without removeEventListener",
                                description="Event listeners without cleanup cause memory leaks",
                                file_path=rel_path, line_number=line_num,
                                recommendation="Remove event listener in useEffect cleanup",
                            ))

                    # Window resize/scroll without throttle
                    if re.search(r"""(?:window|document)\.addEventListener\s*\(\s*['"](?:scroll|resize|mousemove)['"]""", line):
                        context = "\n".join(lines[max(0, line_num-5):min(len(lines), line_num+5)])
                        if not re.search(r"(?:throttle|debounce|requestAnimationFrame)", context):
                            self.report.add(PerfFinding(
                                severity="HIGH", category="Performance/Events",
                                title="High-frequency event listener without throttle",
                                description="scroll/resize/mousemove fire rapidly and can cause jank",
                                file_path=rel_path, line_number=line_num,
                                recommendation="Use requestAnimationFrame, throttle, or IntersectionObserver",
                                web_vital="INP",
                            ))

                    # Unoptimized images
                    if re.search(r"""src\s*=\s*['"].*\.(?:png|jpg|jpeg|gif)['"]""", line):
                        if 'loading="lazy"' not in line and "loading={'lazy'}" not in line:
                            self.report.add(PerfFinding(
                                severity="LOW", category="Performance/Images",
                                title="Image without lazy loading",
                                description="Non-lazy images block initial page render",
                                file_path=rel_path, line_number=line_num,
                                recommendation='Add loading="lazy" for below-the-fold images',
                                web_vital="LCP",
                            ))

    def _check_assets(self):
        """Verifica assets por tamano y formato."""
        public_dir = os.path.join(self.project_path, "public")
        src_dir = os.path.join(self.project_path, "src")
        assets_dir = os.path.join(src_dir, "assets") if os.path.isdir(src_dir) else None

        dirs_to_check = [d for d in [public_dir, assets_dir] if d and os.path.isdir(d)]

        for check_dir in dirs_to_check:
            for root, dirs, files in os.walk(check_dir):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    try:
                        size = os.path.getsize(fpath)
                    except Exception:
                        continue

                    rel = os.path.relpath(fpath, self.project_path)
                    ext = os.path.splitext(fname)[1].lower()

                    # Large images
                    if ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp"):
                        if size > 500_000:  # > 500KB
                            size_kb = size // 1024
                            self._metrics["large_assets"].append((rel, size_kb))
                            self.report.add(PerfFinding(
                                severity="HIGH" if size > 1_000_000 else "MEDIUM",
                                category="Performance/Images",
                                title=f"Large image: {fname} ({size_kb}KB)",
                                description="Large images are the #1 cause of slow LCP",
                                file_path=rel,
                                recommendation="Compress and convert to WebP/AVIF. Target <200KB for hero images.",
                                web_vital="LCP",
                            ))

                        if ext not in (".webp", ".avif", ".svg"):
                            self.report.add(PerfFinding(
                                severity="LOW", category="Performance/Images",
                                title=f"Non-optimized image format: {ext}",
                                description=f"{fname} uses {ext} - WebP/AVIF are 25-50% smaller",
                                file_path=rel,
                                recommendation="Convert to WebP format for better compression",
                                web_vital="LCP",
                            ))

                    # Large JS/CSS files
                    if ext in (".js", ".css") and size > 300_000:
                        size_kb = size // 1024
                        self.report.add(PerfFinding(
                            severity="MEDIUM", category="Performance/Bundle",
                            title=f"Large static file: {fname} ({size_kb}KB)",
                            description="Large JS/CSS files increase load time",
                            file_path=rel,
                            recommendation="Consider code splitting or loading asynchronously",
                            web_vital="TTFB",
                        ))

                    # Uncompressed fonts
                    if ext in (".ttf", ".otf") and size > 100_000:
                        size_kb = size // 1024
                        self.report.add(PerfFinding(
                            severity="MEDIUM", category="Performance/Fonts",
                            title=f"Unoptimized font: {fname} ({size_kb}KB)",
                            description="TTF/OTF fonts are larger than WOFF2",
                            file_path=rel,
                            recommendation="Convert to WOFF2 format (typically 30-50% smaller)",
                            web_vital="LCP",
                        ))

    def _check_html_perf(self):
        """Verifica index.html por problemas de rendimiento."""
        index_paths = [
            os.path.join(self.project_path, "index.html"),
            os.path.join(self.project_path, "public", "index.html"),
        ]

        for idx_path in index_paths:
            if not os.path.exists(idx_path):
                continue

            try:
                with open(idx_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    lines = content.split("\n")
            except Exception:
                continue

            rel = os.path.relpath(idx_path, self.project_path)

            for line_num, line in enumerate(lines, 1):
                # Render-blocking scripts in head
                if re.search(r"""<script\s+(?![^>]*(?:async|defer|type\s*=\s*['"]module))""", line):
                    if "<head>" in "\n".join(lines[:line_num]):
                        self.report.add(PerfFinding(
                            severity="HIGH", category="Performance/Loading",
                            title="Render-blocking script in <head>",
                            description="Scripts without async/defer block HTML parsing",
                            file_path=rel, line_number=line_num,
                            recommendation="Add 'defer' or 'async' attribute, or move to end of <body>",
                            web_vital="LCP",
                        ))

                # External fonts without preconnect
                if re.search(r"""href\s*=\s*['"]https://fonts\.googleapis""", line):
                    if "preconnect" not in content:
                        self.report.add(PerfFinding(
                            severity="MEDIUM", category="Performance/Fonts",
                            title="Google Fonts without preconnect",
                            description="Missing preconnect hint delays font loading",
                            file_path=rel, line_number=line_num,
                            recommendation="Add <link rel='preconnect' href='https://fonts.googleapis.com'>",
                            web_vital="LCP",
                        ))

                # Render-blocking CSS
                if re.search(r"""<link[^>]*rel\s*=\s*['"]stylesheet['"][^>]*href\s*=\s*['"]https?://""", line):
                    self.report.add(PerfFinding(
                        severity="MEDIUM", category="Performance/Loading",
                        title="External stylesheet may be render-blocking",
                        description="External CSS blocks rendering until downloaded",
                        file_path=rel, line_number=line_num,
                        recommendation="Consider inlining critical CSS or using media attribute",
                        web_vital="LCP",
                    ))

    def _check_package_perf(self):
        """Verifica dependencias relacionadas con rendimiento."""
        pkg_path = os.path.join(self.project_path, "package.json")
        if not os.path.exists(pkg_path):
            return

        try:
            with open(pkg_path, "r") as f:
                pkg = json.load(f)

            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

            # Check for performance tools
            if "web-vitals" not in deps:
                self.report.add(PerfFinding(
                    severity="LOW", category="Performance/Monitoring",
                    title="web-vitals library not installed",
                    description="Can't measure Core Web Vitals without this library",
                    file_path="package.json",
                    recommendation="Install 'web-vitals' to measure LCP, FID, CLS in production",
                ))

            # Check for image optimization
            has_image_opt = any(d in deps for d in ["sharp", "next/image", "@next/image", "vite-plugin-image-optimizer"])
            if not has_image_opt and self._metrics["total_images"] > 5:
                self.report.add(PerfFinding(
                    severity="MEDIUM", category="Performance/Images",
                    title="No image optimization library installed",
                    description=f"{self._metrics['total_images']} images found without optimization pipeline",
                    file_path="package.json",
                    recommendation="Use vite-plugin-image-optimizer or optimize images at build time",
                    web_vital="LCP",
                ))

            # Bundle analyzer
            has_analyzer = any(d in deps for d in ["rollup-plugin-visualizer", "webpack-bundle-analyzer", "source-map-explorer"])
            if not has_analyzer:
                self.report.add(PerfFinding(
                    severity="INFO", category="Performance/Bundle",
                    title="No bundle analyzer configured",
                    description="Bundle analyzer helps identify large dependencies",
                    file_path="package.json",
                    recommendation="Install 'rollup-plugin-visualizer' for Vite projects",
                ))

        except Exception:
            pass

    def _check_build_config(self):
        """Verifica configuracion de build para optimizaciones."""
        vite_configs = ["vite.config.ts", "vite.config.js"]
        for cfg_name in vite_configs:
            cfg_path = os.path.join(self.project_path, cfg_name)
            if os.path.exists(cfg_path):
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    if "manualChunks" not in content and "splitVendorChunk" not in content:
                        self.report.add(PerfFinding(
                            severity="LOW", category="Performance/Bundle",
                            title="No manual chunk splitting configured",
                            description="Vendor code split improves caching",
                            file_path=cfg_name,
                            recommendation="Configure build.rollupOptions.output.manualChunks for vendor splitting",
                            web_vital="TTFB",
                        ))

                    if "compression" not in content and "viteCompression" not in content:
                        self.report.add(PerfFinding(
                            severity="LOW", category="Performance/Bundle",
                            title="No compression plugin configured",
                            description="gzip/brotli compression reduces transfer size",
                            file_path=cfg_name,
                            recommendation="Install vite-plugin-compression for gzip/brotli output",
                            web_vital="TTFB",
                        ))
                except Exception:
                    pass
                break

    def _generate_findings(self):
        """Genera hallazgos basados en metricas globales."""
        if self._metrics["lazy_components"] == 0 and self.report.files_scanned > 20:
            self.report.add(PerfFinding(
                severity="MEDIUM", category="Performance/Code Splitting",
                title="No React.lazy() code splitting detected",
                description="Without lazy loading, the entire app is loaded upfront",
                file_path="(project-wide)",
                recommendation="Use React.lazy() and Suspense for route-based code splitting",
                web_vital="TTFB",
            ))

        if self._metrics["suspense_boundaries"] == 0 and self.report.files_scanned > 10:
            self.report.add(PerfFinding(
                severity="MEDIUM", category="Performance/UX",
                title="No Suspense boundaries detected",
                description="Without Suspense, async content shows nothing while loading",
                file_path="(project-wide)",
                recommendation="Wrap lazy components and data fetching in <Suspense fallback={...}>",
                web_vital="LCP",
            ))

        if self._metrics["has_loading_states"] == 0 and self.report.files_scanned > 10:
            self.report.add(PerfFinding(
                severity="MEDIUM", category="Performance/UX",
                title="No loading states detected",
                description="Without loading indicators, users see blank content during data fetch",
                file_path="(project-wide)",
                recommendation="Add loading skeletons or spinners while data loads",
                web_vital="CLS",
            ))
