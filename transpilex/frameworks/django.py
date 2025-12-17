import re
import ast
from pathlib import Path
from cookiecutter.main import cookiecutter
from bs4 import BeautifulSoup, NavigableString

from transpilex.config.base import DJANGO_COOKIECUTTER_REPO
from transpilex.config.project import ProjectConfig
from transpilex.utils.assets import copy_assets, replace_asset_paths
from transpilex.utils.file import file_exists, find_files_with_extension, copy_and_change_extension, move_files, \
    copy_items
from transpilex.utils.gulpfile import has_plugins_config
from transpilex.utils.logs import Log
from transpilex.utils.package_json import sync_package_json
from transpilex.utils.replace_variables import replace_variables


class BaseDjangoConverter:
    def __init__(self, config: ProjectConfig):
        self.config = config
        self.project_pages_path = Path(self.config.project_root_path / self.config.project_name / "templates" / "pages")

    def init_create_project(self):
        try:
            has_plugins_file = False

            if file_exists(self.config.src_path / "plugins.config.js"):
                has_plugins_file = True

            cookiecutter(
                DJANGO_COOKIECUTTER_REPO,
                output_dir=str(self.config.project_root_path.parent),
                no_input=True,
                extra_context={'project_name': self.config.project_name,
                               'open_source_license': 'Not open source',
                               'ui_library': self.config.ui_library.title(),
                               'frontend_pipeline': self.config.frontend_pipeline.title(),
                               'has_plugins_config': 'y' if has_plugins_file and self.config.frontend_pipeline == 'gulp' else 'n',
                               'use_auth': 'y' if self.config.use_auth else 'n'
                               },
            )

            Log.success("Django project created successfully")
        except:
            Log.error("Django project creation failed")
            return

        files = find_files_with_extension(self.config.pages_path)
        copy_and_change_extension(files, self.config.pages_path, self.project_pages_path, self.config.file_extension)

        self._convert()

        if self.config.partials_path:
            move_files(Path(self.project_pages_path / "partials"), self.config.project_partials_path)
            replace_variables(self.config.project_partials_path, self.config.variable_patterns,
                              self.config.variable_replacement, self.config.file_extension)

        if self.config.asset_paths:
            copy_assets(self.config.asset_paths, self.config.project_assets_path)
            copy_items(Path(self.config.src_path / "public"), self.config.project_assets_path, copy_mode="contents")

        sync_package_json(self.config, ignore=["scripts", "type", "devDependencies"])

        copy_items(Path(self.config.src_path / "package-lock.json"), self.config.project_root_path)

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
                    content = compiled.sub(lambda m: self._replace_all_includes_with_django(m.group(0)), content)

            content_with_static_paths = self._replace_asset_links_with_static(content)
            final_content = self._replace_html_links_with_django_urls(content_with_static_paths)

            soup = BeautifulSoup(final_content, "html.parser")
            is_layout = bool(soup.find("body") or soup.find(attrs={"data-content": True}))

            if is_layout:
                soup_for_extraction = BeautifulSoup(final_content, "html.parser")
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
                    # Vite pipeline: extract {% vite_asset ... %} directives from HTML
                    vite_asset_pattern = re.compile(r"\{\%\s+vite_asset\s+['\"].+?['\"]\s+\%\}")
                    vite_scripts = vite_asset_pattern.findall(str(soup_for_extraction))
                    scripts_to_move.extend(vite_scripts)

                    soup_for_extraction = BeautifulSoup(
                        vite_asset_pattern.sub("", str(soup_for_extraction)), "html.parser"
                    )

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
{{% load static i18n {'django_vite' if self.config.frontend_pipeline == 'vite' else ''} %}}

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
            else:
                django_template = f"""{{% load static i18n {'django_vite' if self.config.frontend_pipeline == 'vite' else ''} %}}
{final_content}
"""
                final_output = django_template.strip()

            with open(file, "w", encoding="utf-8") as f:
                f.write(final_output + "\n")

            # Log.converted(str(file))
            count += 1

        Log.info(f"{count} files converted in {self.project_pages_path}")

    def _replace_all_includes_with_django(self, content: str):
        """
        Converts @@include(...) and {{> ...}} / {{&gt; ...}} syntaxes to Django {% include %}
        using regex patterns from config.import_patterns (loaded from JSON).
        Mirrors LaravelConverter._replace_all_includes_with_blade().
        """
        fragments = []

        # Collect all include fragments
        for label, pattern in self.config.import_patterns.items():
            if not isinstance(pattern, re.Pattern):
                # safety: compile if it isn't
                try:
                    pattern = re.compile(pattern, re.MULTILINE | re.VERBOSE)
                except re.error as e:
                    Log.warning(f"Invalid import pattern '{label}': {e}")
                    continue

            # also match escaped form like {{&gt; ...}}
            alt_pattern = re.compile(pattern.pattern.replace(r"\>\s*", r"(?:>|&gt;)\s*"), re.MULTILINE | re.VERBOSE)

            for match in alt_pattern.finditer(content):
                fragments.append({
                    "label": label,
                    "full": match.group(0),
                    "path": (match.groupdict().get("path") or "").strip(),
                    "params": (match.groupdict().get("params") or "").strip(),
                })

        # Replace each fragment with Django syntax
        for frag in fragments:
            path = frag["path"]
            params_raw = frag["params"]
            if not path:
                continue

            # Normalize path: remove ./ or ../
            clean_path = re.sub(r"^(\.\/|\.\.\/)+", "", path)
            clean_path = Path(clean_path).with_suffix("").as_posix()

            if "/" not in clean_path:
                clean_path = f"partials/{clean_path}"
            # Case 3: already under shared (rare edge)
            elif clean_path.startswith("partials/"):
                pass  # already correct

            # Skip special title includes (handled separately)
            if Path(clean_path).name.lower() in {"title-meta", "app-meta-title"}:
                content = content.replace(frag["full"], "")
                continue

            # Parse parameters safely
            params = self._parse_include_params(params_raw)
            if params:
                with_parts = " ".join([f"{k}='{v}'" for k, v in params.items()])
                replacement = f"{{% include '{clean_path}.html' with {with_parts} %}}"
            else:
                replacement = f"{{% include '{clean_path}.html' %}}"

            content = content.replace(frag["full"], replacement)

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
        Rewrites asset paths in src, href, and inline/background-image URLs
        to use Django {% static %} or {% vite_asset %} tags.
        If frontend_pipeline == "vite", replaces full <script> tags for JS assets with {% vite_asset %}.
        """
        asset_extensions = [
            'js', 'css', 'png', 'jpg', 'jpeg', 'gif', 'svg', 'ico',
            'webp', 'woff', 'woff2', 'ttf', 'eot', 'mp4', 'webm'
        ]
        extensions_pattern = '|'.join(asset_extensions)

        # Handle full <script> tags separately when using Vite
        if getattr(self.config, "frontend_pipeline", "") == "vite":
            vite_script_pattern = re.compile(
                r'<script\b[^>]*\bsrc=["\']([^"\']+\.js)["\'][^>]*>\s*</script>',
                re.IGNORECASE
            )

            def vite_script_replacer(match: re.Match) -> str:
                path = match.group(1)
                normalized_path = re.sub(r'^(?:.*\/)?assets\/', '', path).lstrip('/')
                return f"{{% vite_asset '{self.config.project_name}/static/{normalized_path}' %}}"

            html = vite_script_pattern.sub(vite_script_replacer, html)

        # Standard src/href replacement for all other assets
        attr_pattern = re.compile(
            r'\b(href|src)\s*=\s*["\']'
            r'(?!{{|#|https?://|//|mailto:|tel:)'  # exclude external URLs
            r'([^"\'#]+\.(?:' + extensions_pattern + r'))'  # asset path
                                                     r'([^"\']*)'  # query/fragment
                                                     r'["\']',
            re.IGNORECASE,
        )

        def attr_replacer(match: re.Match) -> str:
            attr = match.group(1)
            path = match.group(2)
            query_fragment = match.group(3)
            normalized_path = re.sub(r'^(?:.*\/)?assets\/', '', path).lstrip('/')
            ext = Path(normalized_path).suffix.lower().lstrip('.')

            # For vite, we already handled <script> tags above, so skip pure JS files here
            if ext == 'js' and getattr(self.config, "frontend_pipeline", "") == "vite":
                return match.group(0)  # no change (already handled)
            else:
                return f'{attr}="{{% static \'{normalized_path}\' %}}{query_fragment}"'

        html = attr_pattern.sub(attr_replacer, html)

        # Inline CSS background URLs
        inline_style_pattern = re.compile(
            r'url\(\s*[\'"]?(?!{{|#|https?://|//|mailto:|tel:)([^\'")]+)\s*[\'"]?\)',
            re.IGNORECASE,
        )

        def style_replacer(match: re.Match) -> str:
            path = match.group(1)
            normalized_path = re.sub(r'^(?:.*\/)?assets\/', '', path).lstrip('/')
            ext = Path(normalized_path).suffix.lower().lstrip('.')
            return f"url({{% static '{normalized_path}' %}})"

        html = inline_style_pattern.sub(style_replacer, html)

        return html

    def _replace_html_links_with_django_urls(self, html_content):
        """
        Replaces direct .html links in anchor tags (<a>) with Django {% url %} tags.
        Handles 'index.html' specifically to map to the root URL '/'.
        """
        # Regex to find href attributes in <a> tags that end with .html
        pattern = r'(<a\s+[^>]*?href\s*=\s*["\'])([^"\'#]+\.html)(["\'][^>]*?>)'

        def replacer(match):
            pre_path = match.group(1)  # e.g., <a ... href="
            file_path_full = match.group(2)  # e.g., dashboard-clinic.html or ../folder/page.html
            post_path = match.group(3)  # e.g., " ... >

            # Extract the base filename without extension
            # Path() handles relative paths and extracts the clean stem (filename without extension)
            template_name = Path(file_path_full).stem

            # Special case for 'index.html'
            if template_name == 'index':
                django_url_tag = "/"
            else:
                # Construct the new Django URL tag for other pages
                django_url_tag = f"{{% url 'pages:dynamic_pages' template_name='{template_name}' %}}"

            # Reconstruct the anchor tag with the new href
            return f"{pre_path}{django_url_tag}{post_path}"

        return re.sub(pattern, replacer, html_content)


class DjangoGulpConverter(BaseDjangoConverter):
    def __init__(self, config: ProjectConfig):
        super().__init__(config)

    def create_project(self):
        Log.project_start(self.config.project_name)

        self.init_create_project()

        has_plugins_config(self.config)
        replace_asset_paths(self.config.project_assets_path, '/static')

        Log.project_end(self.config.project_name, str(self.config.project_root_path))


class DjangoViteConverter(BaseDjangoConverter):
    def __init__(self, config: ProjectConfig):
        super().__init__(config)

    def create_project(self):
        Log.project_start(self.config.project_name)

        self.init_create_project()

        Log.project_end(self.config.project_name, str(self.config.project_root_path))


class DjangoConverter:
    def __init__(self, config: ProjectConfig):
        self.config = config

        if self.config.frontend_pipeline == "gulp":
            DjangoGulpConverter(self.config).create_project()
        else:
            DjangoViteConverter(self.config).create_project()
