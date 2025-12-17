import os
import re
import ast
import html
import json
from pathlib import Path
from typing import Dict, List, Tuple

from cookiecutter.main import cookiecutter
from bs4 import BeautifulSoup, NavigableString

from transpilex.config.base import SPRING_COOKIECUTTER_REPO, RESERVE_KEYWORDS
from transpilex.config.project import ProjectConfig
from transpilex.utils.assets import copy_assets, replace_asset_paths
from transpilex.utils.casing import apply_casing
from transpilex.utils.file import file_exists, copy_items, move_files
from transpilex.utils.gulpfile import has_plugins_config
from transpilex.utils.logs import Log
from transpilex.utils.package_json import sync_package_json
from transpilex.utils.restructure import restructure_and_copy_files


class BaseSpringConverter:
    def __init__(self, config: ProjectConfig):
        self.config = config
        self.project_templates_path = Path(self.config.project_root_path / "src/main/resources/templates")

        self.project_java_path = self.config.project_root_path / "src/main/java"
        self.project_controllers_path = self.project_java_path / "com/example" / self.config.project_name / "controller"

        self.route_map = None

    def init_create_project(self):
        try:
            has_plugins_file = False

            if file_exists(self.config.src_path / "plugins.config.js"):
                has_plugins_file = True

            cookiecutter(
                SPRING_COOKIECUTTER_REPO,
                output_dir=str(self.config.project_root_path.parent),
                no_input=True,
                extra_context={'name': self.config.project_name,
                               'ui_library': self.config.ui_library.title(),
                               'frontend_pipeline': self.config.frontend_pipeline.title(),
                               'has_plugins_config': 'y' if has_plugins_file and self.config.frontend_pipeline == 'gulp' else 'n'
                               },
            )

            Log.success("Spring Boot project created successfully")
        except:
            Log.error("Spring Boot project creation failed")
            return

        self.route_map = restructure_and_copy_files(
            self.config,
            self.project_templates_path,
            self.config.file_extension
        )

        self._convert()

        self._create_controllers(ignore_list=["shared"])

        if self.config.partials_path:
            move_files(Path(self.project_templates_path / "partials"), self.config.project_partials_path)
            self._replace_variables(self.config.project_partials_path, self.config.variable_patterns,
                                    self.config.file_extension)

        if self.config.asset_paths:
            copy_assets(self.config.asset_paths, self.config.project_assets_path)
            copy_items(Path(self.config.src_path / "public"), self.config.project_assets_path, copy_mode="contents")

        sync_package_json(self.config, ignore=["scripts", "type", "devDependencies"])

        copy_items(Path(self.config.src_path / "package-lock.json"), self.config.project_root_path)

    def _convert(self):
        """Processes templates: partials get fragment wrappers; pages get layout decoration."""
        count = 0
        all_files = list(self.project_templates_path.rglob(f"*{self.config.file_extension}"))

        for file in all_files:
            if not file.is_file() or "shared" in file.parts:
                continue

            is_partial = "partials" in file.parts
            try:
                if is_partial:
                    self._process_partial_file(file)
                else:
                    self._process_page_file(file)
                count += 1
            except Exception as e:
                Log.warning(f"Failed converting {file}: {e}")
        Log.info(f"{count} files converted in {self.project_templates_path}")

    def _protect_handlebars(self, src: str):
        """
        Replace {{ ... }} / Handlebars blocks with placeholders, returning (protected_text, map)
        """
        placeholder_map = {}

        def _repl(m):
            key = f"__HB_{len(placeholder_map)}__"
            placeholder_map[key] = m.group(0)
            return key

        protected = re.sub(r"\{\{[^\{\}]+\}\}", _repl, src)
        return protected, placeholder_map

    def _restore_placeholders(self, text: str, placeholder_map: Dict[str, str]):
        for k, v in placeholder_map.items():
            text = text.replace(k, v)
        return text

    def _parse_include_params(self, raw: str):
        """
        Parse JSON, PHP array(...), Blade-style ['k'=>'v'], or kv pairs key="value"
        Returns dict.
        """
        if not raw:
            return {}

        raw = html.unescape(raw.strip())

        # JSON-style object
        if raw.startswith("{") and raw.endswith("}"):
            try:
                cleaned = re.sub(r"([\{\s,])\s*([a-zA-Z_][\w-]*)\s*:", r'\1"\2":', raw)
                cleaned = re.sub(r",\s*([\}\]])", r"\1", cleaned)
                return json.loads(cleaned)
            except json.JSONDecodeError:
                Log.warning("JSON parse failed for include params; falling back to other parsers.")

        # PHP array(...) -> delegate
        m_arr = re.search(r"array\s*\(([\s\S]*)\)", raw)
        if m_arr:
            return self._extract_php_array_params(f"array({m_arr.group(1)})")

        # Blade ['k' => 'v'] style
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
                    parsed[k] = (b == "true")
                elif n:
                    parsed[k] = float(n) if "." in n else int(n)
            return parsed

        # simple key="value" pairs
        kv_pairs = re.findall(r"(\w+)=[\"']([^\"']+)[\"']", raw)
        if kv_pairs:
            return {k: v for k, v in kv_pairs}

        # fallback: attempt ast.literal_eval after replacements (true/false/null)
        try:
            eval_str = raw.replace('true', 'True').replace('false', 'False').replace('null', 'None')
            return dict(ast.literal_eval(eval_str))
        except Exception:
            Log.warning(f"Unable to parse include params: {raw[:80]}")
            return {}

    def _extract_php_array_params(self, include_str: str):
        m = re.search(r"array\s*\(([\s\S]*)\)", include_str)
        if not m:
            return {}
        body = m.group(1)
        pattern = re.compile(r"""
                (?:['"](?P<key>[^'"]+)['"]\s*=>\s*)?
                (?:
                    ['"](?P<sval>(?:\\.|[^'"])*)['"] |
                    (?P<nval>-?\d+(?:\.\d+)?) |
                    (?P<bool>true|false)
                )
                \s*(?:,\s*|$)
            """, re.VERBOSE | re.DOTALL)
        result = {}
        for match in pattern.finditer(body):
            key = match.group("key")
            if not key:
                continue
            if match.group("sval") is not None:
                result[key] = match.group("sval")
            elif match.group("nval"):
                n = match.group("nval")
                result[key] = float(n) if "." in n else int(n)
            elif match.group("bool"):
                result[key] = match.group("bool") == "true"
        return result

    def _replace_all_includes_with_thymeleaf(self, content: str):
        """
        Convert all include syntaxes matched by self.config.import_patterns into
        Thymeleaf th:replace fragment usage.
        Example: @@include('./partials/page-title', {title: 'X'})
                 -> <th:block th:replace="~{partials/page-title :: page-title(title='X')}"/>
        Also handles Handlebars: {{> partial }} and escaped {{&gt; partial }}
        """
        # Build list of matches first to avoid interfering replacements
        fragments = []
        for label, pattern in self.config.import_patterns.items():
            # allow escaped > like &gt;
            alt_pat = re.compile(pattern.pattern.replace(r"\>\s*", r"(?:>|&gt;)\s*"))
            for m in alt_pat.finditer(content):
                fragments.append({
                    "label": label,
                    "full": m.group(0),
                    "path": m.group("path"),
                    "params": m.groupdict().get("params", "") or ""
                })

        for frag in fragments:
            raw_path = frag["path"]
            params_raw = frag["params"]

            clean_path = re.sub(r"^(\.\/|\.\.\/)+", "", raw_path).replace(".html", "")
            clean_path = Path(clean_path).as_posix()

            # ensure partials prefix
            if not "/" in clean_path and not clean_path.startswith("partials"):
                clean_path = f"shared/partials/{clean_path}"
            elif clean_path.startswith("partials/"):
                clean_path = f"shared/{clean_path}"
            elif clean_path.startswith("shared/partials/"):
                clean_path = clean_path  # keep shared path as-is

            fragment_name = Path(clean_path).name

            # skip title-meta includes (consumed elsewhere)
            if fragment_name.lower() in {"title-meta", "app-meta-title"}:
                content = content.replace(frag["full"], "")
                continue

            params = self._parse_include_params(params_raw)
            if params:
                # format into Thymeleaf params (key='value', key2=123)
                pairs = []
                for k, v in params.items():
                    if isinstance(v, str):
                        escaped = v.replace("'", "\\'")
                        pairs.append(f"{k}='{escaped}'")
                    elif isinstance(v, bool):
                        pairs.append(f"{k}={'true' if v else 'false'}")
                    elif v is None:
                        pairs.append(f"{k}=null")
                    else:
                        pairs.append(f"{k}={v}")
                param_str = ", ".join(pairs)
                replacement = f'<th:block th:replace="~{{{clean_path} :: {fragment_name}({param_str})}}"></th:block>'
            else:
                replacement = f'<th:block th:replace="~{{{clean_path} :: {fragment_name}}}"></th:block>'

            content = content.replace(frag["full"], replacement)

        return content

    def _replace_anchor_links_with_routes(self, content: str, route_map: Dict[str, str]):
        """
        Replace <a href="file.html"> with Thymeleaf-friendly th:href="@{/path}" using route_map.
        Uses th:href to play nicely with Thymeleaf; for index -> @{/}
        Leaves absolute/external links untouched.
        """
        pattern = re.compile(r'href=(["\'])(?P<href>[^"\']+\.html)\1', re.IGNORECASE)

        def repl(m):
            href = m.group("href")
            href_file = Path(href).name
            if href_file in route_map:
                route_path = route_map[href_file]
                if route_path == "/index":
                    return 'th:href="@{/}"'
                # ensure route_path begins with /
                if not route_path.startswith("/"):
                    route_path = "/" + route_path
                return f'th:href="@{{{route_path}}}"'
            # otherwise keep original attribute but convert to th:href if local
            if not href.lower().startswith(("http://", "https://", "//")):
                clean = "/" + href.lstrip("./")
                return f'th:href="@{{{clean}}}"'
            return m.group(0)

        return pattern.sub(repl, content)

    def _replace_asset_paths_for_thymeleaf(self, content: str) -> str:
        """
        Converts:
          - inline styles: style="background:url('../assets/...')"
                -> th:style="|background:url('@{/...}')|"
          - CSS url(...) inside <style> blocks
          - <img>, <link>, <a>, <script> if not already handled
        """

        soup = BeautifulSoup(content, "html.parser")

        def normalize_asset(val: str) -> str | None:
            """Return cleaned path without 'assets/' prefix."""
            if not val:
                return None
            if re.match(r'^(https?:)?//', val) or val.startswith(("data:", "mailto:", "tel:")):
                return None
            m = re.match(r'^(?:\./|\.\./)*assets/(.+)$', val)
            return m.group(1).lstrip('/') if m else None

        for tag in soup.find_all(style=True):
            style_val = tag.get("style")
            if not style_val:
                continue

            # Find url(...) inside style attribute
            urls = re.findall(r'url\((["\']?)(.+?)\1\)', style_val, flags=re.IGNORECASE)
            if not urls:
                continue

            new_style = style_val

            for quote, url_val in urls:
                cleaned = normalize_asset(url_val)
                if cleaned:
                    thymeleaf_url = f"@{{/{cleaned}}}"
                    new_style = new_style.replace(url_val, thymeleaf_url)

            # Rewrite to proper th:style (Thymeleaf processing syntax)
            tag.attrs.pop("style", None)
            tag.attrs["th:style"] = f"|{new_style}|"

        for style_tag in soup.find_all("style"):
            css_text = style_tag.string or ""
            urls = re.findall(r'url\((["\']?)(.+?)\1\)', css_text)
            new_css = css_text
            for quote, url_val in urls:
                cleaned = normalize_asset(url_val)
                if cleaned:
                    new_css = new_css.replace(url_val, f"@{{/{cleaned}}}")
            style_tag.string = new_css

        # Only convert here if they still contain assets/ (backup safety)
        for tag in soup.find_all(["img", "link", "script", "a"]):
            for attr in ["src", "href"]:
                if not tag.has_attr(attr):
                    continue

                val = tag[attr]
                cleaned = normalize_asset(val)
                if cleaned:
                    # remove original attribute
                    tag.attrs.pop(attr, None)

                    # assign Thymeleaf attribute
                    thyme_attr = "th:src" if attr == "src" else "th:href"
                    tag.attrs[thyme_attr] = f"@{{/{cleaned}}}"

        out = str(soup)
        return out

    def _extract_html_data_attributes(self, html_content: str) -> str:
        """
        Extracts data- attributes from the source <html> tag and returns them as a string.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        html_tag = soup.find("html")
        if not html_tag:
            return ""

        # Filter for data- attributes only
        attrs = [f'{k}="{v}"' for k, v in html_tag.attrs.items() if k.startswith("data-")]

        if not attrs:
            return ""

        return " ".join(attrs)

    def _process_page_file(self, file_path: Path):
        with open(file_path, "r", encoding="utf-8") as f:
            original = f.read()

        # protect handlebars/templating placeholders while manipulating DOM
        protected, placeholder_map = self._protect_handlebars(original)

        title_scan_source = original.replace("&gt;", ">")

        # detect title/meta includes using config.import_patterns
        layout_title = ""

        for label, pattern in self.config.import_patterns.items():
            # allow escaped > like &gt; and flexible spacing after >
            try:
                # This replacement makes the regex robust against HTML entities
                alt_re = pattern.pattern.replace(r"\>\s*", r"(?:>|&gt;)\s*")
                alt_pattern = re.compile(alt_re, flags=re.IGNORECASE | re.DOTALL)
            except Exception:
                # fallback generic pattern
                alt_pattern = re.compile(r'\{\{\s*>\s*(?P<path>[^}\s]+)(?:\s*,?\s*(?P<params>\{[\s\S]*?\}))?\s*\}\}',
                                         flags=re.IGNORECASE | re.DOTALL)

            m = alt_pattern.search(title_scan_source)
            if not m:
                continue

            # Extract path
            path_val = None
            if "path" in m.groupdict() and m.group("path"):
                path_val = m.group("path")
            else:
                try:
                    path_val = m.group(1)
                except IndexError:
                    path_val = None

            if not path_val:
                continue

            inc_name = Path(path_val).stem.lower()

            # Extract params
            params_raw = ""
            if "params" in m.groupdict() and m.group("params"):
                params_raw = m.group("params")
            else:
                try:
                    params_raw = m.group(2) or ""
                except IndexError:
                    params_raw = ""

            # parse params
            params_raw = (params_raw or "").strip()
            try:
                parsed = self._parse_include_params(params_raw)
            except Exception:
                parsed = {}

            if inc_name in {"title-meta", "app-meta-title"}:
                layout_title = parsed.get("title") or parsed.get("pageTitle") or layout_title
                if layout_title:
                    break

        escaped_title = layout_title.replace("'", "\\'")

        # parse DOM
        soup = BeautifulSoup(protected, "html.parser")

        # remove and collect link tags
        styles = []
        for tag in list(soup.find_all("link")):
            href = tag.get("href")

            if href and not href.startswith(("http", "//")):
                normalized = re.sub(r"^(?:\./|\.\./)+", "", href)

                # REMOVE assets/ prefix
                if normalized.startswith("assets/"):
                    cleaned = normalized[len("assets/"):]
                    styles.append(f'<link th:href="@{{/{cleaned}}}" rel="stylesheet" type="text/css"/>')
                else:
                    cleaned = normalized.lstrip("/")
                    styles.append(f'<link th:href="@{{/{cleaned}}}" rel="stylesheet" type="text/css"/>')
            else:
                styles.append(str(tag))

            tag.decompose()

        # collect scripts (local ones will be left as-is or transformed)
        scripts = []
        for tag in list(soup.find_all("script")):
            src = tag.get("src")

            if src and not src.startswith(("http", "//")):
                # normalized path without ./ or ../
                normalized = re.sub(r"^(?:\./|\.\./)+", "", src)

                # REMOVE assets/ prefix if it exists
                if normalized.startswith("assets/"):
                    cleaned = normalized[len("assets/"):]
                    scripts.append(f'<script th:src="@{{/{cleaned}}}"></script>')
                else:
                    # normal local script
                    cleaned = normalized.lstrip("/")
                    scripts.append(f'<script th:src="@{{/{cleaned}}}"></script>')
            else:
                scripts.append(str(tag))

            tag.decompose()

        # find main content
        content_div = soup.find(attrs={"data-content": True})
        if content_div:
            body_html = content_div.decode_contents()
            layout_target = f"shared/vertical(title=${{'{escaped_title}'}})"
        elif soup.body:
            body_html = soup.body.decode_contents()
            layout_target = f"shared/base(title=${{'{escaped_title}'}})"
        else:
            body_html = str(soup)
            layout_target = f"shared/base(title=${{'{escaped_title}'}})"

        # restore placeholders inside body_html
        body_html = self._restore_placeholders(body_html, placeholder_map)

        # replace includes with Thymeleaf
        main_content = self._replace_all_includes_with_thymeleaf(body_html).strip()

        html_attrs = self._extract_html_data_attributes(original)

        if html_attrs:
            html_attrs = f"{html_attrs}"

        decorate_line = f'<html xmlns:layout="http://www.ultraq.net.nz/thymeleaf/layout" layout:decorate="~{{{layout_target}}}" {html_attrs}>'

        # restore any leftover handlebars placeholders inside main_content
        main_content = self._replace_asset_paths_for_thymeleaf(main_content)
        main_content = self._replace_anchor_links_with_routes(main_content, self.route_map)

        # restore placeholders (in case some included fragments had them)
        main_content = self._restore_placeholders(main_content, placeholder_map)

        styles = [self._replace_asset_paths_for_thymeleaf(s) for s in styles]
        scripts = [self._replace_asset_paths_for_thymeleaf(s) for s in scripts]

        thymeleaf_output = f"""{decorate_line}

