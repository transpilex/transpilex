from pathlib import Path

from transpilex.cli.prompts import ask_project_config
from transpilex.config.project import ProjectConfig
from transpilex.frameworks.cakephp import CakePHPConverter
from transpilex.frameworks.core import CoreConverter
from transpilex.frameworks.django import DjangoConverter
from transpilex.frameworks.laravel import LaravelConverter
from transpilex.frameworks.mvc import MVCConverter
from transpilex.frameworks.php import PHPConverter
from transpilex.frameworks.ror import RorConverter
from transpilex.utils.pattern import load_compiled_patterns, load_variable_patterns


def main():
    project_config = ask_project_config()
    if project_config is None:
        return

    config = ProjectConfig(
        project_name=project_config["project_name"],
        framework=project_config["framework"],
        ui_library=project_config["ui_library"],
        frontend_pipeline=project_config["frontend_pipeline"],
        src_path=Path(project_config["src_path"]).resolve(),
        asset_paths=project_config["asset_paths"],
        partials_path=project_config["partials_path"],
        dest_path=project_config["dest_path"],
        pages_path=project_config["pages_path"],
        project_root_path=project_config["project_root_path"],
        project_assets_path=project_config["project_assets_path"],
        project_partials_path=project_config["project_partials_path"],
        use_auth=project_config["use_auth"],
        import_patterns=load_compiled_patterns(),
        variable_patterns=load_variable_patterns(),
        variable_replacement=project_config["variable_replacement"],
        file_extension=project_config["file_extension"],
        gulp_config=project_config["gulp_config"],
    )

    if project_config["framework"] == "php":
        PHPConverter(config)
    elif project_config["framework"] == "laravel":
        LaravelConverter(config)
    elif project_config["framework"] == "django":
        DjangoConverter(config)
    elif project_config["framework"] == "core":
        CoreConverter(config)
    elif project_config["framework"] == "mvc":
        MVCConverter(config)
    elif project_config["framework"] == "ror":
        RorConverter(config)
    elif project_config["framework"] == "cakephp":
        CakePHPConverter(config)
