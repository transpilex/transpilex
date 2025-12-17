import re
import json
import subprocess
from pathlib import Path
from typing import Optional

from transpilex.config.base import PHP_VITE_CREATION_COMMAND
from transpilex.config.project import ProjectConfig
from transpilex.utils.assets import copy_assets, copy_public_only_assets
from transpilex.utils.extract_fragments import extract_fragments
from transpilex.utils.file import find_files_with_extension, copy_and_change_extension, move_files, copy_items
from transpilex.utils.git import remove_git_folders
from transpilex.utils.gulpfile import add_gulpfile
from transpilex.utils.logs import Log
from transpilex.utils.package_json import update_package_json
from transpilex.utils.replace_html_links import replace_html_links
from transpilex.utils.replace_variables import replace_variables
from transpilex.utils.template import replace_file_with_template


class BasePHPConverter:
    def __init__(self, config: ProjectConfig):
        self.config = config

    def _to_php_path(self, path: str) -> str:
        return path[:-5] + self.config.file_extension if path.endswith(".html") else path + self.config.file_extension

    def _parse_handlebars_params(self, param_str: Optional[str]) -> dict:
        """Convert 'key="value" another="123"' into {'key': 'value', 'another': '123'}"""
        if not param_str:
            return {}
        pairs = re.findall(r'(\w+)=["\']([^"\']+)["\']', param_str)
        return dict(pairs)

    def _replace_includes(self, content: str, file: Path) -> str:
        """Replace @@include(...) and {{> ...}} patterns with PHP includes."""

        # Extract both types using the same function
        fragments = []
        for label, pattern in self.config.import_patterns.items():
            fragments += extract_fragments(content, pattern, label)

        for frag in fragments:
            path = frag["path"]
            params_str = frag["params"]
            include_type = frag["type"]

            if include_type == "@@":
                if params_str:
                    try:
                        fixed_json = re.sub(r",\s*(?=[}\]])", "", params_str)
                        fixed_json = re.sub(r"'([^']*)'", r'"\1"', fixed_json)
                        params = json.loads(fixed_json)
                        php_vars = ''.join([f"${k} = {json.dumps(v)}; " for k, v in params.items()])
                        php_code = f"<?php {php_vars}include('{self._to_php_path(path)}'); ?>"
                    except json.JSONDecodeError as e:
                        Log.warning(f"[JSON Error] in file {file.name}: {e}")
                        php_code = f"<?php include('{self._to_php_path(path)}'); ?>"
                else:
                    php_code = f"<?php include('{self._to_php_path(path)}'); ?>"

            else:
                params = self._parse_handlebars_params(params_str)
                if params:
                    php_vars = ''.join([f"${k} = {repr(v)}; " for k, v in params.items()])
                    php_code = f"<?php {php_vars}include('./{str(self.config.project_partials_path).split('/')[-1]}/{path}.php'); ?>"
                else:
                    php_code = f"<?php include('./{str(self.config.project_partials_path).split('/')[-1]}/{path}.php'); ?>"

            content = content.replace(frag["full"], php_code)

        return content

    def _convert(self, folder_path):

        count = 0

        for file in folder_path.rglob(f"*{self.config.file_extension}"):
            if not file.is_file():
                continue

            # Read as UTF-8; silently skip if binary/non-UTF8
            try:
                with open(file, "r", encoding="utf-8") as f:
                    content = f.read()
            except (UnicodeDecodeError, OSError):
                continue

            original_content = content

            if self.config.frontend_pipeline == 'gulp':
                content = replace_html_links(content, self.config.file_extension)
            else:
                content = re.sub(
                    r"""(src\s*=\s*["'])((?:\.\./|\./|/)?(?:assets/)?)(images/[^"']+)""",
                    r'\1%BASE%/\3',
                    content,
                    flags=re.IGNORECASE
                )

                content = re.sub(
                    r"""(href\s*=\s*["'])((?:\.\./|\./|/)?(?:assets/)?)(images/[^"']+)""",
                    r'\1%BASE%/\3',
                    content,
                    flags=re.IGNORECASE
                )

                content = re.sub(
                    r"""(background(?:-image)?\s*:\s*url\((['"]?))((?:\.\./|\./|/)?(?:assets/)?)(images/[^'")]+)(['"]?\))""",
                    r'\1%BASE%/\4\5',
                    content,
                    flags=re.IGNORECASE
                )

                content = re.sub(
                    r"""(<script[^>]*src\s*=\s*["'])""" 
                    r"""(?!http:|https:|//|data:)"""
                    r"""((?:\.\./|\./|/)?(?:assets/)?)([^"']+\.js[^"']*)""",
                    r'\1/src/\3',
                    content,
                    flags=re.IGNORECASE
                )

                content = replace_html_links(content, '')

            if any(k in content for k in self.config.import_patterns.keys()):
                content = self._replace_includes(content, file)

            if content != original_content:
                try:
                    with open(file, "w", encoding="utf-8") as f:
                        f.write(content)
                    # Log.converted(str(file))
                    count += 1
                except Exception as e:
                    Log.error(f"Failed to write {file}: {e}")
            else:
                Log.warning(f"File was skipped (no patterns matched): {file}")

        Log.info(f"{count} files converted in {folder_path}")


