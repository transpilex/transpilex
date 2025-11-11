import re
import os
import json
import html
import subprocess
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString

from transpilex.config.base import ROR_VITE_PROJECT_CREATION_COMMAND, ROR_PROJECT_CREATION_COMMAND
from transpilex.config.project import ProjectConfig
from transpilex.utils.assets import copy_assets, replace_asset_paths, copy_public_only_assets
from transpilex.utils.file import move_files, rename_item, copy_items
from transpilex.utils.git import remove_git_folders
from transpilex.utils.gulpfile import add_gulpfile
from transpilex.utils.logs import Log
from transpilex.utils.package_json import update_package_json
from transpilex.utils.replace_variables import replace_variables
from transpilex.utils.restructure import restructure_and_copy_files


class BaseRorConverter:
    def __init__(self, config: ProjectConfig):
        self.config = config
        self.project_views_path = Path(self.config.project_root_path / "app" / "views")
        self.project_partials_path = Path(self.project_views_path / "layouts" / "partials")
        self.project_public_path = Path(self.config.project_root_path / "public")
        self.project_controllers_path = Path(self.config.project_root_path / "app" / "controllers")
        self.project_routes_path = Path(self.config.project_root_path / "config" / "routes.rb")
        self.project_config_deploy_path = Path(self.config.project_root_path / "config" / "deploy.yml")

        self.route_map = None

    def init_create_project(self):
        try:
            self.config.project_root_path.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                ROR_VITE_PROJECT_CREATION_COMMAND if self.config.frontend_pipeline == 'vite' else ROR_PROJECT_CREATION_COMMAND,
                cwd=self.config.project_root_path,
                check=True,
                capture_output=True, text=True)

            Log.success("RoR project created successfully")

            remove_git_folders(self.config.project_root_path)

            try:
                content = self.project_config_deploy_path.read_text(encoding="utf-8")
                content = content.replace("project_name", self.config.project_name)
                self.project_config_deploy_path.write_text(content, encoding="utf-8")

            except (UnicodeDecodeError, OSError):
                Log.error("Error changing project_name in _ViewImports.csproj")

        except subprocess.CalledProcessError:
            Log.error("RoR project creation failed")
            return

        rename_item(Path(self.project_views_path / "layouts"), "shared")

        self.route_map = restructure_and_copy_files(
            self.config,
            self.project_views_path,
            self.config.file_extension,
            case_style="snake"
        )

        rename_item(Path(self.project_views_path / "layouts"), "layouts-eg")
        rename_item(Path(self.project_views_path / "shared"), "layouts")

        self._convert()

        if self.config.partials_path:
            move_files(self.project_views_path / "partials", self.project_partials_path)
            replace_variables(self.project_partials_path, self.config.variable_patterns,
                              self.config.variable_replacement, self.config.file_extension)

        self._create_controllers()

    def _convert(self):
        """Convert files inside RoR views directory."""
        count = 0

        for file in self.project_views_path.rglob(f"*{self.config.file_extension}"):
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

            placeholder_map = {}

            def _protect_erb(mm):
                key = f"__ERB_{len(placeholder_map)}__"
                placeholder_map[key] = mm.group(0)
                return key

            # Protect ERB tags <%= %> and <% %>
            protected_content = re.sub(r"<%[=\-]?.*?%>", _protect_erb, original_content, flags=re.DOTALL)

            soup = BeautifulSoup(protected_content, "html.parser")
            is_partial = "partials" in file.parts

            if is_partial:
                # Convert partials
                out = str(soup)

                # Restore original <%= ... %> blocks
                for key, original in placeholder_map.items():
                    out = out.replace(key, original)

                out = self._replace_all_includes_with_erb(out)
                out = self._replace_asset_image_paths(out)
                out = self._replace_anchor_links_with_routes(out, self.route_map)
                file.write_text(out, encoding="utf-8")

                Log.converted(f"{file}")
                count += 1
                continue

            # Collect <link> tags
            links_html = "\n".join(f"    {str(tag)}" for tag in soup.find_all("link"))
            for tag in soup.find_all("link"):
                tag.decompose()

            # Collect <script> tags
            scripts_html_list = []
            for script_tag in soup.find_all("script"):
                src = script_tag.get("src")
                if src:
                    scripts_html_list.append(f"    {str(script_tag)}")
                script_tag.decompose()

            scripts_output = "\n".join(scripts_html_list)

            # Find main content region
            content_div = soup.find(attrs={"data-content": True})
            if content_div:
                body_html = content_div.decode_contents()
            elif soup.body:
                body_html = soup.body.decode_contents()
            else:
                body_html = str(soup)

            # Restore <%= ... %> in body_html
            for key, original in placeholder_map.items():
                body_html = body_html.replace(key, original)

            main_content = self._replace_all_includes_with_erb(body_html).strip()

            html_attr_section = self._extract_html_data_attributes(original_content)

            # Build ERB output
            erb_output = f"""<% @title = "{layout_title}" %>

    {html_attr_section}

    <% content_for :styles do %>
    {links_html}
    <% end %>

    <% content_for :content do %>
    {main_content}
    <% end %>

    <% content_for :scripts do %>
    {scripts_output}
    <% end %>
    """

            final = self._replace_asset_image_paths(erb_output)
            final = self._replace_anchor_links_with_routes(final, self.route_map)
            file.write_text(final.strip() + "\n", encoding="utf-8")

            Log.converted(f"{file}")
            count += 1

        Log.info(f"{count} files converted in {self.project_views_path}")

    def _parse_include_params(self, raw: str):
        """Parse JSON, key="value" Handlebars-style params, or other formats."""
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

        kv_pairs = re.findall(r"(\w+)=[\"']([^\"']+)[\"']", raw)
        if kv_pairs:
            return {k: v for k, v in kv_pairs}

        return {}

    def _replace_all_includes_with_erb(self, content: str):
        """
        Converts @@include(...) and {{> ...}} / {{&gt; ...}} to ERB <%= render ... %>,
        auto-prepending 'layouts/partials/' for all partial references.
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

            # Case 1: partials/... → layouts/partials/...
            if clean_path.startswith("partials/"):
                clean_path = clean_path.replace("partials/", "layouts/partials/", 1)
            # Case 2: top-level includes (no folder)
            elif "/" not in clean_path:
                clean_path = f"layouts/partials/{clean_path}"
            # Case 3: already under layouts/partials
            elif clean_path.startswith("layouts/partials/"):
                pass  # already correct

            # Skip title includes (they go into @title)
            if Path(clean_path).name.lower() in {"title-meta", "app-meta-title", "title_meta", "app_meta_title"}:
                content = content.replace(frag["full"], "")
                continue

            params = self._parse_include_params(params_raw)
            if params:
                # Format as Ruby hash syntax
                param_pairs = [f"{k}: '{v}'" if isinstance(v, str) else f"{k}: {str(v).lower()}"
                               for k, v in params.items()]
                param_str = ", ".join(param_pairs)
                replacement = f"<%= render '{clean_path}', {param_str} %>"
            else:
                replacement = f"<%= render '{clean_path}' %>"

            content = content.replace(frag["full"], replacement)

        return content

    def _replace_anchor_links_with_routes(self, content: str, route_map: dict[str, str]):
        """
        Replace <a href="filename.html"> with Rails url_for helper:
        href="<%= url_for :controller => '...', :action => '...' %>"
        """
        if not route_map:
            return content

        pattern = re.compile(r'href=["\'](?P<href>[^"\']+\.html)["\']', re.IGNORECASE)

        def repl(match):
            href_val = match.group("href")
            href_file = Path(href_val).name

            if href_file in route_map:
                route_path = route_map[href_file].lstrip("/")
                parts = route_path.split("/")
                controller = parts[0] if len(parts) >= 1 else "application"
                action = parts[1] if len(parts) >= 2 else "index"

                # Prefix if numeric action
                if re.match(r"^\d", action):
                    action = f"{controller}_{action}"

                return f'href="<%= url_for :controller => \'{controller}\', :action => \'{action}\' %>"'

            return match.group(0)

        return pattern.sub(repl, content)

    def _extract_html_data_attributes(self, html_content: str):
        """
        Extracts all attributes from the <html> tag that start with 'data-'
        and returns them formatted for ERB content_for.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        html_tag = soup.find("html")
        if not html_tag:
            return ""

        attrs = [f'{k}="{v}"' for k, v in html_tag.attrs.items() if k.startswith("data-")]
        if not attrs:
            return ""

        attrs_str = " ".join(attrs)
        return f"<% content_for :html_attribute do %>\n{attrs_str}\n<% end %>"

    def _replace_asset_image_paths(self, content: str):
        """
        Convert static asset paths like ./assets/... or ../assets/... in:
          - <img src="...">
          - <link href="...">
          - background-image: url(...)
        to Rails vite_asset_path or asset_path helpers.
        """

        # Pattern for <img src="...">
        img_pattern = re.compile(
            r'<img\s+([^>]*?)src\s*=\s*["\'](?:\.{0,2}/)?assets/(?P<path>[^"\']+)["\']([^>]*?)>',
            flags=re.IGNORECASE | re.DOTALL
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

        # Replace <img> tags with vite_asset_path helper
        def repl_img(match):
            before = match.group(1)
            after = match.group(3)
            img_path = match.group("path").lstrip("/")

            # Extract alt text if present
            alt_match = re.search(r'alt\s*=\s*["\']([^"\']+)["\']', before + after)
            alt_text = alt_match.group(1) if alt_match else ""

            # Extract class if present
            class_match = re.search(r'class\s*=\s*["\']([^"\']+)["\']', before + after)
            class_text = class_match.group(1) if class_match else ""

            # Build the image tag
            result = f"<img src=\"<%= vite_asset_path '{img_path}' %>\""
            if alt_text:
                result += f' alt="{alt_text}"'
            if class_text:
                result += f' class="{class_text}"'

            # Preserve other attributes
            other_attrs = re.sub(r'(src|alt|class)\s*=\s*["\'][^"\']*["\']', '', before + after)
            other_attrs = other_attrs.strip()
            if other_attrs:
                result += f' {other_attrs}'

            result += '>'
            return result

        # Replace in <link href="...">
        def repl_link(match):
            link_path = match.group("path").lstrip("/")
            return f'href="<%= vite_asset_path \'{link_path}\' %>"'

        # Replace in CSS url(...)
        def repl_css(match):
            css_path = match.group("path").lstrip("/")
            return f'url(<%= vite_asset_path \'{css_path}\' %>)'

        # Apply all replacements
        content = img_pattern.sub(repl_img, content)
        content = link_pattern.sub(repl_link, content)
        content = css_pattern.sub(repl_css, content)

        return content

    def _get_route_for_file(self, file: Path):
        """
        Match the .html.erb file to its route_map entry using full relative path comparison.
        Returns the Rails-style route path.
        """
        try:
            # Compute file path relative to views folder (e.g., apps/email.html.erb)
            rel_path = file.relative_to(self.project_views_path)
            rel_html = str(rel_path.with_suffix("").with_suffix("").with_suffix(".html")).replace("\\", "/")

            # Normalize to snake_case for comparison
            normalized_html = rel_html.replace("_", "-").lower()

            # Direct match in route_map keys
            for html_name, route in self.route_map.items():
                html_key = html_name.lower()
                if normalized_html == html_key or normalized_html.endswith(html_key):
                    if route == "/index":
                        return "/"
                    # Convert to snake_case for Rails
                    return route.replace("-", "_")

            # Fallback: construct from path structure
            snake_parts = "/".join([apply_casing(p, "snake") for p in rel_path.with_suffix("").with_suffix("").parts])
            route_guess = "/" + snake_parts
            return route_guess

        except Exception:
            return "/"

    def _create_controller_file(self, path: Path, controller_name: str, actions: list):
        """
        Creates a Rails controller Ruby file with appropriate action methods.
        - Adds render template for each action
        - Prefixes controller name for numeric actions
        """

        class_name = "".join(word.capitalize() for word in controller_name.split("_")) + "Controller"

        methods = ""
        for action_name, view_path, is_nested, route_path in actions:
            # Prefix if action starts with a number
            if re.match(r"^\d", action_name):
                action_name = f"{controller_name}_{action_name}"

            methods += f"  def {action_name}\n"
            methods += f"    render template: '{view_path}'\n"
            methods += "  end\n\n"

        controller_code = f"""class {class_name} < ApplicationController
    {methods.strip()}
    end
    """

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(controller_code, encoding="utf-8")

    def _create_controllers(self, ignore_list=None):
        """
        Generate Rails controllers based on view file structure.
        Follows Rails conventions and organizes by resource/namespace.
        """
        ignore_list = ignore_list or ["layouts", "layouts-eg", "partials", "shared"]

        # Clean up existing controllers (except application_controller.rb)
        if self.project_controllers_path.exists():
            for item in self.project_controllers_path.iterdir():
                if item.name != "application_controller.rb" and item.name != "concerns":
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)

        self.project_controllers_path.mkdir(parents=True, exist_ok=True)

        controllers_actions = {}

        # Scan view directories
        for controller_folder in self.project_views_path.iterdir():
            if not controller_folder.is_dir():
                continue

            controller_name = controller_folder.name
            if controller_name in ignore_list:
                continue

            actions = []

            # Process all .html.erb files in this controller's views
            for file in controller_folder.rglob("*.html.erb"):
                # Skip partials (files starting with _)
                if file.name.startswith("_"):
                    continue

                # Calculate relative path from controller folder
                rel_path = file.relative_to(controller_folder)
                path_parts = list(rel_path.with_suffix("").with_suffix("").parts)

                # Determine if nested (in subdirectory)
                is_nested = len(path_parts) > 1

                # Action name: join path parts with underscore
                action_name = "_".join(path_parts) if is_nested else path_parts[0]

                # View path for documentation
                view_path = f"{controller_name}/{'/'.join(path_parts)}"

                # Get route from route_map
                route_path = self._get_route_for_file(file)

                actions.append((action_name, view_path, is_nested, route_path))

            if actions:
                controller_file_name = f"{controller_name}_controller.rb"
                controller_file_path = self.project_controllers_path / controller_file_name

                self._create_controller_file(controller_file_path, controller_name, actions)
                controllers_actions[controller_name] = actions

                Log.created(str(controller_file_path))

        # Generate routes
        self._create_routes(controllers_actions)

        Log.info(f"Generated {len(controllers_actions)} controllers with routes")

    def _create_routes(self, controllers_actions: dict):
        """
        Generate Rails routes in explicit `get "path", to: 'controller#action'` form.
        """
        route_lines = []
        route_lines.append("\n  # Generated routes from HTML templates")

        for controller_name, actions in sorted(controllers_actions.items()):
            route_lines.append(f"\n  # {controller_name.capitalize()} routes")

            for action_name, view_path, is_nested, route_path in sorted(actions, key=lambda x: x[0]):
                if re.match(r"^\d", action_name):
                    action_name = f"{controller_name}_{action_name}"

                # Clean route path
                if route_path == "/":
                    route_lines.append(f"  root '{controller_name}#{action_name}'")
                    continue

                url_path = route_path.lstrip("/")

                # Handle case like ecommerce/product-grid
                route_lines.append(
                    f"  get \"{url_path}\", to: '{controller_name}#{action_name}'"
                )

        # Inject into routes.rb
        routes_content = self.project_routes_path.read_text(encoding="utf-8")

        if "Rails.application.routes.draw do" in routes_content:
            lines = routes_content.split("\n")
            insert_index = len(lines) - 1
            for i in range(len(lines) - 1, -1, -1):
                if lines[i].strip() == "end":
                    insert_index = i
                    break
            lines[insert_index:insert_index] = route_lines
            new_content = "\n".join(lines)
        else:
            new_content = f"""Rails.application.routes.draw do
    {chr(10).join(route_lines)}
    end
    """

        self.project_routes_path.write_text(new_content, encoding="utf-8")
        Log.updated(f"Routes generated in {self.project_routes_path}")


