import re
import json
import html
import subprocess
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString

from transpilex.config.base import LARAVEL_PROJECT_WITH_AUTH_CREATION_COMMAND, \
    LARAVEL_PROJECT_CREATION_COMMAND, LARAVEL_RESOURCES_PRESERVE
from transpilex.config.project import ProjectConfig
from transpilex.utils.assets import copy_assets, copy_public_only_assets
from transpilex.utils.file import move_files, copy_items
from transpilex.utils.git import remove_git_folders
from transpilex.utils.logs import Log
from transpilex.utils.package_json import update_package_json
from transpilex.utils.replace_variables import replace_variables
from transpilex.utils.restructure import restructure_and_copy_files


class LaravelConverter:
    def __init__(self, config: ProjectConfig):

        self.config = config

        self.project_views_path = Path(self.config.project_root_path / "resources" / "views")
        self.project_shared_path = Path(self.config.project_root_path / "resources" / "views" / "shared")
        self.project_public_path = Path(self.config.project_root_path / "public")
        self.project_vite_path = Path(self.config.project_root_path / "vite.config.js")
        self.vite_inputs = set()
        self.route_map = None

        self.create_project()

    def create_project(self):
        Log.project_start(self.config.project_name)

        try:
            self.config.project_root_path.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                LARAVEL_PROJECT_WITH_AUTH_CREATION_COMMAND if self.config.use_auth else LARAVEL_PROJECT_CREATION_COMMAND,
                cwd=self.config.project_root_path,
                check=True,
                capture_output=True, text=True)

            Log.success("Laravel project created successfully")

            remove_git_folders(self.config.project_root_path)

        except subprocess.CalledProcessError:
            Log.error("Laravel project creation failed")
            return

        self.route_map = restructure_and_copy_files(
            self.config,
            self.project_views_path,
            self.config.file_extension
        )

        self._convert(self.project_views_path)

        if self.config.partials_path:
            move_files(self.project_views_path / "partials", self.project_shared_path / "partials")
            replace_variables(self.project_shared_path, self.config.variable_patterns,
                              self.config.variable_replacement, self.config.file_extension)

        if self.config.asset_paths:
            copy_items(Path(self.config.src_path / "public"), self.config.project_root_path)
            public_only = copy_public_only_assets(self.config.asset_paths, self.project_public_path)
            copy_assets(self.config.asset_paths, self.config.project_assets_path, exclude=public_only,
                        preserve=LARAVEL_RESOURCES_PRESERVE)

        update_package_json(self.config, ignore=["scripts", "type", "devDependencies"])

        self._update_vite_config()

        self._generate_routes(self.project_views_path, self.config.project_root_path / "routes" / "web.php")

        Log.project_end(self.config.project_name, str(self.config.project_root_path))

    def _convert(self, folder_path: Path):
        """Convert files inside Laravel views directory."""
        count = 0

        for file in folder_path.rglob(f"*{self.config.file_extension}"):
            if not file.is_file():
                continue

            try:
                original_content = file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            layout_title = ""
            # normalize &gt; back to >
            title_scan_source = original_content.replace("&gt;", ">")

            for label, pattern in self.config.import_patterns.items():
                # allow both {{> ...}} and {{&gt; ...}}
                alt_pattern = re.compile(pattern.pattern.replace(r"\>\s*", r"(?:>|&gt;)\s*"))
                for m in alt_pattern.finditer(title_scan_source):
                    # "title-meta", "title-meta.html", "app-meta-title", etc.
                    inc_name = Path(m.group("path")).stem.lower()

                    if "title-meta" in inc_name or "app-meta-title" in inc_name:
                        meta = self._parse_include_params(m.groupdict().get("params", "") or "")
                        layout_title = meta.get("title") or meta.get("pageTitle") or ""
                        break
                if layout_title:
                    break

            escaped_title = layout_title.replace("'", "\\'")

            placeholder_map = {}

            def _protect_handlebars(mm):
                key = f"__HB_{len(placeholder_map)}__"
                placeholder_map[key] = mm.group(0)
                return key

            protected_content = re.sub(r"\{\{[^{]+\}\}", _protect_handlebars, original_content)

            soup = BeautifulSoup(protected_content, "html.parser")
            is_partial = "partials" in file.parts or "shared" in file.parts

            if is_partial:
                # convert <script src="..."> to @vite in partials
                for script_tag in soup.find_all("script"):
                    src = script_tag.get("src")
                    if not src:
                        continue
                    normalized = re.sub(r"^(?:\./|\.\./)*", "", src)
                    if normalized.startswith(("assets/js/", "js/", "scripts/")) and not normalized.startswith(
                            ("assets/js/vendor/", "assets/js/libs/", "assets/js/plugins/")
                    ):
                        transformed = re.sub(r"^assets/", "resources/", normalized, 1)
                        vite_line = f"@vite(['{transformed}'])"
                        script_tag.replace_with(NavigableString(vite_line))
                        self.vite_inputs.add(transformed)

                out = str(soup)

                # restore original {{ ... }} blocks
                for key, original in placeholder_map.items():
                    out = out.replace(key, original)

                out = self._replace_all_includes_with_blade(out)
                out = self._replace_asset_image_paths(out)
                out = self._replace_anchor_links_with_routes(out, self.route_map)
                out = re.sub(r'(@yield\(.*?\))=""', r'\1', out)
                file.write_text(out, encoding="utf-8")

                # Log.converted(f"{file}")
                count += 1
                continue

            # collect <link> tags
            links_html = "\n".join(f"    {str(tag)}" for tag in soup.find_all("link"))
            for tag in soup.find_all("link"):
                tag.decompose()

            # collect <script> tags -> @vite where applicable
            scripts_html_list = []
            for script_tag in soup.find_all("script"):
                src = script_tag.get("src")
                if not src:
                    continue
                normalized = re.sub(r"^(?:\./|\.\./)*", "", src)
                if normalized.startswith(("assets/js/", "js/", "scripts/")) and not normalized.startswith(
                        ("assets/js/vendor/", "assets/js/libs/", "assets/js/plugins/")
                ):
                    transformed = re.sub(r"^assets/", "resources/", normalized, 1)
                    vite_line = f"@vite(['{transformed}'])"
                    scripts_html_list.append(f"    {vite_line}")
                    self.vite_inputs.add(transformed)
                else:
                    scripts_html_list.append(f"    {str(script_tag)}")
                script_tag.decompose()

            scripts_output = "\n".join(scripts_html_list)

            # find main content region
            content_div = soup.find(attrs={"data-content": True})
            if content_div:
                body_html = content_div.decode_contents()
                layout_target = "shared.vertical"
            elif soup.body:
                body_html = soup.body.decode_contents()
                layout_target = "shared.base"
            else:
                body_html = str(soup)
                layout_target = "shared.base"

            # restore {{ ... }} in body_html
            for key, original in placeholder_map.items():
                body_html = body_html.replace(key, original)

            main_content = self._replace_all_includes_with_blade(body_html).strip()

            if layout_title:
                extends_line = f"@extends('{layout_target}', ['title' => '{escaped_title}'])"
            else:
                extends_line = f"@extends('{layout_target}')"

            html_attr_section = self._extract_html_data_attributes(original_content)

            blade_output = f"""{extends_line}

{html_attr_section}

@section('styles')
{links_html}
@endsection

@section('content')
{main_content}
@endsection

@section('scripts')
{scripts_output}
@endsection
        """

            final = self._replace_asset_image_paths(blade_output)
            final = self._replace_anchor_links_with_routes(final, self.route_map)
            file.write_text(final.strip() + "\n", encoding="utf-8")

            # Log.converted(f"{file}")
            count += 1

        Log.info(f"{count} files converted in {folder_path}")

    def _parse_include_params(self, raw: str):
        """Parse JSON, PHP array, Blade array, or key="value" Handlebars-style params."""
        if not raw:
            return {}

        raw = html.unescape(raw.strip())

        if raw.startswith("{") and raw.endswith("}"):
            try:
                cleaned = re.sub(r"([\{\s,])\s*([a-zA-Z_][\w-]*)\s*:", r'\1"\2":', raw)
                cleaned = re.sub(r",\s*([\}\]])", r"\1", cleaned)
                return json.loads(cleaned)
            except json.JSONDecodeError as e:
                Log.warning(f"JSON decode error in include params: {e}")

        # PHP array(...) style
        m_arr = re.search(r"array\s*\(([\s\S]*)\)", raw)
        if m_arr:
            return self._extract_php_array_params(f"array({m_arr.group(1)})")

        # Blade array ['key' => 'value'] style
        blade_matches = re.findall(
            r"['\"](?P<key>[^'\"]+)['\"]\s*=>\s*(['\"](?P<val>[^'\"]*)['\"]|(?P<bool>true|false)|(?P<num>-?\d+(?:\.\d+)?))",
            raw,
        )
        if blade_matches:
            parsed = {}
            for k, _, v, b, n in blade_matches:
                if v:
                    parsed[k] = v
                elif b:
                    parsed[k] = b == "true"
                elif n:
                    parsed[k] = float(n) if "." in n else int(n)
            return parsed

        kv_pairs = re.findall(r"(\w+)=[\"']([^\"']+)[\"']", raw)
        if kv_pairs:
            return {k: v for k, v in kv_pairs}

        return {}

    def _extract_php_array_params(self, include_str: str):
        """Parse PHP array(key => value, ...) style parameters."""
        m = re.search(r"array\s*\(([\s\S]*)\)", include_str)
        if not m:
            return {}

        body = m.group(1)
        param_pattern = re.compile(r"""
            (?:['"](?P<key>[^'"]+)['"]\s*=>\s*)?
            (?:
                ['"](?P<sval>(?:\\.|[^'"])*)['"] |
                (?P<nval>-?\d+(?:\.\d+)?) |
                (?P<bool>true|false)
            )
            \s*(?:,\s*|$)
        """, re.VERBOSE | re.DOTALL)

        result = {}
        for match in param_pattern.finditer(body):
            key = match.group("key")
            if not key:
                continue
            if match.group("sval"):
                result[key] = match.group("sval")
            elif match.group("nval"):
                result[key] = float(match.group("nval")) if "." in match.group("nval") else int(match.group("nval"))
            elif match.group("bool"):
                result[key] = match.group("bool") == "true"
        return result

    def _format_blade_params(self, data: dict):
        """Format dict as Blade include parameter array."""
        formatted = []
        for key, value in data.items():
            if isinstance(value, str):
                value = value.replace("'", "\\'")
                formatted.append(f"'{key}' => '{value}'")
            elif isinstance(value, bool):
                formatted.append(f"'{key}' => {'true' if value else 'false'}")
            else:
                formatted.append(f"'{key}' => {json.dumps(value)}")
        return ", ".join(formatted)

    def _replace_all_includes_with_blade(self, content: str):
        """
        Converts @@include(...) and {{> ...}} / {{&gt; ...}} to Blade @include(...),
        auto-prepending 'shared.partials.' for all partial references.
        """
        fragments = []
        for label, pattern in self.config.import_patterns.items():
            # Extend to also match escaped form ({{&gt; ...}})
            alt_pattern = re.compile(pattern.pattern.replace(r"\>\s*", r"(?:>|&gt;)\s*"))
            for match in alt_pattern.finditer(content):
                fragments.append({
                    "label": label,
                    "full": match.group(0),
                    "path": match.group("path"),
                    "params": match.groupdict().get("params", "")
                })

        for frag in fragments:
            path = frag["path"]
            params_raw = frag["params"]

            # Normalize path: remove ./ or ../ prefixes
            clean_path = re.sub(r"^(\.\/|\.\.\/)+", "", path)
            clean_path = Path(clean_path).with_suffix("").as_posix()

            # partials/... → shared.partials....
            if clean_path.startswith("partials/"):
                clean_path = clean_path.replace("partials/", "shared/partials/", 1)
            # top-level includes (no folder)
            elif "/" not in clean_path:
                clean_path = f"shared/partials/{clean_path}"
            # already under shared (rare edge)
            elif clean_path.startswith("shared/partials/"):
                pass  # already correct

            # Convert to dot notation for Blade
            clean_path = clean_path.replace("/", ".")

            # Skip title includes (they go into extends)
            if Path(clean_path).name.lower() in {"title-meta", "app-meta-title"}:
                content = content.replace(frag["full"], "")
                continue

            params = self._parse_include_params(params_raw)
            if params:
                param_str = self._format_blade_params(params)
                replacement = f"@include('{clean_path}', [{param_str}])"
            else:
                replacement = f"@include('{clean_path}')"

            content = content.replace(frag["full"], replacement)

        return content

    def _update_vite_config(self):
        """
        Always recreate vite.config.js with the current inputs.
        Removes all existing content and writes a minimal, valid configuration file.
        """
        # Prepare Vite input list (exclude .min files)
        filtered_inputs = [p for p in sorted(self.vite_inputs) if ".min" not in p]
        inputs_str = ",\n            ".join(f"'{p}'" for p in filtered_inputs)
        new_input_block = f"input: [\n            {inputs_str}\n        ]"

        tailwind = self.config.ui_library == "tailwind"

        # Create clean minimal config
        minimal_config = f"""import {{ defineConfig }} from 'vite';
import laravel from 'laravel-vite-plugin';
{"import tailwindcss from '@tailwindcss/vite';" if tailwind else ""}

export default defineConfig({{
    plugins: [
        laravel({{
            {new_input_block},
            refresh: true,
        }}),
        {"tailwindcss()" if tailwind else ""}
    ],
}});
    """

        self.project_vite_path.parent.mkdir(parents=True, exist_ok=True)
        self.project_vite_path.write_text(minimal_config.strip(), encoding="utf-8")

        Log.info(f"vite.config.js regenerated with {len(filtered_inputs)} inputs at: {self.project_vite_path}")

    def _generate_routes(self, views_dir: Path, web_php_path: Path):
        """
        Generate Laravel routes based on view file structure and append them to routes/web.php.

        Parameters:
            views_dir (Path): Path to 'resources/views' directory.
            web_php_path (Path): Path to 'routes/web.php' file.
        """
        routes = []

        for file in views_dir.rglob("*.blade.php"):
            # skip shared/partials
            if any(part in {"shared", "partials"} for part in file.parts):
                continue

            # relative view name (e.g., charts.apex.area)
            rel_path = file.relative_to(views_dir)
            view_name = rel_path.as_posix().replace(".blade.php", "").replace("/", ".")

            # convert to URL path (e.g., /charts/apex/area)
            route_path = "/" + rel_path.as_posix().replace(".blade.php", "")

            # Handle index pages -> `/`
            if route_path.endswith("/index"):
                route_path = route_path[:-6] or "/"

            route_code = (
                f"Route::get('{route_path}', function () {{\n"
                f"    return view('{view_name}');\n"
                f"}});"
            )
            routes.append(route_code)

        routes_text = "\n\n".join(routes)

        if not routes:
            Log.warning("No routes generated — no Blade views found.")
            return

        # Add section header for clarity
        appended_block = f"\n{routes_text}\n"

        # Append or create the file safely
        web_php_path.parent.mkdir(parents=True, exist_ok=True)
        if web_php_path.exists():
            with open(web_php_path, "a", encoding="utf-8") as f:
                f.write(appended_block)
            Log.success(f"Appended {len(routes)} routes to {web_php_path}")
        else:
            with open(web_php_path, "w", encoding="utf-8") as f:
                f.write("<?php\n\nuse Illuminate\\Support\\Facades\\Route;\n")
                f.write(appended_block)
            Log.success(f"Created new {web_php_path} with {len(routes)} routes")

        return routes_text

    def _replace_anchor_links_with_routes(self, content: str, route_map: dict[str, str]):
        """
        Replace <a href="filename.html"> links with Laravel route URLs from the route map.
        """

        pattern = re.compile(r'href=["\'](?P<href>[^"\']+\.html)["\']', re.IGNORECASE)

        def repl(match):
            href_val = match.group("href")
            href_file = Path(href_val).name
            if href_file in route_map:
                route_path = route_map[href_file]
                if route_path == "/index":
                    return f"href=\"{{{{ url('/') }}}}\""
                return f"href=\"{{{{ url('{route_path}') }}}}\""
            return match.group(0)

        return pattern.sub(repl, content)

    def _extract_html_data_attributes(self, html_content: str):
        """
        Extracts all attributes from the <html> tag that start with 'data-'
        and returns a Blade @section('html_attribute') block.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        html_tag = soup.find("html")
        if not html_tag:
            return ""

        attrs = [f'{k}="{v}"' for k, v in html_tag.attrs.items() if k.startswith("data-")]
        if not attrs:
            return ""

        attrs_str = " ".join(attrs)
        return f"@section('html_attribute')\n{attrs_str}\n@endsection"

    def _replace_asset_image_paths(self, content: str) -> str:
        """
        Convert static asset paths like ./assets/... or ../assets/... in:
          - <img src="...">
          - <link href="...">
          - background-image: url(...)
        to Laravel Blade {{ asset('...') }} syntax.
        """

        # Pattern for <img src="...">
        img_pattern = re.compile(
            r'src\s*=\s*["\'](?:\.{0,2}/)?assets/(?P<path>[^"\']+)["\']',
            flags=re.IGNORECASE
        )

        # Pattern for <link href="...">
        link_pattern = re.compile(
            r'href\s*=\s*["\'](?:\.{0,2}/)?assets/(?P<path>[^"\']+)["\']',
            flags=re.IGNORECASE
        )

        # Pattern for CSS background-image: url(...)
        css_pattern = re.compile(
            r'url\((["\']?)(?:\.{0,2}/)?assets/(?P<path>[^)\'"]+)\1\)',
            flags=re.IGNORECASE
        )

        # Replace in <img src="...">
        def repl_img(match):
            img_path = match.group("path").lstrip("/")
            return f'src="{{{{ asset(\'{img_path}\') }}}}"'

        # Replace in <link href="...">
        def repl_link(match):
            link_path = match.group("path").lstrip("/")
            return f'href="{{{{ asset(\'{link_path}\') }}}}"'

        # Replace in CSS url(...)
        def repl_css(match):
            css_path = match.group("path").lstrip("/")
            return f'url({{{{ asset(\'{css_path}\') }}}})'

        # Apply all replacements
        content = img_pattern.sub(repl_img, content)
        content = link_pattern.sub(repl_link, content)
        content = css_pattern.sub(repl_css, content)

        return content
