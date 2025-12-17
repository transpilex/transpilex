import re
import os
import json
import html
from pathlib import Path
from bs4 import BeautifulSoup
from cookiecutter.main import cookiecutter

from transpilex.config.base import MVC_COOKIECUTTER_REPO
from transpilex.config.project import ProjectConfig
from transpilex.utils.assets import clean_relative_asset_paths, copy_public_only_assets, copy_assets, \
    replace_asset_paths
from transpilex.utils.casing import apply_casing
from transpilex.utils.file import move_files, copy_items, file_exists
from transpilex.utils.gulpfile import add_gulpfile
from transpilex.utils.logs import Log
from transpilex.utils.package_json import update_package_json, sync_package_json
from transpilex.utils.replace_variables import replace_variables
from transpilex.utils.restructure import restructure_and_copy_files
from transpilex.utils.template import replace_file_with_template


class BaseMVCConverter:
    def __init__(self, config: ProjectConfig):
        self.config = config
        self.project_name = self.config.project_name.title()
        self.project_views_path = Path(self.config.project_root_path / "Views")
        self.project_shared_path = Path(self.project_views_path / "Shared")
        self.project_partials_path = Path(self.project_shared_path / "Partials")
        self.project_public_path = Path(self.config.project_root_path / "wwwroot")
        self.project_controllers_path = Path(self.config.project_root_path / "Controllers")
        self.project_index_controller_path = Path(self.project_controllers_path / "IndexController.cs")
        self.project_view_import_path = Path(self.project_views_path / "_ViewImports.cshtml")
        self.project_model_path = Path(self.config.project_root_path / "Models" / "ErrorViewModel.cs")

        self.route_map = None

    def init_create_project(self):
        try:
            has_plugins_file = False

            if file_exists(self.config.src_path / "plugins.config.js"):
                has_plugins_file = True

            cookiecutter(
                MVC_COOKIECUTTER_REPO,
                output_dir=str(self.config.project_root_path.parent),
                no_input=True,
                extra_context={'name': self.config.project_name,
                               'ui_library': self.config.ui_library.title(),
                               'frontend_pipeline': self.config.frontend_pipeline.title(),
                               'has_plugins_config': 'y' if has_plugins_file and self.config.frontend_pipeline == 'gulp' else 'n'
                               },
            )

            Log.success("MVC project created successfully")
        except:
            Log.error("MVC project creation failed")
            return

        self.route_map = restructure_and_copy_files(
            self.config,
            self.project_views_path,
            self.config.file_extension,
            case_style="pascal"
        )

        self._create_controllers(ignore_list=['Shared', '_ViewImports.cshtml', '_ViewStart.cshtml', 'Index.cshtml'])

        self._convert()

        if self.config.partials_path:
            move_files(self.project_views_path / "Partials", self.project_partials_path)
            self._normalize_partials_folder()
            replace_variables(self.project_shared_path, self.config.variable_patterns,
                              self.config.variable_replacement, self.config.file_extension)
            self._add_viewbag_vars_block()

    def _convert(self):
        count = 0

        for file in self.project_views_path.rglob(f"*{self.config.file_extension}"):
            if not file.is_file() or file.name.startswith("_"):
                continue

            try:
                original_content = file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            includes_result = self._replace_all_includes_with_razor(original_content)
            original_content = includes_result["content"]
            viewbag_blocks = includes_result["viewbag_blocks"]

            html_attr_line = self._extract_data_attributes(original_content)
            if html_attr_line:
                viewbag_blocks.append(html_attr_line)

            original_content = original_content.replace("&#64;", "__AT__")

            soup = BeautifulSoup(original_content, "html.parser")

            is_partial = "Partials" in file.parts or "Shared" in file.parts
            if is_partial:
                out = str(soup)

                includes_result = self._replace_all_includes_with_razor(out)
                out = includes_result["content"]

                out = clean_relative_asset_paths(out)

                if self.config.frontend_pipeline == "vite":
                    out = self._convert_script_src_for_vite(out)

                out = self._replace_anchor_links_with_routes(out, self.route_map)
                out = out.replace("__AT__", "&#64;")
                file.write_text(out, encoding="utf-8")

                # Log.converted(f"{file}")
                count += 1
                continue

            # Extract linked resources
            links_html = "\n".join(f"    {str(tag)}" for tag in soup.find_all("link"))
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

            # Extract main content region
            content_block = soup.find(attrs={"data-content": True})
            layout_target = ''

            if content_block:
                body_html = content_block.decode_contents()
                layout_target = f'    Layout = "~/Pages/Shared/_VerticalLayout.cshtml";\n'
            elif soup.body:
                body_html = soup.body.decode_contents()
                # layout_target = f'    Layout = "~/Pages/Shared/_BaseLayout.cshtml";\n'
            else:
                body_html = str(soup)
                # layout_target = f'    Layout = "~/Pages/Shared/_BaseLayout.cshtml";\n'

            viewbag_blocks.append(layout_target)

            # Clean asset paths
            body_html = clean_relative_asset_paths(body_html)

            # Combine all unique ViewBag blocks under @model
            viewbag_block = "@{\n" + "\n".join(viewbag_blocks) + "\n}".strip()
            viewbag_section = f"\n{viewbag_block}\n" if viewbag_block else ""

            final = f"""
{viewbag_section}

@section Styles {{
{links_html}
}}

{body_html}

@section Scripts {{
{scripts_html}
}}"""

            final = self._replace_anchor_links_with_routes(final, self.route_map)
            final = clean_relative_asset_paths(final)

            if self.config.frontend_pipeline == "vite":
                final = self._convert_script_src_for_vite(final)

            final = final.replace("__AT__", "&#64;")
            file.write_text(final.strip() + "\n", encoding="utf-8")
            # Log.converted(str(file))
            count += 1

        Log.info(f"{count} files converted in {self.project_views_path}")

    def _replace_all_includes_with_razor(self, content: str):
        """
        Convert @@include(...) and {{> ...}} to Razor partial syntax with ViewBag params.
        Uses patterns from import_patterns.json via load_compiled_patterns().
        """

        fragments = []

        # --- Collect all @@include(...) and {{> ...}} fragments
        for label, pattern in self.config.import_patterns.items():
            alt_pattern = re.compile(pattern.pattern.replace(r"\>\s*", r"(?:>|&gt;)\s*"))
            for match in alt_pattern.finditer(content):
                fragments.append({
                    "full": match.group(0),
                    "path": match.group("path"),
                    "params": match.groupdict().get("params", "")
                })

        if not fragments:
            return {"content": content, "viewbag_blocks": []}

        # Helper: Parse inline params
        def _parse_params(raw: str) -> dict:
            """Parse parameters from JSON-like or key=value formats."""
            if not raw:
                return {}

            s = html.unescape(raw.strip())

            # JSON-like object: { title: "Dashboard" }
            if s.startswith("{") and s.endswith("}"):
                s = re.sub(r"(?<!\\)\'", '"', s)  # single to double quotes
                s = re.sub(r"([\{\s,])\s*([A-Za-z_][\w-]*)\s*:", r'\1"\2":', s)
                s = re.sub(r",\s*([\}\]])", r"\1", s)
                try:
                    return json.loads(s)
                except json.JSONDecodeError:
                    return {}

            # key="value" pairs (Handlebars-style)
            kv_pairs = re.findall(r'([A-Za-z_][\w-]*)\s*=\s*["\']([^"\']+)["\']', s)
            return {k: v for k, v in kv_pairs}

        # Process fragments in order
        new_content = content
        viewbag_dict = {}
        found_page_title = False

        for frag in fragments:
            path = frag["path"]
            params_raw = frag["params"]

            clean_path = re.sub(r"^(\.\/|\.\.\/)+", "", path)
            clean_path = Path(clean_path).with_suffix("").as_posix()

            # Normalize to /Views/Shared/Partials/
            if clean_path.startswith("partials/"):
                clean_path = clean_path.replace("partials/", "Views/Shared/Partials/", 1)
            elif "/" not in clean_path:
                clean_path = f"Views/Shared/Partials/{clean_path}"

            clean_path_obj = Path(clean_path)
            filename_lower = clean_path_obj.stem.lower()

            # PascalCase partial filename with underscore
            pascal_filename = "_" + apply_casing(clean_path_obj.stem, "pascal") + clean_path_obj.suffix
            clean_path = str(clean_path_obj.parent / pascal_filename).replace("\\", "/")

            params = _parse_params(params_raw)

            # Priority logic
            if ("page-title" in filename_lower) or ("topbar" in filename_lower):
                found_page_title = True
            elif ("title-meta" in filename_lower) and found_page_title:
                # Remove title-meta if page-title/topbar found
                new_content = new_content.replace(frag["full"], "")
                continue

            # Update ViewBag (latest wins)
            for k, v in params.items():
                viewbag_dict[k] = v

            # Replace with Razor partial include
            replacement = f'@await Html.PartialAsync("~/{clean_path}.cshtml")'
            new_content = new_content.replace(frag["full"], replacement)

        # Build ViewBag block
        viewbag_lines = [f'    ViewBag.{k} = "{v}";' for k, v in viewbag_dict.items()]

        return {"content": new_content, "viewbag_blocks": viewbag_lines}

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
        Match the .cshtml file (Pages/UI/Buttons.cshtml) to its route_map entry
        using full relative path comparison (normalized and case-insensitive).
        """

        try:
            # Compute file path relative to Pages folder (e.g., UI/Buttons.cshtml)
            rel_path = file.relative_to(self.project_views_path)
            rel_html = str(rel_path.with_suffix(".html")).replace("\\", "/")  # UI/Buttons.html

            # Normalize both sides for consistent kebab-case comparison
            normalized_html = apply_casing(rel_html, "kebab").lower()

            # Direct match in route_map keys (exact structure)
            for html_name, route in self.route_map.items():
                html_key = apply_casing(html_name.lower(), "kebab")
                if normalized_html == html_key or normalized_html.endswith(html_key):
                    if route == "/index":
                        return "/"
                    return route

            # Partial fallback — compare by folder+stem (e.g. ui/buttons)
            kebab_parts = "/".join([apply_casing(p, "kebab").lower() for p in rel_path.with_suffix("").parts])
            for html_name, route in self.route_map.items():
                html_key = apply_casing(html_name.lower(), "kebab")
                if html_key.endswith(kebab_parts) or kebab_parts.endswith(html_key):
                    return route

            # Default fallback (no match found)
            route_guess = "/" + kebab_parts
            return route_guess

        except Exception:
            return "/"

    def _replace_anchor_links_with_routes(self, html_content: str, route_map: dict[str, str]):
        soup = BeautifulSoup(html_content, "html.parser")

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            href_clean = href.lstrip("/").lower()

            if href_clean.endswith("index.html"):
                a["href"] = "/"
                continue

            if href.startswith("#"):
                continue

            # Route lookup
            key = next(
                (k for k in route_map.keys()
                 if k.lower().strip("/").endswith(href_clean)),
                None
            )

            if not key:
                continue

            route = route_map[key].strip("/")
            parts = [p for p in route.split("/") if p]

            if len(parts) < 2:
                continue

            controller, action = parts[-2], parts[-1]

            controller = self._to_pascal(controller.split("\\")[-1])
            action = self._to_pascal(action)

            # Replace href → asp-controller/action
            del a["href"]
            a["asp-controller"] = controller
            a["asp-action"] = action

        out = str(soup)

        out = out.replace('href="/index.html"', 'href="/"')
        out = out.replace('href="index.html"', 'href="/"')

        out = out.replace('href="/#', 'href="#')
        out = out.replace('href="/javascript:void(0);', 'href="javascript:void(0);')

        return out

    def _create_controllers(self, ignore_list=None):
        """
        Recursively generates controller files for all subfolders in Views.
        - Creates a controller only if the folder directly contains .cshtml files.
        - Controller name = current folder name (e.g. EcommerceController).
        - If a file starts with a number or reserved name (like Empty), prefix the folder (e.g. Ecommerce404, EcommerceEmpty).
        - If the view is inside nested folders (like Views/Apps/Ecommerce), use absolute path: ~/Views/Apps/Ecommerce/ViewName.cshtml
        - Updates route_map last segment to match action_name.
        """

        ignore_list = set(ignore_list or [])

        for root, dirs, files in os.walk(self.project_views_path):
            if any(ig in root for ig in ignore_list):
                continue

            folder_name = os.path.basename(root)
            actions: list[tuple[str, str, str]] = []  # (action_name, view_stem, view_path)

            for file in files:
                if file in ignore_list or not file.endswith(self.config.file_extension):
                    continue

                view_stem = os.path.splitext(file)[0]
                action_name = self._make_action_name(folder_name, view_stem)

                # Relative path for View("~/Views/Apps/Ecommerce/Cart.cshtml")
                rel_path = Path(root).relative_to(self.project_views_path)
                view_full_path = f"~/Views/{rel_path.as_posix()}/{file}"

                actions.append((action_name, view_stem, view_full_path))

                # --- Update route_map ---
                if hasattr(self, "route_map") and isinstance(self.route_map, dict):
                    for key, old_route in list(self.route_map.items()):
                        route = old_route.strip("/")
                        parts = [p for p in route.split("/") if p]
                        if len(parts) >= 2 and parts[-1].lower() == view_stem.lower():
                            parts[-1] = action_name
                            self.route_map[key] = "/" + "/".join(parts)

            # Skip folders without .cshtml
            if not actions:
                continue

            controller_file_path = os.path.join(
                self.project_controllers_path, f"{folder_name}Controller.cs"
            )

            self._create_controller_file_with_views(controller_file_path, folder_name, actions)

    def _to_pascal(self, s: str):
        parts = re.split(r"[^A-Za-z0-9]+", s)
        return "".join(p[:1].upper() + p[1:] for p in parts if p)

    def _make_action_name(self, folder_name: str, file_stem: str):
        """
        Build a valid C# action name from folder + file stem.
        - If stem starts with a digit or is a reserved word (like Empty), prefix folder.
        - Sanitize to PascalCase, ensure starts with a letter.
        """
        reserved_names = {"empty", "class", "namespace", "controller", "view"}

        needs_prefix = bool(re.match(r"^\d", file_stem)) or file_stem.lower() in reserved_names
        base = f"{folder_name}{file_stem}" if needs_prefix else file_stem

        pascal = self._to_pascal(base)

        if not pascal or not pascal[0].isalpha():
            pascal = f"{self._to_pascal(folder_name)}{pascal}"

        return pascal

    def _create_controller_file_with_views(self, path: str, controller_name: str, actions: list[tuple[str, str, str]]):
        """
        actions: list of (action_name, view_stem, view_full_path)
        If nested views exist, use absolute paths (~/Views/.../ViewName.cshtml).
        """
        using_statements = "using Microsoft.AspNetCore.Mvc;"

        methods = []
        for action_name, view_stem, view_path in actions:
            # Always use absolute path to avoid MVC lookup issues for nested folders
            body = f'return View("{view_path}");'
            methods.append(
                f"""        public IActionResult {action_name}()
            {{
                {body}
            }}

    """
            )

        controller_class = f"""
