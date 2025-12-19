import re
import json
import html
import subprocess
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString

from transpilex.config.project import ProjectConfig
from transpilex.utils.logs import Log
from transpilex.config.base import SYMFONY_PROJECT_CREATION_COMMAND, SYMFONY_ASSETS_PRESERVE
from transpilex.utils.git import remove_git_folders
from transpilex.utils.file import copy_items, find_files_with_extension, copy_and_change_extension
from transpilex.utils.gulpfile import add_gulpfile
from transpilex.utils.package_json import update_package_json
from transpilex.utils.assets import copy_assets, replace_asset_paths, clean_relative_asset_paths
from transpilex.utils.replace_html_links import replace_html_links
from transpilex.utils.replace_variables import replace_variables


class BaseSymfonyConverter:
    def __init__(self, config: ProjectConfig):
        self.config = config

        self.project_templates_path = Path(self.config.project_root_path / "templates")

    def init_create_project(self):
        try:
            self.config.project_root_path.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                SYMFONY_PROJECT_CREATION_COMMAND,
                cwd=self.config.project_root_path,
                check=True,
                capture_output=True,
                text=True,
            )

            Log.success("Symfony project created successfully")

            remove_git_folders(self.config.project_root_path)

        except subprocess.CalledProcessError:
            Log.error("Symfony project creation failed")
            return

        files = find_files_with_extension(self.config.pages_path)
        copy_and_change_extension(files, self.config.pages_path, self.project_templates_path,
                                  self.config.file_extension)

        self._convert()

        if self.config.partials_path:
            replace_variables(self.config.project_partials_path, self.config.variable_patterns,
                              self.config.variable_replacement, self.config.file_extension)

    def _convert(self):
        """Convert files into Symfony Twig views."""
        count = 0

        for file in self.project_templates_path.rglob(f"*{self.config.file_extension}"):
            if not file.is_file():
                continue

            try:
                original_content = file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            layout_title = ""
            title_scan_source = original_content.replace("&gt;", ">")

            # Detect title meta includes (same logic as Laravel)
            for label, pattern in self.config.import_patterns.items():
                alt_pattern = re.compile(pattern.pattern.replace(r"\>\s*", r"(?:>|&gt;)\s*"))
                for m in alt_pattern.finditer(title_scan_source):
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
                key = f"@@{len(placeholder_map)}@@"
                placeholder_map[key] = mm.group(0)
                return key

            protected_content = re.sub(
                r"(\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\})",
                _protect_handlebars,
                original_content,
                flags=re.DOTALL
            )

            soup = BeautifulSoup(protected_content, "html.parser")
            is_partial = "partials" in file.parts or "layouts" in file.parts

            if is_partial:

                out = str(soup)

                # Restore handlebars
                for key, original in placeholder_map.items():
                    # Log.error(f"{key} {original}")
                    out = out.replace(key, original)

                out = replace_html_links(out, '')
                out = clean_relative_asset_paths(out)
                out = self._replace_includes_with_twig(out)
                out = re.sub(r'(\{\{.*?\}\})=""', r'\1', out)

                file.write_text(out, encoding="utf-8")
                # Log.converted(f"{file}")
                count += 1
                continue

            links_html = "\n".join(str(tag) for tag in soup.find_all("link"))
            for tag in soup.find_all("link"):
                tag.decompose()

            scripts_to_move = []
            script_to_exclude = "document.write(new Date().getFullYear())"

            for tag in soup.find_all("script"):
                # Check if the tag's text content matches the one to exclude
                if tag.get_text(strip=True) == script_to_exclude:
                    # If it matches, do nothing. Leave it in the main content.
                    pass
                else:
                    # For ALL other scripts (inline or external), add them to the move list.
                    scripts_to_move.append(tag)

            scripts_html = "\n    ".join([str(tag) for tag in scripts_to_move])

            tags_to_decompose = scripts_to_move
            for tag in tags_to_decompose:
                tag.decompose()

            content_div = soup.find(attrs={"data-content": True})
            if content_div:
                body_html = content_div.decode_contents()
                layout_target = "layouts/vertical.html.twig"
            elif soup.body:
                body_html = soup.body.decode_contents()
                layout_target = "layouts/base.html.twig"
            else:
                body_html = str(soup)
                layout_target = "layouts/base.html.twig"

            # Convert include syntax to Twig
            main_content = self._replace_includes_with_twig(body_html).strip()

            html_attr = self._extract_html_data_attributes(original_content)

            twig_output = f"""
{{% extends '{layout_target}' %}}

{html_attr}

{{% set title = '{escaped_title}' %}}

{{% block styles %}}
{links_html}
{{% endblock %}}

{{% block content %}}
{main_content}
{{% endblock %}}

{{% block scripts %}}
{scripts_html}
{{% endblock %}}
    """

            out = replace_html_links(twig_output, '')
            out = clean_relative_asset_paths(out)

            file.write_text(out.strip() + "\n", encoding="utf-8")

            # Log.converted(f"{file}")
            count += 1

        Log.info(f"{count} files converted into {self.project_templates_path}")

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

    def _replace_includes_with_twig(self, content: str):
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
            clean_path = Path(clean_path).with_suffix(".html.twig").as_posix()

            params = self._parse_include_params(params_raw)

            if params:
                json_params = json.dumps(params)
                replacement = f"{{{{ include('{clean_path}', {json_params}) }}}}"
            else:
                replacement = f"{{{{ include('{clean_path}') }}}}"

            content = content.replace(frag["full"], replacement)

        return content

    def _extract_html_data_attributes(self, html_content: str):
        """
        Extracts all data-* attributes from <html> tag and converts them into:
        {% set html_attribute = 'data-x=y data-b=c' %}
        """
        soup = BeautifulSoup(html_content, "html.parser")
        html_tag = soup.find("html")
        if not html_tag:
            return ""

        attrs = []

        for k, v in html_tag.attrs.items():
            if k.startswith("data-"):
                if v is None:
                    attrs.append(k)
                else:
                    attrs.append(f'{k}={v}')

        if not attrs:
            return ""

        attr_string = " ".join(attrs)

        return f"{{% set html_attribute = '{attr_string}' %}}"


class SymfonyGulpConverter(BaseSymfonyConverter):
    def __init__(self, config: ProjectConfig):
        super().__init__(config)

    def create_project(self):
        Log.project_start(self.config.project_name)

        self.init_create_project()

        if self.config.asset_paths:
            copy_assets(self.config.asset_paths, self.config.project_assets_path, preserve=SYMFONY_ASSETS_PRESERVE)
            replace_asset_paths(self.config.project_assets_path, "")

        add_gulpfile(self.config)

        update_package_json(self.config)

        copy_items(
            Path(self.config.src_path / "package-lock.json"),
            self.config.project_root_path,
        )

        Log.project_end(self.config.project_name, str(self.config.project_root_path))


class SymfonyConverter:
    def __init__(self, config: ProjectConfig):
        self.config = config

        if self.config.frontend_pipeline == "gulp":
            SymfonyGulpConverter(self.config).create_project()
