import subprocess
from pathlib import Path
from transpilex.config.project import ProjectConfig
from transpilex.utils.logs import Log
from transpilex.config.base import SYMFONY_PROJECT_CREATION_COMMAND
from transpilex.utils.git import remove_git_folders
from transpilex.utils.file import copy_items
from transpilex.utils.gulpfile import add_gulpfile
from transpilex.utils.package_json import update_package_json
from transpilex.utils.assets import copy_assets, replace_asset_paths


class BaseSymfonyConverter:
    def __init__(self, config: ProjectConfig):
        self.config = config

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


class SymfonyGulpConverter(BaseSymfonyConverter):
    def __init__(self, config: ProjectConfig):
        super().__init__(config)

    def create_project(self):
        Log.project_start(self.config.project_name)

        self.init_create_project()

        if self.config.asset_paths:
            copy_assets(self.config.asset_paths, self.config.project_assets_path)
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
