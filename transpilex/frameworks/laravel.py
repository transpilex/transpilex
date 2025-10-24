import re
import json
import shutil
import html
import subprocess
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString

from transpilex.config.base import LARAVEL_PROJECT_WITH_AUTH_CREATION_COMMAND, \
    LARAVEL_PROJECT_CREATION_COMMAND, LARAVEL_RESOURCES_PRESERVE, LARAVEL_AUTH_FOLDER
from transpilex.config.project import ProjectConfig
from transpilex.utils.assets import copy_assets, copy_public_only_assets, clean_relative_asset_paths
from transpilex.utils.file import remove_item, empty_folder_contents
from transpilex.utils.git import remove_git_folders
from transpilex.utils.logs import Log
from transpilex.utils.package_json import update_package_json
from transpilex.utils.replace_html_links import replace_html_links
from transpilex.utils.restructure import restructure_and_copy_files


class BaseLaravelConverter:
    def __init__(self, config: ProjectConfig):
        self.config = config


class LaravelConverter(BaseLaravelConverter):
    def __init__(self, config: ProjectConfig):
        super().__init__(config)

        self.project_views_path = Path(self.config.project_root_path / "resources" / "views")
        self.project_public_path = Path(self.config.project_root_path / "public")

        self.vite_inputs = set()

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

            remove_item(self.config.project_root_path / "CHANGELOG.md")

        except subprocess.CalledProcessError:
            Log.error("Laravel project creation failed")
            return

        if not self.config.use_auth:
            empty_folder_contents(self.project_views_path)

        restructure_and_copy_files(self.config.pages_path, self.project_views_path, self.config.file_extension)

        self._convert(self.project_views_path)

        public_only = copy_public_only_assets(self.config.asset_paths, self.project_public_path)

        copy_assets(self.config.asset_paths, self.config.project_assets_path, exclude=public_only,
                    preserve=LARAVEL_RESOURCES_PRESERVE)

        update_package_json(self.config)

        Log.project_end(self.config.project_name, str(self.config.project_root_path))

    def _parse_include_params(self, raw: str) -> dict:
        """Parse parameters from JSON, PHP array, or Blade-style syntax."""
        if not raw:
            return {}

        raw = html.unescape(raw.strip())

        # --- Try JSON ---
        if raw.startswith("{") and raw.endswith("}"):
            try:
                cleaned = re.sub(r"([\{\s,])\s*([a-zA-Z_][\w-]*)\s*:", r'\1"\2":', raw)
                cleaned = re.sub(r",\s*([\}\]])", r"\1", cleaned)
                return json.loads(cleaned)
            except json.JSONDecodeError:
                pass

        # --- Try PHP array syntax ---
        m_arr = re.search(r"array\s*\(([\s\S]*)\)", raw)
        if m_arr:
            return self._extract_php_array_params(f"array({m_arr.group(1)})")

        # --- Try Blade ['key' => 'value'] ---
        matches = re.findall(
            r"['\"](?P<key>[^'\"]+)['\"]\s*=>\s*(['\"](?P<val>[^'\"]*)['\"]|(?P<bool>true|false)|(?P<num>-?\d+(?:\.\d+)?))",
            raw
        )
        if matches:
            parsed = {}
            for k, _, v, b, n in matches:
                if v:
                    parsed[k] = v
                elif b:
                    parsed[k] = b == "true"
                elif n:
                    parsed[k] = float(n) if "." in n else int(n)
            return parsed

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

    def _format_blade_params(self, data: dict) -> str:
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

    # ----------------------------------------------------------------------
    # INCLUDE REPLACEMENT
    # ----------------------------------------------------------------------

    def _replace_all_includes_with_blade(self, content: str) -> str:
        """
        Convert @@include(...) and {{> ...}} to Blade @include(...) syntax.
        Uses import_patterns loaded from JSON.
        """

        fragments = []
        for label, pattern in self.config.import_patterns.items():
            for match in pattern.finditer(content):
                fragments.append({
                    "label": label,
                    "full": match.group(0),
                    "path": match.group("path"),
                    "params": match.groupdict().get("params", "")
                })

        for frag in fragments:
            path = frag["path"]
            params_raw = frag["params"]

            # Skip title includes
            if Path(path).name.lower() in {"title-meta.html", "app-meta-title.html"}:
                content = content.replace(frag["full"], "")
                continue

            params = self._parse_include_params(params_raw)
            blade_path = Path(path).with_suffix("").as_posix().replace("/", ".")

            if params:
                param_str = self._format_blade_params(params)
                replacement = f"@include('{blade_path}', [{param_str}])"
            else:
                replacement = f"@include('{blade_path}')"

            content = content.replace(frag["full"], replacement)

        return content

    # ----------------------------------------------------------------------
    # CONVERSION LOGIC
    # ----------------------------------------------------------------------

    def _convert(self, folder_path: Path):
        """Convert files inside Laravel views directory."""
        count = 0

        for file in folder_path.rglob(f"*{self.config.file_extension}"):
            if not file.is_file():
                continue

            try:
                content = file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            soup = BeautifulSoup(content, "html.parser")
            is_partial = "partials" in file.parts

            # ---------------------------------------------------------
            # 1️⃣ Partial Files
            # ---------------------------------------------------------
            if is_partial:
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
                out = self._replace_all_includes_with_blade(out)
                out = clean_relative_asset_paths(out)
                out = replace_html_links(out, "")
                file.write_text(out, encoding="utf-8")

                Log.converted(f"{file.relative_to(folder_path)} (partial)")
                count += 1
                continue

            # ---------------------------------------------------------
            # 2️⃣ Full Page Files
            # ---------------------------------------------------------
            layout_title = ""
            for pattern in self.config.import_patterns.values():
                for m in pattern.finditer(content):
                    if Path(m.group("path")).name.lower() in {"title-meta.html", "app-meta-title.html"}:
                        meta = self._parse_include_params(m.groupdict().get("params", ""))
                        layout_title = meta.get("title") or meta.get("pageTitle") or ""
                        break
                if layout_title:
                    break

            escaped_title = layout_title.replace("'", "\\'")
            extends_line = (
                f"@extends('layouts.vertical', ['title' => '{escaped_title}'])"
                if layout_title else "@extends('layouts.vertical')"
            )

            # Collect styles
            links_html = "\n".join(f"    {str(tag)}" for tag in soup.find_all("link"))
            for tag in soup.find_all("link"): tag.decompose()

            # Collect scripts
            scripts_html = []
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
                    scripts_html.append(f"    {vite_line}")
                    self.vite_inputs.add(transformed)
                else:
                    scripts_html.append(f"    {str(script_tag)}")
                script_tag.decompose()

            scripts_output = "\n".join(scripts_html)

            # Extract main content
            content_div = soup.find(attrs={"data-content": True})
            body_html = (
                content_div.decode_contents()
                if content_div
                else (soup.body.decode_contents() if soup.body else str(soup))
            )

            main_content = self._replace_all_includes_with_blade(body_html).strip()

            blade_output = f"""{extends_line}

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

            final = clean_relative_asset_paths(blade_output)
            file.write_text(final.strip() + "\n", encoding="utf-8")
            Log.converted(f"{file.relative_to(folder_path)} (page)")
            count += 1

        Log.info(f"{count} Laravel Blade files converted in {folder_path}")