class PHPGulpConverter(BasePHPConverter):
    def __init__(self, config: ProjectConfig):
        super().__init__(config)
        self.project_src_path = Path(self.config.project_root_path / 'src')

    def create_project(self):
        Log.project_start(self.config.project_name)

        files = find_files_with_extension(self.config.pages_path)
        copy_and_change_extension(files, self.config.pages_path, self.project_src_path, self.config.file_extension)

        self._convert(self.project_src_path)

        if self.config.partials_path:
            replace_variables(self.config.project_partials_path, self.config.variable_patterns,
                              self.config.variable_replacement, self.config.file_extension)

        if self.config.asset_paths:
            copy_assets(self.config.asset_paths, self.config.project_assets_path)

        add_gulpfile(self.config)

        update_package_json(self.config)

        copy_items(Path(self.config.src_path / "package-lock.json"), self.config.project_root_path)

        Log.project_end(self.config.project_name, str(self.config.project_root_path))


class PHPViteConverter(BasePHPConverter):
    def __init__(self, config: ProjectConfig):
        super().__init__(config)
        self.project_pages_path = Path(self.config.project_root_path / "pages")
        self.project_public_path = Path(self.config.project_root_path / "public")
        self.project_routes_path = Path(self.config.project_root_path / "configs" / "routes.php")

    def create_project(self):

        Log.project_start(self.config.project_name)

        try:
            self.config.project_root_path.mkdir(parents=True, exist_ok=True)

            subprocess.run(PHP_VITE_CREATION_COMMAND, cwd=self.config.project_root_path, check=True,
                           capture_output=True, text=True)

            Log.success("PHP project created successfully")

            remove_git_folders(self.config.project_root_path)

        except subprocess.CalledProcessError:
            Log.error("PHP project creation failed")
            return

        files = find_files_with_extension(self.config.pages_path, "html")
        copy_and_change_extension(files, self.config.pages_path, self.project_pages_path, self.config.file_extension)

        self._convert(self.project_pages_path)
        self._convert(self.config.project_partials_path)

        if self.config.partials_path:
            move_files(Path(self.project_pages_path / "partials"), self.config.project_partials_path)
            replace_variables(self.config.project_partials_path, self.config.variable_patterns,
                              self.config.variable_replacement, self.config.file_extension)

        if self.config.asset_paths:
            copy_items(Path(self.config.src_path / "public"), self.config.project_root_path)
            public_only = copy_public_only_assets(self.config.asset_paths, self.project_public_path)
            copy_assets(self.config.asset_paths, self.config.project_assets_path, exclude=public_only)

        update_package_json(self.config,
                            overrides={
                                "scripts": {
                                    "dev": "vite",
                                    "build": "tsc --noEmit && vite build",
                                    "composer": "php ./bin/composer.phar"
                                }})

        copy_items(Path(self.config.src_path / "package-lock.json"), self.config.project_root_path)

        if self.config.ui_library == "tailwind":
            replace_file_with_template(Path(__file__).parent.parent / "templates" / "php-tw-vite.config.js",
                                       self.config.project_root_path / "vite.config.js")

        self._generate_routes_php(self.project_pages_path, self.project_routes_path)

        Log.project_end(self.config.project_name, str(self.config.project_root_path))

    def _generate_routes_php(self, pages_folder: Path, output_file: Path):
        """
        Generate a complete routes.php file for FastRoute using PHP page files.

        Args:
            pages_folder (Path): Folder containing PHP page files (e.g. 'pages/').
            output_file (Path): Path to routes.php file to generate.
        """

        pages_folder = Path(pages_folder)
        output_file = Path(output_file)

        if not pages_folder.exists() or not pages_folder.is_dir():
            Log.error(f"Pages folder not found: {pages_folder}")
            return

        php_files = sorted([f for f in pages_folder.glob("*.php") if f.is_file()])
        if not php_files:
            Log.warning(f"No PHP files found in {pages_folder}")
            return

        route_lines = []
        for php_file in php_files:
            file_name = php_file.stem
            if file_name == "index":
                continue
            route_path = f"/{file_name}"
            route_lines.append(
                f"\t$r->addRoute('GET', '{route_path}', function ($ROUTE_PARAMS) {{\n"
                f"\t\tinclude('pages/{php_file.name}');\n"
                f"\t}});\n"
            )

        routes_php = f"""<?php

$dispatcher = FastRoute\\simpleDispatcher(function (FastRoute\\RouteCollector $r) {{
\t$r->addRoute('GET', '/', function ($ROUTE_PARAMS) {{
\t\tinclude('pages/index.php');
\t}});
{"".join(route_lines)}
}});

// Fetch method and URI from somewhere
$httpMethod = $_SERVER['REQUEST_METHOD'];
$uri = $_SERVER['REQUEST_URI'];

// Strip query string (?foo=bar) and decode URI
if (false !== $pos = strpos($uri, '?')) {{
\t$uri = substr($uri, 0, $pos);
}}
$uri = rawurldecode($uri);

$routeInfo = $dispatcher->dispatch($httpMethod, $uri);
switch ($routeInfo[0]) {{
\tcase FastRoute\\Dispatcher::NOT_FOUND:
\t\thttp_response_code(404);
\t\tdie('Not found...');
\t\tbreak;
\tcase FastRoute\\Dispatcher::FOUND:
\t\t$routeInfo[1]($routeInfo[2]);
\t\tbreak;
}}
    """

        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(routes_php, encoding="utf-8")

        Log.info(f"{len(route_lines)} routes generated in {output_file}")


class PHPConverter:
    def __init__(self, config: ProjectConfig):
        self.config = config

        if self.config.frontend_pipeline == "gulp":
            PHPGulpConverter(self.config).create_project()
        else:
            PHPViteConverter(self.config).create_project()
