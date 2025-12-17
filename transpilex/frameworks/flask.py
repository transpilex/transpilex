import json
import re
import subprocess
import ast
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString

from transpilex.config.base import FLASK_PROJECT_CREATION_COMMAND_AUTH, FLASK_PROJECT_CREATION_COMMAND
from transpilex.config.project import ProjectConfig
from transpilex.utils.assets import copy_assets, replace_asset_paths
from transpilex.utils.file import find_files_with_extension, copy_and_change_extension, copy_items, move_files
from transpilex.utils.git import remove_git_folders
from transpilex.utils.gulpfile import add_gulpfile
from transpilex.utils.logs import Log
from transpilex.utils.package_json import update_package_json
from transpilex.utils.replace_html_links import replace_html_links
from transpilex.utils.replace_variables import replace_variables


class BaseFlaskConverter:
    def __init__(self, config: ProjectConfig):
        self.config = config

        self.project_pages_path = Path(self.config.project_root_path / "apps" / "templates" / "pages")
        self.project_partials_path = self.config.project_partials_path

    def init_create_project(self):
        try:
            self.config.project_root_path.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                FLASK_PROJECT_CREATION_COMMAND_AUTH if self.config.use_auth else FLASK_PROJECT_CREATION_COMMAND,
                cwd=self.config.project_root_path,
                check=True,
                capture_output=True, text=True)

            Log.success("Flask project created successfully")

            remove_git_folders(self.config.project_root_path)

        except subprocess.CalledProcessError:
            Log.error("Flask project creation failed")
            return

        files = find_files_with_extension(self.config.pages_path)
        copy_and_change_extension(files, self.config.pages_path, self.project_pages_path, self.config.file_extension)

        self._convert()

        if self.config.partials_path:
            move_files(Path(self.project_pages_path / "partials"), self.config.project_partials_path)
            replace_variables(self.project_partials_path, self.config.variable_patterns,
                              self.config.variable_replacement, self.config.file_extension)

    def _convert(self):
        """
        Converts HTML files to Django templates using the same pipeline logic
        as LaravelConverter, driven by config.import_patterns.items().
        """
        count = 0
        for file in self.project_pages_path.rglob("*.html"):
            with open(file, "r", encoding="utf-8") as f:
                content = f.read()

            layout_title = ""
            # normalize &gt; back to >
            title_scan_source = content.replace("&gt;", ">")

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

            # Apply global patterns
            for pattern_name, pattern_data in self.config.import_patterns.items():
                if isinstance(pattern_data, tuple):
                    regex_pattern, handler_name = pattern_data
                elif isinstance(pattern_data, dict):
                    regex_pattern = pattern_data.get("pattern")
                    handler_name = pattern_data.get("handler")
                else:
                    regex_pattern = pattern_data
                    handler_name = None

                if not regex_pattern:
                    continue

                # Only compile if it’s not already a compiled regex
                if isinstance(regex_pattern, re.Pattern):
                    compiled = regex_pattern
                else:
                    compiled = re.compile(regex_pattern, re.DOTALL)

                handler_func = getattr(self, handler_name, None) if handler_name else None

                if handler_func:
                    content = compiled.sub(handler_func, content)
                else:
                    content = compiled.sub(lambda m: self._replace_all_includes_with_flask(m.group(0)), content)

            final_output = self._replace_asset_links_with_static(content)
            final_output = replace_html_links(final_output, '')

            soup = BeautifulSoup(final_output, "html.parser")

            is_layout = bool(soup.find("body") or soup.find(attrs={"data-content": True}))

            if is_layout:
                soup_for_extraction = BeautifulSoup(final_output, "html.parser")
                head_tag = soup_for_extraction.find("head")
                links_html = "\n".join(str(tag) for tag in head_tag.find_all("link")) if head_tag else ""

                def is_year_script(tag):
                    return tag.name == "script" and not tag.has_attr("src") and "getFullYear" in (tag.string or "")

                scripts_to_move = []
                if self.config.frontend_pipeline == "gulp":
                    scripts_to_move = [
                        str(s) for s in soup_for_extraction.find_all("script") if not is_year_script(s)
                    ]
                else:
                    scripts_to_move = []

                scripts_html = "\n".join(scripts_to_move)

                for s in soup_for_extraction.find_all("script"):
                    if not is_year_script(s):
                        s.decompose()

                # Detect content container
                content_div = soup_for_extraction.find(attrs={"data-content": True})
                if content_div:
                    content_section = content_div.decode_contents().strip()
                    template_name = "vertical.html"
                elif soup_for_extraction.body:
                    content_section = soup_for_extraction.body.decode_contents().strip()
                    template_name = "base.html"
                else:
                    content_section = soup_for_extraction.decode()
                    template_name = "base.html"

                # Build Django template structure
                django_template = f"""{{% extends 'layouts/{template_name}' %}}

{{% block title %}}{escaped_title if escaped_title else ""}{{% endblock title %}}

{{% block styles %}}
{links_html}
{{% endblock styles %}}

{{% block {'content' if template_name == 'base.html' else 'page_content'} %}}
{content_section}
{{% endblock {'content' if template_name == 'base.html' else 'page_content'} %}}

{{% block scripts %}}
{scripts_html}
{{% endblock scripts %}}"""

                final_output = django_template.strip()

            with open(file, "w", encoding="utf-8") as f:
                f.write(final_output + "\n")

            # Log.converted(str(file))
            count += 1

        Log.info(f"{count} files converted in {self.project_pages_path}")

    def _replace_all_includes_with_flask(self, content: str):
        """
        Convert @@include(...) and {{> ...}} into Jinja2 Flask includes.
        Extracts ANY meta fields passed in include parameters.
        """

        fragments = []

        for label, pattern in self.config.import_patterns.items():
            if not isinstance(pattern, re.Pattern):
                try:
                    pattern = re.compile(pattern, re.MULTILINE | re.VERBOSE)
                except re.error as e:
                    Log.warning(f"Invalid include pattern '{label}': {e}")
                    continue

            # Also support escaped {{&gt; ...}}
            alt_pattern = re.compile(
                pattern.pattern.replace(r"\>\s*", r"(?:>|&gt;)\s*"),
                re.MULTILINE | re.VERBOSE
            )

            for m in alt_pattern.finditer(content):
                fragments.append({
                    "full": m.group(0),
                    "path": (m.groupdict().get("path") or "").strip(),
                    "params": (m.groupdict().get("params") or "").strip()
                })

        # Process each fragment → produce Flask output
        for frag in fragments:
            raw_path = frag["path"]
            raw_params = frag["params"]

            if not raw_path:
                continue

            # Normalize path
            clean_path = re.sub(r"^(\.\/|\.\.\/)+", "", raw_path)
            clean_path = Path(clean_path).with_suffix("").as_posix()

            # Make sure partials go inside partials/
            if "/" not in clean_path:
                clean_path = f"partials/{clean_path}"
            elif clean_path.startswith("partials/"):
                pass

            params = self._parse_include_params(raw_params)

            set_lines = []

            for key, value in params.items():
                escaped = str(value).replace("'", "\\'")
                set_lines.append(f"{{% set {key}='{escaped}' %}}")

            set_block = "\n".join(set_lines)

            include_line = f"{{% include '{clean_path}.html' %}}"

            final_block = f"{set_block}\n{include_line}" if set_block else include_line

            # Replace original include
            content = content.replace(frag["full"], final_block)

        return content

    def _parse_include_params(self, params_str: str):
        """
        Parses include parameters from various formats:
          - {"title": "Home", "subtitle": "Dashboard"}
          - { title: "Home", subtitle: "Dashboard" }
          - subtitle="UI" title="Images"
          - subtitle='UI' title='Images'
        Returns a Python dictionary of key-value pairs.
        """
        params_str = (params_str or "").strip()
        if not params_str:
            return {}

        if params_str.startswith("{") and params_str.endswith("}"):
            try:
                s = params_str
                # Normalize JS-style unquoted keys
                s = re.sub(r"([{,])\s*([a-zA-Z_][\w]*)\s*:", r"\1 '\2':", s)
                s = s.replace("true", "True").replace("false", "False").replace("null", "None")
                s = re.sub(r",\s*([}\]])", r"\1", s)
                s = re.sub(r"\s{2,}", " ", s)
                return ast.literal_eval(s)
            except Exception as e:
                Log.warning(f"Failed to parse JS/JSON-style include params: {params_str} ({e})")
                return {}

        try:
            pairs = re.findall(r'(\w+)\s*=\s*["\']([^"\']+)["\']', params_str)
            return {k: v for k, v in pairs}
        except Exception as e:
            Log.warning(f"Failed to parse key=value include params: {params_str} ({e})")
            return {}

    def _replace_asset_links_with_static(self, html: str):
        """
        Convert asset paths inside src=, href= to:
            {{ config.ASSETS_ROOT }}/<path>
        Convert inline CSS url(...) paths to:
            /static/<path>
        """

        asset_extensions = [
            'js', 'css', 'png', 'jpg', 'jpeg', 'gif', 'svg', 'ico',
            'webp', 'woff', 'woff2', 'ttf', 'eot', 'mp4', 'webm'
        ]
        extensions_pattern = '|'.join(asset_extensions)

        # IMG, SCRIPT, LINK TAGS → USE {{ config.ASSETS_ROOT }}
        attr_pattern = re.compile(
            r'\b(href|src)\s*=\s*["\']'
            r'(?!{{|#|https?://|//|mailto:|tel:)'
            r'(?P<path>[^"\'#]+\.(?:' + extensions_pattern + r'))'
                                                             r'(?P<trailing>[^"\']*)'
                                                             r'["\']',
            flags=re.IGNORECASE
        )

        def attr_replacer(match: re.Match) -> str:
            attr = match.group(1)
            path = match.group("path")
            trailing = match.group("trailing")

            # Normalize: remove "./", "../", custom folders, and "assets/"
            normalized = re.sub(r'^(?:\.{0,2}/)*(?:.*?/)?assets/', '', path).lstrip('/')

            return f'{attr}="{{{{ config.ASSETS_ROOT }}}}/{normalized}{trailing}"'

        html = attr_pattern.sub(attr_replacer, html)

        # INLINE CSS url(...) → USE /static
        css_pattern = re.compile(
            r'url\(\s*[\'"]?(?:\.{0,2}/)?(?:.*?/)?assets/(?P<path>[^)\'"]+)[\'"]?\s*\)',
            flags=re.IGNORECASE
        )

        def css_replacer(match: re.Match) -> str:
            path = match.group("path").lstrip('/')
            return f"url('/static/{path}')"

        html = css_pattern.sub(css_replacer, html)

        return html


class FlaskGulpConverter(BaseFlaskConverter):
    def __init__(self, config: ProjectConfig):
        super().__init__(config)

    def create_project(self):
        Log.project_start(self.config.project_name)

        self.init_create_project()

        if self.config.asset_paths:
            copy_assets(self.config.asset_paths, self.config.project_assets_path)
            replace_asset_paths(self.config.project_assets_path, '/static')

        add_gulpfile(self.config)

        update_package_json(self.config)

        copy_items(Path(self.config.src_path / "package-lock.json"), self.config.project_root_path)

        Log.project_end(self.config.project_name, str(self.config.project_root_path))


class FlaskConverter:
    def __init__(self, config: ProjectConfig):
        self.config = config

        if self.config.frontend_pipeline == "gulp":
            FlaskGulpConverter(self.config).create_project()
