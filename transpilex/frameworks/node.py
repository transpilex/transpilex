import json
import re
import subprocess
import html
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString

from transpilex.config.base import NODE_DEPENDENCIES
from transpilex.config.project import ProjectConfig
from transpilex.utils.assets import replace_asset_paths, copy_assets, clean_relative_asset_paths
from transpilex.utils.file import copy_items, find_files_with_extension, copy_and_change_extension
from transpilex.utils.gulpfile import add_gulpfile
from transpilex.utils.logs import Log
from transpilex.utils.package_json import update_package_json
from transpilex.utils.replace_html_links import replace_html_links
from transpilex.utils.replace_variables import replace_variables
from transpilex.utils.template import replace_file_with_template


class BaseNodeConverter:
    def __init__(self, config: ProjectConfig):
        self.config = config

        self.project_views_path = Path(self.config.project_root_path / "views")
        self.project_routes_path = Path(self.config.project_root_path / "routes")

    def init_create_project(self):
        self.config.project_root_path.mkdir(parents=True, exist_ok=True)

        files = find_files_with_extension(self.config.pages_path)
        copy_and_change_extension(files, self.config.pages_path, self.project_views_path, self.config.file_extension)

        self._create_routes()

        self._convert()

        if self.config.partials_path:
            replace_variables(self.config.project_partials_path, self.config.variable_patterns,
                              self.config.variable_replacement, self.config.file_extension)

        replace_file_with_template(Path(__file__).parent.parent / "templates" / "node-app.js",
                                   self.config.project_root_path / "app.js")

        if self.config.asset_paths:
            copy_assets(self.config.asset_paths, self.config.project_assets_path)
            replace_asset_paths(self.config.project_assets_path, '')

        if self.config.frontend_pipeline == "gulp":
            add_gulpfile(self.config)
            scripts = {
                "gulp": "gulp",
                "build": "gulp build",
                "dev": "npm-run-all gulp preview",
                "preview": "nodemon app.js",
                "rtl": "gulp rtl",
                "rtl-build": "gulp rtlBuild"
            }
        else:
            scripts = {
                "vite": "vite",
                "build": "vite build",
                "dev": "npm-run-all vite preview",
                "preview": "nodemon app.js",
            }

        update_package_json(self.config,
                            deps=NODE_DEPENDENCIES,
                            overrides={"scripts": scripts})

        copy_items(Path(self.config.src_path / "package-lock.json"), self.config.project_root_path)

    def _convert(self):
        count = 0

        for file in self.project_views_path.rglob(f"*{self.config.file_extension}"):

            if not file.is_file():
                continue

            try:
                original_content = file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            soup = BeautifulSoup(original_content, "html.parser")

            out = str(soup)

            out = clean_relative_asset_paths(out)
            out = self._replace_all_includes(out).strip()
            out = replace_html_links(out, '')

            file.write_text(out.strip(), encoding="utf-8")

            # Log.converted(f"{file}")
            count += 1

        Log.info(f"{count} files converted in {self.project_views_path}")

    def _replace_all_includes(self, content: str):
        """
        Converts @@include(...) / {{> ...}} / {{&gt; ...}}
        into a unified: <%- include('partials/path') %>
        """

        fragments = []

        # Collect matches from all import patterns
        for label, pattern in self.config.import_patterns.items():
            alt_pattern = re.compile(
                pattern.pattern.replace(r">\s*", r"(?:>|&gt;)\s*")
            )
            for match in alt_pattern.finditer(content):
                fragments.append({
                    "full": match.group(0),
                    "path": match.group("path")
                })

        # Replace each fragment
        for frag in fragments:
            path = frag["path"]

            # Remove leading ./ ../
            clean_path = re.sub(r"^(\.\/|\.\.\/)+", "", path)
            clean_path = Path(clean_path).with_suffix("").as_posix()

            # Force into partials folder if not already
            if not clean_path.startswith("partials/"):
                clean_path = f"partials/{clean_path}"

            replacement = f"<%- include('{clean_path}') %>"

            content = content.replace(frag["full"], replacement)

        return content

    def _extract_meta(self, content: str):
        """
        Extract metadata from ANY include matched by config.import_patterns.
        - Extracts JSON {...} or key="value"
        - First occurrence wins (no duplicates)
        """
        meta = {}
        fragments = []

        # Use EXACT SAME pattern logic as your include converter
        for label, pattern in self.config.import_patterns.items():

            pattern_str = pattern.pattern
            pattern_str = pattern_str.replace(r"\>\s*", r"(?:>|&gt;)\s*")
            pattern_str = pattern_str.replace(r">\s*", r"(?:>|&gt;)\s*")

            alt_pattern = re.compile(pattern_str, re.DOTALL)

            for m in alt_pattern.finditer(content):
                fragments.append({
                    "full": m.group(0),
                    "path": m.group("path"),
                    "params": m.groupdict().get("params", "")
                })

        # Process collected include fragments
        for frag in fragments:
            params_raw = (frag["params"] or "").strip()

            # CASE 1 — JSON style { ... }
            if params_raw.startswith("{") and params_raw.endswith("}"):
                try:
                    cleaned = re.sub(r"([\{\s,])([A-Za-z_][\w-]*)\s*:",
                                     r'\1"\2":', params_raw)
                    cleaned = re.sub(r",\s*([\}\]])", r"\1", cleaned)

                    data = json.loads(cleaned)
                except Exception:
                    data = {}

                for k, v in data.items():
                    if k not in meta:
                        meta[k] = " ".join(v.split()) if isinstance(v, str) else v

            # CASE 2 — Handlebars style key="value"
            kv_pairs = re.findall(r"(\w+)=[\"']([^\"']+)[\"']", params_raw)
            for k, v in kv_pairs:
                if k not in meta:
                    meta[k] = v

        return meta

    def _generate_route_code(self, view_name: str, meta: dict):
        route_path = "/" if view_name == "index" else f"/{view_name}"

        meta_js = ""
        if meta:
            js_pairs = [f"{k}: {json.dumps(v)}" for k, v in meta.items()]
            meta_js = ", { " + ", ".join(js_pairs) + " }"

        return f"""route.get('{route_path}', (req, res) => {{
        res.render('{view_name}'{meta_js});
    }});"""

    def _create_routes(self):
        self.project_routes_path.mkdir(parents=True, exist_ok=True)
        route_file_path = self.project_routes_path / "index.js"
        ext = self.config.file_extension

        routes = [
            "const express = require('express');",
            "const route = express.Router();",
            ""
        ]

        for file in self.project_views_path.rglob(f"*{ext}"):

            if "partials" in file.parts:
                continue

            # Build folder-file route style
            relative = file.relative_to(self.project_views_path)
            folder = relative.parent.name if relative.parent != Path('.') else ""
            name = relative.stem

            if folder:
                route_name = f"{folder}-{name}"
            else:
                route_name = name

            if route_name == "index":
                route_path = "/"
            else:
                route_path = f"/{route_name}"

            # Read page content
            try:
                content = file.read_text(encoding="utf-8")
            except Exception:
                continue

            # Extract ALL meta fields
            meta = self._extract_meta(content)

            # Convert meta obj to JS
            if meta:
                js_pairs = [f"{k}: {json.dumps(v)}" for k, v in meta.items()]
                meta_js = "{ " + ", ".join(js_pairs) + " }"
            else:
                meta_js = "{}"

            # Add route
            routes.append(
                f"route.get('{route_path}', (req, res, next) => {{\n"
                f"    res.render('{route_name}', {meta_js});\n"
                f"}});\n"
            )

        routes.append("module.exports = route;")

        route_file_path.write_text("\n".join(routes), encoding="utf-8")
        Log.created(f"routes/index.js at {self.project_routes_path}")


class NodeGulpConverter(BaseNodeConverter):
    def __init__(self, config: ProjectConfig):
        super().__init__(config)

    def create_project(self):
        Log.project_start(self.config.project_name)

        self.init_create_project()

        Log.project_end(self.config.project_name, str(self.config.project_root_path))


class NodeConverter():
    def __init__(self, config: ProjectConfig):
        self.config = config

        if self.config.frontend_pipeline == "gulp":
            NodeGulpConverter(self.config).create_project()