<th:block layout:fragment="styles">
{'\n'.join(styles)}
</th:block>

<th:block layout:fragment="content">
{main_content}
</th:block>

<th:block layout:fragment="scripts">
{'\n'.join(scripts)}
</th:block>

</html>
"""
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(thymeleaf_output.strip() + "\n")

        # Log.converted(str(file_path))

    def _process_partial_file(self, file_path: Path):
        with open(file_path, "r", encoding="utf-8") as f:
            original = f.read()

        protected, placeholder_map = self._protect_handlebars(original)

        # clean asset paths
        protected = self._replace_asset_paths_for_thymeleaf(protected)

        # convert includes in partials too
        content = self._replace_all_includes_with_thymeleaf(protected)

        # parse to process hrefs and other local attributes
        soup = BeautifulSoup(content, "html.parser")
        # update anchors inside partial to route-style
        for a in soup.find_all("a"):
            href = a.get("href")
            if href and href.endswith(".html"):
                replaced = self._replace_anchor_links_with_routes(f'href="{href}"', self.route_map)
                # replaced contains th:href attr — convert into actual attribute on tag
                m = re.search(r'(th:href=.+)$', replaced)
                if m:
                    a.attrs.pop("href", None)
                    # BeautifulSoup requires attribute assignment as string (strip outer quotes)
                    # remove surrounding quotes from m.group
                    attr_val = replaced.split("=", 1)[1].strip()
                    # attr_val includes surrounding quotes; remove them
                    a.attrs["th:href"] = attr_val.strip().strip('"').strip("'")

        processed_content = self._restore_placeholders(str(soup), placeholder_map)

        fragment_name = file_path.stem.lstrip('_')
        final_output = f"""<!DOCTYPE html>
