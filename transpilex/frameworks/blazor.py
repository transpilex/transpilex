import re
import json
import html
from pathlib import Path
from bs4 import BeautifulSoup
from cookiecutter.main import cookiecutter

from transpilex.config.base import BLAZOR_COOKIECUTTER_REPO
from transpilex.config.project import ProjectConfig
from transpilex.utils.assets import copy_assets, replace_asset_paths, clean_relative_asset_paths
from transpilex.utils.casing import apply_casing
from transpilex.utils.file import file_exists, copy_items, move_files
from transpilex.utils.gulpfile import add_gulpfile
from transpilex.utils.logs import Log

from transpilex.utils.package_json import sync_package_json
from transpilex.utils.replace_variables import replace_variables
from transpilex.utils.restructure import restructure_and_copy_files, to_kebab_case


class BlazorConverter:
    def __init__(self, config: ProjectConfig):
        self.config = config
        self.project_name = self.config.project_name.title()
        self.project_pages_path = Path(self.config.project_root_path / "Components" / "Pages")
        self.project_partials_path = Path(self.config.project_root_path / "Components" / "Layout" / "Partials")

        self.create_project()

    def create_project(self):
        Log.project_start(self.project_name)

        try:
            has_plugins_file = False

            if file_exists(self.config.src_path / "plugins.config.js"):
                has_plugins_file = True

            cookiecutter(
                BLAZOR_COOKIECUTTER_REPO,
                output_dir=str(self.config.project_root_path.parent),
                no_input=True,
                extra_context={'name': self.config.project_name,
                               'ui_library': self.config.ui_library.title(),
                               'frontend_pipeline': self.config.frontend_pipeline.title(),
                               'has_plugins_config': 'y' if has_plugins_file and self.config.frontend_pipeline == 'gulp' else 'n'
                               },
            )

            Log.success("Blazor project created successfully")
        except:
            Log.error("Blazor project creation failed")
            return

        self.route_map = restructure_and_copy_files(
            self.config,
            self.project_pages_path,
            self.config.file_extension,
            case_style="pascal"
        )

        self._convert()

        if self.config.partials_path:
            move_files(self.project_pages_path / "Partials", self.project_partials_path)
            replace_variables(self.project_partials_path, self.config.variable_patterns,
                              self.config.variable_replacement, self.config.file_extension)

        if self.config.asset_paths:
            copy_assets(self.config.asset_paths, self.config.project_assets_path)
            replace_asset_paths(self.config.project_assets_path, '')

            self._wrap_js_files_with_load_functions(self.config.project_assets_path / "js",
                                                    ignore_folders=["vendors", "libs", "plugins", "maps"])

        add_gulpfile(self.config)

        sync_package_json(self.config, ignore=["scripts", "type", "devDependencies"])

        copy_items(Path(self.config.src_path / "package-lock.json"), self.config.project_root_path)

        Log.project_end(self.project_name, str(self.config.project_root_path))

    def _convert(self):
        count = 0

        for file in self.project_pages_path.rglob(f"*{self.config.file_extension}"):
            if not file.is_file():
                continue

            try:
                original_content = file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            soup = BeautifulSoup(original_content, "html.parser")

            is_partial = "Partials" in file.parts
            if is_partial:
                out = str(soup)

                out = clean_relative_asset_paths(out)
                out = self._replace_anchor_links_with_routes(out, self.route_map)
                file.write_text(out, encoding="utf-8")

                # Log.converted(f"{file}")
                count += 1
                continue

            # Extract JS paths
            js_import_paths = []
            for tag in soup.find_all('script'):
                src = tag.get('src')

                if src:
                    # Handle external scripts
                    if not any(ex in src for ex in ["plugins/", "vendors/", "libs/", "plugin/", "vendor/", "lib/"]):
                        normalized_src = src.replace("assets/", "./")
                        js_import_paths.append(normalized_src)
                else:
                    # Handle inline scripts (No 'src')
                    script_content = tag.string
                    if script_content and "new Date().getFullYear()" in script_content:
                        # Replace the entire script tag with the Razor expression
                        tag.replace_with(soup.new_string("@DateTime.Now.Year"))
                        continue  # Skip decompose so we don't delete the replacement we just made

                # Remove the tag from the HTML (unless it was the Date replacement)
                tag.decompose()

            # Clean head tags
            for tag in soup.find_all(['link', 'title', 'meta']):
                tag.decompose()

            # Get main content
            content_block = soup.find(attrs={"data-content": True})
            body_html = content_block.decode_contents() if content_block else (
                soup.body.decode_contents() if soup.body else str(soup))

            body_html = clean_relative_asset_paths(body_html)
            body_html = self._replace_anchor_links_with_routes(body_html, self.route_map)
            body_html = self._replace_includes_with_components(body_html)

            route_path = self._get_route_for_file(file)
            code_block = self._generate_interop_block(js_import_paths)

            final_razor = f"""@page "{route_path}"
@rendermode InteractiveServer
@inject IJSRuntime JsRuntime;

{body_html.strip()}

{code_block}
"""
            target_file = file.with_suffix(".razor")
            target_file.write_text(final_razor, encoding="utf-8")
            count += 1

        Log.info(f"{count} files converted in {self.project_pages_path}")

    def _replace_includes_with_components(self, content: str) -> str:
        fragments = []
        for label, pattern in self.config.import_patterns.items():
            alt_pattern = re.compile(pattern.pattern.replace(r"\>\s*", r"(?:>|&gt;)\s*"))
            for match in alt_pattern.finditer(content):
                fragments.append({
                    "full": match.group(0),
                    "path": match.group("path"),
                    "params_raw": match.groupdict().get("params", "")
                })

        for frag in fragments:
            stem = Path(frag["path"]).stem
            clean_name = stem.replace("app-", "")
            component_name = apply_casing(clean_name, "pascal")

            # PageTitle -> PageBreadcrumb
            if component_name == "PageTitle":
                component_name = "PageBreadcrumb"

            params = self._parse_include_params(frag["params_raw"])

            attr_str = ""
            if params:
                attrs = []
                for k, v in params.items():
                    key = "title" if k in ["pageTitle", "page-title"] else k
                    attrs.append(f'{key}="{v}"')
                attr_str = " " + " ".join(attrs)

            # Self-closing PascalCase tag
            replacement = f"<{component_name}{attr_str} />"
            content = content.replace(frag["full"], replacement)

        return content

    def _generate_interop_block(self, js_paths: list):
        """Generates the @code block supporting multiple JS module imports."""
        import_logic = []
        load_calls = []
        module_vars = []

        # Filter to scripts that should be imported as modules (typically in pages/ or js/)
        # Adjust this filter based on which scripts actually export functions
        page_scripts = [p for p in js_paths if "./js/" in p and ".min.js" not in p]

        for i, path in enumerate(page_scripts):
            var_name = f"_module{i}"
            module_vars.append(f"    private IJSObjectReference? {var_name};")

            import_logic.append(
                f'            {var_name} = await JsRuntime.InvokeAsync<IJSObjectReference>("import", "{path}");')

            # Derive function name
            func_name = "load" + apply_casing(Path(path).stem, "pascal")
            load_calls.append(f'            await JsRuntime.InvokeVoidAsync("{func_name}");')

        # Format code blocks
        vars_str = "\n".join(module_vars)
        imports_str = "\n".join(import_logic)

        load_calls.append('            await JsRuntime.InvokeVoidAsync("loadConfig");')
        load_calls.append('            await JsRuntime.InvokeVoidAsync("loadApps");')
        calls_str = "\n".join(load_calls)

        return f"""@code {{
{vars_str}

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {{
        if (firstRender)
        {{
{imports_str}
{calls_str}
        }}
    }}
}}"""

    def _parse_include_params(self, raw: str):
        """Parse parameters passed into includes (JSON, key=value)."""
        if not raw:
            return {}
        raw = html.unescape(raw.strip())

        # JSON-like
        if raw.startswith("{") and raw.endswith("}"):
            try:
                normalized = re.sub(r"([\{\s,])\s*([a-zA-Z_][\w-]*)\s*:", r'\1"\2":', raw)
                normalized = re.sub(r",\s*([\}\]])", r"\1", normalized)
                return json.loads(normalized)
            except json.JSONDecodeError:
                return {}

        kv_pairs = re.findall(r"(\w+)=[\"']([^\"']+)[\"']", raw)
        return {k: v for k, v in kv_pairs}

    def _get_route_for_file(self, file: Path):
        try:
            rel_path = file.relative_to(self.project_pages_path)

            # Process segments: Apps/IssueTracker -> apps/issue-tracker
            route_segments = [to_kebab_case(p) for p in rel_path.with_suffix("").parts]
            route_path = "/" + "/".join(route_segments)

            if route_path.endswith("/index"):
                route_path = route_path[:-6]

            return route_path if route_path else "/"
        except:
            return "/"

    def _replace_anchor_links_with_routes(self, content: str, route_map: dict[str, str]):
        pattern = re.compile(r'href=["\'](?P<href>[^"\']+\.html)["\']', re.IGNORECASE)

        def repl(match):
            href_val = match.group("href")
            href_file = Path(href_val).name

            if href_file in route_map:
                route_path = route_map[href_file]

                if route_path == "/index":
                    return 'href="/"'

                return f'href="{route_path}"'

            return match.group(0)

        content = pattern.sub(repl, content)

        content = content.replace('href="/#', 'href="#')
        content = content.replace('href="/javascript:void(0);', 'href="javascript:void(0);')

        return content

    def _wrap_js_files_with_load_functions(self, js_directory: Path, ignore_folders: list[str] = None):
        """
        Scans a directory for JS files and wraps their content in:
        window.loadFilename = function() { ... };

        :param ignore_folders: List of folder names to skip (e.g., ['vendor', 'libs'])
        """
        if not js_directory.exists():
            Log.warning(f"JS directory {js_directory} does not exist. Skipping wrap.")
            return

        ignore_list = ignore_folders or []

        for js_file in js_directory.rglob("*.js"):
            # Check if file is in an ignored folder
            if any(folder in js_file.parts for folder in ignore_list):
                continue

            if not js_file.is_file():
                continue

            try:
                content = js_file.read_text(encoding="utf-8")

                # Skip if already wrapped or minified
                if "window.load" in content or js_file.suffix == ".min.js":
                    continue

                # Derive function name: 'apps-email' -> 'loadAppsEmail'
                func_name = "load" + apply_casing(js_file.stem, "pascal")

                wrapped_content = f"window.{func_name} = function () {{\n{content}\n}};"

                js_file.write_text(wrapped_content, encoding="utf-8")
            except Exception as e:
                Log.error(f"Failed to wrap JS file {js_file.name}: {e}")
