import json
import re
import html
from pathlib import Path
from bs4 import BeautifulSoup
from cookiecutter.main import cookiecutter

from transpilex.config.base import CODEIGNITER_ASSETS_PRESERVE, CODEIGNITER_COOKIECUTTER_REPO
from transpilex.config.project import ProjectConfig
from transpilex.utils.assets import copy_assets, replace_asset_paths, clean_relative_asset_paths
from transpilex.utils.file import copy_items, find_files_with_extension, copy_and_change_extension, file_exists
from transpilex.utils.gulpfile import has_plugins_config
from transpilex.utils.logs import Log
from transpilex.utils.package_json import sync_package_json
from transpilex.utils.replace_html_links import replace_html_links
from transpilex.utils.replace_variables import replace_variables


class BaseYiiConverter:
    def __init__(self, config: ProjectConfig):
        self.config = config
        self.project_templates_path = Path(self.config.project_root_path / "src" / "Web" / "Pages" / "templates")


class YiiGulpConverter(BaseYiiConverter):
    pass


class YiiConverter:
    def __init__(self, config: ProjectConfig):
        self.config = config

        if self.config.frontend_pipeline == "gulp":
            YiiGulpConverter(self.config).create_project()