<html xmlns:th="http://www.thymeleaf.org">
<th:block th:fragment="{fragment_name}">
{processed_content}
</th:block>
</html>"""

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(final_output.strip() + "\n")
        # Log.converted(str(file_path))

    def _sanitize_action_name(self, controller_name: str, action_name: str) -> str:
        """
        Ensures the generated Java method name is valid.
        Prefixes method when:
        - it starts with a number
        - it is a Java reserved keyword
        """
        sanitized = action_name

        # Replace illegal characters
        sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', sanitized)

        # If starts with number → prefix controller name
        if re.match(r'^\d', sanitized):
            sanitized = f"{controller_name}_{sanitized}"

        # If reserved keyword → prefix controller name
        if sanitized in RESERVE_KEYWORDS:
            sanitized = f"{controller_name}_{sanitized}"

        return sanitized

    def _create_controller_file(self, path: Path, controller_name: str, actions: List[Tuple[str, str]]):
        class_name = controller_name[0].upper() + controller_name[1:]
        request_mapping = controller_name.lower()
        methods = []
        for action_name, template_path in actions:
            safe_name = self._sanitize_action_name(controller_name, action_name)
            method_name = apply_casing(safe_name, "camel")
            get_mapping = action_name.replace('_', '/')
            if get_mapping == 'index':
                mapping_path = ""
            else:
                mapping_path = f"/{get_mapping}"
            methods.append(f"""