class RorGulpConverter(BaseRorConverter):
    def __init__(self, config: ProjectConfig):
        super().__init__(config)

    def create_project(self):
        Log.project_start(self.config.project_name)
        self.init_create_project()

        if self.config.asset_paths:
            copy_assets(self.config.asset_paths, self.config.project_assets_path)
            replace_asset_paths(self.config.project_assets_path, '')

        add_gulpfile(self.config)

        update_package_json(self.config)

        copy_items(Path(self.config.src_path / "package-lock.json"), self.config.project_root_path)

        Log.project_end(self.config.project_name, str(self.config.project_root_path))


class RorViteConverter(BaseRorConverter):
    def __init__(self, config: ProjectConfig):
        super().__init__(config)

    def create_project(self):
        Log.project_start(self.config.project_name)
        self.init_create_project()

        if self.config.asset_paths:
            copy_items(Path(self.config.src_path / "public"), self.project_public_path, copy_mode="contents")
            public_only = copy_public_only_assets(self.config.asset_paths, self.project_public_path)
            copy_assets(self.config.asset_paths, self.config.project_assets_path, exclude=public_only)
            copy_items(Path(self.project_public_path / "images"), self.config.project_assets_path)

        update_package_json(self.config)

        copy_items(Path(self.config.src_path / "package-lock.json"), self.config.project_root_path)

        Log.project_end(self.config.project_name, str(self.config.project_root_path))


class RorConverter:
    def __init__(self, config: ProjectConfig):
        self.config = config

        if self.config.frontend_pipeline == "gulp":
            RorGulpConverter(self.config).create_project()
        else:
            RorViteConverter(self.config).create_project()
