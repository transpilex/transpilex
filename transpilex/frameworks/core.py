import re
import json
import html
import subprocess
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString

from transpilex.config.base import CORE_VITE_PROJECT_CREATION_COMMAND, CORE_PROJECT_CREATION_COMMAND, \
    SLN_FILE_CREATION_COMMAND
from transpilex.config.project import ProjectConfig
from transpilex.utils.assets import clean_relative_asset_paths
from transpilex.utils.file import rename_item, move_files
from transpilex.utils.git import remove_git_folders
from transpilex.utils.logs import Log
from transpilex.utils.replace_variables import replace_variables
from transpilex.utils.restructure import restructure_and_copy_files


class BaseCoreConverter:
    def __init__(self, config: ProjectConfig):
        self.config = config
        self.project_name = self.config.project_name.title()
        self.project_pages_path = Path(self.config.project_root_path / "Pages")
        self.project_shared_path = Path(self.config.project_root_path / self.project_pages_path / "Shared")
        self.route_map = None

    def init_create_project(self):
        try:
            self.config.project_root_path.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                CORE_VITE_PROJECT_CREATION_COMMAND if self.config.frontend_pipeline == 'vite' else CORE_PROJECT_CREATION_COMMAND,
                cwd=self.config.project_root_path,
                check=True,
                capture_output=True, text=True)

            Log.success("Core project created successfully")

            remove_git_folders(self.config.project_root_path)

            rename_item(Path(self.config.project_root_path / "PROJECT_NAME.csproj"),
                        f"{self.project_name}.csproj")

            subprocess.run(
                f'{SLN_FILE_CREATION_COMMAND} {self.project_name}', cwd=self.config.project_root_path,
                shell=True,
                check=True)

            sln_file = f"{self.project_name}.sln"

            subprocess.run(
                f'dotnet sln {sln_file} add {self.project_name}.csproj',
                cwd=self.config.project_root_path, shell=True, check=True)

            Log.info(".sln file created successfully")

        except subprocess.CalledProcessError:
            Log.error("Core project creation failed")
            return

        self.route_map = restructure_and_copy_files(
            self.config,
            self.project_pages_path,
            self.config.file_extension,
            case_style="pascal"
        )

        self._convert(self.project_pages_path)

        if self.config.partials_path:
            move_files(self.project_pages_path / "Partials", self.project_shared_path / "Partials")
            replace_variables(self.project_shared_path, self.config.variable_patterns,
                              self.config.variable_replacement, self.config.file_extension)

    def _convert(self, folder_path: Path):
        count = 0

        for file in folder_path.rglob(f"*{self.config.file_extension}"):
            if not file.is_file():
                continue

            try:
                original_content = file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            # --- Protect {{ }} expressions ---
            placeholder_map = {}

            def _protect_handlebars(m):
                key = f"__HB_{len(placeholder_map)}__"
                placeholder_map[key] = m.group(0)
                return key

            protected_content = re.sub(r"\{\{[^{]+\}\}", _protect_handlebars, original_content)

            soup = BeautifulSoup(protected_content, "html.parser")
            is_partial = "Partials" in file.parts or "Shared" in file.parts

            if is_partial:
                continue

            # Extract linked resources
            links_html = "\n".join(f"    {str(tag)}" for tag in soup.find_all("link"))
            for tag in soup.find_all("link"):
                tag.decompose()

            scripts_html = "\n".join(f"    {str(tag)}" for tag in soup.find_all("script"))
            for tag in soup.find_all("script"):
                tag.decompose()

            # Extract main content region
            content_block = soup.find(attrs={"data-content": True})
            if content_block:
                body_html = content_block.decode_contents()
            elif soup.body:
                body_html = soup.body.decode_contents()
            else:
                body_html = str(soup)

            for key, val in placeholder_map.items():
                body_html = body_html.replace(key, val)

            # Replace includes, patterns, and assets
            body_html = self._replace_all_includes_with_razor(body_html)
            body_html = clean_relative_asset_paths(body_html)
            # body_html = self._replace_anchor_links_with_routes(body_html, self.route_map)

            # Construct Razor file structure
            route_path = self._get_route_for_file(file)
            page_name = file.stem
            model_name = f"{self.config.project_name}.Pages.{page_name}Model"

            final_output = f"""@page "{route_path}"
@model {model_name}

@section Styles {{
{links_html}
}}

{body_html}

@section Scripts {{
{scripts_html}
}}"""

            file.write_text(final_output.strip() + "\n", encoding="utf-8")
            Log.converted(str(file))
            count += 1

        Log.info(f"{count} files converted in {folder_path}")

    def _replace_all_includes_with_razor(self, content: str) -> str:
        """Convert @@include(...) and {{> ...}} to Razor partial syntax."""
        fragments = []
        for label, pattern in self.config.import_patterns.items():
            alt_pattern = re.compile(pattern.pattern.replace(r"\>\s*", r"(?:>|&gt;)\s*"))
            for match in alt_pattern.finditer(content):
                fragments.append({
                    "full": match.group(0),
                    "path": match.group("path"),
                    "params": match.groupdict().get("params", "")
                })

        for frag in fragments:
            path = frag["path"]
            params_raw = frag["params"]
            clean_path = re.sub(r"^(\.\/|\.\.\/)+", "", path)
            clean_path = Path(clean_path).with_suffix("").as_posix()

            # Normalize partial path
            if clean_path.startswith("partials/"):
                clean_path = clean_path.replace("partials/", "Shared/Partials/", 1)
            elif "/" not in clean_path:
                clean_path = f"Shared/Partials/{clean_path}"

            # Parse parameters (JSON, key=value, etc.)
            params = self._parse_include_params(params_raw)
            args = ", ".join(f'new {{ {k} = "{v}" }}' for k, v in params.items()) if params else ""
            replacement = f"@await Html.PartialAsync(\"~/{clean_path}.cshtml\"{', ' + args if args else ''})"
            content = content.replace(frag["full"], replacement)

        return content

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
        """
        Match the .cshtml file (Pages/UI/Buttons.cshtml) to its route_map entry using normalized comparison.
        """

        # Normalize the filename stem to kebab-case, matching route_map keys
        def to_kebab(s):
            s = re.sub(r'([a-z0-9])([A-Z])', r'\1-\2', s)
            return s.lower().replace("_", "-")

        kebab_stem = to_kebab(file.stem)
        possible_html_name = f"{kebab_stem}.html"

        # Direct filename match
        if possible_html_name in self.route_map:
            return self.route_map[possible_html_name]

        # Try partial match
        for html_name, route in self.route_map.items():
            if html_name.startswith(kebab_stem) or kebab_stem in html_name:
                return route

        try:
            relative = file.relative_to(self.project_pages_path)
            parts = [to_kebab(p) for p in relative.with_suffix("").parts]
            route_guess = "/" + "/".join(parts)
            return route_guess
        except Exception:
            return "/"


class CoreGulpConverter(BaseCoreConverter):
    def __init__(self, config: ProjectConfig):
        super().__init__(config)

    def create_project(self):
        Log.project_start(self.config.project_name)
        self.init_create_project()
        Log.project_end(self.config.project_name, str(self.config.project_root_path))


class CoreViteConverter(BaseCoreConverter):
    def __init__(self, config: ProjectConfig):
        super().__init__(config)

    def create_project(self):
        Log.project_start(self.config.project_name)
        self.init_create_project()
        Log.project_end(self.config.project_name, str(self.config.project_root_path))


class CoreConverter:
    def __init__(self, config: ProjectConfig):
        self.config = config

        if self.config.frontend_pipeline == "gulp":
            CoreGulpConverter(self.config).create_project()
        else:
            CoreViteConverter(self.config).create_project()
