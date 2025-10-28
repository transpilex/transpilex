import re
import json
import shutil
import html
import subprocess
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString

from transpilex.config.base import LARAVEL_PROJECT_WITH_AUTH_CREATION_COMMAND, \
    LARAVEL_PROJECT_CREATION_COMMAND, LARAVEL_RESOURCES_PRESERVE
from transpilex.config.project import ProjectConfig
from transpilex.utils.assets import copy_assets, copy_public_only_assets, clean_relative_asset_paths
from transpilex.utils.file import remove_item, empty_folder_contents, move_files
from transpilex.utils.git import remove_git_folders
from transpilex.utils.logs import Log
from transpilex.utils.package_json import update_package_json
from transpilex.utils.replace_html_links import replace_html_links
from transpilex.utils.replace_variables import replace_variables
from transpilex.utils.restructure import restructure_and_copy_files


class LaravelConverter:
    def __init__(self, config: ProjectConfig):

        self.config = config

        self.project_views_path = Path(self.config.project_root_path / "resources" / "views")
        self.project_shared_path = Path(self.config.project_root_path / "resources" / "views" / "shared")
        self.project_public_path = Path(self.config.project_root_path / "public")
        self.project_vite_path = Path(self.config.project_root_path / "vite.config.js")
        self.vite_inputs = {'resources/scss/app.scss'}

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

        restructure_and_copy_files(self.config.pages_path, self.project_views_path, self.config.file_extension)

        self._convert(self.project_views_path)

        if self.config.partials_path:
            move_files(self.project_views_path / "partials", self.project_shared_path / "partials")
            replace_variables(self.config.project_partials_path, self.config.variable_patterns,
                              self.config.variable_replacement, self.config.file_extension)

        if self.config.asset_paths:
            public_only = copy_public_only_assets(self.config.asset_paths, self.project_public_path)
            copy_assets(self.config.asset_paths, self.config.project_assets_path, exclude=public_only,
                        preserve=LARAVEL_RESOURCES_PRESERVE)

        update_package_json(self.config, ignore=["scripts", "type", "devDependencies"])

        self._update_vite_config()

        Log.project_end(self.config.project_name, str(self.config.project_root_path))

    def _parse_include_params(self, raw: str):
        """Parse JSON, PHP array, Blade array, or key="value" Handlebars-style params."""
        if not raw:
            return {}

        raw = html.unescape(raw.strip())

        # --- JSON object style ---
        if raw.startswith("{") and raw.endswith("}"):
            try:
                cleaned = re.sub(r"([\{\s,])\s*([a-zA-Z_][\w-]*)\s*:", r'\1"\2":', raw)
                cleaned = re.sub(r",\s*([\}\]])", r"\1", cleaned)
                return json.loads(cleaned)
            except json.JSONDecodeError as e:
                Log.warning(f"JSON decode error in include params: {e}")

        # --- PHP array(...) style ---
        m_arr = re.search(r"array\s*\(([\s\S]*)\)", raw)
        if m_arr:
            return self._extract_php_array_params(f"array({m_arr.group(1)})")

        # --- Blade array ['key' => 'value'] style ---
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

        # --- Handlebars-style key="value" ---
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

            # Case 1: partials/... → shared.partials....
            if clean_path.startswith("partials/"):
                clean_path = clean_path.replace("partials/", "shared/partials/", 1)
            # Case 2: top-level includes (no folder)
            elif "/" not in clean_path:
                clean_path = f"shared/partials/{clean_path}"
            # Case 3: already under shared (rare edge)
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
                    # ex: "title-meta", "title-meta.html", "app-meta-title", etc.
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
            is_partial = "partials" in file.parts

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
                out = clean_relative_asset_paths(out)
                out = replace_html_links(out, "")
                file.write_text(out, encoding="utf-8")

                Log.converted(f"{file}")
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

            # finally choose extends line
            if layout_title:
                extends_line = f"@extends('{layout_target}', ['title' => '{escaped_title}'])"
            else:
                extends_line = f"@extends('{layout_target}')"

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

            Log.converted(f"{file}")
            count += 1

        Log.info(f"{count} files converted in {folder_path}")

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