namespace {self.project_name}.Controllers
{{
    public class {controller_name}Controller : Controller
    {{
{''.join(methods)}    }}
}}
        """.strip()

        with open(path, "w", encoding="utf-8") as f:
            f.write(using_statements + "\n\n" + controller_class)

    def _normalize_partials_folder(self):
        """
        In `folder`, ensure every partial:
          - has PascalCase filename,
          - starts with '_',
          - removes unprefixed duplicates when an underscored file exists.
        """

        for p in list(self.project_partials_path.rglob(f"*{self.config.file_extension}")):
            if not p.is_file():
                continue

            name = p.stem
            suffix = p.suffix

            target_name = f"_{name}{suffix}"
            target_path = p.with_name(target_name)

            # If target already exists and this is an unprefixed duplicate → delete current
            if target_path.exists() and p.resolve() != target_path.resolve():
                # Prefer the underscored PascalCase file; remove the current one
                try:
                    p.unlink()
                except Exception as e:
                    Log.error(f"Failed to delete duplicate partial {p}: {e}")
                continue

            # If current path is already the correct target, skip
            if p.name == target_name:
                continue

            # Otherwise rename to the normalized target
            try:
                p.rename(target_path)
            except FileExistsError:
                # Rare race: if created concurrently, keep the underscored PascalCase and remove this one
                try:
                    p.unlink()
                except Exception as e:
                    Log.error(f"Failed to delete duplicate partial {p}: {e}")
            except Exception as e:
                Log.error(f"Failed to normalize partial {p}: {e}")

    def _add_viewbag_vars_block(self):

        for f in self.project_partials_path.rglob(f"*{self.config.file_extension}"):
            if not f.is_file() or not f.name.startswith("_"):
                continue

            try:
                text = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            # Collect variable names used as @var
            vars_found = set(re.compile(r"(?<!@)(?<![A-Za-z0-9_])@([A-Za-z_][A-Za-z0-9_]*)\b").findall(text))
            vars_found = {v for v in vars_found if v not in {
                "page", "model", "section", "functions", "inject", "using", "await",
                "RenderBody", "RenderSection", "addTagHelper", "removeTagHelper", "inherits"
            }}

            if not vars_found:
                continue

            # Build lines we want to ensure exist
            desired_lines = [f"    var {v} = ViewBag.{v};" for v in sorted(vars_found)]

            # Decide insertion index: after @page/@model block at top
            lines = text.splitlines()
            insert_idx = 0
            for i, line in enumerate(lines[:50]):  # look near top only
                s = line.strip()
                if s.startswith("@page") or s.startswith("@model"):
                    insert_idx = i + 1

            # Check if any of these lines already exist (to avoid duplicates)
            existing_text_window = "\n".join(lines[: max(0, insert_idx + 30)])
            missing_lines = [ln for ln in desired_lines if ln.strip() not in existing_text_window]

            if not missing_lines:
                # Nothing to insert
                continue

            block = "@{\n" + "\n".join(missing_lines) + "\n}\n"

            # If there’s already a top @{ ... } block right after insert_idx, prefer
            # inserting our new block right after it (keeps a tidy header area).
            def find_top_razor_block_end(start_line_idx: int):
                # Find first "@{" after start_line_idx within first ~30 lines
                for j in range(start_line_idx, min(len(lines), start_line_idx + 30)):
                    if lines[j].lstrip().startswith("@{"):
                        # naive brace balance until matching "}"
                        balance = 0
                        started = False
                        for k in range(j, min(len(lines), j + 500)):
                            line = lines[k]
                            # Count braces (very simple; good enough for top metadata block)
                            balance += line.count("{")
                            balance -= line.count("}")
                            if not started:
                                started = True
                            if started and balance <= 0:
                                return k + 1  # insert after closing brace line
                return None

            after_header_block = find_top_razor_block_end(insert_idx)
            final_insert_idx = after_header_block if after_header_block is not None else insert_idx

            new_text = "\n".join(lines[:final_insert_idx]) + ("\n" if final_insert_idx else "") + block + "\n".join(
                lines[final_insert_idx:])

            f.write_text(new_text, encoding="utf-8")

    def _extract_data_attributes(self, html_content: str):
        """
        Extract all data-* attributes (e.g. data-theme, data-layout-width) from <html> or <body>
        and return them as a ViewBag assignment line.
        """

        try:
            soup = BeautifulSoup(html_content, "html.parser")
        except Exception:
            return []

        # Collect data attributes from <html> and <body>
        data_attrs = {}

        tag = soup.find("html")
        if tag:
            for attr, val in tag.attrs.items():
                if attr.startswith("data-"):
                    # Handle boolean or None-style attrs
                    value_str = val if val not in [True, None] else "true"
                    data_attrs[attr] = str(value_str).strip()

        if not data_attrs:
            return []

        # Join into HTML attribute syntax
        joined_attrs = " ".join(f"{k}={v}" for k, v in data_attrs.items())
        viewbag_line = f'    ViewBag.HTMLAttributes = "{joined_attrs}";'

        return viewbag_line

    def _convert_script_src_for_vite(self, html_content: str):
        try:
            soup = BeautifulSoup(html_content, "html.parser")
        except Exception:
            return html_content

        for script_tag in soup.find_all("script", src=True):
            src_val = script_tag["src"].strip()

            # Skip external or already-converted
            if script_tag.has_attr("vite-src") or src_val.startswith(("http://", "https://", "//")):
                continue

            # Remove leading ./ or ../
            normalized = re.sub(r"^(\.\./|\./)+", "", src_val)
            normalized = normalized.lstrip("/")

            lower = normalized.lower()

            # Strip ANY leading assets/, js/, scripts/
            if lower.startswith("assets/"):
                normalized = normalized[7:]
            elif lower.startswith("js/"):
                normalized = normalized[3:]
            elif lower.startswith("scripts/"):
                normalized = normalized[8:]

            # Build clean path
            normalized_path = f"Assets/{normalized}"

            # Remove accidental double slashes
            normalized_path = re.sub(r"/+", "/", normalized_path)

            # Placeholder (avoid BS rewriting "~")
            vite_placeholder = f"__VITE_PREFIX__{normalized_path}"
            script_tag["vite-src"] = vite_placeholder
            script_tag["type"] = "module"
            del script_tag["src"]

        html_fixed = str(soup)
        html_fixed = html_fixed.replace("__VITE_PREFIX__", "~/dist/")

        return html_fixed


class MVCGulpConverter(BaseMVCConverter):
    def __init__(self, config: ProjectConfig):
        super().__init__(config)

    def create_project(self):
        Log.project_start(self.project_name)
        self.init_create_project()

        if self.config.asset_paths:
            copy_assets(self.config.asset_paths, self.config.project_assets_path)
            replace_asset_paths(self.config.project_assets_path, '')

        add_gulpfile(self.config)

        update_package_json(self.config)

        copy_items(Path(self.config.src_path / "package-lock.json"), self.config.project_root_path)

        Log.project_end(self.project_name, str(self.config.project_root_path))


class MVCViteConverter(BaseMVCConverter):
    def __init__(self, config: ProjectConfig):
        super().__init__(config)

    def create_project(self):
        Log.project_start(self.project_name)
        self.init_create_project()

        if self.config.asset_paths:
            copy_items(Path(self.config.src_path / "public"), self.project_public_path, copy_mode="contents")
            public_only = copy_public_only_assets(self.config.asset_paths, self.project_public_path)
            copy_assets(self.config.asset_paths, self.config.project_assets_path, exclude=public_only)

        copy_items(Path(self.config.src_path / "package-lock.json"), self.config.project_root_path)

        sync_package_json(self.config, ignore=["scripts", "type", "devDependencies"])

        Log.project_end(self.project_name, str(self.config.project_root_path))


class MVCConverter:
    def __init__(self, config: ProjectConfig):
        self.config = config

        if self.config.frontend_pipeline == "gulp":
            MVCGulpConverter(self.config).create_project()
        else:
            MVCViteConverter(self.config).create_project()
