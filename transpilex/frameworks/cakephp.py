import os
import json
import re
import subprocess
import html
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString

from transpilex.config.base import CAKEPHP_PROJECT_CREATION_COMMAND
from transpilex.config.project import ProjectConfig
from transpilex.utils.assets import copy_assets, replace_asset_paths, clean_relative_asset_paths
from transpilex.utils.casing import apply_casing
from transpilex.utils.file import find_files_with_extension, copy_and_change_extension, move_files, copy_items
from transpilex.utils.git import remove_git_folders
from transpilex.utils.gulpfile import add_gulpfile
from transpilex.utils.logs import Log
from transpilex.utils.package_json import update_package_json
from transpilex.utils.replace_html_links import replace_html_links
from transpilex.utils.replace_variables import replace_variables


class BaseCakePHPConverter:
    def __init__(self, config: ProjectConfig):
        self.config = config

        self.project_pages_path = Path(self.config.project_root_path / "templates" / "Pages")
        self.project_partials_path = Path(self.config.project_root_path / "templates" / "element")

    def init_create_project(self):
        try:
            self.config.project_root_path.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                CAKEPHP_PROJECT_CREATION_COMMAND,
                cwd=self.config.project_root_path,
                check=True,
                capture_output=True, text=True)

            Log.success("CakePHP project created successfully")

            remove_git_folders(self.config.project_root_path)

        except subprocess.CalledProcessError:
            Log.error("CakePHP project creation failed")
            return

        files = find_files_with_extension(self.config.pages_path, "html")
        copy_and_change_extension(files, self.config.pages_path, self.project_pages_path, self.config.file_extension)

        self._convert()

        self._rename_hyphens_to_underscores()

        if self.config.partials_path:
            move_files(self.project_pages_path / "partials", self.project_partials_path)
            replace_variables(self.project_partials_path, self.config.variable_patterns,
                              self.config.variable_replacement, self.config.file_extension)

    def _convert(self):
        count = 0

        for file in self.project_pages_path.rglob(f"*{self.config.file_extension}"):

            if not file.is_file():
                continue

            try:
                original_content = file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            soup = BeautifulSoup(original_content, "html.parser")

            out = str(soup)

            out = clean_relative_asset_paths(out)
            out = self._replace_all_includes(out).strip()
            out = replace_html_links(out, '')

            file.write_text(out.strip(), encoding="utf-8")

            Log.converted(f"{file}")
            count += 1

        Log.info(f"{count} files converted in {self.project_pages_path}")

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

    def _replace_all_includes(self, content: str):
        """
        Converts @@include(...) and {{> ...}} / {{&gt; ...}} to CakePHP:
            <?= $this->element('name', ['key' => 'value']) ?>
        where ONLY the file/partial name is used (no layouts/partials/ paths).
        """

        fragments = []

        # Extract include patterns
        for label, pattern in self.config.import_patterns.items():
            pattern_str = pattern.pattern

            # Accept > or &gt;
            pattern_str = pattern_str.replace(r"\>\s*", r"(?:>|&gt;)\s*")
            pattern_str = pattern_str.replace(r">\s*", r"(?:>|&gt;)\s*")

            alt_pattern = re.compile(pattern_str)

            for match in alt_pattern.finditer(content):
                fragments.append({
                    "label": label,
                    "full": match.group(0),
                    "path": match.group("path"),
                    "params": match.groupdict().get("params", "")
                })

        # Process fragments
        for frag in fragments:
            raw_path = frag["path"]
            params_raw = frag["params"]

            # Remove ./ , ../
            clean_path = re.sub(r"^(\.\/|\.\.\/)+", "", raw_path)

            # Remove extension (.html / .php)
            clean_path = Path(clean_path).stem

            # Use only FILENAME (no directory)
            filename_only = clean_path.split("/")[-1]

            # Convert name to snake_case
            filename_only = apply_casing(filename_only, "snake")

            # Parse params
            params = self._parse_include_params(params_raw)

            if params:
                param_pairs = []
                for k, v in params.items():
                    if isinstance(v, str):
                        param_pairs.append(f"'{k}' => '{v}'")
                    else:
                        param_pairs.append(f"'{k}' => {str(v).lower()}")
                param_str = ", ".join(param_pairs)

                replacement = f"<?= $this->element('{filename_only}', [{param_str}]) ?>"
            else:
                replacement = f"<?= $this->element('{filename_only}') ?>"

            content = content.replace(frag["full"], replacement)

        return content

    # def _convert(self):
    #
    #     count = 0
    #
    #     for file in self.project_pages_path.rglob(f"*{self.config.file_extension}"):
    #         if not file.is_file():
    #             continue
    #
    #         # Read as UTF-8; silently skip if binary/non-UTF8
    #         try:
    #             with open(file, "r", encoding="utf-8") as f:
    #                 content = f.read()
    #         except (UnicodeDecodeError, OSError):
    #             continue
    #
    #         original_content = content
    #
    #         content = replace_html_links(content, '')
    #
    #         if any(k in content for k in self.config.import_patterns.keys()):
    #             content = self._replace_includes(content, file)
    #
    #         if content != original_content:
    #             try:
    #                 with open(file, "w", encoding="utf-8") as f:
    #                     f.write(content)
    #                 Log.converted(str(file))
    #                 count += 1
    #             except Exception as e:
    #                 Log.error(f"Failed to write {file}: {e}")
    #         else:
    #             Log.warning(f"File was skipped (no patterns matched): {file}")
    #
    #     Log.info(f"{count} files converted in {self.project_pages_path}")
    #
    # def _parse_handlebars_params(self, param_str: Optional[str]):
    #     """Convert 'key="value" another="123"' into {'key': 'value', 'another': '123'}"""
    #     if not param_str:
    #         return {}
    #     pairs = re.findall(r'(\w+)=["\']([^"\']+)["\']', param_str)
    #     return dict(pairs)
    #
    # def _replace_includes(self, content: str, file: Path):
    #     """Replace @@include(...) and {{> ...}} patterns with CakePHP element calls."""
    #
    #     fragments = []
    #     for label, pattern in self.config.import_patterns.items():
    #         fragments += extract_fragments(content, pattern, label)
    #
    #     for frag in fragments:
    #         path = frag["path"]
    #         params_str = frag["params"]
    #         include_type = frag["type"]
    #
    #         # Normalize path: remove .html extension for CakePHP
    #         element_name = path.replace(".html", "").replace(".php", "")
    #
    #         if include_type == "@@":
    #             if params_str:
    #                 try:
    #                     # Cleanup JSON (same as your PHP version)
    #                     fixed_json = re.sub(r",\s*(?=[}\]])", "", params_str)
    #                     fixed_json = re.sub(r"'([^']*)'", r'"\1"', fixed_json)
    #                     params = json.loads(fixed_json)
    #
    #                     # Convert dict → CakePHP array syntax
    #                     cake_params = ', '.join([f"'{k}' => {repr(v)}" for k, v in params.items()])
    #                     php_code = f"<?= $this->element('{element_name}', [{cake_params}]) ?>"
    #
    #                 except json.JSONDecodeError as e:
    #                     Log.warning(f"[JSON Error] in file {file.name}: {e}")
    #                     php_code = f"<?= $this->element('{element_name}') ?>"
    #
    #             else:
    #                 php_code = f"<?= $this->element('{element_name}') ?>"
    #
    #         else:
    #             params = self._parse_handlebars_params(params_str)
    #             if params:
    #                 cake_params = ', '.join([f"'{k}' => {repr(v)}" for k, v in params.items()])
    #                 php_code = f"<?= $this->element('{element_name}', [{cake_params}]) ?>"
    #
    #             else:
    #                 php_code = f"<?= $this->element('{element_name}') ?>"
    #
    #         content = content.replace(frag["full"], php_code)
    #
    #     return content

    def _rename_hyphens_to_underscores(self, ignore_list=None):
        if ignore_list is None:
            ignore_list = []

        for dirpath, dirnames, filenames in os.walk(self.project_pages_path, topdown=False):
            # Rename files
            for name in filenames:
                if name in ignore_list:
                    continue
                if "-" in name:
                    src = Path(dirpath) / name
                    dst_name = name.replace("-", "_")
                    if dst_name in ignore_list:
                        continue
                    dst = Path(dirpath) / dst_name
                    src.rename(dst)

            # Rename directories
            for name in dirnames:
                if name in ignore_list:
                    continue
                if "-" in name:
                    src = Path(dirpath) / name
                    dst_name = name.replace("-", "_")
                    if dst_name in ignore_list:
                        continue
                    dst = Path(dirpath) / dst_name
                    src.rename(dst)


class CakePHPGulpConverter(BaseCakePHPConverter):
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


class CakePHPConverter:
    def __init__(self, config: ProjectConfig):
        self.config = config

        if self.config.frontend_pipeline == "gulp":
            CakePHPGulpConverter(self.config).create_project()