@GetMapping("{mapping_path}")
public String {method_name}() {{
    return "{template_path}";
}}
    """)
        methods_block = "\n".join(methods)

        package_name = str(self.project_controllers_path.relative_to(self.project_java_path)).replace(os.sep, '.')
        controller_code = f"""package {package_name};

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@Controller
@RequestMapping("/{request_mapping}")
public class {class_name} {{
{methods_block}
}}
    """
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(controller_code)
        Log.created(str(path))

    def _create_controllers(self, ignore_list=None):
        ignore_list = ignore_list or []

        for controller_name in os.listdir(self.project_templates_path):
            if controller_name in ignore_list:
                continue
            controller_folder_path = self.project_templates_path / controller_name
            if not controller_folder_path.is_dir():
                continue

            actions = []
            for root, _, files in os.walk(controller_folder_path):
                for file in files:
                    if file.endswith(self.config.file_extension) and not file.startswith("_"):
                        full_path = Path(root) / file
                        rel_path = full_path.relative_to(self.project_templates_path)
                        template_path = str(rel_path.with_suffix('')).replace(os.sep, '/')
                        action_name = str(full_path.relative_to(controller_folder_path).with_suffix('')).replace(
                            os.sep, '_')
                        actions.append((action_name, template_path))
            if actions:
                controller_file_name = f"{controller_name.capitalize()}.java"
                controller_file_path = self.project_controllers_path / controller_file_name
                self._create_controller_file(controller_file_path, controller_name, actions)
        Log.info("Controller generation completed")

    def _replace_variables(self, folder_path: Path, variable_patterns: dict,
                           file_extension: str):
        """
        Replace @@var and {{ var }} with attribute-based Thymeleaf variables.
        Rules:
          - If an element's textual content is exactly the token -> set th:text="${var}" and remove inner text.
          - If token is mixed with other text -> set th:text to a concatenation expression: e.g. "${title} + ' | Dhonu'".
          - If token appears inside an attribute (including existing th:text="${@@title}"), sanitize to remove the @@/{{ }}.
          - Do NOT add spans or alter tag structure.
          - Does not set th:text on <html> element.
        Parameters are kept same as original signature for drop-in compatibility.
        """
        import html as _html
        folder = Path(folder_path).resolve()
        file_extension = file_extension if file_extension.startswith('.') else f'.{file_extension}'

        # Build a simple var detection regex. Expect variable_patterns keys matching earlier structure.
        # variable_patterns example given earlier:
        # { "@@": "@@(?!if\\b|include\\b)([A-Za-z_]\\w*)\\b", "{{>": "\\{\\{\\s*([a-zA-Z_][a-zA-Z0-9_]*)\\s*\\}\\}" }
        pattern_at = re.compile(variable_patterns.get("@@", r"@@([A-Za-z_]\w*)\b"))
        pattern_mustache = re.compile(variable_patterns.get("{{>", r"\{\{\s*([A-Za-z_]\w*)\s*\}\}"))

        def find_var_in_text(s: str):
            """Return (match_obj, varname) for first occurrence among patterns, or (None, None)."""
            m = pattern_at.search(s)
            if m:
                return m, m.group(1)
            m2 = pattern_mustache.search(s)
            if m2:
                return m2, m2.group(1)
            return None, None

        files_changed = 0

        for file in folder.rglob(f"*{file_extension}"):
            if not file.is_file():
                continue
            try:
                raw = file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            soup = BeautifulSoup(raw, "html.parser")
            modified = False

            # 1) Sanitize attributes first (so we fix th:text="${@@title}" -> th:text="${title}" etc.)
            for tag in soup.find_all(True):
                # skip script/style attributes
                if tag.name in ("script", "style"):
                    continue
                for attr, val in list(tag.attrs.items()):
                    # BeautifulSoup may give list for some attrs (class). Skip non-string attrs.
                    if isinstance(val, (list, tuple)):
                        continue
                    if not isinstance(val, str) or not val:
                        continue

                    # Replace @@var and {{ var }} inside attribute values.
                    # Patterns could appear inside ${...} or alone.
                    # Replace occurrences like @@title -> title (when inside ${...} we'll keep ${title} later),
                    # and {{title}} -> title
                    new_val = val
                    # replace @@name
                    new_val = pattern_at.sub(r"\1", new_val)
                    # replace {{ name }}
                    new_val = pattern_mustache.sub(r"\1", new_val)

                    if new_val != val:
                        tag.attrs[attr] = new_val
                        modified = True

            # 2) Handle textual content nodes.
            # Iterate over all text nodes (NavigableString) but skip script/style content.
            for text_node in list(soup.find_all(string=True)):
                parent = text_node.parent
                if parent is None:
                    continue
                if parent.name in ("script", "style"):
                    continue

                text = str(text_node)
                if not text or not text.strip():
                    continue

                m, varname = find_var_in_text(text)
                if not m:
                    continue

                # Determine the element we should modify: the immediate parent element is best.
                # Avoid setting th:text on the <html> element itself
                target = parent
                if target.name == "html":
                    # skip modifying html root; leave variable untouched (unlikely)
                    continue

                # Compute expression:
                token = m.group(0)
                pre = text[:m.start()].strip()
                post = text[m.end():].strip()

                # If the parent's children include other elements, we still replace the parent's inner content.
                # This is safe for anchors (<a>@@subtitle</a>) and similar inline elements.
                if pre == "" and post == "":
                    # content is exactly variable -> set th:text="${var}" and remove children/text
                    target.attrs["th:text"] = f"${{{varname}}}"
                    # remove all children/text
                    for child in list(target.contents):
                        child.extract()
                    modified = True
                else:
                    # Mixed content -> create concatenation expression.
                    # Build parts: prefix (literal), variable, suffix (literal). Preserve spacing sensibly.
                    parts = []
                    if pre:
                        # escape single quotes inside prefix
                        p = _html.escape(pre)
                        p = p.replace("'", "\\'")
                        parts.append(f"'{pre}'")
                    parts.append(f"${{{varname}}}")
                    if post:
                        q = _html.escape(post)
                        q = q.replace("'", "\\'")
                        parts.append(f"'{post}'")
                    expr = " + ".join(parts)
                    target.attrs["th:text"] = expr
                    # remove all children/text of the target element since th:text will replace them
                    for child in list(target.contents):
                        child.extract()
                    modified = True

            # After processing, write only if changed.
            if modified:
                # Preserve file encoding and newlines by writing UTF-8 text
                file.write_text(str(soup), encoding="utf-8")
                files_changed += 1

        if files_changed:
            Log.info(f"{files_changed} Thymeleaf variable replacements in {folder_path}")


class SpringGulpConverter(BaseSpringConverter):
    def __init__(self, config: ProjectConfig):
        super().__init__(config)

    def create_project(self):
        Log.project_start(self.config.project_name)

        self.init_create_project()

        has_plugins_config(self.config)
        replace_asset_paths(self.config.project_assets_path, '')

        Log.project_end(self.config.project_name, str(self.config.project_root_path))


class SpringViteConverter(BaseSpringConverter):
    def __init__(self, config: ProjectConfig):
        super().__init__(config)

    def create_project(self):
        Log.project_start(self.config.project_name)

        self.init_create_project()

        Log.project_end(self.config.project_name, str(self.config.project_root_path))


class SpringConverter:
    def __init__(self, config: ProjectConfig):
        self.config = config

        if self.config.frontend_pipeline == "gulp":
            SpringGulpConverter(self.config).create_project()
        else:
            SpringViteConverter(self.config).create_project()
